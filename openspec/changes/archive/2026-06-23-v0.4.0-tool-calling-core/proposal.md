# Proposal: v0.4.0-tool-calling-core

## Why

OllamaChat v0.3.0 is chat-only. A blind user on NVDA + Windows 11 can ask
the model a question and hear the streamed answer, but the model cannot
*act* on the host machine: list a directory, copy a file, kill a process.
To close that gap, llama-server (with `--jinja`, already configured in
v0.3.0) supports OpenAI-style tool calling over SSE. The user types a
request like "decime qué archivos hay en Descargas"; the model responds
with a `tool_calls` delta instead of plain text; the client invokes the
tool; the model sees the result and answers.

This change ships the **core** layer only (wx-free, fully unit-tested).
The UI layer — permission dialog, model-side tool list, `shell_execute`
tool registration — is explicitly deferred to a follow-up prompt so this
slice can land behind a clean review budget.

The blind user is the design driver:

- A blind user cannot see a confirmation dialog flashing by. Every tool
  invocation must be announced by voice *before* it runs, and the user
  must be able to deny it from a single keypress.
- A blind user cannot see what got destroyed. Destructive commands
  (`Remove-Item`, `rm -rf`, `format-volume`) MUST be flagged by risk
  level and auto-blocked when they touch system directories
  (`C:\Windows`, `C:\System32`, `C:\Program Files`).
- A blind user re-opens the app often. Session permissions MUST be
  ephemeral (in-memory) — never persisted to disk — so a stolen
  preference is not a security regression.

## What changes

### A. New module `ollamachat/core/permission_manager.py`

Headless, no wx, no I/O. Three things:

1. `class RiskLevel(enum.Enum)`: `GREEN` (read/create), `YELLOW`
   (mutate: `Move-Item`, `mv`, `sed`), `RED` (destructive: `Remove-Item`,
   `rm`, `del`, `format-volume`).
2. `PermissionManager.classify_risk(command: str) -> RiskLevel` —
   pure `re` match against red/yellow/green pattern lists. Never
   raises. Never mutates state.
3. `PermissionManager.is_system_destructive(command: str) -> bool` —
   returns `True` ONLY for system paths (`C:\Windows`, `C:\System32`,
   `C:\Program Files`, `C:\Program Files (x86)`, `format-volume`,
   `clear-disk`). **Never** auto-blocks user-directory operations.
4. `PermissionManager.{grant_session, revoke_session, revoke_all,
   has_session_grant}(tool_name: str)` — in-memory `set[str]`. Reset
   on app close. Never writes to disk.

### B. New module `ollamachat/core/tool_executor.py`

Headless subprocess wrapper, win32-only at runtime:

1. `class ToolResult` — bundles `(tool_name, command, stdout, stderr,
   returncode)`. Two serializers:
   - `to_display_text()` — multi-line text for the chat transcript.
   - `to_tool_message() -> dict` — `{"role": "tool", "content": ...,
     "tool_call_id": ""}` for the next LLM turn. `tool_call_id` is
     filled in by the UI layer (out of scope here).
2. `class ToolExecutor` with `MAX_OUTPUT_CHARS = 4000`. `run(tool_name,
   command, timeout=30.0)`:
   - On `sys.platform != "win32"`: returns a `ToolResult` with stderr
     `"Tool execution only available on Windows."`, returncode `1`.
     Never raises.
   - On win32: prefers `pwsh.exe` (PowerShell 7+), falls back to
     `powershell.exe` if probe fails. Runs with `-NoProfile
     -NonInteractive -Command`, `text=True, encoding="utf-8",
     errors="replace"`, `timeout=timeout`, `creationflags=0x08000000`
     (`CREATE_NO_WINDOW`).
   - Truncates `stdout` and `stderr` to `MAX_OUTPUT_CHARS`.
   - On `TimeoutExpired`: returns `ToolResult(..., returncode=1)`
     with the timeout in stderr. Never raises.

### C. Surgical edit to `ollamachat/core/llama_client.py`

Five localized changes inside the existing `chat_stream` /
`_stream_worker` pair. **No rewrite.**

1. `chat_stream()` gains two optional params:
   `on_tool_call: Callable[[str, str, dict], None] | None = None` and
   `tools: list[dict] | None = None`.
2. Both are forwarded to the daemon `Thread.args=...` tuple.
3. `_stream_worker` accepts the same two params.
4. When `tools is not None`, the body gains
   `body["tools"] = tools` and `body["tool_choice"] = "auto"`.
5. New local `_tc_buffer: dict[int, dict] = {}` accumulates tool-call
   deltas keyed by `index`, joining `function.arguments` strings
   (llama-server splits them across SSE chunks). When
   `finish_reason == "tool_calls"` and `on_tool_call is not None`,
   for each entry: `args = json.loads(entry["arguments"])` with a
   `JSONDecodeError` fallback of `{"raw": entry["arguments"]}`; then
   `wx.CallAfter(on_tool_call, name, id, args)`. Buffer is cleared
   before the next stream.

The existing `on_usage` plumbing, SSE parser, abort event, daemon
thread, and `wx` import-inside-worker pattern are **untouched**.

### D. Tests (TDD, written before code per AGENTS.md)

`tests/core/test_permission_manager.py` (new, 10 tests):
risk classification (green/yellow/red, PowerShell and POSIX verbs),
`is_system_destructive` for each system path AND the critical
user-dir-with-`Remove-Item` negative case, `format-volume` /
`clear-disk`, session grant/revoke/revoke_all.

`tests/core/test_tool_executor.py` (new, 5 tests): non-win32
returns a `ToolResult` with `returncode=1` and the "only available
on Windows" stderr; `to_display_text` includes the tool name and
command; `to_tool_message` shape (`role`, `content`, `tool_call_id`
keys present); stderr surfaces in `to_tool_message`; `MAX_OUTPUT_CHARS`
truncates 5000→4000.

`tests/core/test_llama_client.py` (extend, 4 tests): body contains
`tools` when `tools` is passed; body has NO `tools` key when `None`;
`on_tool_call` is called with `(name, id, args_dict)` on a
`finish_reason="tool_calls"` chunk; `arguments` split across three
SSE chunks is reassembled into `{"command": "ls"}` before the
callback fires.

## Impact

### New capability

- `tool-calling` — the `PermissionManager` policy (risk classification
  + system-path auto-block + ephemeral session grants) and the
  `ToolExecutor` PowerShell wrapper, plus the `LlamaClient` extension
  that surfaces `tool_calls` to a callback. The UI integration (which
  tool catalog, what dialog, what shortcut) is a follow-up capability
  owned by the next prompt.

### Modified capability

- `llama-integration` — REQ-LLAMA-003 (`Stream chat completions`) gains
  the two new optional params and the `tool_calls` SSE buffering
  rule. The existing `on_token` / `on_done` / `on_error` / `on_usage`
  contract and all 16 other REQs are unchanged.

### Explicitly unaffected

- `accessibility-guidelines`, `app-shell`, `chat`, `conversation-persistence`,
  `parameters`, `speech`, `text_utils` — no spec deltas. Reviewers
  can skip these files in the diff.

## Approach

- Two new files, one surgical edit. No dependency additions.
- `core/` stays wx-free at module level (`tool_executor` uses only
  `subprocess` + `sys`; `permission_manager` uses only `enum` + `re`).
- `llama_client` keeps the existing pattern of importing `wx` inside
  `_stream_worker`. The new `on_tool_call` invocation goes through
  the same `wx.CallAfter` bridge.
- TDD order: `test_permission_manager.py` → `permission_manager.py` →
  `test_tool_executor.py` → `tool_executor.py` → new tests in
  `test_llama_client.py` → `_stream_worker` changes.
- Verification: `uv run --no-sync pytest tests/core/ -xvs` — all
  v0.3.0 tests still pass, plus the 19 new tests (10 + 5 + 4).

## Non-goals

- **UI dialog** for permission prompts — owned by PROMPT_TOOL_CALLING2.
- **Tool catalog** (which tools the model can pick from, JSON schema
  for each, `shell_execute` definition) — owned by PROMPT_TOOL_CALLING2.
- **Persisting permissions** to disk (registry, JSON file, etc.) —
  in-memory only, always.
- **Auto-blocking destructive operations in the user's home directory**
  (`C:\Users\...`). The user is the authority on their own files.
- **Cross-platform execution**. `ToolExecutor.run` returns an error
  result on non-win32; never raises, never silently succeeds.
- **Version bump in `pyproject.toml`** — deferred to PROMPT_TOOL_CALLING2
  when the feature is complete.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `is_system_destructive` regex flags a user dir by accident | Med | `test_is_system_destructive_user_dir_returns_false` is a CRITICAL test that locks the user-dir negative case |
| Auto-grant set grows unbounded during long sessions | Low | `revoke_all` is exposed; UI owns the trigger (out of scope here, but the API is ready) |
| `json.loads(entry["arguments"])` raises on malformed JSON from model | Med | `try/except JSONDecodeError` falls back to `{"raw": entry["arguments"]}` — tested implicitly by the buffer-accumulation test |
| Subprocess hangs past `timeout=30s` | Low | `subprocess.TimeoutExpired` caught, returned as a `ToolResult` with `returncode=1`; never raises |
| `pwsh.exe` probe `subprocess.run(..., timeout=5)` adds startup latency | Low | Runs once per `run()` call only if shell is not already known; in practice the cost is bounded |
| `ToolExecutor.run` on non-win32 silently returns error result that a future caller mistakes for a real failure | Med | `to_display_text` and `to_tool_message` both surface the "only available on Windows" string verbatim; the UI will speak it |
| Race: two tool-call deltas arrive in the same SSE chunk | Low | Buffer is `dict[int, dict]` keyed by `index`; order-independent accumulation is exactly the llama-server contract |
| Silent loss of session grants on app crash | Low | Intentional: security boundary. Documented in the `PermissionManager` docstring. |

## Acceptance criteria

- [ ] `ollamachat/core/permission_manager.py` and `ollamachat/core/tool_executor.py` exist and are importable on WSL.
- [ ] `uv run --no-sync pytest tests/core/ -xvs` is green: prior 140 tests + 10 new in `test_permission_manager.py` + 5 new in `test_tool_executor.py` + 4 new in `test_llama_client.py` = 159/159.
- [ ] `core/llama_client.py` diff is **surgical**: `chat_stream` signature, `_stream_worker` signature, the body branch when `tools is not None`, the `_tc_buffer` accumulation, and the `finish_reason == "tool_calls"` dispatch. No other lines change.
- [ ] `core/` still imports no `wx` at module level (`llama_client.py` imports it inside `_stream_worker`, as before).
- [ ] `PermissionManager` does not import `pathlib`, `os`, or `subprocess` — only `enum` and `re`.
- [ ] `ToolExecutor.MAX_OUTPUT_CHARS == 4000` and stdout/stderr are truncated independently.
- [ ] `is_system_destructive("C:\\Users\\Miguel\\Documents\\Remove-Item test.txt")` returns `False` (the locked critical test).
- [ ] `pyproject.toml` version is still `0.3.0` (no bump this change).
- [ ] No file under `ollamachat/ui/` is modified.

## Rollback plan

1. `git revert` the merge commit (single PR per preflight `delivery: single-pr-default`).
2. `rm ollamachat/core/permission_manager.py ollamachat/core/tool_executor.py` if revert leaves them behind.
3. `rm tests/core/test_permission_manager.py tests/core/test_tool_executor.py` likewise.
4. `uv run --no-sync pytest tests/core/ -xvs` must still pass at the prior green state (140/140).
5. `openspec/changes/v0.4.0-tool-calling-core/` archived to `openspec/changes/archive/2026-06-23-v0.4.0-tool-calling-core/` with an `archive-report.md` explaining the rollback.

## Skill resolution

`paths-injected` — `cognitive-doc-design` loaded from
`/home/ic_ma/.config/opencode/skills/`. Engram unavailable per
`AGENTS.md`; artifact store is `openspec`.
