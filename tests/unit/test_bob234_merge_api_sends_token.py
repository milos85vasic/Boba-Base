"""BOB-234 — the merge-API integration helpers must SEND the API token.

Root cause (docs/Issues.md BOB-234): the live merge service runs with
``BOBA_API_TOKEN`` armed (BOB-197 mandatory-auth guard), and
``download-proxy/src/api/routes.py::require_api_token`` answers 401 unless the
request carries ``Authorization: Bearer <token>`` or ``X-Boba-Token: <token>``.
``tests/integration/test_merge_api.py`` used a bare ``requests.Session`` that
sent neither, so every mutating-route test (hooks, magnet, download) failed 401.

These tests drive a REAL local ``http.server`` that mimics exactly that
contract (401 without a matching token header, 200 with it) and prove:

* the token is resolved from the environment first, then from ``.env``;
* the session helper really sends it (200) where a bare session gets 401;
* the token is only sent to the merge-service base URL (never leaked to other
  hosts, e.g. the qBittorrent proxy);
* an armed service with NO token available FAILS loudly (never skips), and the
  failure message never contains a token value (§11.4.10);
* a wrong token is detected up front and FAILS loudly;
* an unarmed (open) service with no token is not a failure.

No secret from the real ``.env`` is read by these tests: every token here is a
fixture value generated per test run.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from tests.integration.merge_api_auth import (
    MergeTokenSession,
    assert_token_usable,
    resolve_api_token,
)


def _make_server(expected_token: str | None) -> tuple[ThreadingHTTPServer, list[dict[str, str]]]:
    """Local server mimicking ``require_api_token``.

    ``expected_token=None`` -> OPEN service (no auth), like BOBA_API_TOKEN unset.
    Records every request's headers so tests can assert what was sent.
    """
    seen: list[dict[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            seen.append({k.lower(): v for k, v in self.headers.items()})
            if expected_token is not None:
                supplied = ""
                auth = self.headers.get("Authorization", "")
                if auth.lower().startswith("bearer "):
                    supplied = auth[7:].strip()
                if not supplied:
                    supplied = self.headers.get("X-Boba-Token", "").strip()
                if not supplied or not secrets.compare_digest(supplied, expected_token):
                    self._reply(401, b'{"detail":"Unauthorized: valid API token required"}')
                    return
            self._reply(200, b'{"ok":true}')

        def _reply(self, code: int, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _handle
        do_POST = _handle
        do_DELETE = _handle

        def log_message(self, *args: object) -> None:  # silence stderr noise
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


@pytest.fixture
def token() -> str:
    return secrets.token_hex(32)


@pytest.fixture
def armed(token: str) -> Iterator[tuple[str, list[dict[str, str]]]]:
    server, seen = _make_server(token)
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", seen
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def open_service() -> Iterator[str]:
    server, _ = _make_server(None)
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# token resolution
# ---------------------------------------------------------------------------


def test_resolve_prefers_environment(tmp_path, token):
    dotenv = tmp_path / ".env"
    dotenv.write_text("BOBA_API_TOKEN=from-dotenv\n")
    value, source = resolve_api_token(environ={"BOBA_API_TOKEN": token}, dotenv_path=dotenv)
    assert value == token
    assert source == "environment"


def test_resolve_falls_back_to_dotenv(tmp_path, token):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f'# comment\nOTHER=x\nexport BOBA_API_TOKEN="{token}"  \nLAST=y\n')
    value, source = resolve_api_token(environ={}, dotenv_path=dotenv)
    assert value == token
    assert source == str(dotenv)


def test_resolve_blank_env_falls_back_to_dotenv(tmp_path, token):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"BOBA_API_TOKEN='{token}'\n")
    value, _ = resolve_api_token(environ={"BOBA_API_TOKEN": "   "}, dotenv_path=dotenv)
    assert value == token


def test_resolve_absent_returns_empty(tmp_path):
    value, source = resolve_api_token(environ={}, dotenv_path=tmp_path / "missing.env")
    assert value == ""
    assert source == ""


# ---------------------------------------------------------------------------
# the session really sends the header
# ---------------------------------------------------------------------------


def test_bare_session_gets_401_against_armed_service(armed):
    """Characterises the BOB-234 defect: the pre-fix bare session -> 401."""
    base, _ = armed
    resp = requests.Session().post(f"{base}/api/v1/magnet", json={}, timeout=5)
    assert resp.status_code == 401


def test_token_session_gets_200_against_armed_service(armed, token):
    base, seen = armed
    session = MergeTokenSession(base, token)
    resp = session.post(f"{base}/api/v1/magnet", json={}, timeout=5)
    assert resp.status_code == 200
    assert seen[-1].get("x-boba-token") == token
    # DELETE (hooks) and GET go through the same path
    assert session.delete(f"{base}/api/v1/hooks/x", timeout=5).status_code == 200
    assert session.get(f"{base}/health", timeout=5).status_code == 200


def test_token_not_sent_outside_merge_base_url(armed, open_service, token):
    base, _ = armed
    other_server, other_seen = _make_server(None)
    try:
        other = f"http://127.0.0.1:{other_server.server_address[1]}"
        session = MergeTokenSession(base, token)
        assert session.post(f"{other}/api/v2/auth/login", data={"a": "b"}, timeout=5).status_code == 200
        assert "x-boba-token" not in other_seen[-1]
        assert "authorization" not in other_seen[-1]
    finally:
        other_server.shutdown()
        other_server.server_close()


def test_prefix_lookalike_host_does_not_receive_token(token):
    """A string-prefix lookalike (``127.0.0.10``, ``:71`` vs ``:7187``) must not match."""
    session = MergeTokenSession("http://127.0.0.1:7187", token)
    assert session._targets_merge("http://127.0.0.1:7187/api/v1/magnet")
    assert session._targets_merge("http://127.0.0.1:7187")
    assert not session._targets_merge("http://127.0.0.10:7187/api/v1/magnet")
    assert not session._targets_merge("http://127.0.0.1:71/api/v1/magnet")
    assert not session._targets_merge("https://127.0.0.1:7187/api/v1/magnet")
    assert not session._targets_merge("http://127.0.0.1:7186/api/v2/auth/login")


# ---------------------------------------------------------------------------
# fail loudly, never skip, never leak
# ---------------------------------------------------------------------------


def test_armed_service_without_token_fails_loudly(armed, token):
    base, _ = armed
    with pytest.raises(pytest.fail.Exception) as info:
        assert_token_usable(base, "", "")
    msg = str(info.value)
    assert "BOBA_API_TOKEN" in msg
    assert "401" in msg
    assert token not in msg


def test_armed_service_with_wrong_token_fails_loudly(armed, token):
    base, _ = armed
    wrong = secrets.token_hex(32)
    with pytest.raises(pytest.fail.Exception) as info:
        assert_token_usable(base, wrong, "environment")
    msg = str(info.value)
    assert "rejected" in msg
    assert wrong not in msg
    assert token not in msg


def test_armed_service_with_right_token_passes(armed, token):
    base, _ = armed
    assert_token_usable(base, token, "environment")  # must not raise


def test_open_service_without_token_is_not_a_failure(open_service):
    assert_token_usable(open_service, "", "")  # must not raise


# ---------------------------------------------------------------------------
# cleanup must authenticate too: the :7186 download-proxy gates
# /api/v2/torrents/delete with the same BOBA_API_TOKEN, so an unauthenticated
# cleanup silently left the test torrent behind (observed live 2026-09-23).
# ---------------------------------------------------------------------------


def _make_qbit_server(expected_token: str) -> tuple[ThreadingHTTPServer, set[str]]:
    """Mimics the :7186 proxy: delete needs the token; info lists what is left."""
    present: set[str] = set()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            from urllib.parse import parse_qs

            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
            if self.path.startswith("/api/v2/torrents/delete"):
                if self.headers.get("X-Boba-Token", "") != expected_token:
                    self._reply(401, b'{"detail":"Unauthorized"}')
                    return
                for h in parse_qs(body).get("hashes", [""])[0].split("|"):
                    present.discard(h)
                self._reply(200, b"")
                return
            self._reply(404, b"")

        def do_GET(self) -> None:
            import json
            from urllib.parse import parse_qs, urlsplit

            wanted = parse_qs(urlsplit(self.path).query).get("hashes", [""])[0]
            rows = [{"hash": h} for h in sorted(present) if not wanted or h == wanted]
            self._reply(200, json.dumps(rows).encode())

        def _reply(self, code: int, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, present


def test_qbit_cleanup_sends_token_and_confirms_removal(token):
    from tests.integration.merge_api_auth import qbit_delete_confirmed, qbit_snapshot_hashes

    server, present = _make_qbit_server(token)
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        sess = requests.Session()
        before = qbit_snapshot_hashes(sess, base, token)
        present.add("a" * 40)  # the test's own torrent, added AFTER the baseline
        qbit_delete_confirmed(sess, base, "a" * 40, token, before, timeout=3)
        assert "a" * 40 not in present
    finally:
        server.shutdown()
        server.server_close()


def test_qbit_cleanup_fails_loudly_when_delete_rejected(token):
    from tests.integration.merge_api_auth import qbit_delete_confirmed, qbit_snapshot_hashes

    server, present = _make_qbit_server(token)
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        sess = requests.Session()
        # the GET side of the stub is open, so the baseline is readable even
        # with no token; only the DELETE is token-gated
        before = qbit_snapshot_hashes(sess, base, "")
        present.add("b" * 40)
        with pytest.raises(pytest.fail.Exception) as info:
            qbit_delete_confirmed(sess, base, "b" * 40, "", before, timeout=2)
        assert "401" in str(info.value)
        assert token not in str(info.value)
    finally:
        server.shutdown()
        server.server_close()


def test_qbit_cleanup_never_deletes_a_preexisting_torrent(token):
    """An operator's torrent (in the baseline) is out of scope even if the hash matches."""
    from tests.integration.merge_api_auth import qbit_delete_confirmed, qbit_snapshot_hashes

    server, present = _make_qbit_server(token)
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        present.add("c" * 40)
        sess = requests.Session()
        before = qbit_snapshot_hashes(sess, base, token)
        qbit_delete_confirmed(sess, base, "c" * 40, token, before, timeout=2)
        assert "c" * 40 in present, "a torrent that existed before the test was deleted"
    finally:
        server.shutdown()
        server.server_close()


def test_qbit_cleanup_is_disarmed_when_baseline_unreadable(token):
    """No provable baseline -> no delete at all (fail safe, nothing touched)."""
    from tests.integration.merge_api_auth import qbit_delete_confirmed

    server, present = _make_qbit_server(token)
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        present.add("d" * 40)
        qbit_delete_confirmed(requests.Session(), base, "d" * 40, token, None, timeout=2)
        assert "d" * 40 in present, "delete ran without a readable baseline"
    finally:
        server.shutdown()
        server.server_close()


def test_qbit_snapshot_returns_none_when_unreachable():
    from tests.integration.merge_api_auth import qbit_snapshot_hashes

    assert qbit_snapshot_hashes(requests.Session(), "http://127.0.0.1:1", "") is None
