"""Runtime tests for PreferencesDialog — wx instantiation required (Windows only).

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
    """Create a PreferencesDialog against a parent wx.Frame."""
    if config is None:
        config = BellbirdConfig()
    from bellbird.ui.preferences_dialog import PreferencesDialog

    parent = wx.Frame(None, title="TestParent")
    dlg = PreferencesDialog(parent, config)
    dlg.Show()  # non-blocking
    return dlg


def _find(dlg, name):
    """Find a named child scoped to ``dlg``.

    ``wx.Window.FindWindowByName`` is a *static* method whose ``parent``
    defaults to ``None`` — so ``dlg.FindWindowByName(name)`` searches every
    live wx window globally and can return a same-named control from a
    previous (deferred-Destroy) dialog instead of this one's. Passing ``dlg``
    as the explicit parent keeps the search scoped.
    """
    return wx.Window.FindWindowByName(name, dlg)


class TestPreferencesDialog:
    """PreferencesDialog: construction, OK flow, control manipulation."""

    def test_dialog_constructs_and_shows(self, app) -> None:
        """Creating and showing the dialog does not crash."""
        dlg = _make_dialog(app)
        try:
            assert isinstance(dlg, wx.Dialog), (
                "PreferencesDialog must be a wx.Dialog"
            )
            assert dlg.GetName() == "preferences_dialog", (
                f"Expected name='preferences_dialog', got {dlg.GetName()!r}"
            )
        finally:
            dlg.Destroy()

    def test_ok_round_trip_unmodified_config(self, app) -> None:
        """OK on an unmodified config round-trips the original values."""
        original = BellbirdConfig(system_prompt="hola")
        dlg = _make_dialog(app, config=original)
        try:
            # The dialog is shown non-modally (Show, not ShowModal), so
            # EndModal() would assert. Simulate the OK handler, which applies
            # the controls back into the config before closing.
            dlg._apply_config()
            result = dlg.get_config()
            assert result.system_prompt == "hola", (
                f"Expected 'hola', got {result.system_prompt!r}"
            )
        finally:
            dlg.Destroy()

    def test_change_system_prompt_updates_config(self, app) -> None:
        """Changing the system prompt TextCtrl and calling _apply_config updates
        the config."""
        dlg = _make_dialog(app)
        try:
            dlg.pref_system_prompt.SetValue("nuevo")
            dlg._apply_config()
            assert dlg._config.system_prompt == "nuevo", (
                f"Expected 'nuevo', got {dlg._config.system_prompt!r}"
            )
        finally:
            dlg.Destroy()

    def test_toggle_lectura_filter_updates_config(self, app) -> None:
        """Toggling a Lectura filter CheckBox and calling _apply_config updates
        the config."""
        dlg = _make_dialog(app)
        try:
            url_check = _find(dlg, "pref_filter_urls")
            assert url_check is not None, "pref_filter_urls not found"
            assert isinstance(url_check, wx.CheckBox)

            # Start checked (True by default), uncheck it
            url_check.SetValue(False)
            dlg._apply_config()
            assert dlg._config.filter_strip_urls is False, (
                "Expected filter_strip_urls to be False after unchecking"
            )
        finally:
            dlg.Destroy()

    def test_preset_selection_updates_config(self, app) -> None:
        """Selecting a preset and ending modal OK updates config.param_presets."""
        from bellbird.core.preset import ParamPreset

        preset = ParamPreset(
            name="Mi Preset", temperature=0.5, max_tokens=2048,
            top_p=0.8, top_k=30, repeat_penalty=1.2, min_p=0.1, seed=42,
        )
        config = BellbirdConfig(param_presets=[preset])
        dlg = _make_dialog(app, config=config)
        try:
            # Select the preset in the listbox
            preset_list = _find(dlg, "pref_presets_list")
            assert preset_list is not None, "pref_presets_list not found"
            assert isinstance(preset_list, wx.ListBox)
            preset_list.SetSelection(0)

            # Non-modal dialog: simulate the OK handler instead of EndModal().
            dlg._apply_config()
            result = dlg.get_config()
            assert len(result.param_presets) == 1, (
                f"Expected 1 preset, got {len(result.param_presets)}"
            )
            assert result.param_presets[0].name == "Mi Preset", (
                f"Expected 'Mi Preset', got {result.param_presets[0].name!r}"
            )
        finally:
            dlg.Destroy()

    def test_audio_voice_round_trip(self, app) -> None:
        """Setting voice/rate controls and applying config updates the
        corresponding fields."""
        dlg = _make_dialog(app)
        try:
            # Set rate via slider
            rate_slider = _find(dlg, "pref_rate_slider")
            assert rate_slider is not None, "pref_rate_slider not found"
            rate_slider.SetValue(5)

            dlg._apply_config()
            assert dlg._config.system_voice_rate == 5, (
                f"Expected system_voice_rate=5, got {dlg._config.system_voice_rate}"
            )
        finally:
            dlg.Destroy()

    def test_all_interactive_controls_have_name(self, app) -> None:
        """Every wx.Button, wx.CheckBox, wx.Choice, wx.Slider, and wx.TextCtrl
        in the dialog has a non-empty GetName()."""
        dlg = _make_dialog(app)
        interactive_types = (wx.Button, wx.CheckBox, wx.Choice, wx.Slider, wx.TextCtrl)
        try:
            unnamed: list[str] = []
            for child in dlg.GetChildren():
                if isinstance(child, interactive_types):
                    name = child.GetName()
                    if not name:
                        # Try to identify the control
                        label = getattr(child, "GetLabel", lambda: "")()
                        unnamed.append(f"{type(child).__name__}(label={label!r})")

            assert not unnamed, (
                f"Interactive controls without name=:\n  " + "\n  ".join(unnamed)
            )
        finally:
            dlg.Destroy()
