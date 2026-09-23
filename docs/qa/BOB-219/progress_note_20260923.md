# BOB-219 progress note — 2026-09-23 (PARTIAL — item stays open)

## Acceptance criterion (1) — MET

Both §11.4.65 export twins of the tracked `docs/guides/tracker-credentials.md`
were silently uncommitted (confirmed: `git ls-files` empty for both,
`git check-ignore -v` confirmed `.gitignore:31:*credentials*` as the
blocking rule for both). Added explicit `!` negations for the two exact
paths (matching the codebase's existing per-file allowlist convention).

```
$ git check-ignore -v docs/guides/tracker-credentials.html docs/guides/tracker-credentials.pdf
(empty — confirmed rescued)
```

## Acceptance criterion (2) — CANNOT BE MET (file no longer exists)

`docs/qa/BOB-124/evidence/loginctl_user_state.txt` does not exist on this
checkout (`ls` confirms "No such file or directory") — it was already
silently lost before this session, exactly the outcome the item warns
about. There is nothing to commit; this criterion is honestly unsatisfiable
for the specific lost artifact.

## Acceptance criteria (3)/(4) — attempted, reverted, left open

Tried a blanket `!docs/qa/**` negation to future-proof the whole QA-evidence
directory against any deny pattern (per criterion 4's "this class cannot
recur silently"). CAUGHT IN SELF-REVIEW before shipping: measured directly
in a scratch git tree that this blanket negation ALSO rescues a genuine
`.env`/`*creds*.json` file if one were ever placed under `docs/qa/` — a
real regression risk, not hypothetical (§11.4.201(1): a fix that leaks
credentials to close a false-null is strictly worse than the defect).

Considered narrowing the rescue's re-deny to the SAME word-substring globs
(`*credentials*`, `*_password*`, etc.) scoped to `docs/qa/**` — rejected
too, because this project routinely authors LEGITIMATE QA evidence whose
subject IS credentials/auth (e.g. BOB-198/BOB-203's own
runtime-auth-verification captures), so a substring re-deny risks
reproducing the identical false-null one directory down, on exactly the
evidence this project needs most.

**No safe blanket mechanism was found in the time available.** Reverted
to the precise, already-verified two-file fix (criterion 1) only.
Criteria (3)/(4) need a more careful design (candidate directions:
extension-scoped re-deny limited to genuinely secret-only shapes — `.env`,
`.pem`, `.key`, `.p12`, `.jks`, with NO word-substring re-deny — needs its
own measurement pass to confirm it doesn't leak per BOB-212's own
"extension-scoped narrowing was disproven" finding for the TOP-LEVEL glob,
though the scope here is narrower; or a per-file content-inspection check
rather than a path-pattern one) — filed as its own, more narrowly-scoped
follow-up rather than risking a rushed unsafe fix to force this item's
closure.

## Independently re-verified this session

```
$ bash scripts/pre_build/check_gitignore_swallow.sh "$(pwd)"
BOB-212 swallow-guard: OK — no first-party source files are silently swallowed by .gitignore.

$ bash tests/security/test_gitignore_swallow_is_loud.sh
...
-- GOLDEN-FALSE (§11.4.201(1)/§11.4.10): real secrets MUST stay ignored --
  [ok]     all 15 secret-bearing shapes remain ignored
RESULT: PASS (exit 0)
```
Plus a targeted scratch-tree stress test confirming a hypothetical
`docs/qa/FAKE/.env` and `docs/qa/FAKE/creds.json` both remain correctly
ignored under the shipped `.gitignore`.

## Item status: left Queued (NOT closed) — this is genuine partial progress,
not a completion.
