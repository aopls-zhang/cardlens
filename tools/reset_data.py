# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys, sqlite3, shutil
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

db = sqlite3.connect("data/cards.db")
for t in ("pending_item", "contact_field", "contact", "imported_photo"):
    n = db.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
    db.execute("DELETE FROM " + t)
    print(f"cleared {t}: {n}")
db.commit()
db.execute("VACUUM")
db.close()

tmp = Path("data/tmp")
if tmp.exists():
    n = len(list(tmp.glob("*")))
    shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    print("removed tmp files:", n)
print("reset done")
