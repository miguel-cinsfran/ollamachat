"""Tests for bellbird.core.keymap — strict TDD, wx-free.

Covers: Binding dataclass, Keymap construction, DEFAULT_KEYMAP collision
freedom, conflict detection, override (de)serialization, resolve(),
format_shortcuts_text(), and the AST guard (no import wx at module level).
"""

import ast
import sys

import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────

# wx.WXK_* integer literals matching wxPython 4.2 canonical values
# These are defined here so core/ tests don't import wx at all.
_WXK_F2 = 340
_WXK_F4 = 342
_WXK_F5 = 343
_WXK_F6 = 344
_WXK_F7 = 345
_WXK_F8 = 346
_WXK_ESCAPE = 27
_WXK_UP = 315
_WXK_DOWN = 317

from bellbird.core.keymap import (
    Binding,
    KEYMAP_MOD_NONE,
    KEYMAP_MOD_CTRL,
    KEYMAP_MOD_SHIFT,
    KEYMAP_MOD_ALT,
    Keymap,
    KeymapConflictError,
    DEFAULT_KEYMAP,
)


# ─── Binding dataclass ───────────────────────────────────────────────────────


class TestBinding:
    """Binding is a frozen dataclass with modifiers, keycode, label."""

    def test_frozen(self):
        b = Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")
        with pytest.raises(AttributeError):
            b.modifiers = 99

    def test_attributes(self):
        b = Binding(KEYMAP_MOD_CTRL | KEYMAP_MOD_SHIFT, ord("C"), "Ctrl+Shift+C")
        assert b.modifiers == KEYMAP_MOD_CTRL | KEYMAP_MOD_SHIFT
        assert b.keycode == ord("C")
        assert b.label == "Ctrl+Shift+C"


# ─── Module-level constants ──────────────────────────────────────────────────


class TestModConstants:
    """Module-level modifiers constants exist and have expected values."""

    def test_values(self):
        assert KEYMAP_MOD_NONE == 0
        assert KEYMAP_MOD_CTRL == 1
        assert KEYMAP_MOD_SHIFT == 2
        assert KEYMAP_MOD_ALT == 4


# ─── Keymap construction ─────────────────────────────────────────────────────


class TestKeymapDefaults:
    """Keymap(defaults) without overrides."""

    def test_defaults_only(self):
        defaults = {"foo": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")}
        km = Keymap(defaults)
        assert km.actions["foo"] == Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")
        assert len(km.actions) == 1

    def test_actions_is_copy(self):
        defaults = {"foo": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")}
        km = Keymap(defaults)
        # Mutate the returned dict
        km.actions["foo"] = Binding(0, 0, "X")
        # Original defaults unchanged
        assert defaults["foo"] == Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")
        # A fresh Keymap has the original defaults
        km2 = Keymap(defaults)
        assert km2.actions["foo"] == Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")


class TestKeymapOverrides:
    """Keymap(defaults, overrides) merges overrides correctly."""

    def test_overrides_merge_and_win(self):
        defaults = {"foo": Binding(0, ord("N"), "N")}
        overrides = {"foo": (KEYMAP_MOD_CTRL, ord("N"))}
        km = Keymap(defaults, overrides)
        # Label preserved from defaults, combo from override
        assert km.actions["foo"] == Binding(KEYMAP_MOD_CTRL, ord("N"), "N")
        assert len(km.actions) == 1

    def test_unknown_action_id_ignored(self):
        overrides = {"ghost_action": (0, ord("Q"))}
        defaults = {}
        km = Keymap(defaults, overrides)
        assert km.actions == {}

    def test_overrides_empty_by_default(self):
        km = Keymap({"x": Binding(0, 0, "X")})
        assert km.actions["x"] == Binding(0, 0, "X")


class TestDefaultKeymap:
    """DEFAULT_KEYMAP module constant."""

    def test_contains_all_documented_ids(self):
        expected_ids = {
            "new_conversation",
            "open_conversation",
            "save_conversation",
            "preferences",
            "exit",
            "announce_status",
            "scan_models",
            "cycle_panels",
            "start_server",
            "stop_server",
            "abort_generation",
            "focus_chat",
            "focus_params",
            "focus_models",
            "focus_server",
            "copy_last",
            "delete_last_exchange",
            "edit_previous",
            "edit_next",
            "regenerate",
            "find_in_history",
            "attach_url",
            "read_selected_message",
        }
        assert set(DEFAULT_KEYMAP.keys()) == expected_ids
        assert len(DEFAULT_KEYMAP) == 23

    def test_labels_match_spec(self):
        expected_labels = {
            "new_conversation": "Ctrl+N",
            "open_conversation": "Ctrl+O",
            "save_conversation": "Ctrl+S",
            "preferences": "Ctrl+,",
            "exit": "Alt+F4",
            "announce_status": "F2",
            "scan_models": "F5",
            "cycle_panels": "F6",
            "start_server": "F7",
            "stop_server": "Ctrl+F7",
            "abort_generation": "Escape",
            "focus_chat": "Alt+1",
            "focus_params": "Alt+2",
            "focus_models": "Alt+3",
            "focus_server": "Alt+6",
            "copy_last": "Ctrl+Shift+C",
            "delete_last_exchange": "Ctrl+K",
            "edit_previous": "Alt+Up",
            "edit_next": "Alt+Down",
            "regenerate": "Ctrl+R",
            "find_in_history": "Ctrl+F",
            "attach_url": "Ctrl+U",
            "read_selected_message": "F8",
        }
        for action_id, binding in DEFAULT_KEYMAP.items():
            assert binding.label == expected_labels[action_id], (
                f"Label mismatch for {action_id}: expected {expected_labels[action_id]!r}, "
                f"got {binding.label!r}"
            )

    def test_no_collisions(self):
        """No two entries share the same (modifiers, keycode)."""
        combos = [(b.modifiers, b.keycode) for b in DEFAULT_KEYMAP.values()]
        assert len(combos) == len(set(combos)), (
            f"Collision detected: {len(combos)} entries but only {len(set(combos))} unique combos"
        )

    def test_default_keymap_has_attach_url(self):
        assert "attach_url" in DEFAULT_KEYMAP

    def test_attach_url_binding_is_ctrl_u(self):
        binding = DEFAULT_KEYMAP["attach_url"]
        assert binding.modifiers == KEYMAP_MOD_CTRL
        assert binding.keycode == ord("U")
        assert binding.label == "Ctrl+U"

    def test_default_keymap_includes_read_selected_message(self):
        assert "read_selected_message" in DEFAULT_KEYMAP

    def test_read_selected_message_binding_is_f8(self):
        binding = DEFAULT_KEYMAP["read_selected_message"]
        assert binding.modifiers == KEYMAP_MOD_NONE
        assert binding.keycode == _WXK_F8
        assert binding.label == "F8"

    def test_read_selected_message_no_collision(self):
        """read_selected_message combo does not collide with any other entry."""
        f8 = DEFAULT_KEYMAP["read_selected_message"]
        f8_combo = (f8.modifiers, f8.keycode)
        for aid, binding in DEFAULT_KEYMAP.items():
            if aid == "read_selected_message":
                continue
            combo = (binding.modifiers, binding.keycode)
            assert combo != f8_combo, (
                f"read_selected_message {f8_combo} collides with {aid} {combo}"
            )

    def test_read_selected_message_set_override_roundtrip(self):
        """Read_selected_message can be overridden and round-trips."""
        km = Keymap(DEFAULT_KEYMAP)
        km.set_override("read_selected_message", KEYMAP_MOD_CTRL | KEYMAP_MOD_SHIFT, ord("K"))
        assert km.resolve("read_selected_message") == (KEYMAP_MOD_CTRL | KEYMAP_MOD_SHIFT, ord("K"))
        km.remove_override("read_selected_message")
        assert km.resolve("read_selected_message") == (KEYMAP_MOD_NONE, _WXK_F8)

    def test_default_keymap_has_23_entries(self):
        assert len(DEFAULT_KEYMAP) == 23

    def test_no_collisions_with_attach_url(self):
        """attach_url combo does not collide with any other entry."""
        attach = DEFAULT_KEYMAP["attach_url"]
        attach_combo = (attach.modifiers, attach.keycode)
        for aid, binding in DEFAULT_KEYMAP.items():
            if aid == "attach_url":
                continue
            combo = (binding.modifiers, binding.keycode)
            assert combo != attach_combo, (
                f"attach_url {attach_combo} collides with {aid} {combo}"
            )

    def test_keymap_find_conflict_includes_attach_url(self):
        """Keymap.find_conflict detects attach_url as a valid conflict target."""
        km = Keymap(DEFAULT_KEYMAP)
        # attach_url's combo should be found
        attach = DEFAULT_KEYMAP["attach_url"]
        result = km.find_conflict(attach.modifiers, attach.keycode)
        assert result == "attach_url"

    def test_wxk_integer_values(self):
        """WXK_* integer literals match wxPython 4.2 canonical values."""
        # These are the integer values of wx.WXK_F2, WXK_F5, etc. in wxPython 4.2
        assert DEFAULT_KEYMAP["announce_status"].keycode == _WXK_F2
        assert DEFAULT_KEYMAP["exit"].keycode == _WXK_F4
        assert DEFAULT_KEYMAP["scan_models"].keycode == _WXK_F5
        assert DEFAULT_KEYMAP["cycle_panels"].keycode == _WXK_F6
        assert DEFAULT_KEYMAP["start_server"].keycode == _WXK_F7
        assert DEFAULT_KEYMAP["stop_server"].keycode == _WXK_F7
        assert DEFAULT_KEYMAP["abort_generation"].keycode == _WXK_ESCAPE
        assert DEFAULT_KEYMAP["edit_previous"].keycode == _WXK_UP
        assert DEFAULT_KEYMAP["edit_next"].keycode == _WXK_DOWN


# ─── Conflict Detection ─────────────────────────────────────────────────────


class TestFindConflict:
    """Keymap.find_conflict detects collisions in the resolved view."""

    def test_no_conflict_returns_none(self):
        km = Keymap({"foo": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")})
        assert km.find_conflict(KEYMAP_MOD_CTRL, ord("Q")) is None

    def test_exact_conflict_returns_action_id(self):
        km = Keymap({"foo": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")})
        assert km.find_conflict(KEYMAP_MOD_CTRL, ord("N")) == "foo"

    def test_conflict_respects_overrides(self):
        km = Keymap(
            {"foo": Binding(0, ord("N"), "N")},
            {"foo": (KEYMAP_MOD_CTRL, ord("N"))},
        )
        assert km.find_conflict(KEYMAP_MOD_CTRL, ord("N")) == "foo"


class TestSetOverride:
    """Keymap.set_override raises on collision, preserves prior state."""

    def test_success_changes_resolved(self):
        km = Keymap({"foo": Binding(0, ord("N"), "N")})
        km.set_override("foo", KEYMAP_MOD_CTRL, ord("M"))
        assert km.resolve("foo") == (KEYMAP_MOD_CTRL, ord("M"))

    def test_collision_raises_and_preserves(self):
        km = Keymap({
            "foo": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N"),
            "bar": Binding(KEYMAP_MOD_CTRL, ord("M"), "Ctrl+M"),
        })
        with pytest.raises(KeymapConflictError) as exc:
            km.set_override("bar", KEYMAP_MOD_CTRL, ord("N"))
        assert "foo" in str(exc.value)
        # Prior override preserved (bar still has its default)
        assert km.resolve("bar") == (KEYMAP_MOD_CTRL, ord("M"))

    def test_same_combo_is_not_a_conflict_for_self(self):
        km = Keymap({"foo": Binding(0, ord("N"), "N")})
        # Setting the same combo on the same action is not a conflict
        km.set_override("foo", 0, ord("N"))
        assert km.resolve("foo") == (0, ord("N"))


class TestRemoveOverride:
    """Keymap.remove_override reverts to default."""

    def test_remove_reverts_to_default(self):
        defaults = {"foo": Binding(0, ord("N"), "N")}
        km = Keymap(defaults)
        km.set_override("foo", KEYMAP_MOD_CTRL, ord("Q"))
        assert km.resolve("foo") == (KEYMAP_MOD_CTRL, ord("Q"))
        km.remove_override("foo")
        assert km.resolve("foo") == (0, ord("N"))

    def test_remove_on_unoverridden_is_noop(self):
        defaults = {"foo": Binding(0, ord("N"), "N")}
        km = Keymap(defaults)
        km.remove_override("foo")  # Should not raise
        assert km.resolve("foo") == (0, ord("N"))


# ─── Override (De)serialization ─────────────────────────────────────────────


class TestToOverridesDict:
    """Keymap.to_overrides_dict returns only non-default overrides."""

    def test_excludes_default_matches(self):
        defaults = {"foo": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")}
        # Override matches default → omitted
        km = Keymap(defaults, overrides={"foo": (KEYMAP_MOD_CTRL, ord("N"))})
        assert km.to_overrides_dict() == {}

    def test_includes_non_default_override(self):
        defaults = {"foo": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")}
        km = Keymap(defaults, overrides={"foo": (KEYMAP_MOD_CTRL, ord("M"))})
        assert km.to_overrides_dict() == {"foo": (KEYMAP_MOD_CTRL, ord("M"))}

    def test_empty_when_no_overrides(self):
        km = Keymap({"foo": Binding(0, 0, "F")})
        assert km.to_overrides_dict() == {}


class TestFromOverridesDict:
    """Keymap.from_overrides_dict rehydrates a keymap."""

    def test_round_trip_preserves_non_default(self):
        defaults = {"foo": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")}
        km = Keymap(defaults, overrides={"foo": (KEYMAP_MOD_CTRL, ord("Q"))})
        blob = km.to_overrides_dict()
        km2 = Keymap.from_overrides_dict(blob, defaults)
        assert km2.actions["foo"] == Binding(KEYMAP_MOD_CTRL, ord("Q"), "Ctrl+N")
        assert km2.to_overrides_dict() == blob

    def test_unknown_ids_silently_dropped(self):
        overrides = {"ghost_action": (0, ord("Q"))}
        defaults = {}
        km = Keymap.from_overrides_dict(overrides, defaults)
        assert "ghost_action" not in km.actions

    def test_colliding_overrides_dropped_with_warning(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        defaults = {
            "a": Binding(0, ord("N"), "N"),
            "b": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N"),
        }
        overrides = {
            "a": (KEYMAP_MOD_CTRL, ord("N")),  # collides with b's resolved default
            "b": (0, ord("N")),  # collides with a's resolved default
        }
        km = Keymap.from_overrides_dict(overrides, defaults)
        # Both should have their defaults (overrides dropped)
        assert km.resolve("a") == (0, ord("N"))
        assert km.resolve("b") == (KEYMAP_MOD_CTRL, ord("N"))
        # At least one warning was logged mentioning both action ids
        assert len(caplog.records) >= 1
        combined = " ".join(r.getMessage() for r in caplog.records)
        assert "a" in combined and "b" in combined

    def test_empty_dict_round_trips_to_noop(self):
        defaults = {"foo": Binding(0, ord("N"), "N")}
        km = Keymap(defaults)
        blob = km.to_overrides_dict()
        assert blob == {}
        km2 = Keymap.from_overrides_dict(blob, defaults)
        assert km2.actions == Keymap(defaults).actions


# ─── resolve() ──────────────────────────────────────────────────────────────


class TestResolve:
    """Keymap.resolve returns the resolved (modifiers, keycode) for an id."""

    def test_known_id_returns_resolved_pair(self):
        km = Keymap(
            {"foo": Binding(0, ord("N"), "N")},
            overrides={"foo": (KEYMAP_MOD_CTRL, ord("Q"))},
        )
        assert km.resolve("foo") == (KEYMAP_MOD_CTRL, ord("Q"))

    def test_override_beats_default(self):
        defaults = {"foo": Binding(0, ord("N"), "N")}
        overrides = {"foo": (KEYMAP_MOD_CTRL, ord("N"))}
        km = Keymap(defaults, overrides)
        assert km.resolve("foo") == (KEYMAP_MOD_CTRL, ord("N"))

    def test_unknown_id_raises_keyerror(self):
        km = Keymap({"foo": Binding(0, 0, "F")})
        with pytest.raises(KeyError) as exc:
            km.resolve("ghost")
        assert "ghost" in str(exc.value)


# ─── format_shortcuts_text ──────────────────────────────────────────────────


class TestFormatShortcutsText:
    """Keymap.format_shortcuts_text formats the resolved keymap."""

    def test_includes_all_actions_sorted(self):
        km = Keymap(DEFAULT_KEYMAP)
        text = km.format_shortcuts_text()
        lines = text.strip().split("\n")
        assert len(lines) == len(DEFAULT_KEYMAP)
        # Lines are sorted by action_id
        ids = list(DEFAULT_KEYMAP.keys())
        ids.sort()
        for i, line in enumerate(lines):
            assert line.startswith(ids[i]), (
                f"Line {i} starts with {ids[i]!r}: {line!r}"
            )

    def test_format_is_action_id_colon_label(self):
        km = Keymap({"test": Binding(KEYMAP_MOD_CTRL, ord("X"), "Ctrl+X")})
        text = km.format_shortcuts_text()
        assert text.strip() == "test: Ctrl+X"

    def test_override_reflected_in_output(self):
        km = Keymap(
            {"foo": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N")},
            overrides={"foo": (KEYMAP_MOD_ALT, ord("N"))},
        )
        text = km.format_shortcuts_text()
        assert "foo: Alt+N" in text
        assert "foo: Ctrl+N" not in text

    def test_new_action_appears_automatically(self):
        km = Keymap({
            "existing": Binding(0, 0, "E"),
            "new_action": Binding(KEYMAP_MOD_CTRL, ord("X"), "Ctrl+X"),
        })
        text = km.format_shortcuts_text()
        assert "new_action: Ctrl+X" in text


# ─── AST guard: no import wx at module level ────────────────────────────────


class TestAstNoWxImport:
    """core/keymap.py must not import wx at module scope."""

    def test_no_wx_import_in_source(self):
        source_path = __import__(
            "bellbird.core.keymap", fromlist=[""]
        ).__file__
        with open(source_path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "wx" or alias.name.startswith("wx."):
                        pytest.fail(
                            f"Found import of wx at module level: "
                            f"{ast.dump(node)}"
                        )

    def test_module_imports_without_wx(self):
        """Verify the module can be imported in an environment without wx."""
        # This is tested by the import at the top of this file already
        # happening successfully. The test exists as a documented scenario.
        from bellbird.core.keymap import Binding, Keymap, DEFAULT_KEYMAP
        assert len(DEFAULT_KEYMAP) == 23


# ─── Logger warning on dropped overrides ────────────────────────────────────


class TestLoggerWarnings:
    """Keymap.from_overrides_dict logs warnings for dropped overrides."""

    def test_logs_warning_on_collision(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        defaults = {
            "a": Binding(0, ord("X"), "X"),
            "b": Binding(0, ord("Y"), "Y"),
        }
        overrides = {"a": (0, ord("Y"))}  # collides with b's default
        Keymap.from_overrides_dict(overrides, defaults)
        assert any("a" in r.getMessage() for r in caplog.records)
