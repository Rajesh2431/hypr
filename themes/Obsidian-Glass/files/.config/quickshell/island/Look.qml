// Desktop-style "look" switches for the shared island / Control Center / launcher / power menu code.
// Obsidian Glass: flat, rounded, no tilts or misprints, sentence-case labels.
pragma Singleton
import QtQuick
import Quickshell

Singleton {
    readonly property bool comic: false
    readonly property real tilt: 0
    readonly property int r: 8
    readonly property real fs: 0.8
    // colour helpers (glass: tinted translucent "on" fills with light text, 1px soft outlines)
    readonly property color onFill: Qt.rgba(0.47, 0.73, 0.91, 0.24)
    readonly property color onText: Punk.text
    readonly property color meter: Qt.rgba(0.47, 0.73, 0.91, 0.55)
    readonly property color edge: "#2C323E"
    readonly property int edgeW: 1
    function caps(s) { return comic ? String(s).toUpperCase() : String(s) }
}
