#!/usr/bin/env python3
"""Card background + accent colour for the hyprlock now-playing card (called by LockMedia.sh).

  lockmedia-card.py COVER.png CARD.png ACCENT.txt
Accent = the most vivid colour that covers a fair part of the cover (lifted so it reads on a
dark card). Card = Spider-Punk comic panel: 480x116 ink-bordered panel with a blue misprint
offset (+8,+8, so the image is 488x124), dark fill with halftone dots in the accent colour
fading in from the right, and an accent corner tab. Drawn at 2x.
Previous (smooth glass) version: lockmedia-card.py.bak-smooth
"""
import colorsys, sys
from PIL import Image, ImageDraw

cover, card_out, accent_out = sys.argv[1:4]
style = sys.argv[4] if len(sys.argv) > 4 else "punk"     # "glass" = Obsidian Glass card
INK, BLUE = (5, 3, 6), (0, 184, 255)
im = Image.open(cover).convert("RGB").resize((64, 64))
pal = im.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
colours = pal.getpalette()
best, score = (255, 23, 68), -1          # fallback: punk crimson
for n, idx in sorted(pal.getcolors(), reverse=True):
    r, g, b = colours[idx * 3: idx * 3 + 3]
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    sc = s * (n ** 0.5) * (0.3 if l < 0.12 or l > 0.92 else 1)
    if sc > score:
        score, best = sc, (r, g, b)
h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in best))
if s < 0.18:                              # grey / black-and-white cover: punk crimson
    h, l, s = colorsys.rgb_to_hls(1.0, 23 / 255, 68 / 255)
l, s = min(max(l, 0.58), 0.70), max(s, 0.65)
acc = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))
open(accent_out, "w").write("#%02X%02X%02X\n" % acc)

if style == "glass":
    # Obsidian Glass: rounded translucent charcoal card, 1px soft border, a soft accent glow behind the cover.
    # Same 488x124 canvas as the comic card so hyprlock positions stay identical.
    S, W, H = 2, 480, 116
    img = Image.new("RGBA", ((W + 8) * S, (H + 8) * S), (0, 0, 0, 0))
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0)); g = ImageDraw.Draw(glow)
    ga = (120, 185, 231) if acc == (255, 41, 82) else acc   # grey cover: Obsidian blue instead of punk crimson
    g.ellipse([20 * S, 0, 150 * S, H * S], fill=ga + (60,))
    from PIL import ImageFilter
    glow = glow.filter(ImageFilter.GaussianBlur(45 * S))
    mask = Image.new("L", img.size, 0); ImageDraw.Draw(mask).rounded_rectangle([0, 0, W * S - 1, H * S - 1], 18 * S, fill=255)
    base = Image.new("RGBA", img.size, (25, 27, 35, 190))
    base = Image.alpha_composite(base, glow)
    img.paste(base, (0, 0), mask)
    ImageDraw.Draw(img).rounded_rectangle([0, 0, W * S - 1, H * S - 1], 18 * S, outline=(57, 66, 81, 255), width=S)
    img.save(card_out); sys.exit(0)

S, W, H, OFF, B = 2, 480, 116, 8, 5
img = Image.new("RGBA", ((W + OFF) * S, (H + OFF) * S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rectangle([OFF * S, OFF * S, (W + OFF) * S - 1, (H + OFF) * S - 1], fill=BLUE + (255,))       # misprint
d.rectangle([0, 0, W * S - 1, H * S - 1], fill=INK + (255,))                                     # ink frame
inner = [B * S, B * S, (W - B) * S - 1, (H - B) * S - 1]
d.rectangle(inner, fill=(22, 16, 26, 240))
# halftone in the accent colour, growing toward the right edge
step = 9 * S
for y in range(inner[1], inner[3], step):
    for x in range(inner[0], inner[2], step):
        ox = x + (step // 2 if ((y - inner[1]) // step) % 2 else 0)
        t = (ox - inner[0]) / (inner[2] - inner[0])
        r = max(0, (t - 0.35) / 0.65) ** 1.4 * step * 0.42
        if r > 0.6 and ox + r < inner[2] and y + r < inner[3]:
            d.ellipse([ox - r, y - r, ox + r, y + r], fill=acc + (110,))
# accent corner tab (top-right), comic "page corner"
d.polygon([(W * S - 1 - 46 * S, 0), (W * S - 1, 0), (W * S - 1, 46 * S)], fill=INK + (255,))
d.polygon([(W * S - 1 - 38 * S, B * S), (W * S - 1 - B * S, B * S), (W * S - 1 - B * S, 38 * S)], fill=acc + (255,))
img.save(card_out)
