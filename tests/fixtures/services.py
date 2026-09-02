"""Live-service fixtures.

Philosophy
----------
Before Phase 0.3, dozens of integration tests looked like::

    def test_something():
        if not requests.get("http://localhost:7187/").ok:
            pytest.skip("merge service unavailable")
        ...

That pattern hides breakage: CI showed "331 passed" while 71 tests were
silently skipped. The completion-initiative (see docs/superpowers/plans/
2026-04-19-completion-initiative.md) replaces those runtime skips with
fixtures that **require** the service to be healthy.

Behaviour:

*   If the service is healthy, the fixture returns the base URL.
*   If the service is unreachable, the fixture **errors** (not skips)
    with a clear message that points the operator at `./start.sh -p`
    or the `requires_compose` marker semantics.
*   ONE deliberate exception: ``merge_service_live_or_skip`` SKIPs and
    never boots the stack. It exists for the opt-in heavy suites under
    ``tests/scaling/**``, where a down stack means "nothing to measure",
    not "the product is broken". See its own docstring for why erroring
    there would be a false-positive refusal.
*   Tests that are genuinely credential-gated (e.g. private-tracker
    logins) use the `@pytest.mark.requires_credentials` marker so CI
    can partition runs.

Environment variables
---------------------

``MERGE_SERVICE_URL``     default ``http://localhost:7187``
``QBITTORRENT_URL``       default ``http://localhost:7186``
``WEBUI_BRIDGE_URL``      default ``http://localhost:7188``
``SERVICE_PROBE_TIMEOUT`` default ``3`` (seconds per probe attempt)
``SERVICE_PROBE_RETRIES`` default ``5`` (fixture retries before error)

``MODE=mock`` short-circuits probes and hands back fake URLs that respx
can intercept — useful for running integration tests offline.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import atexit
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
import requests

_DEFAULT_TIMEOUT: Final[float] = float(os.environ.get("SERVICE_PROBE_TIMEOUT", "3"))
_DEFAULT_RETRIES: Final[int] = int(os.environ.get("SERVICE_PROBE_RETRIES", "5"))


@dataclass(frozen=True)
class ServiceEndpoint:
    """A live service the test needs."""

    name: str
    url: str
    health_path: str
    expect_substring: str | None = None

    @property
    def health_url(self) -> str:
        return f"{self.url.rstrip('/')}{self.health_path}"


def _probe(ep: ServiceEndpoint, timeout: float = _DEFAULT_TIMEOUT, retries: int = _DEFAULT_RETRIES) -> None:
    """Probe ``ep`` until healthy or raise ``RuntimeError``."""
    last_err: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(ep.health_url, timeout=timeout)
            if resp.status_code < 400:
                if ep.expect_substring is None or ep.expect_substring in resp.text:
                    return
                last_err = AssertionError(f"expected substring {ep.expect_substring!r} not in body of {ep.health_url}")
            else:
                last_err = AssertionError(f"HTTP {resp.status_code} from {ep.health_url}")
        except requests.RequestException as exc:
            last_err = exc
        if attempt < retries:
            time.sleep(min(2.0, 0.3 * attempt))
    raise RuntimeError(
        f"Service '{ep.name}' at {ep.health_url} is not healthy after "
        f"{retries} attempts. Last error: {last_err}. "
        "Start the stack with `./start.sh -p` (rootless Podman is fine) "
        "before running this test. If you are running a mocked suite, "
        "set MODE=mock to bypass live probes."
    )


def _mock_mode() -> bool:
    return os.environ.get("MODE", "").lower() == "mock"


def _is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if a TCP connection can be made to the given port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect((host, port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError):
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def merge_service_endpoint() -> ServiceEndpoint:
    return ServiceEndpoint(
        name="merge-search",
        url=os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187"),
        health_path="/health",
        expect_substring='"status"',
    )


@pytest.fixture(scope="session")
def qbittorrent_endpoint() -> ServiceEndpoint:
    return ServiceEndpoint(
        name="qbittorrent-webui-proxy",
        url=os.environ.get("QBITTORRENT_URL", "http://localhost:7186"),
        health_path="/",
    )


@pytest.fixture(scope="session")
def webui_bridge_endpoint() -> ServiceEndpoint:
    return ServiceEndpoint(
        name="webui-bridge",
        url=os.environ.get("WEBUI_BRIDGE_URL", "http://localhost:7188"),
        health_path="/health",
    )


@pytest.fixture(scope="session")
def webui_bridge_process() -> str:
    """Ensure the webui‑bridge host process is running on port 7188.

    If the port is already listening, assume the process is already up
    (maybe started manually) and do nothing. Otherwise, start
    ``webui‑bridge.py`` as a subprocess and register an atexit handler
    to terminate it when the test session ends.

    Returns the base URL (e.g., ``http://localhost:7188``).
    """
    import atexit
    import signal
    import subprocess
    import sys
    from pathlib import Path

    port = 7188
    if _is_port_listening(port):
        # Already running; nothing to do.
        return f"http://localhost:{port}"

    # Start the bridge script.
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "webui-bridge.py"
    if not script.exists():
        raise RuntimeError(f"webui-bridge script not found at {script}")
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # Wait a moment for the server to bind.
    time.sleep(1.5)
    if not _is_port_listening(port):
        proc.terminate()
        stdout, _ = proc.communicate(timeout=2)
        raise RuntimeError(f"webui-bridge failed to start on port {port}. Output:\n{stdout}")

    # Register cleanup.
    def _cleanup():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    atexit.register(_cleanup)
    return f"http://localhost:{port}"


def _live_service_fixture(endpoint_fixture: str) -> Callable[..., str]:
    """Factory that builds a session-scoped live-URL fixture.

    Each live fixture probes the matching endpoint; on failure the test
    errors with the message from :func:`_probe`. When ``MODE=mock`` the
    fixture short-circuits and returns the base URL unchanged so that
    respx/responses stubs can intercept it.
    """

    def _fixture(request: pytest.FixtureRequest) -> str:
        ep: ServiceEndpoint = request.getfixturevalue(endpoint_fixture)
        if _mock_mode():
            return ep.url
        _probe(ep)
        return ep.url

    _fixture.__name__ = endpoint_fixture.replace("_endpoint", "_live")
    return _fixture


@pytest.fixture(scope="session")
def merge_service_live(request):
    """Live merge‑service URL; starts the docker‑compose stack if needed."""
    if _mock_mode():
        ep = request.getfixturevalue("merge_service_endpoint")
        return ep.url
    compose = request.getfixturevalue("compose_up")
    url = compose["merge_service"]
    # Ensure the service is healthy.
    ep = ServiceEndpoint(name="merge-search", url=url, health_path="/health", expect_substring='"status"')
    _probe(ep)
    return url


@pytest.fixture(scope="session")
def qbittorrent_live(request):
    """Live qBittorrent proxy URL; starts the docker‑compose stack if needed."""
    if _mock_mode():
        ep = request.getfixturevalue("qbittorrent_endpoint")
        return ep.url
    compose = request.getfixturevalue("compose_up")
    url = compose["qbittorrent_proxy"]
    ep = ServiceEndpoint(name="qbittorrent-webui-proxy", url=url, health_path="/")
    _probe(ep)
    return url


@pytest.fixture(scope="session")
def webui_bridge_live(request):
    """Live webui‑bridge URL; starts the host process if needed."""
    if _mock_mode():
        ep = request.getfixturevalue("webui_bridge_endpoint")
        return ep.url
    # Ensure the host process is running.
    url = request.getfixturevalue("webui_bridge_process")
    ep = ServiceEndpoint(name="webui-bridge", url=url, health_path="/health")
    _probe(ep)
    return url


@pytest.fixture(scope="session")
def all_services_live(merge_service_live: str, qbittorrent_live: str) -> dict[str, str]:
    """Aggregate fixture for tests that need multiple services."""
    return {"merge_service": merge_service_live, "qbittorrent": qbittorrent_live}


@pytest.fixture(scope="session")
def merge_service_live_or_skip(request) -> str:
    """Merge-service URL, or SKIP when the service is not up.

    Sibling of :func:`merge_service_live`, with two deliberate
    differences that make it the correct gate for OPT-IN heavy suites
    (``tests/scaling/**``) rather than for the integration suites:

    1.  It NEVER brings the compose stack up. ``merge_service_live``
        depends on ``compose_up``, which runs ``<runtime> compose up -d``
        when the ports are closed. A scaling/stress axis must not boot
        the operator's stack as a side effect of collection.
    2.  It SKIPs instead of erroring. The scaling axes are opt-in
        envelope measurements: with the stack down there is nothing to
        measure and no product defect to report, so an ERROR there would
        be a §11.4.201(1) false-positive refusal.

    Why a fixture and not an inline ``pytest.skip`` at each call site:
    the gate stays visible, named, and countable in ONE place instead of
    drifting across N call sites — the invariant
    ``tests/unit/test_no_runtime_service_skips.py`` exists to hold.

    Integration/e2e tests that SHOULD fail loudly when the stack is down
    keep using :func:`merge_service_live`. This fixture does not replace
    it and must not be used to soften a test that is meant to error.
    """
    ep: ServiceEndpoint = request.getfixturevalue("merge_service_endpoint")
    if _mock_mode():
        return ep.url
    try:
        _probe(ep)
    except RuntimeError as exc:
        pytest.skip(f"merge-search not up at {ep.health_url} (SKIP-OK BOB-109): {exc}")
    return ep.url


# ---------------------------------------------------------------------------
# BOB-152 — deterministic live HTTP against a rate-limited service.
#
# ROOT CAUSE this closes (measured 2026-09-02 against the running stack, not
# inferred):
#
#     $ for i in $(seq 1 12); do curl -o/dev/null -w "%{http_code} " -XPOST \
#         localhost:7187/api/v1/search -d '{"query":"probe","limit":1}'; done
#       200 200 200 200 200 200 200 200 429 429 429 429
#     $ grep -i 'ratelimit\|retry-after' <headers of the 429>
#       x-ratelimit-limit: 10
#       x-ratelimit-remaining: 0
#       retry-after: 54
#
# `/api/v1/search` is in the `search` rate-limit class: 10/minute, per-IP,
# FIXED window (download-proxy/src/api/rate_limit.py DEFAULT_LIMITS). Every
# test process on this host shares ONE budget. tests/security alone issues
# ~22 live search POSTs inside a ~50s run, so whether any individual
# assertion sees its real answer or a 429 depends on how many searches
# happened in the preceding 60 seconds — a §11.4.50 determinism defect that
# is entirely SELF-INFLICTED by the suite, not a product fault.
#
# The fix is NOT a longer timeout and NOT `RATE_LIMIT_DISABLED` (that is a
# SERVER-side env var: setting it in the test process cannot reach the
# container, and reconfiguring the operator's stack is out of bounds). The
# fix is to stop tripping the limiter: serialise, and back off using the
# server's OWN `Retry-After` rather than a number guessed here (§11.4.6 —
# the limit is read from the response, never hardcoded in the harness).
#
# The two failure directions are kept DISTINCT (§11.4.201(6) — a shared
# "something went wrong" path would conflate them):
#
#   * 429  -> the service is UP and throttling US. Wait for the window the
#             server names, then retry. Exhausting the retry budget FAILS
#             loudly; it is never swallowed into a pass or a skip.
#   * conn -> connection refused / timed out. Re-probe health. Genuinely
#             down => honest SKIP (an environment condition, not a defect).
#             Still healthy => RE-RAISE: a connection failure against a
#             healthy service IS a defect and must not decay into a skip.
# ---------------------------------------------------------------------------

_RATE_LIMIT_MAX_WAITS: Final[int] = int(os.environ.get("LIVE_RATE_LIMIT_MAX_WAITS", "3"))
_RATE_LIMIT_WAIT_CAP: Final[float] = float(os.environ.get("LIVE_RATE_LIMIT_WAIT_CAP", "75"))


class RateLimitedLiveClient:
    """`requests` wrapper for a LIVE service that self-throttles deterministically.

    Only two behaviours are added over plain ``requests``; everything else
    (headers, body, status, timing) is passed through untouched so callers
    still assert on the real response.

    Not a mock and not a stub (§11.4.27(A)): every call reaches the real
    service over a real socket. This class changes only WHEN the request is
    made, never WHAT is asserted about it.
    """

    def __init__(self, base_url: str, endpoint: ServiceEndpoint) -> None:
        self.base_url = base_url.rstrip("/")
        self._endpoint = endpoint

    # -- internals ---------------------------------------------------------

    def _retry_after_seconds(self, resp: requests.Response) -> float:
        """Seconds to wait, taken from the SERVER's own headers.

        `Retry-After` is emitted by the service's 429 handler
        (`_rate_limited_response`) and is the authoritative
        seconds-until-window-reset. `X-RateLimit-Reset` is the absolute
        fallback. If neither parses, we refuse to invent a number and let
        the caller see the 429 (§11.4.6).
        """
        raw = resp.headers.get("Retry-After", "").strip()
        if raw:
            try:
                return float(raw)
            except ValueError:
                pass
        reset = resp.headers.get("X-RateLimit-Reset", "").strip()
        if reset:
            try:
                return max(0.0, float(reset) - time.time())
            except ValueError:
                pass
        return -1.0

    def _on_connection_error(self, exc: BaseException, url: str) -> None:
        """Discriminate 'service is down' from 'service is up and broke'.

        Never collapses both into one verdict. A skip here is earned by a
        FAILED re-probe, not assumed from the exception type.
        """
        try:
            _probe(self._endpoint, retries=1)
        except RuntimeError:
            pytest.skip(
                f"merge-search is not reachable at {self._endpoint.health_url} "
                f"while calling {url} (SKIP-OK BOB-109): {exc}"
            )
        raise AssertionError(
            f"Connection to {url} failed with {type(exc).__name__}: {exc} — but the "
            f"health endpoint {self._endpoint.health_url} answered immediately "
            "afterwards. The service is UP, so this is a real defect, not an "
            "environment condition, and is deliberately NOT skipped."
        ) from exc

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        waits = 0
        while True:
            try:
                resp = requests.request(method, url, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                self._on_connection_error(exc, url)
                raise  # unreachable; _on_connection_error always skips or raises
            if resp.status_code != 429:
                return resp
            delay = self._retry_after_seconds(resp)
            if delay < 0 or waits >= _RATE_LIMIT_MAX_WAITS:
                if delay < 0:
                    return resp  # no usable header — hand the 429 to the caller
                raise AssertionError(
                    f"{method} {url} still 429 after {waits} rate-limit waits "
                    f"(limit={resp.headers.get('X-RateLimit-Limit', '?')}, "
                    f"retry-after={resp.headers.get('Retry-After', '?')}). Another "
                    "process on this host is consuming the shared per-IP budget "
                    "faster than this suite can drain it. NOT skipped and NOT "
                    "passed: the assertion under this call never got its answer."
                )
            waits += 1
            time.sleep(min(delay, _RATE_LIMIT_WAIT_CAP) + 0.5)

    # -- public API --------------------------------------------------------

    def get(self, path: str, **kwargs) -> requests.Response:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self._request("POST", path, **kwargs)

    def options(self, path: str, **kwargs) -> requests.Response:
        return self._request("OPTIONS", path, **kwargs)

    def delete(self, path: str, **kwargs) -> requests.Response:
        return self._request("DELETE", path, **kwargs)


@pytest.fixture(scope="session")
def merge_service_client(request) -> RateLimitedLiveClient:
    """Rate-limit-aware client for the LIVE merge service.

    Gated on :func:`merge_service_live_or_skip` — NOT on
    :func:`merge_service_live` — deliberately: the security suite must skip
    honestly when the stack is down and must NEVER boot the operator's
    compose stack as a collection side effect.
    """
    url: str = request.getfixturevalue("merge_service_live_or_skip")
    ep: ServiceEndpoint = request.getfixturevalue("merge_service_endpoint")
    return RateLimitedLiveClient(url, ep)
