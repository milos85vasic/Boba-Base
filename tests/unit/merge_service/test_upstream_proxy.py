"""Anti-bluff tests for the configurable outbound proxy (BOBA_UPSTREAM_PROXY).

Covers (CONST-XII — every assertion is on a user-observable outcome, and each
test fails against a no-op stub):

* ``config.proxy`` decision logic: BOBA_UPSTREAM_PROXY wins, *_PROXY fallback,
  loopback/sidecar/NO_PROXY bypass.
* ``apply_proxy_env`` maps the knob onto HTTP(S)_PROXY/NO_PROXY (the env the
  urllib plugin subprocesses honor).
* END-TO-END: a real aiohttp session built the way the tracker clients build it
  (``trust_env`` via ``aiohttp_session_kwargs`` + ``apply_proxy_env``) actually
  TRAVERSES a recording proxy for a tracker host, and STAYS DIRECT for loopback.
* END-TO-END through the REAL ``SearchOrchestrator._search_rutracker`` cookie
  path: with BOBA_UPSTREAM_PROXY set, its tracker fetch traverses the proxy.

Falsifiability (verified in-session, see report):
* Stub ``apply_proxy_env``→no-op  ⇒ env not mapped ⇒ aiohttp + search.py go
  direct ⇒ recording proxy log empty ⇒ traversal tests fail.
* Remove ``**_tracker_session_kwargs()`` (trust_env) from search.py ⇒
  ``_search_rutracker`` fetch goes direct to the unresolvable mirror ⇒ proxy log
  empty ⇒ test_search_rutracker_routes_through_proxy fails.
"""

from __future__ import annotations

import http.server
import importlib
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

import aiohttp
import pytest

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "download-proxy" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Load the REAL config package + config.proxy from download-proxy/src. We purge
# any cached `config` first because the repo-root ./config qBittorrent data dir
# can shadow it as a PEP-420 namespace package under cross-file collection
# ordering (then `config.proxy` would be missing). Pinning SRC at sys.path[0] +
# the purge makes resolution deterministic regardless of collection order.
sys.modules.pop("config.proxy", None)
_cfg = sys.modules.get("config")
if _cfg is None or not getattr(_cfg, "__file__", None):
    sys.modules.pop("config", None)
_proxy = importlib.import_module("config.proxy")

# Load the REAL search.py the same way the rest of the merge_service unit suite
# does, so its top-level `from config.proxy import ...` resolves the real module.
_MS_PATH = SRC / "merge_service"
sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]  # type: ignore[attr-defined]
_spec = importlib.util.spec_from_file_location("merge_service.search", str(_MS_PATH / "search.py"))
_search = importlib.util.module_from_spec(_spec)
sys.modules["merge_service.search"] = _search
_spec.loader.exec_module(_search)  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# In-process recording forward proxy + loopback origin.
# --------------------------------------------------------------------------- #
class _RecordingProxy(http.server.BaseHTTPRequestHandler):
    urls: list[str] = []
    body: bytes = b"<html>no results</html>"

    def do_GET(self) -> None:  # noqa: N802
        type(self).urls.append(self.path)  # absolute-form URL when used as proxy
        self.send_response(200)
        self.send_header("Content-Type", "application/x-bittorrent")
        self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    do_POST = do_GET  # logins POST first

    def log_message(self, *a: object) -> None:  # silence
        return


class _Origin(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        b = b"ORIGIN-DIRECT"
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a: object) -> None:
        return


def _serve(handler) -> tuple[socketserver.TCPServer, int]:
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


@pytest.fixture
def recording_proxy():
    _RecordingProxy.urls = []
    srv, port = _serve(_RecordingProxy)
    try:
        yield f"http://127.0.0.1:{port}", _RecordingProxy
    finally:
        srv.shutdown()


# --------------------------------------------------------------------------- #
# Decision logic.
# --------------------------------------------------------------------------- #
def test_upstream_proxy_prefers_boba_knob(monkeypatch):
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "socks5://10.9.8.7:1080")
    monkeypatch.setenv("HTTPS_PROXY", "http://fallback:3128")
    assert _proxy.upstream_proxy() == "socks5://10.9.8.7:1080"


def test_upstream_proxy_falls_back_to_std_env(monkeypatch):
    monkeypatch.delenv("BOBA_UPSTREAM_PROXY", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://fallback:3128")
    assert _proxy.upstream_proxy() == "http://fallback:3128"


def test_upstream_proxy_none_when_unset(monkeypatch):
    for v in ("BOBA_UPSTREAM_PROXY", "ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(v, raising=False)
    assert _proxy.upstream_proxy() is None


def test_proxy_for_url_routes_tracker_host(monkeypatch):
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "socks5://10.9.8.7:1080")
    assert _proxy.proxy_for_url("https://rutracker.org/forum/tracker.php?nm=x") == "socks5://10.9.8.7:1080"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:7185/api/v2/auth/login",
        "http://localhost:9117/api/v2.0/indexers",
        "http://qbittorrent:7185/api/v2/torrents/add",
        "http://jackett:9117/UI/Dashboard",
    ],
)
def test_proxy_for_url_bypasses_loopback_and_sidecars(monkeypatch, url):
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "http://10.9.8.7:8080")
    assert _proxy.proxy_for_url(url) is None, f"{url} must stay direct"


def test_proxy_for_url_honors_no_proxy_suffix(monkeypatch):
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "http://10.9.8.7:8080")
    monkeypatch.setenv("NO_PROXY", ".corp.local,internal.example")
    assert _proxy.proxy_for_url("http://api.corp.local/x") is None
    assert _proxy.proxy_for_url("http://internal.example/y") is None
    assert _proxy.proxy_for_url("https://nnmclub.to/z") == "http://10.9.8.7:8080"


def test_apply_proxy_env_maps_knob_and_sets_no_proxy(monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", "socks5://egress:1080")
    _proxy.apply_proxy_env()
    import os

    assert os.environ["HTTP_PROXY"] == "socks5://egress:1080"
    assert os.environ["HTTPS_PROXY"] == "socks5://egress:1080"
    no_proxy = os.environ["NO_PROXY"].lower()
    for sidecar in ("127.0.0.1", "localhost", "qbittorrent", "jackett"):
        assert sidecar in no_proxy, f"NO_PROXY must contain {sidecar}; got {no_proxy!r}"


# --------------------------------------------------------------------------- #
# END-TO-END: real aiohttp built the production way honors the proxy + bypass.
# --------------------------------------------------------------------------- #
async def test_aiohttp_tracker_request_traverses_proxy(monkeypatch, recording_proxy):
    proxy_url, rec = recording_proxy
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", proxy_url)
    _proxy.apply_proxy_env()

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout, **_proxy.aiohttp_session_kwargs()) as s:
        async with s.get("http://tracker.invalid/forum/tracker.php?nm=ubuntu") as r:
            body = await r.read()

    assert body == _RecordingProxy.body, "client must receive the body the proxy served"
    assert rec.urls == ["http://tracker.invalid/forum/tracker.php?nm=ubuntu"], (
        f"tracker request must traverse the proxy; proxy saw {rec.urls!r}"
    )


async def test_aiohttp_loopback_stays_direct(monkeypatch, recording_proxy):
    proxy_url, rec = recording_proxy
    origin_srv, oport = _serve(_Origin)
    try:
        for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.setenv("BOBA_UPSTREAM_PROXY", proxy_url)
        _proxy.apply_proxy_env()

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout, **_proxy.aiohttp_session_kwargs()) as s:
            async with s.get(f"http://127.0.0.1:{oport}/health") as r:
                body = await r.read()

        assert body == b"ORIGIN-DIRECT", "loopback call must hit the origin directly"
        assert rec.urls == [], f"loopback call must NOT traverse the proxy; saw {rec.urls!r}"
    finally:
        origin_srv.shutdown()


# --------------------------------------------------------------------------- #
# END-TO-END through the real production search.py tracker client.
# --------------------------------------------------------------------------- #
def test_search_py_imported_real_proxy_helpers():
    """Anti-masking: the guarded import in search.py resolved the REAL module,
    not the no-op fallback (which would silently disable the proxy)."""
    assert _search._tracker_session_kwargs() == {"trust_env": True}


async def test_search_rutracker_routes_through_proxy(monkeypatch, recording_proxy):
    proxy_url, rec = recording_proxy
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(v, raising=False)
    # Cookie path: bb_session present → single GET to the mirror, no login POST.
    monkeypatch.setenv("RUTRACKER_COOKIES", "bb_session=testsession")
    monkeypatch.setenv("RUTRACKER_MIRRORS", "http://tracker.invalid")
    monkeypatch.setenv("BOBA_UPSTREAM_PROXY", proxy_url)
    _proxy.apply_proxy_env()

    orch = _search.SearchOrchestrator()
    results = await orch._search_rutracker("ubuntu", "all")

    # The recording proxy returns non-torrent HTML → 0 parsed results is fine.
    assert results == []
    assert len(rec.urls) == 1, f"_search_rutracker fetch must traverse the proxy; saw {rec.urls!r}"
    assert rec.urls[0].startswith("http://tracker.invalid/forum/tracker.php"), (
        f"proxy must have seen the rutracker mirror URL; saw {rec.urls!r}"
    )
