#!/usr/bin/env python3
"""Comic pieces for the Spider-Punk lock screen (hyprlock-punk-art.conf):
  overlay.png  1920x1080: halftone corners (crimson top-left, blue bottom-right), ink vignette,
               faint speed lines toward the centre
  burst.png    jagged starburst (yellow, ink outline, blue misprint) behind the avatar"""
import math, os
from PIL import Image, ImageDraw, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))
INK, CRIMSON, BLUE, YELLOW = (5, 3, 6), (255, 23, 68), (0, 184, 255), (255, 212, 59)
W, H = 1920, 1080
ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))

# speed lines (very faint), radiating from the centre, only in the outer ring
sl = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(sl)
for i in range(90):
    a = math.radians(i * 4 + (i % 3))
    r0, r1 = 620 + (i * 37) % 160, 1300
    d.line([(W / 2 + r0 * math.cos(a), H / 2 + r0 * math.sin(a)), (W / 2 + r1 * math.cos(a), H / 2 + r1 * math.sin(a))],
           fill=(245, 240, 232, 16), width=2 + i % 3)
ov.alpha_composite(sl)

# halftone corners
def halftone(cx, cy, reach, col):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    step = 22
    for y in range(0, H + step, step):
        for x in range(0, W + step, step):
            ox = x + (step // 2 if (y // step) % 2 else 0)
            t = 1 - math.hypot(ox - cx, y - cy) / reach
            if t > 0:
                r = (t ** 1.3) * step * 0.46
                d.ellipse([ox - r, y - r, ox + r, y + r], fill=col + (150,))
    ov.alpha_composite(layer)
halftone(0, 0, 720, CRIMSON)
halftone(W, H, 760, BLUE)

# ink vignette
vg = Image.new("L", (W, H), 0); d = ImageDraw.Draw(vg)
d.rectangle([0, 0, W, H], fill=170); d.ellipse([-260, -200, W + 260, H + 200], fill=0)
vg = vg.filter(ImageFilter.GaussianBlur(120))
ink = Image.new("RGBA", (W, H), INK + (255,)); ink.putalpha(vg)
ov.alpha_composite(ink)
ov.save(os.path.join(HERE, "overlay.png"), optimize=True)

# starburst behind the avatar
S = 600; C = S / 2
b = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(b)
def pts(cx, cy, r1, r2, n=16, rot=-4):
    out = []
    for i in range(n * 2):
        a = math.radians(rot + i * 180 / n)
        r = (r1 * (0.9 + 0.1 * ((i * 7) % 3) / 2)) if i % 2 == 0 else r2
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out
d.polygon(pts(C + 14, C + 14, 280, 205), fill=BLUE + (255,))
d.polygon(pts(C, C, 280, 205), fill=YELLOW + (255,), outline=INK + (255,), width=12)
b.save(os.path.join(HERE, "burst.png"), optimize=True)
print("overlay.png burst.png")
