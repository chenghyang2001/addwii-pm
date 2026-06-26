# Session 3 摘要：客服題庫批次自動化（401/401 完成）

**日期**：2026-06-25（跨至 06-26 收工）
**主題**：addwii Home Clean Room Streamlit 客服 Bot（Qwen2.5-7B）題庫自動問答，Row 89–403 補完，全題庫 401/401 綁定答案。

---

## 完成事項

### 批次自動化（核心交付）

- **題庫 401/401 題全綁定 AI 答案**（col5 問題 → col8 答案），**零逾時、零待答**。Session 2 已完成 Row 4–88，本 session 完成 Row 89–403 + 補跑 7 個逾時列。
- 產出 `tools/batch_faq_query.py`（427 行，Playwright + openpyxl），走 **7 輪 code-writer ↔ code-qa** + **code-reviewer APPROVED**，5 層 QA 全綠。

### 根因翻盤（最重要的發現）

- 推翻舊判斷「後端 lacp 套件壞」——**後端 100% 正常**。「不回應」真因有二：
  1. **注入法失效**：`nativeInputValueSetter` + 合成 `KeyboardEvent`，Streamlit 不認 `isTrusted=false` → 問題沒 commit。改用 Playwright 原生 `fill()`。
  2. **同 session 串味**：Qwen 對話記憶存後端 session_state，「清除」只清畫面。每題 `page.goto` reload 開全新 session。

### 加固（reviewer 建議 + 實戰中止後補）

- 渲染類 `RuntimeError` 降級為單題 timeout 續跑（只有 `BackendError` 才中止整批）——修正 Row 262 中止。
- `wb.save()` 改原子寫（`os.replace`）；`MIN_ANSWER_LEN` 15→8。

## 關鍵技術筆記

- **Streamlit text_input 只認真實事件**：合成 KeyboardEvent 不觸發 websocket commit；Playwright `fill()` / `press()` 走 CDP 送真實事件才有效。
- **單一共用後端不要平行化**：Qwen 單機單實例，並發只會排隊+爆逾時+可能拖垮。順序單流是最佳解。
- **Windows 檔案鎖衝突**：批次跑時外部 `openpyxl`/`cp` 開 xlsx 會擋 `os.replace` 原子 rename（WinError 5）→ 害批次中止。批次跑時不可碰目標 xlsx，監控改讀 log。
- **Python stdout 緩衝**：腳本不逐題 flush，log 中途看不到進度；要嘛 `flush=True`、要嘛靠完成通知。
- **環境 ground truth**：本機 `192.168.23.59`；Bot 在 `.140:8505`（純 Streamlit）；`.140:8507` 有活的 LACP Flask server（webhook 接收端其實建在這，非舊認知的 `.111:8000`）。

## 產出檔案

| 檔案 | 說明 |
|------|------|
| `tools/batch_faq_query.py` | 批次腳本（生產強度、冪等續跑），commit d03fe34 |
| `doc/puppeteer-batch-spec.md` | 腳本規格，commit d03fe34 |
| `doc/session3-summary.md` | 收工摘要（doc 版） |
| `~/Downloads/空氣清淨機_客服Bot_測試題庫_4題.xlsx` | 題庫檔 401 題全綁定（工作表「測試題庫」col8） |

---

## HANDOFF（下次 session 優先處理）

### 立即行動

- [ ] （可選）把完成的題庫 Excel 上傳 Google Drive 或交付給需求方驗收
- [ ] （可選）對 401 筆答案做品質統計分析（對題率、知識庫覆蓋缺口、客訴語氣抽樣）
- [ ] 回到 addwii-pm 本業：三 AI 代理人 Discord 系統的 agent/personas/dashboard/deploy 模組（M2+，目前 ❌ 未建立）

### 進行中（需接續）

- 無未完成的批次工作——客服題庫任務 100% 結案（401/401）。
- addwii-pm 主專案（Discord 三代理人）仍在 core 模組階段（config/db/logger 完成，agent/dashboard/deploy 未建）。

### 注意事項

- 客服 Bot 後端正常，**不需修 `C:\work\addwii` 的 lacp**（舊 handoff 誤判，已更正）。
- 若再跑類似 Streamlit 批次：用 `tools/batch_faq_query.py`，注意「批次跑時不碰 xlsx」「不要平行化單一後端」兩條鐵律。
- `__TIMEOUT__` 列 resume 會跳過，需單獨補跑（本次 7 個已補完）。
