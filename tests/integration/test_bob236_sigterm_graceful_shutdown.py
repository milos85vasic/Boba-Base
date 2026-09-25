"""BOB-236 — ``qbittorrent-proxy`` MUST exit cleanly on SIGTERM, well inside
the container's 10s stop-grace period, never needing a SIGKILL.

Root cause (docs/Issues.md BOB-236, systematic-debugging per §11.4.102):
``download-proxy/src/main.py::main()`` installs a top-level SIGTERM handler
that only sets ``_shutdown_event`` (a ``threading.Event``) and then tries to
join its two background service threads with ``timeout=5`` each -- but
NEITHER background thread was ever wired to actually stop:

* ``start_original_proxy()`` -> ``download_proxy.run_server()`` ->
  ``ThreadingHTTPServer.serve_forever()`` only called ``httpd.shutdown()`` on
  ``KeyboardInterrupt``, which CPython never raises on a non-main thread.
* ``start_fastapi_server()`` runs ``asyncio.run(server.serve())`` on a
  background thread. uvicorn's own ``Server.capture_signals()``
  (``uvicorn/server.py``) explicitly skips installing SIGTERM/SIGINT
  handlers when NOT called from the main thread, and nothing else in this
  codebase ever set ``server.should_exit``.

So both ``proxy_thread.join(timeout=5)`` and ``fastapi_thread.join(timeout=5)``
in ``main()`` were GUARANTEED to fully time out on every SIGTERM (neither
thread could ever exit on its own), landing shutdown at ~10.0-11.0s --
right at, and typically just past, the container's default 10s
``StopTimeout`` (``docker-compose.yml`` sets no ``stop_grace_period``, so the
podman/docker default of 10s applies). §11.4.115 RED-baseline captured
2026-09-25 08:13 UTC against the live pre-fix container: ``podman stop
qbittorrent-proxy`` (default timeout) took 10.17s and the container exited
with code 137 (SIGKILL), logging verbatim the reported symptom:
``StopSignal SIGTERM failed to stop container qbittorrent-proxy in 10
seconds, resorting to SIGKILL``. See ``docs/qa/BOB-236/closure_evidence_*.md``
for the full captured transcripts (RED + GREEN).

The fix wires ``_shutdown_event`` through to both servers so each one is
told to stop -- ``httpd.shutdown()`` (download_proxy.py) and
``server.should_exit = True`` (main.py) -- both of which their own serve
loops poll every <=0.5s, so real shutdown now completes in roughly ~1s.

This test drives the REAL live container exactly as ``podman/docker stop``
(and therefore ``start.sh``/compose) would, with no timeout override, so it
reproduces the exact production invocation. It is a standing §11.4.135
regression guard for BOB-236: it MUST fail against a pre-fix build and pass
against a post-fix one.
"""

from __future__ import annotations

import shutil
import subprocess
import time

import pytest


CONTAINER = "qbittorrent-proxy"

# Comfortably separates the pre-fix failure mode (~10.0-11.0s, exit 137)
# from the expected post-fix behaviour (~1s, exit 0) without being so tight
# that ordinary host scheduling jitter could flip a passing run (§11.4.50
# deterministic-consistency headroom). Still far below the container's
# configured 10s StopTimeout, so a PASS here is genuine positive evidence
# the SIGKILL path was never reached.
MAX_GRACEFUL_SHUTDOWN_SECONDS = 5.0

SIGKILL_EXIT_CODE = 137


def _runtime() -> str | None:
    for candidate in ("podman", "docker"):
        if shutil.which(candidate):
            return candidate
    return None


def _container_running(runtime: str, name: str) -> bool:
    result = subprocess.run(
        [runtime, "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return name in result.stdout.splitlines()


def _container_exists(runtime: str, name: str) -> bool:
    result = subprocess.run(
        [runtime, "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return name in result.stdout.splitlines()


def _inspect(runtime: str, name: str, fmt: str) -> str:
    result = subprocess.run(
        [runtime, "inspect", "--format", fmt, name],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        pytest.skip(
            f"[SKIP-with-reason feature_disabled_by_config] {runtime} "
            f"inspect failed for {name}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _wait_container_healthy(runtime: str, name: str, timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = subprocess.run(
            [runtime, "ps", "--filter", f"name={name}", "--format", "{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()
        if "healthy" in status.lower() or (_container_running(runtime, name) and "starting" not in status.lower()):
            return
        time.sleep(2)
    pytest.fail(f"[FAIL] {name} did not return to a running/healthy state within {timeout}s")


@pytest.fixture(scope="module")
def runtime() -> str:
    rt = _runtime()
    if rt is None:
        pytest.skip("[SKIP-with-reason hardware_not_present] no podman/docker on PATH")
    return rt


@pytest.fixture
def require_container(runtime: str):
    """SKIP-with-reason when the container topology is absent (§11.4.3).

    Restarts the container after the test (teardown), even on failure, so
    a SIGKILL-triggering RED run never leaves the dev environment down for
    whatever runs next.
    """
    if not _container_running(runtime, CONTAINER):
        pytest.skip(  # allow-skip: container-presence topology gate, not a service probe
            f"[SKIP-with-reason topology_unsupported] {CONTAINER} not running -- "
            f"run './start.sh -p' first"
        )
    yield CONTAINER
    # Teardown: bring it back if the test's own stop left it down.
    if _container_exists(runtime, CONTAINER) and not _container_running(runtime, CONTAINER):
        subprocess.run([runtime, "start", CONTAINER], capture_output=True, timeout=30)
        _wait_container_healthy(runtime, CONTAINER)


def test_sigterm_stops_container_within_grace_period_no_sigkill(
    runtime: str, require_container: str
) -> None:
    """``<runtime> stop qbittorrent-proxy`` (default timeout, exactly as
    production/compose would invoke it) must complete well within the
    container's 10s StopTimeout and must NOT need a SIGKILL.

    Pre-fix this reproducibly took ~10.0-11.0s and exited 137 (killed).
    Post-fix both background service threads are actually told to stop, so
    real shutdown completes in roughly ~1s and the process exits 0 on its
    own, well before the grace period ever expires.
    """
    start = time.monotonic()
    result = subprocess.run(
        [runtime, "stop", CONTAINER],
        capture_output=True,
        text=True,
        timeout=30,
    )
    elapsed = time.monotonic() - start

    assert result.returncode == 0, (
        f"{runtime} stop {CONTAINER} itself failed (rc={result.returncode})\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    exit_code = int(_inspect(runtime, CONTAINER, "{{.State.ExitCode}}"))

    assert exit_code != SIGKILL_EXIT_CODE, (
        f"{CONTAINER} was SIGKILLed (exit code {SIGKILL_EXIT_CODE}) -- SIGTERM alone did "
        f"not stop it within the grace period. runtime stderr:\n{result.stderr}"
    )
    assert elapsed < MAX_GRACEFUL_SHUTDOWN_SECONDS, (
        f"{CONTAINER} took {elapsed:.2f}s to stop (bound: {MAX_GRACEFUL_SHUTDOWN_SECONDS}s) -- "
        f"shutdown is not graceful even though it avoided SIGKILL this time; "
        f"see docs/qa/BOB-236/ for the root-cause writeup."
    )
