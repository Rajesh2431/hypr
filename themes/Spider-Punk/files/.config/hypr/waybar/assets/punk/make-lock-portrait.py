#!/usr/bin/env python3
"""Lock-screen portrait: the sticker art + a hard comic ink drop shadow, on a square canvas
(hyprlock's image widget scales to a square). Source: ~/Pictures/logos/Punk_Comic_Portrait_Sticker-removebg-preview.png"""
import os
from PIL import Image, ImageFilter
SRC = os.path.expanduser("~/Pictures/logos/Punk_Comic_Portrait_Sticker-removebg-preview.png")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lock-portrait.png")
art = Image.open(SRC).convert("RGBA")
art = art.crop(art.getchannel("A").getbbox())
S, PAD, OFF = 2, 24, 14                               # 2x upscale, margin, shadow offset
art = art.resize((art.width * S, art.height * S), Image.LANCZOS)
side = max(art.size) + 2 * PAD * S + OFF * S
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
x, y = (side - art.width - OFF * S) // 2, (side - art.height - OFF * S) // 2
a = art.getchannel("A").point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(7))
ink = Image.new("RGBA", art.size, (5, 3, 6, 255)); ink.putalpha(a)
canvas.alpha_composite(ink, (x + OFF * S, y + OFF * S))   # hard offset shadow, no blur
canvas.alpha_composite(art, (x, y))
canvas.save(OUT, optimize=True)
print(OUT, canvas.size)
