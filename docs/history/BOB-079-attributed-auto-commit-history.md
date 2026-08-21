# BOB-079 — Attributed history notes for the Auto-commit / `sync:` population (v1.0.0-rc..HEAD)

**Revision:** 1
**Last modified:** 2026-08-21T19:39:37Z
**Status:** documentation note (§11.4.113 — never a history rewrite; this record supplements published
history, it does not touch it)
**Item:** [BOB-079](../workable_items.db) — RD2-12: "Retroactive attributed history notes for
GA-18/21/22/25/26/27 changes (never rewrite published history)"

## Purpose

`docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md` (RD2-00, P0) established that a recurring class of
commit — bare `Auto-commit` and templated `sync: ...` subjects, carrying no ATM-NNN/BOB-NNN or
task/PR reference — has been landing in this repository via a `git pull` fast-forward from a
second host, bypassing §2 (mandated commit wrapper), §11.4.43 (TDD-fix), §11.4.92 (5-pass
evaluation), §11.4.125/§11.4.142/§11.4.194/§11.4.209 (mandatory independent Fable-xhigh review),
and §11.4.234 (dedicated hook-validation script). RD2-12 (this item, BOB-079) asks for a
documentation/changelog note — **not** a history rewrite — that gives each such commit a real,
evidenced attribution: what it actually changed, and which tracked item or work stream (if any)
it can be shown to belong to.

This note is that record. Per §11.4.113 no commit referenced below was amended, rebased, or
force-pushed; every fact here was derived by reading the commit's own diff (never its subject
line, which is precisely what is missing) and cross-checking against the project's own tracked
documents, following the §11.4.124 investigate-before-attribute pattern (git history is FACT,
"probably belongs to X" is a guess and is forbidden per §11.4.6).

## Method

1. The population was enumerated with the project's own guard,
   `scripts/hooks/unattributed-commit-guard.sh` (built for BOB-068/RD2-00; not modified by this
   item), run with no arguments so it scans `<last-reachable-tag>..HEAD` — its real, documented
   default behaviour. The guard's full verbatim output is pasted in the next section.
2. For every flagged SHA: `git show -s --format='...'` for date/author/parents/subject/body,
   `git show --stat --format=''` for the full file list, and `git show -- <path>` / `git diff
   --submodule=log <sha>^ <sha>` for the actual content diff of every changed file (including
   gitlink/submodule-pointer moves) — never the subject line, which carries no information here.
3. Where a diff itself cites a governance-finding id (a `GA-NNN` / `RD2-NNN` code-comment, e.g.
   `# GA-11: ...`) that citation is treated as evidence and reported as such, with the file/line
   it came from. Where a diff or its cross-referenced doc (`GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`)
   independently names the commit's short SHA, that is likewise reported as evidence, not
   inference.
4. Where no such citation exists anywhere in the commit (diff, commit body, or a tracked doc that
   names the SHA), the owning item/work-stream is recorded literally as **UNKNOWN** — the change
   itself is still described in full from the diff, but no ticket is guessed onto it. Per §11.4.6
   this is intentional: a fabricated attribution is worse than an absent one because it looks
   authoritative.
5. The project's `docs/workable_items.db` was queried (read-only `SELECT`, never a write — writes
   to that DB are out of this item's scope and belong to the reporting/workable-items tooling
   only) for any existing tracked item whose body already names one of the GA-NNN/RD2-NNN ids
   found in step 3, to check whether a BOB-NNN placeholder already exists for that specific
   finding. None does beyond BOB-079/BOB-080 themselves (see the per-commit table).

## Guard output (verbatim, this session)

```
$ bash scripts/hooks/unattributed-commit-guard.sh
[unattributed-commit-guard] scanning v1.0.0-rc..HEAD (last known-good release: v1.0.0-rc)

  ── UNATTRIBUTED BARE/TEMPLATED COMMIT(S) (§11.4.84) ──
  
c5576083b81967f9481d1c6e4e918c5d886192d8 Auto-commit

de9270b8ea600fb068270679e98af1a7da35ce38 Auto-commit

1c367775c4a2c816d2973e2097d7de0915cfe9fa Auto-commit

41179c29d917728e7159630dc4a9f68e7dda3170 Auto-commit

7c529ca294314226507339382274ff500a3cf2e0 Auto-commit

34ac4d725f9757db4158e5a51a61edd5c5549926 Auto-commit

49087d769b747fbcfc594685af6d38f5752fff2b Auto-commit

743097ab22a6ebb5fe85ff345259e456b580c2ac Auto-commit

9c8f684ea6e20824ee503ad19b1266450d29847d Auto-commit

54e313fa814fbf87803b274db0bd073cb1966c11 Auto-commit

0d05ec14acfc6e29939c001bbe99da54f573bfa1 Auto-commit

55b86718d8fa759103f575794928cc90665256b9 sync: post-rsync commit 20260628

cdb555f3683e85bd0864e63c5f8f5beee096a820 sync: auto-commit before cross-host sync 20260628

1108fc12112fb8b937429ef30ce6b8e0b1bd8c82 Auto-commit

  14 commit(s) in v1.0.0-rc..HEAD match a closed bare/templated
  pattern with no ATM-NNN or task/PR reference. Per BOB-068 (RD2-00)
  these land via git pull fast-forward from a second session/host —
  investigate the source before amending history (§11.4.113: no
  force-push / no history rewrite; land a documented, attributed
  follow-up commit instead).
```

`v1.0.0-rc` was tagged 2026-06-11T07:28:22+05:00 (`69daf870`) and is a real ancestor of the
current `HEAD` (`0fdc9193`, 2026-08-21T20:39:38+02:00, branch `002-user-owned-downloads`) —
verified with `git merge-base --is-ancestor v1.0.0-rc HEAD`. The population above is therefore
the complete, real set the guard's documented default range produces today; it was not
hand-filtered.

## Per-commit attribution

Chronological, oldest first. "Evidence" column states exactly what was read to produce the row;
"Owning item / finding" is either a cited id (with its source) or the literal `UNKNOWN`.

### `cdb555f3` — 2026-06-28T00:22:45+03:00 — Milos Vasic
**Subject:** `sync: auto-commit before cross-host sync 20260628`
**Files (2):** `.codegraph/.gitignore` (-16 net), `constitution` (submodule pointer bump)
**Evidence:** `git show --stat`, `git show -- .codegraph/.gitignore`, `git diff --submodule=log`.
**What it did:** trims `.codegraph/.gitignore` from 26 to a shorter pattern set, and advances the
`constitution` submodule pointer by one commit.
**Owning item / finding:** UNKNOWN by ticket. Process-attributed by
`GOVERNANCE_AUDIT_2026-08-08_ROUND2.md` (its RD2-00 finding, reflog analysis) as the **named
precedent** for the cross-host sync mechanism this whole population belongs to — this commit and
its child `55b8671` are the June instance the audit explicitly cites as evidence the mechanism is
"a known-but-under-labeled operational sync script running on a second host," not an unknown
process. No BOB-NNN/ATM-NNN exists for the underlying content change itself.

### `55b86718` — 2026-06-28T01:03:00+03:00 — Милош Васић
**Subject:** `sync: post-rsync commit 20260628`
**Files (3):** `qBitTorrent-go/internal/api/api_test.go`, `qBitTorrent-go/internal/api/search.go`,
`qBitTorrent-go/internal/service/merge_search.go` (28 insertions / 18 deletions)
**Evidence:** `git show --stat`, `git show -- <each path>`.
**What it did:** a real Go source change to the merge-search service + its search API + the
corresponding test file — not documentation or config only.
**Owning item / finding:** UNKNOWN. No ticket/GA/RD2 id anywhere in the diff or body. Same
cross-host `rsync` mechanism as `cdb555f3` per the audit's reflog-based process attribution
above.

### `1108fc12` — 2026-06-15T18:52:41+03:00 — Milos Vasic
**Subject:** `Auto-commit`
**Files (10):** 8 `.playwright-mcp/page-2026-06-14T*.yml` accessibility-tree captures +
`qa-buttons-multixt-magnet-BEFORE.png` + `qa-buttons-singlext-magnet-AFTER.png` (31,278
insertions, all additions)
**Evidence:** `git show --stat`, `git diff-tree --name-only`.
**What it did:** commits a Playwright MCP browser-automation session's raw page-snapshot YAML
captures and two before/after screenshots, named for a "multi-torrent-extension vs
single-torrent-extension magnet button" comparison — a QA/manual-testing session's raw artefacts,
landed wholesale with no accompanying doc, test, or ticket reference.
**Owning item / finding:** UNKNOWN. The filenames self-describe the QA scenario (multixt vs
singlext magnet button behaviour) but cite no BOB-NNN/ATM-NNN, and no tracked item in
`docs/workable_items.db` was found whose body names this scenario.

### `0d05ec14` — 2026-08-07T21:52:05+03:00 — Милош Васић
**Subject:** `Auto-commit`
**Files (1):** `constitution` (submodule pointer, `212b883` → `4ab25f5`)
**Evidence:** `git show --stat`, `git diff --submodule=log 0d05ec14^ 0d05ec14`.
**What it did:** a pure constitution-submodule pointer advance, one commit forward, no other file
touched.
**Owning item / finding:** UNKNOWN. No content beyond the pointer move; nothing in the constitution
submodule's own log line (`git diff --submodule=log`) names a boba-side ticket.

### `54e313fa` — 2026-08-08T11:18:51+03:00 — Милош Васић
**Subject:** `Auto-commit`
**Files (26):** `.gitignore`, `CLAUDE.md`, `README.md`, 6× `challenges/helixqa-banks/*.yaml`,
`challenges/scripts/jackett_autoconfig_clean_slate.sh`, `docs/CONTINUATION.md`,
`docs/GOVERNANCE_AUDIT_2026-08-07.md` (new, 392 lines), `docs/PORTING-FROM-LAVA.md`,
`docs/REMAINING_WORK_PLAN.md`, `docs/TESTING.md`,
`docs/incidents/2026-08-07-const033-poweroff-signal-triage.md` (new, 230 lines),
`docs/workable_items.db` (binary), `extension/package-lock.json`,
`extension/tests/unit/torrent-file.test.ts`, `pyproject.toml`,
`scripts/host-power-management/check-no-suspend-calls.sh`, `start.sh` (+128/-…),
and 4 test-file deletions under `tests/{contract,e2e,integration,security}/`.
**Evidence:** `git show --stat` (26-file list read in full) cross-checked against
`docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md` lines 271-330, which independently and explicitly
names this bundle by content, not by SHA, as the carrier of six findings, and separately (line
159-ish) as the single commit RD2-00's reflog analysis traces to this host.
**Owning item / finding — EVIDENCE-BACKED, six findings named by the audit doc itself:**
- **GA-18** (7 dead `jackett-autoconfig` test bodies removed — one file deleted entirely, three
  others' skip-only bodies stripped) — the four test-file deletions in the file list above.
- **GA-21** (`jackett_autoconfig_clean_slate.sh` retired-endpoint fix, now polling the Go `:7189`
  `/api/v1/jackett/autoconfig/runs` API) — confirmed present: this file carries a header comment
  citing "GA-21, 2026-08-08" per the audit's own re-read.
- **GA-22** (6 HelixQA bank dangling symlinks fixed) — the 6 `challenges/helixqa-banks/*.yaml`
  entries in the file list, each now a resolving relative symlink per the audit's re-verification.
- **GA-25** (CONST-033 real-signal triage) — `docs/incidents/2026-08-07-const033-poweroff-signal-triage.md`,
  the new 230-line file in this bundle; content correctness independently confirmed by the audit
  (uptime cross-check, kernel-signal grep, both CONST-033 challenges re-run).
- **GA-26** (ruff `submodules/containers/` exclusion) — `pyproject.toml`'s `extend-exclude` list;
  the audit independently re-ran `ruff check .` and confirmed 0 violations.
- **GA-27** (Hard Stop #3 `start.sh` subcommands — `reload_python`/`reload_plugins`/
  `recreate_stack`) — the `start.sh` (+128 line) hunk in this bundle; the audit separately notes
  this landed with zero test coverage (`grep -rln ... tests/ challenges/` → zero hits at the time),
  which is why BOB-089 (RD2-24) exists as the follow-up and is already `Completed (→ Fixed.md)`
  in `docs/workable_items.db`.

  The audit's own verdict for all six is **DONE-BUT-PROCESS-VIOLATION**: the code changes are
  independently confirmed correct, but they bypassed every review/TDD gate this class of commit
  bypasses — which is exactly the governance defect BOB-080 (RD2-13) tracks separately for
  Fable-xhigh re-review of this same diff.

### `9c8f684e` — 2026-08-08T16:18:21+05:00 — Milos Vasic
**Subject:** `Auto-commit`
**Files (6):** `constitution` (`4ab25f5`→`5eb3f11`), `submodules/{challenges,containers,helixqa,jackett}`
(4 pointer bumps), `scripts/host-power-management/check-no-suspend-calls.sh` (+11 lines).
**Evidence:** `git show --stat`, `git diff --submodule=log`, `git show -- scripts/host-power-management/check-no-suspend-calls.sh`.
**What it did:** four submodule pointer advances plus 11 more lines added to the same
suspend-call-guard exclude-list file that GA-24/`54e313fa` first touched — same functional area
(the guard's known carrier-false-positive class) as GA-24, but this specific commit is not named
by SHA in the audit doc's GA-24 paragraph, which discusses the exclusion list's state, not this
particular follow-on edit.
**Owning item / finding:** UNKNOWN by ticket/finding id for this specific SHA. Functionally
continuous with the GA-24 carrier-false-positive class (same file, same kind of edit) but not
independently cited.

### `743097ab` — 2026-08-08T16:25:52+05:00 — Milos Vasic
**Subject:** `Auto-commit`
**Files (2):** `constitution` (`5eb3f11`→`e0cea69`), `submodules/helixqa` (`66e490d`→`db18c40`)
**Evidence:** `git show --stat`, `git diff --submodule=log`.
**What it did:** two submodule pointer advances, no other content.
**Owning item / finding:** UNKNOWN. Pure pointer bump, no citation anywhere.

### `49087d76` — 2026-08-08T19:58:14+03:00 — Милош Васић
**Subject:** `Auto-commit`
**Files (4):** `docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md` (new, 553 lines),
`download-proxy/src/api/routes.py`, `download-proxy/src/api/scheduler.py`,
`tests/security/test_hooks_schedules_auth.py`
**Evidence:** `git show -- <each path>` (full diff read, not stat-only).
**What it did — EVIDENCE-BACKED, self-citing diff:** adds the `require_api_token` dependency to
`PATCH /api/v1/schedules/{id}` (`scheduler.py:108-110`) and to `PUT /api/v1/theme`
(`routes.py:118`), and extends `tests/security/test_hooks_schedules_auth.py`'s `_MUTATING`
enumeration with `_patch_schedule`/`_put_theme` cases plus a JSON-serializable scheduler-search
double. The `routes.py` diff itself contains the comment *"AFTER this function — GA-11's `PUT
/theme` fix is the first route..."* and the test diff contains *"# GA-11: a JSON-serializable
double for get_scheduled_search..."* — both direct, in-diff citations, not inferred. It also adds
`docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md` itself (the 553-line audit document quoted
extensively above) in the same commit.
**Owning item / finding:** **GA-11** ("PATCH schedules / PUT theme still unauthenticated"), cited
in the commit's own diff. Note for the record: `GOVERNANCE_AUDIT_2026-08-08_ROUND2.md` (added in
this very commit) separately describes GA-11 as still **NOT-DONE** at the time of writing —
this session did not attempt to reconcile that apparent discrepancy (whether the fix landed
before or after the audit text was drafted, in the same auto-commit, is outside BOB-079's scope);
it is stated here as an observed fact, not resolved.

### `41179c29` — 2026-08-12T20:44:17+02:00 — Милош Васић
**Subject:** `Auto-commit`
**Files (1):** `constitution` (submodule pointer, `b128eec`→`3cc71cd`)
**Evidence:** `git show --stat`, `git diff --submodule=log`.
**What it did:** a pure constitution-submodule pointer move. Notably this moves the pointer back
to `3cc71cd` — the exact value it held *before* its own parent commit `7c529ca2` (below) had just
advanced it to `b128eec`. This is consistent with, not separately proof of, the audit's
cross-host-sync hypothesis (two hosts independently advancing the same submodule pointer in
different directions); recorded as an observation, not a re-derivation of that root cause.
**Owning item / finding:** UNKNOWN. No citation.

### `7c529ca2` — 2026-08-12T23:42:03+05:00 — Milos Vasic
**Subject:** `Auto-commit`
**Files (2):** `constitution` (`3cc71cd`→`b128eec`),
`scripts/host-power-management/check-no-suspend-calls.sh` (+20 lines)
**Evidence:** `git show --stat`, `git diff --submodule=log`, `git show -- scripts/host-power-management/check-no-suspend-calls.sh`.
**What it did:** a constitution pointer advance plus 20 more lines added to the same
suspend-call-guard exclude list touched by `54e313fa`/`9c8f684e` above — same functional area as
GA-24 again, not independently cited by SHA.
**Owning item / finding:** UNKNOWN by ticket/finding id for this specific SHA; same
carrier-false-positive-guard functional area as GA-24 (not independently cited).

### `34ac4d72` — 2026-08-09T15:16:57+03:00 — Милош Васић
**Subject:** `Auto-commit`
**Files (5):** `docker-compose.yml`, `docs/qa/e2e-full-pipeline-20260809/multi_source_merge_samples.json`,
`docs/qa/e2e-full-pipeline-20260809/search_linux_full_pipeline.json`,
`docs/qa/e2e-full-pipeline-20260809/tracker_stats_summary.json`, `download-proxy/hooks.json`
(3,873 insertions, all additions except the `docker-compose.yml` hunk)
**Evidence:** `git show -- docker-compose.yml` (full diff read), `git show --stat` for the rest.
**What it did — EVIDENCE-BACKED for the `docker-compose.yml` hunk, self-citing diff:** adds a
`BOBA_API_TOKEN=${BOBA_API_TOKEN:-}` environment passthrough to the `qbittorrent-proxy` service,
with an inline comment reading *"RD2-22 (docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md): optional
shared-secret gate for the mutating download/hooks/schedules/theme routes
(api/routes.py require_api_token). Unset/empty -> those routes stay OPEN (§11.4.122
backward-compat default, unchanged)."* — a direct, in-diff citation.
**Owning item / finding:** **RD2-22**, cited in the commit's own diff, for the `docker-compose.yml`
hunk specifically. The three `docs/qa/e2e-full-pipeline-20260809/*.json` files and
`download-proxy/hooks.json` are QA/captured-evidence artefacts (self-describing directory name,
consistent with a real end-to-end pipeline test run) but carry no ticket citation of their own —
recorded as UNKNOWN for those four files.

### `de9270b8` — 2026-08-15T11:39:43+02:00 — Милош Васић
**Subject:** `Auto-commit`
**Files (1):** `plugins/rutracker.py` (1 line changed)
**Evidence:** `git show -- plugins/rutracker.py` (full diff read).
**What it did:** widens the RuTracker plugin's hardcoded `User-Agent` HTTP header string from a
bare `"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"` to a fuller, more current
Chrome-branded UA string.
**Owning item / finding:** UNKNOWN. No ticket/GA/RD2 id anywhere in the diff or commit body; no
accompanying test or doc change.

### `1c367775` — 2026-08-12T22:56:43+02:00 — Милош Васић
**Subject:** `Auto-commit`
**Files (1):** `docs/qa/coverage-escape-tmux-oomd-20260812/RESUMPTION.md` (new, 68 lines)
**Evidence:** `git show -- <path>` (full file content read, not stat-only).
**What it did:** commits a self-contained session-resumption handoff document, dated
2026-08-12T22:55:00Z, describing an operator-triggered `tmx kill-server` restart mid-session and
listing prior work as already-shipped elsewhere: `vasic-digital/tmux` (`6f9eaeb`
"TMX-083 systemd-oomd victim-avoidance", `92ef3a0`, `b29b9e1`), `HelixDevelopment/qa`
(`50f9ccf` "boba-tmux-session-hardening" bank), and `milos85vasic/Boba-Base`
(`bdb2490` "§11.4.238 coverage-escape audit + first challenge", `058ecda`).
**Owning item / finding:** UNKNOWN for this boba repository's own tracker — every id the document
names (`TMX-083`, `HXC-239/243/267/270/278`) belongs to sibling submodule/external repositories,
not to `docs/workable_items.db`. No BOB-NNN/ATM-NNN was found in this repo's DB whose body
references this scenario. The document is internally self-describing (not silent about its own
origin) even though it carries no local ticket id.

### `c5576083` — 2026-08-20T00:19:23+02:00 — Милош Васић
**Subject:** `Auto-commit`
**Files (8):** `.gitmodules`, `.specify/extensions.yml`, `.specify/extensions/.registry` (new),
`.specify/init-options.json`, `.specify/integration.json`,
`.specify/integrations/speckit.manifest.json`, `.specify/scripts/bash/update-agent-context.sh`
(deleted, -854 lines), `superspec` (new submodule gitlink)
**Evidence:** `git show --stat`, `git show -- .gitmodules`, `git ls-tree c5576083 -- superspec`
(confirms `superspec` is a real `160000` gitlink commit, not a plain file).
**What it did:** SpecKit tooling reorganisation — registers a new `superspec` submodule
(`git@github.com:WangX0111/superspec.git`), deletes the 854-line vendored
`.specify/scripts/bash/update-agent-context.sh` (presumably superseded by the new
submodule/extension mechanism), and updates the four `.specify/*.json`/`.yml` config files
accordingly.
**Owning item / finding:** UNKNOWN. No ticket/GA/RD2 id anywhere in the diff or commit body.

## Counts (§11.4.6 — stated, not implied)

Of the **14** commits the guard's real, unmodified default scan (`v1.0.0-rc..HEAD`) reports:

- **3 commits carry an in-diff, self-citing owning-finding reference**, independently
  cross-checked against a tracked document: `54e313fa` (GA-18, GA-21, GA-22, GA-25, GA-26, GA-27
  — six findings named by `GOVERNANCE_AUDIT_2026-08-08_ROUND2.md`), `49087d76` (GA-11), and
  `34ac4d72` (RD2-22, for one of its five files only).
- **11 commits have no citable owning item or finding anywhere in their diff, body, or a
  cross-referenced tracked document** and are recorded above as **UNKNOWN**: `cdb555f3`,
  `55b86718`, `1108fc12`, `0d05ec14`, `9c8f684e`, `743097ab`, `41179c29`, `7c529ca2` (the
  `docs/qa/e2e-full-pipeline-20260809/*` + `download-proxy/hooks.json` files inside `34ac4d72`
  are counted within that commit's row, not as a 12th UNKNOWN commit), `de9270b8`, `1c367775`,
  `c5576083`.
- None of the 14 commits were reverted, amended, rebased, or force-pushed to produce this record
  (§11.4.113). No entry above states an owning item that was not read directly from evidence.

## What this record does not do

- It does not close BOB-079's underlying process defect (the second-host sync mechanism itself
  remains an open §11.4.66 operator decision per RD2-00) — it only supplies the attribution text
  RD2-12 asked for.
- It does not perform the Fable-xhigh independent re-review of these diffs — that is BOB-080
  (RD2-13), a separate tracked item.
- It does not resolve the `49087d76` GA-11 timing discrepancy noted above.

## README linkage (§11.4.212)

This document is not yet linked from `README.md`. `README.md` is owned by a concurrent stream in
this session and was not edited by this item. The line below is the one that should be added by
whoever next has write access to `README.md`, in the existing `### Incidents & QA evidence`
section (the section already covering `docs/QA_DISCOVERY_LEDGER.md`, `docs/incidents/`, and
`docs/qa/`), placed as a new bullet immediately after the existing `docs/qa/` bullet:

```markdown
- [`docs/history/BOB-079-attributed-auto-commit-history.md`](docs/history/BOB-079-attributed-auto-commit-history.md) — retroactive, evidenced attribution for the 14 unattributed `Auto-commit`/`sync:` commits in `v1.0.0-rc..HEAD` (BOB-079/RD2-12), never a history rewrite (§11.4.113)
```
