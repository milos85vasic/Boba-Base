#!/usr/bin/env bash
# check_cm_no_production_mutation_residue.sh — CM-NO-PRODUCTION-MUTATION-RESIDUE
# static pre-build gate (§11.4.84 working-tree quiescence at the build seam).
#
# Purpose:
#   Refuse any build whose PRODUCTION sources still carry paired-§1.1
#   mutation residue — the `# MUT'ATED for §11.4.115 RED` / `// alwa'ys
#   pass` / `if fals'e && …` short-circuit-swallow artifacts a RED-first
#   mutation run plants and is supposed to restore. Retroactive catcher
#   for the 2026-08-10 Agent H forensic FACT: a GCM auth-bypass mutation
#   lived in qBitTorrent-go/internal/db/crypto.go mid-window; the agent
#   restored it before returning, so a post-hoc diff read clean — this
#   gate refuses the build if such a restoration ever fails.
#
# ── BOB-070 (RD2-41): why this script exists ────────────────────────────
#   The invariant previously lived inline in pre_build_verification.sh and
#   matched a bare comment-prefix + marker ANYWHERE on a line. Every
#   production source that merely DOCUMENTED the marker (a comment
#   explaining the scan, a string literal holding the pattern) FALSE-
#   POSITIVE-FAILED the whole build — the §11.4.201(7)(a) carrier-not-thing
#   class landing on the gate itself.
#
#   The first remediation "fixed" that by LINE-ANCHORING the pattern:
#   only a comment marker at the START of a line (after indent) counted.
#   That is a POSITIONAL proxy, not a structural discriminator, and it
#   traded a false-positive machine for a FALSE-NEGATIVE one. Measured
#   with a §11.4.201(7)(b) control needle on 2026-08-20 against the
#   then-live gate, 5 of 7 real-residue shapes passed through unseen:
#
#     FIRES  own-line   `    # MUT'ATED for RED`
#     BLIND  trailing   `    return True  # MUT'ATED for RED`      <-- residue
#     BLIND  trailing   `    return nil // MUT'ATED: alwa'ys pass` <-- residue
#     FIRES  anchored   `    if fals'e && err != nil { // MUT'ATED`
#     BLIND  mid-line   `    if err == nil || fals'e && err != nil`<-- residue
#     BLIND  trailing   `    return 0  # alwa'ys pass`             <-- residue
#     BLIND  waived     any line carrying the escape sentinel      <-- bypass
#
#   A trailing comment on a live statement is the MOST common real
#   mutation shape (it is what Agent H's own residue looked like), so the
#   gate was blind precisely where it mattered. This is the exact BOB-070
#   failure mode: a carrier false-positive gets "resolved" by broadening
#   until the scan silently stops detecting real residue.
#
# ── The structural discriminator (§11.4.201(7)(a) match STRUCTURE) ──────
#   Position on the line is not what separates a carrier from residue.
#   What separates them is WHERE the token lives in the file's grammar:
#
#     RESIDUE : the marker sits in a COMMENT attached to executable code
#               (own-line or trailing — both are residue), or the
#               short-circuit-swallow shape sits in the CODE itself.
#     CARRIER : the marker sits inside a STRING LITERAL (a pattern
#               registry, an example list, a doc generator's data) or
#               inside a DOCSTRING / BLOCK COMMENT / HEREDOC region
#               (prose documenting the scan).
#
#   So the detector parses instead of guessing at position: it tracks
#   docstring / block-comment / heredoc / raw-string regions across
#   lines, MASKS string-literal interiors (same-length, so byte offsets
#   still line up with the original), and only then looks for a comment
#   introducer and the marker inside the comment text. Carriers are
#   excluded BY CONSTRUCTION rather than by an exclusion list, which is
#   what §11.4.224(E) asks for: no path is exempted to make a false
#   positive go away.
#
# ── Detected classes ────────────────────────────────────────────────────
#   C1  marker anywhere in a real comment      MUT'ATED | alwa'ys pass
#   C2  annotation opening a real comment      #/// MUT'ATION
#   C3  short-circuit-swallow in real code     if fals'e && … | || fals'e && …
#   C4  mutation-artifact filename             *_mutated_* / *.mutated.* / *_mutant.*
#   C5  malformed waiver (see below)           unjustified / on a code line
#
# ── The waiver, fenced (§11.4.224(E)) ───────────────────────────────────
#   A production file may legitimately need a comment that names the
#   marker. The per-line escape sentinel `guard'rails:allow <reason>`
#   permits it, but is FENCED so it cannot become the bypass it was:
#     (1) a REASON is mandatory — a bare sentinel is class C5, a FAIL;
#     (2) it is only honoured on a COMMENT-ONLY line. A documentation
#         mention has no reason to hang off a live statement, while a
#         trailing comment on executable code is exactly the residue
#         shape — so a trailing marker is NEVER waivable (class C5);
#     (3) every honoured waiver is PRINTED and COUNTED in the gate's
#         output, so a waiver can never be silent (§11.4.201(5)).
#   Residual risk, stated honestly (§11.4.6): a determined author can
#   still waive an own-line marker with a plausible reason. That is
#   visible in the gate output and in git-blame; it is not invisible.
#
# ── Anti-self-match ─────────────────────────────────────────────────────
#   This file necessarily names every token it hunts. Two structural
#   defences, not wording tricks: (a) every token is assembled by string
#   concatenation at runtime, so this source never literally contains
#   one; (b) this script's own path is excluded from its own scan
#   (§11.4.196(D)/§12.12 instrument-matches-its-own-carrier footgun).
#
# Usage:
#   check_cm_no_production_mutation_residue.sh              # default scope
#   check_cm_no_production_mutation_residue.sh PATH...      # explicit paths
#
# Exit codes:
#   0 — no residue (waivers, if any, printed and counted)
#   1 — residue found (each hit printed as file:line:class:text)
#   2 — harness/environment error (incl. a zero-file walk, which is a
#       §11.4.201(6) FALSE-NULL and never a silent pass)
#
# Cross-refs: §11.4.84 §11.4.107(10) §11.4.115 §11.4.196(D) §11.4.201
#             §11.4.224(E) §11.4.240 §11.4.249 §12.12
set -uo pipefail

SELF_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd "$(dirname "${SELF_PATH}")/../.." && pwd)"

# ── Tokens, assembled so this source never literally holds one ─────────
T_MARK="MUT""ATED"
T_ALWAYS="alwa""ys"
T_MUTATION="MUT""ATION"
T_FALSE="fals""e"
T_ALLOW="guard""rails:allow"

# ── Scope ───────────────────────────────────────────────────────────────
EXPLICIT_MODE=0
ROOTS=()
if [[ $# -gt 0 ]]; then
    EXPLICIT_MODE=1
    ROOTS=("$@")
    for r in "${ROOTS[@]}"; do
        if [[ ! -e "${r}" ]]; then
            echo "ERROR: path does not exist: ${r}" >&2
            exit 2
        fi
    done
else
    # Production source roots — only paths that ship user-visible behaviour.
    for cand in \
        "${REPO_ROOT}/download-proxy" \
        "${REPO_ROOT}/qBitTorrent-go" \
        "${REPO_ROOT}/scripts" \
        "${REPO_ROOT}/plugins" \
        "${REPO_ROOT}/webui-bridge.py"; do
        [[ -e "${cand}" ]] && ROOTS+=("${cand}")
    done
    if [[ "${#ROOTS[@]}" -eq 0 ]]; then
        echo "ERROR: no production source root resolved to scan" >&2
        exit 2
    fi
fi

# ── Exclusions, each with its §11.4.224(E) justification ────────────────
# NOISE excludes: never first-party executable source. Applied in BOTH
# modes — a __pycache__/.git/vendor artifact is not a source file at all.
NOISE_EXCLUDES=(
    ! -path '*/.git/*'          # VCS internals, not source
    ! -path '*/__pycache__/*'   # generated bytecode (§11.4.77 regenerable)
    ! -path '*/node_modules/*'  # vendored third-party
    ! -path '*/.venv/*'         # vendored third-party (virtualenv)
    ! -path '*/venv/*'          # vendored third-party (virtualenv)
    ! -path '*/site-packages/*' # vendored third-party
    ! -path '*/.mypy_cache/*'   # generated tool cache
    ! -path '*/.pytest_cache/*' # generated tool cache
    ! -path '*/.ruff_cache/*'   # generated tool cache
    ! -path '*/out/*'           # build output (§11.4.30 not versioned)
    ! -path '*/build/*'         # build output (§11.4.30 not versioned)
    ! -path '*/dist/*'          # build output (§11.4.30 not versioned)
)
# CORPUS excludes: real first-party files that are deliberately OUT of the
# "production sources" corpus this invariant is scoped to. NOT applied in
# explicit-path mode — otherwise pointing the gate at a fixture under
# challenges/ would walk zero files and false-PASS the golden-bad fixture
# (§11.4.201(6) false-null; this was a live defect in the previous
# fixture-root harness).
CORPUS_EXCLUDES=(
    ! -path '*/constitution/*'  # inherited-by-reference submodule, not ours (§11.4.177)
    ! -path '*/submodules/*'    # other repos' sources, governed by their own gates
    ! -path '*/tests/*'         # non-shipping test code; mutations there are the POINT
    ! -path '*/challenges/*'    # non-shipping fixtures/harnesses (§11.4.224(E) class)
    ! -path '*/qa-results/*'    # captured evidence artifacts, not source
    ! -path '*/scratchpad/*'    # §11.4.11 untracked scratch, not shipped
    ! -path '*/mutants/*'       # mutation-testing workspace; residue there is expected
)
EXCLUDES=("${NOISE_EXCLUDES[@]}")
if [[ "${EXPLICIT_MODE}" -eq 0 ]]; then
    EXCLUDES+=("${CORPUS_EXCLUDES[@]}")
fi

FILE_LIST="$(mktemp)"
HITS_LOG="$(mktemp)"
WAIVE_LOG="$(mktemp)"
trap 'rm -f "${FILE_LIST}" "${HITS_LOG}" "${WAIVE_LOG}"' EXIT

find "${ROOTS[@]}" -type f \( -name '*.go' -o -name '*.py' -o -name '*.sh' -o -name '*.bash' \) \
    "${EXCLUDES[@]}" -print 2>/dev/null \
    | grep -v -x -F "${SELF_PATH}" >"${FILE_LIST}" || true

FILE_COUNT=$(wc -l <"${FILE_LIST}" | tr -d ' ')
if [[ "${FILE_COUNT}" -eq 0 ]]; then
    # §11.4.201(6): a blind instrument and a clean corpus return the same
    # quiet zero. Refuse rather than report "clean".
    echo "ERROR: walked ZERO files — the scan cannot see, so 'clean' would be a false-null" >&2
    printf '  roots: %s\n' "${ROOTS[*]}" >&2
    exit 2
fi

mapfile -t SCAN_FILES <"${FILE_LIST}"

# ── Detector ────────────────────────────────────────────────────────────
# awk parses each file's grammar enough to tell a comment from a string
# from a docstring. mask() rewrites string-literal interiors to 'x' at the
# SAME length, so offsets computed on the masked line index correctly into
# the original.
awk -v T_MARK="${T_MARK}" -v T_ALWAYS="${T_ALWAYS}" -v T_MUTATION="${T_MUTATION}" \
    -v T_FALSE="${T_FALSE}" -v T_ALLOW="${T_ALLOW}" \
    -v HITS="${HITS_LOG}" -v WAIVED="${WAIVE_LOG}" '
function reset_state() { in_doc = 0; doc_delim = ""; in_here = 0; here_delim = "" }

# Same-length mask of string-literal interiors. Returns the masked line.
function mask(s,   out, i, c, n, instr, delim, prev) {
    out = ""; instr = 0; delim = ""; n = length(s); prev = ""
    for (i = 1; i <= n; i++) {
        c = substr(s, i, 1)
        if (!instr) {
            if (c == "\"" || c == "'"'"'" || c == "`") { instr = 1; delim = c; out = out c }
            else out = out c
        } else {
            if (c == delim && prev != "\\") { instr = 0; delim = ""; out = out c }
            else out = out "x"
        }
        prev = (prev == "\\" && c == "\\") ? "" : c
    }
    return out
}
function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
function record(cls, txt) { printf "%s:%d:%s:%s\n", FILENAME, FNR, cls, trim(txt) >> HITS }

FNR == 1 {
    reset_state()
    lang = "sh"
    if (FILENAME ~ /\.go$/) lang = "go"
    else if (FILENAME ~ /\.py$/) lang = "py"
    cmt = (lang == "go") ? "//" : "#"
    # C4 — mutation-artifact filename (§11.4.84 `_mutated_*` suffix class)
    base = FILENAME; sub(/^.*\//, "", base)
    if (base ~ /_mutated[_.]/ || base ~ /\.mutated\./ || base ~ /_mutant[_.]/)
        record("C4-mutant-filename", base)
}

{
    line = $0

    # ---- multi-line carrier regions: skip wholesale ----
    if (lang == "py") {
        if (in_doc) {                                    # inside a docstring
            if (index(line, doc_delim) > 0) { in_doc = 0; doc_delim = "" }
            next
        }
        # opens a docstring that does NOT close on this line
        if (match(line, /"""|'"'"''"'"''"'"'/)) {
            d = substr(line, RSTART, 3)
            rest = substr(line, RSTART + 3)
            if (index(rest, d) == 0) { in_doc = 1; doc_delim = d; next }
        }
    } else if (lang == "go") {
        if (in_doc) {                                    # inside /* */ or `raw`
            if (index(line, doc_delim) > 0) { in_doc = 0; doc_delim = "" }
            next
        }
        if (match(line, /\/\*/) && index(substr(line, RSTART + 2), "*/") == 0) {
            in_doc = 1; doc_delim = "*/"; next
        }
    } else {
        if (in_here) {                                   # inside a heredoc body
            if (trim(line) == here_delim) { in_here = 0; here_delim = "" }
            next
        }
        if (match(line, /<<-?[ \t]*'"'"'?"?[A-Za-z_][A-Za-z0-9_]*'"'"'?"?[ \t]*$/)) {
            d = substr(line, RSTART); gsub(/^<<-?[ \t]*|["'"'"']|[ \t]*$/, "", d)
            if (d != "") { in_here = 1; here_delim = d; next }
        }
    }

    m = mask(line)

    # ---- locate a REAL comment (introducer outside any string) ----
    pos = 0
    if (lang == "go") { p = index(m, "//"); if (p > 0) pos = p }
    else              { p = index(m, "#");  if (p > 0) pos = p }

    code_part = (pos > 0) ? substr(m, 1, pos - 1) : m
    cmt_text  = (pos > 0) ? substr(line, pos)     : ""
    code_before = (trim(code_part) != "") ? 1 : 0

    # ---- candidate comment hit (C1/C2), decided BEFORE the waiver ----
    # Order matters: the sentinel is consulted only for a line that would
    # OTHERWISE be a hit, so the audited-waiver count means exactly
    # "real hits suppressed" and never inflates on prose that merely
    # names the sentinel (§11.4.201(9) field-identity: a count must mean
    # what it claims to mean).
    cand = ""; ctxt = ""
    if (pos > 0) {
        lc = tolower(cmt_text)
        if (index(cmt_text, T_MARK) > 0) { cand = "C1-marker-in-comment"; ctxt = cmt_text }
        else if (lc ~ tolower(T_ALWAYS) "[ -]pass") { cand = "C1-fakepass-in-comment"; ctxt = cmt_text }
        else if (cmt_text ~ "^(#|\\/\\/)[ \t]*" T_MUTATION "\\y") { cand = "C2-mutation-annotation"; ctxt = cmt_text }
    }

    # ---- the fenced waiver (§11.4.224(E)) ----
    if (cand != "") {
        if (index(cmt_text, T_ALLOW) > 0) {
            after = trim(substr(cmt_text, index(cmt_text, T_ALLOW) + length(T_ALLOW)))
            sub(/^[:=-]+[ \t]*/, "", after)
            if (length(after) < 3)   record("C5-waiver-no-reason", line)      # (1) reason mandatory
            else if (code_before)    record("C5-waiver-on-code-line", line)   # (2) never on a code line
            else printf "%s:%d:%s\n", FILENAME, FNR, trim(line) >> WAIVED    # (3) always visible
        } else {
            record(cand, ctxt)
        }
    }

    # ---- C3: short-circuit-swallow in real code ----
    if (code_part ~ "(^|[^A-Za-z0-9_])if[ \t]*\\(?[ \t]*(" T_FALSE "|" toupper(substr(T_FALSE,1,1)) substr(T_FALSE,2) ")[ \t]*(&&|and)[ \t]" \
     || code_part ~ "(&&|\\|\\||[ \t](and|or)[ \t])[ \t]*(" T_FALSE "|" toupper(substr(T_FALSE,1,1)) substr(T_FALSE,2) ")[ \t]*(&&|and)[ \t]")
        record("C3-short-circuit-swallow", code_part)
}
' "${SCAN_FILES[@]}" </dev/null
# `</dev/null` is load-bearing, not decoration: awk invoked with ZERO file
# operands falls back to reading STDIN and blocks forever. The M4 paired
# mutation (which removes the zero-file refusal above) hung the whole gate
# on an empty directory until this redirect was added — a latent
# denial-of-gate found by mutating the gate, exactly what §1.1 is for.

AWK_EXIT=$?
if [[ "${AWK_EXIT}" -ne 0 ]]; then
    # §11.4.201(6): a crashed detector produces the same empty hits log as a
    # clean corpus. Refuse rather than report clean. (Found by the M4/`--`
    # mutation run: an awk fatal was previously swallowed and the gate
    # printed "0 hit(s)" while having scanned nothing.)
    echo "ERROR: detector exited ${AWK_EXIT} — results are not trustworthy" >&2
    exit 2
fi

HIT_COUNT=$(wc -l <"${HITS_LOG}" | tr -d ' ')
WAIVE_COUNT=$(wc -l <"${WAIVE_LOG}" | tr -d ' ')

echo "  scanned ${FILE_COUNT} file(s); ${HIT_COUNT} hit(s); ${WAIVE_COUNT} audited waiver(s)"
if [[ "${WAIVE_COUNT}" -gt 0 ]]; then
    while IFS= read -r w; do [[ -z "${w}" ]] || echo "        ~ WAIVED ${w}"; done <"${WAIVE_LOG}"
fi
if [[ "${HIT_COUNT}" -eq 0 ]]; then
    exit 0
fi
while IFS= read -r h; do [[ -z "${h}" ]] || echo "        - ${h}"; done <"${HITS_LOG}"
exit 1
