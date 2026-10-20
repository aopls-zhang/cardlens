# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import os
from PyInstaller.utils.hooks import collect_all

HERE = os.path.abspath(os.path.dirname(SPEC))
ROOTDIR = os.path.abspath(os.path.join(HERE, ".."))

datas = [(os.path.join(ROOTDIR, "server", "static"), "server/static")]
binaries, hiddenimports = [], []
for pkg in ("rapidocr", "onnxruntime", "cv2"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

a = Analysis(
    [os.path.join(ROOTDIR, "server", "app.py")],
    pathex=[ROOTDIR, os.path.join(ROOTDIR, "tools"), os.path.join(ROOTDIR, "server")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["uvicorn.logging", "uvicorn.loops.auto",
                                   "uvicorn.protocols.http.auto", "uvicorn.lifespan.on"],
    hookspath=[], runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "PyQt5", "PySide2", "pandas", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="CardScan",
          console=True, icon=None)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="CardScan")
