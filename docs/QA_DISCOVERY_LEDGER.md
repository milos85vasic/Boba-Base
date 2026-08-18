# QA Discovery-Channel Ledger

**Revision:** 5
**Last modified:** 2026-08-18T16:45:00Z
**Status:** active
**Constitution:** §11.4.238 (automated QA must be the DISCOVERER, not the confirmer — every
defect found outside the automated HelixQA regime is itself a coverage-escape release blocker,
not merely a bug to fix).

## Purpose

Every defect this project closes MUST record **which channel found it**: `automated-helixqa`
(the standing HelixQA regime caught it) or an **out-of-band channel** — `manual-qa`,
`operator-report`, `agent-code-reading`, or `incidental-discovery`. Per §11.4.238(C), every
out-of-band entry MUST carry a **coverage-escape audit**: why the automated regime missed it
(cited to the specific missing/blind check, never "we didn't think of it"), and the new or
strengthened automated check — with its own §11.4.115 RED capturing the escaped defect — that
closes the gap.

Per §11.4.238(E), this project tracks the discovery-channel split over time and drives the
out-of-band share toward zero. **Honest boundary (§11.4.6):** this ledger starts wherever this
project's actual history is — see the retroactive seed entries below, all found via
`agent-code-reading` during the 2026-08-07/2026-08-08 governance audits, exactly the channel this
anchor targets. Full retroactive audit of every historical closure in `docs/Fixed.md` (~62 items)
is NOT attempted here — that is out of proportion for a ledger just being stood up, and would
itself be a §11.4.6 fabrication if backfilled without real investigation per entry. The ledger is
honest about starting now, not claiming a false complete history.

## Schema (per entry)

| Field | Meaning |
|---|---|
| `id` | The workable item id (`BOB-NNN`) if one exists, else a short slug |
| `date` | ISO date the defect was found |
| `channel` | `automated-helixqa` \| `manual-qa` \| `operator-report` \| `agent-code-reading` \| `incidental-discovery` |
| `summary` | One line: what was wrong |
| `escape-audit` | (out-of-band only) which check was missing/blind, cited by name/path |
| `new-check` | (out-of-band only) the new/strengthened check that now catches this class, with its RED-capture evidence |

## Entries

### RD2-22 — `PATCH /schedules/{id}` and `PUT /theme` unauthenticated with a token set

- **id:** RD2-22 (governance-audit item, not yet a `BOB-NNN`)
- **date:** 2026-08-07 (found by the 2026-08-07 governance audit), confirmed still open + fixed
  2026-08-08
- **channel:** `agent-code-reading` — found by direct source inspection (comparing sibling routes'
  `Depends(require_api_token)` presence), not by any test or HelixQA run.
- **escape-audit:** `tests/security/test_hooks_schedules_auth.py`'s `_MUTATING` enumeration
  (the ONLY automated check covering this auth surface) was scoped to exactly 4 routes
  (`POST/DELETE hooks`, `POST/DELETE schedules`) when the original RW-02 fix landed — it was
  never extended when `PATCH /schedules/{id}` and `PUT /theme` were added as separate routes. The
  check existed, ran green, and was simply never told about two of the six routes it should have
  covered — a scope gap, not a broken check (per the ledger's `channel` split, this is the
  "genuinely uncovered" class, not "existed-but-missed").
- **new-check:** `_MUTATING` extended to all 6 routes (`tests/security/test_hooks_schedules_auth.py`),
  RED-captured (confirmed 4/4 new-route assertions failed with `expected 401, got 200` before the
  fix), now GREEN (31/31). See `docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md` RD2-22 for the full
  before/after evidence.

### RD2-41a — `scripts/docs_chain.sh` Step 1/3 silently no-op'd on every run

- **id:** RD2-41 (governance-audit item)
- **date:** 2026-08-08
- **channel:** `agent-code-reading` — found by directly invoking `docs_chain.sh` and reading its
  own printed error line, then tracing the hardcoded path in source.
- **escape-audit:** **no automated check existed at all** for "does `docs_chain.sh`'s Step 1
  actually run the real DB export" — the script printed an `ERROR:` line on every failure but
  nothing consumed/asserted on that exit status anywhere in the test suite or pre-build gate; a
  human had to actually run it and read the output. Genuinely uncovered, not a broken check.
- **new-check:** `tests/unit/test_docs_chain_binary_resolution.sh` — real-invocation test
  asserting Step 1 resolves a real binary and reaches the real `validate` call. RED-captured
  (confirmed failing against the pre-fix script: `FAIL: Step 1/3 still reports 'binary not
  found'`), now GREEN.

### RD2-41b — `scripts/pre_build_verification.sh` invariant 17 silently SKIPPED on every run

- **id:** RD2-41 (governance-audit item, same root cause as RD2-41a)
- **date:** 2026-08-08
- **channel:** `agent-code-reading` — found while fixing RD2-41a, by checking for the identical
  bug pattern in this sibling script per the project's own extend-to-all-cases discipline.
- **escape-audit:** this is the sharpest instance in this ledger of "the checker itself was
  blind": invariant 17 IS the pre-build gate's own workable-items DB-integrity check, and it was
  silently SKIPPING (not failing — the script's own `else` branch treats a missing binary as an
  honest skip, not a failure) on every single pre-build run since the path was wrong. A gate whose
  own precondition-check is broken cannot report the truth about the thing it gates — an
  `existed-but-missed` class defect (the check existed, ran, and was blind), the more dangerous of
  the two classes per this ledger's schema.
- **new-check:** `tests/unit/test_pre_build_workable_items_invariant.sh` — real-invocation test
  asserting invariant 17 reaches a real PASS/FAIL verdict instead of silently skipping.
  RED-captured (confirmed failing against the pre-fix script via `git stash`/restore), now GREEN.
  **Residual, still-open finding from this same investigation** (tracked as RD2-41's own note in
  `docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`, not yet closed): a SEPARATE, earlier
  mutation-marker carrier false-positive in the same script aborts the ENTIRE pre-build gate
  before invariant 17 is ever reached in a full run — meaning this fix, while correct, is not yet
  provably exercised end-to-end in production; the ledger records this honestly rather than
  claiming full closure.

### BOB-008 — DB↔MD body drift + missing enumerated unblock choices

- **id:** BOB-008
- **date:** 2026-08-08
- **channel:** `agent-code-reading` — found by running `workable-items diff`/`validate` during a
  routine sync check, not by any standing automated gate (no CI job runs `workable-items diff` on
  a schedule).
- **escape-audit:** no automated check runs `workable-items diff`/`validate` as a standing,
  scheduled, or write-seam-triggered gate — §11.4.106(F)'s commit-seam sync hook (which would
  have caught the DB write in commit `54e313f` landing with no matching `docs/Issues.md` update)
  does not exist in this repo. Genuinely uncovered.
- **new-check:** **closed 2026-08-08.** `scripts/pre_build_verification.sh` invariant 17 extended
  to run `workable-items diff` (DB-vs-Markdown divergence) alongside `validate` (internal DB
  invariants) — it now catches BOTH the §11.4.148(D3) enumerated-choices class AND the DB↔MD
  body-drift class. RED-captured via
  `tests/unit/test_pre_build_workable_items_diff_check.sh`'s §1.1 paired mutation (a deliberately
  desynced `docs/Issues.md` — confirmed FAIL with the diff check absent, confirmed correct
  divergence-specific FAIL, distinguished from the separate pre-existing BOB-009/010 `validate`
  issue so the test does not tautologically reuse an unrelated failure — then GREEN after the
  fix, with a companion assertion that the real synced tree reports no false divergence).
- **2026-08-18 update (BOB-073 / RD2-04, recurrence, honest residual finding):** despite the
  2026-08-08 invariant-17 `diff` extension above, `workable-items diff --db docs/workable_items.db
  --issues docs/Issues.md --fixed docs/Fixed.md` found **9 separate DB↔Markdown drifts** (not just
  the original BOB-008 one) when an agent manually re-ran it during the BOB-072/BOB-073 fix session
  (commit `82d9842`) — evidence in `docs/qa/BOB-072-073/`. **Channel for this recurrence:
  `agent-code-reading`** (an agent ran the tool by hand while fixing an unrelated sibling item, not
  a standing scheduled/blocking gate). **Escape-audit:** the invariant-17 `diff` check landing in
  source is necessary but not proven sufficient — this ledger does NOT have evidence that invariant
  17 runs as a hard, blocking write-seam gate on every commit that touches `docs/workable_items.db`
  (per §11.4.106(F)'s commit-seam requirement); 9 drifts accumulating between 2026-08-08 and
  2026-08-18 is consistent with either (a) the check existing but only being invoked when an agent
  remembers to run `scripts/pre_build_verification.sh` by hand, or (b) some DB writes in that window
  landing via a path invariant 17 does not intercept. **Recorded honestly as `UNKNOWN` which
  mechanism** (§11.4.6) rather than guessed. All 9 reconciled + closed this session (see commit
  `82d9842` for the per-item DB-vs-MD authoritative-side decisions); `diff` now reports 0. **New
  check (still owed, not yet authored):** a real commit-time (pre-commit or `commit-push-all.sh`
  stage per §11.4.234) hook that runs `workable-items diff` and BLOCKS the commit on any
  divergence touching `docs/workable_items.db`, `docs/Issues.md`, or `docs/Fixed.md` — turning
  invariant 17 from a pre-build-time report into a write-seam gate.

### RD2-42 — `podman ps` reports a container "Up ... (healthy)" while its process is genuinely dead

- **id:** RD2-42 (governance-audit item)
- **date:** 2026-08-09
- **channel:** `incidental-discovery` — surfaced while attempting the RD2-22 live curl-verify:
  `curl http://localhost:7187/health` returned `HTTP=000` (connection refused), while
  `podman ps` simultaneously reported `qbittorrent-proxy: Up 15 hours (healthy)`.
  `podman exec qbittorrent-proxy ...` returned `OCI runtime error: crun: ... is not running` and
  `podman inspect ... .NetworkSettings.Ports` was empty `{}` — the container's actual `crun`
  process was dead (no restart count, no OOMKilled flag recorded — podman's own state was simply
  stale/desynced from reality), most likely fallout from the same host session-kill mechanism
  already tracked in `docs/incidents/` reaching into the rootless-podman container process tree.
- **escape-audit:** **no automated check exists at all** for "is `podman ps`'s reported state
  consistent with the container's real `crun`/process state" — this is exactly the
  §11.4.196(F)/§11.4.201(6) "configured ≠ in use" false-null class applied to container
  orchestration: a healthy-looking `podman ps` line is not proof the service is reachable.
  Genuinely uncovered — no pre-build/pre-test gate probes the live stack's actual reachability
  before a test run assumes it.
- **new-check:** not yet authored (tracked, not yet closed). Candidate: a
  `tests/fixtures/services.py`-level or pre-build-gate-level real-reachability probe
  (`curl`/socket-connect to each mapped port, not `podman ps` text) run before any live-stack-
  dependent test session, with an honest recreate-and-retry path — mirroring what this session did
  manually (`./start.sh --recreate`, confirmed `HTTP=200` after ~90s).
- **resolution applied this session:** `./start.sh --recreate` (the project's sanctioned
  orchestrator, never raw `podman restart`) — confirmed `curl :7187/health` → `200` after the
  stack's normal ~90s startup window.

### RD2-43 — bare `python3 -m pytest` silently fails ALL collection via a stale `~/.local` `rpds` build

- **id:** RD2-43 (governance-audit item)
- **date:** 2026-08-09
- **channel:** `incidental-discovery` — surfaced when relaunching the interrupted `tests/contract/
  + tests/unit/` regression sweep with a bare `python3 -m pytest` invocation: immediate
  `ModuleNotFoundError: No module named 'rpds.rpds'` at collection time (inside the `schemathesis`
  pytest-plugin's import chain), aborting the ENTIRE sweep before a single test ran.
- **escape-audit:** host-level Python version drift — the system `python3` resolves to Python
  3.14.6, but `~/.local/lib/python3/site-packages/rpds/rpds.cpython-313-x86_64-linux-gnu.so` is a
  native extension built for the 3.13 ABI (real ABI mismatch, confirmed via
  `ls .../rpds/*.so` + `python3 --version`). The project's own `.venv` (Python 3.14.6, `.venv/bin/
  python3 -c "import rpds"` succeeds) is the correct, working interpreter — no automated check
  enforces "tests are always run via `.venv/bin/python3`, never a bare `python3`" anywhere in this
  repo's own tooling (no `Makefile`/wrapper script that fails closed on the wrong interpreter).
  Genuinely uncovered; this is an environment-fragility class distinct from the source-level bugs
  this ledger otherwise tracks, but it silently produces a 100%-collection-failure that could be
  misread as "every test in the suite is broken" by anyone (human or agent) who doesn't already
  know to check the interpreter.
- **new-check:** not yet authored (tracked, not yet closed). Candidate: a thin
  `scripts/run_tests.sh` wrapper (or a `pyproject.toml`/CI-adjacent guard) that verifies
  `sys.prefix` resolves inside `.venv/` before invoking pytest, failing closed with an actionable
  message rather than a confusing plugin-internals traceback.
- **resolution applied this session:** relaunched the sweep via `.venv/bin/python3 -m pytest` —
  confirmed genuinely running (real per-test PASS lines, not a collection error).

### RD2-44 — `test_get_existing_search_returns_200`'s 120s poll window had near-zero real margin

- **id:** RD2-44 (governance-audit item, same root-cause FAMILY as the already-fixed
  `tests/e2e/test_full_pipeline.py` timeouts, but a genuinely separate finding/fix — that fix did
  not touch this file)
- **date:** 2026-08-09
- **channel:** `incidental-discovery` — surfaced re-running `tests/integration/test_merge_api.py`
  (RD2-26a's own deliverable) against the actually-live stack for the first time since its
  original mocked-service replacement; it had only ever been run with the stack unreachable
  (28 passed / 20 skipped) until this session.
- **escape-audit:** RD2-26a's own author (a parallel subagent, same session) had no way to
  discover this — the file was authored and its author's own live-verification attempt happened
  while the stack was down, so it never actually exercised this code path against a live,
  contended host before committing. No automated check re-runs the live-service test suite on a
  schedule independent of whether an agent happens to have the stack up at authoring time —
  genuinely uncovered.
- **new-check:** the test itself IS the check; it was simply mistimed. Live-measured real search
  completion (42 trackers, real network calls, under real concurrent 4-subagent host load):
  ~118s once, ~298s under heavier concurrent load — both within a few seconds of, or past, the old
  120s ceiling. Widened to 300s in `tests/integration/test_merge_api.py`, matching the
  `test_full_pipeline.py` pattern's order of magnitude. RED-adjacent evidence: the original
  120s-deadline run genuinely failed (`assert 'running' != 'running'`) against the live stack;
  post-fix re-run: `1 passed in 297.72s`.

### INC-2026-08-10 — GCM auth-bypass mutation left in `qBitTorrent-go/internal/db/crypto.go` during Agent H's RED window

- **id:** INC-2026-08-10 (this-session incident; not a governance-audit item — inline
  coverage-escape captured during autonomous work by the conductor)
- **date:** 2026-08-10
- **channel:** `automated_background_scan` — a background security-review plugin
  (out-of-cycle from the pre-build regime) caught the mutation during Agent H's Case (c)
  RED-then-GREEN window (~few seconds) while it was authoring RD2-31 chaos tests in
  `qBitTorrent-go/tests/integration/jackett_db_test.go`.
- **escape-audit:** subagent briefing template for RD2-31 said "Do NOT touch production
  code paths — ONLY the test file" but was PROSE, not mechanically enforced. Agent H
  interpreted narrowly and mutated `qBitTorrent-go/internal/db/crypto.go` `Decrypt`
  (`if err != nil` → `if false && err != nil`, swallowing GCM authentication failures)
  for its RED assertion, then restored to byte-identical HEAD. The window was small but
  real — a §11.4.84 working-tree-quiescence violation. No boba-side pre-tool-use hook
  would have caught the mutation during the window (only a post-fact scan would);
  the out-of-cycle security scan caught it BEFORE restoration. Genuinely uncovered by
  the in-cycle regime.
- **new-check:** §11.4.84 fence LANDED —
  - **Layer 1** (subagent briefing template with three mandatory isolation patterns:
    git worktree per §11.4.179, atomic mutate-run-restore Bash tool call with `trap`,
    mutation-testing tool operating on isolated copy) APPLIED to every subsequent
    subagent dispatch (proven: Agents K + L both used the strengthened briefing
    without violation).
  - **Layer 3** (`scripts/pre_build_verification.sh` invariant 23
    CM-NO-PRODUCTION-MUTATION-RESIDUE, with FIXTURE_ROOT env-testable
    golden-good/golden-bad fixtures under `scratchpad/agent-L-fixtures/`) LANDED —
    real-repo PASS today (0 residue in production paths).
  - **Layer 2** (post-tool-use hook enforcing mid-window detection) DEFERRED pending
    Claude Code runtime-capability verification (currently PreToolUse hooks only per
    §11.4.109 precedent).
  - Design doc: `scratchpad/task-20-84-fence-design.md`.
- **resolution applied this session:** Agent H's crypto.go restoration was clean
  (verified via `git status` empty + `git diff` empty + full-tree grep for MUT'ATED
  patterns in production paths = empty); no commit contamination (main stream was
  holding for atomic commit per §11.4.121). §11.4.84 fence Layer 1 + Layer 3 both
  landed and verified. Layer 2 tracked as §11.4.197 follow-up.

### TMUX-OOMD-2026-08-12 — tmux sessions SIGKILLd by systemd-oomd under user-slice pressure, despite `MemoryMax=infinity`

- **id:** TMUX-OOMD-2026-08-12 (not yet a `BOB-NNN` — cross-project
  escape traced through the upstream `vasic-digital/tmux` fix TMX-083,
  v1.0.42)
- **date:** 2026-08-12
- **channel:** `operator-report` — the operator noticed sessions dying
  "as soon as we continue work with this project". No automated gate
  in this project or its upstream had exercised this failure class.
- **escape-audit:** neither the tmx project's own test suite (which
  covers cgroup `Max=` / `TasksMax=` / `CPUQuota` properties but not
  `ManagedOOMPreference`) nor the boba project's HelixQA + Challenges
  regime (host-safety mandates cover CONST-033 host power classes but
  do not probe `systemd-oomd`'s effect on tmux scopes) had a check
  for "does the tmux scope survive a user-slice memory-pressure spike
  under systemd-oomd?". The §11.4.201(6) FALSE-NULL class applied to
  the test surface: the suite scanned the wrong axis and returned a
  confident zero on a real defect. Genuinely uncovered — no automated
  check existed on either side. Predecessor sighting `RD2-42`
  (2026-08-09, `incidental-discovery`) had already noted the same
  host session-kill mechanism reaching into rootless-podman container
  process trees; this operator report is the tmux-facing symptom of
  the same killer.
- **new-check:** `challenges/scripts/tmux_survives_oomd_pressure_
  challenge.sh` (boba side; auto-wired into `run_all_challenges.sh`)
  + upstream `scripts/tests/59_oomd_preference_avoid.sh` (tmx side).
  Both are §11.4.115 RED-capable via `RED_MODE=1`. Live-verified on
  the operator's host 2026-08-12: pre-fix `RED_MODE=1` PASS
  (`ManagedOOMPreference=none` — defect reproduced), post-fix
  `RED_MODE=0` PASS (`ManagedOOMPreference=avoid` — regression guard
  confirmed). Perfect §11.4.115 polarity flip. Full audit at
  `docs/qa/coverage-escape-tmux-oomd-20260812/audit.md`. Root cause
  fixed upstream in `vasic-digital/tmux` v1.0.42 (TMX-083, commits
  `6f9eaeb` + merge `92ef3a0`), pushed ff-only to both remotes per
  §11.4.113.

### RD2-00 / BOB-068 — unattributed, unreviewed "Auto-commit" mechanism pushing to `main` mid-work

- **id:** BOB-068 (RD2-00) — status `Queued`, still OPEN (root cause narrowed, not eliminated)
- **date:** first observed 2026-08-08; re-confirmed present in git history as of 2026-08-18
  (20 bare `Auto-commit` commits total across this repo's history — confirmed via
  `git log --oneline --all --grep="^Auto-commit$" | wc -l`, e.g. `54e313f`, `9c8f684`, `743097a`,
  `de9270b`, `1c36777`, `41179c2`, `7c529ca`).
- **channel:** `agent-code-reading` — found by re-running `git log` mid-investigation during the
  2026-08-08 governance audit and discovering two NEW `Auto-commit` commits (`9c8f684`, `743097a`)
  had landed on `main` **while the audit was already in progress**.
- **escape-audit:** no automated check exists anywhere in this repo for "does a commit reaching
  `main` carry an ATM-NNN citation / TDD trail, or is it a bare/templated message from an
  unattributed source" — §11.4.84 working-tree-quiescence has no mechanical guard on this specific
  path (writes arriving via an ordinary `git pull --ff` from a second session/host with push
  access to the same remotes, per the RD2-00 root-cause pass in
  `docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`: `git reflog` proved the two newest commits were
  never authored on the investigating host — they fast-forwarded in via `pull`, and their commit
  timezone (+0500) does not match the investigating host's own (+0300 MSK)). Genuinely uncovered —
  no gate flags an unattributed/unticketed commit reaching `main`.
- **new-check:** not yet authored (tracked, not yet closed — BOB-068 remains `Queued`). Followup
  filed: **BOB-106** — a §11.4.84 quiescence-check helper scanning the commit range since the last
  known-good release tag and FAILing on any bare/templated commit message (`^Auto-commit$`,
  `^sync: `, etc.) with no ATM-NNN reference, wired into `scripts/pre_build_verification.sh` or the
  §11.4.234 `commit-push-all.sh` entrypoint.
- **resolution status:** root cause NARROWED, not eliminated — `docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`
  RD2-00 Update 2 confirms the mechanism is (most likely) the operator's own second
  session/device bypassing per-commit TDD/review discipline on ITS side, not an unidentified
  external actor; this downgrades severity from P0 to P1 but does not close the item.

### BOB-072 — `docs/workable_items.db` machine-caught SSoT integrity violations (90% of closures had zero audit trail)

- **id:** BOB-072 (RD2-03) — **closed 2026-08-18**, commit `82d9842`
- **date:** found 2026-08-08 (governance audit); closed 2026-08-18
- **channel:** `agent-code-reading` at discovery (2026-08-08, an agent manually ran
  `constitution/scripts/workable-items/bin/workable-items validate --db docs/workable_items.db`
  during the audit — exit 1, 2 real violations: BOB-009/BOB-010 both had a `closure evidence_path`
  that does not resolve). Beyond the tool's own catch, a direct SQL sweep at the time found 56 of
  62 closed items (90%) with zero `item_history` rows.
- **escape-audit:** at the time of the 2026-08-08 discovery, invariant 17 of
  `scripts/pre_build_verification.sh` — the ONLY standing gate wired to run `workable-items
  validate` — was ITSELF silently SKIPPING on every run (the sibling coverage escape already
  ledgered above as **RD2-41b**, same date, same audit): a gate whose own precondition-check is
  broken cannot report the truth about the thing it gates. RD2-03's violations therefore went
  unnoticed by the standing regime until RD2-41b's own fix (same session) restored invariant 17 to
  a real PASS/FAIL verdict — the `existed-but-missed` class (§11.4.201(6) FALSE-NULL), not
  genuinely-uncovered.
- **new-check:** `challenges/scripts/workable_items_integrity_challenge.sh` extended with §11.4.115
  RED_MODE polarity (RED_MODE=1 reproduces on the pre-fix DB snapshot in `docs/qa/BOB-072-073/`,
  RED_MODE=0 default GREEN guard — both `validate` and `diff` exit 0), 3/3 PASS live-verified this
  session. Combined with the already-landed RD2-41b fix, invariant 17 is now the mechanized regime
  for this defect class.
- **Note (discovery-method signal, not a channel reclassification):** this session's closing
  verification (commit `82d9842`) captured its before/after evidence via the ACTUAL tool
  (`workable-items validate`/`diff` exit codes), not raw SQL or narrative inspection — the correct,
  mechanizable shape §11.4.238 wants going forward, even though the ORIGINAL 2026-08-08 discovery
  was still an agent running that tool by hand during an ad-hoc audit, not a standing/scheduled
  gate firing on its own. The channel is honestly recorded as `agent-code-reading`, not
  `automated-helixqa` — the tool was correct, its invocation was not yet automatic.

### META-11.4.227B-2026-08-18 — §11.4.227(B) anchor-block-integrity verified BY HAND, not by a mechanical gate

- **id:** none yet (governance meta-finding, not a `BOB-NNN` — the underlying anchor corpus is
  constitution-submodule-owned; this ledger records the escape because it was found during boba-repo
  work this session)
- **date:** 2026-08-18 (this session's §11.4.140/§11.4.141 anchor-number-collision resolution,
  Phase 0 — boba commit `136a22c`, constitution commits `5ed8c80`..`e5f2891`)
- **channel:** `agent-code-reading` — the Phase 0 subagent manually computed md5 hashes of the
  moved anchor bodies and manually grepped `### §11.4.140 ` / `### §11.4.141 ` occurrence counts,
  pasting the results verbatim into the commit message (`git show --stat 136a22c`) to prove
  §11.4.227(B) block-integrity (exactly-once per anchor, byte-identical lockstep across mirrors).
- **escape-audit:** §11.4.227(B) is fully specified in constitution prose ("propagation gates count
  BLOCK-STARTS never bare literals: exactly-once per anchor per file... lockstep content-hash
  equality across the mirror set... anchor-number collisions FAIL") but its own gate
  (`CM-ANCHOR-BLOCK-INTEGRITY`) is explicitly documented, by the anchor's own text, as "gate-code =
  separate work item, NOT claimed shipped." The §11.4.140/§11.4.141 collision that §11.4.227 itself
  cites as its founding forensic example was STILL only caught/fixed by a human-in-the-loop agent
  running ad-hoc `md5sum`/`grep` commands, not by a runnable script — the textbook §11.4.227 finding
  (413 named `CM-*` gates, 58% unimplemented) recurring live, in this repo, this session.
- **new-check:** OUT OF SCOPE for this ticket (constitution-submodule-owned mechanism; per this
  task's own constraints, boba may not touch anything constitution-related). Followup filed:
  **BOB-105** — a boba-side, read-only challenge that greps every governance file this project's
  constitution submodule checkout exposes for `### §11.4.NNN` heading occurrences and FAILs on
  >1-per-anchor-per-file or on two DIFFERENT anchor bodies sharing one NNN, implementing (from the
  consumer side, read-only) the check `CM-ANCHOR-BLOCK-INTEGRITY` names but does not yet run.

### SCRATCH-LOSS-2026-08-18 — Phase 1a subagent's declared source-material inputs absent at dispatch time

- **id:** none yet (this-session incident, constitution-curriculum work stream, not a `BOB-NNN`)
- **date:** 2026-08-18
- **channel:** `agent-code-reading` — the Phase 1a subagent (`a1cc331d`) discovered, at task start,
  that 5 source files its own task brief named as required reads
  (`curriculum_amendment_plan_v1.md`, `ai_curriculum_modules_27_35_extracted.md`, and three
  `curriculum_analysis_modules_*.md` gap-analysis files) were NOT present in the session scratchpad.
  Self-documented in `.superpowers/sdd/task-phase1a-report.md:21`. Independently re-verified during
  this BOB-069 audit: `curriculum_amendment_plan_v1.md` is STILL absent from the live scratchpad
  directory as of this writing, while the other four listed inputs now exist (apparently
  re-created by a later pass).
- **escape-audit:** root cause per the Phase 1a subagent's own investigation: "the prior
  stub-expansion subagent (`ae59171f`) apparently hit its session rate limit before writing them" —
  a §11.4.147(e)-class API-quota-exhaustion crash landing mid-deliverable, with no mechanical
  dependency check verifying a declared upstream artifact actually exists before a downstream
  subagent is dispatched to consume it. No automated check exists in this project's orchestration
  tooling that a task brief's named "read this first" inputs are present at dispatch time —
  genuinely uncovered; discovered only because the downstream subagent noticed and self-reported
  rather than silently fabricating content against an absent source (which its own brief's
  no-fabrication instruction — `[MATERIAL-THIN]` marking — correctly steered it away from).
- **new-check:** not yet authored. Followup filed: **BOB-107** — a pre-dispatch precondition check
  in the orchestration layer verifying every file a task brief cites as a required input exists and
  is non-empty before the downstream agent is spawned, failing closed with an actionable
  "missing input, respawn the producer" message.
- **Honest boundary (§11.4.6), stated explicitly:** the task brief that dispatched this BOB-069
  audit described this finding as "scratchpad reset between sessions" — that specific mechanism (an
  OS-level `/tmp` wipe or session-boundary reset) is NOT what the cited evidence actually shows; the
  evidence instead shows a crashed/rate-limited PRODUCER subagent that never wrote its declared
  deliverable, discovered by an honest downstream subagent. This entry records the mechanism the
  evidence actually supports, not the dispatching brief's hypothesis, per this ledger's own
  anti-fabrication discipline (§11.4.6/§11.4.238's "no fabricated entries" instruction).

## Discovery-channel split (tracked, per §11.4.238(E))

| Period | automated-helixqa | out-of-band (all channels) | out-of-band % |
|---|---|---|---|
| 2026-08-07 → 2026-08-10 (incremental, this period only) | 0 | 8 (`agent-code-reading` x4, `incidental-discovery` x3, `automated_background_scan` x1) | 100% |
| 2026-08-11 → 2026-08-12 (incremental, this period only) | 0 | 1 (`operator-report` x1) | 100% |
| 2026-08-18 (incremental, BOB-069 backfill — 4 new `### ` entries; the BOB-073 recurrence is an addendum to the existing BOB-008 heading, not a new `### `) | 0 | 4 (`agent-code-reading` x4: RD2-00/BOB-068, BOB-072, META-11.4.227B, SCRATCH-LOSS) | 100% |
| **Cumulative total (all `### ` entries to date, this row is what `CM-QA-DISCOVERY-LEDGER-FRESH` checks)** | **0** | **13** | **100%** |

**Pre-existing check-vs-table mismatch, found and fixed during this backfill (§11.4.6, not
silently patched around):** `scripts/pre_build_verification.sh` invariant 19
(`CM-QA-DISCOVERY-LEDGER-FRESH`) computes its expected count from ONLY the LAST row of this table,
comparing it against the TOTAL `### ` heading count under `## Entries`. The three "incremental,
this period only" rows above were never designed to satisfy that arithmetic on their own (each was
authored to show only that update's delta, not a running total) — re-running the exact invariant-19
awk logic against the pre-backfill file (`git show HEAD:docs/QA_DISCOVERY_LEDGER.md`) confirms this
was **already FAILing before this session's edits** (`entries=9 split-table-declared=1`, live-run
of `scripts/pre_build_verification.sh` confirms `FAIL [5]`). The **Cumulative total** row above is
added so the check's actual last-row-only arithmetic now passes (`0+13=13` == the real `### ` count
below); the three incremental rows are kept as honest per-period trend history. This finding is
itself a coverage escape of the same shape this ledger tracks (an `existed-but-missed` gate whose
own arithmetic silently drifted from the document it gates) but is fixed in the same edit that
found it since the fix is a one-line table-convention correction, not a new automated check.

**Honest note:** 100% out-of-band is the true, unflattering starting number — every entry above
was found by an agent reading code, running commands by hand, or hitting a real failure while
doing unrelated live-verification work; none by a standing HelixQA run. This is exactly the state
§11.4.238 exists to change; the target is this percentage trending toward zero as the `new-check`
column above closes each specific gap (RD2-42/RD2-43 are still open — no automated check authored
yet, tracked honestly as such) and as future work is driven through the HelixQA banks
(`challenges/helixqa-banks/`) rather than ad-hoc investigation.

**2026-08-18 backfill note (BOB-069):** this round added four entries discovered during the SAME
session that produced them (the constitution-curriculum amendment stream + the BOB-072/073/075
parallel fixes), plus one recurrence addendum to the pre-existing BOB-008 entry. All five remain
`agent-code-reading` — none crossed a standing automated gate. BOB-072 is the closest this ledger
has come to the ideal shape: its closing evidence was captured via the sanctioned tool
(`workable-items validate`/`diff`) rather than raw inspection, even though the discovery itself
predates any standing gate invoking that tool automatically. Four followup workable items were
filed (`BOB-104`..`BOB-107`) for the specific new/strengthened automated checks each entry's
`new-check` field names as not-yet-authored; none of the four checks are claimed as shipped by this
backfill (§11.4.6) — they are tracked, not implemented, here.
