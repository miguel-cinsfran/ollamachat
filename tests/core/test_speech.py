"""Tests for Speech module — strict TDD, RED first, then GREEN."""

import sys
from unittest.mock import Mock, patch

import pytest


# ─── Helper to reload speech module ──────────────────────────────────────────


def _reload_speech():
    """Remove speech from sys.modules so it re-imports on next access."""
    for mod in list(sys.modules.keys()):
        if "ollamachat.core.speech" in mod or "ollamachat" in mod:
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
    from ollamachat.core.speech import Speech

    speech = Speech()
    assert speech._output is not None
    assert not speech.is_silent


def test_constructor_import_error():
    """Given ImportError on accessible_output2, Speech() is silent."""
    # Ensure accessible_output2 cannot be imported
    saved_modules = {}
    for key in list(sys.modules.keys()):
        if "accessible_output2" in key:
            saved_modules[key] = sys.modules.pop(key)

    _reload_speech()

    from ollamachat.core.speech import Speech

    speech = Speech()
    assert speech._output is None
    assert speech.is_silent

    # Restore
    sys.modules.update(saved_modules)


def test_constructor_oserror():
    """Given Auto() raises OSError, Speech() is silent."""
    _ensure_accessible_output2_present()
    with patch(
        "accessible_output2.outputs.auto.Auto",
        side_effect=OSError("No TTS engine"),
    ):
        _reload_speech()
        from ollamachat.core.speech import Speech

        speech = Speech()
        assert speech.is_silent
        assert speech._output is None


# ─── speak Method ────────────────────────────────────────────────────────────


def test_speak_with_output(mock_auto):
    """Given a working output, speak delegates correctly."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech.speak("Hola", interrupt=True)
    mock_auto.return_value.speak.assert_called_once_with("Hola", interrupt=True)


def test_speak_when_silent():
    """Given silent speech, speak does nothing and raises no exception."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech._output = None  # force silent
    speech.is_silent = True

    speech.speak("Hola")  # should not raise


def test_speak_with_non_string_text(mock_auto):
    """Given non-string text, speak does not raise."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech.speak(None)  # should not raise


# ─── output Method ────────────────────────────────────────────────────────────


def test_output_when_available(mock_auto):
    """Given a working output, output delegates correctly."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech.output("Línea en braille")
    mock_auto.return_value.output.assert_called_once_with("Línea en braille")


def test_output_when_silent():
    """Given silent speech, output does not raise."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech._output = None
    speech.is_silent = True

    speech.output("texto")  # should not raise


# ─── stop Method ──────────────────────────────────────────────────────────────


def test_stop_when_available(mock_auto):
    """Given a working output, stop delegates correctly."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech.stop()
    mock_auto.return_value.stop.assert_called_once()


def test_stop_when_silent():
    """Given silent speech, stop does not raise."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech._output = None
    speech.is_silent = True

    speech.stop()  # should not raise


# ─── announce_token_chunk — Flushing Logic ────────────────────────────────────


def test_short_token_no_flush(mock_auto):
    """Given a short token, buffer accumulates without flushing."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech.announce_token_chunk("Ho")
    assert speech._buffer == "Ho"
    mock_auto.return_value.speak.assert_not_called()


def test_sentence_terminator_flush(mock_auto):
    """Given a sentence terminator, buffer flushes."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech._buffer = "Hola."
    speech.announce_token_chunk("")
    mock_auto.return_value.speak.assert_called_once_with("Hola.", interrupt=False)
    assert speech._buffer == ""


def test_eighty_char_fallback_flush(mock_auto):
    """Given 81-char token, buffer flushes immediately."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech.announce_token_chunk("a" * 81)
    mock_auto.return_value.speak.assert_called_once_with("a" * 81, interrupt=False)
    assert speech._buffer == ""


def test_question_mark_flush(mock_auto):
    """Given a question mark, buffer flushes."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech._buffer = "¿Qué tal"
    speech.announce_token_chunk("?")
    mock_auto.return_value.speak.assert_called_once_with("¿Qué tal?", interrupt=False)
    assert speech._buffer == ""


def test_newline_flush(mock_auto):
    """Given a newline, buffer flushes."""
    from ollamachat.core.speech import Speech

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
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech._buffer = "fragmento pendiente"
    speech.flush_token_buffer()
    mock_auto.return_value.speak.assert_called_once_with(
        "fragmento pendiente", interrupt=False
    )
    assert speech._buffer == ""


def test_flush_empty_buffer_noop(mock_auto):
    """Given an empty buffer, flush does nothing."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    speech._buffer = ""
    speech.flush_token_buffer()
    mock_auto.return_value.speak.assert_not_called()


# ─── Never-Crash Guarantee ────────────────────────────────────────────────────


def test_output_raises_mid_call(mock_auto):
    """Given output.output raises, the method catches and returns None."""
    from ollamachat.core.speech import Speech

    mock_auto.return_value.output.side_effect = RuntimeError("TTS failed")
    speech = Speech()
    result = speech.output("texto")
    assert result is None


def test_speak_raises_mid_call(mock_auto):
    """Given output.speak raises, the method catches and returns None."""
    from ollamachat.core.speech import Speech

    mock_auto.return_value.speak.side_effect = OSError("TTS engine crashed")
    speech = Speech()
    result = speech.speak("texto")
    assert result is None


# ─── Screen Reader Detection ─────────────────────────────────────────────────


def test_is_screen_reader_active_true(mock_auto):
    """Given the TTS backend is a real screen reader, returns True."""
    from ollamachat.core.speech import Speech

    mock_auto.return_value.is_system_output.return_value = False
    speech = Speech()
    assert speech.is_screen_reader_active() is True


def test_is_screen_reader_active_false_when_system_output(mock_auto):
    """Given the TTS backend is a generic system voice, returns False."""
    from ollamachat.core.speech import Speech

    mock_auto.return_value.is_system_output.return_value = True
    speech = Speech()
    assert speech.is_screen_reader_active() is False


def test_is_screen_reader_active_false_in_silent_mode():
    """Given the wrapper is in silent mode, returns False even if probed."""
    from ollamachat.core.speech import Speech

    speech = Speech()
    # Force silent mode
    speech.is_silent = True
    speech._output = None
    assert speech.is_screen_reader_active() is False


def test_is_screen_reader_active_swallows_probe_exception(mock_auto):
    """Given is_system_output raises, returns False (never-crash contract)."""
    from ollamachat.core.speech import Speech

    mock_auto.return_value.is_system_output.side_effect = RuntimeError(
        "probe failed"
    )
    speech = Speech()
    assert speech.is_screen_reader_active() is False
