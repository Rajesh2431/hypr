#!/usr/bin/env python3
"""Round lock-screen avatar from portrait-src.png: head crop on a soft dark-crimson backdrop
(hyprlock draws it as a circle with rounding = -1)."""
import os
from PIL import Image, ImageDraw, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))
src = Image.open(os.path.join(HERE, "portrait-src.png")).convert("RGBA")
box = (95, 20, 415, 340)                      # head + shoulders, square
art = src.crop(box).resize((640, 640), Image.LANCZOS)
bg = Image.new("RGBA", (640, 640))
d = ImageDraw.Draw(bg)
for r in range(460, 0, -4):                   # radial glow: crimson centre -> near black
    t = r / 460
    c = (int(40 + 120 * (1 - t)), int(10 + 8 * (1 - t)), int(24 + 30 * (1 - t)), 255)
    d.ellipse([320 - r, 300 - r, 320 + r, 300 + r], fill=c)
bg = bg.filter(ImageFilter.GaussianBlur(18))
bg.alpha_composite(art)
bg.convert("RGB").save(os.path.join(HERE, "avatar.png"), optimize=True)
print("avatar.png")
