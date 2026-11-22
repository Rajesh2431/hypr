#!/usr/bin/env python3
"""Spider-Sense radar feed for cffi/radar (cffi/radar-widget.c).

Every 2 s it checks what a spider-sense should tingle about and turns each
thing into a blip. Each kind has its own bearing; the more urgent it is, the
closer it sits to the centre:

  CPU load (30°) · memory (80°) · temperature (130°) · battery (200°)
  unread notifications (255°) · microphone / screen share in use (320°)

Line:  level \x1f tooltip \x1f angle\x1cdist\x1c#rgb\x1cpulse \x1d … \x1f badge \x1f focus(0|1)
The radar replaces the bell, so notification state is checked every 0.5 s (a stat() when
nothing changed); the system checks run every 2 s.
Only reads /proc, /sys, ~/.cache/island/center-state.json and pactl (cheap).
"""
import ctypes, json, os, signal, subprocess, sys, time

try:
    ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)   # die with waybar
except Exception:
    pass

CRIMSON, BLUE, YELLOW, ORANGE, PAPER, PURPLE = "#FF1744", "#00B8FF", "#FFD43B", "#FF6B24", "#F5F0E8", "#8B35FF"
HWMON = ["/sys/class/hwmon/hwmon1/temp1_input", "/sys/class/thermal/thermal_zone0/temp"]
STATE = os.path.expanduser("~/.cache/island/center-state.json")


def rd(p, d=""):
    try:
        with open(p) as f:
            return f.read().strip()
    except OSError:
        return d


def cpu_sample():
    v = [int(x) for x in rd("/proc/stat").splitlines()[0].split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return idle, sum(v)


def mem_pct():
    m = {}
    for l in rd("/proc/meminfo").splitlines():
        k, v = l.split(":", 1)
        m[k] = int(v.split()[0])
    return 100 * (1 - m.get("MemAvailable", 0) / max(1, m.get("MemTotal", 1)))


def temp_c():
    for p in HWMON:
        try:
            return int(rd(p)) / 1000
        except ValueError:
            continue
    return None


def battery():
    for b in ("BAT0", "BAT1"):
        cap = rd(f"/sys/class/power_supply/{b}/capacity")
        if cap:
            return int(cap), rd(f"/sys/class/power_supply/{b}/status")
    return None, ""


def mic_in_use():
    """True when something records a real input (not a .monitor of the speakers, e.g. cava)."""
    try:
        outs = json.loads(subprocess.run(["pactl", "-f", "json", "list", "source-outputs"],
                                         capture_output=True, text=True, timeout=2).stdout or "[]")
        srcs = json.loads(subprocess.run(["pactl", "-f", "json", "list", "sources", "short"],
                                         capture_output=True, text=True, timeout=2).stdout or "[]")
    except Exception:
        return False
    monitors = {str(x["index"]) for x in srcs if str(x.get("name", "")).endswith(".monitor")}
    return any(str(o.get("source")) not in monitors and o.get("properties", {}).get("stream.capture.sink") != "true"
               for o in outs)


def unread():
    try:
        d = json.loads(rd(STATE, "{}"))
        return int(d.get("count", 0)), d.get("focusName") if d.get("focus") else None
    except ValueError:
        return 0, None


def sev(value, lo, hi):
    """0 at lo, 1 at hi"""
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def main():
    last = None
    prev = cpu_sample()
    sysat, st_m = 0.0, None
    cpu = mem = 0.0; temp = None; bat, bstat = None, ""; mic = False
    while True:
        time.sleep(0.5)
        try:
            m = os.stat(STATE).st_mtime
        except OSError:
            m = None
        if time.time() - sysat < 2 and m == st_m:
            continue
        st_m = m
        if time.time() - sysat >= 2:
            sysat = time.time()
            cur = cpu_sample()
            cpu = 100 * (1 - (cur[0] - prev[0]) / max(1, cur[1] - prev[1]))
            prev = cur
            mem, temp = mem_pct(), temp_c()
            bat, bstat = battery()
            mic = mic_in_use()
        nunread, focus = unread()

        blips, lines, level = [], [], 0
        def add(angle, s, color, label, pulse=False, danger_at=0.85, alert_at=0.45):
            nonlocal level
            blips.append(f"{angle}\x1c{0.9 - 0.75 * s:.2f}\x1c{color}\x1c{1 if pulse else 0}")
            lines.append(label)
            level = max(level, 2 if s >= danger_at else 1 if s >= alert_at else 0)

        if cpu >= 25:
            s = sev(cpu, 25, 95)
            add(30, s, CRIMSON if s > .6 else YELLOW, f"<span color='{CRIMSON}'>●</span>  CPU working hard  <b>{cpu:.0f}%</b>", s > .85)
        if mem >= 60:
            s = sev(mem, 60, 95)
            add(80, s, PURPLE if s < .6 else CRIMSON, f"<span color='{PURPLE}'>●</span>  Memory filling up  <b>{mem:.0f}%</b>", s > .85)
        if temp is not None and temp >= 62:
            s = sev(temp, 62, 92)
            add(130, s, ORANGE if s < .6 else CRIMSON, f"<span color='{ORANGE}'>●</span>  Running hot  <b>{temp:.0f}°C</b>", s > .8)
        if bat is not None and bstat not in ("Charging", "Full") and bat <= 40:
            s = sev(40 - bat, 0, 32)          # 40 % -> 0, 8 % -> 1
            add(200, s, YELLOW if s < .6 else CRIMSON, f"<span color='{YELLOW}'>●</span>  Battery low  <b>{bat}%</b>", s > .7)
        if nunread > 0:
            s = sev(nunread, 0, 12) * 0.6     # notifications alone never mean danger
            add(255, s, BLUE, f"<span color='{BLUE}'>●</span>  {nunread} unread notification{'s' if nunread != 1 else ''}", False)
        if mic:
            add(320, 0.5, ORANGE, f"<span color='{ORANGE}'>●</span>  Microphone is listening", True, danger_at=2, alert_at=0.4)

        # demo hook: `touch ~/.cache/spider-sense-demo` shows fake danger blips for 20 s (screenshots / testing)
        demo = os.path.expanduser("~/.cache/spider-sense-demo")
        if os.path.exists(demo) and time.time() - os.path.getmtime(demo) < 20:
            blips = [f"30\x1c0.2\x1c{CRIMSON}\x1c1", f"130\x1c0.45\x1c{ORANGE}\x1c0", f"255\x1c0.75\x1c{BLUE}\x1c0", f"320\x1c0.55\x1c{ORANGE}\x1c1"]
            lines = [f"<span color='{CRIMSON}'>●</span>  CPU working hard  <b>97%</b>  (demo)", f"<span color='{ORANGE}'>●</span>  Running hot  <b>84°C</b>  (demo)"]
            level = 2
        mood = ("ALL QUIET", "TINGLING", "DANGER!")[level]
        head = f"<span font_family='Bangers' size='x-large' color='{(PAPER, YELLOW, CRIMSON)[level]}'>SPIDER-SENSE: {mood}</span>"
        body = "\n".join(lines) if lines else "<span alpha='70%'>Nothing on the radar. The city sleeps.</span>"
        foot = f"\n\n<span alpha='55%' size='small'>closer to the centre = more urgent" + \
               (f"  ·  {focus} on" if focus else "") + "\nclick: Control Center  ·  right-click: Do Not Disturb</span>"
        badge = "" if not nunread else str(nunread) if nunread < 100 else "99+"
        line = "\x1f".join([("calm", "alert", "danger")[level], (head + "\n" + body + foot).replace("\n", "\x1e"),
                            "\x1d".join(blips), badge, "1" if focus else "0"])
        if line != last:
            try:
                print(line, flush=True)
            except BrokenPipeError:
                return
            last = line


if __name__ == "__main__":
    main()
