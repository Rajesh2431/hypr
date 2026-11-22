pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import "functions"

Singleton {
    id: root
    property QtObject m3colors
    property QtObject animation
    property QtObject animationCurves
    property QtObject colors
    property QtObject rounding
    property QtObject font
    property QtObject sizes

    // Obsidian Glass palette (tokens: ~/.config/hypr/waybar/style/punk/tokens.css). Original: Appearance.qml.bak-punk
    m3colors: QtObject {
        property bool darkmode: true
        property color m3primary: "#78B9E7"
        property color m3onPrimary: "#0C0D11"
        property color m3primaryContainer: "#1F3346"
        property color m3onPrimaryContainer: "#E6E8F0"
        property color m3secondary: "#78B9E7"
        property color m3onSecondary: "#0C0D11"
        property color m3secondaryContainer: "#222630"
        property color m3onSecondaryContainer: "#E6E8F0"
        property color m3background: "#101116"
        property color m3onBackground: "#E6E8F0"
        property color m3surface: "#101116"
        property color m3surfaceContainerLow: "#15171E"
        property color m3surfaceContainer: "#191B23"
        property color m3surfaceContainerHigh: "#222630"
        property color m3surfaceContainerHighest: "#35232F"
        property color m3onSurface: "#E6E8F0"
        property color m3surfaceVariant: "#222630"
        property color m3onSurfaceVariant: "#9CA4B5"
        property color m3inverseSurface: "#E6E8F0"
        property color m3inverseOnSurface: "#0C0D11"
        property color m3outline: "#9CA4B5"
        property color m3outlineVariant: "#0C0D11"
        property color m3shadow: "#000000"
    }

    colors: QtObject {
        property color colSubtext: m3colors.m3outline
        property color colLayer0: m3colors.m3background
        property color colOnLayer0: m3colors.m3onBackground
        property color colLayer0Border: ColorUtils.mix(root.m3colors.m3outlineVariant, colLayer0, 0.4)
        property color colLayer1: m3colors.m3surfaceContainerLow
        property color colOnLayer1: m3colors.m3onSurfaceVariant
        property color colOnLayer1Inactive: ColorUtils.mix(colOnLayer1, colLayer1, 0.45)
        property color colLayer1Hover: ColorUtils.mix(colLayer1, colOnLayer1, 0.92)
        property color colLayer1Active: ColorUtils.mix(colLayer1, colOnLayer1, 0.85)
        property color colLayer2: m3colors.m3surfaceContainer
        property color colOnLayer2: m3colors.m3onSurface
        property color colLayer2Hover: ColorUtils.mix(colLayer2, colOnLayer2, 0.90)
        property color colLayer2Active: ColorUtils.mix(colLayer2, colOnLayer2, 0.80)
        property color colPrimary: m3colors.m3primary
        property color colOnPrimary: m3colors.m3onPrimary
        property color colSecondary: m3colors.m3secondary
        property color colSecondaryContainer: m3colors.m3secondaryContainer
        property color colOnSecondaryContainer: m3colors.m3onSecondaryContainer
        property color colTooltip: m3colors.m3inverseSurface
        property color colOnTooltip: m3colors.m3inverseOnSurface
        property color colShadow: ColorUtils.transparentize(m3colors.m3shadow, 0.7)
        property color colOutline: m3colors.m3outline
    }

    rounding: QtObject {
        property int unsharpen: 0
        property int verysmall: 6
        property int small: 8
        property int normal: 12
        property int large: 16
        property int full: 9999
        property int screenRounding: large
        property int windowRounding: 12
    }

    font: QtObject {
        property QtObject family: QtObject {
            property string main: "JetBrainsMono Nerd Font"
            property string title: "Noto Sans"
            property string expressive: "Noto Sans"
        }
        property QtObject pixelSize: QtObject {
            property int smaller: 12
            property int small: 15
            property int normal: 16
            property int larger: 19
            property int huge: 22
        }
    }

    animationCurves: QtObject {
        readonly property list<real> expressiveDefaultSpatial: [0.38, 1.21, 0.22, 1.00, 1, 1]
        readonly property list<real> expressiveEffects: [0.34, 0.80, 0.34, 1.00, 1, 1]
        readonly property list<real> emphasizedDecel: [0.05, 0.7, 0.1, 1, 1, 1]
        readonly property real expressiveDefaultSpatialDuration: 500
        readonly property real expressiveEffectsDuration: 200
    }

    animation: QtObject {
        property QtObject elementMove: QtObject {
            property int duration: animationCurves.expressiveDefaultSpatialDuration
            property int type: Easing.BezierSpline
            property list<real> bezierCurve: animationCurves.expressiveDefaultSpatial
            property Component numberAnimation: Component {
                NumberAnimation {
                    duration: root.animation.elementMove.duration
                    easing.type: root.animation.elementMove.type
                    easing.bezierCurve: root.animation.elementMove.bezierCurve
                }
            }
        }

        property QtObject elementMoveEnter: QtObject {
            property int duration: 400
            property int type: Easing.BezierSpline
            property list<real> bezierCurve: animationCurves.emphasizedDecel
            property Component numberAnimation: Component {
                NumberAnimation {
                    duration: root.animation.elementMoveEnter.duration
                    easing.type: root.animation.elementMoveEnter.type
                    easing.bezierCurve: root.animation.elementMoveEnter.bezierCurve
                }
            }
        }

        property QtObject elementMoveFast: QtObject {
            property int duration: animationCurves.expressiveEffectsDuration
            property int type: Easing.BezierSpline
            property list<real> bezierCurve: animationCurves.expressiveEffects
            property Component numberAnimation: Component {
                NumberAnimation {
                    duration: root.animation.elementMoveFast.duration
                    easing.type: root.animation.elementMoveFast.type
                    easing.bezierCurve: root.animation.elementMoveFast.bezierCurve
                }
            }
        }
    }

    sizes: QtObject {
        property real elevationMargin: 10
    }
}
