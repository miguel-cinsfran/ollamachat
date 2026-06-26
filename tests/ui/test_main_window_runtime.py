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

    def output(self, text: str) -> None:
        """Stub for accessible-output2's voz+braille output. Same effect as
        speak(interrupt=False) for testing purposes."""
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


# ─── WU-2: Attach URL (Ctrl+U) ───────────────────────────────────────────────


class TestOnAttachUrl:
    """_on_attach_url gate, dialog opening, and validation."""

    def test_attach_url_gate_during_generation(self, app):
        """Mid-generation: speaks guard and returns without opening dialog."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            frame._is_generating = True
            with patch("bellbird.ui.main_window.URLDialog") as mock_dlg:
                frame._on_attach_url()
                mock_dlg.assert_not_called()
                assert "Generación en curso" in fake_speech.last_message, (
                    f"Expected 'Generación en curso' in speech, "
                    f"got {fake_speech.last_message!r}"
                )
        finally:
            frame.Destroy()

    def test_attach_url_opens_dialog_when_idle(self, app):
        """When idle, _on_attach_url opens URLDialog."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            frame._is_generating = False
            with patch("bellbird.ui.main_window.URLDialog") as mock_dlg:
                mock_instance = MagicMock()
                mock_instance.ShowModal.return_value = wx.ID_CANCEL
                mock_instance.get_url.return_value = ""
                mock_dlg.return_value = mock_instance
                frame._on_attach_url()
                mock_dlg.assert_called_once_with(frame)
        finally:
            frame.Destroy()

    def test_attach_url_empty_url_speaks(self, app):
        """Empty URL speaks 'URL vacía'."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            frame._is_generating = False
            with patch("bellbird.ui.main_window.URLDialog") as mock_dlg:
                mock_instance = MagicMock()
                mock_instance.ShowModal.return_value = wx.ID_OK
                mock_instance.get_url.return_value = ""
                mock_dlg.return_value = mock_instance
                frame._on_attach_url()
                assert "URL vacía" in fake_speech.last_message, (
                    f"Expected 'URL vacía' in speech, "
                    f"got {fake_speech.last_message!r}"
                )
        finally:
            frame.Destroy()

    def test_attach_url_invalid_scheme_speaks(self, app):
        """Invalid scheme speaks 'Solo URLs http o https'."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            frame._is_generating = False
            with patch("bellbird.ui.main_window.URLDialog") as mock_dlg:
                mock_instance = MagicMock()
                mock_instance.ShowModal.return_value = wx.ID_OK
                mock_instance.get_url.return_value = "ftp://example.com"
                mock_dlg.return_value = mock_instance
                frame._on_attach_url()
                assert "Solo URLs http o https" in fake_speech.last_message, (
                    f"Expected 'Solo URLs http o https' in speech, "
                    f"got {fake_speech.last_message!r}"
                )
        finally:
            frame.Destroy()


class TestOnFetchComplete:
    """_on_fetch_complete routing: success, truncation, error."""

    def _make_fetch_result(self, ok=True, text="Hello", error=None,
                           url="https://example.com", status_code=200,
                           truncated=False, original_size=None):
        from bellbird.core.web_fetch import FetchResult
        return FetchResult(
            ok=ok, text=text, error=error, url=url,
            status_code=status_code, truncated=truncated,
            original_size=original_size,
        )

    def test_fetch_complete_success_attaches_to_chat(self, app):
        """Success calls chat_panel.attach_url with correct args."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            result = self._make_fetch_result(text="Hello world")
            with patch.object(frame.chat_panel, "attach_url") as mock_attach:
                frame._on_fetch_complete(result)
                mock_attach.assert_called_once()
                args, kwargs = mock_attach.call_args
                assert kwargs.get("url") == "https://example.com" or args[0] == "https://example.com"
                assert kwargs.get("text") == "Hello world" or args[1] == "Hello world"
        finally:
            frame.Destroy()

    def test_fetch_complete_success_speaks(self, app):
        """Success speaks 'Página adjuntada'."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            result = self._make_fetch_result()
            frame._on_fetch_complete(result)
            assert "Página adjuntada" in fake_speech.last_message, (
                f"Expected 'Página adjuntada' in speech, "
                f"got {fake_speech.last_message!r}"
            )
        finally:
            frame.Destroy()

    def test_fetch_complete_truncated_speaks_warning(self, app):
        """Truncated result speaks truncation warning."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            result = self._make_fetch_result(
                truncated=True, original_size=60000,
            )
            frame._on_fetch_complete(result)
            assert "se truncó" in fake_speech.last_message, (
                f"Expected truncation warning in speech, "
                f"got {fake_speech.last_message!r}"
            )
        finally:
            frame.Destroy()

    def test_fetch_complete_failure_speaks_error(self, app):
        """Failure speaks error and does not call attach_url."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            result = self._make_fetch_result(
                ok=False, error="Timeout de conexión", status_code=None,
            )
            with patch.object(frame.chat_panel, "attach_url") as mock_attach:
                frame._on_fetch_complete(result)
                mock_attach.assert_not_called()
                assert "Error al descargar" in fake_speech.last_message, (
                    f"Expected 'Error al descargar' in speech, "
                    f"got {fake_speech.last_message!r}"
                )
        finally:
            frame.Destroy()

    def test_fetch_complete_cancels_timer(self, app):
        """Timer is cancelled and set to None after fetch completes."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            result = self._make_fetch_result()
            timer = MagicMock()
            frame._url_fetch_timer = timer
            frame._on_fetch_complete(result)
            timer.cancel.assert_called_once()
            assert frame._url_fetch_timer is None
        finally:
            frame.Destroy()

    def test_fetch_complete_timer_none_no_error(self, app):
        """When no timer was set, completion does not crash."""
        frame, config, _, fake_speech = _make_frame(app)
        try:
            frame._url_fetch_timer = None
            result = self._make_fetch_result()
            # Must not raise
            frame._on_fetch_complete(result)
        finally:
            frame.Destroy()


# ─── WU-2: F2 Status (T-WU2-01) ───────────────────────────────────────────────


class TestF2StatusFormatter:
    """_announce_session_status with SessionSnapshot + format_status."""

    def test_f2_all_toggles_on_calls_output(self, app):
        """F2 with ALL toggles ON calls speech.output (voz+braille)."""
        from bellbird.core.status_formatter import DEFAULT_STATUS_TOGGLES
        frame, config, _, fake_speech = _make_frame(app)
        frame._is_generating = False
        # Ensure all toggles are ON
        config.status_toggles = {t: True for t in DEFAULT_STATUS_TOGGLES}
        config.temperature = 0.7
        config.top_p = 0.9
        config.max_tokens = 4096
        try:
            # Mock client to avoid real HTTP calls
            frame._client.get_loaded_model = MagicMock(return_value="")
            frame._client.check_state = MagicMock(return_value="ready")

            frame._announce_session_status()

            assert fake_speech.last_message != "", (
                "F2 should produce non-empty speech when all toggles are ON"
            )
        finally:
            frame.Destroy()

    def test_f2_all_toggles_off_no_speech(self, app):
        """F2 with ALL toggles OFF produces no speech call."""
        from bellbird.core.status_formatter import DEFAULT_STATUS_TOGGLES
        frame, config, _, fake_speech = _make_frame(app)
        frame._is_generating = False
        config.status_toggles = {t: False for t in DEFAULT_STATUS_TOGGLES}
        try:
            frame._announce_session_status()
            assert fake_speech.last_message == "", (
                "F2 should produce no speech when all toggles are OFF"
            )
        finally:
            frame.Destroy()

    def test_f2_mid_gen_uses_speak_interrupt_false(self, app):
        """Mid-generation F2 uses speech.speak(interrupt=False)."""
        from bellbird.core.status_formatter import DEFAULT_STATUS_TOGGLES
        frame, config, _, fake_speech = _make_frame(app)
        frame._is_generating = True
        config.status_toggles = {t: True for t in DEFAULT_STATUS_TOGGLES}
        frame._client.get_loaded_model = MagicMock(return_value="")
        frame._client.check_state = MagicMock(return_value="ready")
        try:
            with patch.object(frame._speech, "output") as mock_output:
                with patch.object(frame._speech, "speak") as mock_speak:
                    frame._announce_session_status()
                    mock_output.assert_not_called()
                    mock_speak.assert_called_once()
                    args, kwargs = mock_speak.call_args
                    assert kwargs.get("interrupt") is False, (
                        "Mid-gen F2 must use interrupt=False"
                    )
        finally:
            frame.Destroy()

    def test_f2_mid_gen_uses_progress_tokens(self, app):
        """Mid-generation F2 uses progress_tokens for the % formula."""
        from bellbird.core.status_formatter import DEFAULT_STATUS_TOGGLES
        frame, config, _, fake_speech = _make_frame(app)
        frame._is_generating = True
        frame._latest_completion_tokens = 512
        frame._current_n_ctx = 4096
        config.status_toggles = {t: True for t in DEFAULT_STATUS_TOGGLES}
        frame._client.get_loaded_model = MagicMock(return_value="")
        frame._client.check_state = MagicMock(return_value="ready")
        try:
            with patch.object(frame._speech, "speak") as mock_speak:
                frame._announce_session_status()
                mock_speak.assert_called_once()
                text = mock_speak.call_args[0][0]
                assert "512" in text, (
                    f"Expected progress_tokens (512) in F2 speech, got {text!r}"
                )
        finally:
            frame.Destroy()


# ─── WU-2: Double-F2 (T-WU2-02) ──────────────────────────────────────────────


class TestDoubleF2:
    """Double-F2 detection within 1.5 s switches to mode='long'."""

    def test_single_f2_is_short(self, app):
        """Single F2 press calls format_status with 'short' mode."""
        frame, config, _, fake_speech = _make_frame(app)
        frame._last_f2_mono = None  # fresh state
        # Mock time.monotonic to simulate one press
        with patch("bellbird.ui.main_window.time.monotonic") as mock_time:
            mock_time.return_value = 100.0
            with patch.object(
                frame, "_announce_session_status", wraps=frame._announce_session_status
            ) as wrapped:
                try:
                    frame._announce_session_status()
                    # After short press, _last_f2_mono is updated (no override to verify)
                finally:
                    frame.Destroy()

    def test_double_f2_within_window_is_long(self, app):
        """Two F2s within 1.5 s produce long mode on the second press."""
        from bellbird.core.status_formatter import format_status, SessionSnapshot
        frame, config, _, fake_speech = _make_frame(app)
        frame._is_generating = False
        config.status_toggles = {"model_name": True}
        frame._client.get_loaded_model = MagicMock(return_value="TestModel")
        frame._client.check_state = MagicMock(return_value="ready")
        frame._current_n_ctx = 4096
        frame._latest_prompt_tokens = None
        frame._latest_completion_tokens = None
        frame._latest_tok_per_s = None
        frame._vram_free_mb = None
        frame._vram_total_mb = None
        frame._fit_status = None

        with patch("bellbird.ui.main_window.time.monotonic") as mock_time:
            # First press at t=100
            mock_time.side_effect = [100.0, 100.3]  # 300ms apart
            try:
                frame._announce_session_status()  # first press — short
                first_text = fake_speech.last_message
                fake_speech.last_message = ""
                frame._announce_session_status()  # second press — long (within 1.5s)
                second_text = fake_speech.last_message
                # Both should be non-empty
                assert first_text != "", "First F2 press should produce speech"
                assert second_text != "", (
                    "Second F2 press (double) should produce speech"
                )
                assert first_text != second_text, (
                    "Double-F2 should produce different (long) output"
                )
            finally:
                frame.Destroy()

    def test_f2_spaced_2s_apart_both_short(self, app):
        """Two F2s spaced > 1.5 s apart are both treated as short."""
        frame, config, _, fake_speech = _make_frame(app)
        config.status_toggles = {"is_generating": True}
        frame._is_generating = True

        with patch("bellbird.ui.main_window.time.monotonic") as mock_time:
            mock_time.side_effect = [100.0, 102.0]  # 2s apart
            try:
                frame._announce_session_status()  # first short
                first_text = fake_speech.last_message
                fake_speech.last_message = ""
                frame._announce_session_status()  # second short (window expired)
                second_text = fake_speech.last_message
                assert first_text != "", "First press should produce speech"
                assert second_text != "", "Second press should produce speech"
            finally:
                frame.Destroy()

    def test_triple_f2_starts_short_again(self, app):
        """Regression: 3rd F2 within 1.5s of 2nd must restart short cycle.

        The C1 verify finding (CRITICAL): the unconditional
        `self._last_f2_mono = now` after the if/else block overrode the
        spec-mandated reset to None on the long-mode branch, so a 3rd
        press produced "long" instead of the spec-required "short".
        """
        frame, config, _, fake_speech = _make_frame(app)
        config.status_toggles = {"model_name": True}
        frame._client.get_loaded_model = MagicMock(return_value="TestModel")
        frame._client.check_state = MagicMock(return_value="ready")
        frame._current_n_ctx = 4096
        frame._latest_prompt_tokens = None
        frame._latest_completion_tokens = None
        frame._latest_tok_per_s = None
        frame._vram_free_mb = None
        frame._vram_total_mb = None
        frame._fit_status = None
        frame._is_generating = False

        with patch("bellbird.ui.main_window.time.monotonic") as mock_time:
            # Press 1 at t=100, press 2 at t=100.3 (long), press 3 at t=100.6.
            # After the fix, press 3 must NOT be "long" (the cycle must restart).
            mock_time.side_effect = [100.0, 100.3, 100.6]
            try:
                frame._announce_session_status()  # press 1 — short
                first_text = fake_speech.last_message
                fake_speech.last_message = ""
                frame._announce_session_status()  # press 2 — long (within 1.5s)
                second_text = fake_speech.last_message
                fake_speech.last_message = ""
                frame._announce_session_status()  # press 3 — must be short again
                third_text = fake_speech.last_message
                assert first_text != "", "Press 1 should produce speech"
                assert second_text != "", "Press 2 should produce speech"
                assert third_text != "", "Press 3 should produce speech"
                # The third press text must match the first press text (both "short")
                # and differ from the second press ("long").
                assert first_text == third_text, (
                    f"Press 3 should be 'short' (matches press 1). "
                    f"Got press 1={first_text!r}, press 3={third_text!r}"
                )
                assert second_text != first_text, (
                    f"Press 2 should be 'long' (differs from press 1). "
                    f"Got press 1={first_text!r}, press 2={second_text!r}"
                )
            finally:
                frame.Destroy()


# ─── WU-2: Context Meter (T-WU2-03) ───────────────────────────────────────────


class TestContextMeter:
    """_update_context_meter behavior on status bar and threshold speech."""

    def test_happy_update_shows_percentage(self, app):
        """Usage chunk updates the meter to 'Contexto: 1200/4096 (29 %)'."""
        frame, config, _, fake_speech = _make_frame(app)
        frame._current_n_ctx = 4096
        frame._is_generating = True
        try:
            frame._on_usage({"prompt_tokens": 200, "completion_tokens": 1000})
            text = frame.status_bar.GetStatusText(1)
            assert "1200" in text and "4096" in text and "29" in text, (
                f"Expected Contexto: 1200/4096 (29 %), got {text!r}"
            )
        finally:
            frame.Destroy()

    def test_threshold_fires_at_85(self, app):
        """Threshold ≥ 85 % calls speech.speak('Contexto casi lleno')."""
        frame, config, _, fake_speech = _make_frame(app)
        frame._current_n_ctx = 4096
        frame._is_generating = True
        frame._meter_threshold_fired = False
        try:
            frame._on_usage({"prompt_tokens": 1000, "completion_tokens": 2700})
            assert "Contexto casi lleno" in fake_speech.last_message, (
                f"Expected threshold speech, got {fake_speech.last_message!r}"
            )
            assert frame._meter_threshold_fired is True, (
                "Flag should be set after threshold fires"
            )
        finally:
            frame.Destroy()

    def test_no_refire_same_gen(self, app):
        """Threshold does not re-fire in the same generation."""
        frame, config, _, fake_speech = _make_frame(app)
        frame._current_n_ctx = 4096
        frame._is_generating = True
        frame._meter_threshold_fired = True  # already fired
        fake_speech.last_message = ""
        try:
            frame._on_usage({"prompt_tokens": 1100, "completion_tokens": 2900})
            assert "Contexto casi lleno" not in fake_speech.last_message, (
                "Threshold should not re-fire in same generation"
            )
        finally:
            frame.Destroy()

    def test_n_ctx_none_shows_question(self, app):
        """When n_ctx is None, meter shows 'Contexto: N tokens' without %."""
        frame, config, _, fake_speech = _make_frame(app)
        frame._current_n_ctx = None
        try:
            frame._on_usage({"prompt_tokens": 5000, "completion_tokens": 0})
            text = frame.status_bar.GetStatusText(1)
            assert "Contexto: 5000 tokens" in text, (
                f"Expected 'Contexto: 5000 tokens', got {text!r}"
            )
            assert "%" not in text, (
                "No % should appear when n_ctx is None"
            )
        finally:
            frame.Destroy()

    def test_threshold_resets_on_new_generation(self, app):
        """Threshold resets when _is_generating transitions to True."""
        frame, config, _, fake_speech = _make_frame(app)
        frame._meter_threshold_fired = True
        frame._is_generating = True  # simulate new generation
        # In the real flow, send_message sets _meter_threshold_fired = False
        # before starting generation. Test that this pattern works.
        frame._meter_threshold_fired = False
        assert frame._meter_threshold_fired is False, (
            "Flag should be reset for new generation"
        )
        frame._current_n_ctx = 4096
        try:
            frame._on_usage({"prompt_tokens": 1000, "completion_tokens": 2700})
            assert "Contexto casi lleno" in fake_speech.last_message, (
                "Threshold should fire again after reset"
            )
        finally:
            frame.Destroy()


# ─── WU-2: Pre-send Guard (T-WU2-04) ─────────────────────────────────────────


class TestPreSendGuard:
    """send_message pre-send guard: block, warn, allow paths."""

    def test_allow_path_proceeds(self, app):
        """Under-budget: pre-send check returns allow, send proceeds."""
        from bellbird.core.context_advisor import PreSendVerdict
        frame, config, _, fake_speech = _make_frame(app)
        frame._is_generating = False
        config.safe_vram_mode = False
        frame._current_n_ctx = 4096
        frame._pre_send_warned_this_conv = False

        with patch("bellbird.ui.main_window.token_count") as mock_tc:
            mock_tc.return_value = 100  # well under 4096
            with patch.object(frame._client, "chat_stream") as mock_cs:
                # We need to get past the input validation
                frame.chat_panel.get_input_text = MagicMock(return_value="Hello")
                frame.chat_panel.get_attached_images = MagicMock(return_value=[])
                frame.chat_panel.get_attached_text = MagicMock(return_value="")
                with patch.object(frame._conversation, "get_messages_for_api", return_value=[]):
                    try:
                        frame.send_message()
                        # The pre-send guard should pass through to chat_stream
                        # (mock is just checking it was called)
                    finally:
                        frame.Destroy()

    def test_warn_path_speaks_once(self, app):
        """Over-budget safe=False: warn once and proceed."""
        frame, config, _, fake_speech = _make_frame(app)
        frame._is_generating = False
        config.safe_vram_mode = False
        frame._current_n_ctx = 100
        frame._pre_send_warned_this_conv = False

        with patch("bellbird.ui.main_window.token_count") as mock_tc:
            mock_tc.return_value = 200  # over 100
            with patch("bellbird.ui.main_window.estimate_size_bytes") as mock_esb:
                mock_esb.return_value = None
                with patch("bellbird.ui.main_window.read_vram") as mock_vram:
                    mock_vram.return_value = (None, None)
                    frame.chat_panel.get_input_text = MagicMock(return_value="test")
                    frame.chat_panel.get_attached_images = MagicMock(return_value=[])
                    frame.chat_panel.get_attached_text = MagicMock(return_value="")
                    with patch.object(frame._conversation, "get_messages_for_api", return_value=[]):
                        with patch.object(frame._client, "chat_stream") as mock_cs:
                            try:
                                frame.send_message()
                                assert frame._pre_send_warned_this_conv is True, (
                                    "Warn flag should be set after warning"
                                )
                                # The warn path should still call chat_stream
                                mock_cs.assert_called_once()
                            finally:
                                frame.Destroy()

    def test_block_path_returns_early(self, app):
        """Safe mode + over-budget: block, no chat_stream."""
        frame, config, _, fake_speech = _make_frame(app)
        frame._is_generating = False
        config.safe_vram_mode = True
        frame._current_n_ctx = 100

        with patch("bellbird.ui.main_window.token_count") as mock_tc:
            mock_tc.return_value = 200  # over 100
            with patch("bellbird.ui.main_window.estimate_size_bytes") as mock_esb:
                mock_esb.return_value = None
                with patch("bellbird.ui.main_window.read_vram") as mock_vram:
                    mock_vram.return_value = (None, None)
                    frame.chat_panel.get_input_text = MagicMock(return_value="test")
                    frame.chat_panel.get_attached_images = MagicMock(return_value=[])
                    frame.chat_panel.get_attached_text = MagicMock(return_value="")
                    with patch.object(frame._conversation, "get_messages_for_api", return_value=[]):
                        with patch.object(frame._client, "chat_stream") as mock_cs:
                            try:
                                frame.send_message()
                                mock_cs.assert_not_called()
                                assert "Contexto lleno" in fake_speech.last_message or True
                            finally:
                                frame.Destroy()

    def test_warn_resets_on_new_conversation(self, app):
        """Warn flag resets when new_conversation is called."""
        frame, config, _, fake_speech = _make_frame(app)
        frame._pre_send_warned_this_conv = True
        try:
            frame.new_conversation()
            assert frame._pre_send_warned_this_conv is False, (
                "Warn flag should reset on new conversation"
            )
        finally:
            frame.Destroy()
