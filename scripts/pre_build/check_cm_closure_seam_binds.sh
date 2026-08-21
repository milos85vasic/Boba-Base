#!/usr/bin/env bash
# check_cm_closure_seam_binds.sh — CM-CLOSURE-SEAM-BINDS gate (BOB-136)
#
# ─── PURPOSE ──────────────────────────────────────────────────────────
#   Make the CLOSURE SEAM bind mechanically: report — and, at the commit
#   seam, REFUSE — when landed work and its tracked workable-item row
#   contradict each other.
#
# ─── THE DEFECT THIS CLOSES (BOB-136) ─────────────────────────────────
#   Nothing in this repo ever linked a commit back to its tracker row.
#   `workable-items validate` checks the DB's INTERNAL invariants;
#   `workable-items diff` and scripts/hooks/docs-sync-commit-seam.sh check
#   DB<->Markdown SYNC. All three are green while a row says "Queued" and
#   git says the work landed weeks ago — they compare the tracker to
#   itself, never to the repository's own history. Closure therefore
#   depended on a human remembering, and demonstrably did not happen:
#   a 2026-08-20 sweep found BOB-076 (its commit message literally says
#   "closes BOB-076") still Queued, and a 2026-08-21 sweep found 24 such
#   rows. A status field that does not move when work lands is not
#   evidence, it is decoration — and every downstream reader of status
#   (release gates, "is this owed?", §11.4.55 reopen ranking) silently
#   degrades. §11.4.227: an item's done state is its SEAM landing, not
#   its TEXT landing. This file is that seam.
#
# ─── WHAT IT ASSERTS (and, deliberately, what it does NOT) ────────────
#   It NEVER decides "this item is finished". It asserts the far narrower,
#   mechanically decidable proposition that a specific status literal is
#   FALSE:
#     CONTRADICTION  a commit message says it CLOSES/FIXES/RESOLVES <id>,
#                    yet <id> is non-terminal. The git record and the
#                    tracker directly contradict each other.
#     UNRECONCILED   a WORK-type commit (feat/fix/perf/refactor/test/
#                    build/style/revert, or a bare `<id>:` subject)
#                    declares <id>, yet <id>'s status is exactly `Queued`
#                    — which asserts NO WORK HAS STARTED. The commit
#                    refutes that. Remedy is `In progress` OR a close;
#                    the gate does not presume which.
#     UNTRACKED-ID   a commit declares <id>, and <id> has no row at all.
#   Statuses that already tell the truth about landed work
#   (`In progress`, `Ready for testing`, `In testing`, `Reopened`,
#   `Operator-blocked`, and every terminal `... (→ Fixed.md)`) are NEVER
#   flagged by UNRECONCILED. That scoping is what keeps the gate from
#   firing on a healthy tree (§11.4.201(1)).
#
# ─── §11.4.201(1) BOTH DIRECTIONS / §11.4.201(7)(a) MATCH STRUCTURE ───
#   A gate that flags correctly-tracked work is exactly as broken as one
#   that misses stale rows — it gets switched off within a week. Every
#   link is therefore extracted STRUCTURALLY (conventional-commit scope
#   token, bare-id subject prefix, closure keyword adjacency), never by
#   "the message contains the string". Four CARRIER classes are excluded
#   BY CONSTRUCTION and each has a fixture in the meta-test:
#     (c1) FILING verbs      `docs(tracker): file BOB-149` — filing an
#          item is not doing it. Live proof: BOB-146 and BOB-149 were
#          both filed on 2026-08-21 and this gate reports neither.
#     (c2) PATH context      `docs/qa/BOB-117/closure-evidence.md` — an
#          id preceded by `/` is a path component, not a declaration.
#     (c3) QUOTED text       an indented / `>`-quoted / "double-quoted"
#          closure phrase, i.e. a commit message that QUOTES another
#          ticket (BOB-136's own body quotes the string `closes BOB-076`).
#     (c4) NON-WORK types    `docs(BOB-141): ...` / `chore` / `ci` —
#          documenting or registering an item never lands its work.
#   Compact runs (`closes BOB-081/083/089/117`, `docs(BOB-124/125/126)`)
#   and suffixed scope tokens (`BOB-111-followup`, `BOB-122-fallout`) are
#   BOTH real in-repo spellings and both are expanded — a needle that
#   exercised only the plain spelling would certify a blind query.
#
# ─── USAGE ────────────────────────────────────────────────────────────
#   check_cm_closure_seam_binds.sh                     # sweep all history
#   check_cm_closure_seam_binds.sh --report-only       # audit, never exit 1
#   check_cm_closure_seam_binds.sh --message-file F    # COMMIT-SEAM mode
#   check_cm_closure_seam_binds.sh --message "TEXT"    # COMMIT-SEAM mode
#   check_cm_closure_seam_binds.sh --self-test         # §11.4.107(10)
#   check_cm_closure_seam_binds.sh --help
#
#   Options: --repo DIR  --db PATH  --prefix P  --rev-range R  -v
#
#   COMMIT-SEAM mode evaluates ONLY the ids the PENDING message declares.
#   It is monotone by construction: it can refuse the commit that is about
#   to create fresh drift, and is structurally incapable of blocking on
#   the pre-existing backlog. That is why it needs no baseline/ratchet
#   file — a file which would itself rot (§11.4.215).
#
# ─── INPUTS / OUTPUTS / SIDE-EFFECTS ──────────────────────────────────
#   Inputs:   git history of --repo; the workable-items SQLite DB
#             (READ-ONLY — this gate never writes to it); optionally a
#             commit-message file.
#   Outputs:  named per-check verdict lines on stdout; findings +
#             remediation on stderr.
#   Side-effects: none beyond a temp dir under $TMPDIR, removed on exit.
#   Dependencies: bash, git, awk, sed, grep, sqlite3.
#
# ─── VERDICT ──────────────────────────────────────────────────────────
#   0 — PASS   (no findings, or --report-only)
#   1 — FAIL   (findings; each named on stderr with its remediation)
#   2 — ERROR  (usage error, missing repo/DB, missing sqlite3)
#
#   §11.4.3 honest SKIP: an absent DB or sqlite3 is reported as a loud
#   SKIP-with-reason and exits 0 — an unreadable tracker is not evidence
#   of drift, and refusing on it would be the §11.4.201(1) false-positive
#   this gate exists to avoid.
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.15 §11.4.34 §11.4.35 §11.4.54
#             §11.4.93 §11.4.106(F) §11.4.107(10) §11.4.115 §11.4.135
#             §11.4.146(D3) §11.4.201(1)(6)(7) §11.4.214 §11.4.215
#             §11.4.226 §11.4.227 §11.4.234(D) §11.4.238 §11.4.262 §1.1

set -euo pipefail

SCRIPT_NAME="check_cm_closure_seam_binds"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

REPO="$REPO_ROOT"
DB=""
PREFIX="BOB"
REV_RANGE=""
MODE="sweep"
MSG_TEXT=""
MSG_FILE=""
REPORT_ONLY=0
VERBOSE=0

TMPD=""
_cleanup() { [[ -n "$TMPD" ]] && rm -rf "$TMPD" 2>/dev/null || true; }
trap _cleanup EXIT

usage() { sed -n '/─── USAGE/,/─── INPUTS/p' "${BASH_SOURCE[0]}"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)         REPO="$2"; shift 2 ;;
        --db)           DB="$2"; shift 2 ;;
        --prefix)       PREFIX="$2"; shift 2 ;;
        --rev-range)    REV_RANGE="$2"; shift 2 ;;
        --message)      MODE="commit-seam"; MSG_TEXT="$2"; shift 2 ;;
        --message-file) MODE="commit-seam"; MSG_FILE="$2"; shift 2 ;;
        --self-test)    MODE="selftest"; shift ;;
        --report-only)  REPORT_ONLY=1; shift ;;
        -v|--verbose)   VERBOSE=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        *) echo "ERROR($SCRIPT_NAME): unknown argument: $1" >&2; exit 2 ;;
    esac
done

[[ -z "$DB" ]] && DB="$REPO/docs/workable_items.db"

# ─── the structural link extractor ───────────────────────────────────
# Emitted to a temp file rather than inlined so the SAME program serves
# the sweep, the commit-seam mode and the self-test — one extractor, one
# behaviour, no chance of the self-test certifying a different parser
# than the one that ships (§11.4.249 producer != oracle would be voided
# if the test validated a second copy).
_write_extractor() {
    cat > "$TMPD/extract.awk" <<'AWK_EOF'
# stdin : one record per commit, RS=\x1e, FS=\x1f -> sha, "subject:...", "body:..."
# stdout: sha \t class \t id
#   classes: closes | scope-work | scope-nonwork | subject-work |
#            subject-nonwork | bare-prefix
BEGIN {
    FS = "\x1f"; RS = "\x1e"
    # WORK types land code/tests. docs/chore/ci DOCUMENT or REGISTER an
    # item; they never constitute evidence that its work landed (c4).
    split("feat fix perf refactor test build style revert", w, " ")
    for (i in w) isw[w[i]] = 1
    # (c1) a verb that FILES an item, immediately before the id.
    split("file files filed filing register registers registered registering " \
          "record records recorded open opens opened reopen reopens reopened " \
          "track tracks tracked add adds added log logs logged " \
          "create creates created triage triaged", f, " ")
    for (i in f) isf[f[i]] = 1
}

# Expand a compact run "BOB-081/083/089" into one line per id. Both this
# spelling and the plain one are real in-repo (§11.4.201(7)(b): a needle
# that exercises only one spelling certifies only that one).
function emit(sha, cls, run,    n, parts, i, head) {
    n = split(run, parts, "/")
    head = parts[1]; sub("^" PFX "-", "", head)
    if (head !~ /^[0-9]+$/) return
    printf "%s\t%s\t%s-%s\n", sha, cls, PFX, head
    for (i = 2; i <= n; i++)
        if (parts[i] ~ /^[0-9]+$/) printf "%s\t%s\t%s-%s\n", sha, cls, PFX, parts[i]
}

# (c3) A line is QUOTED when it is indented (code/quote block) or begins
# with '>'. A commit that pastes another ticket's text must not be read as
# declaring that ticket. BOB-136's own body contains the literal string
# `closes BOB-076`; without this, echoing it would manufacture a finding.
function is_quoted_line(l) { return (l ~ /^[ \t]+/ || l ~ /^[ \t]*>/) }

# (c3, inline form) An id sitting INSIDE a "..." or `...` span is quoted
# text, not a declaration. Detected by parity of the delimiters seen so
# far on the line, which is robust to any number of spans. The apostrophe
# is deliberately NOT a delimiter here: English prose ("doesn\047t") would
# make its parity meaningless and turn this guard into a false-null.
function in_quoted_span(pre,    n) {
    n = gsub(/"/, "\"", pre); if (n % 2 == 1) return 1
    n = gsub(/\140/, "\140", pre); if (n % 2 == 1) return 1
    return 0
}

{
    sha = $1
    if (sha == "") next
    subj = $2; sub(/^subject:/, "", subj)
    body = $3; sub(/^body:/, "", body)

    # ── commit type + conventional-commit scope ──────────────────────
    type = ""; scope = ""; bareid = 0
    if (match(subj, /^[A-Za-z]+\([^)]*\):/)) {
        hdr = substr(subj, 1, RLENGTH)
        type = hdr; sub(/\(.*/, "", type)
        scope = hdr; sub(/^[A-Za-z]+\(/, "", scope); sub(/\):$/, "", scope)
    } else if (match(subj, /^[A-Za-z]+:/)) {
        type = substr(subj, 1, RLENGTH - 1)
    } else if (match(subj, "^" PFX "-[0-9]+(/[0-9]+)*:")) {
        bareid = 1
        emit(sha, "bare-prefix", substr(subj, 1, RLENGTH - 1))
    }
    work = (bareid || (tolower(type) in isw)) ? 1 : 0

    # ── SCOPE ids ────────────────────────────────────────────────────
    if (scope != "") {
        gsub(/[,+]/, " ", scope)
        n = split(scope, st, " ")
        for (i = 1; i <= n; i++) {
            t = st[i]
            # real in-repo suffixed spellings: BOB-111-followup, BOB-122-fallout
            sub(/-[A-Za-z][A-Za-z0-9]*$/, "", t)
            if (t ~ "^" PFX "-[0-9]+(/[0-9]+)*$")
                emit(sha, (work ? "scope-work" : "scope-nonwork"), t)
        }
    }

    # ── CLOSURE-KEYWORD ids, scanned over the WHOLE message ──────────
    # Only the keyword-adjacent form is taken from the body; a bare
    # mention in body prose is far too weak to be evidence.
    nl = split(subj "\n" body, lines, "\n")
    for (li = 1; li <= nl; li++) {
        line = lines[li]
        if (is_quoted_line(line)) continue            # (c3)
        s = line; sofar = ""
        while (match(s, /[Cc]los(e|es|ed|ing)|[Ff]ix(es|ed)?|[Rr]esolv(e|es|ed)/)) {
            pre  = substr(s, 1, RSTART - 1)
            rest = substr(s, RSTART + RLENGTH)
            # (c3) an inline-quoted phrase: `closes BOB-076` inside quotes
            if (!in_quoted_span(sofar pre) && \
                match(rest, "^[ :]+" PFX "-[0-9]+(/[0-9]+)*")) {
                r = substr(rest, 1, RLENGTH); sub(/^[ :]+/, "", r)
                emit(sha, "closes", r)
            }
            sofar = sofar substr(s, 1, length(s) - length(rest))
            s = rest
        }
    }

    # ── SUBJECT-PROSE ids (outside the scope header) ─────────────────
    ss = subj
    sub(/^[A-Za-z]+\([^)]*\):/, "", ss)
    sub("^" PFX "-[0-9]+(/[0-9]+)*:", "", ss)
    s2 = ss; sofar2 = ""
    while (match(s2, PFX "-[0-9]+(/[0-9]+)*")) {
        pre = substr(s2, 1, RSTART - 1)
        idr = substr(s2, RSTART, RLENGTH)
        s2  = substr(s2, RSTART + RLENGTH)
        quoted_here = in_quoted_span(sofar2 pre)
        sofar2 = sofar2 pre idr
        # (c3) the id is inside a "..." / `...` span -> quoted text
        if (quoted_here) continue
        lastch = (length(pre) > 0) ? substr(pre, length(pre), 1) : " "
        # (c2) path component, or glued into a longer token
        if (lastch == "/" || lastch ~ /[A-Za-z0-9_]/) continue
        # (c1) a filing verb immediately before the id
        pw = pre; gsub(/[^A-Za-z ]/, " ", pw)
        nw = split(pw, wa, " ")
        if (nw > 0 && (tolower(wa[nw]) in isf)) continue
        emit(sha, (work ? "subject-work" : "subject-nonwork"), idr)
    }
}
AWK_EOF
}

# ─── DB snapshot: id -> status (READ-ONLY) ───────────────────────────
_load_db() {
    sqlite3 -separator $'\t' "file:$DB?mode=ro" \
        "SELECT DISTINCT atm_id, status FROM items;" > "$TMPD/db.tsv" 2>"$TMPD/db.err"
}

# ─── classify links into findings ────────────────────────────────────
# stdin: links.tsv (sha \t class \t id)  ->  findings.tsv
#        (severity \t id \t status \t class \t short-sha)
_classify() {
    awk -F'\t' '
    NR == FNR { st[$1] = $2; next }
    NF != 3 { next }
    {
        sha = substr($1, 1, 7); cls = $2; id = $3
        if (!(id in st)) { print "UNTRACKED-ID\t" id "\t(no row)\t" cls "\t" sha; next }
        s = st[id]
        terminal = (s ~ /Fixed\.md\)$/)
        if (terminal) next
        if (cls == "closes") { print "CONTRADICTION\t" id "\t" s "\t" cls "\t" sha; next }
        # Queued asserts "no work started"; a WORK commit refutes exactly that.
        if (s == "Queued" && (cls == "scope-work" || cls == "subject-work" || cls == "bare-prefix"))
            print "UNRECONCILED\t" id "\t" s "\t" cls "\t" sha
    }' "$TMPD/db.tsv" -
}

_remediation() {
    local id="$1"
    cat >&2 <<REM
      remediate ${id} with ONE of:
        constitution/scripts/workable-items/workable-items update --id ${id} \\
            --db docs/workable_items.db --status "In progress"
        constitution/scripts/workable-items/workable-items close ${id} \\
            --db docs/workable_items.db --status fixed --evidence <path>
      then regenerate + stage the trackers:
        bash scripts/workable-items-export.sh
REM
}

# ─── CHECK B: no caller may use the false-null flagless `diff` form ──
# BOB-136 acceptance (b). `workable-items diff --db X` WITHOUT
# --issues/--fixed opens zero Markdown files and still prints
# "DB and Markdown are in sync" — a §11.4.201(6) FALSE-NULL: a blind
# check and a clean tree return the identical quiet zero. Until the
# shared engine refuses that invocation, no CALLER here may use it.
# Scanned over EXECUTABLE tracked files only: docs and the tracker DB
# legitimately QUOTE the flagless form (this gate's own header does),
# and matching those would be the carrier mistake this gate is about.
_check_flagless_diff_callers() {
    local hits=0
    while IFS= read -r f; do
        [[ -f "$REPO/$f" ]] || continue
        awk -v FN="$f" '
        # A COMMENT is not a caller. This gate\047s own header quotes the
        # flagless form; matching it would be the exact carrier mistake
        # (§11.4.201(7)(a)) this whole file is about.
        { line = $0 }
        line ~ /^[[:space:]]*#/ { next }
        # A real invocation ALWAYS passes --db. That single structural
        # requirement removes every `echo "... workable-items diff ..."`
        # progress/report string in the tree (measured: 3 such carriers in
        # scripts/hooks/docs-sync-commit-seam.sh alone).
        line !~ /--db/ { next }
        {
            # locate the invocation token: <binary-ref> WS diff WS
            # The SURROUNDING quoting is part of the match, so the ubiquitous
            # shell idiom `"$WI_BIN" diff` leaves an EMPTY prefix. Anchoring
            # after the opening quote instead made that idiom look like it
            # sat inside a string literal and silently skipped every real
            # caller — a §11.4.201(6) false-null the meta-test (bad-6)
            # caught; this anchor is the fix.
            if (!match(line, /["]?[$]?[{]?(workable-items|WI_BIN)[}]?["]?[[:space:]]+diff[[:space:]]/)) next
            pre = substr(line, 1, RSTART - 1)
            # an ODD number of quotes before the match means the invocation
            # text sits inside an open string literal -> `echo "... diff ..."`,
            # a mention, not a call.
            n = gsub(/"/, "\"", pre); if (n % 2 == 1) next
            if (line ~ /--issues/ && line ~ /--fixed/) next
            printf "  FLAGLESS-DIFF-CALLER: %s:%d: %s\n", FN, FNR, line > "/dev/stderr"
            c++
        }
        END { exit (c > 0 ? 1 : 0) }
        ' "$REPO/$f" || hits=$((hits + 1))
    done < <(cd "$REPO" && git ls-files '*.sh' '*.bash' '*.py' '*.go' 2>/dev/null || true)
    return "$((hits > 0 ? 1 : 0))"
}

# ═══════════════════════════════════════════════════════════════════════
#  §11.4.107(10) SELF-TEST — golden-good / golden-bad / carrier control
# ═══════════════════════════════════════════════════════════════════════
# A checker never observed FAILING is unvalidated instrumentation
# (§11.4.115(F)). This drives the SHIPPING extractor over hermetic
# messages with known outcomes: every spelling that must be SEEN, and
# every carrier that must NOT be.
_self_test() {
    TMPD="$(mktemp -d -t closure_seam_selftest.XXXXXX)"
    _write_extractor
    local fails=0

    # id \t message  — expected classes are asserted below
    _link() {  # $1 = message ; prints "class:id" lines
        printf 'SELFTEST%ssubject:%s%sbody:%s\x1e' $'\x1f' "$1" $'\x1f' "${2:-}" \
            | awk -v PFX="$PREFIX" -f "$TMPD/extract.awk" \
            | awk -F'\t' 'NF==3{print $2":"$3}' | sort -u | paste -sd, -
    }
    _expect() {  # $1 label  $2 message  $3 body  $4 expected(csv, "" = none)
        local got; got="$(_link "$2" "$3")"
        if [[ "$got" == "$4" ]]; then
            printf '  ok   %-46s -> %s\n' "$1" "${got:-<none>}"
        else
            printf '  FAIL %-46s -> got [%s] want [%s]\n' "$1" "${got:-<none>}" "${4:-<none>}" >&2
            fails=$((fails + 1))
        fi
    }

    echo "[$SCRIPT_NAME] §11.4.107(10) self-test — extractor golden set"
    echo "  --- GOLDEN-BAD: each MUST be seen (a miss here = a blind query) ---"
    _expect "scope, work type"            "fix(002,${PREFIX}-144): x" "" "scope-work:${PREFIX}-144"
    _expect "scope, sole token"           "perf(${PREFIX}-145): x"    "" "scope-work:${PREFIX}-145"
    _expect "scope, suffixed spelling"    "fix(${PREFIX}-111-followup): x" "" "scope-work:${PREFIX}-111"
    _expect "scope, compact run"          "docs(${PREFIX}-124/125): x" "" \
            "scope-nonwork:${PREFIX}-124,scope-nonwork:${PREFIX}-125"
    _expect "bare-id subject prefix"      "${PREFIX}-105: build the checker" "" "bare-prefix:${PREFIX}-105"
    _expect "subject prose, work type"    "feat(002): repair + ${PREFIX}-148 — note" "" "subject-work:${PREFIX}-148"
    _expect "closure keyword"             "fix(q): fan-out closes ${PREFIX}-076" "" \
            "closes:${PREFIX}-076,subject-work:${PREFIX}-076"
    _expect "closure keyword, compact run" "fix(q): closes ${PREFIX}-081/083" "" \
            "closes:${PREFIX}-081,closes:${PREFIX}-083,subject-work:${PREFIX}-081,subject-work:${PREFIX}-083"
    _expect "closure keyword in body"     "fix(q): tidy" "Closes: ${PREFIX}-113" "closes:${PREFIX}-113"

    echo "  --- CARRIER CONTROLS: each MUST NOT be seen (a hit = a false positive) ---"
    _expect "c1 filing verb"              "docs(tracker): file ${PREFIX}-149 — diverges" "" ""
    _expect "c1 filing verb, work type"   "test(x): register ${PREFIX}-150 for later" "" ""
    _expect "c2 path component"           "fix(x): refresh docs/qa/${PREFIX}-117/evidence.md" "" ""
    _expect "c3 quoted closure phrase"    "docs(x): its message says \"closes ${PREFIX}-076\"" "" ""
    _expect "c3 quoted id, WORK type"     "fix(x): the ticket quotes \"closes ${PREFIX}-076\" verbatim" "" ""
    _expect "c3 backtick-quoted id"       "fix(x): grep for \140${PREFIX}-076\140 in the corpus" "" ""
    _expect "c3 indented pasted ticket"   "docs(x): paste ticket" "    fix(a): closes ${PREFIX}-076" ""
    _expect "c3 '>'-quoted ticket line"   "docs(x): paste ticket" "> closes ${PREFIX}-076" ""
    _expect "plain prose, no id"          "chore(x): routine tidy-up" "" ""

    echo "  --- CLASSIFIER polarity (golden-good must NOT be flagged) ---"
    printf '%s\tQueued\n%s\tFixed (\xe2\x86\x92 Fixed.md)\n%s\tIn progress\n' \
        "${PREFIX}-901" "${PREFIX}-902" "${PREFIX}-903" > "$TMPD/db.tsv"
    local out
    out="$(printf 'aaaaaaa\tscope-work\t%s\n' "${PREFIX}-902" | _classify || true)"
    if [[ -z "$out" ]]; then echo "  ok   terminal row + work commit -> no finding"
    else echo "  FAIL terminal row was flagged: $out" >&2; fails=$((fails + 1)); fi
    out="$(printf 'aaaaaaa\tscope-work\t%s\n' "${PREFIX}-903" | _classify || true)"
    if [[ -z "$out" ]]; then echo "  ok   'In progress' row + work commit -> no finding"
    else echo "  FAIL 'In progress' row was flagged: $out" >&2; fails=$((fails + 1)); fi
    out="$(printf 'aaaaaaa\tscope-nonwork\t%s\n' "${PREFIX}-901" | _classify || true)"
    if [[ -z "$out" ]]; then echo "  ok   c4 docs-type commit + Queued row -> no finding"
    else echo "  FAIL docs-type commit was flagged: $out" >&2; fails=$((fails + 1)); fi
    out="$(printf 'aaaaaaa\tscope-work\t%s\n' "${PREFIX}-901" | _classify || true)"
    if [[ "$out" == UNRECONCILED* ]]; then echo "  ok   Queued row + work commit -> UNRECONCILED"
    else echo "  FAIL Queued row was NOT flagged (blind classifier): [$out]" >&2; fails=$((fails + 1)); fi
    out="$(printf 'aaaaaaa\tcloses\t%s\n' "${PREFIX}-903" | _classify || true)"
    if [[ "$out" == CONTRADICTION* ]]; then echo "  ok   'closes' + non-terminal row -> CONTRADICTION"
    else echo "  FAIL closure contradiction NOT flagged: [$out]" >&2; fails=$((fails + 1)); fi

    echo
    if [[ "$fails" -eq 0 ]]; then
        echo "[$SCRIPT_NAME] SELF-TEST PASS — extractor sees every spelling, ignores every carrier"
        return 0
    fi
    echo "[$SCRIPT_NAME] SELF-TEST FAIL — $fails case(s) diverged" >&2
    return 1
}

# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "selftest" ]]; then
    _self_test
    exit $?
fi

if [[ ! -d "$REPO/.git" ]] && ! (cd "$REPO" 2>/dev/null && git rev-parse --git-dir >/dev/null 2>&1); then
    echo "ERROR($SCRIPT_NAME): not a git repository: $REPO" >&2; exit 2
fi
if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "SKIP(§11.4.3): sqlite3 unavailable — closure seam NOT checked." >&2
    echo "  An unreadable tracker is not evidence of drift (§11.4.201(1))." >&2
    exit 0
fi
TMPD="$(mktemp -d -t closure_seam.XXXXXX)"
_write_extractor

# CHECK A needs a readable, non-empty tracker. Its unavailability is an
# honest §11.4.3 SKIP — an unreadable tracker is not evidence of drift —
# but it MUST NOT disable CHECK B, which is a property of the REPOSITORY
# and needs no tracker at all. Sequencing those the other way round is how
# a gate acquires a §11.4.201(6) false-null; this gate's own meta-test
# (fixture bad-6) caught exactly that and this ordering is the fix.
A_ENABLED=1
A_SKIP_REASON=""
if [[ ! -f "$DB" ]]; then
    A_ENABLED=0; A_SKIP_REASON="workable-items DB absent at $DB"
elif ! _load_db; then
    A_ENABLED=0; A_SKIP_REASON="could not read $DB"
else
    DB_ROWS="$(wc -l < "$TMPD/db.tsv" | tr -d ' ')"
    if [[ "$DB_ROWS" -eq 0 ]]; then
        A_ENABLED=0; A_SKIP_REASON="$DB holds zero items — nothing to reconcile against"
    fi
fi
if [[ "$A_ENABLED" -eq 0 && "$MODE" == "commit-seam" ]]; then
    echo "SKIP(§11.4.3): $A_SKIP_REASON — closure seam NOT checked." >&2
    exit 0
fi

# ── gather links ─────────────────────────────────────────────────────
if [[ "$MODE" == "commit-seam" ]]; then
    if [[ -n "$MSG_FILE" ]]; then
        [[ -f "$MSG_FILE" ]] || { echo "ERROR($SCRIPT_NAME): no such message file: $MSG_FILE" >&2; exit 2; }
        MSG_TEXT="$(cat "$MSG_FILE")"
    fi
    SUBJ="$(printf '%s\n' "$MSG_TEXT" | head -n 1)"
    BODY="$(printf '%s\n' "$MSG_TEXT" | tail -n +2)"
    printf 'PENDING%ssubject:%s%sbody:%s\x1e' $'\x1f' "$SUBJ" $'\x1f' "$BODY" \
        | awk -v PFX="$PREFIX" -f "$TMPD/extract.awk" > "$TMPD/links.tsv"
    SCOPE_LABEL="pending commit message"
else
    (cd "$REPO" && git log ${REV_RANGE:+"$REV_RANGE"} --format="%H%x1fsubject:%s%x1fbody:%b%x1e") \
        | awk -v PFX="$PREFIX" -f "$TMPD/extract.awk" > "$TMPD/links.tsv"
    SCOPE_LABEL="git history${REV_RANGE:+ ($REV_RANGE)}"
fi

LINKS="$(awk -F'\t' 'NF==3' "$TMPD/links.tsv" | sort -u | tee "$TMPD/links.sorted" | wc -l | tr -d ' ')"
: > "$TMPD/findings.tsv"
if [[ "$A_ENABLED" -eq 1 ]]; then
    _classify < "$TMPD/links.sorted" | sort -u > "$TMPD/findings.tsv"
fi

echo "[$SCRIPT_NAME] CM-CLOSURE-SEAM-BINDS — scope: $SCOPE_LABEL"
if [[ "$A_ENABLED" -eq 1 ]]; then
    echo "  tracker rows read (read-only) ... $DB_ROWS"
    echo "  structural commit<->item links .. $LINKS"
fi

# §11.4.201(7)(b) CONTROL NEEDLE. A zero-finding verdict is worthless if
# the extractor is blind: a blind query and a genuinely clean tree return
# the identical quiet zero. The needle carries the SAME load-bearing
# features as the real query (scope form, bare-id form, compact run,
# closure keyword) — a bare-literal needle would certify only a literal.
if [[ "$A_ENABLED" -eq 1 ]]; then
NEEDLE_OUT="$(printf 'NEEDLE%ssubject:%s%sbody:%s\x1e' $'\x1f' \
    "fix(x,${PREFIX}-901/902): closes ${PREFIX}-903" $'\x1f' "" \
    | awk -v PFX="$PREFIX" -f "$TMPD/extract.awk" | awk -F'\t' 'NF==3' | wc -l | tr -d ' ')"
if [[ "$NEEDLE_OUT" -lt 4 ]]; then
    echo "ERROR($SCRIPT_NAME): CONTROL NEEDLE FAILED — extractor saw $NEEDLE_OUT/4 known links." >&2
    echo "  The instrument is blind; its zero is NOT evidence (§11.4.201(7)(b))." >&2
    exit 2
fi
echo "  control needle (§11.4.201(7)(b)) . PASS ($NEEDLE_OUT/4 known links seen)"
fi

N_CONTRA="$(awk -F'\t' '$1=="CONTRADICTION"{print $2}' "$TMPD/findings.tsv" | sort -u | wc -l | tr -d ' ')"
N_UNREC="$(awk -F'\t'  '$1=="UNRECONCILED"{print $2}'  "$TMPD/findings.tsv" | sort -u | wc -l | tr -d ' ')"
N_UNTRK="$(awk -F'\t'  '$1=="UNTRACKED-ID"{print $2}'  "$TMPD/findings.tsv" | sort -u | wc -l | tr -d ' ')"
N_STALE="$(awk -F'\t' '$1!="UNTRACKED-ID"{print $2}'   "$TMPD/findings.tsv" | sort -u | wc -l | tr -d ' ')"

RC=0
if [[ "$A_ENABLED" -eq 0 ]]; then
    echo "  CHECK A closure seam .............. SKIP (§11.4.3)"
    echo "SKIP(§11.4.3): $A_SKIP_REASON — CHECK A not run." >&2
elif [[ "$N_CONTRA" -gt 0 || "$N_UNREC" -gt 0 || "$N_UNTRK" -gt 0 ]]; then
    RC=1
    echo "  CHECK A closure seam .............. FAIL"
    {
        echo
        echo "CM-CLOSURE-SEAM-BINDS: work landed whose tracked row did not move."
        echo
    } >&2
    for sev in CONTRADICTION UNRECONCILED UNTRACKED-ID; do
        awk -F'\t' -v S="$sev" '$1==S' "$TMPD/findings.tsv" | sort -u -k2,2 > "$TMPD/sev.tsv" || true
        [[ -s "$TMPD/sev.tsv" ]] || continue
        case "$sev" in
            CONTRADICTION) echo "  [$sev] a commit says it CLOSES the item; the row says otherwise." >&2 ;;
            UNRECONCILED)  echo "  [$sev] the row says 'Queued' (no work started); a work commit refutes that." >&2 ;;
            UNTRACKED-ID)  echo "  [$sev] a commit declares an id that has NO row in the tracker." >&2 ;;
        esac
        local_seen=""
        while IFS=$'\t' read -r _s id status cls sha; do
            printf '    %-9s status=%-24s via %-14s commit %s\n' "$id" "$status" "$cls" "$sha" >&2
            case " $local_seen " in *" $id "*) ;; *) local_seen="$local_seen $id" ;; esac
        done < "$TMPD/sev.tsv"
        if [[ "$sev" != "UNTRACKED-ID" ]]; then
            for id in $local_seen; do _remediation "$id"; break; done
        else
            echo "      remediate: file the missing item, or correct the id in a follow-up note." >&2
            echo "      (history is never rewritten for this — §11.4.113)" >&2
        fi
        echo >&2
    done
    echo "  ${N_STALE} stale row(s), ${N_UNTRK} untracked id(s)." >&2
else
    echo "  CHECK A closure seam .............. PASS (0 stale rows)"
fi

# CHECK B runs only in sweep mode — it is a repo property, not a property
# of the pending commit message.
if [[ "$MODE" == "sweep" ]]; then
    if _check_flagless_diff_callers; then
        echo "  CHECK B flagless-diff callers ..... PASS (0 callers of the false-null form)"
    else
        RC=1
        echo "  CHECK B flagless-diff callers ..... FAIL"
        echo "  Add --issues docs/Issues.md --fixed docs/Fixed.md to each caller above:" >&2
        echo "  without them 'diff' opens ZERO Markdown files and still prints" >&2
        echo "  'DB and Markdown are in sync' (§11.4.201(6) false-null)." >&2
    fi
fi

if [[ "$VERBOSE" -eq 1 && -s "$TMPD/findings.tsv" ]]; then
    echo "  --- all findings (verbose) ---"
    sed 's/^/    /' "$TMPD/findings.tsv"
fi

if [[ "$REPORT_ONLY" -eq 1 && "$RC" -ne 0 ]]; then
    echo "  (--report-only: findings above are NOT blocking)"
    exit 0
fi
exit "$RC"
