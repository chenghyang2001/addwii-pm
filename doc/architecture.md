# addwii-pm — 系統架構文件

**版本基準**：M6（2026-06-24）｜三 AI 代理人 Discord 協作系統

---

## 1. 系統概觀

addwii-pm 是一套廣告公司三人團隊（總監 A → PM 經理 B → 組員 C）的 AI 代理人協作系統。每位真人擁有一個獨立的 Discord Bot，所有人在同一個 `#team` 頻道對話，AI 代理人彼此可透過 @mention 傳遞工作指令。

```
真人（Discord 手機/PC）
      │ 發訊息到 #team
      ▼
Discord Gateway
      ├─ Bot A（addwii-A）  ← 總監 A 的代理人
      ├─ Bot B（addwii-B）  ← PM 經理 B 的代理人（ChengHsien）
      └─ Bot C（addwii-C）  ← 組員 C 的代理人
      
VPS（187.127.109.145）:
  ├─ addwii.db（SQLite WAL）  ← 三個 bot 共用狀態
  └─ Dashboard（FastAPI :8092）← 任務看板

外網：Cloudflare Tunnel → 瀏覽器看板（規劃中）
```

**核心設計原則**：

- 每個 bot 是獨立行程（systemd service），無共同 orchestrator
- Bot 間溝通透過 Discord 頻道本身（@mention + `[hop:N]`）
- AI 回應用 `claude -p` CLI（Max 訂閱，零 API 費用）

---

## 2. 組件與角色

| 層級 | 檔案 | 角色 | 說明 |
|------|------|------|------|
| **進入點** | `main.py` | CLI 啟動器 | 解析 `--role A/B/C`，驗證 Token，延遲 import bot |
| **Discord 層** | `agent/bot.py` | 事件路由 | `on_message` 過濾→人類/Bot 分流，`process_human_message` 主流程 |
| **AI 層** | `core/claude_cli.py` | subprocess 包裝 | `invoke_claude()` + per-role `asyncio.Semaphore(1)` |
| **意圖層** | `agent/intent_engine.py` | 結構化解析 | 二次 `claude -p` + regex 提取 fenced JSON + Pydantic 驗證 |
| **動作層** | `agent/actions.py` | DB 寫入 | Pydantic Action 物件 → SQLite 寫入（任務/筆記/會議/反思） |
| **人格層** | `agent/persona.py` | Prompt 工廠 | 讀 `personas/*.md` + DB 動態任務清單 → system prompt |
| **資料層** | `core/db.py` | SQLite WAL | context manager，`get_conn(read_only=True/False)` |
| **設定層** | `core/config.py` | 全域單例 | 讀 `config.json` + `.env`，`cfg.resolve_role()` 對應真人 ID |
| **看板層** | `dashboard/api.py` | FastAPI REST | 5 個端點：`/api/tasks` `/api/messages` `/api/notes` `/api/agents` `/api/stats` |
| **前端** | `dashboard/static/index.html` | SPA | 純 HTML/JS，axios 拉 API 渲染任務看板 |
| **部署** | `deploy/*.service` | systemd | 4 個 unit：`addwii-bot-a/b/c` + `addwii-dashboard` |
| **人格素材** | `personas/_base.md` + `role_[a/b/c].md` | Markdown | 基礎規則 + 角色特定性格注入 |

**資料庫表格**：

| 表格 | 用途 |
|------|------|
| `agents` | 三個 role（A/B/C）的設定、Discord ID |
| `tasks` | 任務追蹤（assignee/assigner/status/deadline） |
| `task_events` | 任務狀態變更歷程 |
| `notes` | 工作筆記 |
| `meeting_records` | 會議記錄（decisions + action_items） |
| `reflections` | 個人反思 |
| `messages` | Discord 訊息快取（speaker_kind: human/agent，hop 計數） |

---

## 3. 組件互動模式

### 3a. 線程模型

每個 bot 是單執行緒 asyncio event loop（discord.py 架構）。`claude -p` 呼叫透過 `loop.run_in_executor(None, _invoke_sync)` 卸載到 thread pool，避免 blocking event loop。每個 role 有獨立 `asyncio.Semaphore(1)`，確保同一時間只有一個 subprocess 呼叫。

### 3b. 真人訊息資料流

```
Discord #team 訊息
  → on_message：過濾自己 / 過濾非目標頻道
  → resolve_role()：確認是否為此 bot 的主人
  → process_human_message()：
      ①  INSERT INTO messages (speaker_kind='human')
      ②  build_system_prompt()（讀 personas/*.md + DB 任務清單）
      ③  invoke_claude(role, content, system_prompt)  ← 第1次 claude -p
      ④  parse_intent(role, content)                  ← 第2次 claude -p（IntentEngine）
      ⑤  handle_action(parsed_action)  → INSERT INTO tasks/notes/...
      ⑥  channel.send(response + action_msg)
      ⑦  INSERT INTO messages (speaker_kind='agent')
```

### 3c. Bot-to-Bot 轉發機制

```
Bot A 回應 → 附加 [hop:1] 並 @mention Bot B
Bot B 收到 → _handle_bot_message():
    - extract_hop() → 取得 hop 計數
    - hop >= MAX_HOPS(3) → 停止（防無限迴圈）
    - 自己未在 @mentions → 忽略
    - 回應後附加 [hop:2]
Bot C 若再被 @mention → hop:2 → 正常回應 → [hop:3]
下一個若再試 → hop:3 >= 3 → 停止
```

**關鍵約束**：不可用 `if message.author.bot: return`，因為 bot 必須能看到彼此的訊息。

### 3d. IntentEngine 協定

```
user_text → claude -p (system: _INTENT_SYSTEM_PROMPT)
         → 回應格式：```json\n{...}\n```
         → _JSON_BLOCK_RE 提取 JSON
         → json.loads() → Pydantic 驗證
         → ActionAssignTask / ActionReportTask / ActionAddNote / ... / ActionNone
任何失敗（CLI錯誤/JSON解析錯誤/驗證失敗）→ 降級 ActionNone（純對話，不寫 DB）
```

---

## 4. 使用者操作觸發的資料流

### 流程 A：真人指派任務

```
ChengHsien（B 的主人）在 Discord 輸入：「幫我指派 C 做明天前的競品分析報告」
  ↓
Bot B 的 on_message 收到（resolve_role → B）
  ↓
invoke_claude → 生成自然語言回應（「好的，我來指派給 C...」）
  ↓
parse_intent → claude -p → JSON：{"action":"assign_task","assignee":"C","title":"競品分析報告","deadline":"2026-06-25"}
  ↓
Pydantic 驗證 → ActionAssignTask
  ↓
handle_action → INSERT INTO tasks (assigner='B', assignee='C', status='assigned', ...)
  ↓
Bot B 回覆頻道：「好的，我來指派給 C... ✅ 已建立任務 #42：競品分析報告（期限：06-25）」
```

### 流程 B：Bot-to-Bot 轉發（A 指派給 C）

```
Bot A 想讓 C 知道某件事 → channel.send("@Bot-C 請確認... [hop:1]")
  ↓
Bot C 的 on_message → _handle_bot_message → hop=1 < 3 + @mention ✓
  ↓
invoke_claude（Clean content, 去除 @mention 和 [hop:N]）
  ↓
Bot C 回覆 → "已收到... [hop:2]"
```

### 流程 C：Dashboard 查詢

```
瀏覽器 GET /api/tasks
  ↓
FastAPI → get_tasks_overview()
  ↓
SQLite SELECT tasks WHERE status IN ('assigned','in_progress','done')
  ↓
回傳 JSON：{assigned:[...], in_progress:[...], done:[...]}
```

---

## 5. 關鍵架構決策（ADR 摘要）

| 決策 | 理由 | 代價 |
|------|------|------|
| **Discord 而非 Telegram** | Discord bot 原生接收其他 bot 訊息（開 Message Content Intent），Telegram bot 無此能力 | Discord 免費 API 有 rate limit；Telegram 更輕量 |
| **`[hop:N]` 而非 `author.bot` 過濾** | 三個 bot 需要互相聽到彼此；`author.bot: return` 會讓 bot 間協作失效 | 每條 bot 訊息需多一次 regex 解析；hop counter 需嵌入訊息尾部 |
| **SQLite WAL（非 PostgreSQL/Redis）** | 三個 bot + 一個 dashboard 的並發量低，WAL 模式夠用；零外部依賴、易備份 | 不支援跨機器部署；WAL 在長事務下 checkpoint 可能延遲；`timeout=30` 無 retry 邏輯 |
| **`claude -p` CLI（非 Anthropic SDK）** | Max 訂閱可免費使用，不消耗 API Credits；無需管理 API key | 每次呼叫是新 subprocess（30-60ms overhead）；需要 Claude Code CLI 已登入狀態 |
| **雙重 claude -p 呼叫（回應 + 意圖）** | 分離「說話邏輯」與「工作流觸發」；任一次失敗不影響另一次 | 每條真人訊息消耗 2x claude -p；延遲翻倍（可能 10-60 秒） |
| **Per-role Semaphore(1)** | 防止同一個 role 同時發出多個 subprocess，避免競爭；不同 role 可並發 | A 被主人連發訊息時，後面的訊息需排隊等待 |
| **Import-time Fail-fast（claude CLI 路徑檢查）** | 早期發現設定錯誤，不讓 bot 跑到一半才崩潰 | `claude_cli.py` 任何 import（含 intent_engine）都會觸發路徑檢查；CI/CD 無 claude 的環境無法測試 |

---

## 6. 部署與測試拓撲

```
開發（本機 Windows PC）
  │ git push
  ▼
GitHub（chenghyang2001/addwii-pm）
  │ git pull（VPS 端手動）
  ▼
VPS /opt/addwii-pm/
  ├─ python -m venv .venv
  ├─ pip install -r requirements.txt
  ├─ tools/init_db.py（初始化 /opt/addwii-pm/data/addwii.db）
  └─ systemd --user 啟動 4 個 service：
       addwii-bot-a.service   （main.py --role A）
       addwii-bot-b.service   （main.py --role B）
       addwii-bot-c.service   （main.py --role C）
       addwii-dashboard.service（uvicorn dashboard.api:app --port 8092）

驗證：
  journalctl --user -u addwii-bot-b -f     ← 確認 bot 上線
  curl localhost:8092/api/stats            ← dashboard 回應
  Discord 手動傳訊息 → 觀察 bot 回覆

Cloudflare Tunnel（規劃中）：
  cloudflared tunnel → :8092 ← 外部瀏覽器存取 dashboard
```

**測試策略**：

- 單元：每個 `.py` 底部有 `if __name__ == "__main__":` 冒煙測試（`bot.py` 用 `unittest.IsolatedAsyncioTestCase`）
- 整合：需要 VPS 環境（SQLite DB + claude CLI）
- E2E：Discord 手動發訊息，目視 bot 回覆 + `journalctl` log 確認
