"""wx-free HTML rendering for chat messages.

Exports a single public function ``render_message_html`` that takes
markdown text and optional reasoning and returns a complete HTML
document string. The module has no dependency on wxPython, making it
testable on WSL.
"""

import html

import markdown

# Extensions used for rendering both the main message and reasoning.
MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "sane_lists", "nl2br"]

# Inline CSS — uses rgba(127,127,127, X) alpha blending so the colours
# adapt to the browser's theme (light/dark/high-contrast).
CSS = """
body { max-width: 920px; margin: 2rem auto; padding: 0 1rem;
       line-height: 1.6; font-family: -apple-system, BlinkMacSystemFont,
       "Segoe UI", Roboto, sans-serif; }
pre { background: rgba(127,127,127,0.08); padding: 0.75rem;
      border-radius: 4px; overflow-x: auto; }
code { font-family: Consolas, "Courier New", monospace; font-size: 0.95em; }
pre code { background: transparent; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid rgba(127,127,127,0.4); padding: 0.4rem 0.6rem;
         text-align: left; }
th { font-weight: 600; }
details { margin: 1rem 0; padding: 0.5rem 0.75rem;
          border-left: 3px solid rgba(127,127,127,0.5);
          background: rgba(127,127,127,0.04); }
summary { cursor: pointer; font-weight: 600; }
h1, h2, h3, h4 { line-height: 1.3; margin-top: 1.5rem; }
blockquote { border-left: 3px solid rgba(127,127,127,0.4);
             padding-left: 1rem; margin-left: 0; opacity: 0.85; }
"""

# Complete HTML document template.
HTML_TEMPLATE = (
    "<!doctype html>"
    '<html lang="es">'
    "<head>"
    '<meta charset="utf-8">'
    "<title>{title}</title>"
    "<style>{css}</style>"
    "</head>"
    "<body>{body}</body>"
    "</html>"
)

TITLE = "Bellbird — Mensaje"


def _render_markdown(text: str) -> str:
    """Helper: escape raw HTML then render markdown with standard extensions.

    Pre-escaping prevents XSS via raw HTML passthrough (markdown preserves
    raw HTML by default). Blockquote ``>`` and autolink ``<url>`` syntax
    are affected but very rare in chat LLM messages.
    """
    return markdown.markdown(
        html.escape(text),
        extensions=MARKDOWN_EXTENSIONS,
    )


def render_message_html(text: str, reasoning: str | None = None) -> str:
    """Render a chat message as a complete HTML document for browser viewing.

    The markdown extensions ``fenced_code``, ``tables``, ``sane_lists``
    and ``nl2br`` are applied. When ``reasoning`` is non-empty, it is
    rendered as markdown and wrapped in a ``<details><summary>
    Razonamiento</summary>...</details>`` block above the content.

    The output document declares ``lang="es"`` and ``charset="utf-8"``
    and embeds a minimal readable CSS (system fonts, monospace for
    code, subtle table borders, distinguished summary).

    HTML in the input is escaped by ``html.escape()`` (applied before
    ``markdown.markdown()``), so user content with literal ``<script>``
    is safe.

    Args:
        text: Markdown text of the message.
        reasoning: Optional chain-of-thought text. When non-empty,
            rendered as markdown inside a ``<details>`` above the
            main content.

    Returns:
        Full HTML document string (doctype + head + body).
    """
    body_html = _render_markdown(text)

    if reasoning:
        reasoning_html = _render_markdown(reasoning)
        details = (
            "<details>"
            "<summary>Razonamiento</summary>"
            f"{reasoning_html}"
            "</details>"
        )
        body_html = details + body_html

    return HTML_TEMPLATE.format(
        title=TITLE,
        css=CSS,
        body=body_html,
    )
