#!/usr/bin/env python3
"""Sound for Waybar via cffi/menu-widget.so (drop-down like Wi-Fi/Bluetooth).

Bar: volume icon + %, mic-muted badge. Click: menu with output device / port
switching, mute, volume steps, microphone (select + mute) and per-app volume.
Scroll/right-click are handled by waybar config (Volume.sh / pavucontrol).
Updates instantly from `pactl subscribe`.

  sound.py status     feed for the widget
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
import subprocess
import sys
import time

PUNK = os.environ.get("PUNK_ICONS") == "1"   # Spider-Punk style: icon comes from CSS (state class), no glyph
I_VOL = ["\U000f057f", "\U000f0580", "\U000f057e"]          # low / mid / high
I_MUTE, I_HEAD, I_SPK = "\U000f075f", "\U000f02cb", "\U000f04c3"
I_MIC, I_MIC_OFF, I_APP = "\U000f036c", "\U000f036d", "\U000f0387"
I_UP, I_DOWN, I_MIX = "\U000f005d", "\U000f0045", "\U000f0751"
SCRIPTS = os.path.expanduser("~/.config/hypr/scripts")


def pj(*args):
    try:
        return json.loads(subprocess.run(["pactl", "-f", "json", *args], capture_output=True,
                                         text=True, timeout=3).stdout or "[]")
    except Exception:
        return []


def pget(*args):
    try:
        return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


def vol(o):
    try:
        return int(list(o["volume"].values())[0]["value_percent"].rstrip("%"))
    except Exception:
        return 0


def vol_icon(v, muted):
    return I_MUTE if muted or v == 0 else I_VOL[0 if v < 34 else 1 if v < 67 else 2]


def port_icon(port_name):
    return I_HEAD if "head" in (port_name or "").lower() else I_SPK


def record():
    sinks = pj("list", "sinks")
    sources = [s for s in pj("list", "sources") if not s.get("monitor_source")]
    inputs = pj("list", "sink-inputs")
    dsink, dsrc = pget("get-default-sink"), pget("get-default-source")
    sink = next((s for s in sinks if s["name"] == dsink), sinks[0] if sinks else None)
    src = next((s for s in sources if s["name"] == dsrc), sources[0] if sources else None)

    E = lambda *f: "\x1c".join(f)
    if not sink:
        return "\x1f".join(["muted", I_MUTE, "No audio output", E("note", "No audio output")])
    v, muted = vol(sink), sink["mute"]
    mic_muted = bool(src and src["mute"])
    port = sink.get("active_port")
    bar = f"{vol_icon(v, muted)} {v}%" if not muted else f"{I_MUTE} muted"
    if mic_muted:
        bar += f"  <span alpha='45%'>{I_MIC_OFF}</span>"
    cls = "muted" if muted else ""
    if PUNK:   # speaker icon from CSS (vol-low/mid/high/muted); mic-off stays a small crimson mark
        bar = f"{v}%" if not muted else "muted"   # muted mic = normal state: no mark (privacy dot shows a live mic)
        cls = "muted" if muted else ("vol-low" if v < 34 else "vol-mid" if v < 67 else "vol-high")

    tip = [f"<b>{html.escape(sink['description'])}</b>",
           f"{vol_icon(v, muted)}  Volume {v}%" + ("  (muted)" if muted else "")]
    if src:
        tip.append(f"{I_MIC_OFF if mic_muted else I_MIC}  Microphone {vol(src)}%" + ("  (muted)" if mic_muted else ""))
    tip += ["", "<span alpha='55%' size='small'>Click: sound menu · Scroll: volume · Right-click: mixer</span>"]

    m = [E("header", "<b>Output</b>")]
    for s in sinks:
        m.append(E("check", html.escape(s["description"]), f"pactl set-default-sink {s['name']}",
                   "1" if s is sink else "0"))
    ports = [p for p in sink.get("ports", []) if p.get("availability") != "not available"]
    if len(ports) > 1:
        m += ["sep", E("header", "Play through")]
        for p in ports:
            m.append(E("check", f"{port_icon(p['name'])}   {html.escape(p['description'])}",
                       f"pactl set-sink-port {sink['name']} {p['name']}", "1" if p["name"] == port else "0"))
    m += [E("check", f"{I_MUTE}   Mute", f"pactl set-sink-mute {sink['name']} toggle", "1" if muted else "0"),
          E("sub", f"{vol_icon(v, muted)}   Volume  {v}%")]
    for target in (100, 75, 50, 25, 10):
        m.append(E("item", f"{target}%", f"pactl set-sink-volume {sink['name']} {target}%"))
    m += [E("item", f"{I_UP}   +5%", f"pactl set-sink-volume {sink['name']} +5%"),
          E("item", f"{I_DOWN}   −5%", f"pactl set-sink-volume {sink['name']} -5%"), "end"]

    if sources:
        m += ["sep", E("header", "<b>Microphone</b>")]
        for s in sources:
            m.append(E("check", html.escape(s["description"]), f"pactl set-default-source {s['name']}",
                       "1" if s is src else "0"))
        if src:
            m.append(E("check", f"{I_MIC_OFF}   Mute microphone", f"pactl set-source-mute {src['name']} toggle",
                       "1" if mic_muted else "0"))

    if inputs:
        m += ["sep", E("header", "<b>Apps</b>")]
        for i in inputs:
            props = i.get("properties", {})
            name = props.get("application.name") or props.get("media.name") or "App"
            iv, im = vol(i), i["mute"]
            m.append(E("sub", f"{I_APP}   {html.escape(name)}    <span alpha='60%'>{'muted' if im else f'{iv}%'}</span>"))
            m.append(E("check", "Mute", f"pactl set-sink-input-mute {i['index']} toggle", "1" if im else "0"))
            for target in (100, 75, 50, 25):
                m.append(E("item", f"{target}%", f"pactl set-sink-input-volume {i['index']} {target}%"))
            if len(sinks) > 1:
                m.append("sep")
                for s in sinks:
                    m.append(E("check", f"Play on {html.escape(s['description'])}",
                               f"pactl move-sink-input {i['index']} {s['name']}", "1" if i["sink"] == s["index"] else "0"))
            m.append("end")

    m += ["sep", E("item", f"{I_MIX}   Sound Settings…", "pavucontrol")]
    return "\x1f".join([cls, bar, "\n".join(tip), "\x1d".join(m)]).replace("\n", "\x1e")


def main():
    sub = subprocess.Popen(preexec_fn=_pdeathsig, args=["pactl", "subscribe"], stdout=subprocess.PIPE, bufsize=0)
    last = None

    last_emit = [0.0]

    def emit():
        nonlocal last
        last_emit[0] = time.time()
        line = record()
        if line != last:
            try:
                print(line, flush=True)
            except BrokenPipeError:
                sub.kill()
                sys.exit(0)
            last = line

    emit()
    watch = [sub.stdout, sys.stdin]
    while True:
        r, _, _ = select.select(watch, [], [], 10)
        if not r:
            emit()            # safety net
            continue
        if sys.stdin in r and not os.read(0, 4096):
            sub.kill()        # widget went away
            return
        if sub.stdout in r:
            if not os.read(sub.stdout.fileno(), 65536):       # raw read
                time.sleep(1)  # pipewire restarted: resubscribe
                sub = subprocess.Popen(preexec_fn=_pdeathsig, args=["pactl", "subscribe"], stdout=subprocess.PIPE, bufsize=0)
                watch = [sub.stdout, sys.stdin]
            # drain a burst of events, then refresh once
            while select.select([sub.stdout], [], [], 0.05)[0]:   # drain a burst of events
                if not os.read(sub.stdout.fileno(), 65536):
                    break
            # playing audio streams send a constant trickle of change events:
            # refresh at most twice a second
            wait = 0.5 - (time.time() - last_emit[0])
            if wait > 0:
                time.sleep(wait)
                while select.select([sub.stdout], [], [], 0)[0]:
                    if not os.read(sub.stdout.fileno(), 65536):
                        break
            emit()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        main()
    else:
        sys.exit(__doc__)
