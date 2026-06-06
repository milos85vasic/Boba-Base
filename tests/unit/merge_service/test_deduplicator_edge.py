"""Edge/error-path tests for ``merge_service.deduplicator.Deduplicator``.

Anti-bluff: each test asserts a real observable dedup outcome — distinct
items stay distinct, true duplicates collapse into ONE merged group with
both sources, the freeleech rule actually prevents a bad merge, sizes
parse to real byte counts, content-type detection tags the right enum.
A wrong tier ladder, regex, or tie-breaker flips these.
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


def _import(modname: str):
    spec = importlib.util.spec_from_file_location(
        f"merge_service.{modname}", os.path.join(_MS_PATH, f"{modname}.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"merge_service.{modname}"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def search_mod():
    return _import("search")


@pytest.fixture(scope="module")
def dedup_mod(search_mod):  # ensure search is loaded first (deduplicator imports it)
    return _import("deduplicator")


@pytest.fixture
def dedup(dedup_mod):
    return dedup_mod.Deduplicator()


def _result(search_mod, name, link="", size="1.0 GB", seeds=0, leechers=0, tracker="rutracker", freeleech=False):
    return search_mod.SearchResult(
        name=name,
        link=link,
        size=size,
        seeds=seeds,
        leechers=leechers,
        engine_url="https://x.example",
        tracker=tracker,
        freeleech=freeleech,
    )


# --------------------------------------------------------------------------
# merge_results — grouping behaviour
# --------------------------------------------------------------------------


def test_empty_input_yields_empty(dedup):
    assert dedup.merge_results([]) == []


def test_distinct_titles_stay_distinct(dedup, search_mod):
    a = _result(search_mod, "Inception 2010 1080p", link="magnet:?xt=urn:btih:" + "a" * 40)
    b = _result(search_mod, "The Matrix 1999 1080p", link="magnet:?xt=urn:btih:" + "b" * 40)
    merged = dedup.merge_results([a, b])
    assert len(merged) == 2


def test_identical_infohash_collapses_to_one_group(dedup, search_mod):
    h = "magnet:?xt=urn:btih:" + "c" * 40
    a = _result(search_mod, "Totally Different Title One", link=h, tracker="rutracker", seeds=5)
    b = _result(search_mod, "Completely Other Words Here", link=h, tracker="kinozal", seeds=3)
    merged = dedup.merge_results([a, b])
    assert len(merged) == 1
    assert len(merged[0].original_results) == 2
    # Both source trackers are recorded.
    trackers = {r.tracker for r in merged[0].original_results}
    assert trackers == {"rutracker", "kinozal"}


def test_same_title_year_collapses_via_metadata_tier(dedup, search_mod):
    a = _result(search_mod, "Inception 2010 1080p BluRay", link="https://a/1", tracker="rutracker", seeds=10)
    b = _result(search_mod, "Inception 2010 1080p WEB-DL", link="https://b/2", tracker="kinozal", seeds=2)
    merged = dedup.merge_results([a, b])
    assert len(merged) == 1
    assert len(merged[0].original_results) == 2
    # total_seeds aggregates both sources.
    assert merged[0].total_seeds == 12


def test_seed_count_drives_canonical_seed_ordering(dedup, search_mod):
    # Higher-seed result is popped first as the group seed (deterministic).
    low = _result(search_mod, "Inception 2010 1080p A", link="https://a", tracker="rutracker", seeds=1)
    high = _result(search_mod, "Inception 2010 1080p B", link="https://b", tracker="kinozal", seeds=99)
    merged = dedup.merge_results([low, high])
    assert len(merged) == 1
    # The first original_result is the higher-seed seed.
    assert merged[0].original_results[0].seeds == 99


# --------------------------------------------------------------------------
# freeleech cross-tracker conflict rule
# --------------------------------------------------------------------------


def test_non_freeleech_iptorrents_not_merged_with_other_tracker(dedup, search_mod):
    ipt = _result(search_mod, "Inception 2010 1080p", link="https://ipt", tracker="iptorrents", freeleech=False)
    other = _result(search_mod, "Inception 2010 1080p", link="https://rt", tracker="rutracker")
    merged = dedup.merge_results([ipt, other])
    # The freeleech-conflict guard must keep them as TWO separate groups.
    assert len(merged) == 2


def test_freeleech_iptorrents_may_merge_with_other_tracker(dedup, search_mod):
    ipt = _result(search_mod, "Inception 2010 1080p", link="https://ipt", tracker="iptorrents", freeleech=True)
    other = _result(search_mod, "Inception 2010 1080p", link="https://rt", tracker="rutracker")
    merged = dedup.merge_results([ipt, other])
    assert len(merged) == 1


def test_freeleech_conflict_predicate_symmetry(dedup, search_mod):
    a = _result(search_mod, "X", tracker="iptorrents", freeleech=False)
    b = _result(search_mod, "X", tracker="rutracker")
    assert dedup._is_cross_tracker_freeleech_conflict(a, b) is True
    assert dedup._is_cross_tracker_freeleech_conflict(b, a) is True
    # Two iptorrents results are NOT a cross-tracker conflict.
    c = _result(search_mod, "X", tracker="iptorrents", freeleech=False)
    assert dedup._is_cross_tracker_freeleech_conflict(a, c) is False


# --------------------------------------------------------------------------
# _parse_size — defensive coercion (the int/-1 sentinel crash regression)
# --------------------------------------------------------------------------


def test_parse_size_none(dedup):
    assert dedup._parse_size(None) is None


def test_parse_size_negative_int_sentinel(dedup):
    # -1 byte-count sentinel must not crash and must be treated as unknown.
    assert dedup._parse_size(-1) is None


def test_parse_size_positive_int(dedup):
    assert dedup._parse_size(2048) == 2048.0


def test_parse_size_empty_string(dedup):
    assert dedup._parse_size("") is None


def test_parse_size_unparseable_string(dedup):
    assert dedup._parse_size("a lot") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 KB", 1024.0),
        ("2 MB", 2 * 1024**2),
        ("3 GB", 3 * 1024**3),
        ("1 TB", 1024**4),
        ("512 B", 512.0),
    ],
)
def test_parse_size_units(dedup, text, expected):
    assert dedup._parse_size(text) == expected


def test_parse_size_non_string_object(dedup):
    assert dedup._parse_size(object()) is None


# --------------------------------------------------------------------------
# _extract_infohash
# --------------------------------------------------------------------------


def test_extract_infohash_from_magnet(dedup):
    h = "a1b2c3d4" * 5  # 40 hex chars
    assert dedup._extract_infohash(f"magnet:?xt=urn:btih:{h}&dn=x") == h


def test_extract_infohash_none_for_empty(dedup):
    assert dedup._extract_infohash("") is None


def test_extract_infohash_none_for_http_url(dedup):
    assert dedup._extract_infohash("https://tracker/dl.php?id=1") is None


# --------------------------------------------------------------------------
# _compare_name_and_size — tier 3
# --------------------------------------------------------------------------


def test_name_size_match_within_tolerance(dedup, search_mod):
    a = _result(search_mod, "Inception 2010 1080p", size="4000 MB")
    b = _result(search_mod, "Inception 2010 1080p", size="4010 MB")  # 10MB diff < 50MB tol
    assert dedup._compare_name_and_size(a, b) is True


def test_name_size_mismatch_beyond_tolerance(dedup, search_mod):
    a = _result(search_mod, "Inception 2010 1080p", size="4000 MB")
    b = _result(search_mod, "Inception 2010 1080p", size="6000 MB")
    assert dedup._compare_name_and_size(a, b) is False


def test_name_size_unparseable_size_no_match(dedup, search_mod):
    a = _result(search_mod, "Inception 2010 1080p", size="???")
    b = _result(search_mod, "Inception 2010 1080p", size="4 GB")
    assert dedup._compare_name_and_size(a, b) is False


# --------------------------------------------------------------------------
# _detect_content_type — branch coverage on the priority ladder
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("[anime] One Piece 1000", "ANIME"),
        ("Show S02E10 720p", "TV_SHOW"),
        ("Album (Progressive Rock) 2020", "MUSIC"),
        ("Great Story audiobook mp3", "AUDIOBOOK"),
        ("Elden Ring CODEX", "GAME"),
        ("App Setup installer.exe", "SOFTWARE"),
        ("Arch Linux 2024 iso", "SOFTWARE"),
        ("Some Database Server tool 2024", "SOFTWARE"),
        ("Movie 2020 BluRay x265", "MOVIE"),
        ("Movie 1080p", "MOVIE"),
        ("Novel Collection epub", "EBOOK"),
        ("Artist Discography flac", "MUSIC"),
        ("Indie band live set", "MUSIC"),
        ("Game OST score", "MUSIC"),
        ("zzz qqq unidentifiable blob", "UNKNOWN"),
    ],
)
def test_detect_content_type_ladder(dedup, search_mod, name, expected):
    identity = search_mod.CanonicalIdentity(title=name)
    dedup._detect_content_type(identity, name)
    assert identity.content_type == search_mod.ContentType[expected], name


# --------------------------------------------------------------------------
# _score_name — best-name selection
# --------------------------------------------------------------------------


def test_score_name_prefers_richer_release_name(dedup):
    plain = dedup._score_name("inception")
    rich = dedup._score_name("Inception 2020 1080p BluRay x265 - GROUP")
    assert rich > plain


def test_update_to_best_name_picks_richest(dedup, search_mod):
    poor = _result(search_mod, "inception", link="https://a", tracker="rutracker", seeds=1)
    rich = _result(search_mod, "Inception 2020 1080p BluRay x265 - GRP", link="https://b", tracker="kinozal", seeds=1)
    h = "magnet:?xt=urn:btih:" + "d" * 40
    poor.link = h
    rich.link = h  # force a merge via infohash
    merged = dedup.merge_results([poor, rich])
    assert len(merged) == 1
    # canonical identity should be derived from the richer name.
    assert "Inception" in (merged[0].canonical_identity.title or "")


# --------------------------------------------------------------------------
# _calculate_similarity — fuzzy fallback
# --------------------------------------------------------------------------


def test_similarity_identical_high(dedup):
    assert dedup._calculate_similarity("Inception 2010", "Inception 2010") >= 0.99


def test_similarity_disjoint_low(dedup):
    assert dedup._calculate_similarity("Inception", "Totally Unrelated Words") < 0.85
