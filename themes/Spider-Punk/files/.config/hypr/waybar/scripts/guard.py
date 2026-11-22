#!/usr/bin/env python3
"""guard.py CMD [ARGS…] — run a waybar module command and make sure it stops
when waybar does. For programs that ignore PR_SET_PDEATHSIG (e.g. binaries
with file capabilities like waybar-weather, where the kernel clears it).
stdout is passed through unchanged."""
import ctypes, os, select, signal, subprocess, sys

ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)       # the guard itself dies with waybar
child = subprocess.Popen(sys.argv[1:], stdout=subprocess.PIPE)

def stop(*_):
    try:
        child.terminate(); child.wait(2)
    except Exception:
        child.kill()
    sys.exit(0)

for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
    signal.signal(s, stop)
out = select.poll(); out.register(1, select.POLLERR | select.POLLHUP)
src = child.stdout.fileno()
while True:
    if out.poll(0) or os.getppid() == 1:
        stop()
    r, _, _ = select.select([src], [], [], 1.0)
    if r:
        data = os.read(src, 65536)
        if not data:
            stop()
        try:
            os.write(1, data)
        except OSError:
            stop()
