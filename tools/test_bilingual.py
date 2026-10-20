# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys
sys.path.insert(0, "tools")
from pathlib import Path
from ocr_bench import load_engine, ocr_one, extract_fields
sys.stdout.reconfigure(encoding="utf-8")
eng = load_engine()
blocks, ms = ocr_one(eng, Path("samples/bilingual.png"))
f = extract_fields(blocks)
for k in ("name", "company", "title", "addresses", "phones", "emails"):
    print(f"  {k:10} = {f.get(k)}")
