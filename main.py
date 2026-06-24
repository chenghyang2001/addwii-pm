"""addwii-pm Discord Bot 進入點

用法：
    python main.py --role A
    python main.py --role B
    python main.py --role C

從環境變數 BOT_TOKEN_{role} 讀取 Bot Token，啟動對應角色的 Discord bot。
"""
import argparse
import os
import sys
from pathlib import Path

# 在所有 I/O 相關操作前設定 UTF-8 模式（Windows cp950 環境下避免編碼錯誤）
os.environ.setdefault("PYTHONUTF8", "1")

from dotenv import load_dotenv  # noqa: E402

# 載入與本檔案同目錄的 .env（含各角色的 BOT_TOKEN_A/B/C）
# 注意：此處用預設的 override=False，不覆蓋系統已有的環境變數
load_dotenv(Path(__file__).resolve().parent / ".env")

# 確保設定單例在 bot 模組之前初始化，避免 Config.__init__ 重複載入 .env 的時序問題
from core.config import cfg  # noqa: E402,F401


def build_parser() -> argparse.ArgumentParser:
    """建立並回傳 argparse 解析器，方便測試與 --help 驗證。"""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="addwii-pm Discord Bot 啟動器",
    )
    parser.add_argument(
        "--role",
        required=True,
        type=str.upper,  # 輸入時自動轉大寫，無須呼叫端手動處理
        choices=["A", "B", "C"],
        metavar="ROLE",
        help="啟動角色：A、B 或 C（大小寫無關）",
    )
    return parser


def main() -> None:
    """主流程：解析角色、驗證 Token、啟動 Discord Bot。"""
    parser = build_parser()
    args = parser.parse_args()
    role: str = args.role  # type=str.upper 已保證大寫

    # 先驗證 Token，避免 bot 模組載入後才發現 Token 缺失造成不清楚的錯誤訊息
    env_key = f"BOT_TOKEN_{role}"
    token = os.environ.get(env_key)
    if not token:
        print(
            f"錯誤：缺少環境變數 {env_key!r}，"
            "請在 .env 或系統環境中設定後再啟動。",
            file=sys.stderr,
        )
        sys.exit(1)

    # Token 確認後才延遲 import bot 模組（agent/bot.py 在 Token 驗證通過後才需要）
    from agent.bot import AddwiiBot  # noqa: PLC0415

    bot = AddwiiBot(role)
    bot.run(token)


if __name__ == "__main__":
    main()
