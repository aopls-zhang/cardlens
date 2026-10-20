# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
"""用已有 blocks 重新跑抽取，不需要重拍"""
import sys, json, sqlite3
sys.path.insert(0, "tools")
from ocr_bench import extract_fields
sys.stdout.reconfigure(encoding="utf-8")

db = sqlite3.connect("data/cards.db")
db.row_factory = sqlite3.Row
rows = db.execute("SELECT id, fields_json FROM pending_item WHERE fields_json IS NOT NULL").fetchall()
for r in rows:
    d = json.loads(r["fields_json"])
    f = extract_fields(d["blocks"])
    d["fields"] = f
    db.execute("UPDATE pending_item SET fields_json=? WHERE id=?",
               (json.dumps(d, ensure_ascii=False), r["id"]))
    print(f"{f.get('name')} | {f.get('company')} | {f.get('title')}")
    print(f"   地址: {f.get('addresses')}")
    print(f"   电话: {f.get('phones')}  座机: {f.get('tels')}  邮箱: {f.get('emails')}")
db.commit()
