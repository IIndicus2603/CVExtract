# Logging config, file rotate 10MB giữ 7 backup, console rich + access log uvicorn

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


class _BelowError(logging.Filter):
    """Chỉ cho qua record dưới mức ERROR, để handler native không in trùng traceback rich"""

    def filter(self, record: logging.LogRecord) -> bool:
        """Trả False với record từ ERROR trở lên"""
        return record.levelno < logging.ERROR


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "drop_ws": {"()": _DropWebSocketNoise},
        "below_error": {"()": _BelowError},
    },
    "formatters": {
        "file": {
            "format": "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        # Log vòng đời uvicorn theo style native "INFO:     ..."
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": None,
        },
        # Rich tự vẽ cột thời gian + level, formatter chỉ cần message
        "rich": {
            "format": "%(message)s",
            "datefmt": "[%X]",
        },
        # Access log của uvicorn, thay client_addr bằng thời gian, tự tô màu status
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s [%(asctime)s] - "%(request_line)s" %(status_code)s',
            "datefmt": "%H:%M:%S",
            "use_colors": None,
        },
    },
    "handlers": {
        # Access log của uvicorn ra stdout theo style native
        "access_console": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "level": "INFO",
            "stream": "ext://sys.stdout",
        },
        # Log vòng đời uvicorn (INFO/WARNING) theo style native, chặn ERROR để rich lo
        "console_sys": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "level": "INFO",
            "stream": "ext://sys.stdout",
            "filters": ["below_error"],
        },
        # Chỉ ERROR trở lên đi qua rich để traceback tô màu
        "console_err": {
            "class": "rich.logging.RichHandler",
            "formatter": "rich",
            "level": "ERROR",
            "markup": False,
            "show_path": False,
            "rich_tracebacks": True,
        },
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
        # Vòng đời uvicorn ra native, traceback ra rich, đều lưu file
        "uvicorn":       {"handlers": ["console_sys", "console_err", "file_info", "file_error"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"filters": ["drop_ws"], "propagate": True},
        # Access log built-in của uvicorn, mỗi request 1 dòng kèm status
        "uvicorn.access": {"handlers": ["access_console"], "level": "INFO", "filters": ["drop_ws"], "propagate": False},
    },
    "root": {
        "level": "INFO",
        "handlers": ["file_info", "file_error"],
    },
}


def setup_logging():
    """Gọi 1 lần khi app khởi động để apply LOGGING_CONFIG"""
    logging.config.dictConfig(LOGGING_CONFIG)
