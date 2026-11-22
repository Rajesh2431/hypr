// Obsidian Glass design tokens for the island, Control Center, launcher, notifications and power menu.
// Same property names as the Spider-Punk version (the shared QML reads these); per-style file.
pragma Singleton
import QtQuick
import Quickshell

Singleton {
    readonly property color bg:      "#EB101116"   // glass: slightly translucent (layers are blurred)
    readonly property color bg2:     "#15171E"
    readonly property color surface: "#191B23"
    readonly property color surface2:"#222630"
    readonly property color ink:     "#0C0D11"     // outlines + text on accent fills
    readonly property color text:    "#E6E8F0"
    readonly property color subtext: "#9CA4B5"
    readonly property color faint:   "#687184"
    readonly property color crimson: "#78B9E7"     // primary accent (blue)
    readonly property color blue:    "#7ED6DE"     // secondary accent (cyan)
    readonly property color purple:  "#A6A1E3"
    readonly property color magenta: "#B79CE0"
    readonly property color yellow:  "#E5C07B"
    readonly property color orange:  "#E0A07B"
    readonly property color border:  "#394251"
    readonly property string display: "Noto Sans"
    readonly property string poster:  "Noto Sans"
    readonly property string mono:    "JetBrainsMono Nerd Font"
    readonly property string assets:  "file://" + Quickshell.env("HOME") + "/.config/hypr/waybar/assets/glass/"
    readonly property var inks: [crimson, blue, purple, magenta, yellow, orange]
    function alpha(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }
}
