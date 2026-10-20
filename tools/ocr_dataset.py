# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys, json, time
from pathlib import Path
sys.path.insert(0, "tools")
from ocr_bench import load_engine, ocr_one, extract_fields

sys.stdout.reconfigure(encoding="utf-8")
man = json.loads(Path("数据/cards_manifest.json").read_text(encoding="utf-8"))
eng = load_engine()

results = []
t0 = time.time()
for i, m in enumerate(man):
    p = Path(m["path"])
    try:
        blocks, ms = ocr_one(eng, p)
        f = extract_fields(blocks)
    except Exception as e:
        results.append({"path": m["path"], "error": str(e)})
        continue
    results.append({
        "path": m["path"], "sheet": m["sheet"], "idx": m["idx"],
        "ms": ms, "n_blocks": len(blocks),
        "blocks": [{"t": b["text"], "s": b["score"]} for b in blocks],
        "fields": f,
    })
    if (i + 1) % 20 == 0:
        print(f"  {i+1}/{len(man)}  {time.time()-t0:.0f}s", flush=True)

Path("数据/ocr_results.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")

ok = [r for r in results if "error" not in r]
print("\ntotal:", len(results), "errors:", len(results) - len(ok), "elapsed:", round(time.time()-t0, 1), "s")
print("avg ms:", round(sum(r["ms"] for r in ok) / max(1, len(ok)), 1))
print("avg blocks:", round(sum(r["n_blocks"] for r in ok) / max(1, len(ok)), 1))

def has(r, k):
    v = r["fields"].get(k)
    return bool(v) and (len(v) > 0 if isinstance(v, list) else True)

for k in ("name", "company", "title", "phones", "emails", "address"):
    n = sum(1 for r in ok if has(r, k))
    print(f"  {k:8} {n:3d}/{len(ok)} ({n/max(1,len(ok))*100:.0f}%)")

empty = [r for r in ok if not any(has(r, k) for k in ("name", "company", "phones", "emails"))]
print("empty results:", len(empty))
for r in empty[:5]:
    print("   ", Path(r["path"]).name, "blocks=", r["n_blocks"])
