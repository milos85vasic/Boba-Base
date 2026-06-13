"""Pytest configuration and shared fixtures for qBittorrent-Fixed.

Fixture locations:

*   Mocks and sample data — this file.
*   Live-service fixtures (``merge_service_live``, ``qbittorrent_live``,
    ``webui_bridge_live``, ``all_services_live``) — :mod:`tests.fixtures.services`.

The live fixtures deliberately error (not skip) when services are down,
so that CI reports breakage instead of silently passing. See
docs/superpowers/plans/2026-04-19-completion-initiative.md Phase 0.3.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from typing import Any

# Module roots that unit-test files install/replace as throw-away stubs via raw
# sys.modules assignment (no monkeypatch teardown). They MUST be snapshotted and
# restored around every unit test or they leak across files under randomized
# ordering (§11.4.50 pollution: env_loader/tokyotoshokan/kinozal/rutor/iptorrents).
_POLLUTING_ROOTS = (
    "api",
    "merge_service",
    "config",
    "helpers",
    "env_loader",
    "novaprinter",
    "socks",
    "tokyotoshokan",
    "kinozal",
    "rutor",
    "iptorrents",
)

_CORRECT_MS_PATH: str | None = None

# Cache for the throw-away "pirateiro" stub that test_plugin_pirateiro.py
# registers at module/collection scope. See _isolate_download_proxy_modules
# for why it is re-registered before pirateiro-file tests and purged after
# every unit test (§11.4.50 isolation; guarded by
# tests/unit/test_pirateiro_isolation_guard.py per §11.4.135).
_PIRATEIRO_STUB: Any = None


def _fixup_merge_service_path() -> None:
    """Ensure merge_service in sys.modules has the correct __path__.

    Some test arrangements (including pytest collection of packages under
    tests/unit/merge_service/) can cause merge_service to enter sys.modules
    with __path__ pointing to the test tree instead of download-proxy/src.
    This corrects that.
    """
    global _CORRECT_MS_PATH
    ms = sys.modules.get("merge_service")
    if ms is None:
        return
    if _CORRECT_MS_PATH is None:
        # conftest.py lives at tests/, but download-proxy/ is at the REPO ROOT
        # (tests/../download-proxy). Using .parent (=tests/) produced a
        # non-existent tests/download-proxy/... path that corrupted
        # merge_service.__path__ and broke submodule imports under cross-file
        # ordering (§11.4.50 pollution root cause). Use the repo root.
        _repo_root = Path(__file__).resolve().parent.parent
        _CORRECT_MS_PATH = str(_repo_root / "download-proxy" / "src" / "merge_service")
    if hasattr(ms, "__path__"):
        if _CORRECT_MS_PATH not in ms.__path__:
            ms.__path__ = [_CORRECT_MS_PATH]  # type: ignore[attr-defined]


def _purge_stub_api_module() -> None:
    """Remove stub api packages created by test modules at import time.

    Several test files create a lightweight stub 'api' package via
    sys.modules.setdefault('api', type(sys)('api')) so they can exec_module
    leaf modules (routes.py, etc.) without booting the full FastAPI app.
    If that stub leaks into a later test that expects the real api module
    (e.g. via patch('api.app', ...)), the stub lacks 'app' and the test fails.
    """
    api_mod = sys.modules.get("api")
    if api_mod is not None and not hasattr(api_mod, "app"):
        del sys.modules["api"]

if os.environ.get("MUTANT_UNDER_TEST"):
    _here = Path(__file__).resolve().parent
    if _here.parent.name == "mutants":
        _root = _here.parent.parent
    else:
        _root = _here.parent
    _mutant_src = _root / "mutants" / "download-proxy" / "src"
    if _mutant_src.is_dir():
        sys.path.insert(0, str(_mutant_src.resolve()))
    _mutant_working_dir = _root / "mutants"
    if _mutant_working_dir.is_dir():
        for i, p in enumerate(sys.path):
            resolved = Path(p).resolve()
            if resolved == _mutant_working_dir.resolve():
                sys.path[i] = str(_mutant_src.resolve())
                break


@pytest.fixture(autouse=True)
def _cleanup_event_loop(request):
    """Prevent asyncio event-loop pollution between tests.

    pytest-asyncio 1.3.0 on Python 3.13 uses ``asyncio.Runner`` internally.
    If a prior test leaves a running loop (e.g. via an unclean ``asyncio.run()``
    or a fixture teardown edge-case), subsequent async tests fail with
    ``RuntimeError: Runner.run() cannot be called from a running event loop``.
    This fixture forces a clean slate after every test.
    """
    import asyncio
    import gc

    yield

    # Force GC so any dangling Runner instances are collected before we
    # inspect the loop state.
    gc.collect()

    # Close any loop that was set on the current thread without creating
    # a new one.  We probe the policy's internal storage first; if that
    # fails we fall back to the public API.
    try:
        policy = asyncio.get_event_loop_policy()
        loop = None
        if hasattr(policy, "_local") and hasattr(policy._local, "_loop"):
            loop = policy._local._loop
        if loop is None:
            loop = policy.get_event_loop()
        if loop is not None and not loop.is_closed():
            if loop.is_running():
                # Cancel every task we can reach.
                for task in asyncio.all_tasks(loop):
                    task.cancel()
                # Spin the loop briefly so cancellations take effect.
                # We can't use run_until_complete on a running loop, so we
                # just run a zero-delay call_soon and hope the runner
                # cleans up on its own next cycle.  This is a best-effort
                # mitigation, not a guaranteed fix.
                loop.call_soon(loop.stop)
            else:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()
    except RuntimeError:
        pass
    except Exception:
        pass

    # Unset the thread-local loop so the next test starts fresh.
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _isolate_download_proxy_modules(request):
    """Keep each test's ``sys.modules`` scribbles from leaking into the next.

    Several pre-existing UNIT-test files install throw-away stub packages
    for ``api`` and ``merge_service`` (so they can import leaf modules
    without executing ``api/__init__.py``, which boots FastAPI). If those
    stubs leak into the next test, any subsequent ``from api.routes
    import X`` fails with ``'api' is not a package``.

    The isolation is RESTRICTED to ``tests/unit/`` because those are the
    only callers that install stubs. Integration + e2e tests import the
    real modules and keep live references -- wiping ``merge_service.*``
    out from under them while pytest-asyncio still has scheduled
    coroutines produced KeyError/Exception-ignored cascades that broke
    ``tests/e2e/test_full_pipeline.py``.
    """
    test_path = str(request.node.fspath)
    if "/tests/unit/" not in test_path.replace("\\", "/"):
        yield
        return
    import socket

    # test_plugin_pirateiro.py registers sys.modules["pirateiro"] at MODULE
    # (collection) scope with no teardown. Because it is present before any
    # per-test snapshot, the symmetric snapshot/restore below would preserve it
    # forever and leak it into later tests/unit/ tests (§11.4.50). Its own tests
    # need the stub present at each @patch("pirateiro....") setup. So: cache the
    # stub the first time we see it, RE-REGISTER it before pirateiro-file tests,
    # and PURGE it on teardown of every unit test. Guarded by
    # tests/unit/test_pirateiro_isolation_guard.py (§11.4.135).
    _is_pirateiro_test = "test_plugin_pirateiro.py" in test_path.replace("\\", "/")
    global _PIRATEIRO_STUB
    if "pirateiro" in sys.modules:
        _PIRATEIRO_STUB = sys.modules["pirateiro"]
    if _is_pirateiro_test and _PIRATEIRO_STUB is not None:
        sys.modules["pirateiro"] = _PIRATEIRO_STUB

    saved = {
        k: v
        for k, v in sys.modules.items()
        if k in _POLLUTING_ROOTS or any(k.startswith(root + ".") for root in _POLLUTING_ROOTS)
    }
    # Some unit tests call enable_socks_proxy(True) which sets socket.socket to a
    # SOCKS wrapper (a MagicMock in stubbed plugin tests) and never restores it,
    # poisoning later tests that assert on the real socket (§11.4.50 root cause).
    _saved_socket = socket.socket
    # os.environ leaks across tests too: a credential test that sets e.g.
    # IPTORRENTS_USERNAME without restoring it breaks a later test that asserts
    # the alt-env-var fallback path (which only triggers when the primary vars
    # are absent). Snapshot + restore the whole environment per unit test.
    _saved_environ = dict(os.environ)
    _fixup_merge_service_path()
    _purge_stub_api_module()
    try:
        yield
    finally:
        for k in list(sys.modules):
            if k in _POLLUTING_ROOTS or any(k.startswith(root + ".") for root in _POLLUTING_ROOTS):
                del sys.modules[k]
        sys.modules.update(saved)
        # Purge the collection-time pirateiro stub on the way out of EVERY unit
        # test (see the setup note above). The cached _PIRATEIRO_STUB lets the
        # next pirateiro-file test re-register it before its @patch setup runs.
        sys.modules.pop("pirateiro", None)
        socket.socket = _saved_socket
        os.environ.clear()
        os.environ.update(_saved_environ)
        _fixup_merge_service_path()


# Re-export live-service fixtures so that tests can request them by name
# from any conftest without an explicit import.
from tests.fixtures.services import (
    all_services_live,
    merge_service_endpoint,
    merge_service_live,
    qbittorrent_endpoint,
    qbittorrent_live,
    webui_bridge_endpoint,
    webui_bridge_live,
    webui_bridge_process,
)
from tests.fixtures.compose import compose_up


@pytest.fixture(scope="session")
def docker_compose_command() -> str:
    """Use podman compose instead of docker compose."""
    return "podman compose"


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig: Any) -> str:
    """Use the root docker‑compose.yml, not tests/docker‑compose.yml."""
    return os.path.join(str(pytestconfig.rootdir), "docker-compose.yml")


@pytest.fixture(scope="session")
def docker_compose_project_name() -> str:
    """Use the same project name as the existing stack (qbittorrent)."""
    return "qbittorrent"


@pytest.fixture(scope="session")
def docker_setup() -> list[str]:
    """Skip automatic compose up; we'll handle startup manually."""
    return []


@pytest.fixture(scope="session")
def docker_cleanup() -> list[str]:
    """Skip automatic compose DOWN on teardown.

    pytest-docker's default cleanup is ``compose down -v`` — which would tear
    down a stack the test session did NOT bring up (``docker_setup`` is ``[]``).
    That destroyed the operator's running stack mid-session every time a suite
    touched the ``docker_services`` fixture. We own startup/shutdown via
    ``./start.sh`` / the orchestrator, so the test suite must NEVER ``down`` the
    stack. Empty list = no teardown command (mirrors ``docker_setup``)."""
    return []


from tests.fixtures.live_search import (
    _live_search_cache,
    fresh_magnet_hash,
    fresh_magnet_uri,
    live_search_result,
)


@pytest.fixture
def qbittorrent_host() -> str:
    """Default qBittorrent host."""
    return os.environ.get("QBITTORRENT_HOST", "localhost")


@pytest.fixture
def qbittorrent_port() -> str:
    """Default qBittorrent WebUI port (proxy)."""
    return os.environ.get("QBITTORRENT_PORT", "7185")


@pytest.fixture
def qbittorrent_url(qbittorrent_host: str, qbittorrent_port: str) -> str:
    """Full qBittorrent WebUI URL (container-internal)."""
    return f"http://{qbittorrent_host}:{qbittorrent_port}"


@pytest.fixture
def mock_qbittorrent_api() -> Mock:
    """Mock qBittorrent API client for unit tests."""
    api = Mock()
    api.get_torrents = AsyncMock(return_value=[])
    api.add_torrent = AsyncMock(return_value={"hash": "abc123"})
    api.get_torrent_files = AsyncMock(return_value=[])
    return api


@pytest.fixture
def sample_search_result() -> dict:
    """One novaprinter-shaped search hit."""
    return {
        "name": "Ubuntu 22.04 LTS",
        "link": "magnet:?xt=urn:btih:abc123",
        "size": "2.5 GB",
        "seeds": "100",
        "leechers": "20",
        "engine_url": "https://example-tracker.com",
        "desc_link": "https://example-tracker.com/details/123",
    }


@pytest.fixture
def sample_merged_result() -> dict:
    """One merge-service-shaped merged result."""
    return {
        "canonical_name": "Ubuntu 22.04 LTS",
        "canonical_infohash": "abc123",
        "size": "2.5 GB",
        "sources": [
            {"tracker": "tracker1.com", "seeds": 100, "leechers": 20},
            {"tracker": "tracker2.com", "seeds": 80, "leechers": 15},
        ],
        "total_seeds": 180,
        "total_leechers": 35,
        "download_urls": [
            "magnet:?xt=urn:btih:abc123",
            "https://tracker1.com/download/123",
            "https://tracker2.com/download/456",
        ],
    }
