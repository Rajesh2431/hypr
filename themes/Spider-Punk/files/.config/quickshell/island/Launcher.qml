// Spotlight-style launcher (Super+D):  qs ipc -c island call launcher toggle
//
//  type to search apps (ranked by match quality + how often you use them),
//  "= 2+2" or plain math  -> calculator (qalc: units, currencies…; Enter copies)
//  3+ letters             -> also matching files in ~ (fd)
//  "> command"            -> run it in a terminal
//  system actions         -> Lock, Sleep, Restart, Shut Down, Log Out, Control Center…
//  last row               -> search the web
//  ↑/↓ (or Tab) to move · Enter to open · Esc to close
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Widgets

Scope {
    id: lx
    required property var shell
    property bool open: false
    property string query: ""
    property var results: []
    property int sel: 0

    readonly property string home: Quickshell.env("HOME")
    readonly property string scripts: home + "/.config/hypr/scripts"
    function g(cp) { return String.fromCodePoint(cp) }
    function sh(cmd) { Quickshell.execDetached(["sh", "-c", cmd]) }
    function toggle() { if (open) close(); else { query = ""; calc = ""; files = []; open = true; compute() } }
    function close() { open = false }

    IpcHandler {
        target: "launcher"
        function toggle(): void { lx.toggle() }
        function hide(): void { lx.close() }
        function search(q: string): void { if (!lx.open) lx.toggle(); input.text = q }   // open with a query
    }

    // ---------------- usage counts (ranking)
    property var counts: ({})
    FileView { id: usage; path: lx.home + "/.cache/island/launcher.json"
               onLoaded: { try { lx.counts = JSON.parse(text()).counts || {} } catch (e) {} } }
    function used(id) { const c = Object.assign({}, counts); c[id] = (c[id] || 0) + 1; counts = c
                        usage.setText(JSON.stringify({ counts: c }) + "\n") }

    // ---------------- calculator (qalc) and files (fd), both async + debounced
    property string calc: ""
    property var files: []
    // anything with a number (or "=…") goes to qalc; the answer is kept only if it is a real result
    function looksMath(q) { return /^=/.test(q) || (/\d/.test(q) && q.length <= 60 && !/^[a-z]+\d*$/i.test(q)) }
    Timer { id: slow; interval: 140; onTriggered: {
        const q = lx.query.trim()
        if (q && lx.looksMath(q)) {
            const expr = q.replace(/^=\s*/, "").replace(/(\d+(?:\.\d+)?)\s*%\s*of\s+/gi, "$1% * ")   // "15% of 2400" -> 15% * 2400
            calcProc.command = ["qalc", "-t", expr]; calcProc.running = true
        } else lx.calc = ""
        if (q.length >= 3 && !q.startsWith(">") && !/^=/.test(q) && !/^[\d\s.,+\-*\/^%()]+$/.test(q)) {
            fdProc.command = ["fd", "-i", "--max-results", "4", "--max-depth", "6", "-E", "node_modules", "-E", ".cache",
                              "-E", ".local/share/Steam", "--", q.replace(/\s+/g, ".*"), lx.home]
            fdProc.running = true
        } else lx.files = []
    } }
    Process { id: calcProc; stdout: StdioCollector { onStreamFinished: {
        const r = text.trim(), q = lx.query.trim().replace(/^=\s*/, "")
        // reject errors, echoes of the input, and answers without a number
        const ok = r && !/error|warning|undefined|^[a-z ]+$/i.test(r) && /\d/.test(r) && !/[a-z]+\(/i.test(r)   // no unevaluated functions
                   && r.replace(/\s/g, "") !== q.replace(/\s/g, "")
        // "5 km to mi" comes back as "3 mi + 188 yd + …": ask again for one decimal number in the target unit
        const m = q.match(/^(.*\S)\s+(?:to|in)\s+([^\s\d]+)$/i)
        if (ok && / \+ /.test(r) && m) { calc2.unit = m[2]; calc2.command = ["qalc", "-t", "(" + m[1] + ")/(1 " + m[2] + ")"]; calc2.running = true; return }
        lx.calc = ok ? r : ""; lx.compute() } } }
    Process { id: calc2; property string unit
              stdout: StdioCollector { onStreamFinished: {
                  const v = parseFloat(text.trim().replace(/^≈\s*/, ""))
                  lx.calc = isNaN(v) ? "" : (Math.abs(v - Math.round(v)) < 1e-9 ? String(Math.round(v)) : "≈ " + Number(v.toPrecision(6))) + " " + calc2.unit
                  lx.compute() } } }
    Process { id: fdProc; stdout: StdioCollector { onStreamFinished: { lx.files = text.trim() ? text.trim().split("\n") : []; lx.compute() } } }
    onQueryChanged: { sel = 0; if (!looksMath(query.trim())) calc = ""; compute(); slow.restart() }
    Connections { target: DesktopEntries.applications; function onValuesChanged() { if (lx.open) lx.compute() } }
    Timer { id: openKick; interval: 60; onTriggered: lx.compute() }
    onOpenChanged: if (open) openKick.restart()

    // ---------------- system actions
    readonly property var actions: [
        { name: "Lock Screen", icon: 0xf033e, keys: "lock", cmd: () => sh(scripts + "/LockScreen.sh") },
        { name: "Sleep", icon: 0xf04b2, keys: "suspend sleep", cmd: () => sh("systemctl suspend") },
        { name: "Restart", icon: 0xf0709, keys: "reboot restart", cmd: () => sh(scripts + "/Wlogout.sh") },
        { name: "Shut Down", icon: 0xf0425, keys: "power off shutdown", cmd: () => sh(scripts + "/Wlogout.sh") },
        { name: "Log Out", icon: 0xf0343, keys: "logout exit", cmd: () => sh(scripts + "/Wlogout.sh") },
        { name: "Control Center", icon: 0xf0493, keys: "notifications control center focus", cmd: () => sh("qs ipc -c island call center toggle") },
        { name: "Wallpaper", icon: 0xf02e9, keys: "wallpaper background", cmd: () => sh("qs ipc -c island call wallpaper toggle") },
        { name: "KooL Settings", icon: 0xf0493, keys: "settings preferences kool", cmd: () => sh(scripts + "/Kool_Quick_Settings.sh") },
        { name: "Screenshot", icon: 0xf0100, keys: "screenshot capture", cmd: () => sh("sleep 0.3; " + scripts + "/ScreenShot.sh --area") },
        { name: "Color Picker", icon: 0xf0485, keys: "color picker hex", cmd: () => sh("sleep 0.3; hyprpicker -a") }
    ]

    // ---------------- ranking
    function score(q, e) {
        const n = (e.name || "").toLowerCase()
        let s = 0
        if (n === q) s = 120
        else if (n.startsWith(q)) s = 100
        else if (n.split(/[\s\-_.]+/).some(w => w.startsWith(q))) s = 85
        else if (n.indexOf(q) >= 0) s = 65
        else {
            const extra = ((e.genericName || "") + " " + (e.keywords || []).join(" ") + " " + (e.comment || "") + " " + (e.id || "")).toLowerCase()
            if (extra.indexOf(q) >= 0) s = 40
            else {
                const words = n.split(/[\s\-_.]+/).filter(w => w)
                const initials = words.map(w => w[0]).join("")
                if (q.length >= 2 && initials.startsWith(q)) s = 50          // "vsc" -> Visual Studio Code
                else {                                                     // "ffx" -> Firefox (first word only)
                    let i = 0
                    for (const ch of (words[0] || "")) if (ch === q[i]) i++
                    if (i === q.length && q.length >= 2) s = 20
                }
            }
        }
        return s ? s + Math.min(25, Math.log2(1 + (counts[e.id] || 0)) * 6) : 0
    }
    function appIcon(e) { return e.icon ? Quickshell.iconPath(e.icon, true) : "" }
    function compute() {
        const q = query.trim().toLowerCase()
        const out = []
        const apps = DesktopEntries.applications.values.filter(e => !e.noDisplay)
        if (calc) out.push({ kind: "Calculator", title: "= " + calc, sub: "Enter to copy", glyph: 0xf00ec,
                             act: () => sh("printf %s " + JSON.stringify(calc.replace(/^.*=\s*/, "").replace(/^≈\s*/, "")) + " | wl-copy") })
        if (q.startsWith(">")) {
            const cmd = query.trim().slice(1).trim()
            if (cmd) out.push({ kind: "Command", title: "Run: " + cmd, sub: "in a terminal", glyph: 0xf018d,
                                act: () => Quickshell.execDetached(["kitty", "--hold", "sh", "-c", cmd]) })
        } else if (!q) {
            // empty: most used apps first, then A–Z
            apps.slice().sort((a, b) => (counts[b.id] || 0) - (counts[a.id] || 0) || a.name.localeCompare(b.name))
                .slice(0, 8).forEach(e => out.push({ kind: (counts[e.id] ? "Frequent" : "Applications"), title: e.name, sub: e.genericName || e.comment || "",
                                                     icon: appIcon(e), glyph: 0xf003b, act: () => { used(e.id); e.execute() } }))
        } else {
            apps.map(e => ({ e: e, s: score(q, e) })).filter(x => x.s > 0).sort((a, b) => b.s - a.s).slice(0, 8)
                .forEach(x => out.push({ kind: "Applications", title: x.e.name, sub: x.e.genericName || x.e.comment || "",
                                         icon: appIcon(x.e), glyph: 0xf003b, act: () => { used(x.e.id); x.e.execute() } }))
            actions.filter(a => (a.name + " " + a.keys).toLowerCase().indexOf(q) >= 0).slice(0, 3)
                .forEach(a => out.push({ kind: "System", title: a.name, sub: "", glyph: a.icon, act: a.cmd }))
            files.forEach(f => out.push({ kind: "Files", title: f.replace(/\/$/, "").split("/").pop(), sub: f.replace(home, "~"),
                                          glyph: f.endsWith("/") ? 0xf024b : 0xf0214, act: () => Quickshell.execDetached(["xdg-open", f]) }))
            out.push({ kind: "Web", title: "Search the web for “" + query.trim() + "”", sub: "google.com", glyph: 0xf059f,
                       act: () => Quickshell.execDetached(["xdg-open", "https://www.google.com/search?q=" + encodeURIComponent(query.trim())]) })
        }
        results = out
        if (sel >= out.length) sel = Math.max(0, out.length - 1)
    }
    function launch(i) { const r = results[i]; if (!r) return; close(); r.act() }

    component LText: Text {
        color: Punk.text; font.family: Punk.mono; font.pixelSize: 13
        elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
    }

    PanelWindow {
        id: win
        visible: lx.open || card.opacity > 0.01
        screen: lx.shell.islandScreen
        anchors.top: true
        margins.top: Math.round((screen ? screen.height : 1080) * 0.16)
        implicitWidth: 680
        implicitHeight: 560                     // fixed: only the card animates (no surface resizes)
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "spotlight"
        WlrLayershell.keyboardFocus: lx.open ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
        mask: Region { item: card }
        HyprlandFocusGrab { windows: [win]; active: lx.open; onCleared: lx.close() }

        Rectangle {
            id: card
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            height: 92 + (lx.results.length ? Math.min(list.contentHeight, 440) + 14 : 0)
            Behavior on height { NumberAnimation { duration: 220; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
            color: "transparent"; radius: 0
            clip: true
            opacity: lx.open ? 1 : 0
            scale: lx.open ? 1 : 0.92
            rotation: lx.open ? 0 : -1.5
            Behavior on opacity { NumberAnimation { duration: 140 } }
            Behavior on scale { NumberAnimation { duration: 280; easing.type: Easing.OutBack; easing.overshoot: 1.8 } }
            Behavior on rotation { NumberAnimation { duration: 280; easing.type: Easing.OutBack } }

            // torn ink panel with a crimson misprint (large step: the edge barely "boils" while it grows)
            PunkPanel { anchors.fill: parent; z: -1; fill: Punk.alpha(Punk.bg, 0.97); misprint: Punk.crimson
                        offset: Qt.point(7, 7); strokeWidth: 3.5; seed: 23; jag: 2.6; step: 34; dotsOpacity: 0.32 }

            // ---- search strip: crimson poster band
            Rectangle {
                id: strip
                x: 16; y: 16; width: parent.width - 40; height: 58
                color: Punk.crimson; border.width: 3; border.color: Punk.ink
                Rectangle { z: -1; x: 5; y: 5; width: parent.width; height: parent.height; color: Punk.ink }
                Text { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                       text: input.text ? "" : "SEARCH!"; font.family: Punk.display; font.pixelSize: 24; color: Punk.ink }
            }
            LText { x: 32; y: 16; height: 58; text: lx.g(0xf140b); font.pixelSize: 24; color: Punk.yellow }
            TextInput {
                id: input
                x: 68; y: 16; width: parent.width - 180; height: 58
                verticalAlignment: TextInput.AlignVCenter
                color: Punk.text; font.family: Punk.mono; font.pixelSize: 19; font.bold: true
                selectionColor: Punk.ink; selectedTextColor: Punk.yellow
                focus: lx.open
                text: lx.query
                onTextChanged: lx.query = text
                onVisibleChanged: if (visible) forceActiveFocus()
                Connections { target: lx; function onOpenChanged() { if (lx.open) { input.text = ""; input.forceActiveFocus() } } }
                LText { anchors.fill: parent; visible: !parent.text; text: "type it. loud."; color: Punk.alpha(Punk.text, 0.62); font.pixelSize: 19 }
                Keys.onEscapePressed: lx.close()
                Keys.onReturnPressed: lx.launch(lx.sel)
                Keys.onEnterPressed: lx.launch(lx.sel)
                Keys.onDownPressed: { lx.sel = Math.min(lx.results.length - 1, lx.sel + 1); list.positionViewAtIndex(lx.sel, ListView.Contain) }
                Keys.onUpPressed: { lx.sel = Math.max(0, lx.sel - 1); list.positionViewAtIndex(lx.sel, ListView.Contain) }
                Keys.onTabPressed: { lx.sel = (lx.sel + 1) % Math.max(1, lx.results.length); list.positionViewAtIndex(lx.sel, ListView.Contain) }
            }


            // ---- results
            ListView {
                id: list
                x: 16; y: 90; width: parent.width - 40; height: Math.min(contentHeight, 440)
                model: lx.results
                clip: true; boundsBehavior: Flickable.StopAtBounds
                spacing: 3
                delegate: Item {
                    id: row
                    required property var modelData
                    required property int index
                    readonly property bool header: index === 0 || lx.results[index - 1].kind !== modelData.kind
                    width: list.width; height: (header ? 26 : 0) + 50
                    // section header: a little stamped tag
                    Rectangle { visible: row.header; x: 4; y: 4; width: kt.implicitWidth + 14; height: 19; rotation: -2
                                color: Punk.yellow; border.width: 2; border.color: Punk.ink
                                Text { id: kt; anchors.centerIn: parent; text: (row.modelData.kind || "").toUpperCase(); font.family: Punk.poster
                                       font.pixelSize: 14; font.letterSpacing: 1; color: Punk.ink } }
                    readonly property bool on: lx.sel === row.index
                    Rectangle {      // blue misprint behind the selected row
                        visible: row.on; x: 5; y: (row.header ? 26 : 0) + 5; width: parent.width - 6; height: 48; color: Punk.blue
                    }
                    Rectangle {
                        y: row.header ? 26 : 0; width: parent.width - 6; height: 48; radius: 0
                        color: row.on ? Punk.crimson : (rm.containsMouse ? Punk.surface : "transparent")
                        border.width: row.on ? 2 : 0; border.color: Punk.ink
                        Rectangle { visible: !row.on && rm.containsMouse; width: 3; height: parent.height; color: Punk.blue }
                        Item {
                            id: ic; x: 10; anchors.verticalCenter: parent.verticalCenter; width: 32; height: 32
                            Image { id: img; anchors.fill: parent; source: row.modelData.icon || ""; sourceSize.width: 64; sourceSize.height: 64
                                    asynchronous: true; visible: status === Image.Ready }
                            LText { anchors.centerIn: parent; visible: !img.visible; text: lx.g(row.modelData.glyph || 0xf003b); font.pixelSize: 20
                                    color: row.on ? Punk.ink : Punk.subtext }
                        }
                        Column {
                            anchors.left: ic.right; anchors.leftMargin: 12; anchors.right: parent.right; anchors.rightMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            LText { width: parent.width; text: row.modelData.title; font.family: Punk.poster; font.pixelSize: 20; font.letterSpacing: 0.5
                                    color: Punk.text }
                            LText { width: parent.width; visible: text !== ""; text: row.modelData.sub || ""; font.pixelSize: 11
                                    color: row.on ? Punk.text : Punk.subtext }
                        }
                        MouseArea { id: rm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    // only real pointer movement selects (not rows sliding under a resting pointer)
                                    property point last: Qt.point(-1, -1)
                                    onPositionChanged: m => { const p = mapToItem(null, m.x, m.y)
                                                              if (last.x >= 0 && (Math.abs(p.x - last.x) > 1 || Math.abs(p.y - last.y) > 1)) lx.sel = row.index
                                                              last = p }
                                    onExited: last = Qt.point(-1, -1)
                                    onClicked: lx.launch(row.index) }
                    }
                }
            }
        }
    }
}
