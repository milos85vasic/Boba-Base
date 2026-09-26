# Quickstart run 2026-09-26 — 003-zero-shortcomings-audit

Branch `003-zero-shortcomings-audit`, HEAD 13912ce. Output below is pasted verbatim from this session (ANSI colour codes stripped). No credential values appear; the fixtures print only variable names with `<redacted-per-§11.4.10>`.

## Step 1 — enumerate vs three ground truths (real repo)

```
$ scripts/zero_shortcomings_audit.sh enumerate
[INFO] Zero-shortcomings audit — enumeration (20260926T080351Z-pid2624665)
[INFO] Open backlog items:        37
[INFO] Unimplemented gates:       414
[INFO] Open coverage-escapes:     0
[rc=0]

$ constitution/scripts/workable-items/workable-items validate --db docs/workable_items.db
validate: OK — 245 items, all invariants satisfied
[rc=0]

$ sqlite3 docs/workable_items.db "SELECT count(*) FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete';"
37
[rc=0]

$ bash constitution/scripts/gates/cm_gate_ledger_ratchet.sh | grep -c UNIMPLEMENTED
414
$ bash constitution/scripts/gates/cm_gate_ledger_ratchet.sh | grep -v $'\t'
LEDGER-FAIL: ratchet violated — unimplemented=414 exceeds checked-in baseline=403 (a CM-* gate was named with neither an implementation nor a registered deferral; ...)
LEDGER: unimplemented=414 baseline=403 fails=1
CM-GATE-LEDGER-RATCHET: FAIL — see LEDGER-FAIL lines above; ...

$ grep -c '^### ' docs/QA_DISCOVERY_LEDGER.md
28
$ grep -c '\*\*new-check:\*\*' docs/QA_DISCOVERY_LEDGER.md
27
```

Reconciliation of the 28 vs 27: an awk pass over the ledger shows the single heading without a `**new-check:**` is `### BOB-164a`, whose recorded channel is `automated-helixqa` (the parser only counts non-automated entries lacking new-check as open). `enumerate --surface escapes --json` -> `{"escapes_open":0}`.

Result: backlog 37 == 37; gates 414 == 414; escapes 0 == 0. Note: the ledger-ratchet script itself exits FAIL (414 > baseline 403) — that is the pre-existing gate-ledger finding, not caused by this feature.

## Step 2 — verify-closure (run against fixtures, `AUDIT_QA_ROOT=tests/audit/fixtures/docs_qa_fixture`, so no real docs/qa item or docs/workable_items.db is touched; `--reopen-on-mismatch` deliberately NOT used)

```
BOB-FIXTURE-MATCH               -> [ OK ] verify-closure: BOB-FIXTURE-MATCH reproduced its recorded evidence   [rc=0]
BOB-FIXTURE-MISMATCH            -> [FAIL] ... MISMATCH — recorded '5 passed, 0 failed', got '3 passed, 0 failed'   [rc=1]
BOB-FIXTURE-MISMATCH-CREDENTIAL -> [FAIL] ... MISMATCH — recorded 'RUTRACKER_PASSWORD=<redacted-per-§11.4.10>', got 'BOBA_API_TOKEN=<redacted-per-§11.4.10>'   [rc=1]
BOB-FIXTURE-LAYER-TOOWEAK       -> [FAIL] ... declares evidence layer 'source' but 'runtime' is required — a lower-rigor substitute is not accepted (FR-005)   [rc=2]
BOB-FIXTURE-NO-COMMAND          -> [FAIL] ... has no **Command:** field to re-run   [rc=2]
```

`git status --short` afterwards showed no new changes from these runs. The reopen-in-tracker half of the FR-013 negative control (`--reopen-on-mismatch` + `workable-items validate`) was NOT run: it mutates the real tracker DB, which this task forbids. The mismatch-detection half (exit 1) is shown above; the reopen path is exercised only by the tests/audit suite (see below), not by this run.

## Step 3 — evidence-corruption guard (FR-008)

SKIPPED against the real repo: the quickstart step requires running a closure command with a deliberate side effect on an unrelated tracked file, which would dirty real docs/qa items. Coverage instead comes from `tests/audit/test_zero_shortcomings_audit_corruption_guard.sh` (5 passed, 0 failed in the suite run below).

## Step 4 — standing-check

```
$ AUDIT_STANDING_LOG_DIR=<scratchpad> scripts/zero_shortcomings_audit.sh standing-check
[INFO] standing-check: 20260926T080556Z-pid2766901 mode=standing-check status=ok {"backlog_open":37,"gates_unimplemented":414,"escapes_open":0}
[rc=0]
log file line: 20260926T080556Z-pid2766901 mode=standing-check status=ok {"backlog_open":37,"gates_unimplemented":414,"escapes_open":0}
```

The run log was redirected to a scratch directory, so nothing was written under docs/qa/zero_shortcomings_audit/. The counts equal Step 1's.

Not run: `scripts/pre_build_verification.sh` end-to-end, and the scratch-doc negative control. The pre-build script is uncommitted-modified by another concurrent agent (`git status`: ` M scripts/pre_build_verification.sh`) and is a very long run, so only the wiring was observed: line 2582 invokes `scripts/zero_shortcomings_audit.sh standing-check`. That the stage appears in a real pre-build run is therefore UNCONFIRMED here.

## Supporting: `bash -n` (T-POLISH-2) and tests/audit suite (T-POLISH-3)

`bash -n` rc=0 for scripts/zero_shortcomings_audit.sh, scripts/lib/audit_{execution_policy,ledger_parser,run_id}.sh and all 12 tests/audit/test_*.sh.

Suite (each file `timeout 100 nice -n 19 bash <file>`, all rc=0, `git status` unchanged before/after each file):

```
test_audit_execution_policy: 6 passed, 0 failed
test_audit_ledger_parser: 5 passed, 0 failed
test_audit_run_id: 2 passed, 0 failed
test_zero_shortcomings_audit_blocked_surface: 2 passed, 0 failed
test_zero_shortcomings_audit_corruption_guard: 5 passed, 0 failed
test_zero_shortcomings_audit_enumerate: 6 passed, 0 failed
test_zero_shortcomings_audit_evidence_layer: 2 passed, 0 failed
test_zero_shortcomings_audit_redaction: 13 passed, 0 failed
test_zero_shortcomings_audit_risk_order: 6 passed, 0 failed
test_zero_shortcomings_audit_standing_check: 12 passed, 0 failed
test_zero_shortcomings_audit_test_type_declared: 9 passed, 0 failed
test_zero_shortcomings_audit_verify_closure: 4 passed, 0 failed
```

Aggregate 72 passed, 0 failed; per-file `  PASS:` line counts equal each file's own summary.
