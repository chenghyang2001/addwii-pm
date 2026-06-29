# Session 5 Summary — 2026-06-29

## 日期

2026-06-29

## 完成事項

### 1. 修復 `.claude` repo git merge 衝突

- 問題：`git pull` 被 `.last-cleanup` 與 `.last-update-result.json` 兩個本機未 commit 改動阻擋
- 解法：`git stash → git merge origin/main → git stash drop`
- 結果：成功同步 36 個檔案（含新 short-term 記憶、settings.json、多個 project memory）

### 2. NUC 下線 → VPS 升格為 AIHCR 唯一 runtime（重大架構變更）

- **觸發**：使用者明確宣告 NUC（192.168.51.33）已實體移除
- **原三層架構**：本機 PC（開發）→ NUC（部署主層）→ VPS（備援）
- **新兩層架構**：本機 PC（開發）→ VPS（部署主層，唯一 runtime）
- 所有原「@小核」任務全移給「@小雲」；NUC IP 不再有效

### 3. 全域規則與記憶同步更新

- 更新 `~/.claude/instructions/aihcr-deployment.md`：移除 NUC 全部內容，VPS 升格為主層，標注 VPS 路徑待 @小雲 SSH 實測確認
- 新建 `memory/nuc-removed-vps-primary.md`：記錄變更事實與後續行為規則
- 更新 `memory/MEMORY.md`：加入新記憶索引條目

## 關鍵技術筆記

### NUC 移除後的行為規則

- 「小核查今天 AIHCR 跑了沒」→ 一律找 **@小雲**（VPS `187.127.109.145`）
- VPS 的 cron 時間、路徑尚待 @小雲 SSH 實測（不可沿用 NUC 的 04:00 Asia/Taipei）
- 全域 `aihcr-deployment.md` 已更新，下個 session 起即時生效

### git stash 解衝突流程

```bash
git stash && git merge origin/main && git stash drop
```

機器特定檔案（`.last-cleanup`、`.last-update-result.json`）每次兩機同步都可能衝突，用 stash 是正確解法。

## 產出檔案

| 檔案 | 類型 | 說明 |
|------|------|------|
| `~/.claude/instructions/aihcr-deployment.md` | 修改 | NUC 移除，三層→兩層架構，@小核→@小雲 |
| `~/.claude/projects/C--Users-B00332-workspace-addwii-pm/memory/nuc-removed-vps-primary.md` | 新建 | NUC 下線記憶條目 |
| `~/.claude/projects/C--Users-B00332-workspace-addwii-pm/memory/MEMORY.md` | 修改 | 加入新記憶索引 |

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] 請 @小雲 SSH 到 VPS（187.127.109.145）確認 AIHCR cron 實際路徑、時間、log 位置，並更新 `~/.claude/instructions/aihcr-deployment.md` 的「待確認」欄位
- [ ] 確認 VPS 上 AIHCR 今日是否正常執行（cron log 查看）
- [ ] 繼續 addwii-pm Discord bot 開發（M2 agent/ + personas/ 模組）

### 進行中（需接續）

- Discord bot core 模組（config.py ✅、logger.py ✅、db.py ⚠️需VPS QA）已完成；`agent/` 和 `personas/` 模組尚未建立（M2+）
- AIHCR 整體系統已從 NUC 遷移到 VPS，但 VPS 端的具體 runtime 狀態尚未驗證

### 注意事項

- VPS AIHCR 路徑`~/aihcr-daily/`與時區需要 SSH 實測，**不可沿用舊 NUC 記憶**（NUC 是 Asia/Taipei 04:00，VPS 時區可能不同）
- `~/.claude` repo 兩機同步時，`.last-cleanup` 類的機器特定檔案用 `git stash` 解決衝突
