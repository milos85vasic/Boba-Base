"""BOB-005 (broad): MORE public-tracker plugins must import in the harness.

Companion to test_public_plugin_harness.py. That test pins a small
representative set (piratebay, torlock, yts, nyaa, limetorrents). This test
broadens coverage to every OTHER managed public plugin in plugins/ that
imports the nova3 framework (novaprinter + helpers), so a framework-layout
regression (BOB-005 cause #1) or a missing PySocks (cause #2) is caught
across the full installed surface, not just the representative slice.

Anti-bluff: it reuses the EXACT real harness — `python3 -c` in a clean
subprocess with sys.path = <nova3 root>, `import novaprinter`, and
`importlib.import_module('engines.<name>')` — so the conftest socks-stub
cannot mask cause #2. A negative-control test reproduces the buggy layout
(framework only under engines/) and asserts ModuleNotFoundError, proving
the harness genuinely catches the regression.

Each engine is filesystem-verified to exist in plugins/ before use; names
that don't exist are skipped (so this test stays correct as plugins/
evolves without becoming a silent bluff).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLUGINS = _REPO_ROOT / "plugins"

# Public plugins NOT already covered by test_public_plugin_harness.py. Each
# imports the nova3 framework and exposes a class matching its module name.
# (iptorrents is a private-tracker plugin and intentionally excluded.)
_BASE_HARNESS_COVERED = {"piratebay", "torlock", "yts", "nyaa", "limetorrents"}
_CANDIDATE_ENGINES = [
    "anilibra",
    "bitsearch",
    "eztv",
    "gamestorrents",
    "kickass",
    "megapeer",
    "solidtorrents",
    "tokyotoshokan",
    "torrentgalaxy",
    "torrentkitty",
]

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


def _engines_present() -> list[str]:
    present = []
    for eng in _CANDIDATE_ENGINES:
        if eng in _BASE_HARNESS_COVERED:
            continue
        if (_PLUGINS / f"{eng}.py").is_file():
            present.append(eng)
    return present


_ENGINES = _engines_present()


def _build_nova3(tmp_path: Path, engines: list[str], *, framework_at_root: bool) -> Path:
    """Build a faithful nova3 layout from the repo's plugins/. When
    framework_at_root is False, reproduce the BOB-005 bug (framework only
    under engines/)."""
    nova3 = tmp_path / "nova3"
    engines_dir = nova3 / "engines"
    engines_dir.mkdir(parents=True)
    (engines_dir / "__init__.py").write_text("")
    for eng in engines:
        (engines_dir / f"{eng}.py").write_text((_PLUGINS / f"{eng}.py").read_text())
    for fw in ("novaprinter.py", "helpers.py"):
        text = (_PLUGINS / fw).read_text()
        # mirrors copy_plugins copying every *.py into engines/
        (engines_dir / fw).write_text(text)
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


def test_engine_candidate_set_is_non_empty():
    """Guard against the test silently covering nothing if plugins/ is
    reorganised (a zero-engine run would be a coverage bluff)."""
    assert _ENGINES, (
        "No broad-harness engines found in plugins/ — update _CANDIDATE_ENGINES "
        "or investigate why the managed public plugins are missing."
    )


@pytest.mark.parametrize("engine", _ENGINES)
def test_public_plugin_imports_in_harness_broad(tmp_path, engine):
    """Each additional managed public plugin imports cleanly via the real
    harness with the framework at the nova3 root + PySocks available."""
    try:
        import socks  # noqa: F401 — cause #2 guard: PySocks must be installed
    except ModuleNotFoundError:
        pytest.fail(
            "PySocks not installed — public plugins' helpers.py needs it "
            "(BOB-005 cause #2; add PySocks to download-proxy/requirements.txt)"
        )
    nova3 = _build_nova3(tmp_path, [engine], framework_at_root=True)
    proc = _run_harness(nova3, engine)
    assert "IMPORT_OK" in proc.stdout, (
        f"{engine} failed to import via harness.\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )


def test_buggy_layout_reproduces_modulenotfound_broad(tmp_path):
    """Negative control: with the framework ONLY under engines/ (BOB-005
    bug), the harness fails with ModuleNotFoundError for novaprinter —
    proving this test genuinely catches the regression (anti-bluff)."""
    engine = _ENGINES[0]
    nova3 = _build_nova3(tmp_path, [engine], framework_at_root=False)
    proc = _run_harness(nova3, engine)
    assert "IMPORT_OK" not in proc.stdout
    assert "ModuleNotFoundError" in proc.stderr and "novaprinter" in proc.stderr
