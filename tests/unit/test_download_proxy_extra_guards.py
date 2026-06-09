"""Extra anti-bluff guard tests for plugins/download_proxy.py.

Targets the narrow defensive branches left uncovered by
``test_download_proxy_coverage.py`` + ``test_download_proxy_deep.py``:

* binary-passthrough except branch (undecodable torrents/add body),
* undecodable Content-Encoding HTML still theme-injected + rebranded,
* proxy error paths where ``send_error`` itself raises (swallowed),
* intercept-success with ``os.unlink`` raising ``OSError`` (non-fatal),
* malformed path makes the two short-circuit handlers return False,
* ``rewrite_csp`` idempotent on the default-src fallback path.

Each test asserts a USER-OBSERVABLE outcome (the bytes that reach
qBittorrent, the bytes the browser receives, the absence of an escaping
exception) and would FAIL against a no-op stub of the behaviour under
test. Per CLAUDE.md §11.4 / CONST-XII.

NOTE: this file is deliberately separate from the existing
download_proxy test files to avoid edit collisions; it reuses the same
``download_proxy`` module name + ``_make_handler`` pattern so the module
under test is shared (single import, coverage attributable).
"""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DP_PATH = os.path.join(_REPO_ROOT, "plugins", "download_proxy.py")

sys.path.insert(0, os.path.join(_REPO_ROOT, "plugins"))

if "download_proxy" not in sys.modules:
    _dp_spec = importlib.util.spec_from_file_location("download_proxy", _DP_PATH)
    _dp_mod = importlib.util.module_from_spec(_dp_spec)
    sys.modules["download_proxy"] = _dp_mod
    _dp_spec.loader.exec_module(_dp_mod)
else:
    _dp_mod = sys.modules["download_proxy"]

DownloadHandler = _dp_mod.DownloadHandler
rewrite_csp = _dp_mod.rewrite_csp
MERGE_SERVICE_ORIGIN = _dp_mod.MERGE_SERVICE_ORIGIN


def _make_handler(path="/test", method="GET", body=None, headers=None):
    """Create a DownloadHandler with mocked socket streams.

    Mirrors the helper in test_download_proxy_deep.py.
    """
    handler = DownloadHandler.__new__(DownloadHandler)
    handler.path = path
    handler.command = method
    handler.headers = headers or {}
    handler.wfile = io.BytesIO()
    handler.rfile = io.BytesIO(body or b"")
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.client_address = ("127.0.0.1", 12345)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    handler.address_string = MagicMock(return_value="127.0.0.1")
    return handler


def _mock_response(status, headers, body):
    resp = MagicMock()
    resp.status = status
    resp.headers = headers
    resp.read = MagicMock(return_value=body)
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# --------------------------------------------------------------------------
# 1. Undecodable torrents/add body passes through to qBittorrent VERBATIM.
#    Source lines 842-847 (the `except (UnicodeDecodeError, ValueError)`).
#    `b"urls=\xff\xfe\xfa"` is NOT valid UTF-8 (0xff is never a UTF-8 lead
#    byte), so body.decode("utf-8") raises and the raw bytes pass through.
# --------------------------------------------------------------------------


class TestUndecodableBodyPassthrough:
    def test_invalid_utf8_body_proxied_verbatim(self):
        raw = b"urls=\xff\xfe\xfa"
        # Sanity: this body really is undecodable, so we exercise the
        # except branch (not the happy path).
        with pytest.raises(UnicodeDecodeError):
            raw.decode("utf-8")

        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/add",
            body=raw,
            headers={"Content-Length": str(len(raw))},
        )
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            handler.handle_request(raw)
            # USER-OBSERVABLE: the EXACT original bytes reach qBittorrent —
            # no decode, no urlencode round-trip, no truncation.
            mock_proxy.assert_called_once_with(raw)


# --------------------------------------------------------------------------
# 2. HTML body with an undecodable Content-Encoding (e.g. `br`) still gets
#    theme-injected + rebranded on the RAW bytes.
#    Source lines 918-920 (the `else` branch when _maybe_decode_body is
#    False but content is HTML). The proxy injects/rebrands raw bytes.
# --------------------------------------------------------------------------


class TestUndecodableContentEncodingStillThemed:
    def test_br_encoded_html_is_injected_and_rebranded(self):
        # Plain-but-mislabelled HTML: Content-Encoding 'br' is unknown to
        # _maybe_decode_body so it returns (body, False). The body itself
        # is readable HTML, so inject/rebrand operate on it directly.
        raw_html = b"<html><head><title>qBittorrent</title></head><body></body></html>"
        handler = _make_handler(path="/")
        resp = _mock_response(
            200,
            {"Content-Type": "text/html; charset=utf-8", "Content-Encoding": "br"},
            raw_html,
        )
        with patch("urllib.request.urlopen", return_value=resp):
            handler.proxy_to_qbittorrent(None)

        sent = handler.wfile.getvalue()
        # USER-OBSERVABLE: the bytes the browser receives carry the theme
        # css path (injection) AND the Боба rebrand (qBittorrent -> Боба).
        assert b"/__qbit_theme__/skin.css" in sent
        assert "Боба".encode() in sent
        assert b"<title>qBittorrent" not in sent


# --------------------------------------------------------------------------
# 3. Proxy error paths where send_error ITSELF raises are swallowed.
#    Source lines 943-946 (HTTPError) and 949-952 (generic) wrap the
#    send_error call in `try: ... except Exception: pass`.
# --------------------------------------------------------------------------


class TestSendErrorRaisingIsSwallowed:
    def test_httperror_send_error_raises_no_escape(self):
        handler = _make_handler(path="/api/v2/app/version")
        # send_error raises (e.g. client already disconnected) — must NOT
        # propagate out of proxy_to_qbittorrent.
        handler.send_error = MagicMock(side_effect=BrokenPipeError("client gone"))
        err = urllib.error.HTTPError(
            url="/api/v2/app/version", code=404, msg="Not Found", hdrs=None, fp=None
        )
        with patch("urllib.request.urlopen", side_effect=err):
            # USER-OBSERVABLE: no exception escapes — the server thread
            # survives a dead-client send_error.
            handler.proxy_to_qbittorrent(None)
        handler.send_error.assert_called_once_with(404, "Not Found")

    def test_generic_error_send_error_raises_no_escape(self):
        handler = _make_handler(path="/api/v2/app/version")
        handler.send_error = MagicMock(side_effect=BrokenPipeError("client gone"))
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError):
            handler.proxy_to_qbittorrent(None)
        handler.send_error.assert_called_once_with(502, "Bad Gateway")


# --------------------------------------------------------------------------
# 4. Intercept-success with os.unlink raising OSError is non-fatal.
#    Source lines 866-868 (the `try: os.unlink(...) except OSError: pass`).
#    The proxy must still forward the file:// rewritten body and return
#    cleanly even when the temp-file cleanup fails.
# --------------------------------------------------------------------------


class TestUnlinkOSErrorNonFatal:
    def test_unlink_failure_does_not_break_intercept(self):
        body = b"urls=https://rutracker.org/forum/dl.php?t=123"
        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/add",
            body=body,
            headers={"Content-Length": str(len(body))},
        )
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            with patch("download_proxy.download_via_nova2dl", return_value="/tmp/x.torrent"):
                with patch("os.unlink", side_effect=OSError("permission denied")):
                    # USER-OBSERVABLE: returns cleanly (no exception) AND the
                    # file:// rewritten body reached qBittorrent.
                    handler.handle_request(body)

        mock_proxy.assert_called_once()
        forwarded = mock_proxy.call_args[0][0].decode("utf-8")
        assert "file%3A%2F%2F%2Ftmp%2Fx.torrent" in forwarded or "file:///tmp/x.torrent" in forwarded
        # The proxy was driven, not the 502 error path.
        handler.send_error.assert_not_called()


# --------------------------------------------------------------------------
# 5. Malformed path makes _serve_boba_logo / _serve_theme_bridge return
#    False (request falls through) rather than raising.
#    Source lines 790-791 + 809-810 (the `except Exception: return False`).
#    urlparse on a control-char path can raise; the guards swallow it.
# --------------------------------------------------------------------------


class TestMalformedPathFallsThrough:
    def test_both_short_circuits_return_false_on_urlparse_error(self):
        handler = _make_handler(path="/whatever")
        # Force urlparse to raise to drive the except branch in both
        # short-circuit helpers (covers a hostile/malformed self.path).
        with patch("urllib.parse.urlparse", side_effect=ValueError("bad path")):
            # USER-OBSERVABLE: neither helper raises; both decline (False)
            # so do_GET falls through to proxy_to_qbittorrent.
            assert handler._serve_boba_logo() is False
            assert handler._serve_theme_bridge() is False


# --------------------------------------------------------------------------
# 6. rewrite_csp idempotent when origin already in the default-src
#    fallback. Source branch 594->596: when there is no connect-src and
#    default-src ALREADY contains the merge origin, we must NOT append it
#    a second time. The synthesised connect-src carries the origin once.
# --------------------------------------------------------------------------


class TestRewriteCspDefaultSrcIdempotent:
    def test_origin_in_default_src_not_double_appended(self):
        origin = MERGE_SERVICE_ORIGIN
        # No connect-src; default-src ALREADY whitelists the merge origin.
        # Branch 594->596: the fallback copies default-src verbatim into a
        # new connect-src WITHOUT appending the origin a second time.
        csp = f"default-src 'self' {origin}; script-src 'self';"
        out = rewrite_csp(csp)
        # USER-OBSERVABLE: a connect-src directive exists, and within that
        # synthesised connect-src the origin appears exactly once (the
        # fallback did not re-append it). It legitimately also appears in
        # the preserved default-src, so the total is 2 — but the connect-src
        # directive itself carries it once, never twice.
        assert "connect-src" in out
        connect_directive = next(
            part.strip() for part in out.split(";") if part.strip().startswith("connect-src")
        )
        assert connect_directive.count(origin) == 1
