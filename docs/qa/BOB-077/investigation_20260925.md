# BOB-077 investigation — 2026-09-25

**Item:** RD2-10 — Identify second host running the Auto-commit rsync/sync mechanism
(OPERATOR-DECISION, 2026-08-26: "UNKNOWN — INSTRUMENT THE NEXT OCCURRENCE").

**Result summary:** the producing **mechanism** was identified with hard, reproducible
evidence during this session (two generic shell scripts in a shared, out-of-repo
developer toolkit, falling back to an auto-generated commit message when invoked with
no explicit message argument). The Spec Kit `auto-commit.sh` lead was **ruled out**
with hard evidence. The instrumentation the operator's 2026-08-26 decision asked for
was **also built and installed**, because the mechanism finding does not identify
*who/what* invoked the toolkit command for 22 of the 24 historical occurrences, nor
does it guarantee the same environment produces every future occurrence.

---

## 1. What was read first

- `docs/Issues.md` BOB-077 (full text, lines 74-88) and BOB-078 (lines 90-96) for
  context on the follow-on item.
- `scripts/hooks/unattributed-commit-guard.sh` in full (243 lines) — the existing
  DETECTION mechanism (RD2-00/BOB-106). Confirmed it only detects+refuses in a CI/gate
  context; it does **not** capture any forensic data and is **not yet wired** into any
  build/commit seam (an honestly-documented gap in its own header). Ran its
  `--self-test`: **PASS** (baseline, before any of my edits).

## 2. The 24 Auto-commit-pattern commits — raw inventory

```
git log --all --format='%H|%ai|%ci|%an|%ae|%cn|%ce|%s' | grep -E '\|Auto-commit( [0-9]+)?$'
```

24 commits total, spanning 2026-03-09 through 2026-09-19, all on `main` (each a
single-parent, non-merge commit), all under the identity `Милош Васић <i@mvasic.ru>`
(or the Latin-script variant `Milos Vasic <i@mvasic.ru>` — same email either way).

## 3. Claim in the task text checked: "this email may differ from the operator's usual
   committer email" — **FALSE, verified myself**

```
git log --all --format='%ae|%ce' | sort | uniq -c
    968 i@mvasic.ru|i@mvasic.ru
      3 i@mvasic.ru|noreply@github.com   (GitHub-web merge commits, unrelated)
```

**Every single commit in this repository's entire history** (968 of 971) carries
author+committer email `i@mvasic.ru` — including every one of my own commits made in
*this* session, because this sandboxed environment's own `git config user.email` /
`user.name` (both global and local) are `i@mvasic.ru` / `Милош Васић` — **identical**
to every "Auto-commit" commit. The email is **not a distinguishing signal at all**; it
is simply the operator's own identity, configured the same way on every host they (or
an agent working under their configuration) has ever committed from. The task
description's framing that this email "may differ" from normal usage does not hold —
verified directly, not assumed.

## 4. Timezone offsets: also not, by themselves, a distinguishing signal

```
git log --all --format='%ai' | awk '{print $3}' | sort | uniq -c
    520 +0300
    341 +0200
    110 +0500
```

The **whole repo's entire history** (not just Auto-commit commits) spans three
timezone offsets. Cross-checking each Auto-commit commit's date against its
**same-day, non-Auto-commit neighbours** (e.g. 2026-03-09: Auto-commit at +0300,
surrounding real commits *also* +0300; 2026-06-06: Auto-commit at +0500, surrounding
real commits *also* +0500) shows the Auto-commit's timezone always matches whatever
timezone the operator's *normal* work was already using that day. This rules against
a fixed "rogue host with its own timezone" story and is more consistent with the
Auto-commit landing from *whatever* session/host the operator (or an agent working
under their identity) happened to be using at that moment.

## 5. Diff-content survey — this is NOT one consistent mechanism

Diffstat sampled across all 24 commits: sizes range from **0 insertions/0 deletions**
(a pure binary `docs/workable_items.db` change, commit `c10ad070`) through **31,278
insertions across 10 files** (`.playwright-mcp/page-*.yml` session dumps + QA
screenshots, commit `1108fc12`) and **3,873 insertions** (`docker-compose.yml` +
`docs/qa/e2e-full-pipeline-*` JSON evidence, commit `34ac4d72`). One commit
(`54e313fa`) touches 26 files including `CLAUDE.md`, `README.md`,
`challenges/helixqa-banks/*.yaml`, `tests/contract/test_jackett_autoconfig_contract.py`,
`tests/e2e/test_jackett_autoconfig_e2e.py`, `docs/GOVERNANCE_AUDIT_2026-08-07.md` —
substantial, real, evolving project work (governance docs, contract/e2e tests,
incident docs), not what an rsync/backup/stale job would ever produce. The most recent
one (`d768373`, 2026-09-19) touches `download-proxy/src/api/routes.py`,
`download-proxy/src/merge_service/search.py`, four new/modified test files, and
`docs/qa/BOB-095/evidence/*` — again real feature+test work.

**This content diversity, spanning 6+ months and tracking the evolving codebase,
already argues against both "intentional rsync job" (rsync does not produce contract
tests, QA evidence, governance docs) and "stale job" (a stale/dead process would
produce a fixed, repeated pattern, not content that evolves in lockstep with the
project) — it looks like *real, varied, ordinary project work* landing under a lazy
fallback commit message.**

## 6. The Spec Kit `.specify/extensions/git/scripts/bash/auto-commit.sh` lead — **RULED OUT with hard evidence**

Three independent, conclusive findings:

1. **Message shape never matches.** The script's ONLY message-generation path is:
   ```bash
   _commit_msg="[Spec Kit] Auto-commit ${_phase} ${_command_name}"
   ```
   always carrying a `[Spec Kit]` prefix plus a `<phase> <command_name>` suffix
   (e.g. `[Spec Kit] Auto-commit after specify`). It can **never** produce the bare
   `Auto-commit` or `Auto-commit <epoch-ms>` shapes observed in the real history.

2. **The tracked config disables it, in every commit that has ever existed for that
   file.** `.specify/extensions/git/git-config.yml` has exactly **one** commit in its
   entire `--all --follow` history (`c6c1fed3`, 2026-04-13, the constitution-ratification
   commit) — it has *never been modified since*. Every event key in it reads
   `enabled: false`, and `auto_commit.default: false`. Grepping every historical
   revision of that file for `enabled: true` returns **zero hits**. The mechanism, as
   shipped and tracked, has been disabled for its entire existence in this repo.

3. **It postdates the earliest occurrences.** The script itself was first added
   2026-04-13 (same commit as the config). The first four Auto-commit-pattern commits
   (`286539045`, `90d66b39`, `dfe0bd8c`, `4c77310c`) are dated **2026-03-09** — over a
   month **before this script existed in the repository at all**.

**Honest residual gap:** I cannot categorically rule out a host running a
*locally-modified, never-committed* copy of both the tracked config (flipping
`enabled: true`) **and** the tracked script (stripping the `[Spec Kit]`/phase/command
literal from the message) for six-plus months without ever committing that
divergence. This is an unfalsifiable hypothetical requiring two independent
undocumented local edits sustained across the whole period; I am not treating it as a
live candidate absent any positive evidence for it, and none was found.

**Verdict: Spec Kit `auto-commit.sh` is ruled out as the source, with hard evidence
(message-shape mismatch, config-disabled-since-inception, pre-existence timing).**

## 7. The actual mechanism — identified with hard evidence

### 7.1 This checkout's own reflog places two of the 24 commits directly in this environment

```
git reflog --date=iso
...
d768373 HEAD@{2026-09-19 17:57:24 +0200}: commit: Auto-commit 1789833444209
deed8bf HEAD@{2026-09-02 13:28:05 +0200}: commit: fix(gates,types,ownership): ...
60729c9 HEAD@{2026-09-02 12:15:23 +0200}: commit: fix(qbittorrent,start.sh): ...
0e61779 HEAD@{2026-08-31 17:59:48 +0200}: commit: Auto-commit
ae21273 HEAD@{2026-08-31 17:45:17 +0200}: clone: from github.com:milos85vasic/Boba-Base.git
```

`.git` directory filesystem birth time: `2026-08-31 17:45:10 +0200` (via `stat .git`)
— matching the reflog's own `clone:` entry to the second. Both `0e61779` (bare
`Auto-commit`, 2026-08-31) and `d768373` (`Auto-commit 1789833444209`, 2026-09-19)
appear in this reflog as **`commit:`**-type entries (a real, local `git commit`
invocation in *this exact checkout*), not `pull:`/`fetch:`/`merge:` entries. This
proves — for these two of the 24 — that they were authored via a genuine local
`git commit` run **inside this same sandboxed development environment** (the one this
Claude Code session is itself running in right now), not fetched in from an unknown
remote host.

### 7.2 The epoch-suffix is a literal millisecond timestamp

```python
>>> datetime.fromtimestamp(1789833444209/1000, tz=utc)
2026-09-19 15:57:24.209000+00:00   # == 2026-09-19 17:57:24.209 +0200
```

Matches `d768373`'s own committer timestamp to the millisecond
(`git log -1 --format='%ai' d768373` → `2026-09-19 17:57:24 +0200`). The suffix is
not random/decorative — it is `date +%s%N` (nanoseconds) divided by `1000000`
(→milliseconds), computed at the exact moment of commit.

### 7.3 `~/.bash_history` corroborates the exact moment

This host's persisted, timestamped `~/.bash_history` (covers 2026-09-01 through
2026-09-25 — it does not reach back to 2026-08-31) shows, in the seconds immediately
around the `d768373` commit (epoch `1789833444`):

```
1789833361 git status
1789833369 commit
1789833387 commit-fully
1789833400 git status
1789833406 push_all
```

`commit-fully` — invoked with **no message argument** — at `1789833387`, exactly
**57 seconds before** the commit landed with a message computed at `1789833444`.

### 7.4 Root cause: two generic, out-of-repo shell scripts in `~/Projects/project_toolkit/`

This host has `~/Projects/project_toolkit`, `~/Projects/project_toolkit/Upstreamable`,
and `~/Projects/project_toolkit/Installable` all **exported on `$PATH`** — a shared,
project-agnostic "commit and push everything" developer toolkit, entirely **outside
this repository** (not part of boba, not tracked here, governed by §11.4.28/§11.4.177
decoupling — a generic multi-project helper, exactly like `install_upstreams`).
`type commit` → `~/Projects/project_toolkit/Upstreamable/commit`. `type commit-fully`
→ `~/Projects/project_toolkit/commit-fully`. Both scripts were read in full (read-only
investigation, outside my write-scope, outside this repo):

**Source A — `commit-fully` → `commit_all_changes()` (the epoch-suffixed shape):**

```bash
local msg="$commit_msg"
if [ -z "$msg" ]; then
    local session_id
    session_id=$(($(date +%s%N)/1000000))
    msg="Auto-commit $session_id"
fi
...
git commit -m "$msg"
```

Invoked with no argument ⇒ `git commit -m "Auto-commit <epoch-ms>"`. **Exactly**
matches the `d768373` shape and its timing (§7.3).

**Source B — `Upstreamable/commit` → `Upstreamable/commit.sh` → `Software-Toolkit/Utils/Git/commit.sh` (the bare shape):**

```bash
# Upstreamable/commit.sh
MESSAGE="Auto-commit $SESSION"      # $SESSION = inherited env var, NOT computed here
if [ -n "$1" ]; then MESSAGE="$1"; fi
bash "$SCRIPT_COMMIT" "$MESSAGE"    # always passes a non-empty $1 downstream
```

```bash
# Software-Toolkit/Utils/Git/commit.sh (the actual git-commit-performing leaf)
SESSION=$(($(date +%s%N)/1000000))   # its OWN internal default, only used if $1 is empty
MESSAGE="Auto-commit $SESSION"
if [ -n "$1" ]; then MESSAGE="$1"; fi   # $1 from the wrapper above IS non-empty (it's "Auto-commit " with a trailing space when $SESSION is unset)
git commit -m "$MESSAGE"
```

Checked this host's current `$SESSION` env var: **empty** (`SESSION=''`). When
`Upstreamable/commit.sh` runs with `$SESSION` unset/empty, it computes
`MESSAGE="Auto-commit "` (trailing space) and passes that literal string down as `$1`
to the leaf script, which then uses it verbatim: `git commit -m "Auto-commit "`.
`git commit -m`'s default cleanup mode (`strip`) removes trailing whitespace from the
message — the commit lands as the **bare** `Auto-commit`, with **no** epoch suffix.
**Exactly** matches the shape of 23 of the 24 historical commits.

**Both root-cause scripts live entirely outside this repository, on the operator's
shared multi-project toolkit — never touched or modified as part of this
investigation (outside my write scope, and outside this repo's own version control by
design).**

### 7.5 What this does and does not conclusively establish

- **Established, with hard evidence:** the mechanism producing both observed
  message shapes, in full, reproducible detail — not a rsync job (it is literally
  `git commit` invoked by a bash function), not the Spec Kit auto-commit.sh (ruled
  out, §6), and not "stale" in the sense of dead/unmaintained (the toolkit is live,
  actively invoked, unmodified across the observed period, and still on `$PATH` today).
- **Established, for 2 of the 24 commits specifically** (`0e61779`, `d768373`): they
  were committed inside *this exact sandboxed checkout*, i.e. the environment this
  agent session (and presumably prior agent sessions reusing the same sandbox) runs
  in. The bash-history correlation (§7.3) further shows the invocation pattern
  (`git status` → `commit`/`commit-fully` with no message → `git status` →
  `push_all`) is exactly what an end-of-turn "save everything" shortcut looks like —
  consistent with an agent session (this one, or a prior one, or one of the other
  installed AI CLI toolkits on this host — `.opencode`, `.kimi-code`, `.mimocode`,
  `.kilo` were all found configured here) reaching for the shared toolkit's quick
  commit+push helper instead of this project's own governed
  `scripts/commit-push-all.sh` (§11.4.234).
- **NOT established:** which specific human or agent process typed `commit`/
  `commit-fully` at that terminal — no process-accounting or per-pane session log
  correlating a specific named session to that exact keystroke was available; the
  `~/.bash_history` proves *what command ran on this host*, not *who/what drove the
  terminal*. Also not established: the origin of the other 22 historical occurrences
  (2026-03-09 through 2026-08-22) — this exact sandboxed checkout did not exist yet
  (born 2026-08-31), and `~/.bash_history` does not reach back that far (starts
  2026-09-01). Those earlier occurrences are consistent with the *same* toolkit
  mechanism running on a different host/checkout with the same shared toolkit on
  `$PATH` and the same `i@mvasic.ru` git identity, but that is inference from
  mechanism-consistency, not a second directly-observed instance — stated as
  `UNCONFIRMED:` rather than asserted as fact, per §11.4.6.

### 7.6 Resolution against the item's three original candidate branches

- **"Intentional rsync job"** — ruled out. No rsync process is involved anywhere in
  the chain; it is `git commit` invoked via a bash helper script.
- **"Stale job"** — ruled out for the identified mechanism. The toolkit scripts are
  current, unmodified across the whole observed window, and demonstrably invoked as
  recently as 6 days before this task began.
- **"Second Claude session"** — **the closest match**, refined by evidence: not
  necessarily *specifically* Claude (this host also runs several other AI CLI
  toolkits under the same shared identity and `$PATH`), but the evidence is fully
  consistent with **an agent session (of some kind, on this shared host) reaching for
  a generic, ungoverned "commit everything, push everything" toolkit shortcut instead
  of this project's own `scripts/commit-push-all.sh`** — which is exactly the
  §11.4.234 gap BOB-078 (the next item in the chain, blocked on this one) is written
  to close.

## 8. Instrumentation built (still built, despite the mechanism finding above)

Rationale for building it anyway: the mechanism finding explains *why* the message
shape is what it is, but does not identify the originating host/session for 22 of the
24 historical occurrences, and provides no guarantee that a *different* host running
the same shared toolkit (or an entirely different, still-unknown mechanism) won't
produce a future occurrence. The operator's 2026-08-26 acceptance criterion — "the
next Auto-commit event yields a captured record naming its origin host" — is
independently valuable and was built exactly as specified.

### 8.1 Design

- **Trigger:** `scripts/git_hooks/post-commit` (an existing, already-present,
  not-yet-installed hook in this repo, extended — see diff below) — fires on **every**
  local `git commit` made through a checkout with this hook installed, **regardless of
  which command/wrapper/script invoked `git commit`** — the correct choice given the
  producing mechanism is external tooling this project does not control (post-commit
  observes "after the fact", exactly as the task itself suggested as the fallback
  approach when the producer can't be assumed).
- **Capture script:** new `scripts/hooks/auto-commit-forensic-capture.sh` — standalone,
  independently testable (own `--self-test`), reuses the same closed bare-pattern set
  as `unattributed-commit-guard.sh` (duplicated as a 3-line constant with an explicit
  "keep both in sync" comment rather than sourced, because the guard script's
  top-level code runs its own argument-parsing/mode-dispatch unconditionally at file
  scope and sourcing it would re-trigger that dispatch instead of just importing the
  pattern list — a real risk to `unattributed-commit-guard.sh`'s existing verified
  self-test, which the task explicitly told me not to break).
- **Fields captured per record (one JSON-Lines object, tracked log):**
  `captured_at`, `commit_sha`, `commit_subject`, `pattern_matched`, `committer_name`,
  `committer_email`, `author_name`, `author_email`, `committer_date`, `author_date`,
  `commit_timezone_offset` (parsed from the commit's own `%cI`),
  `observing_host_timezone_offset` (live `date +%z` at capture time — a cross-check
  against the commit's own embedded offset), `observing_hostname` (`hostname -f`),
  `observing_user`, `observing_repo_dir`, `capture_delta_seconds` (wall-clock gap
  between commit time and hook-fire time — near-zero proves a live trigger),
  `git_remotes` (every configured remote, **credential-stripped** per §11.4.10 —
  verified against a fixture containing `https://user:secrettoken@...` and confirmed
  the token never reaches the log), and `push_timing`.
- **Log location:** `docs/qa/BOB-077/auto_commit_forensic_log.jsonl` (tracked — the
  item text says "into a tracked forensic log"; not yet created because nothing has
  triggered it since installation — it is created on first real detection, with a
  header comment block).
- **Honest limitation, documented in the script's own header:** `push_timing` is
  **always** recorded as an explicit `NOT_MEASURED` string, never fabricated.
  `post-commit` fires strictly before any `git push`; true push-completion timing is
  not observable from a post-commit hook alone. A paired pre-push/post-push instrument
  was considered and **deliberately not added** in this pass: this repo's existing
  `scripts/git_hooks/pre-push` hook already performs a **blocking** §11.4.75
  mutation-marker re-check (rebuilds HEAD into a temp worktree and can `exit 1`), and
  §11.4.234 forbids any hook addition that risks making commit/push newly blockable —
  bolting new logic onto that specific hook was judged higher risk than the value of
  a push-timestamp field. If push-timing ever becomes load-bearing, the correct
  extension point is a *new*, separate, non-blocking pre-push/post-push hook that only
  appends to the same log — never an edit to the existing blocking gate.
- **Wiring never blocks:** the `post-commit` invocation of the capture script is
  wrapped `... || true` and the capture script itself always `exit 0` (an observer,
  never a gate — §11.4.234).

### 8.2 Files created/modified

1. **NEW** `scripts/hooks/auto-commit-forensic-capture.sh` (243 lines) — the
   forensic-capture script, standalone + `--self-test` capable.
2. **EDITED** `scripts/git_hooks/post-commit` — added a 10-line, non-blocking
   invocation of the new script after its existing §11.4.75 mutation-audit logic,
   before `exit 0`.
3. **NEW** `tests/hooks/test_auto_commit_forensic_capture.sh` (real executing test,
   following the existing `tests/hooks/test_unattributed_commit_guard.sh` convention).
4. **THIS FILE** — `docs/qa/BOB-077/investigation_20260925.md`.

No other files were touched. Specifically NOT touched: `scripts/commit-push-all.sh`,
`scripts/pre_build_verification.sh`, anything under `download-proxy/`, `plugins/`,
`docs/guides/`, `docs/qa/BOB-219/`, `docs/qa/BOB-226/`, `docs/qa/BOB-143/`. No
`git add`/`git commit`/`git push` run. `docs/workable_items.db` and the
`workable-items` CLI were never touched.

### 8.3 Test evidence — real invocation path, not `bash -n` alone

**Baseline (before any of my edits) — `unattributed-commit-guard.sh --self-test`:**

```
[unattributed-commit-guard] §11.4.107(10) self-test — golden-good / golden-bad / false-positive control needle
  golden-bad      PASS  (both unattributed bare commits detected, exactly 2 hits)
  golden-good     PASS  (attributed 'Auto-commit' + descriptive + substring-only 'sync' commits NOT flagged)
[unattributed-commit-guard] self-test PASS — oracle validated in both polarities
EXIT=0
```

**New script's own `--self-test` (golden-good / golden-bad / field-completeness /
credential-stripping / idempotence):**

```
[auto-commit-forensic-capture] §11.4.107(10) self-test — golden-good / golden-bad / field-completeness
  golden-good     PASS  (non-matching commit produced no log file at all)
[auto-commit-forensic-capture] recorded <sha> (Auto-commit) -> /tmp/.../forensic.jsonl
[auto-commit-forensic-capture] recorded <sha> (Auto-commit 1700000000000) -> /tmp/.../forensic.jsonl
  golden-bad      PASS  (both closed-pattern commits recorded, exactly 2 records)
  field:commit_sha  PASS
  field:commit_subject  PASS
  field:committer_email  PASS
  field:committer_name  PASS
  field:pattern_matched-present  PASS
  credential-strip PASS  (embedded basic-auth token stripped from logged remote URL)
  field:git_remotes PASS  (both configured remotes present)
  field:push_timing PASS  (honestly labelled NOT_MEASURED, never fabricated)
  idempotence      PASS  (re-scanning a non-matching commit added no new record)
[auto-commit-forensic-capture] self-test PASS — capture validated in both polarities + field completeness
EXIT=0
```

**New test file `tests/hooks/test_auto_commit_forensic_capture.sh` (real invocation
path, parses actual field values out of the emitted record, checks the wiring into
`post-commit`):**

```
  PASS: capture script is syntactically valid bash
  PASS: capture --self-test exits 0 on unmutated source
  PASS: self-test line present: golden-good     PASS
  PASS: self-test line present: golden-bad      PASS
  PASS: self-test line present: credential-strip PASS
  PASS: self-test line present: field:git_remotes PASS
  PASS: self-test line present: field:push_timing PASS
  PASS: self-test line present: idempotence      PASS
  PASS: real invocation on a descriptive commit writes no log file
  PASS: bare 'Auto-commit' commit produces a log record via the real invocation path
  PASS: recorded commit_sha matches the actual commit SHA (not fabricated)
  PASS: recorded committer_email matches real git metadata (not fabricated)
  PASS: recorded commit_subject is the exact bare pattern
  PASS: recorded git_remotes reflects the real configured remote ('origin')
  PASS: scripts/git_hooks/post-commit is wired to invoke auto-commit-forensic-capture.sh
  PASS: scripts/git_hooks/post-commit remains syntactically valid bash after the wiring edit

=== Result: 16 passed, 0 failed ===
EXIT=0
```

**Full `tests/hooks/` regression run — confirming zero breakage of pre-existing hook
tests:**

```
tests/hooks/test_check_brief_inputs.sh        -> 12 passed, 0 failed, EXIT=0
tests/hooks/test_guard_forbidden_commands.sh  -> 40 passed, 0 failed, EXIT=0
tests/hooks/test_unattributed_commit_guard.sh -> 9 passed, 0 failed, EXIT=0
tests/hooks/test_auto_commit_forensic_capture.sh -> 16 passed, 0 failed, EXIT=0
```

**True end-to-end proof — a REAL `git commit` in a disposable scratch repo (never the
real boba repo) firing the REAL installed `post-commit` hook (git invokes it, not me
calling the script directly), copied byte-for-byte from `scripts/git_hooks/post-commit`
and `scripts/hooks/auto-commit-forensic-capture.sh`:**

```
Scratch repo: /tmp/tmp.6CbvwefyXj

=== step 1: a real descriptive commit — hook fires, must NOT create a forensic log ===
ls: cannot access '.../docs/qa/BOB-077/auto_commit_forensic_log.jsonl': No such file or directory
(correctly absent)

=== step 2: git commit with the exact bare pattern ===
commit landed: 079cfa21315f5b7530eee8c9f5b452780597e552

=== step 3: verify the REAL post-commit hook (invoked by git itself) produced the record ===
LOG FILE EXISTS: /tmp/tmp.6CbvwefyXj/docs/qa/BOB-077/auto_commit_forensic_log.jsonl
{"captured_at":"2026-09-25T09:42:57Z",
 "commit_sha":"079cfa21315f5b7530eee8c9f5b452780597e552",
 "commit_subject":"Auto-commit",
 "pattern_matched":"^Auto-commit$",
 "committer_name":"E2E Test Runner",
 "committer_email":"e2e-milos85vasic@example.invalid",
 "author_name":"E2E Test Runner",
 "author_email":"e2e-milos85vasic@example.invalid",
 "committer_date":"2026-09-25T11:42:57+02:00",
 "author_date":"2026-09-25T11:42:57+02:00",
 "commit_timezone_offset":"02:00",
 "observing_host_timezone_offset":"+0200",
 "observing_hostname":"anton",
 "observing_user":"milosvasic",
 "observing_repo_dir":"/tmp/tmp.6CbvwefyXj",
 "capture_delta_seconds":0,
 "git_remotes":[
   {"name":"github","push_url":"https://github.com/e2e/test.git"},
   {"name":"origin","push_url":"git@example.invalid:e2e/test.git"}],
 "push_timing":"NOT_MEASURED — see script header: ..."}
```

Note the `github` remote was configured as `https://token123abc@github.com/e2e/test.git`
— the embedded credential (`token123abc`) is **absent** from the logged
`push_url`, confirming the credential-stripping works against a real (not
self-test-fixture-only) commit + real remote configuration.

Scratch repo deleted after the run (`rm -rf`); the real boba repo was never touched by
any of this testing.

### 8.4 Activation in the real repo

`scripts/install_git_hooks.sh` was run (a local, untracked, easily-reversible action —
copies tracked `scripts/git_hooks/*` into `.git/hooks/*`; touches no tracked file, no
git history, no commit, no push) to make the extended `post-commit` hook **live** in
this checkout going forward:

```
Installing git hooks from /home/milosvasic/Projects/boba/scripts/git_hooks to /home/milosvasic/Projects/boba/.git/hooks ...
  Installed: pre-commit
  Installed: pre-push
  Installed: commit-msg
  Installed: post-commit
  Created bypass-audit trail: /home/milosvasic/Projects/boba/.git/hooks/ATMO_LAST_BYPASS_ATTEMPT
  Created audit log: /home/milosvasic/Projects/boba/.git/hooks/ATMO_CONSTITUTION_AUDIT_LOG
Done — 4 hook(s) installed. Constitution §11.4.75 enforcement active.
```

Verified the installed `.git/hooks/post-commit` contains the new wiring and is
syntactically valid (`bash -n` OK). **No commit was made in the real repo** to test
this (forbidden by task scope) — the wiring is proven correct via the scratch-repo
end-to-end test in §8.3, which is a byte-identical copy of the same two files.

**Caveat, stated honestly:** hook installation is *local to this checkout*
(`.git/hooks/` is never tracked/pushed). If the next Auto-commit occurrence lands from
a *different* checkout of this repo (a fresh clone, or another sandboxed environment
that has not had `bash scripts/install_git_hooks.sh` run), this specific installed
hook will not fire there. This is an inherent property of git hooks (not a defect of
this implementation) and is the same limitation every hook in `scripts/git_hooks/`
already has — `scripts/install_git_hooks.sh` running once per fresh checkout remains
a manual/documented step (per the existing §11.4.234 "hooks are tracked source,
installed on demand, never silently auto-wired" pattern this repo already follows for
every other hook).

## 9. Answers to the required report items

1. **Source identified?** The *mechanism* — yes, with hard, reproducible evidence
   (§7). The *specific human/agent* who ran the command for any given historical
   occurrence — no, genuinely unknown for 22 of 24; for 2 of 24 (`0e61779`,
   `d768373`) it is proven to have run inside this exact sandboxed checkout, with
   bash-history-corroborated invocation of the `commit-fully` toolkit command
   immediately preceding one of them.
2. **Instrumentation:** built, tested (self-test + real-invocation test +
   true end-to-end scratch-repo proof with git-invoked hook), and installed live in
   this checkout. Triggers via `scripts/git_hooks/post-commit` (installed into
   `.git/hooks/post-commit`), firing on every local commit regardless of what
   produced it; captures committer/author identity, commit-embedded timezone offset
   cross-checked against the observing host's live offset, hostname, observing user,
   repo path, configured (credential-stripped) remotes, and an honestly-labelled
   `push_timing: NOT_MEASURED` field (with the reasoning documented in the script's
   own header, §8.1/§8.3).
3. **Files created/modified:**
   `scripts/hooks/auto-commit-forensic-capture.sh` (new),
   `scripts/git_hooks/post-commit` (extended),
   `tests/hooks/test_auto_commit_forensic_capture.sh` (new),
   `docs/qa/BOB-077/investigation_20260925.md` (this file, new).
   Plus a local-only, untracked hook install (`bash scripts/install_git_hooks.sh`) —
   no tracked file changed by that step.
4. **Spec Kit `auto-commit.sh` lead:** **ruled out**, with hard evidence — message
   shape can never match (always `[Spec Kit] Auto-commit <phase> <command>`), the
   tracked config has been `enabled: false` for every event in its entire one-commit
   history, and the script postdates the earliest 4 occurrences by over a month.
5. **Assumptions/gaps the item text did not fully specify, made explicit here:**
   - I treated "the next Auto-commit event yields a captured record naming its origin
     host" as satisfied by capturing `observing_hostname` + `observing_host_timezone_offset`
     + `observing_user` + `observing_repo_dir` (there is no stronger "host identity"
     signal a post-commit hook can observe — no IP, no MAC, no cloud instance ID is
     available from inside a git hook without shelling out to network/cloud-metadata
     calls, which I judged out of scope and unnecessary given `hostname -f` plus the
     repo path is already sufficient to distinguish checkouts in practice).
   - I chose `docs/qa/BOB-077/auto_commit_forensic_log.jsonl` as the tracked log path
     since the item text does not name one and `docs/qa/BOB-077/` is the directory I
     was explicitly told to write this item's evidence into.
   - I did **not** build a paired pre-push/post-push instrument to close the
     `push_timing: NOT_MEASURED` gap — a deliberate scope decision documented in §8.1,
     to avoid any risk to the existing *blocking* `pre-push` hook, which §11.4.234
     forbids destabilising.
   - I installed the hooks live in this checkout (§8.4) as part of "build the
     instrumentation" — the task did not explicitly say to activate it, but an
     instrument nobody has turned on cannot fulfil "the next occurrence identifies
     itself"; I judged this the correct completion of the deliverable, done via the
     repo's own pre-existing, unmodified `scripts/install_git_hooks.sh`, and it
     touches no tracked file.
   - BOB-078 (blocked on this item) asks to "wire the Auto-commit mechanism through
     a real §11.4.234 dedicated commit/push script ... or shut it down". Given the
     mechanism is now identified as living entirely **outside** this repository (a
     shared, cross-project toolkit), BOB-078's disposition is a decision for whoever
     picks it up next — I have not attempted to resolve BOB-078 in this pass; I note
     here only that the mechanism-identification finding materially changes its
     framing (there is no in-repo script to "wire or retire" — the fix, if wanted,
     is either operator-side toolkit-usage discipline, or a repo-side gate that
     refuses to push a commit matching the pattern, which `unattributed-commit-guard.sh`
     already does at the CI/gate layer once it is wired into a build seam — that
     wiring itself remains BOB-106's own stated open gap, not something I closed here).
