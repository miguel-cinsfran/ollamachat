"""Runtime tests for MainWindow — recents, export, auto-restore, persist.

These tests require wxPython; skipped on WSL/Linux via
``importorskip("wx")``. Run via ``run_tests.bat`` on Windows.
"""

import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

pytest.importorskip("wx")

import wx


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def app():
    """Create a wx.App for the test module."""
    return wx.App()


class FakeSpeech:
    """Minimal speech stub for testing announce behavior."""
    def __init__(self):
        self.last_message = ""
        self.messages: list[str] = []

    def speak(self, text: str, interrupt: bool = False) -> None:
        self.last_message = text
        self.messages.append(text)


def _make_frame(app, config_overrides: dict | None = None):
    """Create a MainWindow with patched config and speech.

    Args:
        app: wx.App fixture.
        config_overrides: Dict of config attributes to override.

    Returns:
        Tuple of (frame, config, mock_save_config, fake_speech).
    """
    from bellbird.core.config import BellbirdConfig

    config = BellbirdConfig()
    if config_overrides:
        for k, v in config_overrides.items():
            setattr(config, k, v)

    fake_speech = FakeSpeech()

    with patch("bellbird.ui.main_window.load_config", return_value=config):
        with patch(
            "bellbird.ui.main_window.save_config",
            side_effect=lambda cfg, path=None: None,
        ) as mock_save:
            from bellbird.ui.main_window import MainWindow

            frame = MainWindow(None, title="Test")
            # Replace real speech with fake
            frame._speech = fake_speech
            return frame, config, mock_save, fake_speech


def _ensure_files(paths: list[str], content: str = '{"messages": []}') -> list[str]:
    """Create temporary files and return their absolute paths."""
    result = []
    for p in paths:
        abs_p = os.path.abspath(p)
        Path(abs_p).parent.mkdir(parents=True, exist_ok=True)
        Path(abs_p).write_text(content, encoding="utf-8")
        result.append(abs_p)
    return result


# ─── Task 2.5: Recents submenu ───────────────────────────────────────────────


class TestRecentsSubmenu:
    """Recientes submenu population, filtering, and click handling."""

    def test_recentes_poblado(self, app, tmp_path: Path) -> None:
        """recent_files with 3 valid paths → 3 menu items after refresh."""
        paths = _ensure_files([
            str(tmp_path / "c1.json"),
            str(tmp_path / "c2.json"),
            str(tmp_path / "c3.json"),
        ])
        frame, config, _, _ = _make_frame(
            app, {"recent_files": paths},
        )
        try:
            frame._refresh_recents_menu()
            assert frame._recents_menu.GetMenuItemCount() == 3, (
                f"Expected 3 items, got {frame._recents_menu.GetMenuItemCount()}"
            )
        finally:
            frame.Destroy()

    def test_recentes_filtra_inexistentes(self, app, tmp_path: Path) -> None:
        """1 valid + 1 non-existent path → only 1 item after refresh."""
        valid_paths = _ensure_files([str(tmp_path / "exists.json")])
        missing = str(tmp_path / "missing.json")
        paths = valid_paths + [missing]
        frame, config, _, _ = _make_frame(
            app, {"recent_files": paths},
        )
        try:
            frame._refresh_recents_menu()
            assert frame._recents_menu.GetMenuItemCount() == 1, (
                f"Expected 1 item (filtered), got "
                f"{frame._recents_menu.GetMenuItemCount()}"
            )
        finally:
            frame.Destroy()

    def test_recentes_click_carga(self, app, tmp_path: Path) -> None:
        """Clicking a recents item calls Conversation.load with the right path."""
        paths = _ensure_files([str(tmp_path / "conv.json")])
        frame, config, _, _ = _make_frame(
            app, {"recent_files": paths},
        )
        frame._refresh_recents_menu()

        # Mock Conversation.load
        mock_conv = MagicMock()
        mock_conv.messages = []
        with patch(
            "bellbird.ui.main_window.Conversation.load",
            return_value=(mock_conv, ""),
        ) as mock_load:
            try:
                # Simulate clicking the first recent item via MagicMock event
                evt = MagicMock()
                evt.GetId.return_value = next(iter(frame._recent_items.keys()))
                frame._on_recent_click(evt)

                mock_load.assert_called_once()
                called_path = str(mock_load.call_args[0][0])
                assert called_path == paths[0], (
                    f"Expected load({paths[0]!r}), got load({called_path!r})"
                )
            finally:
                frame.Destroy()

    def test_recentes_click_actualiza_recents(self, app, tmp_path: Path) -> None:
        """Clicking a recents item updates config.recent_files (MRU push)."""
        paths = _ensure_files([
            str(tmp_path / "a.json"),
            str(tmp_path / "b.json"),
        ])
        frame, config, mock_save, _ = _make_frame(
            app, {"recent_files": list(reversed(paths))},
        )
        frame._refresh_recents_menu()

        mock_conv = MagicMock()
        mock_conv.messages = []
        with patch(
            "bellbird.ui.main_window.Conversation.load",
            return_value=(mock_conv, ""),
        ):
            try:
                # Click the FIRST item via MagicMock event
                evt = MagicMock()
                evt.GetId.return_value = next(iter(frame._recent_items.keys()))
                frame._on_recent_click(evt)

                # After clicking, this path should be at the front
                assert config.recent_files[0] == paths[0], (
                    f"Expected {paths[0]!r} at front, "
                    f"got {config.recent_files[0]!r}"
                )
            finally:
                frame.Destroy()

    def test_recentes_vacio_muestra_label(self, app) -> None:
        """Empty recent_files → disabled 'Sin recientes' item."""
        frame, config, _, _ = _make_frame(app, {"recent_files": []})
        try:
            frame._refresh_recents_menu()
            assert frame._recents_menu.GetMenuItemCount() == 1, (
                f"Expected 1 placeholder item, got "
                f"{frame._recents_menu.GetMenuItemCount()}"
            )
            item = frame._recents_menu.FindItemByPosition(0)
            assert item.GetLabel() == "Sin recientes", (
                f"Expected 'Sin recientes', got {item.GetLabel()!r}"
            )
            assert not item.IsEnabled(), "Placeholder item must be disabled"
        finally:
            frame.Destroy()


# ─── Task 2.6: Export to Markdown ─────────────────────────────────────────────


class TestExportToMarkdown:
    """Exportar a Markdown... menu item behavior."""

    def test_exportar_llama_to_markdown_con_system_prompt(self, app) -> None:
        """_on_export calls to_markdown with the current system_prompt."""
        frame, config, _, fake_speech = _make_frame(
            app, {"system_prompt": "Eres un asistente útil"},
        )

        with patch.object(frame._conversation, "to_markdown") as mock_tm:
            mock_tm.return_value = "# Conversación\n\nTest content"
            with patch("wx.FileDialog") as mock_dlg:
                mock_dlg.return_value.ShowModal.return_value = wx.ID_OK
                mock_dlg.return_value.GetPath.return_value = "/tmp/test_export.md"
                with patch("builtins.open", MagicMock()):
                    try:
                        frame._on_export()

                        mock_tm.assert_called_once_with(
                            system_prompt="Eres un asistente útil",
                        )
                    finally:
                        frame.Destroy()

    def test_exportar_escribe_utf8(self, app, tmp_path: Path) -> None:
        """Exported file is written with UTF-8 encoding."""
        filepath = str(tmp_path / "export.md")
        frame, config, _, fake_speech = _make_frame(app)

        with patch.object(frame._conversation, "to_markdown") as mock_tm:
            mock_tm.return_value = "# Conversación\n\nContenido con acentos: áéíóú"
            with patch("wx.FileDialog") as mock_dlg:
                mock_dlg.return_value.ShowModal.return_value = wx.ID_OK
                mock_dlg.return_value.GetPath.return_value = filepath
                try:
                    frame._on_export()

                    content = Path(filepath).read_text(encoding="utf-8")
                    assert "áéíóú" in content, (
                        "Expected UTF-8 content with accented chars"
                    )
                    assert content == "# Conversación\n\nContenido con acentos: áéíóú"
                finally:
                    frame.Destroy()

    def test_exportar_speaker_anuncia(self, app) -> None:
        """On successful export, speech.speak is called with the filename."""
        frame, config, _, fake_speech = _make_frame(app)

        with patch.object(frame._conversation, "to_markdown") as mock_tm:
            mock_tm.return_value = "# Conversación"
            with patch("wx.FileDialog") as mock_dlg:
                mock_dlg.return_value.ShowModal.return_value = wx.ID_OK
                mock_dlg.return_value.GetPath.return_value = (
                    "/tmp/mi_exporte.md"
                )
                with patch("builtins.open", MagicMock()):
                    try:
                        frame._on_export()

                        assert "Exportado a" in fake_speech.last_message, (
                            f"Expected 'Exportado a' in speech, "
                            f"got {fake_speech.last_message!r}"
                        )
                        assert "mi_exporte.md" in fake_speech.last_message, (
                            f"Expected filename in speech, "
                            f"got {fake_speech.last_message!r}"
                        )
                    finally:
                        frame.Destroy()

    def test_exportar_falla_no_crashea(self, app) -> None:
        """When to_markdown raises, no crash occurs."""
        frame, config, _, fake_speech = _make_frame(app)

        with patch.object(frame._conversation, "to_markdown") as mock_tm:
            mock_tm.side_effect = ValueError("Simulated failure")
            with patch("wx.FileDialog") as mock_dlg:
                mock_dlg.return_value.ShowModal.return_value = wx.ID_OK
                mock_dlg.return_value.GetPath.return_value = "/tmp/fail.md"
                try:
                    # Must not raise
                    frame._on_export()

                    assert "Error al exportar" in fake_speech.last_message, (
                        f"Expected error speech, got {fake_speech.last_message!r}"
                    )
                finally:
                    frame.Destroy()


# ─── Task 2.7: Auto-restore at startup ────────────────────────────────────────


class TestAutoRestore:
    """_auto_restore_last_session behavior."""

    def test_auto_restore_carga_exitosa(self, app, tmp_path: Path) -> None:
        """When auto-restore is enabled, Conversation.load is called."""
        conv_path = str(tmp_path / "last.json")
        _ensure_files([conv_path])

        frame, config, _, fake_speech = _make_frame(
            app, {
                "restore_last_session": True,
                "last_session_path": conv_path,
            },
        )

        mock_conv = MagicMock()
        mock_conv.messages = [{"role": "user", "content": "Hello"}]
        with patch(
            "bellbird.ui.main_window.Conversation.load",
            return_value=(mock_conv, ""),
        ) as mock_load:
            with patch.object(frame.chat_panel, "set_history") as mock_set:
                try:
                    frame._auto_restore_last_session()

                    mock_load.assert_called_once()
                    mock_set.assert_called_once()
                    assert "Sesión restaurada" in fake_speech.last_message, (
                        f"Expected 'Sesión restaurada', got "
                        f"{fake_speech.last_message!r}"
                    )
                finally:
                    frame.Destroy()

    def test_auto_restore_no_hace_nada_si_toggle_off(self, app) -> None:
        """When restore_last_session is False, load is NOT called."""
        frame, config, _, _ = _make_frame(
            app, {
                "restore_last_session": False,
                "last_session_path": "/tmp/nonexistent.json",
            },
        )

        with patch(
            "bellbird.ui.main_window.Conversation.load",
        ) as mock_load:
            try:
                frame._auto_restore_last_session()
                mock_load.assert_not_called()
            finally:
                frame.Destroy()

    def test_auto_restore_falla_limpia_path(self, app, tmp_path: Path) -> None:
        """When load fails, last_session_path is cleared."""
        conv_path = str(tmp_path / "corrupt.json")
        _ensure_files([conv_path])

        frame, config, mock_save, _ = _make_frame(
            app, {
                "restore_last_session": True,
                "last_session_path": conv_path,
            },
        )

        with patch(
            "bellbird.ui.main_window.Conversation.load",
            side_effect=ValueError("Corrupt file"),
        ):
            try:
                frame._auto_restore_last_session()

                assert config.last_session_path == "", (
                    f"Expected last_session_path cleared, got "
                    f"{config.last_session_path!r}"
                )
            finally:
                frame.Destroy()

    def test_auto_restore_anuncia_fallo(self, app, tmp_path: Path) -> None:
        """When load fails, speech announces the failure."""
        conv_path = str(tmp_path / "bad.json")
        _ensure_files([conv_path])

        frame, config, _, fake_speech = _make_frame(
            app, {
                "restore_last_session": True,
                "last_session_path": conv_path,
            },
        )

        with patch(
            "bellbird.ui.main_window.Conversation.load",
            side_effect=ValueError("Corrupt"),
        ):
            try:
                frame._auto_restore_last_session()

                assert "No se pudo restaurar" in fake_speech.last_message, (
                    f"Expected failure speech, got "
                    f"{fake_speech.last_message!r}"
                )
            finally:
                frame.Destroy()


# ─── Task 2.8: Persist last_session_path + recent_files ───────────────────────


class TestPersistSessionAndRecents:
    """Save and load operations persist session path and recents."""

    def test_save_persiste_last_y_recents(self, app, tmp_path: Path) -> None:
        """After save, config.last_session_path and recent_files[0] are set."""
        filepath = str(tmp_path / "saved.json")
        frame, config, mock_save, _ = _make_frame(app)

        with patch("wx.FileDialog") as mock_dlg:
            mock_dlg.return_value.ShowModal.return_value = wx.ID_OK
            mock_dlg.return_value.GetPath.return_value = filepath
            try:
                frame.save_conversation()

                assert config.last_session_path == os.path.abspath(filepath), (
                    f"Expected {os.path.abspath(filepath)!r}, "
                    f"got {config.last_session_path!r}"
                )
                assert config.recent_files[0] == os.path.abspath(filepath), (
                    f"Expected {os.path.abspath(filepath)!r} at front, "
                    f"got {config.recent_files[0]!r}"
                )
            finally:
                frame.Destroy()

    def test_load_persiste_last_y_recents(self, app, tmp_path: Path) -> None:
        """After load, config.last_session_path and recent_files[0] are set."""
        filepath = str(tmp_path / "loaded.json")
        _ensure_files([filepath], content='{"messages": [], "system_prompt": ""}')

        frame, config, mock_save, _ = _make_frame(app)

        with patch("wx.FileDialog") as mock_dlg:
            mock_dlg.return_value.ShowModal.return_value = wx.ID_OK
            mock_dlg.return_value.GetPath.return_value = filepath
            try:
                frame.load_conversation()

                assert config.last_session_path == os.path.abspath(filepath), (
                    f"Expected {os.path.abspath(filepath)!r}, "
                    f"got {config.last_session_path!r}"
                )
                assert config.recent_files[0] == os.path.abspath(filepath), (
                    f"Expected {os.path.abspath(filepath)!r} at front, "
                    f"got {config.recent_files[0]!r}"
                )
            finally:
                frame.Destroy()

    def test_save_falla_no_persiste(self, app) -> None:
        """When Conversation.save raises, config is not modified."""
        frame, config, mock_save, _ = _make_frame(app)
        original_path = config.last_session_path

        with patch("wx.FileDialog") as mock_dlg:
            mock_dlg.return_value.ShowModal.return_value = wx.ID_OK
            mock_dlg.return_value.GetPath.return_value = "/tmp/fail_save.json"
            with patch(
                "bellbird.ui.main_window.Conversation.save",
                side_effect=OSError("Disk full"),
            ):
                try:
                    # Must not raise
                    frame.save_conversation()

                    assert config.last_session_path == original_path, (
                        f"Expected last_session_path unchanged "
                        f"({original_path!r}), got {config.last_session_path!r}"
                    )
                finally:
                    frame.Destroy()

    def test_recents_dedup_al_guardar(self, app, tmp_path: Path) -> None:
        """Saving the same path twice produces one entry (dedup)."""
        filepath = str(tmp_path / "dedup.json")
        frame, config, mock_save, _ = _make_frame(app)

        with patch("wx.FileDialog") as mock_dlg:
            mock_dlg.return_value.ShowModal.return_value = wx.ID_OK
            mock_dlg.return_value.GetPath.return_value = filepath
            try:
                # First save
                frame.save_conversation()
                first_count = len(config.recent_files)

                # Second save with same path
                frame.save_conversation()
                second_count = len(config.recent_files)

                # After dedup, count should be the same (not incremented)
                assert second_count == first_count, (
                    f"Expected dedup (count stays {first_count}), "
                    f"got {second_count}"
                )
                assert config.recent_files[0] == os.path.abspath(filepath), (
                    f"Expected path at front, got {config.recent_files[0]!r}"
                )
            finally:
                frame.Destroy()
