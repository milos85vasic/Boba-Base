"""
BOB-005 regression: public-tracker plugins must import in the merge-service
plugin harness.

Root cause (reproduced 2026-06-06): the merge service runs each public plugin
via `python3 -c` with `sys.path = <nova3 root>` and `import novaprinter`; every
plugin does `from helpers import ...`. Two stacked defects made EVERY public
plugin fail with "plugin raised an unhandled exception":
  (1) novaprinter.py / helpers.py were copied to nova3/engines/, not the nova3
      ROOT where the harness imports them → ModuleNotFoundError: novaprinter.
  (2) helpers.py does a top-level `import socks` (PySocks) which was absent from
      the python-alpine download-proxy container → ModuleNotFoundError: socks.

This test replicates the EXACT harness in a clean subprocess (so the conftest
socks-stub cannot mask cause #2 — that stub is what hid this bug from the unit
suite). It builds a faithful nova3 layout (framework at root + engines/) from
the repo's plugins/, then asserts representative public plugins import.

§11.4.43 RED-first: against the buggy layout (framework NOT at root) the first
assertion below FAILs (test_buggy_layout_reproduces_modulenotfound proves the
test catches the regression). The fixed layout GREENs.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLUGINS = _REPO_ROOT / "plugins"

# Representative public plugins that import the nova3 framework (novaprinter +
# helpers). Each is a managed plugin shipped in plugins/.
_ENGINES = ["piratebay", "torlock", "yts", "nyaa", "limetorrents"]

# The import-only slice of the real orchestrator harness
# (download-proxy/src/merge_service/search.py::_search_public_tracker).
_HARNESS = (
    "import sys, os\n"
    "sys.path.insert(0, {nova3!r})\n"
    "os.chdir({nova3!r})\n"
    "import importlib\n"
    "import novaprinter\n"
    "m = importlib.import_module('engines.{engine}')\n"
    "getattr(m, '{engine}')\n"
    "print('IMPORT_OK')\n"
)


def _build_nova3(tmp_path: Path, *, framework_at_root: bool) -> Path:
    """Build a nova3 layout from the repo's plugins/. When framework_at_root is
    False we reproduce the BOB-005 bug (framework only under engines/)."""
    nova3 = tmp_path / "nova3"
    engines = nova3 / "engines"
    engines.mkdir(parents=True)
    (engines / "__init__.py").write_text("")
    for eng in _ENGINES:
        src = _PLUGINS / f"{eng}.py"
        (engines / f"{eng}.py").write_text(src.read_text())
    for fw in ("novaprinter.py", "helpers.py"):
        text = (_PLUGINS / fw).read_text()
        # Always present under engines/ (mirrors copy_plugins copying *.py there)
        (engines / fw).write_text(text)
        if framework_at_root:
            (nova3 / fw).write_text(text)
    return nova3


def _run_harness(nova3: Path, engine: str) -> subprocess.CompletedProcess:
    script = _HARNESS.format(nova3=str(nova3), engine=engine)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


@pytest.mark.parametrize("engine", _ENGINES)
def test_public_plugin_imports_in_harness(tmp_path, engine):
    """With the framework at the nova3 root + PySocks available, each public
    plugin imports cleanly via the real harness (catches BOB-005 causes #1+#2)."""
    try:
        import socks  # noqa: F401  — cause #2 guard: PySocks must be installed
    except ModuleNotFoundError:
        pytest.fail(
            "PySocks not installed — public plugins' helpers.py needs it "
            "(BOB-005 cause #2; add PySocks to download-proxy/requirements.txt)"
        )
    nova3 = _build_nova3(tmp_path, framework_at_root=True)
    proc = _run_harness(nova3, engine)
    assert "IMPORT_OK" in proc.stdout, (
        f"{engine} failed to import via harness.\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )


def test_buggy_layout_reproduces_modulenotfound(tmp_path):
    """Negative control: with the framework ONLY under engines/ (the BOB-005
    bug), the harness fails with ModuleNotFoundError — proving this test
    genuinely catches the regression (anti-bluff)."""
    nova3 = _build_nova3(tmp_path, framework_at_root=False)
    proc = _run_harness(nova3, "piratebay")
    assert "IMPORT_OK" not in proc.stdout
    assert "ModuleNotFoundError" in proc.stderr and "novaprinter" in proc.stderr
