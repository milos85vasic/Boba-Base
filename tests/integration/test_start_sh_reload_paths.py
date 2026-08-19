"""BOB-089 — RED-first tests for ``start.sh --reload-python|--reload-plugins|--recreate``.

Closes the test-coverage gap flagged by §11.4.43/§11.4.115: the three
container-restart subcommands documented in ``CLAUDE.md`` under "Pick
the right restart level" had NO automated verification of their real
runtime contract.

Contracts these tests observe (from ``start.sh`` §687-763):

* ``--reload-python``  → clears ``__pycache__`` inside ``qbittorrent-proxy``
  AND restarts the container (StartedAt bumps forward, same container id).
* ``--reload-plugins`` → restarts ``qbittorrent-proxy`` (StartedAt bumps
  forward, same container id).  DOES NOT copy any plugin file from
  ``plugins/`` into ``config/qBittorrent/nova3/engines/`` — that is
  ``./install-plugin.sh``'s job.
* ``--recreate``       → full compose ``down`` + ``up`` — the
  ``qbittorrent-proxy`` container is DESTROYED and RECREATED, so its
  container id CHANGES (a plain restart would keep the same id).

Each test observes a runtime property the subcommand claims to
produce (§11.4.115(F) — verdicts read from the target at run time,
not source greps).  §11.4.161 rootless podman is auto-detected the
same way ``start.sh`` itself detects it.

The RED-first §11.4.115 evidence for this file lives at
``docs/qa/BOB-089/RED_reload_python_stub.log`` — captured by mutating
``reload_python`` to no-op the container-exec step and observing that
``test_reload_python_clears_pycache_and_restarts`` FAILs (the marker
``__pycache__`` survives).  GREEN capture on the same test with the
mutation reverted lives at ``docs/qa/BOB-089/GREEN_all_three.log``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
START_SH = REPO_ROOT / "start.sh"
CONTAINER = "qbittorrent-proxy"
MARKER_CACHE_DIR = "/config/download-proxy/__pycache__"
MARKER_FILE = f"{MARKER_CACHE_DIR}/BOB_089_marker.pyc"
PLUGIN_MARKER_NAME = "bob089_reload_plugins_marker.py"


# ---------------------------------------------------------------------------
# Helpers — §11.4.161 rootless-podman-preferred runtime detection, mirroring
# start.sh:detect_container_runtime().
# ---------------------------------------------------------------------------


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


def _run_start_sh(subcommand: str, timeout: int) -> subprocess.CompletedProcess:
    """Invoke ``./start.sh <subcommand>`` from the repo root."""
    return subprocess.run(
        ["bash", str(START_SH), subcommand],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
    )


def _wait_container_healthy(runtime: str, name: str, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _container_running(runtime, name):
            return
        time.sleep(1)
    pytest.fail(f"[FAIL] {name} did not return to running state within {timeout}s")


# ---------------------------------------------------------------------------
# Fixtures — SKIP-with-reason when the topology is absent (§11.4.3 /
# §11.4.69 feature_class=container_orchestration).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def runtime() -> str:
    rt = _runtime()
    if rt is None:
        pytest.skip("[SKIP-with-reason hardware_not_present] no podman/docker on PATH")
    return rt


@pytest.fixture(scope="module")
def require_container(runtime: str) -> str:
    if not _container_running(runtime, CONTAINER):
        pytest.skip(
            f"[SKIP-with-reason topology_unsupported] {CONTAINER} not running — "
            f"run './start.sh -p' first"
        )
    return CONTAINER


# ---------------------------------------------------------------------------
# The three contract tests.
# ---------------------------------------------------------------------------


def test_reload_python_clears_pycache_and_restarts(
    runtime: str, require_container: str
) -> None:
    """--reload-python: __pycache__ inside container is cleared AND container restarts."""
    # 1. Plant a marker __pycache__ inside the container (observable state).
    subprocess.run(
        [runtime, "exec", CONTAINER, "mkdir", "-p", MARKER_CACHE_DIR],
        check=True, capture_output=True, timeout=15,
    )
    subprocess.run(
        [runtime, "exec", CONTAINER, "sh", "-c", f"echo BOB-089 > {MARKER_FILE}"],
        check=True, capture_output=True, timeout=15,
    )
    # Confirm marker is present pre-invocation (control-needle per §11.4.201(7b)).
    pre_check = subprocess.run(
        [runtime, "exec", CONTAINER, "test", "-f", MARKER_FILE],
        capture_output=True, timeout=15,
    )
    assert pre_check.returncode == 0, "marker __pycache__ NOT planted — instrument blind"

    before_started = _inspect(runtime, CONTAINER, "{{.State.StartedAt}}")
    before_id = _inspect(runtime, CONTAINER, "{{.Id}}")

    result = _run_start_sh("--reload-python", timeout=120)
    assert result.returncode == 0, (
        f"start.sh --reload-python exited {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    _wait_container_healthy(runtime, CONTAINER)

    # 2. Assert marker __pycache__ is gone (rm -rf clause landed).
    post_check = subprocess.run(
        [runtime, "exec", CONTAINER, "test", "-d", MARKER_CACHE_DIR],
        capture_output=True, timeout=15,
    )
    assert post_check.returncode != 0, (
        f"__pycache__ still exists after --reload-python — cache-clear step did not run"
    )

    # 3. Assert restart really happened (StartedAt bumped forward, same container id).
    after_started = _inspect(runtime, CONTAINER, "{{.State.StartedAt}}")
    after_id = _inspect(runtime, CONTAINER, "{{.Id}}")
    assert after_started != before_started, (
        f"container StartedAt unchanged ({before_started}) — restart step did not run"
    )
    assert after_id == before_id, (
        f"container id changed (was={before_id} now={after_id}) — "
        f"expected restart (same id), not recreate"
    )


def test_reload_plugins_restarts_without_copying_files(
    runtime: str, require_container: str
) -> None:
    """--reload-plugins: restart happens; plugin file NOT auto-copied from plugins/."""
    engines_dir = REPO_ROOT / "config" / "qBittorrent" / "nova3" / "engines"
    plugins_dir = REPO_ROOT / "plugins"
    src_marker = plugins_dir / PLUGIN_MARKER_NAME
    dst_marker = engines_dir / PLUGIN_MARKER_NAME

    # Ensure clean start: no leftover marker either side.
    src_marker.unlink(missing_ok=True)
    dst_marker.unlink(missing_ok=True)
    src_marker.write_text("# BOB-089 marker — must NOT be auto-copied by --reload-plugins\n")

    try:
        before_started = _inspect(runtime, CONTAINER, "{{.State.StartedAt}}")
        before_id = _inspect(runtime, CONTAINER, "{{.Id}}")

        result = _run_start_sh("--reload-plugins", timeout=120)
        assert result.returncode == 0, (
            f"start.sh --reload-plugins exited {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

        _wait_container_healthy(runtime, CONTAINER)

        # Assert restart happened (StartedAt forward, same id).
        after_started = _inspect(runtime, CONTAINER, "{{.State.StartedAt}}")
        after_id = _inspect(runtime, CONTAINER, "{{.Id}}")
        assert after_started != before_started, (
            f"container StartedAt unchanged ({before_started}) — restart step did not run"
        )
        assert after_id == before_id, (
            f"container id changed — expected restart (same id), not recreate "
            f"(was={before_id} now={after_id})"
        )

        # Assert plugin file was NOT auto-copied — that's install-plugin.sh's job.
        assert not dst_marker.exists(), (
            f"--reload-plugins auto-copied {PLUGIN_MARKER_NAME} into {engines_dir} — "
            f"contract violation, that copy is install-plugin.sh's responsibility"
        )
    finally:
        src_marker.unlink(missing_ok=True)
        dst_marker.unlink(missing_ok=True)


@pytest.mark.slow
def test_recreate_stack_destroys_and_recreates_container(
    runtime: str, require_container: str
) -> None:
    """--recreate: qbittorrent-proxy container is DESTROYED and RECREATED (id changes)."""
    before_id = _inspect(runtime, CONTAINER, "{{.Id}}")

    result = _run_start_sh("--recreate", timeout=300)
    assert result.returncode == 0, (
        f"start.sh --recreate exited {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    _wait_container_healthy(runtime, CONTAINER, timeout=120)

    # A recreate destroys the container object and makes a new one — id CHANGES.
    # (A plain restart would keep the same id — that's the discriminator between
    # --reload-python/--reload-plugins and --recreate.)
    after_id = _inspect(runtime, CONTAINER, "{{.Id}}")
    assert after_id != before_id, (
        f"container id unchanged after --recreate ({before_id}) — "
        f"expected destroy+recreate, got a plain restart"
    )
