# CardScan

> Author: **aopls-zhang** ｜ License: **GPL-3.0-or-later** ｜ Home: https://github.com/aopls-zhang/cardlens

[简体中文](README.md) ｜ **English**

Turn the business cards you photograph into a structured contact library. **Everything stays local** — images never go to a cloud service, are never kept long-term, and OCR runs on your own desktop.

This is a small open-source project. The goal is a solid foundation: works offline, all three platforms can connect, and the data stays with you.

## What it does

- Capture with a phone camera / batch-import from the gallery / enter manually
- Desktop-side OCR (PP-OCRv6) for Simplified Chinese, Traditional Chinese, English, French, and Spanish
- Extracts: name, company (multiple entities supported), title, department, mobile, landline, fax, WeChat, QQ, WhatsApp, Telegram, LINE, Skype, DingTalk, Feishu, email, website, address, and QR code content
- OCR results are **never saved automatically** — every record must be reviewed by a human, with per-field confidence coloring
- Inbox queue / contact library / search / batch delete
- Photos are queued locally when offline and re-uploaded automatically once connected
- UI in Simplified Chinese, Traditional Chinese, and English

## Architecture

~~~
Phone (capture)             Desktop (OCR + storage)
┌──────────────┐   image   ┌──────────────────────┐
│ Android APK  │ ────────> │ FastAPI + PP-OCRv6   │
│ iOS PWA      │   fields  │ SQLite + extraction  │
└──────────────┘ <──────── └──────────────────────┘
        QR pairing / LAN HTTPS
~~~

- **OCR only runs on the desktop.** The model is large and on-device accuracy is lower, so recognition is centralized on the server. When the phone is offline, photos enter a local queue and are re-uploaded later.
- **Images are not kept.** They are deleted right after review; only fields are stored.
- **Data is field-level.** `contact_field` stores every (type, value) pair; the main table is a read projection, leaving room for multi-device sync later.

## Quick start

~~~powershell
python -m pip install -r requirements.txt
python server/app.py
~~~

- Desktop: http://127.0.0.1:17800
- Phone (same Wi-Fi): http://<desktop-ip>:17800
- API docs: http://127.0.0.1:17800/docs
- First run generates a self-signed certificate under `data/certs/` and also listens on HTTPS 17801

## Entry points

| Entry | How | Limitations |
|---|---|---|
| Desktop web | Open 127.0.0.1:17800 | none |
| Phone web | Scan the QR for https://IP:17801, or use the “Link” module | Certificate warning on first visit; no flash on iOS |
| Android app | Scan to download the APK, or use the “Link” module | none |
| iOS | Safari → https://IP:17801 → Add to Home Screen (PWA) | no flash; native camera needs TestFlight |

### Android

~~~powershell
cd mobile
Copy-Item ..\server\static\* www\ -Recurse -Force
npx.cmd cap sync android
cd android && .\gradlew.bat assembleDebug
~~~

Output: `mobile/android/app/build/outputs/apk/debug/app-debug.apk`.
Requires JDK 21 and the Android SDK (`local.properties` must point at it).

### iOS

No native app for now. Open `https://<desktop-ip>:17801/` in Safari, tap Share → **Add to Home Screen**,
and use it as a PWA (icon, full screen, camera works).

Limitations: WebKit does not expose the torch API, so dark environments rely on screen light; the app stops when backgrounded.

If a native build is ever needed, run `npx cap add ios` and build on macOS + Xcode; TestFlight distribution does not require App Store review.

## Project layout

~~~
server/app.py            FastAPI: upload / queue / review / storage / batch ops
server/certs.py          Self-signed certificate generation
server/static/           Phone and desktop pages (same asset set)
tools/ocr_bench.py       OCR wrapper + field extraction (shared with the server)
tools/                   Tests, sample generation, maintenance scripts
mobile/                  Capacitor project (Android)
data/                    Runtime data (gitignored)
~~~

## Development

~~~powershell
# Extraction unit tests (no camera needed)
python tools/test_extract.py
python tools/test_phone.py
python tools/test_dept_phone.py

# API regression
python server/app.py
python tools/test_api.py

# Front-end script syntax check
python tools/extract_js.py
node --check shots/check.js
~~~

## Known limitations

- Orientation handling for vertical/rotated cards is heuristic (“the address containing a house number goes first”), not real deskewing
- A fax number in a separate text block from its label cannot be classified automatically and must be filled in by hand
- Images are not retained, so OCR mistakes cannot be traced back afterwards
- Torch support in browsers is limited to some Android Chrome builds; iOS has none at all
- Multi-device field sync is not implemented yet (the schema is ready for it)
- The desktop build runs from Python directly; a PyInstaller script produces a portable EXE

## Copyright and license

Copyright (C) 2026 **aopls-zhang**

Released under the **GNU General Public License v3.0 or later**. See [LICENSE](LICENSE) for the full text.

In short: you may use, modify, and redistribute it freely, but **derivative works must remain open source**,
and the original copyright notice and author name (`aopls-zhang`) must be preserved.
