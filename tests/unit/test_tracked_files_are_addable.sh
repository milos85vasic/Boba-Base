#!/usr/bin/env bash
# test_tracked_files_are_addable.sh — every TRACKED file must be `git add`-able.
#
# §11.4.30 (tracked authoritative content is never gitignored) + §11.4.215
# (a doc that BINDS work must live tracked in the repo) + §11.4.234(D)
# (the commit/push mechanism is ALWAYS unblocked).
#
# THE TRAP: when a .gitignore rule matches a path that is ALSO tracked,
# `git add <path>` exits NON-ZERO ("The following paths are ignored by one of
# your .gitignore files"). Under `set -euo pipefail` that kills
# scripts/commit-push-all.sh mid-flight — the file is committed in the repo,
# visibly modified in `git status`, and impossible to commit through the
# mandated entrypoint. Observed live 2026-08-20 on
# .specify/memory/constitution.md; a sweep then found 58 such files across
# five distinct rules (.claude/, .opencode/, .specify/*, config/merge-service/,
# .playwright-mcp/).
#
# §11.4.43 RED-first: against the pre-fix .gitignore this test FAILs listing
# the un-addable tracked files. After the negations it GREENs.
#
# Detection is structural, not a substring scan: `git check-ignore --no-index`
# reports rule-matches against ALL tracked paths in one pass (fast), then each
# candidate is verified through the REAL `git add --dry-run` invocation path
# (§11.4.201(11) — probe the artifact, never a proxy).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
cd "$PROJECT_ROOT"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

# ── Documented exception list (§11.4.224(E)-style exclusion fence) ──────────
# Every entry MUST carry a justification. These are tracked GENERATED
# artifacts (timestamped Playwright MCP page snapshots) that were committed
# at some point and are matched by the `.playwright-mcp/` ignore rule. They
# are NOT un-ignored here because the correct remedy is to stop tracking them
# (§11.4.30 "no versioned build artifacts") — a REMOVAL of tracked content,
# which is an operator decision under §11.4.122 and needs the §11.4.124
# git-history investigation first. Listed here as an HONEST, enumerated gap
# rather than silently passing or silently un-ignoring.
# TODO(PLAYWRIGHT-MCP-ARTIFACTS): operator decision — untrack these 8 files?
is_allowed_exception() {
    case "$1" in
        .playwright-mcp/*) return 0 ;;
        *) return 1 ;;
    esac
}

# ── Collect tracked paths that gitignore rules match (fast single pass) ─────
CANDIDATES="$(git ls-files -z | xargs -0 git check-ignore --no-index 2>/dev/null || true)"

UNADDABLE=()
EXCEPTED=0
if [ -n "$CANDIDATES" ]; then
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        # Verify through the REAL invocation path — a rule-match alone does
        # not prove `git add` fails.
        if git add --dry-run -- "$f" >/dev/null 2>&1; then
            continue
        fi
        if is_allowed_exception "$f"; then
            EXCEPTED=$((EXCEPTED+1))
            continue
        fi
        UNADDABLE+=("$f")
    done <<<"$CANDIDATES"
fi

if [ "${#UNADDABLE[@]}" -eq 0 ]; then
    pass "every tracked file is git add-able (${EXCEPTED} documented exception(s) skipped)"
else
    fail "${#UNADDABLE[@]} TRACKED file(s) are rejected by 'git add' — the §11.4.234 commit mechanism is broken for them"
    for f in "${UNADDABLE[@]}"; do
        rule="$(git check-ignore -v --no-index "$f" 2>/dev/null | awk '{print $1}')"
        echo "       - $f    (rule: ${rule:-unknown})" >&2
    done
    echo "       Remediation: add a '!' negation in .gitignore for the tracked path." >&2
    echo "       NOTE: git cannot re-include a file whose PARENT DIR is excluded —" >&2
    echo "       change 'dir/' to 'dir/*' first, then negate the specific path." >&2
fi

# ── Guard the guard (§11.4.201(1)): the detector must actually be able to see.
# A control needle: a path we KNOW is ignored and NOT tracked must be reported
# as ignored by check-ignore, proving the instrument is not blind.
NEEDLE=".playwright-mcp/__control_needle_not_tracked__.yml"
if git check-ignore --no-index "$NEEDLE" >/dev/null 2>&1; then
    pass "control needle: check-ignore instrument is seeing (not blind)"
else
    fail "control needle FAILED — check-ignore reports nothing for a known-ignored path; the scan above proves nothing"
fi

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
