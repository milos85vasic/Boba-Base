#!/usr/bin/env python3
"""BOB-139 — §11.4.120 reconciliation for two stale gates. NOT YET APPLIED.

`tests/unit/test_streaming.py` contains two tests whose assertions codify the
FAIL-OPEN defect that BOB-139 removed.  Their own docstrings say the quiet
part out loud:

    "When request.is_disconnected raises during download, stream continues."
    "When request.is_disconnected raises, _client_gone returns False and
     stream continues."

Both assert `assert not any("close" in e for e in events)` — i.e. they assert
that a raising probe does NOT stop the stream, which is precisely the leak.

§11.4.120 (fix-breaks-its-own-gate) mandates RECONCILIATION: rewrite the gate
to assert the NEW mechanism.  The two forbidden responses are (a) fake-passing
the gate and (b) reverting the correct fix.  §11.4.102 investigation was
performed first and confirms these gates asserted old-correct-now-removed
behaviour — they are not catching a regression the fix introduced.

This script was NOT run by the BOB-139 agent: `tests/unit/test_streaming.py`
is outside that agent's assigned file ownership and editing it would have
violated the §11.4.119 single-resource-owner constraint under which parallel
agents were dispatched.  The owner of that file should run:

    .venv/bin/python docs/qa/BOB-139/reconcile_stale_gates.py
    .venv/bin/python -m pytest tests/unit/test_streaming.py -q --import-mode=importlib

The script is self-verifying: it asserts each old block appears exactly once
before replacing it, so it cannot silently half-apply.
"""

from __future__ import annotations

import sys
from pathlib import Path

PATH = "tests/unit/test_streaming.py"

OLD_DOWNLOAD = '''    def test_download_progress_stream_client_disconnect_raises(self):
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
'''

NEW_DOWNLOAD = '''    def test_download_progress_stream_client_disconnect_raises(self):
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
'''

OLD_SEARCH_HEAD = '''    def test_search_results_stream_client_disconnect_raises(self):
        """When request.is_disconnected raises, _client_gone returns False and stream continues."""
        request = MagicMock()
        request.is_disconnected = AsyncMock(side_effect=Exception("disconnect check failed"))
'''

NEW_SEARCH_BLOCK = '''    def test_search_results_stream_client_disconnect_raises(self):
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
'''

OLD_SEARCH_TAIL = """        gen = SSEHandler.search_results_stream("sid", FakeOrchestrator(), poll_interval=0, request=request)
        events = asyncio.run(self._collect(gen))
        assert not any("close" in e for e in events)
        assert any("search_complete" in e for e in events)
"""


def main() -> int:
    src = Path(PATH).read_text(encoding="utf-8")

    if src.count(OLD_DOWNLOAD) != 1:
        print(f"REFUSING: expected exactly 1 stale download gate, found {src.count(OLD_DOWNLOAD)}", file=sys.stderr)
        return 1
    src = src.replace(OLD_DOWNLOAD, NEW_DOWNLOAD, 1)

    start = src.find(OLD_SEARCH_HEAD)
    if start == -1 or src.count(OLD_SEARCH_HEAD) != 1:
        print("REFUSING: stale search gate not found exactly once", file=sys.stderr)
        return 1
    end = src.find(OLD_SEARCH_TAIL, start)
    if end == -1:
        print("REFUSING: stale search gate tail not found", file=sys.stderr)
        return 1
    src = src[:start] + NEW_SEARCH_BLOCK + src[end + len(OLD_SEARCH_TAIL) :]

    Path(PATH).write_text(src, encoding="utf-8")
    print(f"reconciled 2 stale gates in {PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
