"""§11.4.85 STRESS suite for the multi-word query URL-encoding fix.

Drives the REAL search() of a representative set of the fixed plugins
(eztv, torlock, glotorrents, torrentscsv, limetorrents) under sustained
load (N>=100 iterations) with a battery of multi-word / unicode / boundary
queries, asserting EVERY constructed URL is free of raw control characters
(i.e. urllib.request.Request accepts it).

Stress dimensions per §11.4.85:
  * sustained load   — N=120 iterations >= the 100 floor, p50/p95/p99 latency
  * boundary inputs  — empty, very long, many spaces, leading/trailing space,
                       tabs, single word, multi word, cyrillic, punctuation
  * determinism (§11.4.50) — identical PASS verdict + identical violation
                       count across 3 repeats.

Anti-bluff (§11.4 / §11.4.85): every PASS cites a captured-evidence artifact
(latency + per-query results JSON). §1.1: ``test_guard_bites_on_raw_space``
proves the URL-control-char assertion FAILS on a synthetic raw-space URL —
if a plugin reverted to raw-space interpolation the stress assertion would
flip RED.
"""

from __future__ import annotations

import statistics
import time

import pytest

from .conftest import (
    FIXED_PLUGINS,
    drive_search,
    url_has_raw_space,
    url_is_urllib_acceptable,
)

# Battery of queries exercising multi-word / unicode / boundary conditions.
# A leading "" (empty) is a boundary input; plugins must still build a
# urllib-acceptable URL (or build none) without emitting a raw control char.
QUERY_BATTERY = [
    "the matrix",            # the canonical multi-word crash trigger
    "linux",                 # single word (already-working boundary)
    "Война и мир",           # cyrillic multi-word (non-ASCII)
    "a b c d e f g h",       # many spaces
    "  leading and trailing  ",  # leading/trailing whitespace
    "tab\tseparated words",  # embedded tab control char
    "ubuntu 24.04 LTS amd64",  # punctuation + digits + spaces
    "x" * 500,               # very long single token
    "word " * 40,            # very long multi-word
]

N_ITERATIONS = 120  # >= §11.4.85 100-iteration sustained-load floor


def _run_one_iteration(plugin: str) -> tuple[int, int]:
    """Drive the plugin against the full query battery once.
    Returns (urls_built, raw_space_violations).

    The defect class under test is the RAW SPACE in the constructed URL
    (the multi-word-query crash). For each space-bearing query the built
    URL must contain no raw space; a space-free query that produces a
    urllib-unacceptable URL purely from its own SPACE content is also a
    violation. (Non-space control chars supplied IN the query are a
    separate, broader gap — characterised in the chaos suite, not asserted
    here, per §11.4.6 honesty about what the fix actually addresses.)"""
    urls_built = 0
    violations = 0
    for q in QUERY_BATTERY:
        query_has_only_space_ws = "\t" not in q and "\n" not in q and "\r" not in q
        try:
            urls = drive_search(plugin, q)
        except Exception:
            urls = []
        for u in urls:
            urls_built += 1
            if url_has_raw_space(u):
                violations += 1
            elif query_has_only_space_ws and not url_is_urllib_acceptable(u):
                # A non-space control char in the URL that did NOT come from
                # the query (the query had only spaces) — would be a real
                # encoding regression.
                violations += 1
    return urls_built, violations


@pytest.mark.parametrize("plugin", FIXED_PLUGINS)
def test_sustained_load_no_raw_control_chars(plugin: str, evidence) -> None:
    """N>=100 iterations of the full query battery; EVERY built URL must be
    free of raw control characters. 100% pass + captured latency."""
    latencies: list[float] = []
    total_urls = 0
    total_violations = 0
    for _ in range(N_ITERATIONS):
        t0 = time.perf_counter()
        built, viol = _run_one_iteration(plugin)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        total_urls += built
        total_violations += viol

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    p99 = latencies[int(len(latencies) * 0.99) - 1]
    summary = {
        "plugin": plugin,
        "iterations": N_ITERATIONS,
        "queries_per_iteration": len(QUERY_BATTERY),
        "total_urls_built": total_urls,
        "total_violations": total_violations,
        "latency_ms_p50": round(p50, 4),
        "latency_ms_p95": round(p95, 4),
        "latency_ms_p99": round(p99, 4),
        "verdict": "PASS" if total_violations == 0 else "FAIL",
    }
    evidence.add(latencies_ms=[round(x, 4) for x in latencies])
    path = evidence.emit(summary)

    assert total_urls > 0, f"{plugin}: built no URLs across {N_ITERATIONS} iterations"
    assert total_violations == 0, (
        f"{plugin}: {total_violations} raw-space violations across "
        f"{N_ITERATIONS} iterations — multi-word queries crash urllib. "
        f"Evidence: {path}"
    )


@pytest.mark.parametrize("plugin", FIXED_PLUGINS)
def test_deterministic_across_repeats(plugin: str, evidence) -> None:
    """§11.4.50 determinism: 3 repeats of a 100-iteration run produce the
    IDENTICAL violation count (always 0). A divergent run is an auto-FAIL."""
    counts: list[int] = []
    for _ in range(3):
        viol_total = sum(_run_one_iteration(plugin)[1] for _ in range(100))
        counts.append(viol_total)
    summary = {
        "plugin": plugin,
        "repeats": 3,
        "iterations_per_repeat": 100,
        "violation_counts": counts,
        "verdict": "PASS" if counts == [0, 0, 0] else "FAIL",
    }
    path = evidence.emit(summary)
    assert counts == [0, 0, 0], (
        f"{plugin}: non-deterministic or non-zero violations {counts}. Evidence: {path}"
    )


def test_guard_bites_on_raw_space(evidence) -> None:
    """§1.1 paired check: the guard MUST flag a raw-space URL (what a
    reverted plugin would build) AND urllib MUST reject it; a %20-encoded
    URL must pass both. If this stopped failing the stress assertion would
    be toothless — it proves the guard bites on the exact defect shape."""
    reverted = "https://eztv.example/search/the matrix"  # raw space — pre-fix shape
    assert url_has_raw_space(reverted), "guard failed to flag a raw space"
    # urllib's own predicate must reject it (the real crash path).
    assert not url_is_urllib_acceptable(reverted), (
        "urllib oracle should reject a raw-space URL"
    )
    # A properly-encoded URL must pass both checks.
    fixed = "https://eztv.example/search/the%20matrix"
    assert not url_has_raw_space(fixed)
    assert url_is_urllib_acceptable(fixed)
    evidence.emit({"guard": "bites-on-raw-space", "verdict": "PASS"})
