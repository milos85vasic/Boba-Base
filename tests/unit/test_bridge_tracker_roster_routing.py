"""B1-BRIDGE — the bridge routes LITERAL private-tracker URLs through auth.

WHY THIS FILE EXISTS (§11.4.245 oracle independence; §11.4.238 coverage escape)
------------------------------------------------------------------------------
``tests/unit/api_layer/test_tracker_roster_single_source.py`` fixed the roster
duplication and shipped two kinds of guard:

* ``test_dead_alias_url_takes_the_authenticated_path`` — drives the real API
  handler with the LITERAL URL ``https://nnm-club.me/...`` and asserts the
  user-observable outcome. Independent oracle: the domain is written in the
  test, not read from the roster.
* ``test_every_consumer_resolves_the_same_roster`` — **iterates the roster
  itself**. It proves the four consumers AGREE; it can never prove a given
  domain is PRESENT, because deleting an entry also deletes it from the
  assertions. A self-referential oracle (§11.4.245).

MEASURED CONSEQUENCE (2026-09-02). Dropping ``nnm-club.me`` from
``PRIVATE_TRACKER_DOMAINS`` failed the API half (2 failed, ``assert 404 == 200``)
and left the BRIDGE half **fully green — 32 passed**. Half the fork the shared
roster was extracted to end was therefore still blind to a roster deletion: the
bridge is the consumer that would silently stop auth-routing the domain and hand
the private URL to qBittorrent anonymously.

WHAT THIS FILE ADDS
-------------------
1. ``test_literal_private_url_takes_the_authenticated_path`` — the bridge's
   mirror of the API-side routing test. LITERAL URLs, LITERAL plugin names,
   asserted at the SINK: a stub qBittorrent on an ephemeral loopback port sees
   an AUTHENTICATED multipart add of the fetched ``.torrent`` and never the raw
   private URL. Delete a domain from the roster and this goes RED with the API
   half.
2. ``test_non_tracker_url_is_proxied_anonymously`` — the §11.4.201(1)
   false-positive guard. A matcher answering "tracker" for everything would
   satisfy (1) while breaking every ordinary WebUI add.
3. ``test_roster_contains_every_domain_the_fleet_depends_on`` — a
   PRESENCE assertion against a checked-in literal map. Justification is in that
   test's own docstring: (1) covers only the domains a routing test names, so a
   domain nobody routes could still be deleted silently.

HERMETIC: a ``ThreadingHTTPServer`` on ``127.0.0.1:0`` stands in for
qBittorrent (the pattern already used by
``test_qbit_add_shared_predicate.py::test_upload_path_executes_end_to_end_against_a_stub``).
Nothing here touches the operator's live instance, and no torrent is ever added
to it.
"""

import importlib.util
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


# --------------------------------------------------------------------------
# LITERAL fixtures. Every domain and plugin name below is written out here on
# purpose — a test that read them from ``merge_service.trackers`` would delete
# its own assertion along with the roster entry (the §11.4.245 defect this file
# exists to close).
# --------------------------------------------------------------------------

# (url, expected plugin) — the six domains the four-way drift table in
# ``merge_service/trackers.py`` recorded as present in SOME roster and missing
# from another, plus each tracker's primary.
_PRIVATE_URLS = [
    ("https://rutracker.org/forum/dl.php?t=1000001", "rutracker"),
    ("https://rutracker.net/forum/dl.php?t=1000002", "rutracker"),
    ("https://rutracker.nl/forum/dl.php?t=1000003", "rutracker"),
    ("https://kinozal.tv/download.php?id=2000001", "kinozal"),
    ("https://kinozal.me/download.php?id=2000002", "kinozal"),
    ("https://kinozal.guru/download.php?id=2000003", "kinozal"),
    ("https://nnmclub.to/forum/download.php?id=3000001", "nnmclub"),
    ("https://nnmclub.ro/forum/download.php?id=3000002", "nnmclub"),
    # The alias whose absence from the merge-service roster corrupted downloads,
    # and whose deletion this file's whole reason for existing is to catch.
    ("https://nnm-club.me/forum/download.php?id=3000003", "nnmclub"),
    ("https://iptorrents.com/download.php/4000001/x.torrent", "iptorrents"),
    ("https://iptorrents.me/download.php/4000002/x.torrent", "iptorrents"),
    ("https://iptorrents.org/download.php/4000003/x.torrent", "iptorrents"),
]

_TORRENT_BYTES = (
    b"d8:announce20:http://tracker.test"
    b"4:infod6:lengthi12e4:name8:demo.bin"
    b"12:piece lengthi16384e6:pieces20:" + (b"\x00" * 20) + b"ee"
)


def _load_bridge():
    """Import ``webui-bridge.py`` (the hyphen forbids a plain import)."""
    spec = importlib.util.spec_from_file_location(
        "webui_bridge_roster_routing_probe", str(_REPO_ROOT / "webui-bridge.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bridge():
    return _load_bridge()


class _StubQBittorrent(BaseHTTPRequestHandler):
    """Hermetic stand-in for qBittorrent, recording every request it receives.

    This is the SINK the routing decision is observed at: the authenticated
    path arrives as a multipart ``torrents`` add after a login, the anonymous
    proxy path arrives as the bridge's own request forwarded verbatim (with the
    private URL still sitting in the ``urls=`` query string).
    """

    seen: list[tuple[str, str, bytes]] = []  # (method, path, body)

    def log_message(self, *args):  # silence the stub
        pass

    def _record_and_reply(self, body=b""):
        type(self).seen.append((self.command, self.path, body))
        if self.path.endswith("/api/v2/auth/login"):
            self.send_response(204)
            self.send_header("Set-Cookie", "QBT_SID_7185=stub-session; path=/")
            self.end_headers()
            return
        payload = b'{"added_torrent_ids":["abc"],"success_count":1,"pending_count":0}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self._record_and_reply(self.rfile.read(length) if length else b"")

    def do_GET(self):
        self._record_and_reply()


@pytest.fixture
def stub_qbittorrent():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubQBittorrent)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _StubQBittorrent.seen = []
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def bridge_server(bridge, stub_qbittorrent, monkeypatch):
    """The REAL bridge handler, serving on loopback, pointed at the stub."""
    host, port = stub_qbittorrent.server_address
    monkeypatch.setattr(bridge, "QBITTORRENT_HOST", host)
    monkeypatch.setattr(bridge, "QBITTORRENT_PORT", port)

    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.WebUIBridgeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _get(server, path):
    """Issue a real HTTP GET at the bridge and return (status, body)."""
    import http.client

    host, port = server.server_address
    conn = http.client.HTTPConnection(host, port, timeout=15)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def _add_url_path(url):
    """The WebUI 'add by URL' request shape the bridge intercepts."""
    return "/api/v2/torrents/add?" + urllib.parse.urlencode({"urls": url})


@pytest.mark.parametrize(("url", "expected_plugin"), _PRIVATE_URLS)
def test_literal_private_url_takes_the_authenticated_path(
    bridge, bridge_server, stub_qbittorrent, monkeypatch, tmp_path, url, expected_plugin
):
    """A LITERAL private-tracker URL is fetched WITH credentials by the bridge.

    RED when its domain is dropped from the roster: ``identify_plugin`` returns
    ``None``, the bridge falls through to ``proxy_to_qbittorrent``, and the raw
    private URL is handed to qBittorrent to fetch ANONYMOUSLY — the tracker
    answers a login page and the user's ".torrent" is HTML.

    The oracle is the SINK, not the roster: the stub either sees an
    authenticated multipart add of real torrent bytes, or it sees the private
    URL in a ``urls=`` query. Those are mutually exclusive and both are
    asserted.
    """
    torrent = tmp_path / f"{expected_plugin}_probe.torrent"
    torrent.write_bytes(_TORRENT_BYTES)

    calls = []

    def _fake_nova2dl(self, plugin, target_url):
        calls.append((plugin, target_url))
        return str(torrent)

    monkeypatch.setattr(bridge.WebUIBridgeHandler, "download_via_nova2dl", _fake_nova2dl)

    status, body = _get(bridge_server, _add_url_path(url))

    # USER-OBSERVABLE OUTCOME: the bridge reports the add as done itself,
    # having performed the credentialed download.
    assert status == 200, (url, body)
    assert body == b"OK", (url, body)

    # The AUTHENTICATED tracker fetch ran, keyed to the right plugin.
    assert calls == [(expected_plugin, url)], f"{url} was not auth-routed: {calls}"

    methods_paths = [(m, p) for m, p, _ in _StubQBittorrent.seen]
    bodies = [b for _, _, b in _StubQBittorrent.seen]

    # It authenticated, then uploaded the FETCHED BYTES as a multipart payload.
    assert any(p.endswith("/api/v2/auth/login") for _, p in methods_paths), methods_paths
    add_bodies = [b for (_, p, b) in _StubQBittorrent.seen if p.endswith("/api/v2/torrents/add") and b]
    assert add_bodies, methods_paths
    assert b'name="torrents"' in add_bodies[0]
    assert _TORRENT_BYTES in add_bodies[0]

    # ...and the anonymous path was NOT taken: the private URL never reached
    # qBittorrent for it to fetch without credentials.
    assert not any(url in p for _, p in methods_paths), f"private URL leaked anonymously: {methods_paths}"
    assert not any(url.encode() in b for b in bodies), "private URL leaked in a proxied body"


def test_non_tracker_url_is_proxied_anonymously(bridge, bridge_server, stub_qbittorrent, monkeypatch, tmp_path):
    """§11.4.201(1) false-positive guard.

    A matcher that claimed every URL belongs to a tracker would satisfy the
    positive test above while breaking every ordinary WebUI "add by URL". An
    ordinary URL MUST be proxied through to qBittorrent untouched and MUST NOT
    reach the credentialed nova2dl fetch.
    """
    ordinary = "https://example.test/ubuntu-24.04.torrent"

    calls = []

    def _fake_nova2dl(self, plugin, target_url):  # pragma: no cover - must not run
        calls.append((plugin, target_url))
        return None

    monkeypatch.setattr(bridge.WebUIBridgeHandler, "download_via_nova2dl", _fake_nova2dl)

    status, _ = _get(bridge_server, _add_url_path(ordinary))

    assert status == 200
    assert calls == [], "an ordinary URL must never be sent through the tracker-auth path"

    # The proxied request reached qBittorrent with the URL still in the query —
    # this IS the anonymous passthrough.
    paths = [p for _, p, _ in _StubQBittorrent.seen]
    assert any("urls=" in p and "example.test" in urllib.parse.unquote(p) for p in paths), paths
    # ...and no multipart torrent upload happened, because nothing was fetched.
    assert not any(b'name="torrents"' in b for _, _, b in _StubQBittorrent.seen)


def test_roster_contains_every_domain_the_fleet_depends_on():
    """PRESENCE assertion against a checked-in literal map.

    WHY THIS IS NEEDED ON TOP OF THE ROUTING TESTS (the decision the review
    asked for, with its evidence). The routing tests above are the strong
    guard, but their coverage is exactly the set of URLs THIS FILE NAMES. That
    set is complete today — it is every one of the 12 roster entries, checked by
    the count assertion below — but nothing keeps it complete: a domain added to
    the roster tomorrow and deleted next month would be caught by NO routing
    test, because none would name it. A literal expected-map closes that hole
    for O(1) maintenance cost, and it is oracle-independent in the §11.4.245
    sense — it is written here, not read from the module under test.

    EXACT SET EQUALITY, not containment. An ADDITION must also fail this test.
    A new authenticated-tracker domain is a security-relevant change to which
    hosts the fleet will spend credentials on; requiring the author to state it
    here (and to add a routing case above) is the point, not friction.
    """
    from merge_service.trackers import PRIVATE_TRACKER_DOMAINS

    expected = {
        "rutracker": ("rutracker.org", "rutracker.net", "rutracker.nl"),
        "kinozal": ("kinozal.tv", "kinozal.me", "kinozal.guru"),
        "nnmclub": ("nnmclub.to", "nnmclub.ro", "nnm-club.me"),
        "iptorrents": ("iptorrents.com", "iptorrents.me", "iptorrents.org"),
    }

    assert expected == PRIVATE_TRACKER_DOMAINS, (
        "the authenticated-tracker roster changed. If deliberate, update this "
        "literal AND add a routing case to _PRIVATE_URLS above; if not, a "
        "roster entry was lost and private URLs will be fetched anonymously."
    )

    # The PRIMARY (index 0) is what PRIVATE_TRACKER_BASE_URLS derives from, so
    # a reorder is a different defect from a deletion and is pinned separately.
    for name, domains in expected.items():
        assert PRIVATE_TRACKER_DOMAINS[name][0] == domains[0], f"{name} primary changed"

    # Control needle (§11.4.201(7)(b)): every roster entry has a routing case
    # above, so this file's positive coverage is total rather than a sample.
    routed = {url.split("//", 1)[1].split("/", 1)[0] for url, _ in _PRIVATE_URLS}
    assert routed == {d for domains in expected.values() for d in domains}
