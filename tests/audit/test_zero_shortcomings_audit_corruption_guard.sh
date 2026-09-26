#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/zero_shortcomings_audit.sh 2>/dev/null || true  # sourced for its functions only

pass=0
fail=0

check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then
        printf '  PASS: %s\n' "$desc"
        pass=$((pass + 1))
    else
        printf '  FAIL: %s\n' "$desc"
        fail=$((fail + 1))
    fi
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
git init -q .
mkdir -p docs/qa/BOB-OTHER-ITEM docs/qa/BOB-THIS-ITEM
echo "original evidence" > docs/qa/BOB-OTHER-ITEM/closure_evidence.md
git add -A && git commit -q -m "seed"

snapshot="$(audit_snapshot_tracked_evidence)"

# Simulate the exact BOB-109 class: a command that, as a side effect,
# overwrites a DIFFERENT item's evidence file.
echo "corrupted by an unrelated command" > docs/qa/BOB-OTHER-ITEM/closure_evidence.md
# And a legitimate write inside THIS item's own evidence dir, which must NOT
# be reverted (Review Focus item 2 — the guard must not be over-broad).
echo "new evidence for the item under test" > docs/qa/BOB-THIS-ITEM/new_file.md

incidents="$(audit_detect_and_revert_corruption "$snapshot" "docs/qa/BOB-THIS-ITEM")"

check "the guard detects exactly one corrupted file outside the item's own dir" \
    '[[ "$(printf "%s\n" "$incidents" | grep -c .)" -eq 1 ]]'
check "the corrupted file was reverted to its committed content" \
    '[[ "$(cat docs/qa/BOB-OTHER-ITEM/closure_evidence.md)" == "original evidence" ]]'
check "the legitimate new file inside the item's own dir was left alone" \
    '[[ -f docs/qa/BOB-THIS-ITEM/new_file.md ]]'

# Review finding 1 (Critical): a file that was ALREADY dirty (uncommitted
# legitimate work) before the command ran must be restored to its PRE-COMMAND
# bytes, never to HEAD, or the operator's uncommitted work is destroyed.
echo "UNCOMMITTED LEGIT WORK" > docs/qa/BOB-OTHER-ITEM/closure_evidence.md
backup="$(mktemp -d)"
snapshot2="$(audit_snapshot_tracked_evidence "$backup")"
echo "CORRUPT" > docs/qa/BOB-OTHER-ITEM/closure_evidence.md
audit_detect_and_revert_corruption "$snapshot2" "docs/qa/BOB-THIS-ITEM" "$backup" >/dev/null
check "a pre-dirty file is restored to its pre-command content, not HEAD" \
    '[[ "$(cat docs/qa/BOB-OTHER-ITEM/closure_evidence.md)" == "UNCOMMITTED LEGIT WORK" ]]'
rm -rf "$backup"

# I-2(a): a command that DELETES another item's tracked evidence file must be
# detected and the file restored (previously `[[ -f ]] || continue` skipped it).
git checkout -q -- .
backup="$(mktemp -d)"
snap_del="$(audit_snapshot_tracked_evidence "$backup")"
rm docs/qa/BOB-OTHER-ITEM/closure_evidence.md
del_incidents="$(audit_detect_and_revert_corruption "$snap_del" "docs/qa/BOB-THIS-ITEM" "$backup")"
check "I-2(a): a deleted tracked file outside the own dir is restored" \
    '[[ -f docs/qa/BOB-OTHER-ITEM/closure_evidence.md && "$(cat docs/qa/BOB-OTHER-ITEM/closure_evidence.md)" == "original evidence" ]]'
check "I-2(a): the deletion is reported as an incident" \
    'printf "%s\n" "$del_incidents" | grep -qx "docs/qa/BOB-OTHER-ITEM/closure_evidence.md"'
rm -rf "$backup"

# I-2(a'): a PRE-DIRTY file that is then deleted is restored to its
# pre-command bytes (never to HEAD).
echo "DIRTY THEN DELETED" > docs/qa/BOB-OTHER-ITEM/closure_evidence.md
backup="$(mktemp -d)"
snap_dd="$(audit_snapshot_tracked_evidence "$backup")"
rm docs/qa/BOB-OTHER-ITEM/closure_evidence.md
audit_detect_and_revert_corruption "$snap_dd" "docs/qa/BOB-THIS-ITEM" "$backup" >/dev/null
check "I-2(a'): a pre-dirty file deleted by the command is restored to its pre-command bytes" \
    '[[ "$(cat docs/qa/BOB-OTHER-ITEM/closure_evidence.md 2>/dev/null)" == "DIRTY THEN DELETED" ]]'
rm -rf "$backup"
git checkout -q -- .

# I-2(b): paths containing spaces must not defeat the snapshot format.
mkdir -p "docs/qa/BOB SPACE ITEM"
echo "space original" > "docs/qa/BOB SPACE ITEM/closure evidence.md"
git add -A && git commit -q -m "space path"
backup="$(mktemp -d)"
snap_sp="$(audit_snapshot_tracked_evidence "$backup")"
echo "space corrupted" > "docs/qa/BOB SPACE ITEM/closure evidence.md"
sp_incidents="$(audit_detect_and_revert_corruption "$snap_sp" "docs/qa/BOB-THIS-ITEM" "$backup")"
check "I-2(b): a modified file whose path has spaces is restored" \
    '[[ "$(cat "docs/qa/BOB SPACE ITEM/closure evidence.md")" == "space original" ]]'
check "I-2(b): the space-path incident is reported with its full path" \
    'printf "%s\n" "$sp_incidents" | grep -qxF "docs/qa/BOB SPACE ITEM/closure evidence.md"'
rm -rf "$backup"

# I-2(b'): a pre-dirty space-path file is restored to its pre-command bytes.
echo "space dirty legit" > "docs/qa/BOB SPACE ITEM/closure evidence.md"
backup="$(mktemp -d)"
snap_sp2="$(audit_snapshot_tracked_evidence "$backup")"
rm "docs/qa/BOB SPACE ITEM/closure evidence.md"
audit_detect_and_revert_corruption "$snap_sp2" "docs/qa/BOB-THIS-ITEM" "$backup" >/dev/null
check "I-2(b'): a pre-dirty space-path file deleted by the command is restored to pre-command bytes" \
    '[[ "$(cat "docs/qa/BOB SPACE ITEM/closure evidence.md" 2>/dev/null)" == "space dirty legit" ]]'
rm -rf "$backup"
git checkout -q -- .

# Own-dir writes (modify AND delete) stay untouched, and an unchanged tree
# yields zero incidents (the false-positive guard, §11.4.201(1)).
echo "own tracked" > docs/qa/BOB-THIS-ITEM/tracked.md
git add -A && git commit -q -m "own tracked"
snap_own="$(audit_snapshot_tracked_evidence)"
rm docs/qa/BOB-THIS-ITEM/tracked.md
own_incidents="$(audit_detect_and_revert_corruption "$snap_own" "docs/qa/BOB-THIS-ITEM")"
check "a deletion INSIDE the item's own dir is left alone (not restored)" \
    '[[ ! -e docs/qa/BOB-THIS-ITEM/tracked.md && -z "$own_incidents" ]]'
git checkout -q -- .
snap_clean="$(audit_snapshot_tracked_evidence)"
clean_incidents="$(audit_detect_and_revert_corruption "$snap_clean" "docs/qa/BOB-THIS-ITEM")"
check "an unchanged tree reports zero incidents" '[[ -z "$clean_incidents" ]]'

cd - >/dev/null

# Review finding 2 (Important): a FAILING recorded command must not abort
# verify-closure before the guard's detect step runs.
mkdir -p tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-CMD-FAILS
fail_out="$(AUDIT_QA_ROOT=tests/audit/fixtures/docs_qa_fixture bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-CMD-FAILS 2>&1)" || true
check "a failing recorded command still reaches the comparison (guard not skipped)" \
    'printf "%s" "$fail_out" | grep -q "MISMATCH"'

printf 'test_zero_shortcomings_audit_corruption_guard: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
