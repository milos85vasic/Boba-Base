"""BOB-005 regression at the install layer: start.sh::copy_plugins must
place the nova3 framework modules (novaprinter.py, helpers.py) at the nova3
ROOT, not only under engines/.

The merge service runs each public plugin via `python3 -c` with
sys.path = <nova3 root> and `import novaprinter`; every plugin does
`from helpers import ...`. If copy_plugins only copies the framework into
engines/ the harness fails with ModuleNotFoundError (BOB-005 cause #1).

This test drives the REAL start.sh function (no reimplementation): it
sources start.sh in a clean bash subprocess (start.sh has a
`BASH_SOURCE == 0` guard so sourcing does NOT run main), cds into a
hermetic temp tree containing a minimal plugins/ dir, then invokes
copy_plugins and asserts the OBSERVABLE filesystem outcome — the framework
modules exist at config/qBittorrent/nova3/ (root) AND a plugin lands under
engines/.

CONTAINER_RUNTIME is forced to a non-podman value so copy_plugins uses
plain `cp` (no podman/`podman unshare` dependency) — keeping the test
deterministic and offline.

Anti-bluff: a companion negative test runs a stripped copy_plugins variant
that omits the root copy and asserts the root files are ABSENT — proving
the positive assertion is not vacuously satisfied.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_START_SH = _REPO_ROOT / "start.sh"


def _has_bash() -> bool:
    from shutil import which

    return which("bash") is not None


pytestmark = pytest.mark.skipif(not _has_bash(), reason="bash not available on this host")


def _seed_plugins(workdir: Path) -> None:
    """Create a minimal but faithful plugins/ tree under workdir."""
    plugins = workdir / "plugins"
    plugins.mkdir()
    # Framework modules the harness imports.
    (plugins / "novaprinter.py").write_text("# novaprinter fixture\nPRETTY = 'novaprinter'\n")
    (plugins / "helpers.py").write_text("# helpers fixture\nHELPER = 'helpers'\n")
    # A representative engine plugin.
    (plugins / "piratebay.py").write_text("# engine fixture\nclass piratebay:\n    url = 'x'\n")


def _run_copy_plugins(workdir: Path, script_body: str) -> subprocess.CompletedProcess:
    """Source start.sh and run a snippet against the hermetic workdir."""
    # start.sh runs `cd "$SCRIPT_DIR"` at source time, so we MUST cd into the
    # hermetic workdir AFTER sourcing — otherwise copy_plugins resolves the
    # repo's real plugins/ instead of our fixture.
    runner = (
        f"set -euo pipefail\n"
        f"export CONTAINER_RUNTIME=docker\n"  # force plain cp (no podman)
        f'source "{_START_SH}"\n'
        f'cd "{workdir}"\n'
        f"{script_body}\n"
    )
    return subprocess.run(
        ["bash", "-c", runner],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "NO_COLOR": "1"},
    )


def test_copy_plugins_installs_framework_at_nova3_root(tmp_path):
    """Driving the REAL copy_plugins lands novaprinter.py + helpers.py at the
    nova3 root and the engine under engines/ (guards BOB-005 cause #1)."""
    work = tmp_path / "repo"
    work.mkdir()
    (work / "config" / "qBittorrent" / "nova3" / "engines").mkdir(parents=True)
    _seed_plugins(work)

    proc = _run_copy_plugins(work, "copy_plugins")
    assert proc.returncode == 0, f"copy_plugins failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"

    nova3_root = work / "config" / "qBittorrent" / "nova3"
    engines = nova3_root / "engines"

    # OBSERVABLE: framework modules exist at the nova3 ROOT.
    assert (nova3_root / "novaprinter.py").is_file(), "novaprinter.py missing at nova3 root (BOB-005 regression)"
    assert (nova3_root / "helpers.py").is_file(), "helpers.py missing at nova3 root (BOB-005 regression)"
    # OBSERVABLE: the engine plugin landed under engines/.
    assert (engines / "piratebay.py").is_file(), "engine plugin missing under engines/"
    # The root files must be the real framework content, not empty.
    assert (nova3_root / "novaprinter.py").read_text().strip() != ""
    assert (nova3_root / "helpers.py").read_text().strip() != ""


def test_omitting_root_copy_leaves_framework_absent_at_root(tmp_path):
    """Anti-bluff negative control: a copy_plugins variant that only fills
    engines/ (the BOB-005 bug) leaves the framework ABSENT at the root —
    proving the positive test's root-existence assertion is meaningful."""
    work = tmp_path / "repo"
    work.mkdir()
    (work / "config" / "qBittorrent" / "nova3" / "engines").mkdir(parents=True)
    _seed_plugins(work)

    # Mimic the buggy install: copy every plugin file into engines/ ONLY.
    buggy = 'for p in plugins/*.py; do cp "$p" config/qBittorrent/nova3/engines/; done'
    proc = _run_copy_plugins(work, buggy)
    assert proc.returncode == 0, f"buggy snippet failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"

    nova3_root = work / "config" / "qBittorrent" / "nova3"
    # Under the bug, the framework is present under engines/ but NOT at root.
    assert (nova3_root / "engines" / "novaprinter.py").is_file()
    assert not (nova3_root / "novaprinter.py").exists()
    assert not (nova3_root / "helpers.py").exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
