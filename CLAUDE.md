# addwii-pm：三 AI 代理人 Discord 協作系統

## 專案概述

廣告公司三人團隊（A 總監 → B PM 經理 → C 組員）各自擁有一個 Discord AI 代理人 bot，在同一個頻道協作。代理人用 `claude -p` CLI（Max 訂閱，零 API 費用）產生回應，SQLite 存資料。

## 架構

```
真人（手機 Discord） → #team 頻道 → Discord Gateway
                                    ├── Bot A 行程（systemd: addwii-bot-a）
                                    ├── Bot B 行程（systemd: addwii-bot-b）
                                    └── Bot C 行程（systemd: addwii-bot-c）
                                    
VPS 共用：addwii.db（SQLite WAL）+ DASHBOARD（FastAPI :8092）
外網：Cloudflare Tunnel → 瀏覽器看板
```

## 技術堆疊

- Python 3.10+, discord.py>=2.3, FastAPI, SQLite（WAL）
- `claude -p` CLI（Max 訂閱）作為 AI 後端
- 部署：VPS（Hostinger）+ systemd 4 個 service

## 執行方式

```bash
# 初始化 DB（第一次）
PYTHONUTF8=1 python tools/init_db.py

# 啟動單一 bot（測試用）
PYTHONUTF8=1 python main.py --role B

# 啟動 dashboard（測試用）
PYTHONUTF8=1 uvicorn dashboard.api:app --port 8092
```

## 目錄結構

```
addwii-pm/
├── config.json          # Discord guild/channel/members 設定（需填入真實 ID）
├── .env                 # Bot tokens（不 commit，從 .env.example 複製）
├── core/
│   ├── config.py        # Config 單例（✅ 完成 QA）
│   ├── db.py            # SQLite WAL context manager（⚠️ 需 VPS QA）
│   └── logger.py        # 日誌模組（✅ 完成 QA）
├── db/
│   └── schema.sql       # 完整 DB schema（⚠️ 需 VPS QA）
├── tools/
│   └── init_db.py       # DB 初始化腳本（⚠️ 需 VPS QA）
├── doc/
│   └── architecture.md  # 系統架構文件（208 行，arch-deck 產出）
├── mermaid/
│   └── 20260624-addwii-ai代理/
│       ├── mmd/         # 5 張架構 .mmd + mmd/wiki/ 7 張 GitNexus wiki .mmd
│       ├── png/         # 5 張架構 PNG + png/wiki/ 7 張 wiki PNG
│       └── addwii-pm-架構圖表合輯.pptx  # 14 頁簡報合輯（arch-deck 產出）
├── agent/               # M2+ 建立
├── personas/            # M2+ 建立
├── dashboard/           # M5 建立
└── deploy/              # M6 建立
```

## 重要架構決策

1. **Discord 而非 Telegram**：Discord bot 可以原生收到其他 bot 的訊息（開啟 Message Content Intent），不需要 orchestrator 中間層
2. **防迴圈機制**：`[hop:N]` 標記嵌入訊息尾部，max_hops=3；**不可用** `if message.author.bot: return`（會讓 bot 看不到彼此）
3. **SQLite WAL**：三個 bot 行程並發寫入，WAL 模式 + timeout=30 夠用
4. **零 API 費用**：`claude -p` 走 Max 訂閱；不設 ANTHROPIC_API_KEY 全域環境變數

## Discord 設定前置（部署前必做）

1. 在 Discord Developer Portal 建三個 bot 應用程式
2. 每個 bot 開啟：Settings → Bot → **Message Content Intent**（Privileged）
3. 邀請三個 bot 進同一個 Discord Server（需 Manage Server 權限）
4. 填入 `config.json`：guild_id, channel_id, 三個 discord_user_id（真人帳號）
5. 在 VPS 設定 `.env`：BOT_TOKEN_A, BOT_TOKEN_B, BOT_TOKEN_C

## 開發規範（給 VPS 上的 Claude Code）

- 所有 .py 檔案必須走 code-writer → code-qa（sequential），才能 commit
- 所有自然語言、commit message、docstring 用**繁體中文**
- commit 後自動 push（`git push`）
- 不硬編碼路徑，一律用 `Path(__file__).resolve()` 或 `$HOME`
- `PYTHONUTF8=1` 加在所有 Python 執行指令前
