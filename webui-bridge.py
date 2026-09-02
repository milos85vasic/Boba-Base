#!/usr/bin/env python3
"""
WebUI Bridge for Боба Private Tracker Support

This module solves the WebUI download issue by creating a bridge between
WebUI and nova2dl.py. It intercepts download requests and handles them
with proper authentication.

Author: Milos Vasic
Version: 2.0.0
License: Apache 2.0
"""

import json
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Configuration
#
# qBittorrent target resolution (§11.4.111 resolve-by-configured-address):
# the qBittorrent WebUI on :7185 is CONTAINER-INTERNAL and NOT published to
# the host. The host (and the host-side bridge process) reaches qBittorrent's
# WebUI through the download-proxy on :7186 (published + tunneled). So the
# default target MUST be the host-reachable download-proxy, not the
# container-internal :7185. Precedence:
#   1. BRIDGE_QBIT_URL / QBITTORRENT_URL — explicit base URL (preferred)
#   2. QBITTORRENT_HOST + QBITTORRENT_PORT — legacy host/port pair
#   3. default http://localhost:7186 (download-proxy → qBit WebUI)
# A Linux/container deploy can set BRIDGE_QBIT_URL=http://qbittorrent:7185 (or
# QBITTORRENT_HOST/PORT) and the same code path works unchanged.
_DEFAULT_QBIT_URL = "http://localhost:7186"


def _resolve_qbittorrent_url():
    """Resolve the host-reachable qBittorrent base URL from the environment."""
    explicit = os.environ.get("BRIDGE_QBIT_URL") or os.environ.get("QBITTORRENT_URL")
    if explicit:
        return explicit.rstrip("/")
    host = os.environ.get("QBITTORRENT_HOST")
    port = os.environ.get("QBITTORRENT_PORT")
    if host or port:
        return f"http://{host or 'localhost'}:{port or '7186'}".rstrip("/")
    return _DEFAULT_QBIT_URL


QBITTORRENT_URL = _resolve_qbittorrent_url()

# Parsed host/port kept as module attributes for back-compat: callers (and
# tests) may override QBITTORRENT_HOST / QBITTORRENT_PORT directly. The proxy
# path prefers QBITTORRENT_URL but falls back to host:port so a monkeypatched
# host/port still steers the target.
_parsed_qbit = urllib.parse.urlparse(QBITTORRENT_URL)
QBITTORRENT_HOST = _parsed_qbit.hostname or "localhost"
QBITTORRENT_PORT = _parsed_qbit.port or 7186
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "7188"))


# ---------------------------------------------------------------------------
# Content tagging (§11.4.251 — import the shared builder, never fork it).
#
# The tag ALGORITHM has exactly one implementation:
# ``download-proxy/src/merge_service/tagging.py``. The Python proxy reaches it
# through ``routes.py:_build_tag_field``; this bridge reaches the SAME module
# here. Reimplementing the dimensions (content type / quality / year / genre +
# the Boba/Боба promo pair) would be the byte-identical fork §11.4.251
# forbids, and would drift the instant either copy learned a new codec.
#
# Only the sys.path bootstrap is bridge-local, and it has to be: this bridge is
# a HOST process started as ``python3 webui-bridge.py`` from the repository
# root, so ``download-proxy/src`` is not importable until it is put on the
# path. The location is derived from ``__file__`` rather than a hardcoded
# absolute path, so a relocated checkout still resolves (§11.4.177).
# ---------------------------------------------------------------------------
_MERGE_SERVICE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "download-proxy", "src")

# ---------------------------------------------------------------------------
# Shared, dependency-free contracts (§11.4.251 — import, never fork).
#
# Both modules below are STDLIB-ONLY by contract, precisely so this host
# process — whose entire dependency set is the standard library — can import
# them. Unlike the tagging import above (lazy + guarded, because a missing tag
# is cosmetic), these are imported EAGERLY and are allowed to fail loudly:
#
#   * ``trackers`` decides whether a download is fetched WITH credentials. A
#     silently-empty roster would send every private-tracker URL down the
#     anonymous path and save login pages as ``.torrent`` files. Failing to
#     start is the honest outcome; degrading is the bluff (§11.4.252).
#   * ``qbit_add`` decides whether an add SUCCEEDED. A missing predicate must
#     not degrade into an optimistic default.
#
# The path is derived from ``__file__``, so a relocated checkout still resolves
# (§11.4.177).
# ---------------------------------------------------------------------------
if _MERGE_SERVICE_SRC not in sys.path:
    sys.path.insert(0, _MERGE_SERVICE_SRC)
from merge_service.qbit_add import qbit_add_succeeded as _qbit_add_succeeded_shared  # noqa: E402
from merge_service.trackers import PRIVATE_TRACKER_DOMAINS as _PRIVATE_TRACKER_DOMAINS  # noqa: E402
from merge_service.trackers import identify_tracker_in_text as _identify_tracker_in_text  # noqa: E402


def _bridge_tag_field(name):
    """Return qBittorrent's comma-separated ``tags`` value for ``name``.

    ``name`` is the downloaded ``.torrent`` filename — the only input the
    shared builder REQUIRES, and the one that needs no network: quality is
    parsed out of it offline. The bridge has no enriched metadata (it never
    performed a merge-service search), so content type / year / genres are
    genuinely absent and are therefore omitted rather than invented
    (§11.4.6 — the builder emits no placeholder for what did not resolve).

    Tagging must NEVER block or fail a download: any error returns an empty
    string, which qBittorrent treats as "no tags". An untagged torrent is a
    cosmetic loss; a failed add is a real one. This mirrors the contract of
    ``download-proxy/src/api/routes.py:_build_tag_field`` exactly.
    """
    try:
        if _MERGE_SERVICE_SRC not in sys.path:
            sys.path.insert(0, _MERGE_SERVICE_SRC)
        from merge_service.tagging import build_tags, tags_to_qbittorrent_field

        return tags_to_qbittorrent_field(build_tags(name=os.path.basename(name or "")))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[WebUI-Bridge] Tagging skipped ({type(exc).__name__}: {exc})")
        return ""


def _qbit_base_url():
    """Current qBittorrent base URL, read from the LIVE module globals.

    Deliberately not a constant: ``QBITTORRENT_HOST`` / ``QBITTORRENT_PORT``
    are documented as overridable by callers and tests (see the note above
    their definition), so every request must re-read them rather than bake
    the value in at import time.
    """
    return f"http://{QBITTORRENT_HOST}:{QBITTORRENT_PORT}"


def _qbit_credentials():
    """Resolve the qBittorrent WebUI credentials from the environment.

    Mirrors ``download-proxy/src/config/__init__.py`` exactly so the bridge
    and the proxy can never disagree about which account they use:
    ``QBITTORRENT_USER`` then ``QBITTORRENT_USERNAME``, defaulting to
    ``admin`` (and the same shape for the password).
    """
    username = os.environ.get("QBITTORRENT_USER", os.environ.get("QBITTORRENT_USERNAME", "admin"))
    password = os.environ.get("QBITTORRENT_PASS", os.environ.get("QBITTORRENT_PASSWORD", "admin"))
    return username, password


def qbittorrent_login():
    """Log in to the qBittorrent WebUI and return the session cookie.

    Success detection is by SESSION COOKIE, never by response body.
    qBittorrent 5.2.3 answers a successful login with **HTTP 204 and an
    EMPTY body** plus ``Set-Cookie: QBT_SID_<port>=...``; the legacy
    ``200 Ok.`` shape does not appear on this build, so a body check would
    reject every valid login. A wrong password answers 401 with no cookie.

    Returns:
        The ``QBT_SID_<port>=<value>`` cookie pair as a string, or None when
        authentication failed for any reason. The caller MUST treat None as
        a hard failure — there is no anonymous fallback (§11.4.252
        fail-closed: the previous anonymous path is exactly the defect this
        function exists to close).
    """
    base = _qbit_base_url()
    username, password = _qbit_credentials()
    payload = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(  # noqa: S310
        f"{base}/api/v2/auth/login",
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": base,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            if resp.status not in (200, 204):
                print(f"[WebUI-Bridge] Login rejected: HTTP {resp.status}")
                return None
            for header, value in resp.headers.items():
                if header.lower() == "set-cookie" and "QBT_SID" in value:
                    return value.split(";", 1)[0]
            print("[WebUI-Bridge] Login returned no session cookie — treating as failure")
            return None
    except urllib.error.HTTPError as e:
        print(f"[WebUI-Bridge] Login failed: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"[WebUI-Bridge] Login error: {e}")
        return None


def _qbit_add_succeeded(status, body):
    """Did qBittorrent really ACCEPT this ``/api/v2/torrents/add``?

    THIN DELEGATION (§11.4.251). This was a hand-maintained SECOND
    implementation of the predicate in ``api/routes.py``, and the two drifted
    until they recorded OPPOSITE verdicts for ``409``: ``routes`` read it as a
    duplicate (success), this file read it as a malformed request (failure).
    Three separate review findings traced back to that one duplication, and a
    mutation of either copy left the other's tests green — which is exactly how
    it went unnoticed.

    The divergence was argued from a claim that a duplicate add returns ``200``
    with a success summary. That claim is FALSE: re-measured 2/2 against
    qBittorrent v5.2.3 / WebAPI 2.15.1, a duplicate add returns ``409``. The
    clause is therefore not preserved — it is deleted, and the single measured
    contract now lives in :mod:`merge_service.qbit_add`, which this function
    delegates to unconditionally.

    The ``409`` reading is sound here for the same reason it is sound in
    ``routes``: the payload invariant holds. ``upload_to_qbittorrent`` reads the
    ``.torrent`` file from disk and always writes a ``torrents`` multipart part,
    so this bridge structurally cannot emit the no-payload add that draws the
    other ``409``. (An EMPTY file is still a payload part, and this build
    answers that with ``415``.)
    """
    return _qbit_add_succeeded_shared(status, body)


# Private tracker URL patterns — DERIVED from the ONE roster
# (``merge_service.trackers``), never re-typed here.
#
# This dict used to be a hand-kept fourth copy and had drifted: it carried
# ``rutracker.net`` and ``nnm-club.me`` that the merge service's roster lacked,
# and lacked ``kinozal.guru`` / ``kinozal.me`` / ``iptorrents.org`` that others
# carried. The drift is not cosmetic — a domain this bridge auth-routes but the
# merge service does not gets fetched ANONYMOUSLY there, and the tracker's HTML
# login page is saved as the user's ``.torrent``.
#
# Kept as a module-level name (and as ``{name: [domains]}``) because it is part
# of this module's public surface — tests and operators read it.
PRIVATE_TRACKERS = {name: list(domains) for name, domains in _PRIVATE_TRACKER_DOMAINS.items()}


class WebUIBridgeHandler(BaseHTTPRequestHandler):
    """Handle WebUI requests with private tracker support."""

    def log_message(self, format, *args):
        """Custom logging."""
        print(f"[WebUI-Bridge] {self.address_string()} - {format % args}")

    def do_POST(self):
        """Handle POST requests."""
        self.handle_request()

    def do_GET(self):
        """Handle GET requests."""
        self.handle_request()

    def handle_request(self):
        """Main request handler."""
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)

            # Liveness probe — the services-fixture preflight hits
            # /health at the bridge endpoint to make sure the bridge is
            # reachable before any test that depends on it runs. Return
            # a deeper signal: also probe the qBittorrent backend on
            # :7185 so `healthy` doesn't just mean "the python server is
            # up" but "the passthrough works." The probe timeout is
            # short so a slow qBittorrent doesn't hang the liveness
            # check — we degrade to `status:degraded` instead.
            if path == "/health":
                import http.client as _http
                import json as _json

                backend_status = "unknown"
                try:
                    conn = _http.HTTPConnection(QBITTORRENT_HOST, QBITTORRENT_PORT, timeout=2)
                    conn.request("GET", "/api/v2/app/version")
                    resp = conn.getresponse()
                    backend_status = "ok" if resp.status < 500 else f"http_{resp.status}"
                    conn.close()
                except Exception as exc:
                    backend_status = f"unreachable:{type(exc).__name__}"
                overall = "healthy" if backend_status == "ok" else "degraded"
                payload = _json.dumps(
                    {
                        "status": overall,
                        "service": "webui-bridge",
                        "backend": backend_status,
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            # Check if this is a torrent download
            if "urls" in query:
                urls = query.get("urls", [""])[0]
                if urls:
                    self.handle_torrent_download(urls)
                    return

            # Proxy to qBittorrent
            self.proxy_to_qbittorrent()

        except Exception as e:
            self.send_error(500, str(e))

    def handle_torrent_download(self, url):
        """Handle torrent download with private tracker support."""
        url = urllib.parse.unquote(url)

        # Identify if this is a private tracker
        plugin = self.identify_plugin(url)

        if plugin:
            print(f"[WebUI-Bridge] Private tracker detected: {plugin}")
            print(f"[WebUI-Bridge] URL: {url[:80]}...")

            # Use nova2dl.py for private trackers
            torrent_file = self.download_via_nova2dl(plugin, url)

            if torrent_file:
                # Upload to qBittorrent WITH content tags (IMPORTANT-2).
                #
                # This call site is the bridge's whole reason to exist — a
                # private-tracker download — and it used to pass no tags at
                # all, so every torrent the bridge added landed with
                # ``tags=''``: not even the ``Boba``/``Боба`` promo pair, even
                # though the downloaded filename carries everything the
                # offline quality detector needs. The ``tags=`` parameter had
                # existed since the auth fix but only the test ever filled it
                # (§11.4.108 — the capability was present at the SOURCE layer
                # and dead at the RUNTIME layer).
                tags = _bridge_tag_field(torrent_file)
                success = self.upload_to_qbittorrent(torrent_file, tags=tags)

                if success:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"OK")

                    # Cleanup
                    try:
                        os.unlink(torrent_file)
                    except OSError as e:
                        print(f"[WebUI-Bridge] Cleanup error: {e}")
                    return

        # Not a private tracker or download failed, proxy to qBittorrent
        self.proxy_to_qbittorrent()

    def identify_plugin(self, url):
        """Identify which nova3 plugin owns ``url``, else ``None``.

        Delegates to the shared roster's substring matcher. The SUBSTRING
        (rather than host) semantics are this consumer's deliberate policy and
        are preserved: the bridge intercepts a WebUI "add by URL" whose payload
        can legitimately carry a tracker address inside a parameter, and
        over-matching here routes through AUTHENTICATION — the safe direction.
        Under-matching is the defect this change removes. The merge-service API
        uses the stricter host matcher because it gates credential spend.
        """
        return _identify_tracker_in_text(url)

    def download_via_nova2dl(self, plugin, url):
        """Download using nova2dl.py."""
        try:
            cmd = ["python3", "/config/qBittorrent/nova3/nova2dl.py", plugin, url]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                output = result.stdout.strip()
                if " " in output:
                    return output.split(" ")[0]

            print(f"[WebUI-Bridge] nova2dl failed: {result.stderr}")
            return None

        except Exception as e:
            print(f"[WebUI-Bridge] Error: {e}")
            return None

    def upload_to_qbittorrent(self, filepath, tags=None, stopped=False):
        """Upload a torrent file to qBittorrent as an AUTHENTICATED client.

        ``/api/v2/torrents/add`` is a state-changing endpoint and qBittorrent
        rejects it with **403** when the caller carries no session (measured
        against qBittorrent 5.2.3, 2026-09-01). This bridge previously POSTed
        with no login and no cookie, which only ever worked because the WebUI
        config carried an authentication BYPASS
        (``WebUI\\LocalHostAuth=false`` + a subnet whitelist covering loopback
        and all RFC1918). That bypass ACCEPTED a deliberately wrong password
        and has been removed; the terminal step of ``handle_torrent_download``
        must therefore log in for itself.

        Sequence: ``qbittorrent_login()`` -> session cookie -> multipart POST
        carrying that cookie plus a ``Referer`` matching the upstream origin
        (see ``proxy_to_qbittorrent`` for why the Referer is load-bearing).

        Args:
            filepath: path to the ``.torrent`` file to add.
            tags: optional comma-separated tag string attached to the torrent.
            stopped: when True the torrent is added in a stopped/paused state
                (both the qBittorrent 5.x ``stopped`` and the legacy
                ``paused`` field are sent, so the flag works on either build).

        Returns:
            True only when qBittorrent really accepted the torrent, decided by
            :func:`_qbit_add_succeeded` against the measured add contract — the
            2xx status AND the response body, because this server answers a
            rejected add with 200 shapes as well as with 4xx ones. Any
            authentication failure, transport error, rejecting status, or 2xx
            body reporting nothing added returns False — never an optimistic
            default, and never a bare status check.
        """
        try:
            session = qbittorrent_login()
            if not session:
                print(
                    "[WebUI-Bridge] Upload aborted: qBittorrent login failed "
                    "(check QBITTORRENT_USER / QBITTORRENT_PASS)"
                )
                return False

            base = _qbit_base_url()
            url = f"{base}/api/v2/torrents/add"

            # Create multipart request.
            #
            # N-b: the boundary is drawn from a CSPRNG, never from the clock.
            # It used to be `str(int(time.time()))` — one second of resolution,
            # so any observer who knows roughly when an upload happened can
            # reproduce the exact delimiter. Nothing in this body is
            # attacker-controlled today, but a predictable boundary is the
            # precondition for a body-splitting attack, and the `tags` field
            # added alongside this fix is the first content here that is
            # DERIVED rather than hardcoded — so the hygiene is bought before
            # it is needed, not after.
            #
            # `secrets.token_hex` yields [0-9a-f] only, which is a strict
            # subset of the RFC 2046 `bcharsnospace` set, and the assembled
            # delimiter (22 + 32 = 54 chars) stays inside the 70-char limit.
            #
            # CRLF / delimiter injection through `tags` (§11.4.251 — relied
            # upon, NOT re-implemented): the tag string reaching this function
            # always comes from `merge_service.tagging._sanitise`, which does
            # `" ".join(text.split())` — collapsing \r, \n and \t — and caps
            # each tag at `MAX_TAG_LENGTH`. A tag therefore cannot contain the
            # CRLF a forged part needs, nor a comma that would split the field.
            # Duplicating that scrubbing here would fork the sanitiser; the
            # contract is pinned instead by
            # `test_shared_sanitiser_strips_the_crlf_this_body_relies_on`, so
            # if the dependency ever stops scrubbing, this file's guard fails.
            boundary = "----WebKitFormBoundary" + secrets.token_hex(16)

            with open(filepath, "rb") as f:
                file_data = f.read()

            fields = {}
            if tags:
                fields["tags"] = tags
            if stopped:
                # qBittorrent >= 5.0 renamed `paused` to `stopped`; sending
                # both keeps the flag effective across builds and an unknown
                # field is ignored rather than rejected.
                fields["stopped"] = "true"
                fields["paused"] = "true"

            body = []
            for name, value in fields.items():
                body.append(f"------{boundary}".encode())
                body.append(f'Content-Disposition: form-data; name="{name}"'.encode())
                body.append(b"")
                body.append(str(value).encode())
            body.append(f"------{boundary}".encode())
            body.append(b'Content-Disposition: form-data; name="torrents"; filename="torrent.torrent"')
            body.append(b"Content-Type: application/x-bittorrent")
            body.append(b"")
            body.append(file_data)
            body.append(f"------{boundary}--".encode())

            body = b"\r\n".join(body)

            req = urllib.request.Request(  # noqa: S310
                url,
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary=----{boundary}",
                    "Content-Length": len(body),
                    "Cookie": session,
                    "Referer": base,
                },
            )

            # The success DECISION is delegated to `_qbit_add_succeeded`, which
            # implements the measured cross-version add contract (IMPORTANT-3).
            # The previous `response.status == 200` could not tell a 200 that
            # ADDED the torrent from a 200 that added NOTHING — so this
            # function's own docstring promise ("True only when qBittorrent
            # really accepted the torrent") was false, and a rejected add was
            # reported to `handle_torrent_download` as OK.
            try:
                with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
                    status = response.status
                    payload = response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as http_exc:
                # Read the error response instead of discarding it: 409 / 415
                # carry qBittorrent's own reason, and printing it makes a
                # refusal diagnosable in one step (§11.4.201(5)).
                status = http_exc.code
                payload = (http_exc.read() or b"").decode("utf-8", "replace")

            accepted = _qbit_add_succeeded(status, payload)
            if not accepted:
                print(
                    f"[WebUI-Bridge] qBittorrent did NOT accept the torrent: "
                    f"HTTP {status} {payload[:200]!r}"
                )
            return accepted

        except Exception as e:
            print(f"[WebUI-Bridge] Upload error: {e}")
            return False

    def _is_root_liveness_probe(self):
        """True for a bare ``GET /`` with no torrent download in flight.

        The dashboard's bridge-health probe
        (``download-proxy/src/api/__init__.py:bridge_health``) GETs the
        bridge root and treats ``status < 500`` as "the bridge is alive".
        That probe must report on the *bridge process* liveness, which is
        independent of whether the qBittorrent backend on :7185 is
        reachable. When the passthrough to qBittorrent fails for such a
        bare-root probe we answer with a 200 liveness payload instead of
        leaking qBittorrent's connection error as a misleading 500 — a
        listening bridge with a down upstream is NOT "down".
        """
        try:
            parsed = urllib.parse.urlparse(self.path)
        except Exception:
            return False
        if parsed.path != "/":
            return False
        if urllib.parse.parse_qs(parsed.query):
            return False
        return self.command == "GET"

    def _send_root_liveness(self, backend_error):
        """Answer a bare-root liveness probe when qBittorrent is unreachable.

        Returns HTTP 200 with ``backend: unreachable`` so the dashboard
        renders the bridge as UP (it is — it answered) while still
        signalling that the qBittorrent passthrough is currently down.
        """
        payload = json.dumps(
            {
                "status": "alive",
                "service": "webui-bridge",
                "backend": "unreachable",
                "backend_error": str(backend_error),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def proxy_to_qbittorrent(self):
        """Proxy request to qBittorrent.

        Header hygiene:

        * ``Host`` and ``Content-Length`` are recomputed by urllib.
        * ``Referer`` and ``Origin`` are rewritten to
          ``http://localhost:$QBITTORRENT_PORT``. qBittorrent's WebUI
          enforces same-origin by default on state-changing endpoints
          (``/api/v2/auth/login`` returns 401 if the Referer does not
          match its host), and without this rewrite every login
          attempt through the bridge would fail.

        Upstream-down handling: if qBittorrent is unreachable
        (``URLError`` — connection refused / network unreachable / DNS),
        a bare-root liveness probe is answered 200 (the bridge is alive,
        only its upstream is down); any other path returns 502 Bad
        Gateway with correct gateway semantics instead of a generic 500.
        """
        try:
            target = f"http://{QBITTORRENT_HOST}:{QBITTORRENT_PORT}{self.path}"

            # Read body if POST
            body = None
            if self.command == "POST":
                length = int(self.headers.get("Content-Length", 0))
                if length > 0:
                    body = self.rfile.read(length)

            req = urllib.request.Request(target, data=body, method=self.command)

            qbit_origin = f"http://localhost:{QBITTORRENT_PORT}"
            for header, value in self.headers.items():
                header_lower = header.lower()
                if header_lower in ("host", "content-length"):
                    continue
                if header_lower == "referer" or header_lower == "origin":
                    value = qbit_origin
                req.add_header(header, value)

            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                raw_body = resp.read()
                upstream_headers = list(resp.headers.items())

                # BYTE-FOR-BYTE PASS-THROUGH. The themed-WebUI overlay
                # that used to mutate this body was removed 2026-09-01 by
                # operator decision (see plugins/download_proxy.py and
                # tests/integration/test_vanilla_webui_unmodified.py):
                # it shipped zero qBittorrent features and its
                # qBittorrent -> Боба rebrand rewrote the token inside
                # inline <script> blocks, killing the WebUI's JS.
                # Content-Encoding is forwarded untouched.
                body = raw_body

                self.send_response(resp.status)
                for header, value in upstream_headers:
                    if header.lower() == "transfer-encoding":
                        continue
                    self.send_header(header, value)
                self.end_headers()
                self.wfile.write(body)

        except urllib.error.HTTPError as e:
            # Forward qBittorrent's status/headers/body so auth failures
            # surface as 401 with ``Fails.`` body instead of being
            # rewritten to BaseHTTPRequestHandler's generic 401 HTML.
            try:
                self.send_response(e.code)
                for header, value in (e.headers or {}).items():
                    if header.lower() == "transfer-encoding":
                        continue
                    self.send_header(header, value)
                self.end_headers()
                self.wfile.write(e.read() or e.reason.encode("utf-8"))
            except Exception:
                self.send_error(e.code, e.reason)

        except urllib.error.URLError as e:
            # qBittorrent upstream unreachable (connection refused /
            # network unreachable / DNS failure). HTTPError is a URLError
            # subclass and is handled above, so this branch is the
            # genuine transport-level failure. A bare-root liveness probe
            # must still see the bridge as alive — answer 200; everything
            # else gets a correct 502 Bad Gateway rather than a generic
            # 500 that the dashboard would misread as "bridge down".
            if self._is_root_liveness_probe():
                self._send_root_liveness(e.reason)
            else:
                self.send_error(502, f"qBittorrent upstream unreachable: {e.reason}")


def run_bridge():
    """Start the WebUI bridge server."""
    # ThreadingHTTPServer so one slow request (e.g. a long poll to qBit)
    # does not block the liveness probe from /api/v1/bridge/health.
    # Without this, the dashboard chip flipped to "down" any time a
    # real client happened to be mid-request.
    server = ThreadingHTTPServer(("", BRIDGE_PORT), WebUIBridgeHandler)

    print("=" * 70)
    print("Боба WebUI Bridge Server")
    print("=" * 70)
    print(f"Bridge Port: {BRIDGE_PORT}")
    print(f"qBittorrent backend: http://{QBITTORRENT_HOST}:{QBITTORRENT_PORT}")
    print("=" * 70)
    print("This bridge enables private tracker downloads in WebUI")
    print("=" * 70)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    run_bridge()
