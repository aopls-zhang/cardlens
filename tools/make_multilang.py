# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
"""生成多语种名片样图，用于检验 OCR 字符集覆盖度"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path("samples/multilang")
OUT.mkdir(parents=True, exist_ok=True)
FP = "C:/Windows/Fonts/msyh.ttc"
FPB = "C:/Windows/Fonts/msyhbd.ttc"

CARDS = {
    "zh_cn": dict(
        name="张伟", title="技术总监", company="杭州云启科技有限公司",
        lines=["手机: 138 1234 5678", "邮箱: zhangwei@yunqi-tech.com",
               "地址: 杭州市余杭区文一西路 969 号"],
        accent="#1e40af"),
    "zh_tw": dict(
        name="陳美玲", title="業務總監", company="臺灣雲啟科技股份有限公司",
        lines=["手機: 0912 345 678", "信箱: meiling@yunqi-tech.tw",
               "地址: 臺北市信義區松高路 1 號"],
        accent="#0f766e"),
    "en": dict(
        name="John Smith", title="Sales Director", company="Acme Global Inc.",
        lines=["Mobile: +1 415 555 0123", "Email: john.smith@acme-global.com",
               "Address: 500 Market St, San Francisco, CA 94105"],
        accent="#b91c1c"),
    "fr": dict(
        name="Jean-Pierre Dupont", title="Directeur Commercial",
        company="Dupont & Associés SARL",
        lines=["Tél. +33 1 23 45 67 89", "Mob. +33 6 12 34 56 78",
               "Courriel: jean.dupont@dupont-associes.fr",
               "Adresse: 12 rue de la Paix, 75002 Paris"],
        accent="#7c3aed"),
    "es": dict(
        name="José María García", title="Director General",
        company="García y Asociados S.L.",
        lines=["Teléfono: +34 91 234 56 78", "Móvil: +34 612 345 678",
               "Correo: jose.garcia@gyas.es",
               "Dirección: Calle Mayor 45, 28013 Madrid"],
        accent="#c2410c"),
}


def make(key, c):
    W, H = 1000, 600
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_name = ImageFont.truetype(FPB, 68)
    f_co = ImageFont.truetype(FP, 36)
    f_sm = ImageFont.truetype(FP, 27)

    d.rectangle((0, 0, W, 12), fill=c["accent"])
    d.text((55, 55), c["name"], font=f_name, fill="#111")
    d.text((55, 150), c["title"], font=f_sm, fill="#555")
    d.text((55, 195), c["company"], font=f_co, fill="#222")
    d.line((55, 265, 945, 265), fill="#ddd", width=2)
    y = 295
    for ln in c["lines"]:
        d.text((55, y), ln, font=f_sm, fill="#333")
        y += 52
    img.save(OUT / f"{key}.png")
    return OUT / f"{key}.png"


for k, v in CARDS.items():
    print("made", make(k, v))
