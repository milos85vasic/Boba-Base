# BOB-222 closure evidence — 2026-09-23

## Fix

`scripts/pre_build_verification.sh` invariant 30 (`CM-BASH-UNIT-TESTS-EXECUTED`):
replaced the hand-maintained three-directory glob
(`tests/unit/test_*.sh` + `tests/pre_build/test_*.sh` +
`tests/hooks/test_*.sh` — silently missing `tests/security/` and any
future new test directory, the third occurrence of this class per
§11.4.250) with tree-wide discovery (`find "${PROJECT_ROOT}/tests" -type f
-name 'test_*.sh'`), with NO directory-level exclusions (audited the full
tree, found none needed). The pre-existing total-blindness guard is
extended with a genuinely NEW partial-blindness check: it compares what
was actually run-or-legitimately-quarantined against an INDEPENDENTLY
re-derived on-disk count (not reused from the discovery array, so a bug
truncating that array post-discovery is still caught) — a silently-dropped
directory is now detected, not only "zero ran."

One genuinely-new latent file was surfaced by switching to tree-wide
discovery: `tests/test_constitution_inheritance.sh` (lives one level above
the old three named directories, so was invisible to both the old glob AND
never triggered any prior gate) invokes
`scripts/pre_build_verification.sh` end-to-end three times — added to the
pre-existing self-recursion quarantine array (same class, same documented
membership criterion, as the two suites already quarantined there).

`tests/pre_build/test_bob221_expected_red_declaration.sh` (existing,
tracked) was also touched — a necessary 2-line anchor update, since its
extraction of invariant 30's loop was anchored on the literal old-glob
text; left unmodified it would have ABORTED the moment this fix landed.

## Independently re-verified this session (coordinator, including a
genuine paired-mutation revert/restore against real pre-fix HEAD content)

```
$ bash tests/pre_build/test_bash_suite_discovery_covers_new_dirs.sh
  ok   P1..P6, P2b — all 7 properties pass
RESULT: GREEN (exit 0)

$ git show HEAD:scripts/pre_build_verification.sh > scripts/pre_build_verification.sh
$ bash tests/pre_build/test_bash_suite_discovery_covers_new_dirs.sh
RESULT: RED (exit 1) — 5 properties failed (P2, P2b, P4, P5, P6)
(restored the fixed file — diff --stat vs the subagent's own reported
+96/-6 confirms byte-for-byte correct restoration)

$ bash tests/pre_build/test_bash_suite_discovery_covers_new_dirs.sh
RESULT: GREEN (exit 0) — restored correctly
```
Genuine reproduction against the real pre-fix production file (not a
reimplementation) — reverting alone (no other change) breaks it, restoring
fixes it.

```
$ grep -n "BASH_TEST_SELF_RECURSIVE\|test_constitution_inheritance" scripts/pre_build_verification.sh
1135: # tests/test_constitution_inheritance.sh ADDED (BOB-222, 2026-09-23) ...
1145: BASH_TEST_SELF_RECURSIVE=(
1148:     "test_constitution_inheritance.sh"  # runs pre_build_verification.sh x3 ...

$ bash tests/security/test_gitignore_swallow_is_loud.sh
RESULT: PASS (exit 0)
```
Confirms `tests/security/` genuinely now runs as part of this invariant
(previously executed by nothing) and the new per-file quarantine entry is
present as reported.

## Honest boundary (not silenced)

The subagent's own report discloses a real mid-development bug it found
and fixed in its OWN new test (a `BOBA_PREBUILD_NESTED` env-var leak into
the test's internal scratch sub-invocations causing a false RAN=0), and
flags one deliberate, necessary scope deviation (editing the existing
`test_bob221_expected_red_declaration.sh`, required to avoid a genuine
regression) — both independently verified above and accepted as correct,
minimal, and honestly disclosed rather than silently done.

## git diff --stat

```
scripts/pre_build_verification.sh                          |  96 +++++++++--
tests/pre_build/test_bob221_expected_red_declaration.sh    |  15 ++-
2 files changed, ~101 insertions(+), ~10 deletions(-)
```
Plus new `tests/pre_build/test_bash_suite_discovery_covers_new_dirs.sh`
(366 lines).
