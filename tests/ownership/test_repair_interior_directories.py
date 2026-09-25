"""BOB-226 — the repair-side walk MUST reach foreign-owned INTERIOR
directories, not merely the files and symlinks tests/unit/test_ownership_repair.sh
already covers.

WHAT THIS CLOSES
-----------------
``scripts/ownership_repair.sh`` walks a declared scope root and re-owns every
item whose uid is not the operator's (the walk's ``find`` predicate at
``! -uid "${OP_UID}"`` carries no ``-type`` filter at all, so by its own
source it is meant to reach directories exactly as it reaches files). The
unit suite that is meant to prove that, ``tests/unit/test_ownership_repair.sh``,
seeds a foreign uid only onto FILES and SYMLINKS (``seed_wrong -R`` selects
``-type f -o -type l``) — its own header explains why: several of its cases
(8, 9, 18) must create a symlink INSIDE a seeded tree *after* seeding it
wrong, and an unprivileged operator cannot write into a directory it no
longer owns. Case 22 seeds one foreign-owned DIRECTORY, but only the
DECLARED ROOT, and only on the injected-failure path (a shimmed ``chown``
that always fails on that one path) — never on the success path, and never
on an INTERIOR directory reached by recursion.

Production's real first-start repair walks exactly the untested shape:
content a container wrote as root inside a bind mount, where every
directory the container created — not only its files — carries the
container's mapped subuid.

WHY THIS LIVES HERE AND NOT AS ANOTHER CASE IN THE BASH SUITE
----------------------------------------------------------------
This fixture does NOT hit the constraint the header above describes for
cases 8/9/18: no content is written INSIDE a directory *after* that
directory becomes foreign-owned. Every file this test needs lives inside
``wrong_dir``/``nested_wrong_dir`` BEFORE either directory is chowned, and
the chown itself is one non-recursive, one-shot ``<runtime> unshare chown``
call naming every target explicitly (mirroring ``seed_wrong -D`` in the bash
suite, applied to more than the declared root). So the constraint that kept
this shape out of the unit suite is specifically about POST-HOC writes, not
about foreign-owned interior directories as such — but the BOB-226 item's
own ACCEPTANCE criterion asks for this as an INTEGRATION-layer test
alongside ``tests/ownership/test_container_writes_owned_files.py`` (which
already covers the CREATION side, FR-002), so it lands here rather than as
a 23rd case bolted onto an already-3000-line bash file testing a narrower,
harder-to-build shape.

WHAT "CORRECT" MEANS HERE (mirrors test_container_writes_owned_files.py)
--------------------------------------------------------------------------
Every interior directory's owner uid, read back from the host filesystem
after the repair, equals the uid of the account running this test — never
"the script exited 0", never "no exception was raised". Exit code is
checked too, but only as corroboration; the load-bearing assertions read
``os.stat()`` on the actual directories (§11.4.201 — assert the real
condition, not a proxy for it).

MODE PRESERVATION
-------------------
Each seeded interior directory is given a distinctive, non-default mode
(0o751 / 0o740 — chosen so a bug that silently reset either to a common
default such as 0o755 or 0o775 would be caught) BEFORE it is handed the
foreign uid. The repair's own contract (FR-015 / the "MODE IS NEVER
WIDENED" header block in scripts/ownership_repair.sh) is that fixing
ownership must never fix — or break — anything else. A repair that
corrects the uid but chmods the directory to some other value en route
would be exactly the kind of silent side effect FR-015 exists to forbid,
and it would go uncaught by every existing case, because none of them puts
a directory through the repair's success path at all.

ANTI-BLUFF (§11.4.27 / §11.4.201)
------------------------------------
This drives ``scripts/ownership_repair.sh`` for real, over a real
``<runtime> unshare``-seeded tree, via its documented CLI (``--scope`` /
``--state-dir``) — no mock, no stub, no description of expected behaviour.
See ``docs/qa/BOB-226/closure_evidence_*.md`` for the captured RED (this
test failing for the right reason, against a copy of the script whose
directory-repair path was disabled) and GREEN (this test passing against
the real, unmodified script) runs.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ownership_repair.sh"

# Generous but bounded (§12 host-safety) — no image pull is involved (unlike
# test_container_writes_owned_files.py); this only re-enters a user
# namespace and runs the repair script against a small local tree.
RUN_TIMEOUT_S = 120
UNSHARE_TIMEOUT_S = 60


def _runtime() -> str | None:
    """Return an available rootless container runtime, or None.

    Probed, never assumed (§11.4.6): a host without a runtime is a
    legitimate state, not a failure of this feature.
    """
    for candidate in ("podman", "docker"):
        if shutil.which(candidate):
            return candidate
    return None


def _foreign_uid_probe(runtime: str, probe_dir: Path) -> int | None:
    """Return a REAL foreign uid ``<runtime> unshare chown`` can seed here,
    or None if it cannot.

    Mirrors the ``NS_RUNTIME`` probe at the top of
    ``tests/unit/test_ownership_repair.sh``: the mere presence of the
    runtime binary does not prove its ``unshare`` can actually produce a
    not-operator-owned item on this host/kernel — only measuring it does
    (§11.4.201(7)(b) — a null is not evidence until the instrument is
    proven able to see through the same path).
    """
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe_file = probe_dir / "f"
    probe_file.touch()
    result = subprocess.run(
        [runtime, "unshare", "chown", "1:1", "--", str(probe_file)],
        capture_output=True, text=True, timeout=UNSHARE_TIMEOUT_S, check=False,
    )
    if result.returncode != 0:
        return None
    got_uid = probe_file.stat().st_uid
    if got_uid == os.getuid():
        return None
    return got_uid


def _unshare_reap(runtime: str, path: Path) -> None:
    """Remove *path* (and everything under it) from inside the same user
    namespace that seeded it foreign-owned.

    A foreign-owned directory cannot be entered/deleted by the operator —
    that is the defect under test — so a plain ``rmtree`` would raise
    ``PermissionError`` during cleanup. Mirrors
    ``tests/ownership/test_container_writes_owned_files.py::_container_cleanup``.
    Deliberately swallows its own errors: cleanup must never mask a test
    result, and this always runs in a ``finally``.
    """
    try:
        subprocess.run(
            [runtime, "unshare", "rm", "-rf", str(path)],
            capture_output=True, text=True, timeout=UNSHARE_TIMEOUT_S, check=False,
        )
    except Exception:
        pass


_RUNTIME = _runtime()
_FOREIGN_UID: int | None = None
if _RUNTIME is not None:
    _probe_root = Path(tempfile.mkdtemp(prefix="ownership-repair-dirprobe-"))
    try:
        _FOREIGN_UID = _foreign_uid_probe(_RUNTIME, _probe_root)
    finally:
        _unshare_reap(_RUNTIME, _probe_root)
        shutil.rmtree(_probe_root, ignore_errors=True)

# Honest SKIP-with-reason (§11.4.3), not a failure: this feature's property is
# unobservable, not false, when no runtime is present or its `unshare` cannot
# seed a real foreign uid here.
pytestmark = pytest.mark.skipif(
    _FOREIGN_UID is None,
    reason=(
        "no container runtime whose `unshare` can seed a real foreign uid on "
        "this host — a not-operator-owned interior directory cannot be built "
        "unprivileged here (topology_unsupported)"
    ),
)


@pytest.mark.requires_runtime
def test_repair_reaches_interior_directories_and_preserves_their_mode() -> None:
    """RED (pre-BOB-226 coverage): no automated assertion anywhere covered
    this shape, so a repair that silently skipped foreign-owned interior
    directories would have shipped with every existing suite green.

    GREEN: every interior directory the fixture seeds foreign is repaired to
    the operator's uid, its mode is byte-identical to what it was before the
    repair touched it, and every file inside is repaired too.
    """
    assert _RUNTIME is not None and _FOREIGN_UID is not None  # guarded above
    runtime = _RUNTIME
    operator_uid = os.getuid()

    root = Path(tempfile.mkdtemp(prefix="ownership-repair-interior-"))
    try:
        scope_root = root / "declared_scope"
        wrong_dir = scope_root / "wrong_dir"
        nested_wrong_dir = wrong_dir / "nested_wrong_dir"
        leaf_file = wrong_dir / "leaf_file.txt"
        deep_file = nested_wrong_dir / "deep_file.txt"
        control_file = scope_root / "already_correct.txt"

        # --- build the tree AS THE OPERATOR, in full, first ----------------
        # Nothing is ever written INTO wrong_dir/nested_wrong_dir after they
        # become foreign-owned — see the module docstring for why that keeps
        # this fixture buildable unprivileged where cases 8/9/18 could not be
        # extended this way.
        nested_wrong_dir.mkdir(parents=True)
        leaf_file.write_text("leaf\n")
        deep_file.write_text("deep\n")
        control_file.write_text("control\n")

        # Distinctive, non-default modes: a repair that silently normalised
        # either to something else (e.g. the directories' original 0o755
        # from mkdir's default umask) would be caught by comparing against
        # THESE exact values, not against "some plausible directory mode".
        #
        # BOTH modes deliberately keep "other" at r-x (bit 5): the walk's
        # DISCOVERY step (`find`) runs as the unprivileged operator, who
        # falls into the "other" class for a directory it does not own or
        # share a group with — so "other" must retain read+execute or find
        # cannot even list what is inside (measured while writing this
        # test: 0o751 denies "other" read and `find` fails with EPERM
        # before the repair ever gets a chance to run, which is a property
        # of Unix directory permissions, not of ownership_repair.sh, and
        # would have made this test assert something it did not intend to).
        # "Other" write stays denied throughout (bit 5, not 7), so the
        # pre-repair PermissionError assertion below still reproduces the
        # real defect (operator can read/traverse but not write/chown).
        wrong_dir.chmod(0o745)
        nested_wrong_dir.chmod(0o715)
        wrong_dir_mode_before = stat.S_IMODE(wrong_dir.stat().st_mode)
        nested_mode_before = stat.S_IMODE(nested_wrong_dir.stat().st_mode)
        assert wrong_dir_mode_before == 0o745
        assert nested_mode_before == 0o715

        # --- seed the untested shape: a REAL foreign uid on the DIRECTORIES,
        # not only the files inside them -------------------------------------
        # One namespace entry for every target (mirrors seed_wrong -D in the
        # bash suite, applied to more than just the declared root): the
        # operator IS uid 0 inside `<runtime> unshare`, so it can chown
        # ANY of these regardless of the order they are named in.
        seed = subprocess.run(
            [
                runtime, "unshare", "chown", "1:1", "--",
                str(wrong_dir), str(nested_wrong_dir),
                str(leaf_file), str(deep_file),
            ],
            capture_output=True, text=True, timeout=UNSHARE_TIMEOUT_S, check=False,
        )
        assert seed.returncode == 0, (
            f"could not seed the foreign-owned interior-directory fixture: "
            f"rc={seed.returncode} stderr={seed.stderr}"
        )

        # Control needle (§11.4.201(7)(b)): confirm the seed really produced
        # the untested shape — a foreign-owned DIRECTORY, not just a foreign
        # file — before drawing any conclusion from what follows.
        assert wrong_dir.stat().st_uid != operator_uid, (
            "seed via `unshare chown` did not change wrong_dir's uid at all "
            "— the fixture never reached the untested shape, so nothing "
            "below would prove anything"
        )
        assert nested_wrong_dir.stat().st_uid != operator_uid, (
            "seed via `unshare chown` did not change nested_wrong_dir's uid"
        )
        assert control_file.stat().st_uid == operator_uid, (
            "the unseeded control file changed uid — the seed step reached "
            "further than intended"
        )
        # The defect is real, not a proxy for it: the operator genuinely
        # cannot write into a foreign-owned directory ("other" is r-x, not
        # rwx, and the operator is not in the mapped group).
        with pytest.raises(PermissionError):
            (wrong_dir / "should_be_denied_pre_repair").touch()

        # --- declared scope: the same shape the shipped scope file uses ----
        scope_file = root / "owned_paths.yaml"
        scope_file.write_text(
            "schema_version: 1\n"
            "paths:\n"
            f'  - path: "{scope_root}"\n'
            "    kind: downloads\n"
            "    optional: false\n"
            "    preserve_mode: false\n"
            "    recursive: true\n"
        )
        state_dir = root / "state"

        # --- the REAL invocation path: the unmodified production script ----
        run = subprocess.run(
            [
                "bash", str(SCRIPT),
                "--scope", str(scope_file),
                "--state-dir", str(state_dir),
            ],
            capture_output=True, text=True, timeout=RUN_TIMEOUT_S, check=False,
        )

        assert run.returncode == 0, (
            "scripts/ownership_repair.sh did not report success against a "
            "tree containing foreign-owned INTERIOR directories.\n"
            f"rc={run.returncode}\n"
            f"stdout={run.stdout[-2000:]}\n"
            f"stderr={run.stderr[-2000:]}"
        )

        # --- THE LOAD-BEARING ASSERTION: both interior directories, not ----
        # only the files/symlinks the unit suite already covers -------------
        wrong_dir_uid_after = wrong_dir.stat().st_uid
        nested_uid_after = nested_wrong_dir.stat().st_uid
        assert wrong_dir_uid_after == operator_uid, (
            f"interior directory {wrong_dir} is still owned by uid "
            f"{wrong_dir_uid_after} after the repair reported success — the "
            f"repair-side walk does not reach foreign-owned INTERIOR "
            f"DIRECTORIES, only the files/symlinks the unit suite covers "
            f"(BOB-226)"
        )
        assert nested_uid_after == operator_uid, (
            f"nested interior directory {nested_wrong_dir} is still owned "
            f"by uid {nested_uid_after} after the repair reported success "
            f"— a SECOND level of foreign-owned interior directories was "
            f"not reached either (BOB-226)"
        )
        assert leaf_file.stat().st_uid == operator_uid, (
            "the file inside the now-repaired wrong_dir is still foreign-owned"
        )
        assert deep_file.stat().st_uid == operator_uid, (
            "the file inside the now-repaired nested_wrong_dir is still "
            "foreign-owned"
        )
        assert control_file.stat().st_uid == operator_uid  # never touched

        # --- mode preservation: the ACCEPTANCE's second half ---------------
        wrong_dir_mode_after = stat.S_IMODE(wrong_dir.stat().st_mode)
        nested_mode_after = stat.S_IMODE(nested_wrong_dir.stat().st_mode)
        assert wrong_dir_mode_after == wrong_dir_mode_before, (
            f"repairing wrong_dir's ownership changed its mode from "
            f"{oct(wrong_dir_mode_before)} to {oct(wrong_dir_mode_after)} — "
            f"the repair must correct ownership ONLY; FR-015's "
            f"mode-preservation promise is not scoped to files alone"
        )
        assert nested_mode_after == nested_mode_before, (
            f"repairing nested_wrong_dir's ownership changed its mode from "
            f"{oct(nested_mode_before)} to {oct(nested_mode_after)}"
        )

        # The defect is actually gone now, not merely "no error was
        # reported" (§11.4.201): the operator can write into what was, a
        # moment ago, a directory it did not own.
        (wrong_dir / "now_writable_post_repair.txt").write_text("ok\n")

        # Corroboration only (the uid/mode assertions above are what this
        # test is FOR): the documented completion marker exists, so this run
        # really did go through the script's real success path and not some
        # other exit.
        assert (state_dir / "repair-marker.json").exists(), (
            "the repair reported exit 0 but wrote no completion marker — "
            "the run did not go through the documented success path"
        )
    finally:
        _unshare_reap(runtime, root)
        shutil.rmtree(root, ignore_errors=True)
