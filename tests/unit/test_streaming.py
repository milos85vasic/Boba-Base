import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))

from api.streaming import SSEHandler


class TestSSEHandler:
    def test_format_event_basic(self):
        result = SSEHandler.format_event(event="test_event", data={"key": "value"})
        assert "event: test_event" in result
        assert "data: " in result
        assert '"key"' in result
        assert '"value"' in result
        assert result.endswith("\n")

    def test_format_event_with_id(self):
        result = SSEHandler.format_event(event="test_event", data={"x": 1}, event_id="abc-123")
        assert "id: abc-123" in result
        assert "event: test_event" in result

    def test_format_event_multiline_data(self):
        result = SSEHandler.format_event(event="test", data={"msg": "line1\nline2"})
        assert "line1" in result
        assert "line2" in result

    def test_format_event_empty_event(self):
        result = SSEHandler.format_event(event="", data={"k": "v"})
        assert "event:" not in result
        assert "data:" in result

    def test_search_results_stream_not_found(self):
        class FakeOrchestrator:
            def get_search_status(self, sid):
                return None

        gen = SSEHandler.search_results_stream("bad-id", FakeOrchestrator())
        events = asyncio.run(self._collect(gen))
        assert len(events) == 2
        assert '"error"' in events[1]

    def test_search_results_stream_completed(self):
        class FakeMeta:
            status = "completed"
            total_results = 5
            merged_results = 3
            trackers_searched = ["rutracker"]

            def to_dict(self):
                return {"status": "completed", "total_results": 5}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                return FakeMeta()

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect(gen))
        assert any("search_start" in e for e in events)
        assert any("search_complete" in e for e in events)

    def test_download_progress_stream_not_found(self):
        gen = SSEHandler.download_progress_stream("dl-id", lambda x: None, poll_interval=0)
        events = asyncio.run(self._collect(gen))
        assert len(events) == 2
        assert any("download_start" in e for e in events)
        assert any("download_complete" in e for e in events)

    def test_download_progress_stream_complete(self):
        call_count = 0

        def get_progress(dl_id):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                return None
            return {"progress": 50, "complete": False}

        gen = SSEHandler.download_progress_stream("dl-id", get_progress, poll_interval=0)
        events = asyncio.run(self._collect(gen))
        assert len(events) >= 2

    def test_create_streaming_response(self):
        async def fake_gen():
            yield "data: test\n\n"

        response = SSEHandler.create_streaming_response(fake_gen())
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"

    def test_download_progress_stream_client_disconnect(self):
        """Client disconnect during download progress should emit close event."""
        request = MagicMock()
        request.is_disconnected = AsyncMock(return_value=True)

        gen = SSEHandler.download_progress_stream("dl-id", lambda x: {"progress": 50}, poll_interval=0, request=request)
        events = asyncio.run(self._collect(gen))
        assert any("close" in e for e in events)
        assert any("client_disconnected" in e for e in events)

    def test_download_progress_stream_client_disconnect_raises(self):
        """When request.is_disconnected raises during download, stream continues."""
        request = MagicMock()
        request.is_disconnected = AsyncMock(side_effect=Exception("fail"))

        call_count = [0]

        def get_progress(dl_id):
            call_count[0] += 1
            if call_count[0] > 2:
                return None
            return {"progress": 50, "complete": False}

        gen = SSEHandler.download_progress_stream("dl-id", get_progress, poll_interval=0, request=request)
        events = asyncio.run(self._collect(gen))
        assert not any("close" in e for e in events)
        assert any("download_complete" in e for e in events)

    def test_download_progress_stream_complete_flag_true(self):
        """Progress with complete=True should stop the stream after yielding progress."""
        def get_progress(dl_id):
            return {"progress": 100, "complete": True}

        gen = SSEHandler.download_progress_stream("dl-id", get_progress, poll_interval=0)
        events = asyncio.run(self._collect(gen))
        assert any("download_progress" in e for e in events)
        assert any("download_start" in e for e in events)
        # Should stop without needing a None progress return

    def test_search_results_stream_no_request_no_disconnect(self):
        """Without request, _client_gone returns False and stream completes normally."""
        class FakeMeta:
            status = "completed"
            total_results = 0
            merged_results = 0
            trackers_searched = []

            def to_dict(self):
                return {"status": "completed"}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                return FakeMeta()

            def get_live_results(self, sid):
                return []

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect(gen))
        assert any("search_start" in e for e in events)
        assert any("search_complete" in e for e in events)

    async def _collect(self, gen):
        results = []
        async for item in gen:
            results.append(item)
        return results


class TestSearchResultsStreamEdgeCases:
    """Edge cases for search_results_stream: disconnect, tracker stats, failed status, exceptions."""

    async def _collect(self, gen):
        results = []
        async for item in gen:
            results.append(item)
        return results

    def test_search_results_stream_client_disconnect(self):
        """Client disconnect should emit close event and stop."""
        request = MagicMock()
        request.is_disconnected = AsyncMock(return_value=True)

        class FakeOrchestrator:
            def get_search_status(self, sid):
                return MagicMock(
                    status="running",
                    total_results=0,
                    merged_results=0,
                    trackers_searched=[],
                    tracker_stats={},
                    to_dict=lambda: {"status": "running"},
                )

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0, request=request)
        events = asyncio.run(self._collect(gen))
        assert any("close" in e for e in events)
        assert any("client_disconnected" in e for e in events)

    def test_search_results_stream_client_disconnect_raises(self):
        """When request.is_disconnected raises, _client_gone returns False and stream continues."""
        request = MagicMock()
        request.is_disconnected = AsyncMock(side_effect=Exception("disconnect check failed"))

        class FakeMeta:
            status = "running"
            total_results = 0
            merged_results = 0
            trackers_searched = []

            def to_dict(self):
                return {"status": "running"}

        call_count = [0]

        class FakeOrchestrator:
            def get_search_status(self, sid):
                call_count[0] += 1
                if call_count[0] > 2:
                    m = FakeMeta()
                    m.status = "completed"
                    return m
                return FakeMeta()

            def get_live_results(self, sid):
                return []

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0, request=request)
        events = asyncio.run(self._collect(gen))
        assert not any("close" in e for e in events)
        assert any("search_complete" in e for e in events)

    def test_search_results_stream_tracker_transitions(self):
        """Tracker status transitions should emit tracker_started and tracker_completed events."""
        from types import SimpleNamespace

        class FakeStat:
            def __init__(self, status):
                self.status = status

            def to_dict(self):
                return {"name": "test_tracker", "status": self.status}

        class FakeMeta:
            status = "running"
            total_results = 0
            merged_results = 0
            trackers_searched = ["test_tracker"]

            def to_dict(self):
                return {"status": "running"}

        call_count = [0]

        class FakeOrchestrator:
            def get_search_status(self, sid):
                call_count[0] += 1
                m = FakeMeta()
                if call_count[0] == 1:
                    m.tracker_stats = {"test_tracker": FakeStat("pending")}
                elif call_count[0] == 2:
                    m.tracker_stats = {"test_tracker": FakeStat("running")}
                elif call_count[0] == 3:
                    m.tracker_stats = {"test_tracker": FakeStat("success")}
                else:
                    m.status = "completed"
                    m.tracker_stats = {"test_tracker": FakeStat("success")}
                return m

            def get_live_results(self, sid):
                return []

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect(gen))
        started_events = [e for e in events if "tracker_started" in e]
        completed_events = [e for e in events if "tracker_completed" in e]
        assert len(started_events) == 1
        assert len(completed_events) == 1

    def test_search_results_stream_tracker_stats_emit_exception(self):
        """Exception in tracker stats emit should not kill the stream."""
        class BrokenStat:
            status = "running"

            def to_dict(self):
                raise RuntimeError("broken to_dict")

        class FakeMeta:
            status = "running"
            total_results = 0
            merged_results = 0
            trackers_searched = ["broken"]

            def to_dict(self):
                return {"status": "running"}

        call_count = [0]

        class FakeOrchestrator:
            def get_search_status(self, sid):
                call_count[0] += 1
                m = FakeMeta()
                if call_count[0] == 1:
                    m.tracker_stats = {"broken": BrokenStat()}
                else:
                    m.status = "completed"
                    m.tracker_stats = {"broken": BrokenStat()}
                return m

            def get_live_results(self, sid):
                return []

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect(gen))
        # Stream should complete normally despite broken to_dict
        assert any("search_complete" in e for e in events)

    def test_search_results_stream_status_failed(self):
        """Status='failed' should emit search_complete."""
        class FakeMeta:
            status = "failed"
            total_results = 3
            merged_results = 1
            trackers_searched = ["tracker1"]

            def to_dict(self):
                return {"status": "failed", "total_results": 3}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                return FakeMeta()

            def get_live_results(self, sid):
                return []

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect(gen))
        complete_events = [e for e in events if "search_complete" in e]
        assert len(complete_events) == 1
        assert "failed" in events[-1] or "failed" in str(events)

    def test_search_results_stream_live_results_exception_on_completed(self):
        """Exception in get_live_results on completed should not kill stream, still emits search_complete."""
        class FakeMeta:
            status = "completed"
            total_results = 5
            merged_results = 3
            trackers_searched = ["t1"]

            def to_dict(self):
                return {"status": "completed", "total_results": 5}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                return FakeMeta()

            def get_live_results(self, sid):
                raise RuntimeError("live results unavailable")

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect(gen))
        assert any("search_complete" in e for e in events)

    def test_search_results_stream_live_results_exception_during_running(self):
        """Exception in get_live_results during running should not kill stream."""
        class FakeMeta:
            status = "running"
            total_results = 0
            merged_results = 0
            trackers_searched = []

            def to_dict(self):
                return {"status": "running"}

        call_count = [0]

        class FakeOrchestrator:
            def get_search_status(self, sid):
                call_count[0] += 1
                if call_count[0] > 2:
                    m = FakeMeta()
                    m.status = "completed"
                    return m
                return FakeMeta()

            def get_live_results(self, sid):
                raise RuntimeError("boom")

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect(gen))
        assert any("search_complete" in e for e in events)

    def test_search_results_stream_result_no_hash_attribute(self):
        """Result without hash attribute uses id() fallback and does not raise."""
        class FakeResult:
            name = "No Hash"
            seeds = 10

        class FakeMeta:
            status = "running"
            total_results = 1
            merged_results = 0
            trackers_searched = ["t1"]

            def to_dict(self):
                return {"status": "running", "total_results": 1}

        call_count = [0]

        class FakeOrchestrator:
            def get_search_status(self, sid):
                call_count[0] += 1
                if call_count[0] > 2:
                    m = FakeMeta()
                    m.status = "completed"
                    return m
                return FakeMeta()

            def get_live_results(self, sid):
                return [FakeResult()]

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect(gen))
        result_events = [e for e in events if "result_found" in e]
        assert len(result_events) >= 1


class TestRealTimeStreaming:
    """Tests for real-time streaming of individual search results."""

    async def _collect_limit(self, gen, max_iterations=20):
        results = []
        async for item in gen:
            results.append(item)
            if len(results) >= max_iterations:
                break
        return results

    def test_streaming_seeks_live_results_while_status_running(self):
        """SSE must emit result_found events while status=running.

        Regression guard for issue #6: the old POST /search blocked
        until all trackers finished, so by the time the SSE consumer
        attached the status was already ``completed``.  With the
        start_search + background-task split, SSE now sees intermediate
        status and emits results as they arrive.
        """

        class FakeResult:
            hash = "xyz"
            name = "Debian 12"
            seeds = 42
            leechers = 1
            tracker = "rutracker"
            size = 1024
            link = "magnet:?xt=urn:btih:xyz"

        call_count = [0]

        class FakeMeta:
            def __init__(self, status):
                self.status = status
                self.total_results = 1
                self.merged_results = 0
                self.trackers_searched = ["rutracker"]

            def to_dict(self):
                return {"status": self.status, "total_results": 1}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                call_count[0] += 1
                # First two polls: still running. After that: completed.
                if call_count[0] >= 3:
                    return FakeMeta("completed")
                return FakeMeta("running")

            def get_live_results(self, sid):
                return [FakeResult()]

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect_limit(gen))
        result_events = [e for e in events if "result_found" in e]
        complete_events = [e for e in events if "search_complete" in e]
        assert result_events, "Expected at least one result_found event"
        # result_found must come before search_complete.
        first_result_idx = next(i for i, e in enumerate(events) if "result_found" in e)
        first_complete_idx = next(i for i, e in enumerate(events) if "search_complete" in e)
        assert first_result_idx < first_complete_idx
        assert complete_events, "Expected search_complete event"

    def test_streaming_yields_individual_results(self):
        """Test that search_results_stream yields individual results as they arrive, not just counts."""

        class FakeResult:
            hash = "abc123"
            name = "Test Movie 2023 1080p"
            seeds = 100
            tracker = "rutracker"

        call_count = [0]

        class FakeMeta:
            status = "running"
            total_results = 1
            merged_results = 0
            trackers_searched = ["rutracker"]

            def to_dict(self):
                return {"status": "running", "total_results": 1}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                call_count[0] += 1
                if call_count[0] > 3:
                    m = FakeMeta()
                    m.status = "completed"
                    return m
                return FakeMeta()

            def get_live_results(self, sid):
                return [FakeResult()]

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect_limit(gen))
        has_result_found = any("result_found" in e for e in events)
        assert has_result_found, "Should emit result_found event with individual result data"

    def test_streaming_result_contains_result_details(self):
        """Test that result_found event contains actual result details (name, seeds, tracker)."""
        call_count = [0]

        class FakeResult:
            hash = "def456"
            name = "Awesome Film 2024 4K"
            seeds = 250
            leechers = 50
            tracker = "kinozal"

        class FakeMeta:
            status = "running"
            total_results = 1
            merged_results = 0
            trackers_searched = ["kinozal"]

            def to_dict(self):
                return {"status": "running", "total_results": 1}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                call_count[0] += 1
                if call_count[0] > 3:
                    m = FakeMeta()
                    m.status = "completed"
                    return m
                return FakeMeta()

            def get_live_results(self, sid):
                return [FakeResult()]

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect_limit(gen))
        result_events = [e for e in events if "result_found" in e]
        assert len(result_events) > 0, "Should have result_found event"
        assert "Awesome Film" in result_events[0], "Result should contain name"

    def test_streaming_shows_trackers_as_they_complete(self):
        """Test that results_update events show which trackers have completed."""
        call_count = [0]

        class FakeMeta:
            status = "running"
            total_results = 10
            merged_results = 5
            trackers_searched = ["rutracker", "kinozal"]

            def to_dict(self):
                return {"status": "running", "total_results": 10, "trackers_searched": ["rutracker", "kinozal"]}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                call_count[0] += 1
                if call_count[0] > 3:
                    m = FakeMeta()
                    m.status = "completed"
                    return m
                return FakeMeta()

            def get_live_results(self, sid):
                return []

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect_limit(gen))
        update_events = [e for e in events if "results_update" in e]
        assert len(update_events) > 0, "Should have results_update events"
        has_trackers = any("rutracker" in e or "kinozal" in e for e in update_events)
        assert has_trackers, "Should show which trackers have been searched"


class TestSSEFormatCompliance:
    """Test that SSE events conform to the Server-Sent Events specification."""

    def test_event_ends_with_double_newline(self):
        """SSE events must end with two newline characters per spec."""
        from api.streaming import SSEHandler

        event = SSEHandler.format_event("result_found", {"name": "test"})
        assert event.endswith("\n\n"), f"Event should end with \\n\\n, got: {event!r}"

    def test_empty_event_ends_with_double_newline(self):
        """Even empty events must end with two newlines."""
        from api.streaming import SSEHandler

        event = SSEHandler.format_event("", {"data": "value"})
        assert event.endswith("\n\n"), f"Empty event should end with \\n\\n, got: {event!r}"

    def test_multiline_data_ends_with_double_newline(self):
        """Multiline data events must end with two newlines."""
        from api.streaming import SSEHandler

        event = SSEHandler.format_event("update", {"key": "line1\nline2"})
        assert event.endswith("\n\n"), f"Multiline event should end with \\n\\n, got: {event!r}"
