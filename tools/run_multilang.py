# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys
sys.path.insert(0, "tools")
from pathlib import Path
from ocr_bench import load_engine, ocr_one

sys.stdout.reconfigure(encoding="utf-8")
eng = load_engine()
for p in sorted(Path("samples/multilang").glob("*.png")):
    blocks, ms = ocr_one(eng, p)
    print("=" * 60)
    print(p.stem, ms, "ms")
    for b in blocks:
        print(f"  {b['score']:.3f}  {b['text']}")
