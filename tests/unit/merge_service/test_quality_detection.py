"""
Unit tests for quality detection and size parsing functions in routes.py.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

import importlib.util

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

_merge_service_mod = sys.modules.setdefault("merge_service", type(sys)("merge_service"))
_merge_service_mod.__path__ = [_MS_PATH]

_search_spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
_search_mod = importlib.util.module_from_spec(_search_spec)
sys.modules["merge_service.search"] = _search_mod
_search_spec.loader.exec_module(_search_mod)

_enricher_spec = importlib.util.spec_from_file_location("merge_service.enricher", os.path.join(_MS_PATH, "enricher.py"))
_enricher_mod = importlib.util.module_from_spec(_enricher_spec)
sys.modules["merge_service.enricher"] = _enricher_mod
_enricher_spec.loader.exec_module(_enricher_mod)

_jackett_spec = importlib.util.spec_from_file_location("merge_service.jackett_autoconfig", os.path.join(_MS_PATH, "jackett_autoconfig.py"))
_jackett_mod = importlib.util.module_from_spec(_jackett_spec)
sys.modules["merge_service.jackett_autoconfig"] = _jackett_mod
_jackett_spec.loader.exec_module(_jackett_mod)

_scheduler_spec = importlib.util.spec_from_file_location("merge_service.scheduler", os.path.join(_MS_PATH, "scheduler.py"))
_scheduler_mod = importlib.util.module_from_spec(_scheduler_spec)
sys.modules["merge_service.scheduler"] = _scheduler_mod
_scheduler_spec.loader.exec_module(_scheduler_mod)

_validator_spec = importlib.util.spec_from_file_location("merge_service.validator", os.path.join(_MS_PATH, "validator.py"))
_validator_mod = importlib.util.module_from_spec(_validator_spec)
sys.modules["merge_service.validator"] = _validator_mod
_validator_spec.loader.exec_module(_validator_mod)

_routes_path = os.path.join(_SRC_PATH, "api", "routes.py")
_spec = importlib.util.spec_from_file_location("api_routes", _routes_path)
_routes_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("api", type(sys)("api"))
sys.modules["api"].__path__ = [os.path.join(_SRC_PATH, "api")]
_spec.loader.exec_module(_routes_mod)
_detect_quality = _routes_mod._detect_quality
_parse_size_to_bytes = _routes_mod._parse_size_to_bytes


class TestDetectQuality:
    def test_2160p_is_uhd_4k(self):
        assert _detect_quality("Interstellar 2160p UHD BluRay", "") == "uhd_4k"

    def test_4k_keyword_is_uhd_4k(self):
        assert _detect_quality("Interstellar 4K Remux", "") == "uhd_4k"

    def test_uhd_keyword_is_uhd_4k(self):
        assert _detect_quality("Interstellar UHD BluRay", "") == "uhd_4k"

    def test_1080p_is_full_hd(self):
        assert _detect_quality("Interstellar 1080p BluRay x264", "") == "full_hd"

    def test_bluray_keyword_is_full_hd(self):
        assert _detect_quality("Interstellar BluRay x264", "") == "full_hd"

    def test_720p_is_hd(self):
        assert _detect_quality("Interstellar 720p WEB-DL", "") == "hd"

    def test_480p_is_sd(self):
        assert _detect_quality("Interstellar 480p DVDRip", "") == "sd"

    def test_dvdrip_is_sd(self):
        assert _detect_quality("Interstellar DVDRip XviD", "") == "sd"

    def test_size_50gb_is_uhd_4k(self):
        assert _detect_quality("Something", "50 GB") == "uhd_4k"

    def test_size_10gb_is_full_hd(self):
        assert _detect_quality("Something", "10 GB") == "full_hd"

    def test_size_3gb_is_hd(self):
        assert _detect_quality("Something", "3 GB") == "hd"

    def test_size_500mb_is_sd(self):
        assert _detect_quality("Something", "500 MB") == "sd"

    def test_size_10mb_is_unknown(self):
        assert _detect_quality("Something", "10 MB") == "unknown"

    def test_no_quality_no_size_is_unknown(self):
        assert _detect_quality("Random Title", "") == "unknown"

    def test_empty_name_empty_size_is_unknown(self):
        assert _detect_quality("", "") == "unknown"

    def test_none_name(self):
        assert _detect_quality(None, "") == "unknown"

    def test_name_quality_overrides_size(self):
        assert _detect_quality("Movie 480p", "50 GB") == "sd"

    def test_size_threshold_boundary_uhd(self):
        assert _detect_quality("Something", "40 GB") == "uhd_4k"
        assert _detect_quality("Something", "39.9 GB") == "full_hd"

    def test_size_threshold_boundary_full_hd(self):
        assert _detect_quality("Something", "8 GB") == "full_hd"

    def test_size_threshold_boundary_hd(self):
        assert _detect_quality("Something", "2 GB") == "hd"

    def test_size_threshold_boundary_sd(self):
        assert _detect_quality("Something", "300 MB") == "sd"
        assert _detect_quality("Something", "299 MB") == "unknown"

    def test_webdl_keyword_is_hd(self):
        assert _detect_quality("Movie WEBDL", "") == "hd"

    def test_hdrip_keyword_is_hd(self):
        assert _detect_quality("Movie HDRip", "") == "hd"

    def test_camrip_is_sd(self):
        assert _detect_quality("Movie CAMRip", "") == "sd"

    def test_fullhd_keyword(self):
        assert _detect_quality("Movie FullHD", "") == "full_hd"

    def test_fhd_keyword(self):
        assert _detect_quality("Movie FHD", "") == "full_hd"


class TestParseSizeToBytes:
    def test_gb(self):
        result = _parse_size_to_bytes("2.5 GB")
        expected = 2.5 * (1024**3)
        assert abs(result - expected) < 1

    def test_mb(self):
        result = _parse_size_to_bytes("500 MB")
        expected = 500 * (1024**2)
        assert abs(result - expected) < 1

    def test_tb(self):
        result = _parse_size_to_bytes("1 TB")
        expected = 1024**4
        assert abs(result - expected) < 1

    def test_kb(self):
        result = _parse_size_to_bytes("1024 KB")
        assert result == 1024 * 1024

    def test_bytes(self):
        assert _parse_size_to_bytes("512 B") == 512

    def test_empty_string(self):
        assert _parse_size_to_bytes("") == 0

    def test_none(self):
        assert _parse_size_to_bytes(None) == 0

    def test_plain_number(self):
        assert _parse_size_to_bytes("12345") == 12345.0

    def test_no_units(self):
        assert _parse_size_to_bytes("just text") == 0

    def test_case_insensitive(self):
        assert _parse_size_to_bytes("1 gb") == _parse_size_to_bytes("1 GB")

    def test_float_size(self):
        result = _parse_size_to_bytes("1.5 TB")
        expected = 1.5 * (1024**4)
        assert abs(result - expected) < 1

    def test_zero(self):
        assert _parse_size_to_bytes("0") == 0.0

    def test_whitespace_handling(self):
        assert _parse_size_to_bytes("  10 GB  ") == 10 * (1024**3)
