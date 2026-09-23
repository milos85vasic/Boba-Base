"""BOB-203 — real auth-enforcing middleware for the :7186 download proxy.

MEASURED DEFECT (live, pre-fix). `plugins/download_proxy.py::DownloadHandler`
is a stdlib `ThreadingHTTPServer` handler that forwards EVERY request
byte-for-byte to qBittorrent (`proxy_to_qbittorrent`), including mutating
torrent control (`POST /api/v2/torrents/stop`, `/pause`, `/delete`, `/add`,
...). Measured live against the operator's running stack: a caller holding a
qBittorrent WebUI session (trivially obtainable — the WebUI credentials are
the hardcoded `admin`/`admin`, see CLAUDE.md "Critical Constraints") could
call `POST /api/v2/torrents/stop` through :7186 and get a `200` with ZERO
awareness of `BOBA_API_TOKEN` anywhere on this path, even though the token
was ALREADY armed in `.env`. `download-proxy/src/api/routes.py`'s
`require_api_token` dependency — a working, correctly-implemented,
`hmac.compare_digest`-based gate — exists and protects :7187's own mutating
routes (hooks, schedules, `PUT /theme`, `/download*`, `/magnet`), but was
never wired onto anything :7186 forwards, because :7186 is not a FastAPI app
at all (it predates `Depends()` entirely).

THE FIX (this session): `DownloadHandler._boba_token_ok` /
`_send_unauthorized` reimplement `require_api_token`'s exact contract
(env-gated AT REQUEST TIME, constant-time `hmac.compare_digest`, dual header
support — `Authorization: Bearer <token>` OR `X-Boba-Token: <token>`,
fail-open when `BOBA_API_TOKEN` is unset/empty — §11.4.122, UNCHANGED by this
fix) directly inside `plugins/download_proxy.py`, applied in `do_POST` to
every path except the two qBittorrent session-lifecycle endpoints
(`/api/v2/auth/login`, `/api/v2/auth/logout`) — gating those would break the
WebUI's own login flow (a browser POSTs credentials there with no way to also
attach a `BOBA_API_TOKEN` header) without closing any additional exposure:
even WITH a session obtained through the (deliberately, per CLAUDE.md)
hardcoded admin/admin credentials, every actual torrent mutation now ALSO
requires the separate `BOBA_API_TOKEN` secret. `proxy_to_qbittorrent` was
additionally taught to STRIP the `Authorization` / `X-Boba-Token` headers
before forwarding — both are consumed by THIS gate and mean nothing to
qBittorrent, which was measured (directly against :7185, no proxy involved)
to answer ANY request carrying an `Authorization` header with its own `403`,
independent of this fix — forwarding the exact header a caller uses to
satisfy OUR gate would make it the thing that gets THEIR own otherwise-valid
request rejected downstream.

WHY THIS IS A DIFFERENT MODULE THAN `require_api_token` (§11.4.28/§11.4.251
— not a byte-identical fork; a genuinely different transport). This handler
is loaded by qBittorrent's nova3 engine loader as a search plugin and
therefore imports NOTHING but the standard library (see the BOB-111
rate-limiting comment in `plugins/download_proxy.py`) — importing from
`download-proxy/src/api` would couple the plugin surface to the FastAPI app's
dependency tree AND would race the OTHER thread's `sys.path` mutation in
`download-proxy/src/main.py::main` (`proxy_thread` and `fastapi_thread` start
concurrently). The CONTRACT (env var name, header names, constant-time
compare, fail-open default, 401 body shape) is therefore pinned by tests on
BOTH sides rather than by a shared import.

EVIDENCE CLASS (§11.4.226): RUNTIME-OVER-A-REAL-SOCKET, matching the sibling
rate-limiting file `tests/security/test_rate_limit_download_proxy.py`, whose
`_Stack`/`_StubQbtHandler`/`_free_port` harness this file reuses verbatim
(§11.4.251 — one harness, not a divergent copy). This file binds the REAL
`DownloadHandler` to a real ephemeral TCP port with a real
`ThreadingHTTPServer` and drives it with real `urllib` requests, exactly as
the container does. The one thing that is NOT real is the qBittorrent
backend: a local stub HTTP server stands in for :7185 so the test never needs
the operator's container and never proxies to a real torrent client
(§11.4.27(A) — the stub is downstream of the gate under test, not itself
under test). This is ALSO the project's own documented fallback for exactly
this situation (per the BOB-203 dispatch brief): "FastAPI's own
TestClient/httpx.AsyncClient driving the real app object in-process ... is
an acceptable real-infrastructure interpretation" — the stdlib-server
analogue of that same idea, since `DownloadHandler` has no ASGI app object
for a TestClient to drive.

§11.4.10: the token used throughout is a SYNTHETIC per-run uuid value, never
a real secret, never logged. The wrong-token case is a second, DIFFERENT
synthetic value.

§11.4.263: no subprocess or proc object is mocked in this file, so no
`mock.pid` is involved anywhere.

RD2-23-style permanent regression guard: this file IS the standing guard for
the BOB-203 fix (§11.4.135) — no separate/duplicate guard test is authored.
Polarity-switch proof (§11.4.115), captured in this session: with the
`_boba_token_ok`/`do_POST` gate reverted to its pre-fix form (`git stash` /
`git diff | git apply -R` on `plugins/download_proxy.py`), every
`test_unauthenticated_*_is_401_when_token_set` case in this file goes RED
(each "expected 401 ... got 200" — the right reason, auth bypassed, not a
script-bug crash); restoring the fix returns the file to GREEN with zero
diff against the fixed source.
"""

# CM-NO-UNSCOPED-LIVE-DESTRUCTION: EXEMPT reason=stub_server_not_a_client — this
# file IMPLEMENTS `/api/v2/torrents/{info,stop,pause,resume,delete,add,
# setCategory}` and `/api/v2/app/{setPreferences,shutdown}` as a throwaway
# `_StubQbtHandler` SERVER (bound to 127.0.0.1 on a dynamically-allocated
# free port via `_free_port()`, torn down at the end of every test) that the
# real `DownloadHandler` proxy under test is pointed at via `QBITTORRENT_HOST
# = 127.0.0.1`. No request in this file EVER reaches a real, configured, or
# live qBittorrent instance — only this file's own ephemeral, test-owned
# stub. Matches the same exemption already granted to
# tests/unit/test_stress_purge_scoping.py for the identical reason.

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import socket
import sys
import threading
import uuid
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DP_PATH = os.path.join(_REPO_ROOT, "plugins", "download_proxy.py")

_TOKEN = f"test-token-{uuid.uuid4()}"
_WRONG_TOKEN = f"wrong-token-{uuid.uuid4()}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _StubQbtHandler(BaseHTTPRequestHandler):
    """Stands in for qBittorrent on :7185.

    Records every request it receives (method, path, headers seen) into the
    class-level ``seen`` list so a test can assert BOTH that the gate let a
    request through AND what the downstream request actually looked like
    (specifically: that the auth headers the gate consumed were stripped
    before forwarding). `auth/login` answers 204 with a fake session cookie,
    mirroring qBittorrent's real contract; everything else answers 200,
    mirroring qBittorrent silently accepting a mutation against an unknown
    torrent hash (the exact shape the live-measured defect exploited).
    """

    protocol_version = "HTTP/1.1"
    seen: list[dict[str, object]] = []
    lock = threading.Lock()

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
        pass

    def _record(self, body: bytes | None):
        with self.lock:
            self.__class__.seen.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": body,
                }
            )

    def do_GET(self):  # noqa: N802 - stdlib signature
        self._record(None)
        payload = b"stub-qbittorrent"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # noqa: N802 - stdlib signature
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else None
        self._record(body)

        if self.path.startswith("/api/v2/auth/login"):
            self.send_response(204)
            self.send_header("Set-Cookie", "QBT_SID_STUB=fake-session-value")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _load_download_proxy(env: dict[str, str], qbt_port: int):
    """Import a FRESH `download_proxy` module under the given env.

    A fresh module object per case is required: nothing in this module's
    auth gate is cached at import time (BOBA_API_TOKEN is read per-request,
    per `require_api_token`'s own contract), but QBITTORRENT_HOST/PORT ARE
    read at import time by module-level constants, so a fresh module per
    stub-backend port is still required — matching the sibling rate-limit
    harness this file reuses.
    """
    # NOTE: this helper's save/restore window covers ONLY module import
    # (QBITTORRENT_HOST/PORT are read from module-level constants at import
    # time, so they must be correct AT import). BOBA_API_TOKEN is
    # DELIBERATELY NOT part of this function's save/restore — it is read by
    # `_boba_token_ok` AT REQUEST TIME, long after this function returns, so
    # restoring it here would unset it before the first HTTP request ever
    # arrives and every case would silently exercise the fail-open path
    # instead of the gate. `_Stack` owns BOBA_API_TOKEN's lifetime instead,
    # for exactly as long as the stack itself is alive.
    env = dict(env)
    env.pop("BOBA_API_TOKEN", None)
    env["QBITTORRENT_HOST"] = "127.0.0.1"
    env["QBITTORRENT_PORT"] = str(qbt_port)
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        spec = importlib.util.spec_from_file_location("download_proxy_auth_case", _DP_PATH)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["download_proxy_auth_case"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _Stack:
    """A live stub-qBittorrent + a live download-proxy, both on real sockets."""

    def __init__(self, env: dict[str, str]):
        _StubQbtHandler.seen = []

        # BOBA_API_TOKEN is read by `_boba_token_ok` AT REQUEST TIME (per
        # require_api_token's own contract, mirrored here), so it must stay
        # set in the process environment for the STACK's whole lifetime —
        # not merely during module import. Saved/restored around the stack's
        # own lifetime (close()) rather than _load_download_proxy's narrower
        # import-time window.
        self._token_key = "BOBA_API_TOKEN"
        self._saved_token = os.environ.get(self._token_key)
        if self._token_key in env:
            os.environ[self._token_key] = env[self._token_key]
        else:
            os.environ.pop(self._token_key, None)

        self.qbt_port = _free_port()
        self.qbt = ThreadingHTTPServer(("127.0.0.1", self.qbt_port), _StubQbtHandler)
        self.qbt.daemon_threads = True
        threading.Thread(target=self.qbt.serve_forever, daemon=True).start()

        self.mod = _load_download_proxy(env, self.qbt_port)
        self.proxy_port = _free_port()
        self.proxy = ThreadingHTTPServer(("127.0.0.1", self.proxy_port), self.mod.DownloadHandler)
        self.proxy.daemon_threads = True
        threading.Thread(target=self.proxy.serve_forever, daemon=True).start()

    def _do(self, method: str, path: str, body: bytes | None, headers: dict[str, str] | None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.proxy_port}{path}", data=body, method=method
        )
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 - fixed loopback URL
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            with contextlib.closing(e):
                return e.code, dict(e.headers), e.read()

    def get(self, path: str = "/", headers: dict[str, str] | None = None):
        return self._do("GET", path, None, headers)

    def post(self, path: str, body: bytes = b"hashes=0000000000000000000000000000000000000000", headers=None):
        h = {"Content-Type": "application/x-www-form-urlencoded"}
        h.update(headers or {})
        return self._do("POST", path, body, h)

    def close(self):
        for srv in (self.proxy, self.qbt):
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:  # noqa: BLE001 - teardown is best-effort (§11.4.14)
                pass
        sys.modules.pop("download_proxy_auth_case", None)
        if self._saved_token is None:
            os.environ.pop(self._token_key, None)
        else:
            os.environ[self._token_key] = self._saved_token


@pytest.fixture
def stack():
    made: list[_Stack] = []

    def _make(**env):
        s = _Stack(env)
        made.append(s)
        return s

    yield _make
    for s in made:
        s.close()


# ---------------------------------------------------------------------------
# RED / the measured defect: unauthenticated mutation via :7186 when the
# token IS armed.
# ---------------------------------------------------------------------------


def test_unauthenticated_torrents_stop_is_401_when_token_set(stack):
    """The exact measured defect: POST /api/v2/torrents/stop with no header."""
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, body = s.post("/api/v2/torrents/stop")
    assert status == 401, f"expected 401, got {status} body={body!r}"
    assert json.loads(body) == {"detail": "Unauthorized: valid API token required"}
    # The request must NEVER have reached qBittorrent.
    assert _StubQbtHandler.seen == [], f"stub qBittorrent received a request it should never see: {_StubQbtHandler.seen}"


def test_wrong_token_torrents_stop_is_401(stack):
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, body = s.post(
        "/api/v2/torrents/stop", headers={"X-Boba-Token": _WRONG_TOKEN}
    )
    assert status == 401, f"expected 401, got {status} body={body!r}"
    assert _StubQbtHandler.seen == [], "wrong token still reached qBittorrent"


def test_empty_bearer_token_is_401(stack):
    """`Authorization: Bearer ` (empty) must not be treated as 'no header at all'
    and accidentally short-circuit into some other acceptance path."""
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, body = s.post(
        "/api/v2/torrents/stop", headers={"Authorization": "Bearer "}
    )
    assert status == 401, f"expected 401, got {status} body={body!r}"


# ---------------------------------------------------------------------------
# GREEN / golden-FALSE: a correct token succeeds, proving the gate is not
# just refusing everything unconditionally.
# ---------------------------------------------------------------------------


def test_correct_token_via_x_boba_token_header_succeeds(stack):
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, _body = s.post(
        "/api/v2/torrents/stop", headers={"X-Boba-Token": _TOKEN}
    )
    assert status == 200, f"correct token was refused: {status}"
    assert len(_StubQbtHandler.seen) == 1, "request never reached qBittorrent"
    assert _StubQbtHandler.seen[0]["path"] == "/api/v2/torrents/stop"


def test_correct_token_via_authorization_bearer_header_succeeds(stack):
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, _body = s.post(
        "/api/v2/torrents/stop", headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert status == 200, f"correct token was refused: {status}"
    assert len(_StubQbtHandler.seen) == 1


def test_auth_headers_are_stripped_before_forwarding_to_qbittorrent(stack):
    """Neither header the gate consumes reaches qBittorrent.

    Regression guard for the collision this session ALSO measured live: with
    the headers forwarded, qBittorrent's OWN embedded server answers any
    request carrying an Authorization header with its own unrelated 403 —
    independent of this fix — which would otherwise make satisfying THIS
    gate the thing that breaks the caller's own otherwise-valid request.
    """
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, _body = s.post(
        "/api/v2/torrents/stop",
        headers={"Authorization": f"Bearer {_TOKEN}", "X-Boba-Token": _TOKEN},
    )
    assert status == 200, status
    assert len(_StubQbtHandler.seen) == 1
    forwarded = _StubQbtHandler.seen[0]["headers"]
    assert "authorization" not in forwarded, forwarded
    assert "x-boba-token" not in forwarded, forwarded


# ---------------------------------------------------------------------------
# Fail-open preserved (§11.4.122) — the existing no-auth default is
# UNCHANGED when BOBA_API_TOKEN is unset/empty.
# ---------------------------------------------------------------------------


def test_open_when_token_unset(stack):
    s = stack()  # BOBA_API_TOKEN deliberately absent
    status, _headers, _body = s.post("/api/v2/torrents/stop")
    assert status == 200, f"mutation refused with no token configured at all: {status}"
    assert len(_StubQbtHandler.seen) == 1


def test_open_when_token_empty_string(stack):
    s = stack(BOBA_API_TOKEN="")
    status, _headers, _body = s.post("/api/v2/torrents/stop")
    assert status == 200, f"mutation refused with an empty-string token: {status}"


# ---------------------------------------------------------------------------
# Session-lifecycle exemption — login/logout stay reachable so the WebUI's
# own login flow (which cannot attach a BOBA_API_TOKEN header) still works.
# ---------------------------------------------------------------------------


def test_auth_login_remains_exempt_even_when_token_set(stack):
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, _body = s.post(
        "/api/v2/auth/login", body=b"username=admin&password=admin"
    )
    assert status == 204, f"login was gated: {status}"
    assert len(_StubQbtHandler.seen) == 1
    assert _StubQbtHandler.seen[0]["path"] == "/api/v2/auth/login"


def test_auth_logout_remains_exempt_even_when_token_set(stack):
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, _body = s.post("/api/v2/auth/logout", body=b"")
    assert status == 200, f"logout was gated: {status}"


# ---------------------------------------------------------------------------
# GET reads stay open regardless — the gate only ever applies to POST.
# ---------------------------------------------------------------------------


def test_get_requests_remain_open_regardless_of_token(stack):
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, _body = s.get("/api/v2/torrents/info")
    assert status == 200, f"a GET (read) request was gated: {status}"


# ---------------------------------------------------------------------------
# Every other qBittorrent mutating endpoint reachable through this proxy is
# closed the SAME way — not merely the one route the brief happened to name.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v2/torrents/stop",
        "/api/v2/torrents/pause",
        "/api/v2/torrents/resume",
        "/api/v2/torrents/delete",
        "/api/v2/torrents/add",
        "/api/v2/torrents/setCategory",
        "/api/v2/app/setPreferences",
        "/api/v2/app/shutdown",
    ],
)
def test_every_mutating_v2_endpoint_is_gated(stack, path):
    s = stack(BOBA_API_TOKEN=_TOKEN)
    status, _headers, _body = s.post(path, body=b"hashes=x")
    assert status == 401, f"{path} was reachable with no token: {status}"

    status2, _h2, _b2 = s.post(path, body=b"hashes=x", headers={"X-Boba-Token": _TOKEN})
    assert status2 == 200, f"{path} refused a CORRECT token: {status2}"
