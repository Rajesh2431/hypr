#!/usr/bin/env python3
"""Waybar bell for the island's Control Center (custom module, JSON).
Shows the unread count, or the active Focus mode's icon. Reads the state file
the island writes: ~/.cache/island/center-state.json (checked twice a second;
a stat() is all it costs when nothing changes)."""
import ctypes, json, os, signal, sys, time
ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)   # die with waybar

PATH = os.path.expanduser("~/.cache/island/center-state.json")
BELL, BELL_DOT = "\U000f009a", "\U000f116b"
last_m, last_out = None, None
while True:
    try:
        m = os.stat(PATH).st_mtime
    except OSError:
        m = None
    if m != last_m:
        last_m = m
        try:
            d = json.load(open(PATH))
        except Exception:
            d = {}
        n, focus = int(d.get("count") or 0), d.get("focusName") or ""
        if focus:
            text = chr(int(d.get("focusIcon") or 0xf0594)) + (f" {n}" if n else "")
            cls, tip = "focus", f"Focus: {focus}" + (f"\n{n} notification{'s' if n != 1 else ''}" if n else "")
        else:
            text = (BELL_DOT if n else BELL) + (f" {n}" if n else "")
            cls, tip = ("unread" if n else "empty"), (f"{n} notification{'s' if n != 1 else ''}" if n else "No notifications")
        tip += "\n\n<span alpha='55%' size='small'>Click: Control Center · Right-click: Do Not Disturb</span>"
        out = json.dumps({"text": text, "class": cls, "tooltip": tip}, ensure_ascii=False)
        if out != last_out:
            try:
                print(out, flush=True)
            except BrokenPipeError:
                sys.exit(0)
            last_out = out
    time.sleep(0.5)
