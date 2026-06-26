"""Tests for bellbird.core.sound_player — strict TDD, RED first, then GREEN.

Covers: path resolution, missing file, theme="none", non-win32 guard,
correct winsound invocation, never-crash contract.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _ensure_winsound_present():
    """Ensure winsound is available in sys.modules for patching."""
    if "winsound" not in sys.modules:
        import types

        winsound_mod = types.ModuleType("winsound")
        winsound_mod.PlaySound = MagicMock()
        winsound_mod.SND_FILENAME = 0x00020000
        winsound_mod.SND_ASYNC = 0x0001
        sys.modules["winsound"] = winsound_mod


@pytest.fixture(autouse=True)
def ensure_winsound():
    """Ensure winsound fakes are present."""
    _ensure_winsound_present()
    yield


class TestSoundPlayer:
    """SoundPlayer path resolution and play semantics."""

    # ── resolve ────────────────────────────────────────────────────────────

    def test_resolve_default_theme(self, tmp_path):
        """GIVEN a SoundPlayer with sounds_dir=<tmp>/sounds, theme='default'
        WHEN _resolve('generation_complete') runs
        THEN the result is <tmp>/sounds/default/generation_complete.wav."""
        from bellbird.core.sound_player import SoundPlayer

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="default")
        result = sp._resolve("generation_complete")
        assert result == Path(str(tmp_path / "sounds" / "default" / "generation_complete.wav"))

    def test_resolve_custom_theme(self, tmp_path):
        """GIVEN a SoundPlayer with theme='custom'
        WHEN _resolve is called
        THEN the path uses the custom subdir."""
        from bellbird.core.sound_player import SoundPlayer

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="custom")
        result = sp._resolve("server_ready")
        assert result == Path(str(tmp_path / "sounds" / "custom" / "server_ready.wav"))

    def test_resolve_theme_none_returns_none(self, tmp_path):
        """GIVEN theme='none'
        WHEN _resolve is called
        THEN returns None (fast-path — skip everything)."""
        from bellbird.core.sound_player import SoundPlayer

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="none")
        result = sp._resolve("generation_complete")
        assert result is None

    # ── play ───────────────────────────────────────────────────────────────

    def test_play_missing_file_noop(self, tmp_path):
        """GIVEN a SoundPlayer pointing to a non-existent file
        WHEN play is called
        THEN no exception is raised and winsound is NOT called."""
        from bellbird.core.sound_player import SoundPlayer

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="default")
        with patch("bellbird.core.sound_player.sys.platform", "win32"):
            sp.play("generation_complete")
        # No assert needed — the test is that we didn't raise

    def test_play_existing_file_calls_winsound(self, tmp_path):
        """GIVEN a SoundPlayer and an existing WAV file on win32
        WHEN play is called
        THEN winsound.PlaySound is called with the correct path."""
        from bellbird.core.sound_player import SoundPlayer

        import winsound

        # Create the file
        sound_dir = tmp_path / "sounds" / "default"
        sound_dir.mkdir(parents=True, exist_ok=True)
        wav_file = sound_dir / "generation_complete.wav"
        wav_file.write_text("RIFF....WAVE", encoding="latin-1")

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="default")
        with patch("bellbird.core.sound_player.sys.platform", "win32"):
            with patch("winsound.PlaySound") as mock_play:
                sp.play("generation_complete")
                mock_play.assert_called_once_with(
                    str(wav_file),
                    winsound.SND_FILENAME | winsound.SND_ASYNC,
                )

    def test_play_theme_none_noop(self, tmp_path):
        """GIVEN theme='none'
        WHEN play is called
        THEN winsound.PlaySound is NOT called."""
        from bellbird.core.sound_player import SoundPlayer

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="none")
        with patch("bellbird.core.sound_player.sys.platform", "win32"):
            with patch("winsound.PlaySound") as mock_play:
                sp.play("generation_complete")
                mock_play.assert_not_called()

    def test_play_non_win32_noop(self, tmp_path):
        """GIVEN sys.platform != 'win32'
        WHEN play is called
        THEN no exception and winsound is not called."""
        from bellbird.core.sound_player import SoundPlayer

        # Create the file so the only guard is platform
        sound_dir = tmp_path / "sounds" / "default"
        sound_dir.mkdir(parents=True, exist_ok=True)
        wav_file = sound_dir / "generation_complete.wav"
        wav_file.write_text("RIFF....WAVE", encoding="latin-1")

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="default")
        with patch("bellbird.core.sound_player.sys.platform", "linux"):
            with patch("winsound.PlaySound") as mock_play:
                sp.play("generation_complete")
                mock_play.assert_not_called()

    def test_play_missing_winsound_noop(self, tmp_path):
        """GIVEN winsound raises ImportError
        WHEN play is called
        THEN no exception propagates."""
        from bellbird.core.sound_player import SoundPlayer

        import builtins

        real_import = builtins.__import__

        def _block_winsound(name, *args, **kwargs):
            if "winsound" in name:
                raise ImportError(f"blocked: {name}")
            return real_import(name, *args, **kwargs)

        sound_dir = tmp_path / "sounds" / "default"
        sound_dir.mkdir(parents=True, exist_ok=True)
        wav_file = sound_dir / "generation_complete.wav"
        wav_file.write_text("RIFF....WAVE", encoding="latin-1")

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="default")
        with patch("bellbird.core.sound_player.sys.platform", "win32"):
            # Remove winsound from sys.modules to force re-import
            saved = sys.modules.pop("winsound", None)
            try:
                with patch("builtins.__import__", side_effect=_block_winsound):
                    sp.play("generation_complete")
            finally:
                if saved:
                    sys.modules["winsound"] = saved

    def test_play_winsound_raises_is_caught(self, tmp_path):
        """GIVEN winsound.PlaySound raises RuntimeError
        WHEN play is called
        THEN no exception propagates."""
        from bellbird.core.sound_player import SoundPlayer

        sound_dir = tmp_path / "sounds" / "default"
        sound_dir.mkdir(parents=True, exist_ok=True)
        wav_file = sound_dir / "generation_complete.wav"
        wav_file.write_text("RIFF....WAVE", encoding="latin-1")

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="default")
        with patch("bellbird.core.sound_player.sys.platform", "win32"):
            with patch("winsound.PlaySound", side_effect=RuntimeError("fail")):
                sp.play("generation_complete")

    # ── never-crash ────────────────────────────────────────────────────────

    def test_play_never_raises(self, tmp_path):
        """GIVEN any combination of bad parameters
        WHEN play is called
        THEN no exception propagates."""
        from bellbird.core.sound_player import SoundPlayer

        sp = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="default")
        # Called twice: once with missing file, once with theme none
        sp.play("nonexistent_event")
        sp2 = SoundPlayer(sounds_base=str(tmp_path / "sounds"), theme="none")
        sp2.play("generation_complete")
