"""Simple file logger for Bellbird.

Writes log entries to ``data/bellbird.log``. Never raises: logging
failures are swallowed so a broken log file never crashes the app.

The data/ folder is created next to the current working directory at
first use, so installed applications log alongside their working
directory and the project tree logs under its own data/ during dev.

Usage:

    from bellbird.core.logger import get_logger

    log = get_logger()
    log.info("Application started")
    log.error("Failed to connect: %s", exc)
"""

import logging
from pathlib import Path


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DIRNAME = "data"
_LOG_FILENAME = "bellbird.log"
_LOGGER_NAME = "bellbird"


def get_logger(name: str = _LOGGER_NAME) -> logging.Logger:
    """Return a configured logger that writes to ``data/bellbird.log``.

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
    logger = logging.getLogger(name)
    if getattr(logger, "_bellbird_configured", False):
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger._bellbird_configured = True  # type: ignore[attr-defined]

    try:
        log_dir = Path.cwd() / _LOG_DIRNAME
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / _LOG_FILENAME

        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)
    except Exception:
        # Logging must never crash the app.
        logger.addHandler(logging.NullHandler())

    return logger
