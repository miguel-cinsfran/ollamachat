# Text Filters Capability Specification — v0.11.0 (NEW)

> **Provenance**: `openspec/changes/2026-06-25-preferences-hints-presets-reading/proposal.md`
> § 4.4 (Pestaña "Lectura") and R1 (filter order). This is a NEW capability
> spec for `bellbird/core/text_filters.py::apply_filters`. It is wx-free and
> fully unit-testable in WSL. Cross-references:
> `parameters` delta (markdown-strip reuse), `app-configuration` delta
> (4 filter toggles), `speech` delta (optional TTS integration).

## Purpose

Defines the `apply_filters` text-shaping pipeline that consumes
the 4 `BellbirdConfig.filter_strip_*` toggles and returns a
filtered string for TTS output. The pipeline exists so blind
users can opt out of screen-reader-friction content (markdown
markers, raw URLs, emoji descriptions, fenced code) without
touching the source content of the conversation. The order is
fixed by proposal R1: `strip_markdown` → `strip_urls` →
`strip_emojis` → `strip_code_blocks`.

## Requirements

### Requirement: `apply_filters` is a pure, wx-free function (proposal §4.4)

`bellbird/core/text_filters.py` SHALL define
`apply_filters(text: str, config: BellbirdConfig) -> str` as
a **pure** function: same `(text, config)` input → same
output, no side effects, no `wx` import. The function MUST
never raise (regression guard: the TTS path is the caller's
last-mile channel; an exception there would crash the
stream). When `text` is empty, the function returns `""`
without inspecting the toggles. When all 4 toggles are
`False`, the function returns the input unchanged (idempotent
no-op). Each individual filter step is a pass-through when
its toggle is `False`.

#### Scenario: empty input returns empty (regression guard)

- GIVEN `apply_filters("", cfg)` is called for any `BellbirdConfig cfg`
- WHEN the result is read
- THEN the result is `""`
- AND no exception is raised
- AND the toggles are NOT inspected (call is `text == ""` short-circuit)

#### Scenario: all 4 toggles False is a no-op (idempotent)

- GIVEN `BellbirdConfig(filter_strip_markdown=False, filter_strip_urls=False, filter_strip_emojis=False, filter_strip_code_blocks=False)`
- WHEN `apply_filters("Hello **bold** https://x.com 👋 ```code```", cfg)` is called
- THEN the result equals the input string (every step is a pass-through)

#### Scenario: `apply_filters` is wx-free (regression guard)

- GIVEN the source of `bellbird/core/text_filters.py`
- WHEN the AST test greps for `import wx` or `from wx`
- THEN no match is found (the module imports only stdlib + `core.config.BellbirdConfig` + `core.text_utils.strip_markdown`)

#### Scenario: `apply_filters` never raises (regression guard)

- GIVEN any `text` (including `None`, non-string, exotic Unicode, very long)
- AND any `BellbirdConfig` (including a config where all toggles throw on access — defensive)
- WHEN `apply_filters(text, cfg)` is called
- THEN no exception propagates to the caller (the function returns a string, possibly the input verbatim)

### Requirement: `apply_filters` applies filters in the documented order (proposal R1)

`apply_filters` SHALL apply the enabled filters in this exact
order: (1) `strip_markdown` (via the existing
`core.text_utils.strip_markdown`), (2) `strip_urls` (regex
`https?://\S+` → `""`), (3) `strip_emojis` (Unicode emoji
range regex → `""`), (4) `strip_code_blocks` (triple-backtick
fences → `""`). The order is FINAL for this change (proposal
R1 documents the dependency: strip markdown first to consume
code fences and link syntax, then URLs to drop the
`https://…` tail, then emojis, then residual code blocks).

#### Scenario: all 4 filters ON strips each marker class

- GIVEN `BellbirdConfig()` (all toggles True)
- WHEN `apply_filters("**bold** see https://x.com 👋 ```code``` more", cfg)` is called
- THEN the result contains no `**` markers
- AND the result contains no `https://` substring
- AND the result contains no `👋` character
- AND the result contains no triple-backtick fences

#### Scenario: filter step is a pass-through when its toggle is False (regression guard)

- GIVEN `BellbirdConfig(filter_strip_markdown=False)` (only markdown OFF)
- WHEN `apply_filters("**bold** https://x.com", cfg)` is called
- THEN the result still contains `**bold**` (markdown was NOT stripped)
- AND the result does NOT contain `https://` (URLs were stripped)

#### Scenario: order is `strip_markdown` → `strip_urls` → `strip_emojis` → `strip_code_blocks` (proposal R1)

- GIVEN `BellbirdConfig()` (all ON) AND input `"[link](https://x.com)"` (markdown link wrapping a URL)
- WHEN `apply_filters` runs
- THEN the link syntax `[link]` is consumed by `strip_markdown` first
- AND the residual `https://x.com` is consumed by `strip_urls` second
- AND the final result is `"link"` (NOT `"[link](https://x.com)"` and NOT `""`)

### Requirement: `strip_markdown` step reuses the existing `core.text_utils.strip_markdown` (proposal §4.4)

The `filter_strip_markdown` toggle SHALL route through the
existing `core.text_utils.strip_markdown` function (no
duplicate implementation). When the toggle is `True`,
`apply_filters` calls `strip_markdown(text)` and continues
with the (already-stripped) result. When the toggle is
`False`, this step is a pass-through.

#### Scenario: `filter_strip_markdown=True` reuses `text_utils.strip_markdown`

- GIVEN `BellbirdConfig()` (markdown ON) AND input `"**bold**"`
- WHEN `apply_filters("**bold**", cfg)` is called
- THEN the result equals `text_utils.strip_markdown("**bold**")` (i.e. `"bold"`)
- AND the result contains no `**` markers

#### Scenario: `filter_strip_markdown=False` preserves markdown markers

- GIVEN `BellbirdConfig(filter_strip_markdown=False, filter_strip_urls=False, filter_strip_emojis=False, filter_strip_code_blocks=False)` (all OFF except none ON)
- WHEN `apply_filters("**bold**", cfg)` is called
- THEN the result is `"**bold**"` (the markers are preserved — all steps are pass-throughs)

### Requirement: `strip_urls` step drops `https?://\S+` matches

The `filter_strip_urls` toggle SHALL enable a regex step
that removes any substring matching `https?://\S+` (HTTP or
HTTPS URL followed by non-whitespace). The regex MUST match
both `http://` and `https://` schemes. The regex MUST NOT
match bare hostnames (e.g. `example.com` is preserved; only
the scheme-prefixed form is dropped).

#### Scenario: `filter_strip_urls=True` drops an HTTPS URL

- GIVEN `BellbirdConfig()` (URLs ON) AND input `"See https://example.com for details"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `"See  for details"` (the URL is removed, double-space is the documented behavior; collapsing whitespace is out of scope for this change)

#### Scenario: `filter_strip_urls=True` drops an HTTP URL

- GIVEN `BellbirdConfig()` AND input `"Visit http://example.org today"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `"Visit  today"` (HTTP is also dropped)

#### Scenario: `filter_strip_urls=True` preserves bare hostnames (regression guard)

- GIVEN `BellbirdConfig()` AND input `"See example.com for details"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `"See example.com for details"` (the scheme prefix is required to trigger the strip — bare hostnames stay)

#### Scenario: `filter_strip_urls=False` preserves URLs (regression guard)

- GIVEN `BellbirdConfig(filter_strip_markdown=False, filter_strip_urls=False, filter_strip_emojis=False, filter_strip_code_blocks=False)` AND input `"See https://x.com"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `"See https://x.com"` (the URL is preserved)

### Requirement: `strip_emojis` step drops Unicode emoji characters

The `filter_strip_emojis` toggle SHALL enable a step that
removes Unicode emoji characters (the canonical emoji
ranges: `U+1F300`–`U+1FAFF`, `U+2600`–`U+27BF`, etc., per the
Python `unicodedata` `emoji`-flag-based detection OR a
documented regex). ASCII punctuation MUST NOT be stripped
(`!`, `?`, `,`, `.`, `:`, `;` are not emoji).

#### Scenario: `filter_strip_emojis=True` drops a wave emoji

- GIVEN `BellbirdConfig()` (emojis ON) AND input `"Hello 👋 world"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `"Hello  world"` (the wave emoji is removed, double-space is the documented behavior)

#### Scenario: `filter_strip_emojis=True` drops multiple emojis

- GIVEN `BellbirdConfig()` AND input `"🎉 party 🚀 launch"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `" party  launch"` (both emoji characters are removed)

#### Scenario: `filter_strip_emojis=True` preserves ASCII punctuation (regression guard)

- GIVEN `BellbirdConfig()` AND input `"¡Hola! ¿Cómo estás? Listo: sí."`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `"¡Hola! ¿Cómo estás? Listo: sí."` (ASCII punctuation is not emoji)

#### Scenario: `filter_strip_emojis=False` preserves emojis (regression guard)

- GIVEN `BellbirdConfig(filter_strip_markdown=False, filter_strip_urls=False, filter_strip_emojis=False, filter_strip_code_blocks=False)` AND input `"Hello 👋 world"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `"Hello 👋 world"` (the emoji is preserved)

### Requirement: `strip_code_blocks` step drops triple-backtick fences

The `filter_strip_code_blocks` toggle SHALL enable a step
that removes fenced code blocks delimited by triple
backticks (`` ``` ``), with or without a language tag, and
content in between. The fence may be on its own line or
inline; the regex MUST consume the opening fence, the
content, and the closing fence.

#### Scenario: `filter_strip_code_blocks=True` drops a fenced block

- GIVEN `BellbirdConfig()` (code blocks ON) AND input `"text ```code block``` more"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `"text code block more"` (the fence and the backticks are removed; whitespace normalization is out of scope)

#### Scenario: `filter_strip_code_blocks=True` drops a fenced block with a language tag

- GIVEN `BellbirdConfig()` AND input `"```python\nprint(1)\n```"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result does not contain triple backticks
- AND the result contains `"print(1)"` (the language tag is consumed by the regex)

#### Scenario: `filter_strip_code_blocks=False` preserves code blocks (regression guard)

- GIVEN `BellbirdConfig(filter_strip_markdown=False, filter_strip_urls=False, filter_strip_emojis=False, filter_strip_code_blocks=False)` AND input `"text ```code``` more"`
- WHEN `apply_filters(input, cfg)` is called
- THEN the result equals `"text ```code``` more"` (the fence is preserved)

## Test strategy

- WSL: add `tests/core/test_text_filters.py` with 4 test classes
  mirroring the 4 steps: `TestStripMarkdown` (1+ scenario),
  `TestStripUrls` (4 scenarios), `TestStripEmojis` (4
  scenarios), `TestStripCodeBlocks` (3 scenarios); plus
  `TestApplyFiltersOrder` (2 scenarios for the pipeline
  order, including the `[link](https://x.com)` case from
  R1), `TestApplyFiltersEmpty` (1 scenario), `TestApplyFiltersAllOff`
  (1 scenario), `TestApplyFiltersNeverRaises` (1 scenario
  with `None` and exotic inputs), and `TestTextFiltersWxFree`
  (AST guard). Total target: ~17 scenarios.
- The `filter_strip_markdown` reuse is a single scenario in
  `TestStripMarkdown` that asserts the result equals
  `text_utils.strip_markdown(input)` directly.
- WSL: extend `tests/core/test_config.py::TestV0110Config`
  with the per-toggle round-trip coverage (the toggles
  belong to `BellbirdConfig`; the consumption belongs to
  `apply_filters`).
