#!/usr/bin/env python3
"""Network change events for the Dynamic Island (one JSON line per event).

kinds: wifi_on (ssid, signal), wifi_lost (ssid), radio_off, radio_on,
       eth_on (name), eth_off, vpn_on (ip), vpn_off, limited, portal, online
Sources: `nmcli monitor` (instant) + Tailscale status every 5 s.
A Wi-Fi drop is only reported if it lasts 3 s (no spam while roaming).
"""
# die with the parent (waybar / quickshell), and make our own long-running
# children (pactl subscribe, nmcli monitor, dbus-monitor, ...) die with us
import ctypes as _ctypes, signal as _signal
def _pdeathsig():
    try:
        _ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, _signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:
        pass
_pdeathsig()

import json
import os
import select
import subprocess
import sys
import time


sys.path.insert(0, os.path.expanduser("~/.config/hypr/waybar/scripts"))
import vpnstat  # noqa: E402  (Cloudflare WARP + Tor)


def vpn_state():
    w, t = vpnstat.warp_cached(15), vpnstat.tor()
    return {"warp_known": w is not None, "warp": bool(w and w["connected"]), "warp_mode": vpnstat.warp_mode_label(w["mode"]) if w else "",
            "tor": bool(t["running"]), "tor_ready": bool(t["running"] and t["progress"] >= 100)}


def nm(*a):
    try:
        return subprocess.run(["nmcli", *a], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return ""


def split(line):
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


def tailscale():
    try:
        d = json.loads(subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True,
                                      timeout=3).stdout or "{}")
    except Exception:
        return None, ""
    return d.get("BackendState") == "Running", ((d.get("Self") or {}).get("TailscaleIPs") or [""])[0]


def snapshot():
    s = {"radio": nm("-t", "-f", "WIFI", "radio").strip() == "enabled", "wifi": None, "signal": 0,
         "eth": None, "conn": nm("networking", "connectivity").strip()}
    for l in nm("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device").splitlines():
        f = split(l)
        if len(f) < 4:
            continue
        if f[1] == "wifi" and f[2] == "connected":
            s["wifi"] = f[3]
        elif f[1] == "ethernet" and f[2] == "connected":
            s["eth"] = f[3] or f[0]
    if s["wifi"]:
        for l in nm("-t", "-f", "IN-USE,SIGNAL", "device", "wifi", "list", "--rescan", "no").splitlines():
            f = split(l)
            if f[0] == "*":
                s["signal"] = int(f[1] or 0)
                break
    return s


def say(kind, **kw):
    try:
        print(json.dumps({"kind": kind, **kw}, ensure_ascii=False), flush=True)
    except BrokenPipeError:
        sys.exit(0)


def main():
    mon = subprocess.Popen(preexec_fn=_pdeathsig, args=["nmcli", "monitor"], stdout=subprocess.PIPE, bufsize=0)
    prev = snapshot()
    ts_up, ts_ip = tailscale()
    vp = vpn_state()
    lost_at, lost_ssid = None, None
    next_ts, dirty_at = time.time() + 5, None
    while True:
        r, _, _ = select.select([mon.stdout, sys.stdin], [], [], 1)
        now = time.time()
        if sys.stdin in r and not os.read(0, 4096):
            mon.kill()
            return
        if mon.stdout in r:
            if not os.read(mon.stdout.fileno(), 65536):     # raw read: nothing hides in a buffer
                time.sleep(2)
                mon = subprocess.Popen(preexec_fn=_pdeathsig, args=["nmcli", "monitor"], stdout=subprocess.PIPE, bufsize=0)
            dirty_at = dirty_at or now + 0.6          # let a burst of NM messages settle
        if dirty_at and now >= dirty_at:
            dirty_at = None
            cur = snapshot()
            if cur["radio"] != prev["radio"]:
                say("radio_on" if cur["radio"] else "radio_off")
                lost_at = None
            elif cur["wifi"] and cur["wifi"] != prev["wifi"]:
                if lost_at and lost_ssid == cur["wifi"]:
                    lost_at = None                       # quick reconnect to the same network: stay quiet
                else:
                    lost_at = None
                    say("wifi_on", ssid=cur["wifi"], signal=cur["signal"])
            elif prev["wifi"] and not cur["wifi"] and cur["radio"]:
                lost_at, lost_ssid = now, prev["wifi"]    # report only if it lasts 3 s
            if cur["eth"] != prev["eth"]:
                say("eth_on", name=cur["eth"]) if cur["eth"] else say("eth_off")
            if cur["conn"] != prev["conn"] and (cur["wifi"] or cur["eth"]):
                if cur["conn"] == "portal":
                    say("portal")
                elif cur["conn"] in ("limited", "none"):
                    say("limited")
                elif cur["conn"] == "full" and prev["conn"] in ("limited", "none", "portal"):
                    say("online")
            prev = cur
        if lost_at and now - lost_at >= 3:
            if not snapshot()["wifi"]:
                say("wifi_lost", ssid=lost_ssid)
            lost_at = None
        if now >= next_ts:
            next_ts = now + 5
            up, ip = tailscale()
            if up is not None and up != ts_up and ts_up is not None:
                say("vpn_on", ip=ip) if up else say("vpn_off")
            if up is not None:
                ts_up, ts_ip = up, ip
            v = vpn_state()
            if v.get("warp_known") and vp.get("warp_known") and v["warp"] != vp["warp"]:
                say("warp_on", mode=v["warp_mode"]) if v["warp"] else say("warp_off")
            elif v.get("warp_known") and vp.get("warp_known") and v["warp"] and v["warp_mode"] != vp["warp_mode"]:
                say("warp_on", mode=v["warp_mode"])
            if v["tor"] and not vp["tor"] and not v["tor_ready"]:
                say("tor_start")
            if v["tor_ready"] and not vp["tor_ready"]:
                say("tor_on")
            if vp["tor"] and not v["tor"]:
                say("tor_off")
            vp = v


if __name__ == "__main__":
    main()
