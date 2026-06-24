# Session 2 收工摘要：addwii-pm M2-M6 全程開發與部署

**日期**：2026-06-24
**執行者**：小雲（VPS sub-agent）

---

## 本 Session 完成事項

### M2 QA：驗證既有核心模組
- `core/claude_cli.py`：async subprocess wrapper，Per-role Semaphore，QA PASS
- `agent/persona.py`：build_system_prompt() 讀取 personas/*.md，QA PASS
- `agent/bot.py` M2 版：人類訊息路由，QA PASS

### M3：意圖引擎 + 動作處理
- **新建** `agent/intent_engine.py`
  - `parse_intent(role, text)` → Pydantic v2 ParsedAction
  - 支援：assign_task / report_task / add_note / add_meeting / add_reflection / none
  - 從 fenced code block 提取 JSON，fallback 為 ActionNone
- **新建** `agent/actions.py`
  - `handle_action(action, author_role, channel_id, hop)` → Optional[str]
  - 關鍵修復：欄位名稱對應 schema.sql 實際值
    - tasks：assigner / assignee（非 assigner_role / assignee_role）
    - task_events：actor / event / note（非 actor_role / event_type / detail）
    - status 合法值：assigned/in_progress/done/blocked/cancelled
    - STATUS_MAP：映射 open → assigned
    - meeting_records：owner / summary（summary 必填，NOT NULL）
    - reflections：owner（非 author_role）

### M4：Bot-to-Bot @mention + hop 防迴圈
- **升級** `agent/bot.py` 至 M4 版本
  - `extract_hop(content)` → 正則提取 `[hop:N]`
  - `_handle_bot_message()`：hop < MAX_HOPS + 被 @mention → 回應 hop+1
  - `process_human_message()`：記錄 → Intent → AI → handle_action → 發送 → 記錄
  - 防迴圈規則：只跳過 `self.user.id == message.author.id`（不用 `if message.author.bot: return`）
  - 關鍵修復：messages 表欄位 text/role/speaker_kind/hop（非 content/sender_role/sender_type/hop_count）

### M5：Dashboard
- **新建** `dashboard/queries.py`：唯讀查詢（get_tasks_overview / get_recent_messages / get_agents_status / get_system_stats）
- **新建** `dashboard/api.py`：FastAPI app，port 8092，6 個端點
- **新建** `dashboard/static/index.html`：深色主題 SPA 看板，4 個 Kanban 欄，30 秒自動更新
- 驗證：`/api/stats` 和 `/api/agents` 回傳正確 JSON

### M6：systemd 部署
- **新建** `deploy/addwii-bot-a.service`（systemd unit）
- **新建** `deploy/addwii-bot-b.service`
- **新建** `deploy/addwii-bot-c.service`
- **新建** `deploy/addwii-dashboard.service`（uvicorn --port 8092）
- **新建** `deploy/cloudflared-config.md`（Cloudflare Tunnel 設定說明）
- 安裝並啟用：`systemctl enable` 4 個服務
- 驗證：4 個服務全部 **active (running)**

---

## 踩坑紀錄（重要）

### 1. SSH heredoc 嵌套 single-quote 失敗
- 症狀：`unexpected EOF while looking for matching `
- 原因：Python 程式碼中的 `human`, `agent`, `open` 打破 heredoc 引號
- 解法：在本機用 Write tool 寫到 scratchpad，再 scp 傳 VPS

### 2. schema.sql 欄位名稱不符
- 症狀：`sqlite3.OperationalError: no such column: discord_bot_id`
- 原因：程式碼假設的欄位名稱與實際 schema 不符
- 解法：`PRAGMA table_info(<table>)` 逐表驗查，再修正所有欄位引用

### 3. tasks.status CHECK 約束
- 症狀：INSERT 失敗（open 不在 CHECK 清單）
- 原因：schema 只允許 assigned/in_progress/done/blocked/cancelled
- 解法：加 STATUS_MAP 映射 + 預設用 assigned

### 4. datetime.utcnow() 棄用警告
- 解法：改用 `datetime.now(timezone.utc).replace(tzinfo=None).isoformat()`

### 5. messages 表欄位
- 實際欄位：text / role / speaker_kind / hop（bot.py 原來用 content / sender_role / sender_type / hop_count）

---

## 目前服務狀態（VPS 187.127.109.145）

| 服務 | 狀態 | 備註 |
|------|------|------|
| addwii-bot-a | active (running) | 總監 AI，A 帳號 discord_user_id 為 placeholder -1 |
| addwii-bot-b | active (running) | PM 經理 AI，B = ChengHsien = 1519082801545089195 |
| addwii-bot-c | active (running) | 組員 AI，C 帳號 discord_user_id 為 placeholder -2 |
| addwii-dashboard | active (running) | FastAPI port 8092 |

---

## 待辦（下一 Session）

1. **填入 A/C 的 discord_user_id**：在 Discord Developer Portal 取得真實帳號 ID，更新 `config.json`
2. **確認 bot 實際登入**：`journalctl -u addwii-bot-b -n 50` 確認 discord.py 連線成功
3. **測試端對端**：在 Discord #team 頻道發訊息，確認對應 bot 回應
4. **Cloudflare Tunnel 設定**：依 `deploy/cloudflared-config.md` 建立 Tunnel 讓外網可存取 dashboard
5. **監控告警**：考慮加入失敗重試通知（Telegram Bot）

---

## Git 記錄

```
be69b6c  新增 M5：Dashboard API（FastAPI 8092）+ 靜態 SPA 看板
??      新增 M6：systemd 部署設定（4 個服務 + Cloudflare Tunnel 說明）
```

Commit: `6a9a62d` — M6 deploy/ 目錄已 push 至 origin/master
