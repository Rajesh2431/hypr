#!/usr/bin/env python3
"""Cloudflare WARP + Tor status/actions, shared by wifi.py (network menu) and
the Dynamic Island's netwatch.py.

Tor runs as a *user* service (no sudo): ~/.config/systemd/user/tor-user.service,
config ~/.config/tor-user/torrc (SOCKS 127.0.0.1:9050, control 127.0.0.1:9051).

  vpnstat.py newnym     Tor: new identity (new circuits)
  vpnstat.py exitip     Tor: show the current exit IP (notification)
  vpnstat.py tor on|off start / stop the Tor user service
"""
import json
import os
import socket
import subprocess
import sys

TOR_DATA = os.path.expanduser("~/.local/share/tor-user")
TOR_UNIT = "tor-user"
WARP_MODES = [("warp", "Full VPN (WARP)"), ("warp+doh", "WARP + DNS over HTTPS"),
              ("doh", "DNS only (1.1.1.1)"), ("proxy", "Local proxy (SOCKS 40000)")]
_MODE_NAMES = {"Warp": "warp", "WarpWithDnsOverHttps": "warp+doh", "DnsOverHttps": "doh",
               "WarpProxy": "proxy", "DnsOverTls": "dot", "WarpWithDnsOverTls": "warp+dot", "TunnelOnly": "tunnel_only"}


def run(*cmd, timeout=3):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return subprocess.CompletedProcess(cmd, 1, "", "")


def warp():
    """{'installed', 'service', 'status', 'connected', 'network', 'mode'} or None if not installed."""
    if not any(os.access(os.path.join(p, "warp-cli"), os.X_OK) for p in os.environ.get("PATH", "").split(":")):
        return None
    svc = run("systemctl", "is-active", "warp-svc").stdout.strip() == "active"
    w = {"service": svc, "status": "Service off", "connected": False, "network": "", "mode": ""}
    if not svc:
        return w
    out = run("warp-cli", "--accept-tos", "status").stdout
    for line in out.splitlines():
        if line.startswith("Status update:"):
            w["status"] = line.split(":", 1)[1].strip()
        elif line.startswith("Network:"):
            w["network"] = line.split(":", 1)[1].strip()
        elif line.startswith("Reason:") and not w["network"]:
            w["network"] = line.split(":", 1)[1].strip()
    w["connected"] = w["status"] == "Connected"
    for line in run("warp-cli", "--accept-tos", "settings").stdout.splitlines():
        if "Mode:" in line:
            w["mode"] = _MODE_NAMES.get(line.split("Mode:", 1)[1].strip(), line.split("Mode:", 1)[1].strip().lower())
            break
    return w


import threading as _threading
import time as _time
_warp_cache = {"val": None, "at": 0.0, "busy": False}


def warp_cached(max_age=15):
    """Non-blocking WARP status: returns the last known value and refreshes it in a
    background thread at most every `max_age` s (warp-cli can hang for many seconds
    when warp-svc is busy; callers must never freeze on it)."""
    c = _warp_cache
    if not c["busy"] and _time.time() - c["at"] > max_age:
        c["busy"] = True

        def work():
            try:
                c["val"] = warp()
            finally:
                c["at"], c["busy"] = _time.time(), False
        _threading.Thread(target=work, daemon=True).start()
    return c["val"]


def warp_mode_label(mode):
    return dict(WARP_MODES).get(mode, mode or "?")


def _tor_ctl(*commands):
    """Send commands to Tor's control port (cookie auth); returns the replies or None."""
    try:
        cookie = open(os.path.join(TOR_DATA, "control_auth_cookie"), "rb").read().hex()
        s = socket.create_connection(("127.0.0.1", 9051), timeout=2)
        f = s.makefile("rwb")
        f.write(f"AUTHENTICATE {cookie}\r\n".encode()); f.flush()
        if not f.readline().startswith(b"250"):
            return None
        out = []
        for c in commands:
            f.write((c + "\r\n").encode()); f.flush()
            out.append(f.readline().decode(errors="replace").strip())
        f.write(b"QUIT\r\n"); f.flush()
        s.close()
        return out
    except Exception:
        return None


def tor():
    """{'running', 'progress', 'summary', 'browser'} — 'browser' = Tor Browser's own Tor is up."""
    running = run("systemctl", "--user", "is-active", TOR_UNIT).stdout.strip() in ("active", "activating")
    t = {"running": running, "progress": 0, "summary": "", "browser": _listening(9150)}
    if running:
        r = _tor_ctl("GETINFO status/bootstrap-phase")
        if r and "PROGRESS=" in r[0]:
            try:
                t["progress"] = int(r[0].split("PROGRESS=")[1].split()[0])
                t["summary"] = r[0].split('SUMMARY="')[1].split('"')[0] if 'SUMMARY="' in r[0] else ""
            except (IndexError, ValueError):
                pass
    return t


def _listening(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
        return True
    except OSError:
        return False


def notify(title, body=""):
    subprocess.Popen(["notify-send", "-a", "Tor", "-t", "3500", title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    cmd = sys.argv[1:] or [""]
    if cmd[0] == "newnym":
        r = _tor_ctl("SIGNAL NEWNYM")
        notify("Tor: new identity" if r and r[0].startswith("250") else "Tor: could not change identity",
               "New circuits will be used for new connections" if r else "Is Tor running?")
    elif cmd[0] == "exitip":
        r = run("curl", "-s", "--max-time", "20", "--socks5-hostname", "127.0.0.1:9050",
                "https://check.torproject.org/api/ip", timeout=25)
        try:
            d = json.loads(r.stdout)
            notify("Tor exit IP: " + d.get("IP", "?"), "Using Tor ✔" if d.get("IsTor") else "Not going through Tor!")
        except Exception:
            notify("Tor: could not check the exit IP", "Is Tor connected?")
    elif cmd[0] == "tor" and len(cmd) == 2 and cmd[1] in ("on", "off"):
        run("systemctl", "--user", "start" if cmd[1] == "on" else "stop", TOR_UNIT, timeout=15)
    else:
        sys.exit(__doc__)
