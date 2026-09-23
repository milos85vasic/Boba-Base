#!/usr/bin/env bash
# test_check_cm_no_fail_open_skip.sh — §11.4.107(10) self-validated-analyzer
# harness for scripts/pre_build/check_cm_no_fail_open_skip.sh (BOB-161,
# the §11.4.69 CM-NO-FAIL-OPEN-SKIP gate).
#
# Purpose:
#   Prove the gate SEES every fail-open-skip class it claims to detect
#   (golden-TRUE), does NOT fire on environment-derived skips or on carriers
#   that merely mention a skip in a comment/string (golden-FALSE), enforces
#   the finding-SET baseline in both directions (new finding -> FAIL, stale
#   baseline row -> FAIL), refuses to report a blind zero (§11.4.201(6)), and
#   is load-bearing under a paired §1.1 mutation.
#
# WHY THIS DRIVES THE REAL GATE (§11.4.249 producer != oracle != gate): the
#   harness EXECUTES the gate and reads its exit code + output. It never
#   re-implements the detector, so it cannot drift along with it.
#
# Every scratch tree is a throwaway `git init` under `mktemp -d`, destroyed on
#   EXIT. Nothing in the real checkout is created, staged or modified. The one
#   real-tree case only READS the tree.
#
# Usage:   bash tests/pre_build/test_check_cm_no_fail_open_skip.sh
# Inputs:  none. Outputs: PASS:/FAIL: lines on stdout.
# Exit:    0 every case behaved as specified | 1 a case diverged.
# Dependencies: bash, git, python3.
# Cross-references: §1.1 §11.4.69 §11.4.107(10) §11.4.115 §11.4.201 §11.4.224
#   docs/scripts/check_cm_no_fail_open_skip.md

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE_DIR="$REPO_ROOT/scripts/pre_build"
GATE="$GATE_DIR/check_cm_no_fail_open_skip.sh"
ENGINE="$GATE_DIR/cm_no_fail_open_skip_analyzer.py"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bob161_selftest.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

fails=0
pass() { printf 'PASS: %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*"; fails=$((fails + 1)); }

if [[ ! -f "$GATE" || ! -f "$ENGINE" ]]; then
  fail "gate or engine missing (gate=$GATE engine=$ENGINE) — CM-NO-FAIL-OPEN-SKIP does not exist"
  echo "=== ${fails} failure(s) ==="
  exit 1
fi

new_tree() {  # $1 = name -> prints path of a fresh git repo with tests/
  local dir="$WORK/$1"
  rm -rf "$dir"; mkdir -p "$dir/tests/integration" "$dir/tests/unit"
  git -C "$dir" init -q .
  printf '%s' "$dir"
}

# An environment-derived skip so a tree is never BLIND by construction.
env_skip_file() {  # $1 = tree
  cat > "$1/tests/unit/test_env_only.py" <<'PY'
import shutil
import pytest


def test_needs_go():
    if shutil.which("go") is None:
        pytest.skip("go toolchain not installed")
PY
}

run_gate() {  # $1 = gate path, $2 = tree, $3 = baseline -> OUT / RC
  OUT="$(bash "$1" --root "$2" --baseline "$3" 2>&1)"
  RC=$?
}

EMPTY_BASELINE="$WORK/empty.baseline"
: > "$EMPTY_BASELINE"

# ============================================== CASE 1: golden-TRUE STATUS
echo "-- case 1: golden-TRUE — skip conditioned on a response status --"
T="$(new_tree c1)"; env_skip_file "$T"
cat > "$T/tests/integration/test_status.py" <<'PY'
import pytest
import requests


def test_api():
    resp = requests.get("http://localhost:7187/health", timeout=2)
    if resp.status_code >= 500:
        pytest.skip("service degraded")
    assert resp.json()["status"] == "ok"
PY
run_gate "$GATE" "$T" "$EMPTY_BASELINE"
if [[ $RC -eq 1 ]] && grep -qF 'tests/integration/test_status.py:test_api:STATUS#1' <<<"$OUT"; then
  pass "case 1: status-conditioned skip is a finding (rc=1, key named)"
else
  fail "case 1: expected rc=1 naming test_status.py:test_api:STATUS#1; got rc=$RC out=[$OUT]"
fi

# ============================================== CASE 2: golden-TRUE EMPTY
echo "-- case 2: golden-TRUE — skip conditioned on an empty / absent body --"
T="$(new_tree c2)"; env_skip_file "$T"
cat > "$T/tests/integration/test_empty.py" <<'PY'
import urllib.request

import pytest


def _fetch(url):
    with urllib.request.urlopen(url, timeout=2) as handle:
        return handle.read()


def test_search_results():
    payload_bytes = _fetch("http://localhost:7187/api/v1/search")
    if not payload_bytes:
        pytest.skip("empty body — probably transient")
    if b'"results"' not in payload_bytes:
        pytest.skip("no results key")
PY
run_gate "$GATE" "$T" "$EMPTY_BASELINE"
if [[ $RC -eq 1 ]] \
   && grep -qF 'tests/integration/test_empty.py:test_search_results:EMPTY#1' <<<"$OUT" \
   && grep -qF 'tests/integration/test_empty.py:test_search_results:EMPTY#2' <<<"$OUT"; then
  pass "case 2: both empty/absent-body skips found through a helper (interprocedural taint)"
else
  fail "case 2: expected EMPTY#1 and EMPTY#2; got rc=$RC out=[$OUT]"
fi

# ======================================= CASE 3: golden-TRUE UNREACH (answered)
echo "-- case 3: golden-TRUE — skip in an except that also catches ANSWERED errors --"
T="$(new_tree c3)"; env_skip_file "$T"
cat > "$T/tests/integration/test_unreach.py" <<'PY'
import unittest

import requests


class TestLive(unittest.TestCase):
    def test_live(self):
        try:
            requests.get("http://localhost:9117/", timeout=2).raise_for_status()
        except requests.RequestException as exc:
            self.skipTest(f"jackett unavailable: {exc}")
PY
run_gate "$GATE" "$T" "$EMPTY_BASELINE"
if [[ $RC -eq 1 ]] && grep -qF 'tests/integration/test_unreach.py:TestLive.test_live:UNREACH#1' <<<"$OUT"; then
  pass "case 3: RequestException-catching skip (swallows HTTPError) is a finding"
else
  fail "case 3: expected TestLive.test_live:UNREACH#1; got rc=$RC out=[$OUT]"
fi

# ============================================== CASE 4: golden-TRUE shell
echo "-- case 4: golden-TRUE — shell bare ab_skip and forbidden reason --"
T="$(new_tree c4)"; env_skip_file "$T"
cat > "$T/tests/unit/test_sink.sh" <<'SH'
#!/usr/bin/env bash
if [[ -z "$codec" ]]; then ab_skip "sink returned nothing"; fi
ab_skip_with_reason "sink probe" network_unreachable_external
ab_skip_with_reason "sink probe" transient_probably
SH
run_gate "$GATE" "$T" "$EMPTY_BASELINE"
if [[ $RC -eq 1 ]] \
   && grep -qF 'tests/unit/test_sink.sh:<sh>:SHELL_BARE_SKIP#1' <<<"$OUT" \
   && grep -qF 'tests/unit/test_sink.sh:<sh>:SHELL_REASON#1' <<<"$OUT" \
   && grep -qF 'tests/unit/test_sink.sh:<sh>:SHELL_REASON#2' <<<"$OUT"; then
  pass "case 4: bare ab_skip + forbidden/non-closed-set reasons are findings"
else
  fail "case 4: expected SHELL_BARE_SKIP#1, SHELL_REASON#1, #2; got rc=$RC out=[$OUT]"
fi

# ================================= CASE 5: golden-FALSE with carriers
echo "-- case 5: golden-FALSE — env-derived skips + carriers are NOT findings --"
T="$(new_tree c5)"; env_skip_file "$T"
cat > "$T/tests/integration/test_carrier.py" <<'PY'
"""Docstring carrier: if resp.status_code >= 500: pytest.skip("x")."""
import os

import pytest
import requests

HINT = "pytest.skip('down') if resp.status_code >= 500 else None"


def test_topology_absent():
    # carrier: if resp.status_code >= 500: pytest.skip("down")
    try:
        requests.get("http://localhost:7187/health", timeout=1)
    except requests.ConnectionError:
        pytest.skip("stack not running (connection refused) — topology absent")
    if not os.environ.get("RUTRACKER_USERNAME"):
        pytest.skip("credentials not configured")
PY
cat > "$T/tests/unit/test_carrier.sh" <<'SH'
#!/usr/bin/env bash
# ab_skip "comment carrier"
echo "ab_skip is the forbidden helper"   # string carrier
printf '%s\n' 'ab_skip_with_reason x network_unreachable_external'
ab_skip_with_reason "no GPU on this host" hardware_not_present
SH
run_gate "$GATE" "$T" "$EMPTY_BASELINE"
if [[ $RC -eq 0 ]]; then
  pass "case 5: env-derived skips, connection-only topology skip and carriers pass (rc=0)"
else
  fail "case 5: expected rc=0 (false-positive refusal, §11.4.201(1)); got rc=$RC out=[$OUT]"
fi

# ================================ CASE 6: baseline is a SET, both directions
echo "-- case 6: finding-SET baseline — absorbed, new, stale --"
T="$(new_tree c6)"; env_skip_file "$T"
cp "$WORK/c1/tests/integration/test_status.py" "$T/tests/integration/test_status.py"
BL="$WORK/c6.baseline"
printf '# comment line\ntests/integration/test_status.py:test_api:STATUS#1\n' > "$BL"
run_gate "$GATE" "$T" "$BL"
if [[ $RC -eq 0 ]]; then pass "case 6a: a baselined finding is absorbed (rc=0)"
else fail "case 6a: expected rc=0 with the finding baselined; got rc=$RC out=[$OUT]"; fi

cp "$WORK/c2/tests/integration/test_empty.py" "$T/tests/integration/test_empty.py"
run_gate "$GATE" "$T" "$BL"
if [[ $RC -eq 1 ]] && grep -qF 'NEW' <<<"$OUT" && grep -qF 'test_empty.py:test_search_results:EMPTY#1' <<<"$OUT"; then
  pass "case 6b: a finding outside the baseline SET fails (rc=1, NEW named)"
else fail "case 6b: expected rc=1 NEW test_empty.py; got rc=$RC out=[$OUT]"; fi

rm -f "$T/tests/integration/test_empty.py"
printf 'tests/integration/gone.py:test_gone:STATUS#1\n' >> "$BL"
run_gate "$GATE" "$T" "$BL"
if [[ $RC -eq 1 ]] && grep -qF 'STALE' <<<"$OUT" && grep -qF 'gone.py:test_gone:STATUS#1' <<<"$OUT"; then
  pass "case 6c: a baseline row with no live finding fails (monotone ratchet must tighten)"
else fail "case 6c: expected rc=1 STALE gone.py; got rc=$RC out=[$OUT]"; fi

# A one-out-one-in SWAP keeps the COUNT but not the SET — must fail.
T="$(new_tree c6d)"; env_skip_file "$T"
cp "$WORK/c2/tests/integration/test_empty.py" "$T/tests/integration/test_empty.py"
sed -i '/if b.*not in payload_bytes/,+1d' "$T/tests/integration/test_empty.py"
BL2="$WORK/c6d.baseline"
printf 'tests/integration/test_status.py:test_api:STATUS#1\n' > "$BL2"
run_gate "$GATE" "$T" "$BL2"
if [[ $RC -eq 1 ]]; then pass "case 6d: a count-preserving swap is still caught (SET, not count)"
else fail "case 6d: expected rc=1 on a one-out-one-in swap; got rc=$RC out=[$OUT]"; fi

# ================================ CASE 7: blind / unverifiable -> rc=2
echo "-- case 7: blind zero and unparseable input are refused (rc=2) --"
T="$(new_tree c7a)"
printf 'def test_x():\n    assert True\n' > "$T/tests/unit/test_plain.py"
run_gate "$GATE" "$T" "$EMPTY_BASELINE"
if [[ $RC -eq 2 ]]; then pass "case 7a: zero skip sites in the corpus is refused as BLIND (rc=2)"
else fail "case 7a: expected rc=2 BLIND; got rc=$RC out=[$OUT]"; fi

T="$(new_tree c7b)"; env_skip_file "$T"
printf 'def test_x(:\n    pass\n' > "$T/tests/unit/test_broken.py"
run_gate "$GATE" "$T" "$EMPTY_BASELINE"
if [[ $RC -eq 2 ]] && grep -qF 'test_broken.py' <<<"$OUT"; then
  pass "case 7b: an unparseable test file makes the tree UNVERIFIED (rc=2, file named)"
else fail "case 7b: expected rc=2 naming test_broken.py; got rc=$RC out=[$OUT]"; fi

T="$WORK/c7c_not_a_repo"; mkdir -p "$T/tests"
run_gate "$GATE" "$T" "$EMPTY_BASELINE"
if [[ $RC -eq 2 ]]; then pass "case 7c: a non-git root cannot be enumerated (rc=2)"
else fail "case 7c: expected rc=2 for a non-git root; got rc=$RC out=[$OUT]"; fi

# ============================ CASE 8: control needle is in the gate's path
echo "-- case 8: the gate proves its own instrument can see (control needle) --"
T="$(new_tree c8)"; env_skip_file "$T"
run_gate "$GATE" "$T" "$EMPTY_BASELINE"
if [[ $RC -eq 0 ]] && grep -qF 'control-needle: seen' <<<"$OUT"; then
  pass "case 8: a PASS carries the in-path control-needle proof"
else fail "case 8: expected rc=0 with 'control-needle: seen'; got rc=$RC out=[$OUT]"; fi

# ======================================= CASE 9: the real tree
echo "-- case 9: real tree against the committed baseline --"
OUT="$(bash "$GATE" 2>&1)"; RC=$?
BASELINE_DATA_ROWS="$(grep -cvE '^[[:space:]]*(#|$)' "$GATE_DIR/cm_no_fail_open_skip.baseline" || true)"
if [[ $RC -eq 0 ]] && [[ "$BASELINE_DATA_ROWS" -eq 0 ]] && grep -qF '0 finding(s)' <<<"$OUT" && grep -qF 'control-needle: seen' <<<"$OUT"; then
  pass "case 9: real tree matches the committed finding SET (rc=0), the BOB-192 end-state holds (baseline has 0 data rows, 0 findings) and the zero is control-needled, not blind"
else fail "case 9: expected rc=0 on the real tree; got rc=$RC out=[$(tail -n 20 <<<"$OUT")]"; fi

# ============================== CASE 10: paired §1.1 mutations
echo "-- case 10: paired §1.1 mutations — a neutered gate must lose case 1 --"
MUT="$WORK/mut"; mkdir -p "$MUT"
cp "$GATE" "$ENGINE" "$MUT/"
# M1: every trigger classifier returns "no trigger". The in-gate control
# needle must catch this (rc=2), so case 1's rc=1 expectation flips.
sed -i 's/^TRIGGERS_ENABLED = True$/TRIGGERS_ENABLED = False/' "$MUT/cm_no_fail_open_skip_analyzer.py"
if ! grep -q '^TRIGGERS_ENABLED = False$' "$MUT/cm_no_fail_open_skip_analyzer.py"; then
  fail "case 10: mutation M1 did not apply — the harness would test nothing"
else
  run_gate "$MUT/check_cm_no_fail_open_skip.sh" "$WORK/c1" "$EMPTY_BASELINE"
  if [[ $RC -ne 1 ]]; then pass "case 10/M1: neutered detection no longer yields case-1 rc=1 (got rc=$RC) — case 1 is load-bearing"
  else fail "case 10/M1: neutered gate still rc=1 — case 1 is decorative"; fi
  # M2: ALSO disable the in-gate control needle: the neutered gate now PASSes
  # a golden-TRUE tree — exactly the bluff case 1 exists to catch.
  sed -i 's/^CONTROL_NEEDLE_ENABLED = True$/CONTROL_NEEDLE_ENABLED = False/' "$MUT/cm_no_fail_open_skip_analyzer.py"
  run_gate "$MUT/check_cm_no_fail_open_skip.sh" "$WORK/c1" "$EMPTY_BASELINE"
  if [[ $RC -eq 0 ]]; then pass "case 10/M2: needle+detection neutered -> gate PASSes golden-TRUE (rc=0); only case 1's assertion stands between that and a bluff"
  else fail "case 10/M2: expected the doubly-neutered gate to rc=0 (proving the mutation reached it); got rc=$RC"; fi
fi
# M3: neuter the baseline comparison (every finding treated as baselined).
cp "$ENGINE" "$MUT/cm_no_fail_open_skip_analyzer.py"
sed -i 's/^BASELINE_ENFORCED = True$/BASELINE_ENFORCED = False/' "$MUT/cm_no_fail_open_skip_analyzer.py"
if grep -q '^BASELINE_ENFORCED = False$' "$MUT/cm_no_fail_open_skip_analyzer.py"; then
  run_gate "$MUT/check_cm_no_fail_open_skip.sh" "$WORK/c1" "$EMPTY_BASELINE"
  if [[ $RC -ne 1 ]]; then pass "case 10/M3: neutered baseline comparison flips case 1 (got rc=$RC)"
  else fail "case 10/M3: baseline-neutered gate still rc=1 — comparison is not load-bearing"; fi
else
  fail "case 10/M3: mutation did not apply"
fi

echo
if [[ $fails -eq 0 ]]; then echo "=== all cases PASS ==="; exit 0; fi
echo "=== ${fails} failure(s) ==="
exit 1
