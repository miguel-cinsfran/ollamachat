"""Smoke test: Speech degrades gracefully when accessible_output2 is missing."""

import sys

import pytest


def test_speech_silent_on_import_error():
    """Given accessible_output2 is missing, Speech is silent and doesn't raise."""
    # Remove accessible_output2 from sys.modules
    saved = {}
    for key in list(sys.modules.keys()):
        if "accessible_output2" in key:
            saved[key] = sys.modules.pop(key)

    # Remove bellbird.core.speech so it re-imports
    for key in list(sys.modules.keys()):
        if "bellbird" in key:
            saved[key] = sys.modules.pop(key)

    from bellbird.core.speech import Speech

    speech = Speech()
    assert speech.is_silent

    # These should not raise
    speech.speak("test")
    speech.announce_token_chunk("test")
    speech.flush_token_buffer()
    speech.output("test")
    speech.stop()

    # Restore
    sys.modules.update(saved)
