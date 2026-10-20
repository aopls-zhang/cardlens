# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys
sys.path.insert(0, "tools")
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import qrcode

sys.stdout.reconfigure(encoding="utf-8")

# 造一张带二维码的名片
fp = "C:/Windows/Fonts/msyh.ttc"
img = Image.new("RGB", (1000, 600), "white")
d = ImageDraw.Draw(img)
f1, f2, f3 = ImageFont.truetype(fp, 60), ImageFont.truetype(fp, 30), ImageFont.truetype(fp, 24)
d.text((60, 60), "范利锋", font=f1, fill="#111")
d.text((60, 150), "副总经理", font=f2, fill="#333")
d.text((60, 200), "华为(中国广州)有限公司", font=f2, fill="#222")
d.text((60, 260), "手机：15876663000", font=f3, fill="#333")
d.text((60, 300), "邮箱：7188866600@qq.com", font=f3, fill="#333")
d.text((60, 340), "地址：广州市白云区机杨路168松柏工贸城北区五号", font=f3, fill="#333")

qr = qrcode.make("https://card.example.com/v/7188866600")
qr = qr.resize((200, 200))
img.paste(qr.convert("RGB"), (760, 200))
img.save("samples/card_qr.png")

from ocr_bench import load_engine, ocr_one, extract_fields, decode_qr
eng = load_engine()
blocks, ms = ocr_one(eng, Path("samples/card_qr.png"))
f = extract_fields(blocks)
print("name:", f.get("name"), "| company:", f.get("company"))
print("qr:", decode_qr(Path("samples/card_qr.png")))
