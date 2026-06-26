"""Tests for bellbird.core.system_voice — strict TDD, RED first, then GREEN.

Covers: no-op outside win32, missing win32com, voices list, set_voice
validation, set_rate clamp, speak delegation, never-crash contract.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


# ─── Helper to fake win32com for testability ────────────────────────────────


def _ensure_win32com_present():
    """Ensure win32com is available in sys.modules for patching."""
    if "win32com" not in sys.modules:
        import types

        win32com_mod = types.ModuleType("win32com")
        client_mod = types.ModuleType("win32com.client")
        client_mod.Dispatch = MagicMock()  # placeholder, overridden per test
        win32com_mod.client = client_mod
        sys.modules["win32com"] = win32com_mod
        sys.modules["win32com.client"] = client_mod


# ─── Fixture ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def ensure_win32com():
    """Ensure win32com fakes are present for every test."""
    _ensure_win32com_present()
    yield


class TestSystemVoice:
    """SystemVoice platform guards and no-ops."""

    def test_voices_non_win32_returns_empty(self):
        """GIVEN sys.platform != 'win32'
        WHEN SystemVoice.voices() is called
        THEN the result is []."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "linux"):
            result = sv.voices()
            assert result == []

    def test_voices_win32_missing_win32com_returns_empty(self):
        """GIVEN sys.platform == 'win32' and win32com raises ImportError
        WHEN SystemVoice.voices() is called
        THEN the result is []."""
        from bellbird.core.system_voice import SystemVoice

        # Simulate import error by patching builtins.__import__
        import builtins

        real_import = builtins.__import__

        def _block_win32com(name, *args, **kwargs):
            if "win32com" in name:
                raise ImportError(f"blocked: {name}")
            return real_import(name, *args, **kwargs)

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            with patch("builtins.__import__", side_effect=_block_win32com):
                result = sv.voices()
                assert result == []

    def test_voices_win32_with_voices(self):
        """GIVEN sys.platform == 'win32' with stubbed Dispatch returning voices
        WHEN SystemVoice.voices() is called
        THEN returns the voice names."""
        from bellbird.core.system_voice import SystemVoice

        # Create fake voice objects with GetDescription
        voice_a = MagicMock()
        voice_a.GetDescription.return_value = "Microsoft Helena"
        voice_b = MagicMock()
        voice_b.GetDescription.return_value = "Microsoft Sabina"

        fake_voices = MagicMock()
        fake_voices.__iter__.return_value = [voice_a, voice_b]

        fake_dispatch = MagicMock()
        fake_dispatch.GetVoices.return_value = fake_voices

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            with patch("win32com.client.Dispatch", return_value=fake_dispatch):
                result = sv.voices()
                assert result == ["Microsoft Helena", "Microsoft Sabina"]

    def test_voices_never_raises(self):
        """GIVEN any platform state
        WHEN SystemVoice.voices() is called
        THEN no exception propagates."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            with patch(
                "win32com.client.Dispatch",
                side_effect=RuntimeError("COM failure"),
            ):
                result = sv.voices()
                assert result == []

    # ── set_voice ──────────────────────────────────────────────────────────

    def test_set_voice_non_win32_returns_false(self):
        """GIVEN sys.platform != 'win32'
        WHEN set_voice is called
        THEN returns False."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "linux"):
            assert sv.set_voice("Helena") is False

    def test_set_voice_empty_returns_false(self):
        """GIVEN any SystemVoice
        WHEN set_voice("") is called
        THEN returns False."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        assert sv.set_voice("") is False

    def test_set_voice_success(self):
        """GIVEN a SystemVoice on win32 with voices
        WHEN set_voice with a valid name
        THEN returns True."""
        from bellbird.core.system_voice import SystemVoice

        fake_voice = MagicMock()
        fake_voice.GetDescription.return_value = "Helena"
        fake_voices_iter = MagicMock()
        fake_voices_iter.__iter__.return_value = [fake_voice]

        fake_dispatch = MagicMock()
        fake_dispatch.GetVoices.return_value = fake_voices_iter

        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            with patch("win32com.client.Dispatch", return_value=fake_dispatch):
                sv = SystemVoice()
                result = sv.set_voice("Helena")
                assert result is True

    def test_set_voice_unknown_returns_false(self):
        """GIVEN a SystemVoice with known voices
        WHEN set_voice with an unknown name
        THEN returns False and previous voice unchanged."""
        from bellbird.core.system_voice import SystemVoice

        fake_voice = MagicMock()
        fake_voice.GetDescription.return_value = "Helena"
        fake_voices_iter = MagicMock()
        fake_voices_iter.__iter__.return_value = [fake_voice]

        fake_dispatch = MagicMock()
        fake_dispatch.GetVoices.return_value = fake_voices_iter

        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            with patch("win32com.client.Dispatch", return_value=fake_dispatch):
                sv = SystemVoice()
                sv.set_voice("Helena")
                result = sv.set_voice("nonexistent")
                assert result is False

    def test_set_voice_never_raises(self):
        """GIVEN any failure mode
        WHEN set_voice is called
        THEN no exception propagates."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            with patch(
                "win32com.client.Dispatch",
                side_effect=RuntimeError("fail"),
            ):
                result = sv.set_voice("Helena")
                assert result is False

    # ── set_rate ───────────────────────────────────────────────────────────

    def test_set_rate_clamps_below(self):
        """GIVEN a SystemVoice on win32
        WHEN set_rate(-20) is called
        THEN the effective rate is -10."""
        from bellbird.core.system_voice import SystemVoice

        fake_dispatch = MagicMock()
        sv = SystemVoice()
        sv._voice = fake_dispatch  # Simulate win32 connection
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            sv.set_rate(-20)
            assert fake_dispatch.Rate == -10

    def test_set_rate_clamps_above(self):
        """GIVEN a SystemVoice on win32
        WHEN set_rate(50) is called
        THEN the effective rate is 10."""
        from bellbird.core.system_voice import SystemVoice

        fake_dispatch = MagicMock()
        sv = SystemVoice()
        sv._voice = fake_dispatch
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            sv.set_rate(50)
            assert fake_dispatch.Rate == 10

    def test_set_rate_in_range(self):
        """GIVEN a SystemVoice on win32
        WHEN set_rate(2) is called
        THEN the effective rate is 2."""
        from bellbird.core.system_voice import SystemVoice

        fake_dispatch = MagicMock()
        sv = SystemVoice()
        sv._voice = fake_dispatch
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            sv.set_rate(2)
            assert fake_dispatch.Rate == 2

    def test_set_rate_non_win32_noop(self):
        """GIVEN sys.platform != 'win32'
        WHEN set_rate is called
        THEN no exception propagates."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "linux"):
            sv.set_rate(2)  # must not raise

    def test_set_rate_never_raises(self):
        """GIVEN dispatch raises
        WHEN set_rate is called
        THEN no exception propagates."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        sv._voice = MagicMock()
        sv._voice.Rate = "invalid"  # not int, setting may fail
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            try:
                sv.set_rate(2)
            except Exception:
                pytest.fail("set_rate raised unexpectedly")

    # ── speak ──────────────────────────────────────────────────────────────

    def test_speak_non_win32_noop(self):
        """GIVEN sys.platform != 'win32'
        WHEN speak is called
        THEN no exception and no SAPI call."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "linux"):
            sv.speak("hola")  # must not raise

    def test_speak_with_empty_text(self):
        """GIVEN any SystemVoice
        WHEN speak("") is called
        THEN no exception."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        sv.speak("")  # must not raise

    def test_speak_with_non_string(self):
        """GIVEN any SystemVoice
        WHEN speak(None) is called
        THEN no exception."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        sv.speak(None)  # must not raise

    def test_speak_calls_sapi_on_win32(self):
        """GIVEN a SystemVoice on win32 with stubbed Dispatch
        WHEN speak("hola") is called
        THEN Speak is called with SVSFlagsAsync (1)."""
        from bellbird.core.system_voice import SystemVoice

        fake_dispatch = MagicMock()
        sv = SystemVoice()
        sv._voice = fake_dispatch
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            sv.speak("hola")
            fake_dispatch.Speak.assert_called_once_with("hola", 1)

    def test_speak_swallows_sapi_error(self):
        """GIVEN Speak raises OSError
        WHEN speak is called
        THEN no exception propagates."""
        from bellbird.core.system_voice import SystemVoice

        fake_dispatch = MagicMock()
        fake_dispatch.Speak.side_effect = OSError("COM error")
        sv = SystemVoice()
        sv._voice = fake_dispatch
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            sv.speak("hola")  # must not raise

    def test_speak_never_raises(self):
        """GIVEN any failure mode
        WHEN speak is called
        THEN no exception propagates."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            # Remove win32com from sys.modules so import raises
            saved = sys.modules.pop("win32com", None)
            saved_client = sys.modules.pop("win32com.client", None)
            try:
                import builtins

                real_import = builtins.__import__

                def _block_win32com(name, *args, **kwargs):
                    if "win32com" in name:
                        raise ImportError(f"blocked: {name}")
                    return real_import(name, *args, **kwargs)

                with patch("builtins.__import__", side_effect=_block_win32com):
                    sv.speak("hola")  # must not raise
            finally:
                if saved:
                    sys.modules["win32com"] = saved
                if saved_client:
                    sys.modules["win32com.client"] = saved_client

    # ── is_available ───────────────────────────────────────────────────────

    def test_is_available_non_win32_false(self):
        """GIVEN sys.platform != 'win32'
        WHEN is_available() is called
        THEN returns False."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        with patch("bellbird.core.system_voice.sys.platform", "linux"):
            assert sv.is_available() is False

    def test_is_available_win32_true(self):
        """GIVEN sys.platform == 'win32' and voice is set
        WHEN is_available() is called
        THEN returns True."""
        from bellbird.core.system_voice import SystemVoice

        fake_dispatch = MagicMock()
        sv = SystemVoice()
        sv._voice = fake_dispatch
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            assert sv.is_available() is True

    def test_is_available_no_voice_false(self):
        """GIVEN SystemVoice with _voice is None
        WHEN is_available() is called
        THEN returns False."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        sv._voice = None
        with patch("bellbird.core.system_voice.sys.platform", "win32"):
            assert sv.is_available() is False

    # ── AST guard: no wx import at module scope ────────────────────────────

    def test_no_wx_import_in_source(self):
        """GIVEN the source of system_voice.py
        WHEN AST is inspected
        THEN no 'import wx' or 'from wx' at module scope."""
        import ast

        import bellbird.core.system_voice as mod

        source_path = mod.__file__
        with open(source_path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "wx" or alias.name.startswith("wx."):
                        pytest.fail(
                            f"Found import of wx at module scope: {ast.dump(node)}"
                        )
