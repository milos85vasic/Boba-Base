"""Error/edge-path tests for ``merge_service.search``.

Targets the pure diagnostic + metadata helpers that the SSE dashboard
depends on: ``_classify_plugin_stderr`` (which turns a plugin
subprocess's stderr into a structured error_type the dashboard renders
as a red chip) and ``_detect_result_metadata`` (which infers
content_type + quality from a raw torrent name/size).

These are anti-bluff: each assertion pins a user-observable outcome (the
exact error_type string a chip shows, the exact content_type/quality a
result is tagged with). A wrong classification ladder or regex would
flip these.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]


def _import_search_module():
    spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_service.search"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def search_mod():
    return _import_search_module()


# --------------------------------------------------------------------------
# _classify_plugin_stderr — the diagnostic ladder
# --------------------------------------------------------------------------


def test_classify_empty_stderr_with_deadline_and_no_results(search_mod):
    diag = search_mod._classify_plugin_stderr("", killed_by_deadline=True, had_results=False)
    assert diag["error_type"] == "deadline_timeout"
    assert "25s" in diag["error"]
    assert diag["stderr_tail"] == ""


def test_classify_empty_stderr_benign_when_had_results(search_mod):
    # Deadline hit but rows already streamed → not a timeout error.
    diag = search_mod._classify_plugin_stderr("", killed_by_deadline=True, had_results=True)
    assert diag["error_type"] is None
    assert diag["error"] is None


def test_classify_empty_stderr_no_deadline_is_benign(search_mod):
    diag = search_mod._classify_plugin_stderr("", killed_by_deadline=False, had_results=False)
    assert diag["error_type"] is None
    assert diag["error"] is None
    assert diag["stderr_tail"] == ""


def test_classify_whitespace_only_stderr_is_benign(search_mod):
    diag = search_mod._classify_plugin_stderr("   \n  \t ", killed_by_deadline=False, had_results=False)
    assert diag["error_type"] is None


@pytest.mark.parametrize(
    ("stderr", "expected_type"),
    [
        ("urllib.error.HTTPError: HTTP Error 403: Forbidden", "upstream_http_403"),
        ("Connection error: Forbidden", "upstream_http_403"),
        ("Connection error: Not Found", "upstream_http_404"),
        ("HTTP Error 404: gone", "upstream_http_404"),
        ("Gateway Timeout while fetching", "upstream_timeout"),
        ("HTTP Error 504: backend", "upstream_timeout"),
        ("socket.gaierror: Name does not resolve", "dns_failure"),
        ("Name has no usable address records", "dns_failure"),
        ("ssl: certificate verify failed", "tls_failure"),
        ("[SSL: TLSV1_ALERT_INTERNAL_ERROR] alert", "tls_failure"),
        ("FileNotFoundError: [Errno 2] /config/x", "plugin_env_missing"),
        ("IndexError: list index out of range", "plugin_parse_failure"),
        ("list index out of range", "plugin_parse_failure"),
        ("json.decoder.JSONDecodeError: Expecting value", "plugin_parse_failure"),
        ("'NoneType' object is not iterable", "plugin_crashed"),
        ("TypeError: cannot unpack", "plugin_crashed"),
        ("http.client.IncompleteRead(0 bytes read)", "upstream_incomplete"),
        ("Traceback (most recent call last):", "plugin_crashed"),
        ('{"__error__": "boom"}', "plugin_crashed"),
    ],
)
def test_classify_known_error_signatures(search_mod, stderr, expected_type):
    diag = search_mod._classify_plugin_stderr(stderr, killed_by_deadline=False, had_results=False)
    assert diag["error_type"] == expected_type, f"{stderr!r} should map to {expected_type}"
    assert diag["error"]  # a human summary is always present for real errors
    assert diag["stderr_tail"]  # raw tail is preserved


def test_classify_403_takes_priority_over_generic_traceback(search_mod):
    # A 403 line wins even when a traceback is also present (earlier branch).
    stderr = "Traceback (most recent call last):\nurllib.error.HTTPError: HTTP Error 403: Forbidden"
    diag = search_mod._classify_plugin_stderr(stderr, killed_by_deadline=False, had_results=False)
    assert diag["error_type"] == "upstream_http_403"


def test_classify_benign_noise_stderr(search_mod):
    # Plugin printed informational noise with no recognised error signature.
    diag = search_mod._classify_plugin_stderr(
        '{"__done__": 0}', killed_by_deadline=False, had_results=True
    )
    assert diag["error_type"] is None
    assert diag["error"] is None
    # Even benign noise has its tail preserved for debugging.
    assert diag["stderr_tail"] == '{"__done__": 0}'


def test_classify_stderr_tail_is_truncated_to_400_chars(search_mod):
    long_stderr = "x" * 1000 + "HTTP Error 403: Forbidden"
    diag = search_mod._classify_plugin_stderr(long_stderr, killed_by_deadline=False, had_results=False)
    assert diag["error_type"] == "upstream_http_403"
    assert len(diag["stderr_tail"]) == 400
    # Keeps the *tail* (most recent), so the error line survives.
    assert diag["stderr_tail"].endswith("HTTP Error 403: Forbidden")


# --------------------------------------------------------------------------
# _detect_result_metadata — content_type + quality inference
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected_ct"),
    [
        ("[Anime] Naruto Shippuden 500", "anime"),
        ("Breaking Bad S01E05 1080p", "tv"),
        ("Some Show Season 1-3 Pack", "tv"),
        ("Great Audiobook Unabridged", "audiobook"),
        ("Cyberpunk 2077 FitGirl Repack", "game"),
        ("Ubuntu 22.04 Desktop amd64.iso", "software"),
        ("Inception 2010 BluRay x264", "movie"),
        ("Some Movie 2021 1080p", "movie"),
        ("Dune Part Two 2160p HDR", "movie"),
        ("My Book Collection epub", "ebook"),
        ("Pink Floyd Discography FLAC", "music"),
        ("Random Game OST soundtrack", "music"),
    ],
)
def test_detect_content_type_from_name(search_mod, name, expected_ct):
    ct, _q = search_mod._detect_result_metadata(name, "1.0 GB")
    assert ct == expected_ct, f"{name!r} expected content_type {expected_ct}"


@pytest.mark.parametrize(
    ("name", "expected_q"),
    [
        ("Movie 2160p UHD", "uhd_4k"),
        ("Movie 4K release", "uhd_4k"),
        ("Movie 1080p FullHD", "full_hd"),
        ("Movie 720p HDRip", "hd"),
        ("Movie 480p SD", "sd"),
        ("Movie BluRay disc", "full_hd"),
        ("Movie WEB-DL release", "hd"),
        ("Movie HDTV capture", "hd"),
        ("Movie DVD rip clean", "sd"),
    ],
)
def test_detect_quality_from_name(search_mod, name, expected_q):
    _ct, q = search_mod._detect_result_metadata(name, "1.0 GB")
    assert q == expected_q, f"{name!r} expected quality {expected_q}"


def test_detect_quality_size_fallback_4k(search_mod):
    # No quality token in name → fall back to size buckets.
    _ct, q = search_mod._detect_result_metadata("Mystery Release Name", str(50 * 1024**3))
    assert q == "uhd_4k"


def test_detect_quality_size_fallback_full_hd(search_mod):
    _ct, q = search_mod._detect_result_metadata("Mystery Release Name", str(10 * 1024**3))
    assert q == "full_hd"


def test_detect_quality_size_fallback_hd(search_mod):
    _ct, q = search_mod._detect_result_metadata("Mystery Release Name", str(3 * 1024**3))
    assert q == "hd"


def test_detect_quality_size_fallback_sd(search_mod):
    _ct, q = search_mod._detect_result_metadata("Mystery Release Name", str(400 * 1024**2))
    assert q == "sd"


def test_detect_quality_size_fallback_formatted_string(search_mod):
    # size given as a human string ("40 GB") rather than raw bytes.
    _ct, q = search_mod._detect_result_metadata("Plain Name", "40 GB")
    assert q == "uhd_4k"


def test_detect_quality_tiny_size_yields_none(search_mod):
    _ct, q = search_mod._detect_result_metadata("Plain Name", "5 MB")
    assert q is None


def test_detect_metadata_empty_name(search_mod):
    ct, q = search_mod._detect_result_metadata("", "0 B")
    assert ct is None
    assert q is None


# --------------------------------------------------------------------------
# validate_tracker_name — guard against injection in subprocess script
# --------------------------------------------------------------------------


def test_validate_tracker_name_accepts_valid(search_mod):
    assert search_mod.validate_tracker_name("rutracker") == "rutracker"
    assert search_mod.validate_tracker_name("torrents-csv") == "torrents-csv"
    assert search_mod.validate_tracker_name("a_b_1") == "a_b_1"


@pytest.mark.parametrize("bad", ["", "a b", "a;rm -rf", "a/b", "a.b", "a'b", 'x"y'])
def test_validate_tracker_name_rejects_invalid(search_mod, bad):
    with pytest.raises(ValueError, match="Invalid tracker name"):
        search_mod.validate_tracker_name(bad)


# --------------------------------------------------------------------------
# EncryptedSessionStore — corrupt-token fallback edge path
# --------------------------------------------------------------------------


def test_encrypted_session_store_corrupt_token_returns_default(search_mod):
    from cachetools import TTLCache

    cache: TTLCache = TTLCache(maxsize=8, ttl=60)
    store = search_mod.EncryptedSessionStore(cache)
    # Plant an undecryptable token directly in the backing cache.
    cache["rutracker"] = b"not-a-valid-fernet-token"
    # get() must swallow the decrypt failure and return the default.
    assert store.get("rutracker", "fallback") == "fallback"


def test_encrypted_session_store_roundtrip(search_mod):
    from cachetools import TTLCache

    store = search_mod.EncryptedSessionStore(TTLCache(maxsize=8, ttl=60))
    store["kinozal"] = {"cookies": {"sid": "abc"}}
    assert store["kinozal"] == {"cookies": {"sid": "abc"}}
    assert "kinozal" in store
    # The raw backing value must be an opaque (encrypted) token, never plaintext.
    raw = store._raw_values()[0]
    assert b"abc" not in raw
