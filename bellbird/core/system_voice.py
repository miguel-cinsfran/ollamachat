"""wx-free wrapper around Windows SAPI (SAPI.SpVoice via win32com.client).

Provides SystemVoice — an on-demand OS-level TTS channel used for explicit
re-reads of selected messages. Degrades to a silent no-op on any platform
that is not ``win32``, and on ``win32`` systems where ``pywin32`` is missing.

The class is deliberately minimal: voice list, voice selection, rate control,
and a single ``speak`` method. All methods honour the never-crash contract
(no public method raises). No ``import wx`` at module scope.
"""

import logging
import sys

logger = logging.getLogger(__name__)


class SystemVoice:
    """Headless SAPI voice wrapper.

    Args:
        voice_name: Initial voice name. Empty = first available.
        rate: Initial rate (``-10..+10``). Clamped on set.
    """

    def __init__(self, voice_name: str = "", rate: int = 0) -> None:
        self._voice = None  # type: ignore
        self._voice_name: str = ""
        self._rate: int = 0

        if sys.platform == "win32":
            try:
                import win32com.client  # type: ignore[import-untyped]

                voice = win32com.client.Dispatch("SAPI.SpVoice")
                self._voice = voice
                if voice_name:
                    self.set_voice(voice_name)
                self.set_rate(rate)
            except Exception:
                self._voice = None
        else:
            self._voice = None

    @staticmethod
    def voices() -> list[str]:
        """List available SAPI voice names.

        Returns an empty list outside win32, when pywin32 is missing,
        or when SAPI returns no voices. Never raises.
        """
        if sys.platform != "win32":
            return []
        try:
            import win32com.client  # type: ignore[import-untyped]

            voice = win32com.client.Dispatch("SAPI.SpVoice")
            result: list[str] = []
            for v in voice.GetVoices():
                result.append(v.GetDescription())
            return result
        except Exception:
            return []

    def set_voice(self, name: str) -> bool:
        """Set the active SAPI voice by name.

        Args:
            name: Voice name to select. Empty string is a no-op.

        Returns:
            ``True`` on success, ``False`` if the voice is not found,
            on non-win32, or on any SAPI error. The previously-set
            voice is unchanged on failure.
        """
        if not name:
            return False
        if sys.platform != "win32":
            return False
        if self._voice is None:
            return False
        try:
            for v in self._voice.GetVoices():
                if v.GetDescription() == name:
                    self._voice.Voice = v
                    self._voice_name = name
                    return True
            return False
        except Exception:
            return False

    def set_rate(self, rate: int) -> None:
        """Set the SAPI rate, clamped to ``[-10, +10]``.

        No-op outside win32 or when the voice is not available.
        Never raises.
        """
        if sys.platform != "win32":
            return
        if self._voice is None:
            return
        try:
            clamped = max(-10, min(10, rate))
            self._voice.Rate = clamped
            self._rate = clamped
        except Exception:
            pass

    def speak(self, text: str) -> None:
        """Speak text through the active SAPI voice.

        No-op outside win32, when pywin32 is missing, or when ``text``
        is not a non-empty string. Never raises.
        """
        if sys.platform != "win32":
            return
        if self._voice is None:
            return
        if not isinstance(text, str) or not text:
            return
        try:
            self._voice.Speak(text, 1)  # SVSFlagsAsync=1
        except Exception:
            pass

    def is_available(self) -> bool:
        """Return ``True`` when the SAPI voice is connected.

        Always ``False`` outside win32 or when pywin32 could not load.
        Never raises.
        """
        if sys.platform != "win32":
            return False
        return self._voice is not None
