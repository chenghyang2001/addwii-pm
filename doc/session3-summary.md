# Session 3 收工摘要：客服題庫批次自動化（Row 89–403 完成，401/401）

**日期**：2026-06-25
**主題**：addwii Home Clean Room Streamlit 客服 Bot（Qwen2.5-7B）題庫自動問答，把 Row 89–403 補完，全題庫 401/401 綁定答案。

---

## 成果

- **題庫 401 題全數綁定 AI 答案**（col5 問題 → col8 答案），**零逾時、零待答**。
- Session 2 已完成 Row 4–88；本 session 完成 Row 89–403（含 7 個逾時列補跑）。
- 產出 `tools/batch_faq_query.py`（427 行，Playwright + openpyxl 批次腳本）：走 **7 輪 code-writer ↔ code-qa** + **code-reviewer APPROVED**，5 層 QA 全綠。

## 根因翻盤（最重要）

一開始以為「後端掛了 / lacp 套件壞」，實測拆解後**完全推翻**：

1. **後端 100% 正常**——範例按鈕 / Playwright `fill()` 都能讓它 8 秒內正確作答。
2. **真因 A：問題注入法失效**。舊腳本用 `page.evaluate` 的 `nativeInputValueSetter` + **合成** `KeyboardEvent`，但 Streamlit text_input **不認 `isTrusted=false` 的合成事件** → 問題沒 commit 到 server-side session_state → 後端拿空問題、2 秒空跑、不吐答案 → 偽裝成「後端不回應」。
   - **解法**：改用 Playwright 原生 `locator.fill()`（送真實事件），Streamlit 才 commit。不按 Enter（會觸發 rerun 洗掉送出鈕）。
3. **真因 B：同 session 連續問會串味**。Qwen 對話記憶存在後端 session_state，「清除」鈕只清畫面、不清後端 context → Row 90「偏鄉運費」被 Row 89「發票」主題污染。
   - **解法**：每題前 `page.goto(bot_url)` reload 開全新 session，徹底隔離。

## 6 類 bug（7 輪修正逐一攻破）

| 輪 | bug | 修法 |
|----|-----|------|
| 1 | 操作順序錯（清除鈕不在當前 tab）+ ruff F401 | 先切 tab 再點；刪未用 import |
| 2 | 切 tab 後 sleep 太短 + `click_button` 沒過濾隱形鈕（靜默失效） | 等元素 + `is_visible()` 過濾 |
| 3 | `wait_for_selector` 鎖第一匹配的隱形鈕 → timeout | 改 `wait_for_function` 掃任一可見鈕 |
| 4 | 合成事件注入不 commit（真因 A） | Playwright 原生 `fill()` |
| 5 | 同 session 串味（真因 B） | 每題 reload 開全新 session |
| 6 | 渲染類 RuntimeError 穿透殺整批（Row 262 中止） | 降級為單題 timeout 續跑，只有 BackendError 才中止 |

加固另含：`wb.save()` 改原子寫（`os.replace`）、`MIN_ANSWER_LEN` 15→8。

## 踩坑紀錄（給未來）

- **Windows 檔案鎖衝突**：批次跑時，外部監控用 `openpyxl` 開 xlsx / `cp` 備份，會擋住腳本的 `os.replace` 原子 rename（WinError 5）→ 害批次誤判「Excel 開著」中止。**批次跑時不要碰目標 xlsx**，要監控改讀 log 檔。
- **Python stdout 緩衝**：腳本不逐題 flush，log 中途看不到進度；要嘛加 `flush=True`，要嘛靠 Excel（但跑時不能碰）或完成通知。
- **單一共用後端不要平行化**：Qwen 單機單實例，多 client 並發只會排隊 + 爆逾時 + 可能拖垮。順序單流是最佳解。

## 環境 ground truth（2026-06-25 實測）

- 本機 = `192.168.23.59`；Bot 在 `192.168.23.140:8505`（純 Streamlit，13 個分頁，知識庫 28 筆）。兩台不同機器，`C:\work\addwii`（伺服器端）不在本機，`.140` 無 SSH/WinRM。
- `.140` 另跑：`:8506` 第二個 Streamlit、`:8507` LACP Flask server（端點 `/lacp/status|events|ping` 回 401、`/lacp/webhook` 回 405＝webhook 接收端其實已建在這，不是先前以為的 `.111:8000`）。

## 交付物

- `tools/batch_faq_query.py`：批次腳本（生產強度，可冪等續跑）。
- `doc/puppeteer-batch-spec.md`：腳本規格。
- 題庫檔 `~/Downloads/空氣清淨機_客服Bot_測試題庫_4題.xlsx`（401 題全綁定，工作表「測試題庫」col8）。
