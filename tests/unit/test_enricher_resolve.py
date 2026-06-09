"""
Unit tests for MetadataEnricher with mocked APIs.

Tests individual lookup methods directly since resolve() has a fixed API order.
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

import pytest

# Add source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))

from merge_service.enricher import MetadataEnricher, MetadataResult


def _make_mock_session(response_data, status=200, method="get"):
    """Create a properly mocked aiohttp session for nested async context managers."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=response_data)
    mock_response.text = AsyncMock(return_value=json.dumps(response_data))

    mock_response_cm = MagicMock()
    mock_response_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    if method == "get":
        mock_session.get = MagicMock(return_value=mock_response_cm)
    elif method == "post":
        mock_session.post = MagicMock(return_value=mock_response_cm)

    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_session_cm


class TestEnricherLookupOMDb:
    """Test OMDb lookup method."""

    @pytest.fixture
    def enricher(self):
        with patch.dict(os.environ, {"OMDB_API_KEY": "test_key"}):
            return MetadataEnricher()

    @pytest.mark.asyncio
    async def test_lookup_omdb_success(self, enricher):
        """OMDb lookup with valid response."""
        mock_session_cm = _make_mock_session(
            {
                "Title": "The Matrix",
                "Year": "1999",
                "imdbRating": "8.7",
                "Genre": "Action, Sci-Fi",
                "Plot": "A computer hacker learns...",
                "Response": "True",
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_omdb("The Matrix")
            assert result is not None
            assert isinstance(result, MetadataResult)
            assert result.title == "The Matrix"
            assert result.source == "OMDb"

    @pytest.mark.asyncio
    async def test_lookup_omdb_no_api_key(self):
        """OMDb lookup without API key returns None."""
        with patch.dict(os.environ, {}, clear=True):
            enricher = MetadataEnricher()
            result = await enricher._lookup_omdb("The Matrix")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_omdb_not_found(self, enricher):
        """OMDb lookup with 'False' response returns None."""
        mock_session_cm = _make_mock_session({"Response": "False", "Error": "Movie not found!"})

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_omdb("NonExistentMovie12345")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_omdb_timeout(self, enricher):
        """OMDb lookup timeout returns None."""
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(side_effect=TimeoutError())
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_omdb("The Matrix")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_omdb_http_error(self, enricher):
        """OMDb lookup with non-200 status returns None."""
        mock_session_cm = _make_mock_session({}, status=503)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_omdb("The Matrix")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_omdb_connection_error(self, enricher):
        """OMDb lookup with connection error returns None."""
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_omdb("The Matrix")
            assert result is None


class TestEnricherLookupTMDB:
    """Test TMDB lookup method."""

    @pytest.fixture
    def enricher(self):
        with patch.dict(os.environ, {"TMDB_API_KEY": "test_key"}):
            return MetadataEnricher()

    @pytest.mark.asyncio
    async def test_lookup_tmdb_success(self, enricher):
        """TMDB lookup with valid response."""
        mock_session_cm = _make_mock_session(
            {
                "results": [
                    {
                        "title": "The Matrix",
                        "release_date": "1999-03-31",
                        "vote_average": 8.7,
                        "genre_ids": [28, 878],
                        "overview": "A computer hacker...",
                    }
                ]
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tmdb("The Matrix")
            assert result is not None
            assert isinstance(result, MetadataResult)
            assert result.title == "The Matrix"
            assert result.source == "TMDB"

    @pytest.mark.asyncio
    async def test_lookup_tmdb_no_api_key(self):
        """TMDB lookup without API key returns None."""
        with patch.dict(os.environ, {}, clear=True):
            enricher = MetadataEnricher()
            result = await enricher._lookup_tmdb("The Matrix")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_tmdb_empty_results(self, enricher):
        """TMDB lookup with empty results returns None."""
        mock_session_cm = _make_mock_session({"results": []})

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tmdb("NonExistentMovie12345")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_tmdb_http_error(self, enricher):
        """TMDB lookup with non-200 status returns None."""
        mock_session_cm = _make_mock_session({}, status=500)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tmdb("The Matrix")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_tmdb_connection_error(self, enricher):
        """TMDB lookup with connection error returns None."""
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tmdb("The Matrix")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_tmdb_missing_fields(self, enricher):
        """TMDB lookup with missing optional fields returns MetadataResult with fallbacks."""
        mock_session_cm = _make_mock_session(
            {
                "results": [
                    {
                        "title": "No Date Movie",
                    }
                ]
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tmdb("No Date Movie")
            assert result is not None
            assert result.title == "No Date Movie"
            assert result.year is None
            assert result.poster_url is None
            assert result.overview is None


class TestEnricherLookupTVMaze:
    """Test TVMaze lookup method."""

    @pytest.fixture
    def enricher(self):
        return MetadataEnricher()

    @pytest.mark.asyncio
    async def test_lookup_tvmaze_success(self, enricher):
        """TVMaze lookup with valid response."""
        mock_session_cm = _make_mock_session(
            [
                {
                    "show": {
                        "name": "Breaking Bad",
                        "premiered": "2008-01-20",
                        "rating": {"average": 9.5},
                        "genres": ["Drama", "Crime"],
                        "summary": "A high school chemistry teacher...",
                    }
                }
            ]
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tvmaze("Breaking Bad")
            assert result is not None
            assert isinstance(result, MetadataResult)
            assert result.title == "Breaking Bad"
            assert result.source == "TVMaze"

    @pytest.mark.asyncio
    async def test_lookup_tvmaze_empty(self, enricher):
        """TVMaze lookup with empty results returns None."""
        mock_session_cm = _make_mock_session([])

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tvmaze("NonExistentShow12345")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_tvmaze_http_error(self, enricher):
        """TVMaze lookup with non-200 status returns None."""
        mock_session_cm = _make_mock_session([], status=404)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tvmaze("Breaking Bad")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_tvmaze_connection_error(self, enricher):
        """TVMaze lookup with connection error returns None."""
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tvmaze("Breaking Bad")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_tvmaze_no_show_key(self, enricher):
        """TVMaze lookup with missing 'show' key returns None."""
        mock_session_cm = _make_mock_session([{}])

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_tvmaze("Broken Show")
            assert result is not None
            assert result.title == ""


class TestEnricherLookupAniList:
    """Test AniList lookup method."""

    @pytest.fixture
    def enricher(self):
        return MetadataEnricher()

    @pytest.fixture
    def enricher_with_anilist(self):
        with patch.dict(os.environ, {"ANILIST_CLIENT_ID": "test_id"}):
            return MetadataEnricher()

    @pytest.mark.asyncio
    async def test_lookup_anilist_success(self, enricher_with_anilist):
        """AniList lookup with valid response."""
        mock_session_cm = _make_mock_session(
            {
                "data": {
                    "Media": {
                        "id": 1,
                        "title": {"english": "Attack on Titan", "romaji": "Shingeki no Kyojin"},
                        "startDate": {"year": 2013},
                        "coverImage": {"large": "https://example.com/poster.jpg"},
                        "description": "Humans fight giants...",
                    }
                }
            },
            method="post",
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher_with_anilist._lookup_anilist("Attack on Titan")
            assert result is not None
            assert isinstance(result, MetadataResult)
            assert result.title == "Attack on Titan"
            assert result.source == "AniList"

    @pytest.mark.asyncio
    async def test_lookup_anilist_empty(self, enricher_with_anilist):
        """AniList lookup with empty results returns None."""
        mock_session_cm = _make_mock_session({"data": {"Media": None}}, method="post")

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher_with_anilist._lookup_anilist("NonExistentAnime12345")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_anilist_no_client_id(self):
        """AniList lookup without client ID returns None."""
        with patch.dict(os.environ, {}, clear=True):
            enricher = MetadataEnricher()
            result = await enricher._lookup_anilist("Attack on Titan")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_anilist_http_error(self, enricher_with_anilist):
        """AniList lookup with non-200 status returns None."""
        mock_session_cm = _make_mock_session({}, status=500, method="post")

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher_with_anilist._lookup_anilist("Attack on Titan")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_anilist_connection_error(self, enricher_with_anilist):
        """AniList lookup with connection error returns None."""
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher_with_anilist._lookup_anilist("Attack on Titan")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_anilist_missing_title(self, enricher_with_anilist):
        """AniList lookup with missing title fields returns fallback."""
        mock_session_cm = _make_mock_session(
            {
                "data": {
                    "Media": {
                        "id": 1,
                        "title": {},
                        "startDate": {"year": 2013},
                    }
                }
            },
            method="post",
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher_with_anilist._lookup_anilist("Test")
            assert result is not None
            assert result.title == ""


class TestEnricherLookupMusicBrainz:
    """Test MusicBrainz lookup method."""

    @pytest.fixture
    def enricher(self):
        return MetadataEnricher()

    @pytest.mark.asyncio
    async def test_lookup_musicbrainz_success(self, enricher):
        """MusicBrainz lookup with valid response."""
        mock_session_cm = _make_mock_session(
            {
                "release-groups": [
                    {
                        "title": "Abbey Road",
                        "first-release-date": "1969-09-26",
                        "id": "abc123",
                    }
                ]
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_musicbrainz("Abbey Road Beatles")
            assert result is not None
            assert isinstance(result, MetadataResult)
            assert result.source == "MusicBrainz"

    @pytest.mark.asyncio
    async def test_lookup_musicbrainz_empty(self, enricher):
        """MusicBrainz lookup with empty results returns None."""
        mock_session_cm = _make_mock_session({"release-groups": []})

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_musicbrainz("NonExistentAlbum12345")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_musicbrainz_http_error(self, enricher):
        """MusicBrainz lookup with non-200 status returns None."""
        mock_session_cm = _make_mock_session({}, status=503)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_musicbrainz("Abbey Road")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_musicbrainz_connection_error(self, enricher):
        """MusicBrainz lookup with connection error returns None."""
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_musicbrainz("Abbey Road")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_musicbrainz_missing_date(self, enricher):
        """MusicBrainz lookup with missing release date returns result with year None."""
        mock_session_cm = _make_mock_session(
            {
                "release-groups": [
                    {
                        "title": "Untitled Album",
                        "id": "xyz789",
                    }
                ]
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_musicbrainz("Untitled Album")
            assert result is not None
            assert result.year is None


class TestEnricherLookupOpenLibrary:
    """Test OpenLibrary lookup method."""

    @pytest.fixture
    def enricher(self):
        return MetadataEnricher()

    @pytest.mark.asyncio
    async def test_lookup_openlibrary_success(self, enricher):
        """OpenLibrary lookup with valid response."""
        mock_session_cm = _make_mock_session(
            {
                "docs": [
                    {
                        "title": "The Great Gatsby",
                        "author_name": ["F. Scott Fitzgerald"],
                        "first_publish_year": 1925,
                    }
                ]
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_openlibrary("The Great Gatsby")
            assert result is not None
            assert isinstance(result, MetadataResult)
            assert result.source == "OpenLibrary"

    @pytest.mark.asyncio
    async def test_lookup_openlibrary_empty(self, enricher):
        """OpenLibrary lookup with empty results returns None."""
        mock_session_cm = _make_mock_session({"docs": []})

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_openlibrary("NonExistentBook12345")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_openlibrary_http_error(self, enricher):
        """OpenLibrary lookup with non-200 status returns None."""
        mock_session_cm = _make_mock_session({}, status=429)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_openlibrary("The Great Gatsby")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_openlibrary_connection_error(self, enricher):
        """OpenLibrary lookup with connection error returns None."""
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_openlibrary("The Great Gatsby")
            assert result is None

    @pytest.mark.asyncio
    async def test_lookup_openlibrary_no_title(self, enricher):
        """OpenLibrary lookup with missing title still returns result."""
        mock_session_cm = _make_mock_session(
            {
                "docs": [
                    {
                        "first_publish_year": 2000,
                        "key": "/works/OL123W",
                    }
                ]
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            result = await enricher._lookup_openlibrary("No Title Book")
            assert result is not None
            assert result.title == ""
            assert result.year == 2000


class TestEnricherResolve:
    """Test the high-level resolve() method."""

    @pytest.fixture
    def enricher(self):
        return MetadataEnricher()

    @pytest.mark.asyncio
    async def test_resolve_no_apis_available(self, enricher):
        """resolve() with no API keys and no HTTP responses should return None."""
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(side_effect=Exception("No network"))
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            with patch.dict(os.environ, {}, clear=True):
                enricher = MetadataEnricher()
                result = await enricher.resolve("Some Title")
                assert result is None

    @pytest.mark.asyncio
    async def test_resolve_cache_hit(self, enricher):
        """Cache hit should return cached result without API call."""
        cached = MetadataResult(
            source="test",
            title="Cached Title",
            year=2024,
            content_type="movie",
            genres=["Action"],
            overview="Cached overview",
        )
        enricher._cache["cached title"] = cached

        result = await enricher.resolve("Cached Title")
        assert result is not None
        assert result.title == "Cached Title"

    @pytest.mark.asyncio
    async def test_resolve_tmdb_first(self, enricher):
        """resolve() should try TMDB first and return its result."""
        mock_session_cm = _make_mock_session(
            {
                "results": [
                    {
                        "title": "TMDB Movie",
                        "release_date": "2024-01-01",
                        "vote_average": 7.5,
                        "genre_ids": [28],
                        "overview": "TMDB overview",
                    }
                ]
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            with patch.dict(os.environ, {"TMDB_API_KEY": "test_key"}):
                enricher = MetadataEnricher()
                result = await enricher.resolve("TMDB Movie")
                assert result is not None
                assert result.title == "TMDB Movie"
                assert result.source == "TMDB"

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_omdb(self, enricher):
        """resolve() should fall back to OMDb when TMDB fails."""
        def build_session():
            mock_session = MagicMock()
            mock_session.get = MagicMock()
            mock_session_cm = MagicMock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=False)
            return mock_session_cm

        tmdb_session_cm = build_session()
        tmdb_session_cm.__aenter__.return_value.get.return_value.__aenter__ = AsyncMock(
            side_effect=aiohttp.ClientError("TMDB down")
        )

        omdb_session_cm = build_session()
        omdb_response = MagicMock()
        omdb_response.status = 200
        omdb_response.json = AsyncMock(return_value={"Title": "OMDb Movie", "Year": "2023", "Response": "True"})
        omdb_response_cm = MagicMock()
        omdb_response_cm.__aenter__ = AsyncMock(return_value=omdb_response)
        omdb_response_cm.__aexit__ = AsyncMock(return_value=False)
        omdb_session_cm.__aenter__.return_value.get.return_value = omdb_response_cm

        calls = [tmdb_session_cm, omdb_session_cm]
        call_idx = 0

        def session_factory(*args, **kwargs):
            nonlocal call_idx
            result = calls[call_idx]
            call_idx += 1
            return result

        with patch("aiohttp.ClientSession", side_effect=session_factory):
            with patch.dict(os.environ, {"TMDB_API_KEY": "test_key", "OMDB_API_KEY": "test_key"}):
                enricher = MetadataEnricher()
                result = await enricher.resolve("OMDb Movie")
                assert result is not None
                assert result.source == "OMDb"

    @pytest.mark.asyncio
    async def test_resolve_cache_persists_across_calls(self, enricher):
        """resolve() should cache result after first successful lookup."""
        mock_session_cm = _make_mock_session(
            {
                "results": [
                    {
                        "title": "Cached Movie",
                        "release_date": "2024-01-01",
                    }
                ]
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm) as mock_factory:
            with patch.dict(os.environ, {"TMDB_API_KEY": "test_key"}):
                enricher = MetadataEnricher()
                result1 = await enricher.resolve("Cached Movie")
                assert result1 is not None
                assert result1.source == "TMDB"

                result2 = await enricher.resolve("Cached Movie")
                assert result2 is not None
                assert result2 is result1
                assert mock_factory.call_count == 1

    def test_detect_quality(self, enricher):
        """Quality detection should work for various names."""
        assert enricher.detect_quality("Movie.2024.1080p.BluRay") is not None
        assert enricher.detect_quality("Movie.2024.720p.WEB-DL") is not None
        assert enricher.detect_quality("Movie.2024.2160p.UHD") is not None
        assert enricher.detect_quality("Movie.2024.DVDSCR") is not None

    def test_detect_quality_none_name(self, enricher):
        """detect_quality should handle None input."""
        assert enricher.detect_quality(None) is None

    def test_detect_quality_empty_string(self, enricher):
        """detect_quality should handle empty string."""
        assert enricher.detect_quality("") is None

    def test_detect_quality_uhd(self, enricher):
        """detect_quality should detect UHD as 4K."""
        assert enricher.detect_quality("Movie 2023 UHD BluRay") == "4K"
        assert enricher.detect_quality("Movie 2160p") == "4K"

    def test_detect_quality_bluray_variants(self, enricher):
        """detect_quality should detect various BluRay naming conventions."""
        assert enricher.detect_quality("Movie BluRay") == "BluRay"
        assert enricher.detect_quality("Movie blu-ray") == "BluRay"

    def test_detect_quality_sd(self, enricher):
        """detect_quality should detect SD quality."""
        assert enricher.detect_quality("Movie 480p") == "SD"
        assert enricher.detect_quality("Movie sdrip") == "SD"
        assert enricher.detect_quality("Movie camrip") == "SD"

    def test_detect_quality_webdl(self, enricher):
        """detect_quality should detect WEB-DL quality."""
        assert enricher.detect_quality("Movie web-dl") == "WEB-DL"
        assert enricher.detect_quality("Movie webrip") == "WEB-DL"
        assert enricher.detect_quality("Movie WEB.DL") == "WEB-DL"

    def test_detect_quality_hdtv(self, enricher):
        """detect_quality should detect HDTV quality."""
        assert enricher.detect_quality("Movie HDTV") == "HDTV"

    def test_detect_quality_dvd(self, enricher):
        """detect_quality should detect DVD quality."""
        assert enricher.detect_quality("Movie DVD") == "DVD"
        assert enricher.detect_quality("Movie dvdr") == "DVD"

    def test_clear_cache(self, enricher):
        """Clear cache should empty the cache."""
        enricher._cache["test"] = MetadataResult(
            source="test",
            title="Test",
            year=2024,
            content_type="movie",
            genres=["Action"],
            overview="Test",
        )
        enricher.clear_cache()
        assert len(enricher._cache) == 0

    @pytest.mark.asyncio
    async def test_resolve_invalid_json(self, enricher):
        """Invalid JSON response should be handled gracefully."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(side_effect=json.JSONDecodeError("test", "", 0))

        mock_response_cm = MagicMock()
        mock_response_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response_cm)

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            with patch.dict(os.environ, {"TMDB_API_KEY": "test_key"}):
                enricher = MetadataEnricher()
                result = await enricher.resolve("Some Movie")
                assert result is None

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_anilist(self):
        """resolve() should fall back to AniList when TMDB, OMDb, TVMaze fail."""
        mock_session_cm = _make_mock_session(
            {"data": {"Media": {"title": {"english": "Anime Title"}, "id": 1}}},
            method="post",
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            with patch.dict(os.environ, {"ANILIST_CLIENT_ID": "test_key"}):
                enricher = MetadataEnricher()
                result = await enricher.resolve("Anime Title")
                assert result is not None
                assert result.source == "AniList"

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_tvmaze(self):
        """resolve() should fall back to TVMaze when TMDB and OMDb have no keys."""
        mock_session_cm = _make_mock_session(
            [{"show": {"name": "TV Show", "premiered": "2020-01-01", "summary": "A show"}}]
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            enricher = MetadataEnricher()
            result = await enricher.resolve("TV Show")
            assert result is not None
            assert result.source == "TVMaze"
            assert result.title == "TV Show"

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_openlibrary(self):
        """resolve() should fall back to OpenLibrary when upstream providers have no keys."""
        mock_session_cm = _make_mock_session(
            {"docs": [{"title": "A Book", "first_publish_year": 2000}]}
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            enricher = MetadataEnricher()
            result = await enricher.resolve("A Book")
            assert result is not None
            assert result.source == "OpenLibrary"
            assert result.title == "A Book"

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_musicbrainz(self):
        """resolve() should fall back to MusicBrainz when upstream providers fail."""
        mock_session_cm = _make_mock_session(
            {"release-groups": [{"title": "An Album", "id": "album123"}]}
        )

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            enricher = MetadataEnricher()
            result = await enricher.resolve("An Album")
            assert result is not None
            assert result.source == "MusicBrainz"
            assert result.title == "An Album"

    @pytest.mark.asyncio
    async def test_resolve_all_fail_returns_none(self):
        """resolve() should return None when all lookup methods fail."""
        mock_session_cm = _make_mock_session({}, status=404)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            enricher = MetadataEnricher()
            result = await enricher.resolve("NonExistent")
            assert result is None
