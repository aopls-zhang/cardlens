# 名片扫描（CardScan）

> 作者：**aopls-zhang** ｜ 许可证：**GPL-3.0-or-later** ｜ 项目首页：https://github.com/aopls-zhang

把自己拍的名片变成结构化的联系人库。**全程本地**：图片不上云、不长期保存，识别跑在自己的电脑上。

一个开源小项目，目标是把基础做扎实：离线可用、三端能连、数据在自己手里。

## 能做什么

- 手机拍照 / 从相册批量导入 / 手写录入
- 电脑本地 OCR（PP-OCRv6），简体、繁体、英文、法文、西班牙文
- 自动抽字段：姓名、公司（可多主体）、职位、部门、手机、座机、传真、微信、QQ、WhatsApp、Telegram、LINE、Skype、钉钉、飞书、邮箱、网址、地址、二维码内容
- 识别结果**必须人工核对**后才入库，字段级置信度着色
- 待处理队列 / 联系人库 / 搜索 / 批量删除
- 断网时照片先存本地，联网自动补传
- 中文（简繁）、英文界面

## 架构

~~~
手机（拍摄端）            电脑（识别与存储）
┌──────────────┐  图片    ┌──────────────────────┐
│ Android APK  │ ───────> │ FastAPI + PP-OCRv6   │
│ iOS PWA      │  字段    │ SQLite + 字段抽取     │
└──────────────┘ <─────── └──────────────────────┘
        扫码配对 / 局域网 HTTPS
~~~

- **识别只在电脑上做**：模型体积大、手机端精度低，统一放服务端。手机断网时照片进本地队列，联网补传。
- **图片不保存**：核对完立即删除，库里只有字段。
- **数据是字段级的**：`contact_field` 存每一条的 (类型, 值)，主表只是检索投影，为后续多端同步留位置。

## 快速开始

~~~powershell
python -m pip install -r requirements.txt
python server/app.py
~~~

- 电脑：http://127.0.0.1:17800
- 手机（同一 WiFi）：http://<电脑IP>:17800
- API 文档：http://127.0.0.1:17800/docs
- 首次运行会在 `data/certs/` 生成自签证书，同时监听 HTTPS 17801

## 三端入口

| 入口 | 怎么用 | 限制 |
|---|---|---|
| 电脑网页 | 打开 127.0.0.1:17800 | 无 |
| 手机网页 | 扫码打开 https://IP:17801，或用「链接方式」模块里的二维码 | 首次要确认证书；iOS 无闪光灯 |
| Android App | 扫码下载 APK，或用「链接方式」模块 | 无 |
| iOS | Safari 打开 https://IP:17801 → 添加到主屏幕（PWA） | 无闪光灯；要原生相机需 TestFlight |

### Android

~~~powershell
cd mobile
Copy-Item ..\server\static\* www\ -Recurse -Force
npx.cmd cap sync android
cd android && .\gradlew.bat assembleDebug
~~~

产物在 `mobile/android/app/build/outputs/apk/debug/app-debug.apk`。
需要 JDK 21 + Android SDK（`local.properties` 指向 SDK 路径）。

### iOS

暂不提供原生 App。iPhone 用 Safari 打开 `https://<电脑IP>:17801/`，点分享 → **添加到主屏幕**，
即可作为 PWA 使用（图标、全屏、可拍照）。

限制：WebKit 不暴露闪光灯接口，暗光下只能靠屏幕补光；切换到后台会停止。

如果将来要做原生版，`npx cap add ios` 生成工程后在 macOS + Xcode 上构建，走 TestFlight 分发即可，无需上架。

## 项目结构

~~~
server/app.py            FastAPI：上传 / 队列 / 核对 / 入库 / 批量操作
server/certs.py          自签证书生成
server/static/           手机端与桌面端页面（同一套）
tools/ocr_bench.py       OCR 封装 + 字段抽取（被服务复用）
tools/                   测试、数据生成、诊断脚本
mobile/                  Capacitor 工程（Android + iOS）
data/                    运行时数据（不入库）
~~~

## 开发

~~~powershell
# 抽取规则单测（不需要相机）
python tools/test_extract.py
python tools/test_phone.py
python tools/test_dept_phone.py

# 接口回归
python server/app.py
python tools/test_api.py

# 脚本语法检查
python tools/extract_js.py
node --check shots/check.js
~~~

## 已知限制

- 竖排/旋转名片的方向判断靠启发式（"含门牌号的地址在前"），不是真正的方向校正
- 传真号码和标签分处两个文本块时无法自动归类，需人工填
- 图片不保留，事后无法追溯 OCR 错误
- 浏览器端闪光灯只有部分 Android Chrome 支持，iOS 全线不可用
- 还没有多端字段同步（数据结构已预留）
- 桌面端目前用 Python 直接运行；提供 PyInstaller 打包脚本，可产出免安装 EXE

## 版权与许可

Copyright (C) 2026 **aopls-zhang**

本项目以 **GNU General Public License v3.0 or later** 发布，全文见 [LICENSE](LICENSE)。

这意味着：你可以自由使用、修改、分发，但**分发衍生作品时必须同样开源**，
并且必须保留原始版权声明与作者信息（`aopls-zhang`）。
