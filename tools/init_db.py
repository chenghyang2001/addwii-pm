"""資料庫初始化腳本 — 建立 SQLite DB、執行 schema、seed agents 三筆初始資料。"""
import os
import sqlite3
import sys
from pathlib import Path

# 將專案根目錄加入 sys.path，確保無論從何處執行腳本都可以 import core 模組
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import cfg  # noqa: E402（sys.path 調整必須先於 core import）
from core.db import get_conn  # noqa: E402

# schema.sql 相對於專案根目錄的固定位置
_SCHEMA_PATH = _PROJECT_ROOT / "db" / "schema.sql"

# 三位代理人的初始資料
# 欄位順序：role, display_name, discord_user_id, bot_discord_id, reports_to, persona_file
# INSERT OR IGNORE 確保重複執行初始化腳本時不報 UNIQUE 衝突錯誤
SEED_AGENTS = [
    ("A", "總監",         0, None, None, "personas/role_a.md"),
    ("B", "PM 經理",      -1, None, "A",  "personas/role_b.md"),
    ("C", "校園推廣組員",  -2, None, "B",  "personas/role_c.md"),
]


def main() -> None:
    """執行資料庫初始化並列印確認訊息。"""
    try:
        # 取得 DB 路徑（與 core/db.py 邏輯保持一致，避免建出兩個不同路徑的 DB 檔案）
        db_path = os.environ.get("ADDWII_DB_PATH") or str(cfg.base_dir / "data" / "addwii.db")

        # 確保 data/ 目錄存在（初次執行時建立）
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 確認 schema.sql 存在才繼續
        if not _SCHEMA_PATH.exists():
            print(f"錯誤：找不到 schema 檔案 {_SCHEMA_PATH}", file=sys.stderr)
            sys.exit(1)

        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")

        # 用原生 sqlite3 連線執行 executescript（可執行多條 SQL，包含 PRAGMA）
        # executescript 會自動 commit 前一個 transaction 再執行
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(schema_sql)

            # Seed agents — INSERT OR IGNORE 保冪等（role 是 PRIMARY KEY，重複 INSERT 靜默跳過）
            conn.executemany(
                """
                INSERT OR IGNORE INTO agents
                    (role, display_name, discord_user_id, bot_discord_id, reports_to, persona_file)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                SEED_AGENTS,
            )
            conn.commit()
        finally:
            conn.close()

        print(f"✅ 資料庫初始化完成：{db_path}")

        # 列印 agents 表目前內容確認 seed 是否成功
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT role, display_name, reports_to FROM agents"
            ).fetchall()

        print("\nagents 表目前內容：")
        print(f"{'role':<6}  {'display_name':<16}  reports_to")
        print("-" * 44)
        for row in rows:
            reports = row["reports_to"] if row["reports_to"] is not None else "—"
            print(f"{row['role']:<6}  {row['display_name']:<16}  {reports}")

    except Exception as e:
        print(f"錯誤：資料庫初始化失敗 — {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
