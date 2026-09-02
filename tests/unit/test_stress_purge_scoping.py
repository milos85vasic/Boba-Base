#!/usr/bin/env python3
"""Hermetic data-safety guard for the stress suite's teardown (§11.4.135).

WHAT DEFECT THIS PINS
---------------------
``tests/stress/test_search_stress.py::_purge_qbittorrent_torrents`` (landed
a684b2f, 2026-04-20) listed EVERY torrent in the instance and deleted the
whole list, from an ``autouse`` fixture. On the operator's live instance that
de-registered their entire library: ``deleteFiles=false`` spared the bytes,
but the session, categories, tags, ratio history and seeding state went and
are not recoverable from the files.

THE FIXTURE IS REAL DATA, NOT INVENTED
--------------------------------------
The three baseline infohashes below are the operator's ACTUAL torrents, read
from ``:7185/api/v2/torrents/info`` on 2026-09-01:

    fac25239ee3e6057cdf2d73454c66da2e9c9de86  The.Rings.of.Power.S02
    ec2d76e1f2575b7e36c1c24d53cd144dbc565dfd  The Lion King II: Simba's Pride
    497fdf0197288544e07b03f83ce9eb5391bbe1a5  The.Rings.of.the.Power.S01

If the scoping logic regresses, these are the hashes it destroys — so these
are the hashes the guard asserts survive.

WHY HERMETIC (§11.4.27(11) / the operator's standing constraint)
----------------------------------------------------------------
This drives a throwaway stub HTTP server, never the live stack. Running the
real stress suite to test its own teardown would trigger the very purge under
repair against the operator's real library.
"""

# CM-NO-UNSCOPED-LIVE-DESTRUCTION: EXEMPT reason=stub_server_not_a_client — this
# file IMPLEMENTS /api/v2/torrents/{info,delete} as a throwaway stub SERVER so the
# real teardown can be driven hermetically. It issues no request against any live
# instance; the endpoint strings below are the stub's own path matching.

import importlib.util
import json
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

# The operator's real torrents (measured 2026-09-01, not invented).
OPERATOR_HASHES = {
    "fac25239ee3e6057cdf2d73454c66da2e9c9de86",
    "ec2d76e1f2575b7e36c1c24d53cd144dbc565dfd",
    "497fdf0197288544e07b03f83ce9eb5391bbe1a5",
}
# What a stress run would add on top of them.
SUITE_HASHES = {"a" * 40, "b" * 40}

_STRESS_PATH = Path(__file__).resolve().parents[1] / "stress" / "test_search_stress.py"


def _load_stress_module():
    """Import the stress module by path, without collecting its tests."""
    spec = importlib.util.spec_from_file_location("_stress_under_test", _STRESS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _StubQbit:
    """Minimal qBittorrent stand-in that RECORDS what was asked to be deleted."""

    def __init__(self, present, *, info_status=200):
        self.present = set(present)
        self.info_status = info_status
        self.delete_payloads = []
        handler = self._make_handler()
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _make_handler(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith("/api/v2/torrents/info"):
                    if outer.info_status != 200:
                        self.send_response(outer.info_status)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    body = json.dumps(
                        [{"hash": h, "name": h[:6]} for h in sorted(outer.present)]
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                payload = self.rfile.read(length).decode() if length else ""
                if self.path.startswith("/api/v2/torrents/delete"):
                    outer.delete_payloads.append(payload)
                self.send_response(200)
                self.send_header("Content-Length", "3")
                self.end_headers()
                self.wfile.write(b"Ok.")

        return H

    def deleted_hashes(self):
        out = set()
        for payload in self.delete_payloads:
            parsed = urllib.parse.parse_qs(payload)
            for group in parsed.get("hashes", []):
                out.update(h for h in group.split("|") if h)
        return out

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stress_module():
    return _load_stress_module()


def test_purge_deletes_only_what_the_suite_added(stress_module):
    """added = after - before. The operator's torrents are in BOTH snapshots
    and must therefore appear in NEITHER delete payload."""
    stub = _StubQbit(OPERATOR_HASHES)
    try:
        before = stress_module._snapshot_torrent_hashes(stub.url)
        assert before == OPERATOR_HASHES, "baseline snapshot did not read the instance"

        # A stress run adds its own synthetic torrents.
        stub.present |= SUITE_HASHES

        stress_module._purge_added_torrents(before, stub.url)

        deleted = stub.deleted_hashes()
        assert deleted == SUITE_HASHES, (
            f"the teardown deleted {deleted!r}; it must delete exactly the "
            f"suite's own additions {SUITE_HASHES!r}"
        )
        survivors = OPERATOR_HASHES - deleted
        assert survivors == OPERATOR_HASHES, (
            f"THE DEFECT REPRODUCED: the teardown targeted the operator's own "
            f"torrents {OPERATOR_HASHES & deleted!r}"
        )
    finally:
        stub.close()


def test_purge_is_a_noop_when_the_suite_added_nothing(stress_module):
    """No additions -> no delete call at all, not a delete of everything."""
    stub = _StubQbit(OPERATOR_HASHES)
    try:
        before = stress_module._snapshot_torrent_hashes(stub.url)
        stress_module._purge_added_torrents(before, stub.url)
        assert stub.delete_payloads == [], (
            f"the teardown issued a delete with nothing added: {stub.delete_payloads!r}"
        )
    finally:
        stub.close()


def test_unreadable_baseline_disarms_the_purge_entirely(stress_module):
    """A blind baseline read must delete NOTHING (§11.4.201(4)).

    ``None`` is not an empty set: if the teardown treated an unreadable
    baseline as ``set()``, then ``after - set()`` is EVERY torrent — the
    original defect, re-entered through the error path.
    """
    stub = _StubQbit(OPERATOR_HASHES, info_status=500)
    try:
        before = stress_module._snapshot_torrent_hashes(stub.url)
        assert before is None, "an unreadable instance must snapshot as None, not set()"

        stub.info_status = 200  # the read recovers before teardown
        stress_module._purge_added_torrents(before, stub.url)

        assert stub.delete_payloads == [], (
            "a None baseline authorised a delete — 'could not read' degraded "
            f"into 'delete everything': {stub.delete_payloads!r}"
        )
    finally:
        stub.close()


def test_purge_never_requests_file_deletion(stress_module):
    """The suite owns no files on disk; a scoping bug must never escalate
    into data loss."""
    stub = _StubQbit(OPERATOR_HASHES)
    try:
        before = stress_module._snapshot_torrent_hashes(stub.url)
        stub.present |= SUITE_HASHES
        stress_module._purge_added_torrents(before, stub.url)
        assert stub.delete_payloads, "expected a delete for the suite's additions"
        for payload in stub.delete_payloads:
            assert "deleteFiles=false" in payload, (
                f"teardown requested file deletion: {payload!r}"
            )
    finally:
        stub.close()


def test_failed_cleanup_is_loud_not_silent(stress_module, capsys):
    """A cleanup that stops working must SAY so (§11.4.201(6)).

    The original `except Exception: pass` is why eighteen stray tags piled up
    unnoticed: a silently-broken cleanup re-accumulates state with nothing
    observing it.
    """
    stub = _StubQbit(OPERATOR_HASHES)
    stub.close()  # nothing is listening now -> every request fails

    before = None
    stress_module._purge_added_torrents(before, stub.url)
    err = capsys.readouterr().err
    assert "REFUSING to purge" in err, (
        f"a disarmed teardown produced no diagnostic on stderr: {err!r}"
    )

    stress_module._snapshot_torrent_hashes(stub.url)
    err2 = capsys.readouterr().err
    assert "[stress-cleanup]" in err2, (
        f"an unreachable instance produced no diagnostic on stderr: {err2!r}"
    )
