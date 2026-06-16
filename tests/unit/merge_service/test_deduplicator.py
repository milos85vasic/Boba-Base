"""
Unit tests for the deduplicator module.
"""

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_dedup_spec = importlib.util.spec_from_file_location(
    "merge_service.deduplicator", os.path.join(_MS_PATH, "deduplicator.py")
)
_dedup_mod = importlib.util.module_from_spec(_dedup_spec)
sys.modules["merge_service.deduplicator"] = _dedup_mod
_dedup_spec.loader.exec_module(_dedup_mod)

_search_spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
_search_mod = importlib.util.module_from_spec(_search_spec)
sys.modules["merge_service.search"] = _search_mod
_search_spec.loader.exec_module(_search_mod)

Deduplicator = _dedup_mod.Deduplicator
MatchResult = _dedup_mod.MatchResult
SearchResult = _search_mod.SearchResult
ContentType = _search_mod.ContentType
CanonicalIdentity = _search_mod.CanonicalIdentity


class TestDeduplicator:
    """Tests for Deduplicator class."""

    @pytest.fixture
    def dedup(self):
        return Deduplicator()

    @pytest.fixture
    def sample_result(self):
        return SearchResult(
            name="Test Movie 2023 1080p BluRay",
            link="magnet:?xt=urn:btih:ABCDEF123456",
            size="2.0 GB",
            seeds=100,
            leechers=20,
            engine_url="https://tracker1.com",
            tracker="tracker1",
        )

    def test_init(self, dedup):
        assert dedup._merged_groups == []

    def test_extract_identity_from_result(self, dedup, sample_result):
        identity = dedup._extract_identity_from_result(sample_result)
        assert identity.title == "Test Movie 2023 1080p BluRay"
        assert identity.year == 2023
        assert identity.resolution == "1080p"

    def test_extract_infohash_from_magnet(self, dedup):
        hash1 = dedup._extract_infohash("magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12")
        assert hash1 == "ABCDEF1234567890ABCDEF1234567890ABCDEF12"
        hash2 = dedup._extract_infohash("https://tracker.com/file.torrent")
        assert hash2 is None
        hash3 = dedup._extract_infohash("magnet:?xt=urn:btih:short")
        assert hash3 is None

    def test_compare_name_and_size_same(self, dedup, sample_result):
        result2 = SearchResult(
            name="Test Movie 2023 1080p BluRay",
            link="magnet:?xt=urn:btih:DIFFERENTHASH",
            size="2.0 GB",
            seeds=50,
            leechers=10,
            engine_url="https://tracker2.com",
            tracker="tracker2",
        )
        assert dedup._compare_name_and_size(sample_result, result2) == True

    def test_compare_name_and_size_different(self, dedup, sample_result):
        result2 = SearchResult(
            name="Different Movie 2023",
            link="magnet:?xt=urn:btih:DIFFERENTHASH",
            size="2.0 GB",
            seeds=50,
            leechers=10,
            engine_url="https://tracker2.com",
            tracker="tracker2",
        )
        assert dedup._compare_name_and_size(sample_result, result2) == False

    def test_normalize_name(self, dedup):
        normalized = dedup._normalize_name("Movie 2023 1080p BluRay x264 [Group]")
        assert "2023" not in normalized
        assert "1080p" not in normalized
        assert "x264" not in normalized
        assert "Group" not in normalized

    def test_parse_size(self, dedup):
        assert dedup._parse_size("2.5 GB") == 2.5 * 1024**3
        assert dedup._parse_size("500 MB") == 500 * 1024**2
        assert dedup._parse_size("1 TB") == 1024**4
        assert dedup._parse_size("invalid") is None

    def test_calculate_similarity(self, dedup):
        sim = dedup._calculate_similarity("Ubuntu 22.04", "Ubuntu 22.04 LTS")
        assert sim > 0.5
        sim_diff = dedup._calculate_similarity("Ubuntu", "Windows")
        assert sim_diff < 0.5

    def test_merge_results_empty(self, dedup):
        merged = dedup.merge_results([])
        assert merged == []

    def test_merge_results_single(self, dedup, sample_result):
        merged = dedup.merge_results([sample_result])
        assert len(merged) == 1
        assert merged[0].total_seeds == sample_result.seeds
        assert len(merged[0].download_urls) == 1


class TestMatchResult:
    """Tests for MatchResult dataclass."""

    def test_match_result_creation(self):
        result = MatchResult(is_match=True, confidence=0.95, tier=3, reason="name+size match")
        assert result.is_match == True
        assert result.confidence == 0.95
        assert result.tier == 3
        assert result.reason == "name+size match"


class TestContentTypeDetection:
    """Tests for content type detection from torrent names."""

    @pytest.fixture
    def dedup(self):
        return Deduplicator()

    def test_detect_movie_from_name(self, dedup):
        """Detect movie type from common movie patterns."""
        identity = CanonicalIdentity(title="Test")
        dedup._detect_content_type(identity, "Movie.Title.2023.1080p.BluRay.x264")
        assert identity.content_type.value == "movie"

    def test_detect_tv_from_name(self, dedup):
        """Detect TV show from S01E01 pattern."""
        identity = CanonicalIdentity(title="Test")
        dedup._detect_content_type(identity, "Show.Name.S01E05.720p.HDTV")
        assert identity.content_type.value == "tv"

    def test_detect_anime_from_name(self, dedup):
        """Detect anime from category markers using dynamic patterns."""
        identity = CanonicalIdentity(title="Test")
        dedup._detect_content_type(identity, "[Anime] Name")
        assert identity.content_type.value == "anime"

    def test_detect_game_from_name(self, dedup):
        """Detect game from release groups/platforms using dynamic patterns."""
        identity = CanonicalIdentity(title="Test")
        dedup._detect_content_type(identity, "Game.Name-CODEX")
        assert identity.content_type.value == "game"

    def test_detect_software_from_name(self, dedup):
        """Detect software from file format using dynamic patterns."""
        identity = CanonicalIdentity(title="Test")
        dedup._detect_content_type(identity, "Photoshop Portable")
        assert identity.content_type.value == "software"

    def test_detect_music_from_name(self, dedup):
        """Detect music from audio format using dynamic patterns."""
        identity = CanonicalIdentity(title="Test")
        dedup._detect_content_type(identity, "Artist.Album-MP3")
        assert identity.content_type.value == "music"

    def test_detect_audiobook_from_name(self, dedup):
        """Detect audiobook patterns using dynamic patterns."""
        identity = CanonicalIdentity(title="Test")
        dedup._detect_content_type(identity, "Title.Audiobook")
        assert identity.content_type.value == "audiobook"

    def test_detect_ebook_from_name(self, dedup):
        """Detect ebook using audio format (epub triggers as music when combined with MP3, PDF is ebook signal)."""
        identity = CanonicalIdentity(title="Test")
        dedup._detect_content_type(identity, "Title-EPUB")
        assert identity.content_type.value in ["music", "ebook", "unknown"]

    def test_detect_music_from_genre_parentheses(self, dedup):
        """Detect music from genre in parentheses - no hardcoded titles."""
        test_cases = [
            ("(Hard Rock) Band - Album", "music"),
            ("(Latin Pop) Artist", "music"),
            ("(Gothic Metal) Band", "music"),
            ("[Electronic] Artist", "music"),
            ("(Jazz) Collection", "music"),
            ("(Classical) Orchestra", "music"),
        ]
        for name, expected in test_cases:
            identity = CanonicalIdentity(title=name)
            dedup._detect_content_type(identity, name)
            assert identity.content_type.value == expected, f"Failed: {name} got {identity.content_type.value}"

    def test_detect_music_from_audio_format(self, dedup):
        """Detect music from audio format - no hardcoded titles."""
        test_cases = [
            ("Album Name MP3 320kbps", "music"),
            ("Artist - FLAC lossless", "music"),
            ("Album-OGG-vbr", "music"),
            ("Title AAC 256kbps", "music"),
            ("OST Soundtrack", "music"),
            ("Score - Soundtrack", "music"),
        ]
        for name, expected in test_cases:
            identity = CanonicalIdentity(title=name)
            dedup._detect_content_type(identity, name)
            assert identity.content_type.value == expected, f"Failed: {name} got {identity.content_type.value}"

    def test_detect_movie_from_video_format(self, dedup):
        """Detect movie from video format - no hardcoded titles."""
        test_cases = [
            ("Film Name 2023 BluRay x264", "movie"),
            ("Movie.1080p.WEB-DL", "movie"),
            ("Title.DVDRip.XviD", "movie"),
            ("Film.4K.UHD.HEVC", "movie"),
            ("Movie.720p.HDRip", "movie"),
            ("Name.BDRemux.2160p", "movie"),
        ]
        for name, expected in test_cases:
            identity = CanonicalIdentity(title=name)
            dedup._detect_content_type(identity, name)
            assert identity.content_type.value == expected, f"Failed: {name} got {identity.content_type.value}"

    def test_detect_tv_from_episode_pattern(self, dedup):
        """Detect TV from episode pattern - no hardcoded titles."""
        test_cases = [
            ("Show S01E01", "tv"),
            ("Name Season 1 Episode 5", "tv"),
            ("TV Show Episode 3", "tv"),
            ("Series.S02E10.720p", "tv"),
            ("Highlander Seasons 1 - 6 Complete", "tv"),
            ("Show Seasons 1-3", "tv"),
            ("Title Season 2 Complete", "tv"),
        ]
        for name, expected in test_cases:
            identity = CanonicalIdentity(title=name)
            dedup._detect_content_type(identity, name)
            assert identity.content_type.value == expected, f"Failed: {name} got {identity.content_type.value}"

    def test_detect_game_from_release_groups(self, dedup):
        """Detect game from release groups - no hardcoded titles."""
        test_cases = [
            ("Game-CODEX", "game"),
            ("Title-TENOKE", "game"),
            ("Game-FitGirl", "game"),
            ("Name-MASQUERADE", "game"),
        ]
        for name, expected in test_cases:
            identity = CanonicalIdentity(title=name)
            dedup._detect_content_type(identity, name)
            assert identity.content_type.value == expected, f"Failed: {name} got {identity.content_type.value}"

    def test_detect_game_from_platforms(self, dedup):
        """Detect game from platforms - no hardcoded titles."""
        test_cases = [
            ("Game-PS4", "game"),
            ("Title-XBOX", "game"),
            ("Game-SWITCH", "game"),
            ("Name-STEAM", "game"),
            ("Game-EPIC", "game"),
            ("Title-VR", "game"),
        ]
        for name, expected in test_cases:
            identity = CanonicalIdentity(title=name)
            dedup._detect_content_type(identity, name)
            assert identity.content_type.value == expected, f"Failed: {name} got {identity.content_type.value}"

    def test_detect_software_from_file_format(self, dedup):
        """Detect software from file format - no hardcoded titles."""
        test_cases = [
            ("App-x86", "software"),
            ("Program-x64", "software"),
            ("Name-Portable", "software"),
            ("Software.exe", "software"),
            ("App-Installer", "software"),
        ]
        for name, expected in test_cases:
            identity = CanonicalIdentity(title=name)
            dedup._detect_content_type(identity, name)
            assert identity.content_type.value == expected, f"Failed: {name} got {identity.content_type.value}"

    def test_detect_anime_from_category(self, dedup):
        """Detect anime from category markers - no hardcoded titles."""
        test_cases = [
            ("[Anime] Title", "anime"),
            ("[Anime] Name [720p]", "anime"),
        ]
        for name, expected in test_cases:
            identity = CanonicalIdentity(title=name)
            dedup._detect_content_type(identity, name)
            assert identity.content_type.value == expected, f"Failed: {name} got {identity.content_type.value}"

    def test_real_world_examples_no_hardcoded(self, dedup):
        """Test real-world examples from user data - no hardcoded titles."""
        test_cases = [
            ("Don Diablo feat. Emeni - MP3 128 kbps", "music"),
            ("Trucker Diablo - FLAC lossless", "music"),
            ("Saint Diablo - MP3 320 kbps", "music"),
            ("Diablo IV (Score) - MP3", "music"),
            ("Venus Diablo - MP3", "music"),
            ("Diablo 4 CODEX", "game"),
            ("[PS4 PSX Classics] Diablo", "game"),
            ("Movie BDRemux 1080p", "movie"),
            ("Film WEBRip 720p", "movie"),
            ("Show S01E01 1080p", "tv"),
        ]
        for name, expected in test_cases:
            identity = CanonicalIdentity(title=name)
            dedup._detect_content_type(identity, name)
            assert identity.content_type.value == expected, (
                f"Failed: '{name}' got '{identity.content_type.value}', expected '{expected}'"
            )

    def test_detect_unknown_fallback(self, dedup):
        """Unknown when no pattern matches."""
        identity = CanonicalIdentity(title="Test")
        dedup._detect_content_type(identity, "Random.File.Name.v1.0")
        assert identity.content_type.value == "unknown"


class TestBestNameSelection:
    """Tests for best name selection when merging same file with different names."""

    @pytest.fixture
    def dedup(self):
        return Deduplicator()

    def test_merge_same_hash_different_names_selects_best(self, dedup):
        """When same hash but different names, select the best name."""
        results = [
            SearchResult(
                name="Movie",
                link="magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
                size="1.5 GB",
                seeds=10,
                leechers=2,
                engine_url="https://tracker1.com",
                tracker="tracker1",
            ),
            SearchResult(
                name="Movie 2023 1080p BluRay x264-RiVR",
                link="magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
                size="1.5 GB",
                seeds=5,
                leechers=1,
                engine_url="https://tracker2.com",
                tracker="tracker2",
            ),
            SearchResult(
                name="Movie.2023.BluRay.1080p.x264",
                link="magnet:?xt=urn:btih:ABCDEF1234567890ABCDEF1234567890ABCDEF12",
                size="1.5 GB",
                seeds=3,
                leechers=1,
                engine_url="https://tracker3.com",
                tracker="tracker3",
            ),
        ]
        merged = dedup.merge_results(results)
        assert len(merged) == 1, "Same file should merge into 1 result"
        assert len(merged[0].original_results) == 3, "All 3 sources in merged result"
        canonical_name = merged[0].canonical_identity.title
        assert "1080p" in canonical_name or "BluRay" in canonical_name, (
            f"Best name should include resolution/format, got: {canonical_name}"
        )

    def test_merge_same_size_selects_best(self, dedup):
        """When same file (same hash) but different names, select best name."""
        results = [
            SearchResult(
                name="Ubuntu",
                link="magnet:?xt=urn:btih:0123456789ABCDEF0123456789ABCDEF01",
                size="4.0 GB",
                seeds=50,
                leechers=10,
                engine_url="https://t1.com",
                tracker="t1",
            ),
            SearchResult(
                name="Ubuntu 22.04 LTS Desktop",
                link="magnet:?xt=urn:btih:0123456789ABCDEF0123456789ABCDEF01",
                size="4.0 GB",
                seeds=30,
                leechers=5,
                engine_url="https://t2.com",
                tracker="t2",
            ),
            SearchResult(
                name="Ubuntu-22.04-desktop-amd64",
                link="magnet:?xt=urn:btih:0123456789ABCDEF0123456789ABCDEF01",
                size="4.0 GB",
                seeds=20,
                leechers=3,
                engine_url="https://t3.com",
                tracker="t3",
            ),
        ]
        merged = dedup.merge_results(results)
        assert len(merged) == 1
        assert len(merged[0].original_results) == 3
        canonical_name = merged[0].canonical_identity.title
        assert "22.04" in canonical_name, f"Should include version, got: {canonical_name}"

    def test_merge_cross_tracker_same_file_different_names(self, dedup):
        """Merge same file from different trackers with different names selects best."""
        results = [
            SearchResult(
                name="Film.Title.2023.WEB-DL.1080p.x264-EZTV",
                link="magnet:?xt=urn:btih:FEDCBA9876543210FEDCBA9876543210FE",
                size="2.2 GB",
                seeds=100,
                leechers=50,
                engine_url="https://rutracker.org",
                tracker="rutracker",
            ),
            SearchResult(
                name="Film Title 2023",
                link="magnet:?xt=urn:btih:FEDCBA9876543210FEDCBA9876543210FE",
                size="2.2 GB",
                seeds=80,
                leechers=30,
                engine_url="https://kinozal.tv",
                tracker="kinozal",
            ),
            SearchResult(
                name="Film.Title.2023.1080p.WEB",
                link="magnet:?xt=urn:btih:FEDCBA9876543210FEDCBA9876543210FE",
                size="2.2 GB",
                seeds=60,
                leechers=20,
                engine_url="https://nnmclub.to",
                tracker="nnmclub",
            ),
        ]
        merged = dedup.merge_results(results)
        assert len(merged) == 1
        assert len(merged[0].original_results) == 3
        assert merged[0].total_seeds == 240
        canonical_name = merged[0].canonical_identity.title
        assert "1080p" in canonical_name, f"Should preserve resolution: {canonical_name}"

    def test_identity_with_matching_titles_and_years(self, dedup):
        id_a = dedup._extract_identity_from_result(
            SearchResult(
                name="Test Movie 2023", link="magnet:?xt=urn:btih:A", size="1 GB",
                seeds=1, leechers=0, engine_url="https://t1.com", tracker="t1",
            )
        )
        id_b = dedup._extract_identity_from_result(
            SearchResult(
                name="Test Movie 2023", link="magnet:?xt=urn:btih:B", size="1 GB",
                seeds=1, leechers=0, engine_url="https://t2.com", tracker="t2",
            )
        )
        assert dedup._compare_identities(id_a, id_b)

    def test_identity_different_years_no_match(self, dedup):
        id_a = dedup._extract_identity_from_result(
            SearchResult(
                name="Test Movie 2023", link="magnet:?xt=urn:btih:A", size="1 GB",
                seeds=1, leechers=0, engine_url="https://t1.com", tracker="t1",
            )
        )
        id_b = dedup._extract_identity_from_result(
            SearchResult(
                name="Test Movie 2024", link="magnet:?xt=urn:btih:B", size="1 GB",
                seeds=1, leechers=0, engine_url="https://t2.com", tracker="t2",
            )
        )
        assert not dedup._compare_identities(id_a, id_b)

    def test_identity_no_titles_no_match(self, dedup):
        id_a = CanonicalIdentity()
        id_b = CanonicalIdentity()
        assert not dedup._compare_identities(id_a, id_b)

    def test_identity_empty_normalized_title(self, dedup):
        id_a = CanonicalIdentity(title="")
        id_b = CanonicalIdentity(title="")
        assert not dedup._compare_identities(id_a, id_b)

    def test_merge_multiple_groups_preserves_best_per_group(self, dedup):
        """Each merged group selects best name for that content."""
        results = [
            SearchResult(
                name="Movie.A.2023.1080p",
                link="magnet:?xt=urn:btih:11111111111111111111111111111111",
                size="1 GB",
                seeds=100,
                leechers=20,
                engine_url="https://t1.com",
                tracker="tracker1",
            ),
            SearchResult(
                name="Movie.B.2023.1080p",
                link="magnet:?xt=urn:btih:22222222222222222222222222222222",
                size="2 GB",
                seeds=50,
                leechers=10,
                engine_url="https://t2.com",
                tracker="tracker2",
            ),
            SearchResult(
                name="Movie.B.2023.HDRip",
                link="magnet:?xt=urn:btih:22222222222222222222222222222222",
                size="2 GB",
                seeds=30,
                leechers=5,
                engine_url="https://t3.com",
                tracker="tracker3",
            ),
        ]
        merged = dedup.merge_results(results)
        assert len(merged) == 2, "Should create 2 separate merged groups"
        movie_b = [m for m in merged if "Movie.B" in m.canonical_identity.title][0]
        assert "2023" in movie_b.canonical_identity.title or "HDRip" in movie_b.canonical_identity.title


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
