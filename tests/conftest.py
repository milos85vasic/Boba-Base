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
import types
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


def _resync_submodule_attrs() -> None:
    """Make every parent package's submodule ATTRIBUTE agree with ``sys.modules``.

    Importing ``api.hooks`` has TWO side effects: ``sys.modules["api.hooks"] =
    mod`` AND ``sys.modules["api"].hooks = mod``. The snapshot/restore in
    :func:`_isolate_download_proxy_modules` only ever repaired the first one.
    The second is an in-place mutation of a module object the snapshot copied by
    reference, so restoring ``sys.modules`` cannot undo it.

    That gap produced BOB-135. ``tests/unit/api_layer/test_hooks_coverage.py``
    (and its siblings) legitimately purge ``sys.modules["api.hooks"]`` and
    re-import it; both views then point at the FRESH module. On teardown
    ``sys.modules.update(saved)`` put the ORIGINAL object back in ``sys.modules``
    while the parent attribute kept the fresh one -- from there on, two live
    ``api.hooks`` modules with independent ``HOOKS_FILE`` globals, and which one
    you got depended on how you asked for it:
    ``monkeypatch.setattr("api.hooks.HOOKS_FILE", ...)`` walks the parent
    ATTRIBUTE (pytest's ``derive_importpath``/``resolve``), while ``from
    api.hooks import router`` returns the ``sys.modules`` entry. The patch landed
    on the module the app did not use, so the app kept the real
    ``/config/download-proxy/hooks.json`` path and its write was refused with
    ``[Errno 13] Permission denied: '/config'`` -- a failure that only appeared
    once an earlier test had split the module, i.e. only in the bulk suite.

    ``sys.modules`` is authoritative (it is what ``import`` returns), so parent
    attributes are re-pointed at it. Attributes left orphaned by a purge are
    dropped as well, because ``resolve()`` reads the parent attribute BEFORE it
    attempts an import and would otherwise keep handing out the dead module.

    Guarded by ``tests/unit/test_module_attr_isolation_guard.py`` (§11.4.135).
    """
    # sys.modules -> parent attribute.
    for name, mod in list(sys.modules.items()):
        if "." not in name or not isinstance(mod, types.ModuleType):
            continue
        if name.split(".", 1)[0] not in _POLLUTING_ROOTS:
            continue
        parent_name, _, child = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        # Only real modules: a few tests install a MagicMock as sys.modules["api"]
        # and assert on it, so writing attributes onto it would be pollution of
        # exactly the kind this fixture exists to prevent.
        if not isinstance(parent, types.ModuleType):
            continue
        if getattr(parent, child, None) is not mod:
            setattr(parent, child, mod)

    # Drop parent attributes whose sys.modules entry is gone.
    for name, parent in list(sys.modules.items()):
        if not isinstance(parent, types.ModuleType) or not hasattr(parent, "__path__"):
            continue
        if name.split(".", 1)[0] not in _POLLUTING_ROOTS:
            continue
        for child, value in list(vars(parent).items()):
            if not isinstance(value, types.ModuleType):
                continue
            full = f"{name}.{child}"
            if getattr(value, "__name__", None) == full and full not in sys.modules:
                delattr(parent, child)


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
    # a new one.  The policy's thread-local storage is the only accessor
    # that can read the current loop WITHOUT manufacturing one, so it is
    # the sole probe -- see the no-fallback note below.
    try:
        # Resolving the POLICY getter is interpreter-dependent (BOB-158).
        # asyncio.get_event_loop_policy() is deprecated from 3.14 (slated for
        # removal in Python 3.16) and, under this project's default
        # `error::DeprecationWarning` pytest filter (pyproject.toml), calling
        # it raises DeprecationWarning-as-exception on EVERY test's teardown
        # (this fixture is autouse). asyncio.events._get_event_loop_policy()
        # is the exact same lazy-init implementation the public function
        # delegates to (verified: `get_event_loop_policy` is a one-line
        # `warnings._deprecated(...)` shim around it) with no deprecation
        # shim of its own -- but it is ABSENT on the interpreter production
        # actually runs, 3.12.13 (docker-compose.yml pins python:3.12-alpine;
        # pyproject.toml declares py312 for both ruff and mypy). The exact
        # release that introduced the private name was not probed (no 3.13
        # interpreter available here), so this binds by feature-detection
        # rather than by a version comparison. Measured on the two
        # interpreters that matter, under -W error::DeprecationWarning:
        #
        #   3.14.6   _get_event_loop_policy present; public getter WARNS
        #   3.12.13  _get_event_loop_policy ABSENT;  public getter is silent
        #
        # so binding whichever name this interpreter provides is warning-free
        # on both. Hardcoding the private name made the suite unrunnable on
        # the deployed interpreter: AttributeError on every teardown, which
        # `except RuntimeError` below does not catch (measured: 870 passed,
        # 870 errors for tests/unit/merge_service/ on 3.12.13). The lookup is
        # deliberately lazy rather than a `getattr(..., default)`: a default
        # argument is evaluated eagerly and would itself raise on a future
        # release that has completed the 3.16 removal.
        # See tests/conftest.py Task-7 warnings audit
        # (.superpowers/sdd/task-7-warnings-audit.md) for the root-cause
        # trail: this DeprecationWarning was previously silently absorbed by
        # a too-broad `except Exception: pass` immediately below (§11.4.201(1)
        # false-positive guard-bug).
        _get_policy = getattr(asyncio.events, "_get_event_loop_policy", None)
        if _get_policy is None:
            _get_policy = asyncio.events.get_event_loop_policy
        policy = _get_policy()
        loop = None
        if hasattr(policy, "_local") and hasattr(policy._local, "_loop"):
            loop = policy._local._loop
        # There is deliberately NO `policy.get_event_loop()` fallback here
        # (BOB-158). Under the stock policy `_local._loop` is authoritative --
        # set_event_loop(l) stores l there and get_event_loop() reads it back
        # (measured: `policy._local._loop is l` after set_event_loop(l), on
        # both 3.12.13 and 3.14.6) -- so once it is None there is no
        # pre-existing loop left for a fallback to discover. All the fallback
        # could do was manufacture one, which is exactly what the comment
        # above forbids: measured on 3.12.13 it raises
        # DeprecationWarning("There is no current event loop") -- an error
        # under the filter above, and the second half of BOB-158 -- and,
        # unfiltered, it CREATES a fresh loop only for this block to close.
        # On 3.14.6 it can only raise RuntimeError, which the handler below
        # swallowed, so the dead branch stayed invisible for as long as the
        # suite ran on 3.14 alone. `_local._loop` is present on BOTH
        # interpreters, so removing the fallback costs no coverage on either;
        # a policy without `_local` leaves `loop` None and this fixture
        # correctly does nothing rather than guess.
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
                    # asyncgen finalizer exceptions do NOT escape here:
                    # BaseEventLoop.shutdown_asyncgens() gathers every
                    # ag.aclose() with return_exceptions=True and routes
                    # any Exception subclass to call_exception_handler()
                    # internally (verified against the CPython 3.14
                    # asyncio.base_events source + a live probe: a
                    # deliberately-raising asyncgen finalizer produced
                    # only a "Task exception was never retrieved" log,
                    # nothing propagated through run_until_complete()).
                    # The only exception genuinely reachable from THIS
                    # call is RuntimeError("Event loop is closed") --
                    # reproduced live via `loop.close();
                    # loop.run_until_complete(loop.shutdown_asyncgens())`.
                    # A blanket `except Exception` here previously also
                    # silently swallowed a DeprecationWarning-as-exception
                    # raised anywhere in this block, defeating the
                    # project's error::DeprecationWarning policy --
                    # narrowed per Task-107 followup to Task-7 audit
                    # recommendation #1 (see line ~143 above for the
                    # sibling narrowing + its evidence trail).
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except RuntimeError:
                    pass
                loop.close()
    except RuntimeError:
        # Defensive only. This previously caught the RuntimeError("There is
        # no current event loop in thread ...") raised by the
        # policy.get_event_loop() fallback on 3.14; that call is gone
        # (BOB-158), so the sole reachable source left is loop.close()
        # racing a loop that became running between the is_running() test
        # and the close. Deliberately still narrow: a blanket
        # `except Exception` here previously silently swallowed any
        # DeprecationWarning-as-exception raised by this block's own code
        # (e.g. from a stray deprecated-API call), defeating the project's
        # error::DeprecationWarning enforcement policy -- narrowed per
        # Task-7 warnings audit recommendation #1.
        pass

    # Unset the thread-local loop so the next test starts fresh.
    try:
        # asyncio.set_event_loop(None) delegates to the current policy's
        # set_event_loop(), whose only guard
        # (`if loop is not None and not isinstance(loop, AbstractEventLoop):
        # raise TypeError(...)`) never fires for loop=None -- verified
        # against the CPython 3.14 asyncio.events source, so under the
        # standard policy this call cannot raise at all. RuntimeError is
        # kept as a defensive catch for a custom/third-party event-loop
        # policy that overrides set_event_loop() and raises on teardown
        # (mirrors the sibling `except RuntimeError` narrowing above for
        # "no current event loop"-shaped failures). Verified NOT to raise
        # DeprecationWarning on this project's Python 3.14.6. A blanket
        # `except Exception` here previously silently swallowed a
        # DeprecationWarning-as-exception raised anywhere in this block --
        # narrowed per Task-107 followup to Task-7 audit recommendation #1.
        asyncio.set_event_loop(None)
    except RuntimeError:
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
    _resync_submodule_attrs()
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
        # sys.modules.update(saved) above cannot undo the parent-package
        # attributes the import system mutated in place -- see BOB-135.
        _resync_submodule_attrs()


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
