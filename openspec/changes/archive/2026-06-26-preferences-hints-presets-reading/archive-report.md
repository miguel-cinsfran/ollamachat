# Archive Report — Preferences Hints + Presets + Reading Filters (v0.11.0)

**Archived on**: 2026-06-26
**Original change date**: 2026-06-25
**Commits in this change**:
- `8290ec1`: feat(core): add parameter presets and reading filters foundation (WU-1)
- `c44ac3a`: docs: add WU-1 apply-progress
- `888085e`: feat(ui): preferences hints + presets + reading filters (WU-2)
- `e1d0362`: docs(apply-progress): mark WU-2 complete
- `e46ca25`: chore(spec): align v0.11.0 preferences spec with impl + clean apply-progress
- `2fa11e7`: chore(spec): add v0.11.0 preferences spec deltas

**Final test run**: 844 passed, 15 skipped (WSL) — green in `uv run --no-sync pytest -xvs`.

**Verdict at archive time**: READY_TO_ARCHIVE (1 CRITICAL + 5 WARNING remediated in commits e46ca25 + 2fa11e7).

## Stale-checkbox reconciliation

The `tasks.md` in this change (the persisted SDD task artifact) contains unchecked `- [ ]` checkboxes for all 21 tasks (T1A–T1G, T2A–T2N). This is because `sdd-apply` never updated the `tasks.md` file with `[x]` markers — the implementation is documented in `apply-progress.md` and verified in `verify-report.md`. Per the Strict-vs-OpenSpec Archive Policy, the orchestrator explicitly instructed this archive to proceed with stale-checkbox reconciliation. The archive report records the exceptional reason: the `apply-progress.md` and `verify-report.md` prove every task was completed and tested (844 tests pass, all acceptance criteria met). No functional work was left undone.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `app-configuration` | Updated | Appended `## Added in v0.11.0` section: `param_presets` field, 4 `filter_strip_*` toggles, Lectura tab requirement, Preset sub-panel, HINTS table, `&` mnemonics, dialog size bump, test strategy |
| `parameters` | Updated | Appended `## Added in v0.11.0` section: `ParamPreset` dataclass schema, `_apply_preset_to_controls` semantics, Modelo tab preset sub-panel UI, Lectura tab `strip_markdown` reuse |
| `text-filters` | **Created** | New capability spec (`openspec/specs/text-filters/spec.md`): `apply_filters` pure function, 4-step pipeline order, per-step scenarios, wx-free guard, test strategy |
| `speech` | **Deferred** | Optional delta spec exists in archive but was NOT synced to canonical specs — the SUGGESTION section (TTS integration via `apply_filters`) was not wired in this change. Marked as deferred follow-up. |

## What landed

- Every control in `PreferencesDialog` has a uniform `HINTS` entry (function + range) via `SetToolTip` + `SetHelpText`. 40+ entries.
- All Spanish labels in all 9 tabs (General, Modelo, Chat, Lectura, Herramientas, Avanzado, Audio, Atajos, Estado) have `&` mnemonics, unique per tab.
- `ParamPreset` frozen dataclass + `param_presets: list[ParamPreset]` in `BellbirdConfig`. JSON round-trips.
- Preset sub-panel in Modelo tab: ListBox + 3 buttons (Aplicar / Guardar actual como... / Borrar).
- New **Lectura** tab with 4 filter toggles: strip_markdown, strip_urls, strip_emojis, strip_code_blocks.
- Pure `core/text_filters.py::apply_filters(text, config)` function with fixed order (strip_markdown -> strip_urls -> strip_emojis -> strip_code_blocks).
- Dialog size bumped to `(720, 600)`.

## Archive Contents

- `proposal.md` ✅
- `specs/` ✅ (app-configuration, parameters, text-filters, speech)
- `design.md` ✅
- `tasks.md` ✅ (21/21 tasks — stale checkboxes reconciled per orchestrator instruction)
- `apply-progress.md` ✅
- `verify-report.md` ✅
- `archive-report.md` ✅ (this file)

## Source of Truth Updated

The following canonical specs now reflect the v0.11.0 behavior:
- `openspec/specs/app-configuration/spec.md` (appended v0.11.0 section)
- `openspec/specs/parameters/spec.md` (appended v0.11.0 section)
- `openspec/specs/text-filters/spec.md` (new capability)

## Remediation applied (pre-archive)

The verify-report verdict was BLOCKED with 1 CRITICAL (C1: leaked LLM tokens in `apply-progress.md`) and 5 WARNINGs (W1–W5: spec drifts). These were remediated in commits `e46ca25` (trim leaked tokens + spec drift alignment) and `2fa11e7` (add v0.11.0 spec deltas to git).

## Lessons applied

- v0.8.2 WU-1/WU-2 split (mirrors #11 / #12 / #0.9.0 pattern).
- v0.8.3 verify-reads-code — verify agent audited real code, not just tests.
- v0.8.3 pre-archive `chore(spec):` remediation (mirrors #11 pattern).
- v0.9.0 wx-free core — `core/preset.py` and `core/text_filters.py` have AST tests enforcing the no-wx rule.
- **NEW lesson learned (this change)**: sub-agent tool-call serialization can leak LLM tokens into file writes when the sub-agent's prompt is too long. Mitigation: small `chore(docs):` trim post-apply, before archive. File names that contain tool-call tokens are a strong signal.

## Open follow-ups (deferred, non-blocking)

- S1: TTS integration in `Speech.speak_with_system_voice` — `apply_filters` is NOT called. Wire in a follow-up change.
- W4 drift: spec said `interrupt=True` for "Nombre vacio" / "Ya existe"; impl uses `interrupt=False`. Already remediated in e46ca25.
- W5 drift: HINTS AST test scope (excludes StaticText, includes Notebook). Already remediated in e46ca25.

## References

- proposal: `openspec/changes/archive/2026-06-26-preferences-hints-presets-reading/proposal.md`
- specs: `openspec/changes/archive/2026-06-26-preferences-hints-presets-reading/specs/`
- design: `openspec/changes/archive/2026-06-26-preferences-hints-presets-reading/design.md`
- verify: `openspec/changes/archive/2026-06-26-preferences-hints-presets-reading/verify-report.md`
- canonical specs synced: `openspec/specs/app-configuration/`, `openspec/specs/parameters/`, `openspec/specs/text-filters/`
