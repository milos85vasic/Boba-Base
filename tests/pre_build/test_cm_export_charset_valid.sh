#!/usr/bin/env bash
# §1.1 paired mutations for CM-EXPORT-CHARSET-VALID (BOB-169 acceptance (d)).
#
# A gate is UNVALIDATED INSTRUMENTATION until it has been OBSERVED to FAIL on a
# genuinely broken corpus (§11.4.115(F)). These cases plant the violations and
# require the refusal — including the two BLIND cases, where a naive gate reports
# zero violations and passes (§11.4.201(6): a blind instrument and a clean corpus
# return the identical quiet zero).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_export_charset_valid.sh"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
bad(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
[[ -f "$GATE" ]] || { echo "FAIL: gate missing"; exit 1; }

FIX="$(mktemp -d)"; trap 'rm -rf "$FIX"' EXIT
usable(){ [[ -n "${1:-}" && -d "${1}/docs" ]]; }

# make_case <name> <n_good> <n_bad>
make_case() {
  local r="${FIX}/$1"; mkdir -p "${r}/docs" || return 1
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
run_gate() { # $1=root $2=baseline
  usable "${1:-}" || { OUT="fixture setup failed for root='${1:-}' — gate NOT executed"; RC=97; return; }
  OUT="$(BOBA_EXPORT_CHARSET_BASELINE="$2" GOMAXPROCS=2 nice -n 19 ionice -c 3 bash "$GATE" "$1" 2>&1)"; RC=$?
}

R="$(make_case over 2 1)"
run_gate "$R" 0
[[ "$RC" -ne 0 ]] && ok "MUTATION: a NEW charset-less export above baseline -> gate REFUSES (exit ${RC})" \
                 || bad "a new charset-less export above baseline was ACCEPTED (exit ${RC}) — the ratchet does not bite"
grep -q 'exceeds the ratchet baseline' <<<"$OUT" && ok "refusal names the ratchet and a sample offender" || bad "refusal message does not name the ratchet"

run_gate "$R" 1
[[ "$RC" -eq 0 ]] && ok "NEGATIVE CONTROL: at baseline -> PASSES (no false-positive refusal, §11.4.201(1))" \
                 || bad "at-baseline corpus was REFUSED (exit ${RC}) — false-positive refusal"

R2="$(make_case under 2 0)"
run_gate "$R2" 1
[[ "$RC" -eq 0 ]] && grep -q 'lower BASELINE' <<<"$OUT" \
  && ok "below baseline -> PASSES and tells the operator to tighten the ratchet" \
  || bad "below-baseline case did not pass with tightening advice (exit ${RC})"

R3="$(make_case blind 0 0)"
run_gate "$R3" 0
[[ "$RC" -ne 0 ]] && grep -q 'BLIND' <<<"$OUT" \
  && ok "BLIND corpus (zero exports) -> REFUSES rather than reporting a clean zero (§11.4.201(6))" \
  || bad "an empty corpus reported CLEAN — the false-null the needle exists to prevent (exit ${RC})"

R4="$(make_case nocompliant 0 2)"
run_gate "$R4" 99
[[ "$RC" -ne 0 ]] && grep -q 'cannot distinguish' <<<"$OUT" \
  && ok "zero-compliant corpus -> REFUSES: detector cannot be shown to discriminate" \
  || bad "a corpus with NO compliant file passed under a loose baseline (exit ${RC})"

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
