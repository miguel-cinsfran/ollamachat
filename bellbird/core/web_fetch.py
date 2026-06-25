"""Fetch web page content as plain text — wx-free, strict TDD.

Provides ``FetchResult`` (frozen dataclass) and ``fetch_text()`` for
downloading a web page and extracting its readable text using only
stdlib ``html.parser`` and ``requests``. Never raises to the caller —
all errors are data inside ``FetchResult``.
"""

import html
import html.parser
import re
from dataclasses import dataclass
from typing import Optional

import requests

# Bellbird version for User-Agent header.
# TODO: read from pyproject.toml dynamically when a version import exists.
_BELLBIRD_VERSION = "0.8.3"

# Scheme validation: only http:// and https:// are allowed.
_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


# ─── Result dataclass ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FetchResult:
    """Result of a ``fetch_text`` call.

    Never raises — all errors are captured as data in this object so the
    caller always gets a ``FetchResult``, never an exception.

    Attributes:
        ok: Whether the fetch succeeded (2xx/3xx status).
        text: Extracted readable text (empty on failure).
        error: Human-readable error message, or ``None`` on success.
        url: The original URL that was fetched.
        status_code: HTTP status code, or ``None`` if no response.
        truncated: ``True`` if the text was truncated to ``max_chars``.
        original_size: Length of the text before truncation, or ``None``.
    """

    ok: bool
    text: str
    error: str | None
    url: str
    status_code: int | None
    truncated: bool
    original_size: int | None


# ─── HTML → text extraction ───────────────────────────────────────────────────


class _HTMLTextExtractor(html.parser.HTMLParser):
    """HTMLParser that skips ``<script>`` and ``<style>`` content.

    Collects text from ``handle_data`` only when outside those tags,
    then returns the concatenated result via ``get_text()``.
    """

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def _clean_html(raw: str) -> str:
    """Strip script/style, extract text, unescape entities, collapse whitespace."""
    extractor = _HTMLTextExtractor()
    extractor.feed(raw)
    text = extractor.get_text()
    text = html.unescape(text)
    # Collapse runs of whitespace into single spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ─── Main fetch function ──────────────────────────────────────────────────────


def fetch_text(url: str, *, timeout: int = 10, max_chars: int = 50000) -> FetchResult:
    """Download a URL and extract readable text.

    Args:
        url: The URL to fetch (only ``http://`` and ``https://``).
        timeout: Request timeout in seconds (default 10).
        max_chars: Maximum characters for the returned text (default 50_000).

    Returns:
        ``FetchResult`` — never raises. Use ``result.ok`` to check success.
    """
    # ── Empty URL guard ───────────────────────────────────────────────────
    if not url:
        return FetchResult(
            ok=False,
            text="",
            error="URL vacía",
            url=url,
            status_code=None,
            truncated=False,
            original_size=None,
        )

    # ── Scheme pre-validation (SSRF guard) ─────────────────────────────────
    if not _SCHEME_RE.match(url):
        return FetchResult(
            ok=False,
            text="",
            error="scheme no permitido, solo http o https",
            url=url,
            status_code=None,
            truncated=False,
            original_size=None,
        )

    # ── HTTP request ───────────────────────────────────────────────────────
    try:
        response = requests.get(
            url,
            headers={"User-Agent": f"Bellbird/{_BELLBIRD_VERSION}"},
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        return FetchResult(
            ok=False,
            text="",
            error="Timeout de conexión",
            url=url,
            status_code=None,
            truncated=False,
            original_size=None,
        )
    except requests.exceptions.ConnectionError:
        return FetchResult(
            ok=False,
            text="",
            error="Error de conexión",
            url=url,
            status_code=None,
            truncated=False,
            original_size=None,
        )
    except requests.exceptions.RequestException as e:
        return FetchResult(
            ok=False,
            text="",
            error=str(e),
            url=url,
            status_code=None,
            truncated=False,
            original_size=None,
        )

    # ── Encoding and text extraction ───────────────────────────────────────
    try:
        raw_html = response.text
    except Exception:
        # Fallback: decode with apparent encoding
        raw_html = response.content.decode(response.apparent_encoding, errors="replace")

    text = _clean_html(raw_html)
    original_size = len(text)
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    success = 200 <= response.status_code < 400

    return FetchResult(
        ok=success,
        text=text,
        error=None if success else f"HTTP {response.status_code}: {response.reason}",
        url=url,
        status_code=response.status_code,
        truncated=truncated,
        original_size=original_size,
    )
