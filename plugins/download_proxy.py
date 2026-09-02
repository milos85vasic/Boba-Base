#!/usr/bin/env python3
"""
Download Proxy for the qBittorrent WebUI.

Intercepts private-tracker URLs on ``POST /api/v2/torrents/add`` and
downloads the .torrent via nova2dl.py with authentication. EVERY other
request — and every response body and header — is passed through
BYTE-FOR-BYTE, so browsers see the stock vanilla qBittorrent WebUI.

The themed-WebUI overlay (CSS/JS injection + qBittorrent→Боба rebrand)
was REMOVED 2026-09-01 by operator decision: it shipped zero qBittorrent
features and broke the WebUI's JavaScript. Cross-app theme STATE for the
Angular dashboard on :7187 is unaffected and still lives in
``download-proxy/src/api/theme_state.py``.
"""

import sys
import os
import json
import urllib.request
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import subprocess
import logging
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

QBITTORRENT_HOST = os.environ.get("QBITTORRENT_HOST", "localhost")
QBITTORRENT_PORT = os.environ.get("QBITTORRENT_PORT", "7185")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "7186"))

# NOTE: the private-tracker roster is NOT re-typed here any more. It lives in
# ``merge_service.trackers`` and is resolved lazily by ``identify_plugin``
# below — see the long comment there for why the import cannot be eager in this
# particular file. ``PLUGIN_PATTERNS`` / ``COMPILED_PATTERNS`` were this file's
# copy of that roster and had drifted from the other three (it uniquely carried
# ``kinozal.me`` and ``iptorrents.org``, and uniquely lacked ``kinozal.guru``
# and ``nnmclub.ro``).


# ---------------------------------------------------------------------------
# Content tagging on the tracker-intercept path (§11.4.251 — import the
# shared builder, never fork it).
#
# WHY THIS PATH NEEDED IT. The intercept below already rewrites
# ``params["urls"]`` to the locally-downloaded ``file://`` path and re-encodes
# the form, so it is the LAST place that can attach tags before qBittorrent
# sees the add. Without this, a private-tracker download that arrives through
# the browser's own WebUI (rather than through webui-bridge.py) lands with
# ``tags=''`` — the same IMPORTANT-2 defect, on a second path.
#
# WHY THE IMPORT IS SAFE HERE (verified, not assumed — §11.4.6). This module is
# staged into ``/config/qBittorrent/nova3/engines`` by install-plugin.sh and
# imported by ``download-proxy/src/main.py::start_original_proxy``, which runs
# inside the ``qbittorrent-proxy`` container. That container bind-mounts the
# proxy source at ``/config/download-proxy`` (docker-compose.yml
# ``./download-proxy:/config/download-proxy``), so ``merge_service`` is on
# disk right there. Measured 2026-09-01 from the real engines working
# directory inside the running container:
#
#     python3 -c "import sys; sys.path.insert(0,'/config/download-proxy/src');
#                 from merge_service.tagging import build_tags; ..."
#     -> 720p,Boba,Боба
#
# ``merge_service.tagging`` pulls only ``merge_service.enricher``, whose
# module-level imports are stdlib (logging/os/re/dataclasses) — ``aiohttp`` is
# imported lazily inside the async network methods, which the offline
# ``detect_quality`` path never enters. So this adds NO dependency.
#
# The same file is also copied into the ``qbittorrent`` container, where the
# proxy server is never started. The import is therefore LAZY (inside the
# function, never at module import) and fully guarded: a context without
# ``merge_service`` degrades to no tags instead of breaking the add.
# ---------------------------------------------------------------------------


def _merge_service_src_candidates():
    """Ordered, deduplicated roots that may contain the ``merge_service`` package."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.environ.get("MERGE_SERVICE_SRC"),
        # Container layout: docker-compose bind-mounts ./download-proxy here.
        "/config/download-proxy/src",
        # Repo layout when this file is read straight from plugins/.
        os.path.join(os.path.dirname(here), "download-proxy", "src"),
    ]
    seen = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.append(candidate)
    return seen


def build_tag_field(name):
    """Return qBittorrent's comma-separated ``tags`` value for ``name``.

    ``name`` is the downloaded ``.torrent`` filename — the only input the
    shared builder REQUIRES and the one that needs no network, since quality
    is parsed out of it offline. This path has no enriched metadata (no
    merge-service search happened), so content type / year / genres are
    genuinely absent and are omitted rather than invented (§11.4.6).

    Tagging must NEVER block or fail a download: every failure path returns an
    empty string, which qBittorrent treats as "no tags". An untagged torrent is
    a cosmetic loss; a failed add is a real one. Same contract as
    ``api/routes.py:_build_tag_field`` and ``webui-bridge.py:_bridge_tag_field``.
    """
    try:
        for root in _merge_service_src_candidates():
            if os.path.isdir(os.path.join(root, "merge_service")):
                if root not in sys.path:
                    sys.path.insert(0, root)
                break
        from merge_service.tagging import build_tags, tags_to_qbittorrent_field

        return tags_to_qbittorrent_field(build_tags(name=os.path.basename(name or "")))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Tagging skipped ({type(exc).__name__}: {exc})")
        return ""


def merge_tag_values(existing, derived):
    """Union ``existing`` (whatever the client already sent) with ``derived``.

    The client's tags are NEVER discarded: a user who typed their own tag into
    the WebUI's add dialog must keep it. Order is client-first, then derived,
    de-duplicated case-sensitively (qBittorrent's tags are case-sensitive, and
    ``Боба`` has no case-folding relationship to anything Latin).
    """
    out = []
    for value in (existing or "", derived or ""):
        for tag in value.split(","):
            tag = tag.strip()
            if tag and tag not in out:
                out.append(tag)
    return ",".join(out)


# ---------------------------------------------------------------------------
# BOB-111 — per-IP rate limiting for the :7186 public surface.
#
# WHY THIS IS NOT slowapi (§11.4.251 — one mechanism, not a divergent copy).
# The merge service on :7187 is protected by `SlowAPIMiddleware`, installed in
# `download-proxy/src/api/rate_limit.py`. That middleware is ASGI. THIS server
# is a stdlib `ThreadingHTTPServer` running on its OWN THREAD in the same
# process (`download-proxy/src/main.py::start_original_proxy`), so no ASGI
# middleware can reach it — measured 2026-08-21 on the operator's live stack:
#
#     Server: BaseHTTP/0.6 Python/3.12.13     (:7186, stdlib)
#     Server: uvicorn                          (:7187, ASGI)
#     150 sequential GET :7186/  ->  200:150  429:0
#
# The module docstring of `api/rate_limit.py` previously claimed install()
# covered ":7186 (same FastAPI app object today)". That claim was FALSE and is
# corrected there by this change.
#
# `plugins/download_proxy.py` additionally has a hard constraint the merge
# service does not: it is loaded by qBittorrent's nova3 engine loader as a
# search plugin, and it therefore imports NOTHING but the standard library.
# Pulling in fastapi/slowapi/limits here would couple the plugin surface to the
# merge service's dependency tree.
#
# So the TRANSPORT adapter differs (it must), while the POLICY CONTRACT is kept
# identical to :7187 on every operator-visible axis:
#
#   * limit strings              "N/second|minute|hour|day"
#   * env override naming        RATE_LIMIT_<CLASS>
#   * global escape              RATE_LIMIT_DISABLED=1
#   * per-IP keying              RemoteAddr, X-Forwarded-For ONLY under an
#                                explicit TRUST_FORWARDED_FOR=1 opt-in
#   * strategy                   fixed window
#   * refusal                    HTTP 429, body {"error": "rate_limited"},
#                                Retry-After + X-RateLimit-* headers
#   * one bucket per request     a request is charged to EXACTLY ONE class,
#                                never two (the same rule api/rate_limit.py
#                                states for its dependency-vs-decorator split)
#
# TWO CLASSES, and the split is the same shape as :7187's cheap/expensive one:
#
#   proxy           — WebUI passthrough. GENEROUS.
#                     MEASURED 2026-08-21: the qBittorrent WebUI page served
#                     through :7186 references 76 UNIQUE local sub-resources
#                     (223 src/href occurrences), so ONE cold page load is
#                     ~77 requests in a ~1s burst; qBittorrent's WebUI then
#                     polls /api/v2/sync/maindata at its default 1500ms
#                     refresh interval = 40 req/min sustained, and the
#                     container healthcheck adds 2/min. A limit anywhere near
#                     :7187's 60/minute would blank the operator's WebUI on
#                     the first page load — that would be a §11.4.201(1)
#                     false-positive refusal, as bad as no limiter at all.
#                     600/minute leaves headroom for ~7 cold loads per minute
#                     on top of sustained polling, while still cutting a
#                     `wrk -c 100` flood (BOB-112 measured >1000 req/s) by
#                     two orders of magnitude.
#
#   proxy_download  — POST /api/v2/torrents/add carrying a TRACKER url, i.e.
#                     the branch that shells out to nova2dl AND makes an
#                     outbound authenticated tracker request. That is the
#                     amplification vector, the exact analogue of :7187's
#                     /api/v1/search fan-out, and it gets the same 10/minute.
#
# Buckets are per (client, class), so exhausting the download budget can never
# lock the operator out of the WebUI.
#
# MEMORY: the bucket registry is bounded. Idle buckets are reaped after
# RATE_LIMIT_IDLE_REAP_SECONDS (default 900s, matching the Go limiter in
# qBitTorrent-go/internal/middleware/ratelimit.go), and a hard cap evicts the
# least-recently-used entry, so a source-IP fan-out cannot grow the map without
# limit inside a 768m container.
#
# TRACKED FOLLOW-UP (BOB-111 review, M3) — X-Forwarded-For is FORGEABLE by
# design when TRUST_FORWARDED_FOR=1. The leftmost entry is client-controlled,
# so behind a proxy that APPENDS rather than REPLACES it, a caller can prepend
# a fabricated address and mint a fresh per-IP budget on demand. The correct
# closure is to trust the RIGHTMOST entry contributed by a known-trusted proxy
# hop, or to bind to a configured trusted-proxy CIDR set.
#
# NOT FIXED HERE, deliberately: this behaviour is EXACT PARITY with :7187's
# `_client_key` (download-proxy/src/api/rate_limit.py), the opt-in is OFF by
# default, and this stack runs `network_mode: host` with no reverse proxy, so
# the forgeable path is unreachable as deployed. Fixing one port and not the
# other would leave two divergent keying policies behind one contract
# (§11.4.251). It is one follow-up covering BOTH :7186 and :7187.
# ---------------------------------------------------------------------------

import threading as _rl_threading
import time as _rl_time

# Period names accepted by the `limits` library that backs :7187, so an
# operator can move a limit string between the two ports unchanged. MEASURED
# 2026-08-21 against limits.parse():
#     "10/second" / "10/minute" / "10/hour" / "10/day" / "10/month" /
#     "10/year" / "100/5minutes"   -> accepted
#     "10/s" / "10/m" / "10/min" / "10/h" / "10/d"  -> ValueError
# Abbreviations are REJECTED there, so they are rejected here too.
_RL_PERIODS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "month": 2592000,
    "year": 31104000,
}

RATE_LIMIT_DEFAULTS = {
    "proxy": "600/minute",
    "proxy_download": "10/minute",
}

_RL_MAX_BUCKETS = 4096


def _rl_env_true(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def _rl_parse_period(text):
    """Return window seconds for a `limits`-grammar period, or None.

    Accepts an optional integer multiple prefix ("5minutes") and an optional
    trailing plural, matching :7187. Deliberately does NOT accept "s"/"m"/"h"/
    "d" — those are ValueError on :7187, and mapping them to a guessed period
    would silently reinterpret an operator's configuration (§11.4.6).
    """
    m = re.match(r"^(\d*)\s*([a-z]+)$", text.strip().lower())
    if not m:
        return None
    multiple = int(m.group(1)) if m.group(1) else 1
    name = m.group(2)
    if name not in _RL_PERIODS and name.endswith("s") and name[:-1] in _RL_PERIODS:
        name = name[:-1]
    if name not in _RL_PERIODS or multiple < 1:
        return None
    return _RL_PERIODS[name] * multiple


def _rl_parse_limit(raw, fallback):
    """Parse "N/period" into (count, window_seconds).

    An unparseable value falls back to the class default and SAYS SO — it never
    silently disables the limit, and never silently reinterprets it as some
    other period (§11.4.201: a guard that quietly stops guarding is worse than
    one that refuses loudly; §11.4.6: a value we could not honour is reported,
    not guessed).
    """
    text = (raw or "").strip()
    if not text:
        text = fallback
    count_s, sep, period_s = text.partition("/")
    period = _rl_parse_period(period_s) if sep else None
    try:
        count = int(count_s.strip())
    except ValueError:
        count = 0
    if period is not None and count > 0:
        return count, period
    logger.error(
        "Invalid rate limit %r (expected 'N/second|minute|hour|day|month|year'); "
        "falling back to %r",
        text,
        fallback,
    )
    count_s, _, period_s = fallback.partition("/")
    return int(count_s), _rl_parse_period(period_s)


def _rl_env_int(name, fallback, minimum=1):
    """Read a positive integer env knob, degrading LOUDLY rather than fatally.

    IMPORTANT: this runs at MODULE IMPORT. A bare int() here means a typo in a
    tuning knob raises ValueError during import; `main.py::start_original_proxy`
    catches it, logs "Original proxy failed", and :7186 never binds — a total
    WebUI outage from a malformed env var (reproduced 2026-08-21 with
    RATE_LIMIT_IDLE_REAP_SECONDS=abc). Same loud-fallback shape as
    `_rl_parse_limit`, and clamped to `minimum` so a non-positive value cannot
    silently invert the behaviour it configures.
    """
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        logger.error("Invalid %s=%r (expected an integer); using %s", name, raw, fallback)
        return fallback
    if value < minimum:
        logger.error("%s=%s is below the minimum %s; clamping", name, value, minimum)
        return minimum
    return value


def _rl_limit_for(class_name):
    return _rl_parse_limit(
        os.environ.get("RATE_LIMIT_" + class_name.upper()),
        RATE_LIMIT_DEFAULTS[class_name],
    )


class FixedWindowRateLimiter:
    """Per-(IP, class) fixed-window counters. Safe for ThreadingHTTPServer."""

    def __init__(self, limits, idle_reap_seconds=900, max_buckets=_RL_MAX_BUCKETS):
        self._limits = dict(limits)
        self._idle_reap = idle_reap_seconds
        self._max_buckets = max_buckets
        self._lock = _rl_threading.Lock()
        # key -> [window_start, count, last_seen]
        self._buckets = {}

    def limit_for(self, class_name):
        return self._limits.get(class_name, self._limits["proxy"])

    def check(self, client, class_name, now=None):
        """Charge one request.

        Returns (allowed, limit, remaining, reset_after, first_refusal).

        `first_refusal` is True only for the FIRST refusal in a given window,
        so the caller can log the event ONCE instead of once per refused
        request. That matters: a refusal is cheaper than the work it prevents,
        but a WARNING line per refusal is not — a flood that the limiter
        successfully refuses would still fill the operator's log and the
        container's disk, turning the mitigation into its own
        resource-exhaustion vector. Measured 2026-08-21 before this was added:
        a 604-request flood past the 600/minute budget emitted 200 refusals
        and 200 identical WARNING lines.
        """
        count, window = self.limit_for(class_name)
        now = _rl_time.monotonic() if now is None else now
        key = (client, class_name)
        with self._lock:
            self._reap(now)
            start, used, _, refused = self._buckets.get(key, (now, 0, now, 0))
            if now - start >= window:
                start, used, refused = now, 0, 0
            allowed = used < count
            if allowed:
                used += 1
            else:
                refused += 1
            self._buckets[key] = (start, used, now, refused)
            reset_after = max(1, int(window - (now - start)) + 1)
            return allowed, count, max(0, count - used), reset_after, (not allowed and refused == 1)

    def _reap(self, now):
        """Drop idle buckets; hard-evict LRU if still over the cap."""
        if len(self._buckets) > self._max_buckets // 2:
            stale = [k for k, v in self._buckets.items() if now - v[2] > self._idle_reap]
            for k in stale:
                del self._buckets[k]
        while len(self._buckets) > self._max_buckets:
            oldest = min(self._buckets, key=lambda k: self._buckets[k][2])
            del self._buckets[oldest]


RATE_LIMIT_DISABLED = _rl_env_true("RATE_LIMIT_DISABLED")
TRUST_FORWARDED_FOR = _rl_env_true("TRUST_FORWARDED_FOR")
RATE_LIMIT_IDLE_REAP_SECONDS = _rl_env_int("RATE_LIMIT_IDLE_REAP_SECONDS", 900)

_RATE_LIMITER = (
    None
    if RATE_LIMIT_DISABLED
    else FixedWindowRateLimiter(
        {name: _rl_limit_for(name) for name in RATE_LIMIT_DEFAULTS},
        idle_reap_seconds=RATE_LIMIT_IDLE_REAP_SECONDS,
    )
)

if RATE_LIMIT_DISABLED:
    logger.warning(
        "Rate limiting DISABLED via RATE_LIMIT_DISABLED - :%s accepts unbounded "
        "request rates. Intended for RED baselines and integration harnesses only.",
        PROXY_PORT,
    )


def classify_request(command, path, body):
    """Return the rate-limit class a request must be charged to.

    EXACTLY ONE class per request, and the guarantee that matters is
    ONE-DIRECTIONAL: a request that WILL reach `download_via_nova2dl` is never
    charged to the cheap class. That is the safety property — the amplification
    vector can never be missed.

    The converse does NOT hold, deliberately. This runs BEFORE
    `handle_request`, so it does not re-do that function's multipart sniff: a
    MULTIPART torrents/add upload whose raw bytes happen to contain a
    `urls=<tracker-url>` field parses as form-encoded here and is charged to
    `proxy_download`, while `handle_request` will pass it straight through to
    qBittorrent without any nova2dl fan-out. Such a request is OVER-charged
    against the tighter bucket. That asymmetry is the intended trade: an
    over-charge costs a legitimate uploader part of a 10/minute budget, an
    under-charge would hand an attacker the subprocess-plus-tracker-fetch path
    for free.

    A MALFORMED body cannot escape either — it falls back to the generous
    passthrough class rather than being waved through uncharged (the 422-bypass
    lesson from api/rate_limit.py).
    """
    if command != "POST" or body is None:
        return "proxy"
    try:
        if urllib.parse.urlparse(path).path != "/api/v2/torrents/add":
            return "proxy"
        urls = urllib.parse.parse_qs(body.decode("utf-8")).get("urls", [""])[0]
    except (UnicodeDecodeError, ValueError):
        return "proxy"
    if urls and identify_plugin(urls):
        return "proxy_download"
    return "proxy"



_IDENTIFY_TRACKER_IN_TEXT = None


def _resolve_tracker_matcher():
    """Resolve (once) the shared roster's substring matcher.

    WHY LAZY AND NOT A MODULE-LEVEL IMPORT (§11.4.6 — measured, not assumed).
    This file is copied into ``/config/qBittorrent/nova3/engines/`` by
    ``install-plugin.sh`` (``INFRA_MODULES``) and that directory is mounted into
    BOTH containers. Only ``qbittorrent-proxy`` bind-mounts
    ``./download-proxy:/config/download-proxy`` (docker-compose.yml), so in the
    ``qbittorrent`` container ``merge_service`` is genuinely absent — an eager
    import would raise during nova2's engine enumeration there. Verified
    2026-09-01 inside the running proxy container, from the real engines working
    directory::

        podman exec qbittorrent-proxy sh -lc 'cd /config/qBittorrent/nova3/engines &&
          python3 -c "import sys; sys.path.insert(0,\\"/config/download-proxy/src\\");
                      import merge_service.tagging as t; print(t.__file__)"'
        -> /config/download-proxy/src/merge_service/tagging.py

    ``identify_plugin`` is only ever CALLED by the :7186 proxy server, which
    runs exclusively in that container — so the one context that needs the
    roster provably has it, and the other never asks.

    A failure is logged at ERROR and yields no matcher, so tracker interception
    is skipped rather than silently answered from a stale local copy. That is a
    loud, diagnosable degrade — not a second roster.
    """
    global _IDENTIFY_TRACKER_IN_TEXT
    if _IDENTIFY_TRACKER_IN_TEXT is not None:
        return _IDENTIFY_TRACKER_IN_TEXT
    try:
        for root in _merge_service_src_candidates():
            if os.path.isdir(os.path.join(root, "merge_service")):
                if root not in sys.path:
                    sys.path.insert(0, root)
                break
        from merge_service.trackers import identify_tracker_in_text

        _IDENTIFY_TRACKER_IN_TEXT = identify_tracker_in_text
    except Exception as exc:
        logger.error(
            f"Private-tracker roster unavailable ({type(exc).__name__}: {exc}) — "
            "tracker interception disabled for this process"
        )
        return None
    return _IDENTIFY_TRACKER_IN_TEXT


def _supported_tracker_names():
    """Tracker names this process can intercept — read from the shared roster.

    Returns ``[]`` (and the startup banner says so) when the roster could not be
    resolved, so an operator sees the real capability rather than a hardcoded
    list that no longer reflects what ``identify_plugin`` will do (§11.4.201 —
    the banner asserts the real condition).
    """
    try:
        for root in _merge_service_src_candidates():
            if os.path.isdir(os.path.join(root, "merge_service")):
                if root not in sys.path:
                    sys.path.insert(0, root)
                break
        from merge_service.trackers import PRIVATE_TRACKER_DOMAINS

        return list(PRIVATE_TRACKER_DOMAINS.keys())
    except Exception:
        return []


def identify_plugin(url):
    """Return the nova3 plugin owning ``url``, else ``None``.

    Substring semantics (this consumer's deliberate policy, preserved): the
    intercepted payload is a WebUI "add by URL" body that can carry a tracker
    address inside a parameter. Over-matching routes through AUTHENTICATION,
    which is the safe direction here.
    """
    matcher = _resolve_tracker_matcher()
    if matcher is None:
        return None
    return matcher(url)


def download_via_nova2dl(plugin, url):
    """Download torrent using nova2dl.py with authentication."""
    try:
        cmd = ["python3", "/config/qBittorrent/nova3/nova2dl.py", plugin, url]
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            logger.error(f"nova2dl.py failed: {result.stderr}")
            return None

        output = result.stdout.strip()
        if not output:
            logger.error("nova2dl.py returned empty output")
            return None

        parts = output.split(" ", 1)
        if len(parts) != 2:
            logger.error(f"Unexpected output: {output}")
            return None

        torrent_path = parts[0]
        if not os.path.exists(torrent_path):
            logger.error(f"Torrent file not found: {torrent_path}")
            return None

        logger.info(f"Downloaded to: {torrent_path}")
        return torrent_path
    except subprocess.TimeoutExpired:
        logger.error("nova2dl.py timed out")
        return None
    except Exception as e:
        logger.error(f"Error in download_via_nova2dl: {e}")
        return None


class DownloadHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        if "/api/" in self.path:
            logger.info(f"{self.address_string()} - {format % args}")

    # -- BOB-111 rate limiting ------------------------------------------
    # Charged at the TOP of every entry point, before ANY work: before the
    # qBittorrent round-trip and before the nova2dl fan-out. A limiter that
    # only guards the expensive branch
    # leaves the cheap ones as a free amplifier for the same socket.

    def _rate_limit_client(self):
        """Per-IP key. X-Forwarded-For is honoured ONLY under an explicit
        TRUST_FORWARDED_FOR=1 opt-in — trusting it by default lets any caller
        forge a source IP and mint an unlimited budget."""
        if TRUST_FORWARDED_FOR:
            fwd = (self.headers.get("X-Forwarded-For") or "").strip()
            if fwd:
                return fwd.split(",")[0].strip()
        try:
            return self.client_address[0]
        except (AttributeError, IndexError, TypeError):
            return "unknown"

    def _send_rate_limited(self, limit, remaining, reset_after):
        """Minimal 429 — an opaque token only (§11.4.10). No client IP, no
        bucket internals, no class name in the body."""
        payload = b'{"error": "rate_limited"}'
        try:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Retry-After", str(reset_after))
            self.send_header("X-RateLimit-Limit", str(limit))
            self.send_header("X-RateLimit-Remaining", str(remaining))
            self.send_header("X-RateLimit-Reset", str(reset_after))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _rate_limit_ok(self, body):
        """Charge this request. Returns False iff it was refused (429 sent)."""
        if _RATE_LIMITER is None:
            return True
        class_name = classify_request(self.command, self.path, body)
        allowed, limit, remaining, reset_after, first_refusal = _RATE_LIMITER.check(
            self._rate_limit_client(), class_name
        )
        if allowed:
            return True
        if first_refusal:
            # ONCE per client per window — see FixedWindowRateLimiter.check.
            # Logged WITHOUT the client IP or the request body (§11.4.10).
            logger.warning(
                "Rate limited: class=%s limit=%s (further refusals in this "
                "window are suppressed)", class_name, limit
            )
        self._send_rate_limited(limit, remaining, reset_after)
        return False

    def do_GET(self):
        if not self._rate_limit_ok(None):
            return
        self.handle_request(None)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None
        if not self._rate_limit_ok(body):
            return
        self.handle_request(body)

    def _is_multipart_file_upload(self):
        content_type = self.headers.get("Content-Type", "")
        return "multipart/form-data" in content_type

    def _is_torrent_file_field(self, body):
        content_disposition = self.headers.get("Content-Disposition", "")
        return False

    def handle_request(self, body):
        try:
            path = urllib.parse.urlparse(self.path).path

            if path == "/api/v2/torrents/add" and self.command == "POST" and body:
                if self._is_multipart_file_upload():
                    logger.info("Multipart file upload detected, passing through directly")
                    self.proxy_to_qbittorrent(body)
                    return

                try:
                    body_str = body.decode("utf-8")
                except (UnicodeDecodeError, ValueError):
                    logger.info("Binary body detected, passing through directly")
                    self.proxy_to_qbittorrent(body)
                    return

                params = urllib.parse.parse_qs(body_str)
                urls = params.get("urls", [""])[0]

                if urls:
                    plugin = identify_plugin(urls)
                    if plugin:
                        logger.info(f"Intercepting {plugin} URL: {urls[:80]}...")

                        torrent_file = download_via_nova2dl(plugin, urls)

                        if torrent_file:
                            params["urls"] = [f"file://{torrent_file}"]
                            # IMPORTANT-2: attach content tags here — this is
                            # the last point before qBittorrent sees the add,
                            # and the downloaded filename is the offline
                            # quality signal. Any tags the client already sent
                            # are preserved, never overwritten.
                            derived = build_tag_field(torrent_file)
                            if derived:
                                merged = merge_tag_values(params.get("tags", [""])[0], derived)
                                params["tags"] = [merged]
                                logger.info(f"Applying tags: {merged}")
                            new_body = urllib.parse.urlencode(params, doseq=True).encode("utf-8")

                            self.proxy_to_qbittorrent(new_body)

                            try:
                                os.unlink(torrent_file)
                            except OSError:
                                pass
                            return
                        else:
                            logger.error("Failed to download torrent")
                            self.send_error(502, "Failed to download torrent")
                            return

            self.proxy_to_qbittorrent(body)

        except Exception as e:
            logger.error(f"Error handling request: {e}")
            try:
                self.send_error(500, str(e))
            except Exception:
                pass

    def proxy_to_qbittorrent(self, body):
        try:
            target_url = f"http://{QBITTORRENT_HOST}:{QBITTORRENT_PORT}{self.path}"
            req = urllib.request.Request(target_url, data=body, method=self.command)

            for header, value in self.headers.items():
                header_lower = header.lower()
                if header_lower not in ["host", "content-length"]:
                    if header_lower == "referer":
                        value = f"http://localhost:{QBITTORRENT_PORT}"
                    elif header_lower == "origin":
                        value = f"http://localhost:{QBITTORRENT_PORT}"
                    req.add_header(header, value)

            with urllib.request.urlopen(req, timeout=30) as response:
                # BYTE-FOR-BYTE PASS-THROUGH. The proxy MUST NOT rewrite
                # qBittorrent's HTML, CSS, JS or headers. The themed-WebUI
                # overlay that used to live here was removed 2026-09-01 by
                # operator decision: it implemented zero qBittorrent
                # features and its `qBittorrent` -> `Боба` rebrand rewrote
                # the token INSIDE inline <script> blocks (external .js
                # files were skipped), so the WebUI's own JS namespace
                # vanished and every page died on a ReferenceError.
                # Regression guard:
                # tests/integration/test_vanilla_webui_unmodified.py
                #
                # Content-Encoding is forwarded untouched, so gzip/deflate
                # bodies are relayed exactly as qBittorrent compressed them
                # — nothing here needs to read the body.
                content = response.read()

                self.send_response(response.status)
                for header, value in response.headers.items():
                    if header.lower() in ("transfer-encoding", "content-length"):
                        continue
                    self.send_header(header, value)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()

                self.wfile.write(content)

        except urllib.request.HTTPError as e:
            logger.error(f"HTTP Error {e.code}: {e.reason}")
            try:
                self.send_error(e.code, e.reason)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error proxying to qBittorrent: {e}")
            try:
                self.send_error(502, "Bad Gateway")
            except Exception:
                pass


def run_server():
    server_address = ("", PROXY_PORT)
    httpd = ThreadingHTTPServer(server_address, DownloadHandler)

    logger.info("=" * 60)
    logger.info("Download Proxy Server Started")
    logger.info(f"Proxy Port: {PROXY_PORT}")
    logger.info(f"qBittorrent backend: http://{QBITTORRENT_HOST}:{QBITTORRENT_PORT}")
    logger.info(f"Supported trackers: {_supported_tracker_names()}")
    logger.info("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    run_server()
