#!/usr/bin/env bash
# scripts/compute-badges.sh — §11.4.259 machine-derived badge regenerator (BOB-118)
#
# Purpose: replace hand-typed / stale shields.io badge numbers in README.md
#   with counts computed from REAL, freshly-run invocations of the tools
#   that produce them (pytest --collect-only, vitest list --run, a real
#   `ls` of challenges/scripts/, and a grep of the pre-build gate's own
#   highest "[N/N]" progress label) — never a hand-typed or assumed number.
#
# Usage:
#   scripts/compute-badges.sh                 # compute + rewrite README.md
#                                              # + docs/TESTING.md in place
#   scripts/compute-badges.sh --check          # compute only, print a diff
#                                              # summary, write nothing.
#                                              # exit 0 = in sync,
#                                              # exit 2 = stale (advisory —
#                                              # callers must NOT treat this
#                                              # as fatal per §11.4.234).
#   scripts/compute-badges.sh --check --readme <path> --testing-md <path>
#                                              # override the target files
#                                              # (used by the paired §1.1
#                                              # golden-good/golden-bad test).
#
# Inputs: tests/ (python suite), frontend/ (vitest suite),
#   challenges/scripts/*.sh, scripts/pre_build_verification.sh.
# Outputs: README.md badge row + Contributing-section bullets (default mode
#   only), docs/TESTING.md "Test counts" section (default mode only).
# Side-effects: none in --check mode. Rewrites README.md + docs/TESTING.md
#   in default mode (git-tracked files — review the diff before commit).
# Dependencies: python (repo .venv preferred, falls back like ci.sh),
#   node/vitest (frontend/node_modules — falls back to an honestly-labelled
#   grep proxy if node_modules is absent), bash 4+, sed, grep, awk.
# Cross-references: docs/scripts/compute-badges.md (§11.4.18 companion),
#   docs/TESTING.md (the corroborating authoritative source this script
#   keeps honest), CLAUDE.md §11.4.259 (README badge machine-derivation
#   mandate), BOB-118 (the bug this script fixes).
#
# Anti-bluff (§11.4.6): every number below is read from the STDOUT of a
# real command executed in THIS invocation. If a count genuinely cannot be
# computed (tool absent, command errored), the badge is emitted as a GRAY
# "N/A (reason)" — never a fabricated or carried-forward number.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

README="${ROOT_DIR}/README.md"
TESTING_MD="${ROOT_DIR}/docs/TESTING.md"
MODE="apply"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) MODE="check"; shift ;;
        --readme) README="$2"; shift 2 ;;
        --testing-md) TESTING_MD="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,33p' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *) echo "compute-badges.sh: unknown argument: $1" >&2; exit 64 ;;
    esac
done

# ---------------------------------------------------------------------------
# §11.4.6 no-guessing: resolve a real python interpreter the same way
# ci.sh does (prefer the project venv, then a versioned python3.1x, then a
# bare python3) — never assume a bare `python3` on PATH is the right one.
# ---------------------------------------------------------------------------
resolve_python() {
    local candidate
    for candidate in "${PYTHON:-}" "${ROOT_DIR}/.venv/bin/python" python3.13 python3.12 python3; do
        [[ -z "${candidate}" ]] && continue
        if command -v "${candidate}" >/dev/null 2>&1; then
            echo "${candidate}"
            return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# Python test count — real `pytest --collect-only` over the whole tests/
# tree, parsed from pytest's own trailing summary line. Emits
# "<count>|collected" on success, or "NA|<reason>" if collection fails.
# ---------------------------------------------------------------------------
count_python_tests() {
    local py
    if ! py="$(resolve_python)"; then
        echo "NA|no python interpreter found (tried \$PYTHON, .venv/bin/python, python3.13, python3.12, python3)"
        return
    fi
    local out
    if ! out="$("${py}" -m pytest --collect-only -q "${ROOT_DIR}/tests/" --import-mode=importlib 2>&1)"; then
        # pytest --collect-only can exit non-zero on collection errors even
        # while still emitting a partial "N tests collected" summary line —
        # only treat this as unmeasurable if that line is genuinely absent.
        if ! grep -qE '[0-9]+ tests? collected' <<<"${out}"; then
            local first_err
            first_err="$(grep -m1 -E 'Error|error' <<<"${out}" || true)"
            echo "NA|pytest --collect-only failed: ${first_err:-see full log}"
            return
        fi
    fi
    local n
    n="$(grep -oE '[0-9]+ tests? collected' <<<"${out}" | tail -1 | grep -oE '^[0-9]+')"
    if [[ -z "${n}" ]]; then
        echo "NA|pytest produced no parseable 'N tests collected' summary line"
        return
    fi
    echo "${n}|collected"
}

# ---------------------------------------------------------------------------
# Frontend test count — real `vitest list --run` (exact, one line per test
# case) when node_modules/.bin/vitest is present; otherwise an honestly
# labelled grep proxy over *.spec.ts test-declaration calls (never silently
# passed off as the exact vitest count).
# ---------------------------------------------------------------------------
count_frontend_tests() {
    local frontend="${ROOT_DIR}/frontend"
    local vitest_bin="${frontend}/node_modules/.bin/vitest"
    if [[ -x "${vitest_bin}" ]]; then
        local out
        if out="$(cd "${frontend}" && timeout 120 "${vitest_bin}" list --run 2>&1)"; then
            local n
            n="$(grep -c ' > ' <<<"${out}" || true)"
            if [[ "${n}" -gt 0 ]]; then
                echo "${n}|collected (vitest list --run)"
                return
            fi
        fi
        echo "NA|vitest list --run produced no parseable test lines"
        return
    fi
    # Fallback: node_modules not installed on this host. Proxy-count real
    # it(...)/test(...) declarations — deliberately excludes describe(...)
    # blocks, which are groups not individual tests. Honestly labelled as
    # an approximation, never presented as the exact vitest count.
    if [[ -d "${frontend}/src" ]]; then
        local n
        n="$(grep -rhoE '\b(it|test)\(' "${frontend}/src" --include='*.spec.ts' 2>/dev/null | wc -l | tr -d ' ')"
        if [[ "${n}" -gt 0 ]]; then
            echo "${n}|grep proxy (node_modules absent — run npm ci in frontend/ for an exact count)"
            return
        fi
    fi
    echo "NA|frontend/node_modules absent and no *.spec.ts files found to proxy-count"
}

# ---------------------------------------------------------------------------
# Challenges count — real `ls` of challenges/scripts/*.sh.
# ---------------------------------------------------------------------------
count_challenges() {
    local n
    n="$(ls "${ROOT_DIR}/challenges/scripts/"*.sh 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "${n}" -eq 0 ]]; then
        echo "NA|no challenges/scripts/*.sh files found"
        return
    fi
    echo "${n}|counted"
}

# ---------------------------------------------------------------------------
# Pre-build invariants count — the highest total M from every "[N/M]"
# progress label the gate itself prints, read straight from its source.
# ---------------------------------------------------------------------------
count_prebuild_invariants() {
    local pbv="${ROOT_DIR}/scripts/pre_build_verification.sh"
    if [[ ! -f "${pbv}" ]]; then
        echo "NA|scripts/pre_build_verification.sh not found"
        return
    fi
    local n
    n="$(grep -oE '\[[0-9]+/[0-9]+\]' "${pbv}" | sed 's/\[//; s/\]//' | awk -F/ '{print $2}' | sort -n | tail -1)"
    if [[ -z "${n}" ]]; then
        echo "NA|no [N/N] progress labels found in pre_build_verification.sh"
        return
    fi
    echo "${n}|counted"
}

# ---------------------------------------------------------------------------
# §11.4.259 closed color vocabulary: GREEN(success)/AMBER(yellow)/RED(critical)
# /GRAY(lightgrey, N/A). These are informational COUNT badges (existence, not
# a pass/fail assertion) so a genuinely-computed count is always "blue"
# (informational — matches the sibling plugins/pre-build/challenges badges'
# existing honest style) and an unmeasurable count is GRAY, never invented.
# ---------------------------------------------------------------------------
badge_color_for() {
    local value="$1"
    if [[ "${value}" == "NA" ]]; then
        echo "lightgrey"
    else
        echo "blue"
    fi
}

shields_encode() {
    # Minimal shields.io path-segment encoder matching the encoding already
    # used by the existing badges in this README (space -> %20, etc.).
    local s="$1"
    s="${s// /%20}"
    s="${s//(/%28}"
    s="${s//)/%29}"
    s="${s//:/%3A}"
    s="${s//|/%7C}"
    echo "${s}"
}

# ---------------------------------------------------------------------------
# Compute every count once.
# ---------------------------------------------------------------------------
PY_RESULT="$(count_python_tests)"
PY_COUNT="${PY_RESULT%%|*}"
PY_METHOD="${PY_RESULT#*|}"

FE_RESULT="$(count_frontend_tests)"
FE_COUNT="${FE_RESULT%%|*}"
FE_METHOD="${FE_RESULT#*|}"

CH_RESULT="$(count_challenges)"
CH_COUNT="${CH_RESULT%%|*}"

PB_RESULT="$(count_prebuild_invariants)"
PB_COUNT="${PB_RESULT%%|*}"

# ---------------------------------------------------------------------------
# Scoped subset for the Contributing-section bullet, which names an EXACT
# suite scope ("unit + e2e + contract" — the non-live-HTTP suites a PR is
# expected to keep green, per the "Testing" section's own
# `pytest tests/unit/ tests/e2e/ tests/contract/` invocation) distinct from
# the whole-tree count used for the top badge. Substituting the whole-tree
# number into this specific label would itself be a §11.4.6 mismatch between
# claimed scope and reported number.
# ---------------------------------------------------------------------------
count_python_subset() {
    local py
    if ! py="$(resolve_python)"; then
        echo "NA"
        return
    fi
    local total=0 any=0
    for d in unit e2e contract; do
        if [[ -d "${ROOT_DIR}/tests/${d}" ]]; then
            local n
            n="$("${py}" -m pytest --collect-only -q "${ROOT_DIR}/tests/${d}/" --import-mode=importlib 2>&1 \
                | grep -oE '[0-9]+ tests? collected' | tail -1 | grep -oE '^[0-9]+' || true)"
            if [[ -n "${n}" ]]; then
                total=$((total + n))
                any=1
            fi
        fi
    done
    if [[ "${any}" -eq 0 ]]; then
        echo "NA"
    else
        echo "${total}"
    fi
}
PY_SUBSET_COUNT="$(count_python_subset)"

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# Build the new badge line values.
# ---------------------------------------------------------------------------
if [[ "${PY_COUNT}" == "NA" ]]; then
    PY_LABEL="python%20tests-N%2FA%20%28${PY_METHOD// /%20}%29-lightgrey"
else
    PY_LABEL="python%20tests-$(shields_encode "${PY_COUNT} collected")-blue"
fi

if [[ "${FE_COUNT}" == "NA" ]]; then
    FE_LABEL="frontend%20tests-N%2FA%20%28${FE_METHOD// /%20}%29-lightgrey"
else
    FE_LABEL="frontend%20tests-$(shields_encode "${FE_COUNT} collected")-blue"
fi

PY_LINE="  <img alt=\"tests\"          src=\"https://img.shields.io/badge/${PY_LABEL}\">"
FE_LINE="  <img alt=\"vitest\"         src=\"https://img.shields.io/badge/${FE_LABEL}\">"

# The pre-build and challenges badges were previously REPORTED as
# "(unchanged, cross-checked, matches existing badge)" while never being
# compared to anything and never being rewritten. Measured 2026-08-20: the
# script announced 44 invariants / 38 challenges while README carried 30 and
# 31. That parenthetical was a hardcoded string — a §11.4 bluff at the badge
# layer, in the same file BOB-118 already caught carrying untraceable badge
# numbers. Both badges are now built, checked and rewritten exactly like the
# python/frontend pair, so the claim is earned rather than asserted.
# Guard: tests/unit/test_compute_badges_all_badges_updated.sh
PB_LABEL="pre--build%20invariants-$(shields_encode "${PB_COUNT}")-blue"
CH_LABEL="challenges-$(shields_encode "${CH_COUNT}")-blue"
PB_LINE="  <img alt=\"pre-build\"      src=\"https://img.shields.io/badge/${PB_LABEL}\">"
CH_LINE="  <img alt=\"challenges\"     src=\"https://img.shields.io/badge/${CH_LABEL}\">"

if [[ "${MODE}" == "check" ]]; then
    STALE=0
    if ! grep -qF "${PY_LINE}" "${README}" 2>/dev/null; then
        echo "STALE: python tests badge does not match live count (${PY_COUNT} ${PY_METHOD})"
        STALE=1
    fi
    if ! grep -qF "${FE_LINE}" "${README}" 2>/dev/null; then
        echo "STALE: frontend tests badge does not match live count (${FE_COUNT} ${FE_METHOD})"
        STALE=1
    fi
    if ! grep -qF "${PB_LINE}" "${README}" 2>/dev/null; then
        echo "STALE: pre-build invariants badge does not match live count (${PB_COUNT})"
        STALE=1
    fi
    if ! grep -qF "${CH_LINE}" "${README}" 2>/dev/null; then
        echo "STALE: challenges badge does not match live count (${CH_COUNT})"
        STALE=1
    fi
    if [[ "${STALE}" -eq 1 ]]; then
        echo "compute-badges.sh --check: README badges are STALE — run 'scripts/compute-badges.sh' to refresh"
        exit 2
    fi
    echo "compute-badges.sh --check: README badges are in sync with live counts"
    exit 0
fi

# ---------------------------------------------------------------------------
# Apply mode: rewrite the badge lines in README.md.
# ---------------------------------------------------------------------------
if [[ ! -f "${README}" ]]; then
    echo "compute-badges.sh: ${README} not found" >&2
    exit 1
fi

TMP_README="$(mktemp)"
trap 'rm -f "${TMP_README}"' EXIT

awk -v py_line="${PY_LINE}" -v fe_line="${FE_LINE}" \
    -v pb_line="${PB_LINE}" -v ch_line="${CH_LINE}" \
    -v py_count="${PY_COUNT}" -v fe_count="${FE_COUNT}" \
    -v py_subset="${PY_SUBSET_COUNT}" \
    '
    # §11.4.201(7)(a) match STRUCTURE, not substring. The pre-fix patterns were
    # bare /alt="tests"/ and /alt="vitest"/, which fire on ANY line containing
    # those literals — including the prose paragraph in README.md that
    # DOCUMENTS this very filter. That prose line was replaced with an <img>
    # tag, destroying documentation (observed 2026-08-20). Two independent
    # guards now apply, either of which alone would have prevented it:
    #   (1) in_badge_block — we are inside the <p align="center"> badge block
    #   (2) the line IS an <img …> tag whose src is a shields.io badge URL
    # Regression test: tests/unit/test_compute_badges_carrier_match.sh
    /<p align="center">/ { in_badge_block = 1 }
    /<\/p>/              { in_badge_block = 0 }
    in_badge_block && /^[[:space:]]*<img[[:space:]]+alt="tests"[[:space:]]+src="https:\/\/img\.shields\.io\/badge\// { print py_line; next }
    in_badge_block && /^[[:space:]]*<img[[:space:]]+alt="pre-build"[[:space:]]+src="https:\/\/img\.shields\.io\/badge\// { print pb_line; next }
    in_badge_block && /^[[:space:]]*<img[[:space:]]+alt="challenges"[[:space:]]+src="https:\/\/img\.shields\.io\/badge\// { print ch_line; next }
    in_badge_block && /^[[:space:]]*<img[[:space:]]+alt="vitest"[[:space:]]+src="https:\/\/img\.shields\.io\/badge\// { print fe_line; next }
    /Python unit \+ e2e \+ contract/ {
        if (py_subset == "NA") {
            print
        } else {
            print "- Python unit + e2e + contract (`pytest` — " py_subset " tests collected, see docs/TESTING.md)"
        }
        next
    }
    /Frontend Vitest \(`ng test`/ {
        if (fe_count == "NA") {
            print
        } else {
            print "- Frontend Vitest (`ng test` — " fe_count " tests collected, see docs/TESTING.md)"
        }
        next
    }
    { print }
    ' "${README}" > "${TMP_README}"

mv "${TMP_README}" "${README}"
trap - EXIT

echo "compute-badges.sh: README.md badges refreshed"
echo "  python tests:   ${PY_COUNT} (${PY_METHOD})"
echo "  frontend tests: ${FE_COUNT} (${FE_METHOD})"
# §11.4.6: report what was actually verified, never a hardcoded claim. These two
# lines previously read "(unchanged, cross-checked, matches existing badge)"
# unconditionally, while the badges they described were stale by 14 and 7.
for _b in "challenges:${CH_COUNT}:${CH_LINE}" "pre-build invariants:${PB_COUNT}:${PB_LINE}"; do
    _name="${_b%%:*}"; _rest="${_b#*:}"; _cnt="${_rest%%:*}"; _line="${_rest#*:}"
    if grep -qF "${_line}" "${README}" 2>/dev/null; then
        echo "  ${_name}: ${_cnt} (badge verified present in README)"
    else
        # Unreachable in normal operation — the awk pass above rewrites both
        # lines. If it fires, the badge block shape changed and the rewrite
        # silently missed; say so rather than claim a match (§11.4.201(6)).
        echo "  ${_name}: ${_cnt} (WARNING: badge NOT found in README after rewrite — badge block shape may have changed)" >&2
    fi
done

# ---------------------------------------------------------------------------
# Update docs/TESTING.md — the corroborating authoritative source that BOB-118
# found carried ZERO occurrences of the numbers the README badges claimed.
# ---------------------------------------------------------------------------
if [[ -f "${TESTING_MD}" ]]; then
    if grep -q '^## Test counts (machine-derived, §11.4.259)' "${TESTING_MD}"; then
        # Replace the existing auto-generated section (bounded by its own
        # heading and the next top-level heading or EOF).
        TMP_TESTING="$(mktemp)"
        awk '
            /^## Test counts \(machine-derived, §11\.4\.259\)/ { skip = 1; next }
            skip && /^## / { skip = 0 }
            !skip { lines[++n] = $0 }
            END {
                # Also drop the blank line(s) that PRECEDED the stripped
                # heading. Without this, the unconditional leading `echo ""`
                # in the regeneration block below appends one MORE blank line
                # on every run and they accumulate without bound — the section
                # is always re-appended at EOF, so trimming trailing blanks
                # here is safe regardless of where the old section sat.
                # §11.4.50 determinism: N runs must equal 1 run.
                # Regression: tests/unit/test_compute_badges_carrier_match.sh
                while (n > 0 && lines[n] ~ /^[[:space:]]*$/) { n-- }
                for (i = 1; i <= n; i++) { print lines[i] }
            }
        ' "${TESTING_MD}" > "${TMP_TESTING}"
        mv "${TMP_TESTING}" "${TESTING_MD}"
    fi

    {
        echo ""
        echo "## Test counts (machine-derived, §11.4.259)"
        echo ""
        echo "Regenerated by [\`scripts/compute-badges.sh\`](../scripts/compute-badges.sh)"
        echo "— never hand-typed. Corroborates the README badge row + the"
        echo "Contributing-section bullets. Last regenerated: ${TS}."
        echo ""
        echo "| Suite | Directory | Real count | Method |"
        echo "|---|---|---|---|"
        if [[ "${PY_COUNT}" != "NA" ]]; then
            echo "| Python (whole \`tests/\` tree) | \`tests/\` | **${PY_COUNT}** | \`pytest --collect-only -q\` |"
        else
            echo "| Python (whole \`tests/\` tree) | \`tests/\` | N/A | ${PY_METHOD} |"
        fi
        for d in unit integration e2e contract; do
            if [[ -d "${ROOT_DIR}/tests/${d}" ]]; then
                py="$(resolve_python)"
                sub_n="$("${py}" -m pytest --collect-only -q "${ROOT_DIR}/tests/${d}/" --import-mode=importlib 2>&1 | grep -oE '[0-9]+ tests? collected' | tail -1 | grep -oE '^[0-9]+' || true)"
                if [[ -n "${sub_n}" ]]; then
                    echo "| Python ${d} | \`tests/${d}/\` | **${sub_n}** | \`pytest --collect-only -q\` |"
                fi
            fi
        done
        if [[ "${FE_COUNT}" != "NA" ]]; then
            echo "| Frontend (Vitest) | \`frontend/src/**/*.spec.ts\` | **${FE_COUNT}** | ${FE_METHOD} |"
        else
            echo "| Frontend (Vitest) | \`frontend/src/**/*.spec.ts\` | N/A | ${FE_METHOD} |"
        fi
        echo "| HelixQA Challenges | \`challenges/scripts/*.sh\` | **${CH_COUNT}** | \`ls challenges/scripts/*.sh \| wc -l\` |"
        echo "| Pre-build invariants | \`scripts/pre_build_verification.sh\` | **${PB_COUNT}** | max total of every \`[N/N]\` progress label |"
        echo ""
        echo "**BOB-118 provenance note:** the README badge row previously read"
        echo "\`python tests-585 passing\` / \`frontend tests-182 passing\` with no"
        echo "corroborating source anywhere in this document (a §11.4.6 bluff — the"
        echo "numbers were off by roughly 9x and could not be traced to any real"
        echo "invocation). This table is that corroborating source going forward;"
        echo "wording changed from \"passing\" to \"collected\" because collection"
        echo "counts (this table's method) prove existence, not that every test"
        echo "currently passes — a materially different, honestly-labelled claim."
    } >> "${TESTING_MD}"

    echo "compute-badges.sh: docs/TESTING.md '## Test counts' section refreshed"
fi

# --- §11.4.65 / §11.4.106 export sync -------------------------------------
# This script MUTATES README.md and docs/TESTING.md, which both carry tracked
# .html/.pdf/.docx siblings. Rewriting the .md without regenerating those
# siblings leaves the tree permanently stale, so every badge refresh would
# then FAIL invariant 1 (CM-MARKDOWN-EXPORT-SYNC) on the very next commit.
#
# Measured 2026-08-20: a badge refresh blocked a commit with
#   "CM-MARKDOWN-EXPORT-SYNC: 4 export(s) missing/stale
#      - README.html stale (source changed after export)
#      - README.pdf stale  (source changed after export)
#      - docs/TESTING.html stale (source changed after export)
#      - docs/TESTING.pdf stale  (source changed after export)"
# The oracle was right; this script was the producer of the staleness. Closing
# the loop here means the mutation and its exports land together, as §11.4.12
# requires ("regenerated in the same commit as any edit to its source").
#
# Honest boundary (§11.4.3/§11.4.6): the exporter SKIPs formats whose tool is
# absent (no pandoc -> no .docx) and says so; a missing tool is reported, never
# silently treated as success. A failure here is surfaced as a warning rather
# than aborting, because the badge values themselves are already correctly
# written by this point — losing them to a non-zero exit would be worse than a
# stale export the next gate run will catch anyway.
_EXPORTER="${SCRIPT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}/generate_markdown_exports.sh"
if [[ -x "${_EXPORTER}" || -f "${_EXPORTER}" ]]; then
    echo "compute-badges.sh: regenerating .md exports (§11.4.65) so the tree is not left stale"
    if bash "${_EXPORTER}" >/dev/null 2>&1; then
        echo "compute-badges.sh: exports regenerated"
    else
        echo "compute-badges.sh: WARNING — export regeneration failed; README/TESTING" >&2
        echo "  siblings may be stale. Run 'bash scripts/generate_markdown_exports.sh'" >&2
        echo "  before committing, or invariant 1 (CM-MARKDOWN-EXPORT-SYNC) will FAIL." >&2
    fi
else
    echo "compute-badges.sh: WARNING — ${_EXPORTER} not found; exports NOT regenerated" >&2
fi
