#!/usr/bin/env bash
# test_bob221_expected_red_declaration.sh — BOB-221 RED (§11.4.115 / §11.4.224)
#
# NO IN-SOURCE MARKER, DELIBERATELY (round-2 remediation, MINOR-3).
#   An earlier revision carried `# EXPECTED-RED: BOB-221` here while stating in
#   the same header that the marker "is removed in the SAME commit that turns
#   this suite GREEN". The suite went GREEN and the marker stayed — a shipped
#   self-contradiction and a latent XPASS trap: any future table row naming
#   this file would have found its corroborating marker already in place. The
#   marker is now gone. It is re-added only if this suite is ever legitimately
#   declared expected-red, and removed again by the same rule.
#
# PURPOSE
#   Prove that pre-build invariant 30 (CM-BASH-UNIT-TESTS-EXECUTED) has NO
#   concept of a test that is SUPPOSED to fail, so a correctly-authored RED
#   (mandated by §11.4.115 / §11.4.224, and required to PERSIST by §11.4.135)
#   is counted as a gate failure. Following the constitution's own test-first
#   discipline therefore makes the constitution's own blocking gate refuse.
#   That is a §11.4.120 wrong-seam defect: the gate asserts "no suite fails"
#   when the invariant it should assert is "no suite fails UNEXPECTEDLY".
#
# WHAT THIS ASSERTS (the oracle — §11.4.245)
#   Strategy: SPECIFIED. The acceptance properties are fixed by BOB-221, by
#   §11.4.248's shape, and by the round-1 and round-3 independent reviews;
#   they are NOT read off the implementation. The oracle is structurally
#   independent of the code under test: expected verdicts come from the
#   property statement, never from what the gate happens to do.
#
#   P1   a DECLARED red that FAILS does NOT block.
#   P2   an UNDECLARED failing suite STILL blocks.        (§11.4.201(1) guard)
#   P3   a DECLARED red whose tracked item is CLOSED blocks as STALE.
#   P4   a DECLARED red that unexpectedly PASSES blocks   (strict-xfail).
#   P5   a declaration whose in-file marker names a DIFFERENT id blocks
#        (§11.4.240/§11.4.249 producer separation: two places must agree).
#   P6   a declaration binds to the FILE — a same-basename suite in ANOTHER
#        globbed directory is NOT excused.
#   P7   a row that matched NO executed suite this run blocks.
#   P8   a DECLARED red that exits 3 blocks (a blind instrument is not a
#        verdict, §11.4.201(6)).
#   P9   a DECLARED red whose item is `Completed (...Fixed.md)` blocks as
#        STALE — all FOUR of §11.4.33's terminal statuses, not just `Fixed`.
#   P10  a MATCHED row with more than two fields blocks, counted ONCE.
#   P11  an item whose stored status is EMPTY blocks WITHOUT being asserted
#        CLOSED.
#
#   Added by the round-3 independent review:
#
#   P12  the ABSENT half of P5: a declared suite carrying NO marker at all
#        blocks, naming the two-place agreement. Round 3 measured that
#        disabling the absent-marker refusal left the suite GREEN — the
#        failure still blocked, but only by an unrelated `set -u` accident
#        (`markers[0]: unbound variable` inside the command substitution),
#        and the two-place reason was lost. A future defensive init of
#        `markers` would have turned that silently into HONOURED.
#   P13  the path match is EXACT, not a prefix. Round 3's mutation
#        `[[ "${rel}" == "${rkey}"* ]]` survived 12/12: a reviewed row for
#        tests/unit/test_zz_p.sh then also silenced an attacker-added
#        tests/unit/test_zz_p.sh.sh (RAN=2 FAILED=0 HONOURED=2), silently
#        re-opening the round-1 BLOCKING finding. P6 cannot see it — a
#        prefix match still blocks a same-basename file in a DIFFERENT
#        directory — so the sibling must share the declared path's PREFIX.
#   P14  an inline / trailing `# EXPECTED-RED:` mention is NOT a marker. The
#        pattern's LEFT ANCHOR is what makes the documented §11.4.201(7)(a)
#        claim true, and it is pinned on the REASON: unanchored, the same
#        line yields a dirty capture that blocks for a DIFFERENT reason, so
#        only a reason-level assertion can tell the two apart.
#   P15  a bare-basename row is refused BY THE SWEEP when it matches nothing.
#   P16  an unmatched row with more than two fields is refused by the sweep.
#   P17  an unmatched row with a malformed item id is refused by the sweep.
#        P15-P17 pin the sweep-side dispositions of boundary rows 3/4/5, which
#        round 3 found were claimed in the documentation but untested — a
#        silent `continue` in the sweep's shape branch left a legacy
#        bare-basename row inert (FAILED=0, no message) with the suite green.
#   P18  two rows naming ONE path block as ambiguous, and are counted ONCE.
#
# WHY MOST PROPERTIES ARE ASSERTED ON THE *REASON*, NOT MERELY ON "IT BLOCKED"
#   A failing suite blocks anyway when nothing is declared, so an assertion
#   that only checked "did it block" would pass for the WRONG reason and keep
#   passing if the clause under test were mutated away (§11.4.201 — a green
#   that does not depend on the thing it claims to prove).
#
# THE ORACLE'S OWN CARRIER RULE (§11.4.201(7)(a)) — MECHANICALLY ENFORCED
#   Reason assertions are matched against the gate's blocking LINE, and that
#   line always contains the offending suite's own PATH. So a single-word
#   alternative can be satisfied by a SCENARIO FILENAME rather than by the
#   reason — the assertion then passes for a run whose reason said nothing of
#   the sort. This is not hypothetical: round 2 anchored P3/P9 after finding
#   exactly this shape in the UNKNOWN branch's message ("...outside the
#   §11.4.33 closed set" satisfying a `closed` alternation), and round 3 then
#   found the SAME shape one layer out — P8's `abort` alternative was
#   satisfied by its own scenario file `test_zz_declared_abort.sh`, so ANY
#   declared-branch block passed P8 whatever the reason (demonstrated: replace
#   the exit-code message with `BLOCK:oops` -> suite still GREEN).
#
#   The durable fix is structural, not another one-off rename. Every reason
#   alternative is declared ONCE below and is subject to two mechanical
#   checks, run before any scenario:
#     (i)  every alternative must be MULTI-WORD (contain a space);
#     (ii) every scenario filename must be SPACE-FREE.
#   Together those make a filename carrier impossible by construction rather
#   than by vigilance. The scenario file was ALSO renamed to
#   test_zz_declared_rc3.sh, but that is belt-and-braces; (i)+(ii) is the guard.
#
# WHAT IS UNDER TEST — the REAL gate source, not a paraphrase
#   The suite-execution loop, the post-loop declaration-table sweep, and the
#   blocking predicate are EXTRACTED VERBATIM from
#   scripts/pre_build_verification.sh by content marker (never by line number)
#   and executed against a hermetic scratch PROJECT_ROOT (§11.4.226 anti-echo
#   — the extracted source is RUN, not matched).
#
#   HONEST LAYER BOUNDARY (§11.4.226): this is a runtime-class test of
#   invariant 30's decision logic. It is NOT a full pre_build_verification.sh
#   run — that gate is a 52-invariant monolith and running it here would
#   recurse (invariant 30 executes this very file).
#
# INSTRUMENT VIABILITY (§11.4.201(7)(b))
#   Every extraction is control-needle-checked; a blind harness ABORTS (exit 3)
#   rather than reporting a verdict. A CONTROL scenario (a passing undeclared
#   suite that must NOT block) proves the harness is not simply blocking
#   everything, which would make P2 vacuous. Each scenario additionally
#   asserts the RAN/FAILED/HONOURED counters where they are load-bearing, so
#   "it blocked" is never confused with "the right thing blocked".
#
# EXIT CODES
#   0  GREEN — the declaration mechanism exists and every property holds
#   1  RED   — the mechanism is absent or incomplete
#   3  ABORT — instrument blind / precondition unmet (NOT a verdict)
#
# Usage        : bash tests/pre_build/test_bob221_expected_red_declaration.sh
# Inputs       : scripts/pre_build_verification.sh (read-only, verbatim extract)
#                scripts/lib/expected_red.sh       (read-only, sourced)
# Outputs      : human-readable verdict on stdout
# Side-effects : one mktemp -d scratch tree, removed on every exit path
#                (§11.4.14). Nothing in the real repository is created,
#                staged, modified, or deleted. No network, no container, no
#                signal delivery (§11.4.263), no host power-state change
#                (CONST-033).
# Depends      : bash, sed, grep, mktemp, timeout, python3 (sqlite3 module)
# Refs         : BOB-221; §11.4.115(F), §11.4.120, §11.4.135, §11.4.201(1)(6)(7),
#                §11.4.215, §11.4.224, §11.4.226, §11.4.227, §11.4.240,
#                §11.4.245, §11.4.248, §11.4.249, §11.4.252.

set -uo pipefail

GATE="scripts/pre_build_verification.sh"
HELPER="scripts/lib/expected_red.sh"
SCRATCH=""
RC_GREEN=0; RC_RED=1; RC_ABORT=3

abort() { echo "ABORT: $*" >&2; exit "${RC_ABORT}"; }
cleanup() { [[ -n "${SCRATCH}" && -d "${SCRATCH}" ]] && rm -rf "${SCRATCH}"; }
trap cleanup EXIT

FAILED_PROPS=()
note_fail() { FAILED_PROPS+=("$1"); echo "  RED  $1"; }
note_ok()   { echo "  ok   $1"; }

# ---------------------------------------------------------------------------
# 0a. The reason vocabulary — declared ONCE, mechanically carrier-checked
# ---------------------------------------------------------------------------
REASON_STALE='STALE expected-red declaration'
REASON_UNMATCHED='matched NO executed suite|no executed suite|never evaluated'
REASON_RC='exited 3|not the RED verdict'
REASON_FIELDS='more than two fields|exactly two fields'
REASON_EMPTYSTATUS='no non-empty status|nothing was classified'
REASON_NOMARKER='carries no|two places must agree'
REASON_PATHSHAPE='repo-relative suite path|basename cannot identify a file'
REASON_BADID='is not <PREFIX>'
REASON_AMBIG='table rows name|ambiguous expected-red'
REASON_VARS=(REASON_STALE REASON_UNMATCHED REASON_RC REASON_FIELDS
             REASON_EMPTYSTATUS REASON_NOMARKER REASON_PATHSHAPE
             REASON_BADID REASON_AMBIG)

# (i) every alternative must be MULTI-WORD. A single-word alternative could be
#     satisfied by the suite PATH the blocking line always carries, which is
#     how round 3's P8 carrier arose.
for _rv in "${REASON_VARS[@]}"; do
    IFS='|' read -r -a _alts <<<"${!_rv}"
    for _a in ${_alts[@]+"${_alts[@]}"}; do
        [[ "${_a}" == *" "* ]] || abort "oracle self-check: ${_rv} alternative '${_a}' is a SINGLE WORD — a scenario filename could satisfy it (§11.4.201(7)(a)); every reason alternative must be multi-word"
    done
done

# ---------------------------------------------------------------------------
# 0b. Preconditions + instrument viability
# ---------------------------------------------------------------------------
[[ -r "${GATE}" ]] || abort "cannot read ${GATE} (run from the repository root)"
command -v python3 >/dev/null 2>&1 || abort "python3 absent — cannot build the scratch item store"
command -v timeout >/dev/null 2>&1 || abort "timeout absent — the extracted loop invokes it"

# Extract the REAL suite-execution loop AND the post-loop declaration-table
# sweep, by content marker (never by line number).
#
# The three-way split is deliberate. Deleting the SWEEP is a regression the
# harness must report as P7 RED (not as blindness), so the `else` branch is a
# guard, not dead compatibility code. But deleting only the END MARKER while
# the sweep remains is a DIFFERENT fault, and falling back would then report
# "dead-row rot" for what is really a missing extraction marker — a wrong-cause
# message (§11.4.6). That case aborts with its own diagnosis.
SWEEP_WIRED=0
if grep -q '^# END-INVARIANT-30-SUITE-LOOP$' "${GATE}"; then
    SWEEP_WIRED=1
    LOOP_SRC="$(sed -n '/^for _bt in .*tests\/unit\/test_\*\.sh/,/^# END-INVARIANT-30-SUITE-LOOP$/p' "${GATE}")"
    grep -q 'expected_red_unmatched_rows' <<<"${LOOP_SRC}" \
      || abort "control needle: the extracted region ends at the END marker but contains no table sweep — wrong region captured"
elif grep -q 'expected_red_unmatched_rows' "${GATE}"; then
    abort "control needle: the gate still calls expected_red_unmatched_rows but its '# END-INVARIANT-30-SUITE-LOOP' extraction marker is GONE — restore the marker; falling back here would report a dead-row failure for a missing-marker fault"
else
    LOOP_SRC="$(sed -n '/^for _bt in .*tests\/unit\/test_\*\.sh/,/^done$/p' "${GATE}")"
fi
[[ -n "${LOOP_SRC}" ]] || abort "control needle: could not extract invariant 30's loop from ${GATE} — instrument blind"
grep -q 'BASH_TEST_FAILURES+=' <<<"${LOOP_SRC}" \
  || abort "control needle: extracted region does not record failures — wrong region captured"

BLOCK_SRC="$(grep -A1 -F 'elif [[ "${BASH_TEST_FAILED}" -gt 0 ]]; then' "${GATE}" \
             | sed '1s/^elif /if /' )"
[[ -n "${BLOCK_SRC}" ]] || abort "control needle: could not extract the blocking predicate — instrument blind"
grep -q 'BASH_TEST_FAILED' <<<"${BLOCK_SRC}" \
  || abort "control needle: extracted predicate does not mention BASH_TEST_FAILED — wrong region captured"
BLOCK_SRC="${BLOCK_SRC}
fi"

SCRATCH="$(mktemp -d)" || abort "mktemp -d failed"
mkdir -p "${SCRATCH}/docs"

# ---------------------------------------------------------------------------
# 1. Hermetic scratch PROJECT_ROOT — each scenario builds the exact tree it
#    needs. (A fixed set shuffled through a parking directory cannot express
#    P6's same-basename-different-directory tree, nor P13's prefix sibling.)
# ---------------------------------------------------------------------------
reset_tree() {
    rm -rf "${SCRATCH}/tests"
    mkdir -p "${SCRATCH}/tests/unit" "${SCRATCH}/tests/pre_build" "${SCRATCH}/tests/hooks"
}

# (ii) the second half of the carrier guard: scenario paths are space-free, so
#      a multi-word reason alternative can never be satisfied by a filename.
_assert_spacefree() {
    [[ "$1" != *" "* ]] || abort "oracle self-check: scenario path '$1' contains a SPACE — it could satisfy a multi-word reason alternative (§11.4.201(7)(a))"
}

mk_suite() { # $1 = path relative to SCRATCH, $2 = exit code, $3 = optional marker id
    _assert_spacefree "$1"
    local p="${SCRATCH}/$1"
    mkdir -p "$(dirname "${p}")"
    { echo '#!/usr/bin/env bash'
      [[ -n "${3:-}" ]] && echo "# EXPECTED-RED: $3"
      echo "exit $2"
    } > "${p}"
    chmod +x "${p}"
}

mk_raw() { # $1 = path relative to SCRATCH, $2.. = verbatim lines
    _assert_spacefree "$1"
    local p="${SCRATCH}/$1"; shift
    mkdir -p "$(dirname "${p}")"
    printf '%s\n' "$@" > "${p}"
    chmod +x "${p}"
}

python3 - "${SCRATCH}/docs/workable_items.db" <<'PYEOF'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.execute("CREATE TABLE items (atm_id TEXT PRIMARY KEY, status TEXT, type TEXT, title TEXT)")
db.executemany("INSERT INTO items VALUES (?,?,?,?)", [
    # OPEN — a live RED may legitimately be declared against these.
    ("BOB-901", "Queued",                    "Bug",  "open defect, RED is legitimate"),
    ("BOB-903", "In progress",               "Bug",  "open defect, RED is legitimate"),
    ("BOB-904", "Queued",                    "Bug",  "open — P8 must block on the EXIT CODE alone"),
    # CLOSED — two DIFFERENT members of §11.4.33's four-member terminal
    # vocabulary, so narrowing CLOSED to a single literal cannot survive.
    ("BOB-902", "Fixed (→ Fixed.md)",     "Bug",  "closed defect, declaration is stale"),
    ("BOB-905", "Completed (→ Fixed.md)", "Task", "closed task, declaration is stale"),
    # EMPTY status — never classified; must not be asserted CLOSED.
    ("BOB-906", "",                          "Task", "status empty, nothing to classify"),
])
db.commit()
PYEOF
[[ -s "${SCRATCH}/docs/workable_items.db" ]] || abort "scratch item store was not created"

# ---------------------------------------------------------------------------
# 2. Scenario driver — the REAL extracted loop + sweep + blocking predicate.
# ---------------------------------------------------------------------------
run_gate() { # $@ = declaration rows, each "<repo-relative-path> <ITEM-ID>"
    local decl_rows=("$@")
    local runner="${SCRATCH}/runner.sh"
    {
        echo 'set -uo pipefail'
        echo "PROJECT_ROOT=\"${SCRATCH}\""
        echo 'BASH_TEST_SELF_RECURSIVE=()'
        echo 'BASH_TEST_QUARANTINE=()'
        echo 'BASH_TEST_RAN=0; BASH_TEST_FAILED=0; BASH_TEST_QUARANTINED=0'
        echo 'BASH_TEST_FAILURES=()'
        # Order is load-bearing: the helper ships the REAL declaration table,
        # so the scratch table must be assigned AFTER it or it is clobbered.
        echo "if [[ -r \"${PWD}/${HELPER}\" ]]; then . \"${PWD}/${HELPER}\"; fi"
        printf 'BASH_TEST_EXPECTED_RED=('
        local r; for r in ${decl_rows[@]+"${decl_rows[@]}"}; do printf ' "%s"' "$r"; done
        printf ' )\n'
        echo 'BASH_TEST_STALE_NOTE=""'
        echo 'fail() { echo "BLOCKED: $*"; }'
        echo 'pass() { :; }'
        echo "${LOOP_SRC}"
        echo 'echo "XSUM RAN=${BASH_TEST_RAN} FAILED=${BASH_TEST_FAILED} HONOURED=${BASH_TEST_XRED_HONOURED:-0}"'
        echo "${BLOCK_SRC}"
    } > "${runner}"
    # No signals are sent to any process group here (§11.4.263 — this harness
    # never calls kill/killpg at all).
    ( cd "${SCRATCH}" && timeout 120 bash "${runner}" 2>&1 )
}

xsum() { grep -o 'XSUM RAN=[0-9]* FAILED=[0-9]* HONOURED=[0-9]*' <<<"$1" | head -1; }
blocked()  { grep -q '^BLOCKED:' <<<"$1"; }
reason()   { grep -qE "^BLOCKED:.*(${2})" <<<"$1"; }

# Assert: blocked, for the named reason, with the expected counters.
check_block() { # $1 label, $2 out, $3 reason-alternation, $4 expected-xsum (or "")
    local label="$1" out="$2" rx="$3" want="${4:-}"
    if ! blocked "${out}"; then
        note_fail "${label} did NOT block [$(xsum "${out}")]"; return
    fi
    if ! reason "${out}" "${rx}"; then
        note_fail "${label} blocked, but for the WRONG reason"; return
    fi
    if [[ -n "${want}" && "$(xsum "${out}")" != "${want}" ]]; then
        note_fail "${label} blocked for the right reason but counted wrong: want '${want}', got '$(xsum "${out}")'"; return
    fi
    note_ok "${label}"
}

echo "BOB-221 — invariant 30 EXPECTED-RED declaration mechanism"
echo "gate under test : ${GATE}"
echo "helper expected : ${HELPER} $( [[ -r "${HELPER}" ]] && echo '(present)' || echo '(ABSENT — pre-fix)')"
echo "table sweep     : $( [[ "${SWEEP_WIRED}" -eq 1 ]] && echo 'wired in the gate' || echo 'NOT WIRED — P7 must be RED')"
echo

# --- P-CONTROL ------------------------------------------------------------
reset_tree
mk_suite tests/unit/test_zz_control_pass.sh 0
CTRL_OUT="$(run_gate)"
if blocked "${CTRL_OUT}"; then
    echo "${CTRL_OUT}" | sed 's/^/    | /'
    abort "control needle failed: a passing undeclared suite blocked; P2 would pass vacuously"
fi
[[ "$(xsum "${CTRL_OUT}")" = "XSUM RAN=1 FAILED=0 HONOURED=0" ]] \
  || abort "control needle failed: expected RAN=1 FAILED=0 HONOURED=0, got '$(xsum "${CTRL_OUT}")'"
note_ok "P-CONTROL  a passing undeclared suite does not block (harness sees a clean tree)"

# --- P2 (golden-FALSE: must hold TODAY and AFTER) -------------------------
reset_tree
mk_suite tests/unit/test_zz_undeclared_fail.sh 1
P2_OUT="$(run_gate)"
if blocked "${P2_OUT}" && [[ "$(xsum "${P2_OUT}")" = "XSUM RAN=1 FAILED=1 HONOURED=0" ]]; then
    note_ok "P2         an UNDECLARED failing suite still blocks (§11.4.201(1) guard holds)"
else
    note_fail "P2         an UNDECLARED failing suite did NOT block — the gate has been defanged [$(xsum "${P2_OUT}")]"
fi

# --- P1 -------------------------------------------------------------------
reset_tree
mk_suite tests/unit/test_zz_declared_red.sh 1 BOB-901
P1_OUT="$(run_gate 'tests/unit/test_zz_declared_red.sh BOB-901')"
if ! blocked "${P1_OUT}" && [[ "$(xsum "${P1_OUT}")" = "XSUM RAN=1 FAILED=0 HONOURED=1" ]]; then
    note_ok "P1         a DECLARED red (item OPEN) does not block"
else
    note_fail "P1         a DECLARED red (item OPEN) still blocks — no declaration mechanism [$(xsum "${P1_OUT}")]"
fi

# --- P3 -------------------------------------------------------------------
reset_tree
mk_suite tests/unit/test_zz_declared_stale.sh 1 BOB-902
check_block "P3         a DECLARED red whose item is CLOSED blocks, naming the stale declaration" \
    "$(run_gate 'tests/unit/test_zz_declared_stale.sh BOB-902')" "${REASON_STALE}" ""

# --- P4 -------------------------------------------------------------------
reset_tree
mk_suite tests/unit/test_zz_declared_xpass.sh 0 BOB-903
P4_OUT="$(run_gate 'tests/unit/test_zz_declared_xpass.sh BOB-903')"
if blocked "${P4_OUT}"; then
    note_ok "P4         a DECLARED red that PASSES blocks (strict-xfail parity)"
else
    note_fail "P4         a DECLARED red that PASSES did NOT block — the ratchet cannot force de-declaration"
fi

# --- P5 (marker names a DIFFERENT id) -------------------------------------
reset_tree
mk_suite tests/unit/test_zz_marker_mismatch.sh 1 BOB-999
P5_OUT="$(run_gate 'tests/unit/test_zz_marker_mismatch.sh BOB-901')"
if blocked "${P5_OUT}"; then
    note_ok "P5         a declaration whose marker names a DIFFERENT id blocks"
else
    note_fail "P5         an UNCORROBORATED declaration excused the failure — one place can silence"
fi

# --- P6 (the declaration binds to the FILE, not to a basename) ------------
reset_tree
mk_suite tests/unit/test_zz_declared_red.sh  1 BOB-901
mk_suite tests/hooks/test_zz_declared_red.sh 1 BOB-901
P6_OUT="$(run_gate 'tests/unit/test_zz_declared_red.sh BOB-901')"
if blocked "${P6_OUT}" && [[ "$(xsum "${P6_OUT}")" = "XSUM RAN=2 FAILED=1 HONOURED=1" ]]; then
    note_ok "P6         a declaration binds to the FILE — a same-basename suite elsewhere is NOT excused"
else
    note_fail "P6         a same-basename suite in another directory was excused by one row [$(xsum "${P6_OUT}")]"
fi

# --- P7 (a row that matched nothing cannot self-clear) --------------------
reset_tree
mk_suite tests/unit/test_zz_control_pass.sh 0
check_block "P7         a row that matched NO executed suite blocks (the table's freshness contract)" \
    "$(run_gate 'tests/unit/test_zz_ghost.sh BOB-901')" "${REASON_UNMATCHED}" ""

# --- P8 (an ABORT is not the declared RED verdict) ------------------------
# The item is OPEN and the marker corroborates, so the ONLY reason to block is
# the exit code. The scenario file is deliberately NOT named for its reason.
reset_tree
mk_suite tests/unit/test_zz_declared_rc3.sh 3 BOB-904
check_block "P8         a DECLARED red that exits 3 blocks — a blind instrument is never honoured" \
    "$(run_gate 'tests/unit/test_zz_declared_rc3.sh BOB-904')" "${REASON_RC}" "XSUM RAN=1 FAILED=1 HONOURED=0"

# --- P9 (every §11.4.33 terminal status is a closure) ---------------------
reset_tree
mk_suite tests/unit/test_zz_declared_completed.sh 1 BOB-905
check_block "P9         a DECLARED red whose item is 'Completed' blocks as STALE (all four terminals)" \
    "$(run_gate 'tests/unit/test_zz_declared_completed.sh BOB-905')" "${REASON_STALE}" ""

# --- P10 (a MATCHED row must carry exactly two fields, counted ONCE) ------
reset_tree
mk_suite tests/unit/test_zz_declared_red.sh 1 BOB-901
check_block "P10        a MATCHED row with MORE THAN TWO fields blocks, counted once" \
    "$(run_gate 'tests/unit/test_zz_declared_red.sh BOB-901 EXTRA')" "${REASON_FIELDS}" "XSUM RAN=1 FAILED=1 HONOURED=0"

# --- P11 (an unclassified status is never asserted CLOSED) ----------------
reset_tree
mk_suite tests/unit/test_zz_declared_emptystatus.sh 1 BOB-906
P11_OUT="$(run_gate 'tests/unit/test_zz_declared_emptystatus.sh BOB-906')"
if blocked "${P11_OUT}" && reason "${P11_OUT}" "${REASON_EMPTYSTATUS}" \
   && ! grep -qE "^BLOCKED:.*is CLOSED \(''\)" <<<"${P11_OUT}"; then
    note_ok "P11        an EMPTY stored status blocks without asserting the item is CLOSED"
elif blocked "${P11_OUT}"; then
    note_fail "P11        blocked, but asserted a class it never derived — wrong-cause message (§11.4.6)"
else
    note_fail "P11        an EMPTY stored status did not block [$(xsum "${P11_OUT}")]"
fi

# --- P12 (the ABSENT half of the two-place agreement) ---------------------
reset_tree
mk_suite tests/unit/test_zz_no_marker.sh 1
check_block "P12        a declared suite carrying NO marker blocks, naming the two-place agreement" \
    "$(run_gate 'tests/unit/test_zz_no_marker.sh BOB-901')" "${REASON_NOMARKER}" "XSUM RAN=1 FAILED=1 HONOURED=0"

# --- P13 (the path match is EXACT, not a prefix) --------------------------
# The sibling shares the declared path's PREFIX, which is exactly what P6
# cannot express: a prefix match still blocks a same-basename file in a
# DIFFERENT directory, so only this tree distinguishes the two.
reset_tree
mk_suite tests/unit/test_zz_p.sh    1 BOB-901
mk_suite tests/unit/test_zz_p.sh.sh 1 BOB-901
P13_OUT="$(run_gate 'tests/unit/test_zz_p.sh BOB-901')"
if blocked "${P13_OUT}" && [[ "$(xsum "${P13_OUT}")" = "XSUM RAN=2 FAILED=1 HONOURED=1" ]]; then
    note_ok "P13        the path match is EXACT — a path-PREFIX sibling is NOT excused"
else
    note_fail "P13        a path-PREFIX sibling was excused by one row [$(xsum "${P13_OUT}")]"
fi

# --- P14 (the marker's left anchor is load-bearing) -----------------------
reset_tree
mk_raw tests/unit/test_zz_inline_marker.sh '#!/usr/bin/env bash' ': ok # EXPECTED-RED: BOB-901' 'exit 1'
check_block "P14        an INLINE/trailing marker mention is not a marker (left anchor holds)" \
    "$(run_gate 'tests/unit/test_zz_inline_marker.sh BOB-901')" "${REASON_NOMARKER}" "XSUM RAN=1 FAILED=1 HONOURED=0"

# --- P15/P16/P17 (the SWEEP's malformed-row refusals, boundary rows 3/4/5) -
reset_tree
mk_suite tests/unit/test_zz_control_pass.sh 0
check_block "P15        a bare-BASENAME row is refused by the sweep (boundary 3)" \
    "$(run_gate 'test_zz_control_pass.sh BOB-901')" "${REASON_PATHSHAPE}" "XSUM RAN=1 FAILED=1 HONOURED=0"
check_block "P16        an unmatched row with EXTRA fields is refused by the sweep (boundary 4)" \
    "$(run_gate 'tests/unit/test_zz_ghost.sh BOB-901 EXTRA')" "${REASON_FIELDS}" "XSUM RAN=1 FAILED=1 HONOURED=0"
check_block "P17        an unmatched row with a MALFORMED id is refused by the sweep (boundary 5)" \
    "$(run_gate 'tests/unit/test_zz_ghost.sh nope')" "${REASON_BADID}" "XSUM RAN=1 FAILED=1 HONOURED=0"

# --- P18 (two rows for one path: ambiguous, counted once) -----------------
reset_tree
mk_suite tests/unit/test_zz_declared_red.sh 1 BOB-901
check_block "P18        TWO rows naming one path block as ambiguous, counted once" \
    "$(run_gate 'tests/unit/test_zz_declared_red.sh BOB-901' 'tests/unit/test_zz_declared_red.sh BOB-901')" \
    "${REASON_AMBIG}" "XSUM RAN=1 FAILED=1 HONOURED=0"

echo
TOTAL=18
if [[ "${#FAILED_PROPS[@]}" -eq 0 ]]; then
    echo "RESULT: GREEN (exit 0) — the EXPECTED-RED declaration mechanism satisfies P1..P${TOTAL}."
    exit "${RC_GREEN}"
fi
echo "RESULT: RED (exit 1) — ${#FAILED_PROPS[@]} of ${TOTAL} properties unmet. BOB-221 acceptance not met."
printf '  unmet: %s\n' "${FAILED_PROPS[@]}"
exit "${RC_RED}"
