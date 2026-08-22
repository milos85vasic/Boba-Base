# Session resumption state — 2026-08-22 (weekly quota reset: Aug 24, 21:00 Europe/Belgrade)

Two agents were killed mid-work by the WEEKLY limit. Per §11.4.147(e) quota
exhaustion is a first-class CRASH class, not a completion: both stay owed and
must be respawned, resuming from their exact last point. Neither is written off.

## OWED RESPAWNS (do these first)

### 1. BOB-173 review — agent a488b247ad3fb4770
Last line: "234 passed — matches the author's claim. Final checks: signal-safety,
lint, and the theme_state atomic-write reference for the A5 scope judgement."
So it had already re-run the suite and confirmed the author's count; what remains
is §11.4.263 signal-safety, lint, and its judgement on A5 (non-atomic write).
The full review brief is in this session's transcript. Key unfinished asks:
  - verify BOTH permission seals genuinely seal on THIS filesystem as THIS user
    (`seal_for_create` -> dir 0500, `seal_for_rewrite` -> file 0400). If either
    is a no-op the corresponding RED is still false and the problem only moved.
  - confirm the §11.4.120 reconciliation of test_hooks_remaining.py is a genuine
    reconciliation, not a weakening (that test previously ENCODED THE DEFECT as
    the contract).
  - author a mutation the author did not write.

### 2. BOB-166 re-review — agent ad99f9c240930a7d8
Last line: "Starting the re-review. First, verify the two unchanged files against
my recorded baselines and read the grown test file."
It had not yet re-verified anything this round. Its round-1 verdict was NO-GO on
IMPORTANT-1 (R4 mutation: guard read raw status instead of normalized); the
author has since fixed it with a table-driven {input, normalizesTo} loop covering
BOTH non-canonical routes, and reports R4 now dies diagnostically (canonical four
still pass, the three new cases fail). Round-2 asks: re-run R4, author a fifth
mutation against the new loop, check the MINOR-2 Operator-blocked scoping, and
confirm 272 PASS / 1 FAIL / 3 SKIP.

## UNCOMMITTED WORK IN THE TREE (do not lose)

- constitution/scripts/workable-items/{mutate.go, sync.go,
  cmd/workable-items/update_location_status_invariant_test.go} — BOB-166 fix,
  remediated, awaiting the round-2 review above. NOT committed.
- download-proxy/src/api/hooks.py, tests/unit/api_layer/test_hooks_remaining.py,
  tests/unit/api_layer/test_bob173_hook_persistence_failure.py — BOB-173 fix,
  awaiting the review above. NOT committed.

## SEQUENCING FACT ESTABLISHED THIS SESSION (load-bearing for BOB-166)

pre_build_verification.sh resolves the git-TRACKED prebuilt at
constitution/scripts/workable-items/bin/workable-items (built Aug 19). That stale
prebuilt was EXECUTED against a DB copy: 0 findings, exit 0. No boba gate runs
`go test` on that module. Therefore landing the BOB-166 SOURCE reddens no boba
seam — the gate only goes red once the tracked binaries are rebuilt and
committed, which must be sequenced against draining the ten rows (BOB-166
acceptance (c)). This is the §11.4.108 layer-2 state: source present, artifact
absent. Also: invariant 17's comment claiming "bin/ is a gitignored dir nothing
ever populated" is STALE — the prebuilts exist, are tracked, and are preferred.

## SHIPPED THIS SESSION (all after full adversarial review loops, all pushed x3)

BOB-111 rate limiter (3 rounds) · BOB-135 test-isolation guard (2 rounds) ·
BOB-093 ReDoS bounds (3 rounds) · BOB-109 scaling suite (5 rounds).
Closed: BOB-079, BOB-092, BOB-136, BOB-158.

## STILL OWED, NOT STARTED

- Quiescent long-gate re-run. The one full run this session completed 42/45 with
  its three failures triaged: docs_chain (real, fixed), mtime-moved (NOT a defect
  — three tracked files moved mid-run, mine plus two agents'), and
  CM-RUNTIME-DEPS-PARITY (real, pre-existing, BOB-154). That verdict CANNOT
  inform a release decision; it needs a quiescent tree.
- BOB-154 venv rebuild — now unblocked (BOB-158 landed) but .venv was in use all
  session by pytest-running agents (§11.4.119).
- BOB-170 quiescent GREEN run of the scaling timing gates.
- BOB-169 export fix: ONE flag (`-s` at generate_markdown_exports.sh:57) plus a
  FORCED regeneration of ~286 HTML and their PDFs, HTML BEFORE PDFs. Deferred
  deliberately: 600 files during parallel dispatch is a §11.4.84 collision.

## OPERATOR DECISIONS OWED

BOB-162 brownfield adoption · BOB-163 does-a-429-count-as-responsive ·
BOB-166 acceptance (c) sequencing (drain the ten rows vs rebuild the binaries) ·
:7186 and :7189 deployments (§11.4.235, Hard Stop #3 — orchestration is the
operator's).
