#!/usr/bin/env python3
"""Obsidian Glass wallpaper: dark blue-gray atmosphere, layered foggy ridges, a soft cold glow, fine grain.
Procedural (no external images), so it is free to use. Output: 2560x1440 PNG.
  python3 make-wallpaper.py OUT.png [seed]"""
import sys, numpy as np
from PIL import Image, ImageFilter
W, H = 2560, 1440
out = sys.argv[1]; rng = np.random.default_rng(int(sys.argv[2]) if len(sys.argv) > 2 else 7)
y = np.linspace(0, 1, H)[:, None]; x = np.linspace(0, 1, W)[None, :]
top, bot = np.array([14, 16, 22]), np.array([9, 10, 14])
img = top * (1 - y[..., None]) + bot * y[..., None] + np.zeros((H, W, 3))
# cold glow upper-right + faint cyan haze low-left
d = np.sqrt(((x - 0.72) * 1.6) ** 2 + (y - 0.28) ** 2)
img += np.exp(-(d / 0.42) ** 2)[..., None] * np.array([46, 64, 88])
d2 = np.sqrt(((x - 0.15) * 1.4) ** 2 + (y - 0.85) ** 2)
img += np.exp(-(d2 / 0.35) ** 2)[..., None] * np.array([10, 26, 32])
def ridge(base, amp, freq, seed):
    r = np.random.default_rng(seed); xs = np.linspace(0, 1, W); h = np.zeros(W)
    for k in range(1, 7):
        h += amp / k ** 1.3 * np.sin(2 * np.pi * (freq * k * xs + r.random()))
    return base + h
for i, (base, amp, freq, col, fog) in enumerate([(0.56, 0.05, 0.9, [24, 30, 40], 0.55), (0.66, 0.06, 1.3, [18, 22, 30], 0.45),
                                                   (0.76, 0.05, 1.8, [13, 15, 21], 0.35), (0.87, 0.04, 2.4, [9, 10, 14], 0.2)]):
    h = ridge(base, amp, freq, 100 + i)[None, :]
    mask = (y > h).astype(float)
    m = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2 + i))
    mask = np.asarray(m) / 255.0
    depth = np.clip((y - h) / 0.25, 0, 1)               # fog thins toward the ridge bottom
    layer = np.array(col) + (1 - depth[..., None]) * fog * np.array([30, 38, 50])
    img = img * (1 - mask[..., None]) + layer * mask[..., None]
# vignette + grain
v = 1 - 0.45 * (((x - 0.5) * 1.2) ** 2 + ((y - 0.5) * 1.1) ** 2)
img *= np.clip(v, 0.55, 1)[..., None]
img += rng.normal(0, 2.2, (H, W, 1))
im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
im.save(out, optimize=True)
print(out)
