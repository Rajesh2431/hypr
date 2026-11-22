#!/usr/bin/env python3
"""Headphone / speaker fix for the Ryzen HD-Audio codec (+ Dynamic Island pop).

Problem: after plugging headphones in (or out), PipeWire switches the port but
the codec's 'Headphone' (or 'Speaker') mixer element stays muted at 0 %, so
nothing is heard until `amixer -c N set Headphone unmute 100%` is run.

This watches the 'Headphone Jack' control and, on every plug / unplug (and at
start / after resume), unmutes the element that is now in use:
  plugged   -> Headphone unmute 100%   (+ Master unmute)
  unplugged -> Speaker   unmute 100%   (+ Master unmute)
Volume and mute stay controlled by PipeWire (the 'Master' path), as before.

It also tells the Dynamic Island:  qs ipc -c island call island jack <in|out>
Runs as a systemd user service: ~/.config/systemd/user/audio-jack-fix.service
"""
import ctypes
import os
import re
import select
import signal
import subprocess
import sys
import time

ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)   # die with the service manager's process


def run(*cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return subprocess.CompletedProcess(cmd, 1, "", "")


def find_card():
    """The card that has both a 'Headphone Jack' and a 'Speaker' control (card numbers can change)."""
    for line in open("/proc/asound/cards"):
        m = re.match(r"\s*(\d+)\s+\[", line)
        if not m:
            continue
        n = m.group(1)
        ctl = run("amixer", "-c", n, "controls").stdout
        if "'Headphone Jack'" in ctl and "'Speaker Playback" in ctl:
            return n
    return None


_JACK_ID = {}


def jack(card):
    """True if headphones are plugged in. The jack is an iface=CARD control, so look it up by numid."""
    if card not in _JACK_ID:
        for line in run("amixer", "-c", card, "controls").stdout.splitlines():
            if "iface=CARD" in line and "name='Headphone Jack'" in line:
                _JACK_ID[card] = line.split(",")[0].split("=")[1]
                break
    nid = _JACK_ID.get(card)
    if not nid:
        return None
    out = run("amixer", "-c", card, "cget", f"numid={nid}").stdout
    return ": values=on" in out


def fix(card, plugged):
    if plugged is None:          # jack state unknown: never touch anything (avoid speakers blasting)
        return
    elem, other = ("Headphone", "Speaker") if plugged else ("Speaker", "Headphone")
    run("amixer", "-q", "-c", card, "set", elem, "unmute", "100%")
    run("amixer", "-q", "-c", card, "set", other, "mute")   # Auto-Mute is disabled on this codec
    run("amixer", "-q", "-c", card, "set", "Master", "unmute")


def apply(card, plugged, announce):
    # PipeWire switches the port a moment after the jack event and may re-mute
    # the element while doing so: fix now, then again shortly after.
    for delay in (0.3, 0.8, 1.5):
        time.sleep(delay)
        fix(card, plugged)
    if announce:
        run("qs", "ipc", "-c", "island", "call", "island", "jack", "in" if plugged else "out", timeout=3)


def main():
    card = None
    for _ in range(30):                     # wait for the card at login
        card = find_card()
        if card:
            break
        time.sleep(1)
    if not card:
        sys.exit("no codec with 'Headphone Jack' + 'Speaker' found")
    state = jack(card)
    apply(card, state, announce=False)

    mon = subprocess.Popen(["alsactl", "monitor", f"hw:{card}"], stdout=subprocess.PIPE, bufsize=0)
    last_tick = time.clock_gettime(time.CLOCK_BOOTTIME)
    while True:
        r, _, _ = select.select([mon.stdout], [], [], 10)
        now = time.clock_gettime(time.CLOCK_BOOTTIME)
        if now - last_tick > 30:            # we were suspended: re-apply after resume
            state = jack(card)
            apply(card, state, announce=False)
        last_tick = now
        if not r:
            continue
        line = os.read(mon.stdout.fileno(), 65536).decode(errors="replace")   # raw: all pending events
        if not line:                        # card went away (e.g. driver reload): start over
            time.sleep(2)
            return main()
        if "Jack" not in line:
            continue
        new = jack(card)
        if new != state:
            state = new
            apply(card, state, announce=True)


if __name__ == "__main__":
    main()
