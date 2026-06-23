# Text Utils Capability Specification

## Purpose

Exposes the `ollamachat/core/text_utils.py` headless module providing `strip_markdown(text)` for the message detail popup and accessibility surface. The module uses only the Python standard library and requires no third-party dependencies at runtime.

## Requirements

### Requirement: `strip_markdown` Removes Markdown Syntax

`strip_markdown(text: str) -> str` SHALL strip common markdown syntax and return a plain-text rendering suitable for a read-only `wx.TextCtrl` populated with `TE_RICH2`. The function MUST use only the Python standard library (`re`) and MUST NOT require `wx`, `markdown`, or any third-party dependency at runtime.

The transformation MUST apply, in this order:

| Pattern | Replacement |
|---|---|
| `^#{1,6}\s+` (line start) | `""` (header marker removed) |
| `**(.+?)**` and `__(.+?)__` | `\1` (bold) |
| `*([^\s*][^*]*?)*` and `_([^_\s][^_]*?)_` | `\1` (italic) |
| ``` `` ` ``` fenced code blocks ``` | inner text only, joined with `\n` |
| `` `inline code` `` | inner text (backticks removed) |
| `\[([^\]]+)\]\([^)]+\)` | `\1` (link text only, URL discarded) |
| `^\s*[-*+]\s+` (list item) | `"• "` |

The result MUST have `strip()` applied at the end.

#### Scenario: Strips headers

- **GIVEN** input `"# Title\n\nBody"`
- **WHEN** `strip_markdown("# Title\n\nBody")` is called
- **THEN** the result is `"Title\n\nBody"`

#### Scenario: Strips bold

- **GIVEN** input `"This is **bold** text"`
- **WHEN** `strip_markdown("This is **bold** text")` is called
- **THEN** the result is `"This is bold text"`

#### Scenario: Converts links to anchor text

- **GIVEN** input `"See [docs](https://example.com) here"`
- **WHEN** `strip_markdown("See [docs](https://example.com) here")` is called
- **THEN** the result is `"See docs here"`
- **AND** the URL is discarded

#### Scenario: Converts list items to bullet

- **GIVEN** input `"- first\n- second"`
- **WHEN** `strip_markdown("- first\n- second")` is called
- **THEN** the result starts with `"• first"` and contains `"• second"`

#### Scenario: Plain text passes through

- **GIVEN** input `"  hello world  "`
- **WHEN** `strip_markdown("  hello world  ")` is called
- **THEN** the result is `"hello world"`

#### Scenario: Empty string returns empty string

- **GIVEN** input `""`
- **WHEN** `strip_markdown("")` is called
- **THEN** the result is `""`

#### Scenario: Strips code fences

- **GIVEN** input `"```\nfoo\nbar\n```"`
- **WHEN** `strip_markdown(...)` is called
- **THEN** the result contains `"foo"` and `"bar"` and contains no backticks

### Requirement: `strip_markdown` Is Pure and Headless

`strip_markdown` MUST be a pure function with no I/O, no global state, and no imports of `wx`. The module MUST be importable on WSL where `wxPython` is not installed.

#### Scenario: Importable without wx

- **GIVEN** `ollamachat/core/text_utils.py`
- **WHEN** `from ollamachat.core.text_utils import strip_markdown` runs on a system without wx
- **THEN** no `ImportError` is raised
- **AND** the call is idempotent across invocations
