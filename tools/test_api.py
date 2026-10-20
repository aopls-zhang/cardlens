# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
"""API 回归测试：health -> ingest -> 轮询 -> confirm -> 重复检测"""
import json, sys, time, urllib.request, urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:17800"


def req(method, path, data=None, headers=None):
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode("utf-8", "replace")[:300]}


def upload(path: Path):
    b = "----cardscantest"
    body = ("--%s\r\n" % b).encode()
    body += ('Content-Disposition: form-data; name="files"; filename="%s"\r\n' % path.name).encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += path.read_bytes() + b"\r\n"
    body += ("--%s--\r\n" % b).encode()
    return req("POST", "/api/ingest?source=gallery", body,
               {"Content-Type": "multipart/form-data; boundary=" + b})


def main():
    print("1) health  ", req("GET", "/api/health"))

    img = Path("samples/card_demo.png")
    print("2) ingest  ", json.dumps(upload(img), ensure_ascii=False))
    pid = upload(img)["items"][0].get("pending_id")

    # 第二轮上传同一张，应判重
    # （上一行已再传一次，这里直接读结果）
    dup = upload(img)
    print("3) dup     ", json.dumps(dup, ensure_ascii=False))

    # 从 pending 里找到刚入队的
    pend = req("GET", "/api/pending")
    print("4) pending ", "count=%d" % len(pend.get("items", [])))
    item = pend["items"][0]
    pid = item["id"]

    for _ in range(20):
        if item["status"] in ("ocr_done", "failed"):
            break
        time.sleep(1)
        item = [x for x in req("GET", "/api/pending")["items"] if x["id"] == pid][0]

    print("5) status  ", item["status"])
    res = item.get("result") or {}
    print("   elapsed ", res.get("elapsed_ms"), "ms")
    print("   fields  ", json.dumps(res.get("fields"), ensure_ascii=False))

    payload = {
        "name": "张伟", "company": "杭州云启科技有限公司", "title": "技术总监",
        "dept": None,
        "phones": ["13812345678"], "emails": ["zhangwei@yunqi-tech.com"],
        "addresses": ["杭州市余杭区文一西路969号"],
        "webs": ["www.yunqi-tech.com"], "tags": [], "note": None,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    print("6) confirm ", req("POST", f"/api/pending/{pid}/confirm", body,
                            {"Content-Type": "application/json"}))

    print("7) contacts", json.dumps(req("GET", "/api/contacts"), ensure_ascii=False)[:400])
    print("8) health  ", req("GET", "/api/health"))


if __name__ == "__main__":
    main()
