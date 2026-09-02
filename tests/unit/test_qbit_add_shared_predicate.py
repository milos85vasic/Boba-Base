"""OWED-1 — ``_qbit_add_succeeded`` has ONE implementation, and both sites use it.

THE DEFECT (measured 2026-09-01). ``_qbit_add_succeeded`` existed twice —
``download-proxy/src/api/routes.py`` and ``webui-bridge.py`` — and the copies
drifted until they recorded OPPOSITE verdicts for HTTP ``409``: ``routes`` read
it as a duplicate add (SUCCESS), the bridge read it as a malformed request
(FAILURE). A mutation of either copy left the OTHER site's tests green, which is
precisely how the divergence survived three review rounds.

THE ACCEPTANCE CRITERION (§11.4.115(F) / §1.1): a SINGLE mutation of the shared
predicate must make BOTH sites' tests fail. This file is the BRIDGE half of that
pair; ``tests/unit/test_qbit_login_compat.py`` is the ROUTES half. Mutate
``merge_service/qbit_add.py`` once (e.g. flip the ``409`` clause) and both go
RED together.

MEASURED CONTRACT (qBittorrent v5.2.3 / WebAPI 2.15.1, 2026-09-01) — each row
below is a row of that table, asserted through the BRIDGE's own entry point.
"""

import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _load_bridge():
    """Import ``webui-bridge.py`` (the hyphen forbids a plain import)."""
    spec = importlib.util.spec_from_file_location(
        "webui_bridge_add_predicate_probe", str(_REPO_ROOT / "webui-bridge.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bridge():
    return _load_bridge()


# (status, body, expected, case) — the measured contract table.
_CONTRACT = [
    (200, '{"added_torrent_ids":["abc"],"success_count":1,"pending_count":0}', True, "valid file add"),
    (202, '{"added_torrent_ids":[],"pending_count":1,"success_count":0}', True, ".torrent URL add"),
    (200, '{"added_torrent_ids":["def"],"success_count":1}', True, "magnet add"),
    (409, "Conflict", True, "duplicate add -> already present"),
    (415, "Error: 'x.torrent' is not a valid torrent file.", False, "corrupt/truncated/empty file"),
    (200, "Ok.", True, "legacy qBittorrent <5.x success"),
    (200, "Fails.", False, "legacy qBittorrent <5.x rejection"),
    (200, '{"added_torrent_ids":[],"success_count":0,"pending_count":0}', False, "200 that added nothing"),
    (200, "<html>not json</html>", False, "2xx with unparseable body is not evidence"),
    (200, '{"success_count":"N/A"}', False, "malformed counts classify as failure, never raise"),
    (400, "Bad Request", False, "4xx rejection"),
    (403, "", False, "unauthenticated add"),
]


@pytest.mark.parametrize(("status", "body", "expected", "case"), _CONTRACT)
def test_bridge_matches_the_measured_add_contract(bridge, status, body, expected, case):
    assert bridge._qbit_add_succeeded(status, body) is expected, case


@pytest.mark.parametrize(("status", "body", "expected", "case"), _CONTRACT)
def test_shared_predicate_matches_the_measured_add_contract(status, body, expected, case):
    from merge_service.qbit_add import qbit_add_succeeded

    assert qbit_add_succeeded(status, body) is expected, case


def test_bridge_409_verdict_agrees_with_routes(bridge):
    """The exact cell the two copies disagreed on.

    Pre-fix: bridge said ``False``, routes said ``True``. This asserts they now
    agree AND that they agree on the MEASURED value (duplicate = success), not
    merely on each other.
    """
    from api.routes import _qbit_add_succeeded as routes_predicate

    assert bridge._qbit_add_succeeded(409, "Conflict") is True
    assert routes_predicate(409, "Conflict") is True


def test_both_sites_delegate_to_the_one_implementation(bridge):
    """Structural: neither site re-implements the decision.

    Identity — not merely equal behaviour — so a future re-fork is caught even
    if the fork initially happens to agree.
    """
    from merge_service.qbit_add import qbit_add_succeeded

    import api.routes as routes

    assert bridge._qbit_add_succeeded_shared is qbit_add_succeeded
    assert routes._qbit_add_succeeded_shared is qbit_add_succeeded


def test_payload_invariant_is_enforced_at_the_api_entry_point():
    """``409`` is read as success ONLY because no caller can send an empty add.

    The predicate cannot distinguish "duplicate" from "nothing supplied" — both
    are ``409``. The soundness therefore lives upstream, and this asserts that
    enforcement point still exists: ``DownloadRequest`` rejects empty URLs, so a
    ``409`` reaching the predicate from the API means a genuine duplicate.
    """
    from pydantic import ValidationError

    from api.routes import DownloadRequest

    with pytest.raises(ValidationError):
        DownloadRequest(result_id="r", download_urls=[""])
    with pytest.raises(ValidationError):
        DownloadRequest(result_id="r", download_urls=["   "])

    assert DownloadRequest(result_id="r", download_urls=["https://example.test/a.torrent"]).download_urls == [
        "https://example.test/a.torrent"
    ]


class _StubQBittorrent(BaseHTTPRequestHandler):
    """Hermetic stand-in for qBittorrent on loopback.

    Answers ``/api/v2/auth/login`` the way the real 5.2.3 build does (204 +
    ``Set-Cookie: QBT_SID_<port>``) and replays a caller-chosen status/body for
    ``/api/v2/torrents/add``. Binds an ephemeral loopback port — it NEVER
    touches the operator's live instance.
    """

    add_status = 200
    add_body = b'{"added_torrent_ids":["abc"],"success_count":1}'
    seen = []

    def log_message(self, *args):  # silence the stub
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        type(self).seen.append((self.path, raw))
        if self.path.endswith("/api/v2/auth/login"):
            self.send_response(204)
            self.send_header("Set-Cookie", "QBT_SID_7185=stub-session; path=/")
            self.end_headers()
            return
        if self.path.endswith("/api/v2/torrents/add"):
            self.send_response(type(self).add_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(type(self).add_body)))
            self.end_headers()
            self.wfile.write(type(self).add_body)
            return
        self.send_response(404)
        self.end_headers()


@pytest.fixture
def stub_qbittorrent():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubQBittorrent)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _StubQBittorrent.seen = []
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("status", "body", "expected", "case"),
    [
        (200, b'{"added_torrent_ids":["abc"],"success_count":1}', True, "valid file add"),
        (409, b"Conflict", True, "duplicate add -> already present"),
        (415, b"Error: not a valid torrent file.", False, "corrupt file rejected"),
        (200, b'{"success_count":0,"pending_count":0,"added_torrent_ids":[]}', False, "200 that added nothing"),
    ],
)
def test_upload_path_executes_end_to_end_against_a_stub(
    bridge, stub_qbittorrent, monkeypatch, tmp_path, status, body, expected, case
):
    """EXECUTE the real upload path — login, multipart build, verdict.

    An import-only or predicate-only check would NOT have caught the
    ``NameError: qbittorrent_login`` a linter found in this file: nothing in
    the suite drove ``upload_to_qbittorrent`` far enough to reach line 1 of its
    body. This test does, so that gap is now covered by an executing guard.
    """
    host, port = stub_qbittorrent.server_address
    monkeypatch.setattr(bridge, "QBITTORRENT_HOST", host)
    monkeypatch.setattr(bridge, "QBITTORRENT_PORT", port)

    _StubQBittorrent.add_status = status
    _StubQBittorrent.add_body = body

    torrent = tmp_path / "demo.torrent"
    torrent.write_bytes(b"d8:announce20:http://tracker.test4:infod4:name8:demo.binee")

    result = bridge.WebUIBridgeHandler.upload_to_qbittorrent(
        object(), str(torrent), tags="Boba,Боба", stopped=False
    )

    assert result is expected, case

    # The request really reached the stub, authenticated, with a payload part —
    # i.e. the path executed rather than short-circuiting on an exception.
    paths = [p for p, _ in _StubQBittorrent.seen]
    assert any(p.endswith("/api/v2/auth/login") for p in paths), paths
    add_bodies = [raw for p, raw in _StubQBittorrent.seen if p.endswith("/api/v2/torrents/add")]
    assert add_bodies, paths
    assert b'name="torrents"' in add_bodies[0]
    assert b"d8:announce" in add_bodies[0]


def test_bridge_upload_always_attaches_a_payload_part(bridge):
    """The bridge's half of the same invariant, asserted on the real source.

    ``upload_to_qbittorrent`` reads the ``.torrent`` from disk and always writes
    a ``torrents`` multipart part, so it structurally cannot emit the no-payload
    add that draws the other ``409``.
    """
    import inspect

    src = inspect.getsource(bridge.WebUIBridgeHandler.upload_to_qbittorrent)
    assert 'name="torrents"' in src
    assert "file_data" in src
