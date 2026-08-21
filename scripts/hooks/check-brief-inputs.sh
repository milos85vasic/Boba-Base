#!/usr/bin/env bash
# scripts/hooks/check-brief-inputs.sh — pre-dispatch existence check for
# subagent task-brief source inputs (BOB-107, §11.4.238 coverage-escape
# followup to docs/QA_DISCOVERY_LEDGER.md SCRATCH-LOSS-2026-08-18).
#
# ─── WHY THIS EXISTS ────────────────────────────────────────────────────
# The Phase 1a subagent (a1cc331d, evidence: the historical
# .superpowers/sdd/task-phase1a-report.md line 21 "Concerns" section)
# discovered AT TASK START that 5 source files its brief named as required
# reads were absent from the session scratchpad — root cause: the prior
# producer subagent (ae59171f) hit its session rate limit (a §11.4.147(e)
# API-quota crash) before writing them. No mechanical check verified a
# task brief's declared input files existed BEFORE the downstream
# consumer subagent was dispatched, so the consumer proceeded on absent
# evidence rather than failing closed and asking for a respawn.
#
# ─── WHAT IT CHECKS ─────────────────────────────────────────────────────
# Given a list of "required input" paths — either named explicitly via
# repeated --file, or extracted from a task-brief Markdown file's
# "## Source materials" / "## Required reads" / "## Required inputs"
# section via --brief — checks each path EXISTS and is NON-EMPTY (size
# > 0 bytes; an existing-but-empty file is exactly as unusable as an
# absent one for a subagent that must read real content). Any missing or
# empty input FAILS CLOSED (exit 1) with a report naming every offending
# path and the literal remediation action: "respawn the producer".
#
# ─── BRIEF-EXTRACTION CONVENTION (§11.4.6 — closed, documented scope) ───
# Within the located section, every Markdown inline-code span
# (`` `...` ``) that contains at least one "/" and no whitespace is a
# path candidate. This repo's SDD briefs use a documentation shorthand
# where later list items elide a shared prefix already shown in full —
# e.g. item 1 gives the full absolute path ending ".../<session>/
# scratchpad/plan.md" and item 2 abbreviates the same directory as
# `.../scratchpad/other.md`. A candidate starting with "..." is resolved
# against the two-levels-up directory of the MOST RECENTLY SEEN absolute
# (leading "/") candidate in the SAME section — i.e. `.../scratchpad/X`
# resolves to "<dirname of dirname of last /abs/.../scratchpad/Y>
# /scratchpad/X". A "..." candidate with no preceding absolute candidate
# in the section cannot be resolved and is reported as such (never
# silently skipped — §11.4.201(6) false-null).
#
# ─── USAGE ──────────────────────────────────────────────────────────────
#   bash scripts/hooks/check-brief-inputs.sh --file A [--file B ...]
#       Explicit ad hoc required-input list.
#   bash scripts/hooks/check-brief-inputs.sh --brief PATH/TO/brief.md
#       Extract required inputs from the brief's Source-materials-shaped
#       section and check them. A brief with no such section is honestly
#       reported as "nothing declared" and exits 0 (vacuous truth, never
#       a silent skip of a section that IS present).
#   bash scripts/hooks/check-brief-inputs.sh --self-test
#       §11.4.107(10) self-validation: golden-good (all present) +
#       golden-bad (a missing + an empty input, both named) + a
#       false-positive control needle (a present zero-byte file is
#       correctly flagged as empty, not silently accepted) — entirely
#       inside a disposable temp dir.
#
# ─── EXIT ───────────────────────────────────────────────────────────────
#   0 = OK — every declared/explicit required input exists and is non-empty
#           (or nothing was declared)
#   1 = MISSING/EMPTY — fail closed; per-path report + "respawn the
#           producer" remediation on stderr
#   2 = invocation error (no --file/--brief/--self-test given, brief file
#           itself does not exist, unresolvable "..." shorthand)
#
# ─── WIRING (honest gap, §11.4.6) ───────────────────────────────────────
# This is project-side orchestration tooling per the tracked item's own
# text — a script the conductor runs BEFORE Task/Agent dispatch, not (yet)
# an automatic PreToolUse hook: a brief's required-input list lives in
# free-form prose the Task/Agent tool_input does not structurally expose,
# so automatic enforcement would need either a stricter brief-authoring
# convention or heuristic prompt-scraping — the latter is exactly the
# kind of unproven pattern-match §11.4.226 forbids treating as a
# behavioural oracle. Manual/scripted conductor invocation is the honest,
# non-bluffing interface this pass ships; promoting it to an automatic
# PreToolUse hook remains OWED as a tracked follow-up.
#
# Constitution: §11.4.147(e) (API-quota crash is a first-class crash
# class), §11.4.201(1)/(6) (false-positive refusal forbidden / a null is
# not evidence until proven), §11.4.107(10) (self-validated analyzer),
# §11.4.6 (no-guessing, closed documented scope), §11.4.238 (coverage-
# escape followup), §11.4.101 (fail-closed conservative default).

set -euo pipefail

MODE=""
EXPLICIT_FILES=()
BRIEF=""
while [ $# -gt 0 ]; do
    case "$1" in
        --file) EXPLICIT_FILES+=("$2"); MODE="explicit"; shift 2 ;;
        --brief) BRIEF="$2"; MODE="brief"; shift 2 ;;
        --self-test) MODE="selftest"; shift ;;
        -h|--help) sed -n '/─── USAGE/,/─── EXIT/p' "$0"; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$MODE" ]; then
    echo "ERROR: pass --file PATH (repeatable), --brief PATH, or --self-test" >&2
    exit 2
fi

# Returns 0 iff $1 is a required-input candidate span (contains "/" and no
# whitespace) rather than an unrelated inline-code snippet (a shell
# command, a §-number, an anchor name).
_looks_like_path_candidate() {
    local s="$1"
    [[ "$s" == *"/"* ]] || return 1
    [[ "$s" != *[[:space:]]* ]] || return 1
    return 0
}

# Resolves a "..." -shorthand candidate against $2=last-seen-absolute.
# Prints the resolved path on stdout; prints nothing + returns 1 if
# unresolvable (no prior absolute candidate).
_resolve_ellipsis() {
    local candidate="$1" last_abs="$2" tail grandparent
    if [ -z "$last_abs" ]; then
        return 1
    fi
    tail="${candidate#...}"
    tail="${tail#/}"
    grandparent="$(dirname "$(dirname "$last_abs")")"
    printf '%s/%s' "$grandparent" "$tail"
    return 0
}

# Extracts required-input path candidates from a brief file's
# Source-materials-shaped section onto stdout, one per line, "..."
# shorthand already resolved. $1=brief path
_extract_brief_inputs() {
    local brief="$1" section last_abs="" span resolved
    section="$(awk '
        BEGIN{insec=0}
        /^##+[[:space:]]+([Ss]ource [Mm]aterials|[Rr]equired [Rr]eads?|[Rr]equired [Ii]nputs?)/ { insec=1; next }
        insec && /^##+[[:space:]]/ { insec=0 }
        insec { print }
    ' "$brief")"
    [ -n "$section" ] || return 0
    while IFS= read -r span; do
        [ -n "$span" ] || continue
        if _looks_like_path_candidate "$span"; then
            if [[ "$span" == "..."* ]]; then
                if resolved="$(_resolve_ellipsis "$span" "$last_abs")"; then
                    printf '%s\n' "$resolved"
                else
                    printf 'UNRESOLVABLE:%s\n' "$span"
                fi
            else
                printf '%s\n' "$span"
                [[ "$span" == /* ]] && last_abs="$span"
            fi
        fi
    done < <(printf '%s\n' "$section" | grep -oE '`[^`]+`' | sed -e 's/^`//' -e 's/`$//')
}

# Checks one required-input path. Prints a report line and returns
# 0=present-and-non-empty, 1=missing-or-empty, 2=unresolvable.
_check_one() {
    local p="$1"
    if [[ "$p" == UNRESOLVABLE:* ]]; then
        echo "  UNRESOLVABLE  ${p#UNRESOLVABLE:}  (no preceding absolute path in this section to resolve '...' against)"
        return 2
    fi
    if [ ! -e "$p" ]; then
        echo "  MISSING       $p"
        return 1
    fi
    if [ ! -s "$p" ]; then
        echo "  EMPTY         $p  (exists, 0 bytes — as unusable as absent)"
        return 1
    fi
    echo "  present       $p"
    return 0
}

if [ "$MODE" = "selftest" ]; then
    echo "[check-brief-inputs] §11.4.107(10) self-test — golden-good / golden-bad / empty-file control needle"
    TMPD="$(mktemp -d)"
    trap 'rm -rf "$TMPD"' EXIT

    # golden-good: two real, non-empty inputs.
    echo "content-a" > "$TMPD/a.md"
    echo "content-b" > "$TMPD/b.md"
    GOOD_OUT="$(bash "$0" --file "$TMPD/a.md" --file "$TMPD/b.md" 2>&1)"
    GOOD_EXIT=0
    bash "$0" --file "$TMPD/a.md" --file "$TMPD/b.md" >/dev/null 2>&1 || GOOD_EXIT=$?
    FAILED=0
    if [ "$GOOD_EXIT" -eq 0 ]; then
        echo "  golden-good     PASS  (two present non-empty inputs -> exit 0)"
    else
        echo "  golden-good     FAIL  (present non-empty inputs -> exit ${GOOD_EXIT}, expected 0): ${GOOD_OUT}" >&2
        FAILED=1
    fi

    # golden-bad: one present-non-empty, one missing, one present-but-empty.
    : > "$TMPD/empty.md"
    BAD_EXIT=0
    BAD_OUT="$(bash "$0" --file "$TMPD/a.md" --file "$TMPD/does-not-exist.md" --file "$TMPD/empty.md" 2>&1)" || BAD_EXIT=$?
    if [ "$BAD_EXIT" -eq 1 ] \
        && echo "$BAD_OUT" | grep -q "MISSING       ${TMPD}/does-not-exist.md" \
        && echo "$BAD_OUT" | grep -q "EMPTY         ${TMPD}/empty.md" \
        && echo "$BAD_OUT" | grep -qi "respawn the producer"; then
        echo "  golden-bad      PASS  (missing input AND empty input both named; exit 1; remediation printed)"
    else
        echo "  golden-bad      FAIL  (expected exit 1 naming both the missing and the empty path); got exit ${BAD_EXIT}" >&2
        echo "$BAD_OUT" | sed 's/^/    got: /' >&2
        FAILED=1
    fi

    # --brief extraction, including the "..." shorthand resolution
    # (§11.4.201(1) — proves the resolver, not just the presence check).
    SESSDIR="$TMPD/4db6eadb-fake-session/scratchpad"
    mkdir -p "$SESSDIR"
    echo "plan content" > "$SESSDIR/plan.md"
    echo "extracted content" > "$SESSDIR/extracted.md"
    cat > "$TMPD/brief.md" << BRIEF_FIXTURE
# Fake brief

## Source materials

1. **Plan (master):** \`${SESSDIR}/plan.md\` — the plan
2. **Extraction:** \`.../scratchpad/extracted.md\` — the extraction
3. **Missing sibling:** \`.../scratchpad/missing.md\` — never written

## Next section (must not be scanned)

\`${TMPD}/should-not-be-checked.md\`
BRIEF_FIXTURE
    BRIEF_EXIT=0
    BRIEF_OUT="$(bash "$0" --brief "$TMPD/brief.md" 2>&1)" || BRIEF_EXIT=$?
    if [ "$BRIEF_EXIT" -eq 1 ] \
        && echo "$BRIEF_OUT" | grep -q "present       ${SESSDIR}/plan.md" \
        && echo "$BRIEF_OUT" | grep -q "present       ${SESSDIR}/extracted.md" \
        && echo "$BRIEF_OUT" | grep -q "MISSING       ${SESSDIR}/missing.md" \
        && ! echo "$BRIEF_OUT" | grep -q "should-not-be-checked"; then
        echo "  brief-extract   PASS  ('...' shorthand resolved correctly; out-of-section path NOT scanned; missing sibling detected)"
    else
        echo "  brief-extract   FAIL  (extraction/resolution/section-scoping defect)" >&2
        echo "$BRIEF_OUT" | sed 's/^/    got: /' >&2
        FAILED=1
    fi

    if [ "$FAILED" -eq 1 ]; then
        echo "[check-brief-inputs] self-test FAILED" >&2
        exit 1
    fi
    echo "[check-brief-inputs] self-test PASS — oracle validated in both polarities"
    exit 0
fi

if [ "$MODE" = "explicit" ]; then
    PATHS=("${EXPLICIT_FILES[@]}")
elif [ "$MODE" = "brief" ]; then
    if [ ! -f "$BRIEF" ]; then
        echo "ERROR: brief file not found: $BRIEF" >&2
        exit 2
    fi
    mapfile -t PATHS < <(_extract_brief_inputs "$BRIEF")
    if [ "${#PATHS[@]}" -eq 0 ]; then
        echo "[check-brief-inputs] no Source-materials-shaped section (or it names no path candidates) in $BRIEF — nothing declared, OK"
        exit 0
    fi
    echo "[check-brief-inputs] ${#PATHS[@]} required-input candidate(s) extracted from $BRIEF"
fi

BAD_COUNT=0
for p in "${PATHS[@]}"; do
    _check_one "$p" || BAD_COUNT=$((BAD_COUNT + 1))
done

if [ "$BAD_COUNT" -eq 0 ]; then
    echo "[check-brief-inputs] OK — all ${#PATHS[@]} required input(s) present and non-empty"
    exit 0
fi

echo "" >&2
echo "  ── ${BAD_COUNT} REQUIRED INPUT(S) MISSING, EMPTY, OR UNRESOLVABLE ──" >&2
echo "  Do NOT dispatch the downstream consumer subagent on absent evidence." >&2
echo "  Respawn the producer that was supposed to write the file(s) above," >&2
echo "  confirm they land non-empty, THEN dispatch the consumer." >&2
exit 1
