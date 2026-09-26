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

cd - >/dev/null
printf 'test_zero_shortcomings_audit_corruption_guard: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
