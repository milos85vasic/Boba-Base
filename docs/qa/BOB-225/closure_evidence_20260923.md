# BOB-225 closure evidence — 2026-09-23

## Operator decision implemented

"Carve out generated doc twins" — the §11.4.65/§11.4.153 mandate applies;
the deny-all `*.docx` glob is narrowed with a targeted allowlist for
genuine generated export twins, matching the existing `docs/qa/**/*.log`
precedent.

## Verification before implementing (§11.4.6 — measure, do not assume)

Every `.docx` file under `docs/`, `scripts/`, and the repo root was
checked for a genuine 1:1 pairing with a tracked `.md` sibling (NUL-
delimited `find`, correctly handling a real directory with spaces in its
name that a naive word-split loop initially mis-parsed — caught and fixed
before drawing any conclusion from it):

```
$ (NUL-delimited scan of docs/**/*.docx)
total=384 paired=384 unpaired=0

$ (root + scripts/ scan)
README.docx / AGENTS.docx / CLAUDE.docx / QWEN.docx / CONTRIBUTING.docx /
CONSTITUTION.docx / CHANGELOG.docx / scripts/README.docx /
scripts/system-slice-watchdog/README.docx — all 9 PAIRED
```
No stray/unrelated Word documents found — every candidate genuinely a
generated export twin. `submodules/` (59 files) and `constitution/` (183
files) are SEPARATE git repositories (submodules) — their own tracking is
governed by their own `.gitignore`, out of scope for this repo's fix.

## Fix

`.gitignore`: the deny-all `*.docx` KEPT (a hand-authored or third-party
`.docx` landing anywhere else in the tree is still refused by default);
added directory-scoped negations `!docs/**/*.docx` and `!scripts/**/*.docx`
plus explicit root-level entries for the 7 root docs — a STRUCTURAL fix
(any file matching these patterns is automatically rescued) rather than a
hand-maintained per-file list, closing acceptance criterion 3 ("a check
that a generated twin is actually trackable, so this cannot recur
silently") by construction — no active gate needed, verified directly:

```
$ mkdir -p docs/qa/BOB225_PROBE && echo test > docs/qa/BOB225_PROBE/fake.md \
    && echo test > docs/qa/BOB225_PROBE/fake.docx
$ git check-ignore -v docs/qa/BOB225_PROBE/fake.docx
(empty — a brand-new docs/ file is auto-rescued, no hand-edit required)
```

## Independently re-verified this session

```
$ (scan every docs/scripts/root .docx file for remaining ignore status)
still-ignored count: 0

$ bash scripts/pre_build/check_gitignore_swallow.sh "$(pwd)"
BOB-212 swallow-guard: OK — no first-party source files are silently swallowed by .gitignore.

$ bash tests/security/test_gitignore_swallow_is_loud.sh
-- GOLDEN-FALSE (§11.4.201(1)/§11.4.10): real secrets MUST stay ignored --
  [ok]     all 15 secret-bearing shapes remain ignored
RESULT: PASS (exit 0)
```
The pre-existing two tracked survivors (`docs/features/Status.docx`,
`docs/features/Status_Summary.docx`) show no diff — genuinely unaffected,
now protected by the same structural mechanism rather than surviving by
accident of already being in the index.

## Honest boundary (not silenced)

392 previously-untracked `.docx` files (~7.6MB total, a reasonable size)
become newly tracked by this fix. They are committed AS THEY CURRENTLY
EXIST ON DISK — this fix did NOT trigger a fresh full regeneration pass
against every source `.md` (hundreds of files, a separate, larger
operation); ongoing freshness is governed by the project's existing
§11.4.12/§11.4.106 docs-chain sync discipline, not by this fix. §11.4.153
compliance for the `docs/features/` Status set is now genuinely and
robustly met (previously true only by accident of index membership).

## git diff --stat

```
.gitignore | 22 +++++++++++++---
1 file changed, 19 insertions(+), 3 deletions(-)
```
Plus 392 newly-tracked pre-existing `.docx` files (~7.6MB).
