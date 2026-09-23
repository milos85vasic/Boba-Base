# BOB-160 closure evidence — 2026-09-23

## Both acceptance criteria now genuinely met

**(1) `ci.sh` gains a runtime-gated pytest `tests/ownership/` stage** —
already present (line ~324): `"$PYTHON" -m pytest
"$SCRIPT_DIR/tests/ownership/" -v --import-mode=importlib --tb=short
--timeout=180`, landed by an unrelated prior commit before this session.

**(2) `scripts/pre_build_verification.sh` invariant 30's glob covers both
`tests/unit/test_*.sh` and `tests/pre_build/test_*.sh`** — resolved THIS
SESSION by BOB-222's fix (tree-wide `find "${PROJECT_ROOT}/tests" -type f
-name 'test_*.sh'` discovery, replacing the old three-directory
hand-maintained glob).

## Independently re-verified this session

```
$ ls tests/ownership/
__init__.py __pycache__ test_container_writes_owned_files.py

$ grep -n "tests/ownership" ci.sh
324: if "$PYTHON" -m pytest "$SCRIPT_DIR/tests/ownership/" -v ...

$ (extracted standalone run of invariant 30's exact discovery block)
unit=32 pre_build=22 total=59
```
The invariant's own discovery genuinely returns a non-zero RAN count
including files from BOTH `tests/unit/` (32) AND `tests/pre_build/` (22) —
exactly the item's own stated acceptance criterion for part (2), verified
directly.

## Honest boundary

Part (1) was already resolved before this session by an unrelated commit
(the tracker was never synced). Part (2) is a direct, intended consequence
of this session's own BOB-222 fix, not independently re-implemented here.

## git diff --stat

```
(none — read-only verification; both fixes already landed via other work)
```
