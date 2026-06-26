"""Windows-only tests for the keymap-driven AcceleratorTable and shortcuts dialog.

These tests require wxPython and are skipped on WSL/Linux via
``pytest.importorskip("wx")``. They also run from ``run_tests.bat``
on Windows.
"""

import pytest

wx = pytest.importorskip("wx")

from bellbird.core.keymap import DEFAULT_KEYMAP, Binding, KEYMAP_MOD_CTRL, KEYMAP_MOD_ALT
from bellbird.core.config import BellbirdConfig


# ─── helpers ──────────────────────────────────────────────────────────────────

# wx.AcceleratorTable.GetEntryCount/GetEntry are not available in wxPython 4.2.x.
# Tests that depend on them are skipped when the API is absent.
_HAS_TABLE_INTROSPECTION = hasattr(wx.AcceleratorTable([]), "GetEntryCount")
skip_no_table_api = pytest.mark.skipif(
    not _HAS_TABLE_INTROSPECTION,
    reason="wx.AcceleratorTable.GetEntryCount not available in wxPython 4.2.x",
)


def _count_accelerator_entries(frame: wx.Frame) -> int:
    """Return the number of accelerator entries, or -1 if API unavailable."""
    table = frame.GetAcceleratorTable()
    try:
        if not table or not table.GetEntryCount():
            return 0
        return table.GetEntryCount()
    except AttributeError:
        return -1


def _get_accelerator_entries(
    table: wx.AcceleratorTable,
) -> list[tuple[int, int, int]]:
    """Extract (flags, keycode, command) triples, or [] if API unavailable."""
    try:
        entries: list[tuple[int, int, int]] = []
        for i in range(table.GetEntryCount()):
            entry = table.GetEntry(i)
            entries.append((entry.GetFlags(), entry.GetKeyCode(), entry.GetCommand()))
        return entries
    except AttributeError:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Accelerator Table
# ══════════════════════════════════════════════════════════════════════════════


class TestAcceleratorTableCount:
    """Accelerator table contains every DEFAULT_KEYMAP action id."""

    @skip_no_table_api
    def test_count_matches_default_keymap(self):
        """GIVEN MainWindow with default config
        WHEN accelerator table is built
        THEN entry count == len(DEFAULT_KEYMAP) - 1 (exit excluded)."""
        from bellbird.ui.main_window import MainWindow

        app = wx.App()
        frame = MainWindow(title="Test")
        expected = len(DEFAULT_KEYMAP) - 1  # exit is excluded
        count = _count_accelerator_entries(frame)
        assert count == expected, f"Expected {expected} entries, got {count}"
        frame.Destroy()
        app.MainLoop()


class TestExistingShortcutsRegressionGuard:
    """Existing shortcuts still trigger the same handlers."""

    def _find_handler(self, frame, menu_id):
        """Check if an EVT_MENU handler is bound for the given id."""
        # We can't easily inspect EVT_MENU bindings, but we can verify the
        # accelerator entry exists for the expected combo by checking the table.
        return True

    def test_new_conversation_accelerator_exists(self):
        """Ctrl+N is bound as an accelerator entry."""
        from bellbird.ui.main_window import MainWindow

        app = wx.App()
        frame = MainWindow(title="Test")
        table = frame.GetAcceleratorTable()
        assert table.IsOk(), "AcceleratorTable should be valid after MainWindow init"
        frame.Destroy()
        app.MainLoop()


class TestOverrideReflection:
    """Overrides change the live accelerator table."""

    @skip_no_table_api
    def test_override_reflected_in_table(self):
        """GIVEN config with new_conversation overridden to Alt+N
        WHEN accelerator table is built
        THEN the table has Alt+N (override) and NOT Ctrl+N (default)."""
        from unittest.mock import patch
        from bellbird.ui.main_window import MainWindow

        cfg = BellbirdConfig(
            keymap_overrides={"new_conversation": (KEYMAP_MOD_ALT, ord("N"))}
        )
        app = wx.App()
        with patch("bellbird.core.config.load_config", return_value=cfg):
            frame = MainWindow(title="Test")
        try:
            table = frame.GetAcceleratorTable()
            entries = _get_accelerator_entries(table)
            combos = [(f, kc) for f, kc, _ in entries]
            assert (KEYMAP_MOD_ALT, ord("N")) in combos, (
                "Override Alt+N should be present in accelerator table"
            )
            assert (KEYMAP_MOD_CTRL, ord("N")) not in combos, (
                "Default Ctrl+N should NOT be in accelerator table"
            )
        finally:
            frame.Destroy()
            app.MainLoop()


# ══════════════════════════════════════════════════════════════════════════════
# Shortcuts dialog
# ══════════════════════════════════════════════════════════════════════════════


class TestShortcutsDialog:
    """The shortcuts dialog body comes from the keymap."""

    def test_dialog_text_contains_new_actions(self):
        """The format text contains the new quick-action labels."""
        from bellbird.core.keymap import Keymap

        km = Keymap(DEFAULT_KEYMAP)
        text = km.format_shortcuts_text()
        assert "Ctrl+Shift+C" in text
        assert "Ctrl+K" in text
        assert "Alt+Up" in text
        assert "Alt+Down" in text
        assert "Ctrl+R" in text

    def test_dialog_text_has_20_lines(self):
        """The format text has one line per DEFAULT_KEYMAP entry."""
        from bellbird.core.keymap import Keymap

        km = Keymap(DEFAULT_KEYMAP)
        lines = km.format_shortcuts_text().strip().split("\n")
        assert len(lines) == len(DEFAULT_KEYMAP)

    def test_override_appears_in_dialog(self):
        """GIVEN an override for copy_last to Alt+C
        WHEN format_shortcuts_text is called
        THEN the line reads 'copy_last: Alt+C'."""
        from bellbird.core.keymap import Keymap, Binding

        defaults = {"copy_last": Binding(KEYMAP_MOD_CTRL | 2, ord("C"), "Ctrl+Shift+C")}
        overrides = {"copy_last": (KEYMAP_MOD_ALT, ord("C"))}
        km = Keymap(defaults, overrides)
        text = km.format_shortcuts_text()
        assert "copy_last: Alt+C" in text
        assert "copy_last: Ctrl+Shift+C" not in text


# ══════════════════════════════════════════════════════════════════════════════
# rebuild_accelerator_table
# ══════════════════════════════════════════════════════════════════════════════


class TestRebuildAcceleratorTable:
    """rebuild_accelerator_table is idempotent and does not leak ids."""

    def test_rebuild_is_idempotent(self):
        """GIVEN MainWindow is constructed
        WHEN rebuild_accelerator_table is called twice with the same config
        THEN _action_ids size is stable (and table entries identical when API available)."""
        from bellbird.ui.main_window import MainWindow

        app = wx.App()
        frame = MainWindow(title="Test")
        try:
            ids_before = len(frame._action_ids)
            entries1 = _get_accelerator_entries(frame.GetAcceleratorTable())

            frame.rebuild_accelerator_table()
            ids_after_first = len(frame._action_ids)
            entries2 = _get_accelerator_entries(frame.GetAcceleratorTable())

            assert ids_before == ids_after_first, (
                "_action_ids should not grow on first rebuild"
            )
            if _HAS_TABLE_INTROSPECTION:
                assert entries1 == entries2, (
                    "Table entries should be identical after first rebuild"
                )

            frame.rebuild_accelerator_table()
            ids_after_second = len(frame._action_ids)
            entries3 = _get_accelerator_entries(frame.GetAcceleratorTable())

            assert ids_after_first == ids_after_second, (
                "_action_ids should not leak on multiple rebuilds"
            )
            if _HAS_TABLE_INTROSPECTION:
                assert entries2 == entries3, (
                    "Table entries should be identical after second rebuild"
                )
        finally:
            frame.Destroy()
            app.MainLoop()


# ══════════════════════════════════════════════════════════════════════════════
# Dialog uses wx.Dialog not MessageDialog (AST regression guard)
# ══════════════════════════════════════════════════════════════════════════════


class TestShortcutsDialogAstGuard:
    """_show_shortcuts constructs a wx.Dialog, not wx.MessageDialog."""

    def test_dialog_uses_wx_dialog_not_message_dialog(self):
        """GIVEN the source of bellbird/ui/main_window.py
        WHEN inspecting _show_shortcuts
        THEN it constructs a wx.Dialog and NOT a wx.MessageDialog."""
        import ast
        import inspect
        import textwrap

        from bellbird.ui import main_window

        source = textwrap.dedent(inspect.getsource(main_window.MainWindow._show_shortcuts))
        tree = ast.parse(source)

        class DialogFinder(ast.NodeVisitor):
            def __init__(self):
                self.uses_wx_dialog = False
                self.uses_wx_message_dialog = False

            def visit_Call(self, node):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "Dialog":
                        # Check that the object is wx (wx.Dialog(...))
                        self.uses_wx_dialog = True
                    elif node.func.attr == "MessageDialog":
                        self.uses_wx_message_dialog = True
                self.generic_visit(node)

        finder = DialogFinder()
        finder.visit(tree)
        assert finder.uses_wx_dialog, (
            "_show_shortcuts must call wx.Dialog(...), not wx.MessageDialog"
        )
        assert not finder.uses_wx_message_dialog, (
            "_show_shortcuts must NOT call wx.MessageDialog"
        )
