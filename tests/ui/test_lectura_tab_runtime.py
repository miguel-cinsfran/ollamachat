"""Runtime tests for the Lectura tab of PreferencesDialog — wx required (Windows only).

These tests require a wx application object and real wxPython.
They are skipped automatically on WSL/Linux via ``importorskip("wx")``.
Run via ``run_tests.bat`` on Windows.
"""

import pytest

pytest.importorskip("wx")

import wx

from bellbird.core.config import BellbirdConfig


@pytest.fixture(scope="module")
def app():
    """Create a wx.App for the test module."""
    return wx.GetApp()


def _make_dialog(app, config: BellbirdConfig | None = None) -> "PreferencesDialog":
    """Create a PreferencesDialog and return it."""
    if config is None:
        config = BellbirdConfig()
    from bellbird.ui.preferences_dialog import PreferencesDialog

    parent = wx.Frame(None, title="TestParent")
    dlg = PreferencesDialog(parent, config)
    dlg.Show()
    return dlg


def _find(dlg: wx.Window, name: str) -> wx.Window | None:
    """Find a named child *within* ``dlg``.

    ``wx.Window.FindWindowByName`` is a *static* method whose ``parent``
    argument defaults to ``None`` — meaning ``dlg.FindWindowByName(name)``
    actually performs a **global** search across every live wx window, not a
    search scoped to ``dlg``. Because ``Destroy()`` is deferred, checkboxes
    from previous (not-yet-reaped) dialogs share the same names and can be
    returned instead of this dialog's own controls. Always pass ``dlg`` as the
    explicit parent so the search stays scoped.
    """
    return wx.Window.FindWindowByName(name, dlg)


def _destroy(dlg: wx.Window) -> None:
    """Destroy the dialog and its (test-only) parent frame.

    ``_make_dialog`` parents each dialog on a throwaway ``wx.Frame`` that would
    otherwise leak for the whole module run. Destroying both keeps the window
    tree from accumulating stale named controls between tests.
    """
    parent = dlg.GetParent()
    dlg.Destroy()
    if parent is not None:
        parent.Destroy()


class TestLecturaTab:
    """Lectura tab: filter CheckBoxes, initial state, toggling, round-trip."""

    FILTER_NAMES = [
        "pref_filter_markdown",
        "pref_filter_urls",
        "pref_filter_emojis",
        "pref_filter_code_blocks",
    ]

    def test_lectura_page_constructs(self, app) -> None:
        """The Lectura tab panel exists and is named 'lectura_page'."""
        dlg = _make_dialog(app)
        try:
            panel = _find(dlg, "lectura_page")
            assert panel is not None, "lectura_page panel not found"
            assert isinstance(panel, wx.Window)
        finally:
            _destroy(dlg)

    def test_all_4_filter_checkboxes_present(self, app) -> None:
        """All 4 reading-filter CheckBoxes exist with their documented names."""
        dlg = _make_dialog(app)
        try:
            for name in self.FILTER_NAMES:
                chk = _find(dlg, name)
                assert chk is not None, f"CheckBox '{name}' not found"
                assert isinstance(chk, wx.CheckBox), (
                    f"'{name}' is not a wx.CheckBox (got {type(chk).__name__})"
                )
        finally:
            _destroy(dlg)

    def test_default_state_all_checked(self, app) -> None:
        """With a fresh BellbirdConfig, all 4 filter CheckBoxes are checked."""
        dlg = _make_dialog(app)
        try:
            for name in self.FILTER_NAMES:
                chk = _find(dlg, name)
                assert chk is not None
                assert chk.IsChecked(), (
                    f"'{name}' should be checked by default"
                )
        finally:
            _destroy(dlg)

    def test_uncheck_urls_updates_value(self, app) -> None:
        """Unchecking the URL filter updates its IsChecked() state."""
        dlg = _make_dialog(app)
        try:
            chk = _find(dlg, "pref_filter_urls")
            assert chk is not None
            assert isinstance(chk, wx.CheckBox)

            assert chk.IsChecked(), "Expected initially checked"
            chk.SetValue(False)
            assert not chk.IsChecked(), "Expected unchecked after SetValue(False)"
        finally:
            _destroy(dlg)

    def test_filter_state_round_trips_reopen(self, app) -> None:
        """A config with filter_strip_emojis=False reflects in the CheckBox."""
        config = BellbirdConfig(filter_strip_emojis=False)
        dlg = _make_dialog(app, config=config)
        try:
            chk = _find(dlg, "pref_filter_emojis")
            assert chk is not None
            assert isinstance(chk, wx.CheckBox)
            assert not chk.IsChecked(), (
                "Expected emojis checkbox to be unchecked with "
                "filter_strip_emojis=False"
            )
        finally:
            _destroy(dlg)

    def test_uncheck_urls_apply_config_updates_config(self, app) -> None:
        """Unchecking URL filter and calling _apply_config persists to config."""
        dlg = _make_dialog(app)
        try:
            chk = _find(dlg, "pref_filter_urls")
            assert chk is not None
            assert isinstance(chk, wx.CheckBox)
            chk.SetValue(False)
            dlg._apply_config()
            assert dlg._config.filter_strip_urls is False, (
                "Expected filter_strip_urls=False after uncheck + _apply_config"
            )
        finally:
            _destroy(dlg)
