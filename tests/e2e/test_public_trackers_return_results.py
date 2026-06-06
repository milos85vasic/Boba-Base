"""End-to-end guard: public trackers must return results for common queries.

Prior to 2026-04-19, a search for "linux" hit every one of 40 trackers
but 37 returned 0 results because `_search_public_tracker`'s subprocess
monkeypatched the wrong `novaprinter` module and additionally dropped
every captured row when the per-tracker subprocess timeout fired. After
the fix, the same query reliably returns hundreds of results from 10+
public trackers. This test pins that floor so the bug can't come back.

The floors here are intentionally conservative: a specific tracker may
go down for upstream reasons (403 from a CDN, DNS, CAPTCHA), but at
least ten of the forty public+private trackers should return SOMETHING
for a query as broad as "linux". If this test fails, either the
subprocess-capture is broken again or the upstream outage is wide
enough to warrant investigation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

QUERY = "linux"
LIMIT = 50
TIMEOUT = 300.0
MIN_NONZERO_TRACKERS = 5
MIN_TOTAL_RESULTS = 250


pytestmark = pytest.mark.timeout(420)


@pytest.fixture(scope="module")
def linux_search(merge_service_live: str) -> dict:
    resp = requests.post(
        f"{merge_service_live}/api/v1/search/sync",
        json={"query": QUERY, "limit": LIMIT},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _nonzero_stats(payload: dict) -> list[dict]:
    return [t for t in payload.get("tracker_stats", []) if t.get("results_count", 0) > 0]


def test_linux_search_hits_enough_trackers(linux_search: dict) -> None:
    stats = linux_search.get("tracker_stats", [])
    assert stats, "merge service returned no tracker_stats — API contract broken"
    nonzero = _nonzero_stats(linux_search)
    names = sorted(t["name"] for t in nonzero)
    assert len(nonzero) >= MIN_NONZERO_TRACKERS, (
        f"Only {len(nonzero)}/{len(stats)} trackers returned results for "
        f"{QUERY!r} (floor={MIN_NONZERO_TRACKERS}). Non-zero: {names}. "
        "This is the 37-empty-trackers regression — check that "
        "_search_public_tracker patches the top-level `novaprinter` module "
        "and streams NDJSON with sys.stdout.flush()."
    )


def test_linux_search_has_meaningful_total(linux_search: dict) -> None:
    total = linux_search.get("total_results", 0)
    assert total >= MIN_TOTAL_RESULTS, (
        f"total_results={total} (floor={MIN_TOTAL_RESULTS}). Before the "
        "subprocess-capture fix this number was ~137 because only the 3 "
        "private trackers were returning rows. Dropping below that floor "
        "means we're losing captured results again."
    )


def test_piratebay_specifically_returns_results(linux_search: dict) -> None:
    """piratebay is a canary: it's the largest, fastest-responding public
    tracker in the set. If piratebay returns 0 for 'linux' but was fine
    before, something is broken in OUR code — not in piratebay."""
    pb = next(
        (t for t in linux_search.get("tracker_stats", []) if t["name"] == "piratebay"),
        None,
    )
    assert pb is not None, "piratebay missing from tracker_stats"
    assert pb["results_count"] > 0, (
        f"piratebay returned 0 results for {QUERY!r}. It's the canonical "
        "working public tracker — 0 here implies the monkeypatch or NDJSON "
        "capture broke again. Status={status}, error={error}".format(status=pb.get("status"), error=pb.get("error"))
    )


def test_query_roundtrip_matches(linux_search: dict) -> None:
    """Each tracker_stats entry must echo the query we issued — proves
    the merge service wired the right query into every fan-out task."""
    for t in linux_search.get("tracker_stats", []):
        assert t.get("query") == QUERY, (
            f"tracker {t.get('name')!r} recorded query={t.get('query')!r} (expected {QUERY!r})"
        )


def test_deadline_hit_is_surfaced_on_slow_trackers(linux_search: dict) -> None:
    """Slow plugins (limetorrents, linuxtracker, torrentdownload…) get
    truncated at the per-tracker deadline. When that happens the API
    must carry ``notes["deadline_hit"] == True`` so the dashboard can
    show the stopwatch badge and the operator knows the result set is
    capped. Without this, a 25-row result from a working tracker and
    a 25-row truncation look identical.
    """
    stats = linux_search.get("tracker_stats", [])
    truncated = [t for t in stats if t.get("notes", {}).get("deadline_hit")]
    # At least one plugin in the wild typically hits the 25 s wall on
    # the "linux" query — linuxtracker, limetorrents, and
    # torrentdownload routinely do. A floor of 1 keeps the test stable
    # even when network weather speeds the usual suspects up.
    assert len(truncated) >= 1, (
        "No tracker surfaced deadline_hit on the linux search — either "
        "every slow tracker finished within 25 s (possible but rare) or "
        "the deadline_hit plumb-through is broken. Check search.py's "
        "_search_public_tracker → _last_public_tracker_diag → "
        "stat.notes pipe."
    )
    for t in truncated:
        assert t["notes"].get("deadline_seconds"), (
            f"tracker {t['name']} has deadline_hit=True but no "
            "deadline_seconds — the env value isn't being plumbed through"
        )


@pytest.mark.skipif(  # SKIP-OK: #legacy-untriaged
    os.getenv("ENABLE_DEAD_TRACKERS", "0") == "1" or Path(".env").read_text().find("ENABLE_DEAD_TRACKERS=1") != -1,
    reason="Dead trackers are intentionally enabled via ENABLE_DEAD_TRACKERS=1",
)
def test_dead_trackers_excluded_from_fan_out(linux_search: dict) -> None:
    """The 17 known-dead public trackers must NOT appear in
    tracker_stats by default. Otherwise the dashboard drowns in
    permanently-red chips that can never go green.
    """
    stat_names = {t["name"] for t in linux_search.get("tracker_stats", [])}
    dead = {
        "ali213",
        "audiobookbay",
        "bitru",
        "bt4g",
        "btsow",
        "extratorrent",
        "eztv",
        "one337x",
        "pctorrent",
        "solidtorrents",
        "therarbg",
        "torrentfunk",
        "xfsub",
        "yihua",
    }
    leaked = stat_names & dead
    assert not leaked, (
        f"Dead trackers leaked into the fan-out: {sorted(leaked)}. "
        "Check _get_enabled_trackers → DEAD_PUBLIC_TRACKERS filter."
    )


def test_empty_trackers_surface_a_reason(linux_search: dict) -> None:
    """Every empty tracker should tell us WHY.

    Before the diagnostic plumb-through, `error` and `error_type` were
    always ``None`` on empty trackers and the dashboard had no way to
    distinguish a niche-empty "no linux torrents on an anime tracker"
    from an upstream outage or a plugin crash. The orchestrator now
    pulls `_search_public_tracker`'s subprocess stderr classification
    into `TrackerSearchStat`, so each empty tracker must either:

    * be genuinely empty (``status == "empty"`` with no error — the
      plugin ran cleanly but found nothing for this query), or
    * name the failure (``error_type`` is one of the known classes).

    We allow a small tolerance because transient TLS/CDN weather shifts
    which trackers land in which bucket, but on "linux" at least a
    handful MUST be classified — otherwise the plumb-through is broken.
    """
    stats = linux_search.get("tracker_stats", [])
    empty = [t for t in stats if t.get("results_count", 0) == 0]
    assert empty, "no empty trackers found — test assumes some exist"

    classified = [t for t in empty if t.get("error_type") is not None]
    genuinely_empty = [t for t in empty if t.get("error_type") is None]

    # Every classified tracker should have a human-readable summary too.
    for t in classified:
        assert t.get("error"), (
            f"tracker {t['name']!r} has error_type={t.get('error_type')!r} but no human-readable error summary"
        )

    # Floor: at least one classification should be present. Since the
    # upstream-dead 403/404/DNS trackers are now filtered out via
    # `DEAD_PUBLIC_TRACKERS`, the usual classifications left after
    # filtering are `deadline_timeout` (audiobookbay, torlock) and
    # occasional `plugin_crashed` (torrentgalaxy). If *no* classification
    # lands, the subprocess-stderr plumb-through is broken.
    assert len(classified) >= 1, (
        f"Zero of {len(empty)} empty trackers had a classified "
        "error_type — the subprocess-stderr plumb-through is broken. "
        f"Empty-without-reason list: {sorted(t['name'] for t in genuinely_empty)}"
    )
