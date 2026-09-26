# BOB-219 — re-verification of the tracker-credentials export twins

**Revision:** 1
**Last modified:** 2026-09-26T14:55:00Z

## Result

The live violation this item was filed for is resolved on HEAD, and the gate
that guards the class is proven able to see this exact case.

## Evidence (2026-09-26)

Tracking state:

```
$ git ls-files docs/guides/tracker-credentials.*
docs/guides/tracker-credentials.docx
docs/guides/tracker-credentials.html
docs/guides/tracker-credentials.md
docs/guides/tracker-credentials.pdf
$ git check-ignore -v docs/guides/tracker-credentials.{html,pdf,docx}; echo rc=$?
rc=1        # none of the three twins is ignored
```

Gate on the real tree:

```
$ bash scripts/pre_build/check_md_export_twins_committable.sh .
OK: no tracked §11.4.65-scope .md export twin is silently swallowed by .gitignore (466 .md files scanned)
```

Control needle — the same gate on a scratch repository holding the real
`.gitignore` and the four real files, first unchanged, then with the two rescue
lines (`!docs/guides/tracker-credentials.html` / `.pdf`) deleted:

```
--- with real .gitignore:
OK: no tracked §11.4.65-scope .md export twin is silently swallowed by .gitignore (1 .md files scanned)
--- rescue lines removed:
SWALLOWED EXPORT TWIN: docs/guides/tracker-credentials.html
  blocking rule: .gitignore:31:*credentials*
SWALLOWED EXPORT TWIN: docs/guides/tracker-credentials.pdf
  blocking rule: .gitignore:31:*credentials*
FAIL: 2 tracked §11.4.65-scope .md file(s) have an existing export twin silently swallowed by .gitignore (1 .md files scanned)
```

The `.docx` twin is not reported in the second run because it is rescued
separately by `!docs/**/*.docx` (`.gitignore:321`).

Gate self-test: `bash tests/pre_build/test_check_md_export_twins_committable.sh`
→ `RESULT: PASS (exit 0) — all arms behaved as specified`.

## Still open (unchanged)

Criterion 3's residual — a QA-evidence file with a non-`.md` extension swallowed
by a secret-shaped `.gitignore` pattern — is not addressed here. No change was
made to `.gitignore`.
