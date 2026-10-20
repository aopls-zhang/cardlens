# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys, json
import numpy as np, cv2
from pathlib import Path
sys.path.insert(0, "tools")
from detect_cards import detect, imread_u

sys.stdout.reconfigure(encoding="utf-8")
sheets = sorted(Path("数据/extracted").glob("*.jpg"))
out_root = Path("数据/cards")
out_root.mkdir(parents=True, exist_ok=True)

manifest = []
dist = {}
for p in sheets:
    cells = detect(p)
    bgr = imread_u(p)
    # 检出 0–1 块：判定为单张名片特写，整张作为一张
    if len(cells) <= 1:
        h, w = bgr.shape[:2]
        cells = [(0, 0, w, h)]
    d = out_root / p.stem
    d.mkdir(exist_ok=True)
    for i, (x, y, w, h) in enumerate(cells):
        crop = bgr[y:y+h, x:x+w]
        fp = d / f"{i:02d}.jpg"
        cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 92])[1].tofile(str(fp))
        manifest.append({"sheet": p.name, "idx": i, "path": str(fp), "w": w, "h": h})
    dist[len(cells)] = dist.get(len(cells), 0) + 1

Path("数据/cards_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
print("sheets:", len(sheets), " cards:", len(manifest))
print("per-sheet distribution:", dict(sorted(dist.items())))
