# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
from PIL import Image, ImageDraw, ImageFont
import sys
sys.stdout.reconfigure(encoding="utf-8")

def make(size, path):
    img = Image.new("RGB", (size, size), "#2563eb")
    d = ImageDraw.Draw(img)
    pad = size * 0.18
    w, h = size - pad * 2, (size - pad * 2) * 0.62
    top = (size - h) / 2
    d.rounded_rectangle([pad, top, pad + w, top + h], radius=size * 0.06, fill="#ffffff")
    # 三条“文字线”
    lx0 = pad + w * 0.12
    for i, frac in enumerate((0.30, 0.50, 0.70)):
        lw = w * (0.55 if i < 2 else 0.38)
        y = top + h * frac
        d.rounded_rectangle([lx0, y, lx0 + lw, y + size * 0.035], radius=size * 0.02, fill="#94a3b8")
    # 扫描线
    sy = top + h * 0.86
    d.rounded_rectangle([pad, sy, pad + w, sy + size * 0.045], radius=size * 0.02, fill="#16a34a")
    img.save(path)

make(192, "server/static/icon-192.png")
make(512, "server/static/icon-512.png")
print("icons ok")
