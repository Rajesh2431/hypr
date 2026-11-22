#!/usr/bin/env python3
"""System stats for Waybar via cffi/menu-widget.so (Wi-Fi-style drop-down).

Bar: CPU temperature. Click: menu with CPU, memory, disk, power profile
(switchable) and shortcuts to btop / nvtop / System Monitor.
Replaces the inline "mobo" hover drawer, so nothing widens the bar on hover.

  system.py status   feed for the widget (refreshes every 2 s, every 1 s while open)
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

import html
import os
import select
import subprocess
import sys
import time

import psutil

PUNK = os.environ.get("PUNK_ICONS") == "1"   # Spider-Punk style: icon comes from CSS (state class), no glyph
HWMON = ["/sys/class/hwmon/hwmon1/temp1_input", "/sys/class/thermal/thermal_zone0/temp"]
CRITICAL = 82
SCRIPTS = os.path.expanduser("~/.config/hypr/scripts")
I_TEMP, I_CPU, I_MEM, I_DISK = "\U000f0238", "\U000f035b", "\U000f0be3", "\U000f02ca"
I_PERF, I_BAL, I_SAVE = "\U000f04c5", "\U000f04c4", "\U000f0d42"
I_BTOP, I_GPU, I_MON = "\U000f0128", "\U000f08ae", "\U000f0379"
PROFILES = [("performance", "Performance", I_PERF), ("balanced", "Balanced", I_BAL),
            ("power-saver", "Power saver", I_SAVE)]


def temp_c():
    for p in HWMON:
        try:
            return round(int(open(p).read()) / 1000)
        except (OSError, ValueError):
            continue
    return None


def profile():
    try:
        return subprocess.run(["powerprofilesctl", "get"], capture_output=True, text=True,
                              timeout=2).stdout.strip()
    except Exception:
        return ""


BAT = next((f"/sys/class/power_supply/{d}" for d in sorted(os.listdir("/sys/class/power_supply"))
            if d.startswith("BAT")), None)
I_BAT, I_CHG, I_PLUG, I_GPU2, I_HEALTH, I_SLEEP = "\U000f0079", "\U000f0084", "\U000f06a5", "\U000f08ae", "\U000f02d1", "\U000f04b2"


def rd(path, default=None):
    try:
        return open(path).read().strip()
    except OSError:
        return default


def hm(hours):
    m = int(round(hours * 60))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"


def battery():
    if not BAT:
        return None
    st, cap = rd(f"{BAT}/status", "Unknown"), int(rd(f"{BAT}/capacity", "0") or 0)
    en, ef, efd = (int(rd(f"{BAT}/{k}", "0") or 0) for k in ("energy_now", "energy_full", "energy_full_design"))
    pw = int(rd(f"{BAT}/power_now", "0") or 0)
    b = {"status": st, "cap": cap, "watts": pw / 1e6, "health": (ef / efd * 100) if efd else None,
         "cycles": rd(f"{BAT}/cycle_count"), "limit": rd(f"{BAT}/charge_control_end_threshold"), "eta": ""}
    if pw > 0 and st == "Discharging":
        b["eta"] = hm(en / pw) + " left"
    elif pw > 0 and st == "Charging":
        b["eta"] = hm(max(0, ef - en) / pw) + " until full"
    return b


NV = next((f"/sys/bus/pci/devices/{d}" for d in sorted(os.listdir("/sys/bus/pci/devices"))
           if rd(f"/sys/bus/pci/devices/{d}/vendor") == "0x10de"
           and (rd(f"/sys/bus/pci/devices/{d}/class") or "").startswith("0x03")), None)


def gpu(query):
    """NVIDIA dGPU info. Never wakes the GPU: nvidia-smi only runs if it is already active."""
    if not NV:
        return None
    state = rd(f"{NV}/power/runtime_status", "unknown")
    g = {"awake": state == "active", "state": state}
    if g["awake"] and query:
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4).stdout
            name, t, u, mu, mt, pdraw = [x.strip() for x in out.splitlines()[0].split(",")]
            g.update(name=name.replace("NVIDIA GeForce ", ""), temp=t, util=u, mem=f"{int(mu) / 1024:.1f} / {int(mt) / 1024:.1f} GB", power=pdraw)
        except Exception:
            pass
    return g


def gb(n):
    return f"{n / 1024 ** 3:.1f}"


def color(pct):
    return "#ff6b6b" if pct >= 90 else "#f5c26b" if pct >= 70 else None


def tint(text, pct):
    c = color(pct)
    return f"<span color='{c}'>{text}</span>" if c else text


def record(prof, is_open=False):
    t = temp_c()
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    hot = t is not None and t >= CRITICAL

    bar = f"{t}°C {I_TEMP}" if t is not None else f"{I_CPU} {cpu:.0f}%"
    cls = "critical" if hot else ""
    if PUNK:   # flame icon from CSS
        bar = f"{t}°C" if t is not None else f"{cpu:.0f}%"
    tip = "\n".join([
        "<b>System</b>",
        f"{I_TEMP}  Temperature  {t}°C" if t is not None else "",
        f"{I_CPU}  CPU  {cpu:.0f}%",
        f"{I_MEM}  Memory  {gb(mem.used)} / {gb(mem.total)} GB",
        f"{I_DISK}  Disk  {disk.percent:.0f}% used",
        (lambda bb: f"{I_BAT}  Battery  {bb['cap']}%" + (f" · {bb['eta']}" if bb["eta"] else "") if bb else "")(battery()),
        "",
        "<span alpha='55%' size='small'>Click for details and power profile</span>",
    ]).replace("\n\n\n", "\n\n")

    E = lambda *f: "\x1c".join(f)
    m = [E("header", "<b>System</b>"),
         E("note", f"{I_TEMP}   Temperature    {tint(f'{t}°C', 100 if hot else 0)}" if t is not None else "Temperature    n/a"),
         E("note", f"{I_CPU}   CPU    {tint(f'{cpu:.0f}%', cpu)}"),
         E("note", f"{I_MEM}   Memory    {tint(f'{gb(mem.used)} / {gb(mem.total)} GB  ({mem.percent:.0f}%)', mem.percent)}"),
         E("note", f"{I_DISK}   Disk  /    {tint(f'{gb(disk.used)} / {gb(disk.total)} GB  ({disk.percent:.0f}%)', disk.percent)}"),
         ]
    b = battery()
    if b:
        icon = I_CHG if b["status"] == "Charging" else I_PLUG if b["status"] in ("Full", "Not charging") else I_BAT
        state = {"Charging": "charging", "Discharging": "on battery", "Full": "fully charged",
                 "Not charging": "plugged in, not charging"}.get(b["status"], b["status"].lower())
        m += ["sep", E("header", "Battery"),
              E("note", f"{icon}   {b['cap']}%  ·  {state}" + (f"  ·  {b['eta']}" if b["eta"] else "")),]
        if b["watts"] > 0.05:
            m.append(E("note", f"     {'Charging at' if b['status'] == 'Charging' else 'Using'}  {b['watts']:.1f} W"))
        if b["health"]:
            h = b["health"]
            m.append(E("note", f"{I_HEALTH}   Health  {tint(f'{h:.0f}%', 95 if h < 50 else 75 if h < 70 else 0)}" + (f"  ·  {b['cycles']} cycles" if b["cycles"] not in (None, "0") else "")))
        if b["limit"] and b["limit"] != "100":
            m.append(E("note", f"     Charge limit  {b['limit']}%"))
    g = gpu(is_open)
    if g:
        m += ["sep", E("header", "NVIDIA GPU")]
        if not g["awake"]:
            m.append(E("note", f"{I_SLEEP}   Sleeping  <span alpha='60%'>(saving power)</span>"))
        elif "temp" in g:
            m += [E("note", f"{I_GPU2}   {html.escape(g['name'])}  ·  {tint(g['temp'] + '°C', 100 if int(g['temp']) >= 85 else 0)}  ·  {g['util']}%"),
                  E("note", f"     VRAM  {g['mem']}  ·  {float(g['power'] or 0):.0f} W")]
        else:
            m.append(E("note", f"{I_GPU2}   Awake" + ("" if is_open else "  <span alpha='60%'>(open the menu for details)</span>")))
    m += ["sep", E("header", "Power profile")]
    for key, label, icon in PROFILES:
        m.append(E("check", f"{icon}   {label}", f"powerprofilesctl set {key}", "1" if prof == key else "0"))
    m += ["sep",
          E("item", f"{I_BTOP}   Processes (btop)", f"{SCRIPTS}/WaybarScripts.sh --btop"),
          E("item", f"{I_GPU}   GPU (nvtop)", f"{SCRIPTS}/WaybarScripts.sh --nvtop"),
          E("item", f"{I_MON}   System Monitor", "gnome-system-monitor")]
    return "\x1f".join([cls, bar, tip, "\x1d".join(m)]).replace("\n", "\x1e")


def main():
    psutil.cpu_percent(interval=None)  # prime the counter
    prof, prof_at, last, is_open = profile(), time.time(), None, False
    while True:
        if time.time() - prof_at > (1 if is_open else 5):
            prof, prof_at = profile(), time.time()
        line = record(prof, is_open)
        if line != last:
            try:
                print(line, flush=True)
            except BrokenPipeError:
                return
            last = line
        r, _, _ = select.select([sys.stdin], [], [], 1 if is_open else 2)
        if r:
            msg = os.read(0, 4096).decode(errors="replace")   # raw: may hold several lines
            if not msg:          # widget went away
                return
            words = msg.split()
            if words:
                is_open = words[-1] == "open"
            prof_at = 0          # refresh profile right away


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        main()
    else:
        sys.exit(__doc__)
