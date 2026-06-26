"""Tests for Speech module — strict TDD, RED first, then GREEN."""

import sys
from unittest.mock import Mock, patch

import pytest


# ─── Helper to reload speech module ──────────────────────────────────────────


def _reload_speech():
    """Remove speech from sys.modules so it re-imports on next access."""
    for mod in list(sys.modules.keys()):
        if "bellbird.core.speech" in mod or "bellbird" in mod:
            del sys.modules[mod]


def _ensure_accessible_output2_present():
    """Ensure accessible_output2 is available in sys.modules for patching."""
    if "accessible_output2" not in sys.modules:
        # Create a fake module structure
        import types

        a2_mod = types.ModuleType("accessible_output2")
        outputs_mod = types.ModuleType("accessible_output2.outputs")
        auto_mod = types.ModuleType("accessible_output2.outputs.auto")

        # Add Auto class so patch("accessible_output2.outputs.auto.Auto") resolves
        class FakeAuto:
            pass

        auto_mod.Auto = FakeAuto

        sys.modules["accessible_output2"] = a2_mod
        sys.modules["accessible_output2.outputs"] = outputs_mod
        sys.modules["accessible_output2.outputs.auto"] = auto_mod


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def cleanup_speech():
    """Ensure clean speech import for each test."""
    _reload_speech()
    yield
    _reload_speech()


@pytest.fixture
def mock_auto():
    """Mock accessible_output2.outputs.auto.Auto to simulate availability."""
    _ensure_accessible_output2_present()
    with patch("accessible_output2.outputs.auto.Auto") as mock:
        mock.return_value = Mock()
        yield mock


# ─── Constructor: Never-Crash Initialization ─────────────────────────────────


def test_constructor_with_available_output(mock_auto):
    """Given a stubbed accessible_output2, Speech() is not silent."""
    from bellbird.core.speech import Speech

    speech = Speech()
    assert speech._output is not None
    assert not speech.is_silent


def test_constructor_import_error():
    """Given ImportError on accessible_output2, Speech() is silent."""
    import builtins
    real_import = builtins.__import__

    def _block_a2(name, *args, **kwargs):
        if "accessible_output2" in name:
            raise ImportError(f"blocked: {name}")
        return real_import(name, *args, **kwargs)

    # Remove from sys.modules so Python must call __import__ (not cache hit).
    saved_modules = {k: sys.modules.pop(k) for k in list(sys.modules) if "accessible_output2" in k}

    _reload_speech()
    from bellbird.core.speech import Speech

    try:
        with patch("builtins.__import__", side_effect=_block_a2):
            speech = Speech()
    finally:
        sys.modules.update(saved_modules)

    assert speech._output is None
    assert speech.is_silent


def test_constructor_oserror():
    """Given Auto() raises OSError, Speech() is silent."""
    _ensure_accessible_output2_present()
    with patch(
        "accessible_output2.outputs.auto.Auto",
        side_effect=OSError("No TTS engine"),
    ):
        _reload_speech()
        from bellbird.core.speech import Speech

        speech = Speech()
        assert speech.is_silent
        assert speech._output is None


# ─── speak Method ────────────────────────────────────────────────────────────


def test_speak_with_output(mock_auto):
    """Given a working output, speak delegates correctly."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech.speak("Hola", interrupt=True)
    mock_auto.return_value.speak.assert_called_once_with("Hola", interrupt=True)


def test_speak_when_silent():
    """Given silent speech, speak does nothing and raises no exception."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech._output = None  # force silent
    speech.is_silent = True

    speech.speak("Hola")  # should not raise


def test_speak_with_non_string_text(mock_auto):
    """Given non-string text, speak does not raise."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech.speak(None)  # should not raise


# ─── output Method ────────────────────────────────────────────────────────────


def test_output_when_available(mock_auto):
    """Given a working output, output delegates correctly."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech.output("Línea en braille")
    mock_auto.return_value.output.assert_called_once_with("Línea en braille")


def test_output_when_silent():
    """Given silent speech, output does not raise."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech._output = None
    speech.is_silent = True

    speech.output("texto")  # should not raise


# ─── stop Method ──────────────────────────────────────────────────────────────


def test_stop_when_available(mock_auto):
    """Given a working output, stop delegates correctly."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech.stop()
    mock_auto.return_value.stop.assert_called_once()


def test_stop_when_silent():
    """Given silent speech, stop does not raise."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech._output = None
    speech.is_silent = True

    speech.stop()  # should not raise


# ─── announce_token_chunk — Flushing Logic ────────────────────────────────────


def test_short_token_no_flush(mock_auto):
    """Given a short token, buffer accumulates without flushing."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech.announce_token_chunk("Ho")
    assert speech._buffer == "Ho"
    mock_auto.return_value.speak.assert_not_called()


def test_sentence_terminator_flush(mock_auto):
    """Given a sentence terminator, buffer flushes."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech._buffer = "Hola."
    speech.announce_token_chunk("")
    mock_auto.return_value.speak.assert_called_once_with("Hola.", interrupt=False)
    assert speech._buffer == ""


def test_eighty_char_fallback_flush(mock_auto):
    """Given 81-char token, buffer flushes immediately."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech.announce_token_chunk("a" * 81)
    mock_auto.return_value.speak.assert_called_once_with("a" * 81, interrupt=False)
    assert speech._buffer == ""


def test_question_mark_flush(mock_auto):
    """Given a question mark, buffer flushes."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech._buffer = "¿Qué tal"
    speech.announce_token_chunk("?")
    mock_auto.return_value.speak.assert_called_once_with("¿Qué tal?", interrupt=False)
    assert speech._buffer == ""


def test_newline_flush(mock_auto):
    """Given a newline, buffer flushes."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech._buffer = "primera línea"
    speech.announce_token_chunk("\n")
    mock_auto.return_value.speak.assert_called_once_with(
        "primera línea\n", interrupt=False
    )
    assert speech._buffer == ""


# ─── flush_token_buffer ──────────────────────────────────────────────────────


def test_flush_non_empty_buffer(mock_auto):
    """Given a non-empty buffer, flush speaks and clears."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech._buffer = "fragmento pendiente"
    speech.flush_token_buffer()
    mock_auto.return_value.speak.assert_called_once_with(
        "fragmento pendiente", interrupt=False
    )
    assert speech._buffer == ""


def test_flush_empty_buffer_noop(mock_auto):
    """Given an empty buffer, flush does nothing."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech._buffer = ""
    speech.flush_token_buffer()
    mock_auto.return_value.speak.assert_not_called()


# ─── clear_buffer ─────────────────────────────────────────────────────────────


def test_clear_buffer_discards_without_speaking(mock_auto):
    """Given a non-empty buffer, clear_buffer discards without speaking.

    RED→GREEN: write test first, confirm failure, then implement.
    """
    from bellbird.core.speech import Speech

    speech = Speech()
    speech._buffer = "fragmento pendiente"
    speech.clear_buffer()
    assert speech._buffer == ""
    mock_auto.return_value.speak.assert_not_called()
    mock_auto.return_value.output.assert_not_called()


# ─── Never-Crash Guarantee ────────────────────────────────────────────────────


def test_output_raises_mid_call(mock_auto):
    """Given output.output raises, the method catches and returns None."""
    from bellbird.core.speech import Speech

    mock_auto.return_value.output.side_effect = RuntimeError("TTS failed")
    speech = Speech()
    result = speech.output("texto")
    assert result is None


def test_speak_raises_mid_call(mock_auto):
    """Given output.speak raises, the method catches and returns None."""
    from bellbird.core.speech import Speech

    mock_auto.return_value.speak.side_effect = OSError("TTS engine crashed")
    speech = Speech()
    result = speech.speak("texto")
    assert result is None


# ─── Screen Reader Detection ─────────────────────────────────────────────────


def test_is_screen_reader_active_true(mock_auto):
    """Given the TTS backend is a real screen reader, returns True."""
    from bellbird.core.speech import Speech

    mock_auto.return_value.is_system_output.return_value = False
    speech = Speech()
    assert speech.is_screen_reader_active() is True


def test_is_screen_reader_active_false_when_system_output(mock_auto):
    """Given the TTS backend is a generic system voice, returns False."""
    from bellbird.core.speech import Speech

    mock_auto.return_value.is_system_output.return_value = True
    speech = Speech()
    assert speech.is_screen_reader_active() is False


def test_is_screen_reader_active_false_in_silent_mode():
    """Given the wrapper is in silent mode, returns False even if probed."""
    from bellbird.core.speech import Speech

    speech = Speech()
    # Force silent mode
    speech.is_silent = True
    speech._output = None
    assert speech.is_screen_reader_active() is False


def test_is_screen_reader_active_swallows_probe_exception(mock_auto):
    """Given is_system_output raises, returns False (never-crash contract)."""
    from bellbird.core.speech import Speech

    mock_auto.return_value.is_system_output.side_effect = RuntimeError(
        "probe failed"
    )
    speech = Speech()
    assert speech.is_screen_reader_active() is False


# ─── speak_with_system_voice (v0.10.0) ───────────────────────────────────────


def test_speak_with_system_voice_delegates(mock_auto):
    """Given a working SystemVoice, speak_with_system_voice delegates."""
    from unittest.mock import MagicMock

    from bellbird.core.speech import Speech

    speech = Speech()
    mock_voice = MagicMock()
    speech.speak_with_system_voice("hola", mock_voice)
    mock_voice.speak.assert_called_once_with("hola")


def test_speak_with_system_voice_never_raises(mock_auto):
    """Given a crashy SystemVoice, speak_with_system_voice never raises."""
    from unittest.mock import MagicMock

    from bellbird.core.speech import Speech

    speech = Speech()
    mock_voice = MagicMock()
    mock_voice.speak.side_effect = RuntimeError("SAPI crash")
    speech.speak_with_system_voice("hola", mock_voice)  # must not raise


def test_speak_with_system_voice_no_voice_is_noop(mock_auto):
    """Given no SystemVoice (None), speak_with_system_voice is a no-op."""
    from bellbird.core.speech import Speech

    speech = Speech()
    speech.speak_with_system_voice("hola", None)  # must not raise


def test_speak_with_system_voice_empty_text(mock_auto):
    """Given empty text, speak_with_system_voice does not call the voice."""
    from unittest.mock import MagicMock

    from bellbird.core.speech import Speech

    speech = Speech()
    mock_voice = MagicMock()
    speech.speak_with_system_voice("", mock_voice)
    mock_voice.speak.assert_not_called()


def test_speak_with_system_voice_non_string_text(mock_auto):
    """Given non-string text, speak_with_system_voice does not raise."""
    from unittest.mock import MagicMock

    from bellbird.core.speech import Speech

    speech = Speech()
    mock_voice = MagicMock()
    speech.speak_with_system_voice(None, mock_voice)  # must not raise
    mock_voice.speak.assert_not_called()
