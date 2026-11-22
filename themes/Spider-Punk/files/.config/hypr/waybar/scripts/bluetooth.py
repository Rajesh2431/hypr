#!/usr/bin/env python3
"""Bluetooth for Waybar: bar status + a Wi-Fi-style drop-down menu.

  bluetooth.py status [--cffi]   long-running feed (updates instantly via D-Bus signals);
                        --cffi feeds cffi/menu-widget.so (bar + native GTK drop-down menu,
                        scans for nearby devices while that menu is open)
  bluetooth.py do connect|disconnect|pair|remove MAC   actions used by the menu
  bluetooth.py menu     drop-down: power, connected devices (with battery), paired
                        devices, scan for new devices, Bluetooth settings
  bluetooth.py power    toggle Bluetooth on/off

Reads state from BlueZ over D-Bus; pairs/connects through bluetoothctl.
Battery levels come from org.bluez.Battery1 (BLE devices, and earbuds/headsets
reported by PipeWire).
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
import json
import subprocess
import sys
import time

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

BLUE = "#4f9cff"
I_ON, I_OFF, I_CONN, I_SCAN = "\U000f00af", "\U000f00b2", "\U000f00b1", "\U000f00b0"
I_SETTINGS, I_BACK, I_CHECK = "\U000f0493", "\U000f004d", "\U000f012c"
I_LINK, I_UNLINK, I_TRASH = "\U000f0337", "\U000f0338", "\U000f0a7a"
TYPE_ICONS = {
    "audio-headset": "\U000f02cb", "audio-headphones": "\U000f02cb", "audio-card": "\U000f04c3",
    "phone": "\U000f011c", "input-keyboard": "\U000f030c", "input-mouse": "\U000f037d",
    "input-gaming": "\U000f0297", "input-tablet": "\U000f04f7", "computer": "\U000f0322",
    "video-display": "\U000f0379", "watch": "\U000f0b56",
}
BAT_ICONS = ["\U000f008e", "\U000f007a", "\U000f007b", "\U000f007c", "\U000f007d", "\U000f007e",
             "\U000f007f", "\U000f0080", "\U000f0081", "\U000f0082", "\U000f0079"]

ROFI_THEME = GLib.get_home_dir() + "/.config/hypr/rofi/config-rofi-Beats-menu.rasi"
DROPDOWN = ("window { location: north east; anchor: north east; x-offset: -12px; y-offset: 50px;"
            " width: 460px; } listview { lines: %d; scrollbar: false; }"
            " element-text { horizontal-align: 0.0; } message { padding: 8px 12px; }"
            " mainbox { children: [ \"inputbar\", \"message\", \"listview\" ]; }"
            " entry { placeholder: \"%s\"; }")  # entry last: rofi fails on string-then-list order


def bus():
    return Gio.bus_get_sync(Gio.BusType.SYSTEM, None)


def state(conn=None):
    """{'adapter': {...} | None, 'devices': [ {...}, ... ]}"""
    conn = conn or bus()
    res = conn.call_sync("org.bluez", "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                         None, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
    adapter, devices = None, []
    for path, ifaces in res.items():
        if "org.bluez.Adapter1" in ifaces and adapter is None:
            adapter = dict(ifaces["org.bluez.Adapter1"], path=path)
        if "org.bluez.Device1" in ifaces:
            d = dict(ifaces["org.bluez.Device1"], path=path)
            bat = ifaces.get("org.bluez.Battery1")
            d["Battery"] = bat.get("Percentage") if bat else None
            devices.append(d)
    return {"adapter": adapter, "devices": devices}


def name(d):
    return d.get("Alias") or d.get("Name") or d.get("Address", "?")


def dev_icon(d):
    return TYPE_ICONS.get(d.get("Icon", ""), I_ON)


def bat_icon(p):
    return BAT_ICONS[min(10, max(0, round(p / 10)))]


def bat_color(p):
    return "#ff6b6b" if p <= 15 else "#f5c26b" if p <= 30 else "#8bd5a0"


def notify(title, body=""):
    # synchronous hint: the Dynamic Island shows its own Bluetooth pop, so it skips these (they still reach the centre)
    subprocess.Popen(["notify-send", "-a", "Bluetooth", "-i", "bluetooth", "-t", "2500",
                      "-h", "string:x-canonical-private-synchronous:bluetooth", title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def btctl(*args, timeout=25):
    try:
        r = subprocess.run(["bluetoothctl", "--timeout", str(timeout), *args],
                           capture_output=True, text=True, timeout=timeout + 5)
        return r.returncode == 0 and "fail" not in r.stdout.lower() and "error" not in r.stdout.lower(), r.stdout
    except subprocess.TimeoutExpired:
        return False, "timed out"


# --------------------------------------------------------- GTK menu (cffi)
SELF = 'python3 "%s"' % __file__


def menu_spec(st):
    a = st["adapter"]
    E = lambda *f: "\x1c".join(f)
    out = [E("header", "<b>Bluetooth</b>")]
    if not a:
        return "\x1d".join(out + [E("note", "No adapter found")])
    powered = bool(a.get("Powered"))
    out.append(E("check", "Enabled", f"{SELF} power", "1" if powered else "0"))
    if powered:
        devs = st["devices"]
        conn = [d for d in devs if d.get("Connected")]
        paired = sorted([d for d in devs if d.get("Paired") and not d.get("Connected")], key=lambda d: name(d).lower())
        new = sorted([d for d in devs if not d.get("Paired") and not d.get("Connected")
                      and d.get("Name") and d.get("RSSI") is not None], key=lambda d: -(d.get("RSSI") or -999))
        if conn:
            out += ["sep", E("header", "Connected")]
            for d in conn:
                b = d["Battery"]
                lab = f"{dev_icon(d)}  {html.escape(name(d))}"
                if b is not None:
                    lab += f"    <span color='{bat_color(b)}'>{bat_icon(b)} {b}%</span>"
                out += [E("sub", lab), E("item", f"{I_UNLINK}  Disconnect", f"{SELF} do disconnect {d['Address']}"),
                        E("item", f"{I_TRASH}  Forget device", f"{SELF} do remove {d['Address']}")]
                if b is not None:
                    out.append(E("note", f"Battery {b}%"))
                out.append("end")
        if paired:
            out += ["sep", E("header", "Paired devices")]
            out += [E("item", f"{dev_icon(d)}  {html.escape(name(d))}", f"{SELF} do connect {d['Address']}")
                    for d in paired]
        out += ["sep", E("header", "Available devices" + ("  <span alpha='60%'>· searching…</span>"
                                                            if a.get("Discovering") else ""))]
        if new:
            out += [E("item", f"{dev_icon(d)}  {html.escape(name(d))}", f"{SELF} do pair {d['Address']}")
                    for d in new[:12]]
        else:
            out.append(E("note", "Searching…" if a.get("Discovering") else "No new devices found"))
    out += ["sep", E("item", f"{I_SETTINGS}  Bluetooth Settings…", "blueman-manager")]
    return "\x1d".join(out)


def act_do(action, mac):
    st = state()
    d = next((x for x in st["devices"] if x.get("Address") == mac), {"Address": mac})
    n = name(d)
    if action == "connect":
        notify("Connecting…", n)
        ok, _ = btctl("connect", mac, timeout=20)
        notify(("Connected to " if ok else "Could not connect to ") + n)
    elif action == "disconnect":
        ok, _ = btctl("disconnect", mac, timeout=10)
        notify(("Disconnected " if ok else "Could not disconnect ") + n)
    elif action == "remove":
        ok, _ = btctl("remove", mac, timeout=10)
        notify(("Forgot " if ok else "Could not forget ") + n)
    elif action == "pair":
        notify("Pairing…", n + "\nKeep the device in pairing mode")
        btctl("--agent", "NoInputNoOutput", "pair", mac, timeout=25)
        btctl("trust", mac, timeout=5)
        ok, _ = btctl("connect", mac, timeout=20)
        notify(("Connected to " if ok else "Could not pair with ") + n)


# ------------------------------------------------------------------ status
def _render(st):
    a = st["adapter"]
    if not a:
        return {"text": I_OFF, "class": "missing", "tooltip": "No Bluetooth adapter found"}
    if not a.get("Powered"):
        return {"text": I_OFF, "class": "off", "tooltip": "Bluetooth is off\n\nClick: open menu · Right-click: turn on"}
    conn = [d for d in st["devices"] if d.get("Connected")]
    tip = [f"<b>Bluetooth</b>  ·  {html.escape(a.get('Alias', ''))}" + ("  ·  scanning…" if a.get("Discovering") else "")]
    if not conn:
        tip += ["", "<span alpha='60%'>No devices connected</span>"]
        text, cls = I_ON, "on"
    else:
        tip.append("")
        for d in conn:
            b = d["Battery"]
            line = f"{dev_icon(d)}  {html.escape(name(d))}"
            if b is not None:
                line += f"   <span color='{bat_color(b)}'>{bat_icon(b)} {b}%</span>"
            tip.append(line)
        first = conn[0]
        label = name(first)
        label = label if len(label) <= 14 else label[:13] + "…"
        text = f"{I_CONN} {html.escape(label)}"
        if first["Battery"] is not None:
            text += f" <span color='{bat_color(first['Battery'])}'>{first['Battery']}%</span>"
        if len(conn) > 1:
            text += f" <span alpha='60%'>+{len(conn) - 1}</span>"
        cls = "connected"
    tip += ["", "<span alpha='50%' size='small'>Click: devices menu · Right-click: on/off\n"
                "Middle-click: Bluetooth settings</span>"]
    return {"text": text, "class": cls, "tooltip": "\n".join(tip)}


PUNK = os.environ.get("PUNK_ICONS") == "1"   # Spider-Punk style: icon comes from CSS (state class), no glyph


def render(st):
    d = _render(st)
    if PUNK:   # rune icon from CSS (on / off / missing / connected); keep the device name + battery
        t = d["text"]
        for g in (I_ON, I_OFF, I_CONN, I_SCAN):
            if t.startswith(g):
                t = t[len(g):].lstrip()
        d["text"] = t
    return d


def status_loop(cffi=False):
    conn = bus()
    last = [None]

    def emit(*_):
        try:
            if cffi:
                st = state(conn)
                r = render(st)
                out = "\x1f".join([r["class"], r["text"], r["tooltip"], menu_spec(st)]).replace("\n", "\x1e")
            else:
                out = json.dumps(render(state(conn)), ensure_ascii=False)
        except Exception as e:
            out = json.dumps({"text": I_OFF, "class": "missing", "tooltip": f"Bluetooth unavailable: {e}"}, ensure_ascii=False)
        if out != last[0]:
            try:
                print(out, flush=True)
            except BrokenPipeError:
                sys.exit(0)
            last[0] = out
        return True

    pending = [0]

    def fire():
        pending[0] = 0
        emit()
        return False

    def soon(*_):  # coalesce bursts of signals into one update
        if not pending[0]:
            pending[0] = GLib.timeout_add(150, fire)

    for member in ("PropertiesChanged",):
        conn.signal_subscribe("org.bluez", "org.freedesktop.DBus.Properties", member, None, None,
                              Gio.DBusSignalFlags.NONE, soon)
    for member in ("InterfacesAdded", "InterfacesRemoved"):
        conn.signal_subscribe("org.bluez", "org.freedesktop.DBus.ObjectManager", member, None, None,
                              Gio.DBusSignalFlags.NONE, soon)
    # bluetoothd restarts
    conn.signal_subscribe("org.freedesktop.DBus", "org.freedesktop.DBus", "NameOwnerChanged", None,
                          "org.bluez", Gio.DBusSignalFlags.NONE, soon)
    if cffi:  # the widget says "open"/"close": scan for nearby devices while its menu is shown
        scan = {"stop": 0}

        def discovery(start):
            a = state(conn)["adapter"]
            if not a or not a.get("Powered"):
                return
            try:
                conn.call_sync("org.bluez", a["path"], "org.bluez.Adapter1",
                               "StartDiscovery" if start else "StopDiscovery", None, None,
                               Gio.DBusCallFlags.NONE, 3000, None)
            except Exception:
                pass

        def stop_scan():
            scan["stop"] = 0
            discovery(False)
            return False

        def on_stdin(source, cond):
            if cond & (GLib.IO_HUP | GLib.IO_ERR):
                sys.exit(0)  # widget went away
            line = sys.stdin.readline()
            if not line:
                sys.exit(0)
            cmd = line.strip()
            if cmd == "open":
                discovery(True)
                if scan["stop"]:
                    GLib.source_remove(scan["stop"])
                scan["stop"] = GLib.timeout_add_seconds(90, stop_scan)  # safety cap
            elif cmd == "close":
                if scan["stop"]:
                    GLib.source_remove(scan["stop"])
                stop_scan()
            return True

        GLib.io_add_watch(sys.stdin.fileno(), GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, on_stdin)
    emit()
    GLib.timeout_add_seconds(30, emit)   # safety net (battery updates without signals)
    GLib.MainLoop().run()


# -------------------------------------------------------------------- menu
def rofi(rows, prompt, mesg=None):
    cmd = ["rofi", "-dmenu", "-i", "-markup-rows", "-format", "i", "-p", prompt,
           "-theme-str", DROPDOWN % (min(len(rows), 14), prompt)]
    try:
        open(ROFI_THEME).close()
        cmd += ["-config", ROFI_THEME]
    except OSError:
        pass
    if mesg:
        cmd += ["-mesg", mesg]
    r = subprocess.run(cmd, input="\n".join(rows), capture_output=True, text=True)
    out = r.stdout.strip()
    return int(out) if r.returncode == 0 and out.isdigit() else None


def dim(s):
    return f"<span alpha='55%'>{s}</span>"


def device_row(d):
    row = f"{dev_icon(d)}   {html.escape(name(d))}"
    b = d["Battery"]
    if d.get("Connected"):
        if b is not None:
            row += f"    <span color='{bat_color(b)}'>{bat_icon(b)} {b}%</span>"
        row += f"    <span color='{BLUE}'>{I_CHECK} Connected</span>"
    elif d.get("Paired"):
        row += "    " + dim("Paired")
    else:
        row += "    " + dim(f"New · {d.get('Address', '')}")
    return row


def set_power(on):
    if on:
        subprocess.run(["rfkill", "unblock", "bluetooth"], capture_output=True)
    ok, _ = btctl("power", "on" if on else "off", timeout=5)
    notify("Bluetooth " + ("on" if on else "off") if ok else "Could not change Bluetooth power")


def act_power():
    a = state()["adapter"]
    set_power(not (a and a.get("Powered")))


def device_menu(d):
    mac, n = d["Address"], name(d)
    rows, acts = [], []
    if d.get("Connected"):
        rows.append(f"{I_UNLINK}   Disconnect"); acts.append("disconnect")
    else:
        rows.append(f"{I_LINK}   Connect"); acts.append("connect")
    if d.get("Paired"):
        rows.append(f"{I_TRASH}   Forget this device"); acts.append("remove")
    rows.append(f"{I_BACK}   Back"); acts.append("back")
    info = [html.escape(n), mac]
    if d["Battery"] is not None:
        info.append(f"Battery {d['Battery']}%")
    i = rofi(rows, n, "  ·  ".join(info))
    if i is None:
        return
    act = acts[i]
    if act == "back":
        return main_menu()
    if act == "connect":
        notify("Connecting…", n)
        if not d.get("Paired"):
            btctl("--agent", "NoInputNoOutput", "pair", mac, timeout=25)
            btctl("trust", mac, timeout=5)
        ok, _ = btctl("connect", mac, timeout=20)
        notify(("Connected to " if ok else "Could not connect to ") + n)
    elif act == "disconnect":
        ok, _ = btctl("disconnect", mac, timeout=10)
        notify(("Disconnected " if ok else "Could not disconnect ") + n)
    elif act == "remove":
        ok, _ = btctl("remove", mac, timeout=10)
        notify(("Forgot " if ok else "Could not forget ") + n)


def scan_menu():
    conn = bus()
    st = state(conn)
    a = st["adapter"]
    notify("Scanning for devices…", "Put your device in pairing mode")
    try:
        conn.call_sync("org.bluez", a["path"], "org.bluez.Adapter1", "StartDiscovery", None, None,
                       Gio.DBusCallFlags.NONE, 3000, None)
    except Exception:
        pass
    time.sleep(7)  # discovery stays active while this process holds the bus connection
    st = state(conn)
    new = [d for d in st["devices"] if not d.get("Paired") and (d.get("Name") or d.get("Alias"))
           and d.get("Alias", "").replace("-", ":") != d.get("Address")]
    new.sort(key=lambda d: -(d.get("RSSI") or -999))
    rows = [device_row(d) for d in new] + [f"{I_SCAN}   Scan again", f"{I_BACK}   Back"]
    i = rofi(rows, "New devices", f"{len(new)} device(s) found — pick one to pair and connect")
    try:
        conn.call_sync("org.bluez", a["path"], "org.bluez.Adapter1", "StopDiscovery", None, None,
                       Gio.DBusCallFlags.NONE, 3000, None)
    except Exception:
        pass
    if i is None:
        return
    if i == len(new):
        return scan_menu()
    if i == len(new) + 1:
        return main_menu()
    device_menu(new[i])


def main_menu():
    st = state()
    a = st["adapter"]
    if not a:
        return notify("No Bluetooth adapter found")
    powered = bool(a.get("Powered"))
    rows, acts = [], []
    if powered:
        devs = sorted([d for d in st["devices"] if d.get("Paired") or d.get("Connected")],
                      key=lambda d: (not d.get("Connected"), name(d).lower()))
        for d in devs:
            rows.append(device_row(d)); acts.append(("device", d))
        rows.append(f"{I_SCAN}   Scan for new devices…"); acts.append(("scan", None))
        rows.append(f"{I_OFF}   Turn Bluetooth off"); acts.append(("power", None))
    else:
        rows.append(f"{I_ON}   Turn Bluetooth on"); acts.append(("power", None))
    rows.append(f"{I_SETTINGS}   Bluetooth settings"); acts.append(("settings", None))

    conn = [d for d in st["devices"] if d.get("Connected")]
    mesg = (f"Bluetooth {'on' if powered else 'off'}  ·  {html.escape(a.get('Alias', ''))}"
            + (f"  ·  {len(conn)} connected" if conn else ""))
    i = rofi(rows, "Bluetooth", mesg)
    if i is None:
        return
    kind, d = acts[i]
    if kind == "power":
        set_power(not powered)
    elif kind == "device":
        device_menu(d)
    elif kind == "scan":
        scan_menu()
    elif kind == "settings":
        subprocess.Popen(["blueman-manager"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        status_loop(cffi="--cffi" in sys.argv)
    elif cmd == "do" and len(sys.argv) == 4:
        act_do(sys.argv[2], sys.argv[3])
    elif cmd == "menu":
        if subprocess.run(["pgrep", "-x", "rofi"], capture_output=True).returncode == 0:
            subprocess.run(["pkill", "-x", "rofi"])
        else:
            main_menu()
    elif cmd == "power":
        act_power()
    else:
        sys.exit(__doc__)
