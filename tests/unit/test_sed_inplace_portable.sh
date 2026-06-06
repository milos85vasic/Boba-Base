#!/usr/bin/env bash
# test_sed_inplace_portable.sh — start.sh must edit files in place portably
# (BSD/macOS sed rejects GNU `sed -i "script"`, which aborted the boot before
# `compose up` — §11.4.67 target-shell + §11.4.81 cross-platform parity).
#
# §11.4.43 RED-first: against pre-fix start.sh there is no sed_inplace helper
# (and the raw `sed -i` calls fail on BSD) → this test FAILs. After the fix
# it GREENs on Linux AND macOS.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
START_SH="${PROJECT_ROOT}/start.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

HOME="${HOME:-/tmp/fakehome}"
# shellcheck disable=SC1090
source "$START_SH" >/dev/null 2>&1 || { fail "source start.sh"; echo "RESULT: $PASS passed, $FAIL failed"; exit 1; }

if ! declare -F sed_inplace >/dev/null; then
    fail "sed_inplace helper not defined in start.sh"
    echo "RESULT: $PASS passed, $FAIL failed"; exit 1
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp" "$tmp".*' EXIT
printf 'WebUI\\Port=1234\nWebUI\\Username=old\nkeep=this\n' > "$tmp"

# Plain substitution (the form that crashed BSD sed).
sed_inplace 's/^keep=.*/keep=changed/' "$tmp"
grep -q '^keep=changed$' "$tmp" && pass "plain substitution applied" || fail "plain substitution"

# -E extended-regex form (used by start.sh line 178).
sed_inplace -E 's|^WebUI\\Username=.*|WebUI\\Username=admin|' "$tmp"
grep -q 'WebUI\\Username=admin' "$tmp" && pass "-E substitution applied" || fail "-E substitution"

# line-delete form (used by start.sh line 165).
before=$(wc -l < "$tmp")
sed_inplace '1d' "$tmp"
after=$(wc -l < "$tmp")
[ "$after" -eq "$((before-1))" ] && pass "line-delete applied" || fail "line-delete (before=$before after=$after)"

# No backup files left behind.
ls "$tmp".* >/dev/null 2>&1 && fail "backup file leaked" || pass "no backup file left"

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
