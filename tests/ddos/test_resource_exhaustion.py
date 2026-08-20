"""Resource-exhaustion admission control (§11.4.27(B) ddos, BOB-074).

THE ATTACK. Per-IP rate limiting bounds how fast ONE client may ask. It does
not bound how much work is in flight GLOBALLY — a botnet spread across many
source IPs stays under every per-IP limit while saturating the shared tracker
fan-out. The second line of defence is admission control:
`MAX_CONCURRENT_SEARCHES` (`merge_service/search.py:662`), which makes the
service SHED load with a 429 instead of accepting work it cannot perform.

WHY THIS IS UNCOVERED ELSEWHERE. Every existing test that touches this guard
sets `orch.is_search_queue_full.return_value = False` — it MOCKS THE GUARD OFF
in order to test something else (12 call sites in
`tests/unit/test_merge_api_route_contracts.py` alone). Nothing anywhere asserts
that the guard ENGAGES. A regression that inverted the comparison or dropped
the check from the handler would be invisible to the entire suite.

HOW SATURATION IS ESTABLISHED (stated plainly, §11.4.6 — no invented mechanism).
The in-flight counter `_active_search_count` is BOTH incremented
(`search.py:797`) and decremented (`search.py:945`) inside `_run_search`, the
very method the host-safety fan-out stub replaces. So a stubbed search never
moves the counter at all, and "issue N searches and expect saturation" would
silently assert nothing. These tests therefore set the counter DIRECTLY on the
live orchestrator to represent N searches in flight, then drive the REAL
endpoint. What is simulated is only the SATURATION STATE; everything asserted
on is real — the real `api.app`, the real handler, the real
`is_search_queue_full()` comparison, and the real 429 shed path. Driving true
saturation would require real 43-tracker fan-outs, which is exactly the
off-host damage the host budget forbids (see conftest "HOST SAFETY").
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .conftest import build_app

_CLIENT_A = "203.0.113.11"  # TEST-NET-3 (RFC 5737) — never a routable host
_CLIENT_B = "203.0.113.12"


def _post_search(client: TestClient, ip: str):
    return client.post(
        "/api/v1/search",
        json={"query": "saturate", "validate_trackers": False},
        headers={"X-Forwarded-For": ip},
    )


def _saturate(app, in_flight: int):
    """Represent `in_flight` searches already running on the LIVE orchestrator."""
    orch = app.state.search_orchestrator
    orch._active_search_count = in_flight
    return orch


@pytest.mark.ddos
class TestSearchAdmissionControl:
    def test_queue_full_is_refused_with_429(self, monkeypatch):
        """At the in-flight cap, a further search is shed rather than accepted."""
        monkeypatch.setenv("MAX_CONCURRENT_SEARCHES", "2")
        # Per-IP limit deliberately generous so the refusal under test can only
        # be ADMISSION control, never the rate limiter.
        api_mod, _ = build_app(search="60/minute", default="500/minute")

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            orch = _saturate(api_mod.app, in_flight=2)
            assert orch._max_concurrent_searches == 2, (
                "precondition: MAX_CONCURRENT_SEARCHES was not honoured by the "
                f"orchestrator (got {orch._max_concurrent_searches})"
            )
            shed = _post_search(c, _CLIENT_A)

        assert shed.status_code == 429, (
            "admission control did not shed load at the in-flight cap; got "
            f"{shed.status_code}: {shed.text[:200]!r}"
        )
        assert "MAX_CONCURRENT_SEARCHES" in shed.text, (
            "the refusal did not come from admission control — its body does not "
            f"name the cap: {shed.text[:200]!r}"
        )

    def test_below_the_cap_the_search_is_admitted(self, monkeypatch):
        """§11.4.201(1) control: the gate must not refuse everything.

        A gate that sheds with headroom available is exactly as broken as one
        that never sheds — an inverted comparison produces precisely that, and
        without this control the shed assertion above would pass either way.
        """
        monkeypatch.setenv("MAX_CONCURRENT_SEARCHES", "2")
        api_mod, _ = build_app(search="60/minute", default="500/minute")

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            _saturate(api_mod.app, in_flight=1)  # one slot still free
            admitted = _post_search(c, _CLIENT_A)

        assert 200 <= admitted.status_code < 300, (
            "admission control shed load while a slot was still free; got "
            f"{admitted.status_code}: {admitted.text[:200]!r}"
        )

    def test_admission_control_sheds_a_client_with_an_untouched_per_ip_budget(
        self, monkeypatch
    ):
        """The botnet case a per-IP limiter structurally cannot handle.

        Client B has a completely fresh per-IP budget, so the ONLY thing that
        can refuse it is the GLOBAL in-flight cap.
        """
        monkeypatch.setenv("MAX_CONCURRENT_SEARCHES", "1")
        api_mod, _ = build_app(search="60/minute", default="500/minute")

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            _saturate(api_mod.app, in_flight=1)
            fresh_client = _post_search(c, _CLIENT_B)

        assert fresh_client.status_code == 429, (
            "a client with an untouched per-IP budget was admitted past the "
            f"global in-flight cap; got {fresh_client.status_code}"
        )

    def test_service_still_answers_health_while_shedding(self, monkeypatch):
        """Shedding is graceful: liveness keeps working while load is refused."""
        monkeypatch.setenv("MAX_CONCURRENT_SEARCHES", "1")
        api_mod, _ = build_app(search="60/minute", default="500/minute")

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            _saturate(api_mod.app, in_flight=1)
            shed = _post_search(c, _CLIENT_A)
            health = c.get("/health")

        assert shed.status_code == 429, f"precondition: expected a shed, got {shed.status_code}"
        assert health.status_code == 200, (
            f"/health stopped answering while the service was shedding: {health.status_code}"
        )

    def test_shedding_never_produces_a_5xx(self, monkeypatch):
        """Load shedding must be a deliberate 429, never an incidental crash."""
        monkeypatch.setenv("MAX_CONCURRENT_SEARCHES", "1")
        api_mod, _ = build_app(search="60/minute", default="500/minute")

        with TestClient(api_mod.app, raise_server_exceptions=False) as c:
            _saturate(api_mod.app, in_flight=1)
            codes = [_post_search(c, _CLIENT_A).status_code for _ in range(6)]

        assert [s for s in codes if s >= 500] == [], f"5xx while shedding: {codes}"
        assert set(codes) == {429}, f"expected every over-cap search to be shed; codes={codes}"


@pytest.mark.ddos
def test_cap_knob_is_real_not_hardcoded(monkeypatch):
    """The operator's cap knob genuinely changes where the gate trips.

    Guards §11.4.196(F) CONFIGURED != IN USE: a regression that hardcodes the
    cap would leave the service looking configured while ignoring the knob.
    Two different values must move the threshold.
    """
    monkeypatch.setenv("MAX_CONCURRENT_SEARCHES", "5")
    api_mod, _ = build_app(search="60/minute", default="500/minute")

    with TestClient(api_mod.app, raise_server_exceptions=False) as c:
        orch = _saturate(api_mod.app, in_flight=4)
        assert orch._max_concurrent_searches == 5, (
            f"the knob was ignored: cap resolved to {orch._max_concurrent_searches}, expected 5"
        )
        admitted = _post_search(c, _CLIENT_A)  # 4 in flight, cap 5 -> free slot
        _saturate(api_mod.app, in_flight=5)
        shed = _post_search(c, _CLIENT_A)  # 5 in flight, cap 5 -> full

    assert 200 <= admitted.status_code < 300, (
        f"a free slot under a cap of 5 was refused; got {admitted.status_code}"
    )
    assert shed.status_code == 429, (
        f"the cap of 5 did not trip at 5 in flight; got {shed.status_code}"
    )
