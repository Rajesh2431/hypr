#!/usr/bin/env python3
"""Privacy indicator for Waybar (custom module, JSON). Replaces Waybar's built-in
"privacy" module, which crashes Waybar on the second config reload (SIGUSR2).

Shows an orange mic while an app records audio (cava/visualizers and monitor
sources ignored) and a screen icon while the screen is shared (Hyprland
"screencast" event). Prints empty text (= hidden) otherwise.
"""
# die with the parent (waybar / quickshell), and make our own long-running
# children (pactl subscribe, nmcli monitor, dbus-monitor, ...) die with us
import ctypes as _ctypes, signal as _signal
def _pdeathsig():
    try:
        _ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, _signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:
        pass
_pdeathsig()

import html
import json
import os
import select
import socket
import subprocess
import sys
import time

I_MIC, I_SCREEN, I_CAM = "\U000f036c", "\U000f0379", "\U000f0100"
PUNK = os.environ.get("PUNK_ICONS") == "1"   # Spider-Punk layout: a red "ON AIR" tag in front of the icons
import glob


def camera_users():
    """Apps that have a webcam (/dev/video*) open. Only our own processes are readable, which is
    what matters on a desktop. Empty when there is no camera."""
    vids = set(glob.glob("/dev/video*"))
    if not vids:
        return []
    apps = []
    for fd_dir in glob.glob("/proc/[0-9]*/fd"):
        try:
            if any(os.readlink(os.path.join(fd_dir, f)) in vids for f in os.listdir(fd_dir)):
                pid = fd_dir.split("/")[2]
                with open(f"/proc/{pid}/comm") as fh:
                    name = fh.read().strip()
                if name not in apps and name not in ("wireplumber", "pipewire"):
                    apps.append(name)
        except OSError:
            continue
    return apps
IGNORE = {"cava", "cavasik", "pavucontrol", "peak meter"}


def recorders():
    try:
        outs = json.loads(subprocess.run(["pactl", "-f", "json", "list", "source-outputs"],
                                         capture_output=True, text=True, timeout=3).stdout or "[]")
        sources = {s["index"]: s for s in json.loads(subprocess.run(
            ["pactl", "-f", "json", "list", "sources"], capture_output=True, text=True, timeout=3).stdout or "[]")}
    except Exception:
        return []
    apps = []
    for o in outs:
        p = o.get("properties", {})
        name = p.get("application.name") or p.get("application.process.binary") or "Unknown app"
        src = sources.get(o.get("source"), {})
        if name.lower() in IGNORE or src.get("monitor_source") or p.get("stream.monitor") == "true":
            continue
        if name not in apps:
            apps.append(name)
    return apps


def portal_stream():
    try:
        out = subprocess.run(["pw-cli", "ls", "Node"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return False
    return "xdph" in out or "xdg-desktop-portal" in out


def socket2():
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"), "hypr",
                        os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""), ".socket2.sock")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(path)
        return s
    except OSError:
        return None


def main():
    sub = subprocess.Popen(preexec_fn=_pdeathsig, args=["pactl", "subscribe"], stdout=subprocess.PIPE, bufsize=0)
    hy = socket2()
    sharing, last, buf = False, None, b""

    def emit():
        nonlocal last
        apps = recorders()
        parts, tip = [], []
        if apps:
            parts.append(I_MIC)
            tip.append(f"{I_MIC}  Microphone in use by: " + ", ".join(html.escape(a) for a in apps))
        if sharing:
            parts.append(I_SCREEN)
            tip.append(f"{I_SCREEN}  Your screen is being shared")
        cams = camera_users()
        if cams:
            parts.append(I_CAM)
            tip.append(f"{I_CAM}  Camera in use by: " + ", ".join(html.escape(a) for a in cams))
        text = "  ".join(parts)
        if PUNK and parts:
            text = "ON AIR  " + text
        out = json.dumps({"text": text, "class": "active" if parts else "",
                          "tooltip": "\n".join(tip)}, ensure_ascii=False)
        if out != last:
            try:
                print(out, flush=True)
            except BrokenPipeError:
                sub.kill()
                sys.exit(0)
            last = out

    emit()
    while True:
        watch = [sub.stdout] + ([hy] if hy else [])
        r, _, _ = select.select(watch, [], [], 3 if glob.glob("/dev/video*") else 15)   # camera: poll
        if not r:
            emit()
            continue
        if sub.stdout in r:
            chunk = os.read(sub.stdout.fileno(), 65536)   # raw: no lines hidden in a Python buffer
            if not chunk:
                sub = subprocess.Popen(preexec_fn=_pdeathsig, args=["pactl", "subscribe"], stdout=subprocess.PIPE, bufsize=0)
            elif b"source-output" in chunk:
                time.sleep(0.05)
                emit()
        if hy and hy in r:
            data = hy.recv(65536)
            if not data:
                hy = socket2()
                continue
            buf += data
            *lines, buf = buf.split(b"\n")
            for raw in lines:
                ev, _, arg = raw.decode(errors="replace").partition(">>")
                if ev == "screencast":
                    # screenshots (grim) also fire this event; real sharing goes through
                    # xdg-desktop-portal-hyprland, which creates a PipeWire video stream
                    sharing = arg.split(",")[0] == "1" and portal_stream()
                    emit()


if __name__ == "__main__":
    main()
