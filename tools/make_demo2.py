# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
from PIL import Image, ImageDraw, ImageFont
fp = "C:/Windows/Fonts/msyh.ttc"
img = Image.new("RGB", (1000, 600), "white")
d = ImageDraw.Draw(img)
f1, f2, f3 = ImageFont.truetype(fp, 74), ImageFont.truetype(fp, 40), ImageFont.truetype(fp, 28)
d.rectangle((0, 0, 1000, 14), fill="#1e40af")
d.text((60, 60), "李娜", font=f1, fill="#111")
d.text((60, 168), "市场总监  MARKETING DIRECTOR", font=f3, fill="#555")
d.text((60, 215), "上海启明文化传播有限公司", font=f2, fill="#222")
d.line((60, 300, 940, 300), fill="#ddd", width=2)
d.text((60, 330), "手机 139 8888 6666", font=f3, fill="#333")
d.text((60, 375), "电话 021-6688 9900", font=f3, fill="#333")
d.text((60, 420), "邮箱 lina@qiming-media.cn", font=f3, fill="#333")
d.text((60, 465), "地址 上海市静安区南京西路 1266 号", font=f3, fill="#333")
d.text((60, 510), "www.qiming-media.cn", font=f3, fill="#1e40af")
img.save("samples/card_demo2.png")
print("ok")
