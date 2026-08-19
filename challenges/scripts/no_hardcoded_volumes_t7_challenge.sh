#!/usr/bin/env bash
# no_hardcoded_volumes_t7_challenge.sh — regression guard for BOB-098 /
# GA-23: HelixQA test banks (submodules/helixqa/banks/*.yaml + *.json)
# MUST NOT hardcode host-mounted path literals of the form `/Volumes/T7`.
# The banks are consumed by any host (the boba maintainer's Fedora + the
# operator's macOS + CI hosts + other consumers per §11.4.28 decoupling +
# §11.4.35 consumer-owned DATA); a hardcoded `/Volumes/T7/...` breaks
# every host that does not mount that literal path, so the correct
# pattern is a `${PROJECT_ROOT}`-class env var (e.g. `${BOBA_PROJECT_ROOT}`,
# `${HELIX_OTA_PROJECT_ROOT}`) with `requires_env: [<VAR>]` per bank.
#
# §11.4.115 RED-first: authored to REPRODUCE the defect against the
# pre-fix banks (grep returned 20 hits per GA-23), then FLIPs to GREEN
# once the banks are parametrized (grep returns 0 hits). Exit 0 = GREEN
# (no hardcoded literal), exit 1 = FAIL (regression).
#
# Runs on the current boba checkout. Consumers with different volume
# literals may extend the pattern list via CHECK_PATTERNS (space-sep)
# in their env — the default guards the operator-reported literal.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
BANKS_DIR="${BANKS_DIR:-$REPO_ROOT/submodules/helixqa/banks}"
CHECK_PATTERNS="${CHECK_PATTERNS:-/Volumes/T7}"

if [ ! -d "$BANKS_DIR" ]; then
  # honest §11.4.3 SKIP-with-reason: submodule not checked out
  echo "SKIP: banks dir absent ($BANKS_DIR) — helixqa submodule not initialised"
  exit 0
fi

fail=0
findings=""
for pattern in $CHECK_PATTERNS; do
  # Grep every bank file (yaml + json); a match is a violation.
  matches=$(grep -rnE "$pattern" "$BANKS_DIR" \
    --include='*.yaml' --include='*.yml' --include='*.json' 2>/dev/null || true)
  if [ -n "$matches" ]; then
    fail=1
    findings+="Pattern \"$pattern\" hits (must be zero):\n$matches\n"
  fi
done

if [ "$fail" -ne 0 ]; then
  printf "FAIL: hardcoded host-path literal(s) found in HelixQA banks (BOB-098 / GA-23):\n%b\n" "$findings" >&2
  printf "\nFix: replace the literal with a \${PROJECT_ROOT}-class env var and\n" >&2
  printf "add \`requires_env: [<VAR>]\` to each affected test case (see other\n" >&2
  printf "banks in %s for the pattern).\n" "$BANKS_DIR" >&2
  exit 1
fi

echo "PASS: no hardcoded host-path literals in $BANKS_DIR (patterns: $CHECK_PATTERNS)"
exit 0
