#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

pass=0
fail=0
check() {
    local desc="$1" cond="$2"
    if eval "$cond"; then printf '  PASS: %s\n' "$desc"; pass=$((pass + 1))
    else printf '  FAIL: %s\n' "$desc"; fail=$((fail + 1)); fi
}

LOGDIR=docs/qa/zero_shortcomings_audit
dir_existed=0; [[ -d "$LOGDIR" ]] && dir_existed=1
list_logs() { find "$LOGDIR" -name '*.log' 2>/dev/null | sort || true; }
before="$(list_logs)" || true
before_count="$(printf '%s' "$before" | grep -c . || true)"

rc=0
bash scripts/zero_shortcomings_audit.sh standing-check >/dev/null 2>&1 || rc=$?
after="$(list_logs)" || true
after_count="$(printf '%s' "$after" | grep -c . || true)"
new_logs="$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep . || true)"

check "standing-check always exits 0 (advisory, never blocks)" '[[ "$rc" -eq 0 ]]'
check "standing-check appends exactly one new run-log file" '[[ "$after_count" -eq $((before_count + 1)) ]]'
check "new run log records mode=standing-check" \
    '[[ -n "$new_logs" ]] && grep -q "mode=standing-check" "$new_logs"'
check "new run log holds no credential-shaped value" \
    '[[ -n "$new_logs" ]] && ! grep -Eq "(password|token|secret)=[^ ]" "$new_logs"'

# cleanup: leave the tree exactly as found
[[ -n "$new_logs" ]] && rm -f -- $new_logs
if [[ "$dir_existed" -eq 0 ]]; then rmdir "$LOGDIR" 2>/dev/null || true; fi

printf 'test_zero_shortcomings_audit_standing_check: %d passed, %d failed\n' "$pass" "$fail"
[[ "$fail" -eq 0 ]]
