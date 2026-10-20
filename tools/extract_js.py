# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aopls-zhang
import re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
html = Path("server/static/index.html").read_text(encoding="utf-8")
m = re.findall(r"<script>(.*?)</script>", html, re.S)
print("script blocks:", len(m))
js = m[-1]
Path("shots/check.js").write_text(js, encoding="utf-8")
print("lines:", js.count("\n"))
