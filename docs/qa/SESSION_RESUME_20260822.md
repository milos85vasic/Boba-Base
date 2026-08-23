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


## SECOND QUOTA INTERRUPTION — 2026-08-22, session limit (resets 15:30 Europe/Belgrade)

Two REVIEWERS killed mid-work. Same §11.4.147(e) treatment: crash class, work
stays owed, resume from the exact last point. Both had made real progress.

### 3. BOB-168 review round 2 — agent a763dbd65e4d562e1
Last line: "M5 confirmed dead at case 4b. Job 3: the seventh (reviewer-authored)
mutation set against the NEW guard itself, both in isolated trees."
So jobs 1-2 are DONE — the fail-open fix and the precedence guard are confirmed.
What remains: its own seventh mutation against the new guard (suggested shapes:
make the guard's -f check pass on a directory; make RC=97 collide with a real
runner exit code; make case 4b's roster incomplete so it silently stops
exercising precedence), plus export-twin freshness and the sibling-untouched
check.
Round-1 verdict was NO-GO on B-1 (the test could fire the REAL DDoS bank via
`cd ""` succeeding as a no-op) and I-1 (FAIL>MISSING precedence unguarded).
Both fixed and reproduced by the author before fixing.

### 4. BOB-172 review — agent a4c8ca7e6d328e7f1
Last line: "Full suite green (883 passed — one more than the author's 882, zero
failures; count drift is benign). Now the RED reconstruction: swap in HEAD's
pre-fix search.py, run, restore byte-identical."
So the GREEN half is independently confirmed. What remains: the RED
reconstruction against pre-fix search.py, then the two disclosures it was asked
to judge — (1) the deliberate `_search_one` error-propagation change that
revives a dead `captcha_required` branch at api/routes.py:727, and (2) the
edited `_FakeResp` stub in test_nnmclub_session_login.py — plus its own
reviewer-authored mutation and the five-site drift check.

## LANDED SINCE THE FIRST RESUME DOC WAS WRITTEN

- BOB-173 committed (GO, zero blocking/important). Both permission seals proven
  to genuinely seal; the false-RED mechanism confirmed empirically.
- BOB-166 committed IN THE SUBMODULE as 71589d5 and pushed to all upstreams
  (origin fans out to 8 push URLs; named remotes report up-to-date). PARENT
  POINTER BUMP was in progress when the limit hit — verify it landed, and if not,
  commit `constitution` (pointer 16b67b0..71589d5) in the parent.
- BOB-168 and BOB-172 fixes are complete and remediated, awaiting only the two
  reviews above.

## KNOWN-RED, DELIBERATELY, IN THE CONSTITUTION SUBMODULE

`go test ./cmd/workable-items/` has exactly ONE top-level failure:
TestValidate_OK_RealDocs. That is the new gate correctly reporting the ten
pre-existing stranded rows in the consumer's trackers — causation proven (under
the gate-stubbing mutation the test passes). Draining needs per-row evidence and
is tracked; weakening the gate would be §11.4.120 fake-passing; an exemption
baseline would embed consumer literals in a shared engine AND pre-empt a
§11.4.224(E) operator decision. Where a consumer has no such trackers the test
SKIPs loudly. Do not "fix" this by touching the gate.

## FILED SINCE: BOB-174 (hooks corrupt-load data-loss chain), BOB-175
## (one-directional update guard), BOB-176 (cookies-only rutracker never enabled)

## A CORRECTION I OWE THE RECORD

BOB-168's original filing was MINE and its premise was FALSE. I measured
`challenges/scripts/` while the runner reads
`submodules/challenges/challenges/scripts/` — two similarly-named directories,
wrong one measured (§11.4.201(9) field identity), and I wrote "verified by
invocation" having only listed a directory. The item is corrected in-place.
The generalisable lesson, which is not in §11.4.201(7)(b) as commonly applied:
A CONTROL NEEDLE PROVES THE INSTRUMENT CAN SEE; IT DOES NOT PROVE IT IS POINTED
AT THE THING UNDER TEST. I applied a needle correctly to a sibling's work in the
same commit, then omitted it on my own measurement one paragraph later.
