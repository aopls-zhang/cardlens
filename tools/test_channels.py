# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys, json, sqlite3
sys.path.insert(0, "tools")
from test_api import req
sys.stdout.reconfigure(encoding="utf-8")

items = req("GET", "/api/pending")["items"]
target = None
for it in items:
    if it["status"] == "ocr_done" and it.get("result"):
        target = it
        break
if not target:
    print("no pending")
    raise SystemExit

payload = {
    "name": "王云涛", "company": "南京方通科技有限公司", "title": "经理", "dept": "市场部",
    "note": "展会上聊的，主做叉车配件",
    "channels": [
        {"kind": "mobile", "value": "13584007100"},
        {"kind": "tel", "value": "025-83468121"},
        {"kind": "wechat", "value": "wyt_1988"},
        {"kind": "whatsapp", "value": "+86 135 8400 7100"},
        {"kind": "email", "value": "Wnhoo@163.com"},
        {"kind": "address", "value": "南京市浦口区浦珠南路6号"},
    ],
    "custom": {"公司主营": "叉车配件、仓储设备", "认识场合": "2026 南京物流展"},
}
body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
r = req("POST", "/api/pending/" + target["id"] + "/confirm", body, {"Content-Type": "application/json"})
print("confirm:", json.dumps(r, ensure_ascii=False))
print("status:", [x["status"] for x in req("GET", "/api/pending")["items"] if x["id"] == target["id"]])

db = sqlite3.connect("data/cards.db")
db.row_factory = sqlite3.Row
row = db.execute("SELECT * FROM contact ORDER BY created_hlc DESC LIMIT 1").fetchone()
print("\ncontact:")
for k in ("name", "company", "title", "dept", "phones", "tels", "wechat", "whatsapp", "emails", "addresses", "note"):
    print(f"  {k:9} = {row[k]}")
print("\ncontact_field:")
for r in db.execute("SELECT field, idx, value FROM contact_field WHERE contact_id=?", (row["id"],)):
    print(f"  {r['field']:<16} [{r['idx']}] {r['value']}")
