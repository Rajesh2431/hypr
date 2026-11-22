#!/usr/bin/env python3
"""Lock-screen cover art for hyprlock (hyprlock-punk-art.conf): halftone disc + comic burst + portrait.
Source: portrait-src.png (copied from ~/Downloads/Punk_Comic_Portrait_Sticker-removebg-preview.png).
Square canvas: hyprlock's image widget scales to a square."""
import math, os
from PIL import Image, ImageDraw, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))
INK, PAPER, CRIMSON, BLUE, YELLOW = (5, 3, 6), (245, 240, 232), (255, 23, 68), (0, 184, 255), (255, 212, 59)
S = 1400; C = S // 2
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# 1. halftone disc: crimson dots, big in the middle, fading out
dots = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(dots)
step = 26
for y in range(0, S, step):
    for x in range(0, S, step):
        ox = x + (step // 2 if (y // step) % 2 else 0)
        r = math.hypot(ox - C, y - C) / (S * 0.48)
        if r < 1:
            rad = (1 - r) ** 0.8 * step * 0.42
            d.ellipse([ox - rad, y - rad, ox + rad, y + rad], fill=CRIMSON + (200,))
img.alpha_composite(dots)

# 2. jagged burst with blue misprint + ink outline
def burst(cx, cy, r1, r2, n=14, rot=-6):
    pts = []
    for i in range(n * 2):
        a = math.radians(rot + i * 180 / n)
        r = r1 * (0.92 + 0.08 * ((i * 5) % 3) / 2) if i % 2 == 0 else r2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts
b = burst(C, C + 20, 560, 420)
d = ImageDraw.Draw(img)
d.polygon([(x + 22, y + 22) for x, y in b], fill=BLUE + (255,))
d.polygon(b, fill=YELLOW + (255,), outline=INK + (255,), width=16)

# 3. speed lines inside the burst (ink, thin)
lines = Image.new("RGBA", (S, S), (0, 0, 0, 0)); dl = ImageDraw.Draw(lines)
for i in range(36):
    a = math.radians(i * 10 + 3)
    dl.line([(C + 250 * math.cos(a), C + 20 + 250 * math.sin(a)), (C + 400 * math.cos(a), C + 20 + 400 * math.sin(a))],
            fill=INK + (70,), width=5)
img.alpha_composite(lines)

# 4. portrait sticker, big, with a hard ink shadow
art = Image.open(os.path.join(HERE, "portrait-src.png")).convert("RGBA")
art = art.crop(art.getchannel("A").getbbox())
h = 960; art = art.resize((round(art.width * h / art.height), h), Image.LANCZOS)
x, y = C - art.width // 2 - 10, S - h - 150
a = art.getchannel("A").point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(9))
sh = Image.new("RGBA", art.size, INK + (255,)); sh.putalpha(a)
img.alpha_composite(sh, (x + 26, y + 22))
img.alpha_composite(art, (x, y))
img.save(os.path.join(HERE, "cover.png"), optimize=True)
print("cover.png", img.size)
