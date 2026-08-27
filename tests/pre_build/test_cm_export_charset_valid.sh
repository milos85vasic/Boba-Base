#!/usr/bin/env bash
# §1.1 paired mutations for CM-EXPORT-CHARSET-VALID (BOB-169 acceptance (d), BOB-182).
#
# A gate is UNVALIDATED INSTRUMENTATION until it has been OBSERVED to FAIL on a
# genuinely broken corpus (§11.4.115(F)). These cases plant the violations and
# require the refusal — including the two BLIND cases, where a naive gate reports
# zero violations and passes (§11.4.201(6): a blind instrument and a clean corpus
# return the identical quiet zero).
#
# BOB-182 adds the RATCHET cases. The operator's recorded decision (2026-08-26) is
# the monotone-decrease ratchet, so the ratchet's own invariants are now gate
# behaviour and are tested here:
#   - the baseline is PERSISTED DATA the gate READS and NEVER WRITES (§11.4.249),
#   - a stale ratchet (count below baseline) is a LOUD REFUSAL, not silent drift,
#   - the tightener LOWERS ONLY — it can never raise the bar,
#   - a missing or malformed baseline FAILS CLOSED (§11.4.252),
#   - the value cannot be injected ambiently; loosening is a tracked-file diff.
#
# This file is the VERIFIER in the §11.4.249 four-role split. It lives outside the
# gate, so a mutation that makes the gate always-pass cannot also silence it.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_export_charset_valid.sh"
# The gate now SOURCES the shared reader, so the reader is part of the gate's
# capability surface and the structural net must cover it too.
READER="${PROJECT_ROOT}/scripts/pre_build/lib/cm_export_charset_baseline_read.sh"
TIGHTEN="${PROJECT_ROOT}/scripts/pre_build/tighten_cm_export_charset_baseline.sh"
BASELINE_REL="scripts/pre_build/cm_export_charset_valid.baseline"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
bad(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
[[ -f "$GATE" ]] || { echo "FAIL: gate missing"; exit 1; }
[[ -f "$TIGHTEN" ]] || bad "PRODUCER missing: ${TIGHTEN} — the ratchet has no way to tighten (BOB-182)"

FIX="$(mktemp -d)"; trap 'rm -rf "$FIX"' EXIT
usable(){ [[ -n "${1:-}" && -d "${1}/docs" ]]; }

# make_case <name> <n_good> <n_bad>  -> echoes the fixture root
make_case() {
  local r="${FIX}/$1"; mkdir -p "${r}/docs" "${r}/scripts/pre_build" || return 1
  local i
  for ((i=0;i<$2;i++)); do
    printf '# Doc\n\nSection §1 — text.\n' > "${r}/docs/good${i}.md"
    printf '<!DOCTYPE html><html><head><meta charset="utf-8"><title>g</title></head><body><h1>Doc</h1></body></html>\n' > "${r}/docs/good${i}.html"
  done
  for ((i=0;i<$3;i++)); do
    printf '# Doc\n\nSection §1 — text mentioning charset in prose.\n' > "${r}/docs/bad${i}.md"
    printf '<h1 id="charset-fixture">Doc</h1>\n<p>Section §1 — text.</p>\n' > "${r}/docs/bad${i}.html"
  done
  echo "$r"
}
# set_baseline <root> <value> — writes the fixture's PERSISTED baseline DATA file.
set_baseline() { printf '# fixture\nbaseline=%s\n' "$2" > "${1}/${BASELINE_REL}"; }
baseline_of()  { sed -n 's/^baseline=\([0-9][0-9]*\)$/\1/p' "${1}/${BASELINE_REL}" 2>/dev/null | tail -1; }
sha_of()       { sha256sum "${1}/${BASELINE_REL}" 2>/dev/null | cut -d' ' -f1; }

# I-3: the PRIMARY producer!=gate net. Every gate invocation the suite makes is
# bracketed by a baseline checksum, so ANY write the fixtures exercise is caught
# regardless of which command performed it — perl, awk, ed, python, a here-doc, a
# redirect. The structural grep below is the SECONDARY net: it can only know the
# synonyms someone thought to list, and a mutation using `-gt` instead of `>`
# contains no redirection character at all.
GATE_WROTE=""
run_gate() { # $1=root
  usable "${1:-}" || { OUT="fixture setup failed for root='${1:-}' — gate NOT executed"; RC=97; return; }
  local __before __after; __before="$(sha_of "$1")"
  OUT="$(GOMAXPROCS=2 nice -n 19 ionice -c 3 bash "$GATE" "$1" 2>&1)"; RC=$?
  __after="$(sha_of "$1")"
  [[ "$__before" == "$__after" ]] || GATE_WROTE="${GATE_WROTE} $1"
}
run_tighten() { # $1=root
  OUT="$(GOMAXPROCS=2 nice -n 19 ionice -c 3 bash "$TIGHTEN" "$1" 2>&1)"; RC=$?
}
run_adopt() { # $1=root
  OUT="$(GOMAXPROCS=2 nice -n 19 ionice -c 3 bash "$TIGHTEN" --adopt "$1" 2>&1)"; RC=$?
}

echo "=== CM-EXPORT-CHARSET-VALID :: §1.1 paired mutations ==="

# ---------------------------------------------------------------- ABOVE baseline
R="$(make_case over 2 1)"; set_baseline "$R" 0
run_gate "$R"
# I-1: exit 1 is a CONTRACT, not an incidental non-zero. Invariant 50 branches on
# {0,1,3} to name the CAUSE, so an unpinned code lets the wrong-cause defect back
# in with every test still green (§11.4.201(5)).
[[ "$RC" -eq 1 ]] && ok "MUTATION: a NEW charset-less export above baseline -> gate REFUSES with exit 1 (contract)" \
                 || bad "a new charset-less export above baseline: expected exit 1, got ${RC} — regression code unpinned"
grep -q 'exceeds the ratchet baseline' <<<"$OUT" && ok "refusal names the ratchet and a sample offender" || bad "refusal message does not name the ratchet"

# ---------------------------------------------------------------- AT baseline
set_baseline "$R" 1
AT_SHA_BEFORE="$(sha_of "$R")"
run_gate "$R"
[[ "$RC" -eq 0 ]] && ok "NEGATIVE CONTROL: at baseline -> PASSES (no false-positive refusal, §11.4.201(1))" \
                 || bad "at-baseline corpus was REFUSED (exit ${RC}) — false-positive refusal"
[[ -n "$AT_SHA_BEFORE" && "$AT_SHA_BEFORE" == "$(sha_of "$R")" ]] \
  && ok "RUNTIME: the PASS path left the baseline byte-identical too (immutability is deliberate, not incidental)" \
  || bad "the gate mutated the baseline on its PASS path"

# ---------------------------------------------------------------- BELOW baseline
# BOB-182: a stale ratchet is a FINDING, not a licence to drift. The gate must
# REFUSE and name the tightener, so improvement is LOCKED IN rather than merely
# suggested to a human who may never read the line.
R2="$(make_case under 2 0)"; set_baseline "$R2" 1
run_gate "$R2"
# I-1: exit 3 is what lets invariant 50 say STALE RATCHET instead of "a NEW
# charset-less export landed". Collapsing it to 1 reintroduces the wrong-cause
# defect silently, so the code is asserted exactly.
[[ "$RC" -eq 3 ]] \
  && ok "BOB-182: below baseline -> gate REFUSES with exit 3 (stale ratchet, distinct cause)" \
  || bad "below-baseline: expected exit 3, got ${RC} — the stale-ratchet cause code is unpinned"
grep -q 'tighten_cm_export_charset_baseline.sh' <<<"$OUT" \
  && ok "the stale-ratchet refusal names the exact remediation command (§11.4.234(D))" \
  || bad "stale-ratchet refusal gives no named remediation path (§11.4.234(D))"

# --------------------------------------------- the GATE NEVER WRITES the baseline
# §11.4.249/§11.4.240: enforcement by CAPABILITY, not instruction. Runtime proof —
# the below-baseline run above is exactly the moment a self-writing gate would
# rewrite its own threshold. The bytes must be untouched.
BEFORE_SHA="$(sha_of "$R2")"
run_gate "$R2" >/dev/null 2>&1
AFTER_SHA="$(sha_of "$R2")"
[[ -n "$BEFORE_SHA" && "$BEFORE_SHA" == "$AFTER_SHA" ]] \
  && ok "RUNTIME: the gate did not mutate the baseline file (producer≠gate held, §11.4.249)" \
  || bad "the gate MUTATED its own threshold (${BEFORE_SHA} -> ${AFTER_SHA}) — producer/gate collapse"
# Structural sibling of the runtime proof: the write capability is absent from the source.
# Write synonyms, not just shell redirection: cp/mv/dd/tee/sed -i/truncate/python
# all write, and a grep that only knows about ">" would call a cp-based mutation clean.
# Verbs are TOKEN-anchored: an un-anchored 'ed' matched inside 'sed -n' and made
# this net refuse a purely read-only line — a §11.4.201(7)(a) carrier match, and a
# false-positive refusal is a FAIL-bluff exactly as a false negative is a PASS-bluff.
WRITE_PAT='(^|[^[:alnum:]_])((tee|cp|mv|dd|truncate|install|python3?|perl|awk|ed|sponge)[[:space:]]|sed[[:space:]]+-i)[^|]*(BASELINE_FILE|\$\{f\}|"\$f")|>>?[[:space:]]*"?\$\{?(BASELINE_FILE|f)\}?"?'
if grep -nE "$WRITE_PAT" "$GATE" "$READER" >/dev/null 2>&1; then
  bad "the gate source contains a WRITE to BASELINE_FILE — capability present, §11.4.240(B) violated"
else
  ok "STRUCTURAL: neither the gate nor the reader it sources has a write path to the baseline (§11.4.240(B))"
fi

# ------------------------------------------------- TIGHTEN, then REGRESS -> FAIL
# The full ratchet cycle: improve -> tighten -> the NEW baseline is what bites.
R3="$(make_case cycle 2 2)"; set_baseline "$R3" 2
run_gate "$R3"; [[ "$RC" -eq 0 ]] || bad "cycle fixture did not start at baseline (exit ${RC})"
rm -f "${R3}/docs/bad1.md" "${R3}/docs/bad1.html"          # corpus heals: 2 -> 1
run_tighten "$R3"
[[ "$RC" -eq 0 ]] && ok "PRODUCER: the tightener accepted the improvement (exit ${RC})" \
                 || bad "the tightener refused a genuine improvement (exit ${RC}): ${OUT}"
[[ "$(baseline_of "$R3")" == "1" ]] \
  && ok "PRODUCER: the persisted baseline was LOWERED 2 -> 1 (the ratchet actually ratchets, BOB-182)" \
  || bad "baseline was not lowered; it is $(baseline_of "$R3") — the ratchet still does not ratchet"
printf '# Doc\n\nregression\n' > "${R3}/docs/regress.md"
printf '<h1 id="charset-slug">Doc</h1>\n' > "${R3}/docs/regress.html"   # 1 -> 2, the OLD baseline
run_gate "$R3"
[[ "$RC" -ne 0 ]] \
  && ok "REGRESSION after tightening: a count at the OLD baseline now REFUSES (exit ${RC})" \
  || bad "a regression back to the pre-tighten count was ACCEPTED (exit ${RC}) — the ratchet is not monotone"

# -------------------------------------------------- the TIGHTENER NEVER RAISES
R4="$(make_case raise 2 3)"; set_baseline "$R4" 1
run_tighten "$R4"
# The refusal must be a REASONED one. A missing script also exits non-zero, and
# accepting that would let absence masquerade as enforcement (§11.4.201(6)).
[[ "$RC" -ne 0 ]] && grep -qiE 'monotone|would RAISE|regress' <<<"$OUT" \
  && ok "MUTATION: the tightener REFUSES to raise the baseline 1 -> 3, naming monotone decrease (§11.4.135)" \
  || bad "the tightener did not reason-refuse a raise (exit ${RC}): ${OUT}"
[[ "$(baseline_of "$R4")" == "1" ]] \
  && ok "the refused tighten left the persisted baseline untouched" \
  || bad "a refused tighten still mutated the baseline to $(baseline_of "$R4")"

# ------------------------------------------------ MISSING / MALFORMED baseline
# §11.4.252: an input to correctness that cannot be verified fails CLOSED.
R5="$(make_case nobaseline 2 0)"; rm -f "${R5}/${BASELINE_REL}"
run_gate "$R5"
[[ "$RC" -eq 1 ]] && grep -qi 'baseline' <<<"$OUT" \
  && ok "MISSING baseline -> gate FAILS CLOSED with exit 1 (§11.4.252)" \
  || bad "a missing baseline was treated as a satisfied precondition (exit ${RC})"
R6="$(make_case malformed 2 0)"; printf 'baseline=not-a-number\n' > "${R6}/${BASELINE_REL}"
run_gate "$R6"
[[ "$RC" -eq 1 ]] \
  && ok "MALFORMED baseline -> gate FAILS CLOSED with exit 1" \
  || bad "a malformed baseline was silently accepted (exit ${RC})"

# ------------------------------------------------------ NO AMBIENT LOOSENING
# The BOB-182 bypass: an env var that silently raised the bar left no reviewable
# trace. Loosening must be a tracked-file diff a reviewer sees (§11.4.234(D)).
# The exploit is NOT an absurd value — under the stale-ratchet rule an absurd one
# trips a refusal for the wrong reason, and a bare "exit != 0" assertion would be
# satisfied by that accident while the channel stayed wide open (observed: this
# very mutation sailed through the first version of this case). The real exploit
# is a value injected EQUAL to the live count, which buys a silent PASS. Both are
# probed, and each must refuse FOR THE RIGHT REASON — the FILE's baseline.
R7="$(make_case ambient 2 3)"; set_baseline "$R7" 0
OUT="$(BOBA_EXPORT_CHARSET_BASELINE=3 GOMAXPROCS=2 nice -n 19 bash "$GATE" "$R7" 2>&1)"; RC=$?
[[ "$RC" -ne 0 ]] && grep -q 'exceeds the ratchet baseline 0' <<<"$OUT" \
  && ok "an env var set to the live count cannot buy a PASS; the FILE's baseline decides (exit ${RC})" \
  || bad "BOBA_EXPORT_CHARSET_BASELINE=3 loosened the gate to the live count — the bypass is open: ${OUT}"
OUT="$(BOBA_EXPORT_CHARSET_BASELINE=9999 GOMAXPROCS=2 nice -n 19 bash "$GATE" "$R7" 2>&1)"; RC=$?
[[ "$RC" -ne 0 ]] && grep -q 'ratchet baseline 0' <<<"$OUT" \
  && ok "an absurd injected value is ignored outright — the gate still reports baseline 0 (exit ${RC})" \
  || bad "an injected baseline reached the comparison (exit ${RC}): ${OUT}"

# ------------------------------------------- LEADING-ZERO INTEGERS (review F1)
# A parse guard of ^baseline=[0-9][0-9]*$ accepts "08". Bash [[ -gt ]] / [[ -lt ]]
# then ERROR on invalid octal, `if` swallows the error as false, and BOTH branches
# fall through — the gate reaches its PASS line with violations present, and the
# tightener reaches its write with a RAISE. This is not a malicious input: it is an
# ordinary hand-edit typo, and it is the one cannot-decide class that failed OPEN.
# ("baseline=010" is the same family — it silently means octal 8.)
for BADINT in 08 010; do
  R10="$(make_case "octal${BADINT}" 2 3)"; printf 'baseline=%s\n' "$BADINT" > "${R10}/${BASELINE_REL}"
  run_gate "$R10"
  # The refusal must name the MALFORMED VALUE. "010" is octal 8, so a bare
  # "exit != 0" is satisfied by the stale-ratchet branch firing on a silently
  # misread number — a refusal for the wrong reason, and the same accidental-pass
  # shape that let an earlier mutation sail through (§11.4.201(6)).
  [[ "$RC" -ne 0 ]] && grep -qi 'no parseable' <<<"$OUT" \
    && ok "F1: baseline='${BADINT}' -> gate REFUSES AS MALFORMED (exit ${RC}); no octal fall-through" \
    || bad "F1: baseline='${BADINT}' with 3 violations was not refused as malformed (exit ${RC}) — octal misread: ${OUT}"
done

# The tightener half: stored 08, live 9. Nine is ABOVE eight, so a correct guard
# refuses; the octal error makes both guards false and the write proceeds, printing
# "lowered 08 -> 9" — a RAISE mislabelled as a lowering.
R11="$(make_case octalraise 2 9)"; printf 'baseline=08\n' > "${R11}/${BASELINE_REL}"
run_tighten "$R11"
[[ "$RC" -ne 0 ]] \
  && ok "F1: tightener REFUSES to act on an unparseable stored baseline '08' (exit ${RC})" \
  || bad "F1: tightener acted on baseline='08' (exit ${RC}) — a RAISE 8 -> 9 reported as a lowering: ${OUT}"
[[ "$(baseline_of "$R11")" == "08" ]] \
  && ok "F1: the refused tighten left the malformed baseline byte-identical" \
  || bad "F1: the tightener overwrote a baseline it could not read; it is now $(baseline_of "$R11")"

# ------------------------------------------ PRODUCER FALSE-SUCCESS (review F4)
# mv into a DIRECTORY at the baseline path succeeds by depositing the tmp file
# INSIDE it, leaving nothing at the path — while --adopt reports "ADOPTED" rc=0.
# A success report for a write that did not happen is exactly what this script's
# own anti-bluff header forbids (§11.4.6).
R12="$(make_case dirtarget 2 0)"; rm -f "${R12}/${BASELINE_REL}"; mkdir -p "${R12}/${BASELINE_REL}"
run_adopt "$R12"
[[ "$RC" -ne 0 ]] \
  && ok "F4: --adopt onto a directory target REFUSES rather than reporting a write it did not make (exit ${RC})" \
  || bad "F4: --adopt reported success (exit ${RC}) with no regular file at the baseline path: ${OUT}"
[[ ! -f "${R12}/${BASELINE_REL}" ]] \
  && ok "F4: and indeed nothing was written at the baseline path — the refusal was truthful" \
  || bad "F4: a file appeared at a directory path; fixture assumption broken"

# ------------------------------------------- 64-BIT WRAP (review I-2)
# The strict regex accepts a 20-digit value (no leading zero), and bash arithmetic
# then wraps it mod 2^64. 2^64+3 becomes 3, so a corpus with 3 violations reads as
# "at baseline" and PASSES. Same class as the octal hole, one ring out: a number
# the gate cannot faithfully evaluate must REFUSE, not be silently misread.
for HUGE in 18446744073709551619 18446744073709551617 99999999999999999999; do
  R13="$(make_case "wrap${HUGE:0:6}" 2 3)"; printf 'baseline=%s\n' "$HUGE" > "${R13}/${BASELINE_REL}"
  run_gate "$R13"
  [[ "$RC" -eq 1 ]] && grep -qi 'no parseable' <<<"$OUT" \
    && ok "I-2: baseline='${HUGE}' -> REFUSES as malformed (exit 1); no 2^64 wrap" \
    || bad "I-2: baseline='${HUGE}' with 3 violations was not refused as malformed (exit ${RC}) — arithmetic wrapped: ${OUT}"
done

# ----------------------------------------- DUPLICATE baseline lines (review M-1)
# `sed …p | tail -1` silently resolves an ambiguous file to its LAST MATCHING line,
# so a well-formed 3 followed by a malformed 08 — plausibly the operator's intended
# correction — resolves to 3 and passes. Two conflicting well-formed lines resolve
# just as silently. An ambiguous threshold is an unresolvable signal (§11.4.252).
R14="$(make_case dupmalformed 2 3)"; printf 'baseline=3\nbaseline=08\n' > "${R14}/${BASELINE_REL}"
run_gate "$R14"
[[ "$RC" -eq 1 ]] \
  && ok "M-1: well-formed + malformed baseline lines -> REFUSES as ambiguous (exit 1)" \
  || bad "M-1: an ambiguous baseline file resolved silently to the last matching line (exit ${RC}): ${OUT}"
R15="$(make_case dupvalid 2 3)"; printf 'baseline=3\nbaseline=9\n' > "${R15}/${BASELINE_REL}"
run_gate "$R15"
[[ "$RC" -eq 1 ]] \
  && ok "M-1: two conflicting well-formed baseline lines -> REFUSES as ambiguous (exit 1)" \
  || bad "M-1: two conflicting baselines resolved silently, last wins (exit ${RC}): ${OUT}"

# --------------------------------------------- SYMLINKED baseline (review M-2)
# `-f` follows symlinks. A symlink to a target outside the tree is read normally,
# so after ONE reviewable diff (mode 120000) every later raise edits the outside
# target and leaves no diff at all — a trace-free loosening route.
R16="$(make_case symlink 2 3)"; EXT="${FIX}/external_baseline"
printf 'baseline=9999\n' > "$EXT"; ln -sf "$EXT" "${R16}/${BASELINE_REL}"
run_gate "$R16"
[[ "$RC" -eq 1 ]] && grep -qi 'symlink\|regular file' <<<"$OUT" \
  && ok "M-2: a symlinked baseline is REFUSED (exit 1), not followed out of the tree" \
  || bad "M-2: the gate followed a symlink to an out-of-tree baseline (exit ${RC}): ${OUT}"
run_tighten "$R16"
[[ "$RC" -ne 0 ]] \
  && ok "M-2: the tightener also refuses a symlinked baseline rather than silently replacing it" \
  || bad "M-2: the tightener acted through a symlink (exit ${RC}): ${OUT}"

# ------------------------------------- LARGE REGRESSION exercises the exceed path
# I-3's mutation fired only when (BAD - BASELINE) > 3, so every existing fixture
# was too small to reach it. This fixture drives the exceed branch hard, and the
# run_gate checksum above is what turns that reach into a caught write.
R17="$(make_case bigregress 2 5)"; set_baseline "$R17" 0
run_gate "$R17"
[[ "$RC" -eq 1 ]] \
  && ok "I-3: a 5-over regression REFUSES with exit 1 (the exceed path is exercised)" \
  || bad "I-3: large regression expected exit 1, got ${RC}"
run_gate "$R17"
[[ "$RC" -eq 1 ]] \
  && ok "I-3: and it STILL refuses on a second run — the bar was not quietly raised to meet it" \
  || bad "I-3: second run returned ${RC}; the regression was accommodated between runs"

# ------------------------------------------------------------- BLIND detectors
R8="$(make_case blind 0 0)"; set_baseline "$R8" 0
run_gate "$R8"
[[ "$RC" -ne 0 ]] && grep -q 'BLIND' <<<"$OUT" \
  && ok "BLIND corpus (zero exports) -> REFUSES rather than reporting a clean zero (§11.4.201(6))" \
  || bad "an empty corpus reported CLEAN — the false-null the needle exists to prevent (exit ${RC})"

R9="$(make_case nocompliant 0 2)"; set_baseline "$R9" 99
run_gate "$R9"
[[ "$RC" -ne 0 ]] && grep -q 'cannot distinguish' <<<"$OUT" \
  && ok "zero-compliant corpus -> REFUSES: detector cannot be shown to discriminate" \
  || bad "a corpus with NO compliant file passed under a loose baseline (exit ${RC})"

# I-3 PRIMARY NET verdict, over every gate invocation this suite made.
[[ -z "${GATE_WROTE// /}" ]] \
  && ok "RUNTIME (all invocations): the gate never wrote a baseline file — producer!=gate holds by checksum, not by synonym list" \
  || bad "the gate MUTATED the baseline during these runs:${GATE_WROTE} — producer/gate collapse"

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
