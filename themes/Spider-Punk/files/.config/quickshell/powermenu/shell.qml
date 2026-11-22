// Power menu for KoolDots — replaces wlogout.  Spider-Punk edition.
// Launch/toggle: ~/.config/hypr/scripts/Wlogout.sh
// Keys: ←/→ (h/l, Tab) move · Enter/Space select · Esc close
//       L lock · S suspend · E logout · R reboot · P shutdown
// Logout / Reboot / Shutdown ask for confirmation (Enter again confirms).
// Look: torn comic panels with ink misprints (PunkPanel / Punk.qml are symlinks to ../island).
// Previous (Dynamic Island) version: ~/.cache/island/powermenu-shell.qml.bak-punk
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root

    // ---------- actions (each panel has its own ink) ----------
    readonly property var actions: [
        { key: "l", label: "Lock",      shout: "LOCK IT",    icon: 0xf033e, ink: Punk.blue,    cmd: ["bash", "-c", "$HOME/.config/hypr/scripts/LockScreen.sh"] },
        { key: "s", label: "Suspend",   shout: "NAP TIME",   icon: 0xf04b2, ink: Punk.purple,  cmd: ["systemctl", "suspend"] },
        { key: "e", label: "Log Out",   shout: "BAIL",       icon: 0xf0343, ink: Punk.orange,  cmd: ["bash", "-c", "$HOME/.config/hypr/scripts/Logout.sh"], confirm: "Log out of your session?" },
        { key: "r", label: "Reboot",    shout: "AGAIN!",     icon: 0xf0709, ink: Punk.magenta, cmd: ["systemctl", "reboot"],   confirm: "Restart your computer?" },
        { key: "p", label: "Shut Down", shout: "LIGHTS OUT", icon: 0xf0425, ink: Punk.crimson, cmd: ["systemctl", "poweroff"], confirm: "Power off your computer?" }
    ]
    property int sel: 0
    property var pending: null
    property bool closing: false

    function run(a) {
        closing = true;
        Quickshell.execDetached(a.cmd);
        quitTimer.start();
    }
    function choose(i) {
        const a = actions[i];
        sel = i;
        if (a.confirm && pending !== a) { pending = a; return; }
        run(a);
    }
    function close() { closing = true; quitTimer.start(); }
    Timer { id: quitTimer; interval: 180; onTriggered: Qt.quit() }

    // ---------- uptime ----------
    property string uptime: ""
    Process {
        running: true
        command: ["uptime", "-p"]
        stdout: StdioCollector { onStreamFinished: root.uptime = text.trim().replace(/^up /, "") }
    }
    property string userName: Quickshell.env("USER") || ""

    // ---------- one overlay per monitor; keyboard on the focused one ----------
    Variants {
        model: Quickshell.screens
        PanelWindow {
            id: win
            required property var modelData
            screen: modelData
            anchors { top: true; bottom: true; left: true; right: true }
            exclusionMode: ExclusionMode.Ignore
            color: "transparent"
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.namespace: "logout_dialog"
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

            // backdrop: ink wash + a big halftone screen over the (blurred) desktop
            Item {
                id: dim
                anchors.fill: parent
                opacity: root.closing ? 0 : 1
                Behavior on opacity { NumberAnimation { duration: 160 } }
                Rectangle { anchors.fill: parent; color: Punk.alpha(Punk.bg, 0.72) }
                Image { anchors.fill: parent; fillMode: Image.Tile; source: Punk.assets + "dots-crimson.svg"
                        sourceSize: Qt.size(12, 12); opacity: 0.22 }
                MouseArea { anchors.fill: parent; onClicked: root.pending ? root.pending = null : root.close() }
            }

            Item {
                id: content
                anchors.fill: parent
                focus: true
                opacity: root.closing ? 0 : 1
                scale: root.closing ? 0.96 : 1
                Component.onCompleted: { opacity = 0; scale = 0.9; appear.start(); }
                ParallelAnimation {
                    id: appear
                    NumberAnimation { target: content; property: "opacity"; to: 1; duration: 200; easing.type: Easing.OutCubic }
                    NumberAnimation { target: content; property: "scale"; to: 1; duration: 380; easing.type: Easing.OutBack; easing.overshoot: 1.8 }
                }
                Behavior on opacity { enabled: root.closing; NumberAnimation { duration: 160 } }
                Behavior on scale { enabled: root.closing; NumberAnimation { duration: 160 } }

                Keys.onPressed: e => {
                    const n = root.actions.length;
                    if (e.key === Qt.Key_Escape) { root.pending ? root.pending = null : root.close(); }
                    else if (e.key === Qt.Key_Left || e.key === Qt.Key_H || e.key === Qt.Key_Backtab) { root.pending = null; root.sel = (root.sel + n - 1) % n; }
                    else if (e.key === Qt.Key_Right || e.key === Qt.Key_Tab) { root.pending = null; root.sel = (root.sel + 1) % n; }
                    else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { root.choose(root.sel); }
                    else {
                        const k = e.text.toLowerCase();
                        const i = root.actions.findIndex(a => a.key === k);
                        if (i >= 0) root.choose(i); else return;
                    }
                    e.accepted = true;
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 46

                    // ---- poster: tilted crimson clock panel + cream date tag
                    Item {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 560; height: 210
                        PunkPanel {
                            anchors.fill: parent; rotation: -2.5
                            fill: Punk.crimson; misprint: Punk.blue; offset: Qt.point(12, 12)
                            strokeWidth: 5; seed: 17; jag: 3.2; step: 26
                            dotsColor: Punk.blue; dotsOpacity: 0.35
                        }
                        Text {
                            id: clock
                            anchors.centerIn: parent; anchors.verticalCenterOffset: -14; anchors.horizontalCenterOffset: -6
                            rotation: -2.5
                            color: Punk.text
                            font.family: Punk.display; font.pixelSize: 124; font.letterSpacing: 3
                            style: Text.Raised; styleColor: Punk.ink
                            text: Qt.formatTime(new Date(), "hh:mm")
                            Timer { interval: 1000; running: true; repeat: true; onTriggered: clock.text = Qt.formatTime(new Date(), "hh:mm") }
                        }
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: -14
                            width: dateT.implicitWidth + 30; height: 40; color: Punk.text; rotation: 2
                            border.width: 3; border.color: Punk.ink
                            Rectangle { z: -1; x: 5; y: 5; width: parent.width; height: parent.height; color: Punk.ink }
                            Text {
                                id: dateT; anchors.centerIn: parent
                                color: Punk.ink; font.family: Punk.poster; font.pixelSize: 26; font.letterSpacing: 2
                                text: Qt.formatDate(new Date(), "dddd d MMMM").toUpperCase() + (root.uptime ? "  ·  UP " + root.uptime.toUpperCase() : "")
                            }
                        }
                    }

                    // ---- the buttons: one torn comic panel each
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 26
                        Repeater {
                            model: root.actions
                            Item {
                                id: btn
                                required property var modelData
                                required property int index
                                readonly property bool active: root.sel === index
                                readonly property bool armed: root.pending === modelData
                                readonly property color ink: armed ? Punk.yellow : modelData.ink
                                width: 136; height: 176

                                Item {
                                    id: tile
                                    width: 136; height: 136
                                    // the selected panel lifts and tilts; a press stamps it down
                                    rotation: btn.armed ? -4 : btn.active ? (btn.index % 2 ? 3 : -3) : 0
                                    scale: ma.pressed ? 0.9 : btn.active ? 1.08 : 1
                                    Behavior on rotation { NumberAnimation { duration: 260; easing.type: Easing.OutBack; easing.overshoot: 2 } }
                                    Behavior on scale { NumberAnimation { duration: 240; easing.type: Easing.OutBack; easing.overshoot: 1.6 } }

                                    PunkPanel {
                                        anchors.fill: parent
                                        fill: btn.active || btn.armed ? btn.ink : Punk.bg2
                                        misprint: btn.active || btn.armed ? Punk.ink : btn.modelData.ink
                                        misprintOpacity: btn.active || btn.armed ? 1 : 0.7
                                        offset: btn.active ? Qt.point(8, 8) : Qt.point(5, 5)
                                        strokeWidth: 3.5; seed: 30 + btn.index * 7; jag: 2.4; step: 16
                                        dotsColor: btn.active ? Punk.blue : Punk.crimson; dotsOpacity: btn.active ? 0.3 : 0.18
                                    }
                                    Text {
                                        anchors.centerIn: parent
                                        anchors.verticalCenterOffset: -10; anchors.horizontalCenterOffset: -3
                                        text: String.fromCodePoint(btn.modelData.icon)
                                        font.family: Punk.mono; font.pixelSize: 50
                                        color: btn.active || btn.armed ? Punk.ink : btn.modelData.ink
                                        Behavior on color { ColorAnimation { duration: 140 } }
                                    }
                                    // key hint as a little stamped tag
                                    Rectangle {
                                        anchors.bottom: parent.bottom; anchors.bottomMargin: 16
                                        anchors.horizontalCenter: parent.horizontalCenter; anchors.horizontalCenterOffset: -3
                                        width: 24; height: 22; rotation: -6
                                        color: btn.active || btn.armed ? Punk.ink : Punk.surface
                                        border.width: 2; border.color: Punk.ink
                                        Text { anchors.centerIn: parent; text: btn.modelData.key.toUpperCase()
                                               font.family: Punk.display; font.pixelSize: 15
                                               color: btn.active || btn.armed ? btn.ink : Punk.subtext }
                                    }
                                    MouseArea {
                                        id: ma
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onEntered: if (root.sel !== btn.index) { root.pending = null; root.sel = btn.index; }
                                        onClicked: root.choose(btn.index)
                                    }
                                }
                                Text {
                                    anchors.bottom: parent.bottom
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: btn.armed ? "SURE?!" : btn.active ? btn.modelData.shout : btn.modelData.label.toUpperCase()
                                    color: btn.armed ? Punk.yellow : btn.active ? Punk.text : Punk.subtext
                                    font.family: btn.active || btn.armed ? Punk.display : Punk.poster
                                    font.pixelSize: btn.active || btn.armed ? 24 : 20; font.letterSpacing: 1.5
                                    style: btn.active || btn.armed ? Text.Raised : Text.Normal; styleColor: Punk.ink
                                }
                            }
                        }
                    }

                    // ---- hint / confirmation line: a paper strip (yellow when armed)
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: hint.implicitWidth + 34; height: 34
                        color: root.pending ? Punk.yellow : Punk.alpha(Punk.bg2, 0.95)
                        border.width: 2; border.color: Punk.ink
                        rotation: root.pending ? -1 : 0
                        Behavior on rotation { NumberAnimation { duration: 200; easing.type: Easing.OutBack } }
                        Rectangle { z: -1; x: 4; y: 4; width: parent.width; height: parent.height; color: root.pending ? Punk.crimson : Punk.ink }
                        Text {
                            id: hint
                            anchors.centerIn: parent
                            color: root.pending ? Punk.ink : Punk.subtext
                            font.family: Punk.mono; font.pixelSize: 13; font.bold: true
                            text: root.pending
                                  ? root.pending.confirm + "   Enter / click again to confirm  ·  Esc to cancel"
                                  : (root.userName ? "@" + root.userName + "   ·   " : "") + "←/→ move  ·  Enter select  ·  Esc close"
                        }
                    }
                }
            }
        }
    }
}
