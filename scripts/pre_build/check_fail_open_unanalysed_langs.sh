#!/usr/bin/env bash
# check_fail_open_unanalysed_langs.sh — ADVISORY fail-open scan for Go, Rust,
# Ruby and C (BOB-191).
#
# Purpose:
#   The constitution's CM-DANGEROUS-COMBINATION-FAIL-CLOSED scanner enumerates
#   .go/.rs/.rb/.c files but analyses only Python (ast) and C-family `catch`,
#   so those four languages are reported UNANALYSED — an honest gap, but a gap:
#   qBitTorrent-go (which owns the encrypted tracker credentials) was 100%
#   unscanned. This script fills the gap with detectors that report ONLY shapes
#   that are fail-open by construction, so it cannot reproduce the BOB-189
#   false-positive class (a validator returning false on error is fail-CLOSED):
#     Go    (go/ast, scripts/pre_build/failopen_go): GO-EMPTY-ERR-BRANCH,
#           GO-SWALLOWED-PANIC
#     Rust, Ruby, C (scripts/pre_build/failopen_lang_analyzer.py):
#           RS-EMPTY-ERR-ARM, RS-EMPTY-IF-LET-ERR, RB-EMPTY-RESCUE,
#           RB-RESCUE-NIL, C-EMPTY-ERR-BRANCH
#   The canonical home for these arms is the constitution scanner (§11.4.28);
#   this consumer-side script is the stand-in until they land there — see the
#   upstream proposal in docs/qa/BOB-191/.
#
# Control needles (§11.4.201(7)(b), §11.4.273): BEFORE scanning, each analyser
#   is run on a built-in golden-bad needle (must be SEEN) and a golden-good
#   snippet (must stay SILENT). If either check fails the scan is BLIND and the
#   script exits 2 — a zero from a blind analyser is never reported as clean.
#   A missing toolchain (go / python3) marks that language UNANALYSED, loudly.
#
# Usage:   bash scripts/pre_build/check_fail_open_unanalysed_langs.sh <root>...
# Outputs: one line per hit, then one summary line.
# Exit:    0 no hits, 1 hits (ADVISORY — callers must not block on it),
#          2 bad arguments, a root that does not exist, or a control needle failed
# Side-effects: builds the Go analyser into a mktemp dir, removed on exit.
# Dependencies: bash, find, go (for Go), python3 (for Rust/Ruby/C).
# Cross-references: docs/scripts/check_fail_open_unanalysed_langs.md,
#   tests/pre_build/test_check_fail_open_unanalysed_langs.sh.
#   Constitution: §11.4.28, §11.4.201(6)(7)(b), §11.4.250, §11.4.252.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_ANALYZER="${SCRIPT_DIR}/failopen_lang_analyzer.py"
GO_SRC="${SCRIPT_DIR}/failopen_go"

if [[ $# -lt 1 ]]; then echo "Usage: $0 <root>..." >&2; exit 2; fi
for r in "$@"; do
    [[ -e "${r}" ]] || { echo "ERROR: root does not exist: ${r}" >&2; exit 2; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# ---- enumerate ---------------------------------------------------------------
: > "${WORK}/go.list"; : > "${WORK}/other.list"
while IFS= read -r -d '' f; do
    case "${f}" in
        *.go) printf '%s\n' "${f}" >> "${WORK}/go.list" ;;
        *) printf '%s\n' "${f}" >> "${WORK}/other.list" ;;
    esac
done < <(find "$@" \( -name .git -o -name node_modules -o -name vendor -o -name target \
            -o -name __pycache__ -o -name .venv \) -prune -o -type f \
            \( -name '*.go' -o -name '*.rs' -o -name '*.rb' -o -name '*.c' -o -name '*.h' \) -print0)
N_GO="$(wc -l < "${WORK}/go.list" | tr -d ' ')"
N_OTHER="$(wc -l < "${WORK}/other.list" | tr -d ' ')"

HITS="${WORK}/hits"; : > "${HITS}"
UNANALYSED=()

# ---- Go ----------------------------------------------------------------------
if [[ "${N_GO}" -gt 0 ]]; then
    if ! command -v go >/dev/null 2>&1; then
        UNANALYSED+=("go:${N_GO} (go toolchain absent)")
    else
        if ! ( cd "${GO_SRC}" && go build -o "${WORK}/failopengo" . ) >"${WORK}/gobuild.log" 2>&1; then
            echo "ERROR: could not build the Go analyser:" >&2; sed 's/^/  /' "${WORK}/gobuild.log" >&2; exit 2
        fi
        # control needle + golden-good
        printf 'package x\n\nimport "os"\n\nfunc f() {\n\t_, err := os.Open("x")\n\tif err != nil {\n\t}\n\tdefer func() { recover() }()\n}\n' > "${WORK}/needle.go"
        printf 'package x\n\nfunc g(err error) bool {\n\tif err != nil {\n\t\treturn false\n\t}\n\treturn true\n}\n' > "${WORK}/good.go"
        nout="$("${WORK}/failopengo" "${WORK}/needle.go")"
        if ! grep -q GO-EMPTY-ERR-BRANCH <<<"${nout}" || ! grep -q GO-SWALLOWED-PANIC <<<"${nout}"; then
            echo "ERROR: Go control needle NOT seen — the analyser is blind; refusing to report a clean result" >&2; exit 2
        fi
        if ! "${WORK}/failopengo" "${WORK}/good.go" >/dev/null; then
            echo "ERROR: Go golden-good (fail-closed) snippet was flagged — analyser would false-positive" >&2; exit 2
        fi
        mapfile -t GOF < "${WORK}/go.list"
        "${WORK}/failopengo" "${GOF[@]}" >> "${HITS}"; grc=$?
        [[ "${grc}" -le 1 ]] || { echo "ERROR: Go analyser could not parse some files (exit ${grc})" >&2; exit 2; }
    fi
fi

# ---- Rust / Ruby / C ---------------------------------------------------------
if [[ "${N_OTHER}" -gt 0 ]]; then
    if ! command -v python3 >/dev/null 2>&1; then
        UNANALYSED+=("rs/rb/c:${N_OTHER} (python3 absent)")
    else
        if ! python3 "${PY_ANALYZER}" --selfcheck > "${WORK}/py_self.log" 2>&1; then
            echo "ERROR: Rust/Ruby/C control needles failed — the analyser is blind or false-positive:" >&2
            sed 's/^/  /' "${WORK}/py_self.log" >&2; exit 2
        fi
        mapfile -t OF < "${WORK}/other.list"
        python3 "${PY_ANALYZER}" "${OF[@]}" >> "${HITS}"; prc=$?
        [[ "${prc}" -le 1 ]] || { echo "ERROR: Rust/Ruby/C analyser could not read some files (exit ${prc})" >&2; exit 2; }
    fi
fi

cat "${HITS}"
NH="$(wc -l < "${HITS}" | tr -d ' ')"
UN=""
[[ "${#UNANALYSED[@]}" -gt 0 ]] && UN=" — UNANALYSED: ${UNANALYSED[*]}"
if [[ "${NH}" -gt 0 ]]; then
    echo "ADVISORY: ${NH} fail-open hit(s) across ${N_GO} Go + ${N_OTHER} Rust/Ruby/C file(s) (control needles seen)${UN}"
    exit 1
fi
echo "OK: 0 fail-open hits across ${N_GO} Go + ${N_OTHER} Rust/Ruby/C file(s) (control needles seen)${UN}"
exit 0
