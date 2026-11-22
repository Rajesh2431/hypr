// Obsidian Glass panel: rounded translucent charcoal with a 1px soft border and a faint top highlight.
// Same properties as the Spider-Punk comic panel so the shared QML can use either; the comic ones are ignored.
import QtQuick

Item {
    id: pp
    property color fill: Punk.bg2
    property color misprint: Punk.crimson
    property real misprintOpacity: 0.9
    property point offset: Qt.point(4, 4)
    property color stroke: Punk.ink
    property real strokeWidth: 2.5
    property int seed: 1
    property real jag: 1.8
    property real step: 18
    property bool dots: true
    property color dotsColor: Punk.crimson
    property real dotsOpacity: 0.5
    property bool dotsLeft: false
    property real radius: 16

    Rectangle {
        anchors.fill: parent
        radius: pp.radius
        color: Qt.rgba(pp.fill.r, pp.fill.g, pp.fill.b, Math.min(pp.fill.a, 0.86))
        border.width: 1
        border.color: "#394251"
        antialiasing: true
    }
    Rectangle {   // top inner highlight
        x: pp.radius; y: 1; width: parent.width - 2 * pp.radius; height: 1
        color: Qt.rgba(1, 1, 1, 0.06)
    }
}
