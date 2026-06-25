"""Tests for bellbird.core.web_fetch — strict TDD, wx-free.

Covers: FetchResult frozen dataclass, fetch_text success, scheme guard,
HTML cleaning (script/style stripping, entity unescape, unicode), network
errors, timeouts, HTTP errors, truncation, redirects, User-Agent header,
empty/malformed URLs, and AST guard (no wx import).
"""

import ast
import re

import pytest

from bellbird.core.web_fetch import FetchResult, fetch_text


# ─── Mock helpers ─────────────────────────────────────────────────────────────


class MockResponse:
    """Minimal mock for requests.Response."""

    def __init__(self, text="", status_code=200, reason="OK", apparent_encoding="utf-8"):
        self.text = text
        self.status_code = status_code
        self.reason = reason
        self.apparent_encoding = apparent_encoding
        self.content = text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ─── FetchResult dataclass ────────────────────────────────────────────────────


class TestFetchResult:
    """FetchResult is a frozen dataclass with the documented fields."""

    def test_frozen(self):
        r = FetchResult(
            ok=True, text="hello", error=None,
            url="https://e.com", status_code=200,
            truncated=False, original_size=None,
        )
        with pytest.raises(AttributeError):
            r.ok = False

    def test_all_fields_present(self):
        r = FetchResult(
            ok=True, text="hello", error=None,
            url="https://e.com", status_code=200,
            truncated=False, original_size=None,
        )
        assert r.ok is True
        assert r.text == "hello"
        assert r.error is None
        assert r.url == "https://e.com"
        assert r.status_code == 200
        assert r.truncated is False
        assert r.original_size is None


# ─── fetch_text — scheme guard ─────────────────────────────────────────────────


class TestSchemeGuard:
    """Pre-request scheme validation — no requests call made."""

    def test_invalid_scheme_file(self):
        result = fetch_text("file:///etc/passwd")
        assert result.ok is False
        assert "scheme no permitido" in result.error
        assert result.status_code is None

    def test_invalid_scheme_ftp(self):
        result = fetch_text("ftp://example.com/file.txt")
        assert result.ok is False
        assert "scheme no permitido" in result.error

    def test_invalid_scheme_gopher(self):
        result = fetch_text("gopher://example.com")
        assert result.ok is False
        assert "scheme no permitido" in result.error

    def test_empty_url_returns_error(self):
        result = fetch_text("")
        assert result.ok is False
        assert result.error


# ─── fetch_text — success path ─────────────────────────────────────────────────


class TestFetchTextSuccess:
    """Happy path: simple HTML → clean text."""

    def test_fetch_text_success(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(
                text="<html><body><p>Hello world</p></body></html>",
                status_code=200,
            ),
        )
        result = fetch_text("https://example.com")
        assert result.ok is True
        assert "Hello world" in result.text
        assert result.status_code == 200
        assert result.truncated is False

    def test_fetch_text_allows_redirects(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        captured = {}

        def mock_get(url, **kw):
            captured["allow_redirects"] = kw.get("allow_redirects")
            return MockResponse(text="ok", status_code=200)

        monkeypatch.setattr(wf.requests, "get", mock_get)
        fetch_text("https://example.com")
        assert captured.get("allow_redirects") is True

    def test_fetch_text_uses_custom_user_agent(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        captured = {}

        def mock_get(url, **kw):
            captured["headers"] = kw.get("headers", {})
            return MockResponse(text="ok", status_code=200)

        monkeypatch.setattr(wf.requests, "get", mock_get)
        fetch_text("https://example.com")
        ua = captured["headers"].get("User-Agent", "")
        assert ua.startswith("Bellbird/"), f"UA should start with Bellbird/, got {ua!r}"


# ─── fetch_text — HTML cleaning ────────────────────────────────────────────────


class TestHtmlCleaning:
    """HTML → text: strip script/style, unescape entities, preserve unicode."""

    def test_fetch_text_strips_script_content(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(
                text="<script>alert(1)</script><p>Hello</p>",
            ),
        )
        result = fetch_text("https://example.com")
        assert "alert" not in result.text
        assert "Hello" in result.text

    def test_fetch_text_strips_style_content(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(
                text="<style>body{color:red}</style><p>Hello</p>",
            ),
        )
        result = fetch_text("https://example.com")
        assert "color" not in result.text
        assert "Hello" in result.text

    def test_fetch_text_unescapes_html_entities(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(
                text="<p>a&amp;b&nbsp;c&lt;d&gt;e&quot;f</p>",
            ),
        )
        result = fetch_text("https://example.com")
        assert "&amp;" not in result.text
        assert "\u00a0" in result.text or "&nbsp;" not in result.text
        assert "&lt;" not in result.text
        assert "&gt;" not in result.text
        assert "&quot;" not in result.text

    def test_fetch_text_handles_unicode(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(
                text="<p>Hola mundo áéíóú 😊</p>",
            ),
        )
        result = fetch_text("https://example.com")
        assert "áéíóú" in result.text
        assert "😊" in result.text


# ─── fetch_text — truncated ────────────────────────────────────────────────────


class TestTruncation:
    """Truncation when content exceeds max_chars."""

    def test_fetch_text_truncates_large_response(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        long_text = "<p>" + "x" * 60000 + "</p>"
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(text=long_text),
        )
        result = fetch_text("https://example.com", max_chars=50000)
        assert result.truncated is True
        assert len(result.text) == 50000
        assert result.original_size is not None
        assert result.original_size > 50000


# ─── fetch_text — HTTP errors ──────────────────────────────────────────────────


class TestHttpErrors:
    """4xx/5xx status codes produce ok=False with status_code preserved."""

    def test_fetch_text_status_404(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(text="Not Found", status_code=404, reason="Not Found"),
        )
        result = fetch_text("https://example.com/404")
        assert result.ok is False
        assert result.status_code == 404
        assert "404" in result.error

    def test_fetch_text_status_500(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(text="Error", status_code=500, reason="Internal Server Error"),
        )
        result = fetch_text("https://example.com/500")
        assert result.ok is False
        assert result.status_code == 500
        assert "500" in result.error


# ─── fetch_text — network errors ───────────────────────────────────────────────


class TestNetworkErrors:
    """Network errors produce ok=False, never raise."""

    def test_fetch_text_network_error_returns_result(self, monkeypatch):
        import requests
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: (_ for _ in ()).throw(requests.exceptions.ConnectionError("connection refused")),
        )
        result = fetch_text("https://example.com")
        assert result.ok is False
        assert result.error
        assert result.status_code is None

    def test_fetch_text_timeout_returns_result(self, monkeypatch):
        import requests
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: (_ for _ in ()).throw(requests.exceptions.Timeout("timed out")),
        )
        result = fetch_text("https://example.com")
        assert result.ok is False
        assert result.error
        assert result.status_code is None

    def test_fetch_text_generic_request_exception(self, monkeypatch):
        import requests
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: (_ for _ in ()).throw(requests.exceptions.RequestException("generic")),
        )
        result = fetch_text("https://example.com")
        assert result.ok is False
        assert result.error


# ─── fetch_text — malformed URLs ───────────────────────────────────────────────


class TestMalformedUrls:
    """Invalid URLs that don't match any scheme pattern return ok=False."""

    def test_fetch_text_malformed_url_returns_error(self):
        result = fetch_text("not a url")
        assert result.ok is False
        assert result.error

    def test_fetch_text_http_scheme_works(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(text="<p>ok</p>"),
        )
        result = fetch_text("http://example.com")
        assert result.ok is True

    def test_fetch_text_https_scheme_works(self, monkeypatch):
        import bellbird.core.web_fetch as wf
        monkeypatch.setattr(
            wf.requests, "get",
            lambda url, **kw: MockResponse(text="<p>ok</p>"),
        )
        result = fetch_text("HTTPS://example.com")
        assert result.ok is True


# ─── AST guard: no import wx at module level ───────────────────────────────────


class TestAstNoWxImport:
    """core/web_fetch.py must not import wx at module scope."""

    def test_no_wx_import_in_source(self):
        source_path = __import__(
            "bellbird.core.web_fetch", fromlist=[""]
        ).__file__
        with open(source_path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "wx" or alias.name.startswith("wx."):
                        pytest.fail(
                            f"Found import of wx at module level: "
                            f"{ast.dump(node)}"
                        )
