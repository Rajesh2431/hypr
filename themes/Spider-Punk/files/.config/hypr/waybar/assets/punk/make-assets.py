#!/usr/bin/env python3
"""Spider-Punk zine assets for Waybar + the island (original artwork, no logos).

Run:  python3 make-assets.py      (writes the SVGs next to this file)

Every panel is a hand-cut polygon (seeded jitter, so it is reproducible):
  misprint layer (offset, crimson or blue)  ->  black ink outline  ->  fill
  ->  halftone dots fading in from one side  ->  a few distressed scratches.
Sizes are close to the real on-screen sizes, because GTK rasterises an SVG at
its own size and then stretches it.
"""
import math, random
from pathlib import Path

HERE = Path(__file__).resolve().parent

INK = "#050306"
BLACK = "#151117"
BG = "#0B090D"
CRIMSON = "#FF1744"
BLUE = "#00B8FF"
PURPLE = "#8B35FF"
MAGENTA = "#FF2E93"
YELLOW = "#FFD43B"
ORANGE = "#FF6B24"
PAPER = "#F5F0E8"


def torn(w, h, inset, jag, seed, step=14):
    """Polygon around a w*h box with a torn/hand-cut edge."""
    r = random.Random(seed)
    pts = []
    def edge(x0, y0, x1, y1, nx, ny):
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / step))
        for i in range(n):
            t = i / n
            j = r.uniform(-jag, jag) if 0 < i else r.uniform(0, jag)
            pts.append((x0 + (x1 - x0) * t + nx * j, y0 + (y1 - y0) * t + ny * j))
    a = inset
    # slightly skewed corners: comic panels are never square
    c = [(a + r.uniform(0, 3), a + r.uniform(0, 2)), (w - a - r.uniform(0, 3), a + r.uniform(0, 2)),
         (w - a - r.uniform(0, 2), h - a - r.uniform(0, 2)), (a + r.uniform(0, 2), h - a - r.uniform(0, 2))]
    edge(*c[0], *c[1], 0, 1)
    edge(*c[1], *c[2], -1, 0)
    edge(*c[2], *c[3], 0, -1)
    edge(*c[3], *c[0], 1, 0)
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def halftone_defs(pid, color, size=5, rad=1.1, op=0.55):
    return (f'<pattern id="{pid}" width="{size}" height="{size}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            f'<circle cx="{size/2}" cy="{size/2}" r="{rad}" fill="{color}" fill-opacity="{op}"/></pattern>')


def scratches(w, h, seed, color, n=5, op=0.10):
    r = random.Random(seed)
    out = []
    for _ in range(n):
        x, y = r.uniform(10, w - 10), r.uniform(6, h - 6)
        l, a = r.uniform(8, 30), r.uniform(-0.5, 0.5)
        out.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + l * math.cos(a):.1f}" y2="{y + l * math.sin(a):.1f}" '
                   f'stroke="{color}" stroke-opacity="{op}" stroke-width="{r.uniform(.6, 1.4):.1f}" stroke-linecap="round"/>')
    return "".join(out)


def panel(name, w, h, fill, misprint, dots, dots_from="right", seed=1, jag=1.6, dots_op=0.5, mis=(3, 3),
          stroke=INK, sw=2.2, fill_op=0.92):
    poly_s = torn(w, h, 4, jag, seed + 100)
    poly = torn(w, h, 4, jag, seed)
    gx = ("1", "0") if dots_from == "right" else ("0", "1")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">
<defs>{halftone_defs("ht", dots, op=dots_op)}
<linearGradient id="fade" x1="{gx[0]}" y1="0" x2="{gx[1]}" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="1"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/></linearGradient>
<mask id="m"><polygon points="{poly}" fill="url(#fade)"/></mask></defs>
<polygon points="{poly_s}" transform="translate({mis[0]},{mis[1]})" fill="{misprint}" fill-opacity=".85"/>
<polygon points="{poly}" fill="{fill}" fill-opacity="{fill_op}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"/>
<rect width="{w}" height="{h}" fill="url(#ht)" mask="url(#m)"/>
{scratches(w, h, seed, PAPER)}
</svg>'''
    (HERE / f"{name}.svg").write_text(svg)


def sticker(name, w, h, fill, misprint, seed, outline_only=False):
    poly = torn(w, h, 3, 1.3, seed, step=9)
    poly_s = torn(w, h, 3, 1.3, seed + 7, step=9)
    body = (f'<polygon points="{poly}" fill="none" stroke="{fill}" stroke-width="1.6" stroke-dasharray="5 2 1 2" stroke-linejoin="round"/>'
            if outline_only else
            f'<polygon points="{poly_s}" transform="translate(2.5,2.5)" fill="{misprint}"/>'
            f'<polygon points="{poly}" fill="{fill}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>'
            f'<rect width="{w}" height="{h}" fill="url(#ht)"/>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">
<defs>{halftone_defs("ht", INK, size=4, rad=.7, op=.18)}</defs>{body}</svg>'''
    (HERE / f"{name}.svg").write_text(svg)


def spider(name, s=64):
    """Original punk spider mark: angular body, zig-zag legs, mohawk spikes, lightning."""
    c = s / 2
    legs = []
    for side in (-1, 1):
        for i, (a, b) in enumerate([(-55, -80), (-20, -35), (15, 35), (50, 80)]):
            ra, rb = math.radians(a), math.radians(b)
            kx, ky = c + side * 14 * math.cos(ra), c + 4 + 14 * math.sin(ra)
            ex, ey = c + side * 27 * math.cos(rb) * (1.05 if i % 2 else 1), c + 4 + 27 * math.sin(rb)
            legs.append(f"M{c + side * 6:.1f},{c + 4:.1f} L{kx:.1f},{ky:.1f} L{ex:.1f},{ey:.1f}")
    legs = " ".join(legs)
    spikes = " ".join(f"M{c + dx - 3:.1f},{c - 9:.1f} L{c + dx:.1f},{c - 21 - abs(dx) * -0.4 - (6 - abs(dx)):.1f} L{c + dx + 3:.1f},{c - 9:.1f}"
                      for dx in (-6, 0, 6))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 {s} {s}">
<g transform="translate(2,2)" opacity=".9"><path d="{legs}" stroke="{BLUE}" stroke-width="4" fill="none" stroke-linecap="square" stroke-linejoin="miter"/>
<polygon points="{c-8},{c-6} {c+8},{c-6} {c+10},{c+6} {c},{c+18} {c-10},{c+6}" fill="{BLUE}"/></g>
<path d="{legs}" stroke="{INK}" stroke-width="6" fill="none" stroke-linecap="square" stroke-linejoin="miter"/>
<path d="{legs}" stroke="{CRIMSON}" stroke-width="3" fill="none" stroke-linecap="square" stroke-linejoin="miter"/>
<path d="{spikes}" fill="{PAPER}" stroke="{INK}" stroke-width="2" stroke-linejoin="miter"/>
<polygon points="{c-8},{c-6} {c+8},{c-6} {c+10},{c+6} {c},{c+18} {c-10},{c+6}" fill="{CRIMSON}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="miter"/>
<polygon points="{c-5},{c-3} {c-1},{c+1} {c-6},{c+2}" fill="{PAPER}"/><polygon points="{c+5},{c-3} {c+1},{c+1} {c+6},{c+2}" fill="{PAPER}"/>
<polygon points="{c+1},{c+4} {c-3},{c+10} {c},{c+10} {c-2},{c+15} {c+3},{c+8} {c},{c+8}" fill="{YELLOW}"/>
</svg>'''
    (HERE / f"{name}.svg").write_text(svg)


def bolt(name, w=14, h=24):
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 14 24">
<polygon points="9,1 2,13 7,13 4,23 12,9 7,9 11,1" transform="translate(1.5,1)" fill="{CRIMSON}"/>
<polygon points="9,1 2,13 7,13 4,23 12,9 7,9 11,1" fill="{YELLOW}" stroke="{INK}" stroke-width="1.2" stroke-linejoin="miter"/></svg>'''
    (HERE / f"{name}.svg").write_text(svg)


def halftone_tile(name, color, op):
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">
<circle cx="3" cy="3" r="1.3" fill="{color}" fill-opacity="{op}"/><circle cx="9" cy="9" r="1.3" fill="{color}" fill-opacity="{op}"/></svg>'''
    (HERE / f"{name}.svg").write_text(svg)


def power_icons():
    """Power button: crimson broken ring + lightning-bolt stem (idle), and a yellow
    comic starburst with the same symbol in ink (hover)."""
    def symbol(ring, bolt, ox=0, oy=0, sc=1.0):
        # ring: arc from 50deg to 310deg around (32,34) r 17, open at the top
        import math
        cx, cy, r = 32 + ox, 34 + oy, 17 * sc
        a0, a1 = math.radians(-60), math.radians(240)
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        arc = f"M{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 1 1 {x1:.1f},{y1:.1f}"
        pts = [(35, 6), (24, 30), (31, 30), (27, 46), (41, 22), (34, 22), (38, 6)]
        bp = " ".join(f"{cx - 32 + (x - 32) * sc + 32:.1f},{cy - 34 + (y - 34) * sc + 34:.1f}" for x, y in pts)
        return arc, bp
    arc, bp = symbol(None, None)
    idle = f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<g transform="translate(3,3)" opacity=".9"><path d="{arc}" fill="none" stroke="{BLUE}" stroke-width="9" stroke-linecap="square"/>
<polygon points="{bp}" fill="{BLUE}"/></g>
<path d="{arc}" fill="none" stroke="{INK}" stroke-width="12" stroke-linecap="square"/>
<path d="{arc}" fill="none" stroke="{CRIMSON}" stroke-width="6.5" stroke-linecap="square"/>
<polygon points="{bp}" fill="{YELLOW}" stroke="{INK}" stroke-width="2.6" stroke-linejoin="miter"/>
</svg>'''
    (HERE / "power.svg").write_text(idle)
    # starburst: 14 jagged spikes with uneven lengths (hand-cut)
    r = random.Random(77)
    spikes = []
    for i in range(28):
        a = math.radians(i * 360 / 28 - 90)
        rad = (30 if i % 2 == 0 else 19) + (r.uniform(-2.5, 2.5) if i % 2 == 0 else r.uniform(-1.5, 1.5))
        spikes.append(f"{32 + rad * math.cos(a):.1f},{32 + rad * math.sin(a):.1f}")
    burst = " ".join(spikes)
    arc2, bp2 = symbol(None, None, sc=0.78)
    hot = f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<polygon points="{burst}" transform="translate(2.5,2.5)" fill="{CRIMSON}"/>
<polygon points="{burst}" fill="{YELLOW}" stroke="{INK}" stroke-width="2.4" stroke-linejoin="miter"/>
<circle cx="32" cy="32" r="16" fill="url(#ht)"/>
<defs>{halftone_defs("ht", CRIMSON, size=4, rad=.9, op=.55)}</defs>
<path d="{arc2}" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="square"/>
<polygon points="{bp2}" fill="{CRIMSON}" stroke="{INK}" stroke-width="2" stroke-linejoin="miter"/>
</svg>'''
    (HERE / "power-burst.svg").write_text(hot)


if __name__ == "__main__":
    power_icons()
    # bar islands (≈ real sizes; heights include the 3 px misprint)
    panel("panel-left", 470, 44, BLACK, CRIMSON, CRIMSON, "left", seed=3)
    panel("panel-clock", 250, 44, CRIMSON, BLUE, INK, "right", seed=11, dots_op=.35, fill_op=1)
    panel("panel-hud", 250, 44, BLACK, BLUE, BLUE, "left", seed=21, dots_op=.45)
    panel("panel-right", 470, 44, BLACK, BLUE, MAGENTA, "right", seed=5)
    panel("panel-tip", 360, 160, BLACK, CRIMSON, CRIMSON, "right", seed=31, jag=2.2, dots_op=.35)
    # workspace "comic panels"
    sticker("ws-active", 48, 30, CRIMSON, BLUE, 41)
    sticker("ws-hover", 40, 30, PAPER, INK, 43, outline_only=True)
    sticker("ws-urgent", 40, 30, YELLOW, CRIMSON, 45)
    sticker("btn-hover", 40, 30, BLUE, INK, 47, outline_only=True)
    spider("spider")
    bolt("bolt")
    halftone_tile("dots-crimson", CRIMSON, .35)
    halftone_tile("dots-blue", BLUE, .35)
    # rofi card + lock-screen panels (rofi / hyprlock load PNG, so these are rendered below)
    panel("panel-rofi", 720, 560, BG, CRIMSON, CRIMSON, "right", seed=61, jag=3.0, dots_op=.32, mis=(8, 8), sw=4, fill_op=.96)
    panel("panel-lock", 760, 300, CRIMSON, BLUE, INK, "right", seed=71, jag=3.2, dots_op=.38, mis=(12, 12), sw=6, fill_op=1)
    panel("panel-lockbox", 520, 120, BLACK, CRIMSON, CRIMSON, "left", seed=81, jag=2.4, dots_op=.4, mis=(8, 8), sw=4)
    import subprocess
    for name, dens in (("panel-rofi", 96), ("panel-lock", 96), ("panel-lockbox", 96), ("spider", 384), ("bolt", 384)):
        subprocess.run(["magick", "-background", "none", "-density", str(dens), str(HERE / f"{name}.svg"), str(HERE / f"{name}.png")], check=True)
    print("ok:", ", ".join(sorted(p.name for p in HERE.glob("*.svg"))))
