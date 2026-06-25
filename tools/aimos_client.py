"""AIMOS REST API 最小 client（LACP 協議唯讀對接 + 建立任務骨架）。

用途：取代原本用 Puppeteer 驅動 Streamlit UI 的問答方式，改以程式化方式
對接 AIMOS（鼎創達/addwii 的 AI 任務管理平台）。

本模組只用 Python 標準庫，無任何第三方依賴。提供：
- AimosClient：封裝 LACP 認證與請求的最小 client
- 唯讀冒煙測試 CLI（status / ping / list_pending_tasks）
- LACP 輪詢消費者（poll /lacp/events → 處理 task.created → 回報 /lacp/webhook），
  繞過尚未建置的 inbound webhook，以輪詢方式消費 AIMOS 推給 addwii 的事件

執行前需先設定金鑰環境變數，例如：export AIMOS_LINGCE_KEY=你的金鑰
（或於建構 AimosClient 時以 lingce_key 參數傳入）。本 repo 為 public，
金鑰一律不寫入程式碼。Base URL 可用 AIMOS_BASE_URL 覆蓋，未設定走預設常數。
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# 預設 Base URL：對接文件 v1.0 提供的 LAN 內網位址。
# URL 不是機密，保留常數方便內網開箱即連；金鑰則一律不寫死（見 __init__）。
DEFAULT_BASE_URL = "http://192.168.23.186:8560"


class AimosError(Exception):
    """AIMOS 對接錯誤。

    status_code：HTTP 狀態碼；連線層失敗（逾時/連不上）時為 None。
    message：繁中錯誤說明。
    """

    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class AimosClient:
    """AIMOS LACP REST 最小 client。"""

    def __init__(self, base_url=None, lingce_key=None, timeout=8):
        # base_url 解析順序：建構參數 → 環境變數 → 預設常數（URL 非機密可有預設）。
        self.base_url = (
            base_url or os.environ.get("AIMOS_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        # 金鑰解析順序：建構參數 → 環境變數；刻意「沒有預設常數」。
        # 本 repo 為 public，明文金鑰一旦 commit 會公開到網際網路並觸發
        # GitHub secret scanning，因此缺金鑰時直接拒絕運作而非靜默帶空值。
        self.lingce_key = lingce_key or os.environ.get("AIMOS_LINGCE_KEY")
        if not self.lingce_key:
            raise AimosError(
                status_code=None,
                message="缺少 AIMOS 金鑰：請設定環境變數 AIMOS_LINGCE_KEY，"
                "或建構 AimosClient 時傳入 lingce_key",
            )
        # timeout 預設 8 秒：LAN 內網延遲極低，8 秒足夠涵蓋 AI 任務排隊，
        # 同時避免對端異常時請求無限掛住。
        self.timeout = timeout

    def _build_request(self, method, url, body):
        """組裝帶 LACP 認證 header 的 Request 物件。"""
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url=url, data=data, method=method)
        # X-LINGCE-KEY 是 AIMOS LACP 的認證 header，缺少會被回 401。
        req.add_header("X-LINGCE-KEY", self.lingce_key)
        req.add_header("Content-Type", "application/json")
        return req

    def _request(self, method, path, body=None):
        """送出單一請求並回傳解析後的 dict，失敗一律轉成 AimosError。"""
        url = self.base_url + path
        req = self._build_request(method, url, body)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            # HTTP 4xx/5xx（如 401/404）：嘗試讀回應 body 解析 message，
            # 讓上層拿到 AIMOS 的繁中錯誤說明而非裸狀態碼。
            detail = self._extract_http_message(e)
            raise AimosError(
                status_code=e.code,
                message=f"AIMOS 請求失敗（{method} {path}）：HTTP {e.code}，{detail}",
            ) from e
        except urllib.error.URLError as e:
            # 連線層失敗（DNS/逾時/連不上）：沒有 HTTP 狀態碼。
            raise AimosError(
                status_code=None,
                message=f"無法連線 AIMOS（{method} {path}）：{e.reason}",
            ) from e
        except json.JSONDecodeError as e:
            raise AimosError(
                status_code=None,
                message=f"AIMOS 回應非合法 JSON（{method} {path}）：{e}",
            ) from e
        except (TimeoutError, OSError) as e:
            # 保險網：urlopen(timeout=) 只涵蓋「連線階段」逾時；連線成功後卡在
            # resp.read() 的「讀取階段」逾時，Python 3.10+ 會拋 TimeoutError，
            # 上面三個分支都接不到。補這層確保「失敗一律轉成 AimosError」契約。
            # 必須放在 URLError 之後：URLError 是 OSError 子類，若放前面會把
            # 連線層錯誤一起吃掉、蓋掉較精準的 URLError 訊息。
            raise AimosError(
                status_code=None,
                message=f"AIMOS 連線/讀取逾時或中斷（{method} {path}）：{e}",
            ) from e

    @staticmethod
    def _extract_http_message(http_error):
        """從 HTTPError body 取出 message 欄位，失敗則回原因字串。"""
        try:
            payload = json.loads(http_error.read().decode("utf-8"))
            return payload.get("message", http_error.reason)
        except (json.JSONDecodeError, ValueError, AttributeError):
            # body 不是 JSON 或讀取失敗時，退回 HTTP reason，不再丟新例外。
            return http_error.reason

    def ping(self, source="addwii"):
        """POST /lacp/ping：確認 AIMOS LACP 服務存活。"""
        return self._request("POST", "/lacp/ping", body={"source": source})

    def status(self):
        """GET /lacp/status：取得 system_id / version / queue_size 等狀態。"""
        return self._request("GET", "/lacp/status")

    def list_pending_tasks(self, assignee_type="service", assignee_id=None):
        """GET /api/v1/tasks/pending：列出待處理任務（回傳整包 dict）。"""
        params = {"assignee_type": assignee_type}
        # assignee_id 為 None 時不放進 query：AIMOS 以「有無此參數」區分
        # 查 service 全體 vs 查特定 agent，送空值會改變語意。
        if assignee_id is not None:
            params["assignee_id"] = assignee_id
        query = urllib.parse.urlencode(params)
        return self._request("GET", f"/api/v1/tasks/pending?{query}")

    def create_task(
        self,
        title,
        content,
        assignee_id,
        creator_id,
        priority="normal",
        assignee_type="service",
        creator_type="agent",
    ):
        """POST /api/v1/tasks：建立任務（骨架方法，尚未實測）。

        警告：此端點（POST /api/v1/tasks）尚未經實測驗證，對接文件未列出
        外部建立任務的 REST 端點；正式使用前需先與 AIMOS 端確認端點與欄位。
        本方法保留供日後啟用，冒煙測試不會呼叫它。

        assignee_id / creator_id 刻意設為無預設的必填參數：對接文件 v1.0
        雖列有範例 ID，但未實測，呼叫者須自行向 AIMOS 端確認正確 ID 再傳入，
        避免把來路不明的 magic number 寫死成預設值。
        """
        # 用 is None or not strip() 判斷，避免把合法但 falsy 的值誤判；
        # 同時擋下純空白字串。title 與 content 各自回報，方便定位是哪個欄位空。
        if title is None or not str(title).strip():
            raise ValueError("title 不可為空")
        if content is None or not str(content).strip():
            raise ValueError("content 不可為空")
        body = {
            "title": title,
            "content": content,
            "priority": priority,
            "assignee_type": assignee_type,
            "assignee_id": assignee_id,
            "creator_id": creator_id,
            "creator_type": creator_type,
        }
        return self._request("POST", "/api/v1/tasks", body=body)

    def poll_events(self, source="addwii", limit=20, since=None):
        """GET /lacp/events：拉取 AIMOS 推給本 source 的事件（回傳整包 dict）。"""
        params = {"source": source, "limit": limit}
        # since 為 None 時不帶此參數：語意同 list_pending_tasks 的 assignee_id，
        # 「無 since」代表從頭拉，送空字串會被當成非法游標。
        if since is not None:
            params["since"] = since
        query = urllib.parse.urlencode(params)
        return self._request("GET", f"/lacp/events?{query}")

    def report_result(
        self,
        task_id,
        run_output,
        agent_id="addwii-ext",
        status="done",
        output_file_path="",
        duration_sec=0,
        error_msg="",
    ):
        """POST /lacp/webhook：回報任務執行結果（event_type=agent.result）。

        agent_id 預設 addwii-ext（agents.id=6）為已登記的 agent_code，勿用
        未登記值（如 addwii_ai），否則 AIMOS 端 FOREIGN KEY 會失敗。
        """
        if task_id is None or not str(task_id).strip():
            raise ValueError("task_id 不可為空")
        # status 僅允許 done / fail：避免送出 AIMOS 無法識別的狀態值。
        if status not in {"done", "fail"}:
            raise ValueError("status 必須是 done 或 fail")
        body = {
            "event_type": "agent.result",
            "source": "addwii",
            "data": {
                "agent_id": agent_id,
                "task_id": task_id,
                "status": status,
                "run_output": run_output,
                "output_file_path": output_file_path,
                "duration_sec": duration_sec,
                "error_msg": error_msg,
            },
        }
        return self._request("POST", "/lacp/webhook", body=body)

    def heartbeat(self, agent_id="addwii-ext"):
        """POST /lacp/webhook：送出心跳維持 services.status=online。

        body 格式依對接文件 v1.0 推定，正式前可與 AIMOS 端確認。
        agent_id 同樣須用已登記的 addwii-ext，避免被拒。
        """
        body = {
            "event_type": "agent.heartbeat",
            "source": "addwii",
            "data": {"agent_id": agent_id},
        }
        return self._request("POST", "/lacp/webhook", body=body)

    @staticmethod
    def _extract_cursor(events, fallback_since):
        """從本批事件取最大時間戳當新游標；無時間欄位則沿用 fallback。"""
        # AIMOS event 不保證帶 timestamp/created_at；缺欄位時只能沿用舊 since，
        # 代價是下一輪可能重拉同批事件（改由 consume_once 的 seen_ids 去重補上）。
        stamps = [
            e.get("timestamp") or e.get("created_at")
            for e in events
            if e.get("timestamp") or e.get("created_at")
        ]
        if not stamps:
            return fallback_since
        try:
            return max(stamps)
        except TypeError:
            # 時間戳混型別（如 int 與 str 並存）時 max() 會拋 TypeError；
            # 這不是連線錯誤、不該穿透崩潰，退回 fallback 沿用舊游標即可。
            return fallback_since

    def consume_once(self, handler, source="addwii", since=None, dry_run=True, seen_ids=None):
        """拉一輪事件，只處理 task.created，交給 handler 產生輸出。

        dry_run 預設 True 是安全預設：測試時只拉+跑 handler，不回報 AIMOS，
        避免污染對端佇列；確認無誤後才用 dry_run=False 真正 report_result。

        seen_ids 若傳入 set，則以 task_id 去重：游標無法推進（事件無時間戳）時，
        同一批 task.created 不會每輪重複回報而洗版正式佇列。
        """
        polled = self.poll_events(source, since=since)
        events = polled.get("events", [])
        results = []
        processed = 0
        for event in events:
            # 只處理 task.created：佇列可能混入 agent.result 等非任務事件，
            # 消費者不該把自己回報的結果又當任務處理（會無限迴圈）。
            if event.get("event_type") != "task.created":
                continue
            outcome = self._handle_task_event(event, handler, dry_run, seen_ids)
            if outcome is not None:
                processed += 1
                results.append(outcome)
        next_since = self._extract_cursor(events, since)
        return {
            "polled": len(events),
            "processed": processed,
            "results": results,
            "next_since": next_since,
        }

    def _handle_task_event(self, event, handler, dry_run, seen_ids=None):
        """處理單一 task.created 事件，回傳 {task_id, ...}；已去重則回 None。"""
        data = event.get("data", {})
        task_id = data.get("task_id")
        # 先驗 task_id：live 模式下 report_result(task_id=None) 會在內部拋 ValueError，
        # 該例外在下方 try 之外、又非 AimosError，會穿透 _consume_safe 殺掉整個 consumer。
        # 缺值就 skip + 警告，根本不進到回報路徑。
        if task_id is None or not str(task_id).strip():
            print("警告：事件缺 task_id，已略過", file=sys.stderr)
            return {"task_id": None, "ok": False, "skipped": "缺 task_id"}
        # 去重：游標停滯時避免同一 task 每輪重複處理/回報。
        if seen_ids is not None and task_id in seen_ids:
            return None
        if seen_ids is not None:
            seen_ids.add(task_id)
        try:
            output = handler(data)
        except Exception as e:  # handler 是外掛邏輯，任何例外都要攔下不可炸掉迴圈
            if not dry_run:
                # 真實模式才回報失敗，避免 dry_run 污染 AIMOS。
                self.report_result(
                    task_id=task_id, run_output="", status="fail", error_msg=str(e)
                )
            return {"task_id": task_id, "error": str(e)}
        if dry_run:
            return {"task_id": task_id, "ok": True, "dry_run": True}
        self.report_result(task_id=task_id, run_output=output, status="done")
        return {"task_id": task_id, "ok": True}

    @staticmethod
    def _is_fatal(err):
        """致命 vs 暫時：4xx（401/403/泛 4xx）視為致命，重試也只是空轉。

        status_code is None（逾時/連線層）或 5xx 屬暫時故障，可重試；
        4xx（金鑰失效、授權不足、請求非法）重試永遠失敗，必須中止消費者。
        """
        code = err.status_code
        return code is not None and 400 <= code < 500

    def run_consumer(
        self, handler, source="addwii", interval=30, dry_run=True, max_iterations=None
    ):
        """持續輪詢消費迴圈：每輪（live 才心跳）再消費、更新游標、印進度。

        dry_run=True 為完全唯讀：絕不 POST 任何東西（不送 heartbeat、不回報）。
        致命 AimosError（4xx）會中止迴圈，避免金鑰失效時無限空轉。
        max_iterations=None 為無限迴圈；給整數則跑該次數後停（供測試/有限執行）。
        """
        since = None
        iteration = 0
        # seen_ids 持久跨輪：游標無法推進時用 task_id 去重，避免重複回報洗版。
        seen_ids = set()
        mode = "dry-run（完全唯讀）" if dry_run else "live（回報 AIMOS）"
        print(f"=== AIMOS 消費者啟動（{mode}，間隔 {interval}s）===")
        try:
            while max_iterations is None or iteration < max_iterations:
                iteration += 1
                try:
                    # dry-run 完全唯讀：心跳是 POST，故只在 live 模式送。
                    if not dry_run:
                        self._heartbeat_safe(source)
                    outcome = self._consume_safe(handler, source, since, dry_run, seen_ids)
                except AimosError as e:
                    # 致命錯誤（4xx）由下游 re-raise 上來：停止而非空轉。
                    print(f"金鑰/授權錯誤，消費者中止：{e.message}", file=sys.stderr)
                    break
                if outcome is not None:
                    since = outcome["next_since"]
                    print(
                        f"[第 {iteration} 輪] polled={outcome['polled']} "
                        f"processed={outcome['processed']}"
                    )
                if max_iterations is None or iteration < max_iterations:
                    # 輪詢間隔屬正常節流而非測試 race，用固定 sleep 即可。
                    time.sleep(interval)
        except KeyboardInterrupt:
            print("消費者已停止")

    def _heartbeat_safe(self, source):
        """送心跳：暫時故障只警告，致命（4xx）re-raise 讓 consumer 中止。"""
        try:
            self.heartbeat()
        except AimosError as e:
            if self._is_fatal(e):
                raise
            print(f"警告：心跳失敗（{source}）：{e.message}", file=sys.stderr)

    def _consume_safe(self, handler, source, since, dry_run, seen_ids):
        """消費一輪：暫時 AimosError 警告回 None，致命 re-raise，其他例外兜底。"""
        try:
            return self.consume_once(
                handler, source=source, since=since, dry_run=dry_run, seen_ids=seen_ids
            )
        except AimosError as e:
            if self._is_fatal(e):
                raise  # 4xx 交給 run_consumer break，不在此吞掉
            print(f"警告：本輪消費失敗：{e.message}", file=sys.stderr)
            return None
        except Exception as e:
            # 最外圈兜底：一個畸形事件/未預期例外不該殺掉長駐 daemon。
            print(f"警告：本輪出現未預期例外，已略過：{e}", file=sys.stderr)
            return None


def stub_task_handler(task_data):
    """佔位 handler：echo 任務內容供測試。

    TODO：此處應接 addwii 七大 Agent / Qwen2.5-7B Bot 產生實際答案。
    目前僅 echo 任務內容供測試。真正的答案引擎在 addwii 平台程式碼
    （C:\\work\\addwii\\），不在本檔。
    """
    title = task_data.get("title", "(無標題)")
    content = task_data.get("content", "(無內容)")
    return f"[stub 回覆] 已收到任務「{title}」：{content}"


def _run_smoke_test(client):
    """執行唯讀冒煙測試：status → ping → list_pending_tasks。

    刻意不呼叫 create_task，避免在 AIMOS 上建立真實資料。
    """
    print("=== AIMOS 唯讀冒煙測試 ===")

    status = client.status()
    print(
        f"[狀態] system_id={status.get('system_id')} "
        f"version={status.get('version')} queue_size={status.get('queue_size')}"
    )

    pong = client.ping()
    print(f"[Ping] ok={pong.get('ok')} status={pong.get('status')}")

    pending = client.list_pending_tasks("service")
    count = pending.get("count", 0)
    print(f"[待處理任務] count={count}")
    for task in pending.get("tasks", [])[:3]:
        print(f"  - {task.get('title', '(無標題)')}")

    print("✅ AIMOS 連線測通")


def _build_arg_parser():
    """組裝 CLI 參數：預設唯讀冒煙測試，--consume 切換消費者模式。"""
    parser = argparse.ArgumentParser(
        description="AIMOS REST API 最小 client（唯讀冒煙測試 / LACP 輪詢消費者）"
    )
    parser.add_argument("--base-url", default=None, help="覆蓋 AIMOS Base URL")
    parser.add_argument("--key", default=None, help="覆蓋 X-LINGCE-KEY 金鑰")
    parser.add_argument("--source", default="addwii", help="事件來源名稱（預設 addwii）")
    parser.add_argument("--consume", action="store_true", help="啟動 LACP 輪詢消費者")
    parser.add_argument("--once", action="store_true", help="消費者只跑一輪")
    parser.add_argument("--interval", type=int, default=30, help="輪詢間隔秒數（預設 30）")
    # dry-run / live 互斥：dry-run 為安全預設（不回報），唯有顯式 --live 才回報 AIMOS。
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="完全唯讀：只拉+印+跑 stub，不送 heartbeat、不回報 AIMOS（預設）",
    )
    mode.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="真正 report_result 回報 AIMOS",
    )
    return parser


def _run_consumer_cli(client, args):
    """依 CLI 參數啟動消費者，--once 時只跑一輪。"""
    mode = "dry-run（完全唯讀，不送任何 POST）" if args.dry_run else "live（回報 AIMOS）"
    print(f"消費者模式：{mode}")
    max_iterations = 1 if args.once else None
    client.run_consumer(
        stub_task_handler,
        source=args.source,
        interval=args.interval,
        dry_run=args.dry_run,
        max_iterations=max_iterations,
    )


def main():
    args = _build_arg_parser().parse_args()
    try:
        # client 建構併入 try：缺金鑰時 __init__ 拋 AimosError，
        # 走下方繁中錯誤 + exit(1)，而非裸 traceback。
        client = AimosClient(base_url=args.base_url, lingce_key=args.key)
        if args.consume:
            _run_consumer_cli(client, args)
        else:
            _run_smoke_test(client)
    except AimosError as e:
        print(f"錯誤：{e.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # 執行前需先設定金鑰，例如：export AIMOS_LINGCE_KEY=你的金鑰（或環境變數設定）。
    main()
