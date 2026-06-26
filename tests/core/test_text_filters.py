"""Tests for bellbird.core.text_filters — strict TDD, wx-free.

Covers: apply_filters pipeline order (strip_markdown → strip_urls →
strip_emojis → strip_code_blocks), toggle gating, empty input,
never-crash contract, and AST guard for no wx import.

The 4 individual filter helpers (_strip_urls, _strip_emojis,
_strip_code_blocks) are tested here as private functions.
"""

import ast
import re

import pytest

from bellbird.core.config import BellbirdConfig


# ── Helper to build a config with specific filter toggles ──────────────


def _cfg_all_on() -> BellbirdConfig:
    """Return a BellbirdConfig with all 4 filter toggles True (default)."""
    return BellbirdConfig(
        filter_strip_markdown=True,
        filter_strip_urls=True,
        filter_strip_emojis=True,
        filter_strip_code_blocks=True,
    )


def _cfg_all_off() -> BellbirdConfig:
    """Return a BellbirdConfig with all 4 filter toggles False."""
    return BellbirdConfig(
        filter_strip_markdown=False,
        filter_strip_urls=False,
        filter_strip_emojis=False,
        filter_strip_code_blocks=False,
    )


# ── All-off / Empty / Never-raises ────────────────────────────────────


class TestApplyFiltersBasics:
    """Identity, empty input, and never-crash contract."""

    def test_all_toggles_off_returns_input(self):
        """GIVEN all 4 filter toggles are False
        WHEN apply_filters is called
        THEN the input is returned unchanged."""
        from bellbird.core.text_filters import apply_filters

        text = "Hello **bold** https://x.com 👋 ```code```"
        result = apply_filters(text, _cfg_all_off())
        assert result == text

    def test_empty_input_returns_empty(self):
        """GIVEN an empty string
        WHEN apply_filters is called
        THEN empty string is returned."""
        from bellbird.core.text_filters import apply_filters

        result = apply_filters("", _cfg_all_on())
        assert result == ""

    def test_never_raises_on_none_input(self):
        """GIVEN None as text (defensive)
        WHEN apply_filters is called
        THEN no exception propagates, a string is returned."""
        from bellbird.core.text_filters import apply_filters

        result = apply_filters(None, _cfg_all_on())  # type: ignore[arg-type]
        assert isinstance(result, str)

    def test_never_raises_on_invalid_config(self):
        """GIVEN a config missing the filter toggle attributes
        WHEN apply_filters is called
        THEN no exception propagates, input is returned."""
        from bellbird.core.text_filters import apply_filters

        # A vanilla object without any filter_* attributes
        class MinimalConfig:
            pass

        result = apply_filters("hello", MinimalConfig())
        assert result == "hello"


# ── Individual filter steps ──────────────────────────────────────────


class TestStripMarkdown:
    """filter_strip_markdown toggle reuses core.text_utils.strip_markdown."""

    def test_strip_markdown_toggle_on(self):
        """GIVEN filter_strip_markdown=True
        WHEN apply_filters receives bold markdown
        THEN the ** markers are removed."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=True,
            filter_strip_urls=False,
            filter_strip_emojis=False,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("**bold**", cfg)
        assert result == "bold"
        assert "**" not in result

    def test_strip_markdown_toggle_off(self):
        """GIVEN filter_strip_markdown=False
        WHEN apply_filters receives bold markdown
        THEN the ** markers are preserved."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=False,
            filter_strip_emojis=False,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("**bold**", cfg)
        assert result == "**bold**"

    def test_strip_markdown_reuses_text_utils(self):
        """GIVEN filter_strip_markdown=True
        WHEN apply_filters is called
        THEN the result equals text_utils.strip_markdown(input)."""
        from bellbird.core.text_filters import apply_filters
        from bellbird.core.text_utils import strip_markdown

        text = "# Title\n**bold** and [link](url)"
        result = apply_filters(text, _cfg_all_on())
        expected = strip_markdown(text)
        assert result == expected


class TestStripUrls:
    """filter_strip_urls toggle removes http(s):// URLs."""

    def test_strip_urls_on(self):
        """GIVEN filter_strip_urls=True
        WHEN input contains an HTTPS URL
        THEN the URL is removed."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=True,
            filter_strip_emojis=False,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("See https://example.com for details", cfg)
        assert "https://" not in result
        # The URL is gone; we tolerate double-space
        assert result == "See  for details"

    def test_strip_urls_http(self):
        """GIVEN filter_strip_urls=True
        WHEN input contains an HTTP URL
        THEN the URL is removed."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=True,
            filter_strip_emojis=False,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("Visit http://example.org today", cfg)
        assert "http://" not in result
        assert result == "Visit  today"

    def test_strip_urls_preserves_bare_hostnames(self):
        """GIVEN filter_strip_urls=True
        WHEN input contains a bare hostname (no scheme)
        THEN the hostname is preserved."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=True,
            filter_strip_emojis=False,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("See example.com for details", cfg)
        assert result == "See example.com for details"

    def test_strip_urls_off(self):
        """GIVEN filter_strip_urls=False
        WHEN input contains a URL
        THEN the URL is preserved."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=False,
            filter_strip_emojis=False,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("See https://x.com", cfg)
        assert "https://x.com" in result


class TestStripEmojis:
    """filter_strip_emojis toggle removes Unicode emoji characters."""

    def test_strip_emojis_on_wave(self):
        """GIVEN filter_strip_emojis=True
        WHEN input contains a wave emoji
        THEN the emoji is removed."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=False,
            filter_strip_emojis=True,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("Hello 👋 world", cfg)
        assert "👋" not in result

    def test_strip_emojis_multiple(self):
        """GIVEN filter_strip_emojis=True
        WHEN input contains multiple emojis
        THEN all emojis are removed."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=False,
            filter_strip_emojis=True,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("🎉 party 🚀 launch", cfg)
        assert "🎉" not in result
        assert "🚀" not in result

    def test_strip_emojis_preserves_ascii_punctuation(self):
        """GIVEN filter_strip_emojis=True
        WHEN input contains Spanish punctuation
        THEN punctuation is preserved (not mistaken for emoji)."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=False,
            filter_strip_emojis=True,
            filter_strip_code_blocks=False,
        )
        text = "¡Hola! ¿Cómo estás? Listo: sí."
        result = apply_filters(text, cfg)
        assert result == text

    def test_strip_emojis_off(self):
        """GIVEN filter_strip_emojis=False
        WHEN input contains emojis
        THEN the emojis are preserved."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=False,
            filter_strip_emojis=False,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("Hello 👋 world", cfg)
        assert "👋" in result


class TestStripCodeBlocks:
    """filter_strip_code_blocks toggle removes fenced ```...``` blocks."""

    def test_strip_code_blocks_on(self):
        """GIVEN filter_strip_code_blocks=True
        WHEN input contains a fenced code block
        THEN the backticks are removed."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=False,
            filter_strip_emojis=False,
            filter_strip_code_blocks=True,
        )
        result = apply_filters("text ```code block``` more", cfg)
        assert "```" not in result
        # The content between backticks is preserved
        assert "code block" in result

    def test_strip_code_blocks_with_language_tag(self):
        """GIVEN filter_strip_code_blocks=True
        WHEN input contains a fenced block with a language tag
        THEN the backticks and language tag are removed, content preserved."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=False,
            filter_strip_emojis=False,
            filter_strip_code_blocks=True,
        )
        result = apply_filters("```python\nprint(1)\n```", cfg)
        assert "```" not in result
        assert "print(1)" in result

    def test_strip_code_blocks_off(self):
        """GIVEN filter_strip_code_blocks=False
        WHEN input contains a fenced block
        THEN the backticks are preserved."""
        from bellbird.core.text_filters import apply_filters

        cfg = BellbirdConfig(
            filter_strip_markdown=False,
            filter_strip_urls=False,
            filter_strip_emojis=False,
            filter_strip_code_blocks=False,
        )
        result = apply_filters("text ```code``` more", cfg)
        assert "```" in result


# ── Pipeline order ──────────────────────────────────────────────────


class TestApplyFiltersOrder:
    """Fixed order: strip_markdown → strip_urls → strip_emojis → strip_code_blocks."""

    def test_order_is_strip_markdown_first(self):
        """GIVEN all filters ON
        WHEN input is a markdown link wrapping a URL
        THEN strip_markdown removes the link syntax first,
        THEN the residual URL is removed by strip_urls.
        Final: 'link' (not the raw markdown)."""
        from bellbird.core.text_filters import apply_filters

        result = apply_filters("[link](https://example.com)", _cfg_all_on())
        # strip_markdown removes [link](url) → "link"
        # strip_urls no-op (no bare URL)
        assert result == "link"

    def test_order_is_strip_urls_second(self):
        """GIVEN all filters ON
        WHEN input has a bare URL and a code block
        THEN strip_markdown no-op (no markdown)
        THEN strip_urls removes the URL
        THEN strip_emojis no-op
        THEN strip_code_blocks removes ```code```.
        Final: 'text   end' (URL becomes space gap)."""
        from bellbird.core.text_filters import apply_filters

        result = apply_filters("text https://example.com ```code``` end", _cfg_all_on())
        # strip_markdown: no-op (no markdown in this input)
        # strip_urls: "text  ```code``` end"  (URL removed -> double space)
        # strip_emojis: no-op
        # strip_code_blocks: "text   end" (backticks removed -> content with spaces)
        assert "https://" not in result
        assert "```" not in result
        # end is still there
        assert "end" in result


# ── AST guard ──────────────────────────────────────────────────────


class TestTextFiltersASTGuards:
    """AST-level guards: no wx import, no redefinition of strip_markdown."""

    def test_ast_no_wx_import(self):
        """GIVEN the source of bellbird/core/text_filters.py
        WHEN parsed with ast
        THEN no Import or ImportFrom node references 'wx'."""
        source = (__file__.replace(
            "tests/core/test_text_filters.py", "bellbird/core/text_filters.py"
        ))
        with open(source, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    assert "wx" not in alias.name, (
                        f"wx import found in text_filters.py: {alias.name}"
                    )

    def test_no_strip_markdown_redefinition(self):
        """GIVEN the source of bellbird/core/text_filters.py
        WHEN parsed with ast
        THEN no 'def strip_markdown' is found (reuses core.text_utils)."""
        source = (__file__.replace(
            "tests/core/test_text_filters.py", "bellbird/core/text_filters.py"
        ))
        with open(source, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "strip_markdown":
                pytest.fail("text_filters.py redefines strip_markdown (should import from text_utils)")


# ── Private helper tests (direct unit tests) ───────────────────────


class TestPrivateHelpers:
    """Direct tests for the 3 private regex helpers."""

    def test_strip_urls_removes_https(self):
        """GIVEN _strip_urls with an HTTPS URL
        THEN the URL is removed."""
        from bellbird.core.text_filters import _strip_urls

        result = _strip_urls("See https://example.com/path?q=1 for details")
        assert "https://" not in result

    def test_strip_urls_removes_http(self):
        """GIVEN _strip_urls with an HTTP URL
        THEN the URL is removed."""
        from bellbird.core.text_filters import _strip_urls

        result = _strip_urls("Visit http://example.org today")
        assert "http://" not in result

    def test_strip_urls_preserves_bare(self):
        """GIVEN _strip_urls with a bare hostname
        THEN the hostname is preserved."""
        from bellbird.core.text_filters import _strip_urls

        result = _strip_urls("See example.com for details")
        assert "example.com" in result

    def test_strip_emojis_removes_emoji(self):
        """GIVEN _strip_emojis with an emoji
        THEN the emoji is removed."""
        from bellbird.core.text_filters import _strip_emojis

        result = _strip_emojis("Hello 👋 world")
        assert "👋" not in result

    def test_strip_emojis_preserves_punctuation(self):
        """GIVEN _strip_emojis with Spanish punctuation
        THEN punctuation is preserved."""
        from bellbird.core.text_filters import _strip_emojis

        result = _strip_emojis("¡Hola! ¿Cómo estás?")
        assert result == "¡Hola! ¿Cómo estás?"

    def test_strip_code_blocks_removes_fence(self):
        """GIVEN _strip_code_blocks with a fenced block
        THEN the backticks are removed."""
        from bellbird.core.text_filters import _strip_code_blocks

        result = _strip_code_blocks("text ```code block``` more")
        assert "```" not in result
        assert "code block" in result

    def test_strip_code_blocks_with_language(self):
        """GIVEN _strip_code_blocks with a language-tagged block
        THEN backticks and language tag are removed."""
        from bellbird.core.text_filters import _strip_code_blocks

        result = _strip_code_blocks("```python\nprint(1)\n```")
        assert "```" not in result
        assert "python" not in result
        assert "print(1)" in result
