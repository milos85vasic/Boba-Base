"""
Core data models for the merge service.
"""

import asyncio
import contextlib
import logging
import os
import re as _re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from cachetools import TTLCache

from .retry import retry_policy

_TRACKER_NAME_RE = _re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_tracker_name(name: str) -> str:
    if not name or not _TRACKER_NAME_RE.match(name):
        raise ValueError(f"Invalid tracker name: {name!r}")
    return name


class ContentType(Enum):
    MOVIE = "movie"
    TV_SHOW = "tv"
    ANIME = "anime"
    MUSIC = "music"
    AUDIOBOOK = "audiobook"
    GAME = "game"
    SOFTWARE = "software"
    EBOOK = "ebook"
    OTHER = "other"
    UNKNOWN = "unknown"


class QualityTier(Enum):
    SD = "sd"
    HD = "hd"
    FULL_HD = "full_hd"
    UHD_4K = "uhd_4k"
    UHD_8K = "uhd_8k"
    UNKNOWN = "unknown"


@dataclass
class TrackerSource:
    name: str
    url: str
    enabled: bool = True
    last_checked: datetime | None = None
    health_status: str = "unknown"
    scrape_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "enabled": self.enabled,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
            "health_status": self.health_status,
            "scrape_url": self.scrape_url,
        }


@dataclass
class CanonicalIdentity:
    infohash: str | None = None
    title: str | None = None
    year: int | None = None
    content_type: ContentType | None = None
    season: int | None = None
    episode: int | None = None
    resolution: str | None = None
    codec: str | None = None
    group: str | None = None
    metadata_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "infohash": self.infohash,
            "title": self.title,
            "year": self.year,
            "content_type": self.content_type.value if self.content_type else None,
            "season": self.season,
            "episode": self.episode,
            "resolution": self.resolution,
            "codec": self.codec,
            "group": self.group,
            "metadata_source": self.metadata_source,
        }


@dataclass
class SearchResult:
    name: str
    link: str
    size: str
    seeds: int
    leechers: int
    engine_url: str
    desc_link: str | None = None
    pub_date: str | None = None
    tracker: str | None = None
    category: str | None = None
    freeleech: bool = False
    content_type: str | None = None
    quality: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "link": self.link,
            "size": self.size,
            "seeds": self.seeds,
            "leechers": self.leechers,
            "engine_url": self.engine_url,
            "desc_link": self.desc_link,
            "pub_date": self.pub_date,
            "tracker": self.tracker,
            "category": self.category,
            "freeleech": self.freeleech,
            "content_type": self.content_type,
            "quality": self.quality,
        }
        if self.freeleech and self.tracker:
            d["tracker_display"] = f"{self.tracker} [free]"
        elif self.tracker:
            d["tracker_display"] = self.tracker
        else:
            d["tracker_display"] = None
        return d


def _detect_result_metadata(name: str, size: str) -> tuple[str | None, str | None]:
    """Infer content_type and quality from a raw torrent name and size."""
    n = name.lower() if name else ""

    # --- content_type ---
    content_type = None
    if _re.search(r"\[anime\]", n):
        content_type = "anime"
    elif _re.search(r"[sS]\d+[eE]\d+|\b(seasons?)\s*[\d\-]+\b|\b(episode)\s*[\d\-]+\b", n):
        content_type = "tv"
    elif _re.search(r"\baudiobook\b", n):
        content_type = "audiobook"
    elif any(
        p in n
        for p in [
            "codex",
            "tenoke",
            "fitgirl",
            "masquerade",
            "xbox",
            "playstation",
            "ps3",
            "ps4",
            "ps5",
            "nintendo",
            "switch",
            "steam",
            "epic",
            "vr",
        ]
    ):
        content_type = "game"
    elif _re.search(
        r"\b(x86|x64|portable|\.exe|installer|iso|dmg|appimage|snap|flatpak|pkg|deb|rpm|msi)\b", n
    ) or _re.search(
        r"\b(ubuntu|debian|fedora|arch linux|linux mint|opensuse|centos|redhat|gentoo|slackware|kali|manjaro|pop!_os|elementary)\b",
        n,
    ):
        content_type = "software"
    elif _re.search(
        r"\b(bluray|blu-ray|bdremux|web-?dl|webrip|h?drip|dvdrip|bdrip|x264|x265|hevc|hdr)\b", n
    ) or _re.search(r"\b(720p|1080p|2160p|4k)\b", n):
        content_type = "movie"
    elif _re.search(r"\b(epub|pdf|mobi|azw3|cbz|cbr|djvu)\b", n):
        content_type = "ebook"
    elif (
        _re.search(r"\b(mp3|flac|ogg|opus|aac|wav|aiff|alac|m4a|wma)\b", n)
        or _re.search(r"\b(lossless|320kbps|256kbps|128kbps|v0|vbr|cbr|v2)\b", n)
        or _re.search(r"\b(ost|soundtrack|score)\b", n)
    ):
        content_type = "music"

    # --- quality ---
    quality = None
    if _re.search(r"2160p|4k|uhd", n):
        quality = "uhd_4k"
    elif _re.search(r"1080p|fullhd|fhd", n):
        quality = "full_hd"
    elif _re.search(r"720p|hdrip", n):
        quality = "hd"
    elif _re.search(r"480p|sd|camrip", n):
        quality = "sd"
    elif "bluray" in n or "blu-ray" in n or "bdrip" in n or "bd-remux" in n:
        quality = "full_hd"
    elif "web-dl" in n or "webrip" in n or "web.dl" in n or "webdl" in n or "hdtv" in n:
        quality = "hd"
    elif "dvd" in n:
        quality = "sd"
    else:
        # Size-based fallback
        try:
            sb = float(size)
        except (ValueError, TypeError):
            sb = 0
            m = _re.search(r"([\d.]+)\s*(TB|GB|MB|KB|B)", str(size), _re.I)
            if m:
                value = float(m.group(1))
                unit = m.group(2).upper()
                mult = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
                sb = value * mult.get(unit, 1)
        if sb >= 40 * 1024**3:
            quality = "uhd_4k"
        elif sb >= 8 * 1024**3:
            quality = "full_hd"
        elif sb >= 2 * 1024**3:
            quality = "hd"
        elif sb >= 300 * 1024**2:
            quality = "sd"

    return content_type, quality


@dataclass
class MergedResult:
    canonical_identity: CanonicalIdentity
    original_results: list[SearchResult] = field(default_factory=list)
    total_seeds: int = 0
    total_leechers: int = 0
    best_quality: QualityTier | None = None
    download_urls: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_source(self, result: SearchResult) -> None:
        self.original_results.append(result)
        self.total_seeds += result.seeds
        self.total_leechers += result.leechers
        if result.link not in self.download_urls:
            self.download_urls.append(result.link)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_identity": self.canonical_identity.to_dict(),
            "sources": [
                {"tracker": r.tracker, "seeds": r.seeds, "leechers": r.leechers} for r in self.original_results
            ],
            "total_seeds": self.total_seeds,
            "total_leechers": self.total_leechers,
            "best_quality": self.best_quality.value if self.best_quality else None,
            "download_urls": self.download_urls,
            "created_at": self.created_at.isoformat(),
        }


def _classify_plugin_stderr(stderr: str, *, killed_by_deadline: bool, had_results: bool) -> dict[str, Any]:
    """Categorise a plugin subprocess's stderr into a structured diagnostic.

    Public trackers run as isolated python subprocesses, and their
    stderr is the only evidence we get about WHY a tracker returned
    zero rows. Before this helper, `TrackerSearchStat.error` was always
    ``None`` for the empty-but-broken trackers, leaving the dashboard
    with no way to distinguish "no hits for this niche query" from
    "upstream returned 403" or "plugin crashed".

    Returns a dict with keys ``error_type`` (short enum-like string),
    ``error`` (human summary), and ``stderr_tail`` (raw tail, truncated).
    """
    tail = (stderr or "").strip()
    if not tail and killed_by_deadline and not had_results:
        return {
            "error_type": "deadline_timeout",
            "error": "plugin exceeded 25s per-tracker deadline with no results",
            "stderr_tail": "",
        }
    if not tail:
        return {"error_type": None, "error": None, "stderr_tail": ""}

    lower = tail.lower()
    # Upstream HTTP failures
    if "http error 403" in lower or "connection error: forbidden" in lower:
        error_type = "upstream_http_403"
        summary = "upstream returned HTTP 403 Forbidden"
    elif "connection error: not found" in lower or "http error 404" in lower:
        error_type = "upstream_http_404"
        summary = "upstream returned HTTP 404 Not Found (domain moved?)"
    elif "gateway timeout" in lower or "http error 504" in lower:
        error_type = "upstream_timeout"
        summary = "upstream gateway timed out"
    elif "name does not resolve" in lower or "name has no usable address" in lower:
        error_type = "dns_failure"
        summary = "upstream domain does not resolve (DNS failure)"
    elif "ssl:" in lower or "tlsv1_alert" in lower:
        error_type = "tls_failure"
        summary = "TLS handshake with upstream failed"
    elif "filenotfounderror" in lower:
        error_type = "plugin_env_missing"
        summary = "plugin needs a directory/file that is not present in the container"
    elif "indexerror" in lower or "list index out of range" in lower:
        error_type = "plugin_parse_failure"
        summary = "plugin parse failed (upstream HTML likely changed)"
    elif "'nonetype' object is not iterable" in lower or "typeerror" in lower:
        error_type = "plugin_crashed"
        summary = "plugin crashed with a TypeError"
    elif "jsondecodeerror" in lower:
        error_type = "plugin_parse_failure"
        summary = "plugin failed to decode upstream JSON"
    elif "incompleteread" in lower:
        error_type = "upstream_incomplete"
        summary = "upstream closed the connection mid-response"
    elif "traceback" in lower or "__error__" in lower:
        error_type = "plugin_crashed"
        summary = "plugin raised an unhandled exception"
    else:
        # Plugin ran cleanly but printed something to stderr (often just
        # `{"__done__": 0}` from our probe wrapper or the plugin's own
        # INFO-level logging). Treat as benign noise.
        error_type = None
        summary = None

    return {"error_type": error_type, "error": summary, "stderr_tail": tail[-400:]}


@dataclass
class TrackerSearchStat:
    """Per-tracker run-time diagnostics for a single search.

    Exposed over the HTTP API (``SearchResponse.tracker_stats``) and
    streamed via SSE events (``tracker_started`` / ``tracker_completed``)
    so the dashboard can render a live chip bar above the results table.
    """

    name: str
    tracker_url: str = ""
    status: str = "pending"  # pending | running | success | empty | error | timeout | cancelled
    results_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None
    error_type: str | None = None
    authenticated: bool = False
    attempt: int = 1
    http_status: int | None = None  # when available from the plugin
    category: str = "all"
    query: str = ""
    # Free-form notes for future diagnostics the plugin wants to surface.
    notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tracker_url": self.tracker_url,
            "status": self.status,
            "results_count": self.results_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "error_type": self.error_type,
            "authenticated": self.authenticated,
            "attempt": self.attempt,
            "http_status": self.http_status,
            "category": self.category,
            "query": self.query,
            "notes": self.notes,
        }


@dataclass
class SearchMetadata:
    search_id: str
    query: str
    category: str = "all"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    total_results: int = 0
    merged_results: int = 0
    trackers_searched: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "running"
    tracker_stats: dict[str, "TrackerSearchStat"] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_id": self.search_id,
            "query": self.query,
            "category": self.category,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_results": self.total_results,
            "merged_results": self.merged_results,
            "trackers_searched": self.trackers_searched,
            "errors": self.errors,
            "status": self.status,
            "tracker_stats": [s.to_dict() for s in sorted(self.tracker_stats.values(), key=lambda s: s.name)],
        }


PUBLIC_TRACKERS = {
    "academictorrents": "https://academictorrents.com/",
    "ali213": "http://down.ali213.net/",
    "anilibra": "https://anilibria.tv",
    "audiobookbay": "http://theaudiobookbay.se/",
    "bitru": "https://bitru.org",
    "bt4g": "https://bt4gprx.com/",
    "btsow": "https://btsow.motorcycles",
    "extratorrent": "https://extratorrent.st",
    "eztv": "https://eztv.re",
    "gamestorrents": "https://www.gamestorrents.app",
    "glotorrents": "https://glodls.to/",
    "kickass": "https://kickasstorrents.to/",
    "limetorrents": "https://www.limetorrents.lol",
    "linuxtracker": "http://linuxtracker.org",
    "megapeer": "https://megapeer.vip",
    "nyaa": "https://nyaa.si",
    "one337x": "https://1337x.to",
    "pctorrent": "https://pctorrent.ru",
    "piratebay": "https://thepiratebay.org",
    "pirateiro": "https://pirateiro.io/",
    "rockbox": "https://rawkbawx.rocks/",
    "rutor": "https://rutor.info/",
    "snowfl": "https://snowfl.com/",
    "solidtorrents": "https://solidtorrents.to",
    "bitsearch": "https://bitsearch.to",
    "therarbg": "https://therarbg.com",
    "tokyotoshokan": "http://tokyotosho.info",
    "torlock": "https://torlock2.com",
    "torrentdownload": "https://www.torrentdownload.info/",
    "torrentfunk": "https://www.torrentfunk.com",
    "torrentgalaxy": "https://torrentgalaxy.one",
    "torrentkitty": "https://www.torrentkitty.tv",
    "torrentproject": "https://torrentproject.com.se",
    "torrentscsv": "https://torrents-csv.com",
    "xfsub": "https://www.xfsub.com",
    "yihua": "https://www.yihua.biz",
    "yourbittorrent": "https://yourbittorrent.com/",
    "yts": "https://yts.lt",
}

# Known-dead public trackers as of 2026-04-23. Categorised by the
# classifier during the comprehensive tracker audit:
#
#   upstream_http_403:  eztv, kickass, bt4g, extratorrent, one337x, bitru
#   upstream_http_404:  megapeer, ali213
#   upstream_timeout:   nyaa, audiobookbay, torlock
#   dns_failure:        pctorrent, yihua, torrentgalaxy
#   tls_failure:        xfsub
#   plugin_crash:       torrentgalaxy (site down → empty HTML → index error)
#   site_rebrand:       solidtorrents (redirects to bitsearch.to)
#   site_redesign:      therarbg, gamestorrents, btsow (JS challenge)
#   upstream_dead:      torrentfunk (redirects to rakix), torrentkitty
#   api_changed:        anilibra (returns 400 Unknown query)
#
# They stay in `PUBLIC_TRACKERS` so the classifier keeps reporting the
# real reason (useful when an upstream comes back), but by default
# they're excluded from the fan-out via `_get_enabled_trackers()` so
# the dashboard stops drowning in permanent red chips. Set the env
# `ENABLE_DEAD_TRACKERS=1` to force them back in — e.g. to test whether
# an upstream has recovered, or when an operator is sitting behind a
# VPN/proxy that bypasses the geoblock.
DEAD_PUBLIC_TRACKERS = frozenset(
    {
        "ali213",
        "audiobookbay",
        "bitru",
        "bt4g",
        "btsow",
        "extratorrent",
        "eztv",
        "one337x",
        "pctorrent",
        "solidtorrents",
        "therarbg",
        "torrentfunk",
        "xfsub",
        "yihua",
    }
)


PRIVATE_TRACKERS = {
    "rutracker": "https://rutracker.org",
    "kinozal": "https://kinozal.tv",
    "nnmclub": "https://nnm-club.me",
    "iptorrents": "https://iptorrents.com",
}


class EncryptedSessionStore:
    """At-rest encryption wrapper over a session cache (CONTINUATION #7 /
    Phase 2.3).

    Private-tracker auth cookies must never sit as plaintext in the
    in-memory cache (a stray ``repr`` of the store, a memory dump, or an
    accidental log line would otherwise leak live session cookies). Values
    are JSON-serialised and Fernet-encrypted on write, decrypted on read,
    so every existing call site (set / get / ``in`` / ``len`` / ``del`` /
    iteration) keeps working unchanged while the backing store holds only
    opaque Fernet tokens.

    The key is per-process ephemeral by default — sessions live only in the
    in-memory TTLCache and never outlive the process, so a fresh key per
    boot is sufficient. Set ``SESSION_ENCRYPTION_KEY`` (a urlsafe-base64
    32-byte Fernet key) to pin it across restarts.
    """

    def __init__(self, cache: "TTLCache[str, Any]", key: bytes | None = None) -> None:
        from cryptography.fernet import Fernet

        self._cache = cache
        if key is None:
            env_key = os.getenv("SESSION_ENCRYPTION_KEY")
            key = env_key.encode() if env_key else Fernet.generate_key()
        self._fernet = Fernet(key)

    def _encrypt(self, value: Any) -> bytes:
        import json

        return self._fernet.encrypt(json.dumps(value).encode("utf-8"))

    def _decrypt(self, token: bytes) -> Any:
        import json

        return json.loads(self._fernet.decrypt(token).decode("utf-8"))

    def __setitem__(self, key: str, value: Any) -> None:
        self._cache[key] = self._encrypt(value)

    def __getitem__(self, key: str) -> Any:
        return self._decrypt(self._cache[key])

    def get(self, key: str, default: Any = None) -> Any:
        token = self._cache.get(key)
        if token is None:
            return default
        try:
            return self._decrypt(token)
        except Exception:
            # Corrupt / undecryptable token (e.g. key rotation) — treat as absent.
            return default

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def __delitem__(self, key: str) -> None:
        del self._cache[key]

    def __len__(self) -> int:
        return len(self._cache)

    def __iter__(self) -> Any:
        return iter(self._cache)

    def _raw_values(self) -> list[bytes]:
        """The encrypted Fernet tokens as stored (for tests / introspection)."""
        return list(self._cache.values())


class SearchOrchestrator:
    def __init__(self) -> None:
        from .deduplicator import Deduplicator
        from .validator import TrackerValidator

        self.deduplicator = Deduplicator()
        self.validator = TrackerValidator()

        # Bounded, self-expiring stores so long-running processes don't leak
        # memory.  Previously these were plain dicts that grew without bound
        # and kept entries forever.
        import os as _os_ttl

        from cachetools import TTLCache as _TTLCache

        _max_searches = max(1, int(_os_ttl.getenv("MAX_ACTIVE_SEARCHES", "256")))
        _ttl = max(1, int(_os_ttl.getenv("ACTIVE_SEARCH_TTL_SECONDS", "3600")))
        self._active_searches: TTLCache[str, SearchMetadata] = _TTLCache(maxsize=_max_searches, ttl=_ttl)
        # At-rest encrypted: cookies are Fernet-encrypted in the backing
        # TTLCache so they never sit as plaintext (CONTINUATION #7).
        self._tracker_sessions: EncryptedSessionStore = EncryptedSessionStore(
            _TTLCache(maxsize=_max_searches, ttl=_ttl)
        )
        # Per-search SSE bearer tokens (CONTINUATION #6). Same bound/TTL as
        # the searches they gate so a token never outlives its search.
        self._stream_tokens: TTLCache[str, str] = _TTLCache(maxsize=_max_searches, ttl=_ttl)
        self._last_merged_results: TTLCache[str, tuple[Any, ...]] = _TTLCache(maxsize=_max_searches, ttl=_ttl)
        self._tracker_results: TTLCache[str, dict[str, list[Any]]] = _TTLCache(maxsize=_max_searches, ttl=_ttl)
        # Side-channel: `_search_public_tracker` writes a diagnostic
        # dict here keyed by tracker name so the orchestrator can thread
        # error info into TrackerSearchStat without changing the return
        # type of every _search_* helper. Overwritten on each call so
        # stale entries can't leak into the next search. Keys live only
        # for the duration of a single orchestrator fan-out.
        self._last_public_tracker_diag: dict[str, dict[str, Any]] = {}
        # Bounded tracker fan-out.  Without this, asyncio.gather spawned one
        # task per tracker (~40+) with no backpressure, which let subprocess
        # spawns and aiohttp sessions starve the event loop under load.
        import os as _os

        self._max_concurrent_trackers: int = max(1, int(_os.getenv("MAX_CONCURRENT_TRACKERS", "5")))
        # `_inflight_count` is an instrument for tests and Phase 6 metrics.
        # It is only meaningful while a search is running.
        self._inflight_count: int = 0
        # Stress tests discovered that firing 50+ searches in a row
        # starved the event loop: each fan-out spawns up to
        # `_max_concurrent_trackers` subprocesses, plus aiohttp
        # sessions for private trackers, and even `/health` stopped
        # responding. Cap concurrent SEARCHES (independent of the
        # per-search tracker cap) at `MAX_CONCURRENT_SEARCHES`; when
        # the cap is saturated the API returns 429 Too Many Requests
        # so clients back off instead of piling more work on top.
        self._max_concurrent_searches: int = max(1, int(_os.getenv("MAX_CONCURRENT_SEARCHES", "8")))
        self._active_search_count: int = 0
        self._search_tasks: dict[str, Any] = {}

    def _load_env(self) -> None:
        logger = logging.getLogger(__name__)
        from config import load_env

        try:
            load_env()
        except Exception as e:
            logger.debug(f"config.load_env() failed, falling back to manual parsing: {e}")
            import os

            for path in [
                "/config/.env",
                os.path.expanduser("~/.qbit.env"),
                "/root/.qbit.env",
            ]:
                if os.path.isfile(path):
                    try:
                        with open(path) as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith("#") and "=" in line:
                                    k, v = line.split("=", 1)
                                    k, v = k.strip(), v.strip().strip('"').strip("'")
                                    if k and k not in os.environ:
                                        os.environ[k] = v
                    except Exception as e:
                        logger.debug(f"Could not load env from {path}: {e}")

    def is_search_queue_full(self) -> bool:
        """True when the number of in-flight `_run_search` tasks is at
        or above ``MAX_CONCURRENT_SEARCHES``.

        Callers should translate this into HTTP 429 so clients back off
        instead of piling more subprocess fan-outs on a starving event
        loop. See `docs/MERGE_SEARCH_DIAGNOSTICS.md` §Stress.
        """
        return self._active_search_count >= self._max_concurrent_searches

    def start_search(
        self,
        query: str,
        category: str = "all",
        enable_metadata: bool = True,
        validate_trackers: bool = True,
    ) -> SearchMetadata:
        """Kick off a search and return metadata synchronously.

        This does NOT block on tracker fan-out — use ``_run_search`` as an
        asyncio task to populate results as they stream in.  The returned
        metadata is immediately available at ``get_search_status`` and in
        ``_active_searches`` so SSE consumers can attach before any
        tracker completes.
        """
        import uuid

        search_id = str(uuid.uuid4())
        metadata = SearchMetadata(search_id=search_id, query=query, category=category)
        metadata.status = "running"
        # Seed tracker_stats synchronously so the POST /search response
        # — which returns before the fan-out starts — can already tell
        # the dashboard which trackers will be hit.
        try:
            trackers = self._get_enabled_trackers()
            metadata.trackers_searched = [t.name for t in trackers]
            for t in trackers:
                metadata.tracker_stats[t.name] = TrackerSearchStat(
                    name=t.name,
                    tracker_url=t.url,
                    status="pending",
                    query=query,
                    category=category,
                    authenticated=self._is_tracker_authenticated(t.name),
                )
        except Exception:  # noqa: S110
            # Never let a tracker-enumeration failure block search start.
            pass
        self._active_searches[search_id] = metadata
        self._tracker_results[search_id] = {}
        # Seed a mutable placeholder so SSE clients can read partial
        # merged/all_results as trackers complete.
        self._last_merged_results[search_id] = ([], [])
        return metadata

    def cancel_search(self, search_id: str) -> bool:
        """Cancel a running search and its background task."""
        metadata = self._active_searches.get(search_id)
        if metadata is None:
            return False
        metadata.status = "aborted"
        task = self._search_tasks.pop(search_id, None)
        if task and not task.done():
            task.cancel()
        return True

    async def _run_search(
        self,
        search_id: str,
        query: str,
        category: str = "all",
    ) -> None:
        """Execute the tracker fan-out for a previously-started search.

        This is the body of the old monolithic ``search()`` method, but
        it pushes per-tracker results into ``_tracker_results[search_id]``
        immediately as each tracker finishes so SSE streams them in real
        time.  At the end it runs a single dedup pass and flips the
        metadata to ``completed``/``failed``.
        """
        import asyncio
        import logging
        import time as _time

        logger = logging.getLogger(__name__)
        metadata = self._active_searches.get(search_id)
        if metadata is None:
            return

        self._active_search_count += 1
        try:
            trackers = self._get_enabled_trackers()
            metadata.trackers_searched = [t.name for t in trackers]
            # Clear any stale diag entries from a previous cancelled/errored
            # search before the fan-out so tracker_stats can't inherit an
            # error classification from a run that never finished.
            for t in trackers:
                self._last_public_tracker_diag.pop(t.name, None)
            # ``start_search`` may have already seeded tracker_stats so
            # the POST /search response is accurate before the fan-out
            # begins.  Only backfill any that are missing — never
            # overwrite, so the pending→running transition the SSE
            # streamer watches for remains observable.
            for t in trackers:
                if t.name not in metadata.tracker_stats:
                    metadata.tracker_stats[t.name] = TrackerSearchStat(
                        name=t.name,
                        tracker_url=t.url,
                        status="pending",
                        query=query,
                        category=category,
                        authenticated=self._is_tracker_authenticated(t.name),
                    )

            async def _search_one(tracker: TrackerSource) -> tuple[str, list[SearchResult], str | None]:
                if metadata.status == "aborted":
                    return tracker.name, [], "aborted"
                stat = metadata.tracker_stats.get(tracker.name)
                if stat is None:
                    # Defensive: always have a stat to mutate.
                    stat = TrackerSearchStat(
                        name=tracker.name,
                        tracker_url=tracker.url,
                        status="pending",
                        query=query,
                        category=category,
                        authenticated=self._is_tracker_authenticated(tracker.name),
                    )
                    metadata.tracker_stats[tracker.name] = stat
                stat.status = "running"
                stat.started_at = datetime.now(UTC)
                t0 = _time.perf_counter()
                try:
                    results = await self._search_tracker(tracker, query, category)
                    logger.info(f"Tracker {tracker.name}: {len(results)} results for '{query}'")
                    # Push as soon as the tracker is done so SSE can see it.
                    self._tracker_results[search_id][tracker.name] = results
                    # Bump running totals for SSE results_update event.
                    metadata.total_results += len(results)
                    stat.results_count = len(results)
                    stat.status = "success" if results else "empty"
                    # Pull subprocess diagnostic out of the side-channel
                    # populated by `_search_public_tracker` so the empty
                    # trackers show their real failure reason instead of
                    # `error: None`.
                    diag = self._last_public_tracker_diag.pop(tracker.name, None)
                    if diag:
                        if diag.get("error_type"):
                            stat.error_type = diag["error_type"]
                            stat.error = diag.get("error")
                            if not results:
                                stat.status = "error"
                        if diag.get("stderr_tail"):
                            stat.notes["stderr_tail"] = diag["stderr_tail"]
                        if diag.get("deadline_hit"):
                            stat.notes["deadline_hit"] = True
                            stat.notes["deadline_seconds"] = diag.get("deadline_seconds")
                    return tracker.name, results, None
                except TimeoutError as e:
                    stat.status = "timeout"
                    stat.error = str(e) or "timeout"
                    stat.error_type = "TimeoutError"
                    logger.error(f"Tracker {tracker.name} timeout: {e}")
                    return tracker.name, [], "timeout"
                except Exception as e:
                    stat.status = "error"
                    stat.error = str(e)
                    stat.error_type = e.__class__.__name__
                    logger.error(f"Tracker {tracker.name} error: {e}")
                    return tracker.name, [], str(e)
                finally:
                    stat.completed_at = datetime.now(UTC)
                    stat.duration_ms = int((_time.perf_counter() - t0) * 1000)

            semaphore = asyncio.Semaphore(self._max_concurrent_trackers)

            async def _bounded(tracker: TrackerSource) -> tuple[str, list[SearchResult], str | None]:
                async with semaphore:
                    self._inflight_count += 1
                    try:
                        return await _search_one(tracker)
                    finally:
                        self._inflight_count -= 1

            if metadata.status == "aborted":
                metadata.completed_at = datetime.now(UTC)
                return

            search_results = await asyncio.gather(*[_bounded(t) for t in trackers], return_exceptions=True)

            if metadata.status == "aborted":
                metadata.completed_at = datetime.now(UTC)
                return

            all_results = []
            for item in search_results:
                if isinstance(item, BaseException):
                    metadata.errors.append(f"uncaught exception: {item}")
                    continue
                name, results, error = item
                all_results.extend(results)
                if error:
                    metadata.errors.append(f"{name}: {error}")

            merged = self.deduplicator.merge_results(all_results)
            metadata.merged_results = len(merged)
            self._last_merged_results[search_id] = (merged, all_results)
            metadata.status = "completed"
            metadata.completed_at = datetime.now(UTC)
        except asyncio.CancelledError:
            metadata.status = "aborted"
            metadata.completed_at = datetime.now(UTC)
            raise
        except Exception as e:
            metadata.status = "failed"
            metadata.errors.append(str(e))
            metadata.completed_at = datetime.now(UTC)
        finally:
            self._active_search_count = max(0, self._active_search_count - 1)
            self._search_tasks.pop(search_id, None)

    async def search(
        self,
        query: str,
        category: str = "all",
        enable_metadata: bool = True,
        validate_trackers: bool = True,
    ) -> SearchMetadata:
        """Blocking variant (legacy entry-point) — runs start + run in one
        call and waits for full completion.  Kept for the scheduler and
        for tests that expect the old synchronous-looking behaviour.
        """
        metadata = self.start_search(
            query=query,
            category=category,
            enable_metadata=enable_metadata,
            validate_trackers=validate_trackers,
        )
        # total_results is bumped incrementally inside _run_search now, so
        # reset it first — the legacy callers expect the final number.
        metadata.total_results = 0
        await self._run_search(metadata.search_id, query, category)
        return metadata

    def _is_tracker_authenticated(self, name: str) -> bool:
        """Return True when the tracker has credentials/session available.

        Public trackers always report False.  For the four private
        trackers we first consult ``_tracker_sessions`` (populated after
        a successful login during a search) and fall back to env-var
        presence so the first search still reports an accurate chip
        state before any login round-trip has completed.
        """
        import os

        if name in self._tracker_sessions:
            return True
        if name == "rutracker":
            return bool(os.getenv("RUTRACKER_USERNAME") and os.getenv("RUTRACKER_PASSWORD"))
        if name == "kinozal":
            return bool(os.getenv("KINOZAL_USERNAME") and os.getenv("KINOZAL_PASSWORD"))
        if name == "nnmclub":
            # BOB-006: authenticated when raw cookies are supplied OR
            # username+password are available for a session login.
            return bool(
                os.getenv("NNMCLUB_COOKIES")
                or (os.getenv("NNMCLUB_USERNAME") and os.getenv("NNMCLUB_PASSWORD"))
            )
        if name == "iptorrents":
            return bool(os.getenv("IPTORRENTS_USERNAME") and os.getenv("IPTORRENTS_PASSWORD"))
        return False

    def _get_enabled_trackers(self) -> list[TrackerSource]:
        import os

        trackers = []
        if os.getenv("RUTRACKER_USERNAME") and os.getenv("RUTRACKER_PASSWORD"):
            trackers.append(TrackerSource(name="rutracker", url="https://rutracker.org", enabled=True))
        if os.getenv("KINOZAL_USERNAME") and os.getenv("KINOZAL_PASSWORD"):
            trackers.append(TrackerSource(name="kinozal", url="https://kinozal.tv", enabled=True))
        if os.getenv("NNMCLUB_COOKIES") or (os.getenv("NNMCLUB_USERNAME") and os.getenv("NNMCLUB_PASSWORD")):
            trackers.append(TrackerSource(name="nnmclub", url="https://nnm-club.me", enabled=True))
        if os.getenv("IPTORRENTS_USERNAME") and os.getenv("IPTORRENTS_PASSWORD"):
            trackers.append(TrackerSource(name="iptorrents", url="https://iptorrents.com", enabled=True))
        if os.getenv("JACKETT_API_KEY") and os.getenv("JACKETT_API_KEY") != "YOUR_API_KEY_HERE":
            trackers.append(TrackerSource(name="jackett", url="http://localhost:9117", enabled=True))

        include_dead = os.getenv("ENABLE_DEAD_TRACKERS", "0") == "1"
        for name, url in sorted(PUBLIC_TRACKERS.items()):
            if name in DEAD_PUBLIC_TRACKERS and not include_dead:
                continue
            trackers.append(TrackerSource(name=name, url=url, enabled=True))

        return trackers

    async def _search_tracker(self, tracker: TrackerSource, query: str, category: str) -> list[SearchResult]:
        """Dispatch to the right plugin and return its results.

        Per-plugin diagnostic info (subprocess stderr, error classification)
        is stashed on ``self._last_public_tracker_diag[name]`` when the
        tracker is a public plugin so the orchestrator can surface it in
        ``TrackerSearchStat`` after the call. This is deliberately a
        side-channel rather than a tuple return so the private-tracker
        helpers don't need to change shape.
        """
        import logging

        logger = logging.getLogger(__name__)
        results: list[SearchResult] = []

        try:
            self._load_env()
            if tracker.name == "rutracker":
                results = await self._search_rutracker(query, category)
            elif tracker.name == "kinozal":
                results = await self._search_kinozal(query, category)
            elif tracker.name == "nnmclub":
                results = await self._search_nnmclub(query, category)
            elif tracker.name == "iptorrents":
                results = await self._search_iptorrents(query, category)
            elif tracker.name in PUBLIC_TRACKERS or tracker.name == "jackett":
                try:
                    _raw_deadline = float(os.getenv("PUBLIC_TRACKER_DEADLINE_SECONDS", "60"))
                except ValueError:
                    _raw_deadline = 60.0
                _deadline_seconds = max(5.0, min(120.0, _raw_deadline))
                results = await asyncio.wait_for(
                    self._search_public_tracker(tracker.name, query, category),
                    timeout=_deadline_seconds + 10.0,
                )
        except Exception as e:
            logger.error(f"Error searching {tracker.name}: {e}")

        return results

    async def _search_public_tracker(self, tracker_name: str, query: str, category: str) -> list[SearchResult]:
        validate_tracker_name(tracker_name)
        import asyncio
        import json
        import logging
        import os as _os_timeout
        import signal as _signal

        logger = logging.getLogger(__name__)
        results = []

        # Stream results as NDJSON so a subprocess kill at timeout still
        # leaves every completed row captured on stdout. Patch the top-level
        # `novaprinter` module because every plugin does
        # `from novaprinter import prettyPrinter` — patching engines.novaprinter
        # leaves that binding untouched and was the 37-empty-trackers bug.
        script = (
            "import sys, os, json as _json\n"
            "sys.path.insert(0, '/config/qBittorrent/nova3')\n"
            "os.chdir('/config/qBittorrent/nova3')\n"
            "import importlib\n"
            "try:\n"
            "    import novaprinter as _np\n"
            "    def _capture(d):\n"
            "        sys.stdout.write(_json.dumps(d) + '\\n')\n"
            "        sys.stdout.flush()\n"
            "    _np.prettyPrinter = _capture\n"
            f"    _mod = importlib.import_module('engines.{tracker_name}')\n"
            f"    _cls = getattr(_mod, '{tracker_name}')\n"
            "    _engine = _cls()\n"
            f"    _engine.search({query!r}, {category!r})\n"
            "except Exception as _e:\n"
            "    print(_json.dumps({'__error__': str(_e)}), file=sys.stderr)\n"
        )

        # Deadline-based streaming. `asyncio.wait_for(proc.communicate())`
        # discards buffered stdout on cancellation, so we read stdout
        # line-by-line with a per-read deadline. On timeout, every NDJSON
        # line already flushed is preserved. The deadline is tunable via
        # `PUBLIC_TRACKER_DEADLINE_SECONDS` (clamped to 5..120) so
        # operators on slow networks can widen it without editing code.
        try:
            _raw_deadline = float(_os_timeout.getenv("PUBLIC_TRACKER_DEADLINE_SECONDS", "60"))
        except ValueError:
            _raw_deadline = 60.0
        deadline_seconds = max(5.0, min(120.0, _raw_deadline))
        proc = None
        deadline = asyncio.get_event_loop().time() + deadline_seconds

        def _append(r: dict[str, Any]) -> None:
            if not isinstance(r, dict) or "__error__" in r:
                if isinstance(r, dict) and "__error__" in r:
                    logger.debug(f"Plugin {tracker_name} error: {r['__error__']}")
                return
            try:
                ct, q = _detect_result_metadata(r.get("name", ""), r.get("size", "0 B"))
                results.append(
                    SearchResult(
                        name=r.get("name", ""),
                        size=r.get("size", "0 B"),
                        seeds=int(r.get("seeds", 0)),
                        leechers=int(r.get("leech", 0)),
                        link=r.get("link", ""),
                        desc_link=r.get("desc_link", ""),
                        tracker=tracker_name,
                        engine_url=PUBLIC_TRACKERS.get(tracker_name, (tracker_name == "jackett" and "http://localhost:9117") or ""),
                        content_type=ct,
                        quality=q,
                    )
                )
            except Exception as e:
                logger.debug(f"Skipping malformed {tracker_name} result: {e}")

        killed_by_deadline = False
        stderr_tail = ""
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3",
                "-c",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    killed_by_deadline = True
                    break
                try:
                    assert proc.stdout is not None
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except TimeoutError:
                    killed_by_deadline = True
                    break
                if not line:  # EOF
                    break
                line_s = line.decode(errors="replace").strip()
                if not line_s:
                    continue
                try:
                    _append(json.loads(line_s))
                except Exception:  # noqa: S112
                    continue

            # --- Defensive subprocess cleanup --------------------------------
            # A plugin stuck in a blocking network call may ignore SIGKILL
            # (uninterruptible sleep) or spawn threads/children that outlive
            # the direct child.  We therefore:
            #   1. kill the entire process group so threads/children die too
            #   2. wait for the process with a short timeout
            #   3. only THEN read stderr (reading a live pipe can block)
            # If any cleanup step times out we abandon the process and let
            # the OS reap it — the orchestrator must NEVER hang here.
            # -----------------------------------------------------------------
            if proc.returncode is None:
                with contextlib.suppress(Exception):
                    proc.kill()
                with contextlib.suppress(Exception):
                    os.killpg(os.getpgid(proc.pid), _signal.SIGKILL)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                logger.warning(f"Plugin {tracker_name} proc.wait() timed out during cleanup — abandoning zombie")
            try:
                assert proc.stderr is not None
                stderr_tail = (await asyncio.wait_for(proc.stderr.read(), timeout=5.0)).decode(errors="replace").strip()
                if stderr_tail:
                    logger.debug(f"Plugin {tracker_name} stderr: {stderr_tail[:300]}")
            except TimeoutError:
                logger.warning(f"Plugin {tracker_name} stderr.read() timed out during cleanup")

        except Exception as e:
            logger.debug(f"Plugin {tracker_name} execution error: {e}")
            if proc and proc.returncode is None:
                with contextlib.suppress(Exception):
                    proc.kill()
                with contextlib.suppress(Exception):
                    os.killpg(os.getpgid(proc.pid), _signal.SIGKILL)
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(proc.wait(), timeout=5.0)

        diag = _classify_plugin_stderr(stderr_tail, killed_by_deadline=killed_by_deadline, had_results=bool(results))
        # Expose the truncation fact so the dashboard can show a clock
        # icon. Without this, a tracker that hit the wall at 25 s looks
        # identical to one that returned cleanly — operators have no way
        # to know the result set is capped.
        diag["deadline_hit"] = bool(killed_by_deadline)
        diag["deadline_seconds"] = deadline_seconds
        self._last_public_tracker_diag[tracker_name] = diag
        return results

    async def _search_rutracker(self, query: str, category: str) -> list[SearchResult]:
        import logging
        import os
        from urllib.parse import urlencode

        import aiohttp

        logger = logging.getLogger(__name__)
        results: list[SearchResult] = []
        username = os.getenv("RUTRACKER_USERNAME")
        password = os.getenv("RUTRACKER_PASSWORD")

        if not username or not password:
            return []

        try:
            base_url = os.getenv("RUTRACKER_MIRRORS", "https://rutracker.org").split(",")[0].strip()
            search_url = f"{base_url}/forum/tracker.php?{urlencode({'nm': query, 'fo': 1})}"

            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{base_url}/forum/login.php",
                    data={
                        "login_username": username,
                        "login_password": password,
                        "login": "Вход",
                    },
                ) as resp:
                    cookies = resp.cookies

                cookie_dict = {c.key: c.value for c in cookies.values()}
                self._tracker_sessions["rutracker"] = {
                    "cookies": cookie_dict,
                    "base_url": base_url,
                }
                # rutracker sometimes serves a CAPTCHA page when logins
                # spike (we see this as "0 results for 'linux' this run,
                # 50 for 'ubuntu' the next"). When the cookie jar comes
                # back with no `bb_*` session or the search response is
                # too short to contain real results, signal that via the
                # tracker-diag side-channel so the orchestrator can tag
                # `TrackerSearchStat` with a real ``auth_failure`` /
                # ``upstream_captcha`` label instead of a generic empty
                # chip. Returning [] keeps the semantics stable for
                # callers that treat rutracker failures as non-fatal.
                if not cookie_dict or not any(k.startswith("bb_") for k in cookie_dict):
                    self._last_public_tracker_diag["rutracker"] = {
                        "error_type": "auth_failure",
                        "error": "rutracker login returned no session cookie — likely CAPTCHA wall or credential failure",
                        "stderr_tail": "",
                        "deadline_hit": False,
                        "deadline_seconds": 0.0,
                    }
                    return results

                async with session.get(search_url, cookies=cookies) as resp:
                    html_content = await resp.text()

                if len(html_content) < 1024 and "captcha" in html_content.lower():
                    self._last_public_tracker_diag["rutracker"] = {
                        "error_type": "upstream_captcha",
                        "error": "rutracker served a CAPTCHA page instead of search results",
                        "stderr_tail": "",
                        "deadline_hit": False,
                        "deadline_seconds": 0.0,
                    }
                    return results

                results = self._parse_rutracker_html(html_content, base_url)
        except Exception as e:
            logger.error(f"RuTracker search error: {e}")

        return results

    def _parse_rutracker_html(self, html_content: str, base_url: str) -> list[SearchResult]:
        import html
        import logging
        import re

        logger = logging.getLogger(__name__)
        results: list[SearchResult] = []

        re_threads = re.compile(r'<tr id="trs-tr-\d+.*?</tr>', re.S)
        re_torrent_data = re.compile(
            r'a data-topic_id="(?P<id>\d+?)".*?>(?P<title>.+?)<'
            r".+?"
            r'data-ts_text="(?P<size>\d+?)"'
            r".+?"
            r'data-ts_text="(?P<seeds>[-\d]+?)"'
            r".+?"
            r"leechmed.+?>(?P<leech>\d+?)<"
            r".+?"
            r'data-ts_text="(?P<pub_date>\d+?)"',
            re.S,
        )

        for thread in re_threads.findall(html_content):
            match = re_torrent_data.search(thread)
            if match:
                try:
                    d = match.groupdict()
                    title = html.unescape(d["title"])
                    topic_id = d["id"]
                    size_val = int(d.get("size", 0) or 0)
                    seeds = int(d.get("seeds", 0) or 0)
                    if seeds < 0:
                        seeds = 0
                    leechers = int(d.get("leech", 0) or 0)

                    ct, q = _detect_result_metadata(title, self._format_size(size_val) if size_val else "0 B")
                    results.append(
                        SearchResult(
                            name=title,
                            size=self._format_size(size_val) if size_val else "0 B",
                            seeds=seeds,
                            leechers=leechers,
                            link=f"{base_url}/forum/dl.php?t={topic_id}",
                            desc_link=f"{base_url}/forum/viewtopic.php?t={topic_id}",
                            tracker="rutracker",
                            engine_url=base_url,
                            content_type=ct,
                            quality=q,
                        )
                    )
                except Exception as e:
                    logger.debug(f"Skipping malformed RuTracker result: {e}")
                    continue

        return results

    def _parse_size_string(self, size_str: str | int | float | None) -> int:
        import re

        # Plugins also emit int (byte counts, sometimes the -1 sentinel
        # for "unknown"). Coerce defensively so the whole search
        # doesn't tip over on a single non-string size.
        if size_str is None:
            return 0
        if isinstance(size_str, (int, float)):
            return int(size_str) if size_str > 0 else 0
        if not isinstance(size_str, str):
            return 0
        size_str = size_str.strip().upper()
        multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        match = re.match(r"([\d.]+)\s*([KMGT]?B)", size_str)
        if match:
            mult = multipliers.get(match.group(2), 1)
            return int(float(match.group(1)) * mult)
        return 0

    def _format_size(self, bytes_size: int) -> str:
        if bytes_size == 0:
            return "0 B"
        size: float = float(bytes_size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    async def _search_kinozal(self, query: str, category: str) -> list[SearchResult]:
        import gzip
        import logging
        import os
        from urllib.parse import urlencode

        import aiohttp

        logger = logging.getLogger(__name__)
        results: list[SearchResult] = []
        username = os.getenv("KINOZAL_USERNAME")
        password = os.getenv("KINOZAL_PASSWORD")

        if not username or not password:
            logger.warning("Kinozal credentials not configured")
            return []

        try:
            base_url = os.getenv("KINOZAL_MIRRORS", "https://kinozal.tv").split(",")[0].strip()
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                login_data = urlencode({"username": username, "password": password}, encoding="cp1251")
                async with session.post(
                    f"{base_url}/takelogin.php",
                    data=login_data,
                    allow_redirects=False,
                ) as login_resp:
                    if login_resp.status not in (200, 301, 302):
                        logger.error(f"Kinozal login failed: HTTP {login_resp.status}")
                        return []
                    cookie_dict = {c.key: c.value for c in login_resp.cookies.values()}

                async with session.get(
                    f"{base_url}/browse.php",
                    params={"s": query},
                    cookies=cookie_dict,
                ) as resp:
                    raw = await resp.read()
                    if raw.startswith(b"\x1f\x8b\x08"):
                        raw = gzip.decompress(raw)
                    html = raw.decode("cp1251")
                    for c in resp.cookies.values():
                        cookie_dict[c.key] = c.value

                self._tracker_sessions["kinozal"] = {
                    "cookies": cookie_dict,
                    "base_url": base_url,
                }
            results = self._parse_kinozal_html(html, base_url)
            logger.info(f"Kinozal search '{query}': {len(results)} results")
        except Exception as e:
            logger.error(f"Kinozal search error: {e}")

        return results

    def _parse_kinozal_html(self, html_content: str, base_url: str) -> list[SearchResult]:
        import logging
        import re
        from html import unescape

        logger = logging.getLogger(__name__)
        results: list[SearchResult] = []
        torrent_re = re.compile(
            r'nam"><a\s+?href="/(?P<desc_link>.+?)"\s+?class="r\d">(?P<name>.+?)'
            r"</a>.+?s\'>.+?s\'>(?P<size>.+?)<.+?sl_s\'>(?P<seeds>\d+?)<.+?sl_p\'"
            r">(?P<leech>\d+?)<.+?s\'>(?P<pub_date>.+?)</td>",
            re.S,
        )
        cyrillic_table = str.maketrans({"Т": "T", "Г": "G", "М": "M", "К": "K", "Б": "B"})  # noqa: RUF001
        url_dl = base_url.replace("//", "//dl.")

        for tor in torrent_re.finditer(html_content):
            try:
                topic_id = tor.group("desc_link").split("=")[-1]
                ct, q = _detect_result_metadata(
                    unescape(tor.group("name")), tor.group("size").translate(cyrillic_table)
                )
                results.append(
                    SearchResult(
                        name=unescape(tor.group("name")),
                        size=tor.group("size").translate(cyrillic_table),
                        seeds=int(tor.group("seeds")),
                        leechers=int(tor.group("leech")),
                        link=f"{url_dl}download.php?id={topic_id}",
                        desc_link=f"{base_url}{tor.group('desc_link')}",
                        tracker="kinozal",
                        engine_url=base_url,
                        content_type=ct,
                        quality=q,
                    )
                )
            except Exception as e:
                logger.debug(f"Skipping malformed Kinozal result: {e}")
                continue

        return results

    async def _search_nnmclub(self, query: str, category: str) -> list[SearchResult]:
        import logging
        import os
        from urllib.parse import urlencode

        import aiohttp

        logger = logging.getLogger(__name__)
        results = []
        cookies_raw = os.getenv("NNMCLUB_COOKIES")
        base_url = os.getenv("NNMCLUB_MIRRORS", "https://nnm-club.me").split(",")[0].strip()

        cookie_jar: dict[str, str] = {}
        if cookies_raw:
            # Explicit browser-exported cookies take precedence — no login
            # round-trip needed.
            for pair in cookies_raw.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    cookie_jar[name.strip()] = value.strip()
        else:
            # BOB-006: derive a session cookie from username/password.
            cookie_jar = await self._nnmclub_login(base_url)

        if "phpbb2mysql_4_sid" not in cookie_jar:
            return []

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{base_url}/forum/tracker.php?{urlencode({'nm': query, 'f': '-1'})}",
                    cookies=cookie_jar,
                ) as resp:
                    raw_bytes = await resp.read()
                    html = raw_bytes.decode("cp1251", "ignore")
                self._tracker_sessions["nnmclub"] = {
                    "cookies": cookie_jar,
                    "base_url": base_url,
                }
            results = self._parse_nnmclub_html(html, base_url)
        except Exception as e:
            logger.error(f"NNMClub search error: {e}")

        return results

    async def _nnmclub_login(self, base_url: str) -> dict[str, str]:
        """BOB-006: log in to NNMClub with username/password and return the
        resulting cookie jar (containing ``phpbb2mysql_4_sid`` on success).

        Mirrors the rutracker login path: POST the credentials to
        ``login.php`` and harvest the Set-Cookie session id. Returns an empty
        dict (graceful) when credentials are missing, the request fails, or
        the response carries no session cookie — the caller treats a missing
        ``phpbb2mysql_4_sid`` as "not authenticated" and returns no results.
        Credentials are never logged.
        """
        import logging
        import os

        import aiohttp

        logger = logging.getLogger(__name__)
        username = os.getenv("NNMCLUB_USERNAME")
        password = os.getenv("NNMCLUB_PASSWORD")
        if not username or not password:
            return {}

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{base_url}/forum/login.php",
                    data={
                        "username": username,
                        "password": password,
                        "login": "вход",
                    },
                ) as resp:
                    cookies = resp.cookies

                cookie_dict = {c.key: c.value for c in cookies.values()}
                if "phpbb2mysql_4_sid" not in cookie_dict:
                    self._last_public_tracker_diag["nnmclub"] = {
                        "error_type": "auth_failure",
                        "error": (
                            "nnmclub login returned no session cookie — "
                            "likely credential failure"
                        ),
                        "stderr_tail": "",
                        "deadline_hit": False,
                        "deadline_seconds": 0.0,
                    }
                    return {}
                return cookie_dict
        except Exception as e:
            logger.error(f"NNMClub login error: {e}")
            return {}

    def _parse_nnmclub_html(self, html_content: str, base_url: str) -> list[SearchResult]:
        import logging
        import re
        from html import unescape

        logger = logging.getLogger(__name__)
        results: list[SearchResult] = []
        torrent_re = re.compile(
            r'topictitle"\shref="(?P<desc_link>.+?)"><b>(?P<name>.+?)</b>.+?'
            r'href="(?P<link>d.+?)".+?<u>(?P<size>\d+?)</u>.+?<b>(?P<seeds>\d+?)'
            r"</b>.+?<b>(?P<leech>\d+?)</b>.+?<u>(?P<pub_date>\d+?)</u>",
            re.S,
        )

        for match in torrent_re.finditer(html_content):
            try:
                ct, q = _detect_result_metadata(unescape(match.group("name")), match.group("size"))
                results.append(
                    SearchResult(
                        name=unescape(match.group("name")),
                        size=match.group("size"),
                        seeds=int(match.group("seeds")),
                        leechers=int(match.group("leech")),
                        link=f"{base_url}/forum/{match.group('link')}",
                        desc_link=f"{base_url}/forum/{match.group('desc_link')}",
                        tracker="nnmclub",
                        engine_url=base_url,
                        content_type=ct,
                        quality=q,
                    )
                )
            except Exception as e:
                logger.debug(f"Skipping malformed NNMClub result: {e}")
                continue

        return results

    async def _search_iptorrents(self, query: str, category: str) -> list[SearchResult]:
        import logging
        import os
        from urllib.parse import urlencode

        import aiohttp

        logger = logging.getLogger(__name__)
        results = []
        username = os.getenv("IPTORRENTS_USERNAME")
        password = os.getenv("IPTORRENTS_PASSWORD")
        if not username or not password:
            return []

        base_url = "https://iptorrents.com"
        cat_map = {
            "movies": "72",
            "tv": "73",
            "music": "75",
            "games": "74",
            "anime": "60",
            "software": "1",
            "books": "35",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{base_url}/do-login.php",
                    data={"username": username, "password": password},
                    headers={"Referer": f"{base_url}/login.php"},
                    allow_redirects=False,
                ) as resp:
                    cookies = {c.key: c.value for c in resp.cookies.values()}
                    if not cookies:
                        logger.error(f"IPTorrents login failed: HTTP {resp.status}, no cookies returned")

                self._tracker_sessions["iptorrents"] = {
                    "cookies": cookies,
                    "base_url": base_url,
                }

                params = {"q": query, "o": "seeders"}
                if category != "all" and category in cat_map:
                    params[cat_map[category]] = ""

                search_url = f"{base_url}/t?{urlencode(params)}"
                async with session.get(
                    search_url,
                    cookies=cookies,
                    headers={"Referer": f"{base_url}/t"},
                ) as resp:
                    html_content = await resp.text()

                results = self._parse_iptorrents_html(html_content, base_url)
        except Exception as e:
            logger.error(f"IPTorrents search error: {e}")

        return results

    def _parse_iptorrents_html(self, html_content: str, base_url: str) -> list[SearchResult]:
        import html
        import logging
        import re

        logger = logging.getLogger(__name__)
        results: list[SearchResult] = []
        table_match = re.search(r'<table[^>]*id="torrents"[^>]*>(.+?)</table>', html_content, re.S)
        if not table_match:
            return results
        table = table_match.group(1)

        for row in re.finditer(r"<tr>(.+?)</tr>", table, re.S):
            row_text = row.group(1)
            if "<th" in row_text:
                continue

            name_match = re.search(
                r'<a\s+class=" hv"\s+href="(?P<desc>/t/\d+)">(?P<name>.+?)</a>',
                row_text,
                re.S,
            )
            if not name_match:
                continue

            dl_match = re.search(r'href="(?P<link>/download\.php/\d+/[^"]+\.torrent[^"]*)"', row_text)
            if not dl_match:
                continue

            size_match = re.search(r">(?P<size>[\d.]+\s*(?:K|M|G|T)?B)<", row_text, re.I)

            td_values = re.findall(r"<td[^>]*>(?P<val>\d+)</td>", row_text)
            seeds = int(td_values[0]) if len(td_values) > 0 else 0
            leechers = int(td_values[1]) if len(td_values) > 1 else 0

            is_free = bool(re.search(r'class="free"', row_text, re.I))

            name_text = html.unescape(name_match.group("name"))
            if is_free and "[free]" not in name_text:
                name_text = name_text.rstrip() + " [free]"

            ct, q = _detect_result_metadata(name_text, size_match.group("size") if size_match else "0 B")
            try:
                results.append(
                    SearchResult(
                        name=name_text,
                        size=size_match.group("size") if size_match else "0 B",
                        seeds=seeds,
                        leechers=leechers,
                        link=base_url + dl_match.group("link"),
                        desc_link=base_url + name_match.group("desc"),
                        tracker="iptorrents",
                        engine_url=base_url,
                        freeleech=is_free,
                        content_type=ct,
                        quality=q,
                    )
                )
            except Exception as e:
                logger.debug(f"Skipping malformed IPTorrents result: {e}")
                continue

        return results

    @retry_policy
    async def fetch_torrent(self, tracker: str, url: str) -> bytes | None:
        import logging

        import aiohttp

        logger = logging.getLogger(__name__)
        session_data = self._tracker_sessions.get(tracker)
        if not session_data:
            self._load_env()
            try:
                if tracker == "rutracker":
                    await self._search_rutracker("__probe__", "all")
                elif tracker == "kinozal":
                    await self._search_kinozal("__probe__", "all")
                elif tracker == "nnmclub":
                    await self._search_nnmclub("__probe__", "all")
                elif tracker == "iptorrents":
                    await self._search_iptorrents("__probe__", "all")
            except Exception as e:
                logger.debug(f"Tracker probe failed for {tracker}: {e}")
            session_data = self._tracker_sessions.get(tracker)

        if not session_data:
            logger.error(f"No stored session for tracker: {tracker}")
            return None

        cookies = session_data["cookies"]
        base_url = session_data["base_url"]

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"Referer": base_url}
                async with session.get(url, cookies=cookies, headers=headers, allow_redirects=True) as resp:
                    if resp.status != 200:
                        logger.error(f"fetch_torrent {tracker}: HTTP {resp.status} for {url}")
                        return None
                    content_type = resp.headers.get("Content-Type", "")
                    data = await resp.read()
                    if (
                        "application/x-bittorrent" in content_type
                        or data[:11] == b"d8:announce"
                        or data[:14] == b"d10:created by"
                        or data[:7] == b"d8:files"
                    ):
                        return data
                    if tracker == "rutracker":
                        return await self._fetch_rutracker_redirect(session, url, cookies, base_url)
                    if tracker == "kinozal":
                        return await self._fetch_kinozal_torrent(session, url, cookies, base_url)
                    logger.error(f"fetch_torrent {tracker}: response not a torrent file ({content_type})")
                    return None
        except aiohttp.ClientError:
            raise
        except Exception as e:
            logger.error(f"fetch_torrent {tracker}: {e}")
            return None

    async def _fetch_rutracker_redirect(self, session: Any, url: str, cookies: dict[str, str], base_url: str) -> bytes | None:
        import logging
        import re

        logger = logging.getLogger(__name__)
        try:
            match = re.search(r"[?&]t=(\d+)", url)
            if not match:
                return None
            topic_id = match.group(1)
            dl_url = f"{base_url}/forum/dl.rss.php?{topic_id}"
            headers = {"Referer": f"{base_url}/forum/viewtopic.php?t={topic_id}"}
            async with session.get(dl_url, cookies=cookies, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
                if data[:11] == b"d8:announce" or data[:14] == b"d10:created by":
                    return bytes(data)
        except Exception as e:
            logger.error(f"_fetch_rutracker_redirect: {e}")
        return None

    async def _fetch_kinozal_torrent(self, session: Any, url: str, cookies: dict[str, str], base_url: str) -> bytes | None:
        import logging

        logger = logging.getLogger(__name__)
        try:
            headers = {"Referer": base_url}
            async with session.get(url, cookies=cookies, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
                if data[:11] == b"d8:announce" or data[:14] == b"d10:created by":
                    return bytes(data)
        except Exception as e:
            logger.error(f"_fetch_kinozal_torrent: {e}")
        return None

    def get_search_status(self, search_id: str) -> SearchMetadata | None:
        result = self._active_searches.get(search_id)
        return result if result is not None else None

    def issue_stream_token(self, search_id: str) -> str:
        """Mint and store a single-use SSE bearer token for ``search_id``
        (CONTINUATION #6). Returned to the client in the search response so
        it can authorise its stream connection."""
        import secrets

        token = secrets.token_urlsafe(32)
        self._stream_tokens[search_id] = token
        return token

    def validate_stream_token(self, search_id: str, token: str | None) -> bool:
        """Constant-time check that ``token`` matches the one issued for
        ``search_id``. False when no token was issued, the search expired,
        or the token is missing/wrong."""
        import secrets

        expected = self._stream_tokens.get(search_id)
        if not expected or not token:
            return False
        return secrets.compare_digest(expected, token)

    def get_live_results(self, search_id: str) -> list[Any]:
        """Get all results found so far for a search, not yet merged.

        FIX: Also check _last_merged_results which IS populated incrementally
        as each tracker completes (inside asyncio.gather callback).
        """
        # First try _tracker_results
        if search_id in self._tracker_results:
            results = []
            for tracker_results in self._tracker_results[search_id].values():
                if tracker_results:
                    results.extend(tracker_results)
            if results:
                return results

        # Fallback: check _last_merged_results (populated INCREMENTALLY)
        if search_id in self._last_merged_results:
            _merged, all_results = self._last_merged_results[search_id]
            if all_results:
                return list(all_results)

        return []

    def get_all_tracker_results(self, search_id: str) -> list[Any]:
        """Get all results from _tracker_results."""
        if search_id not in self._tracker_results:
            return []
        results = []
        for tracker_results in self._tracker_results[search_id].values():
            if tracker_results:
                results.extend(tracker_results)
        return results

    def get_active_searches(self) -> list[SearchMetadata]:
        return list(self._active_searches.values())
