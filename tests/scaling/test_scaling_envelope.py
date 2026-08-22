"""Scaling-class envelope tests for boba (BOB-109 / §11.4.27).

WHY THIS FILE EXISTS ALONGSIDE ``test_boba_scaling.py``
------------------------------------------------------
``test_boba_scaling.py`` landed via commit 12b439b, whose own message
records it as *"recover wave-6 subagent partial output before dispatch
termination"*. Two of its axes assert a **tautology**: they compute
``other = N - accepted - rate_limited - timed_out`` and then assert
``accepted + rate_limited + timed_out + other == N``, which reduces to
``N == N``. Measured 2026-08-21: pointing its fan-out axis at a CLOSED
port and invoking it directly still PASSES (see
``docs/qa/BOB-109/red_tautology_proof.txt``). That is §11.4.266
``green-but-broken`` coverage-theater, so it cannot be cited as the
scaling coverage BOB-109 asks for.

THE SCALING QUESTION THIS FILE ACTUALLY ASKS
--------------------------------------------
The merge service fans one user query out across three trackers in
parallel and then DEDUPLICATES the union. The dominant scaling axis is
therefore not "more users" (the rate limiter binds long before the
backend does — see below) but **result-set size**: as trackers return
more rows, what is the cost curve of the merge step?

``Deduplicator.merge_results`` pops a seed and rescans every remaining
candidate (``deduplicator.py`` ``while pending:``), so all-distinct
input — the worst and most realistic case for a broad query — is
**quadratic by construction**. Asserting "sub-quadratic" would be a
§11.4.201(1) false-positive refusal against correct code. This suite
therefore pins the *complexity class* and fails only on a **regression
past quadratic** (e.g. an accidental O(n^3) comparator).

THE RATE LIMITER IS TREATED AS A SUBJECT, NOT IGNORED, NOT FOUGHT
-----------------------------------------------------------------
Measured live 2026-08-21 on :7187 — ``/`` reports
``x-ratelimit-limit: 60``, ``/api/v1/theme/stream`` reports ``120``;
:7189 ``/healthz`` reports no limit headers at all. Source of truth
``api/rate_limit.py::DEFAULT_LIMITS`` declares
``search=10/minute``, ``dashboard=60/minute``, ``sse_stream=5/minute``,
``default=120/minute``, and ``.env`` sets no ``RATE_LIMIT_*`` override.

Consequences, decided deliberately:

* Driving ``/api/v1/search`` past N=10 measures the LIMITER, not the
  fan-out. So concurrency scale-out is measured on the **limiter-free**
  plane (:7189) and the limiter is characterised **separately**.
* The limiter is a per-IP resource SHARED with every other agent on
  this host. Driving it to exhaustion to "discover" its ceiling would
  cross-contaminate their measurements (§11.4.119 single-resource
  owner). This suite therefore reads the advertised ceiling from the
  ``x-ratelimit-*`` response headers using ONE request per class —
  non-destructive, and it still detects a silently-disabled or
  silently-unwired limiter.

§11.4.14 cleanup: every executor is a context manager (joins on all
exit paths) and every HTTP response is closed in a ``finally``; a
session-scoped finaliser asserts no scaling-owned executor outlives the
run. §11.4.69 ``feature_class = scaling`` — every PASS writes a
machine-readable artifact under ``docs/qa/BOB-109/``.
"""

from __future__ import annotations

import ast
import concurrent.futures as cf
import importlib.util
import itertools
import json
import math
import os
import socket
import statistics
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# The ONE directory whose contents are committed as evidence. A
# mutation/experiment run MUST redirect EVIDENCE_DIR away from it — see
# the guard in _emit() (§11.4.84 applied at the evidence layer).
COMMITTED_EVIDENCE_DIR = REPO_ROOT / "docs" / "qa" / "BOB-109"
EVIDENCE_DIR = COMMITTED_EVIDENCE_DIR
# Every artifact from one pytest process carries the same run id, so a
# reader can tell which rows came from the same run and spot a file that
# was left behind by an earlier one (last-write-wins is otherwise
# invisible).
def _process_run_id() -> str:
    """One run id per PROCESS, not per module.

    This used to be computed at each module's import time, so a pytest
    session importing both scaling modules a second apart stamped TWO
    different run ids into one corpus — and the doc could only cite one
    of them. Earlier runs passed only because both imports happened to
    land inside the same second; the checker caught it the first time
    they did not. The id is therefore cached in the environment, keyed
    to this PID so a value inherited from a parent process is never
    reused.
    """
    pid = os.getpid()
    cached = os.environ.get("BOBA_SCALING_RUN_ID", "")
    if cached.endswith(f"-pid{pid}"):
        return cached
    run_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-pid{pid}"
    os.environ["BOBA_SCALING_RUN_ID"] = run_id
    return run_id


RUN_ID = _process_run_id()
MERGE_URL = "http://127.0.0.1:7187"
JACKETT_BOBA_URL = "http://127.0.0.1:7189"

# --- host-safety envelope (§12.6 memory / §12.12 threads) -------------------
# The suite refuses to scale rather than wedge a workstation that other
# agents are sharing. These are ceilings on THIS suite, not host limits.
MAX_WORKERS_CAP = 16          # 8-core host; stay inside 30-40% (CLAUDE.md)
MEM_USED_PCT_CEILING = 60     # §12.6
MIN_THREAD_HEADROOM = 2048    # §12.12
# Timing-derived metrics are only trustworthy on a quiet host; see
# _require_quiescent_host() for the measurements behind this number.
QUIESCENT_LOAD_PER_CPU = 0.75


def _mem_used_pct() -> float:
    vals: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, _, rest = line.partition(":")
        vals[k] = int(rest.split()[0])
    total = vals["MemTotal"]
    avail = vals.get("MemAvailable", vals["MemFree"])
    return (total - avail) * 100.0 / total


def _thread_headroom() -> int:
    import resource

    soft, _hard = resource.getrlimit(resource.RLIMIT_NPROC)
    if soft in (resource.RLIM_INFINITY, -1):
        return 1 << 30
    live = len(list((Path("/proc").glob("[0-9]*/task/[0-9]*"))))
    return soft - live


def _host_safety_reading() -> dict:
    return {
        "mem_used_pct": round(_mem_used_pct(), 2),
        "mem_used_pct_ceiling": MEM_USED_PCT_CEILING,
        "thread_headroom": _thread_headroom(),
        "thread_headroom_floor": MIN_THREAD_HEADROOM,
        "cpu_count": os.cpu_count(),
        "loadavg_1m": round(os.getloadavg()[0], 2),
        "max_workers_cap": MAX_WORKERS_CAP,
    }


def _require_host_headroom() -> dict:
    """Refuse to scale when the host cannot afford it (§12.6 / §12.12).

    A refusal prints its RESOLVED evidence (§11.4.201(5)) so a skip is
    never mistaken for a pass.
    """
    reading = _host_safety_reading()
    if reading["mem_used_pct"] >= MEM_USED_PCT_CEILING:
        pytest.skip(
            f"SKIP-OK BOB-109 host-safety §12.6: memory used "
            f"{reading['mem_used_pct']}% >= {MEM_USED_PCT_CEILING}% ceiling"
        )
    if reading["thread_headroom"] < MIN_THREAD_HEADROOM:
        pytest.skip(
            f"SKIP-OK BOB-109 host-safety §12.12: thread headroom "
            f"{reading['thread_headroom']} < {MIN_THREAD_HEADROOM} floor"
        )
    return reading


def _is_quiescent() -> tuple[bool, dict]:
    """(quiescent?, reading) without skipping — for callers that want to
    drop ONE timing-derived assertion rather than the whole test."""
    reading = _host_safety_reading()
    cpus = reading["cpu_count"] or 1
    ratio = reading["loadavg_1m"] / cpus
    reading["load_per_cpu"] = round(ratio, 3)
    reading["load_per_cpu_ceiling"] = QUIESCENT_LOAD_PER_CPU
    return ratio <= QUIESCENT_LOAD_PER_CPU, reading


def _require_quiescent_host() -> dict:
    """Refuse to TIME anything on a contended host (§11.4.201(8)).

    MEASURED 2026-08-21 on this shared workstation — the timing-based
    complexity metric is only valid when the host is quiet:

      load ~2.8 ..  9 : baseline span exponent 1.759 - 1.882
      load     ~11    : baseline span exponent 2.136  (FALSE FAIL @2.10)
      load  15 .. 23  : baseline span exponent up to 2.358, while the
                        injected-cubic mutants read 2.28 - 2.33 —
                        i.e. under contention the SIGNAL (a real cubic
                        regression) is SMALLER THAN THE NOISE, and the
                        two are not separable. Best-of-N instead of
                        median does not rescue it (baseline 1.857 /
                        1.904 / 2.309 vs cubic 2.278 / 2.294).

    A metric whose correct end-state can cross its own threshold is
    INVALID and must not gate work (§11.4.201(8)), so on a busy host
    this SKIPs with the resolved numbers printed (§11.4.201(5)) rather
    than emitting a verdict it cannot support. The CORRECTNESS
    assertions in this file are deterministic and stay ungated.
    """
    reading = _host_safety_reading()
    cpus = reading["cpu_count"] or 1
    ratio = reading["loadavg_1m"] / cpus
    reading["load_per_cpu"] = round(ratio, 3)
    reading["load_per_cpu_ceiling"] = QUIESCENT_LOAD_PER_CPU
    if ratio > QUIESCENT_LOAD_PER_CPU:
        pytest.skip(
            f"SKIP-OK BOB-109 §11.4.201(8): host not quiescent — loadavg_1m "
            f"{reading['loadavg_1m']} over {cpus} cpus = {ratio:.2f} per cpu "
            f"> {QUIESCENT_LOAD_PER_CPU}. A timing-derived complexity "
            f"exponent is not separable from contention noise at this load; "
            f"emitting a verdict here would be a coin flip in both "
            f"directions."
        )
    return reading


def _emit(name: str, payload: dict) -> Path:
    """Write one evidence artifact.

    Every artifact self-describes, because a bare number cannot say
    whether it came from a passing baseline or a deliberately broken
    mutation run:

    * ``purpose`` — ``baseline`` or ``mutation``
    * ``verdict`` — ``PASS`` / ``FAIL`` / ``UNKNOWN``; callers compute
      the pass condition BEFORE emitting so a committed artifact is
      never silently a failing specimen
    * ``run_id``  — same for every file one process writes

    §11.4.84 GUARD: this file's own history is the argument for it — a
    mutation harness once wrote a 20/40/60 ladder carrying a 443,190 ms
    p99 into ``docs/qa/BOB-109/healthz_scale_out_curve.json``, and that
    experiment residue was committed as evidence. Setting
    ``BOBA_SCALING_MUTATION=1`` without redirecting ``EVIDENCE_DIR``
    now hard-fails instead of overwriting the committed corpus.
    """
    mutation = os.getenv("BOBA_SCALING_MUTATION", "").strip() not in ("", "0")
    # .resolve() BOTH sides: Path.__eq__ is LEXICAL, so a harness that
    # builds its path with a relative join (docs/qa/../qa/BOB-109) or a
    # symlinked checkout compares UNEQUAL and slips a mutation artifact
    # into the committed corpus. Proven live by the reviewer before this
    # line existed (§11.4.201(7)(c) — the PATH is part of the instrument).
    if mutation and EVIDENCE_DIR.resolve() == COMMITTED_EVIDENCE_DIR.resolve():
        raise AssertionError(
            "§11.4.84 refusing to write a MUTATION run into the committed "
            f"evidence directory {COMMITTED_EVIDENCE_DIR}. Redirect "
            "EVIDENCE_DIR to a scratch path before mutating."
        )
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    payload["purpose"] = "mutation" if mutation else payload.get("purpose", "baseline")
    payload.setdefault("verdict", "UNKNOWN")
    payload["run_id"] = RUN_ID
    payload["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload["feature_class"] = "scaling"
    payload["item"] = "BOB-109"
    out = EVIDENCE_DIR / name
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return out


def _pcts(samples: list[float]) -> dict:
    """p50/p95/p99 (§11.4.85 stress shape). Never guesses on tiny N."""
    s = sorted(samples)
    n = len(s)

    def _q(p: float) -> float:
        if n == 1:
            return s[0]
        idx = min(n - 1, max(0, math.ceil(p * n) - 1))
        return s[idx]

    return {
        "n": n,
        "p50_ms": round(statistics.median(s), 3),
        "p95_ms": round(_q(0.95), 3),
        "p99_ms": round(_q(0.99), 3),
        "min_ms": round(s[0], 3),
        "max_ms": round(s[-1], 3),
    }


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --- merge_service import (mirrors tests/unit/merge_service convention) -----

def _load_merge_service():
    ms = REPO_ROOT / "download-proxy" / "src" / "merge_service"
    sys.modules.setdefault("merge_service", type(sys)("merge_service"))
    sys.modules["merge_service"].__path__ = [str(ms)]

    def _load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    search = _load("merge_service.search", ms / "search.py")
    dedup = _load("merge_service.deduplicator", ms / "deduplicator.py")
    return search.SearchResult, dedup.Deduplicator


SearchResult, Deduplicator = _load_merge_service()


def _identity_census(groups: list) -> tuple[set[str], int, set[str], list[int]]:
    """What the merged view PRESERVED — inputs kept AND outputs bound.

    Returns ``(source_links, total_sources, url_union, mismatched)``:

    * ``source_links``  — every ``original_results`` link reachable
    * ``total_sources`` — how many source rows survived
    * ``url_union``     — every ``download_urls`` entry across all groups
    * ``mismatched``    — indices of groups whose ``download_urls`` are
      NOT a subset of that group's OWN sources' links

    Why the last two exist (§11.4.194(4)): a reviewer's TENTH mutation
    left ``original_results`` untouched — so the input census was
    perfect and passed — while replacing every group's
    ``download_urls`` with group 0's. 399 of 400 rows would have handed
    the user THE WRONG TORRENT. ``MergedResult.to_dict()`` serves
    ``download_urls``; it IS the product's download binding, so pinning
    input identity alone leaves the user-visible half unguarded.

    O(n) — cheap enough to assert on every iteration.
    """
    links: set[str] = set()
    url_union: set[str] = set()
    mismatched: list[int] = []
    total = 0
    for idx, g in enumerate(groups):
        own = {src.link for src in g.original_results}
        links |= own
        total += len(g.original_results)
        urls = set(g.download_urls)
        url_union |= urls
        # A group must only ever offer downloads that came from its own
        # sources. Cross-wiring here is invisible to any count.
        if not urls <= own:
            mismatched.append(idx)
    return links, total, url_union, mismatched


def _assert_distinct_merge_identity(groups: list, payload: list, n: int) -> None:
    """Assert the merged view still CONTAINS EVERY INPUT RELEASE.

    §11.4.194(4) — this exists because a reviewer's mutation survived
    every count-based guard in this file: `merge_results` returning the
    CORRECT number of groups while silently replacing the last 10% with
    duplicates of group 0. Real releases vanish from the user's merged
    view; the count is preserved, the timing is preserved, and a
    tail-truncation bug that only fires at n>100 is invisible both to
    the unit suite (small n) and to a count-only gate here — precisely
    the at-scale jurisdiction this file claims.

    Group COUNT is not identity. These three assertions pin identity:
    the right number of groups, the right SET of releases, and no
    release counted twice.
    """
    expected = {r.link for r in payload}
    links, total, url_union, mismatched = _identity_census(groups)

    assert len(groups) == n, (
        f"dedup did not do the work being timed at N={n}: expected {n} "
        f"groups, got {len(groups)}"
    )
    missing = expected - links
    extra = links - expected
    assert links == expected, (
        f"dedup LOST or INVENTED releases at N={n} while preserving the "
        f"group count: {len(missing)} input release(s) missing from the "
        f"merged view, {len(extra)} not from the input. "
        f"missing sample={sorted(missing)[:3]} extra sample={sorted(extra)[:3]}"
    )
    assert total == n, (
        f"dedup duplicated sources at N={n}: merged view holds {total} "
        f"source rows for {n} distinct inputs"
    )
    # The user-visible half: download_urls is what to_dict() serves and
    # what the user actually clicks. A group may only offer downloads
    # drawn from its OWN sources...
    assert not mismatched, (
        f"dedup CROSS-WIRED downloads at N={n}: {len(mismatched)} group(s) "
        f"offer download_urls that came from a DIFFERENT group's sources — "
        f"those rows would hand the user the wrong torrent. "
        f"group indices sample={mismatched[:5]}"
    )
    # ...and across the whole view every input release must still be
    # reachable as a download, or releases silently became unclickable.
    url_missing = expected - url_union
    url_extra = url_union - expected
    assert url_union == expected, (
        f"dedup LOST or INVENTED download bindings at N={n}: "
        f"{len(url_missing)} input release(s) no longer downloadable, "
        f"{len(url_extra)} download url(s) not from the input. "
        f"missing sample={sorted(url_missing)[:3]}"
    )


def _distinct_results(n: int) -> list:
    """`n` mutually NON-matching rows — the dedup worst case, and the
    realistic shape of a broad query fanned across three trackers."""
    return [
        SearchResult(
            name=f"Distinct.Title.{i}.2024.1080p.BluRay.x264-GRP{i}",
            link=f"magnet:?xt=urn:btih:{i:040x}",
            size=f"{1 + (i % 9)}.0 GB",
            seeds=i % 100,
            leechers=i % 7,
            engine_url="http://tracker.invalid",
            tracker=f"T{i % 3}",
        )
        for i in range(n)
    ]


def _identical_results(n: int) -> list:
    """`n` rows that are all the SAME release across trackers — the
    best case, and what dedup exists to collapse."""
    return [
        SearchResult(
            name="Same.Title.2024.1080p.BluRay.x264-GRP",
            link="magnet:?xt=urn:btih:" + ("a" * 40),
            size="4.0 GB",
            seeds=50 + i,
            leechers=3,
            engine_url="http://tracker.invalid",
            tracker=f"T{i % 3}",
        )
        for i in range(n)
    ]


@pytest.fixture(scope="session", autouse=True)
def _no_leaked_executors():
    """§11.4.14 — the Python analogue of `trap ... EXIT`.

    Every executor here is a context manager, so this finaliser asserts
    the invariant rather than performing cleanup: if a future refactor
    leaks a pool, the run fails loudly instead of leaving load
    generators behind.

    SCOPE, stated precisely (the docstring used to overclaim): this
    inspects PROCESS-WIDE threads, not "scaling-owned" ones. It reports
    any non-daemon thread named ``ThreadPoolExecutor*`` that did not
    exist when the session began. In a run of this file those are this
    file's pools, but a third-party library leaking a same-named pool
    would also be caught — a false positive there would be a §11.4.201(1)
    fault, so the name and non-daemon filters are deliberately narrow.
    """
    import threading

    before = {t.ident for t in threading.enumerate()}
    yield
    leaked = [
        t
        for t in threading.enumerate()
        if t.ident not in before
        and t.is_alive()
        and not t.daemon
        and t.name.startswith("ThreadPoolExecutor")
    ]
    assert not leaked, f"§11.4.14 leaked scaling executor threads: {leaked}"


# ===========================================================================
# Axis A — dedup cost vs result-set size (limiter-free, deterministic)
# ===========================================================================


class TestDedupCostScaling:
    """The merge step's cost curve as tracker result volume grows."""

    LADDER = (100, 200, 400, 800)
    REPEATS = 5
    # The gate reads the SPAN exponent log(t_800/t_100)/log(8), not the
    # max of adjacent-step exponents. Measured 2026-08-21 on this host,
    # which is shared with concurrent agents:
    #
    #   * span exponent, 3 independent baseline runs: 1.832 / 1.848 /
    #     1.759 (spread 0.09) — stable.
    #   * max-of-adjacent-steps on the SAME data swings far wider (a
    #     co-tenant load spike produced a 0.981 step and, at an
    #     N=1600 rung, pushed the BASELINE to 2.328). Adjacent steps
    #     are noise-dominated; the span averages that out, and the
    #     N=1600 rung was dropped for the same reason — a longer lever
    #     arm made the estimator noisier, not sharper (§11.4.201(6)).
    #
    # Injected-O(n^3) mutants, same ladder, span exponent:
    #   n/4 extra ops per compare -> 1.986 (NOT caught)
    #   n/2 extra ops per compare -> 2.145 (caught)
    #   n   extra ops per compare -> 2.450 (caught)
    #
    # 2.10 sits above baseline+jitter (1.848 max observed) and below
    # the smallest mutant it must catch, so it neither false-refuses
    # correct code (§11.4.201(1)) nor passes a real cubic regression.
    #
    # HONEST SENSITIVITY FLOOR (§11.4.6): this gate catches a cubic term
    # whose per-comparison cost is >= ~n/2 elementary ops. A cubic term
    # 4x smaller is indistinguishable from quadratic within N<=800 on
    # this host — its crossover lies beyond the tested range. This is a
    # stated blind spot, not a claim of completeness.
    #
    # HONEST GAP (§11.4.6) — carried here, not only in the doc, because
    # this is where the number is chosen: the GREEN polarity of this
    # gate was observed at loadavg 9.4-11.6 (span 1.882) and in three
    # stability runs (1.759 / 1.832 / 1.848), all under 2.10. It has
    # NOT been observed under the quiescence precondition below
    # (loadavg/cpu <= 0.75), because this host never got that quiet
    # while the gate was authored and sibling agents' load is not ours
    # to clear. Quiescence is strictly more favourable than the
    # conditions those passes were measured under, so passing there
    # follows from the data — but it is an inference, not a captured
    # run. A tracked item owes one quiescent GREEN run (§11.4.226
    # unexecuted-standing-guard).
    MAX_GROWTH_EXPONENT = 2.10

    def _time_merge(self, results: list) -> tuple[float, list]:
        """Returns (elapsed_ms, the merged GROUPS).

        Returns the groups themselves, not `len(out)`: a count cannot
        express identity, and identity is what the reviewer's
        tail-truncation mutant defeated.
        """
        dedup = Deduplicator()
        t0 = time.perf_counter()
        out = dedup.merge_results(results)
        return (time.perf_counter() - t0) * 1000.0, out

    @pytest.mark.timeout(300)
    def test_dedup_growth_does_not_regress_past_quadratic(self):
        _require_host_headroom()
        # Record the reading the test was ADMITTED under, not a fresh
        # one taken at emit time: load moves during a multi-second run,
        # and an artifact stamped with a post-hoc load ABOVE the gate's
        # own ceiling reads as if the gate had been violated.
        admission = _require_quiescent_host()
        per_size: dict[str, dict] = {}

        for n in self.LADDER:
            payload = _distinct_results(n)
            samples: list[float] = []
            for _ in range(self.REPEATS):
                dt_ms, groups = self._time_merge(payload)
                samples.append(dt_ms)
                # ANTI-BLUFF: a dedup that returned [], collapsed
                # everything, or silently dropped a tail would look
                # FASTER and sail through a pure timing assertion. The
                # identity census ties the measured time to real work.
                _assert_distinct_merge_identity(groups, payload, n)
            per_size[str(n)] = {"n_results": n, "groups_out": n, **_pcts(samples)}

        exponents = []
        sizes = list(self.LADDER)
        for a, b in itertools.pairwise(sizes):
            ta = per_size[str(a)]["p50_ms"]
            tb = per_size[str(b)]["p50_ms"]
            exponents.append(
                {
                    "from_n": a,
                    "to_n": b,
                    "p50_ratio": round(tb / ta, 4),
                    "growth_exponent": round(math.log(tb / ta) / math.log(b / a), 4),
                }
            )

        lo_n, hi_n = sizes[0], sizes[-1]
        span_exponent = round(
            math.log(per_size[str(hi_n)]["p50_ms"] / per_size[str(lo_n)]["p50_ms"])
            / math.log(hi_n / lo_n),
            4,
        )
        gate_ok = span_exponent <= self.MAX_GROWTH_EXPONENT
        evidence = _emit(
            "dedup_cost_scaling.json",
            {
                "axis": "dedup cost vs result-set size (worst case: all-distinct)",
                "host_safety_at_admission": admission,
                "host_safety_at_emit": _host_safety_reading(),
                "repeats_per_size": self.REPEATS,
                "per_size": per_size,
                "growth_per_step": exponents,
                "span_exponent": span_exponent,
                "span_from_n": lo_n,
                "span_to_n": hi_n,
                "max_growth_exponent_allowed": self.MAX_GROWTH_EXPONENT,
                "gated_on": "span_exponent",
                "verdict": "PASS" if gate_ok else "FAIL",
                "complexity_note": (
                    "merge_results rescans all remaining candidates per seed, "
                    "so all-distinct input is quadratic BY DESIGN. This gate "
                    "catches a regression PAST quadratic, not quadratic itself."
                ),
            },
        )

        assert span_exponent <= self.MAX_GROWTH_EXPONENT, (
            f"dedup complexity regressed past quadratic: span exponent "
            f"{span_exponent} (N={lo_n}->{hi_n}) > "
            f"{self.MAX_GROWTH_EXPONENT}. Per-step: {exponents}. "
            f"Evidence: {evidence}"
        )

    @pytest.mark.timeout(300)
    def test_dedup_latency_distribution_at_operating_size(self):
        """§11.4.85 stress shape: N>=100 iterations, p50/p95/p99, at a
        realistic 3-tracker union size."""
        _require_host_headroom()
        admission = _require_quiescent_host()
        n_results = 200
        iterations = 100
        payload = _distinct_results(n_results)

        samples: list[float] = []
        for _ in range(iterations):
            dt_ms, groups = self._time_merge(payload)
            samples.append(dt_ms)
            _assert_distinct_merge_identity(groups, payload, n_results)

        dist = _pcts(samples)
        budget_ms = 2000.0  # measured p50 ~97ms on this host; 20x headroom
        budget_ok = dist["p99_ms"] < budget_ms
        evidence = _emit(
            "dedup_latency_distribution.json",
            {
                "axis": "dedup latency distribution at operating size",
                "host_safety_at_admission": admission,
                "host_safety_at_emit": _host_safety_reading(),
                "n_results": n_results,
                "iterations": iterations,
                "groups_out": n_results,
                "budget_p99_ms": budget_ms,
                "verdict": "PASS" if budget_ok else "FAIL",
                **dist,
            },
        )
        assert dist["p99_ms"] < budget_ms, (
            f"dedup p99 {dist['p99_ms']}ms exceeded {budget_ms}ms budget at "
            f"N={n_results}. Evidence: {evidence}"
        )

    @pytest.mark.timeout(180)
    def test_dedup_identity_preserved_at_scale(self):
        """UNGATED at-scale identity check — runs on a busy host too.

        §11.4.201(8) forces the two timing-derived tests to skip when
        the host is contended. Without this test, Axis A on a busy host
        would collapse to the single all-identical case, so the
        at-scale DISTINCT-input jurisdiction — where the reviewer's
        tail-truncation mutant lives — would go uncovered exactly when
        the suite still reports green.

        Deterministic and load-independent: it asserts identity, never
        elapsed time, so contention cannot make it lie in either
        direction (§11.4.201(1)).
        """
        _require_host_headroom()
        n = 400
        payload = _distinct_results(n)
        dedup = Deduplicator()
        groups = dedup.merge_results(payload)
        links, total, url_union, mismatched = _identity_census(groups)
        expected = {r.link for r in payload}
        _emit(
            "dedup_identity_at_scale.json",
            {
                "axis": "dedup identity preservation at scale (ungated)",
                "purpose": "baseline",
                "n_results": n,
                "groups_out": len(groups),
                "distinct_sources_preserved": len(links),
                "total_source_rows": total,
                "releases_missing": len(expected - links),
                "releases_invented": len(links - expected),
                "download_urls_union": len(url_union),
                "download_bindings_missing": len(expected - url_union),
                "groups_with_cross_wired_downloads": len(mismatched),
                "verdict": "PASS"
                if (
                    len(groups) == n
                    and links == expected
                    and total == n
                    and not mismatched
                    and url_union == expected
                )
                else "FAIL",
            },
        )
        _assert_distinct_merge_identity(groups, payload, n)

    @pytest.mark.timeout(120)
    def test_dedup_collapses_identical_union_to_one_group(self):
        """Correctness-at-scale guard: the case dedup exists for.

        Without this, a dedup that stopped matching anything would still
        pass the complexity gate (it would merely get *faster*)."""
        _require_host_headroom()
        n = 300
        payload = _identical_results(n)
        dt_ms, groups = self._time_merge(payload)
        aggregated = len(groups[0].original_results) if groups else 0
        _, _, url_union, mismatched = _identity_census(groups)
        expected_urls = {r.link for r in payload}
        _emit(
            "dedup_collapse_identical.json",
            {
                "axis": "dedup correctness at scale (all-identical union)",
                "purpose": "baseline",
                "n_results": n,
                "groups_out": len(groups),
                "sources_aggregated_into_survivor": aggregated,
                "download_urls_union": len(url_union),
                "groups_with_cross_wired_downloads": len(mismatched),
                "elapsed_ms": round(dt_ms, 3),
                "verdict": "PASS"
                if (
                    len(groups) == 1
                    and aggregated == n
                    and not mismatched
                    and url_union == expected_urls
                )
                else "FAIL",
            },
        )
        assert len(groups) == 1, (
            f"dedup failed to collapse {n} identical releases: got "
            f"{len(groups)} groups, expected 1 — dedup is not "
            f"deduplicating at scale"
        )
        # Collapsing to ONE group is not enough: the survivor must carry
        # every source it absorbed, or the merged view silently loses
        # the tracker rows it claims to represent.
        assert aggregated == n, (
            f"dedup collapsed to 1 group but kept only {aggregated} of {n} "
            f"sources — {n - aggregated} tracker row(s) vanished from the "
            f"merged view"
        )
        assert not mismatched, (
            "dedup collapsed to 1 group whose download_urls are not drawn "
            "from its own sources — the survivor would hand the user a "
            "torrent it never absorbed"
        )
        assert url_union == expected_urls, (
            f"dedup collapsed to 1 group but its download bindings are "
            f"wrong: union={sorted(url_union)[:2]} expected="
            f"{sorted(expected_urls)[:2]}"
        )


# ===========================================================================
# Axis B — admission envelope: the limiter as SUBJECT (non-destructive)
# ===========================================================================


def _binding_limit(header_value: str | None) -> int | None:
    """Smallest limit advertised in an ``x-ratelimit-limit`` header.

    When more than one limit applies to a route (slowapi emits the
    default limit AND any per-route decorator), ``requests`` joins the
    repeated headers into ``"120, 5"``. The BINDING ceiling is the
    smallest — parsing the first value would silently report the wrong
    envelope (§11.4.201(9) field-identity: this field is a LIST of
    capacities, not a scalar).
    """
    if header_value is None:
        return None
    parts = [p.strip() for p in str(header_value).split(",") if p.strip()]
    values = [int(p) for p in parts if p.lstrip("-").isdigit()]
    return min(values) if values else None


def _declared_limits() -> dict[str, str]:
    """Read ``DEFAULT_LIMITS`` from source — the authoritative declaration.

    Parsed STATICALLY with :mod:`ast`, never imported: ``rate_limit.py``
    pulls fastapi/slowapi/pydantic, which live in the container and not
    on the host interpreter. Importing it here made this whole axis
    SKIP on the host — a §11.4.201(6) false-null, where a blind
    instrument and a healthy system return the same quiet nothing.
    """
    path = REPO_ROOT / "download-proxy" / "src" / "api" / "rate_limit.py"
    assert path.is_file(), f"rate_limit.py missing at {path}"
    tree = ast.parse(path.read_text())
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "DEFAULT_LIMITS":
                value = node.value
                assert value is not None, "DEFAULT_LIMITS has no value"
                limits = ast.literal_eval(value)
                assert isinstance(limits, dict) and limits, "DEFAULT_LIMITS empty"
                return {str(k): str(v) for k, v in limits.items()}
    raise AssertionError(f"DEFAULT_LIMITS not found in {path}")


class TestRateLimitAdmissionEnvelope:
    """Characterise the ceiling that binds concurrency scale-out.

    ONE request per class — the limiter is shared per-IP with every
    other agent on this host (§11.4.119), so this never drives it to
    exhaustion.
    """

    @pytest.mark.timeout(60)
    def test_limiter_is_enforced_and_headers_are_coherent(self):
        if not _port_open(7187):
            pytest.skip("SKIP-OK BOB-109: merge service :7187 not reachable")
        requests = pytest.importorskip("requests")

        observed: dict[str, dict] = {}
        probes = {
            "dashboard_root": "/",
            "sse_stream": "/api/v1/theme/stream",
        }
        for label, path in probes.items():
            r = None
            try:
                r = requests.get(
                    MERGE_URL + path,
                    timeout=5.0,
                    stream=path.endswith("/stream"),
                    headers={"Accept": "text/event-stream"}
                    if path.endswith("/stream")
                    else {},
                )
                observed[label] = {
                    "path": path,
                    "status": r.status_code,
                    "limit": r.headers.get("x-ratelimit-limit"),
                    "binding_limit": _binding_limit(
                        r.headers.get("x-ratelimit-limit")
                    ),
                    "remaining": r.headers.get("x-ratelimit-remaining"),
                    "retry_after": r.headers.get("retry-after"),
                }
            except requests.RequestException as exc:
                observed[label] = {"path": path, "error": str(exc)}
            finally:
                if r is not None:
                    r.close()

        evidence = _emit(
            "rate_limit_admission_envelope.json",
            {
                "axis": "admission envelope (non-destructive header read)",
                "declared_default_limits": _declared_limits(),
                "observed": observed,
                "method": (
                    "one request per class; limiter never driven to "
                    "exhaustion because it is a per-IP resource shared "
                    "with concurrent agents (§11.4.119)"
                ),
                "verdict": "PASS"
                if all(
                    "error" not in o and _binding_limit(o.get("limit")) not in (None, 0)
                    for o in observed.values()
                )
                else "FAIL",
            },
        )

        for label, obs in observed.items():
            assert "error" not in obs, f"{label} probe failed: {obs} ({evidence})"
            limit = _binding_limit(obs["limit"])
            # A silently-disabled limiter (headers gone) is the
            # regression this catches — it would make every scale-out
            # number above meaningless.
            assert limit is not None, (
                f"{label}: rate limiter advertises no x-ratelimit-limit — "
                f"limiter disabled or unwired. Evidence: {evidence}"
            )
            assert limit > 0, f"{label}: non-positive limit {obs['limit']}"
            remaining = _binding_limit(obs["remaining"])
            assert remaining is not None and 0 <= remaining <= limit, (
                f"{label}: incoherent headers limit={obs['limit']} "
                f"remaining={obs['remaining']}"
            )

    # KNOWN-OPEN DEFECT (filed by the coordinator as BOB-167), observed
    # on every run. `strict=True` is load-bearing: the moment both SSE
    # routes carry the same class this flips to XPASS and FAILS the run,
    # forcing this marker's removal. A self-clearing record, not a
    # suppression — it stays visible as `xfailed` in every report
    # (§11.4.226).
    # SKIP-OK: BOB-167 — evidence docs/qa/BOB-109/rate_limit_class_wiring.json
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BOB-167: two SSE routes, one rate-limit class. "
            "/api/v1/search/stream carries @_rl('sse_stream') and serves 5; "
            "the sibling /api/v1/theme/stream carries no limiter and falls "
            "to the 120/minute default."
        ),
    )
    @pytest.mark.timeout(60)
    def test_sse_shaped_routes_serve_a_consistent_limit_class(self):
        """§11.4.196(F) CONFIGURED != IN USE, in its policy-neutral form.

        A CORRECTION WORTH KEEPING (§11.4.6). This test first asserted
        that /theme/stream must serve `sse_stream`'s 5/minute, on the
        theory that `sse_stream` was declared and wired to nothing. That
        MECHANISM was wrong and the coordinator rejected it: the wiring
        does not use a `*_limit_decorator` symbol at all, it uses
        `@_rl("sse_stream")` (routes.py:801), and the class IS applied —
        to `/search/stream/{search_id}`. Verified here directly:
        that route serves `x-ratelimit-limit: 5`. The original
        MEASUREMENT (120 on /theme/stream) was correct and is what makes
        this a real finding; the cause was not. Searching for one symbol
        NAME and reading the zero hits as "wired nowhere" is the
        §11.4.201(7)(a) carrier/absence trap.

        So this asserts the policy-NEUTRAL invariant instead: two routes
        of the SAME SSE shape — both long-lived connections that pin a
        worker and a generator — must serve the SAME rate-limit class.
        Whether the right answer is to classify /theme/stream or to
        widen sse_stream is an operator decision (BOB-167 acceptance
        (a)), and this test deliberately does not presume it. What it
        refuses to let pass silently is the DIVERGENCE.
        """
        if not _port_open(7187):
            pytest.skip("SKIP-OK BOB-109: merge service :7187 not reachable")
        requests = pytest.importorskip("requests")

        declared = _declared_limits()
        # Both probes are ONE request each. /search/stream is bound to
        # the sse_stream class (5/minute) which is shared per-IP with
        # sibling agents, so this axis never loops on it (§11.4.119).
        routes = {
            "theme_stream": "/api/v1/theme/stream",
            "search_stream": "/api/v1/search/stream/bob109-probe",
        }
        served: dict[str, int | None] = {}
        raw: dict[str, str | None] = {}
        for label, path in routes.items():
            r = None
            try:
                r = requests.get(
                    MERGE_URL + path,
                    timeout=5.0,
                    stream=True,
                    headers={"Accept": "text/event-stream"},
                )
                raw[label] = r.headers.get("x-ratelimit-limit")
                served[label] = _binding_limit(raw[label])
            except requests.RequestException as exc:
                raw[label] = f"error: {exc}"
                served[label] = None
            finally:
                if r is not None:
                    r.close()

        consistent = (
            served["theme_stream"] is not None
            and served["theme_stream"] == served["search_stream"]
        )
        evidence = _emit(
            "rate_limit_class_wiring.json",
            {
                "axis": "SSE-shaped routes serve a consistent limit class",
                "mechanism": "@_rl('<class>') at routes.py:801, NOT a *_limit_decorator symbol",
                "declared_sse_stream": declared["sse_stream"],
                "declared_default": declared["default"],
                "routes": routes,
                "served_binding_limit": served,
                "served_limit_raw": raw,
                "divergent": not consistent,
                "tracked_as": "BOB-167",
                "verdict": "PASS" if consistent else "FAIL",
            },
        )

        assert served["search_stream"] is not None, (
            f"/search/stream advertises no limit — probe failed ({evidence})"
        )
        assert consistent, (
            f"BOB-167: two SSE-shaped routes serve DIFFERENT rate-limit "
            f"classes — {routes['search_stream']} serves "
            f"{served['search_stream']} (the declared sse_stream class "
            f"{declared['sse_stream']}), while {routes['theme_stream']} "
            f"serves {served['theme_stream']} (the default class "
            f"{declared['default']}) because it carries no limiter "
            f"decorator at all. An unclassed SSE route is the cheapest way "
            f"to pin server resources. Which way to reconcile is an "
            f"operator decision. Evidence: {evidence}"
        )


# ===========================================================================
# Axis C — limiter-free concurrent scale-out (:7189 boba-jackett)
# ===========================================================================


class TestLimiterFreeConcurrencyScaleOut:
    """Concurrency scale-out measured where NO limiter distorts it.

    :7189 ``/healthz`` advertises no ``x-ratelimit-*`` headers (measured
    2026-08-21), so the curve here is the service's own envelope rather
    than a rate-limit staircase.
    """

    LADDER = ((50, 4), (100, 8), (200, 16))  # (requests, workers)

    def _burst(self, url: str, n: int, workers: int):
        workers = min(workers, MAX_WORKERS_CAP)
        lat: list[float] = []
        ok = 0
        requests = pytest.importorskip("requests")

        def _one(_i: int):
            t0 = time.perf_counter()
            r = None
            try:
                r = requests.get(url, timeout=10.0)
                return r.status_code, (time.perf_counter() - t0) * 1000.0
            except requests.RequestException:
                return 0, (time.perf_counter() - t0) * 1000.0
            finally:
                if r is not None:
                    r.close()

        start = time.perf_counter()
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for status, dt in ex.map(_one, range(n)):
                lat.append(dt)
                if status == 200:
                    ok += 1
        return time.perf_counter() - start, lat, ok

    @pytest.mark.timeout(300)
    def test_healthz_scale_out_curve(self):
        if not _port_open(7189):
            pytest.skip("SKIP-OK BOB-109: boba-jackett :7189 not reachable")
        reading = _require_host_headroom()

        curve: dict[str, dict] = {}
        for n, workers in self.LADDER:
            wall, lat, ok = self._burst(JACKETT_BOBA_URL + "/healthz", n, workers)
            curve[str(n)] = {
                "n_requests": n,
                "workers": min(workers, MAX_WORKERS_CAP),
                "wall_s": round(wall, 3),
                "ok": ok,
                "ok_rate": round(ok / n, 4),
                "throughput_req_per_s": round(ok / wall, 2) if wall > 0 else None,
                **_pcts(lat),
            }

        # M5 / §11.4.201(8): `ok == N` is load-robust and stays
        # asserted always; the p99 RATIO is timing-derived and is only
        # asserted on a quiescent host, for exactly the reason Axis A's
        # exponent is gated — under contention the top rung degrades
        # disproportionately and the ratio stops measuring the service.
        quiescent, quiesce_reading = _is_quiescent()
        all_ok = all(r["ok"] == r["n_requests"] for r in curve.values())
        lo_p99 = curve[str(self.LADDER[0][0])]["p99_ms"]
        hi_p99 = curve[str(self.LADDER[-1][0])]["p99_ms"]
        max_ratio = 25.0
        ratio_ok = hi_p99 <= max(lo_p99, 1.0) * max_ratio
        evidence = _emit(
            "healthz_scale_out_curve.json",
            {
                "axis": "limiter-free concurrency scale-out (:7189/healthz)",
                "host_safety": reading,
                "ladder": [n for n, _ in self.LADDER],
                "curve": curve,
                "p99_ratio_ceiling": max_ratio,
                "p99_ratio_asserted": quiescent,
                "p99_ratio_observed": round(hi_p99 / max(lo_p99, 1.0), 3),
                "quiescence": quiesce_reading,
                "verdict": "PASS"
                if (all_ok and (ratio_ok or not quiescent))
                else "FAIL",
            },
        )

        for key, row in curve.items():
            # Every request must resolve successfully — this is a
            # REAL assertion on service behaviour, not an identity that
            # holds by construction.
            assert row["ok"] == row["n_requests"], (
                f"boba-jackett dropped requests at N={key}: "
                f"ok={row['ok']}/{row['n_requests']}. Evidence: {evidence}"
            )

        # Scale-out must not collapse: p99 at the top of the ladder is
        # bounded relative to the bottom. Catches a service that
        # serialises (or thrashes) as concurrency rises.
        if not quiescent:
            # Recorded, not asserted — and said out loud rather than
            # silently skipped (§11.4.201(5)).
            print(
                f"[BOB-109] p99-ratio assertion NOT applied: host not "
                f"quiescent ({quiesce_reading['load_per_cpu']} load/cpu > "
                f"{QUIESCENT_LOAD_PER_CPU}); observed ratio "
                f"{hi_p99 / max(lo_p99, 1.0):.2f}x. Evidence: {evidence}"
            )
            return
        assert ratio_ok, (
            f"scale-out collapsed: p99 grew from {lo_p99}ms at "
            f"N={self.LADDER[0][0]} to {hi_p99}ms at N={self.LADDER[-1][0]} "
            f"(> {max_ratio}x). Evidence: {evidence}"
        )
