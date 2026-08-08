"""Contract test for the ``tracker_stats`` field on SearchResponse.

Verifies, against the REAL, running merge-search service — no mocking
of ``SearchOrchestrator`` or any of its internals anywhere in this
file — that:

*   ``POST /api/v1/search/sync`` (blocking) returns ``tracker_stats``
    as a list of dicts whose shape matches the 15-field
    ``TrackerSearchStat.to_dict()`` contract;
*   ``GET /api/v1/search/{id}`` (the follow-up read) echoes the same
    shape for the same search;
*   ``POST /api/v1/search`` (the non-blocking kickoff) returns the
    same shape immediately, for the same set of trackers the live
    service actually has enabled.

Why this replaces the old file
-------------------------------
This file used to ``monkeypatch.setattr(SearchOrchestrator,
"_get_enabled_trackers", ...)`` and
``monkeypatch.setattr(SearchOrchestrator, "_search_tracker", ...)`` —
mocking the exact orchestrator internals a *contract* test is supposed
to validate for real, in direct violation of CLAUDE.md / constitution
§11.4.27 ("No fakes beyond unit tests — mocks/stubs/placeholders are
allowed to exist ONLY in Unit tests! All other test types MUST
interact with real fully implemented System!"). That mocked-shape
coverage was still valuable, so it was relocated (not deleted) to
``tests/unit/test_tracker_stats_shape.py``, where mocking is
permitted. This file is the real replacement: every assertion here
runs against a real HTTP response from a real running process.

Reachability, not auto-start
-----------------------------
``tests/fixtures/services.py`` (``merge_service_live``) and
``tests/fixtures/compose.py`` (``compose_up``) prove real-service
fixtures are viable in this repo, and they were reviewed before
writing this file. They were deliberately NOT used here: those
fixtures *start* the docker-compose stack (``podman compose up -d``)
as a side effect of merely requesting the fixture, and they *error*
(not skip) when the stack cannot be brought up — appropriate for
infra-focused tests like
``tests/integration/test_fixtures_bring_up_services.py``, but wrong
for a contract test, which should be a lightweight, side-effect-free
consumer of an already-running service. Instead this file uses the
same "probe /health, skip on failure" idiom already established in
this repository's own real-HTTP suites (see
``tests/e2e/test_live_stack_evidence.py`` and
``tests/contract/test_crossapp_theme_contract.py``): if the live
service isn't already reachable (e.g. ``./start.sh`` hasn't been run
in this environment), every test SKIPs with an honest, specific
reason — never a silent pass, never a fake assertion.
"""

from __future__ import annotations

import os
import time

import pytest
import requests

MERGE_SERVICE_URL = os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187").rstrip("/")
QUERY = os.environ.get("TRACKER_STATS_CONTRACT_QUERY", "linux")
SEARCH_TIMEOUT = 300.0

pytestmark = pytest.mark.timeout(420)

REQUIRED_FIELDS = {
    "name",
    "tracker_url",
    "status",
    "results_count",
    "started_at",
    "completed_at",
    "duration_ms",
    "error",
    "error_type",
    "authenticated",
    "attempt",
    "http_status",
    "category",
    "query",
    "notes",
}

VALID_STATUSES = {"pending", "running", "success", "empty", "error", "timeout", "cancelled"}


def _service_reachable() -> bool:
    try:
        resp = requests.get(f"{MERGE_SERVICE_URL}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def live_url() -> str:
    if not _service_reachable():
        pytest.skip(  # SKIP-OK: live merge search service unreachable, §11.4.3
            f"merge search service unreachable at {MERGE_SERVICE_URL}/health — "
            "run ./start.sh -p to bring up qbittorrent-proxy (or set "
            "MERGE_SERVICE_URL) before running the real tracker_stats "
            "contract test. No fake-pass: this test does not mock "
            "SearchOrchestrator, so it has no way to validate the real "
            "response shape without a real running service."
        )
    return MERGE_SERVICE_URL


@pytest.fixture(scope="module")
def synced_search(live_url: str) -> dict:
    """One real, blocking search, reused by every assertion in this
    module so the ~seconds-to-minutes-long real fan-out is only paid
    once per test run (mirrors ``tests/fixtures/live_search.py`` and
    ``tests/e2e/test_public_trackers_return_results.py``)."""
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{live_url}/api/v1/search/sync",
                json={"query": QUERY, "limit": 5},
                timeout=SEARCH_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 - retry on transient network errors
            last_err = exc
            time.sleep(3 * (attempt + 1))
            continue
        if resp.status_code == 429:
            # Queue full (MAX_CONCURRENT_SEARCHES) — back off and retry.
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    pytest.skip(  # SKIP-OK: transient / queue-saturated, §11.4.3
        f"could not obtain a real /api/v1/search/sync result from {live_url} "
        f"after retries: {last_err}"
    )


def _assert_stat_shape(stat: dict) -> None:
    assert isinstance(stat, dict), f"tracker_stats entry is not a dict: {stat!r}"
    assert set(stat.keys()) == REQUIRED_FIELDS, (
        f"tracker_stats entry keys {sorted(stat.keys())} do not match the "
        f"contracted 15-field TrackerSearchStat shape {sorted(REQUIRED_FIELDS)}"
    )
    assert stat["status"] in VALID_STATUSES, f"unexpected status {stat['status']!r} (real response: {stat!r})"
    assert isinstance(stat["name"], str) and stat["name"], f"tracker name must be a non-empty string: {stat!r}"


def test_search_sync_returns_tracker_stats_with_required_fields(synced_search: dict) -> None:
    assert "tracker_stats" in synced_search, "real SearchResponse body missing tracker_stats field"
    stats = synced_search["tracker_stats"]
    assert isinstance(stats, list)
    assert stats, "live merge-search service returned zero tracker_stats entries — no trackers enabled?"
    for stat in stats:
        _assert_stat_shape(stat)


def test_get_search_echoes_same_shape(live_url: str, synced_search: dict) -> None:
    search_id = synced_search.get("search_id")
    assert search_id, f"real sync search response missing search_id: {synced_search!r}"

    resp = requests.get(f"{live_url}/api/v1/search/{search_id}", timeout=30)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "tracker_stats" in body
    fstats = body["tracker_stats"]
    assert isinstance(fstats, list)
    assert fstats, "follow-up GET /api/v1/search/{id} returned zero tracker_stats entries"
    for stat in fstats:
        _assert_stat_shape(stat)


def test_search_kickoff_returns_tracker_stats_for_every_enabled_tracker(
    live_url: str, synced_search: dict
) -> None:
    """The non-blocking ``POST /api/v1/search`` returns immediately —
    each entry's ``status`` will be ``pending``/``running``/etc
    depending on how much of the background fan-out has executed by
    the time the response serialises. The contract pins shape + that
    the same real, live-configured set of enabled trackers shows up
    as the blocking sync search already proved is enabled (both calls
    hit the same running orchestrator instance's ``_get_enabled_trackers()``)."""
    resp = requests.post(
        f"{live_url}/api/v1/search",
        json={"query": QUERY, "limit": 5},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "tracker_stats" in body
    stats = body["tracker_stats"]
    assert isinstance(stats, list)
    assert stats, "kickoff search returned zero tracker_stats entries"
    for stat in stats:
        _assert_stat_shape(stat)

    kickoff_names = {s["name"] for s in stats}
    synced_names = {s["name"] for s in synced_search["tracker_stats"]}
    assert kickoff_names == synced_names, (
        f"kickoff search's enabled trackers {sorted(kickoff_names)} != the sync "
        f"search's {sorted(synced_names)} — the live service's enabled-tracker "
        "set is not stable between two real calls to the same process"
    )
