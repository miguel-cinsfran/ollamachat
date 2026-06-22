"""Tests for the logger module — file logging with never-crash contract."""

import logging

import pytest

from ollamachat.core.logger import get_logger


@pytest.fixture
def clean_logger():
    """Remove any cached handlers and sentinel on the 'ollamachat' logger."""
    logger = logging.getLogger("ollamachat")
    _reset_logger(logger)
    yield logger
    _reset_logger(logger)


def _reset_logger(logger):
    """Close and remove all of our FileHandlers, clear the sentinel."""
    for h in list(logger.handlers):
        if isinstance(h, logging.FileHandler):
            try:
                h.close()
            except Exception:
                pass
            logger.removeHandler(h)
    if hasattr(logger, "_ollamachat_configured"):
        delattr(logger, "_ollamachat_configured")


def test_get_logger_returns_logger_instance(clean_logger, monkeypatch, tmp_path):
    """get_logger returns a configured logging.Logger."""
    monkeypatch.chdir(tmp_path)
    log = get_logger()
    assert isinstance(log, logging.Logger)
    assert log.name == "ollamachat"


def test_get_logger_writes_to_data_dir(clean_logger, monkeypatch, tmp_path):
    """The log file is created under data/ in the current working directory."""
    monkeypatch.chdir(tmp_path)
    log = get_logger()
    log.info("hello from ollamachat")
    # Flush buffered writes so we can read the file before the
    # handler is closed.
    for h in log.handlers:
        h.flush()

    log_file = tmp_path / "data" / "ollamachat.log"
    assert log_file.exists(), f"Expected log file at {log_file}"
    content = log_file.read_text(encoding="utf-8")
    assert "hello from ollamachat" in content
    assert "INFO" in content


def test_get_logger_is_idempotent(clean_logger, monkeypatch, tmp_path):
    """Calling get_logger twice returns the same logger with the same handlers."""
    monkeypatch.chdir(tmp_path)
    log1 = get_logger()
    log2 = get_logger()

    assert log1 is log2
    # Only one of OUR FileHandlers, not two (other libraries may have
    # attached their own handlers, e.g. pytest's caplog).
    file_handlers_1 = [h for h in log1.handlers if isinstance(h, logging.FileHandler)]
    file_handlers_2 = [h for h in log2.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers_1) == 1
    assert len(file_handlers_2) == 1


def test_get_logger_levels(clean_logger, monkeypatch, tmp_path):
    """All standard levels (debug, info, warning, error) are written."""
    monkeypatch.chdir(tmp_path)
    log = get_logger()
    log.debug("d-message")
    log.info("i-message")
    log.warning("w-message")
    log.error("e-message")
    for h in log.handlers:
        h.flush()

    content = (tmp_path / "data" / "ollamachat.log").read_text(encoding="utf-8")
    assert "d-message" in content
    assert "i-message" in content
    assert "w-message" in content
    assert "e-message" in content
    assert "DEBUG" in content
    assert "INFO" in content
    assert "WARNING" in content
    assert "ERROR" in content


def test_get_logger_uses_utf8(clean_logger, monkeypatch, tmp_path):
    """Non-ASCII characters are written without raising (UTF-8 encoding)."""
    monkeypatch.chdir(tmp_path)
    log = get_logger()
    log.info("mensaje con eñes y acentos: á é í ó ú ñ")
    for h in log.handlers:
        h.flush()

    content = (tmp_path / "data" / "ollamachat.log").read_text(encoding="utf-8")
    assert "eñes" in content
    assert "ñ" in content


def test_get_logger_swallows_file_open_failure(clean_logger, monkeypatch, tmp_path):
    """If the log file cannot be opened, a NullHandler is attached and no raise."""
    monkeypatch.chdir(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "ollamachat.core.logger.logging.FileHandler",
            lambda *a, **kw: (_ for _ in ()).throw(PermissionError("denied")),
        )
        # Must not raise
        log = get_logger()

    # Should have a NullHandler as fallback (other libraries may have
    # attached their own handlers, e.g. pytest's caplog).
    null_handlers = [h for h in log.handlers if isinstance(h, logging.NullHandler)]
    assert len(null_handlers) == 1

    # And calling .info() must not raise
    log.info("after the fallback")
