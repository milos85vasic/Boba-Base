#!/usr/bin/env python3
"""
Download Proxy for Боба WebUI - Fixed version
Intercepts RuTracker URLs and downloads via nova2dl.py with authentication
Passes through all other requests (including magnet links).

Also injects a two-file theme bridge
(``/__qbit_theme__/skin.css`` + ``/__qbit_theme__/bootstrap.js``)
into every HTML response so the Боба WebUI picks up the
palette chosen in the Angular dashboard at :7187. See
docs/CROSS_APP_THEME_PLAN.md.
"""

import sys
import os
import json
import gzip
import zlib
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
# Where the bridge can find the merge service (default port 7187).
MERGE_SERVICE_URL = os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187")

PLUGIN_PATTERNS = {
    "rutracker": [r"rutracker\.org", r"rutracker\.net", r"rutracker\.nl"],
    "kinozal": [r"kinozal\.tv", r"kinozal\.me"],
    "nnmclub": [r"nnmclub\.to", r"nnm-club\.me"],
    "iptorrents": [r"iptorrents\.(com|me|org)"],
}

COMPILED_PATTERNS = {plugin: [re.compile(p, re.I) for p in patterns] for plugin, patterns in PLUGIN_PATTERNS.items()}


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
#   proxy           — WebUI passthrough + theme/logo assets. GENEROUS.
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



def identify_plugin(url):
    for plugin, patterns in COMPILED_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(url):
                return plugin
    return None


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


# ---------------------------------------------------------------------- theme
#
# The Боба WebUI is qBittorrent's own code — it ignores our
# design system. To keep the two ports visually consistent, every HTML
# response flowing through this proxy is rewritten so a tiny CSS + JS
# pair is loaded from ``/__qbit_theme__/``. The bridge pulls the active
# palette from the merge service at :7187 and applies the tokens to
# ``document.documentElement`` plus a handful of high-level overrides.
#
# The palette catalog below mirrors
# ``frontend/src/app/models/palette.model.ts`` — a lockstep test
# (``tests/unit/test_palette_catalog_python_mirror.py``) keeps the two
# copies in sync.

THEME_PALETTES: dict[str, dict[str, dict[str, str]]] = {
    "darcula": {
        "dark": {
            "bgPrimary": "#2b2b2b",
            "bgSecondary": "#3c3f41",
            "bgTertiary": "#4e5254",
            "border": "#555555",
            "textPrimary": "#a9b7c6",
            "textSecondary": "#808080",
            "accent": "#9d001e",
            "accentHover": "#c4002a",
            "contrast": "#d9a441",
            "success": "#6a8759",
            "danger": "#cc7832",
            "warning": "#d9a441",
            "info": "#6897bb",
            "purple": "#9876aa",
            "shadow": "rgba(0,0,0,0.55)",
        },
        "light": {
            "bgPrimary": "#ffffff",
            "bgSecondary": "#f2f2f2",
            "bgTertiary": "#e4e4e4",
            "border": "#c9c9c9",
            "textPrimary": "#1c1c1c",
            "textSecondary": "#555555",
            "accent": "#9d001e",
            "accentHover": "#7d0017",
            "contrast": "#b07d1f",
            "success": "#0a7b28",
            "danger": "#c9302c",
            "warning": "#b07d1f",
            "info": "#1e6fa8",
            "purple": "#6f42c1",
            "shadow": "rgba(0,0,0,0.12)",
        },
    },
    "dracula": {
        "dark": {
            "bgPrimary": "#282a36",
            "bgSecondary": "#343746",
            "bgTertiary": "#44475a",
            "border": "#6272a4",
            "textPrimary": "#f8f8f2",
            "textSecondary": "#bfbfbf",
            "accent": "#ff79c6",
            "accentHover": "#ff92d0",
            "contrast": "#bd93f9",
            "success": "#50fa7b",
            "danger": "#ff5555",
            "warning": "#f1fa8c",
            "info": "#8be9fd",
            "purple": "#bd93f9",
            "shadow": "rgba(0,0,0,0.55)",
        },
        "light": {
            "bgPrimary": "#f8f8f2",
            "bgSecondary": "#eeeeec",
            "bgTertiary": "#e0e0da",
            "border": "#c9c9c0",
            "textPrimary": "#282a36",
            "textSecondary": "#6272a4",
            "accent": "#d6336c",
            "accentHover": "#bd255a",
            "contrast": "#7048e8",
            "success": "#2b8a3e",
            "danger": "#c92a2a",
            "warning": "#b08900",
            "info": "#1c7ed6",
            "purple": "#6741d9",
            "shadow": "rgba(0,0,0,0.12)",
        },
    },
    "solarized": {
        "dark": {
            "bgPrimary": "#002b36",
            "bgSecondary": "#073642",
            "bgTertiary": "#0a4453",
            "border": "#586e75",
            "textPrimary": "#93a1a1",
            "textSecondary": "#657b83",
            "accent": "#268bd2",
            "accentHover": "#2aa198",
            "contrast": "#b58900",
            "success": "#859900",
            "danger": "#dc322f",
            "warning": "#b58900",
            "info": "#268bd2",
            "purple": "#6c71c4",
            "shadow": "rgba(0,0,0,0.55)",
        },
        "light": {
            "bgPrimary": "#fdf6e3",
            "bgSecondary": "#eee8d5",
            "bgTertiary": "#d9d2bf",
            "border": "#93a1a1",
            "textPrimary": "#073642",
            "textSecondary": "#657b83",
            "accent": "#268bd2",
            "accentHover": "#1d70ad",
            "contrast": "#b58900",
            "success": "#859900",
            "danger": "#dc322f",
            "warning": "#b58900",
            "info": "#268bd2",
            "purple": "#6c71c4",
            "shadow": "rgba(0,0,0,0.12)",
        },
    },
    "nord": {
        "dark": {
            "bgPrimary": "#2e3440",
            "bgSecondary": "#3b4252",
            "bgTertiary": "#434c5e",
            "border": "#4c566a",
            "textPrimary": "#eceff4",
            "textSecondary": "#d8dee9",
            "accent": "#88c0d0",
            "accentHover": "#8fbcbb",
            "contrast": "#ebcb8b",
            "success": "#a3be8c",
            "danger": "#bf616a",
            "warning": "#ebcb8b",
            "info": "#81a1c1",
            "purple": "#b48ead",
            "shadow": "rgba(0,0,0,0.55)",
        },
        "light": {
            "bgPrimary": "#eceff4",
            "bgSecondary": "#e5e9f0",
            "bgTertiary": "#d8dee9",
            "border": "#b8c0ce",
            "textPrimary": "#2e3440",
            "textSecondary": "#4c566a",
            "accent": "#5e81ac",
            "accentHover": "#4c6e95",
            "contrast": "#d08770",
            "success": "#5b8c3a",
            "danger": "#bf616a",
            "warning": "#b08900",
            "info": "#81a1c1",
            "purple": "#b48ead",
            "shadow": "rgba(0,0,0,0.12)",
        },
    },
    "monokai": {
        "dark": {
            "bgPrimary": "#272822",
            "bgSecondary": "#383830",
            "bgTertiary": "#49483e",
            "border": "#75715e",
            "textPrimary": "#f8f8f2",
            "textSecondary": "#cfcfc2",
            "accent": "#f92672",
            "accentHover": "#ff4890",
            "contrast": "#a6e22e",
            "success": "#a6e22e",
            "danger": "#f92672",
            "warning": "#fd971f",
            "info": "#66d9ef",
            "purple": "#ae81ff",
            "shadow": "rgba(0,0,0,0.55)",
        },
        "light": {
            "bgPrimary": "#fafaf5",
            "bgSecondary": "#ededeb",
            "bgTertiary": "#dddbcf",
            "border": "#b0ad9e",
            "textPrimary": "#272822",
            "textSecondary": "#75715e",
            "accent": "#d63384",
            "accentHover": "#b5256e",
            "contrast": "#689822",
            "success": "#689822",
            "danger": "#c02450",
            "warning": "#c6660a",
            "info": "#2a9ab4",
            "purple": "#7a4ddb",
            "shadow": "rgba(0,0,0,0.12)",
        },
    },
    "gruvbox": {
        "dark": {
            "bgPrimary": "#282828",
            "bgSecondary": "#3c3836",
            "bgTertiary": "#504945",
            "border": "#665c54",
            "textPrimary": "#ebdbb2",
            "textSecondary": "#a89984",
            "accent": "#fb4934",
            "accentHover": "#cc241d",
            "contrast": "#fabd2f",
            "success": "#b8bb26",
            "danger": "#fb4934",
            "warning": "#fabd2f",
            "info": "#83a598",
            "purple": "#d3869b",
            "shadow": "rgba(0,0,0,0.55)",
        },
        "light": {
            "bgPrimary": "#fbf1c7",
            "bgSecondary": "#ebdbb2",
            "bgTertiary": "#d5c4a1",
            "border": "#bdae93",
            "textPrimary": "#3c3836",
            "textSecondary": "#665c54",
            "accent": "#9d0006",
            "accentHover": "#79111e",
            "contrast": "#b57614",
            "success": "#79740e",
            "danger": "#9d0006",
            "warning": "#b57614",
            "info": "#076678",
            "purple": "#8f3f71",
            "shadow": "rgba(0,0,0,0.12)",
        },
    },
    "one-dark": {
        "dark": {
            "bgPrimary": "#282c34",
            "bgSecondary": "#353b45",
            "bgTertiary": "#3e4451",
            "border": "#4b5263",
            "textPrimary": "#abb2bf",
            "textSecondary": "#7f848e",
            "accent": "#61afef",
            "accentHover": "#4e96d6",
            "contrast": "#e5c07b",
            "success": "#98c379",
            "danger": "#e06c75",
            "warning": "#e5c07b",
            "info": "#56b6c2",
            "purple": "#c678dd",
            "shadow": "rgba(0,0,0,0.55)",
        },
        "light": {
            "bgPrimary": "#fafafa",
            "bgSecondary": "#eaeaeb",
            "bgTertiary": "#d3d3d5",
            "border": "#a0a1a7",
            "textPrimary": "#383a42",
            "textSecondary": "#696c77",
            "accent": "#4078f2",
            "accentHover": "#2e62cc",
            "contrast": "#986801",
            "success": "#50a14f",
            "danger": "#e45649",
            "warning": "#c18401",
            "info": "#0184bc",
            "purple": "#a626a4",
            "shadow": "rgba(0,0,0,0.12)",
        },
    },
    "tokyo-night": {
        "dark": {
            "bgPrimary": "#1a1b26",
            "bgSecondary": "#24283b",
            "bgTertiary": "#2f344d",
            "border": "#414868",
            "textPrimary": "#c0caf5",
            "textSecondary": "#a9b1d6",
            "accent": "#7aa2f7",
            "accentHover": "#6a91e6",
            "contrast": "#e0af68",
            "success": "#9ece6a",
            "danger": "#f7768e",
            "warning": "#e0af68",
            "info": "#7dcfff",
            "purple": "#bb9af7",
            "shadow": "rgba(0,0,0,0.55)",
        },
        "light": {
            "bgPrimary": "#e6e7ed",
            "bgSecondary": "#d5d6db",
            "bgTertiary": "#c4c7d0",
            "border": "#989caf",
            "textPrimary": "#343b58",
            "textSecondary": "#565a6e",
            "accent": "#34548a",
            "accentHover": "#2a4471",
            "contrast": "#8f5e15",
            "success": "#485e30",
            "danger": "#8c4351",
            "warning": "#8f5e15",
            "info": "#2a6194",
            "purple": "#5a3e8e",
            "shadow": "rgba(0,0,0,0.12)",
        },
    },
}


THEME_SKIN_CSS = """\
/* Боба WebUI theme bridge.
 * Populated with the Darcula-dark fallback; bootstrap.js overrides
 * these with the live palette (and reacts to SSE theme events).
 */
:root {
  --color-bg-primary:     #2b2b2b;
  --color-bg-secondary:   #3c3f41;
  --color-bg-tertiary:    #4e5254;
  --color-border:         #555555;
  --color-text-primary:   #a9b7c6;
  --color-text-secondary: #808080;
  --color-accent:         #9d001e;
  --color-accent-hover:   #c4002a;
  --color-contrast:       #d9a441;
  --color-success:        #6a8759;
  --color-danger:         #cc7832;
  --color-warning:        #d9a441;
  --color-info:           #6897bb;
  --color-purple:         #9876aa;
  --color-shadow:         rgba(0,0,0,0.55);
}

/* Боба WebUI overrides — target its actual class/id names. */
html, body {
  background: var(--color-bg-primary) !important;
  color: var(--color-text-primary) !important;
}
#desktop, #mainWindowTabs, #filterTitle, .sidebar,
.scroll_container, dialog, .MochaMenu, .propContent,
#rssFeedFixedHeightContainer, #tabs, .MochaTab {
  background: var(--color-bg-secondary) !important;
  color: var(--color-text-primary) !important;
  border-color: var(--color-border) !important;
}
a { color: var(--color-accent); }
a:hover { color: var(--color-accent-hover); }
button, input[type="button"], input[type="submit"], .mochaToolButtonText {
  background: var(--color-accent);
  color: #fff;
  border: 1px solid var(--color-accent-hover);
}
button:hover, input[type="button"]:hover, input[type="submit"]:hover {
  background: var(--color-accent-hover);
}
.dynamicTable_pane, .dynamicTable {
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
}
.dynamicTable th, .dynamicTable_headerBackgroundContainer {
  background: var(--color-bg-tertiary);
  color: var(--color-accent);
}
"""


def _build_theme_bootstrap_js() -> str:
    """Materialise bootstrap.js with the palette catalog inlined.

    The catalog is emitted as a Python dict via ``json.dumps`` so the
    bytes sent to the browser are always valid JSON, regardless of how
    the catalog grows. Keeping the catalog inline avoids a second
    CORS round-trip from the :7186 origin.
    """
    catalog_json = json.dumps(THEME_PALETTES, indent=2)
    js = f"""\
// Боба WebUI theme bridge — loaded on every HTML page served by
// the download-proxy on :7186. Fetches the active palette from the
// merge service and subscribes to live updates via SSE so palette swaps
// made in the Angular dashboard mirror here without a manual refresh.

(function () {{
  "use strict";
  var MERGE = (window.__MERGE_SERVICE_URL__ || ('http://' + window.location.hostname + ':7187'));
  var CATALOG = {catalog_json};
  window.__QBIT_PALETTE_CATALOG__ = CATALOG;

  var KEYS = [
    "bg-primary","bg-secondary","bg-tertiary","border","text-primary",
    "text-secondary","accent","accent-hover","contrast","success","danger",
    "warning","info","purple","shadow"
  ];
  function camel(k) {{
    return k.replace(/-([a-z])/g, function (_, c) {{ return c.toUpperCase(); }});
  }}
  function apply(tokens) {{
    var doc = document.documentElement;
    for (var i = 0; i < KEYS.length; i++) {{
      var k = KEYS[i];
      var v = tokens[camel(k)];
      if (v) doc.style.setProperty("--color-" + k, v);
    }}
  }}
  function tokensFor(paletteId, mode) {{
    var entry = CATALOG[paletteId] || CATALOG["darcula"];
    return entry[mode] || entry["dark"];
  }}
  var lastUpdatedAt = null;
  function adopt(state) {{
    if (!state || !state.paletteId || !state.mode) return;
    if (lastUpdatedAt && state.updatedAt && state.updatedAt === lastUpdatedAt) return;
    lastUpdatedAt = state.updatedAt || null;
    apply(tokensFor(state.paletteId, state.mode));
    var doc = document.documentElement;
    doc.setAttribute("data-palette", state.paletteId);
    doc.setAttribute("data-mode", state.mode);
    doc.style.setProperty("color-scheme", state.mode);
    window.__qbitTheme = state;
  }}
  function boot() {{
    // Preseed with Darcula dark so unstyled flashes are minimal.
    apply(tokensFor("darcula", "dark"));
    if (typeof fetch !== "function") return;
    fetch(MERGE + "/api/v1/theme", {{credentials: "omit"}})
      .then(function (r) {{ if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }})
      .then(adopt)
      .catch(function (e) {{ try {{ console.warn("qbit-theme: using fallback", e); }} catch (_) {{}} }});
    try {{
      var es = new EventSource(MERGE + "/api/v1/theme/stream");
      es.addEventListener("theme", function (ev) {{
        try {{ adopt(JSON.parse(ev.data)); }} catch (_) {{}}
      }});
    }} catch (_) {{
      /* no live updates available */
    }}
  }}
  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", boot);
  }} else {{
    boot();
  }}
}})();
"""
    return js


THEME_BOOTSTRAP_JS = _build_theme_bootstrap_js()

THEME_INJECTION_MARKER = "/__qbit_theme__/skin.css"
_THEME_HEAD_TAGS = (
    '<link rel="stylesheet" href="/__qbit_theme__/skin.css">\n'
    '<script src="/__qbit_theme__/bootstrap.js" defer></script>\n'
)
_HEAD_CLOSE_RE = re.compile(rb"</head\s*>", re.IGNORECASE)


def _merge_service_origin() -> str:
    """Return the origin of the merge service for CSP whitelisting.

    Боба ships a strict CSP header (``default-src 'self'; ...``)
    that, without the ``connect-src`` directive, blocks the bridge's
    ``fetch('/api/v1/theme')`` + ``EventSource(...)`` calls cross-origin.
    We whitelist the merge-service origin in the CSP the browser sees.
    """
    from urllib.parse import urlparse

    parsed = urlparse(MERGE_SERVICE_URL)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if scheme == "https" else 7187)
    return f"{scheme}://{host}:{port}"


MERGE_SERVICE_ORIGIN = _merge_service_origin()


_CSP_DIRECTIVE_RE = re.compile(r"\s*([^;\s]+)(?:\s+([^;]*))?\s*;?", re.I)


def rewrite_csp(header_value: str) -> str:
    """Relax Боба's Content-Security-Policy so the theme bridge
    can talk to the merge service.

    Adds the merge-service origin to ``connect-src`` (creating the
    directive if qBittorrent didn't set one). Idempotent. If the input
    is blank, returns it unchanged.
    """
    if not header_value or _theme_injection_disabled():
        return header_value
    origin = MERGE_SERVICE_ORIGIN
    directives: list[tuple[str, str]] = []
    for part in header_value.split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, rest = part.partition(" ")
        directives.append((name.lower(), rest.strip()))

    seen_connect = False
    new_directives: list[tuple[str, str]] = []
    for name, value in directives:
        if name == "connect-src":
            seen_connect = True
            if origin not in value.split():
                value = (value + " " + origin).strip()
        new_directives.append((name, value))
    if not seen_connect:
        # Fall back to default-src if present, extended with our origin.
        default_src = next((v for n, v in directives if n == "default-src"), "'self'")
        if origin not in default_src.split():
            default_src = (default_src + " " + origin).strip()
        new_directives.append(("connect-src", default_src))
    return "; ".join(f"{n} {v}".strip() for n, v in new_directives)


def _theme_injection_disabled() -> bool:
    return os.environ.get("DISABLE_THEME_INJECTION") == "1"


def _maybe_decode_body(body: bytes, content_encoding: str) -> tuple[bytes, bool]:
    """Return (decoded_bytes, decoded_flag).

    ``decoded_flag`` is True only when we successfully turned a gzip /
    deflate payload back into plain text so the injector can mutate
    it. Anything we can't decode (br, zstd, unknown) is returned as
    the original bytes with the flag False — the caller should then
    skip the rewrite and pass the response through untouched.
    """
    if not content_encoding:
        return body, True
    enc = content_encoding.lower().strip()
    try:
        if enc == "gzip":
            return gzip.decompress(body), True
        if enc == "deflate":
            try:
                return zlib.decompress(body), True
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS), True
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug(f"could not decompress {enc}: {exc}")
    return body, False


def inject_theme_assets(body: bytes, content_type: str) -> bytes:
    """Return ``body`` with the two theme-bridge tags injected before
    ``</head>``. Passes through unchanged when:

    * ``body`` is not HTML (``content_type`` doesn't start with ``text/html``),
    * ``body`` already contains our sentinel (idempotency),
    * there is no ``</head>`` tag,
    * the ``DISABLE_THEME_INJECTION=1`` escape hatch is active.
    """
    if _theme_injection_disabled():
        return body
    if not content_type or not content_type.lower().startswith("text/html"):
        return body
    if THEME_INJECTION_MARKER.encode("ascii") in body:
        return body
    match = _HEAD_CLOSE_RE.search(body)
    if not match:
        return body
    # Inject just before the </head> tag preserving the original casing.
    insertion = _THEME_HEAD_TAGS.encode("utf-8")
    return body[: match.start()] + insertion + body[match.start() :]


def serve_theme_asset(path: str) -> tuple[int, dict[str, str], bytes]:
    """Return (status, headers, body) for a ``/__qbit_theme__/*`` request.

    Kept as a pure function so unit tests can poke it without
    standing up the HTTP server.
    """
    if path == "/__qbit_theme__/skin.css":
        payload = THEME_SKIN_CSS.encode("utf-8")
        headers = {
            "Content-Type": "text/css; charset=utf-8",
            "Cache-Control": "no-cache",
            "Content-Length": str(len(payload)),
        }
        return 200, headers, payload
    if path == "/__qbit_theme__/bootstrap.js":
        payload = THEME_BOOTSTRAP_JS.encode("utf-8")
        headers = {
            "Content-Type": "application/javascript; charset=utf-8",
            "Cache-Control": "no-cache",
            "Content-Length": str(len(payload)),
        }
        return 200, headers, payload
    payload = b"Not Found"
    return (
        404,
        {
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Length": str(len(payload)),
        },
        payload,
    )


# ---------------------------------------------------------------------------
# Re-branding: qBittorrent → Боба (duplicated from theme_injector.py so
# download_proxy.py stays self-contained)
# ---------------------------------------------------------------------------

_BOBA_LOGO_PATH = "/images/boba-logo.jpeg"

_REBRAND_PATTERNS = [
    (re.compile(r'src="images/qbittorrent-tray\.svg"', re.IGNORECASE), 'src="/images/boba-logo.jpeg"'),
    (re.compile(r"src='images/qbittorrent-tray\.svg'", re.IGNORECASE), 'src="/images/boba-logo.jpeg"'),
    (re.compile(r'src="images/qbittorrent32\.png"', re.IGNORECASE), 'src="/images/boba-logo.jpeg"'),
    (re.compile(r"src='images/qbittorrent32\.png'", re.IGNORECASE), 'src="/images/boba-logo.jpeg"'),
    (re.compile(r'href="images/qbittorrent-tray\.svg"', re.IGNORECASE), 'href="/images/boba-logo.jpeg"'),
    (re.compile(r"href='images/qbittorrent-tray\.svg'", re.IGNORECASE), 'href="/images/boba-logo.jpeg"'),
    (re.compile(r'href="images/qbittorrent32\.png"', re.IGNORECASE), 'href="/images/boba-logo.jpeg"'),
    (re.compile(r"href='images/qbittorrent32\.png'", re.IGNORECASE), 'href="/images/boba-logo.jpeg"'),
    (re.compile(r'alt="qBittorrent logo"', re.IGNORECASE), 'alt="Боба logo"'),
    (re.compile(r"alt='qBittorrent logo'", re.IGNORECASE), 'alt="Боба logo"'),
    (re.compile(r"<title>qBittorrent", re.IGNORECASE), "<title>Боба"),
    (re.compile(r'content="qBittorrent WebUI"', re.IGNORECASE), 'content="Боба WebUI"'),
    (re.compile(r"content='qBittorrent WebUI'", re.IGNORECASE), 'content="Боба WebUI"'),
    (re.compile(r"qBittorrent", re.IGNORECASE), "Боба"),
]

_BOBA_LOGO_BYTES: bytes | None = None
_BOBA_LOGO_PATH_ON_DISK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "static",
    "boba-logo.jpeg",
)


def _load_boba_logo() -> bytes:
    global _BOBA_LOGO_BYTES
    if _BOBA_LOGO_BYTES is None:
        try:
            with open(_BOBA_LOGO_PATH_ON_DISK, "rb") as f:
                _BOBA_LOGO_BYTES = f.read()
        except Exception:
            _BOBA_LOGO_BYTES = b""
    return _BOBA_LOGO_BYTES


def is_boba_logo_request(path: str) -> bool:
    return path == _BOBA_LOGO_PATH


def serve_boba_logo() -> tuple[int, dict[str, str], bytes]:
    payload = _load_boba_logo()
    if not payload:
        payload = b"Not Found"
        return (
            404,
            {
                "Content-Type": "text/plain; charset=utf-8",
                "Content-Length": str(len(payload)),
            },
            payload,
        )
    return (
        200,
        {
            "Content-Type": "image/jpeg",
            "Cache-Control": "public, max-age=604800",
            "Content-Length": str(len(payload)),
        },
        payload,
    )


def rebrand_html(body: bytes, content_type: str) -> bytes:
    if not content_type or not content_type.lower().startswith("text/html"):
        return body
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    for pattern, replacement in _REBRAND_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.encode("utf-8")


class DownloadHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        if "/api/" in self.path:
            logger.info(f"{self.address_string()} - {format % args}")

    # -- BOB-111 rate limiting ------------------------------------------
    # Charged at the TOP of every entry point, before ANY work: before the
    # logo/theme short-circuits, before the qBittorrent round-trip and before
    # the nova2dl fan-out. A limiter that only guards the expensive branch
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
        if self._serve_boba_logo():
            return
        if self._serve_theme_bridge():
            return
        self.handle_request(None)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None
        if not self._rate_limit_ok(body):
            return
        self.handle_request(body)

    def _serve_boba_logo(self) -> bool:
        """Short-circuit Boba logo requests so they never hit qBittorrent."""
        try:
            path = urllib.parse.urlparse(self.path).path
        except Exception:
            return False
        if not is_boba_logo_request(path):
            return False
        status, headers, payload = serve_boba_logo()
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:
            pass
        return True

    def _serve_theme_bridge(self) -> bool:
        """Short-circuit the two proxy-local theme routes."""
        try:
            path = urllib.parse.urlparse(self.path).path
        except Exception:
            return False
        if not path.startswith("/__qbit_theme__/"):
            return False
        status, headers, payload = serve_theme_asset(path)
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except BrokenPipeError:
            pass
        return True

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
                content_type = response.headers.get("Content-Type", "") or ""
                content_encoding = (response.headers.get("Content-Encoding") or "").lower().strip()
                content = response.read()

                # Inject the theme bridge into HTML responses so the
                # qBittorrent WebUI picks up the dashboard's palette.
                # Also rebrand qBittorrent → Боба and swap the logo.
                is_html = content_type.lower().startswith("text/html")
                decoded_for_injection = False
                if is_html:
                    decoded, decoded_for_injection = _maybe_decode_body(content, content_encoding)
                    if decoded_for_injection:
                        new_decoded = inject_theme_assets(decoded, content_type)
                        new_decoded = rebrand_html(new_decoded, content_type)
                        if new_decoded is not decoded:
                            # Serve the response un-encoded so the browser
                            # doesn't misinterpret our plain-text insertion.
                            content = new_decoded
                            content_encoding = ""
                    else:
                        content = inject_theme_assets(content, content_type)
                        content = rebrand_html(content, content_type)

                self.send_response(response.status)
                for header, value in response.headers.items():
                    h = header.lower()
                    if h in ("transfer-encoding", "content-length"):
                        continue
                    # Drop Content-Encoding if we rewrote the body in place.
                    if h == "content-encoding" and is_html and decoded_for_injection and not content_encoding:
                        continue
                    # Relax qBittorrent's CSP so the injected bridge
                    # can fetch + stream from the merge service on
                    # :7187 without being blocked by connect-src.
                    if is_html and h == "content-security-policy":
                        value = rewrite_csp(value)
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
    logger.info(f"Supported trackers: {list(PLUGIN_PATTERNS.keys())}")
    logger.info(f"Theme bridge -> {MERGE_SERVICE_URL}")
    logger.info("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    run_server()
