# VPS 任務簡報：addwii-pm 開發接手

## 接手狀態（2026-06-24）

| 里程碑 | 狀態 | 備註 |
|--------|------|------|
| M0 骨架 | ✅ 完成 QA + commit | config.py, logger.py 已驗證 |
| M1 資料層 | ⚠️ code-writer 完成，**需要 VPS 跑 QA** | db.py, schema.sql, init_db.py |
| M2 單 bot 對話 | ⏳ 待開發 | |
| M3 IntentEngine | ⏳ 待開發 | |
| M4 Bot 互動 + 防迴圈 | ⏳ 待開發 | |
| M5 Web 儀表板 | ⏳ 待開發 | |
| M6 VPS 部署 | ⏳ 待開發 | |

## 第一件事：環境設定

```bash
# 1. Clone 專案
git clone https://github.com/chenghyang2001/addwii-pm.git /opt/addwii-pm
cd /opt/addwii-pm

# 2. 建 Python 虛擬環境
python3 -m venv .venv
source .venv/bin/activate

# 3. 安裝依賴
PYTHONUTF8=1 pip install -r requirements.txt

# 4. 複製 .env（之後再填真實值）
cp .env.example .env

# 5. 確認 claude -p 可用
claude -p "ping" && echo "OK"
```

## 立刻要做的事：M1 QA

M1 的三個檔案（schema.sql, core/db.py, tools/init_db.py）已由 code-writer 在本機寫好，但尚未 QA。請在 VPS 上跑 code-qa：

### db/schema.sql（簡單，2 test case）

```
TC1 Happy path：sqlite3 addwii.db < db/schema.sql 無報錯；PRAGMA journal_mode 回傳 wal
TC2 Edge case：重複執行 schema.sql 不報錯（所有 CREATE TABLE 都有 IF NOT EXISTS）
```

### core/db.py（中等，3 test case）

```
TC1 Happy path：from core.db import get_conn; with get_conn() as conn: print(conn.execute("SELECT 1").fetchone()[0])  → 印出 1
TC2 Edge case：read_only=True 模式開啟，嘗試 INSERT 應 raise sqlite3.OperationalError（唯讀）
TC3 Integration：execute_write("INSERT INTO notes(owner,content) VALUES(?,?)", ("B","測試")) → 回傳 lastrowid > 0
```

### tools/init_db.py（簡單，2 test case）

```
TC1 Happy path：PYTHONUTF8=1 python tools/init_db.py → 印出 ✅ 初始化完成；SELECT agents 顯示 A/B/C 三列
TC2 Edge case：重複執行不報錯（INSERT OR IGNORE）
```

**QA PASS 後 commit：**

```bash
git add db/ core/db.py tools/
git commit -m "新增 M1 資料層：SQLite WAL schema + db context manager + init_db 腳本"
git push
```

## 接下來：M2～M6 按計畫建置

詳細規格見 `C:\Users\user\.claude\plans\agents-ai-team-happy-pond.md`（本機 PC 的計畫檔）。
VPS 無法直接讀這個路徑，以下是摘要：

### M2 單 bot 對話迴路

需要建立的檔案：

- `core/claude_cli.py`：改寫自 yang_vps_hermes_bot/bot.py 的 invoke_claude，加 per-role Semaphore（限並發）
- `agent/persona.py`：`build_prompt(role, db_ctx, user_text)` → 呼叫 `claude -p <text> --append-system-prompt <system>`
- `personas/_base.md`、`personas/role_a.md`、`personas/role_b.md`、`personas/role_c.md`
- `agent/bot.py`：discord.Client，`on_message` 路由（人類訊息 → 只有對應 bot 回應）
- `main.py`：`python main.py --role A/B/C` 入口

**M2 on_message 路由邏輯（關鍵！）：**

```python
async def on_message(self, message):
    if message.author.id == self.user.id:   # 自己的訊息，永遠 skip
        return
    if message.author.bot:                   # 其他 bot 的訊息（M2 暫時 skip，M4 才處理）
        return
    # 真人發言
    role = self.config.resolve_role(message.author.id)
    if role != self.role:                    # 不是我的主人
        return
    await self.process(message)
```

**M2 驗證：**
三個 bot 加入同一測試 Discord Server + #team 頻道；真人 B 發言只有 Bot B 回應；messages 表有記錄。

### M3 IntentEngine + 動作寫入

- `agent/intent_engine.py`：呼叫 `claude -p` 解析意圖 → Pydantic Action 物件
- `agent/actions.py`：assign_task / report_task / add_note / add_meeting / add_reflection / none

**IntentEngine JSON 協定（fenced code block）：**

```json
{"action":"assign_task","assignee":"C","title":"...","deadline":"2026-06-28"}
{"action":"report_task","task_id":42,"status":"done","summary":"..."}
{"action":"add_note","text":"..."}
{"action":"add_meeting","title":"...","decisions":"...","action_items":"..."}
{"action":"add_reflection","text":"..."}
{"action":"none"}
```

Pydantic 驗證失敗 → 降級純對話，**不寫 DB**。

### M4 Bot 互動 + 防迴圈

擴充 `agent/bot.py` 的 `on_message`，加入 bot-to-bot @mention 處理：

```python
if message.author.bot:
    hop = extract_hop(message)              # 從訊息尾部取 [hop:N]
    if hop >= MAX_HOPS:                     # max_hops=3
        return
    if self.user not in message.mentions:   # 沒被 @mention 就不回
        return
    # 被 @mention + hop < 3 → 用 AI 生成回應
```

`actions.py` 發言時加 `[hop:N]` 標記，N = 上一個 hop + 1。

### M5 Web 儀表板

- `dashboard/queries.py`：唯讀 SQL 查詢（tasks overview, recent messages 等）
- `dashboard/api.py`：FastAPI，`/api/tasks`、`/api/overview`、掛 static 檔
- `dashboard/static/`：index.html + app.js + styles.css（三欄看板：assigned/in_progress/done）

Port 8092。Cloudflare Tunnel 暴露到外網。

### M6 VPS 部署

- `deploy/addwii-bot-a.service`（`python main.py --role A`）
- `deploy/addwii-bot-b.service`（`python main.py --role B`）
- `deploy/addwii-bot-c.service`（`python main.py --role C`）
- `deploy/addwii-dashboard.service`（`uvicorn dashboard.api:app --host 0.0.0.0 --port 8092`）
- `deploy/cloudflared-config.md`（Cloudflare Tunnel 設定說明）

## 開發原則（重要）

1. **所有 .py 檔案走 code-writer → code-qa（sequential）**，QA PASS 才 commit
2. **commit message 繁體中文**，commit 後立刻 push
3. **PYTHONUTF8=1** 加在所有 Python 執行前
4. **不硬編碼路徑**，一律 `Path(__file__).resolve()` 或環境變數
5. **不設 ANTHROPIC_API_KEY 全域環境變數**（會消耗 API Credits，要用 Max 訂閱走 claude -p）
6. **不用 `if message.author.bot: return`**（Discord 防迴圈要用 hop 計數器，不是 bot flag）

## Discord 前置設定（需使用者手動完成）

這些無法自動化，需要使用者到 Discord Developer Portal 操作：

1. 建三個 bot 應用程式，各取得 Token → 填入 VPS `.env`（BOT_TOKEN_A/B/C）
2. 每個 bot 開啟 **Message Content Intent**
3. 三個 bot 邀請進同一 Discord Server
4. 取得 guild_id 和 channel_id → 填入 `config.json`
5. 取得三個真人的 discord_user_id → 填入 `config.json` 的 members[A/B/C].discord_user_id

完成以上設定後，VPS 才能測試 M2。
