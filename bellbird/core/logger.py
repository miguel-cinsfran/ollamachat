"""Simple file logger for Bellbird.

Writes log entries to ``bellbird.log`` inside the OS user-data
directory (``platformdirs.user_data_dir("Bellbird", appauthor=False)``).
Never raises: logging failures are swallowed so a broken log file
never crashes the app.

Usage:

    from bellbird.core.logger import get_logger

    log = get_logger()
    log.info("Application started")
    log.error("Failed to connect: %s", exc)
"""

import logging
from pathlib import Path

from bellbird.core.paths import user_data_dir


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_FILENAME = "bellbird.log"
_LOGGER_NAME = "bellbird"

_log_path: Path | None = None


def get_log_path() -> Path | None:
    """Return the path to the current log file, or None if not yet initialised."""
    return _log_path


def get_logger(name: str = _LOGGER_NAME) -> logging.Logger:
    """Return a configured logger that writes to the user-data directory.

    Idempotent: repeated calls with the same name return the same
    configured logger. If the log file cannot be opened, a
    ``NullHandler`` is attached so logging calls still do not raise.

    Uses a sentinel attribute (``_bellbird_configured``) on the
    logger object itself to detect prior configuration, rather than
    relying on ``logger.handlers`` — the latter would falsely return
    early when other libraries (e.g. pytest's ``caplog``) have
    attached their own handlers.

    Args:
        name: Logger name. Defaults to ``"bellbird"``.

    Returns:
        A configured ``logging.Logger`` instance.
    """
    global _log_path
    logger = logging.getLogger(name)
    if getattr(logger, "_bellbird_configured", False):
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger._bellbird_configured = True  # type: ignore[attr-defined]

    try:
        log_dir = user_data_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / _LOG_FILENAME
        _log_path = log_path

        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)
    except Exception:
        # Logging must never crash the app.
        logger.addHandler(logging.NullHandler())

    return logger
