"""§11.4.85 STRESS + CHAOS automation tests for the two Boba button-fix endpoints.

Endpoints under test (``download-proxy/src/api/routes.py``):

* :func:`api.routes.generate_magnet` — the "magnet" button. Pure-ish: takes
  ``{result_id, download_urls}`` and returns ``{"magnet","hashes"}``. The fix
  builds a SINGLE ``xt=urn:btih:`` from the FIRST (primary) infohash, so a
  merged content row carrying N distinct tracker-copies collapses to ONE
  torrent instead of a malformed N-xt magnet. No network.
* :func:`api.routes.initiate_download` — the "qBit" button. Adds the PRIMARY
  source to qBittorrent over aiohttp, then BREAKS after the first successful
  add (primary-with-fallback). The qBittorrent ``ClientSession`` is MOCKED
  end-to-end — these tests NEVER touch a real qBittorrent (§11.4.98 no live
  pollution).

Anti-bluff (§11.4.5 / §11.4.69 / §11.4.85): every PASS asserts a
USER-OBSERVABLE outcome (xt count, add-attempt count, ``added_count``, status
string) AND cites a captured-evidence artefact written under
``qa-results/button_stress/local/`` (latency distribution + categorised
outcomes). The run-id is a FIXED ``"local"`` string so assertions never depend
on wall-clock.

Host safety (§12.6): N is kept modest (<=200), no real network, no sleeps.

Stress coverage (closed-set per §11.4.85):
  - sustained load: 150 ``generate_magnet`` iterations, per-iter latency p50/p95
    recorded + single-xt invariant asserted every iter;
  - concurrent contention: 12 concurrent ``generate_magnet`` via
    ``asyncio.gather`` — no exception, all single-xt;
  - boundary conditions: empty / single / 1000-infohash / malformed-mixed /
    non-magnet-tracker-URL — each categorised.

Chaos coverage (closed-set per §11.4.85):
  - process/upstream death (qBittorrent unreachable): ``ClientConnectionError``
    on the login POST → status ``connection_failed`` (no raise);
  - upstream fault (primary add fails, fallback add succeeds): exactly 2 add
    attempts + ``added_count==1``;
  - state/auth fault (login non-2xx + no cookie): status ``auth_failed`` + zero
    add attempts;
  - input corruption (10k-char random ``download_urls`` entry): well-formed,
    possibly xt-less magnet, no hang / no raise.

N/A note (§11.4.85, honest): ``generate_magnet`` and the mocked
``initiate_download`` path do no disk I/O and hold no locks, so the §11.4.85
*disk-full* and *FD/lock-exhaustion* chaos sub-classes are genuinely
inapplicable to THESE functions — there is no exhaustible resource on their
in-process / mocked path to exhaust. This is stated explicitly rather than
faked with a no-op test.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from fastapi import Request

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from api.routes import DownloadRequest, generate_magnet, initiate_download  # noqa: E402

# Fixed run-id (no wall-clock in the path) so artefact assertions are stable.
_EVIDENCE_DIR = _REPO_ROOT / "qa-results" / "button_stress" / "local"


def _write_evidence(name: str, payload: dict) -> Path:
    """Persist a captured-evidence artefact and return its path (§11.4.69)."""
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path


def _assert_nonempty_artifact(path: Path) -> None:
    """Anti-bluff guard: the cited evidence file MUST exist and be non-empty."""
    assert path.is_file(), f"captured-evidence artefact missing: {path}"
    assert path.stat().st_size > 0, f"captured-evidence artefact is empty: {path}"


def _magnet_request(result_id: str, download_urls: list[str]) -> MagicMock:
    """A ``MagicMock(spec=Request)`` whose ``.json()`` returns the magnet body.

    Mirrors the established pattern in
    ``tests/unit/test_download_merged.py`` so the mock matches what
    ``generate_magnet`` actually awaits.
    """
    req = MagicMock(spec=Request)
    req.json = AsyncMock(return_value={"result_id": result_id, "download_urls": download_urls})
    return req


def _xt_count(magnet: str) -> int:
    return magnet.count("xt=urn:btih:")


# ---------------------------------------------------------------------------
# STRESS — sustained load
# ---------------------------------------------------------------------------


class TestMagnetStressSustainedLoad:
    """§11.4.85 stress: sustained load on ``generate_magnet``."""

    @pytest.mark.asyncio
    async def test_sustained_load_single_xt_with_latency_evidence(self):
        """150 iterations, download_urls size cycling 1..50.

        USER-OBSERVABLE assertion: every produced magnet carries EXACTLY ONE
        ``xt=urn:btih:`` (the primary), regardless of how many distinct
        infohashes the merged row carried. Evidence: per-iteration latency list
        + p50/p95 persisted to ``magnet_latency.json``.
        """
        iterations = 150
        latencies_ms: list[float] = []
        xt_counts: list[int] = []

        for i in range(iterations):
            n_sources = (i % 50) + 1  # 1..50 distinct tracker-copies
            hashes = [f"{(i * 50 + j + 1):040x}" for j in range(n_sources)]
            urls = [f"magnet:?xt=urn:btih:{h}&tr=udp://t{j}:1337" for j, h in enumerate(hashes)]
            req = _magnet_request(f"row-{i}", urls)

            t0 = time.perf_counter()
            resp = await generate_magnet(req)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

            magnet = resp["magnet"]
            count = _xt_count(magnet)
            xt_counts.append(count)
            # Every iteration: exactly one torrent in the magnet.
            assert count == 1, f"iter {i} ({n_sources} sources) produced {count} xt: {magnet}"
            # The chosen xt is the PRIMARY (first) source.
            assert hashes[0] in magnet, f"iter {i}: primary infohash missing"

        p50 = statistics.median(latencies_ms)
        p95 = sorted(latencies_ms)[int(0.95 * (len(latencies_ms) - 1))]
        p_max = max(latencies_ms)

        evidence = _write_evidence(
            "magnet_latency.json",
            {
                "feature": "generate_magnet sustained load",
                "iterations": iterations,
                "latency_ms": latencies_ms,
                "p50_ms": p50,
                "p95_ms": p95,
                "max_ms": p_max,
                "xt_counts": xt_counts,
                "all_single_xt": all(c == 1 for c in xt_counts),
            },
        )
        _assert_nonempty_artifact(evidence)

        # Latency sanity bound (host-safety + perf regression guard). A pure
        # string-build per call must stay well under these ceilings.
        assert p50 < 50.0, f"p50 latency {p50:.3f}ms exceeds 50ms bound"
        assert p95 < 200.0, f"p95 latency {p95:.3f}ms exceeds 200ms bound"
        assert all(c == 1 for c in xt_counts), "a sustained-load iteration produced != 1 xt"
        # The recorded distribution must be non-degenerate (proves we measured).
        assert len(latencies_ms) == iterations


# ---------------------------------------------------------------------------
# STRESS — concurrent contention
# ---------------------------------------------------------------------------


class TestMagnetStressConcurrency:
    """§11.4.85 stress: concurrent contention on ``generate_magnet``."""

    @pytest.mark.asyncio
    async def test_concurrent_calls_no_exception_all_single_xt(self):
        """12 concurrent ``generate_magnet`` calls via ``asyncio.gather``.

        USER-OBSERVABLE assertion: no call raises and every result is a
        single-xt magnet. Evidence: per-task xt-count + any exception class
        persisted to ``magnet_concurrency.json``.
        """
        concurrency = 12

        async def one(idx: int):
            hashes = [f"{(idx * 7 + k + 1):040x}" for k in range(idx + 1)]
            urls = [f"magnet:?xt=urn:btih:{h}" for h in hashes]
            resp = await generate_magnet(_magnet_request(f"c-{idx}", urls))
            return _xt_count(resp["magnet"])

        results = await asyncio.gather(*(one(i) for i in range(concurrency)), return_exceptions=True)

        exceptions = [repr(r) for r in results if isinstance(r, BaseException)]
        xt_counts = [r for r in results if not isinstance(r, BaseException)]

        evidence = _write_evidence(
            "magnet_concurrency.json",
            {
                "feature": "generate_magnet concurrent contention",
                "concurrency": concurrency,
                "exceptions": exceptions,
                "xt_counts": xt_counts,
            },
        )
        _assert_nonempty_artifact(evidence)

        assert not exceptions, f"concurrent generate_magnet raised: {exceptions}"
        assert len(xt_counts) == concurrency, "lost a concurrent result"
        assert all(c == 1 for c in xt_counts), f"a concurrent call produced != 1 xt: {xt_counts}"


# ---------------------------------------------------------------------------
# STRESS — boundary conditions
# ---------------------------------------------------------------------------


class TestMagnetStressBoundaries:
    """§11.4.85 stress: boundary conditions, each categorised."""

    @pytest.mark.asyncio
    async def test_boundary_conditions_categorised_with_evidence(self):
        """Five boundary inputs, each asserting a categorised outcome.

        empty -> magnet with NO xt; single -> one xt; 1000 infohashes -> ONE xt
        (primary); malformed+valid mix -> the valid primary's xt; non-magnet
        tracker URL -> well-formed, no xt. Evidence persisted to
        ``magnet_boundaries.json``.
        """
        primary40 = "abc123def4567890abc123def4567890abc12345"
        outcomes: dict[str, dict] = {}

        # (1) empty download_urls -> well-formed magnet:?dn=... with NO xt.
        resp = await generate_magnet(_magnet_request("empty", []))
        m_empty = resp["magnet"]
        outcomes["empty"] = {"magnet": m_empty, "xt_count": _xt_count(m_empty), "hashes": resp["hashes"]}
        assert m_empty.startswith("magnet:?dn="), f"empty case not well-formed: {m_empty}"
        assert _xt_count(m_empty) == 0, f"empty download_urls must yield NO xt: {m_empty}"

        # (2) single source -> exactly one xt.
        resp = await generate_magnet(_magnet_request("single", [f"magnet:?xt=urn:btih:{primary40}"]))
        m_single = resp["magnet"]
        outcomes["single"] = {"magnet": m_single, "xt_count": _xt_count(m_single)}
        assert _xt_count(m_single) == 1, f"single source must yield ONE xt: {m_single}"
        assert primary40 in m_single

        # (3) 1000 distinct infohashes -> still exactly ONE xt (the primary).
        big_hashes = [f"{i:040x}" for i in range(1, 1001)]
        big_urls = [f"magnet:?xt=urn:btih:{h}" for h in big_hashes]
        resp = await generate_magnet(_magnet_request("ubuntu-1000", big_urls))
        m_big = resp["magnet"]
        outcomes["thousand_infohashes"] = {"xt_count": _xt_count(m_big), "n_input": len(big_urls)}
        assert _xt_count(m_big) == 1, f"1000-infohash row must collapse to ONE xt, got {_xt_count(m_big)}"
        assert big_hashes[0] in m_big, "primary (first) source must be the chosen torrent"

        # (4) malformed entry (no btih) mixed with a valid one -> use valid primary.
        mixed = [
            "magnet:?dn=garbage-no-infohash&tr=udp://x:1",  # malformed: no btih
            f"magnet:?xt=urn:btih:{primary40}",  # valid -> becomes the primary hash
        ]
        resp = await generate_magnet(_magnet_request("mixed", mixed))
        m_mixed = resp["magnet"]
        outcomes["malformed_mixed"] = {"magnet": m_mixed, "xt_count": _xt_count(m_mixed), "hashes": resp["hashes"]}
        assert _xt_count(m_mixed) == 1, f"mixed case must yield ONE xt from the valid source: {m_mixed}"
        assert primary40 in m_mixed, "the valid infohash must be used as primary"

        # (5) a non-magnet tracker URL entry -> well-formed magnet, no btih found.
        resp = await generate_magnet(_magnet_request("http-row", ["https://rutracker.org/forum/viewtopic.php?t=123"]))
        m_http = resp["magnet"]
        outcomes["non_magnet_tracker_url"] = {"magnet": m_http, "xt_count": _xt_count(m_http)}
        assert m_http.startswith("magnet:?dn="), f"non-magnet URL case not well-formed: {m_http}"
        assert _xt_count(m_http) == 0, f"non-magnet tracker URL must yield NO xt: {m_http}"

        evidence = _write_evidence(
            "magnet_boundaries.json",
            {"feature": "generate_magnet boundary conditions", "outcomes": outcomes},
        )
        _assert_nonempty_artifact(evidence)


# ---------------------------------------------------------------------------
# CHAOS — fault injection on initiate_download (aiohttp fully mocked)
# ---------------------------------------------------------------------------


def _add_resp(body: str, status: int = 200) -> AsyncMock:
    """An aiohttp response context-manager mock for a ``/torrents/add`` call."""
    resp = AsyncMock()
    resp.text = AsyncMock(return_value=body)
    resp.status = status
    resp.cookies = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _login_resp(ok: bool) -> AsyncMock:
    """An aiohttp login response: ``Ok.``/200 when ``ok`` else ``Fails.``/200.

    On the failure case the cookie jar carries NO ``QBT_SID`` cookie, so
    ``_qbit_login_succeeded`` returns False and the handler short-circuits to
    ``auth_failed`` (mirrors a rejected qBittorrent login).
    """
    resp = AsyncMock()
    resp.text = AsyncMock(return_value="Ok." if ok else "Fails.")
    resp.status = 200 if ok else 403
    # Empty cookie jar -> no session cookie -> login fails on the failure path;
    # on the success path the "Ok." body alone satisfies _qbit_login_succeeded.
    resp.cookies = {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _session_with_post_sequence(responses: list[AsyncMock]) -> AsyncMock:
    """A ClientSession mock whose successive ``.post`` calls yield ``responses``."""
    session = AsyncMock()
    session.post = MagicMock(side_effect=responses)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _add_attempt_count(session: AsyncMock) -> int:
    return sum(1 for c in session.post.call_args_list if "/torrents/add" in str(c))


class TestInitiateDownloadChaos:
    """§11.4.85 chaos: fault injection on the qBit-button download path."""

    @pytest.mark.asyncio
    async def test_qbittorrent_unreachable_connection_failed(self):
        """Process/upstream death: login POST raises ``ClientConnectionError``.

        USER-OBSERVABLE: the handler returns status ``connection_failed`` and
        does NOT propagate the exception. Evidence -> ``chaos_outcomes.json``.
        """
        session = AsyncMock()
        session.post = MagicMock(side_effect=aiohttp.ClientConnectionError("qBittorrent down"))
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        req = DownloadRequest(result_id="x", download_urls=["magnet:?xt=urn:btih:" + ("a" * 40)])

        with (
            patch("api.routes._get_orchestrator", return_value=MagicMock()),
            patch("api.routes._get_qbit_username", return_value="admin"),
            patch("api.routes._get_qbit_password", return_value="admin"),
            patch("api.hooks.dispatch_event", new_callable=AsyncMock),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            result = await initiate_download(req, MagicMock())

        assert result["status"] == "connection_failed", f"expected connection_failed, got {result}"
        evidence = _write_evidence(
            "chaos_connection_failed.json",
            {
                "feature": "initiate_download qBittorrent unreachable",
                "category": "process_death/upstream_unreachable",
                "injected_fault": "aiohttp.ClientConnectionError on login POST",
                "observed_status": result["status"],
                "raised": False,
            },
        )
        _assert_nonempty_artifact(evidence)

    @pytest.mark.asyncio
    async def test_primary_add_fails_fallback_succeeds_two_attempts(self):
        """Upstream fault: primary add returns ``Fails.``, fallback returns ``Ok.``.

        USER-OBSERVABLE: EXACTLY 2 add attempts and ``added_count == 1`` — proves
        break-after-first-SUCCESS (not after first ATTEMPT) plus the
        primary-with-fallback behaviour. Evidence -> ``chaos_fallback.json``.
        """
        # POST sequence: login(ok), add#1(Fails.), add#2(Ok.). Both URLs are
        # non-tracker magnets so each takes the direct ``data={"urls": url}``
        # add branch (no orchestrator fetch).
        session = _session_with_post_sequence(
            [_login_resp(True), _add_resp("Fails."), _add_resp("Ok.")]
        )
        req = DownloadRequest(
            result_id="Ubuntu",
            download_urls=[
                "magnet:?xt=urn:btih:" + ("a" * 40),
                "magnet:?xt=urn:btih:" + ("b" * 40),
            ],
        )

        with (
            patch("api.routes._get_orchestrator", return_value=MagicMock()),
            patch("api.routes._get_qbit_username", return_value="admin"),
            patch("api.routes._get_qbit_password", return_value="admin"),
            patch("api.hooks.dispatch_event", new_callable=AsyncMock),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            result = await initiate_download(req, MagicMock())

        add_attempts = _add_attempt_count(session)
        assert add_attempts == 2, f"expected EXACTLY 2 add attempts (fail->fallback), got {add_attempts}"
        assert result.get("added_count") == 1, f"expected added_count==1, got {result.get('added_count')}"
        assert result.get("status") == "initiated", f"expected status initiated, got {result.get('status')}"

        evidence = _write_evidence(
            "chaos_fallback.json",
            {
                "feature": "initiate_download primary-fail fallback-success",
                "category": "upstream_fault/partial_failure",
                "add_attempts": add_attempts,
                "added_count": result.get("added_count"),
                "status": result.get("status"),
            },
        )
        _assert_nonempty_artifact(evidence)

    @pytest.mark.asyncio
    async def test_auth_failure_zero_add_attempts(self):
        """State/auth fault: login non-2xx + no cookie -> ``auth_failed``.

        USER-OBSERVABLE: status ``auth_failed`` and ZERO add attempts (the
        handler must never POST a torrent when login was rejected). Evidence ->
        ``chaos_auth_failed.json``.
        """
        session = _session_with_post_sequence([_login_resp(False)])
        req = DownloadRequest(result_id="x", download_urls=["magnet:?xt=urn:btih:" + ("a" * 40)])

        with (
            patch("api.routes._get_orchestrator", return_value=MagicMock()),
            patch("api.routes._get_qbit_username", return_value="admin"),
            patch("api.routes._get_qbit_password", return_value="admin"),
            patch("api.hooks.dispatch_event", new_callable=AsyncMock),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            result = await initiate_download(req, MagicMock())

        add_attempts = _add_attempt_count(session)
        assert result["status"] == "auth_failed", f"expected auth_failed, got {result}"
        assert add_attempts == 0, f"a rejected login must trigger ZERO add attempts, got {add_attempts}"

        evidence = _write_evidence(
            "chaos_auth_failed.json",
            {
                "feature": "initiate_download auth rejected",
                "category": "state_fault/auth_rejected",
                "observed_status": result["status"],
                "add_attempts": add_attempts,
            },
        )
        _assert_nonempty_artifact(evidence)

    @pytest.mark.asyncio
    async def test_input_corruption_huge_random_string(self):
        """Input corruption: a 10k-char random ``download_urls`` entry.

        USER-OBSERVABLE: ``generate_magnet`` does not hang or raise and returns
        a well-formed (here xt-less) magnet — the corrupt entry contains no
        ``btih`` so no infohash is extracted. Evidence ->
        ``chaos_input_corruption.json``.
        """
        rng = random.Random(20260614)  # noqa: S311 — junk-input fixture, not crypto; deterministic per §11.4.50
        junk = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/:?=&%") for _ in range(10_000))

        t0 = time.perf_counter()
        resp = await asyncio.wait_for(generate_magnet(_magnet_request("corrupt", [junk])), timeout=1.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        magnet = resp["magnet"]
        assert magnet.startswith("magnet:?dn="), f"corrupt input did not yield a well-formed magnet: {magnet[:120]}"
        assert _xt_count(magnet) == 0, f"corrupt non-btih input must yield NO xt: {magnet[:120]}"
        assert resp["hashes"] == [], f"no infohash should be extracted from junk, got {resp['hashes']}"

        evidence = _write_evidence(
            "chaos_input_corruption.json",
            {
                "feature": "generate_magnet huge random input",
                "category": "input_corruption",
                "input_len": len(junk),
                "elapsed_ms": elapsed_ms,
                "xt_count": _xt_count(magnet),
                "hashes": resp["hashes"],
            },
        )
        _assert_nonempty_artifact(evidence)
        assert elapsed_ms < 1000.0, f"corrupt-input handling took {elapsed_ms:.1f}ms (possible hang)"
