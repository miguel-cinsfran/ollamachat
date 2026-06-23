"""Text utilities for Bellbird.

Provides strip_markdown() to convert markdown text into plain text
suitable for screen reader output. Uses only the 're' standard library
module — no external dependencies.
"""

import re


def strip_markdown(text: str) -> str:
    """Strip common markdown formatting from a string.

    Applies a fixed pipeline of regex substitutions in this order:
    headers → bold → italic → fenced code → inline code → links →
    list items → strip().

    Args:
        text: Markdown-formatted input string.

    Returns:
        Plain text with markdown markers removed.
    """
    # Headers: remove leading # characters and space
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)

    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)

    # Fenced code blocks: ```...``` with optional language tag
    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", r"\1", text)

    # Inline code: `text`
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Links: [text](url) or [text](url "title")
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)

    # List items: - or * or + at line start → bullet character
    text = re.sub(r"^[\s]*[-*+]\s+", "• ", text, flags=re.MULTILINE)

    return text.strip()
