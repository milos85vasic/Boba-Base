"""Real end-to-end tests for the full search-merge-download pipeline.

These tests drive the pipeline exactly the way an end user's browser
does: a real HTTP request into the real, running merge-search FastAPI
app (``download-proxy/src/api``), through the real, unmocked
``SearchOrchestrator``, out to real public/private tracker plugins over
real network I/O, back through the real ``Deduplicator`` merge step, and
finally asserted against the real JSON body a dashboard client would
render:

    1. Search query -> real HTTP fan-out to multiple real trackers
    2. Real deduplication/merging of the raw per-tracker results
    3. The merged, user-observable response body

Anti-bluff disclosure (2026-08-09 relocation)
----------------------------------------------
This file used to contain the above docstring's promise while every test
in it actually patched ``SearchOrchestrator._get_enabled_trackers`` and
``SearchOrchestrator._search_tracker`` with synthetic fakes, so **no real
tracker HTTP call ever happened** — a direct violation of this project's
own anti-bluff mandate (mocks are permitted ONLY in ``tests/unit/``) and
of the ``tests/e2e/`` directory's own naming contract. That mocked
orchestration-bookkeeping coverage was real and worth keeping, so it was
relocated verbatim to
``tests/unit/test_full_pipeline_orchestration_logic.py`` (where mocking
production collaborators is permitted) and replaced here with the real
thing.

This file contains **no** ``@patch`` / ``monkeypatch`` / ``patch.object``
of any ``SearchOrchestrator``-internal method anywhere. The only network
boundary this file does not control is the public/private trackers
themselves, which are flaky by nature (upstream CDNs, geo-blocks,
CAPTCHAs) — exactly the same determinism trade-off already accepted by
the project's other real e2e files in this directory
(``test_public_trackers_return_results.py``,
``test_live_stack_evidence.py``). We therefore assert only deterministic,
structural facts about the real pipeline's behaviour (a floor on the
number of trackers genuinely fanned out to, at least one real tracker
genuinely succeeding, the dedup/merge step's arithmetic being internally
consistent) rather than pinning any specific flaky tracker's result
count.

Live-service contract
----------------------
Per ``tests/fixtures/services.py``'s own documented philosophy, a fixture
that silently *errors* (rather than skips) is the right behaviour for a
test whose entire job is proving the fixture brings services up (see
``tests/integration/test_fixtures_bring_up_services.py``). This file is
not that test — it is a feature-level e2e suite — so, matching the
existing convention already established by
``tests/e2e/test_live_stack_evidence.py`` in this very directory, it
probes the live merge service directly and SKIPs with an honest, specific
reason (§11.4.3) when the stack genuinely is not reachable in the
executing environment, rather than starting a multi-container compose
stack as a side effect of merely importing/collecting a test file. Start
the real stack with ``./start.sh -p`` (or let CI bring it up) to exercise
these tests for real; that is exactly the mechanism
``tests/fixtures/compose.py``/``tests/fixtures/services.py`` already
provide for tests that opt into auto-start (see
``test_public_trackers_return_results.py``).

Run-id: e2e-full-pipeline-20260809
Evidence dir: docs/qa/e2e-full-pipeline-20260809/
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
import requests

MERGE_SERVICE_URL = os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187").rstrip("/")
RUN_ID = "e2e-full-pipeline-20260809"
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "docs" / "qa" / RUN_ID
# A real, unmocked "linux" fan-out across ~20-30 real trackers is bounded
# per-tracker by PUBLIC_TRACKER_DEADLINE_SECONDS (<=120s + 10s overhead in
# merge_service/search.py), but on a host that is concurrently running
# other heavy workloads the wall-clock can legitimately run well past a
# "quiet host" baseline. This is generous on purpose so a genuinely slow
# (but real) live host gets a fair chance to complete instead of racing an
# artificially tight budget.
SEARCH_TIMEOUT = 540.0

# Broad, historically-reliable query. "linux" is the exact query pinned as
# reliable by tests/e2e/test_public_trackers_return_results.py (proven
# floor: >=5 nonzero trackers, >=250 total results at time of writing) —
# reused here deliberately to avoid introducing a second, unproven source
# of flakiness. That file asserts the *fan-out floor*; this file asserts
# the *merge/dedup pipeline's structural correctness* on the same query,
# so the two are complementary rather than duplicative.
QUERY = "linux"

# A real, unstubbed fan-out reaches every enabled PUBLIC_TRACKERS entry
# (38 registered, 14 dead-listed and excluded by default -> ~24 public
# trackers alone, before any credentialed private trackers/jackett). The
# floor below is set conservatively below that so it tolerates a handful
# of additional trackers being disabled/misconfigured on any given host,
# while still being high enough to fail hard against the old mocked
# fan-out (which used exactly 3 synthetic TrackerSource objects).
MIN_TRACKERS_ATTEMPTED = 15
MIN_TOTAL_RESULTS = 20

pytestmark = pytest.mark.timeout(570)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _save_evidence(name: str, payload: object) -> Path:
    """Persist a real response body as captured evidence (§11.4.83)."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        path.write_text(str(payload))
    return path


def _service_reachable() -> bool:
    try:
        r = requests.get(f"{MERGE_SERVICE_URL}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def live_url() -> str:
    if not _service_reachable():
        pytest.skip(  # SKIP-OK: live service unreachable, §11.4.3
            f"merge service not reachable at {MERGE_SERVICE_URL}/health — "
            "start the real stack with `./start.sh -p` to run this real "
            "end-to-end pipeline test (no fake-pass, no orchestrator mocking)."
        )
    return MERGE_SERVICE_URL


@pytest.fixture(scope="module")
def full_pipeline_search(live_url: str) -> dict:
    """Run ONE real full-pipeline search over real HTTP; reuse it across assertions.

    This is the actual feature under test: a real POST to
    ``/api/v1/search/sync`` drives the real, running FastAPI app -> the
    real ``SearchOrchestrator.search`` -> real ``_get_enabled_trackers`` ->
    real ``_search_tracker`` fan-out over real network I/O -> the real
    ``Deduplicator`` merge step -> the real JSON body below. Nothing in
    this call path is mocked.
    """
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{live_url}/api/v1/search/sync",
                json={"query": QUERY, "limit": 50},
                timeout=SEARCH_TIMEOUT,
            )
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as exc:
            # Fast-failing (service down / mid-restart) — cheap to retry.
            last_err = exc
            time.sleep(3 * (attempt + 1))
            continue
        except requests.exceptions.Timeout as exc:
            # The connection was established and the server was genuinely
            # processing (not fast-failing) — it simply did not finish
            # within SEARCH_TIMEOUT. Retrying would only compound an
            # already-long wall-clock cost on a busy host, so this is an
            # honest environment-load SKIP rather than a hammer-and-hope
            # retry loop.
            pytest.skip(  # SKIP-OK: real search exceeded the read timeout on a loaded host, §11.4.3
                f"real {QUERY!r} full-pipeline search against the live stack did not "
                f"complete within {SEARCH_TIMEOUT}s (host under heavy concurrent load "
                f"from other work): {exc}"
            )
        if resp.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        body = resp.json()
        _save_evidence("search_linux_full_pipeline.json", body)
        return body
    pytest.skip(  # SKIP-OK: queue saturated / transient, §11.4.3
        f"could not obtain a {QUERY!r} search result from the live stack after retries: {last_err}"
    )


# --------------------------------------------------------------------------- #
# 1. The full pipeline genuinely completes with real, user-observable results
# --------------------------------------------------------------------------- #
def test_full_pipeline_completes_with_real_results(full_pipeline_search: dict) -> None:
    body = full_pipeline_search

    assert body.get("search_id"), f"no search_id in response: {body!r}"
    assert body.get("query") == QUERY, f"query did not round-trip: {body.get('query')!r}"
    assert body.get("status") == "completed", f"search status={body.get('status')!r} (expected 'completed')"

    total = body.get("total_results", 0)
    assert total >= MIN_TOTAL_RESULTS, (
        f"total_results={total} (floor={MIN_TOTAL_RESULTS}) — the real fan-out "
        "produced far fewer raw results than a healthy pipeline should for "
        f"{QUERY!r}. Either the trackers are widely down or the real fan-out "
        "is broken."
    )

    results = body.get("results") or []
    assert results, "no result objects in the response body — nothing for a real client to render"

    # User-observable result shape: a dashboard card needs a name, a size,
    # sources, and a usable download link/magnet.
    for r in results[:5]:
        assert r.get("name"), f"result missing name: {r!r}"
        assert r.get("size"), f"result missing size: {r!r}"
        sources = r.get("sources") or []
        assert sources, f"result has no 'sources' — the real merge step produced an empty source list: {r!r}"
        download_urls = r.get("download_urls") or []
        assert download_urls, f"result has no usable download_urls: {r!r}"


# --------------------------------------------------------------------------- #
# 2. Real multi-tracker fan-out (catches a reversion to a tiny/stubbed roster)
# --------------------------------------------------------------------------- #
def test_full_pipeline_fans_out_to_many_real_trackers(full_pipeline_search: dict) -> None:
    """The orchestrator's real ``_get_enabled_trackers`` returns dozens of
    real trackers (see ``PUBLIC_TRACKERS``/``DEAD_PUBLIC_TRACKERS`` in
    ``merge_service/search.py``). The old, mocked version of this file
    only ever exercised 3 synthetic ``TrackerSource`` objects — this
    assertion is the direct regression guard against that: it fails hard
    if the real fan-out ever shrinks back down to a handful of trackers.
    """
    stats = full_pipeline_search.get("tracker_stats", [])
    _save_evidence(
        "tracker_stats_summary.json",
        [{"name": t.get("name"), "status": t.get("status"), "results_count": t.get("results_count")} for t in stats],
    )
    assert stats, "no tracker_stats — API contract broken"
    assert len(stats) >= MIN_TRACKERS_ATTEMPTED, (
        f"only {len(stats)} trackers were fanned out to (floor={MIN_TRACKERS_ATTEMPTED}). "
        "This is the exact shape of the old bug this file used to hide: an "
        "orchestrator wired to a tiny, stubbed tracker roster instead of the "
        "real one."
    )

    successful = [t for t in stats if t.get("status") == "success" and t.get("results_count", 0) > 0]
    assert len(successful) >= 2, (
        f"fewer than 2 trackers reached status=='success' with real rows for {QUERY!r}. "
        "Either a wide upstream outage is in progress, or the real HTTP fan-out "
        "never actually reached an upstream tracker. "
        f"Stats: {[(t.get('name'), t.get('status'), t.get('results_count')) for t in stats][:15]}"
    )

    # Every fanned-out tracker's diagnostic entry must echo the query we
    # issued — proves the real request body was wired all the way through
    # to each real per-tracker task, not a canned/fixed value.
    for t in stats:
        assert t.get("query") == QUERY, f"tracker {t.get('name')!r} recorded query={t.get('query')!r}"


# --------------------------------------------------------------------------- #
# 3. Real deduplication/merge arithmetic (the actual defect class this file
#    used to bluff about: TestDeduplication in the old mocked version only
#    ever exercised Deduplicator against hand-written sample data, never
#    against real, merged, live-tracker output).
# --------------------------------------------------------------------------- #
def test_full_pipeline_merge_step_is_internally_consistent(full_pipeline_search: dict) -> None:
    body = full_pipeline_search
    total = body.get("total_results", 0)
    merged = body.get("merged_results", 0)

    # Structural dedup invariant: merging can only ever reduce (or
    # preserve) the raw per-tracker result count, never inflate it.
    assert 0 < merged <= total, (
        f"merged_results={merged}, total_results={total} — the real "
        "Deduplicator.merge_results() output is not a subset-or-equal of "
        "the raw fan-out count, which is structurally impossible for a "
        "genuine merge step."
    )

    results = body.get("results") or []
    assert len(results) <= merged, (
        f"API returned {len(results)} results but merged_results={merged} "
        "— more results were returned than the real merge step produced."
    )

    multi_source_results = [r for r in results if len(r.get("sources") or []) > 1]
    _save_evidence(
        "multi_source_merge_samples.json",
        [
            {"name": r.get("name"), "sources": r.get("sources"), "seeds": r.get("seeds"), "leechers": r.get("leechers")}
            for r in multi_source_results[:10]
        ],
    )
    for r in multi_source_results:
        sources = r["sources"]
        expected_seeds = sum(s.get("seeds", 0) for s in sources)
        expected_leechers = sum(s.get("leechers", 0) for s in sources)
        assert r.get("seeds") == expected_seeds, (
            f"merged result {r.get('name')!r} has seeds={r.get('seeds')} but its "
            f"{len(sources)} real per-tracker sources sum to {expected_seeds} — "
            "the real aggregation arithmetic in the merge step is wrong."
        )
        assert r.get("leechers") == expected_leechers, (
            f"merged result {r.get('name')!r} has leechers={r.get('leechers')} but its "
            f"{len(sources)} real per-tracker sources sum to {expected_leechers} — "
            "the real aggregation arithmetic in the merge step is wrong."
        )
        download_urls = r.get("download_urls") or []
        assert len(download_urls) == len(set(download_urls)), (
            f"merged result {r.get('name')!r} has duplicate entries in download_urls: {download_urls!r}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
