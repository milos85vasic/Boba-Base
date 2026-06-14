"""LIVE credential-validity guard for the stored private-tracker logins.

Anti-bluff rationale (§11.4 / §11.4.10 / §11.4.68 / §11.4.69)
------------------------------------------------------------
This test proves the *stored* private-tracker credentials genuinely WORK
by driving a REAL search through the running merge service (port 7187) and
asserting each tracker's REAL authentication state.

The assertion under test is the ``authenticated`` boolean the merge
service returns in ``tracker_stats`` *for each tracker after it actually
attempted a login + search against the live upstream*. That flag is NOT a
tautology: it is set to ``True`` only when the proxy container's stored
credentials successfully authenticated to the real tracker. If a stored
credential is wrong, expired, or revoked, the upstream login fails and the
merge service reports ``authenticated=False`` — and this test FAILS. There
is no mock, no fixture, no stub in the auth path: the search hits the real
RuTracker / Kinozal / NNMClub / IPTorrents over the network with the
exact secrets held by the proxy. A green run therefore means "an end user
can log in to these trackers with what we have stored", which is the only
thing that matters.

SECURITY (§11.4.10 — non-negotiable)
------------------------------------
This test NEVER reads, prints, or logs any credential value. The proxy
container holds the secrets; the test reads ONLY the ``authenticated``
boolean (and ``status`` / ``results_count`` / ``error``) the merge service
returns. It does not touch ``.env``, does not exec into the container, and
needs zero credential values to do its job.

HONEST SKIP (§11.4.3 — never a fake PASS)
-----------------------------------------
* Merge service unreachable  -> ``pytest.skip`` (1 s probe; never boots).
* A PRIVATE tracker reporting ``authenticated=False`` whose ``error``
  mentions captcha / timeout / temporarily / rate-limit / unreachable /
  deadline -> ``pytest.skip`` with that reason. RuTracker cookies expire
  periodically and CAPTCHA / transient upstream faults are operator-blocked,
  not a credential defect (see CLAUDE.md).
* Otherwise, a PRIVATE tracker with ``authenticated=False`` is a genuine
  FAIL — the stored credential is bad/expired.
* A credentialed tracker entirely ABSENT from ``tracker_stats`` is a FAIL:
  the search did not run it.

Run (host python3 is 3.9 and cannot collect this suite; use the venv)::

    cd /Volumes/T7/Projects/Boba
    .venv/bin/python -m pytest tests/integration/test_tracker_auth_live.py \
        -v --import-mode=importlib -p no:cacheprovider
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import pytest

# base = MERGE_SERVICE_URL or the default localhost:7187 (per CLAUDE.md port map).
MERGE_BASE = os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187").rstrip("/")

QUERY = "ubuntu"
LIMIT = 50

# Terminal poll states the merge service uses for a finished search.
_TERMINAL_STATES = {"completed", "no_results"}

# Poll cadence: ~7 s between polls, capped at ~120 s total.
_POLL_INTERVAL_S = 7.0
_POLL_DEADLINE_S = 120.0

# PRIVATE trackers — must authenticate with the stored credentials.
_PRIVATE_TRACKERS = ("rutracker", "kinozal", "nnmclub", "iptorrents")
# PUBLIC tracker — needs no login (RuTor, per CLAUDE.md), so authenticated is
# expected False; it is proven instead by returning results.
_PUBLIC_TRACKERS = ("rutor",)

# Substrings in a tracker's ``error`` that mark a transient / operator-blocked
# condition (CAPTCHA, expired cookies, upstream timeout, rate-limit) rather
# than a genuine bad-credential failure. Matched case-insensitively.
_TRANSIENT_ERROR_MARKERS = (
    "captcha",
    "timeout",
    "temporarily",
    "rate limit",
    "unreachable",
    "deadline",
)


def _merge_service_required() -> None:
    """Probe the merge service health endpoint (1 s); skip if it is down.

    Mirrors the project's probe-and-skip discipline (tests/fixtures/services.py)
    but for the LIVE credential guard we SKIP — never error, never boot a
    stack — when the service is absent, so this test can run on a developer
    box without the stack up.
    """
    health_url = f"{MERGE_BASE}/health"
    try:
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=1) as resp:  # noqa: S310 (trusted localhost)
            if resp.status >= 400:
                pytest.skip(f"merge service health returned HTTP {resp.status} at {health_url}")  # SKIP-OK: live-service-down
            body = resp.read().decode("utf-8", errors="replace")
        if '"status"' not in body:
            pytest.skip(f"merge service at {health_url} did not return a health body")  # SKIP-OK: live-service-down
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        pytest.skip(  # SKIP-OK: live-service-down
            f"merge service unreachable at {health_url}: {exc!r}. "
            "Start the stack with `./start.sh -p` to run this credential guard."
        )


def _http_json(url: str, *, method: str = "GET", payload: dict | None = None, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted localhost)
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _run_live_search() -> dict:
    """Start a real search and poll it to a terminal state. Returns the
    final search payload (with ``tracker_stats``)."""
    started = _http_json(
        f"{MERGE_BASE}/api/v1/search",
        method="POST",
        payload={"query": QUERY, "limit": LIMIT},
        timeout=30,
    )
    search_id = started.get("search_id")
    assert search_id, f"merge service did not return a search_id: {started!r}"

    deadline = time.monotonic() + _POLL_DEADLINE_S
    last_status = started.get("status")
    final: dict | None = None
    while time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
        try:
            payload = _http_json(f"{MERGE_BASE}/api/v1/search/{search_id}", timeout=15)
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
            # A single torn/slow poll mid-stream is not a verdict; keep polling.
            continue
        last_status = payload.get("status")
        if last_status in _TERMINAL_STATES:
            final = payload
            break

    if final is None:
        pytest.skip(  # SKIP-OK: live-service-down
            f"live search did not reach a terminal state within {_POLL_DEADLINE_S:.0f}s "
            f"(last status={last_status!r}). Treated as an operator-blocked transient, "
            "not a credential failure."
        )
    return final


@pytest.fixture(scope="module")
def live_search_stats() -> dict[str, dict]:
    """Run ONE real ``ubuntu`` search and index its tracker_stats by name.

    Module-scoped so the five parametrized cases share a single live fan-out
    instead of issuing five separate searches.
    """
    _merge_service_required()
    payload = _run_live_search()
    stats = payload.get("tracker_stats", [])
    assert stats, "merge service returned no tracker_stats — API contract broken"
    return {t["name"]: t for t in stats if t.get("name")}


@pytest.mark.requires_credentials
@pytest.mark.timeout(180)
@pytest.mark.parametrize("tracker", _PRIVATE_TRACKERS)
def test_private_tracker_credentials_authenticate(live_search_stats: dict[str, dict], tracker: str) -> None:
    """The stored credentials for a PRIVATE tracker must actually log in.

    THE credential proof: ``authenticated is True`` after the merge service
    really attempted a login + search against the live tracker. Fails if the
    stored credential is wrong/expired; honest-skips on CAPTCHA / transient.
    """
    stat = live_search_stats.get(tracker)
    assert stat is not None, (
        f"credentialed private tracker {tracker!r} is ABSENT from tracker_stats "
        f"(present: {sorted(live_search_stats)}). The search did not run it — "
        "the plugin is disabled or the fan-out dropped it."
    )

    authenticated = stat.get("authenticated")
    status = stat.get("status")
    error = (stat.get("error") or "")

    if authenticated is not True:
        lowered = error.lower()
        if any(marker in lowered for marker in _TRANSIENT_ERROR_MARKERS):
            pytest.skip(  # SKIP-OK: operator-blocked transient (captcha / expired cookies / upstream fault)
                f"{tracker}: authenticated=False with transient/operator-blocked error "
                f"({error!r}); RuTracker cookies expire & CAPTCHA/timeouts are not a "
                "credential defect (CLAUDE.md)."
            )
        pytest.fail(
            f"{tracker}: authenticated={authenticated!r} (expected True) — the STORED "
            f"credentials failed to log in. status={status!r}, error={error!r}. "
            "This is a genuine bad/expired-credential failure, not a transient."
        )

    # Credentials proven good. The tracker must also have RUN cleanly (not
    # errored/timed-out) — success or empty are both legitimate logged-in states.
    assert status in {"success", "empty"}, (
        f"{tracker}: authenticated=True but status={status!r} (expected success|empty). "
        f"error={error!r} — login worked yet the search itself did not complete cleanly."
    )


@pytest.mark.timeout(180)
@pytest.mark.parametrize("tracker", _PUBLIC_TRACKERS)
def test_public_tracker_returns_results_without_auth(live_search_stats: dict[str, dict], tracker: str) -> None:
    """A PUBLIC tracker (RuTor) needs no login and is proven by real results.

    Per CLAUDE.md RuTor is a public tracker with no login endpoint, so
    ``authenticated`` is expected False; correctness is proven by it returning
    actual results from the live upstream.
    """
    stat = live_search_stats.get(tracker)
    assert stat is not None, (
        f"public tracker {tracker!r} is ABSENT from tracker_stats "
        f"(present: {sorted(live_search_stats)}). The search did not run it."
    )

    status = stat.get("status")
    results_count = stat.get("results_count", 0)
    error = stat.get("error")

    assert status == "success", (
        f"{tracker}: status={status!r} (expected success) for a public tracker. "
        f"results_count={results_count}, error={error!r}."
    )
    assert results_count > 0, (
        f"{tracker}: results_count={results_count} (expected > 0). A public tracker "
        "that returns nothing for 'ubuntu' means the live search path is broken, "
        f"not a credential issue. error={error!r}."
    )
