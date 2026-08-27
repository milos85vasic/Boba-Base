#!/usr/bin/env bash
# SHARED READ-ONLY BASELINE READER for CM-EXPORT-CHARSET-VALID.
#
# WHY THIS EXISTS: the round-1 BLOCKING was one parse rule written twice and fixed
# once. Duplicated validation diverges — that is the whole lesson — so every
# consumer now reads the baseline through this single function. It READS and
# VALIDATES only; it contains no write path, so sourcing it grants the gate no
# capability it is supposed to lack (§11.4.249, §11.4.240(B)).
#
# WHAT IT REFUSES, and why each is an unresolvable signal rather than a value
# (§11.4.252 fail closed — the gate takes the conservative-safe default):
#
#   SYMLINK        `-f` follows symlinks, so a link to a target outside the tree
#                  reads normally. After ONE reviewable diff adding the link
#                  (mode 120000), every later raise edits the outside target and
#                  leaves no diff at all — trace-free loosening, which is exactly
#                  the property the tracked-file design exists to provide.
#   NOT REGULAR    a directory at the path makes `mv` "succeed" by depositing the
#                  temp file inside it, leaving nothing at the path.
#   NOT EXACTLY 1  `sed …p | tail -1` silently resolves an ambiguous file to its
#                  last matching line: "baseline=3" followed by "baseline=08" —
#                  plausibly the operator's intended correction — resolved to 3
#                  and passed. Two conflicting well-formed lines resolved just as
#                  quietly. Ambiguity is not a value.
#   NOT A BOUNDED  the regex is strict AND bounded: no leading zeros (bash reads
#   NON-NEG INT    "08" as invalid octal and ERRORS, and `if` swallows that error
#                  as false, so both comparisons fell through to PASS), and at
#                  most 18 digits (bash arithmetic wraps mod 2^64, so
#                  18446744073709551619 silently became 3 and a corpus with 3
#                  violations read as "at baseline" and PASSED). Both measured
#                  2026-08-26. A number a caller cannot faithfully evaluate must
#                  refuse, never be silently misread.
#
# CONTRACT
#   read_baseline <path>
#     sets BASELINE_VALUE (the integer) on success
#     sets BASELINE_ERROR (a human sentence) on failure
#     returns 0 usable · 2 absent · 1 present but unusable
#   The 2-vs-1 split exists so a caller can offer --adopt for an absent baseline
#   without offering it for a corrupt one.

# The single source of truth for what a baseline value may look like.
# 0, or 1-18 digits with no leading zero. 18 digits max keeps every value well
# inside the signed 64-bit range bash evaluates in.
CM_BASELINE_BRE='s/^baseline=\(0\|[1-9][0-9]\{0,17\}\)$/\1/p'

read_baseline() {
    local f="${1:-}"
    BASELINE_VALUE=""
    BASELINE_ERROR=""

    if [[ -h "${f}" ]]; then
        BASELINE_ERROR="${f} is a symlink. The ratchet must be a regular file inside the tree, so that every change to it is a diff a reviewer sees; a link can be re-pointed outside the tree and edited without leaving one. Replace it with a regular file."
        return 1
    fi
    if [[ ! -e "${f}" ]]; then
        BASELINE_ERROR="no ratchet baseline at ${f}"
        return 2
    fi
    if [[ ! -f "${f}" ]]; then
        BASELINE_ERROR="${f} exists but is not a regular file"
        return 1
    fi

    local n
    n="$(grep -c '^baseline=' "${f}" 2>/dev/null)" || n=0
    if [[ "${n}" -ne 1 ]]; then
        BASELINE_ERROR="${f} carries ${n} 'baseline=' lines; exactly one is required. An ambiguous threshold is an unresolvable signal, not a value to be resolved by picking one."
        return 1
    fi

    local v
    v="$(sed -n "${CM_BASELINE_BRE}" "${f}")"
    if [[ -z "${v}" ]]; then
        BASELINE_ERROR="${f} carries no parseable 'baseline=<n>' line (expected 0, or 1-18 digits with no leading zero)"
        return 1
    fi

    BASELINE_VALUE="${v}"
    return 0
}
