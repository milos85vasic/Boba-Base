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

cd - >/dev/null

# Review finding 2 (Important): a FAILING recorded command must not abort
# verify-closure before the guard's detect step runs.
mkdir -p tests/audit/fixtures/docs_qa_fixture/BOB-FIXTURE-CMD-FAILS
fail_out="$(AUDIT_QA_ROOT=tests/audit/fixtures/docs_qa_fixture bash scripts/zero_shortcomings_audit.sh verify-closure BOB-FIXTURE-CMD-FAILS 2>&1)" || true
check "a failing recorded command still reaches the comparison (guard not skipped)" \
    'printf "%s" "$fail_out" | grep -q "MISMATCH"'

printf 'test_zero_shortcomings_audit_corruption_guard: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
