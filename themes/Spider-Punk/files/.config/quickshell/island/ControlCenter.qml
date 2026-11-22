// Control Center + Notification Center (replaces swaync's control center).
// Opens under the bar on the right: quick toggles (customisable: Edit -> add /
// remove / reorder, saved to center.json), Focus modes, volume + brightness,
// now playing, and the notification list (actions, dismiss, clear all).
//
// Toggle:  qs ipc -c island call center toggle      (bell button, Super+Shift+N)
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Widgets
import Quickshell.Services.Pipewire
import Quickshell.Services.Notifications
import Quickshell.Bluetooth

Scope {
    id: cc
    required property var shell          // island root (Spotify state, helpers)
    required property var server         // NotificationServer
    property var times: ({})             // notification id -> arrival time (ms)

    property bool open: false
    property bool editing: false
    property string page: "main"         // "main" | "focus"
    function toggle() { if (open) close(); else { open = true; poll.running = true } }
    function close() { open = false; editing = false; page = "main" }

    readonly property string home: Quickshell.env("HOME")
    readonly property string scripts: home + "/.config/hypr/scripts"
    function sh(cmd) { Quickshell.execDetached(["sh", "-c", cmd]) }
    function g(cp) { return String.fromCodePoint(cp) }

    // ------------------------------------------------------------ config (center.json)
    readonly property var catalog: ({
        wifi:        { icon: 0xf0928, label: "Wi-Fi" },
        bluetooth:   { icon: 0xf00af, label: "Bluetooth" },
        focus:       { icon: 0xf0594, label: "Focus" },
        nightlight:  { icon: 0xf0594, label: "Night Light" },
        stayawake:   { icon: 0xf0176, label: "Stay Awake" },
        mute:        { icon: 0xf057e, label: "Sound" },
        mic:         { icon: 0xf036c, label: "Microphone" },
        profile:     { icon: 0xf04c5, label: "Power Mode" },
        warp:        { icon: 0xf015f, label: "WARP" },
        tailscale:   { icon: 0xf0582, label: "Tailscale" },
        airplane:    { icon: 0xf001d, label: "Airplane" },
        screenshot:  { icon: 0xf0100, label: "Screenshot" },
        record:      { icon: 0xf044a, label: "Record Screen" },
        colorpicker: { icon: 0xf0485, label: "Color Picker" },
        lock:        { icon: 0xf033e, label: "Lock" },
        power:       { icon: 0xf0425, label: "Power" },
        wallpaper:   { icon: 0xf02e9, label: "Wallpaper" },
        settings:    { icon: 0xf0493, label: "Settings" }
    })
    property var tiles: ["wifi", "bluetooth", "focus", "nightlight", "stayawake", "mute", "mic", "profile", "warp", "screenshot"]
    property var focusModes: [
        { id: "dnd",    name: "Do Not Disturb", icon: 0xf0594, silence: true, allow: [] },
        { id: "work",   name: "Work",   icon: 0xf00d6, silence: true, allow: ["Slack", "Thunderbird", "Mail", "Teams", "Calendar"], profile: "balanced" },
        { id: "sleep",  name: "Sleep",  icon: 0xf02e3, silence: true, allow: [], profile: "power-saver", nightlight: true },
        { id: "gaming", name: "Gaming", icon: 0xf0297, silence: true, allow: ["Steam", "Discord"], profile: "performance", stayAwake: true }
    ]
    FileView {
        id: cfgFile
        path: cc.home + "/.config/quickshell/island/center.json"
        onLoaded: { try { const d = JSON.parse(text()); if (d.tiles) cc.tiles = d.tiles; if (d.focus) cc.focusModes = d.focus } catch (e) {} }
        onLoadFailed: cc.saveCfg()
    }
    function saveCfg() { cfgFile.setText(JSON.stringify({ tiles: tiles, focus: focusModes }, null, 2) + "\n") }
    function moveTile(id, dir) {
        const t = tiles.slice(), i = t.indexOf(id), j = i + dir
        if (i < 0 || j < 0 || j >= t.length) return
        t.splice(i, 1); t.splice(j, 0, id); tiles = t; saveCfg()
    }
    function removeTile(id) { tiles = tiles.filter(x => x !== id); saveCfg() }
    function addTile(id) { if (tiles.indexOf(id) < 0) { tiles = tiles.concat([id]); saveCfg() } }

    // ------------------------------------------------------------ runtime state
    property var st: ({})                 // polled: wifi, ssid, night, profile, airplane, warp, ts
    Process {
        id: poll
        command: ["sh", "-c",
            "echo wifi=$(nmcli -t -f WIFI radio);" +
            "echo ssid=$(nmcli -t -f ACTIVE,SSID dev wifi 2>/dev/null | grep '^yes' | head -1 | cut -d: -f2-);" +
            "echo night=$(" + cc.scripts + "/Hyprsunset.sh status 2>/dev/null | grep -o '\"class\":\"[a-z]*\"' | cut -d'\"' -f4);" +
            "echo profile=$(powerprofilesctl get 2>/dev/null);" +
            "echo airplane=$(rfkill -n -o SOFT list 2>/dev/null | sort -u | tr '\\n' ' ');" +
            "echo warp=$(timeout 3 warp-cli --accept-tos status 2>/dev/null | head -1 | cut -d: -f2);" +
            "echo ts=$(tailscale status --json 2>/dev/null | grep -m1 BackendState | cut -d'\"' -f4)"]
        stdout: StdioCollector {
            onStreamFinished: {
                const o = {}
                text.split("\n").forEach(l => { const i = l.indexOf("="); if (i > 0) o[l.slice(0, i)] = l.slice(i + 1).trim() })
                cc.st = o
            }
        }
    }
    Timer { interval: 3000; repeat: true; running: cc.open; onTriggered: poll.running = true }
    Timer { id: repoll; interval: 900; onTriggered: poll.running = true }
    function after(cmd) { sh(cmd); repoll.restart() }

    // stay awake: hold an idle inhibitor (hypridle honours it)
    property bool stayAwake: false
    Process { running: cc.stayAwake; command: ["systemd-inhibit", "--what=idle", "--who=Control Center", "--why=Stay awake", "sleep", "infinity"] }
    // screen recording
    Process { id: rec; command: ["sh", "-c", "mkdir -p \"$HOME/Videos\"; exec wf-recorder -f \"$HOME/Videos/Recording-$(date +%Y%m%d-%H%M%S).mp4\""] }

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var source: Pipewire.defaultAudioSource
    PwObjectTracker { objects: [cc.sink, cc.source] }

    // ------------------------------------------------------------ focus modes
    property string focus: ""            // active focus mode id ("" = off)
    property var before: null            // stay-awake to restore when focus turns off
    readonly property var focusMode: { for (const m of focusModes) if (m.id === focus) return m; return null }
    // Power mode + night light are captured from the LIVE system (not `st`, which is only polled
    // while the panel is open, so keybind / radar toggles used to restore stale values) into
    // ~/.cache/island/focus-before when focus first turns on. Each mode applies its own settings and
    // falls back to that baseline for the ones it doesn't set; turning focus off restores it.
    function setFocus(id) {
        const next = (id === focus) ? "" : id
        if (focus === "" && next !== "") before = { stay: stayAwake }
        const m = focusModes.find(x => x.id === next)
        const f = "\"$HOME/.cache/island/focus-before\"", hs = "\"" + scripts + "/Hyprsunset.sh\""
        const base = "[ -s " + f + " ] || echo \"$(powerprofilesctl get 2>/dev/null) $(" + hs + " status 2>/dev/null | grep -o '\"class\":\"[a-z]*\"' | cut -d'\"' -f4)\" > " + f + "; " +
                     "read p n < " + f + "; "
        if (m) {
            const prof = m.profile ? m.profile : "$p"
            const night = m.nightlight === true ? "on" : m.nightlight === false ? "off" : "$n"
            after(base + "[ -n \"" + prof + "\" ] && powerprofilesctl set \"" + prof + "\"; " +
                  "case \"" + night + "\" in on|off) " + hs + " \"" + night + "\" >/dev/null ;; esac")
            stayAwake = m.stayAwake !== undefined ? m.stayAwake : (before ? before.stay : stayAwake)
        } else {
            after("[ -s " + f + " ] || exit 0; read p n < " + f + "; [ -n \"$p\" ] && powerprofilesctl set \"$p\"; " +
                  "case \"$n\" in on|off) " + hs + " \"$n\" >/dev/null ;; esac; rm -f " + f)
            if (before) stayAwake = before.stay
            before = null
        }
        focus = next
        shell.focusPop(m ? m.name : "", m ? m.icon : 0)
        writeState()
    }
    // should this notification pop / make noise right now?
    function allowed(n) {
        if (!focusMode || !focusMode.silence) return true
        if (n.urgency === NotificationUrgency.Critical) return true
        return (focusMode.allow || []).some(a => (n.appName || "").toLowerCase().indexOf(a.toLowerCase()) >= 0)
    }

    // ------------------------------------------------------------ state file for the waybar bell
    readonly property int count: server.trackedNotifications.values.length
    onCountChanged: writeState()
    // restore the active focus mode after a reload / restart. Nothing is written until the old
    // file has been read, otherwise the first writeState() wiped it and DND silently turned off.
    property bool stateReady: false
    FileView { id: stateFile; path: cc.home + "/.cache/island/center-state.json"; blockLoading: true
               onLoaded: { if (cc.stateReady) return
                           try { const d = JSON.parse(text())
                                 if (d.focus && cc.focusModes.some(m => m.id === d.focus)) {
                                     cc.focus = d.focus; cc.before = { stay: false }
                                     if (cc.focusMode.stayAwake) cc.stayAwake = true } } catch (e) {}
                           cc.stateReady = true; cc.writeState() }
               onLoadFailed: { cc.stateReady = true; cc.writeState() } }
    function writeState() {
        if (!stateReady) return
        stateFile.setText(JSON.stringify({ count: count, focus: focus, focusName: focusMode ? focusMode.name : "",
                                           focusIcon: focusMode ? focusMode.icon : 0, open: open }) + "\n")
    }
    onOpenChanged: writeState()
    Component.onCompleted: { Quickshell.execDetached(["mkdir", "-p", home + "/.cache/island"]); syncGroups() }

    IpcHandler {
        target: "center"
        function toggle(): void { cc.toggle() }
        function present(): void { if (!cc.open) cc.toggle() }
        function hide(): void { cc.close() }
        function dnd(): void { cc.setFocus("dnd") }
        function focusmode(id: string): void { cc.setFocus(id) }
        function clear(): void { cc.clearAll() }
        function editmode(): void { if (!cc.open) cc.toggle(); cc.page = "main"; cc.editing = !cc.editing }
        function focuspage(): void { if (!cc.open) cc.toggle(); cc.page = "focus" }
    }
    // ---- notifications grouped per app (newest app first, newest card first)
    property var groups: ({})
    ListModel { id: groupModel }
    function syncGroups() {
        const g = {}, latest = {}
        for (const n of server.trackedNotifications.values) {
            const a = n.appName || "Notification"
            ;(g[a] = g[a] || []).push(n)
            latest[a] = Math.max(latest[a] || 0, times[n.id] || 0)
        }
        for (const a in g) g[a].sort((x, y) => (times[y.id] || 0) - (times[x.id] || 0))
        const order = Object.keys(g).sort((x, y) => latest[y] - latest[x])
        groups = g
        for (let i = groupModel.count - 1; i >= 0; i--) if (!g[groupModel.get(i).app]) groupModel.remove(i)
        order.forEach((a, idx) => {
            let cur = -1
            for (let i = 0; i < groupModel.count; i++) if (groupModel.get(i).app === a) { cur = i; break }
            if (cur < 0) groupModel.insert(Math.min(idx, groupModel.count), { app: a })
            else if (cur !== idx) groupModel.move(cur, idx, 1)
        })
    }
    Connections { target: cc.server.trackedNotifications; function onValuesChanged() { cc.syncGroups() } }
    onTimesChanged: syncGroups()
    // a stable accent colour per app (timeline dot, app name)
    function accent(app) {
        let h = 7
        for (const ch of (app || "")) h = (h * 31 + ch.charCodeAt(0)) >>> 0
        return Punk.inks[h % Punk.inks.length]
    }
    function clearAll() { server.trackedNotifications.values.slice().forEach(n => n.dismiss()) }
    function ago(id) {
        const t = times[id]; if (!t) return ""
        const s = Math.max(0, Math.round((shell.nowClock - t) / 1000))
        return s < 60 ? "now" : s < 3600 ? Math.floor(s / 60) + "m" : s < 86400 ? Math.floor(s / 3600) + "h" : Math.floor(s / 86400) + "d"
    }

    // ------------------------------------------------------------ tile model
    function info(id) {
        const c = catalog[id] || { icon: 0xf0766, label: id }
        const o = { icon: c.icon, label: c.label, sub: "", on: false, act: () => {} }
        switch (id) {
        case "wifi": o.on = st.wifi === "enabled"; o.sub = o.on ? (st.ssid || "Not connected") : "Off"
            o.act = () => after("nmcli radio wifi " + (o.on ? "off" : "on")); break
        case "bluetooth": {
            const a = Bluetooth.defaultAdapter; o.on = !!(a && a.enabled)
            const n = Bluetooth.devices.values.filter(d => d.connected)
            o.sub = !o.on ? "Off" : n.length ? (n.length === 1 ? n[0].name : n.length + " devices") : "On"
            o.act = () => { if (a) a.enabled = !a.enabled }; break }
        case "focus": o.on = focus !== ""; o.sub = focusMode ? focusMode.name : "Off"; if (focusMode) o.icon = focusMode.icon
            o.act = () => { page = "focus" }; break
        case "nightlight": o.on = st.night === "on"; o.sub = o.on ? "On" : "Off"; o.icon = 0xf06e8
            o.act = () => after(scripts + "/Hyprsunset.sh toggle"); break
        case "stayawake": o.on = stayAwake; o.sub = o.on ? "Screen stays on" : "Off"; o.act = () => { stayAwake = !stayAwake }; break
        case "mute": { const m = sink && sink.audio ? sink.audio.muted : false; o.on = !m
            o.icon = m ? 0xf075f : 0xf057e; o.sub = m ? "Muted" : Math.round((sink && sink.audio ? sink.audio.volume : 0) * 100) + "%"
            o.act = () => { if (sink && sink.audio) sink.audio.muted = !sink.audio.muted }; break }
        case "mic": { const m = source && source.audio ? source.audio.muted : true; o.on = !m
            o.icon = m ? 0xf036d : 0xf036c; o.sub = m ? "Muted" : "On"
            o.act = () => { if (source && source.audio) source.audio.muted = !source.audio.muted }; break }
        case "profile": { const p = st.profile || "balanced"; o.on = p !== "balanced"
            o.sub = ({ performance: "Performance", balanced: "Balanced", "power-saver": "Power Saver" })[p] || p
            o.icon = p === "performance" ? 0xf04c5 : p === "power-saver" ? 0xf0d42 : 0xf04c4
            const nx = ({ balanced: "performance", performance: "power-saver", "power-saver": "balanced" })[p] || "balanced"
            o.act = () => after("powerprofilesctl set " + nx); break }
        case "warp": o.on = (st.warp || "").indexOf("Connected") >= 0; o.sub = (st.warp || "…").trim() || "…"
            o.act = () => after("warp-cli --accept-tos " + (o.on ? "disconnect" : "connect")); break
        case "tailscale": o.on = st.ts === "Running"; o.sub = o.on ? "Connected" : "Off"
            o.act = () => after("tailscale " + (o.on ? "down" : "up")); break
        case "airplane": o.on = (st.airplane || "").trim() === "blocked"; o.sub = o.on ? "On" : "Off"
            o.act = () => after(scripts + "/AirplaneMode.sh"); break
        case "screenshot": o.sub = "Select area"; o.act = () => { close(); sh("sleep 0.4; " + scripts + "/ScreenShot.sh --area") }; break
        case "record": o.on = rec.running; o.sub = o.on ? "Recording… tap to stop" : "Full screen"
            o.act = () => { if (rec.running) rec.signal(2); else { close(); rec.running = true } }; break
        case "colorpicker": o.sub = "Copy hex"; o.act = () => { close(); sh("sleep 0.4; hyprpicker -a") }; break
        case "lock": o.sub = "Lock screen"; o.act = () => { close(); sh(scripts + "/LockScreen.sh") }; break
        case "power": o.sub = "Power menu"; o.act = () => { close(); sh(scripts + "/Wlogout.sh") }; break
        case "wallpaper": o.sub = "Change"; o.act = () => { close(); sh("qs ipc -c island call wallpaper toggle") }; break
        case "settings": o.sub = "KooL settings"; o.act = () => { close(); sh(scripts + "/Kool_Quick_Settings.sh") }; break
        }
        return o
    }

    // ------------------------------------------------------------ building blocks
    component CText: Text {
        color: Punk.text; font.family: Punk.mono; font.pixelSize: 13
        elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
    }
    component Pill: Rectangle {
        id: pill
        property string text
        property bool strong: false
        signal hit()
        implicitWidth: pt.implicitWidth + 22; implicitHeight: 26; radius: 1
        color: strong ? Punk.crimson : (pm.containsMouse ? Punk.surface2 : Punk.surface)
        border.width: 2; border.color: pm.containsMouse ? Punk.blue : Punk.ink
        Behavior on border.color { ColorAnimation { duration: 140 } }
        Rectangle { z: -1; x: 3; y: 3; width: parent.width; height: parent.height; color: pill.strong ? Punk.blue : Punk.ink }
        CText { id: pt; anchors.centerIn: parent; text: pill.text; font.family: Punk.poster; font.pixelSize: 15; font.letterSpacing: 1
                color: Punk.text }
        MouseArea { id: pm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: pill.hit() }
    }
    component Slider: Item {
        id: sl
        property real value: 0               // real value from the system
        property int icon
        signal moved(real v)
        // while dragging (and briefly after) show where the pointer is, not the
        // value reported back by PipeWire / sysfs, which arrives late and makes the fill jump
        property real local: 0
        property bool holding: sm.pressed || hold.running
        readonly property real shown: holding ? local : value
        implicitHeight: 44
        Timer { id: hold; interval: 600 }
        function setFrom(x) { local = Math.max(0, Math.min(1, x / width)); moved(local) }
        Rectangle {
            anchors.fill: parent; radius: 1; color: Punk.bg
            border.width: 2; border.color: Punk.ink
            Rectangle {
                x: 2; y: 2; height: parent.height - 4; radius: 0; color: Punk.crimson
                width: Math.max(40, (parent.width - 4) * Math.max(0, Math.min(1, sl.shown)))
                Behavior on width { enabled: !sl.holding; NumberAnimation { duration: 260; easing.type: Easing.OutBack; easing.overshoot: 1.4 } }
                Image { anchors.fill: parent; fillMode: Image.Tile; source: Punk.assets + "dots-blue.svg"; sourceSize: Qt.size(12, 12); opacity: 0.35 }
                Rectangle { anchors.right: parent.right; width: 3; height: parent.height; color: Punk.yellow }   // the "edge" of the ink
            }
            CText { x: 14; anchors.verticalCenter: parent.verticalCenter; text: cc.g(sl.icon); font.pixelSize: 17; color: Punk.ink }
            CText { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                    text: Math.round(sl.shown * 100); font.family: Punk.display; font.pixelSize: 19
                    color: sl.shown > 0.9 ? Punk.ink : Punk.text; style: Text.Outline; styleColor: Punk.ink }
            MouseArea {
                id: sm; anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                preventStealing: true                 // the Flickable must not grab the drag
                onPressed: m => sl.setFrom(m.x)
                onPositionChanged: m => { if (pressed) sl.setFrom(m.x) }
                onReleased: hold.restart()
                onWheel: w => { sl.local = Math.max(0, Math.min(1, sl.shown + (w.angleDelta.y > 0 ? 0.05 : -0.05))); hold.restart(); sl.moved(sl.local) }
            }
        }
    }

    // ------------------------------------------------------------ notification card
    component NotifCard: Item {
        id: nc
        property var n: null
        property int badge: 0                  // >1: front card of a stack (click opens the stack)
        property color accent: "#f2f2f2"
        signal openStack()
        readonly property bool critical: !!n && n.urgency === NotificationUrgency.Critical
        readonly property string iconSrc: {
            if (!n) return ""
            if (n.image) return n.image
            const a = n.appIcon || ""
            return !a ? "" : a.startsWith("/") ? "file://" + a : a.indexOf("://") > 0 ? a : Quickshell.iconPath(a, true)
        }
        readonly property var acts: n ? (n.actions || []).filter(a => a.identifier !== "default") : []
        property real dx: 0
        height: face.height

        // swipe sideways to dismiss (springs back if you let go early)
        DragHandler {
            id: swipe; target: null; yAxis.enabled: false
            onTranslationChanged: nc.dx = translation.x
            onActiveChanged: if (!active) {
                if (Math.abs(nc.dx) > 110 && nc.n) nc.n.dismiss()
                nc.dx = 0
            }
        }

        Rectangle {
            id: face
            x: nc.dx; width: nc.width
            height: row.implicitHeight + 24
            radius: 1
            opacity: 1 - Math.min(0.7, Math.abs(nc.dx) / 240)
            rotation: nc.dx / 60                     // the card tilts as you fling it, like a torn page
            color: hov.hovered ? Punk.surface : Punk.bg2
            border.width: 2
            border.color: Punk.ink
            // printed misprint behind the card (accent shifts crimson -> blue on hover)
            Rectangle { z: -1; x: 4; y: 4; width: parent.width; height: parent.height
                        color: nc.critical ? Punk.yellow : hov.hovered ? Punk.blue : Punk.alpha(nc.accent, 0.85)
                        Behavior on color { ColorAnimation { duration: 220 } } }
            // accent spine + halftone corner
            Rectangle { x: 2; y: 2; width: 4; height: parent.height - 4; color: nc.critical ? Punk.crimson : nc.accent }
            Image { anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 2; width: parent.width * 0.4; height: Math.min(parent.height - 4, 46)
                    fillMode: Image.Tile; source: Punk.assets + (hov.hovered ? "dots-blue.svg" : "dots-crimson.svg"); sourceSize: Qt.size(12, 12); opacity: 0.28 }
            HoverHandler { id: hov; cursorShape: Qt.PointingHandCursor }
            TapHandler {
                onTapped: {
                    if (nc.badge > 1) { nc.openStack(); return }
                    const d = nc.n ? (nc.n.actions || []).find(a => a.identifier === "default") : null
                    if (d) d.invoke()
                }
            }

            Row {
                id: row
                x: 14; y: 12; width: parent.width - 26; spacing: 11
                ClippingRectangle {
                    width: 40; height: 40; radius: 1; color: Punk.surface2
                    border.width: 2; border.color: Punk.ink
                    Image { id: ic; anchors.fill: parent; anchors.margins: nc.iconSrc.startsWith("image://icon") ? 7 : 0
                            fillMode: Image.PreserveAspectCrop; asynchronous: true; source: nc.iconSrc; sourceSize.width: 96
                            visible: ok
                            // a theme without the icon hands back a tiny "missing" checkerboard: treat that as no icon
                            readonly property bool ok: status === Image.Ready && implicitWidth > 8 }
                    Image { anchors.centerIn: parent; visible: !ic.ok; width: 14; height: 24
                            source: Punk.assets + "bolt.svg"; sourceSize: Qt.size(28, 48) }
                }
                Column {
                    width: parent.width - 51; spacing: 3
                    Item {
                        width: parent.width; height: 18
                        CText { id: appn; text: ((nc.n && nc.n.appName) || "App").toUpperCase(); font.family: Punk.poster; font.pixelSize: 16
                                font.letterSpacing: 1.2; color: nc.accent; width: Math.min(implicitWidth, parent.width - 100) }
                        // timestamp: a little yellow paper tag
                        Rectangle {
                            anchors.left: appn.right; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter
                            visible: agoT.text !== ""; width: agoT.implicitWidth + 8; height: 14; color: Punk.yellow; rotation: -2
                            CText { id: agoT; anchors.centerIn: parent; text: nc.n ? cc.ago(nc.n.id) : ""; font.pixelSize: 9; font.bold: true; color: Punk.ink }
                        }
                        // stack size / close
                        Rectangle {
                            visible: nc.badge > 1 && !hov.hovered
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            height: 18; width: bt.implicitWidth + 10; radius: 0; rotation: 3
                            color: nc.accent; border.width: 2; border.color: Punk.ink
                            CText { id: bt; anchors.centerIn: parent; text: "+" + (nc.badge - 1); font.family: Punk.display; font.pixelSize: 13; color: Punk.ink }
                        }
                        Rectangle {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            width: 22; height: 22; radius: 0; rotation: xm.containsMouse ? 8 : 0
                            Behavior on rotation { NumberAnimation { duration: 160; easing.type: Easing.OutBack } }
                            color: xm.containsMouse ? Punk.crimson : Punk.surface2
                            border.width: 2; border.color: Punk.ink
                            visible: hov.hovered
                            CText { anchors.centerIn: parent; text: cc.g(0xf0156); font.pixelSize: 12; color: xm.containsMouse ? Punk.ink : Punk.text }
                            MouseArea { id: xm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: if (nc.n) nc.n.dismiss() }
                        }
                    }
                    CText { width: parent.width; text: (nc.n && nc.n.summary) || ""; font.bold: true; font.pixelSize: 13; textFormat: Text.PlainText }
                    // body: two lines, more on hover (smoothly)
                    Item {
                        width: parent.width; height: bodyT.implicitHeight; clip: true
                        visible: bodyT.text !== ""
                        CText { id: bodyT; width: parent.width; wrapMode: Text.WordWrap; elide: Text.ElideRight
                                maximumLineCount: hov.hovered ? 7 : 2
                                text: ((nc.n && nc.n.body) || "").replace(/<img[^>]*>/g, ""); color: Punk.subtext; font.pixelSize: 11; textFormat: Text.StyledText }
                    }
                    Flow {
                        width: parent.width; spacing: 6; visible: nc.acts.length > 0; topPadding: 4
                        Repeater {
                            model: nc.acts
                            Rectangle {
                                required property var modelData
                                height: 24; width: at.implicitWidth + 20; radius: 0
                                color: am.containsMouse ? nc.accent : Punk.surface2
                                border.width: 2; border.color: Punk.ink
                                CText { id: at; anchors.centerIn: parent; text: modelData.text.toUpperCase(); font.family: Punk.poster; font.pixelSize: 14; font.letterSpacing: 1
                                        color: am.containsMouse ? Punk.ink : Punk.text }
                                MouseArea { id: am; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: modelData.invoke() }
                            }
                        }
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------ the panel
    PanelWindow {
        id: panel
        visible: cc.open || box.opacity > 0.01
        screen: cc.shell.islandScreen
        anchors.top: true
        anchors.right: true
        margins.top: 52
        margins.right: 10
        implicitWidth: 420
        // the window keeps one size; the visible card inside animates its height.
        // (resizing a layer surface on every content change made the panel jump)
        implicitHeight: (screen ? screen.height : 1080) - 66
        mask: Region { item: box }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "control-center"
        WlrLayershell.keyboardFocus: cc.open ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None

        HyprlandFocusGrab { windows: [panel]; active: cc.open; onCleared: cc.close() }

        Rectangle {
            id: box
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: Math.min(body.implicitHeight + (nsec.visible ? 18 + nsec.height : 0) + 28, panel.height)
            Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
            color: "transparent"; radius: 0
            clip: true
            PunkPanel { anchors.fill: parent; z: -1; fill: Punk.alpha(Punk.bg, 0.97); misprint: Punk.crimson; offset: Qt.point(6, 6)
                        seed: 9; jag: 2.4; step: 22; strokeWidth: 3; dotsColor: Punk.crimson; dotsOpacity: 0.4 }
            opacity: cc.open ? 1 : 0
            // slams down from under the bar with a little overshoot
            transform: Translate { y: cc.open ? 0 : -24; Behavior on y { NumberAnimation { duration: 320; easing.type: Easing.OutBack; easing.overshoot: 1.6 } } }
            Behavior on opacity { NumberAnimation { duration: 180 } }
            focus: cc.open
            Keys.onEscapePressed: cc.page !== "main" ? cc.page = "main" : (cc.editing ? cc.editing = false : cc.close())

            Item {
                id: content
                anchors.fill: parent; anchors.margins: 16; anchors.rightMargin: 22; anchors.bottomMargin: 22

                // controls: fixed at the top (never scroll away)
                Column {
                    id: body
                    width: parent.width
                    spacing: 12
                    // ---- header: date + focus chip + edit
                    Item {
                        width: parent.width; height: 56
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            CText { text: Qt.formatDateTime(new Date(cc.shell.nowClock), "dddd d MMMM").toUpperCase(); color: Punk.yellow
                                    font.family: Punk.poster; font.pixelSize: 15; font.letterSpacing: 1.5 }
                            CText { text: Qt.formatDateTime(new Date(cc.shell.nowClock), "hh:mm AP"); font.family: Punk.display; font.pixelSize: 30
                                    style: Text.Raised; styleColor: Punk.crimson }
                        }
                        Row {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                            Pill { visible: cc.page === "main"; text: cc.editing ? "Done" : "Edit"; strong: cc.editing; onHit: cc.editing = !cc.editing }
                            Pill { visible: cc.page !== "main"; text: "Back"; onHit: cc.page = "main" }
                        }
                    }

                    // ================= FOCUS PAGE =================
                    Column {
                        visible: cc.page === "focus"; width: parent.width; spacing: 8
                        CText { text: "FOCUS"; font.family: Punk.display; font.pixelSize: 24; style: Text.Raised; styleColor: Punk.blue }
                        CText { width: parent.width; wrapMode: Text.WordWrap; color: Punk.subtext; font.pixelSize: 11
                                text: "Silences notifications (allowed apps and critical alerts still come through) and can switch power mode, night light and stay-awake." }
                        Repeater {
                            model: cc.focusModes
                            Rectangle {
                                required property var modelData
                                readonly property bool act: cc.focus === modelData.id
                                width: parent.width - 4; height: 58; radius: 0
                                color: act ? Punk.purple : (fm.containsMouse ? Punk.surface2 : Punk.surface)
                                border.width: 2; border.color: Punk.ink
                                Rectangle { z: -1; x: 4; y: 4; width: parent.width; height: parent.height; color: parent.act ? Punk.yellow : Punk.ink }
                                Rectangle { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 36; height: 36; radius: 0
                                            color: parent.act ? Punk.ink : Punk.bg; border.width: 2; border.color: Punk.ink
                                            CText { anchors.centerIn: parent; text: cc.g(modelData.icon); font.pixelSize: 17; color: parent.parent.act ? Punk.yellow : Punk.text } }
                                Column {
                                    x: 60; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 80
                                    CText { width: parent.width; text: modelData.name.toUpperCase(); font.family: Punk.poster; font.pixelSize: 17; font.letterSpacing: 1; color: Punk.text }
                                    CText { width: parent.width; font.pixelSize: 10; color: parent.parent.act ? Punk.text : Punk.subtext
                                            text: [ modelData.allow && modelData.allow.length ? "Allows " + modelData.allow.join(", ") : "Silences everything",
                                                    modelData.profile ? ({ performance: "Performance", balanced: "Balanced", "power-saver": "Power saver" })[modelData.profile] : "",
                                                    modelData.nightlight ? "Night light" : "", modelData.stayAwake ? "Stay awake" : "" ].filter(x => x).join("  ·  ") }
                                }
                                MouseArea { id: fm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: { cc.setFocus(modelData.id); cc.page = "main" } }
                            }
                        }
                        CText { width: parent.width; wrapMode: Text.WordWrap; color: Punk.faint; font.pixelSize: 10
                                text: "Edit modes in ~/.config/quickshell/island/center.json" }
                    }

                    // ================= MAIN PAGE =================
                    // ---- tiles
                    Grid {
                        visible: cc.page === "main"
                        width: parent.width; columns: 2; spacing: 8
                        Repeater {
                            model: cc.tiles
                            Rectangle {
                                id: tile
                                required property string modelData
                                required property int index
                                readonly property var t: { cc.st; cc.focus; cc.stayAwake; rec.running; Bluetooth.devices.values; return cc.info(modelData) }
                                width: (body.width - 12) / 2; height: 58; radius: 0
                                color: t.on ? (tm.pressed ? Qt.darker(Punk.crimson, 1.2) : Punk.crimson) : (tm.pressed ? Punk.surface2 : tm.containsMouse && !cc.editing ? Punk.surface2 : Punk.surface)
                                border.width: 2; border.color: Punk.ink
                                Behavior on color { ColorAnimation { duration: 150 } }
                                // misprint: blue when on, ink when off; the press "stamps" the panel down onto it
                                Rectangle { z: -1; x: tm.pressed ? 1 : 4; y: tm.pressed ? 1 : 4; width: parent.width; height: parent.height
                                            color: tile.t.on ? Punk.blue : Punk.ink
                                            Behavior on x { NumberAnimation { duration: 90 } } Behavior on y { NumberAnimation { duration: 90 } } }
                                Image { visible: tile.t.on; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 2; width: parent.width * 0.45; height: parent.height - 4
                                        fillMode: Image.Tile; source: Punk.assets + "dots-blue.svg"; sourceSize: Qt.size(12, 12); opacity: 0.3 }
                                Rectangle { x: 10; anchors.verticalCenter: parent.verticalCenter; width: 36; height: 36; radius: 0
                                            color: tile.t.on ? Punk.ink : Punk.bg; border.width: 2; border.color: Punk.ink
                                            CText { anchors.centerIn: parent; text: cc.g(tile.t.icon); font.pixelSize: 17; color: tile.t.on ? Punk.crimson : Punk.text } }
                                Column {
                                    x: 56; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 62 - (cc.editing ? 82 : 0)
                                    CText { width: parent.width; text: tile.t.label.toUpperCase(); font.family: Punk.poster; font.pixelSize: 16; font.letterSpacing: 1; color: Punk.text }
                                    CText { width: parent.width; text: tile.t.sub; font.pixelSize: 10; color: tile.t.on ? Punk.text : Punk.subtext }
                                }
                                MouseArea { id: tm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: if (!cc.editing) tile.t.act() }
                                // edit mode: remove + move
                                Row {
                                    visible: cc.editing; anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                                    Repeater {
                                        model: [ { g: 0xf0141, a: "left" }, { g: 0xf0142, a: "right" }, { g: 0xf0156, a: "del" } ]
                                        Rectangle {
                                            required property var modelData
                                            width: 22; height: 22; radius: 0; color: modelData.a === "del" ? Punk.yellow : Punk.bg
                                            border.width: 2; border.color: Punk.ink
                                            CText { anchors.centerIn: parent; text: cc.g(modelData.g); font.pixelSize: 13; color: modelData.a === "del" ? Punk.ink : Punk.text }
                                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                onClicked: modelData.a === "del" ? cc.removeTile(tile.modelData) : cc.moveTile(tile.modelData, modelData.a === "left" ? -1 : 1) }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    // ---- edit mode: tiles you can add
                    Column {
                        visible: cc.page === "main" && cc.editing; width: parent.width; spacing: 6
                        CText { text: "ADD CONTROLS"; color: Punk.subtext; font.family: Punk.poster; font.pixelSize: 14; font.letterSpacing: 1.5 }
                        Flow {
                            width: parent.width; spacing: 6
                            Repeater {
                                model: Object.keys(cc.catalog).filter(k => cc.tiles.indexOf(k) < 0)
                                Rectangle {
                                    required property string modelData
                                    width: at.implicitWidth + 44; height: 30; radius: 0; color: am.containsMouse ? Punk.surface2 : Punk.surface
                                    border.width: 2; border.color: am.containsMouse ? Punk.blue : Punk.ink
                                    CText { x: 10; anchors.verticalCenter: parent.verticalCenter; text: cc.g(0xf0415); color: Punk.yellow; font.pixelSize: 14 }
                                    CText { id: at; x: 30; anchors.verticalCenter: parent.verticalCenter; text: cc.catalog[modelData].label; font.pixelSize: 12 }
                                    MouseArea { id: am; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: cc.addTile(modelData) }
                                }
                            }
                        }
                    }

                    // ---- sliders
                    Slider { visible: cc.page === "main"; width: parent.width
                             value: cc.sink && cc.sink.audio ? (cc.sink.audio.muted ? 0 : cc.sink.audio.volume) : 0
                             icon: cc.sink && cc.sink.audio && cc.sink.audio.muted ? 0xf075f : 0xf057e
                             onMoved: v => { if (cc.sink && cc.sink.audio) { cc.sink.audio.muted = false; cc.sink.audio.volume = v } } }
                    Slider { id: bri; visible: cc.page === "main"; width: parent.width
                             value: cc.shell.blMax > 0 && cc.shell.blRaw >= 0 ? cc.shell.blRaw / cc.shell.blMax : 0
                             icon: 0xf00e0
                             property real want: -1
                             property real sent: -1
                             onMoved: v => { want = v; if (!briT.running) briT.start() }
                             Timer { id: briT; interval: 60; repeat: true
                                     onTriggered: { if (bri.want === bri.sent) { stop(); return }
                                                    bri.sent = bri.want; cc.sh("brightnessctl -q set " + Math.max(1, Math.round(bri.want * 100)) + "%") } } }

                    // ---- now playing
                    Rectangle {
                        visible: cc.page === "main" && !!cc.shell.sp.title
                        width: parent.width - 4; height: 72; radius: 0; color: Punk.surface
                        border.width: 2; border.color: Punk.ink
                        Rectangle { z: -1; x: 4; y: 4; width: parent.width; height: parent.height; color: Punk.blue }
                        ClippingRectangle { id: mc; x: 10; anchors.verticalCenter: parent.verticalCenter; width: 52; height: 52; radius: 0; color: Punk.bg
                                            border.width: 2; border.color: Punk.ink
                                            Image { anchors.fill: parent; fillMode: Image.PreserveAspectCrop; asynchronous: true
                                                    source: cc.shell.sp.cover ? "file://" + cc.shell.sp.cover : "" } }
                        Column {
                            anchors.left: mc.right; anchors.leftMargin: 12; anchors.right: ctl.left; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                            CText { width: parent.width; text: (cc.shell.sp.title || "").toUpperCase(); font.family: Punk.poster; font.pixelSize: 18; font.letterSpacing: 0.5 }
                            CText { width: parent.width; text: cc.shell.sp.artist || ""; color: Punk.blue; font.pixelSize: 11 }
                        }
                        Row {
                            id: ctl; anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 14
                            Repeater {
                                model: [ { g: 0xf04ae, a: "prev" }, { g: cc.shell.sp.playing ? 0xf03e4 : 0xf040a, a: "toggle" }, { g: 0xf04ad, a: "next" } ]
                                CText { required property var modelData; text: cc.g(modelData.g); font.pixelSize: modelData.a === "toggle" ? 22 : 18
                                        MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: cc.shell.spotify([parent.modelData.a]) } }
                            }
                        }
                    }
                }

                // ================= NOTIFICATIONS: timeline stacks =================
                // Only this area scrolls (the controls above stay put).
                Item {
                    id: nsec
                    visible: cc.page === "main"
                    anchors.top: body.bottom; anchors.topMargin: 18
                    width: parent.width
                    readonly property real maxArea: Math.max(130, panel.height - 28 - body.implicitHeight - 18 - nhead.height - 10)
                    readonly property real areaH: cc.count ? Math.min(nlist.contentHeight + 4, maxArea) : 120
                    height: nhead.height + 10 + areaH

                    // ---- header: title + live count + clear
                    Item {
                        id: nhead
                        width: parent.width; height: 30
                        CText { id: ntitle; anchors.verticalCenter: parent.verticalCenter; text: "NOTIFICATIONS"; font.family: Punk.display; font.pixelSize: 22
                                font.letterSpacing: 1; style: Text.Raised; styleColor: Punk.crimson }
                        Rectangle {
                            id: nbadge
                            visible: cc.count > 0
                            anchors.left: ntitle.right; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter
                            height: 22; width: Math.max(24, nbt.implicitWidth + 12); radius: 0; color: Punk.yellow; rotation: -4
                            border.width: 2; border.color: Punk.ink
                            CText { id: nbt; anchors.centerIn: parent; text: cc.count; font.family: Punk.display; font.pixelSize: 15; color: Punk.ink }
                            // "POW": the badge punches in whenever the count changes
                            property int seen: cc.count
                            onSeenChanged: pow.restart()
                            SequentialAnimation { id: pow
                                NumberAnimation { target: nbadge; property: "scale"; to: 1.35; duration: 90; easing.type: Easing.OutQuad }
                                NumberAnimation { target: nbadge; property: "scale"; to: 1; duration: 260; easing.type: Easing.OutBack; easing.overshoot: 2.5 } }
                        }
                        Pill { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                               visible: cc.count > 0; text: "Clear all"; onHit: cc.clearAll() }
                    }

                    // ---- empty state: gently floating bell
                    Item {
                        visible: cc.count === 0
                        anchors.top: nhead.bottom; anchors.topMargin: 10
                        width: parent.width; height: 120
                        CText {
                            id: bell; anchors.horizontalCenter: parent.horizontalCenter; y: 18
                            text: cc.g(0xf009a); font.pixelSize: 30; color: Punk.surface2; style: Text.Outline; styleColor: Punk.ink
                        }
                        Column {
                            anchors.horizontalCenter: parent.horizontalCenter; y: 64; spacing: 3
                            CText { anchors.horizontalCenter: parent.horizontalCenter; text: "ALL QUIET ON THE STREET"; font.family: Punk.poster; font.pixelSize: 17; font.letterSpacing: 1.5; color: Punk.subtext }
                            CText { anchors.horizontalCenter: parent.horizontalCenter; font.pixelSize: 10; color: Punk.faint
                                    text: cc.focusMode ? cc.focusMode.name + " is on" : "New notifications will appear here" }
                        }
                    }

                    // ---- the stacks
                    ListView {
                        id: nlist
                        visible: cc.count > 0
                        anchors.top: nhead.bottom; anchors.topMargin: 10
                        width: parent.width; height: nsec.areaH
                        clip: true
                        spacing: 10
                        model: groupModel
                        boundsBehavior: Flickable.StopAtBounds
                        flickDeceleration: 2500
                        cacheBuffer: 600
                        add: Transition {
                            ParallelAnimation {
                                NumberAnimation { property: "x"; from: 90; to: 0; duration: 420; easing.type: Easing.OutBack; easing.overshoot: 1.7 }
                                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200 }
                            }
                        }
                        remove: Transition {
                            ParallelAnimation {
                                NumberAnimation { property: "x"; to: 460; duration: 260; easing.type: Easing.InBack }
                                NumberAnimation { property: "rotation"; to: 9; duration: 260; easing.type: Easing.InQuad }
                                NumberAnimation { property: "opacity"; to: 0; duration: 240 }
                            }
                        }
                        displaced: Transition { NumberAnimation { properties: "x,y"; duration: 240; easing.type: Easing.OutBack; easing.overshoot: 1.3 } }

                        // smooth, animated wheel scrolling (only this list moves)
                        NumberAnimation { id: wheelAnim; target: nlist; property: "contentY"; duration: 260; easing.type: Easing.OutCubic }
                        WheelHandler {
                            onWheel: e => {
                                const maxY = Math.max(0, nlist.contentHeight - nlist.height)
                                if (e.pixelDelta.y !== 0) { wheelAnim.stop(); nlist.contentY = Math.max(0, Math.min(maxY, nlist.contentY - e.pixelDelta.y)) }
                                else {
                                    const from = wheelAnim.running ? wheelAnim.to : nlist.contentY
                                    wheelAnim.to = Math.max(0, Math.min(maxY, from - e.angleDelta.y * 0.9)); wheelAnim.restart()
                                }
                                scrollHint.restart()
                            }
                        }

                        delegate: Item {
                            id: grp
                            required property string app
                            required property int index
                            // keep the last cards while the stack flies out (the group is gone from cc.groups by then)
                            property var items: []
                            readonly property var live: cc.groups[app] || []
                            onLiveChanged: if (live.length) items = live
                            Component.onCompleted: items = live
                            property bool expanded: false
                            readonly property bool stacked: items.length > 1
                            readonly property color accent: cc.accent(app)
                            readonly property int ghosts: stacked && !expanded ? Math.min(items.length - 1, 2) : 0
                            width: ListView.view ? ListView.view.width : 0
                            height: expanded ? exp.height : front.height + ghosts * 7

                            // timeline rail: coloured dot per app, hairline joining the stacks
                            Rectangle { x: 7; y: 0; width: 2; height: grp.height + nlist.spacing; color: Punk.alpha(Punk.crimson, 0.35)
                                        visible: grp.index < groupModel.count - 1 }
                            Rectangle {
                                x: 2; y: 14; width: 12; height: 12; radius: 0; rotation: 45; color: grp.accent
                                border.width: 2; border.color: Punk.ink
                            }

                            // collapsed deck: ghost cards peeking out under the front card
                            Repeater {
                                model: grp.ghosts
                                Rectangle {
                                    required property int index
                                    z: -1 - index
                                    x: 22 + (index + 1) * 9; width: grp.width - 22 - (index + 1) * 18
                                    y: front.height - 34 + (index + 1) * 7; height: 34; radius: 0
                                    rotation: index ? -1.2 : 1
                                    color: index ? Punk.bg : Punk.surface
                                    border.width: 2; border.color: Punk.ink
                                }
                            }
                            NotifCard {
                                id: front
                                x: 22; width: grp.width - 22
                                visible: !grp.expanded
                                n: grp.items[0] || null
                                badge: grp.stacked ? grp.items.length : 0
                                accent: grp.accent
                                onOpenStack: grp.expanded = true
                            }

                            // expanded: header + every card, fanning in one after another
                            Column {
                                id: exp
                                visible: grp.expanded
                                x: 22; width: grp.width - 22
                                spacing: 6
                                Item {
                                    width: parent.width; height: 28
                                    CText { anchors.verticalCenter: parent.verticalCenter; text: grp.app.toUpperCase(); font.family: Punk.poster; font.pixelSize: 17; color: grp.accent }
                                    Row {
                                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                                        Pill { text: "Show less"; onHit: grp.expanded = false }
                                        Pill { text: cc.g(0xf0156); onHit: grp.items.slice().forEach(x => x.dismiss()) }
                                    }
                                }
                                Repeater {
                                    model: grp.expanded ? grp.items : []
                                    NotifCard {
                                        id: ec
                                        required property var modelData
                                        required property int index
                                        width: exp.width
                                        n: modelData
                                        accent: grp.accent
                                    }
                                }
                            }
                        }
                    }
                    // soft fade where the list continues above / below
                    Rectangle {
                        visible: nlist.visible && nlist.contentY > 2
                        anchors.top: nlist.top; width: nlist.width; height: 22
                        gradient: Gradient { GradientStop { position: 0; color: Punk.bg } GradientStop { position: 1; color: "transparent" } }
                    }
                    Rectangle {
                        visible: nlist.visible && nlist.contentY + nlist.height < nlist.contentHeight - 2
                        anchors.bottom: nlist.bottom; width: nlist.width; height: 26
                        gradient: Gradient { GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Punk.bg } }
                    }
                    // slim scroll indicator, shown while scrolling
                    Rectangle {
                        visible: nlist.visible && nlist.contentHeight > nlist.height
                        anchors.right: nlist.right; anchors.rightMargin: -8
                        width: 3; radius: 0; color: Punk.crimson
                        height: Math.max(24, nlist.height * nlist.height / Math.max(1, nlist.contentHeight))
                        y: nlist.y + (nlist.height - height) * (nlist.contentY / Math.max(1, nlist.contentHeight - nlist.height))
                        opacity: scrollHint.running || nlist.moving ? 1 : 0
                        Timer { id: scrollHint; interval: 900 }
                    }
                }
            }
        }
    }
}
