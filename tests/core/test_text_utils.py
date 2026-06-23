"""Tests for text_utils module — strict TDD, RED first, then GREEN."""


def test_strip_headers():
    """Given markdown headers, strip_markdown removes the # markers."""
    from bellbird.core.text_utils import strip_markdown

    result = strip_markdown("# Title\n\nBody")
    assert result == "Title\n\nBody"


def test_strip_bold_italic():
    """Given bold markers, strip_markdown removes the ** markers."""
    from bellbird.core.text_utils import strip_markdown

    result = strip_markdown("**bold**")
    assert result == "bold"


def test_strip_code_fences():
    """Given fenced code blocks, strip_markdown removes backticks."""
    from bellbird.core.text_utils import strip_markdown

    result = strip_markdown("```\nfoo\nbar\n```")
    assert "foo" in result
    assert "bar" in result
    assert "```" not in result


def test_strip_inline_code():
    """Given inline code, strip_markdown removes the backticks."""
    from bellbird.core.text_utils import strip_markdown

    result = strip_markdown("`x`")
    assert result == "x"


def test_strip_links():
    """Given markdown links, strip_markdown keeps text but removes URL."""
    from bellbird.core.text_utils import strip_markdown

    result = strip_markdown("[docs](https://example.com)")
    assert result == "docs"


def test_strip_list_items():
    """Given list items, strip_markdown replaces - with bullet character."""
    from bellbird.core.text_utils import strip_markdown

    result = strip_markdown("- a\n- b")
    assert result.startswith("• a")
    assert "• b" in result


def test_strip_empty_string():
    """Given an empty string, strip_markdown returns empty string."""
    from bellbird.core.text_utils import strip_markdown

    result = strip_markdown("")
    assert result == ""


def test_strip_plain_text_unchanged():
    """Given plain text, strip_markdown strips whitespace only."""
    from bellbird.core.text_utils import strip_markdown

    result = strip_markdown("  hello  ")
    assert result == "hello"
