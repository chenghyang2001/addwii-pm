"""LACP 引擎 REST API sidecar（部署在 addwii 平台機器 .140）。

把 addwii 平台的六大模組（knowledge / operation / feedback / sensor /
security / planning）包成 REST 端點，供跨機的 LACP handler 呼叫。
addwii Bot 在 .140:8505 是純 Streamlit、沒有問答 API，平台的六大函式也
不在本開發機，因此本 sidecar 必須部署到平台機才有引擎可綁。

需設環境變數 ADDWII_ENGINE_MODULE 指向實際含六大函式的 Python 模組；
函式名依 integration doc v1.0 Table 9（見 ENGINE_FUNC_NAMES），若平台
實際名稱不同請改 ENGINE_FUNC_NAMES。引擎綁定集中在 _load_engine_callable，
是唯一需要對平台實作做 adapter 的點。

安全：這是會觸發 AI 與六大業務模組的端點，必須設環境變數 ADDWII_ENGINE_KEY
作為共用密鑰，未設則拒絕啟動（fail-closed）；POST /answer 須帶 header
X-LINGCE-KEY 且值相符才放行。預設只聽 127.0.0.1（loopback）；要對外服務
請顯式 --host 0.0.0.0，且務必確保密鑰已設、網段可信。

端點：
- POST /answer  body {"question": "...", "module"?: "..."} → {"ok", "module", "answer"}
                （須帶 header X-LINGCE-KEY）
- GET  /health  → {"ok", "wired"}（不洩漏內部模組名，免認證供監控）
"""

import argparse
import importlib
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 關鍵字 → 模組路由表（integration doc v1.0 Table 9）。
# 用「關鍵字命中」而非 ML 分類：規則透明、可離線、平台端易稽核與調整。
# 關鍵字一律以小寫存放，route_module 會把輸入轉小寫再比對（涵蓋 FAQ/PII 等英文）。
MODULE_KEYWORDS = [
    (("知識", "問答", "產品", "問題"), "knowledge"),
    (("客服", "faq", "腳本"), "operation"),
    (("回饋", "評論", "分析"), "feedback"),
    (("感測", "空氣", "異常"), "sensor"),
    (("pii", "個資", "稽核"), "security"),
    (("規劃", "報價", "提案"), "planning"),
]

# 模組 → 平台函式名（doc v1.0 Table 9）。平台實際簽名未能於開發機驗證，
# 名稱不符時改這裡即可，無需動其他邏輯。
ENGINE_FUNC_NAMES = {
    "knowledge": "knowledge_query",
    "operation": "cs_agent_run",
    "feedback": "feedback_analyze",
    "sensor": "sensor_report",
    "security": "pii_scan",
    "planning": "planning_generate",
}

# 無任何關鍵字命中時的 fallback：知識問答涵蓋面最廣，當預設最不易誤導。
DEFAULT_MODULE = "knowledge"

# 請求體大小上限 1MB：問題文字不該大到哪去，擋下惡意大 body 的記憶體 DoS。
MAX_BODY_BYTES = 1 * 1024 * 1024

# 引擎函式 cache：import_module + getattr 有成本，命中後快取避免每次請求重載。
_engine_cache = {}


class EngineNotWired(Exception):
    """引擎尚未綁定：未設 ADDWII_ENGINE_MODULE 或找不到對應模組/函式。"""


def route_module(text):
    """依關鍵字把問題文字路由到六大模組之一，無命中回 DEFAULT_MODULE。"""
    lowered = (text or "").lower()
    for keywords, module in MODULE_KEYWORDS:
        for keyword in keywords:
            if keyword in lowered:
                return module
    return DEFAULT_MODULE


def _load_engine_callable(module):
    """取得指定模組的平台函式（唯一引擎綁定點 / adapter 點）。

    這裡刻意把「呼叫哪個平台函式」做成可設定 + 文件化，而非寫死呼叫某個
    未驗證的 API：六大函式的實際簽名無法在開發機確認，硬寫會在平台端炸掉。
    """
    if module in _engine_cache:
        return _engine_cache[module]
    module_path = os.environ.get("ADDWII_ENGINE_MODULE")
    if not module_path:
        raise EngineNotWired(
            "未設定 ADDWII_ENGINE_MODULE：請指向平台上含六大函式的 Python 模組"
        )
    func_name = ENGINE_FUNC_NAMES.get(module)
    if func_name is None:
        raise EngineNotWired(f"未知模組 {module}：不在 ENGINE_FUNC_NAMES 對照表內")
    try:
        engine_module = importlib.import_module(module_path)
        fn = getattr(engine_module, func_name)
    except ImportError as e:
        raise EngineNotWired(
            f"無法匯入引擎模組 {module_path}（module={module}）：{e}"
        ) from e
    except AttributeError as e:
        raise EngineNotWired(
            f"引擎模組 {module_path} 找不到函式 {func_name}（module={module}）：{e}"
        ) from e
    _engine_cache[module] = fn
    return fn


def answer(question, module=None):
    """路由 + 呼叫引擎函式，回標準化結果 dict。"""
    if module is None:
        module = route_module(question)
    try:
        fn = _load_engine_callable(module)
        result = fn(question)
        return {"ok": True, "module": module, "answer": str(result)}
    except EngineNotWired as e:
        # 引擎未綁定屬「可預期的部署未完成」，回 ok=False 讓上層轉 503，
        # 而非 500：這不是程式錯誤，是平台尚未接線。
        return {"ok": False, "module": module, "error": str(e)}


class EngineRequestHandler(BaseHTTPRequestHandler):
    """六大模組 REST handler：POST /answer、GET /health。"""

    def _send_json(self, status, payload):
        """統一 JSON 回應；ensure_ascii=False 保留繁中可讀。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        """比對 header X-LINGCE-KEY 是否等於 ADDWII_ENGINE_KEY。"""
        # 啟動時已保證 ADDWII_ENGINE_KEY 有值（run 內 fail-closed），此處只比對。
        return self.headers.get("X-LINGCE-KEY") == os.environ.get("ADDWII_ENGINE_KEY")

    def do_POST(self):
        # 整段包 try：任何未預期例外都轉 500 通用訊息，不回 stack 給對端。
        try:
            if self.path != "/answer":
                self._send_json(404, {"ok": False, "error": "端點不存在"})
                return
            # 認證優先於任何處理：缺/錯密鑰一律 401，不洩漏期望值。
            if not self._authorized():
                self._send_json(401, {"ok": False, "error": "認證失敗：X-LINGCE-KEY 不符"})
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            # 先看宣告長度就擋，不把超大 body 讀進記憶體。
            if length > MAX_BODY_BYTES:
                self._send_json(413, {"ok": False, "error": "請求體過大"})
                return
            raw = self.rfile.read(length) if length else b""
            data = json.loads(raw.decode("utf-8")) if raw else {}
            question = data.get("question")
            if question is None or not str(question).strip():
                self._send_json(400, {"ok": False, "error": "缺少 question 欄位"})
                return
            result = answer(question, module=data.get("module"))
            # 引擎未綁定（ok=False）回 503 服務未就緒，可成功回答回 200。
            self._send_json(200 if result.get("ok") else 503, result)
        except Exception:
            # 伺服器端記真實例外（含 traceback）到 stderr 供除錯，對端只回通用訊息。
            print(traceback.format_exc(), file=sys.stderr)
            self._send_json(500, {"ok": False, "error": "伺服器內部錯誤"})

    def do_GET(self):
        try:
            if self.path != "/health":
                self._send_json(404, {"ok": False, "error": "端點不存在"})
                return
            # /health 免認證供監控，但只回 wired 布林，不洩漏真實模組名。
            self._send_json(
                200,
                {"ok": True, "wired": bool(os.environ.get("ADDWII_ENGINE_MODULE"))},
            )
        except Exception:
            print(traceback.format_exc(), file=sys.stderr)
            self._send_json(500, {"ok": False, "error": "伺服器內部錯誤"})

    def log_message(self, fmt, *args):
        # 靜音預設 access log：避免每次 LACP polling 都洗版 stderr。
        pass


def run(host="127.0.0.1", port=None):
    """啟動引擎 API；預設只聽 loopback，對外請顯式開並確保認證已設。

    fail-closed：未設 ADDWII_ENGINE_KEY 直接拒絕啟動——不准跑沒有認證的
    AI 端點。port 為 None 時讀 ADDWII_ENGINE_PORT，預設 8509。
    """
    if not os.environ.get("ADDWII_ENGINE_KEY"):
        print(
            "錯誤：未設定 ADDWII_ENGINE_KEY，拒絕啟動無認證的 AI 端點",
            file=sys.stderr,
        )
        sys.exit(1)
    if port is None:
        port = int(os.environ.get("ADDWII_ENGINE_PORT", "8509"))
    # ThreadingHTTPServer：每請求一執行緒，避免單一 60 秒慢生成阻塞 /health 與他人。
    server = ThreadingHTTPServer((host, port), EngineRequestHandler)
    print(f"引擎 API 啟動 {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("引擎 API 已停止")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(
        description="LACP 引擎 REST API sidecar（六大模組 → REST）"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="綁定位址（預設 127.0.0.1 只聽 loopback；對外用 --host 0.0.0.0）",
    )
    parser.add_argument(
        "--port", type=int, default=None, help="埠號（預設讀 ADDWII_ENGINE_PORT 或 8509）"
    )
    args = parser.parse_args()
    try:
        run(host=args.host, port=args.port)
    except OSError as e:
        # 埠被占用等綁定失敗：印繁中錯誤而非裸 traceback。
        print(f"錯誤：引擎 API 啟動失敗：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
