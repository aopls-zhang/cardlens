# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys, json, time
sys.path.insert(0, "tools")
from pathlib import Path
from test_api import upload, req

ids = []
for p in sorted(Path("samples/multilang").glob("*.png")):
    r = upload(p)
    it = r["items"][0]
    ids.append(it["pending_id"])
    print(p.stem, it["status"])

for _ in range(60):
    time.sleep(1)
    items = req("GET", "/api/pending")["items"]
    if all(x["status"] in ("ocr_done", "failed") for x in items if x["id"] in ids):
        break

for x in items:
    f = (x["result"] or {}).get("fields", {})
    print(json.dumps({"id": x["id"], "status": x["status"],
                      "name": f.get("name"), "company": f.get("company"),
                      "title": f.get("title"), "phones": f.get("phones"),
                      "address": f.get("address")}, ensure_ascii=False))
