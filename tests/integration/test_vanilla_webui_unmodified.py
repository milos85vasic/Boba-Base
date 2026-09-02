"""Vanilla-WebUI pass-through guard.

Operator decision (2026-09-01): the themed qBittorrent WebUI overlay is
REMOVED and the stock vanilla qBittorrent WebUI is served instead. The
overlay implemented zero qBittorrent features (branding + palette only)
and actively BROKE vanilla's JavaScript: the rebrand rule
``(re.compile(r"qBittorrent", re.IGNORECASE), "Боба")`` rewrote the token
*inside inline ``<script>`` blocks* while external ``.js`` files were left
untouched, so inline code referenced ``window.Боба.*`` that the external
scripts never define -> ReferenceError -> the WebUI JS never initialises.

This is the permanent regression guard for that defect (§11.4.135). It
drives the REAL download-proxy handler over REAL HTTP against a fake
upstream and asserts the proxied bytes are IDENTICAL to what qBittorrent
sent — in particular that ``qBittorrent`` inside a ``<script>`` block is
NOT rewritten.

RED polarity (§11.4.115): against the pre-removal code this guard FAILS
(the body is rewritten). After the overlay removal it PASSES.

Runnable BOTH ways so the evidence does not depend on a pytest install
(§11.4.201 — an unmeasurable gate is itself a bluff):

    python3 -m pytest tests/integration/test_vanilla_webui_unmodified.py
    python3 tests/integration/test_vanilla_webui_unmodified.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROXY_SRC = REPO / "plugins" / "download_proxy.py"

# The exact shape of the defect: an inline <script> that both DEFINES and
# USES the `qBittorrent` global, alongside a </head> the injector targets.
VANILLA_HTML = (
    b"<!DOCTYPE html>\n"
    b"<html><head>\n"
    b"<title>qBittorrent Web UI</title>\n"
    b'<meta name="description" content="qBittorrent WebUI">\n'
    b'<script src="scripts/client.js"></script>\n'
    b"<script>\n"
    b"  window.qBittorrent = window.qBittorrent || {};\n"
    b"  window.qBittorrent.Client = { name: 'qBittorrent' };\n"
    b"  document.addEventListener('DOMContentLoaded', function () {\n"
    b"    window.qBittorrent.Client.init();\n"
    b"  });\n"
    b"</script>\n"
    b"</head>\n"
    b'<body><img src="images/qbittorrent-tray.svg" alt="qBittorrent logo"></body>\n'
    b"</html>\n"
)

UPSTREAM_CSP = "default-src 'self'; script-src 'self' 'unsafe-inline';"


def _load_download_proxy():
    spec = importlib.util.spec_from_file_location("_dp_vanilla_guard", PROXY_SRC)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeQbitHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=UTF-8")
        self.send_header("Content-Length", str(len(VANILLA_HTML)))
        self.send_header("Content-Security-Policy", UPSTREAM_CSP)
        self.end_headers()
        self.wfile.write(VANILLA_HTML)


def _serve(handler_cls):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, thread


def fetch_through_proxy() -> tuple[bytes, dict[str, str]]:
    """GET / through the REAL download-proxy handler over REAL HTTP."""
    upstream, upstream_thread = _serve(_FakeQbitHandler)
    dp = _load_download_proxy()
    dp.QBITTORRENT_HOST = "127.0.0.1"
    dp.QBITTORRENT_PORT = str(upstream.server_address[1])
    proxy, proxy_thread = _serve(dp.DownloadHandler)
    try:
        url = f"http://127.0.0.1:{proxy.server_address[1]}/"
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.read(), dict(resp.headers)
    finally:
        proxy.shutdown()
        proxy.server_close()
        proxy_thread.join(timeout=5)
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)
        sys.modules.pop("_dp_vanilla_guard", None)


# --------------------------------------------------------------------------
# Assertions — pure functions so both pytest and the standalone runner
# execute the IDENTICAL checks (§11.4.251 — one implementation, not a fork).
# --------------------------------------------------------------------------


def check_script_block_qbittorrent_token_not_rewritten(body, headers):
    """The load-bearing assertion: the WebUI's own JS namespace survives."""
    assert b"window.qBittorrent = window.qBittorrent || {};" in body, (
        "the proxy rewrote the `qBittorrent` JS global inside a <script> "
        "block — this is the ReferenceError that breaks the vanilla WebUI"
    )
    assert b"window.qBittorrent.Client.init();" in body
    assert body.count(b"qBittorrent") == VANILLA_HTML.count(b"qBittorrent"), (
        f"expected {VANILLA_HTML.count(b'qBittorrent')} `qBittorrent` tokens, "
        f"got {body.count(b'qBittorrent')}"
    )
    assert "Боба".encode() not in body, "proxy injected Боба branding"


def check_html_passed_through_byte_for_byte(body, headers):
    assert body == VANILLA_HTML, "proxied HTML differs from upstream bytes"


def check_no_theme_overlay_assets_injected(body, headers):
    assert b"__qbit_theme__" not in body, "theme overlay assets still injected"
    assert b"boba-logo" not in body, "boba logo still substituted"


def check_csp_header_not_rewritten(body, headers):
    csp = headers.get("Content-Security-Policy")
    assert csp == UPSTREAM_CSP, f"CSP rewritten: {csp!r}"
    assert "7187" not in (csp or ""), "merge-service origin injected into CSP"


def post_torrent_add_through_proxy(tracker_url: str) -> bytes:
    """POST /api/v2/torrents/add through the proxy; return the body the
    upstream actually received.

    Guards the tracker-add interception (identify_plugin ->
    download_via_nova2dl) that is NOT part of the theme overlay and MUST
    keep working after its removal.
    """
    received: list[bytes] = []

    class _AddHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            received.append(self.rfile.read(n) if n else b"")
            payload = b"Ok."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    upstream, upstream_thread = _serve(_AddHandler)
    dp = _load_download_proxy()
    dp.QBITTORRENT_HOST = "127.0.0.1"
    dp.QBITTORRENT_PORT = str(upstream.server_address[1])

    with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as tmp:
        tmp.write(b"d8:announce0:e")
    dp.download_via_nova2dl = lambda plugin, url: tmp.name

    proxy, proxy_thread = _serve(dp.DownloadHandler)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{proxy.server_address[1]}/api/v2/torrents/add",
            data=urllib.parse.urlencode({"urls": tracker_url}).encode(),
            method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=15):
            pass
        return received[0] if received else b""
    finally:
        proxy.shutdown()
        proxy.server_close()
        proxy_thread.join(timeout=5)
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)
        sys.modules.pop("_dp_vanilla_guard", None)
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def check_tracker_interception_still_works(body, headers):
    """MUST-PRESERVE: the torrent-add tracker interception is untouched."""
    seen = post_torrent_add_through_proxy(
        "https://rutracker.org/forum/viewtopic.php?t=1234567"
    )
    assert b"file%3A%2F%2F" in seen or b"file://" in seen, (
        "the rutracker URL was NOT intercepted and rewritten to a local "
        f"file:// path — upstream received {seen!r}"
    )
    assert b"rutracker.org" not in seen, (
        f"the raw tracker URL leaked through to qBittorrent: {seen!r}"
    )


CHECKS = (
    check_script_block_qbittorrent_token_not_rewritten,
    check_html_passed_through_byte_for_byte,
    check_no_theme_overlay_assets_injected,
    check_csp_header_not_rewritten,
    check_tracker_interception_still_works,
)


# --------------------------------------------------------------------------
# pytest surface
# --------------------------------------------------------------------------

try:  # pragma: no cover — pytest may not be installed on every host
    import pytest
except ImportError:  # pragma: no cover
    pytest = None

if pytest is not None:  # pragma: no cover — exercised under pytest only

    @pytest.fixture(autouse=True)
    def _serialize_live_searches():
        """Override the conftest autouse fixture.

        This test stands up its OWN in-process servers and needs no live
        merge service, so the orchestrator-idle wait does not apply.
        """
        yield

    @pytest.fixture()
    def proxied_response():
        return fetch_through_proxy()

    @pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.__name__)
    def test_vanilla_webui_passthrough(check, proxied_response):
        check(*proxied_response)


# --------------------------------------------------------------------------
# stdlib standalone runner
# --------------------------------------------------------------------------

def main() -> int:
    body, headers = fetch_through_proxy()
    failures = 0
    for check in CHECKS:
        try:
            check(body, headers)
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {check.__name__}\n      {exc}")
        else:
            print(f"PASS  {check.__name__}")
    print(f"\n{len(CHECKS) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
