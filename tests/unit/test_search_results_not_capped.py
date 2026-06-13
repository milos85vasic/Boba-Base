"""§11.4.135 regression guard — get_search must NOT cap the merged list at 50.

Defect B (operator-reported 2026-06-13): a "Linux" search streamed 2153 results
into the live grid, but on completion the grid collapsed to "just a fraction"
because ``get_search`` hardcoded ``for m in merged[:50]``. The post-completion
result set must match the streamed set (all merged), with an optional ``?limit``
to truncate for callers that explicitly want a page.

RED on the pre-fix code (returns 50), GREEN after the uncap (returns all 73).
"""

import os
import sys
from datetime import datetime, timezone, UTC
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_src = os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


def _merged_item(i: int) -> SimpleNamespace:
    best = SimpleNamespace(
        name=f"Linux result {i}",
        size="1 GB",
        seeds=i,
        leechers=0,
        link=f"magnet:?xt=urn:btih:{i:040x}",
        desc_link=None,
        tracker="rutracker",
        quality="hd",
        content_type="software",
        freeleech=False,
    )
    return SimpleNamespace(
        original_results=[best],
        canonical_identity=SimpleNamespace(content_type=SimpleNamespace(value="software")),
        total_seeds=i,
        total_leechers=0,
    )


def _metadata(n: int) -> MagicMock:
    meta = MagicMock()
    meta.search_id = "sid"
    meta.query = "Linux"
    meta.status = "completed"
    meta.total_results = n
    meta.merged_results = n
    meta.trackers_searched = ["rutracker"]
    meta.errors = []
    meta.started_at = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
    meta.completed_at = datetime(2026, 6, 13, 12, 0, 5, tzinfo=UTC)
    meta.to_dict.return_value = {"tracker_stats": []}
    return meta


def _orch(n: int) -> MagicMock:
    merged = [_merged_item(i) for i in range(n)]
    orch = MagicMock()
    orch.get_search_status.return_value = _metadata(n)
    orch._last_merged_results = {"sid": (merged, merged)}
    return orch


@pytest.mark.asyncio
async def test_get_search_returns_all_merged_not_capped_at_50():
    from api.routes import get_search

    n = 73  # > the old hardcoded 50 cap
    with patch("api.routes._get_orchestrator", return_value=_orch(n)):
        resp = await get_search("sid", MagicMock())
    # Pre-fix: ``merged[:50]`` → 50. Fixed: all 73 (matches the live stream).
    assert len(resp.results) == n, f"expected all {n} merged results, got {len(resp.results)}"
    assert resp.merged_results == n


@pytest.mark.asyncio
async def test_get_search_optional_limit_truncates():
    from api.routes import get_search

    n = 73
    with patch("api.routes._get_orchestrator", return_value=_orch(n)):
        resp = await get_search("sid", MagicMock(), limit=10)
    assert len(resp.results) == 10


@pytest.mark.asyncio
async def test_get_search_small_set_returned_whole():
    from api.routes import get_search

    n = 7  # fewer than 50 — must still be returned whole
    with patch("api.routes._get_orchestrator", return_value=_orch(n)):
        resp = await get_search("sid", MagicMock())
    assert len(resp.results) == n
