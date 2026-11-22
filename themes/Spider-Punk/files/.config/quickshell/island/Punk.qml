// Spider-Punk design tokens for the island, Control Center and notifications.
// Mirrors ~/.config/hypr/waybar/style/punk/tokens.css; change both together.
pragma Singleton
import QtQuick
import Quickshell

Singleton {
    readonly property color bg:      "#0B090D"
    readonly property color bg2:     "#151117"
    readonly property color surface: "#1E151C"
    readonly property color surface2:"#2A1C26"
    readonly property color ink:     "#050306"
    readonly property color text:    "#F5F0E8"
    readonly property color subtext: "#AAA2B2"
    readonly property color faint:   "#6E6676"
    readonly property color crimson: "#FF1744"
    readonly property color blue:    "#00B8FF"
    readonly property color purple:  "#8B35FF"
    readonly property color magenta: "#FF2E93"
    readonly property color yellow:  "#FFD43B"
    readonly property color orange:  "#FF6B24"
    readonly property string display: "Bangers"        // clocks, big headings
    readonly property string poster:  "Bebas Neue"     // labels, app names
    readonly property string mono:    "JetBrainsMono Nerd Font"
    readonly property string assets:  "file://" + Quickshell.env("HOME") + "/.config/hypr/waybar/assets/punk/"
    // per-app accent: always one of the print inks (never random hues)
    readonly property var inks: [crimson, blue, magenta, yellow, orange, purple]
    function alpha(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }
}
