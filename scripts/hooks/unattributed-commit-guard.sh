#!/usr/bin/env bash
# scripts/hooks/unattributed-commit-guard.sh — §11.4.84 quiescence check for
# the unattributed auto-commit path (BOB-106, §11.4.238 coverage-escape
# followup to docs/QA_DISCOVERY_LEDGER.md RD2-00 / BOB-068).
#
# ─── WHY THIS EXISTS ────────────────────────────────────────────────────
# RD2-00 (docs/GOVERNANCE_AUDIT_2026-08-08_ROUND2.md) found 20+ bare
# "Auto-commit" commits in this repo's history — landing via ordinary git
# pull fast-forward from a second session/host with push access to the
# same remotes, mismatched commit timezone vs the investigating host — with
# no ATM-NNN reference and no TDD trail. §11.4.84 working-tree-quiescence
# had NO mechanical guard on this path: no gate flagged a commit reaching
# main with a bare/templated message and no ticket citation. Measured
# 2026-08-21 (this commit): `git log --oneline --all --grep='^Auto-commit$'`
# still returns 21 such commits — the gap is real and current, not
# historical. BOB-068 (RD2-00) remains the tracking item for identifying/
# stopping the SOURCE; this script is the new automated CHECK.
#
# ─── WHAT IT CHECKS ─────────────────────────────────────────────────────
# Walks a commit range (default: since the most recent tag reachable from
# HEAD, i.e. the "last known-good release" per §11.4.114) and FAILs on any
# commit whose SUBJECT LINE matches a closed bare/templated pattern AND
# whose full message (subject + body) carries NO ATM-NNN-shaped ticket
# reference and NO task/PR reference. Matching is by REGEX STRUCTURE
# anchored to the whole subject line — never a bare substring test
# (§11.4.201(7)(a)) — so "sync: refresh dashboards" fires but "feat: add
# sync endpoint" (which merely CONTAINS "sync") does not.
#
# Closed bare/templated pattern set (extend by adding to BARE_PATTERNS):
#   ^Auto-commit$        — the exact pattern RD2-00 found, 21 instances
#   ^sync:[[:space:]]     — a second templated-auto-sync shape named in
#                           the tracked item's acceptance text
#
# Reference regexes (a commit carrying either is NOT flagged):
#   TICKET_RE  [A-Z][A-Z0-9]*-[0-9]+          e.g. ATM-317, BOB-107
#   TASKPR_RE  (?i)\b(task|pr)[ _#-]*[0-9]+   e.g. "PR #123", "task-45"
#
# ─── §11.4.201(1) NO-FALSE-POSITIVE PROPERTY ───────────────────────────
# A commit whose subject merely CONTAINS "Auto-commit" as a substring of a
# longer, real subject line (e.g. "Auto-commit cache warmed (BOB-1)") does
# NOT match `^Auto-commit$` (anchored, exact) and is never flagged. A bare
# "Auto-commit" commit whose BODY carries a ticket reference is correctly
# recognised as attributed and not flagged either — see --self-test.
#
# ─── USAGE ──────────────────────────────────────────────────────────────
#   bash scripts/hooks/unattributed-commit-guard.sh
#       Scan <last-reachable-tag>..HEAD (real usage; requires a tag).
#   bash scripts/hooks/unattributed-commit-guard.sh --range A..B
#       Scan an explicit rev-range (also what --self-test uses internally).
#   bash scripts/hooks/unattributed-commit-guard.sh --self-test
#       §11.4.107(10) self-validation: golden-good + golden-bad + a
#       false-positive control needle, in a disposable temp git repo. The
#       real working tree and its history are never touched.
#
# ─── EXIT ───────────────────────────────────────────────────────────────
#   0 = OK (range clean, or --self-test passed)
#   1 = VIOLATION — unattributed bare/templated commit(s) found in range
#   2 = invocation error (bad range, no git, no reachable tag and no
#       --range given, self-test setup failure)
#
# ─── WIRING (honest gap, §11.4.6) ───────────────────────────────────────
# This script is NOT yet invoked from scripts/pre_build_verification.sh
# or scripts/commit-push-all.sh (the two entry points the tracked item
# names as candidates) — both are outside this authoring pass's granted
# edit scope. Wiring it into one of those two seams remains OWED as the
# item's closing step; see the BOB-106 tracker entry.
#
# Constitution: §11.4.84 (working-tree quiescence), §11.4.201(1)/(7)(a)
# (structure-not-substring, false-positive-refusal is a bluff),
# §11.4.107(10) (self-validated golden-good/golden-bad), §11.4.115
# (RED-first), §11.4.6 (no-guessing), §11.4.238 (coverage-escape
# followup), §11.4.34 (reason vocabulary), §11.4.54 (ATM-NNN shape).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
    echo "ERROR: not inside a git repository" >&2
    exit 2
fi

BARE_PATTERNS=(
    '^Auto-commit$'
    '^sync:[[:space:]]'
)
TICKET_RE='[A-Z][A-Z0-9]*-[0-9]+'
TASKPR_RE='(TASK|PR)[ _#-]*[0-9]+'

MODE="default"
RANGE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --range) RANGE="$2"; MODE="range"; shift 2 ;;
        --self-test) MODE="selftest"; shift ;;
        -h|--help) sed -n '/─── USAGE/,/─── EXIT/p' "$0"; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

# Returns 0 (flag it) iff the commit's SUBJECT matches one of the closed
# bare/templated patterns AND its full message (subject+body) carries no
# ticket / task / PR reference. $1=subject $2=full-message
_is_unattributed_bare_commit() {
    local subject="$1" full="$2" pat matched=1
    for pat in "${BARE_PATTERNS[@]}"; do
        if [[ "$subject" =~ $pat ]]; then
            matched=0
            break
        fi
    done
    [ "$matched" -eq 0 ] || return 1
    if [[ "$full" =~ $TICKET_RE ]] || [[ "$full" =~ $TASKPR_RE ]]; then
        return 1
    fi
    return 0
}

# Walks $1=rev-range, prints one "<sha> <subject>" line per violating
# commit to stdout, returns the violation count via echo (caller counts
# lines). Uses NUL-delimited records so a multi-line body never confuses
# the loop (§11.4.201(7)(c) — the record delimiter is part of the
# instrument).
_scan_range() {
    local range="$1" out
    out="$(git -C "$REPO_ROOT" log "$range" --format='%H%x1f%s%x1f%B%x1e' 2>/dev/null)" || {
        echo "ERROR: git log failed for range '$range'" >&2
        return 2
    }
    [ -n "$out" ] || return 0
    local rec sha subject full
    while IFS= read -r -d $'\x1e' rec; do
        [ -n "$rec" ] || continue
        sha="${rec%%$'\x1f'*}"
        rec="${rec#*$'\x1f'}"
        subject="${rec%%$'\x1f'*}"
        full="${rec#*$'\x1f'}"
        if _is_unattributed_bare_commit "$subject" "$full"; then
            printf '%s %s\n' "$sha" "$subject"
        fi
    done <<< "$out"
    return 0
}

if [ "$MODE" = "selftest" ]; then
    echo "[unattributed-commit-guard] §11.4.107(10) self-test — golden-good / golden-bad / false-positive control needle"
    TMPREPO="$(mktemp -d)"
    trap 'rm -rf "$TMPREPO"' EXIT
    git -C "$TMPREPO" init -q -b main
    git -C "$TMPREPO" config user.email "selftest@example.invalid"
    git -C "$TMPREPO" config user.name "selftest"

    git -C "$TMPREPO" commit -q --allow-empty -m "root: seed"
    BASE="$(git -C "$TMPREPO" rev-parse HEAD)"

    # golden-good #1: a real, descriptive commit — never matches any
    # bare/templated pattern at all.
    git -C "$TMPREPO" commit -q --allow-empty -m "feat: add sync endpoint (ATM-001)"

    # golden-good #2 (false-positive control needle, §11.4.201(1)): the
    # EXACT bare subject the guard targets, but WITH a ticket reference in
    # the body — proves the guard reads the full message, not only the
    # bare-looking subject, before it flags.
    git -C "$TMPREPO" commit -q --allow-empty -m "Auto-commit" -m "ATM-999: scheduled dashboard regen"

    # golden-good #3: contains the word "sync" but does NOT match the
    # anchored '^sync: ' pattern — proves structure-not-substring
    # (§11.4.201(7)(a)).
    git -C "$TMPREPO" commit -q --allow-empty -m "chore: resync vendor lockfile (BOB-042)"

    # golden-bad #1: the exact RD2-00 shape — bare "Auto-commit", empty
    # body, no reference anywhere.
    git -C "$TMPREPO" commit -q --allow-empty -m "Auto-commit"

    # golden-bad #2: the second closed pattern, unattributed.
    git -C "$TMPREPO" commit -q --allow-empty -m "sync: refresh dashboards"

    HEAD="$(git -C "$TMPREPO" rev-parse HEAD)"
    FAILED=0

    HITS="$(cd "$TMPREPO" && REPO_ROOT="$TMPREPO" _scan_range "${BASE}..${HEAD}" || true)"
    HIT_COUNT="$(printf '%s\n' "$HITS" | grep -c . || true)"

    if [ "$HIT_COUNT" -eq 2 ] && printf '%s\n' "$HITS" | grep -q ' Auto-commit$' && printf '%s\n' "$HITS" | grep -q '^[0-9a-f]* sync: refresh dashboards$'; then
        echo "  golden-bad      PASS  (both unattributed bare commits detected, exactly 2 hits)"
    else
        echo "  golden-bad      FAIL  (expected exactly 2 hits: bare 'Auto-commit' + bare 'sync: ...'; got ${HIT_COUNT})" >&2
        printf '%s\n' "$HITS" | sed 's/^/    got: /' >&2
        FAILED=1
    fi

    if [ "$HIT_COUNT" -eq 2 ]; then
        echo "  golden-good     PASS  (attributed 'Auto-commit' + descriptive + substring-only 'sync' commits NOT flagged)"
    else
        echo "  golden-good     FAIL  (§11.4.201(1) false positive — a correctly-attributed or non-matching commit was flagged)" >&2
        FAILED=1
    fi

    if [ "$FAILED" -eq 1 ]; then
        echo "[unattributed-commit-guard] self-test FAILED" >&2
        exit 1
    fi
    echo "[unattributed-commit-guard] self-test PASS — oracle validated in both polarities"
    exit 0
fi

if [ "$MODE" = "default" ]; then
    TAG="$(git -C "$REPO_ROOT" describe --tags --abbrev=0 HEAD 2>/dev/null || true)"
    if [ -z "$TAG" ]; then
        echo "ERROR: no tag reachable from HEAD — pass --range A..B explicitly" >&2
        exit 2
    fi
    RANGE="${TAG}..HEAD"
    echo "[unattributed-commit-guard] scanning ${RANGE} (last known-good release: ${TAG})"
else
    echo "[unattributed-commit-guard] scanning ${RANGE}"
fi

HITS="$(_scan_range "$RANGE")" || exit 2
HIT_COUNT=0
[ -n "$HITS" ] && HIT_COUNT="$(printf '%s\n' "$HITS" | grep -c .)"

if [ "$HIT_COUNT" -eq 0 ]; then
    echo "[unattributed-commit-guard] OK — no unattributed bare/templated commit in ${RANGE}"
    exit 0
fi

echo "" >&2
echo "  ── UNATTRIBUTED BARE/TEMPLATED COMMIT(S) (§11.4.84) ──" >&2
printf '  %s\n' "$HITS" >&2
echo "" >&2
echo "  ${HIT_COUNT} commit(s) in ${RANGE} match a closed bare/templated" >&2
echo "  pattern with no ATM-NNN or task/PR reference. Per BOB-068 (RD2-00)" >&2
echo "  these land via git pull fast-forward from a second session/host —" >&2
echo "  investigate the source before amending history (§11.4.113: no" >&2
echo "  force-push / no history rewrite; land a documented, attributed" >&2
echo "  follow-up commit instead)." >&2
exit 1
