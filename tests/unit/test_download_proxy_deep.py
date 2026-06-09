"""
Deep coverage for plugins/download_proxy.py — targets download_via_nova2dl,
DownloadHandler HTTP flow, proxy_to_qbittorrent, and run_server.
"""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler
from unittest.mock import MagicMock, patch, mock_open

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

download_via_nova2dl = _dp_mod.download_via_nova2dl
DownloadHandler = _dp_mod.DownloadHandler
identify_plugin = _dp_mod.identify_plugin
run_server = _dp_mod.run_server
rewrite_csp = _dp_mod.rewrite_csp
inject_theme_assets = _dp_mod.inject_theme_assets
serve_theme_asset = _dp_mod.serve_theme_asset
rebrand_html = _dp_mod.rebrand_html
_maybe_decode_body = _dp_mod._maybe_decode_body
_is_boba_logo_request = _dp_mod.is_boba_logo_request
serve_boba_logo = _dp_mod.serve_boba_logo
_load_boba_logo = _dp_mod._load_boba_logo
_BOBA_LOGO_PATH_ON_DISK = _dp_mod._BOBA_LOGO_PATH_ON_DISK


# --------------------------------------------------------------------------
# download_via_nova2dl — lines 53-86
# --------------------------------------------------------------------------


class TestDownloadViaNova2dl:
    def test_success(self):
        """Lines 55-80: successful download."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/tmp/torrent.torrent description\n"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            with patch("os.path.exists", return_value=True):
                result = download_via_nova2dl("rutracker", "http://example.com/torrent")
                assert result == "/tmp/torrent.torrent"

    def test_non_zero_returncode(self):
        """Lines 60-62: non-zero return code returns None."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"
        with patch("subprocess.run", return_value=mock_result):
            result = download_via_nova2dl("rutracker", "http://example.com/torrent")
            assert result is None

    def test_empty_output(self):
        """Lines 65-67: empty output returns None."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            result = download_via_nova2dl("rutracker", "http://example.com/torrent")
            assert result is None

    def test_unexpected_output_format(self):
        """Lines 70-72: unexpected output format returns None."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "single_part_no_space"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            result = download_via_nova2dl("rutracker", "http://example.com/torrent")
            assert result is None

    def test_file_not_found(self):
        """Lines 75-77: torrent file not found returns None."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/tmp/missing.torrent desc\n"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            with patch("os.path.exists", return_value=False):
                result = download_via_nova2dl("rutracker", "http://example.com/torrent")
                assert result is None

    def test_timeout(self):
        """Lines 81-83: subprocess timeout returns None."""
        import subprocess as _subprocess

        with patch("subprocess.run", side_effect=_subprocess.TimeoutExpired("cmd", 60)):
            result = download_via_nova2dl("rutracker", "http://example.com/torrent")
            assert result is None

    def test_generic_exception(self):
        """Lines 84-86: generic exception returns None."""
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            result = download_via_nova2dl("rutracker", "http://example.com/torrent")
            assert result is None


# --------------------------------------------------------------------------
# _load_boba_logo — lines 717-725
# --------------------------------------------------------------------------


class TestLoadBobaLogo:
    def test_load_success(self):
        """Lines 719-722: logo loaded from disk."""
        _dp_mod._BOBA_LOGO_BYTES = None
        with patch("builtins.open", mock_open(read_data=b"fake-logo-bytes")):
            result = _load_boba_logo()
            assert result == b"fake-logo-bytes"

    def test_load_file_not_found(self):
        """Lines 723-724: file not found returns empty bytes."""
        _dp_mod._BOBA_LOGO_BYTES = None
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = _load_boba_logo()
            assert result == b""

    def test_load_cached(self):
        """Lines 719: cached value returned."""
        _dp_mod._BOBA_LOGO_BYTES = b"cached-logo"
        result = _load_boba_logo()
        assert result == b"cached-logo"
        _dp_mod._BOBA_LOGO_BYTES = None


# --------------------------------------------------------------------------
# serve_boba_logo — lines 732-752
# --------------------------------------------------------------------------


class TestServeBobaLogo:
    def test_no_logo_returns_404(self):
        """Lines 734-743: no logo returns 404."""
        _dp_mod._BOBA_LOGO_BYTES = b""
        status, headers, payload = serve_boba_logo()
        assert status == 404
        assert payload == b"Not Found"

    def test_with_logo_returns_200(self):
        """Lines 744-752: logo present returns 200."""
        _dp_mod._BOBA_LOGO_BYTES = b"fake-jpeg"
        status, headers, payload = serve_boba_logo()
        assert status == 200
        assert headers["Content-Type"] == "image/jpeg"
        assert payload == b"fake-jpeg"
        _dp_mod._BOBA_LOGO_BYTES = None


# --------------------------------------------------------------------------
# DownloadHandler — _serve_boba_logo (lines 786-803)
# --------------------------------------------------------------------------


def _make_handler(path="/test", method="GET", body=None, headers=None):
    """Create a DownloadHandler with mocked socket streams."""
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


class TestHandlerServeBobaLogo:
    def test_serves_logo(self):
        """Lines 786-803: _serve_boba_logo returns True for logo path."""
        _dp_mod._BOBA_LOGO_BYTES = b"fake-jpeg"
        handler = _make_handler(path="/images/boba-logo.jpeg")
        result = handler._serve_boba_logo()
        assert result is True
        handler.send_response.assert_called_with(200)
        _dp_mod._BOBA_LOGO_BYTES = None

    def test_non_logo_path(self):
        """Lines 792-793: non-logo path returns False."""
        handler = _make_handler(path="/api/v2/torrents/add")
        result = handler._serve_boba_logo()
        assert result is False

    def test_broken_pipe(self):
        """Lines 800-802: BrokenPipeError on wfile.write is caught."""
        _dp_mod._BOBA_LOGO_BYTES = b"fake-jpeg"
        handler = _make_handler(path="/images/boba-logo.jpeg")
        handler.wfile.write = MagicMock(side_effect=BrokenPipeError)
        result = handler._serve_boba_logo()
        assert result is True
        _dp_mod._BOBA_LOGO_BYTES = None


class TestHandlerServeThemeBridge:
    def test_serves_css(self):
        """Lines 805-822: _serve_theme_bridge serves CSS."""
        handler = _make_handler(path="/__qbit_theme__/skin.css")
        result = handler._serve_theme_bridge()
        assert result is True
        handler.send_response.assert_called_with(200)

    def test_serves_js(self):
        """Lines 805-822: _serve_theme_bridge serves JS."""
        handler = _make_handler(path="/__qbit_theme__/bootstrap.js")
        result = handler._serve_theme_bridge()
        assert result is True

    def test_non_theme_path(self):
        """Lines 811-812: non-theme path returns False."""
        handler = _make_handler(path="/api/v2/torrents/add")
        result = handler._serve_theme_bridge()
        assert result is False

    def test_broken_pipe_on_theme(self):
        """Lines 818-821: BrokenPipeError on theme asset write is caught."""
        handler = _make_handler(path="/__qbit_theme__/skin.css")
        handler.wfile.write = MagicMock(side_effect=BrokenPipeError)
        result = handler._serve_theme_bridge()
        assert result is True


class TestHandlerIsMultipart:
    def test_multipart(self):
        """Lines 824-826: multipart/form-data detected."""
        handler = _make_handler(headers={"Content-Type": "multipart/form-data; boundary=abc"})
        assert handler._is_multipart_file_upload() is True

    def test_not_multipart(self):
        """Lines 824-826: non-multipart content type."""
        handler = _make_handler(headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert handler._is_multipart_file_upload() is False


class TestHandlerIsTorrentField:
    def test_always_false(self):
        """Lines 828-830: always returns False."""
        handler = _make_handler()
        assert handler._is_torrent_file_field(b"body") is False


class TestHandlerDoGet:
    def test_do_get_serves_logo(self):
        """Lines 774-776: do_GET serves logo."""
        _dp_mod._BOBA_LOGO_BYTES = b"fake-jpeg"
        handler = _make_handler(path="/images/boba-logo.jpeg")
        handler.do_GET()
        handler.send_response.assert_called_with(200)
        _dp_mod._BOBA_LOGO_BYTES = None

    def test_do_get_serves_theme(self):
        """Lines 777-778: do_GET serves theme bridge."""
        handler = _make_handler(path="/__qbit_theme__/skin.css")
        handler.do_GET()
        handler.send_response.assert_called_with(200)

    def test_do_get_proxies_other(self):
        """Lines 779: do_GET proxies other requests."""
        handler = _make_handler(path="/api/v2/app/version")
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            handler.do_GET()
            mock_proxy.assert_called_once_with(None)


class TestHandlerDoPost:
    def test_do_post_with_body(self):
        """Lines 781-784: do_POST reads body and calls handle_request."""
        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/add",
            body=b"urls=magnet:?xt=urn:btih:abc",
            headers={"Content-Length": "30"},
        )
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            handler.do_POST()
            mock_proxy.assert_called_once()

    def test_do_post_no_body(self):
        """Lines 782-783: do_POST with no content-length."""
        handler = _make_handler(method="POST", path="/api/v2/torrents/add")
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            handler.do_POST()
            mock_proxy.assert_called_once_with(None)


class TestHandlerHandleRequest:
    def test_multipart_passthrough(self):
        """Lines 837-840: multipart upload passed through."""
        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/add",
            body=b"multipart-data",
            headers={"Content-Type": "multipart/form-data; boundary=abc", "Content-Length": "15"},
        )
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            handler.handle_request(b"multipart-data")
            mock_proxy.assert_called_once_with(b"multipart-data")

    def test_binary_body_passthrough(self):
        """Lines 842-847: binary body passed through."""
        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/add",
            body=b"\x00\x01\x02\x03",
            headers={"Content-Length": "4"},
        )
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            handler.handle_request(b"\x00\x01\x02\x03")
            mock_proxy.assert_called_once_with(b"\x00\x01\x02\x03")

    def test_plugin_intercept_success(self):
        """Lines 854-869: plugin URL intercepted and torrent downloaded."""
        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/add",
            body=b"urls=https://rutracker.org/forum/dl.php?t=123",
            headers={"Content-Length": "45"},
        )
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            with patch("download_proxy.download_via_nova2dl", return_value="/tmp/file.torrent"):
                with patch("os.unlink"):
                    handler.handle_request(b"urls=https://rutracker.org/forum/dl.php?t=123")
                    mock_proxy.assert_called_once()
                    call_args = mock_proxy.call_args[0][0]
                    assert "file%3A%2F%2F" in call_args.decode() or "file://" in call_args.decode()

    def test_plugin_intercept_download_fails(self):
        """Lines 870-873: download failure returns 502."""
        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/add",
            body=b"urls=https://rutracker.org/forum/dl.php?t=123",
            headers={"Content-Length": "45"},
        )
        with patch("download_proxy.download_via_nova2dl", return_value=None):
            handler.handle_request(b"urls=https://rutracker.org/forum/dl.php?t=123")
            handler.send_error.assert_called_with(502, "Failed to download torrent")

    def test_non_plugin_url_passthrough(self):
        """Lines 875: non-plugin URL passed through."""
        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/add",
            body=b"urls=https://example.com/file.torrent",
            headers={"Content-Length": "40"},
        )
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            handler.handle_request(b"urls=https://example.com/file.torrent")
            mock_proxy.assert_called_once()

    def test_non_add_path_passthrough(self):
        """Lines 875: non-/add path passed through."""
        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/pause",
            body=b"hashes=abc",
            headers={"Content-Length": "10"},
        )
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            handler.handle_request(b"hashes=abc")
            mock_proxy.assert_called_once()

    def test_get_request_passthrough(self):
        """Lines 875: GET request passed through."""
        handler = _make_handler(method="GET", path="/api/v2/app/version")
        with patch.object(handler, "proxy_to_qbittorrent") as mock_proxy:
            handler.handle_request(None)
            mock_proxy.assert_called_once_with(None)

    def test_exception_sends_500(self):
        """Lines 877-882: exception sends 500."""
        handler = _make_handler(
            method="POST",
            path="/api/v2/torrents/add",
            body=b"urls=test",
            headers={"Content-Length": "10"},
        )
        with patch.object(handler, "proxy_to_qbittorrent", side_effect=RuntimeError("fail")):
            handler.handle_request(b"urls=test")
            handler.send_error.assert_called_with(500, "fail")


class TestHandlerLogMessage:
    def test_log_api_path(self):
        """Lines 770-772: API path logged."""
        handler = _make_handler(path="/api/v2/app/version")
        handler.log_message("test %s", "message")

    def test_log_non_api_path(self):
        """Lines 770-771: non-API path not logged."""
        handler = _make_handler(path="/images/logo.png")
        handler.log_message("test %s", "message")


class TestHandlerProxyToQbittorrent:
    def test_proxy_rewrites_referer(self):
        """Lines 892-895: referer and origin rewritten."""
        handler = _make_handler(
            path="/api/v2/app/version",
            headers={"Referer": "http://old-host:8080", "Origin": "http://old-host:8080"},
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.read = MagicMock(return_value=b"OK")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            handler.proxy_to_qbittorrent(None)
            handler.send_response.assert_called_with(200)

    def test_proxy_html_response_injects_theme(self):
        """Lines 908-920: HTML response gets theme injection."""
        handler = _make_handler(path="/")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_response.read = MagicMock(return_value=b"<html><head></head><body></body></html>")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            handler.proxy_to_qbittorrent(None)
            handler.send_response.assert_called_with(200)

    def test_proxy_http_error(self):
        """Lines 941-946: HTTPError handled."""
        import urllib.error

        handler = _make_handler(path="/api/v2/app/version")
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="/api/v2/app/version", code=404, msg="Not Found", hdrs=None, fp=None
        )):
            handler.proxy_to_qbittorrent(None)
            handler.send_error.assert_called_with(404, "Not Found")

    def test_proxy_generic_error(self):
        """Lines 947-952: generic error sends 502."""
        handler = _make_handler(path="/api/v2/app/version")
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError):
            handler.proxy_to_qbittorrent(None)
            handler.send_error.assert_called_with(502, "Bad Gateway")

    def test_proxy_csp_rewrite(self):
        """Lines 933-934: CSP header rewritten for HTML responses."""
        handler = _make_handler(path="/")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {
            "Content-Type": "text/html",
            "Content-Security-Policy": "default-src 'self'",
        }
        mock_response.read = MagicMock(return_value=b"<html><head></head><body></body></html>")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            handler.proxy_to_qbittorrent(None)
            # Verify send_header was called with a CSP header
            header_calls = [c for c in handler.send_header.call_args_list]
            csp_calls = [c for c in header_calls if c[0][0].lower() == "content-security-policy"]
            assert len(csp_calls) > 0

    def test_proxy_skips_transfer_encoding(self):
        """Lines 925-926: transfer-encoding skipped, content-length rewritten."""
        handler = _make_handler(path="/")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {
            "Content-Type": "text/plain",
            "Transfer-Encoding": "chunked",
            "Content-Length": "100",
        }
        mock_response.read = MagicMock(return_value=b"OK")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            handler.proxy_to_qbittorrent(None)
            header_names = [c[0][0].lower() for c in handler.send_header.call_args_list]
            assert "transfer-encoding" not in header_names

    def test_proxy_content_encoding_stripped_for_html(self):
        """Lines 928-929: content-encoding stripped when body decoded."""
        handler = _make_handler(path="/")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {
            "Content-Type": "text/html",
            "Content-Encoding": "gzip",
        }
        import gzip as _gzip
        mock_response.read = MagicMock(return_value=_gzip.compress(b"<html><head></head><body></body></html>"))
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            handler.proxy_to_qbittorrent(None)
            header_names = [c[0][0].lower() for c in handler.send_header.call_args_list]
            assert "content-encoding" not in header_names


# --------------------------------------------------------------------------
# run_server — lines 955-971
# --------------------------------------------------------------------------


class TestRunServer:
    def test_run_server_starts(self):
        """Lines 955-971: run_server creates ThreadingHTTPServer."""
        mock_server = MagicMock()
        with patch("download_proxy.ThreadingHTTPServer", return_value=mock_server):
            with patch.object(mock_server, "serve_forever", side_effect=KeyboardInterrupt):
                run_server()
                mock_server.serve_forever.assert_called_once()
                mock_server.shutdown.assert_called_once()


# --------------------------------------------------------------------------
# _maybe_decode_body — additional edge cases
# --------------------------------------------------------------------------


class TestMaybeDecodeBodyEdge:
    def test_gzip_roundtrip(self):
        """Lines 617-618: gzip decompress."""
        import gzip as _gzip
        original = b"<html>test content</html>"
        compressed = _gzip.compress(original)
        result, flag = _maybe_decode_body(compressed, "gzip")
        assert result == original
        assert flag is True

    def test_deflate_roundtrip(self):
        """Lines 619-623: deflate decompress."""
        import zlib as _zlib
        original = b"<html>test content</html>"
        compressed = _zlib.compress(original)
        result, flag = _maybe_decode_body(compressed, "deflate")
        assert result == original
        assert flag is True

    def test_raw_deflate(self):
        """Lines 622-623: raw deflate (no zlib header)."""
        import zlib as _zlib
        original = b"<html>test content</html>"
        compressor = _zlib.compressobj(level=9, wbits=-_zlib.MAX_WBITS)
        compressed = compressor.compress(original) + compressor.flush()
        result, flag = _maybe_decode_body(compressed, "deflate")
        assert result == original
        assert flag is True

    def test_unknown_encoding(self):
        """Lines 626: unknown encoding returns False."""
        original = b"<html>test</html>"
        result, flag = _maybe_decode_body(original, "br")
        assert result == original
        assert flag is False
