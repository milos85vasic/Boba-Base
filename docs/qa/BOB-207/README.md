# BOB-207 — QA evidence: precondition/repair agreement on the ownership property

**Revision:** 1
**Last modified:** 2026-08-27T00:00:00Z
**Item:** BOB-207 · **Feature:** 002-user-owned-downloads
**Artifacts under test:** `scripts/ownership_repair.sh`, `scripts/lib/ownership.sh`,
`tests/unit/test_ownership_repair.sh`, `tests/unit/test_ownership_gid_agreement.sh`
**Baseline commit:** `a3e1141777914f3d71d62a6cd32a4c79c7f43842` (HEAD at capture time)

---

## Why this directory exists

An earlier report of this work claimed the pre-re-base repair suite was
"146 passed / 0 failed — completely blind" to a mutation. **That figure does
not reproduce from committed history and is WITHDRAWN.** It was measured
against the *uncommitted working-tree* state of
`tests/unit/test_ownership_repair.sh` (which was already ` M` before this work
began), not against `HEAD`. That intermediate was overwritten by the re-base
and not preserved, so the number cannot be re-derived — the defect is the
missing snapshot, not the measurement.

Every figure below is re-derived from committed history in this session, with
the sha256 of the exact artifact each run used. This is the third chain to
lose an uncommitted intermediate (after BOB-195 and BOB-102); the remedy
adopted by both — snapshot before editing — is adopted here.

## The corrected claim

The committed suite **does** catch a selects-nothing walk. What it cannot see
is the loss of the **namespace fallback** — `unshare_chown_paths()`, the only
code path able to repair the production defect (a foreign uid, which a plain
`chown` cannot touch: EPERM). The old fixture used a *gid* mismatch, which a
plain `chgrp` repairs, so that path was never reached and its removal was
invisible.

| # | Suite | Repair artifact | Mutation | Result | Verdict |
|---|---|---|---|---|---|
| A | committed | committed | none (control) | 86 / 0 / 0 · rc 0 | baseline |
| B | committed | committed | `unshare_chown_paths` disabled | **86 / 0 / 0 · rc 0** | **BLIND** |
| C | committed | committed | walk selects nothing (`-false`) | 61 / 18 / 1 · rc 1 | catches |
| D | re-based | narrowed | none (control) | 146 / 0 / 0 · rc 0 | baseline |
| E | re-based | narrowed | `unshare_chown_paths` disabled | **101 / 37 / 1 · rc 1** | **CATCHES** |
| F | re-based | narrowed | walk selects nothing (`-false`) | 116 / 23 / 1 · rc 1 | catches |

**B vs E is the load-bearing pair.** Identical mutation, opposite verdicts:
the committed suite ships green while the production repair path is gone; the
re-based suite fails 37 checks. That is what the re-base bought, and it is a
narrower, stronger claim than the withdrawn one.

C is recorded because it *refutes* the withdrawn "completely blind" wording:
on the selects-nothing axis the old suite was never blind.

## Artifact provenance (sha256, first 16)

| Config | suite | repair |
|---|---|---|
| A | `e3aaa7ed49e663f0` | `ae025b74602414ca` |
| B | `e3aaa7ed49e663f0` | `d55a0c098129436e` |
| C | `e3aaa7ed49e663f0` | `8b8b0b7b91a095b0` |
| D | `03fb989d2781acdd` | `47889d4cd25fcdb1` |
| E | `03fb989d2781acdd` | `0c470e9aeb5a58bf` |
| F | `03fb989d2781acdd` | `9874e64eea4b4e6f` |

A/B/C share the committed suite; D/E/F share the re-based suite. The repair
hash differs per mutation, so no two rows can be the same run mislabelled.

## Commands

```bash
# committed-history tree (configs A-C)
git show HEAD:scripts/ownership_repair.sh         > $T/scripts/ownership_repair.sh
git show HEAD:scripts/lib/ownership.sh            > $T/scripts/lib/ownership.sh
git show HEAD:tests/unit/test_ownership_repair.sh > $T/tests/unit/test_ownership_repair.sh

# mutation B/E — disable the fallback at its source (both call sites: the
# batch path at flush_batch and the per-path path in repair_one)
#   UNSHARE_ERR="$("${RUNTIME}" unshare chown -h -- 0:0 "$@" 2>&1 >/dev/null)" && return 0
#   return 1
# becomes
#   UNSHARE_ERR="MUTATION: namespace fallback disabled"
#   return 1

# mutation C/F — the walk selects nothing
#   find_args+=(-false -printf '%U\t%G\t%m\t%p\0')

timeout 900 nice -n 19 ionice -c 3 bash $T/tests/unit/test_ownership_repair.sh
```

Raw output for every configuration is in `runs/`.

## Final state of the shipped tree

| Suite | Result |
|---|---|
| `tests/unit/test_ownership_gid_agreement.sh` | 5 / 0 / 0 · rc 0 (`runs/agreement_suite_final.txt`) |
| `tests/unit/test_ownership_repair.sh` | 146 / 0 / 0 · rc 0 (`runs/config_D.txt`) |
| `tests/pre_build/test_check_cm_ownership_invariants.sh` | 42 / 42 · rc 0 (`runs/pre_build_gate_final.txt`) |

Reverting the one-line predicate change restores the original BOB-207 failure
verbatim — `runs/mutation_revert_predicate.txt`, 4 passed / 1 failed / rc 1.

## A mutation that did NOT hold, recorded

Removing only `|| unshare_chown_paths` from `flush_batch` left the suite green.
Not a fake-pass: `repair_one()` is a second call site, so the tool legitimately
still repaired. Mutations B/E therefore disable the function at its source.
Recorded because a mutation that fails to fail is a result, not a nuisance.

## Fixture note

The re-based suite seeds a **real foreign uid** via `podman unshare chown 1:1`
(host-visible `100000`), replacing the gid proxy. Files and symlinks carry the
foreign uid; directories stay operator-owned except Case 22's declared root —
see the DECLARED GAPS output in `runs/config_D.txt` and `FOLLOWUP_ITEMS.md` ITEM 1.
