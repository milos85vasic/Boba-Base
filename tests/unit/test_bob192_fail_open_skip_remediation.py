"""BOB-192 — RED/GREEN guards for the 10 ratcheted CM-NO-FAIL-OPEN-SKIP findings.

Every finding in ``scripts/pre_build/cm_no_fail_open_skip.baseline`` was a
live-stack test helper that turned evidence the far side ANSWERED (an HTTP
>=400, a non-health body, an empty result set, a non-terminal status, an
answered error swallowed by a broad ``except``) into a SKIP. A skip counts as
green in every summary a human reads, so those helpers left real product
failures invisible (§11.4 / §11.4.69 / §11.4.201(1)).

Each test below drives the REAL helper (imported from the real test module,
never copied) against a LOCAL ``http.server`` fixture on an ephemeral port —
it never touches the live stack — and asserts:

* an ANSWERED failure makes the helper FAIL (``Failed`` / ``AssertionError``),
  never SKIP — this is the polarity that was RED against the pre-fix code;
* a genuinely UNREACHABLE endpoint (a closed port -> connection refused)
  still SKIPs, so the fix cannot collapse into a false-positive refusal on a
  host without the stack (§11.4.201(1) golden-FALSE / §11.4.3).

Mocks are permitted here (tests/unit/, §11.4.27): the only substitutions are
the module-level URL constants and, for the scaling module, its hard-wired
TCP-reachability probe.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import socket
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import requests

REPO = Path(__file__).resolve().parents[2]

Skipped = pytest.skip.Exception
Failed = pytest.fail.Exception


# --------------------------------------------------------------- fixtures
def _load(relpath: str, name: str):
    """Import a real test module by path (no copy of its helpers)."""
    path = REPO / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


Route = tuple[int, str, dict[str, str]]


class _Server:
    """Tiny local HTTP fixture: routes[(METHOD, path)] -> (status, body, headers)."""

    def __init__(self, routes: dict[tuple[str, str], Route | Callable[[], Route]]):
        self.routes = routes
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                path = self.path.split("?", 1)[0]
                entry = outer.routes.get((self.command, path), (404, "not found", {}))
                status, body, headers = entry() if callable(entry) else entry
                raw = body.encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = _serve
            do_POST = _serve

            def log_message(self, *a):  # keep pytest output clean
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def serve() -> Iterator[Callable[[dict], _Server]]:
    started: list[_Server] = []

    def _start(routes):
        s = _Server(routes)
        started.append(s)
        return s

    yield _start
    for s in started:
        s.close()


@pytest.fixture
def closed_url() -> str:
    """A URL whose port has no listener -> ConnectionRefused (genuine unreachable)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def _json(status: int, obj) -> Route:
    return (status, json.dumps(obj), {"Content-Type": "application/json"})


def _must_fail_not_skip(fn: Callable[[], object]) -> str:
    """Run fn; an answered failure MUST surface as a FAIL, never a SKIP."""
    try:
        fn()
    except Skipped as exc:
        pytest.fail(f"FAIL-OPEN: answered failure was converted into a SKIP: {exc}")
    except (Failed, AssertionError, requests.RequestException) as exc:
        return repr(exc)
    pytest.fail("helper returned normally on an answered failure (fail-open PASS)")


# ------------------------------------------------ test_jackett_autoconfig_real
@pytest.fixture(scope="module")
def jackett_mod():
    return _load("tests/integration/test_jackett_autoconfig_real.py", "_bob192_jackett_real")


def _jackett_ready(mod):
    return mod.jackett_ready.__wrapped__()


def test_jackett_ready_fails_on_answered_500(jackett_mod, serve, monkeypatch):
    srv = serve({("GET", "/UI/Login"): (500, "boom", {})})
    monkeypatch.setattr(jackett_mod, "JACKETT_URL", srv.url)
    _must_fail_not_skip(lambda: _jackett_ready(jackett_mod))


def test_jackett_ready_fails_on_answered_404(jackett_mod, serve, monkeypatch):
    srv = serve({})  # every path 404 — Jackett's login page is gone
    monkeypatch.setattr(jackett_mod, "JACKETT_URL", srv.url)
    _must_fail_not_skip(lambda: _jackett_ready(jackett_mod))


def test_jackett_ready_fails_on_answered_redirect_loop(jackett_mod, serve, monkeypatch):
    """TooManyRedirects is a RequestException the host ANSWERED (UNREACH trigger)."""
    srv = serve({("GET", "/UI/Login"): (302, "", {"Location": "/UI/Login"})})
    monkeypatch.setattr(jackett_mod, "JACKETT_URL", srv.url)
    _must_fail_not_skip(lambda: _jackett_ready(jackett_mod))


def test_jackett_ready_still_skips_when_unreachable(jackett_mod, closed_url, monkeypatch):
    monkeypatch.setattr(jackett_mod, "JACKETT_URL", closed_url)
    with pytest.raises(Skipped):
        _jackett_ready(jackett_mod)


# ------------------------------------------------------------ test_merge_api
@pytest.fixture(scope="module")
def merge_api_mod():
    return _load("tests/integration/test_merge_api.py", "_bob192_merge_api")


def test_qbit_login_fails_on_answered_rejection(merge_api_mod, serve):
    srv = serve({("POST", "/api/v2/auth/login"): (200, "Fails.", {})})
    _must_fail_not_skip(lambda: merge_api_mod._qbit_login(srv.url, requests.Session()))


def test_qbit_login_fails_on_answered_403(merge_api_mod, serve):
    srv = serve({("POST", "/api/v2/auth/login"): (403, "Forbidden", {})})
    _must_fail_not_skip(lambda: merge_api_mod._qbit_login(srv.url, requests.Session()))


def test_qbit_login_accepts_modern_204_with_cookie(merge_api_mod, serve):
    srv = serve({("POST", "/api/v2/auth/login"): (204, "", {"Set-Cookie": "QBT_SID=abc; path=/"})})
    merge_api_mod._qbit_login(srv.url, requests.Session())  # must not raise


def test_download_magnet_fails_when_qbit_refuses_add(merge_api_mod, serve):
    srv = serve(
        {
            ("POST", "/api/v1/download"): _json(200, {"status": "failed", "added_count": 0, "results": []}),
            ("POST", "/api/v2/torrents/delete"): (200, "", {}),
        }
    )
    t = merge_api_mod.TestDownloadEndpoint()
    _must_fail_not_skip(
        # This call bypasses pytest fixture injection (plain method call, not a
        # collected test), so the real `api_token` fixture never runs. The
        # value below is a placeholder: the stubbed `/api/v2/torrents/delete`
        # route above does zero token validation, so any string is behaviorally
        # correct here (BOB-234 added `api_token` for the real service's auth,
        # not for this mock).
        lambda: t.test_download_magnet_added_to_real_qbittorrent(srv.url, srv.url, requests.Session(), "test-token")
    )


def test_search_common_query_fails_on_empty_result_set(merge_api_mod, serve):
    srv = serve(
        {
            ("POST", "/api/v1/search/sync"): _json(
                200, {"query": "ubuntu", "results": [], "errors": [], "tracker_stats": []}
            )
        }
    )
    t = merge_api_mod.TestSearchEndpoint()
    _must_fail_not_skip(lambda: t.test_search_finds_real_results_for_common_query(srv.url, requests.Session()))


# ---------------------------------------------------- test_tracker_auth_live
@pytest.fixture(scope="module")
def auth_mod():
    return _load("tests/integration/test_tracker_auth_live.py", "_bob192_tracker_auth_live")


def test_merge_required_fails_on_answered_500(auth_mod, serve, monkeypatch):
    srv = serve({("GET", "/health"): _json(500, {"detail": "boom"})})
    monkeypatch.setattr(auth_mod, "MERGE_BASE", srv.url)
    _must_fail_not_skip(auth_mod._merge_service_required)


def test_merge_required_fails_on_non_health_body(auth_mod, serve, monkeypatch):
    srv = serve({("GET", "/health"): (200, "<html>not the merge service</html>", {})})
    monkeypatch.setattr(auth_mod, "MERGE_BASE", srv.url)
    _must_fail_not_skip(auth_mod._merge_service_required)


def test_merge_required_fails_on_unhealthy_status_field(auth_mod, serve, monkeypatch):
    srv = serve({("GET", "/health"): _json(200, {"status": "degraded"})})
    monkeypatch.setattr(auth_mod, "MERGE_BASE", srv.url)
    _must_fail_not_skip(auth_mod._merge_service_required)


def test_merge_required_accepts_healthy(auth_mod, serve, monkeypatch):
    srv = serve({("GET", "/health"): _json(200, {"status": "healthy", "service": "merge-search"})})
    monkeypatch.setattr(auth_mod, "MERGE_BASE", srv.url)
    auth_mod._merge_service_required()  # must not raise


def test_merge_required_still_skips_when_unreachable(auth_mod, closed_url, monkeypatch):
    monkeypatch.setattr(auth_mod, "MERGE_BASE", closed_url)
    with pytest.raises(Skipped):
        auth_mod._merge_service_required()


def _live_search_env(auth_mod, monkeypatch, url):
    monkeypatch.setattr(auth_mod, "MERGE_BASE", url)
    monkeypatch.setattr(auth_mod, "_POLL_DEADLINE_S", 0.6)
    monkeypatch.setattr(auth_mod, "_POLL_INTERVAL_S", 0.05)


def test_live_search_fails_when_search_never_terminates(auth_mod, serve, monkeypatch):
    srv = serve(
        {
            ("POST", "/api/v1/search"): _json(200, {"search_id": "s1", "status": "running"}),
            ("GET", "/api/v1/search/s1"): _json(200, {"search_id": "s1", "status": "running"}),
        }
    )
    _live_search_env(auth_mod, monkeypatch, srv.url)
    _must_fail_not_skip(auth_mod._run_live_search)


def test_live_search_fails_when_poll_answers_500(auth_mod, serve, monkeypatch):
    srv = serve(
        {
            ("POST", "/api/v1/search"): _json(200, {"search_id": "s2", "status": "running"}),
            ("GET", "/api/v1/search/s2"): _json(500, {"detail": "boom"}),
        }
    )
    _live_search_env(auth_mod, monkeypatch, srv.url)
    _must_fail_not_skip(auth_mod._run_live_search)


def test_live_search_returns_terminal_payload(auth_mod, serve, monkeypatch):
    srv = serve(
        {
            ("POST", "/api/v1/search"): _json(200, {"search_id": "s3", "status": "running"}),
            ("GET", "/api/v1/search/s3"): _json(200, {"search_id": "s3", "status": "completed", "tracker_stats": []}),
        }
    )
    _live_search_env(auth_mod, monkeypatch, srv.url)
    assert auth_mod._run_live_search()["status"] == "completed"


# ------------------------------------------------------ test_boba_scaling
@pytest.fixture(scope="module")
def scaling_mod():
    return _load("tests/scaling/test_boba_scaling.py", "_bob192_boba_scaling")


def test_scaling_gate_fails_on_answered_unhealthy_healthz(scaling_mod, serve, monkeypatch):
    srv = serve({("GET", "/healthz"): _json(503, {"status": "degraded"})})
    monkeypatch.setattr(scaling_mod, "_service_reachable", lambda *a, **k: True)
    monkeypatch.setattr(scaling_mod, "JACKETT_BOBA_URL", srv.url)
    _must_fail_not_skip(lambda: scaling_mod._services_up.__wrapped__(None))


def test_scaling_gate_accepts_healthy(scaling_mod, serve, monkeypatch):
    srv = serve({("GET", "/healthz"): _json(200, {"status": "ok"})})
    monkeypatch.setattr(scaling_mod, "_service_reachable", lambda *a, **k: True)
    monkeypatch.setattr(scaling_mod, "JACKETT_BOBA_URL", srv.url)
    scaling_mod._services_up.__wrapped__(None)  # must not raise


def test_scaling_gate_still_skips_when_port_closed(scaling_mod, monkeypatch):
    monkeypatch.setattr(scaling_mod, "_service_reachable", lambda *a, **k: False)
    with pytest.raises(Skipped):
        scaling_mod._services_up.__wrapped__(None)
