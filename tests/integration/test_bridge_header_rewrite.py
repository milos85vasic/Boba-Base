"""Guards the webui-bridge header-rewrite contract.

Reported symptom: hitting http://localhost:7188/ in a browser, logging
in with admin/admin, getting back 401 Unauthorized. Root cause: the
bridge forwarded the browser's Referer/Origin headers to qBittorrent
unchanged, and qBittorrent's auth endpoint enforces same-origin.

The source now rewrites Referer + Origin to ``http://localhost:$QBITTORRENT_PORT``.
These tests lock that contract in place so a future refactor can't
silently regress it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "webui-bridge.py"


@pytest.fixture(scope="module")
def src() -> str:
    return BRIDGE.read_text(encoding="utf-8")


def test_bridge_rewrites_referer_to_qbit_port(src: str) -> None:
    """The proxy code must translate the incoming Referer header to
    the qBittorrent origin; otherwise qBittorrent WebUI returns 401
    on auth endpoints.
    """
    # Find the proxy_to_qbittorrent method body.
    m = re.search(r"def proxy_to_qbittorrent\(.*?\n\s*except", src, re.DOTALL)
    assert m is not None, "proxy_to_qbittorrent method not found"
    body = m.group(0)
    assert re.search(r'header_lower\s*==\s*["\']referer["\']', body), (
        "proxy_to_qbittorrent must rewrite the Referer header"
    )
    assert re.search(r'header_lower\s*==\s*["\']origin["\']', body), (
        "proxy_to_qbittorrent must rewrite the Origin header"
    )
    # The rewrite target must be qBittorrent's port, not the bridge port.
    assert "QBITTORRENT_PORT" in body
    assert "BRIDGE_PORT" not in body.replace("proxy_to_qbittorrent", "")[:200]


def test_bridge_forwards_upstream_error_body_on_http_error(src: str) -> None:
    """On urllib HTTPError the bridge must forward qBittorrent's
    actual status + body (so a 401 from qBittorrent reads as 401 with
    its own 'Fails.' body), not BaseHTTPRequestHandler's generic
    'Error response' HTML.
    """
    m = re.search(r"def proxy_to_qbittorrent\(.*?\n(?:\n{2,}|\Z)", src, re.DOTALL)
    assert m, "proxy_to_qbittorrent method not found"
    body = m.group(0)
    assert "except urllib.error.HTTPError" in body
    # Must send_response with e.code AND write the upstream body.
    assert "self.send_response(e.code)" in body
    assert "e.read()" in body


def test_bridge_strips_transfer_encoding_header(src: str) -> None:
    """urllib handles chunked encoding — forwarding the upstream
    Transfer-Encoding header would corrupt the response to the
    client. Skip it.
    """
    m = re.search(r"def proxy_to_qbittorrent\(.*?\n(?:\n{2,}|\Z)", src, re.DOTALL)
    assert m
    body = m.group(0)
    assert re.search(
        r'header\.lower\(\)\s*==\s*["\']transfer-encoding["\']',
        body,
    ), "proxy_to_qbittorrent must skip the Transfer-Encoding upstream header"


def test_bridge_uses_threaded_http_server(src: str) -> None:
    """Single-threaded HTTPServer means one slow request (e.g. a
    client long-poll to qBit) blocks the liveness probe, which
    flipped the dashboard chip to 'down' every time a real user was
    mid-request. ThreadingHTTPServer handles every connection on its
    own thread.
    """
    assert "ThreadingHTTPServer" in src, (
        "webui-bridge.py must import ThreadingHTTPServer (not HTTPServer) "
        "so slow requests do not block the liveness probe"
    )
    # Import site must use the threaded class.
    import_matches = re.findall(
        r"from http\.server import[^\n]+",
        src,
    )
    assert any("ThreadingHTTPServer" in m for m in import_matches), "import site must name ThreadingHTTPServer"
    # Construction site must use the threaded class too.
    assert re.search(r"ThreadingHTTPServer\s*\(", src), "server construction must use ThreadingHTTPServer(...)"
    # And the non-threaded class must not be used.
    assert not re.search(r"\bHTTPServer\s*\(", src.replace("ThreadingHTTPServer", "")), (
        "no remaining HTTPServer(...) construction sites — must be ThreadingHTTPServer"
    )


@pytest.mark.timeout(20)
def test_bridge_serves_concurrent_requests_without_blocking(webui_bridge_live: str) -> None:
    """Live smoke: fire 5 concurrent GETs at the bridge and ensure
    none time out (regression for the 'WebUI Bridge (down)' report).
    The ``webui_bridge_live`` fixture errors if the bridge is down.
    """
    import concurrent.futures
    import urllib.request

    def _hit() -> int:
        with urllib.request.urlopen(f"{webui_bridge_live}/", timeout=5) as r:
            return r.status

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: _hit(), range(5)))
    assert all(s == 200 for s in results), f"not all concurrent probes returned 200: {results}"


def test_bridge_live_login_round_trip(webui_bridge_live: str) -> None:
    """Live-stack smoke: POST /api/v2/auth/login through :7188 must
    return 200 with body starting with 'Ok.', and a subsequent
    cookie-bearing request must succeed.
    """
    import http.cookiejar
    import urllib.parse
    import urllib.request

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    data = urllib.parse.urlencode({"username": "admin", "password": "admin"}).encode()
    req = urllib.request.Request(
        f"{webui_bridge_live}/api/v2/auth/login",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": webui_bridge_live,
        },
        method="POST",
    )
    try:
        with opener.open(req, timeout=10) as resp:
            # VERSION CONTRACT (measured 2026-09-01 against the live image,
            # qBittorrent v5.2.3 / WebAPI 2.15.1): a SUCCESSFUL login returns
            # HTTP 204 with an EMPTY body and sets cookie QBT_SID_<port>.
            # qBittorrent 4.x returned HTTP 200 with body "Ok.".
            #
            # This test asserted the 4.x contract only, so it FAILED against a
            # working 5.x server ("login returned 204"). Accept BOTH, and keep
            # the session cookie as the authoritative signal — the same rule
            # download-proxy/src/api/routes.py and the Go client now apply.
            status = resp.status
            body = resp.read().decode("utf-8", errors="ignore")
            assert status in (200, 204), f"login returned {status}, body={body!r}"
            if status == 200:
                assert body.strip().startswith("Ok"), f"login body: {body!r}"
            else:
                assert body.strip() == "", f"204 must carry an empty body, got {body!r}"
            # Authoritative across both versions: a session cookie was issued.
            assert any(
                c.name == "SID" or c.name.startswith("QBT_SID") for c in jar
            ), f"no session cookie issued; jar={[c.name for c in jar]}"
    except urllib.error.HTTPError as exc:
        pytest.fail(
            f"bridge returned {exc.code} on /api/v2/auth/login — "
            f"Referer rewrite likely not deployed; restart webui-bridge.py"
        )

    # Cookie-bearing API call should succeed.
    with opener.open(f"{webui_bridge_live}/api/v2/app/version", timeout=10) as resp:
        assert resp.status == 200
