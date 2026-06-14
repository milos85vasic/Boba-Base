"""§11.4.85 STRESS + CHAOS automation tests for the Boba auth-status path.

Function under test (``download-proxy/src/api/auth.py``):

* :func:`api.auth.all_trackers_auth_status` — the ``GET /auth/status`` endpoint
  that the dashboard polls. It (a) reports per-tracker session state straight
  from ``orchestrator._tracker_sessions`` and (b) PROBES qBittorrent with the
  EFFECTIVE creds (saved if present, else default ``admin``/``admin``) and
  computes ``qbit_has_session`` as::

        (resp.status in (200, 204))
        and (a QBT_SID / QBT_SID_* cookie is present  OR  body.strip() == "Ok.")

  i.e. a modern 204+QBT_SID success OR a legacy 200 "Ok." success. The whole
  probe is wrapped in ``except Exception: pass`` so qBittorrent being
  unreachable / returning garbage MUST yield ``has_session False`` and MUST NOT
  raise out of the endpoint.

The qBittorrent ``aiohttp.ClientSession`` is MOCKED end-to-end via the EXACT
pattern from ``tests/unit/test_auth_coverage.py::TestAllTrackersAuthStatus``
(an ``AsyncMock`` session whose ``.post`` returns an async-context-manager resp,
``resp.cookies`` a real ``http.cookies.SimpleCookie`` jar). These tests NEVER
touch a real qBittorrent or any real tracker (§11.4.98 — no live pollution, no
network, no sleeps).

Anti-bluff (§11.4.5 / §11.4.69 / §11.4.85). Every PASS asserts a
USER-OBSERVABLE outcome — the ``has_session`` boolean, the per-tracker
``has_session`` flags, the result structure, the determinism-hash equality, the
latency-file existence — NOT "no error". The KEY anti-bluff property proven
explicitly here is **no-false-positive-auth**: on every failure / unreachable /
malformed / non-success response the endpoint reports ``qbittorrent.has_session
is False`` — it never claims authenticated when it is not. Credential VALUES are
never printed or written to evidence (§11.4.10) — only their lengths / a SHA-256
fingerprint.

Host safety (§12.6): N kept modest (<=150), no real network, no sleeps.

Stress coverage (closed-set per §11.4.85):
  - sustained load: 150 ``all_trackers_auth_status`` calls against a mocked
    success qBit + populated orchestrator sessions; per-iter latency p50/p95
    recorded; every call asserted structurally correct with ``has_session``
    True and the tracker states correct;
  - concurrent contention: 12 concurrent calls via ``asyncio.gather`` — all
    succeed, IDENTICAL serialized result (§11.4.50 determinism-hash equality);
  - boundary conditions: no saved creds (default admin/admin fallback); empty
    orchestrator sessions; 60+ tracker sessions; a tracker-session dict missing
    its ``base_url`` field.

Chaos coverage (closed-set per §11.4.85, mock-injected faults):
  - success polarity matrix (modern 204+QBT_SID / legacy 200 "Ok." → True;
    403 "Fails."+no-cookie / 200 empty-jar+non-"Ok." → False — the
    no-false-positive core);
  - process/upstream death: ``ClientConnectionError`` / ``TimeoutError`` on the
    login POST → ``has_session`` False, NO raise out of the endpoint;
  - input/state corruption: a ``resp.cookies`` whose ``.values()`` raises on
    iteration, and a jar with weird Morsel keys → no crash, defined
    ``has_session``;
  - credential edge: unicode / very-long username creds → no crash (values
    never logged per §11.4.10).

N/A note (§11.4.85, honest). ``all_trackers_auth_status`` does NO disk write on
its hot path (the saved-creds file is only READ, via the mocked
``_load_qbit_credentials``) and holds NO lock, so the §11.4.85 *disk-full* and
*FD/lock-exhaustion* chaos sub-classes have no exhaustible resource to exhaust
on THIS function's path. Stated explicitly rather than faked with a no-op test.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import statistics
import sys
import time
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from api.auth import all_trackers_auth_status  # noqa: E402

# Fixed run-id (no wall-clock in the path) so artefact assertions are stable.
_EVIDENCE_DIR = _REPO_ROOT / "qa-results" / "auth_stress" / "local"


# ---------------------------------------------------------------------------
# Evidence helpers (§11.4.5 / §11.4.69)
# ---------------------------------------------------------------------------


def _write_evidence(name: str, payload: dict) -> Path:
    """Persist a captured-evidence artefact and return its path."""
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return path


def _assert_nonempty_artifact(path: Path) -> None:
    """Anti-bluff guard: the cited evidence file MUST exist and be non-empty."""
    assert path.is_file(), f"captured-evidence artefact missing: {path}"
    assert path.stat().st_size > 0, f"captured-evidence artefact is empty: {path}"


def _cred_fingerprint(value: str) -> str:
    """§11.4.10: never store a credential value — store a salted-length hash."""
    return hashlib.sha256(f"len{len(value)}:{value}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Mock builders — mirror tests/unit/test_auth_coverage.py exactly
# ---------------------------------------------------------------------------


def _qbit_resp(*, status: int, body: str, cookie_keys: tuple[str, ...] = ()) -> AsyncMock:
    """A mocked qBittorrent login response (async context manager).

    ``cookies`` is a real ``http.cookies.SimpleCookie`` jar so the genuine
    cookie-presence branch in ``all_trackers_auth_status`` is exercised (a bare
    AsyncMock for ``.cookies`` would raise on ``.values()`` and the auth.py
    ``except: pass`` would silently swallow it — a §11.4.1 FAIL-bluff).
    """
    resp = AsyncMock()
    resp.text = AsyncMock(return_value=body)
    resp.status = status
    jar = SimpleCookie()
    for k in cookie_keys:
        jar[k] = "test-session-value"
    resp.cookies = jar
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _qbit_session(resp: AsyncMock) -> AsyncMock:
    """A mocked ``aiohttp.ClientSession`` whose ``.post`` returns ``resp``."""
    session = AsyncMock()
    session.post = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _success_resp() -> AsyncMock:
    """Modern qBittorrent success: 204 + QBT_SID cookie."""
    return _qbit_resp(status=204, body="", cookie_keys=("QBT_SID",))


def _orch(sessions: dict) -> MagicMock:
    orch = MagicMock()
    orch._tracker_sessions = sessions
    return orch


def _patches(orch: MagicMock, session: AsyncMock, creds: dict | None):
    """The standard patch stack used by every test here."""
    return (
        patch("api.auth._get_orchestrator", return_value=orch),
        patch("api.auth._load_qbit_credentials", return_value=creds),
        patch("aiohttp.ClientSession", return_value=session),
        patch("aiohttp.ClientTimeout", return_value=None),
    )


def _assert_well_formed(result: dict) -> None:
    """USER-OBSERVABLE structural invariant of the /auth/status response."""
    assert isinstance(result, dict)
    assert "trackers" in result
    trackers = result["trackers"]
    for name in ("rutracker", "kinozal", "nnmclub", "iptorrents", "qbittorrent"):
        assert name in trackers, f"missing tracker section: {name}"
        assert isinstance(trackers[name]["has_session"], bool)
    # qBittorrent section carries the effective username (never the password).
    assert "username" in trackers["qbittorrent"]


# ===========================================================================
# STRESS — sustained load
# ===========================================================================


class TestAuthStressSustainedLoad:
    """§11.4.85 stress: sustained load on ``all_trackers_auth_status``."""

    @pytest.mark.asyncio
    async def test_sustained_load_has_session_true_with_latency_evidence(self):
        """150 calls against a modern-success qBit + populated sessions.

        USER-OBSERVABLE assertions, EVERY iteration:
          - structure well-formed;
          - ``qbittorrent.has_session`` is True (genuine 204+QBT_SID success);
          - ``rutracker.has_session`` is True (orchestrator has the session),
            ``kinozal.has_session`` is False (orchestrator does not).
        Latency p50/p95 written to evidence.
        """
        n = 150
        orch = _orch(
            {
                "rutracker": {"cookies": {"bb_session": "x"}, "base_url": "https://rutracker.org"},
            }
        )
        latencies_ms: list[float] = []
        qbit_states: list[bool] = []

        for _ in range(n):
            session = _qbit_session(_success_resp())
            p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
            t0 = time.perf_counter()
            with p_orch, p_creds, p_sess, p_to:
                result = await all_trackers_auth_status()
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

            _assert_well_formed(result)
            assert result["trackers"]["qbittorrent"]["has_session"] is True
            assert result["trackers"]["rutracker"]["has_session"] is True
            assert result["trackers"]["kinozal"]["has_session"] is False
            qbit_states.append(result["trackers"]["qbittorrent"]["has_session"])

        # Every single call must have reported authenticated — no flake.
        assert all(qbit_states), "a sustained-load call failed to report qbit has_session"

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[min(len(latencies_ms) - 1, round(0.95 * (len(latencies_ms) - 1)))]
        evidence = _write_evidence(
            "sustained_load_latency.json",
            {
                "function": "all_trackers_auth_status",
                "iterations": n,
                "all_qbit_has_session_true": all(qbit_states),
                "rutracker_has_session": True,
                "kinozal_has_session": False,
                "latency_ms": {
                    "p50": round(p50, 4),
                    "p95": round(p95, 4),
                    "min": round(latencies_ms[0], 4),
                    "max": round(latencies_ms[-1], 4),
                },
            },
        )
        _assert_nonempty_artifact(evidence)


# ===========================================================================
# STRESS — concurrent contention (§11.4.50 determinism)
# ===========================================================================


class TestAuthStressConcurrent:
    """§11.4.85 stress: concurrent contention with determinism check."""

    @pytest.mark.asyncio
    async def test_concurrent_identical_results(self):
        """12 concurrent calls → all succeed, IDENTICAL serialized result.

        Each coroutine gets its OWN mocked session (an aiohttp response cannot be
        re-entered concurrently), all configured to the SAME modern-success
        outcome. The serialized result of every call MUST hash-equal (§11.4.50).
        """
        concurrency = 12
        orch = _orch(
            {
                "rutracker": {"cookies": {"bb_session": "x"}, "base_url": "https://rutracker.org"},
                "nnmclub": {"cookies": {"phpbb2mysql_4_sid": "y"}, "base_url": "https://nnm-club.me"},
            }
        )

        async def one_call() -> dict:
            session = _qbit_session(_success_resp())
            p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
            with p_orch, p_creds, p_sess, p_to:
                return await all_trackers_auth_status()

        results = await asyncio.gather(*[one_call() for _ in range(concurrency)])

        for result in results:
            _assert_well_formed(result)
            assert result["trackers"]["qbittorrent"]["has_session"] is True
            assert result["trackers"]["rutracker"]["has_session"] is True
            assert result["trackers"]["nnmclub"]["has_session"] is True

        serialized = [json.dumps(r, sort_keys=True) for r in results]
        hashes = {hashlib.sha256(s.encode()).hexdigest() for s in serialized}
        assert len(hashes) == 1, f"non-deterministic concurrent results: {len(hashes)} distinct hashes"

        evidence = _write_evidence(
            "concurrent_determinism.json",
            {
                "concurrency": concurrency,
                "distinct_result_hashes": len(hashes),
                "determinism_hash": next(iter(hashes)),
                "all_qbit_has_session_true": all(r["trackers"]["qbittorrent"]["has_session"] for r in results),
            },
        )
        _assert_nonempty_artifact(evidence)


# ===========================================================================
# STRESS — boundary conditions
# ===========================================================================


class TestAuthStressBoundary:
    """§11.4.85 stress: boundary inputs."""

    @pytest.mark.asyncio
    async def test_no_saved_creds_falls_back_to_default_admin(self):
        """No saved creds (``_load_qbit_credentials`` → None).

        The endpoint MUST still probe with the default ``admin`` user, the probe
        succeeds (mocked), and ``has_session`` is True with username ``admin`` —
        the exact dashboard-auto-auth behaviour the fix restored.
        """
        orch = _orch({})
        session = _qbit_session(_success_resp())
        p_orch, p_creds, p_sess, p_to = _patches(orch, session, None)
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()
        _assert_well_formed(result)
        assert result["trackers"]["qbittorrent"]["has_session"] is True
        assert result["trackers"]["qbittorrent"]["username"] == "admin"

    @pytest.mark.asyncio
    async def test_empty_orchestrator_sessions(self):
        """Empty ``_tracker_sessions`` → every tracker has_session False, qBit
        still probed and True."""
        orch = _orch({})
        session = _qbit_session(_success_resp())
        p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()
        _assert_well_formed(result)
        for name in ("rutracker", "kinozal", "nnmclub", "iptorrents"):
            assert result["trackers"][name]["has_session"] is False
        assert result["trackers"]["qbittorrent"]["has_session"] is True

    @pytest.mark.asyncio
    async def test_many_tracker_sessions(self):
        """60+ orchestrator sessions (only the 4 known names are reported).

        The endpoint reports a FIXED set of 4 trackers + qbittorrent regardless
        of how many extra sessions the orchestrator holds — proven by structure
        + the reported rutracker/nnmclub flags.
        """
        sessions = {f"extra_{i}": {"cookies": {"c": "v"}, "base_url": f"https://t{i}.example"} for i in range(60)}
        sessions["rutracker"] = {"cookies": {"bb_session": "x"}, "base_url": "https://rutracker.org"}
        sessions["nnmclub"] = {"cookies": {"phpbb2mysql_4_sid": "y"}, "base_url": "https://nnm-club.me"}
        orch = _orch(sessions)
        session = _qbit_session(_success_resp())
        p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()
        _assert_well_formed(result)
        assert set(result["trackers"].keys()) == {
            "rutracker",
            "kinozal",
            "nnmclub",
            "iptorrents",
            "qbittorrent",
        }
        assert result["trackers"]["rutracker"]["has_session"] is True
        assert result["trackers"]["nnmclub"]["has_session"] is True

    @pytest.mark.asyncio
    async def test_tracker_session_missing_base_url_field(self):
        """A session dict missing ``base_url`` → has_session True, base_url ""
        (the endpoint's ``.get("base_url", "")`` default), no crash."""
        orch = _orch({"rutracker": {"cookies": {"bb_session": "x"}}})  # no base_url key
        session = _qbit_session(_success_resp())
        p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()
        _assert_well_formed(result)
        assert result["trackers"]["rutracker"]["has_session"] is True
        assert result["trackers"]["rutracker"]["base_url"] == ""


# ===========================================================================
# CHAOS — success-polarity matrix (the no-false-positive-auth core)
# ===========================================================================


class TestAuthChaosSuccessPolarity:
    """§11.4.85 chaos: every qBit response shape → correct ``has_session``.

    This is the anti-bluff core: the endpoint MUST report ``has_session`` True
    ONLY when genuinely authenticated, and False on EVERY non-success response.
    """

    @pytest.mark.asyncio
    async def test_polarity_matrix_no_false_positive_auth(self):
        # (label, status, body, cookie_keys, expected_has_session)
        cases = [
            ("modern_204_qbt_sid", 204, "", ("QBT_SID",), True),
            ("modern_200_qbt_sid", 200, "", ("QBT_SID",), True),
            ("modern_200_qbt_sid_suffixed", 200, "", ("QBT_SID_abc",), True),
            ("legacy_200_ok", 200, "Ok.", (), True),
            ("legacy_200_ok_whitespace", 200, "  Ok.\n", (), True),
            # --- the failure half: NONE may report authenticated ---
            ("forbidden_403_fails_no_cookie", 403, "Fails.", (), False),
            ("ok_status_empty_jar_non_ok_body", 200, "Forbidden", (), False),
            ("ok_status_empty_jar_empty_body", 204, "", (), False),
            ("server_500_no_cookie", 500, "Internal Server Error", (), False),
            ("status_200_unrelated_cookie_only", 200, "Forbidden", ("SESSIONID",), False),
        ]
        orch = _orch({})
        observed: list[dict] = []
        false_positive_count = 0

        for label, status, body, cookies, expected in cases:
            session = _qbit_session(_qbit_resp(status=status, body=body, cookie_keys=cookies))
            p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
            with p_orch, p_creds, p_sess, p_to:
                result = await all_trackers_auth_status()
            _assert_well_formed(result)
            actual = result["trackers"]["qbittorrent"]["has_session"]
            observed.append({"case": label, "expected": expected, "actual": actual})
            assert actual is expected, f"{label}: expected has_session={expected}, got {actual}"
            # Explicit no-false-positive accounting: a False expectation that
            # came back True is an authentication false-positive.
            if expected is False and actual is True:
                false_positive_count += 1

        assert false_positive_count == 0, "AUTH FALSE-POSITIVE: reported authenticated when not authenticated"

        evidence = _write_evidence(
            "no_false_positive_auth_matrix.json",
            {
                "property": "no-false-positive-auth",
                "false_positive_count": false_positive_count,
                "cases": observed,
                "success_cases_true": [o for o in observed if o["expected"] is True],
                "failure_cases_false": [o for o in observed if o["expected"] is False],
            },
        )
        _assert_nonempty_artifact(evidence)


# ===========================================================================
# CHAOS — process / upstream death (qBittorrent unreachable)
# ===========================================================================


class TestAuthChaosUpstreamDeath:
    """§11.4.85 chaos: qBittorrent unreachable mid-probe."""

    @pytest.mark.asyncio
    async def test_connection_error_reports_false_no_raise(self):
        """``ClientConnectionError`` on the login POST → has_session False, NO
        raise out of ``all_trackers_auth_status``."""
        orch = _orch({"rutracker": {"cookies": {"bb_session": "x"}, "base_url": "https://rutracker.org"}})
        session = AsyncMock()
        session.post = MagicMock(side_effect=aiohttp.ClientConnectionError("qBittorrent down"))
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()  # must NOT raise
        _assert_well_formed(result)
        assert result["trackers"]["qbittorrent"]["has_session"] is False
        # The unrelated tracker section is still reported correctly.
        assert result["trackers"]["rutracker"]["has_session"] is True

        evidence = _write_evidence(
            "chaos_connection_error.json",
            {
                "injected_fault": "aiohttp.ClientConnectionError on login POST",
                "qbit_has_session": result["trackers"]["qbittorrent"]["has_session"],
                "raised_out_of_endpoint": False,
            },
        )
        _assert_nonempty_artifact(evidence)

    @pytest.mark.asyncio
    async def test_timeout_error_reports_false_no_raise(self):
        """A ``TimeoutError`` (builtin, raised by asyncio timeouts) on the POST →
        has_session False, NO raise."""
        orch = _orch({})
        session = AsyncMock()
        session.post = MagicMock(side_effect=TimeoutError("login timed out"))
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()
        _assert_well_formed(result)
        assert result["trackers"]["qbittorrent"]["has_session"] is False

    @pytest.mark.asyncio
    async def test_client_session_construction_raises_reports_false(self):
        """Even if constructing the ``ClientSession`` itself raises, the endpoint
        must degrade to has_session False, never propagate."""
        orch = _orch({})
        with (
            patch("api.auth._get_orchestrator", return_value=orch),
            patch("api.auth._load_qbit_credentials", return_value={"username": "admin", "password": "admin"}),
            patch("aiohttp.ClientSession", side_effect=aiohttp.ClientConnectionError("cannot connect")),
        ):
            result = await all_trackers_auth_status()
        _assert_well_formed(result)
        assert result["trackers"]["qbittorrent"]["has_session"] is False


# ===========================================================================
# CHAOS — input / state corruption (malformed cookie jar)
# ===========================================================================


class TestAuthChaosMalformedCookies:
    """§11.4.85 chaos: hostile / malformed ``resp.cookies`` jars."""

    @pytest.mark.asyncio
    async def test_cookies_values_raises_on_iteration(self):
        """``resp.cookies.values()`` raises mid-iteration → endpoint must NOT
        crash and MUST resolve to a defined has_session (False — it never saw a
        valid cookie, and the body is not "Ok.")."""
        orch = _orch({})

        class _ExplodingJar:
            def values(self):
                raise RuntimeError("corrupt cookie jar")

        resp = AsyncMock()
        resp.text = AsyncMock(return_value="<garbage>")
        resp.status = 200
        resp.cookies = _ExplodingJar()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = _qbit_session(resp)

        p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()  # must NOT raise
        _assert_well_formed(result)
        assert result["trackers"]["qbittorrent"]["has_session"] is False

        evidence = _write_evidence(
            "chaos_exploding_cookie_jar.json",
            {
                "injected_fault": "resp.cookies.values() raises RuntimeError",
                "qbit_has_session": result["trackers"]["qbittorrent"]["has_session"],
                "raised_out_of_endpoint": False,
            },
        )
        _assert_nonempty_artifact(evidence)

    @pytest.mark.asyncio
    async def test_weird_morsel_keys_no_crash(self):
        """A jar carrying unusual (non-QBT_SID) cookie keys + a 200 non-"Ok."
        body → defined has_session False, no crash."""
        orch = _orch({})
        weird = SimpleCookie()
        weird["__Secure-weird"] = "1"
        weird["x.y.z"] = "2"
        resp = AsyncMock()
        resp.text = AsyncMock(return_value="not-ok")
        resp.status = 200
        resp.cookies = weird
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = _qbit_session(resp)
        p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "admin", "password": "admin"})
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()
        _assert_well_formed(result)
        assert result["trackers"]["qbittorrent"]["has_session"] is False


# ===========================================================================
# CHAOS — credential edge cases (§11.4.10: never log values)
# ===========================================================================


class TestAuthChaosCredentialEdges:
    """§11.4.85 chaos: pathological credential shapes must not crash."""

    @pytest.mark.asyncio
    async def test_unicode_and_very_long_username(self):
        """Unicode + 5000-char username creds → no crash; the reported username
        equals the supplied one; the VALUE is never written to evidence — only a
        fingerprint (§11.4.10)."""
        long_user = "пользователь-" + ("u" * 5000)
        creds = {"username": long_user, "password": "p" * 4096}
        orch = _orch({})
        session = _qbit_session(_success_resp())
        p_orch, p_creds, p_sess, p_to = _patches(orch, session, creds)
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()  # must NOT crash
        _assert_well_formed(result)
        # The endpoint echoes back the effective username verbatim.
        assert result["trackers"]["qbittorrent"]["username"] == long_user
        assert result["trackers"]["qbittorrent"]["has_session"] is True

        evidence = _write_evidence(
            "chaos_credential_edges.json",
            {
                "username_len": len(long_user),
                "password_len": len(creds["password"]),
                "username_fingerprint": _cred_fingerprint(long_user),
                "qbit_has_session": result["trackers"]["qbittorrent"]["has_session"],
            },
        )
        _assert_nonempty_artifact(evidence)
        # §11.4.10 guard: the raw credential value must NOT be in the evidence.
        assert long_user not in evidence.read_text()

    @pytest.mark.asyncio
    async def test_creds_dict_missing_password_uses_default(self):
        """A creds dict missing ``password`` → ``.get('password','admin')``
        default, probe succeeds, no crash."""
        orch = _orch({})
        session = _qbit_session(_success_resp())
        p_orch, p_creds, p_sess, p_to = _patches(orch, session, {"username": "customuser"})  # no password key
        with p_orch, p_creds, p_sess, p_to:
            result = await all_trackers_auth_status()
        _assert_well_formed(result)
        assert result["trackers"]["qbittorrent"]["username"] == "customuser"
        assert result["trackers"]["qbittorrent"]["has_session"] is True
