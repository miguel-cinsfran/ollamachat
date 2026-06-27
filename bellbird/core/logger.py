"""Per-session file logger for Bellbird.

Each process gets its OWN log file under ``<user-data>/logs/`` named
``session_YYYYMMDD_HHMMSS.log`` (created the first time ``get_logger()``
runs). Old session files are pruned to the most recent ``_KEEP_SESSIONS``
so the folder never grows without bound. This makes it easy to review a
single run end-to-end instead of scrolling one ever-growing file.

Never raises: logging failures are swallowed so a broken log file never
crashes the app.

Usage:

    from bellbird.core.logger import get_logger

    log = get_logger()
    log.info("Application started")
    log.error("Failed to connect: %s", exc)
"""

import logging
import time
from pathlib import Path

from bellbird.core.paths import user_data_dir


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_SUBDIR = "logs"
_LOGGER_NAME = "bellbird"
# How many past session logs to keep before pruning the oldest.
_KEEP_SESSIONS = 20

_log_path: Path | None = None


def get_log_path() -> Path | None:
    """Return the path to the current session's log file, or None if not yet
    initialised."""
    return _log_path


def _prune_old_sessions(log_dir: Path, keep: int) -> None:
    """Delete the oldest ``session_*.log`` files, keeping the newest ``keep``.

    Best-effort: any failure (permission, race) is swallowed — pruning must
    never break logging.
    """
    try:
        files = sorted(log_dir.glob("session_*.log"))
        for old in files[:-keep] if keep > 0 else files:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception:
        pass


def get_logger(name: str = _LOGGER_NAME) -> logging.Logger:
    """Return a configured logger that writes to a per-session file.

    Idempotent: repeated calls with the same name return the same configured
    logger (one FileHandler per process). If the log file cannot be opened, a
    ``NullHandler`` is attached so logging calls still do not raise.

    Uses a sentinel attribute (``_bellbird_configured``) on the logger object
    itself to detect prior configuration, rather than relying on
    ``logger.handlers`` — the latter would falsely return early when other
    libraries (e.g. pytest's ``caplog``) have attached their own handlers.

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
        log_dir = user_data_dir() / _LOG_SUBDIR
        log_dir.mkdir(parents=True, exist_ok=True)

        stamp = time.strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"session_{stamp}.log"
        # Guard against same-second collisions (quick restarts): append a
        # millisecond suffix so a second process never reuses the first's file.
        if log_path.exists():
            millis = int(time.time() * 1000) % 1000
            log_path = log_dir / f"session_{stamp}_{millis:03d}.log"
        _log_path = log_path

        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)

        _prune_old_sessions(log_dir, _KEEP_SESSIONS)
        logger.info("=== Bellbird session log: %s ===", log_path.name)
    except Exception:
        # Logging must never crash the app.
        logger.addHandler(logging.NullHandler())

    return logger
