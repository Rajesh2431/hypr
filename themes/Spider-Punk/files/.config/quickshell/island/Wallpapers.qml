// Wallpaper picker (Super+W):  qs ipc -c island call wallpaper toggle
// Grid of cached thumbnails (wallthumbs.py) from ~/Pictures/wallpapers, search,
// All / Images / Videos, Shuffle. Applying goes through KoolDots'
// WallpaperSelect.sh --apply (awww + wallust colours + lock-screen copy + refresh).
//   arrows move · Enter applies · type to search · Esc closes
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Widgets

Scope {
    id: wp
    required property var shell
    property bool open: false
    property var all: []
    property string current: ""
    property string query: ""
    property string filter: "all"          // all | images | videos
    readonly property var shown: {
        const q = query.trim().toLowerCase()
        return all.filter(w => (filter === "all" || (filter === "videos") === w.video)
                               && (!q || w.name.toLowerCase().indexOf(q) >= 0))
    }
    function g(cp) { return String.fromCodePoint(cp) }
    function toggle() { if (open) open = false; else { query = ""; filter = "all"; all = []; open = true; lister.running = true } }

    IpcHandler {
        target: "wallpaper"
        function toggle(): void { wp.toggle() }
        function hide(): void { wp.open = false }
        function search(q: string): void { if (!wp.open) wp.toggle(); input.text = q }
    }

    Process {
        id: lister
        command: ["python3", Quickshell.env("HOME") + "/.config/quickshell/island/wallthumbs.py"]
        stdout: SplitParser {
            onRead: data => {
                let d; try { d = JSON.parse(data) } catch (e) { return }
                if (d.done) { relist.start(); return }                // thumbnails finished: reload them
                const first = wp.all.length === 0
                wp.current = d.current || ""; wp.all = d.items || []
                if (first) selectCurrent.restart()     // after the grid has rebuilt its delegates
            }
        }
    }
    Timer { id: relist; interval: 300; onTriggered: if (wp.open) lister.running = true }
    Timer { id: selectCurrent; interval: 60; onTriggered: {
        const i = wp.shown.findIndex(w => w.path === wp.current)
        grid.currentIndex = Math.max(0, i); grid.positionViewAtIndex(grid.currentIndex, GridView.Center) } }

    function apply(w) {
        if (!w) return
        open = false
        shell.pop("wall", { thumb: w.thumb, name: w.name }, 2600)
        Quickshell.execDetached([Quickshell.env("HOME") + "/.config/hypr/scripts/WallpaperSelect.sh", "--apply", w.path])
    }
    function shuffle() { const l = shown.filter(w => w.path !== current); if (l.length) apply(l[Math.floor(Math.random() * l.length)]) }

    component WText: Text {
        color: Punk.text; font.family: Punk.mono; font.pixelSize: 13
        elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
    }
    component Chip: Rectangle {
        id: chip
        property string text
        property bool on: false
        signal hit()
        implicitWidth: ct.implicitWidth + 24; height: 30; radius: 0
        color: on ? Punk.blue : (cm.containsMouse ? Punk.surface2 : Punk.surface)
        border.width: 2; border.color: Punk.ink
        Rectangle { z: -1; x: 3; y: 3; width: parent.width; height: parent.height; color: Punk.ink }
        WText { id: ct; anchors.centerIn: parent; text: chip.text.toUpperCase(); font.family: Punk.poster; font.pixelSize: 17; font.letterSpacing: 1
                color: chip.on ? Punk.ink : Punk.text }
        MouseArea { id: cm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: chip.hit() }
    }

    PanelWindow {
        id: win
        visible: wp.open || card.opacity > 0.01
        screen: wp.shell.islandScreen
        implicitWidth: 1060
        implicitHeight: 660
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "wallpaper-picker"
        WlrLayershell.keyboardFocus: wp.open ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
        mask: Region { item: card }
        HyprlandFocusGrab { windows: [win]; active: wp.open; onCleared: wp.open = false }

        Rectangle {
            id: card
            anchors.fill: parent
            color: "transparent"; radius: 0
            clip: true
            opacity: wp.open ? 1 : 0
            scale: wp.open ? 1 : 0.92
            Behavior on opacity { NumberAnimation { duration: 140 } }
            Behavior on scale { NumberAnimation { duration: 300; easing.type: Easing.OutBack; easing.overshoot: 1.6 } }
            PunkPanel { anchors.fill: parent; z: -1; fill: Punk.alpha(Punk.bg, 0.97); misprint: Punk.blue
                        offset: Qt.point(9, 9); strokeWidth: 4; seed: 47; jag: 3; step: 30; dotsColor: Punk.crimson; dotsOpacity: 0.3 }

            // ---- header: search + filters + shuffle
            Rectangle {
                id: sbox
                x: 20; y: 20; width: 420; height: 42; radius: 0; color: Punk.crimson
                border.width: 3; border.color: Punk.ink
                Rectangle { z: -1; x: 4; y: 4; width: parent.width; height: parent.height; color: Punk.ink }
                WText { x: 14; height: parent.height; text: wp.g(0xf140b); font.pixelSize: 19; color: Punk.yellow }
                TextInput {
                    id: input
                    x: 44; width: parent.width - 60; height: parent.height
                    verticalAlignment: TextInput.AlignVCenter
                    color: Punk.text; font.family: Punk.mono; font.pixelSize: 15; font.bold: true
                    selectionColor: Punk.ink; selectedTextColor: Punk.yellow
                    focus: wp.open
                    onTextChanged: { wp.query = text; grid.currentIndex = 0 }
                    Connections { target: wp; function onOpenChanged() { if (wp.open) { input.text = ""; input.forceActiveFocus() } } }
                    WText { anchors.fill: parent; visible: !parent.text; text: "pick your poster"; color: Punk.alpha(Punk.text, 0.62); font.pixelSize: 15 }
                    Keys.onEscapePressed: wp.open = false
                    Keys.onReturnPressed: wp.apply(wp.shown[grid.currentIndex])
                    Keys.onEnterPressed: wp.apply(wp.shown[grid.currentIndex])
                    Keys.onRightPressed: grid.moveCurrentIndexRight()
                    Keys.onLeftPressed: grid.moveCurrentIndexLeft()
                    Keys.onDownPressed: grid.moveCurrentIndexDown()
                    Keys.onUpPressed: grid.moveCurrentIndexUp()
                }
            }
            Row {
                anchors.verticalCenter: sbox.verticalCenter; x: sbox.x + sbox.width + 14; spacing: 6
                Chip { text: "All"; on: wp.filter === "all"; onHit: wp.filter = "all" }
                Chip { text: "Images"; on: wp.filter === "images"; onHit: wp.filter = "images" }
                Chip { text: "Videos"; on: wp.filter === "videos"; onHit: wp.filter = "videos"; visible: wp.all.some(w => w.video) }
            }
            Row {
                anchors.verticalCenter: sbox.verticalCenter; anchors.right: parent.right; anchors.rightMargin: 18; spacing: 10
                WText { anchors.verticalCenter: parent.verticalCenter; text: wp.shown.length + " POSTERS"; color: Punk.subtext; font.family: Punk.poster; font.pixelSize: 17; font.letterSpacing: 1 }
                Chip { text: wp.g(0xf049d) + "  Shuffle"; onHit: wp.shuffle() }
            }

            // ---- grid
            GridView {
                id: grid
                x: 16; y: 78; width: parent.width - 40; height: parent.height - 100
                cellWidth: width / 4; cellHeight: cellWidth * 9 / 16 + 34
                model: wp.shown
                clip: true; boundsBehavior: Flickable.StopAtBounds
                highlightMoveDuration: 120
                onCurrentIndexChanged: positionViewAtIndex(currentIndex, GridView.Contain)
                delegate: Item {
                    id: cell
                    required property var modelData
                    required property int index
                    readonly property bool sel: GridView.isCurrentItem
                    readonly property bool cur: modelData.path === wp.current
                    width: grid.cellWidth; height: grid.cellHeight
                    // a little jitter per cell so the grid looks pasted up by hand; the selected one tilts more
                    readonly property real tilt: ((index * 37) % 7 - 3) * 0.25
                    // misprint behind the frame (crimson; blue when selected)
                    Rectangle {
                        x: frame.x + (cell.sel ? 7 : 4); y: frame.y + (cell.sel ? 7 : 4); width: frame.width; height: frame.height
                        color: cell.sel ? Punk.blue : Punk.alpha(Punk.crimson, 0.55); rotation: frame.rotation
                        Behavior on x { NumberAnimation { duration: 160 } } Behavior on y { NumberAnimation { duration: 160 } }
                    }
                    ClippingRectangle {
                        id: frame
                        x: 8; y: 8; width: parent.width - 20; height: width * 9 / 16; radius: 0
                        color: Punk.bg2
                        border.width: 3; border.color: cell.sel ? Punk.crimson : Punk.ink
                        rotation: cell.sel ? (cell.index % 2 ? 1.6 : -1.6) : cell.tilt
                        scale: cell.sel ? 1.04 : 1
                        z: cell.sel ? 2 : 0
                        Behavior on rotation { NumberAnimation { duration: 240; easing.type: Easing.OutBack; easing.overshoot: 2 } }
                        Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutBack } }
                        Image {
                            anchors.fill: parent; fillMode: Image.PreserveAspectCrop; asynchronous: true; cache: true
                            sourceSize.width: 480
                            source: cell.modelData.thumb ? "file://" + cell.modelData.thumb
                                    : (cell.modelData.video ? "" : "file://" + cell.modelData.path)
                            opacity: status === Image.Ready ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: 180 } }
                        }
                        // badges
                        Rectangle { visible: cell.cur; x: 8; y: 8; height: 24; width: curT.implicitWidth + 14; radius: 0; rotation: -4
                                    color: Punk.yellow; border.width: 2; border.color: Punk.ink
                                    Text { id: curT; anchors.centerIn: parent; text: "NOW!"; font.family: Punk.display; font.pixelSize: 16; color: Punk.ink } }
                        Rectangle { visible: cell.modelData.video; anchors.right: parent.right; anchors.rightMargin: 8; y: 8
                                    width: 28; height: 22; radius: 0; color: Punk.crimson; border.width: 2; border.color: Punk.ink
                                    WText { anchors.centerIn: parent; text: wp.g(0xf040a); font.pixelSize: 12 } }
                    }

                    WText {
                        x: 10; y: frame.y + frame.height + 6; width: parent.width - 20; height: 20
                        horizontalAlignment: Text.AlignHCenter; font.family: Punk.poster; font.pixelSize: 16; font.letterSpacing: 0.5
                        text: cell.modelData.name.toUpperCase(); color: cell.sel ? Punk.yellow : Punk.subtext
                    }
                    MouseArea {
                        anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        property point last: Qt.point(-1, -1)
                        onPositionChanged: m => { const p = mapToItem(null, m.x, m.y)
                                                  if (last.x >= 0 && (Math.abs(p.x - last.x) > 1 || Math.abs(p.y - last.y) > 1)) grid.currentIndex = cell.index
                                                  last = p }
                        onExited: last = Qt.point(-1, -1)
                        onClicked: wp.apply(cell.modelData)
                    }
                }
            }
            WText { anchors.centerIn: grid; visible: wp.shown.length === 0 && wp.all.length > 0; text: "NOTHING MATCHES “" + wp.query + "”"; font.family: Punk.poster; font.pixelSize: 20; color: Punk.subtext }
        }
    }
}
