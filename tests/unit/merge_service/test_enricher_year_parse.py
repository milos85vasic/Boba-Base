"""RED-first regression guard for the unsafe year-parse in ``merge_service.enricher``.

Forensic anchor (§11.4.85 / §11.4.115): every external-metadata lookup parsed
the provider's year string with ``int(s.split("-")[0])``. On a non-numeric or
empty token — OMDb ``Year`` can be ``"N/A"`` (or a range like ``"2011-2013"``); TMDB
``release_date`` / TVMaze ``premiered`` / MusicBrainz ``first-release-date``
can be empty or malformed — ``int(s.split("-")[0])`` raises ``ValueError`` on a
non-numeric leading token. The four lookups wrap the body in ``except Exception`` and
return ``None``, so a single bad year SILENTLY DISCARDS the entire otherwise-valid
enriched result (title, IDs, poster, overview). Same bug class as the
already-fixed ``_parse_size_to_bytes``.

Anti-bluff: these tests drive the REAL lookup code end-to-end via a fake
``aiohttp`` module so the actual ``MetadataResult(year=...)`` construction runs.
Each test asserts a USER-OBSERVABLE outcome — the enriched record is returned
(not dropped) with ``year=None`` — not merely "no exception".

RED proof (pre-fix): the unsafe ``int(...)`` raises ``ValueError`` → the broad
``except`` returns ``None`` → ``assert result is not None`` FAILS.
GREEN (post-fix): ``_safe_year`` yields ``None`` for the bad token, the record
is preserved, ``result.year is None``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

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


# --------------------------------------------------------------------------
# Fake aiohttp: drives the REAL lookup code path so the year-parse executes.
# --------------------------------------------------------------------------


def _install_fake_aiohttp(monkeypatch, payload):
    """Inject a fake ``aiohttp`` whose GET returns ``payload`` from ``.json()``."""

    class _FakeResp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def json(self):
            return payload

    class _FakeSession:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, *a, **k):
            return _FakeResp()

    fake = types.ModuleType("aiohttp")
    fake.ClientSession = _FakeSession

    def _client_timeout(*a, **k):
        return None

    fake.ClientTimeout = _client_timeout
    monkeypatch.setitem(sys.modules, "aiohttp", fake)


# Genuinely unparseable year tokens (no leading 4-digit year) fed to each
# provider branch. A RANGE like "2011-2013" (incl. en-dash) is parseable (leading
# year wins) and is covered separately by the dedicated range tests below.
_BAD_YEARS = ["N/A", "", "unknown", "no year here"]


# --------------------------------------------------------------------------
# OMDb  (enricher.py ~131 : int(data["Year"].split("-")[0]))
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_year", _BAD_YEARS)
async def test_omdb_unparseable_year_preserves_result(enricher_mod, monkeypatch, bad_year):
    monkeypatch.setenv("OMDB_API_KEY", "x")
    e = enricher_mod.MetadataEnricher()
    _install_fake_aiohttp(
        monkeypatch,
        {"Response": "True", "Title": "Some Movie", "Year": bad_year, "Type": "movie", "imdbID": "tt1"},
    )
    result = await e._lookup_omdb("some+movie")
    assert result is not None, f"OMDb result dropped on year={bad_year!r}"
    assert result.title == "Some Movie"
    assert result.year is None


# --------------------------------------------------------------------------
# TMDB  (enricher.py ~166 : int(result["release_date"].split("-")[0]))
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_year", _BAD_YEARS)
async def test_tmdb_unparseable_year_preserves_result(enricher_mod, monkeypatch, bad_year):
    monkeypatch.setenv("TMDB_API_KEY", "x")
    e = enricher_mod.MetadataEnricher()
    _install_fake_aiohttp(
        monkeypatch,
        {"results": [{"title": "Some Film", "media_type": "movie", "id": 7, "release_date": bad_year}]},
    )
    result = await e._lookup_tmdb("some+film")
    assert result is not None, f"TMDB result dropped on release_date={bad_year!r}"
    assert result.title == "Some Film"
    assert result.year is None


# --------------------------------------------------------------------------
# TVMaze  (enricher.py ~197 : int(result["premiered"].split("-")[0]))
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_year", _BAD_YEARS)
async def test_tvmaze_unparseable_year_preserves_result(enricher_mod, monkeypatch, bad_year):
    e = enricher_mod.MetadataEnricher()
    _install_fake_aiohttp(
        monkeypatch,
        [{"show": {"name": "Some Show", "premiered": bad_year, "image": None, "summary": "<p>x</p>"}}],
    )
    result = await e._lookup_tvmaze("some+show")
    assert result is not None, f"TVMaze result dropped on premiered={bad_year!r}"
    assert result.title == "Some Show"
    assert result.year is None


# --------------------------------------------------------------------------
# MusicBrainz  (enricher.py ~271 : int(rg["first-release-date"].split("-")[0]))
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_year", _BAD_YEARS)
async def test_musicbrainz_unparseable_year_preserves_result(enricher_mod, monkeypatch, bad_year):
    e = enricher_mod.MetadataEnricher()
    _install_fake_aiohttp(
        monkeypatch,
        {"release-groups": [{"title": "Some Album", "first-release-date": bad_year, "id": "mbid-1"}]},
    )
    result = await e._lookup_musicbrainz("some+album")
    assert result is not None, f"MusicBrainz result dropped on first-release-date={bad_year!r}"
    assert result.title == "Some Album"
    assert result.year is None


# --------------------------------------------------------------------------
# Valid years still parse (regression guard against over-correction).
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_year_still_parses_omdb(enricher_mod, monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "x")
    e = enricher_mod.MetadataEnricher()
    _install_fake_aiohttp(
        monkeypatch,
        {"Response": "True", "Title": "Dune", "Year": "2021", "Type": "movie", "imdbID": "tt1"},
    )
    result = await e._lookup_omdb("dune")
    assert result is not None
    assert result.year == 2021


@pytest.mark.asyncio
async def test_year_range_takes_leading_year_omdb(enricher_mod, monkeypatch):
    # A range like "2011-2013" must yield the leading 2011, not None and not crash.
    monkeypatch.setenv("OMDB_API_KEY", "x")
    e = enricher_mod.MetadataEnricher()
    _install_fake_aiohttp(
        monkeypatch,
        {"Response": "True", "Title": "Show", "Year": "2011-2013", "Type": "series", "imdbID": "tt2"},
    )
    result = await e._lookup_omdb("show")
    assert result is not None
    assert result.year == 2011
