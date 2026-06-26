"""Windows-only tests for the Atajos tab and KeyCaptureControl.

These tests require wxPython and are skipped on WSL/Linux via
``pytest.importorskip("wx")``. They also run from ``run_tests.bat``
on Windows.
"""

import pytest

wx = pytest.importorskip("wx")

import unittest.mock

from bellbird.core.keymap import DEFAULT_KEYMAP, Keymap, KEYMAP_MOD_CTRL, KEYMAP_MOD_ALT, _format_combo
from bellbird.ui.preferences_dialog import (
    PreferencesDialog,
    KeyCaptureControl,
    _CaptureDialog,
    _ACTION_LABELS,
)


# ══════════════════════════════════════════════════════════════════════════════
# Atajos tab structure
# ══════════════════════════════════════════════════════════════════════════════


class TestTabOrder:
    """9 tabs present in source — labels come from AddPage literals in
    _build_ui, which include the ``&`` mnemonic prefix."""

    def _extract_tab_labels(self) -> list[str]:
        """Parse the full PreferencesDialog class source to extract AddPage
        label literals (with & mnemonics) from all _build_*_page methods."""
        import ast
        import inspect

        source = inspect.getsource(PreferencesDialog)
        tree = ast.parse(source)

        labels: list[str] = []

        class Visitor(ast.NodeVisitor):
            def visit_Call(self, node):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "AddPage"
                    and node.args
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                ):
                    labels.append(node.args[1].value)
                self.generic_visit(node)

        Visitor().visit(tree)
        return labels

    def test_nine_tabs_present(self):
        """The _build_ui method adds exactly 9 tabs with the expected labels."""
        from bellbird.ui.preferences_dialog import PreferencesDialog
        labels = self._extract_tab_labels()
        assert len(labels) == 9, f"Expected 9 tab labels, got {len(labels)}: {labels}"

    def test_tab_order(self):
        """Tab order is &General → &Modelo → C&hat → &Lectura → &Herramientas →
        &Avanzado → A&tajos → A&udio → &Estado (F2)."""
        labels = self._extract_tab_labels()
        expected = [
            "&General", "&Modelo", "C&hat", "&Lectura",
            "&Herramientas", "&Avanzado", "A&tajos", "A&udio",
            "&Estado (F2)",
        ]
        assert labels == expected, f"Tab order mismatch: {labels} != {expected}"


class TestKeymapPageRows:
    """Atajos tab has one row per DEFAULT_KEYMAP entry, alphabetically sorted."""

    def test_rows_match_default_keymap_count(self):
        """GIVEN PreferencesDialog with default config
        WHEN _build_keymap_page runs
        THEN _keymap_rows has one entry per DEFAULT_KEYMAP entry."""
        app = wx.App()
        from bellbird.core.config import BellbirdConfig
        from bellbird.ui.main_window import MainWindow

        frame = MainWindow(title="Test")
        dlg = PreferencesDialog(frame, BellbirdConfig())
        # Force page build by accessing the rows
        count = len(dlg._keymap_rows)
        assert count == len(DEFAULT_KEYMAP), (
            f"Expected {len(DEFAULT_KEYMAP)} rows, got {count}"
        )
        dlg.Destroy()
        frame.Destroy()
        app.MainLoop()

    def test_action_labels_cover_all_ids(self):
        """Every action_id in DEFAULT_KEYMAP has a Spanish label in _ACTION_LABELS."""
        missing = set(DEFAULT_KEYMAP.keys()) - set(_ACTION_LABELS.keys())
        assert not missing, f"Missing Spanish labels for: {missing}"

    def test_row_buttons_have_correct_names(self):
        """Each row's buttons have the documented name attributes."""
        app = wx.App()
        from bellbird.core.config import BellbirdConfig
        from bellbird.ui.main_window import MainWindow

        frame = MainWindow(title="Test")
        dlg = PreferencesDialog(frame, BellbirdConfig())
        # Check first row's buttons
        first_aid = sorted(DEFAULT_KEYMAP.keys())[0]
        row = dlg._keymap_rows[first_aid]
        assert row["cambiar"].GetName() == "keymap_capture_button"
        assert row["restablecer"].GetName() == "keymap_reset_button"
        dlg.Destroy()
        frame.Destroy()
        app.MainLoop()


# ══════════════════════════════════════════════════════════════════════════════
# KeyCaptureControl
# ══════════════════════════════════════════════════════════════════════════════


class TestKeyCaptureControl:
    """KeyCaptureControl EVT_KEY_DOWN reading."""

    def test_panel_name(self):
        """KeyCaptureControl panel has name='key_capture_panel'."""
        app = wx.App()
        dlg = wx.Dialog(None, title="Test")
        kcc = KeyCaptureControl(dlg, None)
        assert kcc.GetName() == "key_capture_panel"
        dlg.Destroy()
        app.MainLoop()

    def test_capture_label_static_text_name(self):
        """The capture label StaticText has name='key_capture_label'."""
        app = wx.App()
        dlg = wx.Dialog(None, title="Test")
        kcc = KeyCaptureControl(dlg, None)
        for child in kcc.GetChildren():
            if child.GetName() == "key_capture_label":
                label = child
                break
        else:
            pytest.fail("No key_capture_label found")
        assert label is not None
        dlg.Destroy()
        app.MainLoop()

    def test_capture_starts_empty(self):
        """captured is False and label is empty before any key is pressed."""
        app = wx.App()
        dlg = wx.Dialog(None, title="Test")
        kcc = KeyCaptureControl(dlg, None)
        assert not kcc.captured
        assert kcc.captured_modifiers == 0
        assert kcc.captured_keycode == 0
        dlg.Destroy()
        app.MainLoop()


# ══════════════════════════════════════════════════════════════════════════════
# _CaptureDialog
# ══════════════════════════════════════════════════════════════════════════════


class TestCaptureDialog:
    """Capture mini-dialog structure and conflict rejection."""

    def test_dialog_name_and_title(self):
        """_CaptureDialog has name='keymap_capture_dialog' and caption 'Capturar atajo'."""
        app = wx.App()
        from bellbird.core.config import BellbirdConfig

        dlg = _CaptureDialog(None, Keymap(DEFAULT_KEYMAP), "copy_last", None)
        assert dlg.GetName() == "keymap_capture_dialog"
        assert dlg.GetTitle() == "Capturar atajo"
        dlg.Destroy()
        app.MainLoop()

    def test_capture_dialog_has_accept_and_cancel_buttons(self):
        """The dialog has buttons named key_capture_accept_button and key_capture_cancel_button."""
        app = wx.App()
        dlg = _CaptureDialog(None, Keymap(DEFAULT_KEYMAP), "copy_last", None)

        accept = dlg.FindWindowByName("key_capture_accept_button")
        cancel = dlg.FindWindowByName("key_capture_cancel_button")
        assert accept is not None, "Accept button not found"
        assert cancel is not None, "Cancel button not found"
        assert not accept.IsEnabled(), "Accept button should be disabled initially"
        dlg.Destroy()
        app.MainLoop()

    def test_accept_disabled_initially(self):
        """Accept button is disabled until a key is captured."""
        app = wx.App()
        dlg = _CaptureDialog(None, Keymap(DEFAULT_KEYMAP), "copy_last", None)
        assert not dlg.accept_btn.IsEnabled()
        dlg.Destroy()
        app.MainLoop()

    def test_conflict_rejection_keeps_previous_binding(self):
        """GIVEN a combo used by another action
        WHEN the user accepts with that combo
        THEN the dialog speaks the conflict, ends with ID_CANCEL (binding unchanged)."""
        app = wx.App()
        mock_speech = unittest.mock.Mock()
        dlg = _CaptureDialog(None, Keymap(DEFAULT_KEYMAP), "copy_last", mock_speech)

        # Simulate capturing Ctrl+N (used by new_conversation)
        dlg._capture._captured = True
        dlg._capture._captured_modifiers = KEYMAP_MOD_CTRL
        dlg._capture._captured_keycode = ord("N")

        with unittest.mock.patch.object(dlg, "EndModal") as mock_endmodal:
            dlg._on_accept(None)

        # Verify Spanish announcement
        mock_speech.speak.assert_called_once()
        msg = mock_speech.speak.call_args[0][0]
        assert "Combinación ya usada por" in msg
        # Verify dialog closes with CANCEL (binding unchanged)
        mock_endmodal.assert_called_once_with(wx.ID_CANCEL)

        dlg.Destroy()
        app.MainLoop()

    def test_no_conflict_returns_ok(self):
        """GIVEN an unused combo
        WHEN accepting
        THEN find_conflict returns None for the unused combo."""
        app = wx.App()
        km = Keymap(DEFAULT_KEYMAP)
        # Ctrl+Q is unused in defaults
        assert km.find_conflict(KEYMAP_MOD_CTRL, ord("Q")) is None
        app.MainLoop()

    def test_set_escape_id(self):
        """Escape closes the capture dialog."""
        import ast
        import inspect

        source = inspect.getsource(_CaptureDialog.__init__)
        assert "SetEscapeId" in source, (
            "_CaptureDialog must call SetEscapeId(wx.ID_CANCEL)"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Restablecer
# ══════════════════════════════════════════════════════════════════════════════


class TestRestablecer:
    """Restablecer removes the override and updates the row."""

    def test_restablecer_clears_override(self):
        """GIVEN an override for copy_last
        WHEN _on_restablecer is called
        THEN the override is removed from config.keymap_overrides."""
        from copy import deepcopy
        from bellbird.core.config import BellbirdConfig

        app = wx.App()
        from bellbird.ui.main_window import MainWindow

        cfg = BellbirdConfig(keymap_overrides={"copy_last": (KEYMAP_MOD_ALT, ord("C"))})
        frame = MainWindow(title="Test")
        dlg = PreferencesDialog(frame, cfg)

        # Verify the override is present initially
        assert "copy_last" in dlg._config.keymap_overrides

        # Call restablecer
        dlg._on_restablecer("copy_last")

        # Verify override is removed
        assert "copy_last" not in dlg._config.keymap_overrides

        dlg.Destroy()
        frame.Destroy()
        app.MainLoop()


# ══════════════════════════════════════════════════════════════════════════════
# PreferencesDialog OK handler
# ══════════════════════════════════════════════════════════════════════════════


class TestPreferencesDialogOverrides:
    """keymap_overrides are written to config on OK."""

    def test_keymap_overrides_survive_apply_config(self):
        """GIVEN an override is set in the Atajos tab
        WHEN _apply_config is called
        THEN keymap_overrides remains on self._config."""
        from bellbird.core.config import BellbirdConfig

        app = wx.App()
        from bellbird.ui.main_window import MainWindow

        cfg = BellbirdConfig()
        frame = MainWindow(title="Test")
        dlg = PreferencesDialog(frame, cfg)

        # Simulate setting an override via Cambiar
        dlg._config.keymap_overrides["copy_last"] = (KEYMAP_MOD_ALT, ord("C"))

        # Call apply config
        dlg._apply_config()

        # Verify override survived
        assert dlg._config.keymap_overrides.get("copy_last") == (KEYMAP_MOD_ALT, ord("C"))

        dlg.Destroy()
        frame.Destroy()
        app.MainLoop()


# ══════════════════════════════════════════════════════════════════════════════
# MainWindow._show_preferences diff-and-rebuild
# ══════════════════════════════════════════════════════════════════════════════


class TestMainWindowShowPreferences:
    """_show_preferences diffs keymap_overrides and calls rebuild_accelerator_table."""

    def test_rebuild_called_on_override_change(self):
        """GIVEN keymap_overrides changed in dialog
        WHEN ShowModal returns wx.ID_OK
        THEN rebuild_accelerator_table is called."""
        from bellbird.core.config import BellbirdConfig
        from bellbird.ui.main_window import MainWindow

        app = wx.App()
        # Start from a known-empty override state regardless of disk content
        clean_cfg = BellbirdConfig()
        modified_cfg = BellbirdConfig(
            keymap_overrides={"new_conversation": (KEYMAP_MOD_ALT, ord("N"))}
        )
        with unittest.mock.patch("bellbird.ui.main_window.load_config", return_value=clean_cfg):
            frame = MainWindow(title="Test")

        with unittest.mock.patch.object(
            frame, "rebuild_accelerator_table",
        ) as mock_rebuild:
            with unittest.mock.patch.object(
                PreferencesDialog, "ShowModal", return_value=wx.ID_OK,
            ):
                with unittest.mock.patch.object(
                    PreferencesDialog, "get_config", return_value=modified_cfg,
                ):
                    with unittest.mock.patch(
                        "bellbird.ui.main_window.save_config"
                    ):
                        frame._show_preferences()

        mock_rebuild.assert_called_once()
        frame.Destroy()
        app.MainLoop()

    def test_no_rebuild_when_overrides_unchanged(self):
        """GIVEN keymap_overrides unchanged in dialog
        WHEN ShowModal returns wx.ID_OK
        THEN rebuild_accelerator_table is NOT called."""
        from bellbird.core.config import BellbirdConfig
        from bellbird.ui.main_window import MainWindow

        app = wx.App()
        frame = MainWindow(title="Test")

        with unittest.mock.patch.object(
            frame, "rebuild_accelerator_table",
        ) as mock_rebuild:
            with unittest.mock.patch.object(
                PreferencesDialog, "ShowModal", return_value=wx.ID_OK,
            ):
                frame._show_preferences()

        mock_rebuild.assert_not_called()
        frame.Destroy()
        app.MainLoop()

    def test_cancel_does_not_rebuild(self):
        """GIVEN user cancels PreferencesDialog
        WHEN ShowModal returns wx.ID_CANCEL
        THEN rebuild_accelerator_table is NOT called."""
        from bellbird.core.config import BellbirdConfig
        from bellbird.ui.main_window import MainWindow

        app = wx.App()
        frame = MainWindow(title="Test")

        with unittest.mock.patch.object(
            frame, "rebuild_accelerator_table",
        ) as mock_rebuild:
            with unittest.mock.patch.object(
                PreferencesDialog, "ShowModal", return_value=wx.ID_CANCEL,
            ):
                frame._show_preferences()

        mock_rebuild.assert_not_called()
        frame.Destroy()
        app.MainLoop()


# ══════════════════════════════════════════════════════════════════════════════
# Format combo consistency
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatCombo:
    """_format_combo produces correct labels."""

    def test_ctrl_shift_c(self):
        """KEYMAP_MOD_CTRL | KEYMAP_MOD_SHIFT, ord('C') → 'Ctrl+Shift+C'."""
        result = _format_combo(KEYMAP_MOD_CTRL | 2, ord("C"))
        assert "Ctrl" in result
        assert "Shift" in result
        assert "C" in result

    def test_alt_n(self):
        """KEYMAP_MOD_ALT, ord('N') → 'Alt+N'."""
        result = _format_combo(KEYMAP_MOD_ALT, ord("N"))
        assert result == "Alt+N"
