# Cấu hình logging cho toàn ứng dụng: chỉ ghi vào file, không in console
# File log được rotate khi đạt 10MB, giữ tối đa 7 file backup

import logging
import logging.config
import os
from datetime import datetime

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Tên file log gắn theo ngày để dễ tra cứu
LOG_DATE = datetime.now().strftime("%Y-%m-%d")


# Drop các log liên quan tới /ws
class _DropWebSocketNoise(logging.Filter):
    PATTERNS = (
        "/ws",                          # Bắt cả "/ws " và "/ws\""
        "WebSocket",                    # Bắt "WebSocket /ws" trong access log
        "Unsupported upgrade request",  # Warning ws=none
        "WebSocket library",            # Warning thiếu lib
        "connection rejected",          # "connection rejected (403 Forbidden)"
        "connection closed",            # "connection closed" sau khi WS bị reject
    )

    def filter(self, record: logging.LogRecord) -> bool:
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
        # Suppress log dài dòng từ thư viện bên ngoài
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


# Gọi 1 lần khi app khởi động
def setup_logging():
    logging.config.dictConfig(LOGGING_CONFIG)
