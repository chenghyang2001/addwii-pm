# Session 總結 — 2026-06-27：sensor_raw_data 抽取管線多項強化

> ⚠️ 這個 session 實際是在另一個專案目錄（`addwii-pm`）的 Claude session 跑的，但**所有工作都屬於 `aihcr-daily`**（sensor 歷史抽取管線）。本總結放在 aihcr-daily 供日後在本專案回顧；addwii-pm 也留一份副本。
> 詳細的單次驗證證據另見 [`sensor-export-0627-0900-run-record.md`](./sensor-export-0627-0900-run-record.md)。

## 一、背景

延續 Session 42（2026-06-26，林紫鈴交辦）建立的 `scripts/sensor_history_export.py`（zap_api `sensor_raw_data` 增量抽取 → 驗證 → CSV → Google Drive）。今天針對部署正確性、檔名格式、抽取名單做了一連串強化，全部走 code-writer → code-qa →（視情況）code-reviewer 三 agent 鐵律，並由 @小雲 在 VPS、@小研 在 zap_api 做唯讀驗證。

## 二、今天的 commit（aihcr-daily，皆已 push GitHub）

| commit | 內容 | 三 agent |
|---|---|---|
| `5ee5be3` | ① wrapper 加 `export PATH="$HOME/.local/bin"`（修 cron 找不到 gws → `--upload` 靜默跳過的雷）；② run_stamp 改台灣時區（`Z`→`+0800`）| ①小修豁免 ②writer→qa→reviewer |
| `4d15f7b` | 每日日期子目錄：`find_or_create_date_subfolder`，當天檔案進 `YYYY-MM-DD` 子夾，建夾失敗 fallback root | writer→qa(3)→reviewer |
| `969cefa` | 09:00 一次性驗證記錄 doc | 文件 |
| `35fa8aa` | 檔名縮短為純日期（run_stamp `%Y%m%d`，去掉 `T時分秒+0800`）| writer→qa(2)→reviewer |
| `e449dfd` | 抽取名單加採購客戶 309 + 305 | config.json |
| `b13a9b0` | 記錄檔補充 | 文件 |
| `b2f82b8` | CSV 檔名加 user 名字（`safe_name_part`，`user_<id>_<名字>_<date>.csv`）| writer→qa(3)→reviewer |

## 三、做了什麼（依序）

1. **修 cron 上傳 PATH bug**：cron 的精簡 PATH（`/usr/bin:/bin`）找不到裝在 `~/.local/bin` 的 gws → `--upload` 會 exit 0 但靜默跳過上傳。wrapper 顯式補 PATH 後，cron 自動上傳才會生效。
2. **檔名時區**：run_stamp 從 UTC（`...Z`）改台灣時區（`...+0800`），讓檔名日期前綴對齊台灣當日（跨午夜不再標前一天）。
3. **每日日期子目錄**：Drive `AIHCR-sensor-history` 底下每天一個 `YYYY-MM-DD` 子夾，當天 CSV+verify 進當天子夾，不再平鋪；建夾失敗 fallback 到 root（資料不遺失）。
4. **檔名縮短純日期**：`user_37_20260627.csv`、`verify_20260627.md`。取捨：同一天跑多次會同名覆蓋且 rebuild 缺口；正規 cron 每 2 天一次（≤1/日）不觸發，已接受。
5. **抽取名單擴充**（見下節）。
6. **CSV 檔名加 user 名字**：`user_<id>_<名字>_<date>.csv`（`safe_name_part` 清檔名非法字元/空白/控制字元、保留中文、上限 40 字；無名字退回 `user_<id>_<date>.csv`）。

## 四、抽取名單：[37,26,86] → [37,26,86,309,305]

依「ZS2 採購名單 Excel」（5 客戶）交辦找 DB user_id。**經 @小研 即時唯讀比對 live zap_api**：

| # | 採購客戶 | DB | user_id | 處置 |
|---|---|---|---|---|
| 1 | 建國達特楊診所/楊志盛 | 查無註冊 | — | 無法加 |
| 2 | 周存聖（11 組最大單）| 查無註冊 | — | 無法加 |
| 3 | 吳增堅(陸) | 查無註冊 | — | 無法加 |
| 4 | 蒙特梭利森林/吳明倫 | 已註冊 0 讀數(6/23) | **309** | ✅ 加（觀察）|
| 5 | 傲人科技/張曉萍 | 疑似、歸屬存疑 | **305** | ✅ 加（待確認）|

**305/308 關鍵真相**：兩者共用同一顆 mac `4802af0dffda`＝同一台 ZS2（6/9 綁 305 灌 521 筆、6/22 重綁 308 灌 2 筆）；305 掛名「惠州伯乐恒科技」、308 名「Abc」，皆中國端代理批次測試帳號，**非台灣傲人科技本名**。已加 305 但 **mac 歸屬待業務確認**。

## 五、驗證（全程唯讀，@小雲 在 VPS 跑）

- 多輪 cron 等效 test run（不帶 --notify）皆 exit 0、驗證全 PASS。
- **09:00 一次性 at job**：使用者先清空 Drive → 乾淨重建 `2026-06-27/` 子夾、4 檔全進子夾、走「建立新」分支。
- 加 309/305 驗證：305 watermark=0 首次回填 521 列、309 抓 0 列，全 PASS。
- 加名字驗證：5 user 全帶名字（含簡體中文完整保留），子夾舊格式檔由小雲精確比對後清除，剩 6 個帶名字檔 + verify。

## 六、排程現況

| 排程 | 位置 | 內容 |
|---|---|---|
| 正規 cron `0 5 */2 * *`（UTC 05:00 = 台灣 13:00）| VPS crontab | `run-sensor-export-vps.sh`，帶 `--upload --notify`，用 5 人名單；首次帶 notify |
| at job #18（UTC 03:00 = 台灣 11:00）| VPS at | 一次性 test，不帶 notify，log → manual-1100-run.log |
| at job #19（UTC 03:50 = 台灣 11:50）| VPS at | 一次性 test，不帶 notify，log → manual-1150-run.log |

## 七、待辦 / 風險

- [ ] **業務確認 305 的 mac `4802af0dffda` 歸屬**；若非傲人科技則從 config.json 移除 305。
- [ ] 蒙特梭利（309）裝機啟用後增量自動開始抓，無需改設定。
- [ ] #1/#2/#3（達特楊診所 / 周存聖 / 吳增堅）待業務催裝機註冊後取得 user_id 再加。
- [ ] 🔴 **PII 風險**：`AIHCR-sensor-history` 為公開（anyone/reader），CSV 含 user_name + mac_address，且**現在客戶名也進到檔名**（檔案列表即洩客戶清單）。接真實客戶資料前須改限定 email 分享或去識別化。
- [ ] NICE_TO_HAVE（reviewer 提，未做）：日期改從單一 datetime 物件導出（消除字串切片耦合）；`find_or_create_date_subfolder` 與既有 `find_or_create_subfolder` 重構共用；`safe_name_part` 改白名單（涵蓋 DEL/C1/零寬/emoji）；同 user 改名後孤兒 delta 檔清理。

## 八、關鍵路徑 / 設定（備查）

- 主腳本：`scripts/sensor_history_export.py`（`safe_name_part` / `find_or_create_date_subfolder` / run_stamp）
- wrapper：`run-sensor-export-vps.sh`（PATH 修正在此）
- 名單設定：`config.json` → `sensor_export.users`（加減 user 改這、不用動程式碼）
- VPS：repo `/home/claude/aihcr-daily`；DB 密碼 env `MYSQL_RD2_PASSWORD`（唯讀 rd2）；唯讀鐵律只 SELECT
- Drive：`AIHCR-sensor-history` id `1XOSwU4VVBV5iR2eUSmasjAF2i_9XUyHm`（公開）
