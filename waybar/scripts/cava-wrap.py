#!/usr/bin/env python3
"""Run KoolDots' WaybarCava.sh, but stop it (and its cava) as soon as Waybar
stops reading this module (reload / restart). The original script only exits
when no waybar process exists, so every reload used to leak a cava."""
# die with the parent (waybar / quickshell), and make our own long-running
# children (pactl subscribe, nmcli monitor, dbus-monitor, ...) die with us
import ctypes as _ctypes, signal as _signal
def _pdeathsig():
    try:
        _ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, _signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:
        pass
_pdeathsig()

import os, select, signal, subprocess, sys

child = subprocess.Popen([os.path.expanduser("~/.config/hypr/scripts/WaybarCava.sh")],
                         stdout=subprocess.PIPE, start_new_session=True)

def stop(*_):
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    sys.exit(0)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGHUP, stop)
out = select.poll()
out.register(sys.stdout.fileno(), select.POLLERR | select.POLLHUP)   # reader went away
src = child.stdout.fileno()
while True:
    if out.poll(0):
        stop()
    r, _, _ = select.select([src], [], [], 1.0)
    if r:
        data = os.read(src, 4096)
        if not data:
            stop()
        try:
            os.write(sys.stdout.fileno(), data)
        except (BrokenPipeError, OSError):
            stop()
