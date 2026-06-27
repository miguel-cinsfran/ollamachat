"""Server lifecycle mixin for MainWindow."""
from __future__ import annotations
import threading
from pathlib import Path

import wx

from bellbird.core.config import save_config
from bellbird.core.context_advisor import estimate_fit, read_vram
from bellbird.core.llama_runner import (
    auto_cuda_binary,
    download_server_binary,
    find_gguf_models,
    find_llama_server,
    get_install_command,
    start_server,
    stop_server,
)
from bellbird.core.logger import get_logger
from bellbird.core.model_meta import find_mmproj_for_model, read_gguf_metadata
from bellbird.core.startup import probe as startup_probe


class ServerMixin:
    """Server lifecycle methods — mixed into MainWindow."""

    def _on_use_model(self) -> None:
        """Start llama-server with the selected model in a background thread."""
        log = get_logger()
        # Guard: the F7 accelerator and the "Iniciar servidor" menu reach this
        # method directly, bypassing the disabled buttons. Without this guard a
        # second trigger while a load is in flight spawns a second server-start
        # thread and a second announce timer — the "se solapan" symptom.
        if self._is_loading_model:
            log.info("_on_use_model: ignored — a model load is already in flight")
            self._speech.speak(
                "Ya se está cargando un modelo, espera", interrupt=False
            )
            return

        model = self.get_model()
        if not model or not Path(model).is_file():
            log.warning("_on_use_model: model file not found: %r", model)
            self._speech.speak("Archivo de modelo no encontrado", interrupt=True)
            return
        basename = Path(model).name
        log.info("_on_use_model: requested load of %s", basename)

        # Resolve mmproj (multimodal projector) WITHOUT ever popping a file
        # dialog here. Vision is opt-in: priority is an explicit config entry,
        # then a sibling auto-detected by name; if neither exists we load the
        # model text-only. Forcing the user to pick a projector for every
        # (usually text-only) model was the cause of the "Usar modelo abre el
        # explorador" bug — and picking the model file itself by mistake then
        # made llama-server fail to load it as a projector.
        model_resolved = Path(model).resolve()
        mmproj_path: str | None = self._config.get_mmproj_for(model)
        # A model can never be its own projector. Drop a bad stored value
        # (a known way the old forced-dialog flow corrupted the config).
        if mmproj_path and Path(mmproj_path).resolve() == model_resolved:
            mmproj_path = None
            self._config.model_mmproj.pop(basename, None)
            try:
                save_config(self._config)
            except OSError:
                pass
        if mmproj_path is None:
            auto = find_mmproj_for_model(Path(model))
            if auto is not None and auto.resolve() != model_resolved:
                mmproj_path = str(auto)

        # Persist a valid projector (best-effort) so future loads skip detection.
        if mmproj_path is not None:
            self._config.model_mmproj[basename] = str(Path(mmproj_path).resolve())
            try:
                save_config(self._config)
            except OSError:
                pass  # best-effort persistence

        # Restore per-model tunings (T-WU2-07). Track whether a saved profile
        # was applied so the load announcement can make the per-model config
        # discoverable (the user asked for an audible "this model uses N ctx").
        applied_saved_tuning = False
        if basename in self._config.model_tunings:
            saved = self._config.model_tunings[basename]
            if "ctx_size" in saved:
                self._config.ctx_size = saved["ctx_size"]
                applied_saved_tuning = True
            if "n_gpu_layers" in saved:
                self._config.n_gpu_layers = saved["n_gpu_layers"]
                applied_saved_tuning = True

        log.info(
            "_on_use_model: starting server — model=%s mmproj=%s ctx=%s ngl=%s port=%s",
            basename, mmproj_path, self._config.ctx_size,
            self._config.n_gpu_layers, self._config.port,
        )
        self._is_loading_model = True
        self._play_loop("connecting")  # warm loop until the server responds
        self.use_model_button.Disable()
        self.restart_server_button.Disable()
        if applied_saved_tuning:
            self._speech.speak(
                f"Iniciando servidor con {basename}. "
                f"Configuración guardada de este modelo: contexto "
                f"{self._config.ctx_size} tokens.",
                interrupt=True,
            )
        else:
            self._speech.speak(
                f"Iniciando servidor con {basename}...", interrupt=True
            )
        self.status_bar.SetStatusText("Iniciando servidor...", 0)
        # Cancel any stale loading timer before arming a new one (defensive —
        # the _is_loading_model guard above already prevents the common race).
        if self._loading_timer is not None:
            self._loading_timer.cancel()
        self._loading_timer = self._make_announce_timer()
        self._model_load_thread = threading.Thread(
            target=self._model_load_worker,
            args=(model, mmproj_path),
            daemon=True,
        )
        self._model_load_thread.start()

    def _model_load_worker(self, model: str, mmproj_path: str | None = None) -> None:
        """Background thread worker for starting the server.

        `ok` and `message` are bound to safe defaults BEFORE the try so
        the finally block can call `_on_start_server_done` even if
        `start_server` raises. Without the defaults, an exception in
        `start_server` triggers `UnboundLocalError` in the finally
        block, the worker thread dies silently, and the buttons stay
        disabled forever.
        """
        ok = False
        message = "Error: start_server raised an exception"
        try:
            ok, message = start_server(
                model, self._client,
                port=self._config.port,
                ctx_size=self._config.ctx_size,
                n_gpu_layers=self._config.n_gpu_layers,
                mmproj=mmproj_path,
                server_binary=self._effective_server_binary(),
            )
        except Exception as e:
            message = f"Error: {type(e).__name__}: {e}"
        finally:
            if self._loading_timer is not None:
                self._loading_timer.cancel()
            vision_flag = ok and (mmproj_path is not None)
            wx.CallAfter(self._on_start_server_done, ok, message, vision_flag)

    def _on_select_mmproj(self) -> None:
        """Open a file dialog to assign an mmproj to the currently loaded model.

        Opt-in only — never called automatically on model load (that was
        the 'bug madre' that showed the dialog on every load).
        """
        model_path = self.get_model()
        if not model_path:
            self._speech.speak("No hay modelo seleccionado.", interrupt=True)
            return
        basename = Path(model_path).name
        default_dir = str(Path(model_path).parent) if Path(model_path).is_file() else str(Path.home() / "models")
        dlg = wx.FileDialog(
            self,
            message=f"Seleccionar mmproj para {Path(model_path).stem}",
            defaultDir=default_dir,
            wildcard="Archivos GGUF (*.gguf)|*.gguf",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        mmproj_path = dlg.GetPath()
        dlg.Destroy()
        if Path(mmproj_path).resolve() == Path(model_path).resolve():
            self._speech.speak("El mmproj no puede ser el mismo archivo que el modelo.", interrupt=True)
            return
        self._config.model_mmproj[basename] = str(Path(mmproj_path).resolve())
        try:
            from bellbird.core.config import save_config
            save_config(self._config)
        except Exception:
            get_logger().exception("_on_select_mmproj: failed to save config")
        stem = Path(mmproj_path).stem
        self._speech.speak(
            f"mmproj guardado: {stem}. Recarga el modelo para activar visión.",
            interrupt=True,
        )

    def _on_download_gpu_server(self, variant: str = "cuda") -> None:
        """Download and activate a GPU build of llama-server.

        variant: "cuda" → CUDA 13.3 (~550 MB, NVIDIA only, fastest)
                 "vulkan" → Vulkan (~32 MB, NVIDIA/AMD/Intel)
        """
        if self._downloading_gpu:
            self._speech.speak("Hay una descarga en progreso, espere...", interrupt=True)
            return

        import os as _os
        local = _os.environ.get("LOCALAPPDATA", str(Path.home()))
        if variant == "cuda":
            dest_dir = Path(local) / "Bellbird" / "llama-server-cuda"
            label = "CUDA (RTX)"
            variant_key = "cuda-13.3"
            title_hint = "~550 MB"
        else:
            dest_dir = Path(local) / "Bellbird" / "llama-server-vulkan"
            label = "Vulkan (GPU)"
            variant_key = "vulkan"
            title_hint = "~32 MB"

        exe_path = dest_dir / "llama-server.exe"
        if exe_path.exists() and self._config.llama_server_path == str(exe_path):
            self._speech.speak(f"La versión {label} ya está activa.", interrupt=True)
            return

        self._downloading_gpu = True

        self._gpu_progress_dlg = wx.ProgressDialog(
            f"Descargando llama-server {label} ({title_hint})",
            "Conectando con GitHub...",
            maximum=100,
            parent=self,
            style=wx.PD_APP_MODAL | wx.PD_ELAPSED_TIME,
        )

        def _progress_cb(lbl: str, done: int, total: int) -> None:
            if total > 0:
                msg = f"{lbl}: {done // 1_000_000} MB / {total // 1_000_000} MB"
            else:
                msg = lbl
            wx.CallAfter(self._pulse_gpu_progress, msg)

        def _worker() -> None:
            ok, result = download_server_binary(variant_key, dest_dir, progress_cb=_progress_cb)
            wx.CallAfter(self._on_download_gpu_done, ok, result, label)

        threading.Thread(target=_worker, daemon=True).start()

    def _pulse_gpu_progress(self, msg: str) -> None:
        """Update the download progress dialog (called on UI thread via CallAfter)."""
        if self._gpu_progress_dlg is not None:
            self._gpu_progress_dlg.Pulse(msg)

    def _on_download_gpu_done(self, ok: bool, result: str, label: str = "GPU") -> None:
        """Called on the UI thread when the GPU binary download finishes."""
        self._downloading_gpu = False
        if self._gpu_progress_dlg is not None:
            self._gpu_progress_dlg.Destroy()
            self._gpu_progress_dlg = None

        if not ok:
            self._speech.speak(f"Error al descargar: {result}", interrupt=True)
            return

        self._config.llama_server_path = result
        try:
            from bellbird.core.config import save_config
            save_config(self._config)
        except Exception:
            get_logger().exception("_on_download_gpu_done: failed to save config")

        self._speech.speak(
            f"Descarga completada. llama-server {label} activado. "
            "Los próximos modelos usarán la tarjeta gráfica.",
            interrupt=True,
        )

    def _on_use_system_server(self) -> None:
        """Revert to the system llama-server binary (from PATH / winget)."""
        if not self._config.llama_server_path:
            self._speech.speak("Ya se está usando el llama-server del sistema.", interrupt=True)
            return

        self._config.llama_server_path = ""
        try:
            from bellbird.core.config import save_config
            save_config(self._config)
        except Exception:
            get_logger().exception("_on_use_system_server: failed to save config")

        self._speech.speak(
            "Volviendo al llama-server del sistema (instalado por winget, solo CPU).",
            interrupt=True,
        )

    def _on_clear_mmproj(self) -> None:
        """Remove the saved mmproj assignment for the currently selected model."""
        model_path = self.get_model()
        if not model_path:
            self._speech.speak("No hay modelo seleccionado.", interrupt=True)
            return
        basename = Path(model_path).name
        if basename not in self._config.model_mmproj:
            self._speech.speak(
                f"El modelo {Path(model_path).stem} no tiene mmproj asignado.",
                interrupt=True,
            )
            return
        del self._config.model_mmproj[basename]
        try:
            from bellbird.core.config import save_config
            save_config(self._config)
        except Exception:
            get_logger().exception("_on_clear_mmproj: failed to save config")
        self._speech.speak(
            f"mmproj eliminado de {Path(model_path).stem}. "
            "El modelo cargará sin visión hasta que asignes otro.",
            interrupt=True,
        )

    def _on_start_server_done(self, ok: bool, message: str, vision_capable: bool = False) -> None:
        """Handle the result of background server start."""
        get_logger().info(
            "_on_start_server_done: ok=%s vision=%s message=%r",
            ok, vision_capable, message,
        )
        self._is_loading_model = False
        self._stop_loop()  # end the "connecting" loop; success/fail cue follows
        self._vision_capable = vision_capable
        if self._loading_timer is not None:
            self._loading_timer.cancel()
            self._loading_timer = None
        if self._is_closing:
            return
        if ok:
            self.status_bar.SetStatusText("Servidor listo", 0)
            loaded = self._client.get_loaded_model()
            self._loaded_model_name = loaded or ""
            self._server_state_cache = "ready"
            self._update_title(loaded or None)
            if loaded:
                self._persist_last_model(Path(loaded).name)
            self._sync_button_state(ok)
            # Fetch context window + VRAM + fit off the UI thread so F2 can show
            # a real "used/total (%)", free VRAM and fit — these fields were
            # never populated before, so those toggles always rendered empty.
            self._fetch_server_meta_async()
            # ONE clear success announcement, spoken last. We deliberately do
            # NOT re-scan models here: the selector is already populated from
            # startup, and _scan_models' async "N modelos encontrados" landed
            # after this line and clobbered it, so the user never heard whether
            # the server actually connected.
            if loaded:
                # output() = voz + braille, so the model name reaches a braille
                # display. Safe now that the clobbering _scan_models() re-announce
                # is gone.
                vision_suffix = " con visión" if vision_capable else ""
                gpu_suffix = ""
                backend = self._active_server_backend()
                if backend:
                    gpu_suffix = f", {backend}"
                self._speech.output(
                    f"Servidor listo. Modelo {Path(loaded).stem}{vision_suffix}{gpu_suffix}"
                )
            else:
                self._speech.output("Servidor listo")
            self._notifier.notify("server_ready", "Servidor listo")
        else:
            self.status_bar.SetStatusText("Error al iniciar", 0)
            self._server_state_cache = "dead"
            self._loaded_model_name = ""
            self._current_n_ctx = None
            self._sync_button_state(ok)
            self._play_cue("error")
            self._speech.speak(message, interrupt=True)

    def _fetch_server_meta_async(self) -> None:
        """Fetch n_ctx + VRAM + fit on a daemon thread; store via CallAfter.

        Populates the F2 fields that were never wired before: context window
        (``_current_n_ctx``), free/total VRAM, and the fit estimate. Without
        this the ``vram`` and ``fit`` status toggles existed in Preferences but
        always rendered empty. ``get_model()`` is read here on the UI thread
        (it touches the combo box) and captured for the worker.
        """
        model_path = self.get_model()
        ctx_size = self._config.ctx_size

        def worker() -> None:
            n_ctx = self._client.get_n_ctx()
            free, total = read_vram()
            fit_status: str | None = None
            try:
                if model_path:
                    meta = read_gguf_metadata(model_path)
                    if meta is not None:
                        fit_status = estimate_fit(meta, ctx_size, free).status
            except Exception:
                fit_status = None
            wx.CallAfter(
                self._on_server_meta_fetched, n_ctx, free, total, fit_status
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_server_meta_fetched(
        self, n_ctx: int | None, vram_free: int | None,
        vram_total: int | None, fit_status: str | None,
    ) -> None:
        """Store fetched server/VRAM metadata on the main thread (for F2)."""
        if self._is_closing:
            return
        self._current_n_ctx = n_ctx
        self._vram_free_mb = vram_free
        self._vram_total_mb = vram_total
        self._fit_status = fit_status
        get_logger().info(
            "server meta: n_ctx=%s vram=%s/%s fit=%s",
            n_ctx, vram_free, vram_total, fit_status,
        )

    def _persist_last_model(self, basename: str) -> None:
        """Save the just-loaded model basename to the persisted config.

        Called from the main thread (via wx.CallAfter) on successful load.
        Best-effort: a write failure is logged but never blocks the UI.
        """
        if basename and self._config.last_model != basename:
            self._config.last_model = basename
            try:
                save_config(self._config)
            except OSError as e:
                get_logger().warning(f"Failed to persist last_model: {e}")

    def _update_title(self, model: str | None) -> None:
        """Update the window title to show the loaded model."""
        if model:
            self.SetTitle(f"Bellbird — {Path(model).stem}")
        else:
            self.SetTitle("Bellbird")

    # ── Startup ────────────────────────────────────────────────────────────

    def _start_probe_thread(self) -> None:
        """Run the startup probe on a daemon thread.

        Spawns a daemon thread that calls ``core.startup.probe()`` and
        posts the result back via ``wx.CallAfter``. The window is already
        shown before any I/O, so the user sees "Iniciando…" immediately.
        """
        import bellbird.core.llama_runner as runner_mod

        def worker() -> None:
            result = startup_probe(self._client, runner_mod)
            wx.CallAfter(self._on_startup_probe_done, result)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_startup_probe_done(self, result) -> None:
        """Handle the startup probe result on the main thread.

        Updates the status bar, speaks the outcome, and triggers a
        background model scan. Early-returns if the window is closing.
        """
        if self._is_closing:
            return

        log = get_logger()

        if result.server_path is None:
            log.warning("Startup: llama-server not installed")
            install_cmd = get_install_command()
            msg = (
                f"llama-server no instalado. "
                f"Instalalo con: {install_cmd}."
            )
            self.status_bar.SetStatusText("llama-server no instalado", 0)
            self._speech.speak(msg, interrupt=True)
            wx.MessageDialog(
                self,
                message=msg,
                caption="llama-server no instalado",
                style=wx.OK | wx.ICON_WARNING,
            ).ShowModal()
            # Still scan models — the user may have a portable install
            self._scan_models()
            return

        if not result.is_running:
            log.info("Startup: llama-server installed but not running")
            self.status_bar.SetStatusText("Servidor detenido", 0)
            self._speech.speak(
                "Servidor detenido. "
                "Selecciona un modelo y pulsa Iniciar servidor.",
                interrupt=True,
            )
            self._scan_models()
            return

        # Server is running and healthy
        loaded = result.loaded_model or ""
        log.info("Startup: connected, model=%r", loaded)
        self._loaded_model_name = loaded
        self._server_state_cache = "ready"
        self._fetch_server_meta_async()
        if loaded:
            self.status_bar.SetStatusText(f"Conectado: {loaded}", 0)
        else:
            self.status_bar.SetStatusText("Conectado", 0)
        self._sync_button_state(True)
        if loaded:
            self._speech.output(f"Modelo: {Path(loaded).stem}")
            self._notifier.notify("model_loaded", Path(loaded).stem)
        else:
            self._speech.speak(
                "Conectado. Sin modelo cargado.", interrupt=True,
            )
        self._scan_models()

    def _scan_models(self) -> None:
        """Scan for .gguf files on a background thread.

        Launches a daemon thread that calls ``find_gguf_models()`` and
        posts the result via ``wx.CallAfter``. Avoids blocking the main
        thread during filesystem traversal.
        """
        def worker() -> None:
            paths = find_gguf_models()
            wx.CallAfter(self._on_scan_done, paths)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_scan_done(self, paths: list[str]) -> None:
        """Handle the model scan result on the main thread."""
        if self._is_closing:
            return
        log = get_logger()
        self.set_models(paths)
        if paths:
            log.info(f"Scan: {len(paths)} .gguf file(s) found")
            self._speech.speak(
                f"{len(paths)} modelos encontrados", interrupt=True,
            )
        else:
            log.warning("Scan: no .gguf files found")
            self._speech.speak(
                "Ningún modelo .gguf encontrado", interrupt=True,
            )

    def _on_start_server(self) -> None:
        """Start llama-server with the selected model."""
        log = get_logger()
        log.info("Start server button clicked")

        model_path = self.get_model()
        if not model_path:
            msg = "Selecciona primero un modelo .gguf"
            self._speech.speak(msg, interrupt=True)
            return

        # D3: fail fast if the .gguf file does not exist on disk.
        # Otherwise llama-server would launch, fail to load the model,
        # and the user would wait the full 60-second timeout for nothing.
        if not Path(model_path).is_file():
            msg = f"No se encontró el archivo: {model_path}"
            log.error(f"Start server: model file not found: {model_path}")
            self._speech.speak(msg, interrupt=True)
            wx.MessageDialog(
                self,
                message=msg,
                caption="Archivo no encontrado",
                style=wx.OK | wx.ICON_ERROR,
            ).ShowModal()
            return

        self._on_use_model()

    def _on_stop_server(self) -> None:
        """Stop the running llama-server."""
        log = get_logger()
        log.info("Stop server button clicked")

        self._vision_capable = False
        self._server_state_cache = "dead"
        self._loaded_model_name = ""
        self._current_n_ctx = None
        self.status_bar.SetStatusText("Deteniendo servidor...", 0)
        self._speech.speak("Deteniendo servidor...", interrupt=True)

        stop_server()

        self.status_bar.SetStatusText("Servidor detenido", 0)
        self._play_cue("server_stopped")
        self._speech.speak("Servidor detenido", interrupt=True)
        self._sync_button_state(False)
        self._update_title(None)

    def _effective_server_binary(self) -> str | None:
        """Resolve which llama-server binary to use.

        Priority: manual config > auto-CUDA (if downloaded) > system PATH (None).
        """
        if self._config.llama_server_path:
            return self._config.llama_server_path
        return auto_cuda_binary()

    def _active_server_backend(self) -> str:
        """Return a short label for the active llama-server backend, or ''."""
        path = self._effective_server_binary() or ""
        if not path:
            return ""
        parent = Path(path).parent.name.lower()
        if "cuda" in parent:
            return "GPU CUDA"
        if "vulkan" in parent:
            return "GPU Vulkan"
        return ""

    def _run_connection_watchdog(self, error_text: str) -> None:
        """Check server state on a daemon thread for connection errors.

        Spawns a daemon thread that calls ``check_state()`` and posts the
        result back via ``wx.CallAfter``. Never blocks the main thread.
        """
        def watchdog_worker() -> None:
            try:
                state = self._client.check_state()
            except Exception:
                state = "dead"
            wx.CallAfter(self._on_server_state_checked, state, error_text)

        t = threading.Thread(target=watchdog_worker, daemon=True)
        t.start()

    def _on_server_state_checked(
        self, state: str, error_text: str = ""
    ) -> None:
        """Handle the result of a connection watchdog server-state check.

        Args:
            state: One of ``"dead"``, ``"loading"``, or ``"ready"``.
            error_text: The original error text from the stream (for logging).
        """
        log = get_logger()
        log.info(
            "_on_server_state_checked: state=%r error=%r",
            state, error_text[:80] if error_text else "",
        )
        # Keep the F2 cache honest with what the watchdog just observed.
        self._server_state_cache = state

        # During an in-flight model load the server is briefly unreachable;
        # check_state() returns "dead" (connection refused) even though it is
        # really just starting. Don't cry "servidor caído" — that produced the
        # spurious restart dialog during a hot model swap.
        if self._is_loading_model:
            log.info("_on_server_state_checked: ignoring %r — model load in flight", state)
            self._speech.speak(
                "Cargando modelo, por favor espera…", interrupt=True
            )
            return

        if state == "dead":
            self._speech.speak(
                "El servidor se detuvo. ¿Reiniciar?", interrupt=True
            )
            self._notifier.notify("error", "Servidor caído")
            self._show_restart_dialog()
        elif state == "loading":
            self._speech.speak(
                "Cargando modelo, por favor espera…", interrupt=True
            )
        else:
            # "ready" — transient error, show existing error dialog
            wx.MessageDialog(
                self,
                message=error_text,
                caption="Error",
                style=wx.OK | wx.ICON_ERROR,
            ).ShowModal()
            self._speech.speak(error_text, interrupt=True)

    def _show_restart_dialog(self) -> None:
        """Show a native wx.Dialog offering to restart the server.

        Uses only ``wx.BoxSizer`` (H/V), no ``wx.MessageDialog`` with
        custom Spanish labels (MSAA regression per AGENTS.md). Focus is
        set on the "Sí" button after ``Fit()``.
        """
        dlg = wx.Dialog(
            self,
            name="server_down_dialog",
            title="Servidor no disponible",
        )
        label = wx.StaticText(
            dlg, label="El servidor se detuvo. ¿Reiniciar?"
        )
        yes_btn = wx.Button(
            dlg, label="Sí, reiniciar", name="restart_yes_button"
        )
        no_btn = wx.Button(
            dlg, label="No, salir", name="restart_no_button"
        )

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(yes_btn, flag=wx.RIGHT, border=8)
        btn_sizer.Add(no_btn)

        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(
            label, flag=wx.ALL | wx.ALIGN_CENTER, border=16
        )
        root_sizer.Add(
            btn_sizer, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=8
        )
        dlg.SetSizer(root_sizer)

        dlg.Fit()
        yes_btn.SetFocus()

        yes_btn.Bind(
            wx.EVT_BUTTON, lambda evt: dlg.EndModal(wx.ID_YES)
        )
        no_btn.Bind(
            wx.EVT_BUTTON, lambda evt: self._on_restart_no(dlg)
        )

        get_logger().info("_show_restart_dialog: shown")
        result = dlg.ShowModal()
        get_logger().info(
            "_show_restart_dialog: choice=%s", "restart" if result == wx.ID_YES else "exit"
        )
        if result == wx.ID_YES:
            self._on_use_model()
        dlg.Destroy()

    def _on_restart_no(self, dlg: wx.Dialog) -> None:
        """User clicked 'No, salir' — clean up generation state."""
        self._is_generating = False
        self._current_response = ""
        self.status_bar.SetStatusText("Servidor detenido", 0)
        dlg.EndModal(wx.ID_NO)
