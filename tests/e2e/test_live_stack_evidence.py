"""Fully-automated E2E tests driving the LIVE merge-search stack.

These tests hit the real running merge service over HTTP (no human in the
loop, re-runnable per §11.4.98) and capture REAL physical evidence under
``docs/qa/<run-id>/`` per §11.4.83. Every assertion targets a
user-observable outcome (response-body fields the dashboard / a real
client would consume) — not merely status codes.

Determinism note (§11.4 anti-bluff, no false-result risk):
External public trackers are flaky by nature. We therefore assert ONLY
deterministic facts:

* the pipeline genuinely completes and returns a non-empty merged set,
* AT LEAST ONE tracker reports ``status == "success"`` with rows
  (the end-to-end fan-out really works), and
* the configured private tracker (iptorrents) authenticated.

We never pin a SPECIFIC flaky public tracker's result count — that would
be a false-result risk. If the live service is unreachable, every test
SKIPs with a reason (§11.4.3); we never fake-pass.

Run-id: e2e-live-20260606
Evidence dir: docs/qa/e2e-live-20260606/
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import time
from pathlib import Path

import pytest
import requests

MERGE_SERVICE_URL = os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187").rstrip("/")
RUN_ID = "e2e-live-20260606"
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "docs" / "qa" / RUN_ID
SEARCH_TIMEOUT = 300.0

pytestmark = pytest.mark.timeout(420)


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


def _wait_for_idle(max_wait: float = 180.0) -> None:
    """Block until the orchestrator reports zero active searches so this
    test's evidence isn't contaminated by a concurrent fan-out."""
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{MERGE_SERVICE_URL}/api/v1/stats", timeout=10)
            if r.status_code == 200 and r.json().get("active_searches", 0) == 0:
                return
        except Exception:
            pass
        time.sleep(2)
    # Don't hard-fail on a busy service; the search call itself retries.


# §11.4.69 CM-NO-FAIL-OPEN-SKIP: the closed set of `error_type` values that
# are DEFINITIVE product-side failures — our own credentials were rejected,
# our own container is missing a required path, or our own plugin broke.
# None of these can honestly be reported as "a transient upstream outage",
# so a test MUST NOT convert them into a PASS-counting SKIP.
# Vocabulary grounded in download-proxy/src/merge_service/search.py
# (_classify_plugin_failure), read 2026-08-21 — not invented (§11.4.6).
DEFINITIVE_AUTH_FAILURE_TYPES = frozenset(
    {
        "upstream_http_403",        # credentials rejected by upstream
        "plugin_env_missing",       # container lacks a path the plugin needs
        "plugin_crashed",           # our plugin raised
        "plugin_parse_failure",     # our plugin could not parse upstream
        "plugin_bad_query_encoding",  # our plugin did not URL-encode
    }
)

# Genuinely transient / network-side conditions. These remain honestly
# skippable — the §11.4.201(1) false-positive guard: hardening the
# definitive classes must NOT turn a real outage into a false FAIL.
TRANSIENT_AUTH_FAILURE_TYPES = frozenset(
    {
        "deadline_timeout",
        "upstream_timeout",
        "dns_failure",
        "tls_failure",
        "upstream_incomplete",
        "upstream_http_404",  # upstream domain moved — upstream-side, not ours
    }
)


def _auth_failure_is_definitive(stat: dict) -> bool:
    """True when a tracker stat carries a DEFINITIVE product-side failure.

    §11.4.6: an `error_type` outside BOTH closed sets is UNKNOWN, not
    "transient" — we return False (conservative-safe, still skippable per
    §11.4.101) but the caller states the unresolved signal honestly rather
    than asserting "transient outage" as a fact it has not established.
    """
    return stat.get("error_type") in DEFINITIVE_AUTH_FAILURE_TYPES


@pytest.fixture(scope="module")
def live_url() -> str:
    if not _service_reachable():
        pytest.skip(  # SKIP-OK: live service unreachable, §11.4.3
            f"merge service not reachable at {MERGE_SERVICE_URL}/health — "
            "start the stack to run live E2E tests (no fake-pass)."
        )
    return MERGE_SERVICE_URL


@pytest.fixture(scope="module")
def debian_search(live_url: str) -> dict:
    """Run ONE real ``debian`` sync search; reuse across assertions."""
    _wait_for_idle()
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{live_url}/api/v1/search/sync",
                json={"query": "debian", "limit": 5},
                timeout=SEARCH_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 - retry on transient errors
            last_err = exc
            time.sleep(3 * (attempt + 1))
            continue
        if resp.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    pytest.skip(  # SKIP-OK: queue saturated / transient, §11.4.3
        f"could not obtain a debian search result after retries: {last_err}"
    )


# --------------------------------------------------------------------------- #
# 1. /health
# --------------------------------------------------------------------------- #
def test_health_reports_healthy(live_url: str) -> None:
    resp = requests.get(f"{live_url}/health", timeout=10)
    body = resp.json()
    _save_evidence("health.json", body)
    assert resp.status_code == 200
    # User-observable: a real dashboard reads status=="healthy" to decide
    # whether the merge service is up.
    assert body.get("status") == "healthy", f"health body: {body!r}"
    assert body.get("service"), "health body missing service identity"


# --------------------------------------------------------------------------- #
# 2. Full pipeline: debian search genuinely works end-to-end
# --------------------------------------------------------------------------- #
def test_debian_search_completes_with_real_results(debian_search: dict) -> None:
    path = _save_evidence("search_debian.json", debian_search)
    assert path.exists()

    # User-observable: the search completed and produced results a real
    # client would render.
    assert debian_search.get("status") == "completed", (
        f"search status={debian_search.get('status')!r} (expected 'completed')"
    )
    total = debian_search.get("total_results", 0)
    assert total > 0, f"total_results={total} — pipeline produced nothing"

    results = debian_search.get("results") or debian_search.get("merged_results") or []
    assert results, "no result objects in body — nothing to render for the user"

    # User-observable result object shape: a card needs a name, a size,
    # a tracker label, and a usable link (download_urls / desc_link).
    first = results[0]
    assert first.get("name"), f"result missing name: {first!r}"
    assert first.get("size"), f"result missing size: {first!r}"
    assert first.get("tracker"), f"result missing tracker: {first!r}"
    link = first.get("download_urls") or first.get("desc_link") or first.get("link")
    assert link, f"result has no usable link/download_urls: {first!r}"


def test_debian_search_has_a_genuinely_successful_tracker(debian_search: dict) -> None:
    """At least ONE tracker must report status=='success' WITH rows — proves
    the fan-out genuinely reached an upstream and parsed real results, not
    just that the orchestrator returned 200."""
    stats = debian_search.get("tracker_stats", [])
    assert stats, "no tracker_stats — API contract broken"
    successful = [
        t for t in stats if t.get("status") == "success" and t.get("results_count", 0) > 0
    ]
    _save_evidence(
        "search_debian_successful_trackers.json",
        [
            {"name": t["name"], "status": t["status"], "results_count": t["results_count"]}
            for t in successful
        ],
    )
    assert successful, (
        "No tracker returned status=='success' with results for 'debian'. "
        "Either every upstream is down (wide outage) or the capture pipeline "
        f"is broken. Stats: {[(t['name'], t.get('status'), t.get('results_count')) for t in stats][:15]}"
    )
    # User-observable: the query round-trips into every fan-out task.
    for t in stats:
        assert t.get("query") == "debian", (
            f"tracker {t.get('name')!r} recorded query={t.get('query')!r}"
        )


# --------------------------------------------------------------------------- #
# 3. Credentialed path: iptorrents authenticated (deterministic)
# --------------------------------------------------------------------------- #
def test_iptorrents_is_authenticated_in_search(debian_search: dict) -> None:
    """IPTorrents is a configured private tracker; the orchestrator logs in
    with the .env creds. We assert it authenticated. If it was momentarily
    down (status not success AND not authenticated), we SKIP — never fail on
    a transient upstream outage."""
    ipt = next(
        (t for t in debian_search.get("tracker_stats", []) if t.get("name") == "iptorrents"),
        None,
    )
    if ipt is None:
        pytest.skip(  # SKIP-OK: iptorrents not in fan-out this run, §11.4.3
            "iptorrents absent from tracker_stats — not configured this run."
        )
    _save_evidence(
        "iptorrents_stat.json",
        {k: ipt.get(k) for k in ("name", "status", "authenticated", "results_count", "error", "error_type")},
    )
    if not ipt.get("authenticated") and ipt.get("status") != "success":
        # §11.4.69 CM-NO-FAIL-OPEN-SKIP (BOB-092, extend-to-all-cases
        # §11.4.146): the OLD code skipped unconditionally here and asserted
        # "transient outage" as a fact. That is a fail-open: rejected
        # credentials (upstream_http_403) and a broken container
        # (plugin_env_missing) are DEFINITIVE product failures and were
        # being reported as a PASS-counting SKIP.
        if _auth_failure_is_definitive(ipt):
            pytest.fail(
                f"iptorrents auth failed DEFINITIVELY: error_type="
                f"{ipt.get('error_type')!r}, status={ipt.get('status')!r}, "
                f"error={ipt.get('error')!r}. This is a product-side failure "
                "(credentials rejected / container or plugin broken), not a "
                "transient upstream outage — §11.4.69 forbids skipping it."
            )
        if ipt.get("error_type") in TRANSIENT_AUTH_FAILURE_TYPES:
            pytest.skip(  # SKIP-OK: proven-transient upstream condition, §11.4.3
                f"iptorrents transient upstream condition error_type="
                f"{ipt.get('error_type')!r} (error={ipt.get('error')!r})."
            )
        pytest.skip(  # SKIP-OK: signal unresolved, conservative-safe §11.4.101
            f"UNKNOWN: iptorrents not authenticated, status={ipt.get('status')!r}, "
            f"error_type={ipt.get('error_type')!r} is in neither the definitive "
            "nor the transient closed set — cannot classify (§11.4.6), so this "
            "is NOT reported as a transient outage."
        )
    # User-observable: the dashboard chip shows iptorrents as authenticated.
    assert ipt.get("authenticated") is True, (
        f"iptorrents authenticated={ipt.get('authenticated')!r} despite being configured. "
        f"status={ipt.get('status')!r}, error={ipt.get('error')!r}"
    )


# --------------------------------------------------------------------------- #
# 4. /api/v1/auth/status structure
# --------------------------------------------------------------------------- #
def test_auth_status_lists_all_configured_trackers(live_url: str) -> None:
    resp = requests.get(f"{live_url}/api/v1/auth/status", timeout=15)
    body = resp.json()
    _save_evidence("auth_status.json", body)
    assert resp.status_code == 200

    trackers = body.get("trackers", {})
    # User-observable: the auth panel renders one row per tracker. The
    # structure (which trackers exist + session presence) is deterministic.
    for name in ("rutracker", "iptorrents", "nnmclub", "kinozal"):
        assert name in trackers, f"auth/status missing {name!r}: keys={sorted(trackers)}"
        entry = trackers[name]
        assert "has_session" in entry, f"{name} entry missing has_session: {entry!r}"
        assert isinstance(entry["has_session"], bool), (
            f"{name} has_session must be bool, got {type(entry['has_session'])}"
        )


# --------------------------------------------------------------------------- #
# 5. BOB-006: /api/v1/auth/nnmclub/status
# --------------------------------------------------------------------------- #
def test_nnmclub_status_endpoint(live_url: str) -> None:
    """BOB-006 added GET /api/v1/auth/nnmclub/status returning a JSON body
    with an ``authenticated`` field.

    BOB-092 (2026-08-19): the earlier SKIP-on-404 fallback for a stale
    container was removed after verifying the live endpoint returns 200
    (see docs/qa/2026-08-19-bob-092/). Drift back to 404 now produces a
    hard FAIL (§11.4.108 layer-3 runtime-signature) instead of a silent
    SKIP that could hide a regression (§11.4.238 automated-QA-discovers)."""
    resp = requests.get(f"{live_url}/api/v1/auth/nnmclub/status", timeout=15)
    body = resp.json()
    _save_evidence("nnmclub_status.json", body)
    assert resp.status_code == 200, f"unexpected status {resp.status_code}: {resp.text[:200]}"
    # User-observable: the nnmclub auth panel reads the authenticated flag.
    assert "authenticated" in body, f"nnmclub/status body missing 'authenticated': {body!r}"
    assert isinstance(body["authenticated"], bool), (
        f"authenticated must be bool, got {type(body['authenticated'])}"
    )


# --------------------------------------------------------------------------- #
# 6. /api/v1/config derives qbittorrent_url from Host header (CONST-XII)
# --------------------------------------------------------------------------- #
def test_config_qbittorrent_url_derives_from_host_header(live_url: str) -> None:
    """CONST-XII: no hardcoded localhost in client-facing URLs. The
    qbittorrent_url returned to a browser MUST derive from the request
    Host header. Send a custom Host and assert the returned URL reflects
    it (and is NOT localhost)."""
    custom_host = "boba.example.com:9999"
    resp = requests.get(
        f"{live_url}/api/v1/config",
        headers={"Host": custom_host},
        timeout=15,
    )
    body = resp.json()
    _save_evidence("config_custom_host.json", {"request_host": custom_host, "response": body})
    assert resp.status_code == 200

    qbit_url = body.get("qbittorrent_url", "")
    # User-observable: the browser is handed a URL it can actually reach,
    # derived from how the client addressed the service — not localhost.
    assert "boba.example.com" in qbit_url, (
        f"qbittorrent_url={qbit_url!r} did not derive from Host {custom_host!r} "
        "(CONST-XII no-hardcoded-localhost violation)."
    )
    assert "localhost" not in qbit_url and "127.0.0.1" not in qbit_url, (
        f"qbittorrent_url={qbit_url!r} leaked a hardcoded localhost despite a "
        "custom Host header (CONST-XII violation)."
    )


# --------------------------------------------------------------------------- #
# 7. SSE: async search stream emits real lifecycle events
# --------------------------------------------------------------------------- #
def test_sse_stream_emits_lifecycle_events(live_url: str) -> None:
    """POST /api/v1/search returns a search_id + stream_token; opening
    GET /api/v1/search/stream/{id}?token=... must deliver real SSE frames
    (search_start / tracker_started / search_complete). We read a short
    window and assert a lifecycle event arrived — completed-tolerant."""
    _wait_for_idle()
    start = requests.post(
        f"{live_url}/api/v1/search",
        json={"query": "debian", "limit": 3},
        timeout=30,
    )
    start.raise_for_status()
    meta = start.json()
    search_id = meta.get("search_id")
    token = meta.get("stream_token")
    assert search_id, f"POST /search did not return search_id: {meta!r}"
    assert token, f"POST /search did not return stream_token: {meta!r}"

    frames: list[str] = []
    events: set[str] = set()
    try:
        with requests.get(
            f"{live_url}/api/v1/search/stream/{search_id}",
            params={"token": token},
            stream=True,
            timeout=(10, 20),
            headers={"Accept": "text/event-stream"},
        ) as sse:
            assert sse.status_code == 200, f"SSE returned {sse.status_code}"
            deadline = time.monotonic() + 20
            for raw in sse.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                frames.append(raw)
                if raw.startswith("event:"):
                    events.add(raw.split(":", 1)[1].strip())
                # Stop once the stream is proven alive with multiple
                # lifecycle events (or the search completed) — collect a
                # richer sample than a bare search_start for evidence.
                if "search_complete" in events:
                    break
                if len(events) >= 2 and len(frames) >= 6:
                    break
                if time.monotonic() > deadline:
                    break
    except requests.exceptions.ReadTimeout:
        # A quiet window is acceptable as long as we already saw frames.
        pass

    _save_evidence("sse_frames_sample.txt", "\n".join(frames[:60]))
    _save_evidence("sse_events_observed.json", sorted(events))

    # User-observable: a browser EventSource client receives real lifecycle
    # events that drive the live progress UI.
    assert frames, "SSE stream produced no frames — live progress UI would be blank"
    assert {"search_start", "tracker_started", "search_complete"} & events, (
        f"no recognised SSE lifecycle event arrived; events seen: {sorted(events)}, "
        f"first frames: {frames[:6]}"
    )


# --------------------------------------------------------------------------- #
# 8. BOB-092 — §11.4.69 CM-NO-FAIL-OPEN-SKIP guards
# --------------------------------------------------------------------------- #
def _module_ast() -> ast.Module:
    """Parse THIS module's own source for structural inspection.

    §11.4.201(7)(a): match STRUCTURE, not substring. A grep for "404"
    matches this comment; an AST walk cannot be fooled by a carrier, and a
    rename/reword mutation still trips the guard (so it is not the
    tautological string-deletion mutation §11.4.115(F) refuses).
    """
    return ast.parse(inspect.getsource(__import__(__name__, fromlist=["_"])))


def _func_node(name: str) -> ast.FunctionDef:
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found in module AST")


def _skip_calls(node: ast.AST) -> list[ast.Call]:
    out = []
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "skip"
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "pytest"
        ):
            out.append(sub)
    return out


def _mentions_status_code(node: ast.AST) -> bool:
    """True if this subtree reads an HTTP status code."""
    return any(
        isinstance(sub, ast.Attribute) and sub.attr == "status_code"
        for sub in ast.walk(node)
    )


def test_guard_nnmclub_status_test_has_no_fail_open_skip() -> None:
    """BOB-092 PERMANENT REGRESSION GUARD (§11.4.135).

    The fix that removed the SKIP-on-404 landed at commit 7baef2b with NO
    guard, and the only test covering it needs the LIVE STACK — so with the
    stack down a re-introduced fail-open would be invisible. This guard is
    live-stack-INDEPENDENT and fails the moment the fail-open returns.

    §11.4.69 reasoning: a 404 is a RESPONSE, so the host was reachable and
    `network_unreachable_external` is definitionally false. No other member
    of the closed reason set fits either — the service is our own, on the
    configured port, with the route declared in source. A 404 is therefore a
    real §11.4.108 SOURCE->ARTIFACT deployment drift and MUST hard-FAIL.
    """
    fn = _func_node("test_nnmclub_status_endpoint")
    offenders = _skip_calls(fn)
    assert not offenders, (
        "BOB-092 REGRESSION: test_nnmclub_status_endpoint contains "
        f"{len(offenders)} pytest.skip() call(s) at line(s) "
        f"{[c.lineno for c in offenders]}. A non-200 from our own service is a "
        "real product failure (§11.4.108 drift) and must FAIL, never SKIP "
        "(§11.4.69 CM-NO-FAIL-OPEN-SKIP)."
    )


def test_guard_no_skip_is_conditioned_on_an_http_status_code() -> None:
    """Class-wide guard (§11.4.146 extend-to-all-cases).

    A received HTTP status code proves the host ANSWERED. Branching on one
    to decide to SKIP is the BOB-092 fail-open shape wherever it appears, so
    no `if <...>.status_code ...:` block in this module may contain a skip.
    """
    offenders: list[tuple[int, int]] = []
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.If) and _mentions_status_code(node.test):
            for call in _skip_calls(node):
                offenders.append((node.lineno, call.lineno))
    assert not offenders, (
        "fail-open detected: skip() reached from an HTTP-status-code branch at "
        f"(if_line, skip_line)={offenders}. The host responded, so no closed-set "
        "§11.4.69 reason applies — this must FAIL, not SKIP."
    )


def test_guard_legitimate_topology_skip_is_preserved() -> None:
    """GOLDEN-FALSE / §11.4.201(1) false-positive guard.

    Hardening the fail-open must NOT turn every legitimate skip into a false
    FAIL. A genuinely UNREACHABLE host (connection refused — no response at
    all) and a genuinely absent tracker are honest §11.4.3 topology skips and
    MUST remain skips. If a future 'hardening' deletes them, this fails.
    """
    unreachable = _func_node("live_url")
    assert _skip_calls(unreachable), (
        "live_url fixture no longer SKIPs when the service is unreachable. An "
        "unreachable host yields NO response — that is an honest topology skip "
        "(§11.4.3), not a product failure. Removing it is a §11.4.201(1) "
        "false-positive refusal."
    )
    assert not _mentions_status_code(unreachable), (
        "live_url's skip must stay conditioned on reachability, not on a "
        "status code (a status code means the host answered)."
    )

    absent = _func_node("test_iptorrents_is_authenticated_in_search")
    assert _skip_calls(absent), (
        "the iptorrents test must retain an honest skip for the "
        "not-configured / proven-transient cases (§11.4.201(1))."
    )


def test_definitive_auth_failure_is_not_skipped() -> None:
    """A tracker whose sink-side probe reports a DEFINITIVE product-side
    failure MUST NOT be skipped as a 'transient outage' (§11.4.69)."""
    assert _auth_failure_is_definitive({"error_type": "upstream_http_403"}) is True
    assert _auth_failure_is_definitive({"error_type": "plugin_env_missing"}) is True


def test_transient_outage_is_still_skipped() -> None:
    """GOLDEN-FALSE (§11.4.201(1)): a genuinely transient upstream
    condition must still be skippable, not turned into a false FAIL."""
    assert _auth_failure_is_definitive({"error_type": "upstream_timeout"}) is False
    assert _auth_failure_is_definitive({"error_type": "dns_failure"}) is False
