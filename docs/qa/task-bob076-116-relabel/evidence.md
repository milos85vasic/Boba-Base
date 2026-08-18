# Evidence — BOB-076/BOB-116 label-collision cleanup (2026-08-18)

**Scope:** rename `docs/qa/BOB-076/` → `docs/qa/BOB-116/` (filesystem, not a git operation —
see finding below) + update forward references in
`docs/incidents/2026-08-18-perceived-forced-logout-2nd.md`,
`docs/QA_DISCOVERY_LEDGER.md`, `docs/CONTINUATION.md`, and the
`forced_logout_incidents.md` memory playbook. Commit-message history is NOT
rewritten (§11.4.113).

## 1. Directory rename

`docs/qa/BOB-076/` contained 8 evidence artifacts, all `*.log`:

```
challenge_pass.log
challenge_polarity_forced_fail.log
const033_challenge_pass.log
journalctl_20-40_to_20-52.log
lid_and_session_events.log
oomctl_snapshot.log
psi_readings.log
ps_LRSS_snapshot.log
```

**Finding: none of these 8 files were ever tracked by git.** `git ls-files
docs/qa/BOB-076/` returned empty before the rename, and `git check-ignore -v`
confirmed every one matches the blanket `*.log` rule at `.gitignore:64`. This
means `git mv` fails ("source directory is empty") — the rename had to be a
plain filesystem `mv`, and `git status` shows nothing for either the old or
new path, before or after. Verified move (identical byte sizes, same 8
filenames, directory now empty at the old path):

```
$ mv docs/qa/BOB-076 docs/qa/BOB-116
$ ls docs/qa/BOB-116/ | wc -l
8
$ ls docs/qa/BOB-076
ls: cannot access 'docs/qa/BOB-076': No such file or directory
$ git status --porcelain docs/qa/BOB-116/ docs/qa/BOB-076/
(empty)
```

**Concern (out of scope, flagged honestly per §11.4.6):** this is itself a
coverage-escape-shaped gap — `.gitignore`'s header comment at line 2 states
"Curated QA evidence lives under docs/qa/ (§11.4.83)", implying that tree is
meant to be tracked, but the blanket `*.log` pattern silently defeats that for
any `.log`-named evidence file anywhere under `docs/qa/`, including this
entire incident's raw-capture evidence set. This is independently
already-documented (stale label) in `docs/scripts/install-resource-pressure-timer.md:115`
("`docs/qa/BOB-076/*.log` is gitignored despite living under the [curated
evidence directory]") — i.e. Task #77's own doc already flagged the same
gap under the old label. Not fixed here: changing `.gitignore` scope is a
separate, cross-cutting decision outside this task's declared file scope.

## 2. Forward-reference updates (grep before/after, per file)

| File | BOB-076 mentions before | BOB-076 mentions after | All post-edit mentions inside annotation context? |
|---|---|---|---|
| `docs/incidents/2026-08-18-perceived-forced-logout-2nd.md` | 2 (both bare/stale) | 4 | yes — 2 in the new top-of-doc NOTE, 2 inline annotated `(initially referenced as BOB-076 informal label, corrected 2026-08-18)` |
| `docs/QA_DISCOVERY_LEDGER.md` | 4 (all bare/stale) | 4 | yes — `id:` field now reads BOB-116 with an explanatory clause; the other 3 are annotated inline |
| `docs/CONTINUATION.md` | 1 (bare) | 1 | yes — annotated inline, IMPORTANT-1 now keyed to BOB-116 |
| `forced_logout_incidents.md` (memory, outside repo) | 1 (bare) | 2 | yes — one annotated evidence-path line + one new explicit correction line |

Revision headers bumped where present: `docs/CONTINUATION.md` Revision 23→24
(§11.4.44), `Last modified` set to the real command-derived UTC timestamp
(`date -u +%Y-%m-%dT%H:%M:%SZ` = `2026-08-18T21:10:20Z`), never guessed.
`docs/QA_DISCOVERY_LEDGER.md` has no §11.4.44 header (not in that doc's
scope) — left as-is.

## 3. Whole-`docs/` scan (context, not all in this task's scope)

`grep -rln "BOB-076" docs/` before this task's edits returned files this task
does NOT own, all of which carry LEGITIMATE, correct BOB-076 references (the
real, distinct, unrelated Type=Task DB item — RD2-09 jackett fork bump,
commit `99a486e`) or belong to other subagents' historical evidence and are
explicitly out of scope per this task's constraints:

- `docs/Issues.md`, `docs/Issues_Summary.md`, `docs/Fixed.md`,
  `docs/Fixed_Summary.md` (+ their `.html` twins), `docs/features/Status.md`
  — the real BOB-076 tracker entry. **Not touched** (explicit constraint).
- `docs/qa/task-close-bob076/*`, `docs/qa/task-77/*`, `docs/qa/task-44/*`,
  `docs/qa/BOB-072-073/backup/Issues.md.pre-fix`,
  `docs/qa/task-review-457cca4-a7e55f9-nit-fixes/verdict.md`,
  `docs/qa/db-deltas/286192008b35dab7b00c59635ba424ed4b72674b.diff`,
  `docs/qa/task-rebuild-verify/summary.md`,
  `docs/qa/task-stress-chaos-session/6_systemd_timer_stress.txt` — historical
  or concurrently-in-flight evidence belonging to other subagents/tasks.
  **Not touched** (explicit constraint — "do not touch other subagents'
  scopes").
- `docs/scripts/install-resource-pressure-timer.md` (+ `.html`) — 2 residual
  stale BOB-076 mentions (line 6 `task #77 (BOB-076 2nd forced-logout
  incident follow-up)`, line 115 the gitignore-gap note quoted above). **Not
  in this task's declared file scope — left as an honest residual for a
  future, separately-scoped follow-up.**
- `docs/QA_DISCOVERY_LEDGER.html`, `docs/CONTINUATION.html`,
  `docs/incidents/2026-08-18-perceived-forced-logout-2nd.html`, and the
  corresponding `.pdf` exports — stale generated exports of the `.md`
  sources this task DID edit. Regenerating them is a docs-chain (§11.4.106)
  export-pipeline action, not a plain edit, and was not run here to avoid
  colliding with any concurrent export/build activity from other in-flight
  subagents. **Honest gap, not fixed here.**

## 4. Literal acceptance-command result (context)

The task's literal verification command was:

```
grep -rn "BOB-076" docs/ | grep -v "old label\|informal label"
```

Run as specified, this is **not** empty (64 lines) — for two independent,
expected reasons, neither of which represents an un-annotated stray
reference introduced or left by this task:

1. **Legitimate out-of-scope files** (§3 above) genuinely and correctly
   mention the real, distinct BOB-076 tracker item, or belong to other
   subagents' historical evidence this task must not touch.
2. **The mandated NOTE text is multi-line-wrapped**: the exact NOTE block
   this task specifies to paste verbatim wraps the words "informal" and
   "label" across two separate lines (`...as an informal` / `label that
   collided...`), so a single-line `grep -v "informal label"` does not
   suppress those two lines even though they are the mandated, correct
   annotation text, used verbatim as instructed.

Scoped to only the files this task edited, every post-edit `BOB-076`
occurrence sits inside an explicit "informal label" / "initially referenced
as" annotation — verified individually per file in §2 above.
