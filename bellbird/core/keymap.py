"""Keymap data model — wx-free, testable on WSL.

Defines the single source of truth for keyboard shortcuts: a ``Keymap``
value object, the ``DEFAULT_KEYMAP`` table, conflict detection, override
(de)serialization, and a formatting helper for the shortcuts dialog.

The data model lives in ``core/`` so it is importable without wxPython;
the translation to ``wx.AcceleratorEntry`` happens in ``ui/main_window.py``.
"""

import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ─── Module-level modifiers constants ─────────────────────────────────────────
# These match wx.ACCEL_* but as plain ints so core/ stays wx-free.
# wx.ACCEL_NORMAL = 0, wx.ACCEL_CTRL = 1, wx.ACCEL_SHIFT = 2, wx.ACCEL_ALT = 4

KEYMAP_MOD_NONE: int = 0
KEYMAP_MOD_CTRL: int = 1
KEYMAP_MOD_SHIFT: int = 2
KEYMAP_MOD_ALT: int = 4

# wx.WXK_* integer literals for core/ (no wx import at module level)
_WXK_F4 = 342
_WXK_F2 = 340
_WXK_F5 = 343
_WXK_F6 = 344
_WXK_F7 = 345
_WXK_F8 = 346
_WXK_ESCAPE = 27
_WXK_UP = 315
_WXK_DOWN = 317

# Lookup from keycode to display name
_KEYCODE_LABELS: dict[int, str] = {
    _WXK_F2: "F2",
    _WXK_F4: "F4",
    _WXK_F5: "F5",
    _WXK_F6: "F6",
    _WXK_F7: "F7",
    _WXK_F8: "F8",
    _WXK_ESCAPE: "Escape",
    _WXK_UP: "Up",
    _WXK_DOWN: "Down",
    ord(","): ",",
}


def _format_combo(modifiers: int, keycode: int) -> str:
    """Build a human-readable shortcut string from a raw combo.

    E.g. ``(KEYMAP_MOD_CTRL | KEYMAP_MOD_SHIFT, ord("C"))`` → ``"Ctrl+Shift+C"``.
    """
    parts: list[str] = []
    if modifiers & KEYMAP_MOD_CTRL:
        parts.append("Ctrl")
    if modifiers & KEYMAP_MOD_SHIFT:
        parts.append("Shift")
    if modifiers & KEYMAP_MOD_ALT:
        parts.append("Alt")

    if keycode in _KEYCODE_LABELS:
        key_str = _KEYCODE_LABELS[keycode]
    elif 32 <= keycode < 127:
        key_str = chr(keycode)
    else:
        key_str = str(keycode)

    if parts:
        return "+".join(parts) + "+" + key_str
    return key_str


# ─── Binding dataclass ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Binding:
    """A single keyboard shortcut binding.

    Attributes:
        modifiers: Bitmask of KEYMAP_MOD_* constants.
        keycode: Virtual key code (e.g. ``ord("N")``, ``wx.WXK_F5``).
        label: Spanish-readable string (e.g. ``"Ctrl+Shift+C"``).
    """

    modifiers: int
    keycode: int
    label: str


# ─── Conflict error ───────────────────────────────────────────────────────────


class KeymapConflictError(ValueError):
    """Raised when ``set_override`` would create a binding collision."""


# ─── Main Keymap class ────────────────────────────────────────────────────────


class Keymap:
    """Resolved keymap: merges defaults with overrides.

    Args:
        defaults: Dict of action_id → Binding for the built-in defaults.
        overrides: Optional dict of action_id → (modifiers, keycode) from
            user preferences. Unknown ids and colliding pairs are silently
            dropped (with a ``logger.warning`` for collisions at load time).
    """

    def __init__(
        self,
        defaults: dict[str, Binding],
        overrides: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        self._defaults: dict[str, Binding] = deepcopy(defaults)
        self._overrides: dict[str, tuple[int, int]] = {}

        if overrides:
            # First pass: build a tentative map of resolved combos from defaults
            resolved_combos: dict[tuple[int, int], str] = {}
            for aid, binding in self._defaults.items():
                key = (binding.modifiers, binding.keycode)
                resolved_combos[key] = aid

            for aid, combo in overrides.items():
                if aid not in self._defaults:
                    # Unknown action id — silently ignore
                    continue
                # Check collision against currently resolved combos
                if combo in resolved_combos and resolved_combos[combo] != aid:
                    logger.warning(
                        "Override collision: %s (%d, %d) collides with %s "
                        "- dropping override for %s",
                        aid, combo[0], combo[1],
                        resolved_combos[combo], aid,
                    )
                    continue
                # Update resolved combo map
                old_combo = (
                    self._defaults[aid].modifiers,
                    self._defaults[aid].keycode,
                )
                if old_combo in resolved_combos and resolved_combos[old_combo] == aid:
                    del resolved_combos[old_combo]
                resolved_combos[combo] = aid
                self._overrides[aid] = combo

    @property
    def actions(self) -> dict[str, Binding]:
        """Resolved view: defaults merged with overrides (overrides win).

        Returns a copy so mutation does not affect the underlying state.
        """
        result = deepcopy(self._defaults)
        for aid, (modifiers, keycode) in self._overrides.items():
            if aid in result:
                # Preserve label from default
                result[aid] = Binding(
                    modifiers=modifiers,
                    keycode=keycode,
                    label=result[aid].label,
                )
        return result

    def resolve(self, action_id: str) -> tuple[int, int]:
        """Return the ``(modifiers, keycode)`` for an action id.

        Raises:
            KeyError: If ``action_id`` is not in the resolved actions.
        """
        if action_id not in self._defaults:
            raise KeyError(f"Unknown action id: {action_id}")
        if action_id in self._overrides:
            return self._overrides[action_id]
        b = self._defaults[action_id]
        return (b.modifiers, b.keycode)

    # ── Conflict Detection ───────────────────────────────────────────────────

    def find_conflict(self, modifiers: int, keycode: int) -> str | None:
        """Return the action_id bound to ``(modifiers, keycode)`` or ``None``."""
        resolved = self.actions
        target = (modifiers, keycode)
        for aid, binding in resolved.items():
            if (binding.modifiers, binding.keycode) == target:
                return aid
        return None

    def set_override(self, action_id: str, modifiers: int, keycode: int) -> None:
        """Set an override, raising ``KeymapConflictError`` on collision.

        The check excludes ``action_id`` itself (re-binding the same combo
        is not a conflict). On error, the prior override is preserved.
        """
        resolved = self.actions
        target = (modifiers, keycode)
        for aid, binding in resolved.items():
            if aid == action_id:
                continue
            if (binding.modifiers, binding.keycode) == target:
                raise KeymapConflictError(
                    f"Conflict: {action_id} -> ({modifiers}, {keycode}) "
                    f"collides with {aid}"
                )
        self._overrides[action_id] = (modifiers, keycode)

    def remove_override(self, action_id: str) -> None:
        """Drop the override for ``action_id``, reverting to default.

        No-op if no override exists for that action.
        """
        self._overrides.pop(action_id, None)

    # ── Serialization ────────────────────────────────────────────────────────

    def to_overrides_dict(self) -> dict[str, tuple[int, int]]:
        """Return only overrides that differ from their defaults.

        Entries matching the default are omitted (no-op round-trip).
        """
        result: dict[str, tuple[int, int]] = {}
        for aid, combo in self._overrides.items():
            if aid in self._defaults:
                default = self._defaults[aid]
                if (default.modifiers, default.keycode) != combo:
                    result[aid] = combo
        return result

    @classmethod
    def from_overrides_dict(
        cls,
        overrides: dict[str, tuple[int, int]],
        defaults: dict[str, Binding],
    ) -> "Keymap":
        """Rehydrate a Keymap from an overrides dict.

        Unknown action ids are silently ignored. Colliding overrides are
        dropped with a ``logger.warning``.
        """
        return cls(defaults=defaults, overrides=overrides)

    # ── Formatting helpers ───────────────────────────────────────────────────

    def format_shortcuts_text(self) -> str:
        """Format the resolved keymap as a human-readable string.

        Returns one ``action_id: <combo>`` line per action, sorted by
        action_id for deterministic output. The combo string is computed
        from the resolved ``(modifiers, keycode)`` (it may differ from
        the default ``Binding.label`` when an override is active).

        The caller (``ui/main_window.py``) copies this text into a
        ``wx.TextCtrl`` for the shortcuts dialog.
        """
        resolved = self.actions
        lines: list[str] = []
        for aid in sorted(resolved.keys()):
            binding = resolved[aid]
            combo_str = _format_combo(binding.modifiers, binding.keycode)
            lines.append(f"{aid}: {combo_str}")
        return "\n".join(lines) + "\n"


# ─── DEFAULT_KEYMAP — single source of truth for all keyboard shortcuts ───────


DEFAULT_KEYMAP: dict[str, Binding] = {
    "new_conversation": Binding(KEYMAP_MOD_CTRL, ord("N"), "Ctrl+N"),
    "open_conversation": Binding(KEYMAP_MOD_CTRL, ord("O"), "Ctrl+O"),
    "save_conversation": Binding(KEYMAP_MOD_CTRL, ord("S"), "Ctrl+S"),
    "preferences": Binding(KEYMAP_MOD_CTRL, ord(","), "Ctrl+,"),
    "exit": Binding(KEYMAP_MOD_ALT, 342, "Alt+F4"),  # wx.WXK_F4
    "announce_status": Binding(KEYMAP_MOD_NONE, 340, "F2"),  # wx.WXK_F2
    "scan_models": Binding(KEYMAP_MOD_NONE, 343, "F5"),  # wx.WXK_F5
    "cycle_panels": Binding(KEYMAP_MOD_NONE, 344, "F6"),  # wx.WXK_F6
    "start_server": Binding(KEYMAP_MOD_NONE, 345, "F7"),  # wx.WXK_F7
    "stop_server": Binding(KEYMAP_MOD_CTRL, 345, "Ctrl+F7"),  # wx.WXK_F7
    "abort_generation": Binding(KEYMAP_MOD_NONE, 27, "Escape"),  # wx.WXK_ESCAPE
    "focus_chat": Binding(KEYMAP_MOD_ALT, ord("1"), "Alt+1"),
    "focus_params": Binding(KEYMAP_MOD_ALT, ord("2"), "Alt+2"),
    "focus_models": Binding(KEYMAP_MOD_ALT, ord("3"), "Alt+3"),
    "focus_server": Binding(KEYMAP_MOD_ALT, ord("6"), "Alt+6"),
    "copy_last": Binding(KEYMAP_MOD_CTRL | KEYMAP_MOD_SHIFT, ord("C"), "Ctrl+Shift+C"),
    "delete_last_exchange": Binding(KEYMAP_MOD_CTRL, ord("K"), "Ctrl+K"),
    "edit_previous": Binding(KEYMAP_MOD_ALT, 315, "Alt+Up"),  # wx.WXK_UP
    "edit_next": Binding(KEYMAP_MOD_ALT, 317, "Alt+Down"),  # wx.WXK_DOWN
    "regenerate": Binding(KEYMAP_MOD_CTRL, ord("R"), "Ctrl+R"),
    "find_in_history": Binding(KEYMAP_MOD_CTRL, ord("F"), "Ctrl+F"),
    "attach_url": Binding(KEYMAP_MOD_CTRL, ord("U"), "Ctrl+U"),
    "read_selected_message": Binding(KEYMAP_MOD_NONE, _WXK_F8, "F8"),
}
