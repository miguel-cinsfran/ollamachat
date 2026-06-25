"""Tests for the logger module — file logging with never-crash contract."""

import logging

import pytest

from bellbird.core.logger import get_logger


@pytest.fixture
def clean_logger():
    """Remove any cached handlers and sentinel on the 'bellbird' logger."""
    logger = logging.getLogger("bellbird")
    _reset_logger(logger)
    yield logger
    _reset_logger(logger)


def _reset_logger(logger):
    """Close and remove all handlers added by these tests, clear the sentinel."""
    for h in list(logger.handlers):
        if isinstance(h, (logging.FileHandler, logging.NullHandler)):
            try:
                h.close()
            except Exception:
                pass
            logger.removeHandler(h)
    if hasattr(logger, "_bellbird_configured"):
        delattr(logger, "_bellbird_configured")


def _patch_user_data_dir(monkeypatch, tmp_path):
    """Helper: monkeypatch user_data_dir in the logger module to return tmp_path."""
    import bellbird.core.logger as logger_module

    monkeypatch.setattr(logger_module, "user_data_dir", lambda: tmp_path)


def test_get_logger_returns_logger_instance(clean_logger, monkeypatch, tmp_path):
    """get_logger returns a configured logging.Logger."""
    _patch_user_data_dir(monkeypatch, tmp_path)
    log = get_logger()
    assert isinstance(log, logging.Logger)
    assert log.name == "bellbird"


def test_get_logger_writes_to_data_dir(clean_logger, monkeypatch, tmp_path):
    """The log file is created under the user-data directory."""
    _patch_user_data_dir(monkeypatch, tmp_path)
    log = get_logger()
    log.info("hello from bellbird")
    # Flush buffered writes so we can read the file before the
    # handler is closed.
    for h in log.handlers:
        h.flush()

    log_file = tmp_path / "bellbird.log"
    assert log_file.exists(), f"Expected log file at {log_file}"
    content = log_file.read_text(encoding="utf-8")
    assert "hello from bellbird" in content
    assert "INFO" in content


def test_get_logger_is_idempotent(clean_logger, monkeypatch, tmp_path):
    """Calling get_logger twice returns the same logger with the same handlers."""
    _patch_user_data_dir(monkeypatch, tmp_path)
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
    _patch_user_data_dir(monkeypatch, tmp_path)
    log = get_logger()
    log.debug("d-message")
    log.info("i-message")
    log.warning("w-message")
    log.error("e-message")
    for h in log.handlers:
        h.flush()

    content = (tmp_path / "bellbird.log").read_text(encoding="utf-8")
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
    _patch_user_data_dir(monkeypatch, tmp_path)
    log = get_logger()
    log.info("mensaje con eñes y acentos: á é í ó ú ñ")
    for h in log.handlers:
        h.flush()

    content = (tmp_path / "bellbird.log").read_text(encoding="utf-8")
    assert "eñes" in content
    assert "ñ" in content


def test_get_logger_swallows_file_open_failure(clean_logger, monkeypatch, tmp_path):
    """If the log file cannot be opened, a NullHandler is attached and no raise."""
    _patch_user_data_dir(monkeypatch, tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "bellbird.core.logger.logging.FileHandler",
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


# ── New tests: Phase 3 — Logger under user-data dir ──────────────────────────


def test_log_path_is_under_user_data_dir(clean_logger, monkeypatch, tmp_path):
    """GIVEN user_data_dir returns <tmp_path>
    WHEN get_logger() runs
    THEN get_log_path() returns <tmp_path>/bellbird.log."""
    from bellbird.core.logger import get_log_path

    _patch_user_data_dir(monkeypatch, tmp_path)
    log = get_logger()
    log_path = get_log_path()
    expected = tmp_path / "bellbird.log"
    assert log_path == expected
    assert log_path.exists()


def test_get_logger_swallows_user_data_dir_error(clean_logger, monkeypatch, tmp_path):
    """GIVEN user_data_dir() raises OSError
    WHEN get_logger() is called
    THEN no exception propagates and NullHandler is attached."""
    import bellbird.core.logger as logger_module

    def raising_user_data_dir():
        raise OSError("permission denied")

    monkeypatch.setattr(logger_module, "user_data_dir", raising_user_data_dir)

    # Must not raise
    log = get_logger()

    # Should have a NullHandler as fallback
    null_handlers = [h for h in log.handlers if isinstance(h, logging.NullHandler)]
    assert len(null_handlers) == 1

    # Calling .info() must not raise
    log.info("after fallback — must not raise")


def test_get_logger_swallows_file_open_error(clean_logger, monkeypatch, tmp_path):
    """GIVEN user_data_dir returns a path BUT FileHandler raises
    WHEN get_logger() is called
    THEN no exception propagates and NullHandler is attached."""
    _patch_user_data_dir(monkeypatch, tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "bellbird.core.logger.logging.FileHandler",
            lambda *a, **kw: (_ for _ in ()).throw(PermissionError("denied")),
        )
        # Must not raise
        log = get_logger()

    # Should have a NullHandler as fallback
    null_handlers = [h for h in log.handlers if isinstance(h, logging.NullHandler)]
    assert len(null_handlers) == 1

    # Calling .info() must not raise
    log.info("after fallback — must not raise")
