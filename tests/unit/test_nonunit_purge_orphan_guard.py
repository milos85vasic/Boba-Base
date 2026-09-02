"""Standing regression guard — a non-unit purge must not orphan its importers
(§11.4.135 / §11.4.238).

WHAT THIS CATCHES
-----------------
``tests/conftest.py``'s ``_reinstate_purged_download_proxy_modules`` restores
the download-proxy module roots that a test OUTSIDE ``tests/unit/`` removed or
replaced. Without it, ``tests/concurrency/test_orchestrator_semaphore.py`` (and
its two siblings) delete every ``merge_service*`` key from ``sys.modules`` with
nothing putting them back, while ``api.routes`` stays in ``sys.modules`` still
holding the now-orphaned ``merge_service.qbit_add.qbit_add_succeeded``. The next
import mints a SECOND module object, and
``tests/unit/test_qbit_add_shared_predicate.py::test_both_sites_delegate_to_the_one_implementation``
fails its ``routes`` half — reporting a REAL two-live-copies state.

WHY A BEHAVIOURAL GUARD, NOT A PRESENCE CHECK
---------------------------------------------
Asserting the fixture's NAME appears in ``conftest.py`` would pass against a
fixture whose body had been gutted (§11.4.201 — a guard must assert the REAL
condition, not a proxy for it). This guard therefore RE-DRIVES the measured
three-file reproducer in a subprocess and asserts it is green.

Measured 2026-09-02: with the fixture removed, this exact selection reports
``1 failed, 52 passed`` with
``AssertionError: assert <function qbit_add_succeeded at 0x...> is <function
qbit_add_succeeded at 0x...>`` (two live instances of the SAME function — the
pollution signature, distinct from a genuine re-fork, which renders the left
side as ``_qbit_add_succeeded_shared``). With the fixture present: ``53
passed``.

Keep this file as the permanent §11.4.135 standing regression test — do NOT
delete it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The measured reproducer, in order: an importer that binds ``api.routes`` at
#: collection scope, a non-unit test that purges ``merge_service*``, then the
#: identity assertion that the orphaning breaks.
_REPRODUCER = (
    "tests/unit/test_qbit_login_compat.py",
    "tests/concurrency/test_orchestrator_semaphore.py",
    "tests/unit/test_qbit_add_shared_predicate.py",
)

_TARGET = (
    "tests/unit/test_qbit_add_shared_predicate.py"
    "::test_both_sites_delegate_to_the_one_implementation"
)


def test_non_unit_purge_does_not_orphan_download_proxy_importers() -> None:
    """The three-file reproducer stays green in its measured order."""
    for rel in _REPRODUCER:
        if not (_REPO_ROOT / rel).is_file():
            pytest.skip(f"reproducer file absent: {rel}")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *_REPRODUCER,
            "-p",
            "no:randomly",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, (
        "A non-unit purge orphaned a download-proxy importer -- "
        "tests/conftest.py::_reinstate_purged_download_proxy_modules is missing "
        f"or no longer restores.\n--- stdout ---\n{proc.stdout[-4000:]}"
    )
    assert "failed" not in proc.stdout, proc.stdout[-4000:]
