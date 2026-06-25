"""Tests for html_render module — strict TDD, RED first, then GREEN."""

import re

import pytest


# ─── Template structure ─────────────────────────────────────────────────────


def test_template_has_lang_and_charset():
    """GIVEN empty text
    WHEN render_message_html("") is called
    THEN the output contains lang="es", charset="utf-8",
    and starts with <!doctype html> (case-insensitive)."""
    from bellbird.core.html_render import render_message_html

    result = render_message_html("")
    assert 'lang="es"' in result
    assert 'charset="utf-8"' in result
    assert result.lstrip().lower().startswith("<!doctype html>")


# ─── Fenced code ────────────────────────────────────────────────────────────


def test_fenced_code_renders_as_pre_code():
    """GIVEN text with a fenced code block
    WHEN render_message_html is called
    THEN the output contains <pre><code> and </code></pre>."""
    from bellbird.core.html_render import render_message_html

    text = "before\n```python\nprint('hi')\n```\nafter"
    result = render_message_html(text)
    assert "<pre><code" in result
    assert "</code></pre>" in result
    assert "print" in result


# ─── Markdown tables ────────────────────────────────────────────────────────


def test_markdown_table_renders_as_table():
    """GIVEN a markdown table
    WHEN render_message_html is called
    THEN the output contains <table>, </table>, <th> and <td>."""
    from bellbird.core.html_render import render_message_html

    text = (
        "| Header 1 | Header 2 |\n"
        "|----------|----------|\n"
        "| Cell 1   | Cell 2   |\n"
    )
    result = render_message_html(text)
    assert "<table>" in result
    assert "</table>" in result
    assert "<th>" in result or "<th " in result
    assert "<td>" in result or "<td " in result


# ─── Reasoning in <details> ─────────────────────────────────────────────────


def test_reasoning_in_details_block():
    """GIVEN non-empty reasoning
    WHEN render_message_html(text, reasoning="thinking here") is called
    THEN the output contains <details>, <summary>Razonamiento</summary>,
    the reasoning text, and <details> index < body content index."""
    from bellbird.core.html_render import render_message_html

    result = render_message_html("content body", reasoning="thinking here")
    assert "<details>" in result
    assert "<summary>Razonamiento</summary>" in result
    assert "thinking here" in result
    # The <details> block must appear BEFORE the body content
    details_pos = result.index("<details>")
    body_pos = result.index("content body")
    assert details_pos < body_pos


def test_no_details_when_reasoning_absent():
    """GIVEN reasoning=None
    WHEN render_message_html(text) is called
    THEN the output does NOT contain <details> or Razonamiento."""
    from bellbird.core.html_render import render_message_html

    result = render_message_html("content body", reasoning=None)
    assert "<details>" not in result
    assert "Razonamiento" not in result


def test_no_details_when_reasoning_empty():
    """GIVEN reasoning=""
    WHEN render_message_html(text, reasoning="") is called
    THEN the output does NOT contain <details>."""
    from bellbird.core.html_render import render_message_html

    result = render_message_html("content body", reasoning="")
    assert "<details>" not in result


# ─── CSS ────────────────────────────────────────────────────────────────────


def test_css_style_block_present():
    """GIVEN any input
    WHEN render_message_html is called
    THEN the output contains <style>, </style>, body {, pre code rules,
    and no hardcoded #hex colors."""
    from bellbird.core.html_render import render_message_html

    result = render_message_html("hello")
    assert "<style>" in result
    assert "</style>" in result
    assert "body {" in result
    # No hardcoded #hex colors in the CSS
    style_match = re.search(r"<style>(.*?)</style>", result, re.DOTALL)
    assert style_match is not None, "Could not extract <style> block"
    css = style_match.group(1)
    hex_colors = re.findall(r"#[0-9a-fA-F]{3,8}", css)
    assert len(hex_colors) == 0, (
        f"Found hardcoded #hex colors in CSS: {hex_colors}"
    )


# ─── XSS safety ─────────────────────────────────────────────────────────────


def test_html_in_text_is_escaped():
    """GIVEN text containing <script>alert(1)</script>
    WHEN render_message_html is called
    THEN the output contains &lt;script&gt; and NOT the raw <script> tag."""
    from bellbird.core.html_render import render_message_html

    text = "Hello <script>alert(1)</script> world"
    result = render_message_html(text)
    assert "<script>alert(1)</script>" not in result
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result


# ─── Reasoning with markdown ────────────────────────────────────────────────


def test_reasoning_with_code_fence():
    """GIVEN reasoning containing a fenced code block
    WHEN render_message_html(text, reasoning=reasoning) is called
    THEN the output contains BOTH <details> and <pre><code> inside it."""
    from bellbird.core.html_render import render_message_html

    reasoning = "```py\nx=1\n```"
    result = render_message_html("hello", reasoning=reasoning)
    assert "<details>" in result
    assert "<pre><code" in result
    # The <pre><code> from reasoning must be between <summary> and </details>
    summary_pos = result.index("<summary>Razonamiento</summary>")
    details_close_pos = result.index("</details>")
    pre_pos = result.index("<pre><code")
    assert summary_pos < pre_pos < details_close_pos, (
        "<pre><code> must be inside <details> after <summary>"
    )


# ─── Edge cases ─────────────────────────────────────────────────────────────


def test_empty_text_does_not_raise():
    """GIVEN empty text and reasoning=None
    WHEN render_message_html("") is called
    THEN no exception is raised and output is a valid document."""
    from bellbird.core.html_render import render_message_html

    result = render_message_html("", reasoning=None)
    assert result.lstrip().lower().startswith("<!doctype html>")
    assert result.rstrip().endswith("</html>")


def test_reasoning_none_treated_as_absent():
    """GIVEN reasoning=None (explicit)
    WHEN render_message_html is called
    THEN <details> is NOT in the output."""
    from bellbird.core.html_render import render_message_html

    result = render_message_html("hello", reasoning=None)
    assert "<details>" not in result
