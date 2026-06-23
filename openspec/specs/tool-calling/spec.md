# Spec: tool-calling

## Purpose

Defines the tool-calling layer that lets llama-server invoke host commands during a conversation. Two core modules — `PermissionManager` (risk classification, system-path auto-block, ephemeral session grants) and `ToolExecutor` (PowerShell subprocess wrapper) — plus the `ToolResult` data class. Safety contract: destructive operations in system directories are auto-blocked; operations in the user's home directory are NEVER auto-blocked; session grants are in-memory only and die with the process. The UI layer (added in v0.4.0-ui) adds the `PermissionDialog`, `ParamsPanel` tools-checkbox, `MainWindow` wiring (`_on_tool_call`, `_run_tool_and_show`, `_on_tool_result`, `_continue_after_tool`), and `ChatPanel` tool-message appenders to complete the user-facing confirmation flow.

## Requirements (7 core + 8 UI = 15 total)

### Requirement: PermissionManager classifies risk

`PermissionManager.classify_risk(command: str) -> RiskLevel` MUST inspect the lowercased command against three pattern lists, in priority order, and return the first matching level:

| Priority | Level | Patterns |
|---|---|---|
| 1 | `RED` | `remove-item`, `\brm\b`, `\bdel\b`, `rmdir`, `rd\s`, `clear-content`, `format-volume` |
| 2 | `YELLOW` | `move-item`, `rename-item`, `set-content`, `copy-item`, `\bmv\b`, `\bcp\b`, `\bsed\b`, `\bawk\b` |
| 3 (fallback) | `GREEN` | (no match) |

`RiskLevel` is an `enum.Enum` (`GREEN`, `YELLOW`, `RED`). The method MUST NOT raise and MUST NOT mutate state. The comparison is case-insensitive.

#### Scenario: Remove-Item is RED

- **GIVEN** a `PermissionManager()` instance
- **WHEN** `classify_risk("Remove-Item C:\\Temp\\junk.txt")` is called
- **THEN** the result is `RiskLevel.RED`

#### Scenario: Move-Item is YELLOW

- **GIVEN** a `PermissionManager()` instance
- **WHEN** `classify_risk("Move-Item a.txt b.txt")` is called
- **THEN** the result is `RiskLevel.YELLOW`

#### Scenario: Get-Process is GREEN

- **GIVEN** a `PermissionManager()` instance
- **WHEN** `classify_risk("Get-Process | Select-Object -First 1")` is called
- **THEN** the result is `RiskLevel.GREEN`

#### Scenario: Classification is case-insensitive

- **GIVEN** a `PermissionManager()` instance
- **WHEN** `classify_risk("REMOVE-ITEM foo.txt")` is called
- **THEN** the result is `RiskLevel.RED`
- **AND** `classify_risk("remove-item foo.txt")` returns the same level

### Requirement: PermissionManager auto-blocks only system paths

`PermissionManager.is_system_destructive(command: str) -> bool` MUST return `True` ONLY when the command matches one of: `c:\windows`, `c:\system32`, `c:\program files`, `c:\program files (x86)`, `format-volume`, `clear-disk`. Comparison is case-insensitive.

The method MUST NOT flag a user-directory operation as system-destructive. The user is the authority over their own files. A command touching `C:\Users\<name>\...` MUST return `False` even if it contains a destructive verb.

#### Scenario: C:\Windows is system-destructive

- **GIVEN** a `PermissionManager()` instance
- **WHEN** `is_system_destructive("Remove-Item C:\\Windows\\System32\\foo.dll")` is called
- **THEN** the result is `True`

#### Scenario: C:\Users\<name>\Documents\Remove-Item is NOT system-destructive (CRITICAL)

- **GIVEN** a `PermissionManager()` instance
- **WHEN** `is_system_destructive("C:\\Users\\Miguel\\Documents\\Remove-Item test.txt")` is called
- **THEN** the result is `False`
- **AND** this is the locked test that prevents auto-blocking user files

#### Scenario: Format-Volume is system-destructive

- **GIVEN** a `PermissionManager()` instance
- **WHEN** `is_system_destructive("Format-Volume -DriveLetter C")` is called
- **THEN** the result is `True`

#### Scenario: read-only command is NOT system-destructive

- **GIVEN** a `PermissionManager()` instance
- **WHEN** `is_system_destructive("Get-Process")` is called
- **THEN** the result is `False`

### Requirement: PermissionManager session grants are in-memory only

`PermissionManager` MUST maintain a per-instance `set[str]` of granted tool names. The methods `grant_session(tool_name)`, `has_session_grant(tool_name) -> bool`, `revoke_session(tool_name)`, and `revoke_all()` MUST mutate and read ONLY this in-memory set. They MUST NOT write to disk, the registry, or any external store. The set is reset to empty when the Python process exits.

`revoke_all()` MUST clear every grant in a single call. `has_session_grant("never-granted")` MUST return `False` without raising.

#### Scenario: grant then has

- **GIVEN** a fresh `PermissionManager()` instance
- **WHEN** `grant_session("shell_execute")` is called
- **THEN** `has_session_grant("shell_execute")` is `True`
- **AND** `has_session_grant("other_tool")` is `False`

#### Scenario: revoke removes one grant only

- **GIVEN** `grant_session("shell_execute")` and `grant_session("read_file")` have both been called
- **WHEN** `revoke_session("shell_execute")` is called
- **THEN** `has_session_grant("shell_execute")` is `False`
- **AND** `has_session_grant("read_file")` is `True`

#### Scenario: revoke_all clears every grant

- **GIVEN** `grant_session("a")` and `grant_session("b")` have been called
- **WHEN** `revoke_all()` is called
- **THEN** `has_session_grant("a")` is `False`
- **AND** `has_session_grant("b")` is `False`

### Requirement: ToolExecutor runs PowerShell on Windows

`ToolExecutor.run(tool_name: str, command: str, timeout: float = 30.0) -> ToolResult` on `sys.platform == "win32"` MUST:

1. Probe for `pwsh.exe` (PowerShell 7+) by running `[shell, "-Command", "exit 0"]` with a 5-second timeout. On `FileNotFoundError` or `subprocess.TimeoutExpired`, fall back to `powershell.exe`.
2. Execute the command via `subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=0x08000000)` (where `0x08000000` is `CREATE_NO_WINDOW`).
3. Truncate `stdout` and `stderr` independently to `MAX_OUTPUT_CHARS` (4000) characters.
4. On `subprocess.TimeoutExpired`, return a `ToolResult` with `returncode=1` and a timeout message in `stderr`. MUST NOT raise.
5. On any other exception, return a `ToolResult` with `returncode=1` and the exception string in `stderr`. MUST NOT raise.

#### Scenario: timeout returns error ToolResult, no raise

- **GIVEN** a stubbed `subprocess.run` that raises `subprocess.TimeoutExpired`
- **WHEN** `ToolExecutor().run("shell_execute", "sleep 999", timeout=5.0)` is called on win32
- **THEN** the returned `ToolResult.returncode == 1`
- **AND** `ToolResult.stderr` contains a timeout-related string
- **AND** no exception propagates to the caller

#### Scenario: stdout truncated to 4000 chars

- **GIVEN** a stubbed `subprocess.run` whose `result.stdout` is 5000 chars
- **WHEN** `ToolExecutor().run("shell_execute", "echo x")` is called on win32
- **THEN** the returned `ToolResult.stdout` has length `4000`

#### Scenario: stderr truncated independently from stdout

- **GIVEN** a stubbed `subprocess.run` whose `result.stdout` is 100 chars and `result.stderr` is 5000 chars
- **WHEN** `ToolExecutor().run("shell_execute", "bad-cmd")` is called on win32
- **THEN** `ToolResult.stderr` has length `4000`
- **AND** `ToolResult.stdout` has length `100` (NOT truncated)

#### Scenario: CREATE_NO_WINDOW flag is set on win32

- **GIVEN** the platform is `win32`
- **WHEN** `ToolExecutor().run("shell_execute", "echo hi")` is called
- **THEN** the stubbed `subprocess.run` was called with `creationflags=0x08000000`

### Requirement: ToolExecutor returns error result on non-Windows

When `sys.platform != "win32"`, `ToolExecutor.run(...)` MUST return a `ToolResult` with `returncode=1` and `stderr` exactly equal to `"Tool execution only available on Windows."`. The method MUST NOT invoke `subprocess` in any form on non-Windows platforms and MUST NOT raise.

#### Scenario: non-win32 returns error result without invoking subprocess

- **GIVEN** `sys.platform` is mocked to `"linux"`
- **WHEN** `ToolExecutor().run("shell_execute", "ls")` is called
- **THEN** the returned `ToolResult.returncode == 1`
- **AND** `ToolResult.stderr == "Tool execution only available on Windows."`
- **AND** `ToolResult.stdout == ""`
- **AND** `subprocess.run` was NOT called

### Requirement: ToolResult.to_display_text formats for the chat UI

`ToolResult.to_display_text() -> str` MUST return a multi-line string with exactly these lines, in order:

1. `"[Herramienta: <tool_name>]"`
2. `"> <command>"`
3. A 40-character `"-"` separator
4. `stdout.rstrip()` — only if `stdout.strip()` is non-empty
5. `"[stderr] <stderr.rstrip()>"` — only if `stderr.strip()` is non-empty
6. `"[codigo de salida: <returncode>]"` — only if `returncode != 0`

Lines are joined with `"\n"`. Output MUST NOT contain markdown, HTML, or other markup. A `ToolResult` with empty stdout/stderr and `returncode == 0` returns the three header lines only.

#### Scenario: happy path includes tool name and command

- **GIVEN** a `ToolResult("shell_execute", "Get-Process", "Idle   123", "", 0)`
- **WHEN** `to_display_text()` is called
- **THEN** the result contains `"[Herramienta: shell_execute]"`
- **AND** the result contains `"> Get-Process"`
- **AND** the result contains `"Idle   123"`
- **AND** the result does NOT contain `"[stderr]"` (stderr empty)
- **AND** the result does NOT contain `"[codigo de salida:"` (returncode 0)

#### Scenario: non-zero exit code surfaces in display

- **GIVEN** a `ToolResult("shell_execute", "bad-cmd", "", "Access denied", 1)`
- **WHEN** `to_display_text()` is called
- **THEN** the result contains `"[stderr] Access denied"`
- **AND** the result contains `"[codigo de salida: 1]"`

### Requirement: ToolResult.to_tool_message formats for the model

`ToolResult.to_tool_message() -> dict` MUST return a plain `dict` with exactly three keys:

- `"role"`: the string `"tool"`
- `"content"`: `stdout` plus `"\n[stderr] <stderr>"` if `stderr` is non-empty, plus `"\n[exit code: <returncode>]"` if `returncode != 0`, then `.strip()`-ed
- `"tool_call_id"`: the empty string `""` (the UI layer fills this in before re-sending to the model)

#### Scenario: happy path message shape

- **GIVEN** a `ToolResult("shell_execute", "ls", "file1\nfile2", "", 0)`
- **WHEN** `to_tool_message()` is called
- **THEN** the result is `{"role": "tool", "content": "file1\nfile2", "tool_call_id": ""}`
- **AND** `"content"` has no leading or trailing whitespace

#### Scenario: stderr and exit code are concatenated into content

- **GIVEN** a `ToolResult("shell_execute", "bad", "", "boom", 2)`
- **WHEN** `to_tool_message()` is called
- **THEN** `result["role"] == "tool"`
- **AND** `result["content"]` contains `"[stderr] boom"`
- **AND** `result["content"]` contains `"[exit code: 2]"`
- **AND** `result["tool_call_id"] == ""`

---

## UI Layer Requirements (added in v0.4.0-ui)

### Requirement: PermissionDialog uses native wx buttons, not MessageDialog

The `PermissionDialog(wx.Dialog)` MUST be built with three native
`wx.Button` instances (labels: `"Permitir una vez"`,
`"Permitir en esta sesion"`, `"Denegar"`) and MUST NOT use
`wx.MessageDialog` for the confirmation itself. Stock labels
(`YES_NO`) on `wx.MessageDialog` are allowed for unrelated
confirmations (e.g. close confirm) but NOT for the tool permission
prompt, because custom Spanish button labels on `wx.MessageDialog`
have documented MSAA regressions.

The dialog MUST:
1. Place the read-only `command_text` (`wx.TextCtrl`, style
   `wx.TE_MULTILINE | wx.TE_READONLY`, `name="command_text"`) above
   the three buttons, preceded by a `wx.StaticText` label
   "El modelo quiere ejecutar:".
2. Show a `wx.StaticText` risk label ("Operacion de lectura o
   creacion" / "Advertencia: operacion de modificacion" /
   "Advertencia: operacion irreversible (los archivos NO van a la
   Papelera)") if `risk_level.name` is GREEN / YELLOW / RED. Strings
   MUST be plain ASCII (no emoji).
3. Set `SetEscapeId(wx.ID_CANCEL)` so the Escape key maps to
   "Denegar".
4. Call `self.command_text.SetFocus()` after `Fit()` so NVDA reads
   the command before any button gets focus.
5. On `sys.platform == "win32"`, attempt `winsound.MessageBeep(
   MB_ICONEXCLAMATION)` inside a `try/except` (audio is best-effort).

#### Scenario: all three buttons present with names

- **GIVEN** the source of `ollamachat/ui/permission_dialog.py`
- **WHEN** inspected via AST
- **THEN** exactly three `wx.Button` constructors exist with
  `name="allow_once_button"`, `name="allow_session_button"`, and
  `name="deny_button"`
- **AND** a `wx.TextCtrl` with `name="command_text"` exists

#### Scenario: no MessageDialog in the file

- **GIVEN** the source of `ollamachat/ui/permission_dialog.py`
- **WHEN** searched for the token `MessageDialog`
- **THEN** the result is zero matches

#### Scenario: focus is on command_text after Fit

- **GIVEN** the `_build_ui` method body
- **WHEN** the order of `self.Fit()` and `self.command_text.SetFocus()`
  is checked
- **THEN** `SetFocus()` is called AFTER `Fit()` (or `self.Fit()` is
  omitted, but `SetFocus()` is called inside `_build_ui`)

### Requirement: SHELL_TOOL_DEFINITION is the only tool exposed to the model

`ollamachat/ui/main_window.py` MUST define, at module level (NOT
inside `MainWindow`), a `SHELL_TOOL_DEFINITION` constant — a Python
`dict` matching the OpenAI function-calling schema, with:

- `type = "function"`
- `function.name = "shell_execute"`
- `function.description` (string, in Spanish, explaining PowerShell
  use)
- `function.parameters` = `{"type": "object", "properties":
  {"command": {"type": "string", "description": "..."}}, "required":
  ["command"]}`

This is the ONLY entry the model is ever offered in v0.4.0. No
`READ_FILE`, `WRITE_FILE`, or other tools.

#### Scenario: SHELL_TOOL_DEFINITION is at module scope

- **GIVEN** the AST of `ollamachat/ui/main_window.py`
- **WHEN** the location of the `SHELL_TOOL_DEFINITION` assignment is
  checked
- **THEN** it is a top-level assignment (NOT nested inside
  `class MainWindow`)

### Requirement: MainWindow sends `tools` to the model only when toggle is on

`MainWindow.send_message()` MUST determine the `tools` argument of
`chat_stream` as follows:

```python
tools = [SHELL_TOOL_DEFINITION] if self.params_panel.get_tools_enabled() else None
```

When `tools` is `None` (toggle off), the model receives no `tools`
key in the request body — `LlamaClient` MUST NOT include a `tools`
key (preserved contract from v0.4.0-core). When the toggle is on,
the request body MUST include the single-tool catalog and
`tool_choice="auto"` (also preserved contract from v0.4.0-core).

The call site MUST also pass `on_tool_call=self._on_tool_call` so
the callback chain is wired up regardless of toggle state (the
toggle only controls the `tools` payload, not the callback).

#### Scenario: tools=None path uses default (no regression)

- **GIVEN** `get_tools_enabled()` returns `False`
- **WHEN** `send_message()` is called
- **THEN** `chat_stream` is invoked with `tools=None`
- **AND** `on_tool_call=self._on_tool_call` is still passed

### Requirement: MainWindow._on_tool_call is the single permission gate

`MainWindow._on_tool_call(tool_name, tool_call_id, args)` MUST be
the SOLE entry point for tool invocations, invoked on the main
thread (via `wx.CallAfter` from `LlamaClient._stream_worker`). The
method MUST, in this exact order:

1. Extract `command = args.get("command", str(args))`.
2. If `self._permission_manager.is_system_destructive(command)`
   returns `True`:
   - Speak "Comando bloqueado por seguridad: {command[:80]}" via
     `self._speech.speak(..., interrupt=True)`.
   - Call `self.chat_panel.append_tool_blocked(tool_name, command)`.
   - **Do not** run the tool. **Do not** continue the conversation
     (the model is not re-pinged with the blocked result).
3. Else if `self._permission_manager.has_session_grant(tool_name)`
   returns `True`:
   - Speak "Ejecutando {tool_name}: {command[:50]}" via
     `self._speech.speak(..., interrupt=True)`.
   - Call `self._run_tool_and_show(tool_name, tool_call_id, command)`.
4. Else:
   - Speak "El modelo quiere ejecutar un comando. Escucha el
     comando y confirma." via `self._speech.speak(..., interrupt=True)`
     (BEFORE showing the dialog, so NVDA announces first).
   - Compute `risk = self._permission_manager.classify_risk(command)`.
   - Show `PermissionDialog(self, tool_name, command, risk)`.
     Modal result dispatch:
     - `wx.ID_YES` → `_run_tool_and_show(tool_name, tool_call_id, command)`.
     - `wx.ID_OK` → `self._permission_manager.grant_session(tool_name)`
       THEN `_run_tool_and_show(...)`.
     - `wx.ID_CANCEL` (or Escape) → speak "Ejecucion denegada."
       and `self.chat_panel.append_tool_denied(tool_name)`.

#### Scenario: system-destructive path blocks without dialog

- **GIVEN** a tool call with `command="Remove-Item C:\\Windows\\foo.dll"`
- **WHEN** `_on_tool_call` is invoked
- **THEN** the dialog is NOT shown
- **AND** `append_tool_blocked` is called
- **AND** `_run_tool_and_show` is NOT called

#### Scenario: session grant skips dialog

- **GIVEN** `grant_session("shell_execute")` was previously called
- **WHEN** `_on_tool_call("shell_execute", "id1", {"command": "ls"})` is invoked
- **THEN** the dialog is NOT shown
- **AND** `_run_tool_and_show` IS called

#### Scenario: user denies via Deny button

- **GIVEN** a fresh `PermissionManager` and the user clicks Deny
- **WHEN** `_on_tool_call` returns after the dialog closes
- **THEN** `append_tool_denied` is called
- **AND** `_run_tool_and_show` is NOT called

### Requirement: Tool execution runs on a daemon thread, not the main thread

`MainWindow._run_tool_and_show(tool_name, tool_call_id, command)`
MUST launch a `threading.Thread(target=worker, daemon=True)` where
`worker` is a local function (or lambda) that:

1. Calls `result = self._tool_executor.run(tool_name, command)`.
2. Calls `wx.CallAfter(self._on_tool_result, result, tool_call_id)`
   to bounce the result back to the main thread.

`threading` MUST be imported at the top of `main_window.py`
(already is in v0.3.0). The thread MUST be `daemon=True` so the app
can exit cleanly even if a tool is mid-execution. The thread MUST
NOT touch any wx widget directly.

#### Scenario: tool runs on background thread

- **GIVEN** `_on_tool_call` decides to run the tool
- **WHEN** `_run_tool_and_show` is invoked
- **THEN** a `threading.Thread` with `daemon=True` is started
- **AND** `_tool_executor.run` is called from inside that thread

### Requirement: Tool result re-feeds the model with the tool message

`MainWindow._on_tool_result(result, tool_call_id)` MUST, on the
main thread:

1. Call `self.chat_panel.append_tool_output(result.to_display_text())`.
2. Speak "Comando completado, codigo {result.returncode}. Consultando
   al modelo." via `self._speech.speak(..., interrupt=True)`.
3. Build `tool_msg = result.to_tool_message()`, then
   `tool_msg["tool_call_id"] = tool_call_id`.
4. Call `self._conversation.add_message("tool", tool_msg["content"],
   tool_call_id=tool_call_id)`. The `tool_call_id` kwarg is REQUIRED —
   without it, the next API request is rejected by llama-server
   (OpenAI-compatible API requires `tool_call_id` on tool messages
   to match the assistant's `tool_calls[].id`).
5. Call `self._continue_after_tool(tool_msg)`.

`MainWindow._continue_after_tool(tool_msg)` MUST re-issue the
chat stream with the full conversation (including the just-added
tool message), preserving the same `on_token` / `on_done` /
`on_error` / `on_usage` / `on_tool_call` callbacks and the same
`tools` value (re-derived from the toggle). The status bar field
2 MUST show "Consultando al modelo..." and `start_generation()` +
`append_assistant_prefix()` MUST be called so the stream display
is reset for the assistant's follow-up response.

`Conversation.add_message(role, content, images=None,
tool_call_id=None)` MUST persist `tool_call_id` on the message
dict when supplied. `Conversation.get_messages_for_api()` MUST
include `tool_call_id` in the returned dict for any tool message
that has one. For non-tool roles, the `tool_call_id` kwarg is
silently ignored (no key is added to the message).

#### Scenario: result triggers another stream with tools still on

- **GIVEN** `get_tools_enabled()` returns `True` and a tool just
  completed with `returncode=0`
- **WHEN** `_on_tool_result` is invoked
- **THEN** `_continue_after_tool` is called
- **AND** `chat_stream` is called with
  `tools=[SHELL_TOOL_DEFINITION]`
- **AND** `on_tool_call=self._on_tool_call` is passed again

#### Scenario: tool_call_id is persisted in the conversation (CRITICAL — v0.4.0-ui verify v1)

- **GIVEN** a `Conversation` instance
- **WHEN** `add_message("tool", "ls output", tool_call_id="call_abc123")` is called
- **THEN** `conv.messages[0]["tool_call_id"] == "call_abc123"`
- **AND** `get_messages_for_api()[0]["tool_call_id"] == "call_abc123"`
- **AND** the next chat completion request body carries a tool
  message with the matching `tool_call_id`

#### Scenario: tool_call_id is omitted when not set (backward compat)

- **GIVEN** a `Conversation` instance and a call to
  `add_message("tool", "ls output")` (no tool_call_id kwarg)
- **WHEN** `get_messages_for_api()` is called
- **THEN** `"tool_call_id"` is NOT a key in the returned message dict

### Requirement: ChatPanel exposes three tool-message appenders

`ChatPanel` MUST expose three methods (added at the bottom of the
class, in any order):

- `append_tool_output(self, text: str) -> None` — appends
  `("tool", text)` to `self._history`; appends
  `"[Herramienta] {preview}"` to `self.message_list`; selects the
  last item.
- `append_tool_blocked(self, tool_name: str, command: str) -> None`
  — appends `("system", "[Bloqueado] {tool_name}: {command}")` to
  `self._history`; appends the same string to `message_list` and
  selects it.
- `append_tool_denied(self, tool_name: str) -> None` — appends
  `("system", "[Denegado] {tool_name}")` to `self._history`;
  appends the same string to `message_list` and selects it.

The literal prefixes `"[Herramienta]"`, `"[Bloqueado]"`, and
`"[Denegado]"` MUST be pure ASCII (no emoji, no non-Latin
characters) so NVDA reads them as plain text and not as
"llave inglesa" / "señal de prohibición".

#### Scenario: append_tool_output shows preview

- **GIVEN** `text = "file1\nfile2\nfile3"`
- **WHEN** `append_tool_output(text)` is called
- **THEN** `self._history` ends with `("tool", "file1\nfile2\nfile3")`
- **AND** `self.message_list` ends with a string starting with
  `"[Herramienta] "` and containing the first 80 chars of `text`

#### Scenario: append_tool_blocked records the command

- **GIVEN** `tool_name="shell_execute"`, `command="Remove-Item C:\\Windows\\foo"`
- **WHEN** `append_tool_blocked("shell_execute", "Remove-Item C:\\Windows\\foo")` is called
- **THEN** `self._history` ends with `("system", "[Bloqueado] shell_execute: Remove-Item C:\\Windows\\foo")`
- **AND** the `message_list` last item contains the same string

### Requirement: ParamsPanel exposes a tools-enable toggle

`ParamsPanel` MUST have, in `_build_ui`, a `wx.CheckBox` with
`name="tools_checkbox"` and label `"Permitir herramientas
(PowerShell)"`, added to the vertical sizer BEFORE
`AddStretchSpacer()`. The checkbox MUST be preceded by a
`wx.StaticText` label "Herramientas:" for MSAA association.

`ParamsPanel.get_tools_enabled() -> bool` MUST return the current
state of the checkbox (`self.tools_checkbox.GetValue()`).

#### Scenario: checkbox is present with the right name

- **GIVEN** the AST of `ollamachat/ui/params_panel.py`
- **WHEN** searched for `wx.CheckBox` constructors
- **THEN** at least one has `name="tools_checkbox"`

#### Scenario: get_tools_enabled returns the checkbox value

- **GIVEN** the AST
- **WHEN** the body of `get_tools_enabled` is inspected
- **THEN** it returns `self.tools_checkbox.GetValue()`
