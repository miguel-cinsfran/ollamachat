"""Streaming and tool-calling mixin for MainWindow."""
from __future__ import annotations
import json
import threading

import wx

from bellbird.core.context_advisor import PreSendSnapshot, pre_send_check, read_vram, token_count
from bellbird.core.logger import get_logger
from bellbird.core.model_meta import estimate_size_bytes
from bellbird.core.payload import build_api_messages, build_options
from bellbird.core.tool_catalog import (
    FILE_TOOL_NAMES,
    FILE_TOOL_RISK,
    display_command,
    get_enabled_tools,
)
from bellbird.ui.permission_dialog import PermissionDialog


class StreamMixin:
    """Streaming + tool-call methods — mixed into MainWindow."""

    def send_message(self) -> None:
        """Build API payload and start streaming.

        Accepts plain text, text with images, or images only. If neither
        text nor images are present, the message is ignored.
        """
        self._aborted = False  # Reset abort flag before each new generation
        if self._is_generating or self._tool_executing or self._preparing_send:
            self._speech.speak("Ya se está generando una respuesta", interrupt=False)
            return

        # Don't fire a request while the server is still loading a model: it
        # would only raise ConnectionError (server not accepting yet) and
        # spuriously trip the "servidor caído" watchdog. This is the common
        # case during a hot model swap.
        if self._is_loading_model:
            self._speech.speak(
                "El servidor aún está cargando el modelo, espera un momento",
                interrupt=True,
            )
            return

        # Read input and attachments
        user_text = self.chat_panel.get_input_text()
        attached_images = self.chat_panel.get_attached_images()
        attached_text = self.chat_panel.get_attached_text()

        # C3: allow empty text if there are images attached
        if not user_text.strip() and not attached_images:
            return

        self._play_cue("message_sent")

        # REQ-MULTI-003: drop images when model is not vision-capable
        if attached_images and not self._vision_capable:
            try:
                self._speech.speak(
                    "Aviso: el modelo actual no procesa imágenes. "
                    "Adjunto enviado sin imagen.",
                    interrupt=True,
                )
            except Exception:
                pass  # Speech failures must never crash the send path
            attached_images = []

        # Build API messages (system prompt + history; user message appended below)
        api_messages = build_api_messages(self._config, self._conversation)

        # New user message
        user_msg: dict
        if attached_images:
            # C5: build OpenAI content-array, incorporating text and attached_text
            parts: list[dict] = []
            if user_text.strip():
                parts.append({"type": "text", "text": user_text})
            if attached_text:
                parts.append({
                    "type": "text",
                    "text": f"[Contenido del archivo adjuntado]\n{attached_text}",
                })
            for b64, mime in attached_images:
                url = f"data:{mime};base64,{b64}"
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })
            user_msg = {"role": "user", "content": parts}
        else:
            # Plain text path (with or without attached_text)
            if attached_text:
                content = (
                    f"{user_text}\n\n"
                    f"[Contenido del archivo adjuntado]\n{attached_text}"
                )
            else:
                content = user_text
            user_msg = {"role": "user", "content": content}
        api_messages.append(user_msg)

        # Clear input and attachment
        self.chat_panel._clear_input()
        self.chat_panel.clear_attachment()

        # C4: store plain text in Conversation, NOT the content-array.
        # For image messages, store a short marker so the conversation log
        # round-trips and the user can see images were sent.
        if attached_images:
            n = len(attached_images)
            if user_text.strip():
                stored = f"{user_text} [imagen adjunta: {n}]"
            else:
                stored = f"[imagen adjunta: {n}]"
        else:
            stored = user_msg["content"]  # str in this branch
        self._conversation.add_message("user", stored)

        # Display: show the text or a marker when sending images only
        if user_text.strip():
            self.chat_panel.append_user_message(user_text)
        else:
            self.chat_panel.append_user_message("[imagen enviada]")

        # ── Pre-send prep (off the UI thread) ──────────────────────────
        # token_count (/tokenize HTTP), read_vram (nvidia-smi subprocess) and
        # check_tool_support (/props HTTP) used to run synchronously here and
        # froze NVDA for 2-3 s on every send. Move them to a daemon thread and
        # resume in _continue_send via wx.CallAfter. _preparing_send blocks a
        # second enviar during the window without faking _is_generating.
        joined_text = user_text
        if attached_text:
            joined_text = f"{user_text}\n\n{attached_text}" if user_text.strip() else attached_text
        model_path = self.get_model()
        tools = get_enabled_tools(self._config)
        self._preparing_send = True

        def prep_worker() -> None:
            try:
                vram_free = (
                    read_vram()[0] if self._vram_free_mb is None else self._vram_free_mb
                )
                model_bytes = estimate_size_bytes(model_path) if model_path else None
                token_est = token_count(
                    joined_text, self._client.base_url, self._client._session, timeout=5.0
                ) or 0
                tool_support = bool(self._client.check_tool_support()) if tools else False
            except Exception:
                # Never strand the send path: fall back to permissive defaults.
                get_logger().exception("send_message prep_worker failed")
                vram_free, model_bytes, token_est, tool_support = (
                    self._vram_free_mb, None, 0, bool(tools),
                )
            wx.CallAfter(
                self._continue_send,
                api_messages, tools, vram_free, model_bytes, token_est, tool_support,
                user_text,
            )

        threading.Thread(target=prep_worker, daemon=True).start()

    def _continue_send(
        self,
        api_messages: list[dict],
        tools,
        vram_free: int | None,
        model_bytes: int | None,
        token_est: int,
        tool_support: bool,
        user_text: str,
    ) -> None:
        """Resume send_message on the UI thread after background prep.

        Runs the pre-send verdict and, if allowed, starts streaming. Always
        clears ``_preparing_send`` so a blocked/aborted send does not wedge the
        re-entry guard.
        """
        self._preparing_send = False
        if self._is_closing:
            return
        log = get_logger()

        presend_snap = PreSendSnapshot(
            estimated_tokens=token_est,
            n_ctx=self._current_n_ctx,
            safe_mode=self._config.safe_vram_mode,
            warn_once=self._pre_send_warned_this_conv,
            vram_free_mb=vram_free,
            model_size_bytes=model_bytes,
        )
        verdict = pre_send_check(presend_snap)
        if verdict.decision == "block":
            self._speech.speak(
                verdict.reason_es or "Contexto lleno; iniciá nueva conversación",
                interrupt=True,
            )
            return
        elif verdict.decision == "warn":
            self._speech.speak(
                verdict.reason_es or "Vas a exceder el contexto",
                interrupt=True,
            )
            self._pre_send_warned_this_conv = True
        # "allow" → proceed silently

        # Reset context meter threshold for the new generation
        self._meter_threshold_fired = False

        # Start generation
        options = build_options(self._config)
        self._current_response = ""
        self._current_reasoning = ""

        self.chat_panel.start_generation()
        self._is_generating = True

        log.info(
            "send_message: user text=%r tools_enabled=%s",
            (user_text[:60] + "...") if len(user_text) > 60 else user_text,
            self._config.tools_enabled,
        )
        self.status_bar.SetStatusText("Generando respuesta...", 2)
        self._speech.speak("Generando respuesta...", interrupt=True)

        self._tool_iteration_count = 0
        if tools and not tool_support:
            tools = None
            # Announce ONCE per model, and never with interrupt=True: it used
            # to fire on every send 1 ms after "Generando respuesta…", cutting
            # that off so the user heard nothing useful when pressing enviar.
            model_key = self.get_model()
            if model_key not in self._tool_support_warned:
                self._tool_support_warned.add(model_key)
                try:
                    self._speech.speak(
                        "Plantilla del modelo no soporta herramientas. Desactivado.",
                        interrupt=False,
                    )
                except Exception:
                    pass

        self._client.chat_stream(
            messages=api_messages,
            options=options,
            on_token=self._on_token,
            on_done=self._on_done,
            on_error=self._on_error,
            on_usage=self._on_usage,
            on_timings=self._on_timings,
            on_tool_call=self._on_tool_call,
            tools=tools,
            on_reasoning=self._on_reasoning,
        )

    def _on_history_delete(self, index: int, role: str) -> None:
        """Sync Conversation.messages with the deleted history entry.

        Called by ChatPanel._on_context_delete after the user deletes
        a message from the history list. System-role rows (tool blocked/
        denied) are UI-only and have no Conversation counterpart.

        Args:
            index: Pre-pop position in _history of the deleted entry.
            role: Role of the deleted entry.
        """
        if role == "system":
            return
        system_count = sum(
            1 for r, _ in self.chat_panel._history[:index] if r == "system"
        )
        conv_index = index - system_count
        if 0 <= conv_index < len(self._conversation.messages):
            self._conversation.messages.pop(conv_index)

    def _on_token(self, token: str) -> None:
        """Handle a content token fragment from the stream.

        Reasoning content is routed via ``_on_reasoning`` and must NOT
        reach this callback. The ``_stream_worker`` guarantees this:
        ``delta.reasoning_content`` and parser-emitted reasoning slices
        go to ``on_reasoning`` only.

        Args:
            token: Content token text from the LLM.
        """
        if not self._is_generating:
            return
        self._current_response += token
        self.chat_panel.update_streaming_preview(self._current_response)
        self._maybe_beep()
        self._speech.announce_token_chunk(token)

    def _on_reasoning(self, reasoning_text: str) -> None:
        """Handle a reasoning fragment from the stream.

        Reasoning is never read aloud by default. On the first chunk
        of a turn, ``"Pensando…"`` is spoken once to indicate the model
        is thinking. Subsequent chunks are accumulated silently.

        MUST NOT update ``_current_response`` and MUST NOT call
        ``chat_panel.update_streaming_preview`` — reasoning is not
        displayed in the chat list.

        Args:
            reasoning_text: A reasoning/chain-of-thought fragment.
        """
        if not self._is_generating:
            return
        if not self._current_reasoning:
            # First reasoning chunk of this turn — announce once
            self._speech.speak("Pensando…", interrupt=False)
        self._current_reasoning += reasoning_text

    def _on_done(self) -> None:
        """Handle stream completion or abort confirmation."""
        # Abort path: check FIRST so an aborted generation is never
        # saved as "Respuesta completa". This is additive to the
        # v0.4.1 two-layer race defense (self._is_generating guard).
        if self._aborted:
            self._speech.speak("Generación detenida", interrupt=True)
            self.chat_panel.end_generation()
            self._current_response = ""
            self._current_reasoning = ""
            self._aborted = False
            self.status_bar.SetStatusText("", 2)
            return

        if not self._is_generating:
            return
        log = get_logger()
        log.info("_on_done: response_len=%d chars", len(self._current_response))
        self._speech.flush_token_buffer()
        if not self._tool_executing:
            self._speech.speak("Respuesta completa", interrupt=True)
            self._notifier.notify("generation_complete", "Respuesta completa")

        # Save assistant message to conversation (including reasoning).
        # Skip when a tool call is pending: _on_tool_result will save the
        # correct assistant+tool_calls message with the full content.
        if self._current_response.strip() and not self._tool_executing:
            self._conversation.add_message(
                "assistant", self._current_response,
                reasoning=self._current_reasoning,
            )

        # Focus courtesy: capture the streaming index before it is
        # reset by end_generation(). Only SetSelection back to the
        # streaming row if the user is still on the placeholder.
        # If they navigated away, don't steal their position.
        cp = self.chat_panel
        last_streaming_idx = cp._streaming_index
        do_focus = (
            last_streaming_idx is not None
            and cp.message_list.GetSelection() == last_streaming_idx
        )

        # Promote placeholder to final preview
        self.chat_panel.end_generation(final_text=self._current_response)

        if do_focus:
            cp.message_list.SetSelection(last_streaming_idx)

        self._is_generating = False
        self.status_bar.SetStatusText("", 2)
        # When a tool call is pending, _on_tool_result still needs
        # _current_response to build the assistant+tool_calls message.
        if not self._tool_executing:
            self._current_response = ""
            self._current_reasoning = ""

    # ── Tool calling (v0.4.0) ─────────────────────────────────────────────

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict) -> None:
        """Callback cuando el modelo solicita ejecutar una herramienta."""
        self._tool_executing = True
        command = display_command(tool_name, args)

        if self._permission_manager.is_system_destructive(command):
            self._speech.speak(
                f"Comando bloqueado por seguridad: {command[:80]}", interrupt=True
            )
            self.chat_panel.append_tool_blocked(tool_name, command)
            self._finish_tool_turn()
            return

        if tool_name in FILE_TOOL_NAMES:
            risk = FILE_TOOL_RISK[tool_name]
        else:
            risk = self._permission_manager.classify_risk(command)

        if self._permission_manager.has_session_grant(tool_name, risk):
            self._speech.speak(
                f"Ejecutando {tool_name}: {command[:50]}", interrupt=True
            )
            self._run_tool_and_show(tool_name, tool_call_id, command, args)
            return

        self._speech.speak(
            "El modelo quiere ejecutar un comando. Escucha el comando y confirma.",
            interrupt=True,
        )
        self._notifier.notify(
            "tool_request", "El modelo quiere ejecutar un comando",
        )
        dlg = PermissionDialog(
            self, tool_name, command, risk,
            permission_manager=self._permission_manager,
            speech=self._speech,
        )
        result = dlg.ShowModal()
        edited_cmd = dlg.get_command()
        dlg.Destroy()

        if result == wx.ID_YES:
            self._run_tool_and_show(tool_name, tool_call_id, edited_cmd, args)
        elif result == wx.ID_OK:
            self._permission_manager.grant_session(tool_name, dlg.get_risk())
            self._run_tool_and_show(tool_name, tool_call_id, edited_cmd, args)
        else:
            self._speech.speak("Ejecución denegada.", interrupt=True)
            self.chat_panel.append_tool_denied(tool_name)
            self._finish_tool_turn()

    def _finish_tool_turn(self) -> None:
        """Reset generation state when a tool call ends WITHOUT continuing.

        Blocked or denied tools end the model's turn. If we don't clear the
        generating flags here, ``send_message``'s guard stays armed and the
        user "can't type anything" — the freeze reported after denying a
        command. We also hand focus back to the input. Idempotent and safe to
        race with ``_on_done`` (which early-returns once ``_is_generating`` is
        False).
        """
        self._tool_executing = False
        self._is_generating = False
        if self.chat_panel._is_generating:
            self.chat_panel.end_generation()
        self.status_bar.SetStatusText("", 2)
        try:
            self.chat_panel.message_input.SetFocus()
        except Exception:
            pass

    def _run_tool_and_show(
        self, tool_name: str, tool_call_id: str, command: str,
        args: dict | None = None,
    ) -> None:
        """Ejecuta la tool en hilo de fondo para no bloquear la UI."""
        # Show WHICH command runs, so the result row below has context (the list
        # previously showed only the output, with no sign of what produced it).
        self.chat_panel.append_tool_call(tool_name, command)

        def worker() -> None:
            if tool_name in FILE_TOOL_NAMES and args is not None:
                result = self._tool_executor.run_file_tool(tool_name, args)
            else:
                result = self._tool_executor.run(tool_name, command)
            wx.CallAfter(
                self._on_tool_result, result, tool_call_id, tool_name, command, args,
            )
        threading.Thread(target=worker, daemon=True).start()

    def _on_tool_result(self, result, tool_call_id: str, tool_name: str = "", command: str = "", args: dict | None = None) -> None:
        """Callback en hilo principal con el resultado de la herramienta."""
        self._tool_executing = False
        log = get_logger()
        if self._aborted:
            log.info("tool cancelled by user abort")
            self.chat_panel.append_tool_output(result.to_display_text())
            return
        if result.cancelled:
            log.info("tool cancelled by user abort")
            self.chat_panel.append_tool_output(result.to_display_text())
            self._speech.speak(
                "Generación detenida", interrupt=True
            )
            return
        self.chat_panel.append_tool_output(result.to_display_text())

        # Build and insert the assistant+tool_calls message (required by
        # the OpenAI contract for the 2nd turn).
        if tool_name:
            if args is not None:
                arguments_str = json.dumps(args)
            else:
                arguments_str = json.dumps({"command": command})
            tool_call_entry = {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": arguments_str,
                },
            }
            self._conversation.add_message(
                "assistant", self._current_response,
                tool_calls=[tool_call_entry],
            )

        # Short feedback announcement
        stdout_text = result.stdout.strip() if result.stdout else ""
        if stdout_text:
            first_line = stdout_text.split("\n")[0][:80]
            feedback = (
                f"Comando completado, código {result.returncode}. "
                f"Primeras líneas: {first_line}"
            )
        else:
            feedback = f"Comando completado, código {result.returncode}."
        self._speech.speak(feedback, interrupt=True)

        tool_msg = result.to_tool_message()
        tool_msg["tool_call_id"] = tool_call_id
        # Persist tool_call_id on the message so the next API call carries
        # the matching ID (required by the OpenAI-compatible API for the
        # tool-calling second turn). Without this, llama-server rejects
        # the request. v0.4.0-ui verify v1 CRITICAL-1.
        self._conversation.add_message(
            "tool", tool_msg["content"], tool_call_id=tool_call_id
        )
        self._continue_after_tool()

    def _continue_after_tool(self) -> None:
        """Reenvía la conversación al modelo con el resultado de la tool.

        Increments the tool iteration counter and checks against
        max_tool_iterations. If the limit is reached, appends a visible
        row and returns without calling chat_stream.
        """
        self._tool_iteration_count += 1
        if self._tool_iteration_count >= self._config.max_tool_iterations:
            msg = f"[Tool loop terminated: max iterations ({self._config.max_tool_iterations}) reached]"
            self.chat_panel.append_tool_output(msg)
            self._speech.speak(
                "Límite de iteraciones alcanzado", interrupt=True,
            )
            self._is_generating = False
            self.status_bar.SetStatusText("", 2)
            return

        self._aborted = False  # Reset abort flag before re-launching the stream
        api_messages = build_api_messages(self._config, self._conversation)

        tools = get_enabled_tools(self._config)

        self._current_response = ""
        self._current_reasoning = ""
        self.chat_panel.start_generation()
        self._is_generating = True
        self.status_bar.SetStatusText("Consultando al modelo...", 2)

        self._client.chat_stream(
            messages=api_messages,
            options=build_options(self._config),
            on_token=self._on_token,
            on_done=self._on_done,
            on_error=self._on_error,
            on_usage=self._on_usage,
            on_timings=self._on_timings,
            on_tool_call=self._on_tool_call,
            tools=tools,
            on_reasoning=self._on_reasoning,
        )

    def _on_error(self, error_text: str) -> None:
        """Handle stream error or abort confirmation.

        Args:
            error_text: Error description. Ignored when ``self._aborted``
                is True (the abort path takes precedence).
        """
        if self._aborted:
            self._speech.speak("Generación detenida", interrupt=True)
            self.chat_panel.end_generation()
            self._current_response = ""
            self._current_reasoning = ""
            self._aborted = False
            self.status_bar.SetStatusText("", 2)
            return

        if not self._is_generating:
            return
        log = get_logger()
        log.error("_on_error: %s", error_text)
        self._current_response = error_text
        self._current_reasoning = ""
        self.chat_panel.end_generation(final_text=error_text)
        self._is_generating = False
        self.status_bar.SetStatusText("Error", 2)

        # Watchdog: connection-class errors → check server state in background
        connection_markers = (
            "ConnectionError",
            "ConnectionRefusedError",
            "ReadTimeout",
            "ChunkedEncodingError",
        )
        if any(marker in error_text for marker in connection_markers):
            self._run_connection_watchdog(error_text)
            return

        # Existing error path for non-connection errors
        wx.MessageDialog(
            self,
            message=error_text,
            caption="Error",
            style=wx.OK | wx.ICON_ERROR,
        ).ShowModal()
        self._speech.speak(error_text, interrupt=True)
        self._notifier.notify("error", "Error")

    # ── Abort ──────────────────────────────────────────────────────────────

    def abort_generation(self) -> None:
        """Abort the current generation and drop the partial response.

        The flag order MUST be: _aborted = True → _is_generating = False
        → client.abort(), so by the time the stream worker fires
        _on_done via wx.CallAfter, both flags are already set and the
        partial response is discarded instead of being saved as
        "Respuesta completa".
        """
        self._aborted = True
        self._is_generating = False
        self._tool_executor.cancel()
        self._client.abort()
        self._speech.stop()
        self._speech.clear_buffer()
        self._current_reasoning = ""

    # ── Usage & Context Meter ───────────────────────────────────────────────

    def _on_timings(self, timings: dict) -> None:
        """Handle timings from the LLM stream.

        Args:
            timings: Dict with predicted_per_second (and possibly other fields).
        """
        tok_per_s = timings.get("predicted_per_second")
        if tok_per_s is not None:
            self._latest_tok_per_s = float(tok_per_s)

    def _on_usage(self, usage: dict) -> None:
        """Handle usage stats from the LLM stream.

        Args:
            usage: Dict with prompt_tokens, completion_tokens, total_tokens.
        """
        self._last_usage = usage
        pt = usage.get("prompt_tokens")
        ct = usage.get("completion_tokens")
        if pt is not None:
            self._latest_prompt_tokens = int(pt)
        if ct is not None:
            self._latest_completion_tokens = int(ct)
        self._update_context_meter(
            self._latest_prompt_tokens or 0,
            self._latest_completion_tokens or 0,
            self._current_n_ctx,
        )

    def _update_context_meter(
        self, prompt_tokens: int, completion_tokens: int, n_ctx: int | None
    ) -> None:
        """Update status bar field 1 with the live context meter.

        Called from ``_on_usage`` after caching the latest token counts.

        Args:
            prompt_tokens: Prompt token count.
            completion_tokens: Completion token count.
            n_ctx: Context window size, or ``None`` if unknown.
        """
        total = prompt_tokens + completion_tokens
        if n_ctx is None:
            self.status_bar.SetStatusText(f"Contexto: {total} tokens", 1)
            return

        pct = round(100 * total / n_ctx)
        self.status_bar.SetStatusText(
            f"Contexto: {total}/{n_ctx} ({pct} %)", 1
        )

        # Threshold announce: >= 85 %, one-shot per generation
        if pct >= 85 and self._is_generating and not self._meter_threshold_fired:
            self._speech.speak("Contexto casi lleno", interrupt=False)
            self._meter_threshold_fired = True
