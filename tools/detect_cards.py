# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import sys
import numpy as np, cv2
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")


def imread_u(p):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def spans(profile, thresh=None, min_gap=4, min_len=60, k=15, ratio=0.45):
    if thresh is None:
        # 自适应阈值：不同扫描件的白色占比差异很大，固定阈值会失效
        sm = np.convolve(profile, np.ones(k) / k, mode="same")
        thresh = max(0.004, float(np.median(sm)) * ratio)
    blank = profile < thresh
    gaps, start = [], None
    for i, b in enumerate(blank):
        if b and start is None:
            start = i
        elif not b and start is not None:
            gaps.append((start, i)); start = None
    if start is not None:
        gaps.append((start, len(blank)))
    gaps = [g for g in gaps if g[1] - g[0] >= min_gap]
    out, prev = [], 0
    for g0, g1 in gaps:
        if g0 - prev >= min_len:
            out.append((prev, g0))
        prev = g1
    if len(blank) - prev >= min_len:
        out.append((prev, len(blank)))
    return out


def detect(p, debug=None, pad=14):
    bgr = imread_u(p)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    # 只用"纯白"做版面骨架：扫描背景偏色，饱和度不可靠
    # v1 参数：真实拼版图上，自适应阈值会切出大量碎片，固定阈值反而更干净
    mask = (v > 248).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    h, w = mask.shape
    cols = spans(mask.mean(axis=0), thresh=0.02, min_gap=5, min_len=120)
    cells = []
    for c0, c1 in cols:
        sub = mask[:, c0:c1]
        for r0, r1 in spans(sub.mean(axis=1), thresh=0.02, min_gap=5, min_len=80):
            x0, x1 = max(0, c0 - pad), min(w, c1 + pad)
            y0, y1 = max(0, r0 - pad), min(h, r1 + pad)
            cw, ch = x1 - x0, y1 - y0
            if cw < 200 or ch < 100:
                continue
            if mask[r0:r1, c0:c1].mean() < 0.04:
                continue
            cells.append((x0, y0, cw, ch))

    cells.sort(key=lambda c: (round(c[1] / 150), c[0]))
    if debug:
        dbg = bgr.copy()
        for i, (x, y, cw, ch) in enumerate(cells):
            cv2.rectangle(dbg, (x, y), (x + cw, y + ch), (0, 200, 0), 5)
            cv2.putText(dbg, str(i), (x + 10, y + 55), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 255), 4)
        dbg = cv2.resize(dbg, (900, int(900 * dbg.shape[0] / dbg.shape[1])))
        cv2.imencode(".png", dbg)[1].tofile(debug)
    return cells


if __name__ == "__main__":
    for name in ("展会20230506_0001.jpg", "展会20230506_0005.jpg", "展会20230506_0010.jpg"):
        p = Path("数据/extracted") / name
        cells = detect(p, debug=f"shots/split2_{Path(name).stem}.png")
        print(name, "->", len(cells))
