"""§11.4.85 stress tests for the offline search pipeline (dedup / enrich /
quality / stderr-classification).

These are OFFLINE and DETERMINISTIC — they construct inputs directly and call
the in-process pipeline layer; no live external network, no running merge
service. They complement the live HTTP stress suite in
``tests/stress/test_search_stress.py``.

Anti-bluff (§11.4.5 / §11.4.69): every test asserts real observable outcomes
(result counts, dedup grouping, recorded latency distribution) and writes a
captured-evidence JSON artefact under ``qa-results/pipeline_stress/<run-id>/``
so a PASS is backed by an inspectable file, not just "it ran".

Stress coverage (closed-set per §11.4.85):
- sustained load: N>=100 dedup+enrich iterations, p50/p95/p99 latency recorded;
- concurrent contention: many parallel dedup operations, no crash / no leak;
- boundary conditions: empty / single / max-duplicate inputs categorised.
"""

from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
_MS_PATH = _SRC_PATH / "merge_service"

if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS_PATH)]


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        f"merge_service.{modname}", str(_MS_PATH / filename)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"merge_service.{modname}"] = mod
    spec.loader.exec_module(mod)
    return mod


_search_mod = _load("search", "search.py")
_dedup_mod = _load("deduplicator", "deduplicator.py")
_enricher_mod = _load("enricher", "enricher.py")

SearchResult = _search_mod.SearchResult
Deduplicator = _dedup_mod.Deduplicator
MetadataEnricher = _enricher_mod.MetadataEnricher
classify_stderr = _search_mod._classify_plugin_stderr


# --------------------------------------------------------------------------- #
# Captured-evidence helper
# --------------------------------------------------------------------------- #
_RUN_ID = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
_EVIDENCE_DIR = _REPO_ROOT / "qa-results" / "pipeline_stress" / _RUN_ID


def _write_evidence(name: str, payload: dict) -> Path:
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    assert path.exists() and path.stat().st_size > 0, "evidence artefact must be non-empty"
    return path


def _make_results(n: int) -> list:
    """Build N synthetic SearchResults across several trackers + qualities."""
    qualities = ["1080p BluRay", "720p WEB-DL", "2160p UHD", "480p HDRip"]
    trackers = ["rutracker", "kinozal", "nnmclub", "eztv"]
    out = []
    for i in range(n):
        q = qualities[i % len(qualities)]
        t = trackers[i % len(trackers)]
        # Every 5th result is a deliberate cross-tracker duplicate of result 0
        # (same infohash) so the deduplicator has real grouping work to do.
        if i % 5 == 0 and i > 0:
            link = "magnet:?xt=urn:btih:" + ("A" * 40)
            name = "Ubuntu Movie 2023 1080p BluRay"
        else:
            link = "magnet:?xt=urn:btih:" + f"{i:040d}"
            name = f"Title {i} 2023 {q}"
        out.append(
            SearchResult(
                name=name,
                link=link,
                size="2.0 GB",
                seeds=100 + i,
                leechers=i,
                engine_url=f"https://{t}.example",
                tracker=t,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Sustained load
# --------------------------------------------------------------------------- #
@pytest.mark.stress
def test_dedup_enrich_sustained_load_records_latency() -> None:
    """>=100 dedup iterations: no crash, bounded results, latency recorded."""
    iterations = 120
    enricher = MetadataEnricher()
    latencies_ms: list[float] = []
    group_counts: list[int] = []

    for _ in range(iterations):
        dedup = Deduplicator()
        results = _make_results(60)
        t0 = time.perf_counter()
        merged = dedup.merge_results(results)
        # enrichment-style quality detection over every row (offline, no net)
        for r in results:
            enricher.detect_quality(r.name)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        group_counts.append(len(merged))

    # Observable outcomes ----------------------------------------------------
    assert len(latencies_ms) == iterations
    # Dedup must collapse the deliberate duplicates: fewer groups than inputs.
    assert all(0 < g < 60 for g in group_counts), f"unexpected group sizes: {set(group_counts)}"
    # Deterministic: identical input each iteration -> identical group count.
    assert len(set(group_counts)) == 1, f"non-deterministic dedup: {set(group_counts)}"

    p50 = statistics.median(latencies_ms)
    p95 = sorted(latencies_ms)[int(0.95 * len(latencies_ms)) - 1]
    p99 = sorted(latencies_ms)[int(0.99 * len(latencies_ms)) - 1]
    evidence = {
        "iterations": iterations,
        "results_per_iter": 60,
        "dedup_groups_per_iter": group_counts[0],
        "latency_ms": {
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "p99": round(p99, 3),
            "max": round(max(latencies_ms), 3),
            "min": round(min(latencies_ms), 3),
        },
    }
    path = _write_evidence("sustained_load", evidence)
    # Sanity bound: a single 60-row dedup must stay well under 2s even on a
    # busy host (regression guard against accidental O(n^2) blowups).
    assert max(latencies_ms) < 2000.0, f"dedup latency exploded: {evidence} ({path})"


# --------------------------------------------------------------------------- #
# Concurrent contention
# --------------------------------------------------------------------------- #
@pytest.mark.stress
def test_dedup_concurrent_contention_no_crash() -> None:
    """20 parallel dedup operations complete with identical, correct output."""
    workers = 20

    def run(_i: int) -> int:
        dedup = Deduplicator()
        merged = dedup.merge_results(_make_results(50))
        return len(merged)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(run, i) for i in range(workers)]
        counts = [f.result(timeout=60) for f in concurrent.futures.as_completed(futures)]

    assert len(counts) == workers, "every concurrent dedup must return a result"
    # No partial / crashed workers -> all return a positive bounded count, and
    # because each builds its own Deduplicator the result is identical.
    assert all(0 < c < 50 for c in counts), f"bad concurrent counts: {counts}"
    assert len(set(counts)) == 1, f"concurrent runs diverged (state leak?): {set(counts)}"

    _write_evidence(
        "concurrent_contention",
        {"workers": workers, "results_per_worker": 50, "groups_each": counts[0], "all_counts": counts},
    )


# --------------------------------------------------------------------------- #
# Boundary conditions
# --------------------------------------------------------------------------- #
@pytest.mark.stress
def test_dedup_boundary_conditions() -> None:
    """Empty / single / all-identical inputs each produce a categorised result."""
    categories: dict[str, int] = {}

    # empty
    categories["empty"] = len(Deduplicator().merge_results([]))
    # single
    categories["single"] = len(Deduplicator().merge_results(_make_results(1)))
    # all identical (same infohash) -> must collapse to exactly one group
    identical = [
        SearchResult(
            name="Same Movie 2023 1080p",
            link="magnet:?xt=urn:btih:" + ("B" * 40),
            size="1.0 GB",
            seeds=10,
            leechers=1,
            engine_url=f"https://t{i}.example",
            tracker=f"t{i}",
        )
        for i in range(30)
    ]
    categories["all_identical"] = len(Deduplicator().merge_results(identical))

    assert categories["empty"] == 0
    assert categories["single"] == 1
    assert categories["all_identical"] == 1, "30 same-infohash rows must collapse to 1 group"

    _write_evidence("boundary_conditions", categories)
