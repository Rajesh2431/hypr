// A hand-cut comic panel: misprint layer (offset) -> black ink outline -> fill -> halftone corner.
// The edge jitter is seeded, so a panel keeps its shape while it resizes.
import QtQuick
import QtQuick.Shapes

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

    function rnd(s) { return function() { s |= 0; s = s + 0x6D2B79F5 | 0; let t = Math.imul(s ^ s >>> 15, 1 | s)
        t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296 } }
    function poly(w, h, sd) {
        const r = rnd(sd), a = 3, pts = []
        const c = [[a + r() * 3, a + r() * 2], [w - a - r() * 3, a + r() * 2], [w - a - r() * 2, h - a - r() * 2], [a + r() * 2, h - a - r() * 2]]
        const n = [[0, 1], [-1, 0], [0, -1], [1, 0]]
        for (let e = 0; e < 4; e++) {
            const p0 = c[e], p1 = c[(e + 1) % 4], len = Math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            const k = Math.max(2, Math.floor(len / step))
            for (let i = 0; i < k; i++) {
                const t = i / k, j = i ? (r() * 2 - 1) * jag : r() * jag
                pts.push(Qt.point(p0[0] + (p1[0] - p0[0]) * t + n[e][0] * j, p0[1] + (p1[1] - p0[1]) * t + n[e][1] * j))
            }
        }
        pts.push(pts[0])
        return pts
    }
    readonly property real iw: Math.max(10, width - Math.abs(offset.x))
    readonly property real ih: Math.max(10, height - Math.abs(offset.y))
    readonly property real ox: offset.x < 0 ? -offset.x : 0
    readonly property real oy: offset.y < 0 ? -offset.y : 0

    Shape {
        x: pp.ox + pp.offset.x; y: pp.oy + pp.offset.y
        width: pp.iw; height: pp.ih
        preferredRendererType: Shape.CurveRenderer
        opacity: pp.misprintOpacity
        ShapePath { strokeWidth: 0; strokeColor: "transparent"; fillColor: pp.misprint
                    PathPolyline { path: pp.poly(pp.iw, pp.ih, pp.seed + 101) } }
    }
    Shape {
        x: pp.ox; y: pp.oy; width: pp.iw; height: pp.ih
        preferredRendererType: Shape.CurveRenderer
        ShapePath { strokeWidth: pp.strokeWidth; strokeColor: pp.stroke; fillColor: pp.fill; joinStyle: ShapePath.RoundJoin
                    PathPolyline { path: pp.poly(pp.iw, pp.ih, pp.seed) } }
    }
    // halftone corner (tiled dots, fading out)
    Image {
        visible: pp.dots
        x: pp.ox + (pp.dotsLeft ? 6 : pp.iw * 0.5); y: pp.oy + 6
        width: pp.iw * 0.5 - 6; height: Math.min(pp.ih - 12, 90)
        fillMode: Image.Tile; source: Punk.assets + (pp.dotsColor === Punk.blue ? "dots-blue.svg" : "dots-crimson.svg")
        sourceSize: Qt.size(12, 12)
        opacity: pp.dotsOpacity
        layer.enabled: false
    }
}
