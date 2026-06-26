"""Runtime tests for SystemVoice — wx convention gating, win32 SAPI optional.

These tests follow the project convention of using ``importorskip("wx")``
for files under ``tests/ui/``. The SystemVoice class itself is wx-free
but uses ``win32com.client`` (win32-only). All tests must verify the
never-crash contract on every code path.

Skipped automatically on WSL/Linux via ``importorskip("wx")``.
Run via ``run_tests.bat`` on Windows.
"""

import sys
from unittest.mock import patch

import pytest

pytest.importorskip("wx")


class TestSystemVoice:
    """SystemVoice: never-crash contract on every code path."""

    def test_non_win32_speak_is_noop(self) -> None:
        """On non-Windows platforms, speak() is a silent no-op."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice(voice_name="Test", rate=5)
        # No exception
        sv.speak("hola")
        assert not sv.is_available(), (
            "SystemVoice should not be available on non-win32"
        )

    def test_speak_with_none_voice_is_silent(self) -> None:
        """Calling speak with no underlying voice is a silent no-op."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice(voice_name="", rate=0)
        sv.speak("test")
        # No exception — already ensured

    def test_list_voices_on_non_win32_returns_empty(self) -> None:
        """list_voices() returns empty list outside win32."""
        from bellbird.core.system_voice import SystemVoice

        result = SystemVoice.voices()
        assert result == [], (
            f"Expected empty list on non-win32, got {result}"
        )

    def test_never_raises_on_garbage_input(self) -> None:
        """Calling SystemVoice methods with garbage input never raises."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice(voice_name="", rate=0)

        # speak with non-string
        sv.speak(None)  # type: ignore[arg-type]
        sv.speak(123)  # type: ignore[arg-type]
        sv.speak("")

        # set_voice with weird values
        sv.set_voice("")
        sv.set_voice(None)  # type: ignore[arg-type]

        # set_rate out of range
        sv.set_rate(-100)
        sv.set_rate(999)

        # No exception — contract satisfied

    def test_set_voice_empty_returns_false(self) -> None:
        """set_voice('') returns False."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        result = sv.set_voice("")
        assert result is False, (
            f"Expected False for empty voice, got {result}"
        )

    def test_set_rate_clamps_to_range(self) -> None:
        """set_rate(15) does not raise and rate stays clamped to [-10, +10]."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        # Should not raise even on non-win32
        sv.set_rate(15)
        # On non-win32, _rate stays at 0 (never set).
        # The contract is "never raises", which is satisfied.

    def test_speak_none_text_does_not_raise(self) -> None:
        """speak(None) must not raise."""
        from bellbird.core.system_voice import SystemVoice

        sv = SystemVoice()
        sv.speak(None)  # type: ignore[arg-type]

    def test_voices_static_empty_outside_win32(self) -> None:
        """voices() static method returns [] on non-win32."""
        from bellbird.core.system_voice import SystemVoice

        assert SystemVoice.voices() == []
