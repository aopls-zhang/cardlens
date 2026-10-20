# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys, json
sys.path.insert(0, "tools")
from pathlib import Path
from ocr_bench import load_engine, ocr_one, extract_fields

sys.stdout.reconfigure(encoding="utf-8")
eng = load_engine()
for p in sorted(Path("samples/multilang").glob("*.png")):
    blocks, ms = ocr_one(eng, p)
    f = extract_fields(blocks)
    print("=" * 56)
    print(p.stem)
    for k in ("name", "company", "title", "phones", "emails", "urls", "address"):
        print(f"  {k:8} = {f.get(k)}")
    print(f"  conf     = {f.get('_conf')}")
