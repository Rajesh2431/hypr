#!/usr/bin/env python3
"""Arch-logo menu for Waybar via cffi/menu-widget.so (click drop-down).

Replaces the hover drawer (custom/menu + layout/theme/files/terminal/browser/
settings buttons) so nothing widens the bar on hover.

  apps.py status    feed for the widget
"""
# die with the parent (waybar / quickshell), and make our own long-running
# children (pactl subscribe, nmcli monitor, dbus-monitor, ...) die with us
import ctypes as _ctypes, signal as _signal
def _pdeathsig():
    try:
        _ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, _signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:
        pass
import sys as _sys
if len(_sys.argv) > 1 and _sys.argv[1] == "status":   # only the long-running feed, never one-shot actions
    _pdeathsig()

import json
import os
import select
import subprocess
import sys
import time

S = os.path.expanduser("~/.config/hypr/scripts")
ARCH = ""
I_APPS, I_FILES, I_TERM, I_WEB = "\U000f003b", "\U000f024b", "\U000f018d", "\U000f059f"
I_THEME, I_WALL, I_STYLE, I_BAR = "\U000f03d8", "\U000f02e9", "\U000f0e09", "\U000f0b5d"
I_SET, I_LAYOUT = "\U000f0493", "\U000f0570"
LAYOUTS = [("dwindle", "Dwindle"), ("master", "Master"), ("scrolling", "Scrolling"), ("monocle", "Monocle")]
LAUNCHER = ('rofi_dir="$HOME/.config/hypr/rofi"; [ ! -d "$rofi_dir" ] && rofi_dir="$HOME/.config/rofi"; '
            'pkill -x rofi; ' + S + '/RofiFocusedWallpaperLink.sh >/dev/null 2>&1; '
            'rofi -show drun -modi run,drun,filebrowser,window -config "$rofi_dir/config.rasi"')


def layout():
    try:
        out = subprocess.run([f"{S}/HyprLayoutModule.sh", "status"], capture_output=True, text=True, timeout=3).stdout
        return json.loads(out).get("class", "")
    except Exception:
        return ""


def record(cur):
    E = lambda *f: "\x1c".join(f)
    name = dict(LAYOUTS).get(cur, cur.title() or "?")
    m = [E("item", f"{I_APPS}   <b>Apps</b>", LAUNCHER),
         E("item", f"{I_FILES}   Files", f"{S}/WaybarScripts.sh --files"),
         E("item", f"{I_TERM}   Terminal", f"{S}/WaybarScripts.sh --term"),
         E("item", f"{I_WEB}   Browser", "xdg-open https://"),
         "sep",
         E("sub", f"{I_LAYOUT}   Window layout    <span alpha='55%'>{name}</span>")]
    for key, label in LAYOUTS:
        m.append(E("check", label, f"{S}/HyprLayoutModule.sh {key}", "1" if key == cur else "0"))
    m += ["end",
          E("item", f"{I_WALL}   Wallpaper…", "qs ipc -c island call wallpaper toggle"),
          E("item", f"{I_THEME}   Colour theme…", f"{S}/ThemeChanger.sh"),
          E("item", f"{I_STYLE}   Bar style…", f"{S}/WaybarStyles.sh"),
          E("item", f"{I_BAR}   Bar layout…", f"{S}/WaybarLayout.sh"),
          "sep",
          E("item", f"{I_SET}   KooL Settings…", f"{S}/Kool_Quick_Settings.sh")]
    tip = (f"<b>Arch menu</b>\nWindow layout: {name}\n\n<span alpha='55%' size='small'>"
           "Click: menu · Middle: wallpapers · Right: bar layouts</span>")
    return "\x1f".join(["", ARCH, tip, "\x1d".join(m)]).replace("\n", "\x1e")


def main():
    last, cur, at = None, layout(), time.time()
    while True:
        if time.time() - at > 3:
            cur, at = layout(), time.time()
        line = record(cur)
        if line != last:
            try:
                print(line, flush=True)
            except BrokenPipeError:
                return
            last = line
        r, _, _ = select.select([sys.stdin], [], [], 3)
        if r:
            if not os.read(0, 4096):     # raw read: never leaves lines in a Python buffer
                return
            at = 0   # menu opened/closed: refresh the layout tick right away


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        main()
    else:
        sys.exit(__doc__)
