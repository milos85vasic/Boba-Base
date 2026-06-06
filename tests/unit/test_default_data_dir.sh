#!/usr/bin/env bash
# test_default_data_dir.sh — Hermetic test for start.sh platform-aware
# data-directory default (§11.4.81 cross-platform parity, CONTINUATION #3).
#
# §11.4.43 RED-first: against pre-fix start.sh there is no default_data_dir
# function (and `main "$@"` runs on source), so sourcing fails / the
# function is undefined → this test FAILs. After the fix it GREENs.
#
# §1.1 paired mutation: force default_data_dir to always echo /mnt/DATA →
# the Darwin assertion FAILs → restore.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
START_SH="${PROJECT_ROOT}/start.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

# Sourcing must NOT execute main (requires the BASH_SOURCE guard).
HOME="${HOME:-/tmp/fakehome}"
# shellcheck disable=SC1090
if ! source "$START_SH" 2>/dev/null; then
    fail "sourcing start.sh failed (missing BASH_SOURCE guard around main?)"
    echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
    exit 1
fi

if ! declare -F default_data_dir >/dev/null; then
    fail "default_data_dir function is not defined in start.sh"
    echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
    exit 1
fi

# macOS branch must NOT be /mnt/DATA (the bug) and must be HOME-relative.
darwin_default="$(default_data_dir Darwin)"
if [[ "$darwin_default" == "$HOME/qbit-data" ]]; then
    pass "Darwin default is \$HOME/qbit-data ($darwin_default)"
else
    fail "Darwin default expected \$HOME/qbit-data, got '$darwin_default'"
fi
[[ "$darwin_default" != "/mnt/DATA" ]] \
    && pass "Darwin default is not /mnt/DATA" \
    || fail "Darwin default is still the broken /mnt/DATA"

# Linux branch preserves existing behavior.
linux_default="$(default_data_dir Linux)"
[[ "$linux_default" == "/mnt/DATA" ]] \
    && pass "Linux default preserved (/mnt/DATA)" \
    || fail "Linux default changed unexpectedly: '$linux_default'"

# No-arg call resolves against the running host without error.
host_default="$(default_data_dir)"
[[ -n "$host_default" ]] \
    && pass "host default resolves non-empty ($host_default)" \
    || fail "host default empty"

echo "RESULT: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
[[ "$FAIL_COUNT" -eq 0 ]]
