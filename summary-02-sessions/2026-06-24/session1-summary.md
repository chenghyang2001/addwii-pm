# Session 1 Summary — addwii-pm（2026-06-24）

## 日期

2026-06-24

## 本 Session 完成事項

### 🏗️ 專案架構決策（從 Telegram 切換到 Discord）

- Opus 模型研究確認 Telegram bot 無法收到其他 bot 訊息（平台硬限制），決定改用 **Discord**
- Discord 三個獨立 bot 各自連 Gateway，Message Content Intent 開啟後可互見彼此訊息
- 確立防迴圈機制：`message.author.id == self.user.id`（只跳過自己） + `[hop:N]` 計數器（不能用 `message.author.bot: return`）

### ✅ M0 骨架（commit c2284ab）

- `config.json`：guild_id/channel_id/members A/B/C/reports_to/max_hops=3
- `.env.example`：BOT_TOKEN_A/B/C、CLAUDE_PATH、ADDWII_DB_PATH
- `.gitignore`：排除 .env、data/、logs/、*.db
- `requirements.txt`：discord.py>=2.3.2、fastapi、uvicorn、pydantic、python-dotenv
- `core/config.py`（133 行，SHA256: 03c441284...，QA PASS）：Config singleton + resolve_role() + get_bot_token()
- `core/logger.py`（63 行，SHA256: f907627...，QA PASS）：TimedRotatingFileHandler

### ✅ M1 資料層（commit 81c48ae + 0f4a436）

- `db/schema.sql`：7 張表（agents/tasks/task_events/notes/meeting_records/reflections/messages）+ WAL + FK
- `core/db.py`：get_conn() context manager、WAL PRAGMA、execute_one/all/write、參數化查詢
- `tools/init_db.py`：建庫 + seed agents A/B/C（INSERT OR IGNORE）
- 🐛 修復：SEED_AGENTS 原本三個成員都設 discord_user_id=0，違反 UNIQUE 約束；小雲在 VPS 修正為 B=-1, C=-2（commit 0f4a436）

### ✅ Discord 設定（commit d08c673）

- guild_id: 1519084697886396486
- channel_id: 1519084697886396489
- B（ChengHsien）discord_user_id: 1519082801545089195
- 三個 Bot Token 已填入 VPS `/opt/addwii-pm/.env`（BOT_TOKEN_A/B/C）
- 三個 bot 的 Message Content Intent 已在 Discord Developer Portal 開啟

### ✅ 設計 PPT + 交接文件（commit 2acaa1c）

- `doc/addwii-pm-design.pptx`：8 張投影片（245 行 gen_pptx.py 生成，39,351 bytes），記錄平台遷移歷程 + Discord 架構
- `doc/handoff-2026-06-24.md`：詳細交接文件，供兩三小時後在另一台電腦繼續使用
- `doc/vps-task-brief.md`：M1-M6 完整規格給 VPS 小雲

### 🔄 M2 指派給 VPS 小雲（背景執行中）

- 背景 agent ID: a4988268644226959
- 指令：完成 M2 → M3 → M4 → M5 → M6 全部不停止
- M2 核心：claude_cli.py、agent/bot.py（人類訊息路由）、personas/*.md、main.py、agent/persona.py

## 關鍵技術筆記

### Discord 防迴圈（最重要）

```python
# ❌ 絕對不能用這個（bot 看不到彼此）
if message.author.bot: return

# ✅ 正確：只跳過自己的訊息
if message.author.id == self.user.id: return

# ✅ 其他 bot：用 [hop:N] 計數器 + @mention 要求
hop = extract_hop(message)
if hop >= MAX_HOPS: return  # max_hops=3
if self.user not in message.mentions: return
```

### IntentEngine 降級機制

Pydantic 驗證失敗 → 降級純對話，**不寫 DB**（防止誤解析）

### VPS claude -p 零費用原則

- 使用 Max 訂閱，**絕對不設 ANTHROPIC_API_KEY 全域環境變數**
- claude -p subprocess 每次呼叫走 OAuth，不扣 API Credits

### SQLite WAL 並發設計

3 個 bot 行程 + 1 個 dashboard 行程共用一個 addwii.db
WAL 模式允許多讀者 + 序列化寫入，`timeout=30` 防鎖死

## 產出檔案表格

| 檔案 | 類型 | 狀態 | Commit |
|------|------|------|--------|
| `config.json` | 設定 | ✅ 已提交 | d08c673 |
| `.env.example` | 範本 | ✅ 已提交 | c2284ab |
| `.gitignore` | 設定 | ✅ 已提交 | c2284ab |
| `requirements.txt` | 依賴 | ✅ 已提交 | c2284ab |
| `core/config.py` | Python | ✅ QA PASS | c2284ab |
| `core/logger.py` | Python | ✅ QA PASS | c2284ab |
| `db/schema.sql` | SQL | ✅ QA PASS | 81c48ae |
| `core/db.py` | Python | ✅ QA PASS | 81c48ae |
| `tools/init_db.py` | Python | ✅ QA PASS（修正後）| 0f4a436 |
| `CLAUDE.md` | 文件 | ✅ 已提交 | 81c48ae |
| `doc/vps-task-brief.md` | 文件 | ✅ 已提交 | 81c48ae |
| `doc/addwii-pm-design.pptx` | PPT | ✅ 已提交 | 2acaa1c |
| `doc/handoff-2026-06-24.md` | 文件 | ✅ 已提交 | 2acaa1c |
| `main.py` | Python | ⚠️ 本地未提交 | — |

---

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] 向 小雲 詢問 M2-M6 進度：`小雲，addwii-pm 現在做到哪個里程碑了？`
- [ ] 確認三個 bot 是否已邀請進 addwii-team Discord server（A/C 目前 user_id 為 -1/-2 佔位）
- [ ] 若 M2-M6 已完成，測試端到端：在 #team 頻道發訊息確認 Bot B 回應且 messages 表有記錄

### 進行中（需接續）

- 小雲背景 agent（ID: a4988268644226959）正在執行 M2→M6 開發，完成後會 push commit「M2-M6 全部完成，系統運行中」
- M2 目標：core/claude_cli.py + personas/*.md + agent/persona.py + agent/bot.py + main.py（人類訊息路由）
- M3 目標：agent/intent_engine.py + agent/actions.py（IntentEngine + DB 寫入）
- M4 目標：bot-to-bot @mention + [hop:N] 計數器防迴圈
- M5 目標：dashboard/api.py + dashboard/static/（FastAPI + vanilla SPA，port 8092）
- M6 目標：deploy/*.service + systemd + cloudflare tunnel

### 注意事項

- `main.py` 存在於本地未提交，需確認是否為 M2 writer 的產出（若 VPS 小雲已產出更完整版本，以 VPS 版為準）
- A 和 C 的真實 discord_user_id 尚未填入（目前 -1/-2 佔位），需等真人使用者提供後更新 config.json
- 小雲 VPS bot token 已在 `/opt/addwii-pm/.env`，不在 GitHub（安全）
- 所有 .py 檔案必須走 code-writer → code-qa 流程才能 commit（writer-qa-iron-rule）
