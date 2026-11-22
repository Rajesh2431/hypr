#!/usr/bin/env python3
"""NVIDIA dGPU for Waybar (custom/gpu, continuous JSON feed).

Never wakes the GPU: while it is runtime-suspended we only read sysfs
(free) and show "zz"; nvidia-smi runs only when the card is already awake.
"""
import ctypes, signal, json, os, subprocess, sys, time

try:
    ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)   # die with waybar
except Exception:
    pass

ICON = "\U000f08ae"   # nf-md-expansion_card (GPU)
PUNK = os.environ.get("PUNK_ICONS") == "1"   # Spider-Punk style: icon comes from CSS (state class), no glyph


def rd(p, d=""):
    try:
        with open(p) as f:
            return f.read().strip()
    except OSError:
        return d


NV = next((f"/sys/bus/pci/devices/{d}" for d in sorted(os.listdir("/sys/bus/pci/devices"))
           if rd(f"/sys/bus/pci/devices/{d}/vendor") == "0x10de"
           and rd(f"/sys/bus/pci/devices/{d}/class").startswith("0x03")), None)


def sample():
    if not NV:
        return {"text": "", "class": "missing", "tooltip": "No NVIDIA GPU"}
    state = rd(f"{NV}/power/runtime_status", "unknown")
    if state != "active":
        return {"text": "zz" if PUNK else f"{ICON} zz", "class": "sleep",
                "tooltip": f"<b>NVIDIA dGPU</b>\nPowered down ({state}), saving battery"}
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4).stdout
        name, u, t, mu, mt, pw = [x.strip() for x in out.splitlines()[0].split(",")]
        u, t = int(float(u)), int(float(t))
    except Exception:
        return {"text": f"{ICON} on", "class": "awake", "tooltip": "<b>NVIDIA dGPU</b>\nAwake (nvidia-smi unavailable)"}
    cls = "critical" if t >= 85 else "warning" if t >= 75 or u >= 90 else "awake"
    tip = (f"<b>{name.replace('NVIDIA GeForce ', '')}</b>\n"
           f"Load {u}%   ·   {t}°C\nVRAM {int(mu) / 1024:.1f} / {int(mt) / 1024:.1f} GB\nPower {pw} W")
    return {"text": f"{u}%" if PUNK else f"<span color='{os.environ.get("GPU_ICON_COLOR", "#FFD43B")}'>{ICON}</span> {u}%", "class": cls, "tooltip": tip, "percentage": u}


last = None
while True:
    d = sample()
    line = json.dumps(d)
    if line != last:
        try:
            print(line, flush=True)
        except BrokenPipeError:
            sys.exit(0)
        last = line
    # awake: 5 s (nvidia-smi is cheap then); asleep: sysfs only, 3 s
    time.sleep(5 if d.get("class") not in ("sleep", "missing") else 3)
