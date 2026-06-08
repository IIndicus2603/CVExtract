# Logging config, chỉ ghi file (không console), rotate 10MB, giữ 7 backup

import logging
import logging.config
import os
from datetime import datetime, timezone

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# UTC date đồng bộ với DB (UTC_TIMESTAMP) và chat schemas
LOG_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


class _DropWebSocketNoise(logging.Filter):
    """Bỏ log liên quan WS (project không dùng nhưng uvicorn vẫn ghi noise)"""
    PATTERNS = (
        "/ws", "WebSocket", "Unsupported upgrade request",
        "WebSocket library", "connection rejected", "connection closed",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        """Trả False để drop record nếu message chứa pattern WS"""
        msg = record.getMessage()
        return not any(p in msg for p in self.PATTERNS)


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "drop_ws": {"()": _DropWebSocketNoise},
    },
    "formatters": {
        "file": {
            "format": "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "file_info": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "file",
            "level": "INFO",
            "filename": f"{LOG_DIR}/app_{LOG_DATE}.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 7,
            "encoding": "utf-8",
        },
        "file_error": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "file",
            "level": "ERROR",
            "filename": f"{LOG_DIR}/error_{LOG_DATE}.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 7,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        # Suppress thư viện bên ngoài quá verbose
        "httpx":      {"level": "WARNING"},
        "pdfplumber": {"level": "WARNING"},
        "asyncio":    {"level": "CRITICAL"},
        "uvicorn.access": {"filters": ["drop_ws"]},
        "uvicorn.error":  {"filters": ["drop_ws"]},
    },
    "root": {
        "level": "INFO",
        "handlers": ["file_info", "file_error"],
    },
}


def setup_logging():
    """Gọi 1 lần khi app khởi động để apply LOGGING_CONFIG"""
    logging.config.dictConfig(LOGGING_CONFIG)
