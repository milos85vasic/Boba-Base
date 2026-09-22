# BOB-229 closure evidence — 2026-09-23

## Discovery

The very first real-repo run of the new BOB-212 guard
(`scripts/pre_build/check_gitignore_swallow.sh`, wired into
`scripts/pre_build_verification.sh` as invariant 56 this session)
immediately caught a live, real instance of exactly the defect class it was
built to detect:

```
[56/56] CM-GITIGNORE-SWALLOW-GUARD: no first-party source file is silently swallowed by .gitignore (§11.4.201(6), BOB-212)
FAIL [4]: CM-GITIGNORE-SWALLOW-GUARD: exit 1 — a first-party source file is silently swallowed by .gitignore
BOB-212 swallow-guard: REFUSED — 2 first-party source file(s) are silently swallowed by .gitignore.
SWALLOWED (first-party source, silently ignored): scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh
blocked by: .gitignore:31:*credentials*	scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh
SWALLOWED (first-party source, silently ignored): tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
blocked by: .gitignore:31:*credentials*	tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
```

## Independently confirmed real, not a guard false-positive

```
$ ls -la scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
-rwxrwxr-x ... Sep  1 18:26 scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh
-rwxrwxr-x ... Sep  1 18:27 tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh

$ git ls-files scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
(empty — confirmed NOT tracked)

$ git status --short scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
(empty — the exact false-null: a file exists, is functional, and produces zero signal)

$ git check-ignore -v scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
.gitignore:31:*credentials*	scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh
.gitignore:31:*credentials*	tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
```

These two files have been in DAILY FUNCTIONAL USE by
`scripts/pre_build_verification.sh` invariant 53
(`CM-QBITTORRENT-WEBUI-CREDENTIALS`, §11.4.239), which has passed cleanly
every single run this whole session — the gate script runs perfectly fine
FROM DISK regardless of git tracking state, so nothing in the ordinary
development flow ever surfaced that these files had never actually landed
in version control. A fresh clone, a different environment, or an
accidental `git clean` would have silently lost an entire gate
implementation plus its 8-case self-validated paired-mutation meta-test.

## Fix

`.gitignore`: added two explicit `!` negation lines for these exact paths,
matching the codebase's existing hand-maintained per-file allowlist pattern
(lines 34-50) that already carves out other legitimately credential-named
source files (`credentials.go`, the frontend credentials-management UI,
etc.).

## Independently verified this session

```
$ git check-ignore -v scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
.gitignore:47:!scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh	scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh
.gitignore:48:!tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh	tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
(negation now wins — confirmed no longer ignored)

$ git status --short scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
?? scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh
?? tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
(now genuinely visible)

$ bash scripts/pre_build/check_gitignore_swallow.sh "$(pwd)"
BOB-212 swallow-guard: OK — no first-party source files are silently swallowed by .gitignore.

$ bash -n scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh && echo OK
$ bash -n tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh && echo OK
(both clean — the rescued files are syntactically intact)

$ timeout 60 bash tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh
=== paired-mutation meta-test: CM-QBITTORRENT-WEBUI-CREDENTIALS ===
PASS: golden-good (rc=0 as expected)
PASS: golden-bad-1 (rc=1 as expected)
PASS: golden-bad-2 (rc=1 as expected)
PASS: golden-bad-3 (rc=1 as expected)
PASS: golden-bad-4 (rc=1 as expected)
PASS: negative-control-quoted (rc=0 as expected)
PASS: negative-control-carrier (rc=0 as expected)
PASS: negative-control-fresh (rc=0 as expected)
=== META-TEST PASS: gate fires on every broken arm and stays clean on every good arm ===
```
The rescued gate + its meta-test are both fully functional (8/8 self-check
cases pass) — this is a genuine, working, no-longer-at-risk artifact.

## Honest boundary

This item is filed and closed in the same session per this project's own
§11.4.202 reporting-directive discipline (a discovered defect always lands
as a tracked item, even when fixed immediately) — it is not a hypothetical
or a design exercise, it is a real incident the new guard genuinely caught
on its very first real-repo run.

## git diff --stat

```
.gitignore | 7 +++++++
1 file changed, 7 insertions(+)
```
Plus two previously-untracked files now staged for the first time:
`scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh`,
`tests/pre_build/test_check_cm_qbittorrent_webui_credentials.sh`.
