"""AIMOS REST API 最小 client（LACP 協議唯讀對接 + 建立任務骨架）。

用途：取代原本用 Puppeteer 驅動 Streamlit UI 的問答方式，改以程式化方式
對接 AIMOS（鼎創達/addwii 的 AI 任務管理平台）。

本模組只用 Python 標準庫，無任何第三方依賴。提供：
- AimosClient：封裝 LACP 認證與請求的最小 client
- 唯讀冒煙測試 CLI（status / ping / list_pending_tasks）

執行前需先設定金鑰環境變數，例如：export AIMOS_LINGCE_KEY=你的金鑰
（或於建構 AimosClient 時以 lingce_key 參數傳入）。本 repo 為 public，
金鑰一律不寫入程式碼。Base URL 可用 AIMOS_BASE_URL 覆蓋，未設定走預設常數。
"""

import argparse
import json
import os
import sys
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


def main():
    parser = argparse.ArgumentParser(description="AIMOS REST API 最小 client（唯讀冒煙測試）")
    parser.add_argument("--base-url", default=None, help="覆蓋 AIMOS Base URL")
    parser.add_argument("--key", default=None, help="覆蓋 X-LINGCE-KEY 金鑰")
    args = parser.parse_args()

    client = AimosClient(base_url=args.base_url, lingce_key=args.key)
    try:
        _run_smoke_test(client)
    except AimosError as e:
        print(f"錯誤：{e.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
