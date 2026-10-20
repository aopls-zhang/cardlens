# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
"""名片 OCR 服务 (里程碑 W1)

启动:
    python server/app.py
    http://<本机局域网IP>:17800/          手机页面
    http://127.0.0.1:17800/docs          API 文档
"""
import hashlib, io, json, sqlite3, sys, threading, time, uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

# PyInstaller 冻结后 __file__ 在临时解压目录，静态资源在那里；数据目录要放在 exe 旁边
FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parent.parent
if not FROZEN:
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_bench import decode_qr, extract_fields, load_engine, ocr_one  # noqa: E402

DATA = (Path(sys.executable).parent / "data") if FROZEN else (ROOT / "data")
TMP = DATA / "tmp"
DATA.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA / "cards.db"

DEV_ID = "win-0001"
TTL_SECONDS = 24 * 3600
MAX_PENDING = 20

_engine = None
_init_lock = threading.Lock()
_infer_lock = threading.Lock()
_db_lock = threading.Lock()

app = FastAPI(title="CardScan OCR", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ---------------------------------------------------------------- storage
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS device (
  dev_id TEXT PRIMARY KEY, name TEXT NOT NULL, pubkey TEXT,
  paired_at INTEGER, last_sync INTEGER
);
CREATE TABLE IF NOT EXISTS contact (
  id TEXT PRIMARY KEY, name TEXT, company TEXT, title TEXT, dept TEXT,
  phones TEXT, tels TEXT, fax TEXT, wechat TEXT, whatsapp TEXT,
  emails TEXT, addresses TEXT, webs TEXT, note TEXT, tags TEXT,
  search_text TEXT, created_hlc TEXT NOT NULL, updated_hlc TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0, deleted_hlc TEXT,
  source_dev TEXT, source_kind TEXT, ocr_engine TEXT, ocr_conf REAL,
  verified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS contact_field (
  contact_id TEXT NOT NULL, field TEXT NOT NULL, idx INTEGER NOT NULL DEFAULT 0,
  value TEXT, conf REAL, hlc TEXT NOT NULL, dev_id TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (contact_id, field, idx)
);
CREATE TABLE IF NOT EXISTS sync_state (
  dev_id TEXT PRIMARY KEY, watermark TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imported_photo (
  sha256 TEXT PRIMARY KEY, first_seen INTEGER NOT NULL,
  contact_id TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS pending_item (
  id TEXT PRIMARY KEY, photo_sha256 TEXT NOT NULL, tmp_path TEXT,
  status TEXT, source TEXT, fields_json TEXT,
  created_at INTEGER, expires_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_item(status);
"""


def init_db():
    with _db_lock:
        conn = db()
        conn.executescript(SCHEMA)
        # 旧库补列
        cols = [r[1] for r in conn.execute("PRAGMA table_info(contact)")]
        for col in ("tels", "fax", "wechat", "whatsapp"):
            if col not in cols:
                conn.execute("ALTER TABLE contact ADD COLUMN " + col + " TEXT")
        conn.commit()
        conn.close()


def now_ms() -> int:
    return int(time.time() * 1000)


def hlc_now() -> str:
    return f"{now_ms():016x}-0000-{DEV_ID}"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def normalize_image(raw: bytes) -> bytes:
    """修正 EXIF 方向 + 限长边 2500 + 转 JPEG。"""
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    scale = 2500.0 / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


# ---------------------------------------------------------------- ocr
def get_engine():
    global _engine
    if _engine is None:
        with _init_lock:
            if _engine is None:
                _engine = load_engine()
    return _engine


def run_ocr(path: Path):
    eng = get_engine()
    with _infer_lock:          # onnxruntime session 不保证可重入，串行推理
        blocks, ms = ocr_one(eng, path)
    fields = extract_fields(blocks)
    return {"blocks": blocks, "fields": fields, "elapsed_ms": ms,
            "qr": decode_qr(path)}


def process_pending(pid: str):
    conn = db()
    try:
        row = conn.execute("SELECT * FROM pending_item WHERE id=?", (pid,)).fetchone()
        if not row:
            return
        try:
            result = run_ocr(Path(row["tmp_path"]))
            # 文本块太少 = 没拍到名片/糊了/空白，直接判失败，不进待核对队列
            status = "ocr_done" if len(result.get("blocks") or []) >= 3 else "failed"
            conn.execute(
                "UPDATE pending_item SET status=?, fields_json=? WHERE id=?",
                (status, json.dumps(result, ensure_ascii=False), pid),
            )
        except Exception as e:
            conn.execute(
                "UPDATE pending_item SET status='failed', fields_json=? WHERE id=?",
                (json.dumps({"error": str(e)}), pid),
            )
        conn.commit()
    finally:
        conn.close()


def cleanup_expired():
    conn = db()
    try:
        rows = conn.execute(
            "SELECT id, tmp_path FROM pending_item WHERE expires_at < ?", (now_ms(),)
        ).fetchall()
        for r in rows:
            p = Path(r["tmp_path"]) if r["tmp_path"] else None
            if p and p.exists():
                p.unlink(missing_ok=True)
            conn.execute("DELETE FROM pending_item WHERE id=?", (r["id"],))
        conn.commit()
    finally:
        conn.close()


def pending_count(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) c FROM pending_item WHERE status IN ('queued','ocr_done')"
    ).fetchone()["c"]


# ---------------------------------------------------------------- models
class Channel(BaseModel):
    kind: str = "mobile"
    value: str = ""


class ConfirmPayload(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    companies: List[str] = Field(default_factory=list)
    title: Optional[str] = None
    dept: Optional[str] = None
    note: Optional[str] = None
    # 联系方式：类型由用户决定（手机/电话/传真/微信/WhatsApp/邮箱/网站/其他）
    channels: List[Channel] = Field(default_factory=list)
    # 名片之外补充的字段（聊出来的信息），键就是字段名
    custom: Dict[str, str] = Field(default_factory=dict)


# 注意：一个列只能对应一个 kind，否则字典推导会互相覆盖（other 曾把 tel 清空）
KIND_TO_COL = {
    "mobile": "phones", "tel": "tels", "fax": "fax",
    "wechat": "wechat", "whatsapp": "whatsapp",
    "email": "emails", "web": "webs", "address": "addresses",
}


SINGLE_FIELDS = [("name", "name"), ("company", "company"), ("title", "title"),
                 ("dept", "dept"), ("note", "note")]
MULTI_FIELDS = [("phones", "phone"), ("tels", "tel"), ("fax", "fax"),
                ("wechat", "wechat"), ("whatsapp", "whatsapp"),
                ("emails", "email"), ("addresses", "address"),
                ("webs", "web"), ("tags", "tag")]


def write_contact(payload: ConfirmPayload, sha: str, source: str, ocr_engine: str):
    cid = str(uuid.uuid4())
    hlc = hlc_now()
    d = payload.model_dump()

    groups: Dict[str, List[str]] = {}
    for ch in payload.channels:
        v = (ch.value or "").strip()
        if v:
            groups.setdefault(ch.kind or "other", []).append(v)

    proj = {col: json.dumps(groups.get(kind, []), ensure_ascii=False)
            for kind, col in KIND_TO_COL.items()}

    search = " ".join(
        [str(d.get(k) or "") for k, _ in SINGLE_FIELDS]
        + [v for vals in groups.values() for v in vals]
        + [str(v) for v in d["custom"].values()]
    ).strip()

    conn = db()
    with _db_lock:
        conn.execute(
            """INSERT INTO contact (id,name,company,title,dept,phones,tels,fax,wechat,
               whatsapp,emails,addresses,webs,note,tags,search_text,created_hlc,
               updated_hlc,source_dev,source_kind,ocr_engine,ocr_conf,verified)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (cid, d["name"], d["company"], d["title"], d["dept"],
             proj["phones"], proj["tels"], proj["fax"], proj["wechat"],
             proj["whatsapp"], proj["emails"], proj["addresses"], proj["webs"],
             d["note"], json.dumps([], ensure_ascii=False),
             search, hlc, hlc, DEV_ID, source, ocr_engine, None),
        )
        for key, field in SINGLE_FIELDS:
            val = d.get(key)
            conn.execute(
                """INSERT INTO contact_field (contact_id,field,idx,value,conf,hlc,dev_id,deleted)
                   VALUES (?,?,?,?,?,?,?,0)""",
                (cid, field, 0, val, 1.0 if val else None, hlc, DEV_ID),
            )
        # 一家名片可能属于多个主体（同一集团下的不同公司）
        extra_co = [c.strip() for c in (d.get("companies") or []) if c and c.strip()]
        if len(extra_co) > 1:
            for i, cval in enumerate(extra_co[1:], start=1):
                conn.execute(
                    """INSERT INTO contact_field (contact_id,field,idx,value,conf,hlc,dev_id,deleted)
                       VALUES (?,?,?,?,?,?,?,0)""",
                    (cid, "company", i, cval, 1.0, hlc, DEV_ID),
                )
        # 联系方式按用户选定的类型落库，类型即 field
        for kind, vals in groups.items():
            for i, val in enumerate(vals):
                conn.execute(
                    """INSERT INTO contact_field (contact_id,field,idx,value,conf,hlc,dev_id,deleted)
                       VALUES (?,?,?,?,?,?,?,0)""",
                    (cid, kind, i, val, 1.0, hlc, DEV_ID),
                )
        # 名片外补充的字段
        for key, val in (d["custom"] or {}).items():
            k = (key or "").strip()
            v = (val or "").strip()
            if k and v:
                conn.execute(
                    """INSERT INTO contact_field (contact_id,field,idx,value,conf,hlc,dev_id,deleted)
                       VALUES (?,?,?,?,?,?,?,0)""",
                    (cid, "custom:" + k, 0, v, 1.0, hlc, DEV_ID),
                )
        conn.execute(
            "UPDATE imported_photo SET contact_id=?, status='done' WHERE sha256=?",
            (cid, sha),
        )
        conn.commit()
        conn.close()
    return cid


# ---------------------------------------------------------------- routes
HTTPS_PORT = 17801


@app.get("/api/netinfo")
def netinfo():
    from certs import lan_ip
    ip = lan_ip()
    return {"ip": ip, "http_port": 17800, "https_port": HTTPS_PORT,
            "http": f"http://{ip}:17800", "https": f"https://{ip}:{HTTPS_PORT}"}


@app.get("/api/qr")
def qr(target: str = "https"):
    from certs import lan_ip
    import io
    import qrcode
    ip = lan_ip()
    if target == "app":
        url = f"http://{ip}:17800/app.apk"
    elif target == "http":
        url = f"http://{ip}:17800/"
    else:
        url = f"https://{ip}:{HTTPS_PORT}/"
    img = qrcode.make(url, box_size=9, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.get("/app.apk")
def download_apk():
    p = ROOT / "server" / "static" / "cardscan.apk"
    if not p.exists():
        raise HTTPException(404, "APK not built yet")
    return FileResponse(p, media_type="application/vnd.android.package-archive",
                        filename="cardscan.apk")


@app.get("/manifest.json")
def manifest():
    p = ROOT / "server" / "static" / "manifest.json"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/manifest+json", headers=NO_CACHE)


@app.get("/icon-{size}.png")
def pwa_icon(size: int):
    p = ROOT / "server" / "static" / ("icon-%d.png" % size)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


@app.get("/scan.html")
def scan_page():
    page = ROOT / "server" / "static" / "scan.html"
    if not page.exists():
        raise HTTPException(404, "scan page missing")
    return FileResponse(page, headers=NO_CACHE)


@app.get("/capture")
def capture_page():
    page = ROOT / "server" / "static" / "capture.html"
    if not page.exists():
        raise HTTPException(404, "capture page missing")
    return FileResponse(page, headers=NO_CACHE)


NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}


@app.get("/")
def index():
    page = ROOT / "server" / "static" / "index.html"
    if page.exists():
        return FileResponse(page, headers=NO_CACHE)
    return RedirectResponse("/docs")


@app.get("/api/health")
def health():
    conn = db()
    try:
        return {
            "ok": True, "dev_id": DEV_ID, "engine": "rapidocr",
            "pending": pending_count(conn),
            "contacts": conn.execute("SELECT COUNT(*) c FROM contact").fetchone()["c"],
        }
    finally:
        conn.close()


@app.post("/api/ingest")
async def ingest(files: List[UploadFile] = File(...), source: str = "gallery"):
    cleanup_expired()
    conn = db()
    out = []
    try:
        for f in files:
            raw = await f.read()
            if not raw:
                out.append({"file": f.filename, "status": "empty"})
                continue
            sha = sha256_bytes(raw)

            dup = conn.execute(
                "SELECT contact_id, status FROM imported_photo WHERE sha256=?", (sha,)
            ).fetchone()
            if dup:
                out.append({
                    "file": f.filename, "status": "duplicate",
                    "sha256": sha, "contact_id": dup["contact_id"],
                })
                continue

            if pending_count(conn) >= MAX_PENDING:
                out.append({"file": f.filename, "status": "queue_full"})
                continue

            try:
                norm = normalize_image(raw)
            except Exception as e:
                out.append({"file": f.filename, "status": "bad_image", "error": str(e)})
                continue

            tmp_path = TMP / f"{sha}.jpg"
            tmp_path.write_bytes(norm)

            pid = str(uuid.uuid4())
            ts = now_ms()
            conn.execute(
                """INSERT INTO pending_item (id,photo_sha256,tmp_path,status,source,
                   fields_json,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?)""",
                (pid, sha, str(tmp_path), "queued", source, None, ts, ts + TTL_SECONDS * 1000),
            )
            conn.execute(
                "INSERT INTO imported_photo (sha256,first_seen,contact_id,status) VALUES (?,?,?,?)",
                (sha, ts, None, "pending"),
            )
            conn.commit()
            threading.Thread(target=process_pending, args=(pid,), daemon=True).start()
            out.append({
                "file": f.filename, "status": "queued", "sha256": sha,
                "pending_id": pid, "url": f"/api/pending/{pid}/image",
            })
        return {"items": out}
    finally:
        conn.close()


@app.get("/api/pending")
def list_pending(status: str = ""):
    cleanup_expired()
    conn = db()
    try:
        sql = "SELECT * FROM pending_item WHERE status != 'done'"
        args = []
        if status:
            sql = "SELECT * FROM pending_item WHERE status=?"
            args.append(status)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, args).fetchall()
        items = []
        for r in rows:
            fj = json.loads(r["fields_json"]) if r["fields_json"] else None
            items.append({
                "id": r["id"], "status": r["status"], "source": r["source"],
                "sha256": r["photo_sha256"], "created_at": r["created_at"],
                "image_url": f"/api/pending/{r['id']}/image",
                "result": fj,
            })
        return {"items": items, "max": MAX_PENDING}
    finally:
        conn.close()


@app.get("/api/pending/{pid}/image")
def pending_image(pid: str):
    conn = db()
    try:
        r = conn.execute(
            "SELECT tmp_path FROM pending_item WHERE id=?", (pid,)
        ).fetchone()
    finally:
        conn.close()
    if not r or not r["tmp_path"] or not Path(r["tmp_path"]).exists():
        raise HTTPException(404, "image gone")
    return FileResponse(r["tmp_path"])


class IdsPayload(BaseModel):
    ids: List[str] = Field(default_factory=list)


@app.post("/api/pending/batch/discard")
def batch_discard(payload: IdsPayload):
    conn = db()
    n = 0
    try:
        for pid in payload.ids:
            r = conn.execute("SELECT tmp_path FROM pending_item WHERE id=?", (pid,)).fetchone()
            if not r:
                continue
            if r["tmp_path"]:
                Path(r["tmp_path"]).unlink(missing_ok=True)
            conn.execute("UPDATE pending_item SET status='done', tmp_path=NULL WHERE id=?", (pid,))
            n += 1
        conn.commit()
        return {"ok": True, "deleted": n}
    finally:
        conn.close()


@app.post("/api/pending/clear")
def clear_pending():
    conn = db()
    try:
        rows = conn.execute("SELECT id, tmp_path FROM pending_item").fetchall()
        for r in rows:
            if r["tmp_path"]:
                Path(r["tmp_path"]).unlink(missing_ok=True)
        conn.execute("DELETE FROM pending_item")
        conn.execute("DELETE FROM imported_photo WHERE status='pending'")
        conn.commit()
        return {"ok": True, "deleted": len(rows)}
    finally:
        conn.close()


@app.post("/api/contacts/batch/delete")
def batch_delete_contacts(payload: IdsPayload):
    conn = db()
    n = 0
    try:
        hlc = hlc_now()
        for cid in payload.ids:
            if not conn.execute("SELECT id FROM contact WHERE id=? AND deleted=0", (cid,)).fetchone():
                continue
            conn.execute("UPDATE contact SET deleted=1, deleted_hlc=? WHERE id=?", (hlc, cid))
            conn.execute("UPDATE contact_field SET deleted=1, hlc=? WHERE contact_id=?", (hlc, cid))
            n += 1
        conn.commit()
        return {"ok": True, "deleted": n}
    finally:
        conn.close()


@app.get("/api/pending/{pid}")
def pending_detail(pid: str):
    conn = db()
    try:
        r = conn.execute("SELECT * FROM pending_item WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "pending not found")
        fj = json.loads(r["fields_json"]) if r["fields_json"] else None
        return {
            "id": r["id"], "status": r["status"], "source": r["source"],
            "image_url": "/api/pending/" + r["id"] + "/image", "result": fj,
        }
    finally:
        conn.close()


@app.post("/api/pending/{pid}/confirm")
def confirm(pid: str, payload: ConfirmPayload):
    conn = db()
    try:
        r = conn.execute("SELECT * FROM pending_item WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "pending not found")
        if r["status"] == "done":
            raise HTTPException(409, "already confirmed")

        cid = write_contact(payload, r["photo_sha256"], r["source"] or "gallery", "rapidocr")

        p = Path(r["tmp_path"]) if r["tmp_path"] else None
        if p and p.exists():
            p.unlink(missing_ok=True)

        with _db_lock:
            conn.execute("UPDATE pending_item SET status='done', tmp_path=NULL WHERE id=?", (pid,))
            conn.commit()
        return {"ok": True, "contact_id": cid}
    finally:
        conn.close()


@app.post("/api/pending/{pid}/discard")
def discard(pid: str):
    conn = db()
    try:
        r = conn.execute("SELECT * FROM pending_item WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "pending not found")
        p = Path(r["tmp_path"]) if r["tmp_path"] else None
        if p and p.exists():
            p.unlink(missing_ok=True)
        with _db_lock:
            conn.execute("UPDATE pending_item SET status='done', tmp_path=NULL WHERE id=?", (pid,))
            conn.execute(
                "UPDATE imported_photo SET status='discarded' WHERE sha256=?",
                (r["photo_sha256"],),
            )
            conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/contacts")
def contacts(q: str = "", limit: int = 60, offset: int = 0):
    conn = db()
    try:
        where, args = "deleted=0", []
        q = (q or "").strip()
        if q:
            where += " AND search_text LIKE ?"
            args.append("%" + q + "%")
        total = conn.execute("SELECT COUNT(*) c FROM contact WHERE " + where, args).fetchone()["c"]
        rows = conn.execute(
            "SELECT id,name,company,title,dept,phones,tels,fax,wechat,whatsapp,emails,"
            "addresses,webs,note,source_kind,created_hlc FROM contact WHERE " + where +
            " ORDER BY created_hlc DESC LIMIT ? OFFSET ?",
            args + [limit, offset],
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            for k in ("phones", "tels", "fax", "wechat", "whatsapp",
                      "emails", "addresses", "webs"):
                try:
                    d[k] = json.loads(d[k]) if d.get(k) else []
                except Exception:
                    d[k] = []
            items.append(d)
        return {"items": items, "total": total}
    finally:
        conn.close()


@app.post("/api/contacts/create")
def create_contact(payload: ConfirmPayload):
    """手动录入：不走拍照/OCR，直接建一条联系人。"""
    if not (payload.name or payload.company or payload.channels):
        raise HTTPException(400, "empty contact")
    cid = write_contact(payload, "", "manual", "none")
    return {"ok": True, "contact_id": cid}


@app.delete("/api/contacts/{cid}")
def delete_contact(cid: str):
    conn = db()
    try:
        row = conn.execute("SELECT id FROM contact WHERE id=?", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "contact not found")
        hlc = hlc_now()
        # 软删除 + 墓碑：物理删除会让"删除"这个动作永远同步不出去
        conn.execute("UPDATE contact SET deleted=1, deleted_hlc=? WHERE id=?", (hlc, cid))
        conn.execute("UPDATE contact_field SET deleted=1, hlc=? WHERE contact_id=?", (hlc, cid))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/contacts/{cid}")
def contact_detail(cid: str):
    conn = db()
    try:
        row = conn.execute("SELECT * FROM contact WHERE id=?", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "contact not found")
        d = dict(row)
        channels, custom = [], {}
        for f in conn.execute(
            "SELECT field, idx, value FROM contact_field WHERE contact_id=? AND deleted=0 ORDER BY field, idx",
            (cid,),
        ):
            name = f["field"]
            if name.startswith("custom:"):
                custom[name[7:]] = f["value"]
            elif name in ("name", "company", "title", "dept", "note"):
                continue
            else:
                channels.append({"kind": name, "value": f["value"]})
        d["channels"] = channels
        d["custom"] = custom
        return d
    finally:
        conn.close()


init_db()

if __name__ == "__main__":
    import threading
    import uvicorn
    from uvicorn import Config, Server
    from certs import ensure_cert

    cert, key, ip = ensure_cert(DATA / "certs")
    # 同一进程再起一个 HTTPS 端口：手机浏览器扫码后跑在安全上下文里，摄像头才可用
    https_cfg = Config(app, host="0.0.0.0", port=HTTPS_PORT,
                       ssl_certfile=cert, ssl_keyfile=key, log_level="warning")
    threading.Thread(target=Server(https_cfg).run, daemon=True).start()

    # 控制台编码在部分 Windows 上是 cp1252，这里只输出 ASCII
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(f"[cardscan] HTTP  http://{ip}:17800")
    print(f"[cardscan] HTTPS https://{ip}:{HTTPS_PORT}   (use this for QR)")
    print("[cardscan] author: aopls-zhang | license: GPL-3.0-or-later")
    uvicorn.run(app, host="0.0.0.0", port=17800)
