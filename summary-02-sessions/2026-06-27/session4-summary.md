# Session 4 — aihcr-daily sensor 抽取多項強化（在 addwii-pm 目錄跑）

**日期**：2026-06-27
**機器**：DESKTOP-FFSFP66（家用機）
**重要說明**：本 session 雖在 `addwii-pm` 工作目錄啟動，但**所有實際工作都屬於 `aihcr-daily` 專案**（sensor_raw_data 歷史抽取管線）。addwii-pm 的 Discord bot 本體（M2-M6）本次**未動**。詳細工作記錄見 `aihcr-daily/doc/session-2026-06-27-summary.md`，本檔為 addwii-pm session 序列的存底與指標。

## 完成事項（全屬 aihcr-daily，皆三 agent 鐵律 + push GitHub）

### 程式改動

- **`5ee5be3`** — ① wrapper 加 `export PATH="$HOME/.local/bin"`（修 cron 找不到 gws → `--upload` 靜默跳過的雷）；② run_stamp 改台灣時區（`Z`→`+0800`）。
- **`4d15f7b`** — Drive 上傳改每日日期子目錄 `AIHCR-sensor-history/<YYYY-MM-DD>/`（`find_or_create_date_subfolder`，建夾失敗 fallback root）。
- **`35fa8aa`** — 檔名縮短為純日期（run_stamp `%Y%m%d`）。
- **`e449dfd`** — 抽取名單 `[37,26,86]` → `[37,26,86,309,305]`（採購客戶比對，經 @小研 live DB 唯讀查證）。
- **`b2f82b8`** — CSV 檔名加 user 名字（`safe_name_part`，`user_<id>_<名字>_<date>.csv`）。

### 文件 / 記憶歸檔

- `aihcr-daily/doc/session-2026-06-27-summary.md`（主總結）+ `aihcr-daily/doc/sensor-export-0627-0900-run-record.md`（驗證證據）。
- addwii-pm 留副本 `doc/2026-06-27-aihcr-sensor-work-summary.md`（`d35fee1`）。
- 兩台機器（user `C--Users-user-...` / 公司機 `C--Users-B00332-...`）的 aihcr-daily 長期記憶都更新（B00332 那份順便補上原本斷掉的 `sensor_history_export.md` 指標）。

### 驗證（全程唯讀，@小雲 在 VPS、@小研 在 zap_api）

- 多輪 cron 等效 test run + 三個一次性 `at` job（#17 09:00 / #18 11:00 / #19 11:50）全部 exit 0、驗證全 PASS、佇列已清空無殘留。
- 305 watermark=0 首次回填 521 列；309 抓 0 列（未啟用）；「重用既有子夾 + 同名 gws update 覆蓋」idempotent 路徑實證（同日重跑不堆積重複檔）。

## 關鍵技術筆記

- **cron PATH 踩坑**：互動 SSH 找得到 gws ≠ cron 找得到（cron PATH = `/usr/bin:/bin`）。`--upload` 找不到 gws 會 exit 0 但靜默跳過上傳，只記 warning。
- **305/308 共用同一顆 mac `4802af0dffda`**（同一台 ZS2，6/9 綁 305、6/22 重綁 308），皆中國端代理測試帳號、非台灣傲人科技本名。
- **純日期檔名取捨**：同一天跑多次會同名覆蓋 + rebuild 缺口；正規 cron ≤1/日不觸發。

## 產出檔案

| 檔案 | 專案 | 說明 |
|------|------|------|
| `scripts/sensor_history_export.py` | aihcr-daily | 主腳本（5 處改動）|
| `run-sensor-export-vps.sh` | aihcr-daily | wrapper PATH 修正 |
| `config.json` | aihcr-daily | users 擴充 309/305 |
| `doc/session-2026-06-27-summary.md` | aihcr-daily | 主總結 |
| `doc/sensor-export-0627-0900-run-record.md` | aihcr-daily | 驗證證據 |
| `doc/2026-06-27-aihcr-sensor-work-summary.md` | addwii-pm | 副本留底 |
| `summary-02-sessions/2026-06-27/session4-summary.md` | addwii-pm | 本檔 |

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] **業務確認 305 的 mac `4802af0dffda` 歸屬**（是否＝出貨給傲人科技那台）；確認非傲人科技則從 `aihcr-daily/config.json` 的 `sensor_export.users` 移除 305。
- [ ] **處理 PII 風險**：`AIHCR-sensor-history` 為公開（anyone/reader），CSV 含 user_name+mac_address、客戶名也進檔名 → 接真實客戶資料前須改限定 email 分享或去識別化。
- [ ] 蒙特梭利（309）裝機啟用後會自動開始抓資料（無需改設定，觀察即可）。

### 進行中（需接續）

- aihcr-daily sensor 抽取功能已全部上線並驗證，台灣 13:00 正規 cron（`0 5 */2 * *`，帶 `--notify`）會用 5 人名單自動跑（本 session 未盯第一次 notify 跑，可下次確認三人是否收到通知）。
- **addwii-pm 本體（Discord 三 bot M2-M6）狀態未變**：仍是 MEMORY.md 記載的「小雲執行中」，本 session 完全沒碰，下次回 addwii-pm 工作時接續 M2-M6。

### 注意事項

- 本 session 在 addwii-pm 目錄跑 aihcr-daily 的事，兩專案 git repo 各自獨立；aihcr-daily 改動都在它自己的 repo（已 push）。
- aihcr-daily 的完整知識在 `aihcr-daily/doc/session-2026-06-27-summary.md` 與該專案 memory `feature_sensor_history_export.md`。
- 唯讀鐵律：zap_api 全程只 SELECT。
