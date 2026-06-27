"""wx-runtime test for MainWindow construction without network calls.

This test requires wxPython to run. It is skipped in WSL/CI environments
that do not have wxPython installed (via ``pytest.importorskip("wx")``).

On Windows, it verifies that:
- The window is shown before any I/O (startup checks are async).
- The status bar shows "Iniciando..." on construction.
"""

import pytest

pytest.importorskip("wx")

import wx


@pytest.fixture(scope="module")
def app():
    """Create a wx.App for the test module."""
    return wx.GetApp()


def test_window_shown_before_probe(app):
    """MainWindow can be shown right after __init__, before any I/O completes.

    The constructor must NOT block on the startup probe (it runs on a
    background thread), so the caller — like ``main.py`` — can ``Show()`` the
    frame immediately and the user sees "Iniciando…" while the probe works.
    If ``__init__`` blocked on network I/O this construction + Show would hang.
    """
    from bellbird.ui.main_window import MainWindow

    frame = MainWindow(None, title="Bellbird")
    try:
        frame.Show()  # production shows the frame in main.py, post-construction
        assert frame.IsShown(), "MainWindow must be visible after Show()"
        # Status bar field 0 should say "Iniciando..." until the probe completes
        status_text = frame.status_bar.GetStatusText(0)
        assert "Iniciando" in status_text, (
            f"Status bar field 0 should contain 'Iniciando...', "
            f"got: {status_text!r}"
        )
    finally:
        frame.Destroy()
