"""Shared harness for the DDoS-class test type (BOB-074 / §11.4.27(B), §11.4.169).

WHY A SEPARATE TYPE (and what it deliberately does NOT re-test).
`tests/unit/test_rate_limit.py` proves slowapi works on a SYNTHETIC FastAPI app.
`tests/security/test_rate_limit_public_endpoints.py` proves the REAL app's
routes carry the limiter at their CONFIGURED thresholds. Both answer "is the
limiter wired and correct?". Neither answers the DDoS question, which is about
ABUSE RESILIENCE rather than threshold correctness:

  * does a burst get REFUSED rather than SERVED, with no 5xx leaking out?
  * does the service SURVIVE the burst — still answering afterwards, and still
    answering OTHER callers during it (no collateral denial of service)?
  * does one slow/abusive client BLOCK everyone else (head-of-line blocking)?
  * is an oversized payload REFUSED before it is processed?
  * does the resource-exhaustion admission control actually engage?

Those five are the §11.4.27(B) "ddos tests" category. They are asserted here on
OBSERVABLE OUTCOMES ONLY (status-code populations, response bodies, post-attack
liveness, completion ordering) — never "no exception was raised" (§11.4/§11.4.1).

EVIDENCE CLASS (§11.4.226): RUNTIME-ON-THE-REAL-ASGI-APP. Every test drives the
real `api.app` through the real middleware stack, the real routers and the real
slowapi decorators, in-process. It is NOT a live-socket test — see
`docs/TESTING.md` "DDoS tests" for the honest list of what that cannot cover
(TCP-level slowloris, kernel accept queues, real multi-host traffic) and which
layer covers it instead (`challenges/scripts/ddos_resilience_challenge.sh`).

HOST SAFETY (§12, §12.6, §12.11, CLAUDE.md Mandatory Standard 9). This host runs
live containers and parallel agents; resource exhaustion here has previously
caused forced logouts. Therefore EVERY bound in this package is explicit and
small, and NOTHING here may be raised without re-justifying it:

  * NO live stack is ever touched. No socket is opened. No request ever reaches
    127.0.0.1:7187 (or any port). The ASGI app is driven in-process.
  * Total requests are CAPPED per test by the constants below — the largest
    single burst is `MAX_BURST_REQUESTS` (24). There is no unbounded loop, no
    "flood until it breaks", and no wall-clock-driven ramp anywhere.
  * The tracker fan-out is neutralised (see `_no_real_tracker_fanout`), so no
    test can emit traffic at RuTracker/Kinozal/NNMClub or spawn nova3 plugin
    subprocesses.
  * Concurrency is capped at `MAX_CONCURRENT_CLIENTS` (5) coroutines on ONE
    event loop — no thread pool, no process pool.
  * The largest allocation is `OVERSIZE_UPLOAD_BYTES` (~10 MiB), sized to cross
    the production 10 MiB guard by the smallest margin that proves the point.

§11.4.263: no subprocess or proc object is mocked in this package, so no
`mock.pid` is involved anywhere; the fan-out stub is a plain async function.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: Which production source tree to import the app from.
#:
#: Defaults to the real one. `mutations/run_mutation_check.sh` overrides it with
#: a MUTATED COPY so the paired §1.1 mutations never touch the shared checkout:
#: this repository is worked by several agents at once, and a mutation applied
#: in place can be swept into someone else's `git add` before it is restored —
#: the §11.4.84 working-tree-quiescence failure that once shipped a bypassed
#: JWT verify. Copy-and-point is the only mutation strategy that is safe here.
_SRC_PATH = os.environ.get("BOBA_DDOS_SRC_PATH") or os.path.join(_REPO_ROOT, "download-proxy", "src")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)


# ---------------------------------------------------------------------------
# HOST-SAFETY BOUNDS (§12.6/§12.11). Every number here is a hard cap that the
# tests read — none of them is a "target" a test may exceed. Raising any of
# them requires re-justifying the host budget in docs/TESTING.md.
# ---------------------------------------------------------------------------

#: Largest number of requests any single test may issue. 24 is ~4x the smallest
#: limit used below, which is enough to prove "refused, not served" with a clear
#: margin while staying trivially cheap in-process.
MAX_BURST_REQUESTS = 24

#: Largest number of concurrent in-flight clients (coroutines on one loop).
MAX_CONCURRENT_CLIENTS = 5

#: How long a deliberately-slow request holds the handler. Small enough to keep
#: every test far under the 60s pytest timeout, large enough to be unambiguously
#: distinguishable from the sub-millisecond fast path.
SLOW_REQUEST_DELAY_S = 0.4

#: Cap on the bystander liveness probes issued WHILE a slow request is in
#: flight. The probes must SPAN the slow window (a handful fired back-to-back
#: all land in the first few milliseconds and would miss a blocking section
#: entirely — the exact bluff the M5 mutation exposed), so they are paced by
#: `LIVENESS_PROBE_INTERVAL_S` and bounded by this cap. Each probe is a
#: sub-millisecond in-process GET /health with no I/O, so 60 of them is
#: negligible next to the 24-request bursts elsewhere in this package.
MAX_LIVENESS_PROBES = 60

#: Spacing between those probes. 20ms over a ~0.4-0.8s slow window yields
#: enough samples that several necessarily land inside any blocking section.
LIVENESS_PROBE_INTERVAL_S = 0.02

#: Production refuses .torrent uploads above 10 MiB
#: (`download-proxy/src/api/routes.py:_MAX_TORRENT_UPLOAD_BYTES`). We cross that
#: line by 4 KiB — the smallest margin that proves the guard, so the test costs
#: ~10 MiB of transient RSS and not more.
OVERSIZE_UPLOAD_BYTES = 10 * 1024 * 1024 + 4096

#: Oversized JSON search body. 256 KiB is bounded and ample: `SearchRequest.query`
#: declares no `max_length`, so this documents real behaviour without allocating
#: megabytes per test.
OVERSIZE_QUERY_BYTES = 256 * 1024


def pytest_configure(config: pytest.Config) -> None:
    """Register the `ddos` marker locally.

    `pyproject.toml` runs with `--strict-markers` and is owned elsewhere, so the
    marker is registered here rather than by editing shared config.
    """
    config.addinivalue_line("markers", "ddos: DDoS-class abuse-resilience test (§11.4.27(B))")


def purge_api_modules() -> None:
    """Drop every `api*` module so the next import re-executes them in order.

    `importlib.reload(api)` is NOT sufficient and is actively harmful:
    reloading the package does not reload the cached `api.routes` submodule, so
    production routes stay bound to the PREVIOUS generation's Limiter while the
    middleware consults the new one. The stale limiter keeps enforcing its
    already-exhausted counters, producing blanket false-positive 429s
    (§11.4.201(1)) — which in a DDoS test would look exactly like "the limiter
    is working". Purging is the deterministic fix: one generation, one limiter,
    one set of counters. Documented in `api/rate_limit.py` "RELOAD HAZARD".
    """
    for name in [m for m in sys.modules if m == "api" or m.startswith("api.")]:
        del sys.modules[name]


def build_app(
    *,
    search: str = "6/minute",
    dashboard: str = "6/minute",
    sse: str = "6/minute",
    default: str = "200/minute",
    disabled: bool = False,
    trust_forwarded_for: bool = True,
):
    """Import the REAL production app with the given limits in force.

    Limits are injected through the SAME public env knobs an operator uses
    (`RATE_LIMIT_*`), so a test also proves those knobs are wired. Returns
    `(api_module, rate_limit_module)`.

    `trust_forwarded_for` sets the production `TRUST_FORWARDED_FOR` knob that
    `api.rate_limit._client_key` reads. Without it the limiter keys on
    `request.client.host`, which for an in-process ASGI client is the SAME
    constant for every caller — so "attacker" and "bystander" would collapse
    into one bucket and the per-client isolation assertion would be vacuous.
    Turning it on is what makes distinct simulated clients meaningful here (and
    incidentally proves that knob is wired).
    """
    os.environ["TRUST_FORWARDED_FOR"] = "1" if trust_forwarded_for else "0"
    if disabled:
        os.environ["RATE_LIMIT_DISABLED"] = "1"
    else:
        os.environ.pop("RATE_LIMIT_DISABLED", None)
    os.environ["RATE_LIMIT_SEARCH"] = search
    os.environ["RATE_LIMIT_DASHBOARD"] = dashboard
    os.environ["RATE_LIMIT_SSE_STREAM"] = sse
    os.environ["RATE_LIMIT_DEFAULT"] = default

    purge_api_modules()
    api_mod = importlib.import_module("api")
    rl_mod = importlib.import_module("api.rate_limit")
    # Counters must start empty even if a sibling module generation ran earlier
    # in this pytest session (§11.4.14 quiescent baseline).
    rl_mod.reset_counters()
    return api_mod, rl_mod


@pytest.fixture(autouse=True)
def _no_real_tracker_fanout(monkeypatch):
    """Neutralise the background tracker fan-out.

    HOST SAFETY + §11.4.27(A) isolation boundary. Un-stubbed, every accepted
    search spawns a real `asyncio.create_subprocess_exec` nova3 child and fires
    real HTTP at third-party trackers — in a burst test that is precisely the
    off-host damage no localhost budget can bound, and it would risk IP bans on
    shared trackers. The fan-out is DOWNSTREAM of every mechanism under test
    here (limiter, admission control, payload guard), so stubbing it removes no
    assertion. monkeypatch restores the real method after every test (§11.4.14).
    """
    from merge_service.search import SearchOrchestrator

    async def _no_fanout(self, search_id, query, category="all"):  # noqa: ANN001
        metadata = self._active_searches.get(search_id)
        if metadata is not None:
            metadata.status = "completed"

    monkeypatch.setattr(SearchOrchestrator, "_run_search", _no_fanout)


@pytest.fixture(autouse=True)
def _isolate_env():
    """Restore every knob this package writes, then purge the app modules.

    Without the purge a later test in the same session would inherit this
    package's tiny limits on a cached module generation.
    """
    keys = ("RATE_LIMIT_", "MAX_CONCURRENT_SEARCHES", "TRUST_FORWARDED_FOR")
    saved = {k: v for k, v in os.environ.items() if k.startswith(keys)}
    yield
    for k in [k for k in os.environ if k.startswith(keys)]:
        os.environ.pop(k, None)
    os.environ.update(saved)
    purge_api_modules()
