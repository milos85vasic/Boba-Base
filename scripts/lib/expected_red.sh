#!/usr/bin/env bash
# expected_red.sh — the EXPECTED-RED declaration mechanism for bash suites
#                   (BOB-221; §11.4.115 / §11.4.135 / §11.4.224 / §11.4.248)
#
# PURPOSE
#   Pre-build invariant 30 (CM-BASH-UNIT-TESTS-EXECUTED) asserts "no bash suite
#   fails". The invariant it SHOULD assert is "no bash suite fails
#   UNEXPECTEDLY". Those differ the moment the constitution's own test-first
#   discipline is followed: §11.4.224 requires the RED to be written and
#   observed failing BEFORE the fix, and §11.4.135 requires that guard to
#   PERSIST — so a correctly-authored, still-open RED is a permanent, intended
#   failure that today's gate counts as a defect and refuses the build on.
#   That is a §11.4.120 wrong-seam refusal and a §11.4.201(1) FAIL-bluff.
#
#   This library supplies what the bash side lacked: a way to DECLARE that a
#   named suite is supposed to fail, which is honoured ONLY while the
#   declaration is corroborated, current, and accurate — and which BLOCKS the
#   moment it stops being any of those.
#
# PARITY, NOT A NEW BAR (§11.4.227 — extend what exists, never restate it)
#   The Python side already runs this exact discipline via
#   `pytest.mark.xfail(strict=True, reason=...)`, used at
#   tests/scaling/test_scaling_envelope.py (BOB-167) and
#   tests/stress/test_plugin_parsers_stress_chaos.py (rutracker ReDoS).
#   `strict=True` is the load-bearing half: an XPASS (a declared-red test that
#   unexpectedly PASSES) FAILS, which forces the declaration's removal. A
#   declaration that never expires is a permanent bluff licence, so the bash
#   side is held to the SAME self-clearing bar.
#
# NOT QUARANTINE. `BASH_TEST_QUARANTINE` (pre_build_verification.sh) EXCLUDES a
#   suite — it is never executed and its verdict is never observed. A DECLARED
#   RED is still RUN, and its exit code is still checked; the declaration only
#   changes what the gate concludes from an observed failure. Solving BOB-221
#   by widening quarantine would have traded a false refusal for a false null
#   (§11.4.201(6)) — the strictly worse outcome.
#
# ROWS KEY ON THE REPO-RELATIVE PATH, NEVER ON A BASENAME
#   (round-2 remediation of the round-1 review's BLOCKING-1 finding.)
#   The gate's glob spans THREE directories — tests/unit, tests/pre_build and
#   tests/hooks — so a basename does not identify a file. Keying on one let a
#   single reviewed row silence EVERY same-basename suite in the tree, and let
#   an author land a NEW failing suite at a second path, copy the one-line
#   marker, and be silenced with ZERO table review. That is exactly the
#   producer-alone channel §11.4.240/§11.4.249 exist to close, so the basename
#   no longer reaches the verdict at all: `expected_red_verdict` takes the
#   suite PATH and matches on `${path#${PROJECT_ROOT}/}`.
#   MEASURED before the fix (extracted invariant-30 loop, one row
#   `test_zz_bt.sh BOB-207`): two same-basename failing suites -> RAN=2
#   FAILED=0 HONOURED=2; and with the declared file DELETED, the
#   never-reviewed sibling alone -> RAN=1 FAILED=0 HONOURED=1.
#
# THE TABLE HAS ITS OWN FRESHNESS CONTRACT (§11.4.226)
#   P3 (item closed) and P4 (XPASS) are only ever evaluated when the declared
#   suite RUNS. A row whose suite was deleted, renamed, quarantined or is
#   self-recursive is therefore NEVER judged: it cannot stale out and it
#   cannot XPASS out, so it rots silently and stays ARMED. `expected_red_sweep`
#   /`expected_red_unmatched_rows` closes that: every row must have been
#   evaluated this run, or it blocks. MEASURED before the fix: a row naming an
#   absent suite, alongside two real failures -> RAN=2 FAILED=2 and the ghost
#   row neither blocked nor warned.
#
# THE FULL BOUNDARY LIST — every way a declaration can fail to be judged, and
# what happens now, is enumerated in docs/scripts/expected_red.md ("Boundary
# cases"). It lives in the repository, not in a session report, because a
# document that BINDS behaviour must be tracked where the work happens
# (§11.4.215).
#
# THE EIGHTEEN PROPERTIES (fixed by BOB-221 + the round-1 and round-3
# independent reviews;
# asserted by tests/pre_build/test_bob221_expected_red_declaration.sh)
#   P1   a DECLARED red that FAILS does not block.
#   P2   an UNDECLARED failing suite STILL blocks.   <- the load-bearing guard
#   P3   a DECLARED red whose tracked item is CLOSED blocks, naming the rot.
#   P4   a DECLARED red that PASSES blocks (strict-xfail parity).
#   P5   a declaration not corroborated by the file's own in-source marker
#        blocks (two-place agreement).
#   P6   a declaration binds to the FILE — a same-basename suite in another
#        globbed directory is NOT excused.
#   P7   a row that matched NO executed suite this run blocks.
#   P8   a DECLARED red that ABORTS (exit 3) blocks.
#   P9   a DECLARED red whose item is any of §11.4.33's FOUR terminal statuses
#        blocks as stale — not merely the `Fixed` form.
#   P10  a row with more than two fields blocks.
#   P11  an item whose stored status is EMPTY blocks WITHOUT being asserted
#        CLOSED (a class that was never derived is never claimed).
#   P12  a declaration whose suite carries NO marker at all blocks, naming the
#        two-place agreement (the ABSENT half of P5, which round 3 found was
#        surviving only by an unrelated `set -u` accident).
#   P13  the path match is EXACT: a row for tests/unit/x.sh does not excuse
#        tests/unit/x.sh.sh. A PREFIX match would silently re-open the
#        basename defect while every other scenario stayed green.
#   P14  an inline/trailing `# EXPECTED-RED:` mention is NOT a marker — the
#        pattern's left anchor is load-bearing and is pinned on the REASON.
#   P15  a bare-basename row is refused BY THE SWEEP when it matches nothing.
#   P16  an unmatched row with more than two fields is refused by the sweep.
#   P17  an unmatched row with a malformed item id is refused by the sweep.
#   P18  two rows naming one path block as ambiguous, counted ONCE.
#
# TWO-PLACE AGREEMENT (§11.4.240 / §11.4.249 producer separation)
#   Silencing a failure requires TWO independent places to agree:
#     (a) a row in BASH_TEST_EXPECTED_RED below — reviewed at the gate, and
#     (b) an in-source `# EXPECTED-RED: <ITEM-ID>` marker in the suite itself.
#   Neither the suite author alone nor the table alone can silence anything.
#   A marker with NO table row is inert (the table is the authority); a table
#   row with no/ mismatched marker BLOCKS.
#
# FAIL-CLOSED ON AMBIGUITY (§11.4.252)
#   Every unresolvable input REFUSES rather than defaulting to "declared":
#   an unparseable id, a row that is not a repo-relative suite path, a row
#   with more than two fields, a duplicate table row, an absent/duplicate/
#   mismatched marker, an item id absent from the store, an item row whose
#   status is empty, an unreadable store, a failing query tool, an absent
#   query tool, an out-of-set item status, a row that matched no executed
#   suite, and any exit code that is not the declared RED verdict.
#
# EXIT-CODE CONTRACT — a declaration honours EXIT 1 AND NOTHING ELSE.
#   0        the suite PASSED         -> XPASS, BLOCKS (§11.4.115(F) ratchet)
#   1        the suite's RED verdict  -> honoured while the declaration is valid
#   2,3,124  abort / crash / timeout  -> NOT a verdict, BLOCKS
#   ...      any other non-zero       -> NOT a verdict, BLOCKS
#   Rationale (§11.4.201(6)): a suite that ABORTS reports that its instrument
#   was BLIND, and a blind instrument's silence is never evidence. Sibling
#   suites reserve exit 3 for exactly that (tests/pre_build/
#   test_bob205_danger_roots_scope.sh). Swallowing an abort as "the expected
#   red" would convert a blind instrument into a green one — the precise bluff
#   this mechanism exists to prevent.
#
# Usage        : sourced by scripts/pre_build_verification.sh (invariant 30).
#                Not executable standalone; it defines functions and data only.
# Inputs       : ${PROJECT_ROOT}/docs/workable_items.db  (READ-ONLY; the
#                §11.4.93/§11.4.95 single source of truth for item status —
#                never a hand-maintained parallel list of open tickets)
#                the suite file itself (read-only, for its marker)
# Outputs      : one verdict token per call on stdout (see expected_red_verdict)
# Side-effects : NONE on any tracked file. The item store is opened read-only
#                via a `mode=ro` URI, which CANNOT write by construction —
#                measured 2026-08-27 on a scratch copy of the real WAL-mode
#                store: an UPDATE through such a connection raises
#                `OperationalError: attempt to write a readonly database`.
#                That matters because docs/workable_items.db IS tracked
#                (`git ls-files --error-unmatch` succeeds), so it IS inside
#                invariant 30's own NO-TRACE corpus, and a real write would be
#                caught there as a §11.4.84 quiescence violation.
#                MEASURED, and NOT the reason (§11.4.6 — an earlier revision
#                of this header gave a sidecar-based rationale that is refuted
#                in both directions): on a WAL-mode store BOTH a read-write
#                and a `mode=ro` open create `-wal`/`-shm` sidecars while the
#                connection is open; the read-write open REMOVES them on a
#                clean close and the read-only open LEAVES them behind. Either
#                way they are invisible to the NO-TRACE scan, which enumerates
#                TRACKED paths only — the sidecars are untracked and gitignored
#                (.gitignore `docs/*.db-wal`, `docs/*.db-shm`). Neither open
#                mode moved the `.db` file's own mtime; 12 uncached real
#                `mode=ro` reads through this library left the real store's
#                mtime ns-identical.
#                No network, no container, no signal delivery (§11.4.263), no
#                host power-state change (CONST-033).
# Depends      : bash >= 4.2 (associative arrays), sed, grep; and EITHER
#                python3 (sqlite3 module, preferred) OR the sqlite3 CLI.
# Refs         : BOB-221; §11.4.115(F), §11.4.120, §11.4.135, §11.4.201(1)(6),
#                §11.4.215, §11.4.224, §11.4.226, §11.4.227, §11.4.240,
#                §11.4.248, §11.4.249, §11.4.252.
# See also     : docs/scripts/expected_red.md

# ---------------------------------------------------------------------------
# THE DECLARATION TABLE  (§11.4.35 — consumer-owned DATA, never engine code)
#
# Rows are "<repo-relative-suite-path> <ITEM-ID>", EXACTLY two fields. A row is
# honoured ONLY when every check below passes. This table is a RATCHET in the
# §11.4.135/§11.4.248 sense: it must only SHRINK. Adding a row is a deliberate,
# reviewable act that says "this suite is supposed to fail, and here is the
# open item that says why"; the mechanism then forces the row OUT the moment
# the item closes (P3), the suite starts passing (P4), or the suite stops
# being executed at all (P7).
#
# THE KEY IS A PATH, NOT A BASENAME. `tests/unit/test_x.sh`, never
# `test_x.sh` — a bare basename is REFUSED, because the glob spans three
# directories and a basename cannot identify a file (see the header).
#
# EMPTY BY DEFAULT, DELIBERATELY. An empty table means invariant 30 blocks on
# exactly the same set of failures it blocked on before this library landed
# (P2 holds absolutely, and the post-loop sweep emits nothing), so landing the
# mechanism silences nothing by itself. Every silence is opt-in, two-place,
# and self-expiring.
#
# CANDIDATES MEASURED 2026-08-27 — each still needs its in-source marker added
# (the (b) half of the two-place agreement) before its row can be enabled;
# adding that marker to a suite is a separate, deliberate edit to that suite:
#   "tests/pre_build/test_bob205_danger_roots_scope.sh BOB-205"  # rc=1, Queued
# The tests/unit/test_ownership_gid_agreement.sh (BOB-207) candidate was DROPPED
# 2026-08-27: that suite now exits 0 (re-measured), so enabling its row would be
# an immediate XPASS block. A candidate comment that no longer holds is stale
# guidance, and stale guidance in a mechanism that exists to prevent rot is
# exactly the wrong thing to leave lying around.
# test_bob221_expected_red_declaration.sh (BOB-221) MUST NOT be listed: once
# this library lands that suite PASSES, so a row for it would be an XPASS and
# would block (P4). It no longer carries a marker either — retaining one while
# the suite is green is a latent XPASS trap.
BASH_TEST_EXPECTED_RED=()

# Counters + the note the blocking message carries. Initialised HERE, at source
# time, so the extracted-loop harness in the BOB-221 suite (which sources this
# file before running the real loop text) never trips `set -u`.
BASH_TEST_XRED_HONOURED=0
BASH_TEST_STALE_NOTE=""

# Cache key is the item id ALONE, deliberately: the store path is derived from
# PROJECT_ROOT, which is fixed for the lifetime of a gate run, so (store, id)
# collapses to id. If a future consumer ever varies PROJECT_ROOT mid-process
# this must become a composite key — noted rather than pre-built (§11.4.6).
declare -gA _EXPECTED_RED_STATUS_CACHE=()

# Repo-relative paths of the suites the gate ACTUALLY EXECUTED this run. The
# gate loop writes it (never this library: `expected_red_verdict` is called
# inside a command substitution, so anything it assigned would be lost with
# the subshell). `expected_red_unmatched_rows` reads it to prove every table
# row was really evaluated.
declare -gA _EXPECTED_RED_SEEN=()

# ---------------------------------------------------------------------------
# expected_red_status_class <status-string>
#   Maps one workable-item status onto OPEN | CLOSED | UNKNOWN.
#   The terminal set is §11.4.33's type-aware closure vocabulary and has FOUR
#   members — `Fixed`, `Implemented`, `Completed`, `Obsolete` — all sharing the
#   "(-> Fixed.md)" suffix. Matching on that suffix rather than on any full
#   literal covers all four at once AND keeps this free of any assumption
#   about the UTF-8 arrow's encoding. Recognising only one of the four would
#   let a declaration rot into cover behind the other three (P9).
#   UNKNOWN is a REFUSAL, not a default: an out-of-set status means the store
#   moved under us, and guessing would be §11.4.6.
# ---------------------------------------------------------------------------
expected_red_status_class() {
    case "$1" in
        *"Fixed.md)")                                        echo "CLOSED" ;;
        "Queued"|"In progress"|"Ready for testing"|\
        "In testing"|"Reopened"|"Operator-blocked")           echo "OPEN" ;;
        *)                                                   echo "UNKNOWN" ;;
    esac
}

# ---------------------------------------------------------------------------
# expected_red_item_status <ITEM-ID>
#   Echoes the item's status line(s) from the workable-items store.
#   rc 0 = found (statuses on stdout, one per line)
#   rc 1 = the id is not in the store
#   rc 2 = the store or the query tool is unusable (message on stdout)
#
#   The store path is resolved from PROJECT_ROOT at CALL time, exactly as the
#   gate resolves every other path. No dedicated environment override exists,
#   deliberately: a new override would be a new bypass surface (§11.4.252).
# ---------------------------------------------------------------------------
expected_red_item_status() {
    local id="$1"

    # Shape-validate BEFORE the value reaches any subprocess. This call site is
    # a §11.4.252 dangerous combination (table-supplied input + exec), so the
    # guard is defence-in-depth even though the caller validates too.
    if [[ ! "${id}" =~ ^[A-Z][A-Z0-9]*-[0-9]+$ ]]; then
        echo "malformed item id"
        return 2
    fi

    local cached="${_EXPECTED_RED_STATUS_CACHE[${id}]:-}"
    if [[ -n "${cached}" ]]; then
        printf '%s' "${cached#*|}"
        return "${cached%%|*}"
    fi

    local db="${PROJECT_ROOT:-.}/docs/workable_items.db"
    local out="" rc=0

    if [[ ! -r "${db}" ]]; then
        out="workable-items store not readable at ${db}"
        rc=2
    elif command -v python3 >/dev/null 2>&1; then
        # The closing `)` sits AFTER the heredoc terminator on purpose: with it
        # on the opening line bash reports "unterminated here-document" and the
        # construct is fragile (measured 2026-08-27 via `bash -n`).
        out="$(python3 - "${db}" "${id}" 2>&1 <<'PYEOF'
import os, sqlite3, sys
from urllib.request import pathname2url

db, item = sys.argv[1], sys.argv[2]
try:
    # READ-ONLY by URI: the connection CANNOT write (a write raises
    # OperationalError), so this library can never move the tracked .db that
    # invariant 30's own NO-TRACE scan watches.
    con = sqlite3.connect("file:" + pathname2url(os.path.abspath(db)) + "?mode=ro", uri=True)
    rows = [r[0] for r in con.execute("SELECT status FROM items WHERE atm_id = ?", (item,))]
    con.close()
except Exception as exc:                      # noqa: BLE001 - reported, never swallowed
    sys.stderr.write("workable-items store error: %s" % exc)
    sys.exit(2)
if not rows:
    sys.exit(1)
sys.stdout.write("\n".join(rows))
PYEOF
)" || rc=$?
    elif command -v sqlite3 >/dev/null 2>&1; then
        # A zero-row SELECT exits 0 with EMPTY output; an open/SQL error exits
        # NON-ZERO. Mapping every non-zero to rc 1 would report a broken store
        # as "the id does not exist" — still blocking, but with the wrong cause
        # (§11.4.6). The two are therefore distinguished explicitly.
        out="$(sqlite3 -readonly "${db}" "SELECT status FROM items WHERE atm_id='${id}';" 2>&1)" || rc=$?
        if [[ "${rc}" -ne 0 ]]; then
            out="sqlite3 CLI failed (exit ${rc}) reading ${db}: ${out}"
            rc=2
        elif [[ -z "${out}" ]]; then
            rc=1
        fi
    else
        out="neither python3 nor the sqlite3 CLI is available to read ${db}"
        rc=2
    fi

    _EXPECTED_RED_STATUS_CACHE["${id}"]="${rc}|${out}"
    printf '%s' "${out}"
    return "${rc}"
}

# ---------------------------------------------------------------------------
# expected_red_row_shape_problem <row>
#   Shared row-shape validator. Echoes a human-readable problem and returns 0
#   when the row is malformed; returns 1 (printing nothing) when its shape is
#   fine. Used by BOTH the per-suite verdict and the post-loop sweep so a
#   malformed row is refused whether or not it happens to match a file.
# ---------------------------------------------------------------------------
expected_red_row_shape_problem() {
    local row="$1" rkey rid rextra
    read -r rkey rid rextra <<<"${row}"
    if [[ -n "${rextra:-}" ]]; then
        echo "expected-red table row '${row}' carries more than two fields — the format is exactly '<repo-relative-path> <ITEM-ID>' (fail-closed)"
        return 0
    fi
    if [[ ! "${rkey:-}" =~ ^tests/[A-Za-z0-9_./-]+\.sh$ ]] || [[ "${rkey}" == *".."* ]]; then
        echo "expected-red table row '${row}' does not name a repo-relative suite path (expected e.g. tests/unit/test_x.sh) — a bare basename cannot identify a file, because the gate's glob spans tests/unit, tests/pre_build and tests/hooks (fail-closed)"
        return 0
    fi
    if [[ ! "${rid:-}" =~ ^[A-Z][A-Z0-9]*-[0-9]+$ ]]; then
        echo "expected-red table row '${row}' carries item id '${rid:-}', which is not <PREFIX>-<N> (fail-closed)"
        return 0
    fi
    return 1
}

# ---------------------------------------------------------------------------
# expected_red_verdict <suite-path> <observed-exit-code>
#   The single entry point the gate loop calls, ONCE PER EXECUTED SUITE.
#   The suite's BASENAME is deliberately not a parameter: rows key on the
#   repo-relative path, so a basename never reaches this decision at all.
#   Always exits 0 and always prints EXACTLY ONE of:
#
#     UNDECLARED            no table row names this suite -> the gate applies
#                           its normal rule (non-zero exit blocks). P2.
#     HONOURED              a valid, corroborated, current declaration and the
#                           declared RED verdict was observed. P1.
#     BLOCK:<reason>        the failure must block, and <reason> says why. It
#                           reaches the operator verbatim in the gate's
#                           blocking message, so it names the remedy, never
#                           just the symptom. P3..P6 and P8..P11, and every
#                           fail-closed branch.
# ---------------------------------------------------------------------------
expected_red_verdict() {
    local path="$1" rc="$2"
    local rel="${path#"${PROJECT_ROOT:-.}/"}"
    local row rkey rid rextra id="" hits=0 shape=""

    for row in ${BASH_TEST_EXPECTED_RED[@]+"${BASH_TEST_EXPECTED_RED[@]}"}; do
        read -r rkey rid rextra <<<"${row}"
        [[ "${rkey:-}" = "${rel}" ]] || continue
        hits=$((hits + 1))
        id="${rid:-}"
        shape="$(expected_red_row_shape_problem "${row}")" || shape=""
    done

    # --- not declared: the gate's pre-existing rule applies untouched (P2) ---
    if [[ "${hits}" -eq 0 ]]; then
        echo "UNDECLARED"
        return 0
    fi

    # --- fail-closed: an ambiguous or unparseable declaration is not a licence
    if [[ "${hits}" -gt 1 ]]; then
        echo "BLOCK:ambiguous expected-red declaration — ${hits} table rows name ${rel}; keep exactly one (fail-closed)"
        return 0
    fi
    if [[ -n "${shape}" ]]; then
        echo "BLOCK:${shape}"
        return 0
    fi

    # --- P5: the suite's own in-source marker must corroborate the table -----
    # Anchored to the start of a comment line and to end-of-line, so the prose
    # mentions of the marker that any file documenting this mechanism contains
    # are NOT carriers (§11.4.201(7)(a) — match the thing, never a token that
    # mentions it). The match is TEXTUAL, so a marker-shaped line inside a
    # heredoc or a multi-line string DOES corroborate; that is documented in
    # docs/scripts/expected_red.md and is not independently exploitable — a
    # reviewed table row is still required.
    local -a markers=()
    if [[ -r "${path}" ]]; then
        mapfile -t markers < <(
            sed -nE 's/^[[:space:]]*#[[:space:]]*EXPECTED-RED:[[:space:]]*([A-Z][A-Z0-9]*-[0-9]+)[[:space:]]*$/\1/p' "${path}" 2>/dev/null \
            | sort -u
        )
    else
        echo "BLOCK:cannot read ${rel} to corroborate its expected-red declaration (fail-closed)"
        return 0
    fi
    if [[ "${#markers[@]}" -eq 0 ]]; then
        echo "BLOCK:expected-red declaration names ${id} but ${rel} carries no '# EXPECTED-RED: ${id}' marker — two places must agree (fail-closed)"
        return 0
    fi
    if [[ "${#markers[@]}" -gt 1 ]]; then
        echo "BLOCK:${rel} carries ${#markers[@]} conflicting '# EXPECTED-RED:' markers (${markers[*]}) — keep exactly one (fail-closed)"
        return 0
    fi
    if [[ "${markers[0]}" != "${id}" ]]; then
        echo "BLOCK:expected-red declaration names ${id} but ${rel}'s own marker names ${markers[0]} — two places disagree (fail-closed)"
        return 0
    fi

    # --- P3/P9: the declaration must still be backed by an OPEN tracked item -
    local statuses="" qrc=0
    statuses="$(expected_red_item_status "${id}")" || qrc=$?
    if [[ "${qrc}" -eq 1 ]]; then
        echo "BLOCK:expected-red declaration names ${id}, which does not exist in docs/workable_items.db (fail-closed)"
        return 0
    fi
    if [[ "${qrc}" -ne 0 ]]; then
        echo "BLOCK:cannot resolve ${id} in the workable-items store — ${statuses} (fail-closed)"
        return 0
    fi

    local st cls agg="CLOSED" nclass=0
    while IFS= read -r st; do
        [[ -n "${st}" ]] || continue
        nclass=$((nclass + 1))
        cls="$(expected_red_status_class "${st}")"
        case "${cls}" in
            OPEN)    agg="OPEN"; break ;;
            UNKNOWN) agg="UNKNOWN" ;;
        esac
    done <<<"${statuses}"

    # P11: nothing was classified, so no class may be asserted. The aggregate
    # SEEDS at CLOSED, and reporting that seed as a finding would state a cause
    # that was never derived (§11.4.6) — blocking is right, "it is CLOSED" is
    # not.
    if [[ "${nclass}" -eq 0 ]]; then
        echo "BLOCK:expected-red declaration names ${id}, whose stored status is EMPTY — no non-empty status line was returned, so nothing was classified and neither OPEN nor CLOSED may be asserted (fail-closed)"
        return 0
    fi
    if [[ "${agg}" = "UNKNOWN" ]]; then
        echo "BLOCK:expected-red declaration names ${id}, whose status is outside the §11.4.33 closed set ('${statuses//$'\n'/, }') (fail-closed)"
        return 0
    fi
    if [[ "${agg}" = "CLOSED" ]]; then
        echo "BLOCK:STALE expected-red declaration — ${id} is CLOSED ('${statuses//$'\n'/, }') but ${rel} is still declared red; remove the row and the marker"
        return 0
    fi

    # --- P4: strict-xfail. A declared red that passes forces de-declaration --
    if [[ "${rc}" -eq 0 ]]; then
        echo "BLOCK:XPASS — ${rel} is declared expected-red for ${id} but now PASSES; remove the row and the marker (strict-xfail, §11.4.115(F) ratchet)"
        return 0
    fi

    # --- P8: exit-code contract. Only the RED verdict (1) is the declared
    #         failure; an abort/crash/timeout is a BLIND instrument, and a
    #         blind instrument is never honoured (§11.4.201(6)).
    if [[ "${rc}" -ne 1 ]]; then
        echo "BLOCK:${rel} is declared expected-red for ${id} but exited ${rc}, not the RED verdict (exit 1) — an abort/crash/timeout is not an expected red (fail-closed)"
        return 0
    fi

    # --- P1: valid, corroborated, current, and the declared RED was observed -
    echo "HONOURED"
    return 0
}

# ---------------------------------------------------------------------------
# expected_red_unmatched_rows
#   The TABLE's own freshness contract (§11.4.226), run ONCE after the gate's
#   suite loop. Prints one line per row this run could not evaluate:
#   malformed rows, and rows naming a suite that no executed suite matched.
#   Prints NOTHING when every row was evaluated — and nothing at all when the
#   table is empty, so the empty-table path stays byte-identical to the
#   pre-BOB-221 rule.
#
#   WHY IT EXISTS. P3 and P4 are only ever evaluated when the declared suite
#   RUNS. A row whose suite was DELETED, RENAMED, QUARANTINED or is
#   SELF-RECURSIVE is never judged, so it can neither stale out nor XPASS out:
#   it rots silently and stays ARMED. Blocking such a row is the honest
#   freshness contract — a declaration that cannot be evaluated is not a
#   declaration the gate may rely on.
# ---------------------------------------------------------------------------
expected_red_unmatched_rows() {
    local row rkey rid rextra shape
    for row in ${BASH_TEST_EXPECTED_RED[@]+"${BASH_TEST_EXPECTED_RED[@]}"}; do
        # A whitespace-only row names nothing, matches nothing, and cannot
        # silence anything. It is IGNORED as inert rather than refused — the
        # one boundary where "every unresolvable input REFUSES" does not apply,
        # stated explicitly rather than left as an unexplained gap (§11.4.6).
        [[ -n "${row//[[:space:]]/}" ]] || continue
        read -r rkey rid rextra <<<"${row}"
        # A row whose key MATCHED an executed suite was already judged by
        # expected_red_verdict — including any shape refusal. Reporting it here
        # as well would DOUBLE-COUNT: BASH_TEST_FAILED could exceed
        # BASH_TEST_RAN and the gate would print "2/1 test(s) FAILED" with the
        # same reason twice. Fail-closed either way, but arithmetic that cannot
        # be true is a §11.4.6 imprecision in the operator's own message.
        if [[ -n "${rkey:-}" && -n "${_EXPECTED_RED_SEEN[${rkey}]:-}" ]]; then
            continue
        fi
        if shape="$(expected_red_row_shape_problem "${row}")"; then
            echo "${shape}"
            continue
        fi
        echo "expected-red declaration for ${rkey} (${rid}) matched NO executed suite this run — deleted, renamed, quarantined, self-recursive, or misspelled. Such a row can never self-clear (the item-closed and XPASS checks are only evaluated when the suite runs), so it stays armed; remove the row and the marker, or restore the suite (fail-closed)"
    done
}

# ---------------------------------------------------------------------------
# expected_red_note_append <label> <reason>
#   Accumulates a BLOCK reason onto BASH_TEST_STALE_NOTE, which the gate's
#   blocking message carries so the operator sees WHICH declaration rotted
#   without re-running anything. Capped so one bad table cannot produce an
#   unreadable single-line verdict.
# ---------------------------------------------------------------------------
expected_red_note_append() {
    local name="$1" reason="$2"
    _EXPECTED_RED_NOTE_N="$(( ${_EXPECTED_RED_NOTE_N:-0} + 1 ))"
    if [[ "${_EXPECTED_RED_NOTE_N}" -le 3 ]]; then
        BASH_TEST_STALE_NOTE="${BASH_TEST_STALE_NOTE}; ${name}: ${reason}"
    elif [[ "${_EXPECTED_RED_NOTE_N}" -eq 4 ]]; then
        BASH_TEST_STALE_NOTE="${BASH_TEST_STALE_NOTE}; (+more expected-red declaration problems)"
    fi
}
