"""
Deep coverage for plugins/download_proxy.py — targets download_via_nova2dl,
DownloadHandler HTTP flow, proxy_to_qbittorrent, and run_server.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

# The suite runs under --import-mode=importlib (pyproject.toml), so a
# sibling helper module is not implicitly importable — put this directory
# on sys.path first, exactly as the plugins/ dir is handled inside the
# harness itself.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _download_proxy_harness import (  # noqa: E402
    _make_handler,
    download_via_nova2dl,
    run_server,
)


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

    def test_proxy_html_response_passed_through_unmodified(self):
        """HTML is relayed byte-for-byte — the themed-WebUI overlay was
        removed 2026-09-01 (see tests/integration/
        test_vanilla_webui_unmodified.py)."""
        handler = _make_handler(path="/")
        upstream = b"<html><head><script>window.qBittorrent={};</script></head></html>"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_response.read = MagicMock(return_value=upstream)
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            handler.proxy_to_qbittorrent(None)
            handler.send_response.assert_called_with(200)
            sent = handler.wfile.getvalue()
            assert upstream in sent
            assert b"__qbit_theme__" not in sent

    def test_proxy_http_error(self):
        """Lines 941-946: HTTPError handled."""
        import urllib.error

        handler = _make_handler(path="/api/v2/app/version")
        err = urllib.error.HTTPError(
            url="/api/v2/app/version", code=404, msg="Not Found", hdrs=None, fp=None
        )
        try:
            with patch("urllib.request.urlopen", side_effect=err):
                handler.proxy_to_qbittorrent(None)
                handler.send_error.assert_called_with(404, "Not Found")
        finally:
            err.close()

    def test_proxy_generic_error(self):
        """Lines 947-952: generic error sends 502."""
        handler = _make_handler(path="/api/v2/app/version")
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError):
            handler.proxy_to_qbittorrent(None)
            handler.send_error.assert_called_with(502, "Bad Gateway")

    def test_proxy_csp_forwarded_verbatim(self):
        """qBittorrent's CSP is forwarded untouched (no connect-src
        relaxation for a theme bridge that no longer exists)."""
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
            header_calls = [c for c in handler.send_header.call_args_list]
            csp_calls = [c for c in header_calls if c[0][0].lower() == "content-security-policy"]
            assert len(csp_calls) == 1
            assert csp_calls[0][0][1] == "default-src 'self'"

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

    def test_proxy_content_encoding_preserved_for_html(self):
        """Content-Encoding is forwarded untouched — nothing decodes the
        body any more, so gzip bodies relay exactly as compressed."""
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
            assert "content-encoding" in header_names


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
