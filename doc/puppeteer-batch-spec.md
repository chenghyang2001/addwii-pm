# Puppeteer 客服題庫批次自動化 — 腳本規格（B）

**狀態**：規格先行（後端答案引擎修復後再進三 agent 鐵律建置）
**日期**：2026-06-25
**前置阻擋**：`192.168.23.140:8505` 後端問答引擎目前不回答（見下方「前置條件」），修好才能跑。

---

## 1. 目標

把客服測試題庫的 Row 89–403（共 315 題）自動送進 addwii Streamlit Bot 的「產品知識問答」，擷取 AI 回答寫回 Excel col8。延續 Session 2 已完成的 Row 4–88（同一檔、同一方法）。

## 2. 輸入 / 輸出

| 項目 | 值 |
|------|----|
| Bot URL | `http://192.168.23.140:8505/` |
| 題庫檔 | `~/Downloads/空氣清淨機_客服Bot_測試題庫_4題.xlsx` |
| 工作表 | `測試題庫`（總 403 行） |
| 問題欄 | col5（第 5 欄） |
| 答案欄 | col8（第 8 欄，寫入目標） |
| 處理範圍 | col8 為空的列（自然涵蓋 Row 89–403，並可續跑） |

## 3. 核心邏輯（條列，不寫程式碼）

1. **續跑點偵測**：openpyxl 開檔，掃 col8，從第一個「col5 有問題、col8 為空」的列開始；已填的列一律跳過（冪等、可中斷續跑）。
2. **瀏覽器**：用 Patchright / Playwright（Chromium）開 Bot URL，等 Streamlit 載入（等 `[role="tab"]` 出現 + `/_stcore/health`=ok）。
3. **每題流程**（沿用 Session 2 實證 + 本次修正）：
   1. 點「🗑️ 清除」→ 等 2.5s
   2. 點「🌿 產品知識問答」tab → 等 1.2s
   3. 找 placeholder 含 `CADR|坪|問題` 的可見 `input[type=text]`，用 **React controlled component setter** 注入問題：
      `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set` → `inp.dispatchEvent(input)` → **送 Enter keydown/keyup（keyCode 13）** → `change` → `blur`
   4. **等 3s**（讓 Streamlit 透過 websocket 把值 commit 到 server-side session_state — 本次踩坑：太快點送出會送出空字串）
   5. 點「🔍 送出問題」→ 等 8s（Qwen 生成）
   6. 點「🌿 產品知識問答」tab **一次**（Streamlit 重渲染常跳回第一 tab）→ 等 2.5s
   7. **擷取答案**：找含「💬 AI 回答」的 `[data-testid="stMarkdownContainer"]`，取**其後一個**元素的 `innerText`；輪詢至多 ~30s 直到內容長度 > 15
   8. openpyxl 寫入 col8、`wb.save()`（**每題即存**，防中途崩潰丟進度）
4. **節流**：每題之間留間隔，避免後端排隊崩潰。

## 4. 邊界條件 / 錯誤處理

| 情況 | 處理 |
|------|------|
| 某題等 30s 仍無答案 | 標記該列為 `__TIMEOUT__`（或留空 + 記 log），continue 下一題，**不中斷整批** |
| 偵測到後端錯誤（Traceback/ModuleNotFoundError/TypeError） | 立即停止 + 印錯誤（後端壞了硬跑無意義） |
| 連續 N 題（如 3 題）都 TIMEOUT | 中止並警告「後端可能掛了」 |
| 答案 marker「💬 AI 回答」找不到 | fallback：找含客服語氣關鍵字（您好/根據/建議/很抱歉）且長度 > 30 的區塊；仍無則記 TIMEOUT |
| 題目本身為空（col5 空） | 跳過 |
| Excel 被別的程式開著鎖定 | try/except + 清楚錯誤訊息，提示關閉 Excel |
| 瀏覽器 / 頁面崩潰 | try/except 單題，重新 navigate 後續跑（不從頭） |

## 5. 依賴

- Python 3.10+，`PYTHONUTF8=1`
- `patchright` 或 `playwright`（Chromium）；`openpyxl`
- 不可硬編碼路徑：題庫用 `Path.home()/'Downloads'/...`
- 不需登入（Bot 無認證）

## 6. 前置條件（跑之前必須成立）

1. ✅ **後端答案引擎已修復**：在 .140 重啟後，**手動點一次內建範例鈕（如「多久換一次濾網？」）確認會在 ~8s 內回答**。本規格的批次在此之前不可啟動。
2. Excel 檔未被 Excel 程式開啟（避免鎖定）。
3. 本機 Chromium 可用。

## 7. 驗收

- 乾跑模式 `--dry-run`：只走前 3 題、印答案、**不寫 Excel**，驗證互動序列與擷取正確。
- 正式跑：col8 由 88 推進到 403；每題即存；最終回報「成功 N / timeout M」。
- 抽查 3 題答案內容合理（非空、非問題回音、與問題相關）。

## 8. 本次 session 踩坑紀錄（給未來建置者）

- **Streamlit text_input 是 server-side session_state**：JS 注入 value 後，必須等 ~3s 讓 websocket 把值送到後端，否則點送出會送出舊/空值。Session 2 靠「填完送 Enter + 等待」才成功。
- **送出後 Streamlit 重渲染會跳回第一個 tab**：必須重點「產品知識問答」tab 一次再擷取；但**不要在輪詢中持續重點**（每次點都觸發 rerun、會清掉答案）。
- **「前端 200」不代表「引擎能答」**：本次前端全綠（health ok、websocket 連、banner 即時）但問答完全不吐，連內建鈕也不答 → 後端答案管線死。批次前務必先實測一題。
- 答案 marker 是 `💬 AI 回答`，取其後一個 `stMarkdownContainer`。
