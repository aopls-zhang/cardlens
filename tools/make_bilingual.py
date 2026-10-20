# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
from PIL import Image, ImageDraw, ImageFont
fp = "C:/Windows/Fonts/msyh.ttc"
img = Image.new("RGB", (1000, 600), "white")
d = ImageDraw.Draw(img)
f1, f2, f3 = ImageFont.truetype(fp, 62), ImageFont.truetype(fp, 30), ImageFont.truetype(fp, 24)
d.text((60, 50), "张瑞德", font=f1, fill="#111")
d.text((60, 140), "总经理", font=f2, fill="#333")
d.text((60, 195), "苏州顶瑞机电商贸有限公司", font=f2, fill="#222")
d.text((60, 240), "SUZHOU DINGRUI MECHATRONICS CO., LTD.", font=f3, fill="#666")
d.line((60, 300, 940, 300), fill="#ddd", width=2)
d.text((60, 320), "地址：苏州市金凤南路289号风华广场11楼", font=f3, fill="#333")
d.text((60, 360), "Address: Room 11, Fenghua Plaza, No.289 Jinfeng South Road, Suzhou", font=f3, fill="#333")
d.text((60, 420), "手机：+86 136 8686 5464", font=f3, fill="#333")
d.text((60, 460), "邮箱：zhangrui@163.com", font=f3, fill="#333")
img.save("samples/bilingual.png")
print("ok")
