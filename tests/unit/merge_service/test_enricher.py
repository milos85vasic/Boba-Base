"""
Unit tests for the metadata enricher module.
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

_enricher_spec = importlib.util.spec_from_file_location("merge_service.enricher", os.path.join(_MS_PATH, "enricher.py"))
_enricher_mod = importlib.util.module_from_spec(_enricher_spec)
sys.modules["merge_service.enricher"] = _enricher_mod
_enricher_spec.loader.exec_module(_enricher_mod)

MetadataEnricher = _enricher_mod.MetadataEnricher
MetadataResult = _enricher_mod.MetadataResult


class TestMetadataEnricher:
    """Tests for MetadataEnricher class."""

    @pytest.fixture
    def enricher(self):
        """Create enricher instance."""
        return MetadataEnricher()

    def test_init(self, enricher):
        """Test enricher initialization."""
        assert enricher._omdb_key is None
        assert enricher._tmdb_key is None
        assert enricher._cache == {}

    def test_detect_quality_4k(self, enricher):
        """Test quality detection for 4K."""
        assert enricher.detect_quality("Movie 2023 2160p BluRay") == "4K"
        assert enricher.detect_quality("Movie 2023 4K WEB-DL") == "4K"

    def test_detect_quality_1080p(self, enricher):
        """Test quality detection for 1080p."""
        assert enricher.detect_quality("Movie 2023 1080p BluRay") == "1080p"
        assert enricher.detect_quality("Movie 2023 1080p WEB-DL") == "1080p"

    def test_detect_quality_720p(self, enricher):
        """Test quality detection for 720p."""
        assert enricher.detect_quality("Movie 720p HDTV") == "720p"

    def test_detect_quality_sd(self, enricher):
        """Test quality detection for SD."""
        assert enricher.detect_quality("Movie DVD") == "DVD"
        assert enricher.detect_quality("Movie 480p") == "SD"

    def test_detect_quality_source_based(self, enricher):
        """Test quality detection from source."""
        assert enricher.detect_quality("Movie BluRay") == "BluRay"
        assert enricher.detect_quality("Movie WEB-DL") == "WEB-DL"
        assert enricher.detect_quality("Movie HDTV") == "HDTV"

    def test_detect_quality_unknown(self, enricher):
        """Test quality detection with no clear indicator."""
        assert enricher.detect_quality("Movie 2023") is None

    def test_clear_cache(self, enricher):
        """Test cache clearing."""
        enricher._cache["test"] = MetadataResult(source="test", title="test")

        enricher.clear_cache()

        assert enricher._cache == {}

    def test_resolve_no_apis(self, enricher, monkeypatch):
        """resolve() with no API keys must be deterministic + fully offline.

        With no keys, the keyed lookups (TMDB/OMDb/AniList) skip immediately,
        but the keyless lookups (TVMaze/OpenLibrary/MusicBrainz) would hit the
        public internet with no bound — a network dependency that can hang the
        event loop forever when a host throttles/blackholes (§11.4.98,
        §11.4.69). Stub those three to async no-ops so the test never touches
        the network and completes instantly, and assert NO real aiohttp
        session is ever constructed (the regression guard).
        """
        import asyncio

        import aiohttp

        async def _none(_query):
            return None

        enricher._lookup_tvmaze = _none
        enricher._lookup_openlibrary = _none
        enricher._lookup_musicbrainz = _none

        # Regression guard: count every ClientSession construction. The
        # lookup methods swallow exceptions (broad ``except``), so raising
        # from a fake ctor would be silently eaten — instead spy on the
        # constructor and assert AFTER the run that it was never reached.
        # A non-zero count means a keyless lookup hit the network.
        sessions_opened: list[None] = []
        real_ctor = aiohttp.ClientSession

        def _spy_ctor(*args, **kwargs):
            sessions_opened.append(None)
            return real_ctor(*args, **kwargs)

        monkeypatch.setattr(aiohttp, "ClientSession", _spy_ctor)

        result = asyncio.run(enricher.resolve("Test Movie"))

        assert result is None
        assert sessions_opened == [], (
            f"resolve() with no API keys opened {len(sessions_opened)} network "
            "session(s) — keyless lookups must be stubbed/offline"
        )


class TestMetadataResult:
    """Tests for MetadataResult dataclass."""

    def test_creation(self):
        """Test MetadataResult creation."""
        result = MetadataResult(
            source="TMDB",
            title="Test Movie",
            year=2023,
            content_type="movie",
            tmdb_id="12345",
        )

        assert result.source == "TMDB"
        assert result.title == "Test Movie"
        assert result.year == 2023
        assert result.content_type == "movie"
        assert result.tmdb_id == "12345"

    def test_default_genres(self):
        """Test that genres defaults to empty list."""
        result = MetadataResult(source="test", title="test")

        assert result.genres == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
