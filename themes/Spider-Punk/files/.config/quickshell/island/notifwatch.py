#!/usr/bin/env python3
"""Print one JSON line per desktop notification (watches Notify calls on the
session bus with dbus-monitor; swaync still receives and stores them).
OSD-style notifications (volume / brightness / mute) are skipped: the island
shows those as sliders itself."""
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
import re
import subprocess
import sys

SKIP_HINTS = ("x-canonical-private-synchronous", "synchronous", "x-dunst-stack-tag", "SWAYNC_BYPASS_DND")
STR = re.compile(r'^\s*string "(.*)"\s*$', re.S)

p = subprocess.Popen(preexec_fn=_pdeathsig, args=["dbus-monitor", "--session",
                      "type='method_call',interface='org.freedesktop.Notifications',member='Notify'"],
                     stdout=subprocess.PIPE, text=True, bufsize=1)

msg, cur = None, None


def finish(m):
    if not m or len(m["args"]) < 5:
        return
    app, _rid, icon, summary, body = m["args"][:5]
    if any(h in m["raw"] for h in SKIP_HINTS) or re.search(r'string "value"', m["raw"]):
        return
    if not summary and not body:
        return
    try:
        print(json.dumps({"app": app, "icon": icon, "summary": summary, "body": body,
                          "urgency": 2 if 'byte 2' in m["raw"] else 1}, ensure_ascii=False), flush=True)
    except BrokenPipeError:
        p.kill()
        sys.exit(0)


for line in p.stdout:
    if line.startswith("method call") and "member=Notify" in line:
        finish(msg)
        msg, cur = {"args": [], "raw": ""}, None
        continue
    if line.startswith(("method call", "signal", "method return", "error")):
        finish(msg)
        msg, cur = None, None
        continue
    if msg is None:
        continue
    msg["raw"] += line
    # top-level arguments are indented by exactly 3 spaces
    if cur is not None:                      # continuation of a multi-line string
        cur += "\n" + line.rstrip("\n")
        if cur.endswith('"'):
            msg["args"].append(cur[:-1])
            cur = None
        continue
    if line.startswith("   ") and not line.startswith("    "):
        t = line[3:].rstrip("\n")
        if t.startswith('string "'):
            if t.endswith('"') and len(t) > 8:
                msg["args"].append(t[8:-1])
            else:
                cur = t[8:]
        elif t.startswith("uint32"):
            msg["args"].append(t.split()[-1])
        elif t.startswith("int32"):          # expire_timeout: the last argument of Notify
            msg["args"].append(t.split()[-1])
            finish(msg)
            msg = None
finish(msg)
