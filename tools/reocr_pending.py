# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys, json, sqlite3
from pathlib import Path
sys.path.insert(0, "tools")
from ocr_bench import load_engine, ocr_one, extract_fields

sys.stdout.reconfigure(encoding="utf-8")
eng = load_engine()
db = sqlite3.connect("data/cards.db")
db.row_factory = sqlite3.Row
rows = db.execute("SELECT id, tmp_path, status FROM pending_item WHERE tmp_path IS NOT NULL").fetchall()
print("re-ocr rows:", len(rows))
for r in rows:
    p = Path(r["tmp_path"])
    if not p.exists():
        print("  skip missing", p.name)
        continue
    blocks, ms = ocr_one(eng, p)
    f = extract_fields(blocks)
    db.execute("UPDATE pending_item SET fields_json=? WHERE id=?",
               (json.dumps({"blocks": blocks, "fields": f, "elapsed_ms": ms}, ensure_ascii=False), r["id"]))
    print(f"  {p.name[:10]} phones={f['phones']} name={f['name']}")
db.commit()
db.close()
