#!/usr/bin/env bash
# test_check_cm_no_unscoped_live_destruction.sh — §1.1 paired-mutation
# meta-test for scripts/pre_build/check_cm_no_unscoped_live_destruction.sh
# (CM-NO-UNSCOPED-LIVE-DESTRUCTION).
#
# WHY THIS DRIVES THE REAL GATE (§11.4.249 producer != oracle != gate):
# this harness EXECUTES the gate and reads its exit code. It does NOT restate
# the gate's regexes — a harness that reproduces the detector inside itself is
# a producer=oracle collapse and cannot see the gate drift.
#
# IT IS ALSO FULLY HERMETIC (§11.4.27(11)): every arm runs against a scratch
# tree via CM_UNSCOPED_ROOT. It never contacts, reads, or mutates the live
# qBittorrent instance, so it is safe to run while the operator has real
# torrents in the session — which is the entire point of the defect under
# repair.
#
# THE CANONICAL MUTATION (§11.4.115(F)): ARM 1 restores the VERBATIM pre-fix
# `_purge_qbittorrent_torrents` body — the shape that actually shipped in
# a684b2f and destroyed the operator's library — not a hand-simplified
# stand-in that might be easier to detect than the real thing.
#
# CM-NO-UNSCOPED-LIVE-DESTRUCTION: EXEMPT reason=gate_fixture — this harness embeds
# the verbatim pre-fix destroying shape as the §1.1 mutation fixture, on purpose.
# The fixtures are written to scratch trees and never executed against any instance.
#
# Exit: 0 every arm matched | 1 divergence (gate not trustworthy) | 2 harness error.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE="$REPO_ROOT/scripts/pre_build/check_cm_no_unscoped_live_destruction.sh"

if [[ ! -x "$GATE" ]]; then
    echo "HARNESS ERROR: gate missing or not executable at $GATE" >&2
    exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fails=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; fails=$((fails + 1)); }

# new_tree — a scratch scan root the gate accepts (both roots must exist or it
# reports a harness error, which is itself covered by ARM 6).
new_tree() {
    local d="$WORK/$1"
    rm -rf "$d"
    mkdir -p "$d/tests" "$d/challenges"
    printf '%s' "$d"
}

# run_gate <tree> -> sets OUT / RC
run_gate() {
    OUT="$(CM_UNSCOPED_ROOT="$1" bash "$GATE" 2>&1)"
    RC=$?
}

echo "=== paired-mutation meta-test: CM-NO-UNSCOPED-LIVE-DESTRUCTION ==="
echo

# ---------------------------------------------------------------------------
# ARM 1 — THE MUTATION: the verbatim pre-fix purge must FAIL the gate.
# ---------------------------------------------------------------------------
T1="$(new_tree mutation)"
cat > "$T1/tests/test_stress_prefix.py" <<'PREFIX_EOF'
def _purge_qbittorrent_torrents(qbit_url: str = "http://localhost:7186") -> None:
    """Delete every torrent from qBittorrent."""
    try:
        import http.cookiejar
        import urllib.parse
        import urllib.request

        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        data = urllib.parse.urlencode({"username": "admin", "password": "admin"}).encode()
        opener.open(
            urllib.request.Request(f"{qbit_url}/api/v2/auth/login", data=data, method="POST"),
            timeout=10,
        )
        resp = opener.open(f"{qbit_url}/api/v2/torrents/info", timeout=10)
        import json as _json

        torrents = _json.loads(resp.read().decode("utf-8"))
        hashes = "|".join(t["hash"] for t in torrents)
        if hashes:
            opener.open(
                urllib.request.Request(
                    f"{qbit_url}/api/v2/torrents/delete",
                    data=urllib.parse.urlencode({"hashes": hashes, "deleteFiles": "false"}).encode(),
                    method="POST",
                ),
                timeout=15,
            )
    except Exception:
        pass
PREFIX_EOF

run_gate "$T1"
if [[ "$RC" -eq 1 ]] && printf '%s' "$OUT" | grep -q 'test_stress_prefix.py'; then
    pass "the verbatim pre-fix purge FAILs the gate (rc=1) and the file is named"
else
    fail "mutation arm: expected rc=1 naming the file, got rc=$RC"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi
if printf '%s' "$OUT" | grep -q 'CM-NO-UNSCOPED-LIVE-DESTRUCTION: PASS'; then
    fail "mutation arm printed PASS — the gate reported clean on the destroying shape"
else
    pass "mutation arm never claims PASS"
fi

# ---------------------------------------------------------------------------
# ARM 2 — GOLDEN-FALSE: the diff-scoped shape must NOT fire (§11.4.201(1)).
# A gate that refuses correct code is as bad as one that misses the defect.
# ---------------------------------------------------------------------------
T2="$(new_tree scoped)"
cat > "$T2/tests/test_stress_fixed.py" <<'SCOPED_EOF'
def _snapshot(qbit_url):
    resp = opener.open(f"{qbit_url}/api/v2/torrents/info", timeout=10)
    return {t["hash"] for t in json.loads(resp.read().decode("utf-8"))}


def _purge_added(before, qbit_url):
    if before is None:
        return
    added = _snapshot(qbit_url) - before
    if added:
        opener.open(
            urllib.request.Request(
                f"{qbit_url}/api/v2/torrents/delete",
                data=urllib.parse.urlencode(
                    {"hashes": "|".join(sorted(added)), "deleteFiles": "false"}
                ).encode(),
                method="POST",
            ),
            timeout=15,
        )
SCOPED_EOF

run_gate "$T2"
if [[ "$RC" -eq 0 ]] && printf '%s' "$OUT" | grep -q 'CM-NO-UNSCOPED-LIVE-DESTRUCTION: PASS'; then
    pass "golden-FALSE: the diff-scoped shape passes cleanly (rc=0)"
else
    fail "golden-FALSE arm: expected rc=0 + PASS, got rc=$RC"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi

# ---------------------------------------------------------------------------
# ARM 3 — CARRIER: a set difference that exists only in a COMMENT must not
# satisfy the check (§11.4.201(7)(a) — a token that MENTIONS X is not X).
# ---------------------------------------------------------------------------
T3="$(new_tree carrier)"
cat > "$T3/tests/test_carrier.py" <<'CARRIER_EOF'
# The correct implementation would compute: added = after - before
def _purge(qbit_url):
    resp = opener.open(f"{qbit_url}/api/v2/torrents/info", timeout=10)
    hashes = "|".join(t["hash"] for t in json.loads(resp.read()))
    opener.open(urllib.request.Request(f"{qbit_url}/api/v2/torrents/delete", data=hashes))
CARRIER_EOF

run_gate "$T3"
if [[ "$RC" -eq 1 ]]; then
    pass "carrier arm: a commented-out set difference does NOT satisfy the gate"
else
    fail "carrier arm: expected rc=1, got rc=$RC — prose satisfied a structural check"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi

# ---------------------------------------------------------------------------
# ARM 3b — DOCSTRING CARRIER: a Python DOCSTRING is neither a `#` comment nor
# code. An earlier draft stripped only `#` comments, so a module docstring
# reading "added = after - before" satisfied the check on a file containing no
# such operation. Found against tests/unit/test_stress_purge_scoping.py during
# authoring — the gate's own new test file was passing on prose.
# ---------------------------------------------------------------------------
T3B="$(new_tree docstring_carrier)"
cat > "$T3B/tests/test_docstring_carrier.py" <<'DOCSTR_EOF'
"""Cleanup helper.

The correct shape is: added = after - before
"""


def _purge(qbit_url):
    resp = opener.open(f"{qbit_url}/api/v2/torrents/info", timeout=10)
    hashes = "|".join(t["hash"] for t in json.loads(resp.read()))
    opener.open(urllib.request.Request(f"{qbit_url}/api/v2/torrents/delete", data=hashes))
DOCSTR_EOF

run_gate "$T3B"
if [[ "$RC" -eq 1 ]]; then
    pass "docstring arm: a set difference living only in a docstring does NOT satisfy the gate"
else
    fail "docstring arm: expected rc=1, got rc=$RC — a docstring satisfied a structural check"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi

# ---------------------------------------------------------------------------
# ARM 4 — PROSE FALSE-POSITIVE GUARD: a file that MENTIONS `torrents/info` in
# an operator-facing message while issuing only SCOPED requests must pass.
# This is the real shape of challenges/extension/*.sh, which an earlier draft
# of this gate wrongly refused.
# ---------------------------------------------------------------------------
T4="$(new_tree prose)"
cat > "$T4/challenges/probe.sh" <<'PROSE_EOF'
#!/usr/bin/env bash
FOUND="$(curl -sS "$QBIT_BASE/api/v2/torrents/info?hashes=${INFOHASH}" || true)"
if [ -z "$FOUND" ]; then
  QBIT_NOTE="infohash not (yet) in torrents/info — dead/synthetic magnet"
fi
curl -sS -X POST "$QBIT_BASE/api/v2/torrents/delete" --data "hashes=${INFOHASH}&deleteFiles=true"
PROSE_EOF

run_gate "$T4"
if [[ "$RC" -eq 0 ]]; then
    pass "prose arm: a scoped deleter that merely mentions torrents/info passes"
else
    fail "prose arm: expected rc=0, got rc=$RC — false-positive refusal on correct code"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi

# ---------------------------------------------------------------------------
# ARM 4b — EXEMPTION FENCE. The fence is a BYPASS PATH, so it needs its own
# arms or it becomes the hiding place the gate was built to remove.
#   (i)  a marker with a CLOSED-SET reason exempts, and is REPORTED (never a
#        silent skip — an exemption nobody sees is a skip);
#   (ii) a marker with an INVENTED reason does NOT exempt.
# ---------------------------------------------------------------------------
T4B="$(new_tree exempt_valid)"
cat > "$T4B/tests/test_stub.py" <<'EXEMPT_EOF'
# CM-NO-UNSCOPED-LIVE-DESTRUCTION: EXEMPT reason=stub_server_not_a_client — a stub server.
def handler(self):
    if self.path.startswith("/api/v2/torrents/info"):
        return
    if self.path.startswith("/api/v2/torrents/delete"):
        return
EXEMPT_EOF

run_gate "$T4B"
if [[ "$RC" -eq 0 ]] && printf '%s' "$OUT" | grep -q 'exempted file(s)' \
   && printf '%s' "$OUT" | grep -q 'test_stub.py'; then
    pass "exemption arm: a closed-set reason exempts AND the exemption is reported"
else
    fail "exemption arm: expected rc=0 with the exemption reported, got rc=$RC"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi

T4C="$(new_tree exempt_invented)"
sed 's/reason=stub_server_not_a_client/reason=because_i_said_so/' \
    "$T4B/tests/test_stub.py" > "$T4C/tests/test_stub.py"
run_gate "$T4C"
if [[ "$RC" -eq 1 ]]; then
    pass "exemption arm: an INVENTED reason does not exempt (closed set enforced)"
else
    fail "exemption arm: an invented reason bypassed the gate (rc=$RC)"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi

# ---------------------------------------------------------------------------
# ARM 5 — EMPTY TREE: no destructive calls at all must pass, and must not be
# mistaken for a blind read.
# ---------------------------------------------------------------------------
T5="$(new_tree empty)"
run_gate "$T5"
if [[ "$RC" -eq 0 ]]; then
    pass "empty arm: a tree with no destructive calls passes"
else
    fail "empty arm: expected rc=0, got rc=$RC"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi

# ---------------------------------------------------------------------------
# ARM 6 — MISSING SCAN ROOTS: the gate must report a HARNESS ERROR, never a
# quiet clean verdict. A tree it cannot see is not a tree without violations
# (§11.4.201(6) — a blind reader and a clean tree return the identical zero).
# ---------------------------------------------------------------------------
T6="$WORK/no_roots"
mkdir -p "$T6"
run_gate "$T6"
if [[ "$RC" -eq 2 ]] && printf '%s' "$OUT" | grep -q 'HARNESS ERROR'; then
    pass "missing-roots arm is a HARNESS ERROR (rc=2), not a clean verdict"
else
    fail "missing-roots arm: expected rc=2 + HARNESS ERROR, got rc=$RC"
    printf '%s\n' "$OUT" | sed 's/^/      /'
fi
if printf '%s' "$OUT" | grep -q 'CM-NO-UNSCOPED-LIVE-DESTRUCTION: PASS'; then
    fail "missing-roots arm reported PASS — an unscanned tree must never read as clean"
else
    pass "missing-roots arm does not claim PASS (no false-null)"
fi

echo
if [[ "$fails" -gt 0 ]]; then
    echo "=== META-TEST FAIL: $fails arm(s) diverged — the gate is not trustworthy ==="
    exit 1
fi
echo "=== META-TEST PASS: mutation caught, correct code untouched, blind read refused ==="
exit 0
