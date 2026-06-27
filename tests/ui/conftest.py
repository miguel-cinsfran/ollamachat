"""Shared fixtures for the wx-runtime UI tests.

The UI tests share a module-scoped ``wx.App`` and create/destroy
``MainWindow`` frames inside individual tests. ``MainWindow.__init__``
schedules deferred work — most importantly a daemon *startup probe*
thread that does network I/O and then posts
``wx.CallAfter(self._on_startup_probe_done, result)``.

Because the ``wx.App`` lives for the whole module, that queued
``CallAfter`` can survive the test that created it and only fire later,
during a modal loop (``ShowModal``) in an unrelated test — by which point
the frame and its status bar are already destroyed. The handler then calls
``status_bar.SetStatusText(..., 0)`` on a status bar with zero fields,
tripping a wxWidgets C++ assertion. In a non-interactive run that assertion
pops a modal dialog and **hangs the whole suite** (the historical
"CRASH-01").

No UI *unit* test needs the real probe — the probe logic itself is covered
in ``tests/core/test_startup_probe.py`` — so we stub it out for every UI
test. Tests that want to exercise the probe handler call
``_on_startup_probe_done`` / ``_on_server_state_checked`` directly.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _wx_app_session():
    """Create exactly ONE ``wx.App`` for the entire UI test session.

    wxPython supports a single ``wx.App`` per process. Historically each UI
    test module (and every test in ``test_keymap_capture.py``) created its own
    ``wx.App()`` — 30+ instances across the suite. The accumulated, half-torn
    apps corrupted global wx state and, in the full ``core + ui`` run, the
    suite eventually wedged inside ``test_keymap_capture`` (the historical
    "CRASH-01", which only reproduced after enough apps had piled up).

    This autouse session fixture builds the one app up-front; every per-module
    ``app`` fixture and inline call now resolves it via ``wx.GetApp()`` instead
    of constructing a new one. Degrades to a no-op where wx is unavailable
    (WSL/Linux), so the AST-only ``*_static.py`` tests are unaffected.
    """
    try:
        import wx
    except Exception:
        yield None
        return

    app = wx.GetApp() or wx.App()
    yield app


@pytest.fixture(autouse=True)
def _no_startup_probe_thread():
    """Stop ``MainWindow`` from spawning the real startup-probe thread.

    Degrades to a no-op where wxPython is unavailable (WSL/Linux), so the
    AST-only ``*_static.py`` tests are unaffected.
    """
    try:
        from unittest.mock import patch
        from bellbird.ui.main_window import MainWindow
    except Exception:
        # wx not installed (WSL) — nothing to patch.
        yield
        return

    with patch.object(MainWindow, "_start_probe_thread", lambda self: None):
        yield


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path):
    """Redirect persisted config to a throwaway file for every UI test.

    Several UI tests call ``MainWindow`` methods (``save_conversation``,
    ``_on_use_model``, …) that invoke ``save_config`` *after* the per-test
    ``patch("...main_window.save_config")`` context has already exited — e.g.
    ``_make_frame`` returns from inside its ``with patch`` block, so the patch
    is torn down before the test body runs. Those unpatched writes landed in
    the real user config (``%LOCALAPPDATA%\\Bellbird\\config.json``), polluting
    it with pytest temp paths and (via the mmproj flow) bogus projector entries.

    Redirecting ``config.CONFIG_PATH`` — which both ``save_config`` and
    ``load_config`` read at call time — keeps every write inside ``tmp_path``
    so the developer's real config is never touched. No-op where wx/config is
    unavailable (WSL/Linux), leaving the AST-only ``*_static.py`` tests alone.
    """
    try:
        from unittest.mock import patch
        import bellbird.core.config as config_mod
    except Exception:
        yield
        return

    with patch.object(config_mod, "CONFIG_PATH", tmp_path / "config.json"):
        yield
