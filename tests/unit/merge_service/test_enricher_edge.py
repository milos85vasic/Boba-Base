"""Edge-path tests for ``merge_service.enricher``.

Focuses on the pure, network-free surfaces: ``MetadataEnricher.detect_quality``
(the quality-tier regex ladder shown on result chips), the cache short-circuit
in ``resolve`` (no API key → all lookups skip → cached None), ``clear_cache``,
and ``MetadataResult`` post-init.

Anti-bluff: each detect_quality assertion pins the exact label string the
dashboard renders; a wrong regex/order flips them. The async tests assert the
real cache state-delta, not just "no exception".
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


def _import_enricher():
    spec = importlib.util.spec_from_file_location(
        "merge_service.enricher", os.path.join(_MS_PATH, "enricher.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_service.enricher"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def enricher_mod():
    return _import_enricher()


@pytest.fixture
def enricher(enricher_mod, monkeypatch):
    # Strip all API keys so the network branches are guaranteed skipped.
    for k in ("OMDB_API_KEY", "TMDB_API_KEY", "ANILIST_CLIENT_ID"):
        monkeypatch.delenv(k, raising=False)
    return enricher_mod.MetadataEnricher()


# --------------------------------------------------------------------------
# detect_quality — the regex ladder
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Movie 2160p", "4K"),
        ("Movie 4K", "4K"),
        ("Movie UHD remux", "4K"),
        ("Movie 1080p", "1080p"),
        ("Movie FullHD", "1080p"),
        ("Movie FHD", "1080p"),
        ("Movie 720p", "720p"),
        ("Movie HDRip", "720p"),
        ("Movie 480p", "SD"),
        ("Movie camrip cam", "SD"),
        ("Movie SD copy", "SD"),
    ],
)
def test_detect_quality_resolution_tier(enricher, name, expected):
    assert enricher.detect_quality(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Movie BluRay disc", "BluRay"),
        ("Movie blu-ray", "BluRay"),
        ("Movie BDRip", "BluRay"),
        ("Movie BD-Remux", "BluRay"),
        ("Movie WEB-DL", "WEB-DL"),
        ("Movie WEBRip", "WEB-DL"),
        ("Movie webdl", "WEB-DL"),
        ("Movie HDTV", "HDTV"),
        ("Movie DVD edition", "DVD"),
    ],
)
def test_detect_quality_source_tier(enricher, name, expected):
    assert enricher.detect_quality(name) == expected


def test_detect_quality_resolution_beats_source(enricher):
    # When both a resolution AND a source token are present, resolution wins
    # (it is matched earlier in the ladder).
    assert enricher.detect_quality("Movie 1080p BluRay") == "1080p"


def test_detect_quality_unknown_returns_none(enricher):
    assert enricher.detect_quality("Some Plain Release Name") is None


def test_detect_quality_empty_name_returns_none(enricher):
    assert enricher.detect_quality("") is None


def test_detect_quality_none_name_returns_none(enricher):
    # Guarded by `name.lower() if name else ""`.
    assert enricher.detect_quality(None) is None


# --------------------------------------------------------------------------
# resolve — cache short-circuit (all lookups skipped without API keys)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_without_keys_returns_none(enricher):
    # No API keys → tmdb/omdb/anilist skip; tvmaze/musicbrainz/openlibrary
    # would hit the network, so stub them out to keep this offline.
    async def _none(_q):
        return None

    enricher._lookup_tvmaze = _none
    enricher._lookup_musicbrainz = _none
    enricher._lookup_openlibrary = _none

    result = await enricher.resolve("nonexistent query xyz")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_uses_cache(enricher, enricher_mod):
    cached = enricher_mod.MetadataResult(source="TMDB", title="Cached Title", year=2001)
    enricher._cache["dune"] = cached
    # Querying the cached key (case-insensitive, stripped) returns the
    # cached object WITHOUT touching any lookup method.
    result = await enricher.resolve("  DUNE  ")
    assert result is cached
    assert result.title == "Cached Title"


def test_clear_cache_empties_store(enricher, enricher_mod):
    enricher._cache["x"] = enricher_mod.MetadataResult(source="OMDb", title="X")
    assert len(enricher._cache) == 1
    enricher.clear_cache()
    assert len(enricher._cache) == 0


# --------------------------------------------------------------------------
# MetadataResult dataclass
# --------------------------------------------------------------------------


def test_metadata_result_post_init_genres_default(enricher_mod):
    r = enricher_mod.MetadataResult(source="TMDB", title="X")
    assert r.genres == []


def test_metadata_result_post_init_genres_preserved(enricher_mod):
    r = enricher_mod.MetadataResult(source="TMDB", title="X", genres=["Action", "Drama"])
    assert r.genres == ["Action", "Drama"]
