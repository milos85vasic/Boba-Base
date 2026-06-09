"""
Metadata enrichment for better matching across trackers.

Provides integration with:
- OMDb API (movies)
- TMDB API (movies, TV)
- TVMaze API (TV shows)
- AniList API (anime)
- MusicBrainz API (music)
- OpenLibrary API (books)
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Total request budget for every external metadata API call. A slow,
# throttled, or blackholed endpoint (MusicBrainz rate-limits hard) must
# never be able to hang the event loop forever in ``selector.select`` —
# this bounds every ``aiohttp.ClientSession`` lookup. (§11.4.69)
_HTTP_TIMEOUT_SECONDS = 10.0


@dataclass
class MetadataResult:
    """Result from metadata API lookup."""

    source: str  # OMDb, TMDB, etc.
    title: str
    year: int | None = None
    content_type: str | None = None  # movie, tv, music, book
    imdb_id: str | None = None
    tmdb_id: str | None = None
    anilist_id: str | None = None
    musicbrainz_id: str | None = None
    openlibrary_id: str | None = None
    poster_url: str | None = None
    overview: str | None = None
    genres: list[str] | None = None

    def __post_init__(self) -> None:
        if self.genres is None:
            self.genres = []


class MetadataEnricher:
    """Enriches search results with metadata from external APIs."""

    def __init__(self) -> None:
        self._omdb_key = os.environ.get("OMDB_API_KEY")
        self._tmdb_key = os.environ.get("TMDB_API_KEY")
        self._anilist_id = os.environ.get("ANILIST_CLIENT_ID")
        self._cache: dict[str, MetadataResult] = {}

    async def resolve(self, query: str) -> MetadataResult | None:
        """
        Resolve a query to metadata using multiple APIs.

        Tries APIs in order of reliability:
        1. TMDB (movies, TV)
        2. OMDb (movies)
        3. TVMaze (TV)
        4. AniList (anime)
        5. OpenLibrary (books)
        6. MusicBrainz (music)
        """
        cache_key = query.lower().strip()

        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try TMDB first
        result = await self._lookup_tmdb(query)
        if result:
            self._cache[cache_key] = result
            return result

        # Try OMDb
        result = await self._lookup_omdb(query)
        if result:
            self._cache[cache_key] = result
            return result

        # Try TVMaze
        result = await self._lookup_tvmaze(query)
        if result:
            self._cache[cache_key] = result
            return result

        # Try AniList
        result = await self._lookup_anilist(query)
        if result:
            self._cache[cache_key] = result
            return result

        # Try OpenLibrary
        result = await self._lookup_openlibrary(query)
        if result:
            self._cache[cache_key] = result
            return result

        # Try MusicBrainz
        result = await self._lookup_musicbrainz(query)
        if result:
            self._cache[cache_key] = result
            return result

        return None

    async def _lookup_omdb(self, query: str) -> MetadataResult | None:
        """Look up using OMDb API."""
        if not self._omdb_key:
            return None

        try:
            import aiohttp

            url = f"http://www.omdbapi.com/?apikey={self._omdb_key}&t={query}"

            timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session, session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("Response") == "True":
                        return MetadataResult(
                            source="OMDb",
                            title=data.get("Title", ""),
                            year=int(data.get("Year", "0").split("-")[0]) if data.get("Year") else None,
                            content_type="movie" if data.get("Type") == "movie" else "tv",
                            imdb_id=data.get("imdbID"),
                            poster_url=data.get("Poster"),
                            overview=data.get("Plot"),
                            genres=data.get("Genre", "").split(", ") if data.get("Genre") else [],
                        )
        except Exception as e:
            logger.debug(f"OMDb lookup failed: {e}")

        return None

    async def _lookup_tmdb(self, query: str) -> MetadataResult | None:
        """Look up using TMDB API."""
        if not self._tmdb_key:
            return None

        try:
            import aiohttp

            # Search
            search_url = f"https://api.themoviedb.org/3/search/multi?api_key={self._tmdb_key}&query={query}"

            timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session, session.get(search_url) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    if results:
                        result = results[0]
                        media_type = result.get("media_type")

                        return MetadataResult(
                            source="TMDB",
                            title=result.get("title") or result.get("name", ""),
                            year=int(result.get("release_date", "").split("-")[0])
                            if result.get("release_date")
                            else None,
                            content_type=media_type,
                            tmdb_id=str(result.get("id")),
                            poster_url=f"https://image.tmdb.org/t/p/w500{result.get('poster_path')}"
                            if result.get("poster_path")
                            else None,
                            overview=result.get("overview"),
                        )
        except Exception as e:
            logger.debug(f"TMDB lookup failed: {e}")

        return None

    async def _lookup_tvmaze(self, query: str) -> MetadataResult | None:
        """Look up using TVMaze API."""
        try:
            import aiohttp

            url = f"https://api.tvmaze.com/search/shows?q={query}"

            timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session, session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        result = data[0].get("show", {})
                        return MetadataResult(
                            source="TVMaze",
                            title=result.get("name", ""),
                            year=int(result.get("premiered", "").split("-")[0]) if result.get("premiered") else None,
                            content_type="tv",
                            poster_url=result.get("image", {}).get("medium") if result.get("image") else None,
                            overview=result.get("summary", "").strip("<p></p>"),  # noqa: B005
                        )
        except Exception as e:
            logger.debug(f"TVMaze lookup failed: {e}")

        return None

    async def _lookup_anilist(self, query: str) -> MetadataResult | None:
        """Look up using AniList API (GraphQL)."""
        if not self._anilist_id:
            return None

        try:
            import aiohttp

            query_str = """
            query ($search: String) {
              Media(search: $search, type: ANIME) {
                id
                title { english romaji }
                startDate { year }
                coverImage { large }
                description
              }
            }
            """
            variables = {"search": query}

            timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(
                    "https://graphql.anilist.co",
                    json={"query": query_str, "variables": variables},
                ) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    media = data.get("data", {}).get("Media")
                    if media:
                        return MetadataResult(
                            source="AniList",
                            title=media.get("title", {}).get("english") or media.get("title", {}).get("romaji", ""),
                            year=media.get("startDate", {}).get("year"),
                            content_type="anime",
                            anilist_id=str(media.get("id")),
                            poster_url=media.get("coverImage", {}).get("large"),
                            overview=media.get("description"),
                        )
        except Exception as e:
            logger.debug(f"AniList lookup failed: {e}")

        return None

    async def _lookup_musicbrainz(self, query: str) -> MetadataResult | None:
        """Look up using MusicBrainz API."""
        try:
            import aiohttp

            url = f"https://musicbrainz.org/ws/2/release-group/?query={query}&fmt=json&limit=1"

            timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session, session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    release_groups = data.get("release-groups", [])
                    if release_groups:
                        rg = release_groups[0]
                        return MetadataResult(
                            source="MusicBrainz",
                            title=rg.get("title", ""),
                            year=int(rg.get("first-release-date", "0").split("-")[0])
                            if rg.get("first-release-date")
                            else None,
                            content_type="music",
                            musicbrainz_id=rg.get("id"),
                        )
        except Exception as e:
            logger.debug(f"MusicBrainz lookup failed: {e}")

        return None

    async def _lookup_openlibrary(self, query: str) -> MetadataResult | None:
        """Look up using OpenLibrary API."""
        try:
            import aiohttp

            url = f"https://openlibrary.org/search.json?q={query}&limit=1"

            timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session, session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    docs = data.get("docs", [])
                    if docs:
                        doc = docs[0]
                        return MetadataResult(
                            source="OpenLibrary",
                            title=doc.get("title", ""),
                            year=doc.get("first_publish_year"),
                            content_type="book",
                            openlibrary_id=doc.get("key", "").replace("/works/", ""),
                        )
        except Exception as e:
            logger.debug(f"OpenLibrary lookup failed: {e}")

        return None

    def clear_cache(self) -> None:
        """Clear the metadata cache."""
        self._cache.clear()

    def detect_quality(self, name: str) -> str | None:
        """
        Detect quality tier from torrent name.

        Parses common quality indicators:
        - Resolution: 720p, 1080p, 2160p, 4K, 8K, UHD, FHD, FullHD
        - Source: BluRay, WEB-DL, WEBRip, HDTV, DVD, HDRip, CamRip
        - Codec: x264, x265, HEVC
        """
        import re

        name_lower = name.lower() if name else ""

        if re.search(r"2160p|4k|uhd", name_lower):
            return "4K"
        if re.search(r"1080p|fullhd|fhd", name_lower):
            return "1080p"
        if re.search(r"720p|hdrip", name_lower):
            return "720p"
        if re.search(r"480p|sd|camrip", name_lower):
            return "SD"

        if "bluray" in name_lower or "blu-ray" in name_lower or "bdrip" in name_lower or "bd-remux" in name_lower:
            return "BluRay"
        if "web-dl" in name_lower or "webrip" in name_lower or "web.dl" in name_lower or "webdl" in name_lower:
            return "WEB-DL"
        if "hdtv" in name_lower:
            return "HDTV"
        if "dvd" in name_lower:
            return "DVD"

        return None
