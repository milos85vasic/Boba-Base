"""RW-08 regression guard — `/api/v1/search/sync` keepalive heartbeat.

Root cause (docs/qa/rw08-latency-diagnosis-20260616.md): the old
`/search/sync` did a fully-blocking `await orch.search(...)` and sent ZERO
bytes for the whole ~67 s fan-out, so an idle SSH tunnel / proxy tore the
socket down mid-flight → "search resets over tunnel". The SSE path survives
because its keepalive frames keep the socket warm.

The fix: `/search/sync` streams a tiny keepalive byte (a single space, which
JSON parsers ignore as leading whitespace) every ~`SYNC_HEARTBEAT_SECONDS`
WHILE the search runs, then streams the final JSON result. The result set is
UNCHANGED — only the socket stays warm.

Anti-bluff (§11.4.43 RED-first / §11.4.115): these assertions FAIL against
the old blocking code (no leading-whitespace heartbeat is ever emitted, and
the response is buffered into one chunk) and PASS only once the heartbeat
StreamingResponse is wired. The body is parsed as REAL JSON and the result
count / names are asserted — not just a status code (§11.4 / §11.4.69).
"""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


def _make_slow_orch(delay: float, results):
    """An orchestrator whose `search()` blocks for `delay` seconds (mimicking a
    slow multi-tracker fan-out) then returns metadata + one merged result."""
    orch = MagicMock()
    orch._max_concurrent_searches = 8
    orch.is_search_queue_full.return_value = False
    orch._active_searches = {}
    orch._search_tasks = {}
    orch.issue_stream_token.return_value = "tok"

    search_id = "rw08-test"

    from merge_service.search import SearchResult

    merged = []
    for r in results:
        m = MagicMock()
        best = SearchResult(
            name=f"debian-{r['tracker']}.iso",
            link=r["link"],
            size="700 MB",
            seeds=r["seeds"],
            leechers=0,
            engine_url=f"https://{r['tracker']}.example",
            tracker=r["tracker"],
            content_type="other",
            quality="unknown",
        )
        m.original_results = [best]
        m.canonical_identity = None
        m.total_seeds = r["seeds"]
        m.total_leechers = 0
        merged.append(m)
    orch._last_merged_results = {search_id: (merged, None)}

    metadata = MagicMock()
    metadata.search_id = search_id
    metadata.query = "debian"
    metadata.total_results = len(results)
    metadata.merged_results = len(results)
    metadata.trackers_searched = [r["tracker"] for r in results]
    metadata.errors = []
    metadata.status = "completed"
    metadata.started_at = datetime.now(UTC)
    metadata.completed_at = datetime.now(UTC)
    metadata.to_dict.return_value = {"tracker_stats": []}

    async def _slow_search(**_kwargs):
        await asyncio.sleep(delay)
        return metadata

    orch.search = AsyncMock(side_effect=_slow_search)
    return orch


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    created = []

    def _build(orch):
        _purge_api_module()
        import api
        import api.hooks

        monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(tmp_path / "hooks.json"))
        api.orchestrator_instance = orch
        c = TestClient(api.app)
        created.append(c)
        return c

    yield _build
    for c in created:
        c.close()


def test_search_sync_emits_keepalive_before_json(client_factory, monkeypatch):
    """During a slow search the raw stream MUST contain a keepalive space
    BEFORE the JSON body, and the body MUST still parse with the right
    results. RED on the old blocking handler (no leading whitespace, body
    is one buffered chunk)."""
    # Heartbeat far below the search delay so several keepalives fire.
    monkeypatch.setenv("SYNC_HEARTBEAT_SECONDS", "0.2")

    orch = _make_slow_orch(
        delay=1.0,
        results=[
            {"tracker": "rutor", "link": "magnet:?xt=urn:btih:aaa", "seeds": 42},
            {"tracker": "kinozal", "link": "magnet:?xt=urn:btih:bbb", "seeds": 7},
        ],
    )
    client = client_factory(orch)

    with client.stream("POST", "/api/v1/search/sync", json={"query": "debian"}) as resp:
        assert resp.status_code == 200
        raw = b""
        for chunk in resp.iter_raw():
            raw += chunk

    # 1) At least one leading keepalive space before the first JSON char.
    first_brace = raw.find(b"{")
    assert first_brace > 0, (
        "expected ≥1 keepalive byte BEFORE the JSON body — the old blocking "
        f"handler emits none. raw head={raw[:40]!r}"
    )
    assert raw[:first_brace].strip() == b"", (
        f"bytes before JSON must be pure whitespace keepalive, got {raw[:first_brace]!r}"
    )
    assert b" " in raw[:first_brace], "keepalive byte must be a space"

    # 2) The streamed body still parses as the EXPECTED JSON (no results dropped).
    payload = json.loads(raw)
    assert payload["query"] == "debian"
    assert payload["status"] == "completed"
    assert len(payload["results"]) == 2, "both merged results must survive the heartbeat path"
    trackers = {s["tracker"] for r in payload["results"] for s in r["sources"]}
    assert {"rutor", "kinozal"} <= trackers


def test_search_sync_body_is_leading_whitespace_tolerant_json(client_factory, monkeypatch):
    """A normal (leading-whitespace-tolerant) JSON client parses the full
    streamed body unchanged — proves the heartbeat does not corrupt the
    contract for plain `requests`-style callers."""
    monkeypatch.setenv("SYNC_HEARTBEAT_SECONDS", "0.2")
    orch = _make_slow_orch(
        delay=0.6,
        results=[{"tracker": "rutor", "link": "magnet:?xt=urn:btih:ccc", "seeds": 99}],
    )
    client = client_factory(orch)

    resp = client.post("/api/v1/search/sync", json={"query": "debian"})
    assert resp.status_code == 200
    # httpx/json buffers and tolerates the leading whitespace heartbeat.
    payload = resp.json()
    assert payload["query"] == "debian"
    assert len(payload["results"]) == 1
