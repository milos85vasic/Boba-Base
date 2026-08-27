# T042 readiness preflight — will the 52-invariant gate pass?

**Revision:** 1
**Last modified:** 2026-08-26T20:40:00Z

## Tree state read (anchors, §11.4.6)

| anchor | value |
|---|---|
| HEAD | `a3e1141777914f3d71d62a6cd32a4c79c7f43842` (unchanged across the whole session) |
| branch | `002-user-owned-downloads` |
| untracked (`-uall`) | 42 at start → 43 at end (concurrent writer added one) |
| modified | 43 |
| driver | `scripts/pre_build_verification.sh`, 1969 lines |

`scripts/commit-push-all.sh` was **NOT** run. `scripts/pre_build_verification.sh` was
**NOT** run in full. Every result below comes from executing an individual invariant
or its delegated gate script in isolation, `nice -n 19`.

## Invariant map

52 = **43 bracket-form `[N/52]`** + **9 `run_const_gate "N/52"` invocations**
(33–38, 40, 42, 43). `grep -c run_const_gate` returns 12/13 — the extra hits are the
function definition (L1325) and three comment lines (L1312, L1721, L1725). Union is
1..52 with no gap and no duplicate.

Control needles (§11.4.201(7)(b), same instrument + same path):
`[N/99]` → 0 (instrument discriminates), `invariant` → 103 (instrument sees).

### Blocking vs advisory

Exit logic is `FAIL_COUNT>0 → exit 1`. There is **no** coverage/PENDING layer.
Only a `fail()` call blocks. Four invariants are structurally incapable of blocking
because their failure branch is a bare `echo "  WARN: ..."`:

| # | gate | why it cannot block |
|---|---|---|
| 26 | CM-BADGE-FRESHNESS-CHECK | `echo "  WARN: ..."` on non-zero exit |
| 39 | CM-DANGEROUS-COMBINATION-FAIL-CLOSED | `echo "  WARN: ... (ADVISORY, non-blocking)"` |
| 40 | CM-ORACLE-STRATEGY-NAMED-AND-INDEPENDENT | `run_const_gate ... advisory` |
| 41 | CM-OPENDESIGN-UI-SYSTEM | `echo "  WARN: ... (ADVISORY, non-blocking)"` |

### Git index / status consumers

The driver barely uses git porcelain. `git status` appears only in **comments**
explaining why it is *not* used (L1080-1082: it is structurally blind to the
mtime-only defect class). The real enumerators are:

- **`git ls-files`** (tracked-only) — invariant 30's no-trace corpus, invariant 49.
- **`find` / shell glob** (filesystem, **sees untracked**) — invariant 16
  (`find PROJECT_ROOT -maxdepth 1 -name '*.md'` + `find docs/ scripts/ -name '*.md'`),
  invariant 30 (`"$PROJECT_ROOT"/tests/{unit,pre_build,hooks}/test_*.sh`), and the
  delegated scanners.

**Load-bearing ordering fact:** `commit-push-all.sh` runs the long gate at
**stage 3/6**, and `git add -A` only at **stage 5**. So at gate time every new file
is still untracked — which means the `git ls-files` invariants cannot see them and
only the `find`/glob invariants can. That is exactly where both new-file failures land.

### Hand-maintained lists found

| list | location | risk |
|---|---|---|
| `DANGER_ROOTS` (5) | driver L1511 | BOB-205/214 — misses repo root, `tools/`, `cmd/` |
| `exts` (16, **no `sh`**) | `cm_dangerous_combination_fail_closed.sh` L457 | BOB-213 |
| `BASH_TEST_SELF_RECURSIVE` (2) | driver L1054 | recursion guard |
| `BASH_TEST_QUARANTINE` (0) | driver L1064 | ratchet, currently empty |
| inv-30 test glob (3 dirs) | driver L1196 | **omits `tests/security/`** |
| `.docs_chain/contexts` (2) | `.docs_chain/contexts/` | narrow scope |
| excludes (9) | scanner L458 | prune list |

## Verdict: the gate FAILS. Three blocking invariants, in driver order.

### [16/52] CM-MARKDOWN-EXPORT-SYNC — 6 violations (reproduced 3×, identical)

Scope excludes `docs/research/*` and `docs/qa/*` but **not** `docs/scripts/`.

- `docs/scripts/test_gitignore_swallow_is_loud.{html,pdf}` **MISSING** — caused
  directly by the new untracked `docs/scripts/test_gitignore_swallow_is_loud.md`.
  This is the §11.4.18 companion doc written for the new test script; authoring it
  is what created the invariant-16 violation.
- `docs/Issues.{html,pdf}` + `docs/Fixed.{html,pdf}` **STALE** — `.md` mtime
  1787774388 vs exports 1787772253–1787772292 (~35 min newer). **MOVING TARGET**:
  these six files are all ` M` and owned by a concurrent writer.

Remediation the driver implies: `bash scripts/generate_markdown_exports.sh`.

### [30/52] CM-BASH-UNIT-TESTS-EXECUTED — a new RED test fails the gate

Enumerates by filesystem glob → **runs the new untracked suites**. Executed exactly
as the driver does (`BOBA_PREBUILD_NESTED=1 timeout 300 bash <suite>`):

| suite | exit |
|---|---|
| `tests/pre_build/test_bob205_danger_roots_scope.sh` (NEW) | **1 — RED** |
| `tests/pre_build/test_check_cm_lan_routes_authenticated.sh` (NEW) | 0 (115/0, 56s) |
| `tests/unit/test_ddos_sibling_retry_after_classification.sh` (NEW) | 0 (32/0) |

`BASH_TEST_FAILED>0 → fail()`. The BOB-205 suite is a **RED test for an unfixed
defect** — it is *supposed* to fail, and invariant 30 has no RED-test allowance.

### [48/52] CM-RUNTIME-DEPS-PARITY — 8 divergences (pre-existing, state-dependent)

venv 3.4.9/3.32.2/3.18/0.27.3/1.4.1/0.4.2/0.52.1 vs container counterparts, plus
CPython 3.14.6 (venv) vs 3.12.13 (container). Tracked as BOB-154, blocked on BOB-158.
**Not caused by any new file.** It compares the live `.venv` against the *running*
`qbittorrent-proxy` container, so it is **state-dependent**: with the container down
the gate SKIPs and this failure disappears.

## Per-new-file prediction

| file | invariants that see it | prediction |
|---|---|---|
| `docs/scripts/test_gitignore_swallow_is_loud.md` | 16 (`find docs/`) | **FAIL** — no .html/.pdf twins |
| `docs/qa/{BOB-186,191,196,198,205,206,212,T028-uid100999,T041}/**` | none | PASS — inv 16 excludes `docs/qa/*`; inv 19/20 read only `docs/QA_DISCOVERY_LEDGER.md`, never the filesystem |
| `tests/pre_build/test_bob205_danger_roots_scope.sh` | 30 (glob, executes) | **FAIL** — RED by design |
| `tests/pre_build/test_check_cm_lan_routes_authenticated.sh` | 30 | PASS (115/0) |
| `tests/unit/test_ddos_sibling_retry_after_classification.sh` | 30 | PASS (32/0) |
| `tests/security/test_gitignore_swallow_is_loud.sh` | **none** | PASS by invisibility — **orphan guard** |
| `scripts/pre_build/check_cm_lan_routes_authenticated.sh` | none (not wired into the 52) | PASS |
| `scripts/pre_build/lib/cm_export_charset_scan.py` | 23 (PASS), 39 (adds 1 WARN hit) | PASS |
| `scripts/pre_build/cm_export_charset_valid.baseline` | 50 | PASS (343 scanned, 0 missing, at baseline) |
| `scripts/pre_build/tighten_cm_export_charset_baseline.sh` | none | PASS |
| `config/lan_route_auth_policy.yaml` | none | PASS |
| `qBitTorrent-go/internal/jackettapi/bob204_failclosed_test.go` | 39 only (advisory) | PASS |
| `specs/**/evidence/*.md` (11 new) | none — inv 16 scans only root, `docs/`, `scripts/` | PASS |

**§11.4.18 script-documentation is NOT gated.** `grep -E '11\.4\.18[^0-9]'` over the
driver returns **zero** (the earlier count of 1 was `11.4.18` prefix-matching
`11.4.180`+). There is no `CM-SCRIPT-DOCS-SYNC` among the 52. New scripts without a
companion doc are therefore not a gate failure — the irony is that *writing* one
(`docs/scripts/test_gitignore_swallow_is_loud.md`) is what tripped invariant 16.

**§11.4.44 revision headers are NOT gated** either: `grep -cE
'REVISION-HEADER|revision_header|Revision:\*\*'` → 0 (control needle
`CM-BADGE-FRESHNESS` → 3). New `.md` without headers will not fail.

**Residue scan (inv 23):** 273 files, 0 hits, 1 audited waiver — PASS. The count
already sits at the predicted 273; no new file trips it.

**§11.4.224 test-first:** no invariant demands a paired mutation or fixture for a new
gate script. Invariant 30 only demands that whatever suites *exist* pass.

## Task 3 — the three-hole interaction

**Answer: no. Invariant 39 does not pass today, and fixing the holes cannot make
T042 fail.**

Two independent reasons, both measured:

1. **Structural.** Invariant 39's non-zero branch is
   `echo "  WARN: ... (ADVISORY, non-blocking per §11.4.234 ...)"`. It never calls
   `fail()`. `FAIL_COUNT` is untouched regardless of hit count.

2. **Empirical.** Invariant 39 is *already* WARNing. Running its own gate over its
   own `DANGER_ROOTS` at this tree state:

   | root | hits |
   |---|---|
   | `download-proxy/src` | 28 |
   | `plugins` | 50 |
   | `scripts` | 2 |
   | `frontend/src` | 0 |
   | `qBitTorrent-go` | not scanned (stay-off); per BOB-191 structurally unanalysable → ~0 |
   | **total** | **~80** |

   So the premise "invariant 39 currently PASSes because of the holes" is false — it
   currently WARNs with ~80 hits and contributes nothing to the exit code either way.

Hole probes (a hit is a LEAD, §11.4.194(6)(b) — all triaged to the line):

| probe | result | triage |
|---|---|---|
| `scripts` ext=`sh` (**BOB-213**) | 1 hit | `scripts/codegraph_validate.sh:81` — a real `try{...}catch(e){}` inside an embedded Node `-e` one-liner. Genuine pattern match, but guarded downstream by `n=0` default + `[ "$MCP_NODES" -gt 0 ]` fail-closed assertion. Low severity. |
| `tools` default ext (**BOB-214**) | 3 hits | `tools/plugin_update_automation.py:189,198,215` — silent default returns in first-party Python. **Real and genuinely unscanned.** |
| `cmd` default ext | 0 hits | the RED test's `cmd/boba-ctl` needle is synthetic; no live hit |
| `config` default ext | 43 hits | **FALSE POSITIVE class** — all in `config/qBittorrent/nova3/engines/*.py`, verified `git check-ignore` → GITIGNORED. These are the *installed copies* of `plugins/` (already a DANGER_ROOT), i.e. duplicates of hits already counted. `config/` is correctly excluded. |
| `challenges` ext=`sh` | 0 hits | clean |

Net: fixing all three holes moves the advisory WARN from ~80 to ~84. **Zero effect on
T042's exit code.** T042's outcome is not an artifact of scanner blindness.

## Verified-PASS roster

Executed in isolation, all exit 0 / `fail()`-free: **1–15** (extracted, 0 fails),
**17** (validate 218 items OK; diff in-sync 218/218; DB md5 stable across the read),
**18**, **19–20** (extracted, ledger 28==28), **21–22** (extracted), **23** (273 files,
0 hits), **24** (docs_chain 2/2 in-sync), **25** (5 signatures below threshold),
**27** (170 files), **28** (324), **29** (324), **31–32** (17/17 lockstep),
**33–38** (const-gates), **42–43** (honest SKIP, wired blocking), **44** (5 services),
**45**, **46** (8 counts), **47** (2 builder stages), **49**, **50** (343 exports,
baseline 0), **51** (92 inputs), **52** (79 inputs).

## Honest boundary (§11.4.6)

1. **Invariant 30 is only 3/38 verified.** It runs 40 globbed suites minus 2
   structurally excluded. I ran the **3 new** ones. The other **35 are unverified** —
   any one failing adds to the same single `fail()`. This is the largest residual
   uncertainty and it can only widen the failure, never narrow it.
2. **`qBitTorrent-go` was not scanned** (stay-off constraint). Its inv-39
   contribution is assumed ~0 on BOB-191's structural-unanalysability finding, not
   measured here.
3. **Invariant 48 is state-dependent, not tree-dependent** — its verdict flips with
   whether the `qbittorrent-proxy` container is running.
4. **Four of the six invariant-16 violations are on concurrently-owned files**
   (`docs/{Issues,Fixed}.{html,pdf,md}`). Another agent may regenerate them at any
   moment. Only the two `docs/scripts/test_gitignore_swallow_is_loud.*` misses are
   attributable to this session's new files and stable.
5. **Cross-invariant interactions were not simulated.** Invariant 30's no-trace
   corpus check fails if any suite leaves an mtime trace on a tracked file; I ran
   suites individually, not under that guard, so a trace-induced inv-30 failure
   would not have shown up in my runs.
6. **Whole-driver-only effects unobservable:** ordering, the `BOBA_PREBUILD_NESTED`
   sentinel path, total wall-clock, and any shared state between invariants.

## New finding surfaced by this preflight

`tests/security/test_gitignore_swallow_is_loud.sh` (a BOB-212 RED test authored this
session) sits in a directory **no invariant executes** — inv 30's glob covers only
`tests/unit`, `tests/pre_build`, `tests/hooks`. This is a recurrence of the exact
orphan-guard class the driver's own comment at L1190-1195 records as having already
happened twice ("the SAME orphan-guard class that stranded `tests/pre_build/`
recurred one directory over"). Third occurrence, one directory over again.
