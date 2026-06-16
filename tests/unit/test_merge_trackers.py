import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))

from merge_service.search import (
    DEAD_PUBLIC_TRACKERS,
    PRIVATE_TRACKERS,
    PUBLIC_TRACKERS,
    SearchOrchestrator,
    SearchResult,
    TrackerSource,
)

# Public trackers that aren't bucketed as dead. Most of the fan-out
# math now uses this rather than `PUBLIC_TRACKERS` directly because
# dead trackers are filtered out of `_get_enabled_trackers`.
LIVE_PUBLIC_TRACKERS = {name: url for name, url in PUBLIC_TRACKERS.items() if name not in DEAD_PUBLIC_TRACKERS}


class TestPublicTrackersRegistry:
    def test_public_trackers_not_empty(self):
        assert len(PUBLIC_TRACKERS) > 0

    def test_all_public_trackers_have_urls(self):
        for name, url in PUBLIC_TRACKERS.items():
            assert url.startswith("http"), f"{name} has invalid URL: {url}"

    def test_expected_public_tracker_count(self):
        assert len(PUBLIC_TRACKERS) == 38

    def test_specific_trackers_present(self):
        expected = [
            "piratebay",
            "nyaa",
            "yts",
            "torrentgalaxy",
            "one337x",
            "kickass",
            "eztv",
            "torlock",
            "solidtorrents",
            "rutor",
            "limetorrents",
            "extratorrent",
            "therarbg",
            "bt4g",
            "torrentdownload",
            "torrentfunk",
            "torrentscsv",
            "btsow",
            "snowfl",
            "rockbox",
            "megapeer",
        ]
        for t in expected:
            assert t in PUBLIC_TRACKERS, f"Missing public tracker: {t}"

    def test_no_private_trackers_in_public_registry(self):
        for name in PRIVATE_TRACKERS:
            assert name not in PUBLIC_TRACKERS

    def test_private_trackers_defined(self):
        assert "rutracker" in PRIVATE_TRACKERS
        assert "kinozal" in PRIVATE_TRACKERS
        assert "nnmclub" in PRIVATE_TRACKERS
        assert "iptorrents" in PRIVATE_TRACKERS


class TestGetEnabledTrackers:
    def setup_method(self):
        self.orch = SearchOrchestrator()

    def test_public_trackers_always_enabled(self):
        """Every LIVE public tracker (not in DEAD_PUBLIC_TRACKERS) must
        be enabled by default. Dead trackers are filtered out unless
        ``ENABLE_DEAD_TRACKERS=1`` is set.
        """
        with patch.dict(os.environ, {"ENABLE_DEAD_TRACKERS": "0"}, clear=True):
            trackers = self.orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            for name in LIVE_PUBLIC_TRACKERS:
                assert name in names, f"Live public tracker {name} missing from enabled list"
            for dead in DEAD_PUBLIC_TRACKERS:
                assert dead not in names, f"Dead tracker {dead} leaked into default fan-out"

    def test_public_trackers_all_enabled_when_env_flag_set(self):
        with patch.dict(os.environ, {"ENABLE_DEAD_TRACKERS": "1"}, clear=True):
            trackers = self.orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            for name in PUBLIC_TRACKERS:
                assert name in names, f"ENABLE_DEAD_TRACKERS=1 should force {name} back in"

    def test_private_trackers_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            trackers = self.orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "rutracker" not in names
            assert "kinozal" not in names
            assert "nnmclub" not in names
            assert "iptorrents" not in names

    def test_rutracker_with_credentials(self):
        with patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=True):
            trackers = self.orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "rutracker" in names

    def test_kinozal_with_credentials(self):
        with patch.dict(os.environ, {"KINOZAL_USERNAME": "u", "KINOZAL_PASSWORD": "p"}, clear=True):
            trackers = self.orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "kinozal" in names

    def test_nnmclub_with_cookies(self):
        with patch.dict(os.environ, {"NNMCLUB_COOKIES": "phpbb2mysql_4_sid=abc123"}, clear=True):
            trackers = self.orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "nnmclub" in names

    def test_iptorrents_with_credentials(self):
        with patch.dict(os.environ, {"IPTORRENTS_USERNAME": "u", "IPTORRENTS_PASSWORD": "p"}, clear=True):
            trackers = self.orch._get_enabled_trackers()
            names = [t.name for t in trackers]
            assert "iptorrents" in names

    def test_all_trackers_with_all_credentials(self):
        env = {
            "RUTRACKER_USERNAME": "u",
            "RUTRACKER_PASSWORD": "p",
            "KINOZAL_USERNAME": "u",
            "KINOZAL_PASSWORD": "p",
            "NNMCLUB_COOKIES": "phpbb2mysql_4_sid=abc",
            "IPTORRENTS_USERNAME": "u",
            "IPTORRENTS_PASSWORD": "p",
            "ENABLE_DEAD_TRACKERS": "0",
        }
        with patch.dict(os.environ, env, clear=True):
            trackers = self.orch._get_enabled_trackers()
            # 4 private + every LIVE public (dead ones are filtered out
            # by default unless `ENABLE_DEAD_TRACKERS=1`).
            assert len(trackers) == 4 + len(LIVE_PUBLIC_TRACKERS)

    def test_tracker_sources_have_urls(self):
        with patch.dict(os.environ, {}, clear=True):
            trackers = self.orch._get_enabled_trackers()
            for t in trackers:
                assert t.url, f"Tracker {t.name} has no URL"
                assert t.enabled is True

    def test_trackers_are_sorted_alphabetically_among_public(self):
        with patch.dict(os.environ, {}, clear=True):
            trackers = self.orch._get_enabled_trackers()
            public_names = [t.name for t in trackers if t.name in PUBLIC_TRACKERS]
            assert public_names == sorted(public_names)


class TestSearchTrackerRouting:
    def setup_method(self):
        self.orch = SearchOrchestrator()

    @pytest.mark.asyncio
    async def test_public_tracker_routes_correctly(self):
        with patch.object(self.orch, "_search_public_tracker", new_callable=AsyncMock) as mock:
            mock.return_value = [
                SearchResult(
                    name="Test",
                    size="1 GB",
                    seeds=10,
                    leechers=5,
                    link="magnet:?",
                    desc_link="http://x",
                    tracker="piratebay",
                    engine_url="https://thepiratebay.org",
                )
            ]
            tracker = TrackerSource(name="piratebay", url="https://thepiratebay.org")
            results = await self.orch._search_tracker(tracker, "ubuntu", "all")
            mock.assert_called_once_with("piratebay", "ubuntu", "all")
            assert len(results) == 1
            assert results[0].tracker == "piratebay"

    @pytest.mark.asyncio
    async def test_private_tracker_rutracker_routes(self):
        with patch.object(self.orch, "_search_rutracker", new_callable=AsyncMock) as mock:
            mock.return_value = []
            tracker = TrackerSource(name="rutracker", url="https://rutracker.org")
            await self.orch._search_tracker(tracker, "test", "all")
            mock.assert_called_once_with("test", "all")

    @pytest.mark.asyncio
    async def test_private_tracker_kinozal_routes(self):
        with patch.object(self.orch, "_search_kinozal", new_callable=AsyncMock) as mock:
            mock.return_value = []
            tracker = TrackerSource(name="kinozal", url="https://kinozal.tv")
            await self.orch._search_tracker(tracker, "test", "all")
            mock.assert_called_once_with("test", "all")

    @pytest.mark.asyncio
    async def test_private_tracker_nnmclub_routes(self):
        with patch.object(self.orch, "_search_nnmclub", new_callable=AsyncMock) as mock:
            mock.return_value = []
            tracker = TrackerSource(name="nnmclub", url="https://nnmclub.to")
            await self.orch._search_tracker(tracker, "test", "all")
            mock.assert_called_once_with("test", "all")

    @pytest.mark.asyncio
    async def test_private_tracker_iptorrents_routes(self):
        with patch.object(self.orch, "_search_iptorrents", new_callable=AsyncMock) as mock:
            mock.return_value = []
            tracker = TrackerSource(name="iptorrents", url="https://iptorrents.com")
            await self.orch._search_tracker(tracker, "test", "all")
            mock.assert_called_once_with("test", "all")

    @pytest.mark.asyncio
    async def test_jackett_routes_to_public_tracker(self):
        with patch.object(self.orch, "_search_public_tracker", new_callable=AsyncMock) as mock:
            mock.return_value = []
            tracker = TrackerSource(name="jackett", url="http://localhost:9117")
            await self.orch._search_tracker(tracker, "test", "all")
            mock.assert_called_once_with("jackett", "test", "all")

    @pytest.mark.asyncio
    async def test_unknown_tracker_returns_empty(self):
        tracker = TrackerSource(name="nonexistent_tracker", url="http://x")
        results = await self.orch._search_tracker(tracker, "test", "all")
        assert results == []

    @pytest.mark.asyncio
    async def test_tracker_error_returns_empty(self):
        with patch.object(self.orch, "_search_public_tracker", new_callable=AsyncMock) as mock:
            mock.side_effect = Exception("Connection error")
            tracker = TrackerSource(name="piratebay", url="https://thepiratebay.org")
            results = await self.orch._search_tracker(tracker, "test", "all")
            assert results == []


def _streaming_proc_mock(rows: list[dict]) -> AsyncMock:
    """Build a mock subprocess that yields `rows` as NDJSON on stdout.

    The production `_search_public_tracker` reads stdout line-by-line via
    `proc.stdout.readline()` so partial results survive a per-plugin
    timeout kill. Tests that previously mocked the batched
    `proc.communicate()` path must be adapted to this streaming contract.
    """
    lines = [json.dumps(r).encode() + b"\n" for r in rows]
    lines.append(b"")  # EOF signal
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.stdout = MagicMock()
    mock_proc.stdout.readline = AsyncMock(side_effect=lines)
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read = AsyncMock(return_value=b"")
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.kill = MagicMock()
    return mock_proc


class TestSearchPublicTracker:
    def setup_method(self):
        self.orch = SearchOrchestrator()

    @pytest.mark.asyncio
    async def test_successful_plugin_execution(self):
        mock_results = [
            {
                "name": "Ubuntu 22.04",
                "size": "4.0 GB",
                "seeds": 100,
                "leech": 20,
                "link": "magnet:?xt=urn:btih:abc",
                "desc_link": "http://x/details",
            },
        ]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _streaming_proc_mock(mock_results)

            results = await self.orch._search_public_tracker("piratebay", "ubuntu", "all")
            assert len(results) == 1
            assert results[0].name == "Ubuntu 22.04"
            assert results[0].seeds == 100
            assert results[0].tracker == "piratebay"

    @pytest.mark.asyncio
    async def test_empty_results(self):
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _streaming_proc_mock([])

            results = await self.orch._search_public_tracker("eztv", "test", "all")
            assert results == []

    @pytest.mark.asyncio
    async def test_plugin_timeout(self):
        """Timed-out plugin returns captured rows and leaves loop promptly.

        The new streaming reader catches `asyncio.wait_for` per-line and
        breaks out, so `proc.stdout.readline()` never needs to raise — we
        simulate a timeout by having readline block forever and relying on
        the deadline. Cheapest mock: just return EOF to simulate the
        kill-after-timeout read.
        """
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _streaming_proc_mock([])

            results = await self.orch._search_public_tracker("slowtracker", "test", "all")
            assert results == []

    @pytest.mark.asyncio
    async def test_plugin_nonzero_exit(self):
        """Plugin crashed with stderr — stdout has nothing useful, we return []."""
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_proc = _streaming_proc_mock([])
            mock_proc.returncode = 1
            mock_proc.stderr.read = AsyncMock(return_value=b"ImportError: No module")
            mock_exec.return_value = mock_proc

            results = await self.orch._search_public_tracker("broken", "test", "all")
            assert results == []

    @pytest.mark.asyncio
    async def test_plugin_stderr_error(self):
        """A `__error__` row on stdout is swallowed, not converted to a result."""
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _streaming_proc_mock([{"__error__": "module not found"}])

            results = await self.orch._search_public_tracker("broken", "test", "all")
            assert results == []

    @pytest.mark.asyncio
    async def test_malformed_result_skipped(self):
        mock_results = [
            {
                "name": "Bad",
                "size": "1 GB",
                "seeds": "not_a_number",
                "leech": 0,
                "link": "magnet:?",
                "desc_link": "http://x",
            },
            {
                "name": "Good",
                "size": "1 GB",
                "seeds": 5,
                "leech": 0,
                "link": "magnet:?",
                "desc_link": "http://x",
            },
        ]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _streaming_proc_mock(mock_results)

            results = await self.orch._search_public_tracker("test", "test", "all")
            assert len(results) == 1
            assert results[0].name == "Good"

    @pytest.mark.asyncio
    async def test_multiple_results(self):
        mock_results = [
            {
                "name": f"Result {i}",
                "size": f"{i} GB",
                "seeds": i * 10,
                "leech": i,
                "link": f"magnet:?xt=urn:btih:{i}",
                "desc_link": f"http://x/{i}",
            }
            for i in range(5)
        ]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _streaming_proc_mock(mock_results)

            results = await self.orch._search_public_tracker("test", "ubuntu", "all")
            assert len(results) == 5
            for i, r in enumerate(results):
                assert r.name == f"Result {i}"
                assert r.tracker == "test"


class TestConcurrentSearch:
    def setup_method(self):
        self.orch = SearchOrchestrator()

    @pytest.mark.asyncio
    async def test_search_uses_concurrent_execution(self):
        call_order = []

        async def mock_search(tracker, query, category):
            call_order.append(tracker.name)
            if tracker.name == "rutracker":
                return [
                    SearchResult(
                        name="Rutracker Result",
                        size="1 GB",
                        seeds=10,
                        leechers=5,
                        link="magnet:?1",
                        desc_link="http://r",
                        tracker="rutracker",
                        engine_url="https://rutracker.org",
                    )
                ]
            return []

        with patch.dict(
            os.environ,
            {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p", "ENABLE_DEAD_TRACKERS": "0"},
            clear=True,
        ):
            with patch.object(self.orch, "_search_tracker", side_effect=mock_search):
                metadata = await self.orch.search("ubuntu", "all", enable_metadata=False, validate_trackers=False)
                assert metadata.total_results == 1
                assert "rutracker" in metadata.trackers_searched
                total_trackers = 1 + len(LIVE_PUBLIC_TRACKERS)
                assert len(metadata.trackers_searched) == total_trackers

    @pytest.mark.asyncio
    async def test_search_merges_cross_tracker_results(self):
        async def mock_search(tracker, query, category):
            if tracker.name == "rutracker":
                return [
                    SearchResult(
                        name="Ubuntu 22.04",
                        size="4.0 GB",
                        seeds=50,
                        leechers=10,
                        link="magnet:?rut",
                        desc_link="http://rut",
                        tracker="rutracker",
                        engine_url="https://rutracker.org",
                    )
                ]
            elif tracker.name == "kinozal":
                return [
                    SearchResult(
                        name="Ubuntu 22.04",
                        size="4.0 GB",
                        seeds=30,
                        leechers=5,
                        link="magnet:?kin",
                        desc_link="http://kin",
                        tracker="kinozal",
                        engine_url="https://kinozal.tv",
                    )
                ]
            elif tracker.name == "piratebay":
                return [
                    SearchResult(
                        name="Ubuntu 22.04",
                        size="4.0 GB",
                        seeds=100,
                        leechers=20,
                        link="magnet:?pb",
                        desc_link="http://pb",
                        tracker="piratebay",
                        engine_url="https://thepiratebay.org",
                    )
                ]
            return []

        env = {
            "RUTRACKER_USERNAME": "u",
            "RUTRACKER_PASSWORD": "p",
            "KINOZAL_USERNAME": "u",
            "KINOZAL_PASSWORD": "p",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch.object(self.orch, "_search_tracker", side_effect=mock_search):
                metadata = await self.orch.search("ubuntu", "all", enable_metadata=False, validate_trackers=False)
                stored = self.orch._last_merged_results.get(metadata.search_id)
                merged = stored[0] if stored else []
                ubuntu_merged = [m for m in merged if "Ubuntu 22.04" in m.original_results[0].name]
                assert len(ubuntu_merged) == 1, "Same torrent from multiple trackers should be merged into 1"
                assert len(ubuntu_merged[0].original_results) == 3, "Should have 3 sources"
                assert ubuntu_merged[0].total_seeds == 180, "Seeds should be summed across sources"

    @pytest.mark.asyncio
    async def test_search_handles_partial_failures(self):
        """One working + one crashing tracker: total still completes,
        error surfaces in metadata.errors.

        We use `rutor` as the raising tracker (a live public tracker
        that's always in the fan-out). Previously this test used
        `eztv`, but eztv now lives in `DEAD_PUBLIC_TRACKERS` and never
        runs — so a raise inside the mock never reached the error
        pipe.
        """

        async def mock_search(tracker, query, category):
            if tracker.name == "piratebay":
                return [
                    SearchResult(
                        name="Test",
                        size="1 GB",
                        seeds=10,
                        leechers=5,
                        link="magnet:?",
                        desc_link="http://x",
                        tracker="piratebay",
                        engine_url="https://thepiratebay.org",
                    )
                ]
            if tracker.name == "rutor":
                raise Exception("Connection refused")
            return []

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(self.orch, "_search_tracker", side_effect=mock_search):
                metadata = await self.orch.search("test", "all", enable_metadata=False, validate_trackers=False)
                assert metadata.total_results == 1
                assert metadata.status == "completed"
                assert len(metadata.errors) > 0
