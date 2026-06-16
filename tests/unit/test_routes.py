import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))

from api.routes import _detect_quality, _is_tracker_url, _parse_size_to_bytes


class TestSortBySeeds:
    def test_sort_by_seeds_descending(self):
        results = [
            {"seeds": 100},
            {"seeds": 50},
            {"seeds": 200},
        ]
        results.sort(key=lambda x: x.get("seeds", 0), reverse=True)
        assert [r["seeds"] for r in results] == [200, 100, 50]

    def test_sort_by_seeds_ascending(self):
        results = [
            {"seeds": 100},
            {"seeds": 50},
            {"seeds": 200},
        ]
        results.sort(key=lambda x: x.get("seeds", 0), reverse=False)
        assert [r["seeds"] for r in results] == [50, 100, 200]

    def test_sort_by_leechers_descending(self):
        results = [
            {"leechers": 100},
            {"leechers": 50},
            {"leechers": 200},
        ]
        results.sort(key=lambda x: x.get("leechers", 0), reverse=True)
        assert [r["leechers"] for r in results] == [200, 100, 50]


class TestParseSizeToBytes:
    def test_gb(self):
        assert _parse_size_to_bytes("4.5 GB") == pytest.approx(4.5 * 1024**3)

    def test_mb(self):
        assert _parse_size_to_bytes("800 MB") == pytest.approx(800 * 1024**2)

    def test_tb(self):
        assert _parse_size_to_bytes("1 TB") == pytest.approx(1024**4)

    def test_kb(self):
        assert _parse_size_to_bytes("512 KB") == pytest.approx(512 * 1024)

    def test_bytes(self):
        assert _parse_size_to_bytes("1024 B") == pytest.approx(1024)

    def test_empty(self):
        assert _parse_size_to_bytes("") == 0

    def test_none(self):
        assert _parse_size_to_bytes(None) == 0

    def test_plain_number(self):
        assert _parse_size_to_bytes("1234567") == pytest.approx(1234567)

    def test_invalid_string(self):
        assert _parse_size_to_bytes("abc") == 0


class TestDetectQuality:
    def test_uhd_4k_in_name(self):
        assert _detect_quality("Movie 2160p HDR", "50 GB") == "uhd_4k"

    def test_4k_in_name(self):
        assert _detect_quality("Movie 4K Remux", "50 GB") == "uhd_4k"

    def test_uhd_in_name(self):
        assert _detect_quality("Movie UHD Bluray", "50 GB") == "uhd_4k"

    def test_full_hd_1080p(self):
        assert _detect_quality("Movie 1080p WEB-DL", "10 GB") == "full_hd"

    def test_hd_720p(self):
        assert _detect_quality("Movie 720p x264", "5 GB") == "hd"

    def test_sd_480p(self):
        assert _detect_quality("Movie 480p DVDRip", "1 GB") == "sd"

    def test_unknown(self):
        assert _detect_quality("random_file", "100 MB") == "unknown"

    def test_fallback_by_size_uhd(self):
        assert _detect_quality("some movie", "50 GB") == "uhd_4k"

    def test_fallback_by_size_hd(self):
        assert _detect_quality("some movie", "15 GB") == "full_hd"

    def test_fallback_by_size_sd(self):
        assert _detect_quality("some movie", "0.8 GB") == "sd"

    def test_unknown_size(self):
        assert _detect_quality("some movie", "abc") == "unknown"

    def test_empty_name(self):
        assert _detect_quality("", "1 GB") == "sd"


class TestIsTrackerUrl:
    def test_rutracker(self):
        assert _is_tracker_url("https://rutracker.org/forum/viewtopic.php?t=123") == "rutracker"

    def test_kinozal(self):
        assert _is_tracker_url("https://kinozal.tv/details.php?id=456") == "kinozal"

    def test_nnmclub(self):
        assert _is_tracker_url("https://nnmclub.to/forum/viewtopic.php?t=789") == "nnmclub"

    def test_nnmclub_me(self):
        assert _is_tracker_url("https://nnmclub.to/forum/viewtopic.php?t=789") == "nnmclub"

    def test_iptorrents(self):
        assert _is_tracker_url("https://iptorrents.com/t/12345") == "iptorrents"

    def test_unknown_url(self):
        assert _is_tracker_url("https://example.com/file.torrent") is None

    def test_empty_url(self):
        assert _is_tracker_url("") is None

    def test_invalid_url(self):
        assert _is_tracker_url("not-a-url") is None

    def test_subdomain_rutracker(self):
        assert _is_tracker_url("https://sub.rutracker.org/thing") == "rutracker"
