# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
"""名片 OCR 摸底工具 (实验 0)

用法:
    python tools/ocr_bench.py --demo                 # 生成样图并识别
    python tools/ocr_bench.py -i samples            # 批量识别目录
    python tools/ocr_bench.py -i samples -o out.json
"""
import argparse, json, re, sys, time
from pathlib import Path

PHONE_CAND = re.compile(r"\+?\d[\d\s\-().]{6,}\d")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL   = re.compile(r"(?:https?://|www\.)[^\s，。]+")

# 公司 / 职位 / 地址 关键词：简体中文 + 繁体（归一化后）+ 英文 + 法文 + 西文
COMPANY_KW = [
    "有限公司", "股份有限公司", "有限", "集团", "科技", "股份", "事务所",
    "工作室", "公司", "实业", "展览", "商行", "商贸", "贸易", "合作社",
    "工厂", "制品厂", "印务", "供应", "供应链",
    "inc", "ltd", "llc", "corp", "corporation", "gmbh", "sarl", "sas",
    "s.a.", "s.l.", "associés", "asociados", "consulting", "group", "groupe",
    "grupo", "company", "co.,",
]
TITLE_KW = [
    "经理", "总监", "主管", "总裁", "董事", "合伙人", "律师", "教授", "顾问",
    "专员", "主任", "工程师", "ceo", "cto", "cfo", "coo", "founder",
    "director", "manager", "directeur", "directrice", "gérant", "président",
    "president", "gerente", "commercial", "engineer",
]
ADDR_KW = ["路", "街", "号", "省", "市", "区", "rue", "avenue", "calle",
           "street", "road", "str.", "boulevard", "paseo", "district", "floor",
           "room", "plaza", "building", "industrial", "lane", "drive"]

# 姓名候选里要排除的英文地址词，否则 "Road, Baiyun District, Guangzhou" 会被当成人名
ADDR_WORDS_EN = ("road", "street", "avenue", "district", "floor", "room",
                 "building", "plaza", "lane", "drive", "city", "industrial",
                 "trade", "north", "south", "east", "west")

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def make_demo(out_dir: Path):
    from PIL import Image, ImageDraw, ImageFont
    out_dir.mkdir(parents=True, exist_ok=True)
    W, H = 1000, 600
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    fp = "C:/Windows/Fonts/msyh.ttc"
    f_name = ImageFont.truetype(fp, 76)
    f_sub  = ImageFont.truetype(fp, 38)
    f_sm   = ImageFont.truetype(fp, 30)

    d.text((60, 70),  "张伟", font=f_name, fill="black")
    d.text((60, 180), "技术总监", font=f_sub, fill="#222")
    d.text((60, 240), "杭州云启科技有限公司", font=f_sub, fill="#222")
    d.line((60, 320, 940, 320), fill="#bbbbbb", width=2)
    d.text((60, 355), "手机: 138 1234 5678", font=f_sm, fill="#333")
    d.text((60, 405), "邮箱: zhangwei@yunqi-tech.com", font=f_sm, fill="#333")
    d.text((60, 455), "地址: 杭州市余杭区文一西路 969 号", font=f_sm, fill="#333")
    d.text((60, 505), "www.yunqi-tech.com", font=f_sm, fill="#333")

    p = out_dir / "card_demo.png"
    img.save(p)
    return p


def load_engine():
    """优先 rapidocr 3.x（PP-OCRv6，简体/繁体/英文都强），回退旧版 v3 模型。"""
    try:
        from rapidocr import RapidOCR as NewOCR
        return {"kind": "v6", "eng": NewOCR()}
    except Exception:
        from rapidocr_onnxruntime import RapidOCR as OldOCR
        return {"kind": "v3", "eng": OldOCR()}


def _mk_block(pts, text, score):
    ys = [p[1] for p in pts]
    xs = [p[0] for p in pts]
    return {
        "text": text,
        "score": round(float(score), 4),
        "box": [[round(float(x), 1), round(float(y), 1)] for x, y in pts],
        "h": round(max(ys) - min(ys), 1),
        "y": round(min(ys), 1),
        "x": round(min(xs), 1),
    }


def ocr_one(engine, path: Path):
    t0 = time.time()
    kind = engine["kind"] if isinstance(engine, dict) else "v3"
    eng = engine["eng"] if isinstance(engine, dict) else engine
    out = eng(str(path))
    ms = int((time.time() - t0) * 1000)

    blocks = []
    if kind == "v6":
        boxes = out.boxes if out.boxes is not None else []
        txts = out.txts if out.txts is not None else []
        scores = out.scores if out.scores is not None else []
        for box, text, score in zip(boxes, txts, scores):
            pts = [[float(p[0]), float(p[1])] for p in box]
            blocks.append(_mk_block(pts, text, score))
    else:
        result = out[0] if isinstance(out, tuple) else out
        for item in (result or []):
            if not item or len(item) < 3:
                continue
            blocks.append(_mk_block(item[0], item[1], item[2]))

    blocks.sort(key=lambda b: (b["y"], b["x"]))
    return blocks, ms


def normalize_text(s: str) -> str:
    """繁体归一成简体，用于关键词匹配；原文仍保留。"""
    try:
        import zhconv
        return zhconv.convert(s, "zh-cn")
    except Exception:
        return s


def _uniq(seq):
    out = []
    for x in seq:
        if x and x not in out:
            out.append(x)
    return out


ADDR_LABEL = re.compile(
    r"^(地址|住址|address|adresse|adres|dirección|direccion|所住地)\s*[:：]?\s*", re.I
)

# 以这些词开头的块是"标签行"，不能当公司名或姓名
LABEL_PREFIX = re.compile(
    r"^(电话|手機|手机|传真|傳真|邮箱|信箱|地址|工厂|網址|网址|QQ|微信|邮编|MAIL|TEL|"
    r"FAX|EMAIL|E-mail|ADD|Adresse|Dirección|http|www|M\.P|手机号)", re.I
)

# 广告/业务话术，不可能是人名
AD_WORDS = ("贷款", "招聘", "批发", "供应", "回收", "维修", "培训", "加盟",
            "代理", "热线", "招商", "主营", "厂家", "直销", "优惠", "办理")

# 职位前缀词：出现在职位块开头时说明前面不是人名
ROLE_PREFIX = ("业务", "销售", "市场", "技术", "大区", "区域", "副总", "高级",
               "资深", "首席", "行政", "财务", "人事", "运营", "生产", "采购",
               "产品", "项目", "渠道", "客户", "大客户", "总")

# "张三销售总监" → 姓名 + 职位
NAME_TITLE = re.compile(
    r"^([\u4e00-\u9fa5]{2,3})(销售|业务|市场|技术|大区|区域|副总|高级|资深|"
    r"总监|经理|主管|董事|总裁|总经理)"
)

# "市场部经理" → 部门 + 职位（必须在 NAME_TITLE 之前判断，否则"市场部"会被当成姓名）
DEPT_TITLE = re.compile(
    r"^(.{2,12}?(?:事业部|分公司|部|科|处|室|中心))\s*(.+)$"
)

# "张瑞德/总经理"、"张瑞德｜销售总监" 这类用分隔符把姓名和职位写在一行的
NAME_TITLE_SEP = re.compile(r"^([\u4e00-\u9fa5]{2,4})\s*[/|｜、·]\s*(.+)$")

# 中英文公司名分开收集，中文优先：双语名片上英文名通常更长，按长度取会选错
CN_COMPANY_KW = ["有限公司", "股份有限公司", "有限", "集团", "科技", "股份",
                 "事务所", "工作室", "公司", "实业", "展览", "商行", "商贸",
                 "贸易", "合作社", "工厂", "印务", "供应"]
EN_COMPANY_KW = ["inc", "ltd", "llc", "corp", "corporation", "co,", "co.",
                 "gmbh", "sarl", "sas", "s.a.", "s.l.", "company", "group"]

# 移动电话特征：中国大陆、台湾、香港、法国、西班牙
MOBILE_PATTERNS = [
    re.compile(r"^(?:86)?1[3-9]\d{9}$"),   # 大陆 13812345678 / +86
    re.compile(r"^(?:886)?9\d{8}$"),       # 台湾 0912 345 678
    re.compile(r"^(?:852)?[4569]\d{7}$"),  # 香港
    re.compile(r"^33[67]\d{8}$"),          # 法国 06/07
    re.compile(r"^34[67]\d{8}$"),          # 西班牙 6xx/7xx
]


WECHAT_LABEL = re.compile(r"(微信|wechat|weixin)", re.I)
WHATSAPP_LABEL = re.compile(r"(whatsapp|whats\s*app)", re.I)

# 各大聊天平台：直接从"标签+账号"里捕获值。
# 名片常把 QQ、手机、网址挤在一行，所以不能用"整块替换"的方式取剩余文本。
IM_EXTRACT = [
    ("qq", re.compile(r"\bqq\s*[:：]?\s*(\d{5,12})", re.I)),
    ("wechat", re.compile(r"(?:微信|wechat|weixin)\s*[:：]?\s*([A-Za-z0-9_\-]{3,30})", re.I)),
    ("whatsapp", re.compile(r"whats\s*app\s*[:：]?\s*(\+?[\d\s\-()]{7,20})", re.I)),
    ("telegram", re.compile(r"telegram\s*[:：]?\s*(@?[A-Za-z0-9_]{3,30})", re.I)),
    ("line", re.compile(r"\bline\s*[:：]?\s*([A-Za-z0-9_.\-]{3,30})", re.I)),
    ("skype", re.compile(r"\bskype\s*[:：]?\s*([A-Za-z0-9_.\-]{3,30})", re.I)),
    ("dingtalk", re.compile(r"钉钉\s*[:：]?\s*([A-Za-z0-9_\-]{3,30})", re.I)),
    ("feishu", re.compile(r"飞书\s*[:：]?\s*([A-Za-z0-9_\-]{3,30})", re.I)),
]

# 提取电话前先从文本里剥掉这些，避免 QQ 号被当成座机（手机号要保留）
IM_STRIP = [re.compile(r"\bqq\s*[:：]?\s*\d{5,12}", re.I)]

PHONE_LABELS = [
    ("fax", re.compile(r"传真|傳真|\bfax\b", re.I)),
    ("mobile", re.compile(r"手机|手機|mobile|móvil|movil|\bmob\b", re.I)),
    ("tel", re.compile(r"电话|電話|座机|\btel\b|téléfono|telefono|\btél\b", re.I)),
]


def classify_phone(digits: str) -> str:
    """区分移动电话与固定电话。去掉前导 0 再判断，否则座机号会误判。"""
    d = digits.lstrip("+")
    trimmed = d[1:] if d.startswith("0") else d
    for pat in MOBILE_PATTERNS:
        if pat.match(d) or pat.match(trimmed):
            return "mobile"
    return "tel"


def decode_qr(path):
    """名片上的二维码：解码成文本，交给核对页作为补充信息保留。"""
    try:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return []
        det = cv2.QRCodeDetector()
        out = []
        try:
            ok, decoded, _, _ = det.detectAndDecodeMulti(img)
            if ok:
                out = [d for d in decoded if d]
        except Exception:
            pass
        if not out:
            try:
                data, _, _ = det.detectAndDecode(img)
                if data:
                    out = [data]
            except Exception:
                pass
        return out
    except Exception:
        return []


def extract_fields(blocks):
    for b in blocks:
        b["_n"] = normalize_text(b["text"])
        b["_low"] = b["_n"].lower()

    full = "\n".join(b["text"] for b in blocks)
    f = {"name": None, "company": None, "companies": [], "title": None, "dept": None,
         "phones": [], "tels": [], "fax": [],
         "wechat": [], "whatsapp": [], "qq": [], "telegram": [], "line": [],
         "skype": [], "dingtalk": [], "feishu": [],
         "emails": [], "urls": [], "address": None}

    f["emails"] = _uniq([m.group(0) for m in EMAIL.finditer(full)])
    f["urls"] = _uniq([m.group(0) for m in URL.finditer(full)])

    # 号码类别：只认"同一个文本块内"的标签（如 "传真：025-xxx"）。
    # 跨块按坐标匹配在竖排/旋转名片上会乱（标签的 y 全挤在一起），不可用。
    for b in blocks:
        kind_hint = None
        for kind, pat in PHONE_LABELS:
            if pat.search(b["text"]):
                kind_hint = kind
                break
        # 先把邮箱和 QQ 号从文本里抠掉：它们的数字会被误当成电话号码
        clean_text = EMAIL.sub(" ", b["text"])
        for pat in IM_STRIP:
            clean_text = pat.sub(" ", clean_text)
        # 逐行匹配：正则里的 \s 会吃换行，导致相邻两行号码被拼成超长串而整条丢弃
        for line in clean_text.split("\n"):
            for m in PHONE_CAND.finditer(line):
                raw = m.group(0).strip(" .,-()")
                digits = re.sub(r"\D", "", raw)
                if 7 <= len(digits) <= 15:
                    v = re.sub(r"\s+", " ", raw).strip()
                    kind = kind_hint or classify_phone(digits)
                    bucket = {"mobile": f["phones"], "tel": f["tels"], "fax": f["fax"]}[kind]
                    if v not in bucket:
                        bucket.append(v)

    # 聊天平台账号
    for b in blocks:
        t = b["text"]
        for key, pat in IM_EXTRACT:
            for m in pat.finditer(t):
                val = m.group(1).strip(" :：,，")
                if val and val not in f[key]:
                    f[key].append(val)

    # 公司：可能是多家（同一集团下的不同主体）。中文名优先，其次英文名。
    # 双语名片的中英文名是同一家公司，所以有中文时不再把英文名也算一条。
    cn_list, en_list = [], []
    for b in blocks:
        if LABEL_PREFIX.match(b["_n"]) or LABEL_PREFIX.match(b["text"].strip()):
            continue
        low = b["_low"]
        txt = b["text"].strip()
        if any(k in low for k in CN_COMPANY_KW):
            if txt not in cn_list:
                cn_list.append(txt)
        elif any(k in low for k in EN_COMPANY_KW):
            if txt not in en_list:
                en_list.append(txt)
    f["companies"] = cn_list if cn_list else en_list
    f["company"] = f["companies"][0] if f["companies"] else None

    # 职位：命中职位词，且不是公司那一行（不再要求字号更小——真实名片上职位常与公司同字号）
    for b in blocks:
        t = b["_n"]
        if not any(k in b["_low"] for k in TITLE_KW):
            continue
        if len(t) > 40 or b["text"].strip() == (f["company"] or ""):
            continue
        if any(k in b["_low"] for k in COMPANY_KW) and len(t) > 12:
            continue
        f["title"] = b["text"].strip()
        break

    # 职位块里可能还混着部门或姓名：
    #   "市场部经理"   → 部门=市场部, 职位=经理
    #   "章荣景销售总监" → 姓名=章荣景, 职位=销售总监
    if f["title"]:
        raw = f["title"].strip().strip("/|｜、·:： ")
        f["title"] = raw

        # 1) "张瑞德/总经理" —— 分隔符最明确，命中就不再往下试
        sm = NAME_TITLE_SEP.match(raw)
        if sm and any(k in sm.group(2).lower() for k in TITLE_KW):
            f["name"] = sm.group(1).strip()
            f["title"] = sm.group(2).strip(" （）()")
            dm = None
        else:
            dm = DEPT_TITLE.match(raw)

        if dm is not None and any(k in dm.group(2).lower() for k in TITLE_KW):
            f["dept"] = dm.group(1).strip()
            f["title"] = dm.group(2).strip(" （）()")
        elif dm is not None or not sm:
            m = NAME_TITLE.match(raw)
            if m:
                head = m.group(1)
                rest = raw[len(head):].strip(" （）()")
                if head not in ROLE_PREFIX and not any(k in head.lower() for k in COMPANY_KW):
                    if not f["name"] or f["name"] == f["title"]:
                        f["name"] = head
                    f["title"] = rest

    # 地址：中英文都收。双语名片上常是"中文一行 + 英文一行"，只留一个会丢信息
    addr_items = []
    addr_score = None
    for b in blocks:
        n = b["_n"]
        raw = b["text"].strip()
        val = None
        if ADDR_LABEL.match(n) or ADDR_LABEL.match(raw):
            val = ADDR_LABEL.sub("", raw)
            addr_score = b["score"]
        elif len(n) > 8 and any(k in n.lower() for k in ADDR_KW):
            val = raw
        if val:
            val = val.strip(" :：,，")
            if val and val not in [a[0] for a in addr_items]:
                addr_items.append((val, b["y"], bool(re.search(r"[\u4e00-\u9fa5]", val))))

    # 排序依据：中文地址优先 → 含门牌号的在前 → 纵向位置。
    # 竖排/旋转名片的 y 几乎重合，光靠 y 排不出上下行，只能靠"详细地址通常带数字"来判断。
    addr_items.sort(key=lambda x: (
        0 if re.search(r"[\u4e00-\u9fa5]", x[0]) else 1,
        0 if re.search(r"\d", x[0]) else 1,
        x[1],
    ))

    # 英文地址常被 OCR 拆成两行，纵向相近的英文行拼回一条；中文行单独保留
    merged = []
    for text, y, is_cn in addr_items:
        if merged and not is_cn and not merged[-1][2] and abs(y - merged[-1][1]) < 40:
            merged[-1] = (merged[-1][0] + " " + text, y, False)
        else:
            merged.append((text, y, is_cn))
    f["addresses"] = [m[0] for m in merged]
    f["address"] = f["addresses"][0] if f["addresses"] else None

    # 姓名：字号最大的一块，且不含数字/@、不是公司/职位行
    cands = []
    for b in blocks:
        t = b["text"].strip()
        if len(t) < 2 or len(t) > 40:
            continue
        if re.search(r"[0-9@]", t) or t.lower().startswith("www"):
            continue
        if LABEL_PREFIX.match(b["_n"]) or LABEL_PREFIX.match(t):
            continue
        if any(w in b["_n"] for w in AD_WORDS):
            continue
        if any(w in b["_low"] for w in ADDR_WORDS_EN):
            continue
        if any(k in b["_low"] for k in COMPANY_KW + TITLE_KW):
            continue
        if t == (f["company"] or "") or t == (f["title"] or ""):
            continue
        cands.append(b)
    # 已经从 "姓名/职位" 里拆出姓名时，不再被字号最大的块覆盖。
    # 中文姓名优先：双语名片上英文块字号往往更大，但那多半是地址或公司名。
    if cands and not f["name"]:
        cn = [b for b in cands if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", b["text"].strip())]
        pool = cn or cands
        pool.sort(key=lambda b: (-b["h"], b["y"]))
        f["name"] = pool[0]["text"].strip()

    score_map = {b["text"].strip(): b["score"] for b in blocks}
    conf = {k: score_map.get(f[k]) for k in ("name", "company", "title") if f[k]}
    if f["address"]:
        conf["address"] = addr_score if addr_score is not None else score_map.get(f["address"])
    f["_conf"] = conf
    return f


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", default="samples")
    ap.add_argument("-o", "--output", default="")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    inp = Path(args.input)
    if args.demo:
        p = make_demo(inp)
        print(f"[demo] generated {p}")

    files = [inp] if inp.is_file() else sorted(
        p for p in inp.rglob("*") if p.suffix.lower() in IMG_EXT
    )
    if not files:
        print(f"no images under {inp}")
        return

    engine = load_engine()
    report = []
    for p in files:
        blocks, ms = ocr_one(engine, p)
        fields = extract_fields(blocks)
        report.append({"file": p.name, "ms": ms, "blocks": blocks, "fields": fields})

        print("=" * 70)
        print(f"{p.name}  ({ms} ms, {len(blocks)} blocks)")
        print("-" * 70)
        for b in blocks:
            flag = "OK " if b["score"] >= 0.9 else ("!! " if b["score"] < 0.7 else "~  ")
            print(f"  {flag} {b['score']:.3f}  y={b['y']:>6.1f} h={b['h']:>5.1f}  {b['text']}")
        print("-" * 70)
        for k, v in fields.items():
            if k.startswith("_"):
                continue
            print(f"  {k:<8} = {v}")

    if args.output:
        Path(args.output).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n[json] -> {args.output}")


if __name__ == "__main__":
    main()
