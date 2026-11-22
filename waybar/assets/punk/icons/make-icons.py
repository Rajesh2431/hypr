#!/usr/bin/env python3
"""Spider-Punk bar icon set (original artwork) for the Waybar Spider-Punk style.

  python3 make-icons.py        # writes the SVGs next to this file

Each icon = blue misprint copy (offset) -> thick ink outline -> fill. 64x64 canvas.
Used as CSS background-images in style/Spider-Punk.css; the feed scripts run with
PUNK_ICONS=1 so they drop their font glyph and send a state class instead.
"""
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
INK, PAPER, CRIMSON, BLUE, YELLOW, ORANGE, MAGENTA, PURPLE = (
    "#050306", "#F5F0E8", "#FF1744", "#00B8FF", "#FFD43B", "#FF6B24", "#FF2E93", "#8B35FF")
DIM = "#3A2A35"
MIS = 3.2


def icon(name, layers):
    """layers: list of (markup, fill, misprint?) — markup is shapes without fill/stroke."""
    out = ""
    for markup, fill, mis in layers:
        if mis:
            out += f'<g transform="translate({MIS},{MIS})" fill="{BLUE}" stroke="{BLUE}" stroke-width="3" stroke-linejoin="round" opacity=".95">{markup}</g>'
    for markup, fill, mis in layers:
        out += f'<g fill="{INK}" stroke="{INK}" stroke-width="7" stroke-linejoin="round" stroke-linecap="round">{markup}</g>'
    for markup, fill, mis in layers:
        out += f'<g fill="{fill}" stroke="none">{markup}</g>'
    (HERE / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">{out}</svg>')


def stroke_icon(name, layers):
    """layers: list of (path-d, colour, width) drawn as strokes, with ink + misprint."""
    mis = "".join(f'<path d="{d}" fill="none" stroke="{BLUE}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round" transform="translate({MIS},{MIS})"/>' for d, c, w in layers)
    ink = "".join(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{w + 6}" stroke-linecap="round" stroke-linejoin="round"/>' for d, c, w in layers)
    col = "".join(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>' for d, c, w in layers)
    (HERE / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">{mis}{ink}{col}</svg>')


def arc(cx, cy, r, a0, a1):
    p = lambda a: (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
    (x0, y0), (x1, y1) = p(a0), p(a1)
    return f"M{x0:.1f},{y0:.1f} A{r},{r} 0 0 1 {x1:.1f},{y1:.1f}"


BOLT = '<polygon points="36,8 20,36 30,36 26,56 44,26 34,26 40,8"/>'

# ---------------- HUD ----------------
pins = "".join(f'<rect x="{x}" y="6" width="4" height="8"/><rect x="{x}" y="50" width="4" height="8"/>'
               f'<rect x="6" y="{x}" width="8" height="4"/><rect x="50" y="{x}" width="8" height="4"/>' for x in (20, 30, 40))
icon("cpu", [(pins, PAPER, True), ('<rect x="13" y="13" width="38" height="38" rx="3"/>', BLUE, True),
             ('<rect x="24" y="24" width="16" height="16"/>', INK, False)])
icon("ram", [('<path d="M6 20 h52 v20 h-24 v6 h-4 v-6 h-24 z"/>', MAGENTA, True),
             ('<rect x="12" y="25" width="8" height="10"/><rect x="24" y="25" width="8" height="10"/><rect x="36" y="25" width="8" height="10"/><rect x="48" y="25" width="5" height="10"/>', INK, False),
             ('<path d="M10 44 v8 M18 44 v8 M26 44 v8 M38 44 v8 M46 44 v8 M54 44 v8" stroke-width="3"/>', PAPER, False)])
icon("gpu", [('<path d="M4 16 h52 v30 h-52 z M56 22 h4 v6 h-4 z"/>', YELLOW, True),
             ('<circle cx="22" cy="31" r="10"/><circle cx="44" cy="31" r="6"/>', INK, False),
             ('<path d="M12 46 v8 h20 v-8 z"/>', PAPER, True),
             (f'<path d="M22 22 l3 9 l-3 9 l-3 -9 z M13 31 l9 -3 l9 3 l-9 3 z"/>', CRIMSON, False)])
icon("gpu-sleep", [('<path d="M4 16 h52 v30 h-52 z M56 22 h4 v6 h-4 z"/>', DIM, True),
                   ('<circle cx="22" cy="31" r="10"/><circle cx="44" cy="31" r="6"/>', INK, False),
                   ('<text x="34" y="13" font-family="Bangers" font-size="16">zz</text>', PAPER, False)])
FLAME = '<path d="M32 4 C40 18 52 24 50 40 C49 52 40 60 32 60 C22 60 14 52 14 41 C14 30 22 26 24 16 C28 22 30 26 30 30 C34 24 34 14 32 4 z"/>'
INNER = '<path d="M32 30 C36 38 42 42 41 49 C40 55 36 58 32 58 C27 58 23 54 23 49 C23 44 27 41 28 36 C30 40 31 42 32 43 C33 40 33 35 32 30 z"/>'
icon("temp", [(FLAME, ORANGE, True), (INNER, YELLOW, False)])
icon("temp-hot", [(FLAME, CRIMSON, True), (INNER, YELLOW, False)])

# ---------------- Wi-Fi / Ethernet ----------------
def wifi(name, level, off=False):
    lay = []
    for k, r in enumerate((14, 26, 38), start=1):
        on = (level > k) and not off
        lay.append((arc(32, 52, r, 225, 315), PAPER if on else DIM, 7))
    dot_col = PAPER if (level >= 1 and not off) else DIM
    mis = "".join(f'<path d="{d}" fill="none" stroke="{BLUE}" stroke-width="{w}" stroke-linecap="round" transform="translate({MIS},{MIS})"/>' for d, c, w in lay)
    ink = "".join(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{w + 6}" stroke-linecap="round"/>' for d, c, w in lay)
    col = "".join(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round"/>' for d, c, w in lay)
    dot = f'<circle cx="{32 + MIS}" cy="{52 + MIS}" r="6" fill="{BLUE}"/><circle cx="32" cy="52" r="8.5" fill="{INK}"/><circle cx="32" cy="52" r="5.5" fill="{dot_col}"/>'
    slash = (f'<path d="M12 12 L52 56" stroke="{INK}" stroke-width="12" stroke-linecap="round"/>'
             f'<path d="M12 12 L52 56" stroke="{CRIMSON}" stroke-width="6" stroke-linecap="round"/>') if off else ""
    (HERE / f"{name}.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">{mis}{ink}{col}{dot}{slash}</svg>')
for lv in range(5):
    wifi(f"wifi-{lv}", lv)
wifi("wifi-off", 4, off=True)
icon("eth", [('<path d="M18 10 h28 v26 h-8 v8 h-12 v-8 h-8 z"/>', PAPER, True),
             ('<rect x="24" y="16" width="4" height="10"/><rect x="36" y="16" width="4" height="10"/>', INK, False),
             ('<rect x="28" y="44" width="8" height="14"/>', BLUE, False)])

# ---------------- Bluetooth ----------------
RUNE = "M20 20 L44 42 L32 54 V10 L44 22 L20 44"
stroke_icon("bt-on", [(RUNE, PAPER, 6)])
stroke_icon("bt-connected", [(RUNE, BLUE, 6), ("M10 32 h0.1 M54 32 h0.1", YELLOW, 7)])
(HERE / "bt-off.svg").write_text((HERE / "bt-on.svg").read_text().replace(PAPER, DIM).replace(
    "</svg>", f'<path d="M12 12 L52 54" stroke="{INK}" stroke-width="12" stroke-linecap="round"/><path d="M12 12 L52 54" stroke="{CRIMSON}" stroke-width="6" stroke-linecap="round"/></svg>'))

# ---------------- sound ----------------
SPK = '<path d="M6 24 h12 l16 -14 v44 l-16 -14 h-12 z"/>'
def speaker(name, waves, muted=False):
    lay = [(SPK, PAPER, True)]
    body_mis = f'<g transform="translate({MIS},{MIS})" fill="{BLUE}">{SPK}</g>'
    body = f'<g fill="{INK}" stroke="{INK}" stroke-width="7" stroke-linejoin="round">{SPK}</g><g fill="{PAPER}">{SPK}</g>'
    w = ""
    for k in range(waves):
        d = arc(34, 32, 8 + k * 9, -50, 50)
        w += (f'<path d="{d}" stroke="{INK}" stroke-width="11" fill="none" stroke-linecap="round"/>'
              f'<path d="{d}" stroke="{CRIMSON}" stroke-width="5" fill="none" stroke-linecap="round"/>')
    x = ""
    if muted:
        x = (f'<path d="M42 22 L58 42 M58 22 L42 42" stroke="{INK}" stroke-width="12" stroke-linecap="round"/>'
             f'<path d="M42 22 L58 42 M58 22 L42 42" stroke="{CRIMSON}" stroke-width="6" stroke-linecap="round"/>')
    (HERE / f"{name}.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">{body_mis}{body}{w}{x}</svg>')
speaker("vol-low", 1); speaker("vol-mid", 2); speaker("vol-high", 3); speaker("vol-mute", 0, muted=True)

# ---------------- brightness ----------------
rays = "".join(
    f'<polygon points="{32 + 30 * math.cos(math.radians(a)):.1f},{32 + 30 * math.sin(math.radians(a)):.1f} '
    f'{32 + 17 * math.cos(math.radians(a - 14)):.1f},{32 + 17 * math.sin(math.radians(a - 14)):.1f} '
    f'{32 + 17 * math.cos(math.radians(a + 14)):.1f},{32 + 17 * math.sin(math.radians(a + 14)):.1f}"/>' for a in range(0, 360, 45))
icon("sun", [(rays, YELLOW, True), ('<circle cx="32" cy="32" r="13"/>', YELLOW, True), ('<circle cx="28" cy="28" r="4"/>', PAPER, False)])

# ---------------- battery ----------------
def battery(name, frac, col, extra=None):
    w = max(0, 36 * frac)
    lay = [('<path d="M6 18 h46 v28 h-46 z M52 26 h6 v12 h-6 z"/>', PAPER, True),
           ('<rect x="11" y="23" width="36" height="18"/>', INK, False)]
    if w:
        lay.append((f'<rect x="11" y="23" width="{w:.1f}" height="18"/>', col, False))
    if extra:
        lay.append(extra)
    icon(name, lay)
battery("bat-good", 1.0, BLUE)
battery("bat-half", 0.6, PAPER)
battery("bat-warning", 0.3, YELLOW)
battery("bat-critical", 0.12, CRIMSON)
battery("bat-charging", 0.7, BLUE, ('<polygon points="34,14 22,34 30,34 26,50 40,28 32,28 36,14"/>', YELLOW, False))
battery("bat-plugged", 1.0, BLUE, ('<path d="M22 26 h4 v-6 h4 v6 h4 v-6 h4 v6 h4 v8 a10 10 0 0 1 -20 0 z"/>', PAPER, False))

# ---------------- caffeine ----------------
MUG = '<path d="M10 22 h36 v22 a12 12 0 0 1 -12 12 h-12 a12 12 0 0 1 -12 -12 z"/>'
HANDLE = '<path fill-rule="evenodd" d="M44 26 h6 a8 8 0 0 1 0 16 h-6 v-5 h6 a3 3 0 0 0 0 -6 h-6 z"/>'
icon("cup-empty", [(HANDLE, PAPER, True), (MUG, PAPER, True), ('<rect x="15" y="27" width="26" height="4"/>', DIM, False)])
icon("cup-full", [(HANDLE, PAPER, True), (MUG, PAPER, True), ('<path d="M14 27 h28 v15 a9 9 0 0 1 -9 9 h-10 a9 9 0 0 1 -9 -9 z"/>', CRIMSON, False)])
(HERE / "cup-full.svg").write_text((HERE / "cup-full.svg").read_text().replace("</svg>",
    f'<path d="M20 16 q-4 -5 0 -10 M30 16 q-4 -5 0 -10" stroke="{YELLOW}" stroke-width="3.5" fill="none" stroke-linecap="round"/></svg>'))

# ---------------- AI ----------------
def robot(name, col):
    icon(name, [('<rect x="30" y="2" width="4" height="10"/><circle cx="32" cy="4" r="4"/>', col, True),
                ('<path d="M8 14 h48 v34 l-8 8 h-32 l-8 -8 z"/>', col, True),
                ('<rect x="15" y="24" width="12" height="10"/><rect x="37" y="24" width="12" height="10"/>', INK, False),
                ('<rect x="19" y="27" width="4" height="4"/><rect x="41" y="27" width="4" height="4"/>', PAPER, False),
                ('<path d="M20 42 h24 v4 h-24 z"/>', INK, False)])
robot("ai-ok", BLUE); robot("ai-warn", YELLOW); robot("ai-crit", CRIMSON); robot("ai-idle", DIM)

# ---------------- updates ----------------
icon("updates", [('<path d="M8 20 l24 -12 l24 12 v26 l-24 12 l-24 -12 z"/>', ORANGE, True),
                 ('<path d="M8 20 l24 12 l24 -12 M32 32 v26" fill="none" stroke-width="3"/>', INK, False),
                 ('<path d="M26 4 h12 v10 h6 l-12 12 l-12 -12 h6 z"/>', YELLOW, False)])

print("icons:", len(list(HERE.glob("*.svg"))))

# ---------------- Tailscale: 3x3 dot grid, the "T" (top row + centre column) lit ----------------
def tailscale(name, lit, rest):
    pos = [(x, y) for y in (14, 32, 50) for x in (14, 32, 50)]
    on = {(14, 14), (32, 14), (50, 14), (32, 32), (32, 50)}
    a = "".join(f'<circle cx="{x}" cy="{y}" r="7.5"/>' for x, y in pos if (x, y) in on)
    b = "".join(f'<circle cx="{x}" cy="{y}" r="7.5"/>' for x, y in pos if (x, y) not in on)
    icon(name, [(b, rest, False), (a, lit, True)])
tailscale("ts-on", PAPER, DIM)
tailscale("ts-off", DIM, DIM)
tailscale("ts-exit", YELLOW, CRIMSON)     # traffic leaves through an exit node
tailscale("ts-login", ORANGE, DIM)        # needs login / starting

# ---------------- clipboard: paper board, crimson clip, ink lines ----------------
icon("clipboard", [('<rect x="12" y="10" width="40" height="48" rx="3"/>', PAPER, True),
                   ('<rect x="22" y="5" width="20" height="11" rx="2"/>', CRIMSON, False),
                   ('<path d="M20 28 h24 M20 37 h24 M20 46 h15" stroke-width="4"/>', INK, False)])

# ---------------- hover splash: jagged comic burst that sits behind an icon-only button ----------------
def burst(n, r1, r2, cx=32, cy=32, rot=-8):
    pts = []
    for i in range(n * 2):
        a = math.radians(rot + i * 180 / n)
        r = r1 if i % 2 == 0 else r2 * (0.86 + 0.14 * ((i * 7) % 3) / 2)
        pts.append(f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}")
    return " ".join(pts)
(HERE / "hover-splash.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
    f'<polygon points="{burst(11, 31, 21, 34, 34)}" fill="{CRIMSON}"/>'
    f'<polygon points="{burst(11, 30, 20)}" fill="{YELLOW}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/></svg>')

# ---------------- battery v2: chunky 5-cell comic battery (overrides the bat-* above) ----------------
BOLT2 = '<polygon points="35,6 18,35 29,35 24,58 46,26 34,26 40,6"/>'
def battery2(name, cells, col, bolt=False, alert=False, plug=False):
    body = '<path d="M5 17 h47 v30 h-47 z"/><path d="M52 25 h7 v14 h-7 z"/>'
    lay = [(body, PAPER, True), ('<rect x="10" y="22" width="37" height="20"/>', INK, False)]
    cw, gap = 6.2, 1.5
    lit = "".join(f'<rect x="{11.5 + i * (cw + gap):.1f}" y="23.5" width="{cw}" height="17"/>' for i in range(cells))
    dim = "".join(f'<rect x="{11.5 + i * (cw + gap):.1f}" y="23.5" width="{cw}" height="17"/>' for i in range(cells, 5))
    if dim:
        lay.append((dim, DIM, False))
    if lit:
        lay.append((lit, col, False))
    if alert:   # big "!" punched through the empty cells
        lay.append(('<rect x="33" y="20" width="6" height="15"/><rect x="33" y="38" width="6" height="6"/>', CRIMSON, True))
    if plug:   # on the charger and full: white bolt
        lay.append((BOLT2, PAPER, True))
    if bolt:
        lay.append((BOLT2, YELLOW, True))
    icon(name, lay)
battery2("bat-good", 5, BLUE)
battery2("bat-high", 4, BLUE)
battery2("bat-half", 3, PAPER)
battery2("bat-mid", 2, PAPER)
battery2("bat-warning", 1, YELLOW)
battery2("bat-critical", 1, CRIMSON, alert=True)
for n in range(1, 6):
    battery2(f"bat-charging-{n}", n, BLUE, bolt=True)
battery2("bat-charging", 3, BLUE, bolt=True)
battery2("bat-plugged", 5, BLUE, plug=True)
