"""Speech wrapper around accessible_output2.

This module is the headless TTS layer for Bellbird. It wraps
accessible_output2.outputs.auto.Auto so the app never crashes due to
speech failure. Every public method catches all exceptions and returns None.

Usage:
    speech = Speech()
    speech.speak("Hello, world!")
"""

from typing import Any


class Speech:
    """Text-to-speech wrapper with never-crash semantics.

    Initializes accessible_output2 silently. If the library is missing or
    fails to initialize, all methods become no-ops (silent mode).

    Attributes:
        is_silent: True when no TTS backend is available.
        _buffer: Accumulated token fragments awaiting flush.
    """

    def __init__(self) -> None:
        self._output: Any = None
        self.is_silent: bool = True
        self._buffer: str = ""

        try:
            from accessible_output2.outputs.auto import Auto

            self._output = Auto()
            self.is_silent = False
        except Exception:
            self._output = None
            self.is_silent = True

    def is_screen_reader_active(self) -> bool:
        """Return True if a real screen reader (NVDA, JAWS, etc.) is active.

        Returns False when in silent mode, when the TTS backend is a
        generic system voice rather than a screen reader, or when
        probing the output mode raises any exception.
        """
        if self.is_silent or self._output is None:
            return False
        try:
            return not self._output.is_system_output()
        except Exception:
            return False

    def speak(self, text: str, interrupt: bool = True) -> None:
        """Speak the given text.

        Args:
            text: Text to speak.
            interrupt: True to interrupt current speech, False to queue.
        """
        try:
            if self._output is not None:
                self._output.speak(text, interrupt=interrupt)
        except Exception:
            pass

    def output(self, text: str) -> None:
        """Send text to both speech and braille display.

        Args:
            text: Text to output.
        """
        try:
            if self._output is not None:
                self._output.output(text)
        except Exception:
            pass

    def stop(self) -> None:
        """Stop any current speech output."""
        try:
            if self._output is not None:
                self._output.stop()
        except Exception:
            pass

    def announce_token_chunk(self, token: str) -> None:
        """Accumulate a token fragment into the buffer.

        Flushes the buffer to speech when a sentence terminator is found
        or when the buffer exceeds 80 characters.

        Args:
            token: Token fragment from the LLM stream.
        """
        try:
            self._buffer += token
            # Check for terminators or length overflow
            if any(t in self._buffer for t in (".", "?", "!", "\n")) or len(
                self._buffer
            ) > 80:
                self.speak(self._buffer, interrupt=False)
                self._buffer = ""
        except Exception:
            pass

    def clear_buffer(self) -> None:
        """Discard the token-chunk buffer without speaking it.

        Called from the abort path to clear any buffered token fragments
        that have not yet been flushed to speech. Never-crash: all
        exceptions are caught and suppressed.

        Main-thread only: writes self._buffer; the only concurrent reader
        is announce_token_chunk, also on the main thread via wx.CallAfter.
        """
        try:
            self._buffer = ""
        except Exception:
            pass

    def flush_token_buffer(self) -> None:
        """Speak any remaining buffer content and clear it."""
        try:
            if self._buffer:
                self.speak(self._buffer, interrupt=False)
                self._buffer = ""
        except Exception:
            pass

    def speak_with_system_voice(self, text: str, system_voice: Any) -> None:
        """Speak text through the system SAPI voice.

        Delegates to ``SystemVoice.speak(text)`` if a voice instance
        is provided and the text is a non-empty string.  No-op on
        ``None`` text, empty string, or ``None`` voice.  Never raises.

        This is **not** a replacement for ``speak()`` — it is an
        additional channel for explicit user actions (F8 / button).

        Args:
            text: Plain text to speak.
            system_voice: A ``SystemVoice`` instance, or ``None``.
        """
        try:
            if system_voice is None:
                return
            if not isinstance(text, str) or not text:
                return
            system_voice.speak(text)
        except Exception:
            pass
