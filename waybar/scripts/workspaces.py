#!/usr/bin/env python3
"""Workspace buttons for Waybar (cffi/workspaces-widget.so).

Always shows (at least) 5 buttons: every workspace that has windows, plus the
active one, then the lowest empty numbers to fill up to 5. Examples:
  only 1 used          -> 1 2 3 4 5
  1, 7, 8 used         -> 1 2 3 7 8
  1, 7, 8, 10 used     -> 1 2 7 8 10
More than 5 in use -> all of them are shown.

Each button shows the number plus app icons, using the "window-rewrite" rules
of hyprland/workspaces#rw in ../ModulesWorkspaces (same icons as before).
Updates instantly from Hyprland's event socket (socket2).

Output, one line per change:  entries joined by \\x1d, each  id \\x1c label \\x1c classes
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

import json
import os
import select
import re
import socket
import subprocess
import sys
import time

SLOTS = int(os.environ.get("WORKSPACE_SLOTS", "5"))
MODULES = os.path.expanduser("~/.config/hypr/waybar/ModulesWorkspaces")
EVENTS = ("workspace", "createworkspace", "destroyworkspace", "openwindow", "closewindow",
          "movewindow", "focusedmon", "urgent", "windowtitle", "renameworkspace", "moveworkspace",
          "monitoradded", "monitorremoved", "workspacev2", "moveworkspacev2")


def jsonc(text):
    """Strip // and /* */ comments and trailing commas (enough for waybar files)."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\":
                out.append(text[i + 1]); i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True; out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            i = text.find("*/", i + 2) + 2
            continue
        else:
            out.append(c)
        i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


def load_rules():
    try:
        mod = jsonc(open(MODULES).read()).get("hyprland/workspaces#rw", {})
    except Exception:
        return [], ""
    rules = []
    for key, icon in mod.get("window-rewrite", {}).items():
        parts = dict(re.findall(r"(class|title)<(.*?)>(?=\s*(?:class|title)<|$)", key))
        try:
            compiled = {k: re.compile(v, re.I) for k, v in parts.items()}
        except re.error:
            continue
        if compiled:
            rules.append((compiled, icon.strip()))
    default = mod.get("window-rewrite-default", "").strip()
    if "✘" in default or "foreground='#ff0000'" in default:
        default = "\U000f08c6"   # neutral app icon instead of KoolDots' red ✘ for unknown apps
    return rules, default


def icon_for(client, rules, default):
    for pats, icon in rules:
        if all(p.fullmatch(client.get(k, "") or "") for k, p in pats.items()):
            return icon
    return default


# Spider-Punk layout (PUNK_ICONS=1): app icons coloured by kind, in the comic palette
PUNK = os.environ.get("PUNK_ICONS") == "1"
PUNK_KINDS = [
    (r"firefox|zen|chrom|brave|vivaldi|librewolf|tor ?browser|qutebrowser", "#00B8FF"),   # web: blue
    (r"kitty|alacritty|foot|wezterm|ghostty|konsole|terminal|tmux", "#FFD43B"),            # terminal: yellow
    (r"code|codium|cursor|zed|nvim|neovide|jetbrains|android-studio|studio|emacs|gedit|kate", "#FF2E93"),  # code: magenta
    (r"spotify|mpv|vlc|celluloid|rhythmbox|obs|kdenlive|gimp|inkscape|krita|blender", "#FF6B24"),  # media/creative: orange
    (r"discord|vesktop|telegram|slack|signal|whatsapp|teams|element|thunderbird|zoom", "#8B35FF"),  # chat/mail: purple
    (r"thunar|nautilus|dolphin|nemo|pcmanfm|yazi", "#F5F0E8"),                                     # files: paper
]
PUNK_KINDS = [(re.compile(r, re.I), c) for r, c in PUNK_KINDS]


def punk_colour(client):
    key = (client.get("class") or "") + " " + (client.get("initialClass") or "")
    return next((c for r, c in PUNK_KINDS if r.search(key)), "#FF1744")   # anything else: crimson


def hypr(*args):
    return json.loads(subprocess.run(["hyprctl", "-j", *args], capture_output=True, text=True,
                                     timeout=3).stdout or "null")


def monitor_for(geom):
    """Match the bar's GDK monitor geometry (logical px) to a Hyprland monitor name."""
    if not geom:
        return None
    x, y, w, h = geom
    best = None
    for m in hypr("monitors") or []:
        sc = m.get("scale") or 1
        mw, mh = m["width"] / sc, m["height"] / sc
        if m.get("transform", 0) % 2:
            mw, mh = mh, mw
        d = abs(m["x"] - x) + abs(m["y"] - y) + abs(mw - w) + abs(mh - h)
        if best is None or d < best[0]:
            best = (d, m)
    return best[1] if best else None


def snapshot(rules, default, urgent, geom=None):
    allws = [w for w in (hypr("workspaces") or []) if isinstance(w.get("id"), int) and w["id"] > 0]
    mon = monitor_for(geom)
    if mon and len(hypr("monitors") or []) > 1:
        # several monitors: this bar shows only its own monitor's workspaces
        wss = [w for w in allws if w.get("monitor") == mon["name"]]
        taken = {w["id"] for w in allws if w.get("monitor") != mon["name"] and w.get("windows", 0) > 0}
        taken |= {m["activeWorkspace"]["id"] for m in hypr("monitors") or [] if m["name"] != mon["name"]}
        active = (mon.get("activeWorkspace") or {}).get("id")
    else:
        wss, taken = allws, set()
        active = (hypr("activeworkspace") or {}).get("id")
    clients = hypr("clients") or []
    icons = {}
    for c in sorted(clients, key=lambda c: (c.get("at") or [0, 0])[0]):
        wid = (c.get("workspace") or {}).get("id")
        if isinstance(wid, int) and wid > 0:
            ic = icon_for(c, rules, default)
            if ic and PUNK:
                ic = f"<span color='{punk_colour(c)}'>{ic}</span>"
            if ic and ic not in icons.setdefault(wid, []):
                icons[wid].append(ic)
    used = {w["id"] for w in wss if w.get("windows", 0) > 0}
    shown = set(used)
    if isinstance(active, int) and active > 0:
        shown.add(active)
    n = 1
    while len(shown) < SLOTS and n < 100:
        if n not in shown and n not in taken:   # don't offer numbers that live on another monitor
            shown.add(n)
        n += 1
    urgent &= used
    urgent.discard(active)
    out = []
    for wid in sorted(shown):
        label = str(wid) + ("  " + " ".join(icons[wid]) if icons.get(wid) else "")
        if PUNK and wid == active:   # the active button is a crimson panel: plain paper icons there
            label = re.sub(r"<span color='#[0-9A-F]{6}'>(.*?)</span>", r"\1", label)
        cls = ["active"] if wid == active else []
        if wid not in used:
            cls.append("empty")
        if wid in urgent:
            cls.append("urgent")
        out.append("\x1c".join([str(wid), label, " ".join(cls)]))
    return "\x1d".join(out)


def connect():
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"), "hypr",
                        os.environ["HYPRLAND_INSTANCE_SIGNATURE"], ".socket2.sock")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(path)
    s.settimeout(30)   # periodic refresh as a safety net
    return s


def main():
    rules, default = load_rules()
    urgent, last, buf, geom = set(), None, b"", None
    sock = connect()

    def emit():
        nonlocal last
        line = snapshot(rules, default, urgent, geom)
        if line != last:
            try:
                print(line, flush=True)
            except BrokenPipeError:
                sys.exit(0)
            last = line

    emit()
    while True:
        r, _, _ = select.select([sock, sys.stdin], [], [], 30)
        if sys.stdin in r:
            msg = os.read(0, 4096).decode(errors="replace")   # raw: may hold several lines
            if not msg:
                return              # widget went away
            for line in msg.splitlines():
                parts = line.split()
                if len(parts) == 5 and parts[0] == "monitor":
                    geom = tuple(int(v) for v in parts[1:])
            emit()
            continue
        if not r:
            emit()
            continue
        try:
            data = sock.recv(65536)
            if not data:
                time.sleep(1)
                sock = connect()
                continue
        except socket.timeout:
            emit()
            continue
        buf += data
        *lines, buf = buf.split(b"\n")
        dirty = False
        for raw in lines:
            ev, _, arg = raw.decode(errors="replace").partition(">>")
            if ev == "urgent":
                try:
                    addr = "0x" + arg.strip()
                    c = next((c for c in hypr("clients") or [] if c.get("address") == addr), None)
                    if c:
                        urgent.add((c.get("workspace") or {}).get("id"))
                except Exception:
                    pass
            if ev in EVENTS:
                dirty = True
        if dirty:
            time.sleep(0.03)   # let a burst of events settle
            emit()


if __name__ == "__main__":
    main()
