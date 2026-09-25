# BOB-143 closure evidence — 2026-09-25

**Item:** BOB-143 — Orphaned `.worktrees/` dirs (46M, unresolvable gitdir) pollute
gate scan scope and manufacture false BOB-126-class findings.

**Fix implemented:** option (b) from the item's own text — add `.worktrees/` to
the gate scan-scope exclusion list as a §11.4.224(E)-fenced, checked-in,
justified entry. **Deletion was NOT performed** (and, as established below,
was not even applicable in this checkout — see "Pre-fix investigation").
Nothing inside `.worktrees/` was touched.

---

## 0. Pre-fix investigation (root cause first, per systematic-debugging)

Before writing anything, I verified the item's premise against the live
checkout, per the constitution's "reproduce first" / "no guessing" discipline.

```
$ test -d .worktrees && echo "EXISTS: .worktrees" || echo "MISSING: .worktrees"
MISSING: .worktrees

$ find . -maxdepth 4 -iname "*worktree*" -not -path "./submodules/*" -not -path "./.git/*"
./docs/proposals/subagent-worktree-isolation.md
./docs/proposals/subagent-worktree-isolation.html
./docs/proposals/subagent-worktree-isolation.docx
./docs/proposals/subagent-worktree-isolation.pdf
./constitution/scripts/multitrack/multitrack_resolve_worktree.sh
```

**Finding:** `.worktrees/ci-split-workflows/` and
`.worktrees/completion-initiative-phase-0/` do **not exist** in this checkout
today. They were local, gitignored, host-side scratch directories at the time
BOB-143 was filed (2026-08-20); by 2026-09-25 they are simply absent from
disk (this session's checkout never had them, or they were cleaned up by
unrelated host activity in the interim — either way, git carries no record
of their removal since they were never tracked). This does not change the
task: the item's own acceptance criterion explicitly names exclusion as a
valid, sufficient close path *independent of whether the directories currently
exist* ("or `.worktrees/` is added to a checked-in ... exclusion list"), and
the constitution's own §11.4.6 boundary applies — I did not invent or assume
their presence, I measured it and proceeded on what the checkout actually
shows. A synthetic, deterministic fixture (mirroring the precedent
`tests/pre_build/test_check_cm_go_toolchain_matches_builder.sh` /
BOB-194 pattern, whose own comment states "does not depend on a worktree
happening to exist on disk, which is how the real-tree case caught it only by
luck") is therefore the correct RED/GREEN vehicle here, not a live `.worktrees/`
tree.

## 1. Investigation of the two measured findings

### 1a. `cm_test_mock_pid_explicit_int` (CM-TEST-MOCK-PID-EXPLICIT-INT)

Traced the two invocation paths of this gate in the repository:

- `scripts/pre_build/check_cm_test_mock_pid_explicit_int.sh` — the thin
  wrapper `pre_build_verification.sh` invariant 28 uses. Its
  `DEFAULT_SCAN_ROOTS=("tests")` — it only ever walks `$REPO_ROOT/tests`, so
  a top-level `.worktrees/` directory is structurally outside its scan and
  was never the source of the BOB-143 finding.
- `constitution/scripts/gates/cm_test_mock_pid_explicit_int.sh` (the shared
  engine) invoked **directly** by `scripts/verify-all-constitution-rules.sh`
  (boba's §11.4.32 sweep — the exact instrument BOB-143 cites: "Measured
  2026-08-20 by the §11.4.32 sweep") with `--root @ROOT@` (the whole
  repository) via `config/constitution-sweep.conf`'s `DEFAULT` row. **This**
  is where the false findings were sourced.

Reading `scripts/verify-all-constitution-rules.sh`, this half is **already
fixed** — by commit `c0ea01c` (title unrelated to BOB-143, but its body
lands the fix), which added:

```sh
_BOB143_SWEEP_EXCLUDE=".git node_modules vendor .venv __pycache__ scripts/gates out build dist .worktrees"
export DANGEROUS_COMBO_EXCLUDE="${DANGEROUS_COMBO_EXCLUDE:-$_BOB143_SWEEP_EXCLUDE}"
...
_BOB152_VENDORED_EXCLUDE="${_BOB143_SWEEP_EXCLUDE} submodules"
export MOCK_PID_GUARD_EXCLUDE="${MOCK_PID_GUARD_EXCLUDE:-$_BOB152_VENDORED_EXCLUDE}"
export ORACLE_GUARD_EXCLUDE="${ORACLE_GUARD_EXCLUDE:-$_BOB152_VENDORED_EXCLUDE}"
export KILLPG_GUARD_EXCLUDE="${KILLPG_GUARD_EXCLUDE:-$_BOB152_VENDORED_EXCLUDE}"
```

`.worktrees` is present in `_BOB143_SWEEP_EXCLUDE`, which every one of these
four env-var exports inherits. Item BOB-143 was never closed to reflect this,
so I treated this as an **already-fixed half needing a regression guard**,
not something to re-implement. Confirmed my mutation test above
(`_BOB143_SWEEP_EXCLUDE no longer names .worktrees` abort) catches a future
regression of exactly this wiring.

### 1b. "6 of 57 missing anchor carrier" propagation-gate findings

Traced to `scripts/verify-all-constitution-rules.sh`'s delegation of the
whole `CM-COVENANT-114-<N>-PROPAGATION` family to
`constitution/scripts/gates/covenant_propagation_suite.sh gates --root
"$root"` (boba's own root). The suite pre-computes a carrier list with its
own `find`, and the shared engine
(`constitution/scripts/gates/lib/covenant_propagation_engine.sh`) does its
own carrier discovery too when not given a precomputed list — **neither
pruned `.worktrees`**, and **neither may hardcode a project path** (both are
upstream, inherited by reference per §11.4.28/§11.4.177 — a boba-specific
literal must never be injected into them). Both already read a
**consumer-owned, checked-in exclusion file**:

```
default: <root>/config/covenant_propagation_exclusions.tsv
override: $COVENANT_PROPAGATION_EXCLUSIONS
```

documented in the engine's own header as "the §11.4.224(E) exclusion fence +
the §11.4.135 checked-in-exemption-map pattern", with a **closed class set**
`{vendored-third-party | generated-code | non-shipping-fixtures |
filename-collision}` the engine validates and fails closed (exit 2 / BLIND)
on any row outside it or with no justification. **This file did not exist in
boba** (`config/covenant_propagation_exclusions.tsv` was absent). This is the
genuinely unaddressed half of BOB-143, and is the actual fix delivered here.

I found a real-world precedent of this exact mechanism already in production
use in a sibling project (`/home/milosvasic/Projects/vasic/config/
covenant_propagation_exclusions.tsv`, read-only, for format reference only —
not part of this repository) — confirming the schema and that this is the
established, intended consumer-side mechanism rather than something invented
for this fix.

## 2. Files found and modified

| File | Action | Why |
|---|---|---|
| `config/covenant_propagation_exclusions.tsv` | **Created** | The checked-in, §11.4.224(E)-fenced exclusion-list entry BOB-143 option (b) asks for. Read by default by both `constitution/scripts/gates/lib/covenant_propagation_engine.sh` (single-gate carrier discovery) and `constitution/scripts/gates/covenant_propagation_suite.sh` (the batch runner's own carrier precompute) — no wiring change needed anywhere else, since both already default to `${root}/config/covenant_propagation_exclusions.tsv` and `--root` for boba's own §11.4.32 sweep is always boba's repo root. |
| `tests/pre_build/test_bob143_worktrees_exclude_scope.sh` | **Created** | §1.1 paired-mutation proof, mirroring the proven shape of `tests/pre_build/test_bob152_vendored_exclude_scope.sh` (the closest precedent — same exclude-scope class, same sweep script). Proves the new exclusion row is well-formed, load-bearing on BOTH the direct-engine invocation path and the production `covenant_propagation_suite.sh` invocation path, and regression-guards the already-fixed MOCK_PID/ORACLE/KILLPG/DANGEROUS_COMBO wiring in `scripts/verify-all-constitution-rules.sh`. |

**Files explicitly NOT touched** (per scope): `scripts/pre_build_verification.sh`
(a concurrent, unrelated 135-line diff was already present in the working
tree when I started — not made by me, confirmed by `git diff --stat`
showing changes I never authored), `.gitignore`, anything under
`.worktrees/` (doesn't exist), `download-proxy/`, `plugins/`, `docs/guides/`,
`tests/ownership/`, `tests/integration/test_container*`, `docs/workable_items.db`,
the `workable-items` CLI.

**Why `scripts/pre_build_verification.sh` was NOT the fix location:** the
constitution submodule's engine and suite explicitly forbid a project literal
being hardcoded into them (§11.4.28/§11.4.177 — inherited by reference,
never copied, never given project-specific context), and both already
implement a documented, purpose-built, checked-in consumer-DATA exclusion
mechanism reading `config/covenant_propagation_exclusions.tsv` by default.
Adding the row there is the mechanism these files were designed for; editing
`pre_build_verification.sh` was neither necessary (its own
`CM-COVENANT-PROPAGATION-SUITE` invocation at "Invariant 32" passes
`--root "${PROJECT_ROOT}/constitution"` — the constitution **submodule's**
root, not boba's — so it was never the source of the `.worktrees`-sourced
findings the item measured and needs no change here) nor in scope (it is
explicitly excluded by the task).

## 3. RED — before the fix

Manual reproduction against a synthetic fixture (since the real `.worktrees/`
directories no longer exist — see §0), run BEFORE `config/
covenant_propagation_exclusions.tsv` existed:

```
$ mkdir -p "$WORK/.worktrees/probe" "$WORK/worktrees/control"
$ printf 'This is a stale orphaned worktree copy. No anchor block here.\n' > "$WORK/.worktrees/probe/CLAUDE.md"
$ printf 'This is a stale sibling non-dot worktrees dir. No anchor block here.\n' > "$WORK/worktrees/control/CLAUDE.md"
$ printf '**§11.4.230 — Parallelized-pipeline methodology.** Real correct anchor block text so at least one carrier passes.\n' > "$WORK/CLAUDE.md"

$ bash constitution/scripts/gates/cm_covenant_114_230_propagation.sh --root "$WORK" --quiet
❌ MISSING     worktrees/control/CLAUDE.md  — zero 11.4.230 block-starts (bare-literal citations elsewhere do not count, §11.4.201(7)(a))
❌ MISSING     .worktrees/probe/CLAUDE.md  — zero 11.4.230 block-starts (bare-literal citations elsewhere do not count, §11.4.201(7)(a))
----------------------------------------------------------------------
CM-COVENANT-114-230-PROPAGATION: 1 single-block-PRESENT, 0 POINTER-INHERITANCE-SKIP, 2 MISSING/DUPLICATED, 0 DIVERGENT (anchor 11.4.230) under $WORK
❌ CM-COVENANT-114-230-PROPAGATION: FAIL — anchor-block integrity violated for §11.4.230
rc=1
```

This reproduces the item's exact measured shape: a `.worktrees/**` carrier
manufacturing a false MISSING finding indistinguishable from a real one
(§11.4.201(1) false-positive refusal).

Formal paired-mutation proof, run with the fix FILE ABSENT
(`config/covenant_propagation_exclusions.tsv` moved aside):

```
$ mv config/covenant_propagation_exclusions.tsv /tmp/...bak
$ bash tests/pre_build/test_bob143_worktrees_exclude_scope.sh
== BOB-143 .worktrees/ exclude scope proof ==
gates dir: /home/milosvasic/Projects/boba/constitution/scripts/gates
exclusions file: /home/milosvasic/Projects/boba/config/covenant_propagation_exclusions.tsv
ABORT: the fix (config/covenant_propagation_exclusions.tsv) is absent — nothing to prove
EXIT=3
$ mv /tmp/...bak config/covenant_propagation_exclusions.tsv   # restored
```

Second mutation — file present but the load-bearing row dropped (the more
realistic "someone edited the file and lost the row" regression):

```
$ cp config/covenant_propagation_exclusions.tsv /tmp/...real
$ printf '# mutated: .worktrees row dropped\n*/some-other-dir\tgenerated-code\tunrelated placeholder row\n' > config/covenant_propagation_exclusions.tsv
$ bash tests/pre_build/test_bob143_worktrees_exclude_scope.sh
== BOB-143 .worktrees/ exclude scope proof ==
...
ABORT: expected exactly 1 '*/.worktrees' row in .../config/covenant_propagation_exclusions.tsv, found 0
EXIT=3
$ cp /tmp/...real config/covenant_propagation_exclusions.tsv   # restored, byte-identical (diff -q confirmed)
```

Third mutation — regression-guard for the *already-fixed* half (BOB-143's
CM-TEST-MOCK-PID-EXPLICIT-INT wiring in the sweep script itself):

```
$ sed -i 's/... dist .worktrees"/... dist"/' scripts/verify-all-constitution-rules.sh
$ bash tests/pre_build/test_bob143_worktrees_exclude_scope.sh
== BOB-143 .worktrees/ exclude scope proof ==
row confirmed: */.worktrees	filename-collision	<justification, 1019 chars>
ABORT: _BOB143_SWEEP_EXCLUDE no longer names .worktrees (got: .git node_modules vendor .venv __pycache__ scripts/gates out build dist) — the already-measured-fixed half of BOB-143 regressed
EXIT=3
$ cp /tmp/...bak scripts/verify-all-constitution-rules.sh   # restored, diff -q confirmed identical to HEAD
```

All three mutations correctly fail the test (exit 3 — an honest ABORT that
refuses to certify a verdict when the fix's own precondition is absent,
matching the same convention `tests/pre_build/test_bob152_vendored_exclude_
scope.sh` already uses for its own missing-precondition case).

## 4. GREEN — after the fix

```
$ bash tests/pre_build/test_bob143_worktrees_exclude_scope.sh
== BOB-143 .worktrees/ exclude scope proof ==
gates dir: /home/milosvasic/Projects/boba/constitution/scripts/gates
exclusions file: /home/milosvasic/Projects/boba/config/covenant_propagation_exclusions.tsv
row confirmed: */.worktrees	filename-collision	<justification, 1019 chars>
sweep wiring confirmed: _BOB143_SWEEP_EXCLUDE still names .worktrees (feeds MOCK_PID/ORACLE/KILLPG/DANGEROUS_COMBO_EXCLUDE)

---- direct-engine: cm_covenant_114_230_propagation.sh ----
baseline (empty exclusions file): probe seen (1 hit(s)), control seen (1 hit(s)) — instrument PROVEN seeing both locations
PASS: with the real BOB-143 exclusion active, .worktrees/-rooted probe EXCLUDED (0 hits, and the ⊘ EXCLUDED line was printed), worktrees/-rooted control STILL CAUGHT (1 hit(s)).

---- suite-path: covenant_propagation_suite.sh gates (production invocation shape) ----
baseline (empty exclusions file): anchor 230 row reports 2 MISSING/DUPLICATED (probe + control) — instrument PROVEN seeing both locations
PASS: via the suite path, with the real BOB-143 exclusion active anchor 230's row reports exactly 1 MISSING/DUPLICATED (the worktrees/ control only — the .worktrees/ probe's MISSING dropped out, i.e. was excluded from discovery).

VERDICT: PASS — BOB-143's .worktrees/ exclusion is load-bearing (excluded) while worktrees/ (no dot) is still caught, on both the direct-engine and the production suite invocation paths; the already-fixed MOCK_PID/ORACLE/KILLPG/DANGEROUS_COMBO wiring still names .worktrees.
EXIT=0
```

**Manual confirmation against the real boba root** (proves the fix is
actually wired for real use, not just the hermetic fixture):

```
$ bash constitution/scripts/gates/cm_covenant_114_230_propagation.sh --root . --quiet | head -3
CM-COVENANT-114-230-PROPAGATION: consumer exclusions applied (1) from /home/milosvasic/Projects/boba/config/covenant_propagation_exclusions.tsv:
    ⊘ EXCLUDED  */.worktrees  [filename-collision]
❌ MISSING     AGENTS.md  — zero 11.4.230 block-starts ...
```

(The `AGENTS.md` / `challenges/fixtures/anchor_block_integrity/**` MISSING
lines that follow are **pre-existing, unrelated** findings — AGENTS.md
genuinely lacks the §11.4.230 block today, and `challenges/fixtures/
anchor_block_integrity/**` are the propagation engine's OWN golden-bad/
golden-good meta-test fixtures, deliberately missing blocks by design. Both
are out of BOB-143's scope and untouched by this fix — confirming the
exclusion did not widen to swallow anything beyond `.worktrees`.)

## 5. Proof the fix does NOT create a blind spot (§11.4.201(6))

This is built into the test itself (`worktrees/` non-dot control, always
proven still-caught in every scenario above) rather than a separate step:
every PASS in §4 explicitly asserts the sibling `worktrees/bob143_control/
CLAUDE.md` (no leading dot — same word, deliberately similar name, genuinely
different path) is **still flagged MISSING** with the exclusion active. The
exclusion glob is `*/.worktrees` (an exact directory-name match via `find
-path`), which cannot match a directory named `worktrees` (no leading dot) —
proven empirically, not merely asserted, in both the direct-engine and the
suite invocation paths.

## 6. No regression — existing tests re-run clean

```
$ bash -n tests/pre_build/*.sh   # every file in the directory
syntax sweep done   (0 failures)

$ timeout 120 bash constitution/scripts/gates/cm_covenant_114_230_propagation_mutation_test.sh
...
✅ META PASS: CM-COVENANT-114-230-PROPAGATION is a genuine (non-bluff) gate
EXIT=0

$ bash scripts/pre_build/check_cm_test_mock_pid_explicit_int.sh
  scope: default (tests), repo-root: /home/milosvasic/Projects/boba
  files scanned: 357
PASS: CM-TEST-MOCK-PID-EXPLICIT-INT clean across 357 file(s)
EXIT=0

$ timeout 60 bash tests/pre_build/test_bob152_vendored_exclude_scope.sh
...
VERDICT: PASS — BOB-152 exclude is load-bearing (submodules/ excluded, tests/ still caught) for all 3 affected gates.
EXIT=0
```

`git diff --stat scripts/verify-all-constitution-rules.sh` after all
mutation/restore cycles above: **empty** (confirmed byte-identical to HEAD;
no residual mutation left in the working tree, per §11.4.84 quiescence).

## 7. Honest observation (out of scope, NOT fixed here)

Running `covenant_propagation_suite.sh gates --root .` against boba's real,
fully-populated tree (submodules initialised) surfaces a large number of
`BLIND` verdicts unrelated to `.worktrees` — e.g.
`CM-COVENANT-114-208-PROPAGATION: BLIND — carrier-discovery control needle
FAILED: 3 of 3 root governance files present on disk were NOT returned by
discovery`. **I confirmed this is pre-existing and NOT caused by this fix**:
it reproduces identically with `config/covenant_propagation_exclusions.tsv`
present or temporarily moved aside. It also does not affect the item's
acceptance criterion — the hermetic fixture proof (§3/§4) isolates the
`.worktrees` behaviour from this unrelated, larger-scale instability, so the
mutation proof is not confounded by it. This looks like a distinct, tracked-
worthy defect (possibly related to the engine's own documented SIGPIPE-class
carrier-discovery footgun at scale, or a resource/timing effect under a large
real fleet) but is squarely out of BOB-143's scope and was not touched,
investigated further, or fixed here.

## 8. `pre_build_verification.sh` wiring — left for the conductor

Not needed. `pre_build_verification.sh`'s own `CM-COVENANT-PROPAGATION-SUITE`
invocation (its "Invariant 32", ADVISORY per its own comment) passes
`--root "${PROJECT_ROOT}/constitution"` — the constitution **submodule's**
root — not boba's repository root, so it was never the source of the
`.worktrees`-sourced findings BOB-143 measured and requires no change for
this fix. The actual production path that reads
`config/covenant_propagation_exclusions.tsv` by default
(`scripts/verify-all-constitution-rules.sh`, boba's own §11.4.32 sweep) needed
**no wiring change** either — both the engine and the suite already default
to `${root}/config/covenant_propagation_exclusions.tsv`, and that sweep
already invokes the suite with `--root "$root"` = boba's repository root, so
simply creating the file was sufficient.

## 9. Assumptions the item text did not fully specify

1. **Closed exclusion class.** BOB-143's text does not name which of the
   engine's four closed classes (`vendored-third-party | generated-code |
   non-shipping-fixtures | filename-collision`) applies. I chose
   `filename-collision`: each orphaned worktree is a full historical clone of
   this repository, so its `CLAUDE.md`/`AGENTS.md`/etc. share the exact
   filename the carrier-discovery globs for without being this project's
   real, current, owned carriers — the discovery mechanism collides on
   filename, not on any legitimate governance relationship. This reading is
   consistent with the class's own doc comment ("the filename-collision
   extension") and with the real-world precedent file I read for format
   reference (`/home/milosvasic/Projects/vasic/config/
   covenant_propagation_exclusions.tsv`, outside this repository).
2. **Item still shows "Queued".** Per scope, I did not touch
   `docs/workable_items.db` or run the `workable-items` CLI, so BOB-143's
   status in the tracker is unchanged by this session; closing/reclassifying
   it is left to the conductor.
3. The item's second, already-addressed measurement (`cm_test_mock_pid_
   explicit_int`, §1a above) was fixed by an EARLIER, differently-titled
   commit (`c0ea01c`) that never updated BOB-143's own tracker text to say
   so. I treated this as a pre-existing partial fix to be regression-guarded,
   not re-done.
