"""Claude CLI 呼叫模組 — 透過 subprocess 呼叫 claude -p CLI，每個 role 有獨立 Semaphore 限流。"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# 載入 .env（與專案根目錄同層）
_base_dir = Path(__file__).resolve().parent.parent
_env_file = _base_dir / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

# claude CLI 路徑，從環境變數讀取，預設 /usr/bin/claude
CLAUDE_PATH = os.environ.get("CLAUDE_PATH", "/usr/bin/claude")

# Fail-fast：模組 import 時確認 claude CLI 存在
if not Path(CLAUDE_PATH).is_file():
    print(f"錯誤：找不到 claude CLI：{CLAUDE_PATH}", file=sys.stderr)
    raise FileNotFoundError(f"claude CLI not found: {CLAUDE_PATH}")

# 每個 role 獨立的 asyncio.Semaphore（限制 1 個並發 subprocess）
# 使用工廠函式延遲建立，確保在 event loop 啟動後才建立
_semaphores: dict[str, asyncio.Semaphore] = {}


def _get_semaphore(role: str) -> asyncio.Semaphore:
    """取得或建立指定 role 的 Semaphore（每個 role 限 1 個並發）。"""
    if role not in _semaphores:
        _semaphores[role] = asyncio.Semaphore(1)
    return _semaphores[role]


def _invoke_sync(cmd: list[str], timeout: int = 300) -> str:
    """同步呼叫 claude CLI，供 run_in_executor 使用。

    Args:
        cmd: 完整指令列表（含 claude 路徑和所有參數）
        timeout: 等待 subprocess 的最大秒數

    Returns:
        claude 輸出的文字（strip 後）

    Raises:
        subprocess.TimeoutExpired: 超過 timeout
        FileNotFoundError: claude CLI 不存在
        RuntimeError: claude CLI 回傳非零 exit code
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise
    except FileNotFoundError:
        raise

    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI 回傳非零 exit code {result.returncode}。"
            f"stderr: {result.stderr.strip()!r}"
        )

    return result.stdout.strip()


async def invoke_claude(
    role: str,
    text: str,
    system_prompt: str = "",
    timeout: int = 300,
) -> str:
    """非同步呼叫 claude -p CLI，回傳 AI 回應文字。

    每個 role 透過獨立 Semaphore 限制同時只有 1 個 subprocess，避免資源競爭。

    Args:
        role: 'A'/'B'/'C'，用於選擇對應的 Semaphore
        text: 傳入 claude -p 的使用者訊息
        system_prompt: 若非空，加上 --append-system-prompt 參數
        timeout: 等待 subprocess 的最大秒數，預設 300

    Returns:
        claude 的回應文字（strip 後）

    Raises:
        FileNotFoundError: claude CLI 不在 CLAUDE_PATH
        RuntimeError: claude CLI 回傳非零 exit code
        subprocess.TimeoutExpired: 超過 timeout
    """
    cmd = [CLAUDE_PATH, "-p", text]
    if system_prompt:
        cmd += ["--append-system-prompt", system_prompt]

    sem = _get_semaphore(role)
    async with sem:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _invoke_sync, cmd, timeout)

    return response


if __name__ == "__main__":
    # 簡單冒煙測試
    import asyncio as _asyncio

    async def _smoke():
        print("TC1 happy path：invoke_claude('B', '說一個字：你好')")
        try:
            result = await invoke_claude("B", "說一個字：你好")
            print(f"  回傳：{result!r}")
            assert result, "回應不應為空"
            print("  PASS")
        except Exception as e:
            print(f"  FAIL: {e}")

        print("TC2 edge case：invoke_claude('B', '', system_prompt='你是助理')")
        try:
            result = await invoke_claude("B", "", system_prompt="你是助理")
            print(f"  回傳：{result!r}")
            print("  PASS（空 text 不 crash）")
        except Exception as e:
            print(f"  FAIL: {e}")

    _asyncio.run(_smoke())
