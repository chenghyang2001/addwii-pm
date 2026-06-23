"""設定管理模組 — 單例，讀取 config.json 並根據 ENV 載入 .env"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


class Config:
    """集中管理 addwii-pm 所有設定參數，全域唯一實例。

    存取方式：from core.config import cfg
    """

    def __init__(self) -> None:
        # 使用 __file__ 反推專案根目錄，確保跨機器可攜（不硬編碼路徑）
        self.base_dir: Path = Path(__file__).resolve().parent.parent
        self._env: str = os.environ.get("ENV", "dev")

        # 優先載入 .env.{ENV}，找不到才退而求其次載入 .env
        env_specific = self.base_dir / f".env.{self._env}"
        if env_specific.exists():
            load_dotenv(env_specific, override=True)
        else:
            fallback = self.base_dir / ".env"
            if fallback.exists():
                load_dotenv(fallback, override=True)

        # 讀取主設定檔，找不到立即停止行程（config.json 是必要依賴）
        config_path = self.base_dir / "config.json"
        if not config_path.exists():
            print(f"錯誤：找不到設定檔 {config_path}", file=sys.stderr)
            sys.exit(1)

        with open(config_path, encoding="utf-8") as f:
            self._data: dict = json.load(f)

    # ── Discord 設定 ────────────────────────────────────────────────────

    @property
    def members(self) -> dict:
        """回傳全部 members 設定 dict（key = role 字串 'A'/'B'/'C'）"""
        return self._data["members"]

    @property
    def guild_id(self) -> int:
        """Discord 伺服器 ID"""
        return self._data["discord"]["guild_id"]

    @property
    def channel_id(self) -> int:
        """三個 bot 共用的頻道 ID"""
        return self._data["discord"]["channel_id"]

    @property
    def max_hops(self) -> int:
        """防對話無限迴圈的跳轉上限，預設 3"""
        return self._data["discord"].get("max_hops", 3)

    # ── 日誌設定 ────────────────────────────────────────────────────────

    @property
    def log_dir(self) -> str:
        """logs 根目錄的絕對路徑（供 logger.py 組合子目錄用）"""
        return str(self.base_dir / self._data["logging"]["dir"])

    @property
    def log_retention(self) -> int:
        """日誌保留天數，對應 TimedRotatingFileHandler.backupCount"""
        return self._data["logging"]["retention_days"]

    # ── 成員工具方法 ─────────────────────────────────────────────────────

    def resolve_role(self, discord_user_id: int) -> str | None:
        """給 Discord 真人 user ID，回傳對應的 role ('A'/'B'/'C')。

        Args:
            discord_user_id: Discord 使用者數字 ID

        Returns:
            匹配的 role 字串；discord_user_id=0（未設定 placeholder）或找不到時回傳 None
        """
        # 0 是 config.json 尚未填入的佔位值，視為未設定
        if discord_user_id == 0:
            return None

        for role, member in self.members.items():
            if member.get("discord_user_id") == discord_user_id:
                return role

        return None

    def get_bot_token(self, role: str) -> str:
        """讀取指定 role 的 Discord Bot Token 環境變數。

        Args:
            role: 成員 role 鍵值，例如 'A'、'B'、'C'

        Returns:
            Bot Token 字串

        Raises:
            RuntimeError: 對應的環境變數不存在或為空時，含具體環境變數名稱說明
        """
        env_var = self.members[role]["bot_token_env"]
        token = os.environ.get(env_var)
        if not token:
            raise RuntimeError(
                f"找不到 Bot Token：role={role!r} 需要環境變數 {env_var!r}，"
                "請在 .env 或系統環境變數中設定後再啟動。"
            )
        return token

    def get_display_name(self, role: str) -> str:
        """回傳指定 role 的顯示名稱（例如 '總監'、'PM 經理'）"""
        return self.members[role]["display_name"]

    def get_reports_to(self, role: str) -> str | None:
        """回傳直屬上司的 role 字串；頂層角色（A）回傳 None"""
        return self.members[role]["reports_to"]

    def get_subordinates(self, role: str) -> list[str]:
        """回傳直屬下屬的 role 列表（即 reports_to == role 的所有成員）"""
        return [
            r
            for r, member in self.members.items()
            if member.get("reports_to") == role
        ]


# 全域單例 — 其他模組統一以 from core.config import cfg 取用
cfg = Config()
