# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys
sys.path.insert(0, "tools")
sys.stdout.reconfigure(encoding="utf-8")
from ocr_bench import extract_fields

blocks = [
    {"text": "南京方通科技有限公司", "score": 1.0, "h": 40, "y": 10, "x": 0},
    {"text": "市场部经理", "score": 1.0, "h": 30, "y": 60, "x": 0},
    {"text": "13584007100", "score": 0.999, "h": 22, "y": 130, "x": 0},
    {"text": "025-83468121", "score": 0.995, "h": 22, "y": 160, "x": 0},
    {"text": "王云涛", "score": 1.0, "h": 60, "y": 200, "x": 0},
]
f = extract_fields(blocks)
for k in ("name", "company", "dept", "title", "phones", "tels"):
    print(f"  {k:8} = {f[k]}")
