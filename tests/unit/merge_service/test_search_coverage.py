"""
Additional coverage for merge_service/search.py — classify_plugin_stderr,
parse helpers, orchestrator init, enabled trackers, authenticated state.
"""

import importlib.util
import os
import sys
from unittest.mock import patch

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_search_spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
_search_mod = importlib.util.module_from_spec(_search_spec)
sys.modules["merge_service.search"] = _search_mod
_search_spec.loader.exec_module(_search_mod)

_classify_plugin_stderr = _search_mod._classify_plugin_stderr
validate_tracker_name = _search_mod.validate_tracker_name
SearchOrchestrator = _search_mod.SearchOrchestrator
SearchResult = _search_mod.SearchResult
_detect_result_metadata = _search_mod._detect_result_metadata
ContentType = _search_mod.ContentType
CanonicalIdentity = _search_mod.CanonicalIdentity
TrackerSource = _search_mod.TrackerSource
MergedResult = _search_mod.MergedResult
TrackerSearchStat = _search_mod.TrackerSearchStat


class TestClassifyPluginStderr:
    def test_empty_deadline_no_results(self):
        r = _classify_plugin_stderr("", killed_by_deadline=True, had_results=False)
        assert r["error_type"] == "deadline_timeout"

    def test_empty_no_deadline(self):
        r = _classify_plugin_stderr("", killed_by_deadline=False, had_results=False)
        assert r["error_type"] is None

    def test_http_403(self):
        r = _classify_plugin_stderr("HTTP Error 403", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "upstream_http_403"

    def test_connection_forbidden(self):
        r = _classify_plugin_stderr("Connection error: Forbidden", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "upstream_http_403"

    def test_http_404(self):
        r = _classify_plugin_stderr("HTTP Error 404", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "upstream_http_404"

    def test_connection_not_found(self):
        r = _classify_plugin_stderr("Connection error: Not Found", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "upstream_http_404"

    def test_gateway_timeout(self):
        r = _classify_plugin_stderr("Gateway Timeout", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "upstream_timeout"

    def test_http_504(self):
        r = _classify_plugin_stderr("HTTP Error 504", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "upstream_timeout"

    def test_dns_failure(self):
        r = _classify_plugin_stderr("Name does not resolve", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "dns_failure"

    def test_dns_no_address(self):
        r = _classify_plugin_stderr("name has no usable address", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "dns_failure"

    def test_tls_failure(self):
        r = _classify_plugin_stderr("SSL: CERTIFICATE_VERIFY_FAILED", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "tls_failure"

    def test_tlsv1_alert(self):
        r = _classify_plugin_stderr("tlsv1_alert handshake failure", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "tls_failure"

    def test_file_not_found(self):
        r = _classify_plugin_stderr("FileNotFoundError", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "plugin_env_missing"

    def test_index_error(self):
        r = _classify_plugin_stderr("IndexError: list index out of range", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "plugin_parse_failure"

    def test_type_error_nonetype(self):
        r = _classify_plugin_stderr("'NoneType' object is not iterable", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "plugin_crashed"

    def test_type_error_generic(self):
        r = _classify_plugin_stderr("TypeError: expected str", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "plugin_crashed"

    def test_json_decode_error(self):
        r = _classify_plugin_stderr("JSONDecodeError: Expecting value", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "plugin_parse_failure"

    def test_incomplete_read(self):
        r = _classify_plugin_stderr("IncompleteRead", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "upstream_incomplete"

    def test_traceback(self):
        r = _classify_plugin_stderr("Traceback (most recent call last)", killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "plugin_crashed"

    def test_error_token(self):
        r = _classify_plugin_stderr('{"__error__": "boom"}', killed_by_deadline=False, had_results=False)
        assert r["error_type"] == "plugin_crashed"

    def test_benign_noise(self):
        r = _classify_plugin_stderr("some random log line", killed_by_deadline=False, had_results=False)
        assert r["error_type"] is None
        assert r["error"] is None

    def test_stderr_tail_truncated(self):
        r = _classify_plugin_stderr("x" * 500, killed_by_deadline=False, had_results=False)
        assert len(r["stderr_tail"]) <= 400


class TestValidateTrackerName:
    def test_valid(self):
        assert validate_tracker_name("rutor") == "rutor"

    def test_valid_with_underscore(self):
        assert validate_tracker_name("some_tracker") == "some_tracker"

    def test_valid_with_digits(self):
        assert validate_tracker_name("tracker123") == "tracker123"

    def test_empty(self):
        with pytest.raises(ValueError):
            validate_tracker_name("")

    def test_special_chars(self):
        with pytest.raises(ValueError):
            validate_tracker_name("bad.name")

    def test_spaces(self):
        with pytest.raises(ValueError):
            validate_tracker_name("bad name")


class TestContentType:
    def test_all_values(self):
        expected = ["movie", "tv", "anime", "music", "audiobook", "game", "software", "ebook", "other", "unknown"]
        assert sorted(e.value for e in ContentType) == sorted(expected)


class TestSearchResultToDict:
    def test_freeleech_with_tracker(self):
        r = SearchResult(
            name="Test",
            link="http://x",
            size="1 GB",
            seeds=10,
            leechers=5,
            engine_url="http://x",
            tracker="iptorrents",
            freeleech=True,
        )
        d = r.to_dict()
        assert d["tracker_display"] == "iptorrents [free]"

    def test_no_freeleech_with_tracker(self):
        r = SearchResult(
            name="Test",
            link="http://x",
            size="1 GB",
            seeds=10,
            leechers=5,
            engine_url="http://x",
            tracker="rutor",
        )
        d = r.to_dict()
        assert d["tracker_display"] == "rutor"

    def test_no_tracker(self):
        r = SearchResult(
            name="Test",
            link="http://x",
            size="1 GB",
            seeds=10,
            leechers=5,
            engine_url="http://x",
        )
        d = r.to_dict()
        assert d["tracker_display"] is None

    def test_to_dict_includes_content_type_and_quality(self):
        r = SearchResult(
            name="Test",
            link="http://x",
            size="1 GB",
            seeds=10,
            leechers=5,
            engine_url="http://x",
            content_type="movie",
            quality="full_hd",
        )
        d = r.to_dict()
        assert d["content_type"] == "movie"
        assert d["quality"] == "full_hd"

    def test_to_dict_content_type_quality_none_by_default(self):
        r = SearchResult(
            name="Test",
            link="http://x",
            size="1 GB",
            seeds=10,
            leechers=5,
            engine_url="http://x",
        )
        d = r.to_dict()
        assert d["content_type"] is None
        assert d["quality"] is None


class TestDetectResultMetadata:
    def test_detects_movie_from_resolution(self):
        ct, q = _detect_result_metadata("My Movie 1080p BluRay", "8 GB")
        assert ct == "movie"
        assert q == "full_hd"

    def test_detects_tv_from_season_episode(self):
        ct, q = _detect_result_metadata("Show S01E05 720p", "1 GB")
        assert ct == "tv"
        assert q == "hd"

    def test_detects_game_from_release_group(self):
        ct, q = _detect_result_metadata("Game FitGirl Repack", "15 GB")
        assert ct == "game"

    def test_detects_software_from_os_name(self):
        ct, q = _detect_result_metadata("Ubuntu 22.04 LTS ISO", "4 GB")
        assert ct == "software"

    def test_detects_ebook_from_format(self):
        ct, q = _detect_result_metadata("Linux Guide EPUB", "5 MB")
        assert ct == "ebook"

    def test_detects_music_from_audio_format(self):
        ct, q = _detect_result_metadata("Album FLAC 2024", "300 MB")
        assert ct == "music"

    def test_quality_size_fallback_uhd(self):
        ct, q = _detect_result_metadata("Some Large File", "50 GB")
        assert q == "uhd_4k"

    def test_quality_size_fallback_hd(self):
        ct, q = _detect_result_metadata("Some Medium File", "3 GB")
        assert q == "hd"

    def test_quality_size_fallback_sd(self):
        ct, q = _detect_result_metadata("Some Small File", "500 MB")
        assert q == "sd"

    def test_quality_unknown_for_tiny_file(self):
        ct, q = _detect_result_metadata("Tiny File", "10 MB")
        assert q is None

    def test_unknown_content_type_when_no_signals(self):
        ct, q = _detect_result_metadata("Random File", "1 GB")
        assert ct is None


class TestCanonicalIdentityToDict:
    def test_with_content_type(self):
        ci = CanonicalIdentity(content_type=ContentType.MOVIE, title="Test Movie")
        d = ci.to_dict()
        assert d["content_type"] == "movie"
        assert d["title"] == "Test Movie"

    def test_no_content_type(self):
        ci = CanonicalIdentity()
        d = ci.to_dict()
        assert d["content_type"] is None


class TestMergedResult:
    def test_add_source_dedup_link(self):
        mr = MergedResult(canonical_identity=CanonicalIdentity())
        r1 = SearchResult(name="A", link="http://a", size="1 GB", seeds=5, leechers=1, engine_url="http://x")
        r2 = SearchResult(name="A", link="http://a", size="1 GB", seeds=3, leechers=2, engine_url="http://y")
        mr.add_source(r1)
        mr.add_source(r2)
        assert len(mr.download_urls) == 1
        assert mr.total_seeds == 8
        assert mr.total_leechers == 3

    def test_to_dict(self):
        mr = MergedResult(canonical_identity=CanonicalIdentity(infohash="abc"))
        d = mr.to_dict()
        assert d["canonical_identity"]["infohash"] == "abc"
        assert "created_at" in d


class TestTrackerSourceToDict:
    def test_basic(self):
        ts = TrackerSource(name="rutor", url="https://rutor.info")
        d = ts.to_dict()
        assert d["name"] == "rutor"
        assert d["enabled"] is True
        assert d["last_checked"] is None


class TestTrackerSearchStatToDict:
    def test_basic(self):
        stat = TrackerSearchStat(name="rutor", status="success", results_count=5)
        d = stat.to_dict()
        assert d["name"] == "rutor"
        assert d["status"] == "success"
        assert d["results_count"] == 5
        assert d["notes"] == {}


class TestSearchOrchestratorInit:
    def test_init_defaults(self):
        orch = SearchOrchestrator()
        assert orch._max_concurrent_searches >= 1
        assert orch._max_concurrent_trackers >= 1
        assert orch._active_search_count == 0
        assert orch._inflight_count == 0

    def test_is_search_queue_full(self):
        orch = SearchOrchestrator()
        orch._active_search_count = orch._max_concurrent_searches
        assert orch.is_search_queue_full() is True

    def test_is_search_queue_not_full(self):
        orch = SearchOrchestrator()
        assert orch.is_search_queue_full() is False


class TestOrchestratorGetEnabledTrackers:
    def test_no_private_creds(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {}, clear=True):
            trackers = orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "rutracker" not in names
            assert "kinozal" not in names
            assert "nnmclub" not in names
            assert "iptorrents" not in names

    def test_with_rutracker_creds(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False):
            trackers = orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "rutracker" in names

    def test_dead_trackers_excluded(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {"ENABLE_DEAD_TRACKERS": "0"}, clear=False):
            trackers = orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "eztv" not in names
            assert "ali213" not in names

    def test_dead_trackers_included_when_enabled(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {"ENABLE_DEAD_TRACKERS": "1"}, clear=False):
            trackers = orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "eztv" in names
            assert "ali213" in names

    def test_jackett_included_when_api_key_set(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {"JACKETT_API_KEY": "real-key-123"}, clear=False):
            trackers = orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "jackett" in names

    def test_jackett_excluded_when_placeholder_key(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {"JACKETT_API_KEY": "YOUR_API_KEY_HERE"}, clear=False):
            trackers = orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "jackett" not in names

    def test_jackett_excluded_when_no_key(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {}, clear=True):
            trackers = orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "jackett" not in names


class TestIsTrackerAuthenticated:
    def test_public_tracker_not_authenticated(self):
        orch = SearchOrchestrator()
        assert orch._is_tracker_authenticated("rutor") is False

    def test_rutracker_with_env(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False):
            assert orch._is_tracker_authenticated("rutracker") is True

    def test_kinozal_with_env(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {"KINOZAL_USERNAME": "u", "KINOZAL_PASSWORD": "p"}, clear=False):
            assert orch._is_tracker_authenticated("kinozal") is True

    def test_nnmclub_with_env(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {"NNMCLUB_COOKIES": "sid=abc"}, clear=False):
            assert orch._is_tracker_authenticated("nnmclub") is True

    def test_iptorrents_with_env(self):
        orch = SearchOrchestrator()
        with patch.dict(os.environ, {"IPTORRENTS_USERNAME": "u", "IPTORRENTS_PASSWORD": "p"}, clear=False):
            assert orch._is_tracker_authenticated("iptorrents") is True

    def test_unknown_tracker(self):
        orch = SearchOrchestrator()
        assert orch._is_tracker_authenticated("unknown_tracker") is False


class TestParseSizeString:
    def test_none(self):
        orch = SearchOrchestrator()
        assert orch._parse_size_string(None) == 0

    def test_int(self):
        orch = SearchOrchestrator()
        assert orch._parse_size_string(1024) == 1024

    def test_negative_int(self):
        orch = SearchOrchestrator()
        assert orch._parse_size_string(-1) == 0

    def test_float(self):
        orch = SearchOrchestrator()
        assert orch._parse_size_string(1.5) == 1

    def test_non_string(self):
        orch = SearchOrchestrator()
        assert orch._parse_size_string([1, 2]) == 0

    def test_gb(self):
        orch = SearchOrchestrator()
        assert orch._parse_size_string("1 GB") == 1024**3

    def test_mb(self):
        orch = SearchOrchestrator()
        assert orch._parse_size_string("512 MB") == 512 * 1024**2

    def test_tb(self):
        orch = SearchOrchestrator()
        assert orch._parse_size_string("1 TB") == 1024**4


class TestFormatSize:
    def test_zero(self):
        orch = SearchOrchestrator()
        assert orch._format_size(0) == "0 B"

    def test_bytes(self):
        orch = SearchOrchestrator()
        assert orch._format_size(512) == "512.0 B"

    def test_kb(self):
        orch = SearchOrchestrator()
        assert orch._format_size(1024) == "1.0 KB"

    def test_gb(self):
        orch = SearchOrchestrator()
        assert orch._format_size(1024**3) == "1.0 GB"

    def test_very_large(self):
        orch = SearchOrchestrator()
        result = orch._format_size(1024**5)
        assert "PB" in result


class TestGetLiveResults:
    def test_empty(self):
        orch = SearchOrchestrator()
        assert orch.get_live_results("nonexistent") == []

    def test_from_tracker_results(self):
        orch = SearchOrchestrator()
        r = SearchResult(name="A", link="http://a", size="1 GB", seeds=1, leechers=0, engine_url="http://x")
        orch._tracker_results["s1"] = {"rutor": [r]}
        result = orch.get_live_results("s1")
        assert len(result) == 1

    def test_fallback_merged_results(self):
        orch = SearchOrchestrator()
        r = SearchResult(name="A", link="http://a", size="1 GB", seeds=1, leechers=0, engine_url="http://x")
        orch._last_merged_results["s1"] = ([], [r])
        result = orch.get_live_results("s1")
        assert len(result) == 1


class TestGetSearchStatus:
    def test_not_found(self):
        orch = SearchOrchestrator()
        assert orch.get_search_status("nonexistent") is None


class TestGetActiveSearches:
    def test_empty(self):
        orch = SearchOrchestrator()
        assert orch.get_active_searches() == []


class TestGetAllTrackerResults:
    def test_empty(self):
        orch = SearchOrchestrator()
        assert orch.get_all_tracker_results("nonexistent") == []

    def test_with_results(self):
        orch = SearchOrchestrator()
        r = SearchResult(name="A", link="http://a", size="1 GB", seeds=1, leechers=0, engine_url="http://x")
        orch._tracker_results["s1"] = {"rutor": [r], "piratebay": []}
        result = orch.get_all_tracker_results("s1")
        assert len(result) == 1


class TestGetLiveResultsEdgeCases:
    def test_empty_tracker_results_in_dict(self):
        orch = SearchOrchestrator()
        orch._tracker_results["s1"] = {"rutor": []}
        result = orch.get_live_results("s1")
        assert result == []


class TestStreamTokens:
    def test_issue_and_validate(self):
        orch = SearchOrchestrator()
        token = orch.issue_stream_token("sid")
        assert orch.validate_stream_token("sid", token) is True

    def test_wrong_token(self):
        orch = SearchOrchestrator()
        orch.issue_stream_token("sid")
        assert orch.validate_stream_token("sid", "wrong") is False

    def test_no_token_issued(self):
        orch = SearchOrchestrator()
        assert orch.validate_stream_token("missing", "any") is False

    def test_none_token(self):
        orch = SearchOrchestrator()
        orch.issue_stream_token("sid")
        assert orch.validate_stream_token("sid", None) is False


class TestGetSearchStatusFound:
    def test_found(self):
        orch = SearchOrchestrator()
        from merge_service.search import SearchMetadata
        from datetime import datetime
        meta = SearchMetadata(query="q", search_id="sid", started_at=datetime.now())
        orch._active_searches["sid"] = meta
        assert orch.get_search_status("sid") is meta


class TestGetActiveSearchesNonEmpty:
    def test_with_searches(self):
        orch = SearchOrchestrator()
        from merge_service.search import SearchMetadata
        from datetime import datetime
        meta = SearchMetadata(query="q", search_id="sid", started_at=datetime.now())
        orch._active_searches["sid"] = meta
        assert len(orch.get_active_searches()) == 1
