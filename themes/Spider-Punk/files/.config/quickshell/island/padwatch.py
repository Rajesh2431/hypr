#!/usr/bin/env python3
"""Game-controller events for the Dynamic Island (one JSON line per event).

Sees every gamepad however it connects — USB cable, 2.4 GHz dongle (8BitDo,
Xbox Wireless Adapter, Logitech…) or Bluetooth — via udev input devices with
ID_INPUT_JOYSTICK=1. Battery comes from the controller's own power_supply
(scope=Device: hid-playstation, xpadneo, hid-nintendo, …), matched by sysfs path.

kinds: pad_on (name, bus, battery), pad_off (name, bus),
       pad_low (≤20 %, once), pad_crit (≤10 %, every 2 % lower)
"""
import ctypes
import glob
import json
import os
import select
import signal
import subprocess
import sys
import time

def _pdeathsig():
    try:
        ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)
    except Exception:
        pass
_pdeathsig()

SKIP_NAMES = ("Touchpad", "Motion Sensors", "Accelerometer", "IMU")   # extra nodes some pads create


def say(kind, **kw):
    try:
        print(json.dumps({"kind": kind, **kw}, ensure_ascii=False), flush=True)
    except BrokenPipeError:
        sys.exit(0)


def props(syspath):
    """udev properties of an input device."""
    out = subprocess.run(["udevadm", "info", "-q", "property", "-p", syspath],
                         capture_output=True, text=True, timeout=3).stdout
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)


def read(path, default=""):
    try:
        return open(path).read().strip()
    except OSError:
        return default


def pad_from(syspath, p=None):
    """A controller dict for /sys/devices/.../input/inputN, or None if it isn't a gamepad."""
    p = p or props(syspath)
    if p.get("ID_INPUT_JOYSTICK") != "1":
        return None
    name = (p.get("NAME") or read(os.path.join("/sys" + syspath if not syspath.startswith("/sys") else syspath, "name"))).strip('"')
    if not name or any(s in name for s in SKIP_NAMES):
        return None
    bus = {"usb": "USB", "bluetooth": "Bluetooth"}.get(p.get("ID_BUS", ""), p.get("ID_BUS", "").upper() or "")
    full = syspath if syspath.startswith("/sys") else "/sys" + syspath
    hid = os.path.realpath(os.path.join(full, "device"))       # the HID device behind the input node
    dongle = bus == "USB" and any(w in name.lower() for w in ("receiver", "dongle", "wireless", "adapter", "2.4"))
    return {"name": name, "bus": "USB receiver" if dongle else bus, "hid": hid, "key": full}


def battery_for(hid):
    """(percent | None) from a scope=Device power_supply under the same HID device."""
    for ps in glob.glob("/sys/class/power_supply/*"):
        if read(os.path.join(ps, "scope")) != "Device":
            continue
        dev = os.path.realpath(os.path.join(ps, "device"))
        if hid and (dev == hid or dev.startswith(hid + "/") or hid.startswith(dev + "/")):
            cap = read(os.path.join(ps, "capacity"))
            if cap.isdigit():
                return int(cap)
            level = read(os.path.join(ps, "capacity_level")).lower()
            return {"critical": 5, "low": 15, "normal": 55, "high": 85, "full": 100}.get(level)
    return None


def scan():
    pads = {}
    for inp in glob.glob("/sys/class/input/input*"):
        full = os.path.realpath(inp)
        d = pad_from(full[4:] if full.startswith("/sys") else full)
        if d:
            pads[d["key"]] = d
    return pads


def main():
    mon = subprocess.Popen(["udevadm", "monitor", "--udev", "--property", "--subsystem-match=input"],
                           stdout=subprocess.PIPE, bufsize=0, preexec_fn=_pdeathsig)
    pending = b""
    pads = scan()                     # already connected at start: no pop
    alerts = {}                       # key -> {"low": bool, "crit": int}
    block, next_bat = {}, 0
    while True:
        r, _, _ = select.select([mon.stdout, sys.stdin], [], [], 5)
        if sys.stdin in r and not os.read(0, 4096):
            mon.kill()
            return
        lines = []
        if mon.stdout in r:
            # raw read: select() can't see lines already sitting in a Python buffer
            chunk = os.read(mon.stdout.fileno(), 65536)
            if not chunk:
                time.sleep(2)
                return main()
            pending += chunk
            *done, pending = pending.split(b"\n")
            lines = [l.decode(errors="replace").strip() for l in done]
        for line in lines:
            if line:
                if "=" in line:
                    k, v = line.split("=", 1)
                    block[k] = v
                continue
            # end of one udev event block
            ev, block = block, {}
            path = ev.get("DEVPATH", "")
            if not path.split("/")[-1].startswith("input"):
                continue                       # only the inputN node, not eventN / jsN
            key = "/sys" + path
            if ev.get("ACTION") == "add":
                time.sleep(0.4)                # let the driver register its battery
                d = pad_from(path, ev)
                if d and key not in pads:
                    pads[key] = d
                    alerts[key] = {"low": False, "crit": 101}
                    say("pad_on", name=d["name"], bus=d["bus"], battery=battery_for(d["hid"]))
            elif ev.get("ACTION") == "remove" and key in pads:
                d = pads.pop(key)
                alerts.pop(key, None)
                say("pad_off", name=d["name"], bus=d["bus"])
        if time.time() >= next_bat:            # battery check every 60 s
            next_bat = time.time() + 60
            for key, d in pads.items():
                b = battery_for(d["hid"])
                a = alerts.setdefault(key, {"low": False, "crit": 101})
                if b is None:
                    continue
                if b > 25:
                    a["low"], a["crit"] = False, 101
                elif b <= 10 and b <= a["crit"] - 2:
                    a["crit"], a["low"] = b, True
                    say("pad_crit", name=d["name"], bus=d["bus"], battery=b)
                elif b <= 20 and not a["low"]:
                    a["low"] = True
                    say("pad_low", name=d["name"], bus=d["bus"], battery=b)


if __name__ == "__main__":
    main()
