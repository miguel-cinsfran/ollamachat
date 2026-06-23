# tool-calling Spec — Delta for v0.4.0

## Purpose

Defines the headless, wx-free tool-calling layer that lets llama-server invoke host commands during a conversation. Two new core modules — `PermissionManager` (risk classification, system-path auto-block, ephemeral session grants) and `ToolExecutor` (PowerShell subprocess wrapper) — plus the `ToolResult` data class. Safety contract: destructive operations in system directories are auto-blocked; operations in the user's home directory are NEVER auto-blocked; session grants are in-memory only and die with the process. UI dialog, tool catalog, and `shell_execute` registration are deferred to the follow-up change.

## ADDED Requirements

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
