// Desktop-style "look" switches for the shared island / Control Center / launcher / power menu code.
// This file is per-style (managed by ~/.config/hypr/UserScripts/Styles.sh, see themes/manifest.txt):
//   Spider-Punk  : comic = true  (tilts, misprints, square cuts, ALL-CAPS poster type)
//   Obsidian-Glass: comic = false (flat, rounded glass panels)
// Colours and fonts live in Punk.qml, the panel shape in PunkPanel.qml (both per-style too).
pragma Singleton
import QtQuick
import Quickshell

Singleton {
    readonly property bool comic: true
    readonly property real tilt: 1          // multiplies every decorative rotation
    readonly property int r: 0              // corner radius for cards, chips, tiles
    readonly property real fs: 1            // font scale for the display/poster faces
    // colour helpers (comic: solid crimson "on" fills with ink text, 2px ink outlines)
    readonly property color onFill: Punk.crimson        // fill of an "on" tile / selected row / pressed chip
    readonly property color onText: Punk.ink            // text + icons drawn on onFill
    readonly property color meter: Punk.crimson         // slider / progress fill
    readonly property color edge: Punk.ink              // outline colour
    readonly property int edgeW: 2                      // outline width
    function caps(s) { return comic ? String(s).toUpperCase() : String(s) }
}
