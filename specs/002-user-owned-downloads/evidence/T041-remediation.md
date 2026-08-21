# T041 remediation — evidence

**Revision:** 1
**Last modified:** 2026-08-21T19:35:00Z

Round: remediation of the T041 independent review (verdict NO-GO — 0 BLOCKING,
5 IMPORTANT, 7 MINOR, 5 NIT), per §11.4.134 iterate-to-zero-finding-GO.

The review's own bottom line is recorded here because it is load-bearing for
what this round did and did not have to fix: *"this round's spot-checks found
no false evidence claims — a first for this feature's reviews"*, and the NO-GO
was carried entirely by coverage and guarantee-boundary gaps, not by a
disproven claim.

---

## IMPORTANT-2 — the repair walked a tree that live containers could still write

**Defect.** On `--recreate`, `start.sh` ran `run_ownership_gate` (precondition
AND repair) BEFORE `recreate_stack` took the stack down. FR-004g calls
repair-vs-download concurrency out of scope "by construction"; the construction
only existed on a cold start. Worst case is the migration moment the feature
exists for — the first `--recreate` after the fix, with the OLD `PUID=1000`
qbittorrent still up and mid-download: it writes non-operator-owned pieces
BEHIND the walk, the marker then records "complete" over a tree that is not,
and those stragglers are never repaired without a manual `--force`.

**RED (captured, pre-fix).** `tests/unit/test_start_reload_recreate.sh`, argv
log from the sandboxed real `start.sh`:

    boba-ctl.sh|config  ownership_precondition.sh  ownership_repair.sh  boba-ctl.sh|down  boba-ctl.sh|up|-d
    FAIL: REPAIR_AFTER_DOWN — down must precede the repair (FR-004d)
    RESULT: 10 passed, 1 failed

**Fix.** `run_ownership_gate` split into `run_ownership_precondition` +
`run_ownership_repair`; `recreate_stack` split into `stack_down` + `stack_up`;
the `--recreate` dispatch reordered to
`precondition -> down -> repair -> up`.

The split is not tidiness — the halves have OPPOSITE quiescence requirements.
The precondition READS `docker-compose.yml`, needs no quiescence, and must run
FIRST so a bad compose is refused BEFORE the operator's stack comes down. The
repair WALKS AND CHOWNS and needs a window where nothing can write. One
function cannot serve both orderings.

`run_ownership_gate` is retained as the warm-path wrapper (still called), so no
dead code was introduced (§11.4.124).

**GREEN.** `RESULT: 11 passed, 0 failed`.

**§1.1 mutation sweep — 11/11 RED-OK, zero BLUFF.** This also proves the
structural split did not silently disarm the EIGHT pre-existing mutations that
anchor on `recreate_stack`'s body (§11.4.120 reconcile-not-fake-pass): the
`print_info`/`print_warning`/`print_error`/`print_success` lines were kept
verbatim across the split precisely so those mutations stay lethal.

**Blast radius (§11.4.92 Pass 2).** Seven sibling suites sharing the modified
harness, all green: `test_start_reload_harness` 6/6, `test_start_reload_python`
10/10, `test_start_reload_plugins` 8/8, `test_ownership_precondition` 20/20,
`test_ownership_rootless_detection` 19/19, `test_credential_store_mode` 18/18,
`test_default_data_dir` 4/4.

**Residual, tracked not hidden.** The WARM path (`./start.sh` over an
ALREADY-RUNNING stack) still has the window. Bounded: after any successful pass
the marker is valid for the scope fingerprint and the repair short-circuits
without walking, so the window needs a stale-or-absent marker AND a live stack
together — which a newly-declared scope entry produces. Filed as **BOB-159**.
The warm-path call-site comment, which had claimed the gate runs "before any
container writes into them", was corrected to state the real boundary (§11.4.6:
it was a misstatement in our own source).

---

## A regression this feature had already caused, found by running the suite

`tests/unit/test_start_reload_recreate.sh` had silently gone **8/8 -> 1/8**:
feature 002's ownership gate refuses when the ownership scripts are missing,
which is every sandboxed test, so the suite could not reach the dispatch at all.

**Control (§11.4.201(7)(b)) — the instrument reads a healthy state as healthy.**
The SAME suite run against the pre-gate `start.sh`, extracted from `c2c47a8^`:

    RESULT: 8 passed, 0 failed

so the drop is the gate, not the suite.

**Not a coverage escape.** Invariant 30 existed at `c2c47a8` (10 token hits),
and `c2c47a8`'s message carries `[skip-ci]` — the §11.4.234(D) recorded
deferral. The regime WOULD have caught it; the deferral was recorded; the owed
debt surfaced now. That is the mechanism working, not a hole.

**Reconciliation.** `harness_new_sandbox` now writes recorder shims for the two
ownership scripts. That restores the 7 broken checks AND makes the gate's ORDER
relative to compose observable in `argv.log` — which is what the three new
FR-004d checks assert. The gate's own correctness is covered by
`test_ownership_precondition.sh` / `test_ownership_repair.sh`; stubbing it in
this suite is a seam, not a weakening.

---

## Two false positives found in gates authored earlier in this same session

**1. Mutation-residue detector, on our own prose.** It flagged
`check_cm_closure_seam_binds.sh:369` — `# A real invocation ALWAYS passes --db`.
That is the transitive-verb sense (supplies the flag) against a regex
`always[ -]pass` that cannot separate it from the verdict sense. The detector's
suspicion of the phrase is correct and load-bearing; the WORDING was the
replaceable half. Reworded to "ALWAYS supplies --db". The line sits inside an
`awk` program body where comments are stripped, so gate behaviour is provably
unchanged: gate rc=0, meta-test 29/29, residue scan 260 files / 0 hits.

**2. Closure-seam gate, on a gerund.** It reported `BOB-120` as a contradiction
"via closes". The only closure-shaped text in `d84d226` is *"closing BOB-120
requires an out-of-user-scope watchdog"* — a gerund heading the noun phrase
that is the SUBJECT of "requires", i.e. a statement of what closure would TAKE.
The same commit says "filed as BOB-120 (Critical, left Queued)". The pattern
`[Cc]los(e|es|ed|ing)` matched it as a declaration.

This is the §11.4.201(1) harm exactly: a permanent false finding against a
correctly-Queued row, which teaches readers to ignore the gate. No
conventional-commit trailer uses the gerund, so it was removed from the
finite-verb alternation. The measured carrier is pinned as a golden-FALSE
fixture, body-scoped so it isolates the closure-keyword rule.

**Mutation proof the fixture has teeth:**

    MUTATED (gerund restored): FAIL c3 gerund discusses closure -> got [closes:BOB-120] want [<none>]
    RESTORED:                  SELF-TEST PASS — extractor sees every spelling, ignores every carrier

Live gate after: **0 stale rows**.

---

## Cross-cutting correction: the uid figure was wrong by exactly 1000

MEASURED via `podman info`: the subuid map is `1 -> 100000 (size 65536)`, and
CLAUDE.md states container uid N maps to host `100000+N-1`. So container uid 911
maps to host **100910**, not `101910`, and `PUID=1000` maps to **100999**.

The wrong figure appeared 4x in `check_cm_ownership_invariants.sh` and 2x in its
meta-test (corrected there), and once in
`evidence/T018-review-NOGO.md`. The evidence file was ANNOTATED, not rewritten —
it is a record of what that review said (§11.4.6). The finding it supports is
unaffected: the defect was that the gate passed the fixture at all, whatever the
exact uid.

---

## Honest gaps at the close of this round (§11.4.6)

1. **`CM-RUNTIME-DEPS-PARITY` still FAILs** — the venv runs CPython 3.14.6 while
   the container runs 3.12.13. Needs the BOB-154 venv rebuild, which BOB-158
   unblocks. Deliberately NOT done during this round: `.venv` is a shared
   exclusive resource and multiple agents were running tests against it
   (§11.4.119 single-resource-owner).
2. **Badge suites FAIL** — README's pre-build badge reads 46 against a live count
   of 48. This drift was introduced by renumbering the gate 44 -> 48 earlier in
   this session without re-running `scripts/compute-badges.sh`. §11.4.259
   requires badges be machine-derived, so the remedy is the generator, never a
   hand-typed number. A second, genuinely separate defect — the generator
   rewriting an unrelated `plugins` badge line — is under root-cause.
3. **`test_check_cm_ownership_invariants.sh` appeared in one contended gate run's
   failure list** while two independent clean runs pass it (42/42 standalone; not
   in the failure list of an isolated invariant-30 run). The log records the name
   without a reason. `UNCONFIRMED:` — needs a re-run on a quiet host before the
   gate is called clean.
4. **`CM-NO-FAIL-OPEN-SKIP` does not exist** in this project although §11.4.69
   mandates it. Confirmed with a control needle (`CM-OWNERSHIP-INVARIANTS`
   resolves to 3 files; `CM-NO-FAIL-OPEN-SKIP` resolves only to the test file
   that mentions it). Filed as **BOB-161**.
