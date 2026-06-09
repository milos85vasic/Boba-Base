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
        unmatched.sort(key=lambda r: (-r.seeds, r.link or "", r.name or ""))

        while unmatched:
            # Take the first unmatched result as the seed for a new group
            seed = unmatched.pop(0)
            merged = self._create_merged_result(seed)

            # Find all matches for this seed
            remaining = []
            for result in unmatched:
                match = self._check_match(seed, result)
                if match.is_match:
                    merged.add_source(result)
                else:
                    remaining.append(result)

            # After collecting all sources, update to best name and quality
            if len(merged.original_results) > 1:
                self._update_to_best_name(merged)
            self._update_best_quality(merged)

            unmatched = remaining
            self._merged_groups.append(merged)

        return self._merged_groups

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
        """Extract canonical identity from a search result."""
        identity = CanonicalIdentity(title=result.name)

        # Extract year from name (e.g., "Movie Title 2023")
        year_match = re.search(r"\b(19|20)\d{2}\b", result.name)
        if year_match:
            identity.year = int(year_match.group())

        # Extract season/episode for TV shows
        season_ep = re.search(r"[Ss](\d+)[Ee](\d+)", result.name)
        if season_ep:
            identity.season = int(season_ep.group(1))
            identity.episode = int(season_ep.group(2))
            identity.content_type = ContentType.TV_SHOW

        # Detect content type from name
        self._detect_content_type(identity, result.name)

        # Extract resolution
        resolution = re.search(r"(720p|1080p|2160p|4k|8k)", result.name, re.I)
        if resolution:
            identity.resolution = resolution.group().lower()

        # Extract codec
        codec = re.search(r"(x264|x265|hevc|h264|h265|xvid|divx)", result.name, re.I)
        if codec:
            identity.codec = codec.group().lower()

        return identity

    def _check_match(self, seed: SearchResult, candidate: SearchResult) -> MatchResult:
        """Check if candidate matches the seed result."""

        if self._is_cross_tracker_freeleech_conflict(seed, candidate):
            return MatchResult(
                is_match=False, confidence=0.0, tier=4, reason="non-freeleech iptorrents vs other tracker"
            )

        # Tier 1: Metadata match (canonical identity comparison)
        id_a = self._extract_identity_from_result(seed)
        id_b = self._extract_identity_from_result(candidate)
        if self._compare_identities(id_a, id_b):
            return MatchResult(is_match=True, confidence=0.99, tier=1, reason="metadata identity match")

        # Tier 2: Hash match (infohash)
        # Compare infohashes if available
        if self._compare_hashes(seed, candidate):
            return MatchResult(is_match=True, confidence=1.0, tier=2, reason="infohash match")

        # Tier 3: Name + size exact match
        if self._compare_name_and_size(seed, candidate):
            return MatchResult(is_match=True, confidence=0.95, tier=3, reason="name+size match")

        # Tier 4: Fuzzy name similarity
        similarity = self._calculate_similarity(seed.name, candidate.name)
        if similarity >= self.SIMILARITY_THRESHOLD:
            return MatchResult(
                is_match=True,
                confidence=similarity,
                tier=4,
                reason=f"fuzzy match ({similarity:.2f})",
            )

        return MatchResult(is_match=False, confidence=0.0, tier=4, reason="no match")

    def _compare_hashes(self, a: SearchResult, b: SearchResult) -> bool:
        """Compare infohashes from magnet links."""
        hash_a = self._extract_infohash(a.link)
        hash_b = self._extract_infohash(b.link)

        if hash_a and hash_b:
            return hash_a.lower() == hash_b.lower()
        return False

    def _extract_infohash(self, link: str) -> str | None:
        """Extract infohash from a magnet link or URL."""
        if not link:
            return None

        # Magnet link format: magnet:?xt=urn:btih:HASH
        if link.startswith("magnet:"):
            match = re.search(r"xt=urn:btih:([a-fA-F0-9]{32,40})", link)
            if match:
                return match.group(1)

        return None

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
        """Normalize a torrent name for comparison."""
        # Remove year, resolution, codec, group info for cleaner comparison
        normalized = re.sub(r"\s*\b(19|20)\d{2}\b\s*", " ", name)  # Remove year
        normalized = re.sub(r"\s*(720p|1080p|2160p|4k|8k)\s*", " ", normalized, flags=re.I)  # Remove resolution
        normalized = re.sub(r"\s*(x264|x265|hevc|h264|h265|xvid|divx)\s*", " ", normalized, flags=re.I)  # Remove codec
        normalized = re.sub(r"\s*\[.*?\]\s*", " ", normalized)  # Remove group brackets
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()
        return normalized

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

        size_str = size_str.strip().upper()

        # Match size unit and value
        match = re.match(r"([\d.]+)\s*(GB|MB|KB|TB|B)", size_str)
        if not match:
            return None

        value = float(match.group(1))
        unit = match.group(2)

        multipliers = {
            "B": 1,
            "KB": 1024,
            "MB": 1024**2,
            "GB": 1024**3,
            "TB": 1024**4,
        }

        return value * multipliers.get(unit, 1)

    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names using Levenshtein distance."""
        if not LEV_AVAILABLE:
            # Fallback to simple character overlap
            set1 = set(name1.lower().split())
            set2 = set(name2.lower().split())
            if not set1 or not set2:
                return 0.0
            return len(set1 & set2) / len(set1 | set2)

        # Use Levenshtein ratio
        if LEV_AVAILABLE:
            return float(Levenshtein.ratio(name1.lower(), name2.lower()))
        return 1.0 if name1.lower() == name2.lower() else 0.0

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
        """Detect content type from torrent name using dynamic patterns only."""
        n = name.lower()

        # Priority 1: ANIME - category markers early
        if re.search(r"\[anime\]", n):
            identity.content_type = ContentType.ANIME
            return

        # Priority 2: TV SHOW - episode patterns early (very specific)
        if (
            re.search(r"[sS]\d+[eE]\d+", n)
            or re.search(r"\b(seasons?)\s*[\d\-]+\b", n)
            or re.search(r"\b(episode)\s*[\d\-]+\b", n)
        ):
            identity.content_type = ContentType.TV_SHOW
            return

        # Priority 3: GENRE in parentheses/brackets (music)
        if re.search(
            r"\([^)]*\b(rock|pop|metal|jazz|blues|folk|hip.?hop|electronic|dance|classical|hard.?rock|indie|rap|soul|r&b|country|techno|trance|house|dubstep|ambient)\b",
            n,
        ) or re.search(r"\[(metal|rock|pop|electronic|jazz|indie)\]", n):
            identity.content_type = ContentType.MUSIC
            return

        # Priority 4: AUDIOBOOK signals
        if re.search(r"\baudiobook\b", n):
            identity.content_type = ContentType.AUDIOBOOK
            return

        # Priority 5: GAME - release groups, platforms
        if any(
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
            identity.content_type = ContentType.GAME
            return

        # Priority 6: SOFTWARE - file format and OS markers
        if re.search(r"\b(x86|x64|portable|\.exe|installer|iso|dmg|appimage|snap|flatpak|pkg|deb|rpm|msi)\b", n):
            identity.content_type = ContentType.SOFTWARE
            return

        # Priority 6b: SOFTWARE - OS / distribution names
        if re.search(
            r"\b(ubuntu|debian|fedora|arch linux|linux mint|opensuse|centos|redhat|gentoo|slackware|kali|manjaro|pop!_os|elementary)\b",
            n,
        ):
            identity.content_type = ContentType.SOFTWARE
            return

        # Priority 6c: SOFTWARE - general software terms (when combined with version/year patterns)
        if re.search(
            r"\b(workstation|browser|server|distro|distribution|ide|sdk|debugger|compiler|vm|virtual|emulator|antivirus|firewall|vpn|proxy|database|framework|library)\b",
            n,
        ):
            identity.content_type = ContentType.SOFTWARE
            return

        # Priority 6d: SOFTWARE - multi-platform indicators
        if re.search(r"\((win(dows)?\s*[,/]?\s*mac\s*[,/]?\s*linux|windows\s*[,/]?\s*linux|win/mac|mac/linux)\)", n):
            identity.content_type = ContentType.SOFTWARE
            return

        # Priority 7: VIDEO FORMAT - movie/TV (bluray, web-dl, etc.)
        if re.search(r"\b(bluray|blu-ray|bdremux|web-?dl|webrip|h?drip|dvdrip|bdrip|x264|x265|hevc|hdr)\b", n):
            identity.content_type = ContentType.MOVIE
            return

        # Priority 7b: VIDEO RESOLUTION - standalone (implies movie/TV)
        if re.search(r"\b(720p|1080p|2160p|4k)\b", n):
            identity.content_type = ContentType.MOVIE
            return

        # Priority 7b: EBOOK formats
        if re.search(r"\b(epub|pdf|mobi|azw3|cbz|cbr|djvu)\b", n):
            identity.content_type = ContentType.EBOOK
            return

        # Priority 8: AUDIO FORMAT - music
        if re.search(r"\b(mp3|flac|ogg|opus|aac|wav|aiff|alac|m4a|wma)\b", n) or re.search(
            r"\b(lossless|320kbps|256kbps|128kbps|v0|vbr|cbr|v2)\b", n
        ):
            identity.content_type = ContentType.MUSIC
            return

        # Priority 9: GENRE keywords without parentheses (music)
        if re.search(
            r"\b(rock|pop|metal|jazz|blues|folk|hip hop|electronic|dance|classical|hard rock|indie|rap|soul|r&b|country|techno|trance|house|dubstep|ambient|reggae|punk|funk|disco|metalcore|progressive)\b",
            n,
        ):
            identity.content_type = ContentType.MUSIC
            return

        # Priority 10: OST/Soundtrack (music)
        if re.search(r"\b(ost|soundtrack|score)\b", n):
            identity.content_type = ContentType.MUSIC
            return

        # Default: unknown
        identity.content_type = ContentType.UNKNOWN

    def set_canonical_identity(self, merged: "MergedResult", identity: CanonicalIdentity) -> None:
        """Update the canonical identity for a merged result (after metadata enrichment)."""
        merged.canonical_identity = identity

    def _is_cross_tracker_freeleech_conflict(self, a: SearchResult, b: SearchResult) -> bool:
        """Prevent merging non-freeleech IPTorrents results with other trackers."""
        if a.tracker == "iptorrents" and b.tracker != "iptorrents" and not a.freeleech:
            return True
        return b.tracker == "iptorrents" and a.tracker != "iptorrents" and not b.freeleech

    def _fallback_quality(self, name: str, size: str) -> str:
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
    def _parse_size_to_bytes(size_str: str) -> int:
        """Parse size string (e.g. 2.5 GB, 500 MB) to bytes."""
        import re

        if not size_str:
            return 0
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
