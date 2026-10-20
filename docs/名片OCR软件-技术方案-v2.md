# 名片 OCR 软件 · 技术方案 v2

> 变更：蓝牙方案废弃；三端（Windows / Android / iOS）各自本地保存；任两端建立连接后必须双向同步。

---

## 1. 架构定位的变化

| | v1 | v2 |
|---|---|---|
| 数据形态 | Windows 是唯一主库，手机是采集器 | 每台设备都是**完整副本** |
| 同步方向 | 单向上传 | **双向、任意拓扑**（手机↔手机也要通） |
| 核心难点 | OCR 准确率 | **同步引擎**（离线冲突合并） |
| iOS 定位 | 只需采集 | 必须本地持久化，矛盾出现（见 §6） |

一句话：**这是一个离线优先（offline-first）的分布式应用**，OCR 只是它的输入方式之一。

---

## 2. 架构总览

~~~
┌──────────────────────────────────────────────────────────┐
│                    共享层（一份代码）                      │
│   UI(React) │ Repository 接口 │ SyncEngine(TS) │ OCR 适配  │
└──────────────────────────────────────────────────────────┘
        │                │                │
   ┌────┴────┐      ┌────┴────┐      ┌────┴────┐
   │ Windows │      │ Android │      │   iOS   │
   │ Electron│      │Capacitor│      │Capacitor│
   │  SQLite │      │  SQLite │      │  SQLite │
   └────┬────┘      └────┬────┘      └────┬────┘
        └──────── mDNS 发现 + HTTP/WS ────┘
                    （全互联，无中心）
~~~

三个设计约束：

1. **UI 与同步引擎只依赖 Repository 接口**，不直接碰 SQLite，这样三端可以换不同驱动。
2. **同步引擎是纯 TS、无 IO**，输入输出都是 diff 对象，方便单测和移植。
3. **任何一端都能同时当服务端和客户端**，谁先起来不重要。

---

## 3. 技术选型（基于当前机器）

现有：node ✓ python ✓ dotnet ✓ git ✓ ｜ flutter ✗ dart ✗ cargo ✗

| 层 | 选择 | 理由 |
|---|---|---|
| 共享 UI + 同步引擎 | TypeScript + React + Vite | 一份代码三端复用，同步逻辑只写一遍 |
| Windows 壳 | **Electron**（现成 node，零新装）或 Tauri（需装 Rust，体积小 10 倍） | MVP 用 Electron，成熟后再考虑 Tauri |
| Android / iOS 壳 | Capacitor | 复用同一 Web 包，能拿原生相机、SQLite、mDNS |
| 数据库 | SQLite（三端统一） | Electron: better-sqlite3；移动端: @capacitor-community/sqlite |
| 发现 | mDNS（bonjour-service / 原生 NsdManager、NSNetService） | 免输 IP |
| OCR | Windows 端 RapidOCR（Python 旁路进程）+ 手机端 ML Kit 兜底 | 见 §8 |

> 不选 Flutter 的唯一原因是本机没有 Flutter 且 iOS 要复用 Web；如果团队愿意装 Flutter，Flutter + drift 也是等效方案，同步引擎改用 Dart 重写。

---

## 4. 本地数据模型

核心思想：**记录的"真相"存在字段级表里，主表只是检索用的投影**。

~~~sql
-- 设备白名单
CREATE TABLE device (
  dev_id    TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  pubkey    TEXT,                 -- Ed25519 公钥 base64
  paired_at INTEGER,
  last_sync INTEGER,
  trusted   INTEGER NOT NULL DEFAULT 0
);

-- 名片主表（投影，便于搜索/列表）
CREATE TABLE contact (
  id          TEXT PRIMARY KEY,   -- UUIDv7（时间有序）
  created_hlc TEXT NOT NULL,
  deleted     INTEGER NOT NULL DEFAULT 0,
  deleted_hlc TEXT,
  name        TEXT,
  company     TEXT,
  title       TEXT,
  search_text TEXT                -- 所有字段拼起来，供 FTS5
);

-- 字段级真值表：冲突合并发生在这里
CREATE TABLE contact_field (
  contact_id TEXT    NOT NULL,
  field      TEXT    NOT NULL,    -- name|company|title|dept|phone|email|address|web|note|tag
  idx        INTEGER NOT NULL DEFAULT 0,   -- 多值序号（2 个手机号 -> idx 0/1）
  value      TEXT,
  hlc        TEXT    NOT NULL,    -- 混合逻辑时钟，字典序即时间序
  dev_id     TEXT    NOT NULL,
  deleted    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (contact_id, field, idx)
);

-- 被覆盖的旧值留档，用于「查看历史 / 手动裁决」
CREATE TABLE field_conflict (
  contact_id  TEXT, field TEXT, idx INTEGER,
  loser_value TEXT, loser_hlc TEXT, loser_dev TEXT,
  resolved    INTEGER DEFAULT 0,
  PRIMARY KEY (contact_id, field, idx, loser_hlc)
);

-- 图片内容寻址：相同图片只存一份
CREATE TABLE card_image (
  sha256       TEXT PRIMARY KEY,
  contact_id   TEXT NOT NULL,
  role         TEXT NOT NULL,     -- front|back
  width INTEGER, height INTEGER, bytes INTEGER,
  thumb_sha256 TEXT,
  captured_at  INTEGER,
  hlc          TEXT NOT NULL,
  deleted      INTEGER DEFAULT 0
);

-- 每个对端已确认接收到的水位
CREATE TABLE sync_state (
  dev_id    TEXT PRIMARY KEY,
  watermark TEXT NOT NULL
);
~~~

**为什么必须字段级？** 用户 A 在手机上改了电话号码，用户 B 在电脑上改了公司名，同一张名片。整条记录覆盖 → 丢一个。字段级 LWW → 两个都保住。名片场景里这种并发修改非常常见。

---

## 5. 同步引擎

### 5.1 时钟：HLC

每个变更带一个混合逻辑时钟：

~~~
HLC = 16位十六进制物理毫秒 + '-' + 4位十六进制计数器 + '-' + 8位设备前缀
例：0192f3a1c4d80000-0003-a1b2c3d4
~~~

- 字典序即全序，可直接当增量游标用；
- 收到对端 hlc 时本地时钟必须 max(local, remote)+1，避免设备时钟漂移导致永远不同步；
- 设备前缀在最末位兜底：极端情况下 hlc 完全相同，按 dev_id 排序，保证所有副本收敛到同一结果。

### 5.2 变更表示

每次用户操作 → 写若干条 contact_field（每字段一条，含新 hlc/dev_id）→ 同事务内更新 contact 投影和 FTS。

删除 = 写墓碑（deleted=1 且带新 hlc），**不物理删除**，否则删除动作无法传播。

「复活」语义：删除的 hlc 晚于修改的 hlc → 保持删除；修改更晚 → 复活。规则统一由 hlc 比较得出，不需要特判。

### 5.3 冲突处理

~~~
apply(remote_change):
  local = db.get(same contact_id, field, idx)
  if local is null               -> 直接写入
  else if remote.hlc > local.hlc -> 旧值存入 field_conflict，写入新值
  else if remote.hlc < local.hlc -> 忽略，但记入 conflict 留档
  else                           -> 按 dev_id 字典序决胜（理论上不会发生）
~~~

被覆盖的版本不丢弃，进 field_conflict。UI 上给该字段一个「ⓘ 有历史版本」的角标，用户可回滚。这是"自动合并 + 可追溯"的折中，比弹窗让用户裁决体验好得多。

### 5.4 会话协议（HTTP + WS 双工，任一端可发起）

~~~
1. HELLO        {dev_id, proto, watermark, fingerprint}
2. HELLO_ACK    {dev_id, watermark, need_full}
3. PUSH         {changes:[...], cursor}      # 按 hlc 升序，200 条/页
4. PUSH_RESULT  {applied, conflicts, watermark}
5. （双向各来一轮，然后）
6. BLOB_MANIFEST{missing:[sha256...]}        # 只列差异
7. BLOB_GET     {sha256}                     # 按需，一次一张
8. DONE         {stats}
~~~

- **幂等**：(contact_id, field, idx, hlc) 是天然主键，重复推送无副作用，断线重连直接续传；
- **增量**：watermark 是上次成功同步的最高 hlc，下次只拉水位之后的；
- **断点续传**：每页确认后才推进水位，网络抖动不会丢数据也不会重复。

### 5.5 图片同步（重点，容易拖垮体验）

名片原图 200–400 KB，1000 张就是 300 MB。

| 内容 | 策略 |
|---|---|
| 元数据 | 总是同步 |
| 缩略图 320px（~15 KB） | 总是同步，列表立即可见 |
| 原图 | **默认按需拉取**（点开详情才下），可配置「总是同步原图」 |
| 去重 | sha256 内容寻址，同图只传一次 |

首次全量同步提供三档：仅元数据 / 元数据+缩略图（推荐）/ 全量原图。

### 5.6 发现与配对

- **自动**：mDNS 广播 _cardscan._tcp，携带 dev_id, name, port, proto, fingerprint。已在白名单里的设备直接挑战应答（Ed25519 签 nonce）后同步。
- **首次**：任一端显示二维码 cardscan://pair?d=..&ip=..&p=..&t=..&fp=..，另一方扫码 → 双向写入白名单 → 立即全量同步。手机↔手机同样适用（一方开热点、一方连）。
- **跨网段**（不在同一 WiFi）：暂时不打通。需要的话后续加"经 Windows 中继"，但那本质是把 Windows 变回中心节点，先不做。

### 5.7 同步触发时机

- 应用启动、网络切换（WiFi 连上）、从后台回前台
- 前台每 60s 心跳探测
- 用户手动「立即同步」按钮
- **连上即自动同步，不给确认弹窗**——但要有一个常驻的同步状态条（"正在同步 128/340…"），让用户知道发生了什么事。

---

## 6. iOS 的现实约束：必须现在决策

你要「三端都本地保存」，但 iOS 只有两条路，这是硬约束：

| 路线 | 本地持久性 | 成本 | 适用 |
|---|---|---|---|
| **A. PWA（Safari + IndexedDB）** | ⚠️ 不可靠。Safari 的 ITP 会清理脚本可写存储（未加入主屏约 7 天无访问即清）；加入主屏有一定豁免但 Apple 不承诺；用户清 Safari 数据即全丢 | 零 | 只做「临时缓存 + 尽快回流」 |
| **B. Capacitor 壳 + SQLite** | ✅ 可靠，和 Android 一致 | 需 Apple 开发者账号（$99/年）、需 Xcode、需签名 | 真正要求本地保存 |
| **C. Capacitor 壳 + TestFlight 内测** | ✅ 可靠 | 内部测试 100 人，beta 审核宽松，不必先公开上架 | **推荐过渡方案** |

**结论**：如果 iOS 必须"本地保存"，PWA 方案要放弃。建议按 C 走——用 TestFlight 内测版先跑通，功能稳定后再走正式上架（上架检查清单见 v1 文档，核心是：不能是纯 WebView 壳、隐私清单 PrivacyInfo.xcprivacy、相机与本地网络权限文案、不做账号体系可规避 5.1.1(v)）。

如果暂时接受 A，那 iOS 端的定位要明确写成「本机只缓存最近 N 条，数据以 Windows/Android 副本为准」，并且 UI 上要提示风险，否则用户丢数据会算在你头上。

---

## 7. 拍摄与核对（保留 v1 结论）

拍摄：四角检测 → 透视校正 → 去反光 → 压缩到长边 2000px / JPEG q85。
核对：左图右表单、字段级置信度着色（绿≥0.9 / 黄 0.7–0.9 / 红<0.7）、点字段高亮原图 bbox、必填校验、电话归一化去重、键盘流（Enter 下一字段 / Ctrl+Enter 保存）。
**识别结果一律进草稿态，核对通过才写入 contact_field**——这条不能妥协。

---

## 8. OCR 流水线

~~~
图片 → RapidOCR(Windows) ──→ 文本块+bbox
                              ↓
                     规则抽取（正则/词典/版面位置）
                              ↓
                     结构化字段 + 每字段置信度
                              ↓
                     草稿 → 人工核对 → 落库
~~~

- Windows 端 RapidOCR 作为常驻 Python 子进程，通过 stdin/stdout JSON 通信，避免每次冷启动；
- 手机端 ML Kit 离线识别用于「没连电脑时先出草稿」，精度低一档，核对界面会标出来源；
- 云端 OCR 作为可选开关，默认关闭（涉及第三方共享个人信息）。

---

## 9. 安全与隐私

- **同步通道**：局域网内 HTTPS，自签证书 + 配对时固定指纹（二维码里带 fp），天然防中间人，不用 PKI；
- **本地库**：可选 SQLCipher，性能损失约 10–15%；
- **设备丢失**：设备列表里可撤销 + 下发 WIPE 指令（下次连上时执行）；
- **图片**：写入前剥离 EXIF；
- **合规**：名片承载他人个人信息，全本地处理是最大合规优势，云 OCR 一旦开启就要做告知与单独同意；
- 日志里手机号/邮箱脱敏。

---

## 10. 里程碑

| 周 | 交付 | 验收 |
|---|---|---|
| W1 | 共享数据层 + Repository + SQLite 投影 | 单测：字段写入/读取/墓碑 |
| W2 | SyncEngine（HLC、diff、apply、幂等） | 单测：两副本随机并发编辑后收敛一致 |
| W3 | Windows Electron 壳 + mDNS + 配对二维码 | 手机扫码与电脑互通 |
| W4 | 拍照上传 + RapidOCR + 核对表单 | 端到端录一张名片 |
| W5 | Android Capacitor 包壳 + 三方同步 | 手机 A ↔ PC ↔ 手机 B 全量收敛 |
| W6 | 图片按需同步 + 缩略图 + 搜索 + 导出 | 1000 条压力测试 |
| W7 | iOS Capacitor + TestFlight 内测 | 真机验证本地持久性 |

**W2 是生死线**。同步引擎写错，后面全是补丁。建议第一版就用属性测试（fast-check）跑「随机并发编辑 → 所有副本必须一致」。

---

## 11. 已知风险

1. **iOS PWA 存储不可靠**（§6）——本方案最大的产品级风险，需尽早决策。
2. **mDNS 在部分企业 WiFi / 手机热点下被屏蔽**——必须有二维码/手输 IP 兜底。
3. **设备时钟错乱**（用户手动改时间）——HLC 的 max 规则可缓解，但方案里已用 dev_id 兜底。
4. **图片体积膨胀**——按需同步是必须的，不是优化项。
5. **多副本意味着多份泄露面**——设备越多，丢一台的损失越大，撤销机制要早做。
6. **不做跨网段同步会被用户抱怨**（"我在公司、电脑在家"）——提前在文案上限定"同一局域网"。
