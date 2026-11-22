#!/usr/bin/env python3
"""VPN button for Waybar: Tailscale (+ Cloudflare WARP and Tor sections, moved from the Wi-Fi menu)

Tailscale for Waybar via cffi/menu-widget.so (same drop-down as Wi-Fi / Bluetooth).

Bar: Tailscale icon only (state in the CSS class: on / off / exit / login).
Click: menu with connect/disconnect, this device (copy IP / name), every device
(copy IP or name, SSH, ping, send a file with Taildrop, use as exit node), exit node
picker, settings (accept routes, MagicDNS, shields up, Tailscale SSH server),
receive Taildrop files, network check and the admin console.
Right-click (module config): connect / disconnect.

  tailscale.py status     feed for the widget (no sudo: the user is the tailscale operator)
  tailscale.py toggle     tailscale up / down
  tailscale.py send HOST  pick files with zenity and send them with Taildrop
  tailscale.py receive    save waiting Taildrop files to ~/Downloads/Taildrop
"""
import ctypes, signal, sys
if len(sys.argv) > 1 and sys.argv[1] == "status":   # the feed dies with waybar
    try:
        ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)
    except Exception:
        pass
import html, json, os, select, shlex, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vpnstat  # noqa: E402  (WARP + Tor helpers, shared with the old Wi-Fi menu)
from datetime import datetime, timezone

PUNK = os.environ.get("PUNK_ICONS") == "1"
SELF = shlex.quote(os.path.abspath(__file__))
TERM = "kitty --hold -e"
ADMIN = "https://login.tailscale.com/admin/machines"
I_TS, I_COPY, I_DEV, I_EXIT, I_SET, I_SSH, I_PING, I_SEND, I_RECV, I_NET, I_WEB, I_LOGIN = (
    "\U000f0582", "\U000f018f", "\U000f0379", "\U000f0206", "\U000f0493", "\U000f018d",
    "\U000f0bf8", "\U000f048a", "\U000f01da", "\U000f0a5f", "\U000f059f", "\U000f0342")
OS_ICON = {"linux": "", "macOS": "", "windows": "", "android": "", "iOS": ""}
DIM = "<span alpha='55%'>{}</span>"
VPN = 'python3 "%s"' % os.path.join(os.path.dirname(os.path.abspath(__file__)), "vpnstat.py")
I_WARP, I_TOR, I_NEW = "\U000f015f", "\U000f05f9", "\U000f0453"


def run(*a, timeout=4):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def notify(title, body=""):
    subprocess.Popen(["notify-send", "-a", "Tailscale", "-t", "3000", title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ago(ts):
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if t.year < 2000:
            return ""
        s = (datetime.now(timezone.utc) - t).total_seconds()
    except Exception:
        return ""
    return ("just now" if s < 60 else f"{int(s // 60)} min ago" if s < 3600 else
            f"{int(s // 3600)} h ago" if s < 86400 else f"{int(s // 86400)} days ago")


def snapshot():
    r = run("tailscale", "status", "--json")
    if r is None or not r.stdout.strip():
        return None
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return None
    p = run("tailscale", "debug", "prefs")
    try:
        prefs = json.loads(p.stdout) if p and p.returncode == 0 else {}
    except ValueError:
        prefs = {}
    me = d.get("Self") or {}
    peers = []
    for x in (d.get("Peer") or {}).values():
        ips = x.get("TailscaleIPs") or [""]
        peers.append({"name": x.get("HostName") or "?", "dns": (x.get("DNSName") or "").rstrip("."),
                      "ip": ips[0], "online": bool(x.get("Online")), "os": x.get("OS", ""),
                      "exit": bool(x.get("ExitNode")), "exitopt": bool(x.get("ExitNodeOption")),
                      "seen": x.get("LastSeen", "")})
    peers.sort(key=lambda q: (not q["online"], q["name"].lower()))
    ips = me.get("TailscaleIPs") or []
    return {"state": d.get("BackendState", ""), "tailnet": (d.get("CurrentTailnet") or {}).get("Name", ""),
            "name": me.get("HostName", ""), "dns": (me.get("DNSName") or "").rstrip("."),
            "ip4": next((i for i in ips if ":" not in i), ""), "ip6": next((i for i in ips if ":" in i), ""),
            "peers": peers, "auth": d.get("AuthURL", ""),
            "routes": bool(prefs.get("RouteAll")), "dnsok": bool(prefs.get("CorpDNS", True)),
            "shields": bool(prefs.get("ShieldsUp")), "ssh": bool(prefs.get("RunSSH")),
            "lan": bool(prefs.get("ExitNodeAllowLANAccess"))}


def E(*f):
    return "\x1c".join(f)


def copy(text, label):
    return f"printf %s {shlex.quote(text)} | wl-copy && notify-send -a Tailscale -t 2000 Copied {shlex.quote(label)}"


def tset(flag, label):
    return f"tailscale set {flag} || notify-send -a Tailscale 'Tailscale' {shlex.quote('Could not change ' + label)}"


def vpn_tip(wp, tr):
    s = ""
    if wp and wp.get("connected"):
        s += f"\n{I_WARP}  WARP on · {vpnstat.warp_mode_label(wp['mode'])}"
    if tr and tr.get("running"):
        s += f"\n{I_TOR}  Tor " + ("connected" if tr["progress"] >= 100 else f"connecting {tr['progress']}%")
    return s


def vpn_menu(wp, tr):
    """Cloudflare WARP + Tor sections (moved here from the Wi-Fi menu)."""
    m = []
    if wp:
        m += ["sep", E("header", "Cloudflare WARP"),
              E("check", "Connected" + ("" if wp["service"] else "  <span alpha='55%'>(warp-svc not running)</span>"),
                f"warp-cli --accept-tos {'disconnect' if wp['connected'] else 'connect'}", "1" if wp["connected"] else "0")]
        if wp["service"]:
            state = wp["status"] + (f" · {wp['network']}" if wp["network"] and wp["connected"] else "")
            m += [E("note", f"{I_WARP}   {html.escape(state)}"),
                  E("sub", f"     Mode  <span alpha='55%'>{html.escape(vpnstat.warp_mode_label(wp['mode']))}</span>")]
            for key, label in vpnstat.WARP_MODES:
                m.append(E("check", label, f"warp-cli --accept-tos mode {key}", "1" if wp["mode"] == key else "0"))
            m.append("end")
    if tr is not None:
        m += ["sep", E("header", "Tor"),
              E("check", "Running  <span alpha='55%'>(SOCKS 127.0.0.1:9050)</span>", f"{VPN} tor {'off' if tr['running'] else 'on'}",
                "1" if tr["running"] else "0")]
        if tr["running"]:
            if tr["progress"] >= 100:
                m += [E("note", f"{I_TOR}   Connected to the Tor network"),
                      E("item", f"{I_NEW}   New identity", f"{VPN} newnym"),
                      E("item", f"{I_WEB}   Check exit IP", f"{VPN} exitip")]
            else:
                m.append(E("note", f"{I_TOR}   Connecting… {tr['progress']}%" + (f"  <span alpha='55%'>{html.escape(tr['summary'])}</span>" if tr["summary"] else "")))
        if tr["browser"]:
            m.append(E("note", f"{I_TOR}   Tor Browser is running"))
        m.append(E("item", f"{I_WEB}   Open Tor Browser", "torbrowser-launcher"))
    return m


def record(st, wp=None, tr=None):
    if st is None:
        return "\x1f".join(["missing", "" if PUNK else I_TS, "<b>Tailscale</b>\nnot running (tailscaled service)" + vpn_tip(wp, tr),
                            "\x1d".join([E("note", "tailscaled is not running")] + vpn_menu(wp, tr))]).replace("\n", "\x1e")
    up = st["state"] == "Running"
    exitp = next((p for p in st["peers"] if p["exit"]), None)
    cls = "exit" if up and exitp else "on" if up else "login" if st["state"] in ("NeedsLogin", "Starting", "NeedsMachineAuth") else "off"
    online = sum(p["online"] for p in st["peers"])

    tip = "<b>Tailscale</b>  " + {"on": "connected", "exit": "connected", "off": "off", "login": st["state"]}[cls]
    if st["tailnet"]:
        tip += f"\n{html.escape(st['tailnet'])}"
    if up:
        tip += f"\n{html.escape(st['dns'] or st['name'])}\n{st['ip4']}\n{online}/{len(st['peers'])} devices online"
        if exitp:
            tip += f"\nExit node: {html.escape(exitp['name'])}"
    tip += vpn_tip(wp, tr)
    tip += "\n<span alpha='55%' size='small'>Click: menu · Right-click: Tailscale on / off</span>"

    m = [E("header", "<b>Tailscale</b>" + (f"  {DIM.format('· ' + html.escape(st['tailnet']))}" if st["tailnet"] else "")),
         E("check", "Connected", "tailscale down" if up else
           f"tailscale up || notify-send -a Tailscale Tailscale 'Could not connect'", "1" if up else "0")]
    if cls == "login":
        m.append(E("item", f"{I_LOGIN}   Log in…", f"{TERM} tailscale login"))
    if up:
        m += ["sep", E("header", "This device"),
              E("note", f"{I_DEV}   <b>{html.escape(st['name'])}</b>  {DIM.format(html.escape(st['dns']))}")]
        if st["ip4"]:
            m.append(E("item", f"{I_COPY}   {st['ip4']}  {DIM.format('copy IPv4')}", copy(st["ip4"], st["ip4"])))
        if st["ip6"]:
            m.append(E("item", f"{I_COPY}   {DIM.format(st['ip6'])}  {DIM.format('copy IPv6')}", copy(st["ip6"], st["ip6"])))
        if st["dns"]:
            m.append(E("item", f"{I_COPY}   {html.escape(st['dns'])}  {DIM.format('copy name')}", copy(st["dns"], st["dns"])))

        # devices: one submenu each
        m += ["sep", E("header", "Devices  " + DIM.format(f"{online}/{len(st['peers'])} online"))]
        for p in st["peers"]:
            dot = "<span color='#30d158'>●</span>" if p["online"] else "<span alpha='40%'>○</span>"
            tag = f"  <span color='#FFD43B'>{I_EXIT} exit</span>" if p["exit"] else ""
            m.append(E("sub", f"{dot}  {OS_ICON.get(p['os'], ' ')}  {html.escape(p['name'])}   {DIM.format(p['ip'])}{tag}"))
            if not p["online"] and ago(p["seen"]):
                m.append(E("note", f"Last seen {ago(p['seen'])}"))
            target = p["dns"] or p["ip"]
            m.append(E("item", f"{I_COPY}   Copy IP  {DIM.format(p['ip'])}", copy(p["ip"], f"{p['name']} {p['ip']}")))
            if p["dns"]:
                m.append(E("item", f"{I_COPY}   Copy name  {DIM.format(html.escape(p['dns']))}", copy(p["dns"], p["dns"])))
            if p["online"]:
                m += ["sep",
                      E("item", f"{I_SSH}   SSH", f"{TERM} tailscale ssh {shlex.quote(target)}"),
                      E("item", f"{I_PING}   Ping", f"{TERM} tailscale ping {shlex.quote(target)}"),
                      E("item", f"{I_SEND}   Send files…", f"python3 {SELF} send {shlex.quote(target)}")]
            if p["exitopt"]:
                m.append(E("check", f"{I_EXIT}   Use as exit node",
                           tset("--exit-node=" if p["exit"] else f"--exit-node={shlex.quote(p['ip'])}", "the exit node"),
                           "1" if p["exit"] else "0"))
            m.append("end")

        # exit node
        opts = [p for p in st["peers"] if p["exitopt"]]
        m += ["sep", E("sub", f"{I_EXIT}   Exit node  {DIM.format(html.escape(exitp['name']) if exitp else 'none')}"),
              E("check", "None (direct internet)", tset("--exit-node=", "the exit node"), "0" if exitp else "1")]
        for p in opts:
            m.append(E("check", f"{html.escape(p['name'])}" + ("" if p["online"] else f"  {DIM.format('offline')}"),
                       tset(f"--exit-node={shlex.quote(p['ip'])}", "the exit node"), "1" if p["exit"] else "0"))
        if not opts:
            m.append(E("note", "No device offers an exit node"))
        m += ["sep", E("check", "Allow local network access", tset(f"--exit-node-allow-lan-access={'false' if st['lan'] else 'true'}", "LAN access"),
                       "1" if st["lan"] else "0"), "end"]

        # settings
        m += [E("sub", f"{I_SET}   Settings"),
              E("check", "Use Tailscale DNS (MagicDNS)", tset(f"--accept-dns={'false' if st['dnsok'] else 'true'}", "DNS"), "1" if st["dnsok"] else "0"),
              E("check", "Accept subnet routes", tset(f"--accept-routes={'false' if st['routes'] else 'true'}", "routes"), "1" if st["routes"] else "0"),
              E("check", "Run Tailscale SSH server", tset(f"--ssh={'false' if st['ssh'] else 'true'}", "SSH"), "1" if st["ssh"] else "0"),
              E("check", "Shields up (block incoming)", tset(f"--shields-up={'false' if st['shields'] else 'true'}", "shields up"), "1" if st["shields"] else "0"),
              "end"]

        m += ["sep", E("item", f"{I_RECV}   Receive files (Taildrop)", f"python3 {SELF} receive"),
              E("item", f"{I_NET}   Network check…", f"{TERM} tailscale netcheck")]
    m += ["sep", E("item", f"{I_WEB}   Tailscale admin console", f"xdg-open {ADMIN}")]
    m += vpn_menu(wp, tr)

    bar = "" if PUNK else I_TS
    if wp and wp.get("connected"):
        cls += " warp"
    if tr and tr.get("running"):
        cls += " tor"
    return "\x1f".join([cls, bar, tip, "\x1d".join(m)]).replace("\n", "\x1e")


def feed():
    last, is_open, next_at, st, wp, tr = None, False, 0.0, None, None, None
    while True:
        if time.time() >= next_at:
            st = snapshot()
            wp, tr = vpnstat.warp_cached(15), vpnstat.tor()
            next_at = time.time() + (2 if is_open else 5)
        line = record(st, wp, tr)
        if line != last:
            try:
                print(line, flush=True)
            except BrokenPipeError:
                return
            last = line
        r, _, _ = select.select([sys.stdin], [], [], max(0.2, next_at - time.time()))
        if r:
            msg = os.read(0, 4096).decode(errors="replace")
            if not msg:
                return
            words = msg.split()
            is_open = bool(words) and words[-1] == "open"
            next_at = 0


def send(host):
    r = run("zenity", "--file-selection", "--multiple", "--separator=\n", f"--title=Send to {host} (Taildrop)", timeout=600)
    files = [f for f in (r.stdout.splitlines() if r and r.returncode == 0 else []) if f]
    if not files:
        return
    notify(f"Sending to {host}…", "\n".join(os.path.basename(f) for f in files[:5]))
    r = run("tailscale", "file", "cp", *files, f"{host}:", timeout=3600)
    if r and r.returncode == 0:
        notify(f"Sent to {host}", f"{len(files)} file(s)")
    else:
        notify(f"Could not send to {host}", (r.stderr.strip() if r else "timed out")[:200])


def receive():
    d = os.path.expanduser("~/Downloads/Taildrop")
    os.makedirs(d, exist_ok=True)
    before = set(os.listdir(d))
    r = run("tailscale", "file", "get", "--conflict=rename", d, timeout=120)
    new = sorted(set(os.listdir(d)) - before)
    if r and r.returncode == 0 and new:
        notify(f"Received {len(new)} file(s)", "~/Downloads/Taildrop\n" + "\n".join(new[:5]))
        subprocess.Popen(["xdg-open", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif r and r.returncode == 0:
        notify("No waiting files", "Nothing has been sent to this device")
    else:
        notify("Could not receive files", (r.stderr.strip() if r else "timed out")[:200])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        feed()
    elif cmd == "toggle":
        st = snapshot()
        r = run("tailscale", "down" if st and st["state"] == "Running" else "up", timeout=30)
        if r is None or r.returncode != 0:
            notify("Tailscale", (r.stderr.strip() if r else "timed out")[:200] or "failed")
    elif cmd == "send" and len(sys.argv) > 2:
        send(sys.argv[2])
    elif cmd == "receive":
        receive()
    else:
        print(__doc__)
