#!/usr/bin/env python3
"""Wi-Fi for Waybar via cffi/menu-widget.so (same drop-down style as Bluetooth).

Bar: signal icon only (speeds are in the tooltip and menu). Click: menu with
Wi-Fi on/off, the connected network (IP, speed, disconnect, forget), nearby
networks (rescanned while the menu is open), hidden network, settings.

  wifi.py status            feed for the widget
  wifi.py connect SSID      connect (asks for a password with rofi if needed)
  wifi.py hidden            connect to a hidden network
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
import json
import os
import select
import shlex
import subprocess
import sys
import time

SELF = 'python3 "%s"' % __file__
VPN = 'python3 "%s"' % os.path.join(os.path.dirname(os.path.abspath(__file__)), "vpnstat.py")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vpnstat  # noqa: E402  (WARP + Tor helpers)
I_SIG = ["\U000f092f", "\U000f091f", "\U000f0922", "\U000f0925", "\U000f0928"]
I_OFF, I_NONE, I_ETH, I_LOCK = "\U000f092e", "\U000f092d", "\U000f0200", "\U000f033e"
I_HIDDEN, I_SETTINGS, I_UNLINK, I_TRASH = "\U000f0c3b", "\U000f0493", "\U000f0338", "\U000f0a7a"


def nm(*args, timeout=10):
    try:
        return subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 1, "", "timed out")


def split(line):
    """nmcli -t splits on ':' and escapes literal ':' as '\\:'."""
    out, cur, i = [], "", 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line):
            cur += line[i + 1]; i += 2; continue
        if line[i] == ":":
            out.append(cur); cur = ""
        else:
            cur += line[i]
        i += 1
    return out + [cur]


def notify(title, body=""):
    subprocess.Popen(["notify-send", "-a", "Wi-Fi", "-i", "network-wireless", "-t", "3000", title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


PUNK = os.environ.get("PUNK_ICONS") == "1"   # Spider-Punk style: icon comes from CSS (state class), no glyph


def sig_icon(s):
    return I_SIG[min(4, max(0, s // 20))]


def human(bps):
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024 or unit == "GB/s":
            return f"{bps:.0f} {unit}" if unit == "B/s" else f"{bps:.1f} {unit}"
        bps /= 1024


class Speed:
    def __init__(self):
        self.prev = {}

    def __call__(self, dev):
        try:
            rx = int(open(f"/sys/class/net/{dev}/statistics/rx_bytes").read())
            tx = int(open(f"/sys/class/net/{dev}/statistics/tx_bytes").read())
        except (OSError, ValueError):
            return 0, 0
        now = time.time()
        p = self.prev.get(dev)
        self.prev[dev] = (now, rx, tx)
        if not p or now - p[0] <= 0:
            return 0, 0
        return (rx - p[1]) / (now - p[0]), (tx - p[2]) / (now - p[0])


I_WARP, I_TOR, I_NEW, I_WEB = "\U000f015f", "\U000f05f9", "\U000f0453", "\U000f059f"
I_TS, I_DEV, I_COPY = "\U000f0582", "\U000f0379", "\U000f018f"
TS_OS = {"linux": "\uf17c", "macOS": "\uf179", "windows": "\uf17a", "android": "\uf17b", "iOS": "\uf179"}


def tailscale():
    """Tailscale state (no sudo needed: the user is the tailscale operator)."""
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=3)
        d = json.loads(r.stdout or "{}")
    except Exception:
        return None
    if not d:
        return None
    me = d.get("Self") or {}
    peers = sorted((d.get("Peer") or {}).values(), key=lambda p: (not p.get("Online"), (p.get("HostName") or "").lower()))
    return {"up": d.get("BackendState") == "Running", "state": d.get("BackendState", ""),
            "ip": (me.get("TailscaleIPs") or [""])[0], "tailnet": (d.get("CurrentTailnet") or {}).get("Name", ""),
            "peers": [{"name": p.get("HostName") or "?", "ip": (p.get("TailscaleIPs") or [""])[0],
                       "online": bool(p.get("Online")), "os": p.get("OS", "")} for p in peers]}


def snapshot():
    devs = [split(l) for l in nm("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device").stdout.splitlines()]
    wifi_dev = next((d for d in devs if d[1] == "wifi"), None)
    eth = next((d for d in devs if d[1] == "ethernet" and d[2] == "connected"), None)
    radio = nm("-t", "-f", "WIFI", "radio").stdout.strip() == "enabled"
    nets = {}
    if radio and wifi_dev:
        for l in nm("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "no").stdout.splitlines():
            f = split(l)
            if len(f) < 4 or not f[1]:
                continue
            ssid, sig = f[1], int(f[2] or 0)
            cur = nets.get(ssid)
            if not cur or sig > cur["signal"] or f[0] == "*":
                nets[ssid] = {"ssid": ssid, "signal": sig, "secure": bool(f[3]) and f[3] != "--",
                              "active": f[0] == "*" or bool(cur and cur["active"])}
    saved = {split(l)[0] for l in nm("-t", "-f", "NAME,TYPE", "connection", "show").stdout.splitlines()
             if l.endswith(":802-11-wireless")}
    active = next((n for n in nets.values() if n["active"]), None)
    ip = ""
    if wifi_dev and wifi_dev[2] == "connected":
        for l in nm("-t", "-f", "IP4.ADDRESS", "device", "show", wifi_dev[0]).stdout.splitlines():
            ip = split(l)[-1].split("/")[0]
            break
        if not active and wifi_dev[3]:
            active = {"ssid": wifi_dev[3], "signal": 0, "secure": True, "active": True}
    return {"warp": None, "tor": None, "ts": None,  "dev": wifi_dev[0] if wifi_dev else None, "radio": radio, "eth": eth, "nets": nets,
            "saved": saved, "active": active, "ip": ip}


def record(st, speed, scanning):
    E = lambda *f: "\x1c".join(f)
    a = st["active"]
    down, up = speed(st["dev"]) if st["dev"] and a else (0, 0)
    if not st["dev"]:
        bar, cls, tip = I_ETH if st["eth"] else I_NONE, "ethernet" if st["eth"] else "disconnected", "No Wi-Fi adapter"
    elif not st["radio"]:
        bar, cls, tip = I_OFF, "off", "Wi-Fi is off"
    elif a:
        bar, cls = sig_icon(a["signal"]), "connected"
        tip = (f"<b>{html.escape(a['ssid'])}</b>  ·  {a['signal']}%\n{st['ip']}\n\n"
               f"↓ {human(down)}     ↑ {human(up)}")
    else:
        bar, cls, tip = (I_ETH, "ethernet", "Ethernet connected") if st["eth"] else (I_NONE, "disconnected", "Not connected")
    ts, wp, tr = st.get("ts"), st.get("warp"), st.get("tor")
    if wp:
        tip += f"\n{I_WARP}  WARP " + (f"on · {vpnstat.warp_mode_label(wp['mode'])}" if wp["connected"] else wp["status"].lower())
    if tr and tr["running"]:
        tip += f"\n{I_TOR}  Tor " + ("connected" if tr["progress"] >= 100 else f"connecting {tr['progress']}%")
    if ts:
        tip += f"\n{I_TS}  Tailscale " + (f"on · {ts['ip']}" if ts["up"] else "off")
    tip += "\n\n<span alpha='55%' size='small'>Click: Wi-Fi menu · Right-click: network settings</span>"

    m = [E("header", "<b>Wi-Fi</b>")]
    if st["dev"]:
        m.append(E("check", "Enabled", f"nmcli radio wifi {'off' if st['radio'] else 'on'}", "1" if st["radio"] else "0"))
    if st["eth"]:
        m += ["sep", E("header", "Ethernet"), E("note", f"{I_ETH}   {html.escape(st['eth'][3] or st['eth'][0])}  connected")]
    if st["dev"] and st["radio"]:
        if a:
            q = shlex.quote(a["ssid"])
            m += ["sep", E("header", "Connected"),
                  E("sub", f"{sig_icon(a['signal'])}   <b>{html.escape(a['ssid'])}</b>    <span alpha='60%'>{a['signal']}%</span>"),
                  E("note", f"IP  {st['ip'] or '…'}"),
                  E("note", f"↓ {human(down)}     ↑ {human(up)}"),
                  "sep",
                  E("item", f"{I_UNLINK}   Disconnect", f"nmcli device disconnect {st['dev']}"),
                  E("item", f"{I_TRASH}   Forget network", f"nmcli connection delete id {q}"),
                  "end"]
        # sort by signal *level* (bars), then name: stable order while the menu is open
        others = sorted([n for n in st["nets"].values() if not n["active"]],
                        key=lambda n: (-min(4, n["signal"] // 20), n["ssid"].lower()))
        m += ["sep", E("header", "Available networks" + ("  <span alpha='60%'>· searching…</span>" if scanning else ""))]
        if others:
            for n in others[:14]:
                lab = f"{sig_icon(n['signal'])}   {html.escape(n['ssid'])}"
                tags = []
                if n["ssid"] in st["saved"]:
                    tags.append("saved")
                if n["secure"]:
                    tags.append(I_LOCK)
                if tags:
                    lab += f"    <span alpha='55%'>{'  '.join(tags)}</span>"
                m.append(E("item", lab, f"{SELF} connect {shlex.quote(n['ssid'])}"))
        else:
            m.append(E("note", "Searching…" if scanning else "No networks found"))
        m += ["sep", E("item", f"{I_HIDDEN}   Connect to hidden network…", f"{SELF} hidden")]
    # WARP, Tor and Tailscale live in the VPN button now (cffi/tailscale, scripts/tailscale.py)
    m += ["sep", E("item", f"{I_SETTINGS}   Network Settings…", "nm-connection-editor")]
    if PUNK:   # icon from CSS: class carries the state + signal level
        cls = f"{cls} s{min(4, max(0, a['signal'] // 20))}" if cls == "connected" and a else cls
        bar = ""
    # no 5th (hover) field: the icon stays alone on hover (speeds are in the tooltip and the menu)
    return "\x1f".join([cls, bar, tip, "\x1d".join(m)]).replace("\n", "\x1e")


def main():
    speed, last, is_open, scan_until, next_at = Speed(), None, False, 0.0, 0.0
    st = None
    while True:
        now = time.time()
        if now >= next_at:
            st = snapshot()
            next_at = now + (2 if is_open else 4)
        line = record(st, speed, now < scan_until)
        if line != last:
            try:
                print(line, flush=True)
            except BrokenPipeError:
                return
            last = line
        r, _, _ = select.select([sys.stdin], [], [], 2)
        if r:
            msg = os.read(0, 4096).decode(errors="replace")   # raw: may hold several lines
            if not msg:
                return
            words = msg.split()
            is_open = bool(words) and words[-1] == "open"
            if is_open:
                subprocess.Popen(["nmcli", "device", "wifi", "rescan"], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                scan_until = time.time() + 6
            next_at = 0


# ------------------------------------------------------------------ actions
def ask(prompt, password=False):
    cmd = ["rofi", "-dmenu", "-p", prompt, "-lines", "0", "-theme-str",
           "window { width: 420px; } listview { lines: 0; } entry { placeholder: \"" + prompt + "\"; }"]
    if password:
        cmd.append("-password")
    r = subprocess.run(cmd, input="", capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def wifi_dev():
    for l in nm("-t", "-f", "DEVICE,TYPE", "device").stdout.splitlines():
        f = split(l)
        if f[1] == "wifi":
            return f[0]
    return None


def connect(ssid, hidden=False):
    saved = {split(l)[0] for l in nm("-t", "-f", "NAME,TYPE", "connection", "show").stdout.splitlines()
             if l.endswith(":802-11-wireless")}
    if ssid in saved and not hidden:
        notify("Connecting…", ssid)
        r = nm("connection", "up", "id", ssid, timeout=40)
        # never delete a saved network just because it is out of range right now
        return notify("Connected" if r.returncode == 0 else "Could not connect", ssid)
    secure = hidden
    if not hidden:
        for l in nm("-t", "-f", "SSID,SECURITY", "device", "wifi", "list", "--rescan", "no").stdout.splitlines():
            f = split(l)
            if f[0] == ssid:
                secure = bool(f[1]) and f[1] != "--"
                break
    dev = wifi_dev()
    name = ssid
    args = ["connection", "add", "type", "wifi", "ifname", dev or "*", "con-name", name, "ssid", ssid]
    if hidden:
        args += ["802-11-wireless.hidden", "yes"]
    pw = None
    if secure:
        pw = ask(f"Password for {ssid}", password=True)
        if not pw:
            return  # cancelled: nothing was changed
        args += ["wifi-sec.key-mgmt", "wpa-psk"]
    if nm(*args).returncode != 0:
        return notify("Could not create connection", ssid)
    if pw:
        # set the password through nmcli's editor on stdin, never on a command line
        ed = subprocess.run(["nmcli", "connection", "edit", "id", name], text=True, capture_output=True,
                            input=f"set 802-11-wireless-security.psk {pw}\nsave persistent\nquit\n", timeout=15)
        if ed.returncode != 0:
            nm("connection", "delete", "id", name)
            return notify("Could not save the password", ssid)
    notify("Connecting…", ssid)
    r = nm("connection", "up", "id", name, timeout=45)
    if r.returncode == 0:
        notify("Connected", ssid)
    else:
        nm("connection", "delete", "id", name)
        notify("Could not connect", ssid + ("\nWrong password?" if pw else ""))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "status":
        main()
    elif cmd == "connect" and len(sys.argv) == 3:
        connect(sys.argv[2])
    elif cmd == "hidden":
        ssid = ask("Network name (SSID)")
        if ssid:
            connect(ssid, hidden=True)
    else:
        sys.exit(__doc__)
