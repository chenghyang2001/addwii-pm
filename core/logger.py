"""日誌設定模組 — 統一建立 Console + TimedRotatingFileHandler 的 Logger"""
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from core.config import cfg

# 統一格式：時間戳 + 等級 + Logger 名稱 + 訊息
_LOG_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(name: str, log_subdir: str = "system") -> logging.Logger:
    """建立同時輸出到 console 和每日滾動檔案的 Logger。

    若同名 Logger 已有 handler（例如模組被 import 多次），直接回傳現有實例，
    避免重複加 handler 導致每行日誌重複輸出。

    Args:
        name:       Logger 名稱，通常是模組名或 bot role（如 'addwii'、'bot_A'）
        log_subdir: 在 cfg.log_dir 底下再建的子目錄，預設 'system'

    Returns:
        已設定完畢的 logging.Logger 實例
    """
    logger = logging.getLogger(name)

    # 已有 handler 表示此 Logger 曾被初始化，直接回傳避免重複註冊
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # 組出日誌目錄：log_dir（絕對路徑） / log_subdir
    log_dir = Path(cfg.log_dir) / log_subdir
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler — 即時看到輸出，方便開發除錯
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # 每日午夜滾動的檔案 handler，保留天數從 cfg.log_retention 取得
    log_file = log_dir / f"{name}.log"
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        backupCount=cfg.log_retention,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# 全域系統 Logger — 其他模組可直接 from core.logger import system_logger
system_logger = setup_logger("addwii")
