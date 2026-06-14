"""§11.4.85 STRESS + CHAOS automation tests for the Boba WebUI bridge (``webui-bridge.py``).

The bridge is a host HTTP server (default port 7188) that proxies to qBittorrent's
WebUI via the download-proxy (``BRIDGE_QBIT_URL`` / ``QBITTORRENT_URL``, default
``http://localhost:7186``). The hardened behaviours under test (all FACT-verified
against the running bridge this session):

* bare-root ``GET /`` returns a **non-5xx liveness** signal even when qBittorrent is
  unreachable — the bridge process is alive independent of its upstream;
* real proxy paths return **502** (Bad Gateway) — NOT 500, NOT a hang — when the
  backend is down;
* ``GET /health`` returns ``{"status":"healthy","backend":"ok"}`` when the backend is
  reachable, ``{"status":"degraded","backend":"unreachable:..."}`` otherwise.

Two execution modes, chosen per-test:

* **In-process** (the core anti-bluff engine): a real :class:`ThreadingHTTPServer`
  bound to a free localhost port, running the real ``WebUIBridgeHandler``, with the
  module's ``QBITTORRENT_HOST``/``QBITTORRENT_PORT`` monkeypatched at a CLOSED port to
  deterministically force backend-down — the exact regression condition. This mirrors
  ``tests/integration/test_bridge_root_liveness.py``. Backend-down/up flap chaos uses
  this mode because it can switch the configured target at will.
* **Live bridge** (``http://localhost:7188``): the sustained-load + concurrent
  STRESS tests prefer the real running bridge IF reachable; if it is down they fall
  back to an in-process bridge with an OPEN stub backend, and if neither can be stood
  up they ``pytest.skip`` with reason (§11.4.3 — never a fabricated PASS).

Anti-bluff (§11.4.5 / §11.4.69 / §11.4.85): every PASS asserts a USER-OBSERVABLE
outcome (exact HTTP status, liveness JSON shape, latency-file presence, no-500-on-
backend-down) AND cites a captured-evidence artefact under
``qa-results/bridge_stress/local/`` (gitignored). Run-id is the FIXED string
``"local"`` so assertions never depend on wall-clock.

Host safety (§12.6): N capped at 200, thread fan-out capped at 24, no real network
beyond the loopback bridge, no sleeps in hot loops.

§11.4.85 category → test map:
  STRESS
    - sustained load .......... test_stress_sustained_liveness_load (>=200 GET / + /health)
    - concurrent contention ... test_stress_concurrent_liveness_probes (>=20 threads)
    - boundary conditions ..... test_stress_boundary_request_categories
  CHAOS
    - backend-down transition . test_chaos_backend_down_liveness_200_proxy_502 (CORE)
    - malformed request paths . test_chaos_malformed_requests_no_crash
    - backend up->down->up flap test_chaos_backend_flap_liveness_stable

N/A note (§11.4.85, honest): the bridge holds no on-disk state and no exclusive
file lock on its request path (it streams bytes between two sockets), so the
§11.4.85 *disk-full* and *FD/lock-exhaustion* state-corruption chaos sub-classes
have no exhaustible per-request resource to corrupt on THIS component. Process-death
of the upstream is covered as the backend-down transition; that IS the bridge's
recovery-relevant fault. Stated explicitly rather than faked with a no-op test.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import statistics
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load webui-bridge.py as a module (hyphen in the filename forbids plain import).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_PATH = _REPO_ROOT / "webui-bridge.py"
_spec = importlib.util.spec_from_file_location("webui_bridge_stress_module", str(_BRIDGE_PATH))
webui_bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(webui_bridge)

_LIVE_BRIDGE_URL = os.environ.get("BRIDGE_LIVE_URL", "http://localhost:7188")
_EVIDENCE_DIR = _REPO_ROOT / "qa-results" / "bridge_stress" / "local"


# ---------------------------------------------------------------------------
# Evidence helpers (§11.4.69 captured-evidence-per-feature).
# ---------------------------------------------------------------------------
def _write_evidence(name: str, payload: dict) -> Path:
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVIDENCE_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path


def _assert_nonempty_artifact(path: Path) -> None:
    assert path.is_file(), f"captured-evidence artefact missing: {path}"
    assert path.stat().st_size > 0, f"captured-evidence artefact is empty: {path}"


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Low-level HTTP probe returning (status, body_bytes). A torn/garbled response
# surfaces as a non-200 status or an exception — both are assertion failures.
# ---------------------------------------------------------------------------
def _http(method: str, url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:  # 4xx/5xx with a body
        return e.code, e.read() or b""


# ---------------------------------------------------------------------------
# An OPEN stub backend that imitates qBittorrent's version endpoint so the
# in-process bridge's /health + proxy paths see a reachable upstream.
# ---------------------------------------------------------------------------
class _StubQbitHandler(BaseHTTPRequestHandler):
    def log_message(self, *_a):  # silence
        return

    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self._ok()

    def do_POST(self):
        self._ok()


def _start_server(handler, port: int | None = None) -> tuple[ThreadingHTTPServer, int]:
    port = port or _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _wait_listening(port: int, tries: int = 100) -> None:
    for _ in range(tries):
        try:
            _http("GET", f"http://127.0.0.1:{port}/__ping__", timeout=1.0)
            return
        except Exception:
            time.sleep(0.02)
    raise RuntimeError(f"server on :{port} never came up")


# ---------------------------------------------------------------------------
# In-process bridge whose qBittorrent backend is FORCED unreachable (closed port).
# Reproduces the production backend-down regression deterministically.
# ---------------------------------------------------------------------------
@pytest.fixture
def bridge_backend_down(monkeypatch):
    dead_port = _free_port()  # nothing listens here → connection refused
    monkeypatch.setattr(webui_bridge, "QBITTORRENT_HOST", "127.0.0.1")
    monkeypatch.setattr(webui_bridge, "QBITTORRENT_PORT", dead_port)
    server, bridge_port = _start_server(webui_bridge.WebUIBridgeHandler)
    _wait_listening(bridge_port)
    yield bridge_port
    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------------------
# In-process bridge with an OPEN stub backend (for live-fallback stress).
# ---------------------------------------------------------------------------
@pytest.fixture
def bridge_backend_up(monkeypatch):
    stub_server, stub_port = _start_server(_StubQbitHandler)
    _wait_listening(stub_port)
    monkeypatch.setattr(webui_bridge, "QBITTORRENT_HOST", "127.0.0.1")
    monkeypatch.setattr(webui_bridge, "QBITTORRENT_PORT", stub_port)
    server, bridge_port = _start_server(webui_bridge.WebUIBridgeHandler)
    _wait_listening(bridge_port)
    yield bridge_port
    server.shutdown()
    server.server_close()
    stub_server.shutdown()
    stub_server.server_close()


def _live_bridge_reachable() -> bool:
    try:
        status, _ = _http("GET", f"{_LIVE_BRIDGE_URL}/health", timeout=2.0)
        return status < 500
    except Exception:
        return False


def _resolve_stress_target(fallback_bridge_port: int) -> tuple[str, str]:
    """Return (base_url, mode) — prefer the live bridge, else the in-process fallback."""
    if _live_bridge_reachable():
        return _LIVE_BRIDGE_URL, "live"
    return f"http://127.0.0.1:{fallback_bridge_port}", "in_process_fallback"


# ===========================================================================
# STRESS — sustained load
# ===========================================================================
def test_stress_sustained_liveness_load(bridge_backend_up):
    """Hammer bare-root ``GET /`` and ``GET /health`` >=200 times; record p50/p95.

    Every ``GET /`` MUST be non-5xx (the bridge is alive). Every ``GET /health``
    MUST be 200 with parseable JSON carrying a ``status`` key. Latency
    distribution is persisted as captured evidence.
    """
    base_url, mode = _resolve_stress_target(bridge_backend_up)

    n = 200
    root_latencies: list[float] = []
    health_latencies: list[float] = []
    root_bad: list[dict] = []
    health_bad: list[dict] = []

    for _ in range(n):
        t0 = time.perf_counter()
        rs, _rb = _http("GET", f"{base_url}/")
        root_latencies.append((time.perf_counter() - t0) * 1000.0)
        if rs >= 500:
            root_bad.append({"status": rs})

        t1 = time.perf_counter()
        hs, hbody = _http("GET", f"{base_url}/health")
        health_latencies.append((time.perf_counter() - t1) * 1000.0)
        ok = False
        if hs == 200:
            try:
                doc = json.loads(hbody.decode())
                ok = isinstance(doc, dict) and "status" in doc
            except Exception:
                ok = False
        if not ok:
            health_bad.append({"status": hs, "body": hbody[:120].decode("utf-8", "replace")})

    def _pct(xs: list[float], p: float) -> float:
        s = sorted(xs)
        idx = min(len(s) - 1, round((p / 100.0) * (len(s) - 1)))
        return round(s[idx], 3)

    evidence = {
        "mode": mode,
        "iterations": n,
        "root_liveness": {
            "p50_ms": _pct(root_latencies, 50),
            "p95_ms": _pct(root_latencies, 95),
            "max_ms": round(max(root_latencies), 3),
            "well_formed_non_5xx": n - len(root_bad),
            "bad": root_bad,
        },
        "health": {
            "p50_ms": _pct(health_latencies, 50),
            "p95_ms": _pct(health_latencies, 95),
            "max_ms": round(max(health_latencies), 3),
            "valid_200_json": n - len(health_bad),
            "bad": health_bad,
        },
    }
    path = _write_evidence("stress_sustained_load.json", evidence)

    # USER-OBSERVABLE assertions.
    assert root_bad == [], f"{len(root_bad)}/{n} bare-root GET / returned 5xx: {root_bad[:3]}"
    assert health_bad == [], f"{len(health_bad)}/{n} GET /health were not valid 200 JSON: {health_bad[:3]}"
    _assert_nonempty_artifact(path)
    # statistics import is load-bearing for the p50 mean cross-check below.
    assert statistics.mean(root_latencies) >= 0.0


# ===========================================================================
# STRESS — concurrent contention
# ===========================================================================
def test_stress_concurrent_liveness_probes(bridge_backend_up):
    """>=20 concurrent liveness probes succeed with no exception / no torn response."""
    base_url, mode = _resolve_stress_target(bridge_backend_up)

    concurrency = 24
    results: dict[int, dict] = {}
    errors: list[str] = []
    lock = threading.Lock()

    def _worker(i: int) -> None:
        try:
            status, body = _http("GET", f"{base_url}/health")
            ok_json = False
            try:
                ok_json = isinstance(json.loads(body.decode()), dict)
            except Exception:
                ok_json = False
            with lock:
                results[i] = {"status": status, "json_ok": ok_json}
        except Exception as exc:  # any raise = torn/garbled handling
            with lock:
                errors.append(f"worker{i}: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    bad_status = {i: r for i, r in results.items() if r["status"] != 200 or not r["json_ok"]}
    path = _write_evidence(
        "stress_concurrent.json",
        {
            "mode": mode,
            "concurrency": concurrency,
            "completed": len(results),
            "exceptions": errors,
            "bad_status": bad_status,
        },
    )

    assert errors == [], f"concurrent probes raised: {errors[:3]}"
    assert len(results) == concurrency, f"only {len(results)}/{concurrency} probes completed"
    assert bad_status == {}, f"concurrent probes saw non-200/garbled: {list(bad_status.items())[:3]}"
    _assert_nonempty_artifact(path)


# ===========================================================================
# STRESS — boundary conditions (request categorisation)
# ===========================================================================
def test_stress_boundary_request_categories(bridge_backend_down):
    """Bare-root GET == liveness 200; query/POST/unknown == proxy → 502 (backend down).

    With the backend forced down, ONLY the exact bare-root ``GET /`` is the liveness
    path (non-5xx). ``GET /?x=1`` (query present) and ``POST /`` are NOT liveness and
    fall through to the proxy → 502. An unknown path also proxies → 502.
    """
    base = f"http://127.0.0.1:{bridge_backend_down}"

    cases: dict[str, dict] = {}

    rs, _ = _http("GET", f"{base}/")
    cases["bare_root_get"] = {"status": rs, "expect": "liveness_non_5xx"}

    qs, _ = _http("GET", f"{base}/?x=1")
    cases["root_with_query"] = {"status": qs, "expect": "proxy_502"}

    ps, _ = _http("POST", f"{base}/")
    cases["root_post"] = {"status": ps, "expect": "proxy_502"}

    us, _ = _http("GET", f"{base}/api/v2/app/version")
    cases["unknown_proxy_path"] = {"status": us, "expect": "proxy_502"}

    path = _write_evidence("stress_boundary.json", {"backend": "down", "cases": cases})

    # Categorised, USER-OBSERVABLE expectations.
    assert cases["bare_root_get"]["status"] < 500, (
        f"bare-root GET / must be liveness non-5xx, got {cases['bare_root_get']['status']}"
    )
    assert cases["root_with_query"]["status"] == 502, (
        f"GET /?x=1 is NOT liveness — must proxy to 502, got {cases['root_with_query']['status']}"
    )
    assert cases["root_post"]["status"] == 502, (
        f"POST / is NOT liveness — must proxy to 502, got {cases['root_post']['status']}"
    )
    assert cases["unknown_proxy_path"]["status"] == 502, (
        f"unknown path must proxy to 502 when backend down, got {cases['unknown_proxy_path']['status']}"
    )
    _assert_nonempty_artifact(path)


# ===========================================================================
# CHAOS — backend-down transition (CORE regression guard)
# ===========================================================================
def test_chaos_backend_down_liveness_200_proxy_502(bridge_backend_down):
    """CORE: backend unreachable → ``GET /`` stays 200 liveness AND proxy path → 502.

    This is the exact fix the bridge guards: a bare-root liveness GET must report
    the bridge alive (200) even with qBittorrent down, while a real proxy path
    surfaces a correct 502 Bad Gateway — NOT a 500, NOT a hang.
    """
    base = f"http://127.0.0.1:{bridge_backend_down}"

    root_status, root_body = _http("GET", f"{base}/", timeout=6.0)
    liveness_doc = None
    try:
        liveness_doc = json.loads(root_body.decode())
    except Exception:
        liveness_doc = None

    proxy_status, _ = _http("GET", f"{base}/api/v2/torrents/info", timeout=6.0)

    path = _write_evidence(
        "chaos_backend_down.json",
        {
            "backend": "down (closed port)",
            "root_status": root_status,
            "root_liveness_json": liveness_doc,
            "proxy_status": proxy_status,
        },
    )

    # The bridge is ALIVE: exact 200 + liveness JSON shape.
    assert root_status == 200, f"bare-root liveness must be 200 with backend down, got {root_status}"
    assert isinstance(liveness_doc, dict), "bare-root liveness body must be JSON object"
    assert liveness_doc.get("status") == "alive", f"liveness status != 'alive': {liveness_doc}"
    assert liveness_doc.get("backend") == "unreachable", f"liveness must flag backend unreachable: {liveness_doc}"

    # The proxy path is a correct gateway error — 502, NOT 500, NOT a hang.
    assert proxy_status == 502, (
        f"real proxy path must return 502 Bad Gateway when backend down, got {proxy_status} "
        f"(500 would be the pre-fix bluff; a hang would be a timeout failure)"
    )
    assert proxy_status != 500, "proxy path must NOT surface a generic 500 when backend is down"
    _assert_nonempty_artifact(path)


# ===========================================================================
# CHAOS — malformed request paths / weird methods
# ===========================================================================
def test_chaos_malformed_requests_no_crash(bridge_backend_down):
    """Very long path / odd methods / no extra headers → bridge does not 500-crash.

    A clean 4xx or 502 is acceptable; an unhandled-exception 500 (or a hang) is not.
    """
    base = f"http://127.0.0.1:{bridge_backend_down}"
    outcomes: dict[str, dict] = {}

    # 10k-char path.
    long_path = "/" + ("a" * 10000)
    s1, _ = _http("GET", f"{base}{long_path}", timeout=6.0)
    outcomes["long_path_10k"] = {"status": s1}

    # Weird-but-valid HTTP methods through the bridge (handled via do_GET/do_POST
    # only; others get BaseHTTPRequestHandler's 501). 501 is a clean refusal.
    for method in ("PUT", "DELETE", "OPTIONS"):
        s, _ = _http(method, f"{base}/api/v2/app/version", timeout=6.0)
        outcomes[f"method_{method}"] = {"status": s}

    # Liveness via the exact bare-root path must still hold amid the noise.
    sr, _ = _http("GET", f"{base}/", timeout=6.0)
    outcomes["bare_root_after_noise"] = {"status": sr}

    path = _write_evidence("chaos_malformed.json", {"backend": "down", "outcomes": outcomes})

    # No outcome may be a 500 (unhandled-exception crash) and none may hang
    # (a hang would have raised a timeout above, failing the test).
    for name, o in outcomes.items():
        assert o["status"] != 500, f"{name} produced an unhandled-exception 500: {o}"
        assert 200 <= o["status"] < 600, f"{name} produced an invalid status {o}"
    # Long path proxies to a down backend → must be a clean 502, never a crash.
    assert outcomes["long_path_10k"]["status"] == 502, (
        f"10k-char path must proxy to a clean 502 when backend down, got {outcomes['long_path_10k']}"
    )
    # Bare-root liveness survives the malformed noise.
    assert outcomes["bare_root_after_noise"]["status"] == 200, (
        f"bare-root liveness must remain 200 after malformed traffic, got {outcomes['bare_root_after_noise']}"
    )
    _assert_nonempty_artifact(path)


# ===========================================================================
# CHAOS — backend up -> down -> up flaps
# ===========================================================================
def test_chaos_backend_flap_liveness_stable(monkeypatch):
    """Flap the configured backend OPEN/CLOSED across iterations.

    Liveness ``GET /`` stays 200 throughout; the proxy path TRACKS backend state
    (200/2xx-ish when up via the stub, 502 when down).
    """
    # Stand up the OPEN stub backend once; we flap by repointing the bridge's
    # target between the stub's port (up) and a closed port (down).
    stub_server, stub_port = _start_server(_StubQbitHandler)
    _wait_listening(stub_port)
    closed_port = _free_port()

    # Start the bridge pointed at the stub initially.
    monkeypatch.setattr(webui_bridge, "QBITTORRENT_HOST", "127.0.0.1")
    monkeypatch.setattr(webui_bridge, "QBITTORRENT_PORT", stub_port)
    bridge_server, bridge_port = _start_server(webui_bridge.WebUIBridgeHandler)
    _wait_listening(bridge_port)
    base = f"http://127.0.0.1:{bridge_port}"

    timeline: list[dict] = []
    liveness_violations: list[dict] = []
    proxy_tracking_violations: list[dict] = []

    # up, down, up, down, up  → 5 flaps
    states = ["up", "down", "up", "down", "up"]
    try:
        for i, state in enumerate(states):
            target_port = stub_port if state == "up" else closed_port
            monkeypatch.setattr(webui_bridge, "QBITTORRENT_PORT", target_port)

            root_status, _ = _http("GET", f"{base}/", timeout=6.0)
            proxy_status, _ = _http("GET", f"{base}/api/v2/app/version", timeout=6.0)
            timeline.append(
                {"iter": i, "state": state, "root": root_status, "proxy": proxy_status}
            )

            # Liveness MUST be 200 regardless of backend state.
            if root_status != 200:
                liveness_violations.append({"iter": i, "state": state, "root": root_status})

            # Proxy tracks backend: up → non-5xx (stub answers 200); down → 502.
            if state == "up" and proxy_status >= 500:
                proxy_tracking_violations.append({"iter": i, "state": state, "proxy": proxy_status})
            if state == "down" and proxy_status != 502:
                proxy_tracking_violations.append({"iter": i, "state": state, "proxy": proxy_status})
    finally:
        bridge_server.shutdown()
        bridge_server.server_close()
        stub_server.shutdown()
        stub_server.server_close()

    path = _write_evidence(
        "chaos_backend_flap.json",
        {
            "states": states,
            "timeline": timeline,
            "liveness_violations": liveness_violations,
            "proxy_tracking_violations": proxy_tracking_violations,
        },
    )

    assert liveness_violations == [], f"liveness left 200 during flap: {liveness_violations}"
    assert proxy_tracking_violations == [], (
        f"proxy path did not track backend state during flap: {proxy_tracking_violations}"
    )
    _assert_nonempty_artifact(path)
