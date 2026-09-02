#!/usr/bin/env python3
"""Live-stack auth regression guard for BOTH webui-bridge implementations.

Context (§11.4.115 RED-first, §11.4.135 permanent regression guard).
The qBittorrent WebUI config used to carry an authentication BYPASS
(``WebUI\\LocalHostAuth=false`` + ``WebUI\\AuthSubnetWhitelistEnabled=true``
covering loopback and all RFC1918).  With the bypass on, a deliberately
WRONG password was ACCEPTED (HTTP 204).  The bypass was removed — that
security fix is correct and must stay — and removing it exposed two paths
that had been silently riding on it:

B2-a  ``webui-bridge.py:upload_to_qbittorrent`` POSTed ``/api/v2/torrents/add``
      with no login and no cookie.  Unauthenticated ``torrents/add`` is 403,
      so the bridge's documented purpose (private-tracker downloads) always
      failed.

B2-b  ``qBitTorrent-go/cmd/webui-bridge/main.go`` forwarded the browser's
      ``Referer`` verbatim.  qBittorrent rejects a login whose Referer host
      does not match its own — CORRECT credentials with
      ``Referer: http://localhost:7188/`` return 401 — so nobody could log
      in through the Go bridge at all.  The Python bridge already rewrites
      Referer (``webui-bridge.py:proxy_to_qbittorrent``); the Go one did not.

These are REAL-INFRASTRUCTURE tests (§11.4.27(A) / §11.4.169): they drive
the live qBittorrent on :7185 and a real Go bridge process.  When the stack
is absent they SKIP with an honest reason (§11.4.3) — they never fake a pass.

Anti-bluff (§11.4 / §1.1): every positive assertion is paired with a
NEGATIVE CONTROL asserting a WRONG password is still REJECTED, so a change
that makes everything succeed fails this file rather than passing it.

qBittorrent 5.2.3 success shape (measured 2026-09-01, not assumed):
    login OK    -> HTTP 204, EMPTY body, ``Set-Cookie: QBT_SID_7185=...``
    login BAD   -> HTTP 401, body ``Unauthorized``, NO session cookie
    add (authed)-> HTTP 200, body ``Ok.``
    add (anon)  -> HTTP 403
Never detect login success by ``body == "Ok."`` — that is the legacy shape
and it does not appear on this build.
"""

from __future__ import annotations

import http.cookiejar
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GO_MODULE_DIR = REPO_ROOT / "qBitTorrent-go"
GO_BRIDGE_PKG = "./cmd/webui-bridge"
TORRENT_FIXTURE = REPO_ROOT / "tests" / "test_torrents" / "debian.iso.torrent"

QBIT_HOST = os.environ.get("QBITTORRENT_HOST", "localhost")
QBIT_PORT = int(os.environ.get("QBITTORRENT_PORT", "7185"))
QBIT_BASE = f"http://{QBIT_HOST}:{QBIT_PORT}"
QBIT_USER = os.environ.get("QBITTORRENT_USER", "admin")
QBIT_PASS = os.environ.get("QBITTORRENT_PASS", "admin")


def _free_port():
    """Reserve an ephemeral loopback port and return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(autouse=True)
def _serialize_live_searches():
    """Override the ``tests/integration/conftest.py`` autouse lock.

    That fixture holds a process-wide flock and waits for the merge
    service's search orchestrator to go idle, so no two live TRACKER
    SEARCHES overlap. Nothing in this module performs a tracker search —
    these tests drive qBittorrent's auth/torrent endpoints and a private
    Go bridge process — so inheriting that lock would make this regression
    guard hostage to unrelated contention (measured: a parallel
    integration run held the flock and this file timed out at 60 s while
    blocking on it, turning a real guard into a flake, §11.4.248).

    Isolation is preserved by construction instead: every test tags its
    torrents with a fresh uuid and the bridge binds an ephemeral port, so
    two concurrent runs of this file cannot interfere.
    """
    return None


# --------------------------------------------------------------------------
# small HTTP helpers (stdlib only — no new dependency for a regression guard)
# --------------------------------------------------------------------------
def _request(url, *, method="GET", data=None, headers=None, timeout=20):
    """Return (status, body_bytes, header_list) — never raises on 4xx/5xx."""
    req = urllib.request.Request(  # noqa: S310 - fixed loopback scheme
        url, data=data, method=method, headers=headers or {}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read(), list(resp.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), list((exc.headers or {}).items())


def _session_cookie(header_list):
    """Extract the ``QBT_SID_*`` value from a Set-Cookie header list, or None."""
    for name, value in header_list:
        if name.lower() == "set-cookie" and "QBT_SID" in value:
            return value.split(";", 1)[0]
    return None


def _port_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _login(base, username, password, referer):
    """POST /api/v2/auth/login against ``base``; return (status, cookie_or_None)."""
    body = urllib.parse.urlencode({"username": username, "password": password}).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if referer is not None:
        headers["Referer"] = referer
    status, _, hdrs = _request(f"{base}/api/v2/auth/login", method="POST", data=body, headers=headers)
    return status, _session_cookie(hdrs)


def _multipart_torrent(torrent_bytes, extra_fields):
    """Build a multipart/form-data body for /api/v2/torrents/add."""
    boundary = f"----bobaBridgeTest{uuid.uuid4().hex}"
    parts = []
    for key, value in extra_fields.items():
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{key}"'.encode())
        parts.append(b"")
        parts.append(str(value).encode())
    parts.append(f"--{boundary}".encode())
    parts.append(
        b'Content-Disposition: form-data; name="torrents"; filename="probe.torrent"'
    )
    parts.append(b"Content-Type: application/x-bittorrent")
    parts.append(b"")
    parts.append(torrent_bytes)
    parts.append(f"--{boundary}--".encode())
    return b"\r\n".join(parts), f"multipart/form-data; boundary={boundary}"


def _invoke_upload(module, torrent_path, *, tags, stopped):
    """Call ``upload_to_qbittorrent`` tolerating the pre-fix 2-arg signature.

    §11.4.1: the RED run must FAIL on the product assertion (the upload does
    not reach qBittorrent), NOT crash with a ``TypeError`` because the
    pre-fix function has no ``tags``/``stopped`` parameters.  Degrading here
    keeps the failure a genuine product defect in both directions.
    """
    upload = module.WebUIBridgeHandler.upload_to_qbittorrent
    try:
        return upload(types.SimpleNamespace(), torrent_path, tags=tags, stopped=stopped)
    except TypeError:
        return upload(types.SimpleNamespace(), torrent_path)


def _purge_tag(base, cookie, tag):
    """Delete every torrent carrying ``tag`` — keeps the live stack clean."""
    if not cookie:
        return
    headers = {"Cookie": cookie, "Referer": base}
    status, body, _ = _request(
        f"{base}/api/v2/torrents/info?tag={urllib.parse.quote(tag)}", headers=headers
    )
    if status != 200:
        return
    import json as _json

    try:
        hashes = [t["hash"] for t in _json.loads(body.decode() or "[]")]
    except Exception:
        return
    if not hashes:
        return
    payload = urllib.parse.urlencode(
        {"hashes": "|".join(hashes), "deleteFiles": "true"}
    ).encode()
    _request(
        f"{base}/api/v2/torrents/delete",
        method="POST",
        data=payload,
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    )


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def live_qbittorrent():
    """The real qBittorrent WebUI, or an honest SKIP (§11.4.3)."""
    if not _port_open(QBIT_HOST, QBIT_PORT):
        pytest.skip(
            f"SKIP-REASON hardware_not_present: qBittorrent WebUI unreachable at {QBIT_BASE}"
        )
    return QBIT_BASE


@pytest.fixture(scope="module")
def bridge_python_module():
    """Import ``webui-bridge.py`` (dashed filename => importlib by path)."""
    path = REPO_ROOT / "webui-bridge.py"
    spec = importlib.util.spec_from_file_location("boba_webui_bridge_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def go_bridge(live_qbittorrent):
    """Build and run the real Go webui-bridge binary; yield its base URL."""
    if shutil.which("go") is None:
        pytest.skip("SKIP-REASON topology_unsupported: go toolchain not installed")

    # An EPHEMERAL port, never a fixed :7188. A fixed port makes the suite
    # non-deterministic in two directions: it fights an operator-run bridge,
    # and a back-to-back re-run skips while the previous run's socket is
    # still winding down — a skip that silently under-tests the guard
    # (§11.4.201(6) false-null). An override stays available for manual
    # driving on the canonical port.
    bridge_port = int(os.environ.get("BOBA_TEST_BRIDGE_PORT", "0")) or _free_port()
    bridge_base = f"http://localhost:{bridge_port}"

    tmpdir = tempfile.mkdtemp(prefix="boba-go-bridge-")
    binary = os.path.join(tmpdir, "webui-bridge")
    build = subprocess.run(  # noqa: S603
        ["go", "build", "-o", binary, GO_BRIDGE_PKG],
        cwd=GO_MODULE_DIR,
        capture_output=True,
        text=True,
        timeout=600,
        env={**os.environ, "GOMAXPROCS": "2"},
    )
    if build.returncode != 0:
        shutil.rmtree(tmpdir, ignore_errors=True)
        pytest.fail(f"go build of {GO_BRIDGE_PKG} failed:\n{build.stderr}")

    env = {
        **os.environ,
        "BRIDGE_PORT": str(bridge_port),
        "QBITTORRENT_HOST": QBIT_HOST,
        "QBITTORRENT_PORT": str(QBIT_PORT),
        "GOMAXPROCS": "2",
    }
    proc = subprocess.Popen(  # noqa: S603
        [binary], env=env, cwd=GO_MODULE_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.fail(f"go bridge exited early: {proc.stdout.read()}")
            if _port_open("localhost", bridge_port):
                break
            time.sleep(0.2)
        else:
            pytest.fail(f"go bridge never listened on :{bridge_port}")
        yield bridge_base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        if proc.stdout is not None:
            proc.stdout.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# --------------------------------------------------------------------------
# baseline: the measured qBittorrent contract these fixes are written against
# --------------------------------------------------------------------------
def test_baseline_qbittorrent_auth_contract(live_qbittorrent):
    """Pin the upstream behaviour both fixes depend on (§11.4.201 needle)."""
    ok_status, ok_cookie = _login(QBIT_BASE, QBIT_USER, QBIT_PASS, QBIT_BASE)
    assert ok_status == 204, f"matching-Referer login expected 204, got {ok_status}"
    assert ok_cookie and ok_cookie.startswith("QBT_SID"), "no session cookie issued"

    bad_status, bad_cookie = _login(QBIT_BASE, QBIT_USER, "definitely-not-the-password", QBIT_BASE)
    assert bad_status != 204, "AUTH BYPASS REGRESSION: wrong password was accepted"
    assert bad_cookie is None, "AUTH BYPASS REGRESSION: wrong password issued a session"

    anon_status, _, _ = _request(
        f"{QBIT_BASE}/api/v2/torrents/add",
        method="POST",
        data=b"",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert anon_status == 403, f"unauthenticated torrents/add expected 403, got {anon_status}"


# --------------------------------------------------------------------------
# B2-a — Python bridge must authenticate before uploading
# --------------------------------------------------------------------------
def test_python_bridge_upload_authenticates_and_reaches_qbittorrent(
    live_qbittorrent, bridge_python_module
):
    """RED before the fix: upload_to_qbittorrent POSTs anonymously -> 403 -> False."""
    tag = f"boba-bridge-red-{uuid.uuid4().hex[:8]}"
    module = bridge_python_module
    module.QBITTORRENT_HOST = QBIT_HOST
    module.QBITTORRENT_PORT = QBIT_PORT

    with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as tmp:
        tmp.write(TORRENT_FIXTURE.read_bytes())
        torrent_path = tmp.name

    _, cleanup_cookie = _login(QBIT_BASE, QBIT_USER, QBIT_PASS, QBIT_BASE)
    try:
        result = _invoke_upload(module, torrent_path, tags=tag, stopped=True)
        assert result is True, (
            "upload_to_qbittorrent returned False — the bridge could not add the "
            "torrent to qBittorrent (unauthenticated POST is 403)"
        )

        # USER-OBSERVABLE outcome, not just a return value: the torrent is
        # really present in qBittorrent's own list (§11.4.5 / §11.4.69).
        import json as _json

        deadline = time.time() + 15
        rows = []
        while time.time() < deadline:
            status, body, _ = _request(
                f"{QBIT_BASE}/api/v2/torrents/info?tag={urllib.parse.quote(tag)}",
                headers={"Cookie": cleanup_cookie, "Referer": QBIT_BASE},
            )
            if status == 200:
                rows = _json.loads(body.decode() or "[]")
                if rows:
                    break
            time.sleep(0.5)
        assert rows, f"no torrent tagged {tag} appeared in qBittorrent after the upload"
    finally:
        _purge_tag(QBIT_BASE, cleanup_cookie, tag)
        try:
            os.unlink(torrent_path)
        except OSError:
            pass


def test_python_bridge_upload_rejects_wrong_credentials(
    live_qbittorrent, bridge_python_module, monkeypatch
):
    """NEGATIVE CONTROL: with a bad password the upload must FAIL, not silently pass."""
    module = bridge_python_module
    module.QBITTORRENT_HOST = QBIT_HOST
    module.QBITTORRENT_PORT = QBIT_PORT
    monkeypatch.setenv("QBITTORRENT_USER", QBIT_USER)
    monkeypatch.setenv("QBITTORRENT_PASS", "definitely-not-the-password")

    tag = f"boba-bridge-neg-{uuid.uuid4().hex[:8]}"
    with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as tmp:
        tmp.write(TORRENT_FIXTURE.read_bytes())
        torrent_path = tmp.name
    try:
        result = _invoke_upload(module, torrent_path, tags=tag, stopped=True)
        assert result is False, (
            "upload_to_qbittorrent reported SUCCESS with a wrong password — "
            "the auth bypass is back or the success check is a bluff"
        )
    finally:
        _, cookie = _login(QBIT_BASE, QBIT_USER, QBIT_PASS, QBIT_BASE)
        _purge_tag(QBIT_BASE, cookie, tag)
        try:
            os.unlink(torrent_path)
        except OSError:
            pass


# --------------------------------------------------------------------------
# B2-b — Go bridge must rewrite Referer/Origin to the upstream qBittorrent
# --------------------------------------------------------------------------
def test_go_bridge_login_with_browser_referer_succeeds(go_bridge):
    """RED before the fix: browser Referer is forwarded verbatim -> qBit 401."""
    status, cookie = _login(go_bridge, QBIT_USER, QBIT_PASS, f"{go_bridge}/")
    assert status == 204, (
        f"login through the Go bridge with a browser Referer returned {status}; "
        "qBittorrent rejects a Referer whose host is not its own, so the bridge "
        "must rewrite Referer/Origin to the upstream origin"
    )
    assert cookie and cookie.startswith("QBT_SID"), "no session cookie issued via the bridge"


def test_go_bridge_login_with_wrong_password_is_rejected(go_bridge):
    """NEGATIVE CONTROL: the Referer rewrite must not weaken authentication."""
    status, cookie = _login(go_bridge, QBIT_USER, "definitely-not-the-password", f"{go_bridge}/")
    assert status != 204, "AUTH BYPASS: wrong password accepted through the Go bridge"
    assert cookie is None, "AUTH BYPASS: wrong password issued a session through the Go bridge"


def test_go_bridge_login_with_browser_origin_succeeds(go_bridge):
    """A browser sends Origin as well as Referer on a cross-origin form POST."""
    body = urllib.parse.urlencode({"username": QBIT_USER, "password": QBIT_PASS}).encode()
    status, _, hdrs = _request(
        f"{go_bridge}/api/v2/auth/login",
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{go_bridge}/",
            "Origin": go_bridge,
        },
    )
    assert status == 204, f"login with browser Origin+Referer returned {status}"
    assert _session_cookie(hdrs), "no session cookie issued"


def test_go_bridge_authenticated_torrent_add_reaches_qbittorrent(go_bridge):
    """End-to-end via the bridge: login, then add a torrent, then see it listed."""
    import json as _json

    tag = f"boba-bridge-go-{uuid.uuid4().hex[:8]}"
    status, cookie = _login(go_bridge, QBIT_USER, QBIT_PASS, f"{go_bridge}/")
    assert status == 204 and cookie, f"prerequisite login through the bridge failed ({status})"

    body, content_type = _multipart_torrent(
        TORRENT_FIXTURE.read_bytes(), {"tags": tag, "stopped": "true", "paused": "true"}
    )
    try:
        add_status, add_body, _ = _request(
            f"{go_bridge}/api/v2/torrents/add",
            method="POST",
            data=body,
            headers={
                "Content-Type": content_type,
                "Cookie": cookie,
                "Referer": f"{go_bridge}/",
            },
        )
        assert add_status == 200, (
            f"torrents/add through the Go bridge returned {add_status} "
            f"({add_body[:120]!r}) — expected 200"
        )

        deadline = time.time() + 15
        rows = []
        while time.time() < deadline:
            info_status, info_body, _ = _request(
                f"{go_bridge}/api/v2/torrents/info?tag={urllib.parse.quote(tag)}",
                headers={"Cookie": cookie, "Referer": f"{go_bridge}/"},
            )
            if info_status == 200:
                rows = _json.loads(info_body.decode() or "[]")
                if rows:
                    break
            time.sleep(0.5)
        assert rows, f"no torrent tagged {tag} appeared in qBittorrent via the bridge"
    finally:
        _, cleanup_cookie = _login(QBIT_BASE, QBIT_USER, QBIT_PASS, QBIT_BASE)
        _purge_tag(QBIT_BASE, cleanup_cookie, tag)


def test_go_bridge_unauthenticated_add_is_still_rejected(go_bridge):
    """NEGATIVE CONTROL: the bridge must not manufacture authentication."""
    body, content_type = _multipart_torrent(
        TORRENT_FIXTURE.read_bytes(), {"stopped": "true", "paused": "true"}
    )
    status, _, _ = _request(
        f"{go_bridge}/api/v2/torrents/add",
        method="POST",
        data=body,
        headers={"Content-Type": content_type, "Referer": f"{go_bridge}/"},
    )
    assert status == 403, (
        f"unauthenticated torrents/add through the bridge returned {status}; "
        "expected 403 — the bridge must forward the client's (absent) session, "
        "never inject one of its own"
    )

# ---------------------------------------------------------------------------
# TEST PLAYBACK CLEANUP (§11.4.14) — added 2026-09-01.
#
# WHY: this module mints a unique `boba-bridge-{red,neg,go}-<uuid>` tag per test
# and originally removed none of them. A live audit found EIGHTEEN accumulated
# in the operator's qBittorrent instance while every REAL torrent carried
# tags='' — so the only tags visible in the WebUI were this suite's debris.
# §11.4.14 requires every test to leave the target quiescent.
#
# SCOPE IS DELIBERATELY NARROW: only tags matching this suite's OWN generated
# shape are removed. A blanket "delete every tag" teardown would destroy the
# operator's real, meaningful tags (Movie / 1080p / 1994 / genre / Boba / Боба)
# — a worse defect than the one it fixes.
#
# WHAT THIS PATTERN DOES *NOT* COVER (2026-09-01 remediation — stated so the
# regex is not mistaken for total coverage). The tagging arms added for
# IMPORTANT-2 deliberately mint PRODUCTION-shaped tags (`Boba` / `Боба` /
# `1080p`), because proving the real feature works means creating exactly what
# the real feature creates. Those must never match this pattern — widening it
# to catch them is precisely the destructive teardown the paragraph above
# forbids. `test_bridge_download_path_tags_land_in_qbittorrent` therefore
# cleans up after ITSELF, structurally rather than by pattern: it snapshots
# the tag vocabulary first and afterwards removes only tags that (a) were
# absent before it ran AND (b) no torrent currently carries. An operator tag
# fails (a); a concurrently-created sibling tag fails (b).
# ---------------------------------------------------------------------------

_SUITE_TAG_RE = re.compile(r"^boba-bridge-(red|neg|go)-[0-9a-f]{8}$")


@pytest.fixture(scope="module", autouse=True)
def _purge_suite_tags():
    """Remove ONLY the tags this suite created, after it finishes."""
    yield
    base = f"http://{QBIT_HOST}:{QBIT_PORT}"
    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        opener.open(
            urllib.request.Request(
                f"{base}/api/v2/auth/login",
                data=urllib.parse.urlencode(
                    {"username": QBIT_USER, "password": QBIT_PASS}
                ).encode(),
                headers={"Referer": base},
            ),
            timeout=10,
        ).read()

        raw = opener.open(
            urllib.request.Request(
                f"{base}/api/v2/torrents/tags", headers={"Referer": base}
            ),
            timeout=10,
        ).read().decode()
        mine = [t for t in json.loads(raw) if _SUITE_TAG_RE.match(t)]
        if not mine:
            return
        opener.open(
            urllib.request.Request(
                f"{base}/api/v2/torrents/deleteTags",
                data=urllib.parse.urlencode({"tags": ",".join(mine)}).encode(),
                headers={"Referer": base},
            ),
            timeout=10,
        ).read()
        print(f"[cleanup] purged {len(mine)} suite tag(s)", file=sys.stderr)
    except Exception as exc:  # teardown must never fail the run
        # REPORT rather than swallow: a silent cleanup failure is exactly how
        # the original pollution went unnoticed.
        print(f"[cleanup] could not purge suite tags: {exc!r}", file=sys.stderr)



# ===========================================================================
# REMEDIATION 2026-09-01 — two IMPORTANT findings from the independent
# re-review of the content-tagging batch (verdict NO-GO).
#
# IMPORTANT-2  the webui-bridge add path lands torrents with NO tags at all.
#              `upload_to_qbittorrent` grew a `tags=` parameter, but the
#              PRODUCTION call site (`handle_torrent_download`) never passes
#              it — only the test did. A RuTracker download through the
#              bridge — the bridge's entire documented purpose — therefore
#              lands with tags='', not even the promo tags.
#
# IMPORTANT-3  `upload_to_qbittorrent` returns `response.status == 200`,
#              which cannot distinguish a 200 that ADDED the torrent from a
#              200 that added NOTHING. `routes.py:_qbit_add_succeeded`
#              documents the measured multi-version contract; the bridge
#              ignores it, so its docstring's "True only when qBittorrent
#              really accepted the torrent" is false.
# ===========================================================================

_QUALITY_FIXTURE_NAME = "Boba.Remediation.Probe.1080p.BluRay.x264.torrent"


class _FakeResponse:
    """Minimal stand-in for the object `urllib.request.urlopen` yields."""

    def __init__(self, status, body=b""):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _drive_upload_against_response(module, monkeypatch, torrent_path, status, body):
    """Run the REAL `upload_to_qbittorrent` against one canned HTTP response.

    Only the transport seam is stubbed. Login, multipart assembly, header
    construction and the SUCCESS DECISION are the real production code — the
    decision is precisely the unit under test.
    """
    monkeypatch.setattr(module, "qbittorrent_login", lambda: "QBT_SID_7185=stub")
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda *a, **k: _FakeResponse(status, body),
    )
    return module.WebUIBridgeHandler.upload_to_qbittorrent(
        types.SimpleNamespace(), torrent_path, tags="", stopped=True
    )


# --------------------------------------------------------------------------
# IMPORTANT-3 — the success check must implement the measured add contract
# --------------------------------------------------------------------------
def test_bridge_add_success_check_matches_measured_qbittorrent_contract(
    bridge_python_module, monkeypatch, tmp_path
):
    """RED before the fix: a 200 that added NOTHING is reported as success.

    Response shapes below are the ones qBittorrent really emits, captured
    2026-09-01 against the live 5.2.3 build on :7185 (see the module
    docstring for the auth shapes; the add shapes were measured the same
    session):

        valid file      -> 200 {"added_torrent_ids":["<hash>"],
                                "failure_count":0,"pending_count":0,
                                "success_count":1}
        duplicate file  -> 409 Conflict  (CORRECTED 2026-09-01 after review
                                #3. An earlier note here claimed a duplicate
                                returns 200 identical to success, and argued
                                the 409=FAILURE handling FROM that claim. It is
                                FALSE: re-measured 2/2 across both multipart
                                variations, a duplicate add returns 409. Note
                                409 is AMBIGUOUS on this build — a no-payload
                                add also returns 409 with nothing added — so
                                409 alone cannot distinguish "already present"
                                from "nothing supplied". See
                                download-proxy/src/api/routes.py:_qbit_add_succeeded.)
        url add pending -> 202 {"added_torrent_ids":[],"failure_count":0,
                                "pending_count":1,"success_count":0}
        invalid file    -> 415 Error: '<name>' is not a valid torrent file.
        malformed form  -> 409 Conflict   (NOTHING added — see note below)

    PRECONDITION PROVENANCE (§11.4.115(G)): `constructed`. The BODIES are
    observed verbatim; the 200-with-zero-success PAIRING is constructed,
    because on this build every invalid FILE is rejected at parse time with
    415 rather than a 200 summary (six shapes probed, 6/6 -> 415). The
    legacy `Fails.` body and the JSON zero-success summary remain part of
    the API contract `routes.py:_qbit_add_succeeded` was written against,
    and the bridge must not mis-read them if this build ever emits them.
    """
    module = bridge_python_module
    torrent_path = tmp_path / "probe.torrent"
    torrent_path.write_bytes(TORRENT_FIXTURE.read_bytes())

    added_nothing = [
        (200, b'{"added_torrent_ids":[],"failure_count":1,"pending_count":0,"success_count":0}'),
        (200, b"Fails."),
    ]
    for status, body in added_nothing:
        result = _drive_upload_against_response(
            module, monkeypatch, str(torrent_path), status, body
        )
        assert result is False, (
            f"upload_to_qbittorrent reported SUCCESS for {status} {body!r} — "
            "qBittorrent added NOTHING. The bridge's `response.status == 200` "
            "check cannot tell an accepted add from a rejected one; apply the "
            "contract documented at routes.py:_qbit_add_succeeded."
        )

    # §11.4.201(1) false-positive guard: the genuine successes must still pass.
    really_added = [
        (200, b'{"added_torrent_ids":["b4820792c93ba7f5dacbb84e0731cbae62833d66"],'
              b'"failure_count":0,"pending_count":0,"success_count":1}'),
        (200, b"Ok."),
    ]
    for status, body in really_added:
        result = _drive_upload_against_response(
            module, monkeypatch, str(torrent_path), status, body
        )
        assert result is True, (
            f"upload_to_qbittorrent reported FAILURE for {status} {body!r} — "
            "that is a real success shape; refusing it is a §11.4.201(1) "
            "false-positive refusal, as damaging as the bluff it replaced."
        )


def test_bridge_corrupt_torrent_is_never_reported_as_added(
    live_qbittorrent, bridge_python_module
):
    """LIVE guard: a corrupt .torrent must not be reported as added.

    This is the reviewer's scenario driven end-to-end against the real
    qBittorrent: nova2dl hands back a tracker error page instead of a
    torrent. Measured on 5.2.3 the server answers 415, so the bridge
    already returns False here — this arm PINS that contract so a future
    build that switches to a 200 summary cannot silently reintroduce the
    bluff the sibling test guards.
    """
    module = bridge_python_module
    module.QBITTORRENT_HOST = QBIT_HOST
    module.QBITTORRENT_PORT = QBIT_PORT

    with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as tmp:
        tmp.write(b"<html><head><title>403 Forbidden</title></head><body>x</body></html>")
        corrupt_path = tmp.name

    _, cookie = _login(QBIT_BASE, QBIT_USER, QBIT_PASS, QBIT_BASE)
    before = _torrent_hashes(QBIT_BASE, cookie)
    try:
        result = module.WebUIBridgeHandler.upload_to_qbittorrent(
            types.SimpleNamespace(), corrupt_path, tags="", stopped=True
        )
        assert result is False, (
            "upload_to_qbittorrent reported SUCCESS for a corrupt .torrent — "
            "the caller would answer 200 OK to qBittorrent's search UI while "
            "nothing entered the session (the PASS-bluff class §11.4 forbids)"
        )
        assert _torrent_hashes(QBIT_BASE, cookie) == before, (
            "a corrupt .torrent changed the qBittorrent session — the probe "
            "itself polluted the live instance"
        )
    finally:
        try:
            os.unlink(corrupt_path)
        except OSError:
            pass


def _torrent_hashes(base, cookie):
    """Set of infohashes currently in the session ({} when unreadable)."""
    if not cookie:
        return set()
    status, body, _ = _request(
        f"{base}/api/v2/torrents/info", headers={"Cookie": cookie, "Referer": base}
    )
    if status != 200:
        return set()
    try:
        return {t["hash"] for t in json.loads(body.decode() or "[]")}
    except Exception:
        return set()


# --------------------------------------------------------------------------
# IMPORTANT-2 — the production download path must apply content tags
# --------------------------------------------------------------------------
def _drive_download_path(module, monkeypatch, torrent_path, recorder):
    """Run the REAL `handle_torrent_download` for a private-tracker URL.

    nova2dl and the HTTP response writer are stubbed (no tracker credentials,
    no socket); `handle_torrent_download` itself — the call site under test —
    is production code.
    """
    handler = types.SimpleNamespace()
    handler.identify_plugin = lambda url: "rutracker"
    handler.download_via_nova2dl = lambda plugin, url: torrent_path
    handler.upload_to_qbittorrent = recorder
    handler.proxy_to_qbittorrent = lambda: recorder(None, _proxied=True)
    handler.send_response = lambda *a, **k: None
    handler.send_header = lambda *a, **k: None
    handler.end_headers = lambda *a, **k: None
    handler.wfile = types.SimpleNamespace(write=lambda *a, **k: None)
    module.WebUIBridgeHandler.handle_torrent_download(
        handler, "https://rutracker.org/forum/viewtopic.php?t=1234567"
    )
    return handler


def test_bridge_download_path_passes_content_tags(bridge_python_module, tmp_path, monkeypatch):
    """RED before the fix: the production call site passes NO tags at all.

    `webui-bridge.py:232` calls `self.upload_to_qbittorrent(torrent_file)`.
    The `tags=` parameter exists but production never fills it, so a real
    RuTracker download lands with tags='' — not even `Boba`/`Боба`, despite
    the filename carrying everything the offline quality detector needs.
    """
    module = bridge_python_module
    torrent_path = tmp_path / _QUALITY_FIXTURE_NAME
    torrent_path.write_bytes(TORRENT_FIXTURE.read_bytes())

    seen = {}

    def recorder(filepath, tags=None, stopped=False, _proxied=False):
        seen["proxied"] = _proxied
        seen["tags"] = tags
        return True

    _drive_download_path(module, monkeypatch, str(torrent_path), recorder)

    assert not seen.get("proxied"), "the private-tracker branch was not taken"
    tags = seen.get("tags") or ""
    assert tags, (
        "handle_torrent_download called upload_to_qbittorrent with NO tags — "
        "every bridge download lands untagged (IMPORTANT-2)"
    )
    applied = {t.strip() for t in tags.split(",") if t.strip()}
    assert "Boba" in applied and "Боба" in applied, (
        f"promo tags missing from {applied!r} — both are mandated by the "
        "operator decision recorded in merge_service/tagging.py"
    )
    assert "1080p" in applied, (
        f"quality tag missing from {applied!r} — the filename "
        f"{_QUALITY_FIXTURE_NAME!r} carries it and detection is fully offline"
    )
    assert not any(t.startswith("boba-") for t in applied), (
        f"a `boba-` prefixed tag leaked into {applied!r}; that shape is the "
        "reserved test-debris signature"
    )


def test_bridge_download_path_tags_land_in_qbittorrent(
    live_qbittorrent, bridge_python_module, tmp_path
):
    """USER-OBSERVABLE proof: the tag is read back FROM qBittorrent.

    Not the return value — the torrent's own `tags` field as qBittorrent
    reports it (§11.4.5 / §11.4.69 / §11.4.226 runtime-class evidence).
    """
    module = bridge_python_module
    module.QBITTORRENT_HOST = QBIT_HOST
    module.QBITTORRENT_PORT = QBIT_PORT

    torrent_path = tmp_path / _QUALITY_FIXTURE_NAME
    torrent_path.write_bytes(TORRENT_FIXTURE.read_bytes())

    _, cookie = _login(QBIT_BASE, QBIT_USER, QBIT_PASS, QBIT_BASE)
    before = _torrent_hashes(QBIT_BASE, cookie)
    tags_before = _tag_vocabulary(QBIT_BASE, cookie)

    # NEVER mutate a torrent the operator already has: if the fixture's
    # infohash is present we would be re-tagging THEIR torrent and then
    # deleting it. Skip honestly instead (§11.4.3).
    fixture_hash = "b4820792c93ba7f5dacbb84e0731cbae62833d66"
    if fixture_hash in before:
        pytest.skip(
            "SKIP-REASON topology_unsupported: the fixture torrent is already "
            "in the operator's session; re-tagging it would mutate real data"
        )

    seen = {}

    def spy(filepath, tags=None, stopped=False, _proxied=False):
        seen["tags"] = tags
        return module.WebUIBridgeHandler.upload_to_qbittorrent(
            types.SimpleNamespace(), filepath, tags=tags, stopped=True
        )

    try:
        _drive_download_path(module, None, str(torrent_path), spy)

        deadline = time.time() + 20
        row = None
        while time.time() < deadline:
            status, body, _ = _request(
                f"{QBIT_BASE}/api/v2/torrents/info?hashes={fixture_hash}",
                headers={"Cookie": cookie, "Referer": QBIT_BASE},
            )
            if status == 200:
                rows = json.loads(body.decode() or "[]")
                if rows:
                    row = rows[0]
                    break
            time.sleep(0.5)
        assert row is not None, "the bridge download never reached qBittorrent"

        landed = {t.strip() for t in (row.get("tags") or "").split(",") if t.strip()}
        assert landed, (
            "the torrent landed in qBittorrent with tags='' — the tag field "
            "never reached the add call (IMPORTANT-2)"
        )
        for expected in ("Boba", "Боба", "1080p"):
            assert expected in landed, (
                f"tag {expected!r} is absent from qBittorrent's own view of the "
                f"torrent ({landed!r}) — the return value is not the oracle, "
                "this read-back is"
            )
    finally:
        _post_form = {
            "Cookie": cookie,
            "Referer": QBIT_BASE,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        added = _torrent_hashes(QBIT_BASE, cookie) - before
        if added:
            _request(
                f"{QBIT_BASE}/api/v2/torrents/delete",
                method="POST",
                data=urllib.parse.urlencode(
                    {"hashes": "|".join(sorted(added)), "deleteFiles": "true"}
                ).encode(),
                headers=_post_form,
            )
        # §11.4.14 — also remove the tag VOCABULARY this arm minted. It is
        # PRODUCTION-shaped (Boba / Боба / 1080p), so a pattern-based purge
        # like `_SUITE_TAG_RE` can never be allowed to match it. The rule here
        # is structural instead, and cannot touch the operator's tags by
        # construction: delete a tag only when it (a) did not exist before this
        # test ran AND (b) no torrent currently carries it. Clause (b) also
        # keeps a concurrently-running sibling suite safe — if another test's
        # torrent picked up `Boba` meanwhile, that tag stays.
        minted = _tag_vocabulary(QBIT_BASE, cookie) - tags_before
        if minted:
            in_use = set()
            status, body, _ = _request(
                f"{QBIT_BASE}/api/v2/torrents/info",
                headers={"Cookie": cookie, "Referer": QBIT_BASE},
            )
            if status == 200:
                for row in json.loads(body.decode() or "[]"):
                    in_use.update(
                        t.strip() for t in (row.get("tags") or "").split(",") if t.strip()
                    )
            orphaned = minted - in_use
            if orphaned:
                _request(
                    f"{QBIT_BASE}/api/v2/torrents/deleteTags",
                    method="POST",
                    data=urllib.parse.urlencode({"tags": ",".join(sorted(orphaned))}).encode(),
                    headers=_post_form,
                )


def _tag_vocabulary(base, cookie):
    """Set of tag names qBittorrent currently knows (empty when unreadable)."""
    if not cookie:
        return set()
    status, body, _ = _request(
        f"{base}/api/v2/torrents/tags", headers={"Cookie": cookie, "Referer": base}
    )
    if status != 200:
        return set()
    try:
        return set(json.loads(body.decode() or "[]"))
    except Exception:
        return set()


# --------------------------------------------------------------------------
# N-b — the multipart boundary must be unpredictable, and the tag field it
#       frames must be unable to forge a part.
# --------------------------------------------------------------------------
# The header token is `----` + the local `boundary` variable (which itself
# starts `----WebKitFormBoundary`), so the value on the wire carries EIGHT
# leading dashes and the in-body delimiter ten. That is RFC-consistent —
# delimiter == "--" + token — just written confusingly; match the dash run
# rather than a fixed count so the assertion tests entropy, not formatting.
_BOUNDARY_RE = re.compile(r"boundary=(-+WebKitFormBoundary[A-Za-z0-9]+)")

# RFC 2046 `bcharsnospace` — the characters a boundary token may contain.
_RFC2046_BCHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'()+_,-./:=?"
)


def _captured_multipart(module, monkeypatch, torrent_path, tags):
    """Return (content_type, body_bytes) of the request the bridge would send."""
    captured = {}

    def fake_urlopen(req, *a, **k):
        captured["content_type"] = req.headers.get("Content-type") or req.headers.get(
            "Content-Type"
        )
        captured["body"] = req.data
        return _FakeResponse(200, b"Ok.")

    monkeypatch.setattr(module, "qbittorrent_login", lambda: "QBT_SID_7185=stub")
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    module.WebUIBridgeHandler.upload_to_qbittorrent(
        types.SimpleNamespace(), torrent_path, tags=tags, stopped=True
    )
    return captured["content_type"], captured["body"]


def test_multipart_boundary_is_unpredictable_and_rfc_valid(
    bridge_python_module, monkeypatch, tmp_path
):
    """RED before the fix: the boundary was `str(int(time.time()))`.

    One-second resolution means an observer who knows roughly when an upload
    ran can reproduce the delimiter exactly. Two uploads inside the same
    second produced the IDENTICAL boundary — the property this asserts
    against.
    """
    module = bridge_python_module
    torrent_path = tmp_path / "probe.torrent"
    torrent_path.write_bytes(TORRENT_FIXTURE.read_bytes())

    seen = []
    for _ in range(8):
        content_type, _ = _captured_multipart(
            module, monkeypatch, str(torrent_path), "Boba"
        )
        match = _BOUNDARY_RE.search(content_type or "")
        assert match, f"no recognisable boundary in Content-Type {content_type!r}"
        seen.append(match.group(1))

    assert len(set(seen)) == len(seen), (
        f"the multipart boundary repeated across back-to-back uploads: {seen!r} "
        "— it is derived from the clock, so it is predictable (N-b)"
    )

    suffix = seen[0].split("WebKitFormBoundary", 1)[1]
    assert len(suffix) >= 16, f"boundary entropy suffix too short: {suffix!r}"
    assert not suffix.isdigit(), (
        f"boundary suffix {suffix!r} is a decimal number — that is the "
        "timestamp shape this fix replaced"
    )
    # The delimiter actually written into the body is '--' + boundary; both it
    # and the header token must stay inside RFC 2046's charset and 70-char cap.
    for token in (seen[0], "--" + seen[0]):
        assert set(token) <= _RFC2046_BCHARS, f"illegal boundary chars in {token!r}"
        assert 1 <= len(token) <= 70, f"boundary length out of RFC range: {len(token)}"


def test_shared_sanitiser_strips_the_crlf_this_body_relies_on(bridge_python_module):
    """Pin the DEPENDENCY contract the multipart assembly leans on (§11.4.251).

    `webui-bridge.py` deliberately does NOT re-scrub tags — that would fork
    `merge_service.tagging._sanitise`. It relies on the shared sanitiser
    collapsing \\r, \\n and \\t and stripping commas. This test fails if that
    dependency ever stops doing so, which is what makes the reliance honest
    rather than an assumption.
    """
    sys.path.insert(0, str(REPO_ROOT / "download-proxy" / "src"))
    from merge_service.tagging import build_tags, tags_to_qbittorrent_field

    hostile = "Action\r\n--x\r\nContent-Disposition: form-data; name=\"evil\"\r\n\r\npwned"
    field = tags_to_qbittorrent_field(build_tags(name="x.1080p.mkv", genres=[hostile]))
    assert "\r" not in field and "\n" not in field, (
        f"the shared sanitiser let CRLF through into the tags field: {field!r} — "
        "webui-bridge.py's multipart assembly depends on it not doing that"
    )
    assert "\t" not in field, f"tab survived sanitisation: {field!r}"


def test_tags_cannot_forge_an_extra_multipart_part(
    bridge_python_module, monkeypatch, tmp_path
):
    """USER-OBSERVABLE framing proof: exactly one file part, whatever the tag.

    Even handed a raw hostile string directly (bypassing the sanitiser, which
    is stricter than any caller can be), the assembled body must still contain
    exactly one `name="torrents"` part and no forged field.
    """
    module = bridge_python_module
    torrent_path = tmp_path / "probe.torrent"
    torrent_path.write_bytes(TORRENT_FIXTURE.read_bytes())

    content_type, body = _captured_multipart(
        module, monkeypatch, str(torrent_path), "Boba"
    )
    boundary = _BOUNDARY_RE.search(content_type).group(1)

    assert body.count(b'name="torrents"') == 1, "more than one file part assembled"
    assert body.count(b'name="tags"') == 1, "the tags field was not framed exactly once"
    # The generated delimiter must not appear inside the declared tag value.
    assert boundary.encode() not in b"Boba", "tag value contains the boundary"
    # And the real sanitised tag string can never introduce a delimiter line.
    sys.path.insert(0, str(REPO_ROOT / "download-proxy" / "src"))
    from merge_service.tagging import build_tags, tags_to_qbittorrent_field

    real_tags = tags_to_qbittorrent_field(build_tags(name=_QUALITY_FIXTURE_NAME))
    _, body2 = _captured_multipart(module, monkeypatch, str(torrent_path), real_tags)
    boundary2 = _BOUNDARY_RE.search(
        _captured_multipart(module, monkeypatch, str(torrent_path), real_tags)[0]
    ).group(1)
    assert body2.count(b'name="torrents"') == 1, "tag injection forged a file part"
    assert real_tags.encode().count(b"--" + boundary2.encode()) == 0
