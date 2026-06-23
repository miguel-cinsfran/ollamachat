# Testing Capabilities — OllamaChat v0.3.0

**Strict TDD Mode**: enabled (core/ only; ui/ uses AST + manual verification)
**Detected**: 2026-06-23

## Test Runner

- **Command**: `uv run --no-sync pytest -xvs`
- **Framework**: pytest 9.1.1
- **Current count**: 140/140 tests passing

## Test Layers

| Layer       | Available | Tool / Description |
|-------------|-----------|-------------------|
| Unit        | ✅        | pytest — 6 core test files (conversation, llama_client, llama_runner, logger, speech, text_utils) |
| Static/AST  | ✅        | pytest + ast — 4 ui static test files (structural checks without importing wx) |
| UI Runtime  | ✅        | pytest — 3 ui test files (runnable on WSL, limited to non-GUI checks) |
| Smoke       | ✅        | pytest — 1 smoke test (speech degradation when accessible_output2 missing) |
| Integration | ❌        | Not configured; all tests are unit/static/smoke |
| E2E         | ❌        | Manual GUI testing on Windows 11 with NVDA |

## Coverage

- **Available**: ✅
- **Command**: `uv run --no-sync pytest --cov`
- **Tool**: pytest-cov 7.1.0 (backed by coverage 7.14.2)

## Quality Tools

| Tool         | Available | Command |
|--------------|-----------|---------|
| Linter       | ❌        | — (explicitly excluded per AGENTS.md) |
| Type checker | ❌        | — (explicitly excluded per AGENTS.md) |
| Formatter    | ❌        | — (not configured) |

## Notes

- **Strict TDD scope**: `ollamachat/core/` only. `ollamachat/ui/` is verified via AST static tests (checking structure/patterns) and manual testing on Windows with NVDA.
- **WSL limitation**: wxPython GUI cannot run on WSL. Core tests + AST ui tests + smoke tests pass in WSL with `--no-sync`.
- **GUI verification required**: Windows 11 with NVDA or JAWS for Tab order, F2/F6 shortcuts, Alt+N hotkeys, and popup focus behavior.
- **No ruff/mypy**: Project convention (per AGENTS.md) is that pytest + manual verify cover quality. Do not add linters or type checkers without explicit user request.
