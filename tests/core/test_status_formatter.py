"""Tests for bellbird.core.status_formatter — strict TDD, wx-free.

Covers SessionSnapshot frozen dataclass, DEFAULT_STATUS_TOGGLES,
and format_status pure function with all toggles, modes, and
degradation patterns.
"""

import dataclasses
from typing import Any

import pytest

from bellbird.core.status_formatter import (
    SessionSnapshot,
    DEFAULT_STATUS_TOGGLES,
    format_status,
)


# ─── SessionSnapshot (T-WU1-07) — 4 cases ─────────────────────────────────────


class TestSessionSnapshot:
    """Tests for SessionSnapshot frozen dataclass."""

    def test_frozen_mutation_raises(self):
        """GIVEN a fully populated SessionSnapshot
        WHEN a field is mutated
        THEN dataclasses.FrozenInstanceError is raised."""
        snap = SessionSnapshot(
            model_name="llama-3.1-8b",
            n_ctx=4096,
            prompt_tokens=50,
            completion_tokens=100,
            progress_tokens=None,
            last_tok_per_s=18.4,
            server_state="ready",
            vram_free_mb=8192,
            vram_total_mb=12288,
            fit_status="fits",
            message_count=5,
            temperature=0.7,
            top_p=0.9,
            max_tokens=4096,
            is_generating=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            snap.is_generating = True

    def test_default_set_has_11_names(self):
        """GIVEN DEFAULT_STATUS_TOGGLES
        THEN it is a tuple of 11 strings."""
        assert isinstance(DEFAULT_STATUS_TOGGLES, tuple)
        assert len(DEFAULT_STATUS_TOGGLES) == 11
        expected = [
            "model_name", "context_pct", "max_tokens", "server",
            "vram", "fit", "message_count", "temperature", "top_p",
            "tok_per_s", "is_generating",
        ]
        assert list(DEFAULT_STATUS_TOGGLES) == expected

    def test_ordering_stable(self):
        """GIVEN DEFAULT_STATUS_TOGGLES
        THEN order matches the spec and is deterministic."""
        assert DEFAULT_STATUS_TOGGLES[0] == "model_name"
        assert DEFAULT_STATUS_TOGGLES[-1] == "is_generating"

    def test_all_none_data_constructible(self):
        """GIVEN SessionSnapshot with all-None fields where allowed
        THEN the instance is constructible."""
        snap = SessionSnapshot(
            model_name="",
            n_ctx=None,
            prompt_tokens=None,
            completion_tokens=None,
            progress_tokens=None,
            last_tok_per_s=None,
            server_state="dead",
            vram_free_mb=None,
            vram_total_mb=None,
            fit_status=None,
            message_count=0,
            temperature=0.0,
            top_p=0.0,
            max_tokens=0,
            is_generating=False,
        )
        assert snap.model_name == ""
        assert snap.n_ctx is None
        assert snap.message_count == 0


# ─── Determinism + purity (T-WU1-08 subset) ─────────────────────────────────-


class TestFormatStatusDeterminism:
    """Tests for format_status determinism and purity."""

    def test_byte_identical_output(self):
        """GIVEN identical inputs twice
        WHEN format_status is called
        THEN outputs are byte-equal."""
        snap = _make_full_snapshot()
        toggles = set(DEFAULT_STATUS_TOGGLES)
        a = format_status(snap, toggles, "short")
        b = format_status(snap, toggles, "short")
        assert a == b
        assert isinstance(a, str)

    def test_pure_no_wx_speech_or_logging(self):
        """GIVEN the source of status_formatter.py
        WHEN AST-inspected
        THEN there is no 'import wx', no 'speech.', and no 'logging.'
        at module level."""
        import pathlib
        src = (
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "bellbird/core/status_formatter.py"
        ).read_text(encoding="utf-8")
        assert "import wx" not in src, "status_formatter must NOT import wx"
        assert "speech." not in src, "status_formatter must NOT reference speech"
        assert "logging." not in src, "status_formatter must NOT reference logging"
        assert "time." not in src, "status_formatter must NOT reference time"

    def test_empty_toggles_returns_empty(self):
        """GIVEN toggles=set()
        WHEN format_status runs
        THEN returns ''."""
        snap = _make_full_snapshot()
        result = format_status(snap, set(), "short")
        assert result == ""


# ─── Individual toggle tests (DEFAULT_STATUS_TOGGLES × 11 + extras) ──────────


def _make_full_snapshot() -> SessionSnapshot:
    """Create a fully-populated SessionSnapshot for testing."""
    return SessionSnapshot(
        model_name="llama-3.1-8b",
        n_ctx=4096,
        prompt_tokens=50,
        completion_tokens=100,
        progress_tokens=None,
        last_tok_per_s=18.4,
        server_state="ready",
        vram_free_mb=8192,
        vram_total_mb=12288,
        fit_status="fits",
        message_count=5,
        temperature=0.7,
        top_p=0.9,
        max_tokens=4096,
        is_generating=False,
    )


class TestFormatStatusToggles:
    """One test per toggle verifying ON produces substring, OFF omits it."""

    SNAP = _make_full_snapshot()

    def test_model_name_on(self):
        result = format_status(self.SNAP, {"model_name"}, "short")
        assert "llama" in result

    def test_model_name_off(self):
        result = format_status(self.SNAP, set(), "short")
        assert "llama" not in result

    def test_context_pct_on(self):
        result = format_status(self.SNAP, {"context_pct"}, "short")
        assert "%" in result or "contexto" in result.lower()

    def test_max_tokens_on(self):
        result = format_status(self.SNAP, {"max_tokens"}, "short")
        assert "4096" in result

    def test_server_on(self):
        result = format_status(self.SNAP, {"server"}, "short")
        assert "servidor" in result.lower() or "ready" in result.lower()

    def test_vram_on(self):
        result = format_status(self.SNAP, {"vram"}, "short")
        assert "VRAM" in result

    def test_fit_on(self):
        result = format_status(self.SNAP, {"fit"}, "short")
        assert "fits" in result or "encaje" in result.lower()

    def test_message_count_on(self):
        result = format_status(self.SNAP, {"message_count"}, "short")
        assert "5" in result

    def test_temperature_on(self):
        result = format_status(self.SNAP, {"temperature"}, "short")
        assert "Temperatura" in result
        assert "0,70" in result

    def test_top_p_on(self):
        result = format_status(self.SNAP, {"top_p"}, "short")
        assert "Top P" in result or "0,90" in result

    def test_tok_per_s_on(self):
        result = format_status(self.SNAP, {"tok_per_s"}, "short")
        assert "18" in result

    def test_is_generating_on(self):
        """When is_generating=True, the toggle produces a substring."""
        gen_snap = dataclasses.replace(self.SNAP, is_generating=True)
        result = format_status(gen_snap, {"is_generating"}, "short")
        assert "generando" in result.lower()

    def test_unknown_toggle_ignored(self):
        result = format_status(self.SNAP, {"model_name", "ghost_toggle"}, "short")
        assert "llama" in result
        assert "ghost" not in result


# ─── Short mode ───────────────────────────────────────────────────────────────


class TestFormatStatusShortMode:
    """Tests for mode='short'."""

    def test_short_is_one_sentence(self):
        """GIVEN all toggles ON and full snapshot
        WHEN mode='short'
        THEN result ends with '.' and components are '; '-separated."""
        snap = _make_full_snapshot()
        toggles = set(DEFAULT_STATUS_TOGGLES)
        result = format_status(snap, toggles, "short")
        assert result.endswith(".")
        assert "; " in result

    def test_short_uses_semicolon_separator(self):
        snap = _make_full_snapshot()
        result = format_status(snap, {"model_name", "temperature"}, "short")
        assert "; " in result

    def test_none_data_omits_component(self):
        """GIVEN vram data is None
        WHEN 'vram' toggle is ON
        THEN component is omitted."""
        snap = dataclasses.replace(
            _make_full_snapshot(),
            vram_free_mb=None,
            vram_total_mb=None,
        )
        result = format_status(snap, {"vram"}, "short")
        assert result == ""

    def test_n_ctx_none_omits_context_pct(self):
        snap = dataclasses.replace(_make_full_snapshot(), n_ctx=None)
        result = format_status(snap, {"context_pct"}, "short")
        assert result == ""


# ─── Long mode ────────────────────────────────────────────────────────────────


class TestFormatStatusLongMode:
    """Tests for mode='long'."""

    def test_long_has_newline_separators(self):
        snap = _make_full_snapshot()
        toggles = set(DEFAULT_STATUS_TOGGLES)
        result = format_status(snap, toggles, "long")
        assert "\n" in result

    def test_long_has_multiple_components(self):
        snap = _make_full_snapshot()
        result = format_status(snap, {"model_name", "server", "temperature"}, "long")
        # Each component is on its own line
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) >= 2


# ─── Mid-generation behavior ──────────────────────────────────────────────────


class TestFormatStatusMidGen:
    """Tests for is_generating=True behavior."""

    def test_progress_tokens_drives_percentage(self):
        """GIVEN is_generating=True, progress_tokens=1200, n_ctx=4096
        WHEN format_status runs
        THEN percentage uses progress_tokens, not completion_tokens."""
        snap = dataclasses.replace(
            _make_full_snapshot(),
            is_generating=True,
            n_ctx=4096,
            progress_tokens=1200,
            completion_tokens=80,  # stale small value
        )
        result = format_status(snap, {"context_pct"}, "short")
        # 1200/4096 = 29%, should NOT contain "80"
        assert "29" in result
        assert "80" not in result

    def test_mid_gen_starts_with_generando(self):
        snap = dataclasses.replace(
            _make_full_snapshot(),
            is_generating=True,
            progress_tokens=500,
            n_ctx=4096,
        )
        result = format_status(snap, {"context_pct"}, "short")
        assert result.startswith("Generando:")

    def test_tok_per_s_during_generation(self):
        snap = dataclasses.replace(
            _make_full_snapshot(),
            is_generating=True,
            last_tok_per_s=18.4,
        )
        result = format_status(snap, {"tok_per_s"}, "short")
        assert "18" in result


# ─── End of tests ─────────────────────────────────────────────────────────────
