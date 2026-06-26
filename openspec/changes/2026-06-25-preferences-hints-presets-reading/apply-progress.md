# Apply Progress — v0.11.0 WU-1 (Core + Tests)

## Status

**COMPLETE** — All T1A–T1G tasks implemented and verified.

## Commit

```
feat(core): add parameter presets and reading filters foundation (v0.11.0 WU-1)

- core/preset.py: ParamPreset frozen dataclass + build_preset_from_config + to_dict/from_dict
- core/text_filters.py: apply_filters pure function (strip_markdown + URLs + emojis + code blocks)
- core/config.py: 5 new fields (param_presets, filter_strip_markdown, filter_strip_urls, filter_strip_emojis, filter_strip_code_blocks)
- tests/core/: test_preset (new), test_text_filters (new), test_config (extended)

T-WU1: T1A-T1G. v0.11.0 (WU-1 of 2).
```

## Completed Tasks

| Task | Status | Details |
|------|--------|---------|
| T1A | [x] | `tests/core/test_preset.py` — 9 tests (frozen, to_dict, from_dict, build_preset_from_config, AST guard) |
| T1B | [x] | `bellbird/core/preset.py` — frozen ParamPreset, build_preset_from_config, to_dict/from_dict |
| T1C | [x] | `tests/core/test_text_filters.py` — 29 tests (all-off, empty, never-crashes, individual filters, pipeline order, AST guards, private helpers) |
| T1D | [x] | `bellbird/core/text_filters.py` — apply_filters pipeline, _strip_urls, _strip_emojis, _strip_code_blocks |
| T1E | [x] | `tests/core/test_config.py` — TestV0110Config class (12 tests: defaults, round-trip, forward-compat, per-instance, migration guard) |
| T1F | [x] | `bellbird/core/config.py` — 5 new fields + ParamPreset import + load_config normalisation |
| T1G | [x] | Integration: `uv run --no-sync pytest -xvs tests/core/` → 609 passed, 14 skipped. Commit done. |

## Test Count

- **New tests**: 9 (preset) + 29 (text_filters) + 12 (config extensions) = **50 new test scenarios**
- **Total core tests passing**: 609 (unchanged passing, 14 skipped WSL)

## Files Changed

| File | Action | LOC |
|------|--------|-----|
| `bellbird/core/preset.py` | **NEW** | ~95 |
| `bellbird/core/text_filters.py` | **NEW** | ~120 |
| `bellbird/core/config.py` | MODIFIED | +15 (import + 5 fields + normalisation) |
| `tests/core/test_preset.py` | **NEW** | ~185 |
| `tests/core/test_text_filters.py` | **NEW** | ~350 |
| `tests/core/test_config.py` | MODIFIED | +120 (TestV0110Config) |

## Verification

```bash
uv run --no-sync pytest -xvs tests/core/
# 609 passed, 14 skipped in 96.45s
```

## Notes

- All tests run in WSL (no wx dependency).
- Forward-compat: old configs without the 5 new fields load with defaults.
- No `_MIGRATIONS` entries needed (automatic via `__dataclass_fields__` filter).
- `param_presets` normalisation: `load_config` converts JSON list-of-dicts → `list[ParamPreset]`.
- Code block regex uses non-capturing group `(?:\w+\n)?` to avoid consuming content as a language tag.
- Emoji regex covers canonical ranges (U+1F300–U+1FAFF, U+2600–U+27BF, U+FE00–U+FE0F, U+200D).
