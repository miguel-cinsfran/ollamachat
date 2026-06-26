"""Reading filters for Bellbird TTS — wx-free, strict TDD.

Provides apply_filters(), a pure function that strips unwanted content
from text before TTS output. The 4 filters run in a fixed order:

    strip_markdown → strip_urls → strip_emojis → strip_code_blocks

Each step is gated by a BellbirdConfig.filter_strip_* toggle.
When all toggles are False, apply_filters is a no-op that returns
the input unchanged.

The strip_markdown step reuses bellbird.core.text_utils.strip_markdown.
The 3 other helpers are private regex functions in this module.
"""

import re
from typing import Any, Optional

# Regex: http(s):// followed by non-whitespace characters
_URL_PATTERN = re.compile(r"https?://\S+")

# Regex: Unicode emoji ranges (broad but conservative)
# Covers: U+1F300–U+1FAFF (Misc Symbols, Emoticons, etc.),
#         U+2600–U+27BF (Misc Symbols, Dingbats),
#         U+FE00–U+FE0F (Variation Selectors),
#         U+200D (ZWJ - zero-width joiner for skin tones/families),
#         plus supplemental ranges.
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # Misc Symbols, Emoticons, etc.
    "\U00002600-\U000027BF"  # Misc Symbols, Dingbats
    "\U0000FE00-\U0000FE0F"  # Variation Selectors
    "\U0000200D"             # ZWJ (zero-width joiner)
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols
    "\U0001FA00-\U0001FA6F"  # Chess symbols
    "\U0001FA70-\U0001FAFF"  # Symbols Extended-A
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"  # Enclosed alphanumerics
    "]",
    flags=re.UNICODE,
)

# Regex: fenced code blocks ```...``` with optional language tag.
# Language tag (```python) is only matched when followed by a newline;
# inline ```code``` has no language tag consumed.
_CODE_BLOCK_PATTERN = re.compile(r"```(?:\w+\n)?([\s\S]*?)```")


def apply_filters(text: Any, config: Any) -> str:
    """Apply enabled reading filters in fixed order.

    Pure function: same (text, config) → same output, no side effects.
    Never raises — returns the input verbatim on any error.

    Order: strip_markdown → strip_urls → strip_emojis → strip_code_blocks.

    Args:
        text: The input string to filter.
        config: Any object with ``filter_strip_markdown``,
            ``filter_strip_urls``, ``filter_strip_emojis``,
            ``filter_strip_code_blocks`` attributes (typically a
            BellbirdConfig).

    Returns:
        Filtered string. Returns ``""`` for empty/falsy input.
        Returns the input unchanged if all toggles are False or on error.
    """
    try:
        if not text:
            return ""
        return _run_pipeline(text, config)
    except Exception:
        # Never-crash contract: return input verbatim on any error
        if isinstance(text, str):
            return text
        return str(text) if text is not None else ""


def _run_pipeline(text: str, config: Any) -> str:
    """Run the 4-step filter pipeline in fixed order."""
    # Step 1: strip_markdown (reuses core.text_utils)
    if _toggle_on(config, "filter_strip_markdown"):
        from bellbird.core.text_utils import strip_markdown

        text = strip_markdown(text)

    # Step 2: strip URLs
    if _toggle_on(config, "filter_strip_urls"):
        text = _strip_urls(text)

    # Step 3: strip emojis
    if _toggle_on(config, "filter_strip_emojis"):
        text = _strip_emojis(text)

    # Step 4: strip code blocks
    if _toggle_on(config, "filter_strip_code_blocks"):
        text = _strip_code_blocks(text)

    return text


def _toggle_on(config: Any, attr: str) -> bool:
    """Safely check a boolean toggle attribute.

    Returns ``False`` if the attribute is missing or not a bool-like value.
    """
    try:
        val = getattr(config, attr, False)
        return bool(val)
    except Exception:
        return False


def _strip_urls(text: str) -> str:
    """Drop http(s):// URLs from text.

    Args:
        text: Input string.

    Returns:
        Text with https?:// URLs removed.
    """
    return _URL_PATTERN.sub("", text)


def _strip_emojis(text: str) -> str:
    """Drop Unicode emoji characters from text.

    Uses a broad regex covering canonical emoji ranges.
    ASCII punctuation (¡, ¿, !, ?, etc.) is preserved.

    Args:
        text: Input string.

    Returns:
        Text with emoji characters removed.
    """
    return _EMOJI_PATTERN.sub("", text)


def _strip_code_blocks(text: str) -> str:
    """Drop fenced ```...``` code blocks.

    Handles optional language tag after the opening fence.
    Multiline content inside the fence is preserved (without the
    backticks). Inline single backticks are NOT affected.

    Args:
        text: Input string.

    Returns:
        Text with fenced code block delimiters removed.
    """
    return _CODE_BLOCK_PATTERN.sub(r"\1", text)
