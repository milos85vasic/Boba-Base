"""Extra anti-bluff guard tests for plugins/download_proxy.py.

Targets the narrow defensive branches left uncovered by
``test_download_proxy_coverage.py`` + ``test_download_proxy_deep.py``:

* binary-passthrough except branch (undecodable torrents/add body),
* encoded HTML relayed byte-for-byte with its Content-Encoding intact,
* proxy error paths where ``send_error`` itself raises (swallowed),
* intercept-success with ``os.unlink`` raising ``OSError`` (non-fatal),
  (the themed-WebUI overlay was removed 2026-09-01 — see
  ``tests/integration/test_vanilla_webui_unmodified.py``).

Each test asserts a USER-OBSERVABLE outcome (the bytes that reach
qBittorrent, the bytes the browser receives, the absence of an escaping
exception) and would FAIL against a no-op stub of the behaviour under
test. Per CLAUDE.md §11.4 / CONST-XII.

NOTE: this file is deliberately separate from the existing
download_proxy test files to avoid edit collisions; the shared
``download_proxy`` bootstrap and the ``_make_handler`` / ``_mock_response``
helpers live in ``_download_proxy_harness.py`` (ONE definition, imported
by every download_proxy test file — §11.4.251 forbids the byte-identical
fork these helpers used to be), so the module under test is shared
(single import, coverage attributable).
"""

from __future__ import annotations

import os
import sys
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

# The suite runs under --import-mode=importlib (pyproject.toml), so a
# sibling helper module is not implicitly importable — put this directory
# on sys.path first, exactly as the plugins/ dir is handled inside the
# harness itself.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _download_proxy_harness import (  # noqa: E402
    _make_handler,
    _mock_response,
    sent_headers,
)


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
# 2. An HTML body carrying a Content-Encoding the proxy cannot read (e.g.
#    `br`) is relayed BYTE-FOR-BYTE with its Content-Encoding header
#    intact. The themed-WebUI overlay that used to decode + mutate this
#    body was removed 2026-09-01 by operator decision; it rewrote the
#    `qBittorrent` token inside inline <script> blocks and killed the
#    WebUI's JavaScript. This is the unit-level half of
#    tests/integration/test_vanilla_webui_unmodified.py.
# --------------------------------------------------------------------------


class TestEncodedHtmlPassedThroughUntouched:
    def test_br_encoded_html_relayed_verbatim(self):
        raw_html = b"<html><head><title>qBittorrent</title></head><body></body></html>"
        handler = _make_handler(path="/")
        resp = _mock_response(
            200,
            {"Content-Type": "text/html; charset=utf-8", "Content-Encoding": "br"},
            raw_html,
        )
        with patch("urllib.request.urlopen", return_value=resp):
            handler.proxy_to_qbittorrent(None)

        # The body is deliberately readable HTML carrying a `br` label the
        # proxy never validates: proxy_to_qbittorrent NEVER reads or decodes
        # the body, so the label is exactly what proves the encoding header
        # survives, and byte-equality is what proves the body is untouched.
        # Had the proxy decoded/re-encoded (or injected a rebrand), the
        # bytes below would differ.
        #
        # Two DISTINCT recording surfaces — see _make_handler's docstring:
        #   * handler.wfile  -> the response BODY only
        #   * send_header    -> the response HEADERS (a Mock; headers never
        #                       reach wfile, so asserting on wfile for a
        #                       header can never pass).

        # USER-OBSERVABLE 1: the browser receives qBittorrent's own bytes,
        # byte-for-byte — no injection, no rebrand, no re-encode.
        body = handler.wfile.getvalue()
        assert body == raw_html
        assert b"<title>qBittorrent" in body
        assert b"/__qbit_theme__/" not in body
        assert "Боба".encode() not in body

        # USER-OBSERVABLE 2: the browser receives qBittorrent's own
        # Content-Encoding, relayed once and verbatim — so a genuinely
        # compressed body is still decodable client-side.
        headers = sent_headers(handler)
        ce = [v for name, v in headers if name.lower() == "content-encoding"]
        assert ce == ["br"], f"Content-Encoding not relayed verbatim: {headers}"

        # USER-OBSERVABLE 3: Content-Length describes the ENCODED bytes the
        # proxy actually wrote. A proxy that decompressed would have to send
        # a different length here; this pins that it did not.
        cl = [v for name, v in headers if name.lower() == "content-length"]
        assert cl == [str(len(raw_html))], f"Content-Length rewritten wrongly: {headers}"


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
        try:
            with patch("urllib.request.urlopen", side_effect=err):
                # USER-OBSERVABLE: no exception escapes — the server thread
                # survives a dead-client send_error.
                handler.proxy_to_qbittorrent(None)
            handler.send_error.assert_called_once_with(404, "Not Found")
        finally:
            err.close()

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
