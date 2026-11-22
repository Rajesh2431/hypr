// Dynamic Island for KoolDots (Quickshell) — sits in the centre of Waybar.
//
//  idle      small black pill (click: open Spotify)
//  compact   cover · lyric line (or title) · ♥ · visualizer   (click play/pause,
//            middle ♥, right Spotify menu)
//  hover     grows into a mini player: big cover, title, seekable progress,
//            controls, ♥, synced lyrics
//  events    grows briefly for: song change, volume, brightness, notifications,
//            charger plugged/unplugged, Bluetooth device connected (+battery),
//            microphone starting to record
//
// Start: qs -c island      Data: ~/.config/hypr/waybar/scripts/spotify.py status --island
import QtQuick
import QtQml
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Widgets
import Quickshell.Services.Pipewire
import Quickshell.Services.UPower
import Quickshell.Bluetooth
import Quickshell.Services.Notifications

ShellRoot {
    id: root

    readonly property string home: Quickshell.env("HOME")
    readonly property string spotifyPy: home + "/.config/hypr/waybar/scripts/spotify.py"
    readonly property string here: home + "/.config/quickshell/island"
    readonly property string font: "JetBrainsMono Nerd Font"
    // Spider-Punk palette (Punk.qml). "green" was the Spotify accent; it is now the crimson ink.
    readonly property color green: Punk.crimson
    readonly property color text: Punk.text
    readonly property color dim: Punk.subtext

    function glyph(cp) { return String.fromCodePoint(cp) }
    function spotify(args) { Quickshell.execDetached(["python3", spotifyPy].concat(args)) }
    function fmt(ms) { const s = Math.max(0, Math.floor(ms / 1000)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0") }

    // ------------------------------------------------------------ building blocks
    // (inline components don't see `root`, so everything they need is passed in)
    component Fade: Item {
        property string when
        property string cur
        anchors.fill: parent
        opacity: cur === when ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }
    component Label: Text {
        color: "#F5F0E8"; font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 13
        elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
    }
    component Cover: ClippingRectangle {
        property alias src: img.source
        color: "#2A1C26"
        border.width: 2; border.color: "#050306"
        Image { id: img; anchors.fill: parent; fillMode: Image.PreserveAspectCrop; asynchronous: true; smooth: true; mipmap: true }
    }
    component Bars: Row {
        id: barsRow
        property var values: []
        property real maxH: 16
        property color tint: Punk.crimson
        spacing: 2
        Repeater {
            model: 12
            Rectangle {
                required property int index
                width: 3; radius: 0
                anchors.verticalCenter: parent.verticalCenter
                color: barsRow.tint
                height: 2 + (barsRow.values[index] || 0) / 7 * (barsRow.maxH - 2)
                Behavior on height { NumberAnimation { duration: 60 } }
            }
        }
    }
    component Meter: Item {
        id: meter
        property real value: 0
        property string icon
        property color tint: Punk.crimson
        // laid out at the pop's FINAL size (340 px) and centred: while the island grows the
        // layout is revealed, instead of the track stretching from a tiny width (fill looked "at minimum")
        property real finalWidth: 340
        width: finalWidth
        height: parent ? parent.height : 40
        anchors.centerIn: parent
        Label { x: 16; anchors.verticalCenter: parent.verticalCenter; text: meter.icon; font.pixelSize: 17; color: meter.tint }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            // ink track: square ends, the fill overshoots a touch and has a yellow leading edge
            x: 46; width: meter.finalWidth - 46 - 62; height: 10; radius: 0; color: Punk.surface2
            border.width: 1; border.color: Punk.ink
            Rectangle { width: parent.width * Math.max(0, Math.min(1, meter.value)); height: parent.height; radius: 0; color: meter.tint
                        Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutBack; easing.overshoot: 1.6 } }
                        Rectangle { anchors.right: parent.right; width: 2; height: parent.height; color: Punk.yellow; visible: parent.width > 3 } }
        }
        Label { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                text: Math.round(meter.value * 100); color: Punk.text; font.family: Punk.display; font.pixelSize: 19 }
    }
    component Btn: Label {
        id: btn
        signal activated()
        font.pixelSize: 20
        scale: bm.pressed ? 0.85 : (bm.containsMouse ? 1.12 : 1)
        Behavior on scale { NumberAnimation { duration: 120 } }
        MouseArea { id: bm; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: btn.activated() }
    }

    // ------------------------------------------------------------ state
    property bool ready: false            // no event pop-ups during the first seconds
    Timer { interval: 2500; running: true; onTriggered: root.ready = true }

    property var sp: ({ state: "idle" })
    property string lastKey: ""
    property real nowMs: Date.now()
    Timer { interval: 100; running: root.sp.playing === true; repeat: true; onTriggered: root.nowMs = Date.now() }

    readonly property real position: {
        const s = sp; if (!s.duration) return 0
        const p = s.progress + (s.playing ? Math.max(0, nowMs - s.at * 1000) : 0)
        return Math.min(p, s.duration)
    }
    readonly property int lyricIdx: {
        const L = sp.lyrics; if (!L || !L.length) return -1
        let i = -1; for (let k = 0; k < L.length; k++) { if (L[k][0] <= position + 150) i = k; else break }
        return i
    }
    function lyric(off) {
        const L = sp.lyrics, i = lyricIdx + off
        return (L && i >= 0 && i < L.length) ? (L[i][1] || "♪") : ""
    }
    readonly property string compactLine: lyricIdx >= 0 && lyric(0) !== "♪" ? "♪  " + lyric(0)
                                          : (sp.title ? sp.title + (sp.artist ? "  ·  " + sp.artist : "") : "")

    // events: one at a time, newest wins
    property string ev: ""
    property var evData: ({})
    Timer { id: evTimer; onTriggered: root.ev = "" }
    function pop(kind, data, ms) {
        if (!ready || hovered) return
        evData = data || {}; ev = kind
        evTimer.interval = ms; evTimer.restart()
    }

    property bool hovered: false
    readonly property string base: sp.state === "playing" ? "compact" : sp.state === "paused" ? "paused"
                                   : (sp.state === "login" ? "login" : "idle")
    readonly property bool hasTrack: base === "compact" || base === "paused"
    readonly property string mode: hovered ? (hasTrack ? "expanded" : "idlehover") : (ev !== "" ? ev : base)

    // ------------------------------------------------------------ feeds
    Process {
        id: spProc
        running: true
        command: ["python3", root.spotifyPy, "status", "--island"]
        stdout: SplitParser {
            onRead: data => {
                let d; try { d = JSON.parse(data) } catch (e) { return }
                root.sp = d; root.nowMs = Date.now()
                if (d.key && d.key !== root.lastKey) {
                    if (root.lastKey !== "" && d.playing) root.pop("song", {}, 3500)
                    root.lastKey = d.key
                }
            }
        }
        onExited: spRestart.start()
    }
    Timer { id: spRestart; interval: 3000; onTriggered: spProc.running = true }

    property var bars: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    Process {
        id: cava
        running: true      // listens to all system audio (cava sleeps by itself on silence)
        onExited: cavaRestart.start()
        command: ["setpriv", "--pdeathsig", "TERM", "cava", "-p", root.here + "/cava.conf"]   // dies with the island
        stdout: SplitParser {
            onRead: data => {
                const v = data.split(";").filter(x => x !== "").map(Number)
                if (!v.length) return
                root.bars = v
                if (v.some(x => x > 0)) { root.soundOn = true; silence.restart() }
            }
        }
    }

    Timer { id: cavaRestart; interval: 3000; onTriggered: cava.running = true }
    // true while any sound plays on the computer (cava bars move); off after 1.5 s of silence
    property bool soundOn: false
    Timer { id: silence; interval: 1500; onTriggered: { root.soundOn = false; root.bars = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] } }

    // ---------- notification server (replaces swaync) + Control Center
    property real nowClock: Date.now()
    Timer { interval: 1000; running: true; repeat: true; onTriggered: root.nowClock = Date.now() }
    NotificationServer {
        id: notifServer
        keepOnReload: true
        bodySupported: true
        bodyMarkupSupported: true
        actionsSupported: true
        imageSupported: true
        persistenceSupported: true
        onNotification: n => {
            const h = n.hints || {}
            const sync = String(h["x-canonical-private-synchronous"] || h["synchronous"] || "")
            // OSD-style (volume / brightness / mute toggles): the island shows its own sliders -> drop
            if (h["value"] !== undefined || /volume|bright/i.test(sync) || h["SWAYNC_BYPASS_DND"] !== undefined) return
            // "transient" toasts from KoolDots scripts (notify-send -e) are dropped, but real apps
            // that mark everything transient (Firefox, Chromium: they send a desktop-entry) still show
            if (h["transient"] && !h["desktop-entry"] && !/firefox|chrom|brave|vivaldi|thunderbird/i.test(n.appName)) return
            n.tracked = true
            const t = Object.assign({}, center.times); t[n.id] = Date.now(); center.times = t
            // synchronous-hint notifications (battery, Bluetooth…) already have their own island pop
            if (sync === "" && center.allowed(n))
                root.pop("notif", { app: n.appName, icon: n.image || n.appIcon, summary: n.summary, body: n.body,
                                    urgency: n.urgency === NotificationUrgency.Critical ? 2 : 1 },
                         n.urgency === NotificationUrgency.Critical ? 8000 : 5000)
        }
    }
    ControlCenter { id: center; shell: root; server: notifServer }
    Launcher { id: launcher; shell: root }      // Spotlight (Super+D)
    Wallpapers { id: wallpicker; shell: root }  // wallpaper picker (Super+W)
    function focusPop(name, icon) { pop("focus", { name: name, icon: icon }, 2400) }

    // ---------- timer / Pomodoro: countdown in the idle island; waybar clock right-click = Pomodoro,
    // middle-click = pick minutes.  qs ipc -c island call timer pomodoro | start <min> | stop | toggle
    property real timerEnd: 0            // ms epoch, 0 = off
    property int timerTotal: 0           // s
    property string timerLabel: ""       // FOCUS / BREAK / TIMER
    property bool pomodoro: false
    readonly property int timerLeft: timerEnd > 0 ? Math.max(0, Math.ceil((timerEnd - nowClock) / 1000)) : 0
    readonly property bool timerOn: timerEnd > 0
    function mmss(s) { return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0") }
    function timerStart(minutes, label, pomo) {
        timerTotal = Math.max(1, Math.round(minutes * 60)); timerLabel = label; pomodoro = pomo
        timerEnd = Date.now() + timerTotal * 1000
        pop("timer", { kind: "start" }, 2200)
    }
    function timerStop() { timerEnd = 0; pomodoro = false; pop("timer", { kind: "stop" }, 1800) }
    onTimerLeftChanged: {
        if (!timerOn || timerLeft > 0) return
        const was = timerLabel, pomo = pomodoro
        timerEnd = 0
        Quickshell.execDetached(["sh", "-c", "notify-send -a Timer -u critical " + (was === "FOCUS" ? "'Focus done' 'Take a 5 minute break'"
                                 : was === "BREAK" ? "'Break over' 'Back to it: next focus block'" : "'Time is up' ''") +
                                 "; pw-play /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null"])
        if (pomo && was === "FOCUS") timerStart(5, "BREAK", true)
        else if (pomo && was === "BREAK") timerStart(25, "FOCUS", true)
        else pop("timer", { kind: "done" }, 6000)
    }
    IpcHandler {
        target: "timer"
        function pomodoro(): void { root.timerStart(25, "FOCUS", true) }
        function start(minutes: int): void { if (minutes > 0) root.timerStart(minutes, "TIMER", false) }
        function stop(): void { root.timerStop() }
        function toggle(): void { if (root.timerOn) root.timerStop(); else root.timerStart(25, "FOCUS", true) }
        function status(): string { return root.timerOn ? root.timerLabel + " " + root.mmss(root.timerLeft) : "off" }
    }

    // network changes (netwatch.py: nmcli monitor + tailscale)
    Process {
        id: netProc
        running: true
        command: ["python3", root.here + "/netwatch.py"]
        stdinEnabled: true   // keep stdin open: netwatch exits when it closes
        stdout: SplitParser {
            onRead: data => { try { const n = JSON.parse(data); root.pop("net", n, (n.kind === "portal" || n.kind === "limited") ? 6000 : 3500) } catch (e) {} }
        }
        onExited: netRestart.start()
    }
    Timer { id: netRestart; interval: 3000; onTriggered: netProc.running = true }

    // game controllers on any connection (padwatch.py: udev input + controller battery)
    Process {
        id: padProc
        running: true
        command: ["python3", root.here + "/padwatch.py"]
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                let d; try { d = JSON.parse(data) } catch (e) { return }
                root.pop("pad", d, d.kind === "pad_crit" ? 7000 : d.kind === "pad_low" ? 5000 : 3500)
                if (d.kind === "pad_low" || d.kind === "pad_crit")
                    root.btNotif(d.kind === "pad_crit" ? "critical" : "normal", d.name + " battery " + (d.kind === "pad_crit" ? "critical" : "low") + ": " + d.battery + "%", "")
            }
        }
        onExited: padRestart.start()
    }
    Timer { id: padRestart; interval: 3000; onTriggered: padProc.running = true }

    property bool micActive: false
    Process {
        id: privProc
        running: true
        command: ["python3", root.home + "/.config/hypr/waybar/scripts/privacy.py"]
        stdout: SplitParser {
            onRead: data => {
                let d; try { d = JSON.parse(data) } catch (e) { return }
                const on = (d.text || "") !== ""
                if (on && !root.micActive) root.pop("mic", { text: (d.tooltip || "").split("\n")[0] }, 3500)
                root.micActive = on
            }
        }
        onExited: privRestart.start()
    }
    Timer { id: privRestart; interval: 3000; onTriggered: privProc.running = true }

    // volume (PipeWire)
    PwObjectTracker { objects: [Pipewire.defaultAudioSink, Pipewire.defaultAudioSource] }
    readonly property real volume: Pipewire.defaultAudioSink?.audio?.volume ?? 0
    readonly property bool muted: Pipewire.defaultAudioSink?.audio?.muted ?? false
    onVolumeChanged: pop("volume", {}, 1600)
    onMutedChanged: pop("mute", { target: "sound" }, 2000)
    readonly property bool micMuted: Pipewire.defaultAudioSource?.audio?.muted ?? false
    onMicMutedChanged: pop("mute", { target: "mic" }, 2000)

    // brightness (sysfs, polled — sysfs has no change notifications)
    property string blDir: ""
    property int blMax: 1
    property int blRaw: -1
    Process {
        running: true
        command: ["sh", "-c", "for d in /sys/class/backlight/*; do echo $d; cat $d/max_brightness; break; done"]
        stdout: StdioCollector { onStreamFinished: { const l = text.trim().split("\n"); if (l.length === 2) { root.blDir = l[0]; root.blMax = parseInt(l[1]) || 1 } } }
    }
    FileView {
        id: blFile
        path: root.blDir ? root.blDir + "/brightness" : ""
        onLoaded: { const v = parseInt(text()); if (!isNaN(v) && v !== root.blRaw) { if (root.blRaw >= 0) root.pop("brightness", {}, 1600); root.blRaw = v } }
    }
    Timer { interval: 250; running: root.blDir !== ""; repeat: true; onTriggered: blFile.reload() }

    // ---------- battery: plug in/out, full, low (20%), critical (10%, again every 2%)
    readonly property bool onBattery: UPower.onBattery
    readonly property real batt: { const p = UPower.displayDevice?.percentage ?? 0; return p <= 1 ? p * 100 : p }
    readonly property int battState: UPower.displayDevice?.state ?? 0
    readonly property real toEmpty: UPower.displayDevice?.timeToEmpty ?? 0
    readonly property real toFull: UPower.displayDevice?.timeToFull ?? 0
    property bool lowShown: false
    property bool fullShown: false
    property int lastCrit: 101
    function hm(sec) { const m = Math.round(sec / 60); return m >= 60 ? Math.floor(m / 60) + "h " + String(m % 60).padStart(2, "0") + "m" : m + " min" }
    function storeNotif(urgency, title, body) {   // keep a copy in the notification centre (no island duplicate)
        Quickshell.execDetached(["notify-send", "-a", "Battery", "-u", urgency, "-i", "battery",
                                 "-h", "string:x-canonical-private-synchronous:battery", title, body])
    }
    function battEvent(kind, ms) { pop("battery", { kind: kind }, ms) }
    function checkBattery() {
        if (!ready) return
        if (!onBattery) { lowShown = false; lastCrit = 101; return }
        const p = Math.round(batt)
        if (p <= 10 && p <= lastCrit - 2) {
            lastCrit = p; lowShown = true
            battEvent("critical", 9000)
            storeNotif("critical", "Battery critical: " + p + "%", "Plug in now" + (toEmpty > 0 ? " · about " + hm(toEmpty) + " left" : ""))
        } else if (p <= 20 && !lowShown) {
            lowShown = true
            battEvent("low", 6000)
            storeNotif("normal", "Battery low: " + p + "%", toEmpty > 0 ? "About " + hm(toEmpty) + " left" : "Consider plugging in")
        }
    }
    onBattChanged: checkBattery()
    onReadyChanged: checkBattery()
    onOnBatteryChanged: {
        if (onBattery) { fullShown = false; battEvent("unplug", 3000) }
        else { lowShown = false; lastCrit = 101; battEvent("plug", 3000) }
        checkBattery()
    }
    onBattStateChanged: {
        if (battState === UPowerDeviceState.FullyCharged && !onBattery && !fullShown) {
            fullShown = true
            battEvent("full", 5000)
            storeNotif("normal", "Battery fully charged", "You can unplug the charger")
        }
    }

    // Bluetooth: connected / disconnected / low battery (20 %, once) / critical (10 %, every 2 %)
    function btIcon(icon) {
        const i = String(icon || "")   // a focus pop can leave a numeric icon in evData
        return i.indexOf("head") >= 0 ? 0xf02cb : i.indexOf("audio") >= 0 ? 0xf04c3 : i.indexOf("phone") >= 0 ? 0xf011c
             : i.indexOf("mouse") >= 0 ? 0xf037d : i.indexOf("keyboard") >= 0 ? 0xf030c : i.indexOf("gaming") >= 0 ? 0xf0297
             : i.indexOf("watch") >= 0 ? 0xf0b56 : i.indexOf("computer") >= 0 ? 0xf0322 : 0xf00af
    }
    Instantiator {
        model: Bluetooth.devices
        delegate: QtObject {
            id: btd
            required property var modelData
            readonly property bool isConnected: modelData.connected
            readonly property int bat: modelData.batteryAvailable ? Math.round(modelData.battery * 100) : -1
            property bool lowShown: false
            property int lastCrit: 101
            readonly property bool isPad: (modelData.icon || "").indexOf("gaming") >= 0
            onIsConnectedChanged: {
                if (isPad) return
                if (isConnected) { lowShown = false; lastCrit = 101; root.pop("bt", { dev: modelData, kind: "on" }, 3500) }
                else root.pop("bt", { name: modelData.name, icon: modelData.icon, kind: "off" }, 2800)
            }
            onBatChanged: {
                if (isPad || !isConnected || bat < 0 || !root.ready) return
                if (bat > 25) { lowShown = false; lastCrit = 101; return }
                if (bat <= 10 && bat <= lastCrit - 2) {
                    lastCrit = bat; lowShown = true
                    root.pop("bt", { dev: modelData, kind: "crit" }, 7000)
                    root.btNotif("critical", modelData.name + " battery critical: " + bat + "%", "Charge it soon")
                } else if (bat <= 20 && !lowShown) {
                    lowShown = true
                    root.pop("bt", { dev: modelData, kind: "low" }, 5000)
                    root.btNotif("normal", modelData.name + " battery low: " + bat + "%", "")
                }
            }
        }
    }
    function btNotif(urgency, title, body) {
        Quickshell.execDetached(["notify-send", "-a", "Bluetooth", "-u", urgency, "-i", "bluetooth",
                                 "-h", "string:x-canonical-private-synchronous:btbattery", title, body])
    }

    // test hook:  qs ipc -c island call island demo <plug|unplug|full|low|critical|song|volume>
    IpcHandler {
        target: "island"
        // called by ~/.config/hypr/UserScripts/audio-jack-fix.py on plug / unplug
        function jack(state: string): void { root.pop("jack", { plugged: state === "in" }, 2600) }
        function where(): string { return "focused=" + (Hyprland.focusedMonitor?.name ?? "?") + " island=" + root.islandMonitor + " screen=" + (root.islandScreen?.name ?? "?") + " screens=" + Quickshell.screens.map(x => x.name).join(",") }
        function idlepreview(): void { root.sp = ({ state: "idle" }) }
        function idlelastpreview(): void { root.sp = ({ state: "idle", last: { title: "POWER", artist: "Kanye West", cover: root.sp.cover || "" } }) }   // test only; restart the island after
        function demo(kind: string): void {
            if (["plug", "unplug", "full", "low", "critical"].indexOf(kind) >= 0) root.pop("battery", { kind: kind }, 4000)
            else if (kind.indexOf("bt:") === 0) root.pop("bt", { kind: kind.slice(3), name: "OnePlus Nord Buds 2", icon: "audio-headset",
                                                             dev: kind.slice(3) === "off" ? null : { name: "OnePlus Nord Buds 2", icon: "audio-headset", batteryAvailable: true,
                                                                   battery: kind.slice(3) === "crit" ? 0.08 : kind.slice(3) === "low" ? 0.18 : 0.72 } }, 4000)
            else if (kind.indexOf("pad:") === 0) root.pop("pad", { kind: kind.slice(4), name: "8BitDo Ultimate 2.4G Wireless Controller",
                                                              bus: "USB receiver", battery: kind.slice(4) === "pad_crit" ? 7 : kind.slice(4) === "pad_low" ? 18 : 82 }, 4000)
            else if (kind.indexOf("net:") === 0) root.pop("net", { kind: kind.slice(4), ssid: "Airtel_CyberPsycho", signal: 67, ip: "100.85.64.102", name: "enp2s0", mode: "DNS only (1.1.1.1)" }, 4000)
            else root.pop(kind, {}, 4000)
        }
    }

    // ------------------------------------------------------------ window
    readonly property bool fullscreen: Hyprland.focusedWorkspace?.hasFullscreen ?? false

    // ---- which monitor the island lives on ----
    //   "focused" : follows the monitor you're working on (pointer / active window)
    //   "eDP-1"   : always the laptop screen (or any other monitor name, e.g. "HDMI-A-1")
    readonly property string placement: "focused"
    property string islandMonitor: ""
    // follow focus with a short delay so passing the pointer across a screen edge doesn't make it jump
    Timer { id: follow; interval: 400; onTriggered: root.islandMonitor = Hyprland.focusedMonitor?.name ?? "" }
    Connections { target: Hyprland; function onFocusedMonitorChanged() { follow.restart() } }
    readonly property var islandScreen: {
        const want = placement === "focused" ? (islandMonitor || Hyprland.focusedMonitor?.name || "") : placement
        const list = Quickshell.screens
        for (let i = 0; i < list.length; i++) if (list[i].name === want) return list[i]
        return list.length ? list[0] : null
    }

    PanelWindow {
        id: win
        visible: !root.fullscreen
        screen: root.islandScreen
        anchors.top: true
        margins.top: 6
        implicitWidth: 640
        implicitHeight: 340
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "dynamic-island"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        mask: Region { x: pill.x; y: pill.y; width: pill.width; height: pill.height }

        // Spider-Punk: the misprint layer follows the panel as it grows (blue for notifications)
        Rectangle {
            x: pill.x + 4; y: pill.y + 4; width: pill.width; height: pill.height; radius: pill.radius
            color: root.mode === "notif" ? Punk.blue : Punk.crimson
            Behavior on color { ColorAnimation { duration: 220 } }
            opacity: 0.95
        }
        Rectangle {
            id: pill
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            color: Punk.bg
            border.width: 2
            // ink outline; crimson while a notification or a critical battery alert is showing
            border.color: root.ev === "battery" && root.evData.kind === "critical" ? Punk.yellow
                        : root.mode === "notif" ? Punk.crimson : Punk.ink
            Behavior on border.color { ColorAnimation { duration: 220 } }
            SequentialAnimation on border.width {
                running: root.ev === "battery" && root.evData.kind === "critical"; loops: Animation.Infinite
                NumberAnimation { to: 4; duration: 500 } NumberAnimation { to: 2; duration: 500 }
                onRunningChanged: if (!running) pill.border.width = 2
            }
            clip: true
            radius: 5                              // a comic panel, not a pill

            // halftone screen in the right-hand corner of the panel
            Image {
                anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 2
                width: parent.width * 0.42; height: parent.height - 4
                fillMode: Image.Tile; source: Punk.assets + "dots-crimson.svg"; sourceSize: Qt.size(12, 12)
                opacity: 0.22
            }

            readonly property var sizes: ({
                idle: [root.timerOn ? 210 : root.soundOn ? 168 : 150, 38], idlehover: [root.sp.last ? 560 : 360, root.sp.last ? 92 : 52], login: [220, 38],
                compact: [460, 38], paused: [168, 38], expanded: [560, (root.sp.lyrics && root.sp.lyrics.length) ? 286 : 180],
                song: [560, 84], volume: [340, 40], brightness: [340, 40],
                notif: [560, 78], battery: [440, 40], net: [440, 40], jack: [400, 40], mute: [380, 40], focus: [320, 40], timer: [360, 40], wall: [440, 64], pad: [470, 40], bt: [460, 40], mic: [430, 40]
            })
            width: (sizes[root.mode] || [560, 38])[0]
            height: (sizes[root.mode] || [560, 38])[1]
            Behavior on width { NumberAnimation { duration: 420; easing.type: Easing.OutBack; easing.overshoot: 0.8 } }
            Behavior on height { NumberAnimation { duration: 420; easing.type: Easing.OutBack; easing.overshoot: 0.8 } }

            // HoverHandler (unlike a MouseArea's containsMouse) stays "hovered" while the
            // pointer is over the buttons / progress bar inside the island
            HoverHandler {
                onHoveredChanged: { if (hovered) { collapse.stop(); expandT.restart() } else { expandT.stop(); collapse.restart() } }
            }
            MouseArea {
                id: hover
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
                onClicked: mouse => {
                    if (root.ev === "notif") { root.ev = ""; center.toggle(); return }
                    if (root.ev === "net" && root.evData.kind === "portal") { Quickshell.execDetached(["xdg-open", "http://neverssl.com"]); root.ev = ""; return }
                    if (!root.hasTrack) { root.spotify(["open"]); return }
                    if (mouse.button === Qt.MiddleButton) root.spotify(["like"])
                    else if (mouse.button === Qt.RightButton) root.spotify(["menu"])
                    else if (root.mode !== "expanded") root.spotify(["toggle"])
                }
            }
            Timer { id: expandT; interval: 140; onTriggered: { root.hovered = true; root.ev = "" } }
            Timer { id: collapse; interval: 350; onTriggered: root.hovered = false }

            // ---------- idle
            Fade {
                cur: root.mode; when: "idle"
                // like the real Dynamic Island: an empty pill with the camera lens on the right;
                // white visualizer on the left while any sound plays on the computer
                Bars { x: 16; anchors.verticalCenter: parent.verticalCenter
                       height: 18; maxH: 16; values: root.bars; tint: "#F5F0E8"
                       opacity: root.soundOn && !root.timerOn ? 1 : 0; Behavior on opacity { NumberAnimation { duration: 200 } } }
                // timer running: label + countdown (yellow focus, blue break) in place of the visualizer
                Row {
                    x: 16; anchors.verticalCenter: parent.verticalCenter; spacing: 8; visible: root.timerOn
                    Label { anchors.verticalCenter: parent.verticalCenter; text: root.timerLabel
                            font.family: Punk.poster; font.pixelSize: 13; font.letterSpacing: 1.2; color: root.dim }
                    Label { anchors.verticalCenter: parent.verticalCenter; text: root.mmss(root.timerLeft)
                            font.family: Punk.poster; font.pixelSize: 19; font.letterSpacing: 1
                            color: root.timerLabel === "BREAK" ? Punk.blue : Punk.yellow }
                }
                // the "camera lens" is a tiny punk spider now
                Image {
                    anchors.right: parent.right; anchors.rightMargin: 9; anchors.verticalCenter: parent.verticalCenter
                    width: 22; height: 22; source: Punk.assets + "spider.svg"; sourceSize: Qt.size(44, 44)
                }
                // DND / focus mode on: its icon in purple next to the spider
                Label { anchors.right: parent.right; anchors.rightMargin: 37; anchors.verticalCenter: parent.verticalCenter
                        font.pixelSize: 15; color: "#8B35FF"
                        text: center.focusMode ? root.glyph(center.focusMode.icon) : ""
                        visible: !!center.focusMode }
            }
            // ---------- idle hover: resume the last song (opens Spotify if it is closed)
            Fade {
                cur: root.mode; when: "idlehover"
                readonly property var last: root.sp.last || null
                // with a remembered song
                Item {
                    anchors.fill: parent
                    visible: parent.last !== null
                    Cover { id: lc; x: 14; anchors.verticalCenter: parent.verticalCenter; width: 64; height: 64; radius: 2
                            src: parent.parent.last && parent.parent.last.cover ? "file://" + parent.parent.last.cover : "" }
                    Column {
                        anchors.left: lc.right; anchors.leftMargin: 14; anchors.right: resumeBtn.left; anchors.rightMargin: 14
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Label { text: "LAST PLAYED"; color: root.green; font.family: Punk.poster; font.pixelSize: 15; font.letterSpacing: 1.5 }
                        Label { width: parent.width; text: parent.parent.parent.last ? parent.parent.parent.last.title : ""; font.pixelSize: 16; font.bold: true }
                        Label { width: parent.width; text: parent.parent.parent.last ? parent.parent.parent.last.artist : ""; color: root.dim }
                    }
                    Rectangle {
                        id: resumeBtn
                        anchors.right: openBtn.left; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                        width: 44; height: 44; radius: 2; color: rb.containsMouse ? Punk.yellow : Punk.crimson
                        border.width: 2; border.color: Punk.ink
                        scale: rb.pressed ? 0.9 : 1; Behavior on scale { NumberAnimation { duration: 100 } }
                        Label { anchors.centerIn: parent; anchors.horizontalCenterOffset: 2; text: root.glyph(0xf040a); color: "#050306"; font.pixelSize: 22 }
                        MouseArea { id: rb; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: root.spotify(["resume"]) }
                    }
                    Btn { id: openBtn; anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter
                          text: root.glyph(0xf1bc); font.pixelSize: 20; color: root.green; onActivated: root.spotify(["open"]) }
                }
                // nothing remembered yet
                Item {
                    anchors.fill: parent
                    visible: parent.last === null
                    Label { x: 16; anchors.verticalCenter: parent.verticalCenter; text: root.glyph(0xf1bc); color: root.green; font.pixelSize: 20 }
                    Label { x: 46; anchors.verticalCenter: parent.verticalCenter; text: root.sp.app ? "Spotify is open · nothing playing" : "Spotify is closed"
                            color: root.dim; font.pixelSize: 12 }
                    Rectangle {
                        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                        width: 120; height: 36; radius: 2; color: ob.containsMouse ? Punk.yellow : Punk.crimson
                        border.width: 2; border.color: Punk.ink
                        Label { anchors.centerIn: parent; text: root.glyph(0xf040a) + "  Play"; color: "#050306"; font.bold: true }
                        MouseArea { id: ob; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: root.spotify(["resume"]) }
                    }
                }
            }
            Fade {
                cur: root.mode; when: "login"
                Label { anchors.centerIn: parent; text: root.glyph(0xf1bc) + "  Click to log in"; color: root.green; font.pixelSize: 12 }
            }

            // ---------- compact player
            Fade {
                cur: root.mode; when: "compact"
                Cover { id: cc; x: 7; anchors.verticalCenter: parent.verticalCenter; width: 24; height: 24; radius: 2
                        src: root.sp.cover ? "file://" + root.sp.cover : "" }
                Label {
                    id: line
                    anchors.left: cc.right; anchors.leftMargin: 10
                    anchors.right: heart.left; anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.compactLine
                    // poster type for the running lyric (Bebas is caps-only), title line stays mono
                    font.family: root.lyricIdx >= 0 ? Punk.poster : Punk.mono
                    font.pixelSize: root.lyricIdx >= 0 ? 18 : 13
                    font.letterSpacing: root.lyricIdx >= 0 ? 0.5 : 0
                    color: root.sp.playing ? root.text : root.dim
                    onTextChanged: lineFade.restart()
                    NumberAnimation { id: lineFade; target: line; property: "opacity"; from: 0.2; to: 1; duration: 260 }
                }
                Label { id: heart; anchors.right: cbars.left; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                        text: root.sp.liked ? root.glyph(0xf02d1) : ""; color: root.green; width: root.sp.liked ? implicitWidth : 0 }
                Bars { id: cbars; anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                       height: 18; maxH: 16; values: root.bars }
            }

            // ---------- paused (iOS compact style): cover on the left, status on the right
            Fade {
                cur: root.mode; when: "paused"
                Cover { x: 7; anchors.verticalCenter: parent.verticalCenter; width: 24; height: 24; radius: 2
                        src: root.sp.cover ? "file://" + root.sp.cover : "" }
                Label { anchors.right: parent.right; anchors.rightMargin: 15; anchors.verticalCenter: parent.verticalCenter
                        text: root.glyph(0xf03e4); font.pixelSize: 15; color: root.dim
                        opacity: root.soundOn ? 0 : 1; Behavior on opacity { NumberAnimation { duration: 200 } } }
                Bars { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                       height: 18; maxH: 16; values: root.bars; tint: "#F5F0E8"
                       opacity: root.soundOn ? 1 : 0; Behavior on opacity { NumberAnimation { duration: 200 } } }
            }

            // ---------- expanded mini player
            Fade {
                cur: root.mode; when: "expanded"
                Cover { id: bigc; x: 16; y: 16; width: 132; height: 132; radius: 2
                        src: root.sp.cover ? "file://" + root.sp.cover : "" }
                Column {
                    x: bigc.x + bigc.width + 18; y: 18
                    width: parent.width - x - 18
                    spacing: 3
                    Label { width: parent.width; text: (root.sp.title || "").toUpperCase(); font.family: Punk.poster; font.pixelSize: 24; font.letterSpacing: 0.5 }
                    Label { width: parent.width; text: root.sp.artist || ""; color: "#AAA2B2" }
                    Label { width: parent.width; text: (root.sp.album || "") + (root.sp.year ? "  ·  " + root.sp.year : ""); color: root.dim; font.pixelSize: 11 }
                    Item { width: 1; height: 10 }
                    // seekable progress
                    Item {
                        width: parent.width; height: 14
                        Rectangle { id: track; anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 7; radius: 0; color: Punk.surface2
                                     border.width: 1; border.color: Punk.ink
                            Rectangle { width: parent.width * (root.sp.duration ? root.position / root.sp.duration : 0); height: parent.height; radius: 0; color: Punk.crimson } }
                        Rectangle { width: 11; height: 13; radius: 0; color: Punk.yellow; border.width: 2; border.color: Punk.ink; anchors.verticalCenter: parent.verticalCenter
                                    x: track.width * (root.sp.duration ? root.position / root.sp.duration : 0) - width / 2
                                    visible: seek.containsMouse }
                        MouseArea { id: seek; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: mouse => root.spotify(["seek", String(Math.round(mouse.x / width * root.sp.duration))]) }
                    }
                    Item {
                        width: parent.width; height: 14
                        Label { text: root.fmt(root.position); color: root.dim; font.pixelSize: 10 }
                        Label { anchors.right: parent.right; text: "-" + root.fmt((root.sp.duration || 0) - root.position); color: root.dim; font.pixelSize: 10 }
                    }
                    Item { width: 1; height: 2 }
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 26
                        Btn { text: root.glyph(0xf049d); onActivated: root.spotify(["shuffle"]); font.pixelSize: 15; color: root.sp.shuffle ? root.green : root.dim; anchors.verticalCenter: parent.verticalCenter }
                        Btn { text: root.glyph(0xf04ae); onActivated: root.spotify(["prev"]) }
                        Btn { text: root.sp.playing ? root.glyph(0xf03e4) : root.glyph(0xf040a); onActivated: root.spotify(["toggle"]); font.pixelSize: 26 }
                        Btn { text: root.glyph(0xf04ad); onActivated: root.spotify(["next"]) }
                        Btn { text: root.sp.liked ? root.glyph(0xf02d1) : root.glyph(0xf02d5); onActivated: root.spotify(["like"]); font.pixelSize: 16
                              color: root.sp.liked ? root.green : root.dim; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
                // synced lyrics
                Column {
                    visible: !!(root.sp.lyrics && root.sp.lyrics.length > 0)
                    x: 16; y: 164; width: parent.width - 32
                    spacing: 4
                    Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.lyric(-1); color: Qt.rgba(1, 1, 1, 0.32); font.pixelSize: 12 }
                    Label { id: curLyric; width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.lyric(0) || "♪"
                            color: root.green; font.family: Punk.poster; font.pixelSize: 21; font.letterSpacing: 0.5; wrapMode: Text.WordWrap; maximumLineCount: 2
                            onTextChanged: lyrFade.restart()
                            NumberAnimation { id: lyrFade; target: curLyric; property: "opacity"; from: 0.15; to: 1; duration: 300 } }
                    Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.lyric(1); color: Qt.rgba(1, 1, 1, 0.5); font.pixelSize: 13 }
                    Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.lyric(2); color: Qt.rgba(1, 1, 1, 0.32); font.pixelSize: 12 }
                }
            }

            // ---------- events
            Fade {
                cur: root.mode; when: "song"
                Cover { id: sc; x: 12; anchors.verticalCenter: parent.verticalCenter; width: 60; height: 60; radius: 2
                        src: root.sp.cover ? "file://" + root.sp.cover : "" }
                Column {
                    anchors.left: sc.right; anchors.leftMargin: 14; anchors.right: sbars.left; anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Label { text: "NOW PLAYING"; color: root.green; font.family: Punk.poster; font.pixelSize: 15; font.letterSpacing: 1.5 }
                    Label { width: parent.width; text: root.sp.title || ""; font.pixelSize: 16; font.bold: true }
                    Label { width: parent.width; text: root.sp.artist || ""; color: root.dim }
                }
                Bars { id: sbars; anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter; height: 30; maxH: 28; values: root.bars }
            }
            Fade {
                cur: root.mode; when: "volume"
                Meter { value: root.muted ? 0 : root.volume; tint: root.muted ? root.dim : Punk.crimson
                        icon: root.muted ? root.glyph(0xf075f) : root.glyph(root.volume < 0.34 ? 0xf057f : root.volume < 0.67 ? 0xf0580 : 0xf057e) }
            }
            Fade {
                cur: root.mode; when: "brightness"
                Meter { value: root.blRaw / root.blMax; icon: root.glyph(0xf00e0); tint: Punk.blue }
            }
            Fade {
                cur: root.mode; when: "notif"
                ClippingRectangle {
                    id: ni; x: 14; anchors.verticalCenter: parent.verticalCenter; width: 44; height: 44; radius: 2
                    color: Punk.surface2; border.width: 2; border.color: Punk.crimson
                    readonly property string ic: root.evData.icon || ""
                    Label { anchors.centerIn: parent; text: String.fromCodePoint(0xf009a); font.pixelSize: 20; color: "#AAA2B2"
                            visible: nimg.status !== Image.Ready }
                    Image { id: nimg; anchors.fill: parent; anchors.margins: ni.ic.startsWith("/") || ni.ic.startsWith("file:") ? 0 : 8
                            fillMode: Image.PreserveAspectFit; asynchronous: true
                            source: ni.ic === "" ? ""
                                    : ni.ic.startsWith("/") ? "file://" + ni.ic
                                    : ni.ic.indexOf("://") > 0 ? ni.ic : Quickshell.iconPath(ni.ic, "dialog-information") }
                }
                Column {
                    anchors.left: ni.right; anchors.leftMargin: 14; anchors.right: parent.right; anchors.rightMargin: 20
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1
                    Label { width: parent.width; text: (root.evData.app || "").toUpperCase(); color: Punk.crimson; font.family: Punk.poster; font.pixelSize: 14; font.letterSpacing: 1 }
                    Label { width: parent.width; text: root.evData.summary || ""; font.bold: true; textFormat: Text.PlainText }
                    Label { width: parent.width; text: (root.evData.body || "").replace(/<[^>]*>/g, "").replace(/\n/g, "  "); color: "#AAA2B2"; font.pixelSize: 12; textFormat: Text.PlainText }
                }
            }
            Fade {
                cur: root.mode; when: "pad"
                readonly property string kind: root.evData.kind || "pad_on"
                readonly property int bat: typeof root.evData.battery === "number" ? root.evData.battery : -1
                readonly property color tint: kind === "pad_crit" ? "#FF1744" : kind === "pad_low" ? "#FFD43B" : kind === "pad_off" ? "#AAA2B2" : "#00B8FF"
                Label { x: 18; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 18; color: parent.tint; text: root.glyph(0xf0297) }
                Column {
                    x: 50; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 50 - 80
                    spacing: 0
                    Label { width: parent.width; text: root.evData.name || "Controller"; font.bold: true; font.pixelSize: 12
                            color: parent.parent.kind === "pad_off" ? root.dim : root.text }
                    Label { width: parent.width; font.pixelSize: 10; color: parent.parent.tint
                            text: (({ pad_on: "connected", pad_off: "disconnected", pad_low: "battery low", pad_crit: "battery critical — charge it" })[parent.parent.kind] || "")
                                  + (root.evData.bus ? "  ·  " + root.evData.bus : "") }
                }
                Label { anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter
                        visible: parent.bat >= 0 && parent.kind !== "pad_off"; font.pixelSize: 12
                        color: parent.bat <= 10 ? "#FF1744" : parent.bat <= 20 ? "#FFD43B" : "#00B8FF"
                        text: root.glyph([0xf008e, 0xf007a, 0xf007b, 0xf007c, 0xf007d, 0xf007e, 0xf007f, 0xf0080, 0xf0081, 0xf0082, 0xf0079][Math.min(10, Math.round(Math.max(0, parent.bat) / 10))]) + " " + parent.bat + "%" }
            }
            Fade {
                cur: root.mode; when: "wall"
                Cover { id: wthumb; x: 12; anchors.verticalCenter: parent.verticalCenter; width: 72; height: 44; radius: 2
                        src: root.evData.thumb ? "file://" + root.evData.thumb : "" }
                Column {
                    anchors.left: wthumb.right; anchors.leftMargin: 14; anchors.right: parent.right; anchors.rightMargin: 18
                    anchors.verticalCenter: parent.verticalCenter
                    Label { text: "WALLPAPER"; color: Punk.yellow; font.family: Punk.poster; font.pixelSize: 15; font.letterSpacing: 1.5 }
                    Label { width: parent.width; text: root.evData.name || ""; font.bold: true }
                }
            }
            Fade {
                cur: root.mode; when: "timer"
                readonly property string kind: root.evData.kind || "start"
                Label { x: 18; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 17
                        color: parent.kind === "done" ? Punk.crimson : parent.kind === "stop" ? root.dim : Punk.yellow
                        text: root.glyph(parent.kind === "stop" ? 0xf051f : 0xf13ab) }
                Label { x: 50; anchors.verticalCenter: parent.verticalCenter; font.bold: true
                        text: parent.kind === "done" ? "Time is up" : parent.kind === "stop" ? "Timer stopped"
                              : root.timerLabel === "FOCUS" ? "Focus · 25 min" : root.timerLabel === "BREAK" ? "Break · 5 min"
                              : "Timer · " + Math.round(root.timerTotal / 60) + " min" }
                Label { anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter
                        font.family: Punk.poster; font.pixelSize: 17; color: Punk.yellow
                        text: root.timerOn ? root.mmss(root.timerLeft) : "" }
            }
            Fade {
                cur: root.mode; when: "focus"
                readonly property bool on: (root.evData.name || "") !== ""
                Label { x: 18; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 17; color: parent.on ? "#8B35FF" : root.dim
                        text: root.glyph(parent.on ? root.evData.icon : 0xf0594) }
                Label { x: 50; anchors.verticalCenter: parent.verticalCenter; font.bold: true; color: parent.on ? root.text : root.dim
                        text: parent.on ? root.evData.name : "Focus off" }
                Label { anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter
                        color: "#8B35FF"; font.pixelSize: 12; text: parent.on ? "On" : "" }
            }
            Fade {
                cur: root.mode; when: "mute"
                readonly property bool mic: root.evData.target === "mic"
                readonly property bool off: mic ? root.micMuted : root.muted
                Label { x: 18; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 18
                        color: parent.off ? "#FF1744" : (parent.mic ? "#00B8FF" : root.text)
                        text: parent.mic ? root.glyph(parent.off ? 0xf036d : 0xf036c)
                                         : root.glyph(parent.off ? 0xf075f : (root.volume < 0.34 ? 0xf057f : root.volume < 0.67 ? 0xf0580 : 0xf057e)) }
                Label { x: 50; anchors.verticalCenter: parent.verticalCenter; font.bold: true
                        color: parent.off ? "#FF1744" : root.text
                        text: parent.mic ? (parent.off ? "Microphone muted" : "Microphone on")
                                         : (parent.off ? "Sound muted" : "Sound on") }
                Label { anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter
                        color: root.dim; font.pixelSize: 12
                        text: parent.mic ? "" : (parent.off ? "" : Math.round(root.volume * 100) + "%") }
            }
            Fade {
                cur: root.mode; when: "jack"
                readonly property bool plugged: root.evData.plugged === true
                Label { x: 18; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 18
                        text: parent.plugged ? root.glyph(0xf02cb) : root.glyph(0xf04c3); color: parent.plugged ? "#00B8FF" : root.text }
                Label { x: 50; anchors.verticalCenter: parent.verticalCenter; font.bold: true
                        text: parent.plugged ? "Headphones connected" : "Playing through speakers" }
                Label { anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter
                        color: root.dim; font.pixelSize: 12
                        text: root.muted ? "muted" : Math.round(root.volume * 100) + "%" }
            }
            Fade {
                cur: root.mode; when: "net"
                readonly property string kind: root.evData.kind || ""
                readonly property var look: ({
                    wifi_on:   [0xf0928, "#F5F0E8", "Connected", (root.evData.ssid || "") ],
                    wifi_lost: [0xf092d, "#FF1744", "Wi-Fi disconnected", root.evData.ssid || ""],
                    radio_off: [0xf092e, "#AAA2B2", "Wi-Fi off", ""],
                    radio_on:  [0xf0928, "#F5F0E8", "Wi-Fi on", "searching…"],
                    eth_on:    [0xf0200, "#00B8FF", "Ethernet connected", root.evData.name || ""],
                    eth_off:   [0xf0201, "#AAA2B2", "Ethernet unplugged", ""],
                    vpn_on:    [0xf0582, "#00B8FF", "Tailscale connected", root.evData.ip || ""],
                    vpn_off:   [0xf0582, "#AAA2B2", "Tailscale off", ""],
                    limited:   [0xf092c, "#FFD43B", "No internet", "connected, but offline"],
                    portal:    [0xf092c, "#FFD43B", "Sign in to this network", "click to open"],
                    online:    [0xf0928, "#00B8FF", "Back online", ""],
                    warp_on:   [0xf015f, "#f38020", "Cloudflare WARP on", root.evData.mode || ""],
                    warp_off:  [0xf0164, "#AAA2B2", "Cloudflare WARP off", ""],
                    tor_start: [0xf05f9, "#b48ee0", "Tor connecting…", "building circuits"],
                    tor_on:    [0xf05f9, "#b48ee0", "Connected to Tor", "SOCKS 127.0.0.1:9050"],
                    tor_off:   [0xf05f9, "#AAA2B2", "Tor stopped", ""]
                })[kind] || [0xf0928, "#F5F0E8", "Network", ""]
                Label { x: 18; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 17; color: parent.look[1]
                        text: root.glyph(parent.kind === "wifi_on" ? [0xf092f, 0xf091f, 0xf0922, 0xf0925, 0xf0928][Math.min(4, Math.floor((root.evData.signal || 0) / 20))] : parent.look[0]) }
                Label { id: nt; x: 48; anchors.verticalCenter: parent.verticalCenter; font.bold: true; color: parent.look[1] === "#F5F0E8" ? root.text : parent.look[1]
                        text: parent.look[2] }
                Label { anchors.left: nt.right; anchors.leftMargin: 10; anchors.right: parent.right; anchors.rightMargin: 18
                        anchors.verticalCenter: parent.verticalCenter; horizontalAlignment: Text.AlignRight
                        color: root.dim; font.pixelSize: 12
                        text: parent.look[3] + (parent.kind === "wifi_on" && root.evData.signal ? "  ·  " + root.evData.signal + "%" : "") }
            }
            Fade {
                cur: root.mode; when: "battery"
                readonly property string kind: root.evData.kind || ""
                readonly property color tint: kind === "critical" ? "#FF1744" : kind === "low" ? "#FFD43B"
                                              : (kind === "plug" || kind === "full") ? "#00B8FF" : "#F5F0E8"
                Label { x: 18; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 17; color: parent.tint
                        text: parent.kind === "plug" ? root.glyph(0xf0084) : parent.kind === "full" ? root.glyph(0xf06a5)
                              : parent.kind === "critical" ? root.glyph(0xf10cd) : parent.kind === "low" ? root.glyph(0xf007b) : root.glyph(0xf0079) }
                Label { x: 48; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 48 - 150; font.bold: true; color: parent.tint
                        text: ({ plug: "Charging", unplug: "On battery", full: "Fully charged", low: "Battery low",
                                 critical: "Battery critical — plug in" })[parent.kind] || "Battery" }
                Label { anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter
                        color: root.dim; font.pixelSize: 12
                        text: Math.round(root.batt) + "%" + (parent.kind === "plug" && root.toFull > 0 ? "  ·  " + root.hm(root.toFull) + " to full"
                              : (parent.kind !== "plug" && parent.kind !== "full" && root.toEmpty > 0) ? "  ·  " + root.hm(root.toEmpty) + " left" : "") }
            }
            Fade {
                cur: root.mode; when: "bt"
                readonly property string kind: root.evData.kind || "on"
                readonly property var dev: root.evData.dev || null
                readonly property string dname: dev ? dev.name : (root.evData.name || "Device")
                readonly property int bat: dev && dev.batteryAvailable ? Math.round(dev.battery * 100) : -1
                readonly property color tint: kind === "crit" ? "#FF1744" : kind === "low" ? "#FFD43B" : kind === "off" ? "#AAA2B2" : "#00B8FF"
                Label { x: 18; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 17; color: parent.tint
                        text: root.glyph(root.btIcon(parent.dev ? parent.dev.icon : root.evData.icon)) }
                Label { id: btn1; x: 48; anchors.verticalCenter: parent.verticalCenter; width: Math.min(implicitWidth, parent.width - 48 - 150)
                        text: parent.dname; font.bold: true; color: parent.kind === "off" ? root.dim : root.text }
                Label { anchors.left: btn1.right; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter
                        color: parent.tint; font.pixelSize: 12
                        text: ({ on: "connected", off: "disconnected", low: "battery low", crit: "battery critical" })[parent.kind] || "" }
                Label { anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter
                        visible: parent.bat >= 0 && parent.kind !== "off"; font.pixelSize: 12
                        color: parent.bat <= 10 ? "#FF1744" : parent.bat <= 20 ? "#FFD43B" : "#00B8FF"
                        text: root.glyph([0xf008e, 0xf007a, 0xf007b, 0xf007c, 0xf007d, 0xf007e, 0xf007f, 0xf0080, 0xf0081, 0xf0082, 0xf0079][Math.min(10, Math.round(parent.bat / 10))]) + " " + parent.bat + "%" }
            }
            Fade {
                cur: root.mode; when: "mic"
                Label { x: 18; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 17; color: "#FF6B24"
                        text: (root.evData.text || "").indexOf("screen") >= 0 ? root.glyph(0xf0379) : root.glyph(0xf036c) }
                Label { x: 48; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 66
                        text: (root.evData.text || "Microphone in use").replace(/^\S+\s+/, ""); color: "#F5F0E8"; textFormat: Text.StyledText }
            }
        }
    }
}

