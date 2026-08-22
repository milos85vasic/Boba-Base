"""Scaling-class tests for boba (BOB-109 / §11.4.27).

Real-service scaling measurements across three axes:

1. **Vertical scale** — concurrent SSE subscribers on
   ``/api/v1/theme/stream`` at N ∈ {10, 50, 100, 200}.
2. **Horizontal scale (proxy fan-out)** — parallel ``/api/v1/search``
   requests at N ∈ {1, 2, 5}.
3. **Cache warming** — ``/healthz`` on boba-jackett (7189) at rising
   rps against the BOB-112 TTL cache; RED capture bypasses the cache
   by hitting Jackett's upstream directly.

Every test writes a machine-readable ``docs/qa/BOB-109/*.json``
artifact and cleans up on every exit path (§11.4.14 / §11.4.69
``feature_class = scaling``).

§11.4.6 — every number is measured from a live service, never
simulated. Services on 7187 / 7189 / 9117 MUST already be up (do NOT
restart them from this test).
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import socket
import statistics
import threading
import time
from pathlib import Path

import pytest
import requests

MERGE_URL = "http://localhost:7187"
JACKETT_BOBA_URL = "http://localhost:7189"
JACKETT_UPSTREAM_URL = "http://localhost:9117"
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "docs" / "qa" / "BOB-109"


def _service_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _healthy(url: str, path: str = "/healthz", timeout: float = 2.0) -> bool:
    try:
        r = requests.get(url + path, timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


COMMITTED_EVIDENCE_DIR = EVIDENCE_DIR
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


def _emit_evidence(name: str, payload: dict) -> Path:
    """Write one evidence artifact (BOB-109: self-describing).

    Artifacts from this file are committed, so each one records
    ``purpose`` (baseline|mutation), a ``verdict``, and a ``run_id``
    shared by every file one process writes. Without those a reader
    cannot tell a passing baseline from a failing specimen left behind
    by an earlier run — this directory has already carried both.

    §11.4.84 GUARD: ``BOBA_SCALING_MUTATION=1`` without an
    ``EVIDENCE_DIR`` redirect hard-fails rather than overwriting the
    committed corpus.
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
    out = EVIDENCE_DIR / name
    payload["purpose"] = "mutation" if mutation else payload.get("purpose", "baseline")
    if "verdict" not in payload:
        # Matrices accumulate one row per parametrized N and have no
        # single outcome of their own; derive the roll-up so no
        # committed artifact reads as an unlabelled UNKNOWN.
        rows = [
            v["verdict"]
            for v in payload.values()
            if isinstance(v, dict) and "verdict" in v
        ]
        payload["verdict"] = (
            ("PASS" if all(r == "PASS" for r in rows) else "FAIL")
            if rows
            else "UNKNOWN"
        )
    payload["run_id"] = RUN_ID
    payload["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return out


@pytest.fixture(scope="module", autouse=True)
def _services_up():
    if not _service_reachable("localhost", 7189):
        pytest.skip("boba-jackett :7189 not reachable (SKIP-OK BOB-109)")
    if not _service_reachable("localhost", 9117):
        pytest.skip("jackett :9117 not reachable (SKIP-OK BOB-109)")
    if not _service_reachable("localhost", 7187):
        pytest.skip("merge service :7187 not reachable (SKIP-OK BOB-109)")
    if not _healthy(JACKETT_BOBA_URL):
        pytest.skip("boba-jackett /healthz not ok (SKIP-OK BOB-109)")


# ---------------------------------------------------------------------------
# Axis 1 — Vertical scale: concurrent SSE subscribers on /api/v1/theme/stream
# ---------------------------------------------------------------------------


class TestVerticalScaleSSE:
    """One process, N SSE subscribers on ``/api/v1/theme/stream``.

    BOB-109 CORRECTION (§11.4.6 — the previous wording asserted a
    contract nobody had measured): this docstring used to state that
    the endpoint enforces the ``sse_stream`` per-IP class at 5/minute.
    Measured against the live service 2026-08-21, the route advertises
    ``x-ratelimit-limit: 120`` — the ``default`` class, not
    ``sse_stream``.

    A SECOND CORRECTION (§11.4.201(7)(a) — the carrier trap, committed
    twice in this very docstring). The wording above previously
    continued: "``sse_limit_decorator`` is defined there and applied to
    no route, so the declared class never binds." The symbol clause is
    literally true and the conclusion is FALSE. The wiring does not use
    that symbol at all — it uses ``@_rl("sse_stream")``
    (``routes.py:801``) — and the class DOES bind: the sibling route
    ``/api/v1/search/stream`` serves ``x-ratelimit-limit: 5``, measured
    directly. What is actually wrong is narrower and is filed as
    **BOB-167**: ``/theme/stream`` carries no limiter decorator at all
    and therefore falls to the 120/minute default, while its
    same-shaped sibling is classed at 5. Searching for one symbol NAME
    and reading zero hits as "wired nowhere" is exactly the
    absence-is-not-evidence trap this suite exists to catch.

    The envelope THIS axis measures is therefore the 120/minute
    default. See
    ``test_scaling_envelope.py::TestRateLimitAdmissionEnvelope`` and
    ``docs/qa/BOB-109/rate_limit_class_wiring.json``.

    A 429 is a healthy back-pressure signal, NOT a defect.

    §11.4.14 cleanup: every stream response is ``.close()``d in a
    ``finally`` before the executor exits.
    """

    @pytest.mark.timeout(180)
    @pytest.mark.parametrize("n_subs", [1, 3, 10, 50])
    def test_sse_subscriber_scale(self, n_subs: int):
        matrix_path = EVIDENCE_DIR / "sse_subscribers_matrix.json"
        matrix: dict = {}
        if matrix_path.exists():
            matrix = json.loads(matrix_path.read_text())

        accepted_lat_ms: list[float] = []
        status_codes: list[int] = []
        active: list[requests.Response] = []
        lock = threading.Lock()

        def _subscribe():
            t0 = time.perf_counter()
            try:
                r = requests.get(
                    f"{MERGE_URL}/api/v1/theme/stream",
                    stream=True,
                    # BOB-109: was 5.0s, which sits INSIDE this host's
                    # contended time-to-first-event band — the committed
                    # matrix recorded TTFE 3656 ms at N=1 and an all-50
                    # -errored N=50 row that is contention residue, not a
                    # service defect (the same axis run live at N=50
                    # accepted 50/50 at TTFE p50 242 ms). At 5.0s the
                    # `accepted + rate_limited >= 1` assertion below can
                    # therefore FALSE-FAIL under load (§11.4.201(1)),
                    # reporting a healthy SSE plane as dead. 20s clears
                    # the observed band with margin while still bounding
                    # a genuinely wedged endpoint.
                    timeout=20.0,
                    headers={"Accept": "text/event-stream"},
                )
            except requests.RequestException:
                with lock:
                    status_codes.append(0)
                return
            code = r.status_code
            with lock:
                active.append(r)
                status_codes.append(code)
            if code != 200:
                r.close()
                return
            # Capture time-to-first-event, then release the connection.
            for chunk in r.iter_content(chunk_size=64):
                if chunk:
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    with lock:
                        accepted_lat_ms.append(dt_ms)
                    break
            r.close()

        start = time.perf_counter()
        try:
            with cf.ThreadPoolExecutor(max_workers=min(n_subs, 64)) as ex:
                list(ex.map(lambda _: _subscribe(), range(n_subs)))
        finally:
            for r in active:
                try:
                    r.close()
                except Exception:
                    pass

        wall_s = time.perf_counter() - start
        accepted = sum(1 for c in status_codes if c == 200)
        rate_limited = sum(1 for c in status_codes if c == 429)
        matrix[str(n_subs)] = {
            "verdict": "PASS" if (accepted + rate_limited) >= 1 else "FAIL",
            "n_subs": n_subs,
            "wall_s": round(wall_s, 3),
            "accepted": accepted,
            "rate_limited_429": rate_limited,
            "other_errors": len(status_codes) - accepted - rate_limited,
            "ttfe_ms_p50": round(statistics.median(accepted_lat_ms), 2)
            if accepted_lat_ms
            else None,
            "ttfe_ms_max": round(max(accepted_lat_ms), 2)
            if accepted_lat_ms
            else None,
            "accepted_throughput_conn_per_s": round(accepted / wall_s, 2),
        }
        _emit_evidence("sse_subscribers_matrix.json", matrix)

        # Anti-bluff: EVERY attempt must resolve to a decision (never
        # a timeout or silent drop). Accepted + 429 + errors == N.
        total = accepted + rate_limited + matrix[str(n_subs)]["other_errors"]
        assert total == n_subs, (
            f"attempts unaccounted at N={n_subs}: got {total} of {n_subs}"
        )
        # BOB-109: `total` above is `len(status_codes)` by
        # construction, so that check only catches a thread that failed
        # to record — it does NOT catch a dead service. This does: a
        # 200 or a 429 both prove the SSE plane answered, while an
        # all-connection-error run (status 0) fails.
        assert accepted + rate_limited >= 1, (
            f"SSE plane produced NO HTTP verdict at N={n_subs} "
            f"(all attempts errored): {status_codes}"
        )
        # At small N some connections MUST land — the SSE plane is
        # non-empty.
        if n_subs <= 3:
            assert accepted >= 1, (
                f"SSE plane empty at N={n_subs}: no 200 among {status_codes}"
            )


# ---------------------------------------------------------------------------
# Axis 2 — Horizontal scale (proxy fan-out): parallel /api/v1/search
# ---------------------------------------------------------------------------


class TestHorizontalScaleProxyFanOut:
    """N parallel POST /api/v1/search requests fan out through the
    merge service to the tracker plugins.

    The endpoint kicks off a background search and returns
    immediately with a ``search_id``, so the client-observable
    latency measures the FAN-OUT ADMISSION path — the merge service
    partitioning admission slots across N concurrent callers under
    the ``MAX_CONCURRENT_SEARCHES`` cap and the ``search`` rate-limit
    class.

    The captured matrix maps accepted vs rate-limited vs timeout at
    each N — the aggregate throughput envelope of the proxy fan-out
    plane.
    """

    @pytest.mark.timeout(240)
    @pytest.mark.parametrize("n_parallel", [1, 2, 5, 8])
    def test_search_fanout(self, n_parallel: int):
        matrix_path = EVIDENCE_DIR / "proxy_fanout_matrix.json"
        matrix: dict = {}
        if matrix_path.exists():
            matrix = json.loads(matrix_path.read_text())

        # Bounded client timeout so a stuck admission path becomes
        # a data point (recorded as timeout), never wedges the test
        # (§11.4.201(12) shell-instrument footgun applied at the
        # client library layer).
        # BOB-109 (§11.4.201(1)): was 8.0s, which sits INSIDE this
        # host's contended admission band — a full-suite run at loadavg
        # 24 recorded N=1 as a single client timeout at wall 8.06s, so
        # the `accepted + rate_limited >= 1` assertion below FALSE-FAILED
        # against a merge service that was answering fine. Same class of
        # defect as the SSE axis's 5.0s timeout. 30s clears the observed
        # band while still bounding a genuinely wedged admission path,
        # and a timeout remains a recorded data point, never a hang.
        client_timeout = 30.0

        def _one_search(i: int):
            # Vary the query so the orchestrator does not dedup the
            # burst into one search across callers.
            query = f"scaling_probe_{n_parallel}_{i}_{int(time.time())}"
            t0 = time.perf_counter()
            try:
                r = requests.post(
                    f"{MERGE_URL}/api/v1/search",
                    json={"query": query, "limit": 5, "enable_metadata": False},
                    timeout=client_timeout,
                )
                dt_ms = (time.perf_counter() - t0) * 1000.0
                return (r.status_code, dt_ms)
            except requests.RequestException:
                dt_ms = (time.perf_counter() - t0) * 1000.0
                return (-1, dt_ms)

        start = time.perf_counter()
        with cf.ThreadPoolExecutor(max_workers=n_parallel) as ex:
            results = list(ex.map(lambda i: _one_search(i), range(n_parallel)))
        wall_s = time.perf_counter() - start

        accepted = sum(1 for r in results if r[0] == 200)
        rate_limited = sum(1 for r in results if r[0] == 429)
        timed_out = sum(1 for r in results if r[0] == -1)
        other = n_parallel - accepted - rate_limited - timed_out
        admission_lat_ms = [r[1] for r in results if r[0] == 200]

        matrix[str(n_parallel)] = {
            "verdict": "PASS" if (accepted + rate_limited) >= 1 else "FAIL",
            "n_parallel": n_parallel,
            "wall_s": round(wall_s, 3),
            "accepted": accepted,
            "rate_limited_429": rate_limited,
            "client_timeout": timed_out,
            "other": other,
            "admission_ms_p50": round(statistics.median(admission_lat_ms), 2)
            if admission_lat_ms
            else None,
            "admission_ms_max": round(max(admission_lat_ms), 2)
            if admission_lat_ms
            else None,
            "aggregate_admission_req_per_s": round(accepted / wall_s, 3),
        }
        _emit_evidence("proxy_fanout_matrix.json", matrix)

        # BOB-109: the assertion that used to stand here was a
        # TAUTOLOGY. `other` is DEFINED above as the residual
        # `n_parallel - accepted - rate_limited - timed_out`, so
        # `accepted + rate_limited + timed_out + other == n_parallel`
        # reduces to `n_parallel == n_parallel` and held for ALL
        # inputs. Measured 2026-08-21: with MERGE_URL pointed at a
        # CLOSED port this test still PASSED
        # (docs/qa/BOB-109/red_tautology_proof.txt) — §11.4.266
        # green-but-broken. Replaced with two assertions that a dead
        # service actually fails.
        #
        # (1) No attempt is silently dropped by the executor. This is
        #     real: `results` is what the pool returned, and it is not
        #     algebraically tied to n_parallel.
        assert len(results) == n_parallel, (
            f"executor dropped attempts at N={n_parallel}: "
            f"got {len(results)} results, expected {n_parallel}"
        )
        # (2) The merge service actually answered. A 429 is a healthy
        #     back-pressure verdict and counts; a client-side timeout
        #     (-1) does not. All-timeouts means nothing is serving, and
        #     that MUST fail rather than read as a scaling data point.
        # A 429 counts: back-pressure IS an answer. Only an all-timeout
        # run means nothing is serving. The client timeout above must
        # stay clear of the contended admission band or this assertion
        # reports a healthy service as dead.
        assert accepted + rate_limited >= 1, (
            f"merge service produced NO HTTP verdict at N={n_parallel} "
            f"(all attempts timed out / errored within {client_timeout}s): "
            f"{results}"
        )


# ---------------------------------------------------------------------------
# Axis 3 — Cache warming: /healthz at rising rps + RED bypass
# ---------------------------------------------------------------------------


class TestCacheWarming:
    """/healthz at N ∈ {10, 100, 500, 1000} rps.

    Proves BOB-112's TTL cache holds: cached-path p50 stays roughly
    constant across rps. RED capture (:9117 upstream) shows the
    latency the cache is protecting against.
    """

    def _burst(self, url: str, path: str, n: int) -> tuple[float, list[float], int]:
        latencies_ms: list[float] = []
        ok = 0

        def _one():
            t0 = time.perf_counter()
            try:
                r = requests.get(url + path, timeout=10.0)
                dt = (time.perf_counter() - t0) * 1000.0
                return (r.status_code, dt)
            except requests.RequestException:
                return (0, (time.perf_counter() - t0) * 1000.0)

        start = time.perf_counter()
        # BOB-109 host safety (§12.6/§12.12): was min(n, 128). On this
        # 8-core host that drove loadavg to 40 during a full-suite run —
        # far past the 30-40% of host resources tests are allowed, on a
        # box shared with sibling agents. 16 keeps the burst genuinely
        # concurrent (2x cores) without wedging the workstation; the
        # burst still issues all n requests, just through a bounded
        # pool.
        workers = min(n, 16)
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for status, dt_ms in ex.map(lambda _: _one(), range(n)):
                latencies_ms.append(dt_ms)
                if status == 200 or status == 302:
                    ok += 1
        wall = time.perf_counter() - start
        return wall, latencies_ms, ok

    @pytest.mark.timeout(120)
    @pytest.mark.parametrize("n_req", [10, 100, 500, 1000])
    def test_healthz_cache_holds_under_burst(self, n_req: int):
        matrix_path = EVIDENCE_DIR / "cache_warming_matrix.json"
        matrix: dict = {}
        if matrix_path.exists():
            matrix = json.loads(matrix_path.read_text())

        # Warm the cache first so we measure the warm-cache path
        # (§11.4.6 — we are measuring the invariant this axis claims).
        requests.get(JACKETT_BOBA_URL + "/healthz", timeout=5.0)

        wall, lats, ok = self._burst(JACKETT_BOBA_URL, "/healthz", n_req)
        matrix[str(n_req)] = {
            "verdict": "PASS"
            if (ok >= n_req * 0.98 and statistics.median(lats) < 500.0)
            else "FAIL",
            "n_req": n_req,
            "wall_s": round(wall, 3),
            "ok": ok,
            "ok_rate": round(ok / n_req, 4),
            "latency_ms_p50": round(statistics.median(lats), 3),
            "latency_ms_p95": round(
                statistics.quantiles(lats, n=20)[18]
                if len(lats) >= 20
                else max(lats),
                3,
            ),
            "throughput_req_per_s": round(ok / wall, 2),
        }
        _emit_evidence("cache_warming_matrix.json", matrix)

        assert ok >= n_req * 0.98, (
            f"/healthz drop-rate too high at N={n_req}: ok={ok}/{n_req}"
        )
        # p50 MUST stay well under the upstream-bypass path (RED
        # capture below shows Jackett upstream at ~450-1000ms p50 at
        # the same N). A 500ms ceiling catches a cache-broken
        # regression without flaking on host jitter at 1000 concurrent.
        p50 = matrix[str(n_req)]["latency_ms_p50"]
        assert p50 < 500.0, f"/healthz p50 collapsed at N={n_req}: p50={p50}ms"

    @pytest.mark.timeout(60)
    def test_red_capture_cache_bypass_shows_upstream_latency(self):
        """§11.4.115 RED capture: bypass the cache by hitting upstream
        Jackett directly.

        This is equivalent to disabling the BOB-112 TTL cache (setting
        TTL=0 would make every /healthz call take the upstream path).
        The captured evidence shows the upstream latency-per-call and
        aggregate throughput ceiling the cache is protecting against.

        A PASS here means the cache-bypass path is measurably slower
        than the cache-hit path at the same N — the load-bearing
        property of the cache.
        """
        n_req = 200

        # GREEN — cached path
        requests.get(JACKETT_BOBA_URL + "/healthz", timeout=5.0)
        green_wall, green_lats, green_ok = self._burst(
            JACKETT_BOBA_URL, "/healthz", n_req
        )
        green_p50 = statistics.median(green_lats)

        # RED — direct upstream (Jackett), the path /healthz would take
        # if the TTL cache were disabled or set to TTL=0.
        red_wall, red_lats, red_ok = self._burst(
            JACKETT_UPSTREAM_URL, "/UI/Dashboard", n_req
        )
        red_p50 = statistics.median(red_lats)

        evidence = {
            "verdict": "PASS"
            if statistics.median(green_lats) < statistics.median(red_lats)
            else "FAIL",
            "n_req": n_req,
            "cached_path": {
                "url": f"{JACKETT_BOBA_URL}/healthz",
                "wall_s": round(green_wall, 3),
                "ok": green_ok,
                "p50_ms": round(green_p50, 3),
                "throughput_req_per_s": round(green_ok / green_wall, 2),
            },
            "upstream_bypass_path": {
                "url": f"{JACKETT_UPSTREAM_URL}/UI/Dashboard",
                "wall_s": round(red_wall, 3),
                "ok": red_ok,
                "p50_ms": round(red_p50, 3),
                "throughput_req_per_s": round(red_ok / red_wall, 2),
            },
            "speedup_ratio_p50": round(red_p50 / max(green_p50, 0.001), 2),
            "throughput_ratio": round(
                (green_ok / green_wall) / max(red_ok / red_wall, 0.001), 2
            ),
        }
        _emit_evidence("red_cache_bypass.json", evidence)

        # Anti-bluff: the cached path MUST be measurably faster p50.
        # If not, either the cache is broken OR the upstream is
        # instant — either way the axis measurement is void and this
        # test SHOULD fail.
        assert green_p50 < red_p50, (
            "cached /healthz should be faster than upstream Jackett bypass: "
            f"cached_p50={green_p50:.3f}ms vs upstream_p50={red_p50:.3f}ms"
        )
