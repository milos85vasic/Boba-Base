"""
Unit tests for progressive de-duplicated result streaming.

Covers the operator-approved fix: the SSE stream emits ``merged_update``
events carrying the DEDUPLICATED (merged) result set as it builds, so the
dashboard grid grows smoothly to the final unique count instead of swapping
a large raw list (~1785 rows) for a small merged list (~663) on
``search_complete``.

Asserts:
  (a) the stream emits >= 1 ``merged_update`` event;
  (b) each ``merged_update`` ``results`` payload is DEDUPLICATED — the
      merged count is <= the number of raw rows fed in;
  (c) the FINAL ``merged_update`` ``merged_results`` EQUALS what
      ``GET /search/{id}`` would return (consistency / no-drop guarantee),
      because both go through the SAME ``_serialize_merged_rows`` helper.

Hermetic: a stub orchestrator drives the real ``SSEHandler`` +
``Deduplicator`` + ``_serialize_merged_rows`` — no live merge service
required.
"""

import asyncio
import importlib.util
import json
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")
sys.path.insert(0, _SRC_PATH)

# Register the merge_service + api packages as namespace packages so the
# importlib test-runner mode resolves ``merge_service.search`` (imported by
# api.routes at module top) — mirrors the sibling deduplicator tests.
sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]
for _name in ("search", "deduplicator"):
    _mod_name = f"merge_service.{_name}"
    if _mod_name not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_mod_name, os.path.join(_MS_PATH, f"{_name}.py"))
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[_mod_name] = _mod
        _spec.loader.exec_module(_mod)

from api.routes import _serialize_merged_rows  # noqa: E402
from api.streaming import SSEHandler  # noqa: E402
from merge_service.deduplicator import Deduplicator  # noqa: E402
from merge_service.search import SearchResult  # noqa: E402


def _r(name: str, link: str, tracker: str, seeds: int = 10) -> SearchResult:
    return SearchResult(
        name=name,
        link=link,
        size="2.0 GB",
        seeds=seeds,
        leechers=2,
        engine_url=f"https://{tracker}.example",
        tracker=tracker,
    )


# Build a corpus where the SAME torrent appears on several trackers, so the
# merge collapses the raw rows to a smaller unique set — mirroring the live
# 1785 raw → 663 merged collapse.
def _corpus_per_tracker() -> dict[str, list[SearchResult]]:
    # 4 logical torrents spread across 3 trackers = 9 raw rows total,
    # collapsing to 4 unique merged rows (Matrix x3, Inception x3,
    # Interstellar x2, Solaris x1).
    h1 = "magnet:?xt=urn:btih:" + "A" * 40
    h2 = "magnet:?xt=urn:btih:" + "B" * 40
    h3 = "magnet:?xt=urn:btih:" + "C" * 40
    h4 = "magnet:?xt=urn:btih:" + "D" * 40
    return {
        "rutracker": [
            _r("The Matrix 1999 1080p BluRay", h1, "rutracker", 100),
            _r("Inception 2010 1080p BluRay", h2, "rutracker", 90),
        ],
        "kinozal": [
            _r("The Matrix 1999 1080p BluRay", h1, "kinozal", 80),
            _r("Inception 2010 1080p BluRay", h2, "kinozal", 70),
            _r("Interstellar 2014 1080p BluRay", h3, "kinozal", 60),
        ],
        "nnmclub": [
            _r("The Matrix 1999 1080p BluRay", h1, "nnmclub", 50),
            _r("Inception 2010 1080p BluRay", h2, "nnmclub", 40),
            _r("Interstellar 2014 1080p BluRay", h3, "nnmclub", 30),
            _r("Solaris 1972 1080p BluRay", h4, "nnmclub", 20),
        ],
    }


class _StubMeta:
    """Minimal SearchMetadata-shaped object for the SSE loop."""

    def __init__(self, status: str, total_results: int, merged_results: int):
        self.status = status
        self.total_results = total_results
        self.merged_results = merged_results
        self.trackers_searched = ["rutracker", "kinozal", "nnmclub"]
        self.tracker_stats = {}

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "total_results": self.total_results,
            "merged_results": self.merged_results,
            "tracker_stats": [],
        }


class _StubOrchestrator:
    """Drives the SSE loop through pending -> completed with a growing
    ``_tracker_results`` so the throttled re-merge has data to chew on.

    Mirrors the minimal surface of the real ``SearchOrchestrator`` that
    ``_build_merged_update`` reads: ``deduplicator``,
    ``get_all_tracker_results``, and — critically — ``_last_merged_results``,
    the authoritative ``{search_id: (merged_list, all_results)}`` cache the
    real orchestrator sets at completion (``search.py:856``) and that
    ``GET /search/{id}`` serializes (``routes.py:573``).

    While the search runs, ``_last_merged_results[search_id]`` is ``([], [])``
    (real orchestrator's pending init at ``search.py:702``), so
    ``_build_merged_update`` falls through to re-merging the accumulated raw
    view for interim snapshots. At COMPLETION the stub populates the cache
    with the authoritative merge.

    To distinguish the cached path from the always-re-merge path (anti-bluff
    §11.4.115): a "late tracker" result lands ONLY in the completion cache,
    NOT in ``get_all_tracker_results``. The cached merge therefore contains
    one MORE unique row than a fresh re-merge of ``get_all_tracker_results``
    would produce — exactly the race the new code closes (a tracker that
    landed between the last interim re-merge and completion). The final emit
    MUST equal the cache (5 rows), not a fresh re-merge (4 rows).
    """

    def __init__(self, search_id: str):
        self.search_id = search_id
        self.deduplicator = Deduplicator()
        self._per_tracker = _corpus_per_tracker()
        self._tracker_results: dict[str, dict[str, list]] = {search_id: {}}
        # Authoritative completion cache — empty while running (matches the
        # real orchestrator's pending init), populated at completion.
        self._last_merged_results: dict[str, tuple] = {search_id: ([], [])}
        # A result the real orchestrator would have folded into the final
        # merge but that NEVER reaches ``get_all_tracker_results`` (it landed
        # in the authoritative completion merge after our last interim view).
        h5 = "magnet:?xt=urn:btih:" + "E" * 40
        self._late_result = _r("Stalker 1979 1080p BluRay", h5, "rutracker", 15)
        # Reveal one tracker's results per status poll so the count grows.
        self._reveal_order = list(self._per_tracker.keys())
        self._poll = 0

    def _authoritative_merge(self):
        """What the real orchestrator caches at completion: the merge of all
        tracker results PLUS the late result that arrived at completion."""
        flat = self.get_all_tracker_results(self.search_id)
        return self.deduplicator.merge_results([*flat, self._late_result])

    # --- methods the SSE loop calls ---
    def get_search_status(self, search_id):
        # Reveal trackers progressively across the first N polls, then complete.
        if self._poll < len(self._reveal_order):
            tname = self._reveal_order[self._poll]
            self._tracker_results[search_id][tname] = self._per_tracker[tname]
        self._poll += 1
        flat = self.get_all_tracker_results(search_id)
        revealed = len(self._tracker_results[search_id])
        done = revealed >= len(self._reveal_order)
        status = "completed" if done and self._poll > len(self._reveal_order) else "running"
        if status == "completed":
            # Mirror the real orchestrator: at completion the authoritative
            # cache is set BEFORE status flips to "completed" (search.py:854-857).
            merged = self._authoritative_merge()
            self._last_merged_results[search_id] = (merged, [*flat, self._late_result])
            merged_count = len(merged)
        else:
            merged_count = len(self.deduplicator.merge_results(flat)) if flat else 0
        return _StubMeta(status, len(flat), merged_count)

    def get_all_tracker_results(self, search_id):
        out = []
        for lst in self._tracker_results.get(search_id, {}).values():
            out.extend(lst)
        return out

    def get_live_results(self, search_id):
        return self.get_all_tracker_results(search_id)


async def _drain(orch, search_id):
    frames = []
    # poll_interval=0 keeps the test fast; the merged_update throttle uses
    # wall-clock so we patch the interval to 0 for the running-loop emission.
    gen = SSEHandler.search_results_stream(search_id, orch, poll_interval=0.0)
    async for frame in gen:
        frames.append(frame)
        if "event: search_complete" in frame:
            break
    return frames


def _parse_merged_updates(frames):
    """Extract the JSON ``data`` of every ``merged_update`` frame."""
    out = []
    for frame in frames:
        lines = frame.split("\n")
        if any(line == "event: merged_update" for line in lines):
            data = "\n".join(line[len("data: ") :] for line in lines if line.startswith("data: "))
            out.append(json.loads(data))
    return out


def test_serialize_merged_rows_is_deduplicated():
    """The shared helper collapses duplicate-infohash raw rows to unique rows."""
    flat = []
    for lst in _corpus_per_tracker().values():
        flat.extend(lst)
    assert len(flat) == 9  # raw (rutracker 2 + kinozal 3 + nnmclub 4)
    merged = Deduplicator().merge_results(flat)
    rows = _serialize_merged_rows(merged)
    assert len(rows) == len(merged)
    assert len(rows) < len(flat)  # deduplicated
    # Each merged row aggregates its sources (the same torrent on N trackers).
    assert any(len(row.sources) > 1 for row in rows)


def test_stream_emits_progressive_merged_updates(monkeypatch):
    """(a) >=1 merged_update; (b) each is deduplicated; (c) final == get_search."""
    import api.streaming as streaming_mod

    # Make the running-loop throttle fire on every poll so we observe the
    # progressive growth deterministically (the throttle is wall-clock based).
    monkeypatch.setattr(streaming_mod, "MERGED_UPDATE_MIN_INTERVAL_S", 0.0)

    search_id = "stub-search-1"
    orch = _StubOrchestrator(search_id)
    frames = asyncio.run(_drain(orch, search_id))

    merged_updates = _parse_merged_updates(frames)

    # (a) at least one merged_update event was emitted
    assert len(merged_updates) >= 1, "stream emitted no merged_update events"

    # count raw result_found rows actually streamed
    raw_count = sum(1 for f in frames if "event: result_found" in f)

    # (b) every merged_update payload is deduplicated: merged_results count
    # equals len(results) and is <= the raw rows seen so far.
    for mu in merged_updates:
        assert mu["merged_results"] == len(mu["results"])
        # no two rows share an exact name (deduplicated by identity/infohash)
        names = [row["name"] for row in mu["results"]]
        assert len(names) == len(set(names)), f"duplicate names in merged_update: {names}"
    final_mu = merged_updates[-1]
    assert final_mu["merged_results"] <= raw_count

    # (c) the FINAL merged_update equals what GET /search/{id} would return.
    # GET serializes orch._last_merged_results[search_id][0] via the SAME
    # _serialize_merged_rows (routes.py:573-583) — the authoritative cache,
    # NOT a fresh re-merge of the accumulated raw view.
    cached_merged, _all = orch._last_merged_results[search_id]
    get_search_rows = _serialize_merged_rows(cached_merged)
    assert final_mu["merged_results"] == len(get_search_rows), (
        f"final streamed merged ({final_mu['merged_results']}) != "
        f"get_search merged ({len(get_search_rows)}) — drop at completion"
    )
    # row shape matches the contract
    contract_keys = {"name", "size", "seeds", "leechers", "tracker", "download_urls", "quality", "content_type", "sources", "freeleech"}
    for row in final_mu["results"]:
        assert contract_keys.issubset(set(row.keys())), f"row missing contract keys: {set(row.keys())}"


def test_final_merged_update_is_content_identical_to_cache(monkeypatch):
    """The FINAL merged_update reads the orchestrator's AUTHORITATIVE cache.

    Proves CONTENT identity (not just count): the final ``merged_update``
    ``results`` row NAMES (sorted) EQUAL the serialized NAMES of
    ``_last_merged_results[search_id][0]`` — exactly what ``GET /search/{id}``
    serializes. Anti-bluff (§11.4.115): the stub seeds a "late tracker"
    result into the completion cache ONLY (NOT into
    ``get_all_tracker_results``), so a fresh re-merge of the accumulated raw
    view produces a DIFFERENT (smaller) set than the cache. If
    ``_build_merged_update`` re-merged instead of reading the cache, the final
    emit would be MISSING the late result and this assertion would FAIL —
    distinguishing the two code paths by content, not coincidence.
    """
    import api.streaming as streaming_mod

    monkeypatch.setattr(streaming_mod, "MERGED_UPDATE_MIN_INTERVAL_S", 0.0)

    search_id = "stub-search-content"
    orch = _StubOrchestrator(search_id)
    frames = asyncio.run(_drain(orch, search_id))
    merged_updates = _parse_merged_updates(frames)
    assert merged_updates, "stream emitted no merged_update events"
    final_mu = merged_updates[-1]

    # The authoritative cache is what GET /search/{id} serializes (routes.py:573).
    cached_merged, _all = orch._last_merged_results[search_id]
    cache_rows = _serialize_merged_rows(cached_merged)
    cache_names = sorted(row.name for row in cache_rows)
    final_names = sorted(row["name"] for row in final_mu["results"])

    # CONTENT identity — the exact row set, not merely the same count.
    assert final_names == cache_names, (
        f"final merged_update names {final_names} != cached merge names "
        f"{cache_names} — final emit did not read the authoritative cache"
    )

    # The late-tracker result proves the cache differs from a fresh re-merge:
    # it is present in the cache (hence the final emit) but absent from a
    # re-merge of get_all_tracker_results. If absent here, the test could not
    # distinguish the cached path from the re-merge path.
    assert orch._late_result.name in cache_names, "late-tracker result missing from cache (test setup broken)"
    fresh_remerge = orch.deduplicator.merge_results(orch.get_all_tracker_results(search_id))
    fresh_names = sorted(row.name for row in _serialize_merged_rows(fresh_remerge))
    assert orch._late_result.name not in fresh_names, "late result leaked into get_all_tracker_results (test setup broken)"
    assert final_names != fresh_names, (
        "final emit equals a fresh re-merge — the test cannot distinguish the "
        "cached path from the always-re-merge path (anti-bluff setup broken)"
    )


def test_no_merged_update_when_deduplicator_absent():
    """Defensive: _build_merged_update returns None if no deduplicator wired."""
    from api.streaming import _build_merged_update

    class _Bare:
        pass

    assert _build_merged_update(_Bare(), "x") is None
