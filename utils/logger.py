import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import settings

# ─────────────────────────────────────────────
# Format:  2026-04-03 17:34:22 [INFO    ] [routes.rag] [upload_file] [Uploading 44 chunks]
# ─────────────────────────────────────────────
LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] [%(name)s] [%(funcName)s] [%(message)s]"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Log file config
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "recall_logs.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 5


def _get_level() -> int:
    return logging.DEBUG if settings.debug else logging.INFO


def _get_formatter() -> logging.Formatter:
    return logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with console + rotating file handlers.

    Usage::

        from utils.logger import get_logger
        logger = get_logger(__name__)   # e.g. "routes.rag"
        logger.info("hello")
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        formatter = _get_formatter()

        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)

        # Rotating file handler
        LOG_DIR.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.setLevel(_get_level())
    logger.propagate = False
    return logger
