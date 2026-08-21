"""
Tiered matching engine for deduplicating search results across trackers.

Matching tiers (in order of priority):
1. Metadata match (via external APIs - OMDb, TMDB, etc.)
2. Hash match (infohash comparison)
3. Name + size match (exact name and size)
4. Name similarity match (fuzzy matching via Levenshtein)
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

try:
    import Levenshtein

    LEV_AVAILABLE = True
except ImportError:
    LEV_AVAILABLE = False

from .search import (
    CanonicalIdentity,
    ContentType,
    MergedResult,
    QualityTier,
    SearchResult,
)

# ---------------------------------------------------------------------------
# BOB-145 — derivation cache
# ---------------------------------------------------------------------------
# ``merge_results`` compares every still-unmatched result against each group
# seed, so the comparison count is quadratic in the worst case (N distinct
# titles -> N groups). That alone was survivable; what was NOT survivable is
# that each comparison re-derived, from scratch, values that depend on nothing
# but a single string.
#
# Measured with cProfile on a 400-result fan-out (219 groups) BEFORE this
# change — 9.686 s total, 38,958 comparisons:
#
#     _extract_identity_from_result   78,170 calls   4.879 s cumulative
#     _normalize_name                155,686 calls   3.867 s cumulative
#     re._compile (module-level API) 2,107,721 calls 1.323 s tottime
#     _calculate_similarity (Levenshtein) 77,843 calls 0.223 s cumulative
#
# There are only 400 distinct names in that corpus. So ~99.5% of the identity
# extractions and normalisations recomputed an answer already known, and the
# regex work — not the comparison count, and emphatically not Levenshtein at
# 2.3% — was the cost. Caching the per-string derivations therefore removes the
# real bottleneck without touching a single matching rule.
#
# WHY MODULE-LEVEL FUNCTIONS AND NOT ``lru_cache`` ON THE METHODS: an
# ``lru_cache`` applied to a bound method includes ``self`` in the key, so every
# Deduplicator instance that ever ran a merge stays reachable from the cache
# forever. In a service that is up for hours (BOB-137's own setting) that is a
# memory leak — precisely the wrong trade to make while fixing a stability bug.
# Free functions give one bounded, shared, thread-safe cache instead.
#
# CACHE SIZE: a merge fan-out is bounded by what 3-4 trackers return, i.e. low
# thousands of results. 8192 entries holds several consecutive searches' worth
# of distinct strings; a parse tuple is ~200 bytes, so the ceiling is a couple
# of MB. Bounded by construction — an unbounded cache in a long-running service
# is a leak, not an optimisation.
_NAME_CACHE_SIZE = 8192
_SIZE_CACHE_SIZE = 2048

# Patterns are compiled once at import. The module-level ``re.search(pat, s)``
# convenience API performs a cache lookup on every call; the profile above
# attributes 1.323 s of tottime to that lookup alone.
_RE_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_RE_SEASON_EP = re.compile(r"[Ss](\d+)[Ee](\d+)")
_RE_RESOLUTION = re.compile(r"(720p|1080p|2160p|4k|8k)", re.I)
_RE_CODEC = re.compile(r"(x264|x265|hevc|h264|h265|xvid|divx)", re.I)

_RE_NORM_YEAR = re.compile(r"\s*\b(19|20)\d{2}\b\s*")
_RE_NORM_RESOLUTION = re.compile(r"\s*(720p|1080p|2160p|4k|8k)\s*", re.I)
_RE_NORM_CODEC = re.compile(r"\s*(x264|x265|hevc|h264|h265|xvid|divx)\s*", re.I)
_RE_NORM_BRACKETS = re.compile(r"\s*\[.*?\]\s*")
_RE_NORM_WHITESPACE = re.compile(r"\s+")

_RE_INFOHASH = re.compile(r"xt=urn:btih:([a-fA-F0-9]{32,40})")
_RE_SIZE = re.compile(r"([\d.]+)\s*(GB|MB|KB|TB|B)")

_RE_CT_ANIME_TAG = re.compile(r"\[anime\]")
_RE_CT_EPISODE = re.compile(r"[sS]\d+[eE]\d+")
_RE_CT_SEASONS = re.compile(r"\b(seasons?)\s*[\d\-]+\b")
_RE_CT_EPISODE_WORD = re.compile(r"\b(episode)\s*[\d\-]+\b")
_RE_CT_GENRE_PARENS = re.compile(
    r"\([^)]*\b(rock|pop|metal|jazz|blues|folk|hip.?hop|electronic|dance|classical|hard.?rock|indie|rap|soul|r&b|country|techno|trance|house|dubstep|ambient)\b"
)
_RE_CT_GENRE_BRACKETS = re.compile(r"\[(metal|rock|pop|electronic|jazz|indie)\]")
_RE_CT_AUDIOBOOK = re.compile(r"\baudiobook\b")
_RE_CT_SOFTWARE_FORMAT = re.compile(
    r"\b(x86|x64|portable|\.exe|installer|iso|dmg|appimage|snap|flatpak|pkg|deb|rpm|msi)\b"
)
_RE_CT_SOFTWARE_OS = re.compile(
    r"\b(ubuntu|debian|fedora|arch linux|linux mint|opensuse|centos|redhat|gentoo|slackware|kali|manjaro|pop!_os|elementary)\b"
)
_RE_CT_SOFTWARE_TERMS = re.compile(
    r"\b(workstation|browser|server|distro|distribution|ide|sdk|debugger|compiler|vm|virtual|emulator|antivirus|firewall|vpn|proxy|database|framework|library)\b"
)
_RE_CT_SOFTWARE_MULTIPLATFORM = re.compile(
    r"\((win(dows)?\s*[,/]?\s*mac\s*[,/]?\s*linux|windows\s*[,/]?\s*linux|win/mac|mac/linux)\)"
)
_RE_CT_VIDEO_FORMAT = re.compile(r"\b(bluray|blu-ray|bdremux|web-?dl|webrip|h?drip|dvdrip|bdrip|x264|x265|hevc|hdr)\b")
_RE_CT_VIDEO_RESOLUTION = re.compile(r"\b(720p|1080p|2160p|4k)\b")
_RE_CT_EBOOK = re.compile(r"\b(epub|pdf|mobi|azw3|cbz|cbr|djvu)\b")
_RE_CT_AUDIO_FORMAT = re.compile(r"\b(mp3|flac|ogg|opus|aac|wav|aiff|alac|m4a|wma)\b")
_RE_CT_AUDIO_QUALITY = re.compile(r"\b(lossless|320kbps|256kbps|128kbps|v0|vbr|cbr|v2)\b")
_RE_CT_GENRE_BARE = re.compile(
    r"\b(rock|pop|metal|jazz|blues|folk|hip hop|electronic|dance|classical|hard rock|indie|rap|soul|r&b|country|techno|trance|house|dubstep|ambient|reggae|punk|funk|disco|metalcore|progressive)\b"
)
_RE_CT_SOUNDTRACK = re.compile(r"\b(ost|soundtrack|score)\b")

_GAME_MARKERS = (
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
)


class _NameParse(NamedTuple):
    """Everything a torrent name alone determines, derived exactly once.

    Immutable on purpose: it is handed out from a shared cache, so it must be
    impossible for one caller to alter what a later caller reads.
    """

    year: int | None
    season: int | None
    episode: int | None
    content_type: "ContentType"
    resolution: str | None
    codec: str | None


class _ResultView(NamedTuple):
    """A result plus every value the matcher derives from it, derived once.

    ``_check_match`` reads only these six things about each side. Before
    BOB-145 all six were re-derived on *every* comparison, including for the
    group seed — which is fixed for the whole inner loop, so its derivation was
    recomputed once per candidate for nothing. Hoisting them here turns the
    inner loop into scalar comparisons plus the two Levenshtein calls that are
    the matching rules themselves.
    """

    result: SearchResult
    parsed: "_NameParse"
    norm_name: str
    lower_name: str
    infohash_lower: str | None
    size_bytes: float | None


@lru_cache(maxsize=_NAME_CACHE_SIZE)
def _content_type_for(name: str) -> "ContentType":
    """Classify a torrent name. Pure function of ``name``.

    The rule order is load-bearing and is preserved exactly as it was: the
    first branch that matches wins, and a name matching nothing is UNKNOWN.
    """
    n = name.lower()

    # Priority 1: ANIME - category markers early
    if _RE_CT_ANIME_TAG.search(n):
        return ContentType.ANIME

    # Priority 2: TV SHOW - episode patterns early (very specific)
    if _RE_CT_EPISODE.search(n) or _RE_CT_SEASONS.search(n) or _RE_CT_EPISODE_WORD.search(n):
        return ContentType.TV_SHOW

    # Priority 3: GENRE in parentheses/brackets (music)
    if _RE_CT_GENRE_PARENS.search(n) or _RE_CT_GENRE_BRACKETS.search(n):
        return ContentType.MUSIC

    # Priority 4: AUDIOBOOK signals
    if _RE_CT_AUDIOBOOK.search(n):
        return ContentType.AUDIOBOOK

    # Priority 5: GAME - release groups, platforms
    if any(p in n for p in _GAME_MARKERS):
        return ContentType.GAME

    # Priority 6: SOFTWARE - file format and OS markers
    if _RE_CT_SOFTWARE_FORMAT.search(n):
        return ContentType.SOFTWARE

    # Priority 6b: SOFTWARE - OS / distribution names
    if _RE_CT_SOFTWARE_OS.search(n):
        return ContentType.SOFTWARE

    # Priority 6c: SOFTWARE - general software terms
    if _RE_CT_SOFTWARE_TERMS.search(n):
        return ContentType.SOFTWARE

    # Priority 6d: SOFTWARE - multi-platform indicators
    if _RE_CT_SOFTWARE_MULTIPLATFORM.search(n):
        return ContentType.SOFTWARE

    # Priority 7: VIDEO FORMAT - movie/TV (bluray, web-dl, etc.)
    if _RE_CT_VIDEO_FORMAT.search(n):
        return ContentType.MOVIE

    # Priority 7b: VIDEO RESOLUTION - standalone (implies movie/TV)
    if _RE_CT_VIDEO_RESOLUTION.search(n):
        return ContentType.MOVIE

    # Priority 7b: EBOOK formats
    if _RE_CT_EBOOK.search(n):
        return ContentType.EBOOK

    # Priority 8: AUDIO FORMAT - music
    if _RE_CT_AUDIO_FORMAT.search(n) or _RE_CT_AUDIO_QUALITY.search(n):
        return ContentType.MUSIC

    # Priority 9: GENRE keywords without parentheses (music)
    if _RE_CT_GENRE_BARE.search(n):
        return ContentType.MUSIC

    # Priority 10: OST/Soundtrack (music)
    if _RE_CT_SOUNDTRACK.search(n):
        return ContentType.MUSIC

    # Default: unknown
    return ContentType.UNKNOWN


@lru_cache(maxsize=_NAME_CACHE_SIZE)
def _parse_name(name: str) -> _NameParse:
    """Derive every name-determined identity field. Pure function of ``name``.

    Note on ``content_type``: the original code set TV_SHOW from the season /
    episode match and then *unconditionally* overwrote it with the classifier's
    verdict (every branch of the classifier assigns, including the UNKNOWN
    fall-through). The classifier's answer therefore always won, and that is
    what is returned here — same result, one pass instead of two.
    """
    year_match = _RE_YEAR.search(name)
    season_ep = _RE_SEASON_EP.search(name)
    resolution = _RE_RESOLUTION.search(name)
    codec = _RE_CODEC.search(name)

    return _NameParse(
        year=int(year_match.group()) if year_match else None,
        season=int(season_ep.group(1)) if season_ep else None,
        episode=int(season_ep.group(2)) if season_ep else None,
        content_type=_content_type_for(name),
        resolution=resolution.group().lower() if resolution else None,
        codec=codec.group().lower() if codec else None,
    )


@lru_cache(maxsize=_NAME_CACHE_SIZE)
def _normalized_name(name: str) -> str:
    """Strip year / resolution / codec / group tags. Pure function of ``name``."""
    normalized = _RE_NORM_YEAR.sub(" ", name)
    normalized = _RE_NORM_RESOLUTION.sub(" ", normalized)
    normalized = _RE_NORM_CODEC.sub(" ", normalized)
    normalized = _RE_NORM_BRACKETS.sub(" ", normalized)
    return _RE_NORM_WHITESPACE.sub(" ", normalized).strip().lower()


@lru_cache(maxsize=_NAME_CACHE_SIZE)
def _infohash_for(link: str) -> str | None:
    """Extract the infohash from a magnet link. Pure function of ``link``."""
    if link.startswith("magnet:"):
        match = _RE_INFOHASH.search(link)
        if match:
            return match.group(1)
    return None


@lru_cache(maxsize=_SIZE_CACHE_SIZE)
def _size_in_bytes(size_str: str) -> float | None:
    """Parse a pre-formatted size string to bytes. Pure function of ``size_str``."""
    match = _RE_SIZE.match(size_str.strip().upper())
    if not match:
        return None

    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
    }
    return float(match.group(1)) * multipliers.get(match.group(2), 1)


@dataclass
class MatchResult:
    """Result of a match operation."""

    is_match: bool
    confidence: float  # 0.0 to 1.0
    tier: int  # 1-4 (1 = highest priority)
    reason: str


class Deduplicator:
    """Tiered matching engine for deduplicating search results."""

    # Configuration
    SIZE_TOLERANCE_MB = 50  # Size tolerance in MB for "exact" match
    SIMILARITY_THRESHOLD = 0.85  # Minimum similarity for fuzzy match

    def __init__(self) -> None:
        self._merged_groups: list[MergedResult] = []

    def merge_results(self, results: list[SearchResult]) -> list[MergedResult]:
        """
        Merge duplicate results from multiple trackers.

        Args:
            results: List of SearchResult objects from all trackers

        Returns:
            List of MergedResult objects (deduplicated)
        """
        self._merged_groups = []
        unmatched = list(results)

        # Sort by seed count (higher seeds = more likely to be canonical),
        # with deterministic tie-breakers on (link, name) so the grouping
        # is order-independent — Python's sort is stable, so without a
        # tie-breaker, items with equal seed counts preserve their input
        # order and drive different merge-group seeds depending on caller
        # order. Property test `test_merge_is_order_invariant` guards this.
        # `seeds` is typed int but a tracker plugin can emit None (no seed
        # count reported) — coerce to 0 so the sort never raises TypeError.
        unmatched.sort(key=lambda r: (-(r.seeds or 0), r.link or "", r.name or ""))

        # Derive each result's matcher inputs exactly once, up front, instead of
        # once per comparison (BOB-145). The views are local to this merge, so
        # nothing accumulates between calls.
        pending = [self._build_view(r) for r in unmatched]

        while pending:
            # Take the first unmatched result as the seed for a new group
            seed_view = pending.pop(0)
            merged = self._create_merged_result(seed_view.result)

            # Find all matches for this seed
            remaining = []
            for view in pending:
                match = self._check_match_precomputed(seed_view, view)
                if match.is_match:
                    merged.add_source(view.result)
                else:
                    remaining.append(view)

            # After collecting all sources, update to best name and quality
            if len(merged.original_results) > 1:
                self._update_to_best_name(merged)
            self._update_best_quality(merged)

            pending = remaining
            self._merged_groups.append(merged)

        return self._merged_groups

    def _build_view(self, result: SearchResult) -> _ResultView:
        """Derive everything the matcher needs from one result.

        Every component is a pure function of a single field, so each is served
        from the module-level cache after its first computation.
        """
        infohash = self._extract_infohash(result.link)
        return _ResultView(
            result=result,
            parsed=_parse_name(result.name),
            norm_name=_normalized_name(result.name),
            lower_name=result.name.lower(),
            infohash_lower=infohash.lower() if infohash else None,
            size_bytes=self._parse_size(result.size),
        )

    def _create_merged_result(self, seed: SearchResult) -> MergedResult:
        """Create a new merged result from a seed search result."""
        identity = self._extract_identity_from_result(seed)
        merged = MergedResult(canonical_identity=identity, download_urls=[seed.link])
        merged.add_source(seed)
        return merged

    def _score_name(self, name: str) -> int:
        """Score a name to determine quality (higher = better).

        Criteria:
        - Has resolution (1080p, 720p, 2160p, 4k)
        - Has format (BluRay, WEB-DL, HDRip, DVDRip)
        - Has codec (x264, x265, HEVC)
        - Has year
        - Has release group
        - Not excessively stripped (has spaces)
        """
        score = 0
        name_lower = name.lower()

        # Resolution
        if any(r in name_lower for r in ["2160p", "4k", "1080p", "720p", "480p"]):
            score += 10

        # Format
        if any(f in name_lower for f in ["bluray", "blu-ray", "web-dl", "webrip", "hdrip", "dvdrip", "brrip"]):
            score += 8

        # Codec
        if any(c in name_lower for c in ["x265", "hevc", "x264", "h264", "av1"]):
            score += 6

        # Year
        if any(y in name for y in ["2024", "2023", "2022", "2021", "2020", "2019", "2018"]):
            score += 5

        # Release group (usually at end after dash)
        if "-" in name and not name.startswith("-"):
            score += 4

        # Has spaces (not stripped)
        if " " in name:
            score += 3

        return score

    def _update_to_best_name(self, merged: "MergedResult") -> None:
        """Update merged result to use best name from sources."""
        if not merged.original_results:
            return

        best_result = max(merged.original_results, key=lambda r: self._score_name(r.name))

        if best_result.name != merged.original_results[0].name:
            new_identity = self._extract_identity_from_result(best_result)
            merged.canonical_identity = new_identity

    def _update_best_quality(self, merged: "MergedResult") -> None:
        """Set best_quality based on the highest quality among sources."""
        try:
            from api.routes import _detect_quality
        except ImportError:
            _detect_quality = None  # type: ignore[assignment]

        best = None
        best_weight = -1
        weight_map = {
            "unknown": 1,
            "sd": 2,
            "hd": 3,
            "full_hd": 4,
            "uhd_4k": 5,
            "uhd_8k": 6,
        }
        for r in merged.original_results:
            if _detect_quality is not None:
                q = _detect_quality(r.name, r.size)
            else:
                q = self._fallback_quality(r.name, r.size)
            w = weight_map.get(q, 1)
            if w > best_weight:
                best_weight = w
                best = q
        if best:
            merged.best_quality = QualityTier(best)

    def _extract_identity_from_result(self, result: SearchResult) -> CanonicalIdentity:
        """Extract canonical identity from a search result.

        The identity is a pure function of ``result.name`` — nothing else on the
        result is read — so the expensive regex work is done once per distinct
        name and cached (BOB-145).

        A **fresh** ``CanonicalIdentity`` is constructed on every call. That is
        deliberate and is the reason the cache stores an immutable
        :class:`_NameParse` rather than the identity object itself:
        ``CanonicalIdentity`` is a mutable dataclass that escapes into
        ``MergedResult.canonical_identity`` and is reachable by callers (see
        ``set_canonical_identity`` and ``api.routes``). Handing out one shared
        instance would alias unrelated merge groups together and let a single
        caller's edit silently poison every later lookup.
        """
        parsed = _parse_name(result.name)
        return CanonicalIdentity(
            title=result.name,
            year=parsed.year,
            content_type=parsed.content_type,
            season=parsed.season,
            episode=parsed.episode,
            resolution=parsed.resolution,
            codec=parsed.codec,
        )

    def _check_match(self, seed: SearchResult, candidate: SearchResult) -> MatchResult:
        """Check if candidate matches the seed result."""
        return self._check_match_precomputed(self._build_view(seed), self._build_view(candidate))

    def _check_match_precomputed(self, seed: _ResultView, candidate: _ResultView) -> MatchResult:
        """The matching rules, over already-derived inputs.

        Identical in behaviour to calling :meth:`_check_match` with the two
        underlying results — the tiers, their order, their thresholds and the
        returned confidences/reasons are unchanged. The only difference is that
        the values being compared arrive precomputed (BOB-145).
        """
        if self._is_cross_tracker_freeleech_conflict(seed.result, candidate.result):
            return MatchResult(
                is_match=False, confidence=0.0, tier=4, reason="non-freeleech iptorrents vs other tracker"
            )

        # Tier 1: Metadata match (canonical identity comparison)
        if self._compare_identity_views(seed, candidate):
            return MatchResult(is_match=True, confidence=0.99, tier=1, reason="metadata identity match")

        # Tier 2: Hash match (infohash)
        # Compare infohashes if available
        if seed.infohash_lower and candidate.infohash_lower and seed.infohash_lower == candidate.infohash_lower:
            return MatchResult(is_match=True, confidence=1.0, tier=2, reason="infohash match")

        # Tier 3: Name + size exact match
        if self._compare_name_and_size_views(seed, candidate):
            return MatchResult(is_match=True, confidence=0.95, tier=3, reason="name+size match")

        # Tier 4: Fuzzy name similarity
        similarity = self._similarity_of_lowered(seed.lower_name, candidate.lower_name)
        if similarity >= self.SIMILARITY_THRESHOLD:
            return MatchResult(
                is_match=True,
                confidence=similarity,
                tier=4,
                reason=f"fuzzy match ({similarity:.2f})",
            )

        return MatchResult(is_match=False, confidence=0.0, tier=4, reason="no match")

    def _compare_identity_views(self, a: _ResultView, b: _ResultView) -> bool:
        """Tier-1 identity comparison over precomputed views.

        Mirrors :meth:`_compare_identities` exactly. That method stays the
        authority for callers holding ``CanonicalIdentity`` objects; this one
        applies the same predicate to values already derived. ``title`` there is
        the result name, and its normalisation is ``norm_name`` here.
        """
        if not a.result.name or not b.result.name:
            return False
        if not a.norm_name or not b.norm_name:
            return False
        if self._similarity_of_lowered(a.norm_name, b.norm_name) < 0.80:
            return False

        pa, pb = a.parsed, b.parsed
        if pa.year and pb.year and pa.year != pb.year:
            return False
        if pa.content_type and pb.content_type and pa.content_type != pb.content_type:
            return False
        if pa.season is not None and pb.season is not None and pa.season != pb.season:
            return False
        return not (pa.episode is not None and pb.episode is not None and pa.episode != pb.episode)

    def _compare_name_and_size_views(self, a: _ResultView, b: _ResultView) -> bool:
        """Tier-3 name+size comparison over precomputed views.

        Mirrors :meth:`_compare_name_and_size` exactly.
        """
        if a.norm_name != b.norm_name:
            return False
        if a.size_bytes is None or b.size_bytes is None:
            return False
        return abs(a.size_bytes - b.size_bytes) / (1024 * 1024) <= self.SIZE_TOLERANCE_MB

    def _compare_hashes(self, a: SearchResult, b: SearchResult) -> bool:
        """Compare infohashes from magnet links."""
        hash_a = self._extract_infohash(a.link)
        hash_b = self._extract_infohash(b.link)

        if hash_a and hash_b:
            return hash_a.lower() == hash_b.lower()
        return False

    def _extract_infohash(self, link: str) -> str | None:
        """Extract infohash from a magnet link or URL.

        Pure function of ``link``; cached per distinct link (BOB-145). The
        falsy-link guard stays out of the cache so an unhashable or empty value
        never becomes a cache key.
        """
        if not link:
            return None
        return _infohash_for(link)

    def _compare_name_and_size(self, a: SearchResult, b: SearchResult) -> bool:
        """Check if two results have matching names and sizes."""
        # Normalize names for comparison
        name_a = self._normalize_name(a.name)
        name_b = self._normalize_name(b.name)

        if name_a != name_b:
            return False

        # Compare sizes (with tolerance)
        size_a = self._parse_size(a.size)
        size_b = self._parse_size(b.size)

        if size_a is None or size_b is None:
            return False

        diff_mb = abs(size_a - size_b) / (1024 * 1024)
        return diff_mb <= self.SIZE_TOLERANCE_MB

    def _normalize_name(self, name: str) -> str:
        """Normalize a torrent name for comparison.

        Pure function of ``name``; cached (BOB-145). This was the single
        hottest call in the pre-fix profile — 155,686 calls over 400 distinct
        names, i.e. the same five substitutions repeated ~390x per name.
        """
        return _normalized_name(name)

    def _parse_size(self, size_str: str) -> float | None:
        """Parse size → bytes.

        Accepts both pre-formatted strings (``"4.0 GB"``) and raw
        numeric values (some plugins emit a byte count int, including
        the ``-1`` sentinel). Previously the deduplicator crashed the
        whole fan-out with
        ``'int' object has no attribute 'strip'``.
        """
        if size_str is None:
            return None
        if isinstance(size_str, (int, float)):
            return None if size_str < 0 else float(size_str)
        if not isinstance(size_str, str):
            return None
        if not size_str:
            return None

        # Only the str path is cached, and only after the type guards above
        # have run — an unhashable value must never reach a cache key, and the
        # int/float/None branches are already O(1).
        return _size_in_bytes(size_str)

    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names using Levenshtein distance."""
        return self._similarity_of_lowered(name1.lower(), name2.lower())

    def _similarity_of_lowered(self, name1: str, name2: str) -> float:
        """Similarity of two names the caller has already lower-cased.

        Split out of :meth:`_calculate_similarity` so the hot path does not
        re-lower strings that are lower-case by construction — ``norm_name``
        ends in ``.lower()`` and ``lower_name`` is literally that. The pre-fix
        profile showed 235,663 ``str.lower`` calls per 400-result merge, all but
        a handful of them no-ops on already-lowered input.

        This is the single implementation of the similarity rule;
        :meth:`_calculate_similarity` is a lowering wrapper over it, so the two
        can never drift apart.
        """
        if not LEV_AVAILABLE:
            # Fallback to simple character overlap
            set1 = set(name1.split())
            set2 = set(name2.split())
            if not set1 or not set2:
                return 0.0
            return len(set1 & set2) / len(set1 | set2)

        # Use Levenshtein ratio
        return float(Levenshtein.ratio(name1, name2))

    def _compare_identities(self, a: CanonicalIdentity, b: CanonicalIdentity) -> bool:
        """Compare two canonical identities for Tier 1 match."""
        if a.title and b.title:
            norm_a = self._normalize_name(a.title)
            norm_b = self._normalize_name(b.title)
            if not norm_a or not norm_b:
                return False
            sim = self._calculate_similarity(norm_a, norm_b)
            if sim < 0.80:
                return False
        else:
            return False

        if a.year and b.year and a.year != b.year:
            return False

        if a.content_type and b.content_type and a.content_type != b.content_type:
            return False

        if a.season is not None and b.season is not None and a.season != b.season:
            return False

        return not (a.episode is not None and b.episode is not None and a.episode != b.episode)

    def _detect_content_type(self, identity: CanonicalIdentity, name: str) -> None:
        """Detect content type from torrent name using dynamic patterns only.

        Thin wrapper over the cached, pure classifier (BOB-145). Kept as a
        mutating method because that is its established contract with callers.
        """
        identity.content_type = _content_type_for(name)

    def set_canonical_identity(self, merged: "MergedResult", identity: CanonicalIdentity) -> None:
        """Update the canonical identity for a merged result (after metadata enrichment)."""
        merged.canonical_identity = identity

    def _is_cross_tracker_freeleech_conflict(self, a: SearchResult, b: SearchResult) -> bool:
        """Prevent merging non-freeleech IPTorrents results with other trackers."""
        if a.tracker == "iptorrents" and b.tracker != "iptorrents" and not a.freeleech:
            return True
        return b.tracker == "iptorrents" and a.tracker != "iptorrents" and not b.freeleech

    def _fallback_quality(self, name: str, size: object) -> str:
        """Simple quality detection without api.routes dependency."""
        from .enricher import MetadataEnricher

        enricher = MetadataEnricher()
        quality = enricher.detect_quality(name)
        if quality:
            mapping = {
                "4K": "uhd_4k",
                "1080p": "full_hd",
                "720p": "hd",
                "SD": "sd",
                "BluRay": "full_hd",
                "BDRip": "full_hd",
                "BDRemux": "uhd_4k",
                "WEB-DL": "hd",
                "WEBRip": "hd",
                "HDRip": "hd",
                "HDTV": "hd",
                "DVD": "sd",
                "DVDRip": "sd",
            }
            return mapping.get(quality, "unknown")
        sb = self._parse_size_to_bytes(size)
        if sb >= 40 * 1024**3:
            return "uhd_4k"
        if sb >= 8 * 1024**3:
            return "full_hd"
        if sb >= 2 * 1024**3:
            return "hd"
        if sb >= 300 * 1024**2:
            return "sd"
        return "unknown"

    @staticmethod
    def _parse_size_to_bytes(size_str: object) -> int:
        """Parse a size value to bytes.

        Plugins emit ``size`` either as a pre-formatted string ("2.5 GB")
        or as a raw int byte-count (including the -1 unknown sentinel).
        Coerce to ``str`` before the regex — passing a raw int into
        ``re.match`` raised ``TypeError`` and aborted the whole merge
        (BUG-6, mirrors the same fix already applied in api.routes and
        ``_parse_size``).
        """
        import re

        if not size_str:
            return 0
        size_str = str(size_str)
        match = re.match(r"([\d.]+)\s*(GB|GiB|MB|MiB|KB|KiB|TB|TiB|B)", size_str, re.I)
        if match:
            value = float(match.group(1))
            unit = match.group(2).upper()
            multipliers = {
                "B": 1,
                "KB": 1024,
                "KIB": 1024,
                "MB": 1024**2,
                "MIB": 1024**2,
                "GB": 1024**3,
                "GIB": 1024**3,
                "TB": 1024**4,
                "TIB": 1024**4,
            }
            return int(value * multipliers.get(unit, 1))
        return 0
