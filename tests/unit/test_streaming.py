import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

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
        """A raising probe fails CLOSED: the stream STOPS (BOB-139, §11.4.252).

        Reconciled per §11.4.120 — this gate previously asserted the fail-OPEN
        behaviour ("stream continues"), which was the defect itself: an
        unresolvable probe left the generator streaming forever, holding a
        socket and a task.  "I cannot determine whether the client is gone"
        now resolves to GONE, with its own honest close reason.
        """
        request = MagicMock()
        request.is_disconnected = AsyncMock(side_effect=Exception("fail"))

        def get_progress(dl_id):
            raise AssertionError("stream must stop before polling progress")

        gen = SSEHandler.download_progress_stream("dl-id", get_progress, poll_interval=0, request=request)
        events = asyncio.run(self._collect(gen))
        assert any("event: close" in e for e in events)
        assert any("disconnect_probe_failed" in e for e in events)
        # We do not KNOW the client disconnected, only that we cannot see.
        assert not any("client_disconnected" in e for e in events)

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
        """A raising probe fails CLOSED: the stream STOPS (BOB-139, §11.4.252).

        Reconciled per §11.4.120 — this gate previously asserted the fail-OPEN
        behaviour.  See the download-stream sibling for the full rationale.
        """
        request = MagicMock()
        request.is_disconnected = AsyncMock(side_effect=Exception("disconnect check failed"))

        class FakeOrchestrator:
            def get_search_status(self, sid):
                raise AssertionError("stream must stop before polling the orchestrator")

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0, request=request)
        events = asyncio.run(self._collect(gen))
        assert any("event: close" in e for e in events)
        assert any("disconnect_probe_failed" in e for e in events)
        assert not any("client_disconnected" in e for e in events)

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


class TestBob193EmitFailureDedup:
    """BOB-193: ``seen_hashes`` / ``seen_hashes_local`` are written BEFORE
    the yield in ``search_results_stream``. If ``format_event`` raises
    after the hash was recorded, the result is never sent AND its hash is
    already recorded -- so a purely TRANSIENT emit failure permanently
    drops the result (mid-search: the hash persists across every later
    poll; at completion: the stream ends immediately after, so there is no
    later chance either).

    DECISION (coordinator, recorded 2026-09-23, per docs/Issues.md
    BOB-193): implement option (c) -- keep add-before-yield, but REMOVE
    the hash on emit failure so exactly ONE retry occurs on the next poll.
    Option (a) (do nothing) leaves the reported defect unfixed. Option (b)
    (add-after-successful-yield) gives at-least-once but a DETERMINISTIC
    failure would then retry forever every poll -- an unbounded hot loop,
    strictly worse in the failure case that matters most. Option (c) is
    bounded: at most 2 total emit attempts per result per stream (1
    initial + 1 retry), never more, regardless of how many further polls
    occur while that same result keeps failing.

    This class carries the RED-baseline-on-the-broken-artifact +
    polarity-switch evidence chain (§11.4.115): the assertion below was
    FIRST authored to characterize the pre-fix defect (asserting the
    flaky result is PERMANENTLY dropped -- zero ``result_found`` events
    even though its retry attempt would have succeeded), run and
    confirmed genuinely reproducing against the unfixed source (captured
    as this change's RED evidence), THEN flipped to assert the fixed,
    bounded-single-retry behaviour once option (c) landed. It is this
    flipped (GREEN) assertion that ships as the permanent regression
    guard; the pre-flip PASS-on-broken-code run is the RED evidence cited
    in the accompanying report, not a second test left in the suite
    (leaving both would make the suite self-contradictory).
    """

    async def _collect_limit(self, gen, max_iterations=200):
        results = []
        async for item in gen:
            results.append(item)
            if len(results) >= max_iterations:
                break
        return results

    @staticmethod
    def _make_result(name, result_hash):
        class R:
            hash = result_hash
            seeds = 1
            leechers = 0
            tracker = "rutracker"
            size = 100
            link = f"magnet:?xt=urn:btih:{result_hash}"

        R.name = name
        return R()

    def test_transient_emit_failure_is_retried_exactly_once_then_recovers(self):
        """GREEN (post-fix, permanent regression guard).

        A result whose FIRST ``format_event`` call raises and whose
        SECOND (next-poll) call succeeds must appear in the SSE output
        EXACTLY ONCE -- the one bounded retry recovered it. Pre-fix, this
        same scenario produces ZERO ``result_found`` events for this
        result (see the RED evidence captured for this change before the
        source fix landed: this exact assertion, run against the
        pre-fix ``streaming.py``, FAILS with ``0 == 1`` -- proving the
        scenario genuinely reproduces BOB-193 rather than merely
        asserting an assumption).
        """
        flaky = self._make_result("Flaky Result", "flaky-hash")

        poll_count = [0]
        TOTAL_RUNNING_POLLS = 4

        class FakeMeta:
            status = "running"
            total_results = 1
            merged_results = 0
            trackers_searched = ["rutracker"]

            def to_dict(self):
                return {"status": "running", "total_results": 1}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                poll_count[0] += 1
                if poll_count[0] > TOTAL_RUNNING_POLLS:
                    m = FakeMeta()
                    m.status = "completed"
                    return m
                return FakeMeta()

            def get_live_results(self, sid):
                # The orchestrator's live-result set is unaffected by a
                # previously-failed emit attempt: the SAME flaky result
                # keeps showing up on every poll until it is actually
                # consumed (streamed out), or the search completes.
                if poll_count[0] > TOTAL_RUNNING_POLLS:
                    return []
                return [flaky]

        call_count = {"n": 0}
        original_format_event = SSEHandler.format_event

        def flaky_format_event(event, data, event_id=None):
            if event == "result_found" and isinstance(data, dict) and data.get("name") == "Flaky Result":
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise RuntimeError("simulated transient emit failure")
            return original_format_event(event, data, event_id)

        with patch.object(SSEHandler, "format_event", staticmethod(flaky_format_event)):
            gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
            events = asyncio.run(self._collect_limit(gen))

        result_events = [e for e in events if "result_found" in e and "Flaky Result" in e]
        assert len(result_events) == 1, (
            f"expected the flaky result to be emitted EXACTLY once after its "
            f"one retry succeeded, got {len(result_events)}: {result_events}"
        )
        # Exactly 2 attempts: the failing first attempt + the successful retry.
        assert call_count["n"] == 2, f"expected exactly 2 format_event attempts, got {call_count['n']}"

    def test_success_path_dedup_is_unchanged(self):
        """A result whose FIRST emit succeeds must still be deduped on
        every later poll -- BOB-193's fix touches ONLY the emit-failure
        path, never the success path (scope constraint, verified here).
        """
        ok = self._make_result("Solid Result", "solid-hash")

        poll_count = [0]
        TOTAL_RUNNING_POLLS = 4

        class FakeMeta:
            status = "running"
            total_results = 1
            merged_results = 0
            trackers_searched = ["rutracker"]

            def to_dict(self):
                return {"status": "running", "total_results": 1}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                poll_count[0] += 1
                if poll_count[0] > TOTAL_RUNNING_POLLS:
                    m = FakeMeta()
                    m.status = "completed"
                    return m
                return FakeMeta()

            def get_live_results(self, sid):
                if poll_count[0] > TOTAL_RUNNING_POLLS:
                    return []
                return [ok]

        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
        events = asyncio.run(self._collect_limit(gen))
        result_events = [e for e in events if "result_found" in e and "Solid Result" in e]
        assert len(result_events) == 1, (
            f"success-path dedup regressed: expected exactly 1 emit across "
            f"{TOTAL_RUNNING_POLLS} polls of the SAME live result, got "
            f"{len(result_events)}: {result_events}"
        )

    def test_deterministically_failing_result_is_bounded_never_an_infinite_retry_storm(self):
        """A result whose ``format_event`` ALWAYS raises must NOT be
        retried forever.

        EXACT BOUND IMPLEMENTED (stated precisely, not just "bounded",
        per §11.4.6): at most 2 total emit ATTEMPTS per result per
        stream -- the initial attempt plus exactly 1 retry. Once the
        retry ALSO fails, the hash is left recorded permanently, so a
        3rd, 4th, ... Nth poll of the SAME still-failing result makes
        ZERO further ``format_event`` calls for it. Polling itself stays
        unbounded in COUNT (the stream keeps polling every
        ``poll_interval`` until the search completes or the client
        disconnects) -- what is bounded is the number of emit ATTEMPTS
        made for one given result, which is exactly 2, never more,
        regardless of how many further polls occur.
        """
        cursed = self._make_result("Cursed Result", "cursed-hash")

        poll_count = [0]
        TOTAL_RUNNING_POLLS = 10  # far more than the 2-attempt bound

        class FakeMeta:
            status = "running"
            total_results = 1
            merged_results = 0
            trackers_searched = ["rutracker"]

            def to_dict(self):
                return {"status": "running", "total_results": 1}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                poll_count[0] += 1
                if poll_count[0] > TOTAL_RUNNING_POLLS:
                    m = FakeMeta()
                    m.status = "completed"
                    return m
                return FakeMeta()

            def get_live_results(self, sid):
                # Isolate this test to the "running"-loop dedup set
                # (seen_hashes): no pending results are left for the
                # completion-flush branch (seen_hashes_local), which is
                # covered separately below.
                if poll_count[0] > TOTAL_RUNNING_POLLS:
                    return []
                return [cursed]

        call_count = {"n": 0}
        original_format_event = SSEHandler.format_event

        def cursed_format_event(event, data, event_id=None):
            if event == "result_found" and isinstance(data, dict) and data.get("name") == "Cursed Result":
                call_count["n"] += 1
                raise RuntimeError("simulated deterministic (permanent) emit failure")
            return original_format_event(event, data, event_id)

        with patch.object(SSEHandler, "format_event", staticmethod(cursed_format_event)):
            gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
            events = asyncio.run(self._collect_limit(gen))

        assert not any("result_found" in e and "Cursed Result" in e for e in events)
        assert any("search_complete" in e for e in events), "stream must not hang/crash on a permanently-failing result"
        assert call_count["n"] == 2, (
            f"expected exactly 2 emit attempts (1 initial + 1 bounded retry) "
            f"across {TOTAL_RUNNING_POLLS} polls, got {call_count['n']} -- "
            f"an unbounded retry-storm regression"
        )

    def test_completion_flush_site_also_discards_hash_on_emit_failure(self):
        """The SAME add-before-yield-then-discard-on-failure fix must be
        applied at the OTHER dedup site (``seen_hashes_local`` in the
        ``status in ("completed", "failed")`` completion-flush branch,
        around the original line ~356) -- the item explicitly measured
        the defect at BOTH sites. A single completion pass cannot itself
        demonstrate a cross-poll retry (there is no later poll once the
        stream ends), so this test asserts what IS observable there:
        a raising completion-flush emit does not corrupt the dedup set
        or crash the stream, and ``search_complete`` still lands.
        """
        completion_only = self._make_result("Completion Only Result", "completion-only-hash")

        class FakeMeta:
            status = "completed"
            total_results = 1
            merged_results = 0
            trackers_searched = ["rutracker"]

            def to_dict(self):
                return {"status": "completed", "total_results": 1}

        class FakeOrchestrator:
            def get_search_status(self, sid):
                return FakeMeta()

            def get_live_results(self, sid):
                return [completion_only]

        call_count = {"n": 0}
        original_format_event = SSEHandler.format_event

        def flaky_format_event(event, data, event_id=None):
            if event == "result_found" and isinstance(data, dict) and data.get("name") == "Completion Only Result":
                call_count["n"] += 1
                raise RuntimeError("simulated completion-flush emit failure")
            return original_format_event(event, data, event_id)

        with patch.object(SSEHandler, "format_event", staticmethod(flaky_format_event)):
            gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0)
            events = asyncio.run(self._collect_limit(gen))

        assert not any("result_found" in e and "Completion Only Result" in e for e in events)
        assert any("search_complete" in e for e in events)
        assert call_count["n"] == 1, "single completion pass: exactly one attempt is possible, no cross-poll retry exists here"
