"""wx-free wrapper around ``winsound.PlaySound`` for event sound cues.

Provides ``SoundPlayer`` — a per-theme sound dispatcher that resolves
event names to ``.wav`` files on disk and plays them via ``winsound``.
Degrades to a silent no-op on non-``win32`` platforms, on missing
``winsound``, on missing files, and on ``theme="none"``.

All public methods honour the never-crash contract (no public method
raises). No ``import wx`` at module scope.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class SoundPlayer:
    """Event sound player — theme-aware, silent outside win32.

    Args:
        sounds_base: Base directory for sound themes. Typically
            ``bellbird/data/sounds`` resolved from ``user_data_dir()``.
            Defaults to ``data/sounds`` relative to the package root.
        theme: Theme subdirectory name. ``"none"`` silences all playback.
    """

    def __init__(
        self,
        sounds_base: str | None = None,
        theme: str = "default",
    ) -> None:
        if sounds_base is not None:
            self._base = Path(sounds_base)
        else:
            # Fallback: resolve relative to the package data dir
            pkg_root = Path(__file__).parent.parent / "data"
            self._base = pkg_root / "sounds"
        self._theme = theme

    def _resolve(self, event: str) -> Path | None:
        """Resolve the WAV path for an event.

        Returns ``None`` when ``theme="none"`` (fast-path skip).
        Never raises.
        """
        if self._theme == "none":
            return None
        return self._base / self._theme / f"{event}.wav"

    def play(self, event: str) -> None:
        """Play the WAV file for *event*.

        On ``win32`` with the file present, calls
        ``winsound.PlaySound(path, SND_FILENAME | SND_ASYNC)``.

        Silent no-op on: non-``win32``, missing ``winsound``, missing
        file, ``theme="none"``, or any internal error.  Never raises.
        """
        if sys.platform != "win32":
            return
        path = self._resolve(event)
        if path is None:  # theme == "none"
            return
        if not path.is_file():
            return
        try:
            import winsound

            winsound.PlaySound(
                str(path),
                winsound.SND_FILENAME | winsound.SND_ASYNC,
            )
        except Exception:
            pass

    def play_loop(self, event: str) -> None:
        """Play the WAV for *event* on repeat until :meth:`stop` is called.

        Uses ``SND_LOOP | SND_ASYNC`` (Windows). Designed for seamless-loop
        assets like ``connecting``. Silent no-op outside win32, on missing
        file/winsound, or ``theme="none"``. Never raises.
        """
        if sys.platform != "win32":
            return
        path = self._resolve(event)
        if path is None or not path.is_file():
            return
        try:
            import winsound

            winsound.PlaySound(
                str(path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP,
            )
        except Exception:
            pass

    def stop(self) -> None:
        """Stop any async/looping sound currently playing. Never raises."""
        if sys.platform != "win32":
            return
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
