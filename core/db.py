"""SQLite 連線管理模組 — 提供 WAL 模式 context manager，供 bot 行程和 dashboard 共用。"""
import contextlib
import os
import sqlite3
from pathlib import Path

from core.config import cfg

# SQLite 等鎖的最大秒數（多行程並發 WAL 時避免無限等待）
DB_TIMEOUT = 30


@contextlib.contextmanager
def get_conn(read_only: bool = False):
    """取得 SQLite 連線，自動 commit/rollback/close。

    WAL 模式：多個 reader 可並發讀取，write 序列化。
    read_only=True：dashboard 行程用，以 'file:<path>?mode=ro' URI 開啟。
    不應在 read_only=True 的連線上執行 INSERT/UPDATE/DELETE（使用者責任）。

    Args:
        read_only: True 時以唯讀 URI 開啟，不設定 PRAGMA
                   （唯讀連線不能設 journal_mode，會報錯）

    Yields:
        sqlite3.Connection：row_factory 已設為 sqlite3.Row，可用欄位名存取結果

    Raises:
        Exception: 任何 SQL 錯誤皆自動 rollback 後重新拋出
    """
    # 優先讀環境變數，沒有則用 cfg 計算的 data/ 子目錄
    db_path = os.environ.get("ADDWII_DB_PATH") or str(cfg.base_dir / "data" / "addwii.db")

    # 確保 DB 所在目錄存在（init_db.py 第一次執行時需要建立 data/ 目錄）
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    if read_only:
        # URI 格式加 mode=ro，讓 SQLite 在 OS 層拒絕寫入（需 DB 檔案已存在）
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=DB_TIMEOUT)
    else:
        conn = sqlite3.connect(str(db_path), timeout=DB_TIMEOUT)

    # 用欄位名存取查詢結果，不依賴欄位索引（欄位順序不影響取值）
    conn.row_factory = sqlite3.Row

    if not read_only:
        # 每次連線確認 WAL 與外鍵約束開啟，不依賴 DB 建立時的初始化狀態
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # 確保連線一定被關閉，避免 WAL 鎖殘留
        conn.close()


def execute_one(sql: str, params: tuple = (), read_only: bool = False):
    """執行 SQL 並回傳第一筆結果，查無資料回傳 None。

    Args:
        sql:       SQL 查詢字串（一律用 ? 佔位符，禁止 f-string 拼接防 SQL 注入）
        params:    對應 ? 的參數 tuple
        read_only: True 時以唯讀連線執行

    Returns:
        sqlite3.Row 或 None
    """
    with get_conn(read_only=read_only) as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchone()


def execute_all(sql: str, params: tuple = (), read_only: bool = False) -> list:
    """執行 SQL 並回傳所有結果列表。

    Args:
        sql:       SQL 查詢字串（一律用 ? 佔位符，禁止 f-string 拼接防 SQL 注入）
        params:    對應 ? 的參數 tuple
        read_only: True 時以唯讀連線執行

    Returns:
        list[sqlite3.Row]，查無資料回傳空列表
    """
    with get_conn(read_only=read_only) as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchall()


def execute_write(sql: str, params: tuple = ()) -> int:
    """執行寫入 SQL（INSERT/UPDATE/DELETE）並回傳 lastrowid。

    Args:
        sql:    SQL 字串（一律用 ? 佔位符，禁止 f-string 拼接防 SQL 注入）
        params: 對應 ? 的參數 tuple

    Returns:
        cursor.lastrowid（INSERT 時為新增資料列的 ROWID）
    """
    with get_conn(read_only=False) as conn:
        cursor = conn.execute(sql, params)
        return cursor.lastrowid
