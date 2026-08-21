#!/usr/bin/env bash
# test_check_cm_plugin_count.sh — §1.1 paired-mutation meta-test for
# scripts/pre_build/check_cm_plugin_count.sh (CM-PLUGIN-COUNT).
#
# TDD (§11.4.43/§11.4.115/§11.4.224): this meta-test is authored BEFORE the
# gate is trusted. It proves the gate is not a bluff by exercising it against
# hermetic fixture roots with KNOWN outcomes, plus a real-tree smoke run.
#
# WHY A GATE AT ALL (BOB-149): the managed-plugin roster count is load-bearing
# — constitution Principle II enumerates the roster by name, §11.4.86 requires
# derived docs to re-sync when `install-plugin.sh`'s `PLUGINS=()` array
# changes, and the release checklist step 3 asserts the count. It had already
# drifted to 42 in CLAUDE.md and 48 in the README badge.
#
# Fixtures (each is a self-contained fake repo root):
#   golden-good        -> rc 0  (every documented count matches its derivation)
#   golden-bad-curated -> rc 1  (CLAUDE.md says 7, array holds 3 — the raw
#                                BOB-149 drift shape)
#   golden-bad-legacy  -> rc 1  (regression fixture for the ACTUAL pre-fix
#                                CLAUDE.md wording `**42 managed plugins**`,
#                                which carries no marker at all. A gate that
#                                only understood the new marker convention
#                                would silently PASS the very text BOB-149 was
#                                filed against — a §11.4.201(6) false-null.)
#   golden-bad-missing -> rc 1  (the mandatory `curated` marker deleted. Closes
#                                the §11.4.227 metric-gaming channel: deleting
#                                the number must not be a way to go green.)
#   golden-bad-engines -> rc 1  (an extra engine module on disk that no
#                                documented count accounts for)
#   golden-good-utility-> rc 0  (a NON-engine utility module added to plugins/;
#                                the engine count must NOT move. This is the
#                                §11.4.201(1) false-POSITIVE guard: a gate that
#                                counted every *.py as an engine would refuse a
#                                perfectly healthy tree.)
#   golden-good-carrier-> rc 0  (prose that MENTIONS other plugin numbers
#                                ("the canonical 12", "5 plugins gained ...")
#                                without carrying a marker must NOT be read as
#                                a roster count — the §11.4.201(7)(a)
#                                carrier-vs-thing rule.)
#   golden-bad-multimarker -> rc 1  (3 markers crammed on one line, all counts
#                               correct — the cramming alone must FAIL, or the
#                               2nd and 3rd would go silently unchecked)
#   real-tree          -> rc 0  (the actual boba checkout, after the BOB-149
#                                documentation fix)
#
# A gate that PASSes any golden-bad, or FAILs any golden-good or the real
# tree, is itself the bluff (§11.4.107(10)) and this harness reports it.
#
# Usage:   bash tests/pre_build/test_check_cm_plugin_count.sh
# Inputs:  none (no stdin, no env input).
# Outputs: per-case PASS/FAIL lines on stdout; failure diagnostics on stdout.
# Side-effects: creates and removes one mktemp -d tree; touches nothing in the
#               repository (the real-tree case is a read-only scan).
# Dependencies: bash, mktemp, sed, grep, find.
#
# Exit codes:
#   0 — every fixture (+ the real-tree smoke check) matched its expectation.
#   1 — one or more checks diverged from the expected outcome.
#   2 — harness/environment error (gate missing or not executable).
#
# Cross-refs: §11.4.1 §11.4.4 §11.4.6 §11.4.43 §11.4.69 §11.4.86 §11.4.107(10)
#             §11.4.108 §11.4.115 §11.4.135 §11.4.201 §11.4.224 §11.4.227.

set -euo pipefail

HARNESS_NAME="test_check_cm_plugin_count"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GATE="$REPO_ROOT/scripts/pre_build/check_cm_plugin_count.sh"

if [[ ! -f "$GATE" ]]; then
    echo "FAIL($HARNESS_NAME): gate script not found at $GATE" >&2
    echo "  (expected on the RED run — this meta-test is authored FIRST per" >&2
    echo "   §11.4.115/§11.4.224; implement the gate next)" >&2
    exit 2
fi
if [[ ! -x "$GATE" ]]; then
    echo "FAIL($HARNESS_NAME): gate script not executable at $GATE" >&2
    exit 2
fi

TMPDIR_ROOT="$(mktemp -d -t plugin_count_meta.XXXXXX)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

fails=0

run_gate() {
    # $1 = fixture root. Result returned via globals to avoid a $(...)
    # command-substitution exit-status trap under `set -e`.
    local root="$1" out err rc
    out="$(mktemp -p "$TMPDIR_ROOT")"
    err="$(mktemp -p "$TMPDIR_ROOT")"
    set +e
    "$GATE" --root "$root" >"$out" 2>"$err"
    rc=$?
    set -e
    GOT_RC="$rc"; GOT_OUT="$out"; GOT_ERR="$err"
}

assert_rc() {
    local name="$1" want_rc="$2"
    if [[ "$GOT_RC" -eq "$want_rc" ]]; then
        echo "PASS: $name (rc=$GOT_RC as expected)"
    else
        echo "FAIL: $name — expected rc=$want_rc got rc=$GOT_RC"
        echo "  --- stdout ---"; sed 's/^/    /' "$GOT_OUT"
        echo "  --- stderr ---"; sed 's/^/    /' "$GOT_ERR"
        fails=$((fails + 1))
    fi
}

# ---------------------------------------------------------------------------
# make_fixture <name> <n_curated> <n_bootstrap> <engine-names...>
#   Builds a minimal fake repo root: install-plugin.sh + setup.sh with real
#   PLUGINS=() arrays, a plugins/ tree, and (by default) no CLAUDE.md — each
#   caller writes its own CLAUDE.md so the documented counts are explicit.
# ---------------------------------------------------------------------------
make_fixture() {
    local name="$1"; shift
    local root="$TMPDIR_ROOT/$name"
    mkdir -p "$root/plugins/community" "$root/plugins/webui_compatible"

    # install-plugin.sh curated array = every engine name passed in.
    {
        echo '#!/usr/bin/env bash'
        echo 'PLUGINS=('
        local e
        for e in "$@"; do echo "  \"$e\""; done
        echo ')'
    } > "$root/install-plugin.sh"

    # setup.sh bootstrap array = the first engine only (a proper subset).
    {
        echo '#!/usr/bin/env bash'
        echo 'PLUGINS=('
        echo "    \"$1\""
        echo ')'
    } > "$root/setup.sh"

    # One engine module per curated name, each satisfying the contract.
    local e
    for e in "$@"; do
        cat > "$root/plugins/$e.py" <<PYEOF
class ${e}(object):
    url = 'https://example.invalid/'
    name = '${e}'
    supported_categories = {'all': 'all'}

    def search(self, what, cat='all'):
        pass

    def download_torrent(self, info):
        pass
PYEOF
    done
    echo "$root"
}

# ---------------------------------------------------------------------------
# Fixture 1 (golden-good): every documented count matches its derivation.
# ---------------------------------------------------------------------------
GOOD="$(make_fixture golden_good alpha beta gamma)"
cat > "$GOOD/CLAUDE.md" <<'MDEOF'
## Plugin System

- **3 search-plugin engines** are managed by `install-plugin.sh` <!-- CM-PLUGIN-COUNT: curated -->
- **3 distinct engine modules** exist on disk <!-- CM-PLUGIN-COUNT: engines -->
- **1 bootstrap plugin** is copied by `setup.sh` <!-- CM-PLUGIN-COUNT: bootstrap -->
- **3 files** sit directly in `plugins/` <!-- CM-PLUGIN-COUNT: toplevel -->
- **3 files** exist recursively <!-- CM-PLUGIN-COUNT: recursive -->
MDEOF
run_gate "$GOOD"
assert_rc "golden-good (all documented counts match derivation)" 0

# ---------------------------------------------------------------------------
# Fixture 2 (golden-bad-curated): the raw BOB-149 drift — documented curated
# count disagrees with the authoritative PLUGINS=() array.
# ---------------------------------------------------------------------------
BAD1="$(make_fixture golden_bad_curated alpha beta gamma)"
cat > "$BAD1/CLAUDE.md" <<'MDEOF'
## Plugin System

- **7 search-plugin engines** are managed by `install-plugin.sh` <!-- CM-PLUGIN-COUNT: curated -->
MDEOF
run_gate "$BAD1"
assert_rc "golden-bad-curated (doc says 7, array holds 3 — must FAIL)" 1

# ---------------------------------------------------------------------------
# Fixture 3 (golden-bad-legacy): the ACTUAL pre-fix CLAUDE.md wording, which
# carries no marker. The gate MUST still catch it, or the pre-fix file it was
# filed against would silently pass (§11.4.201(6) false-null).
# ---------------------------------------------------------------------------
BAD2="$(make_fixture golden_bad_legacy alpha beta gamma)"
cat > "$BAD2/CLAUDE.md" <<'MDEOF'
## Plugin System

`plugins/` has **42 managed plugins**. `install-plugin.sh` manages a curated subset.
MDEOF
run_gate "$BAD2"
assert_rc "golden-bad-legacy (unmarked '**42 managed plugins**' — must FAIL)" 1

# ---------------------------------------------------------------------------
# Fixture 4 (golden-bad-missing): mandatory `curated` marker deleted. Deleting
# the number must not be a route to green (§11.4.227 gaming channel).
# ---------------------------------------------------------------------------
BAD3="$(make_fixture golden_bad_missing alpha beta gamma)"
cat > "$BAD3/CLAUDE.md" <<'MDEOF'
## Plugin System

Plugins live in `plugins/` and are installed by `install-plugin.sh`.
MDEOF
run_gate "$BAD3"
assert_rc "golden-bad-missing (mandatory curated marker absent — must FAIL)" 1

# ---------------------------------------------------------------------------
# Fixture 5 (golden-bad-engines): an extra engine module on disk that no
# documented count accounts for (the roster/disk divergence direction).
# ---------------------------------------------------------------------------
BAD4="$(make_fixture golden_bad_engines alpha beta gamma)"
cat > "$BAD4/plugins/community/delta.py" <<'PYEOF'
class delta(object):
    url = 'https://example.invalid/'
    name = 'delta'
    supported_categories = {'all': 'all'}

    def search(self, what, cat='all'):
        pass

    def download_torrent(self, info):
        pass
PYEOF
cat > "$BAD4/CLAUDE.md" <<'MDEOF'
## Plugin System

- **3 search-plugin engines** are managed by `install-plugin.sh` <!-- CM-PLUGIN-COUNT: curated -->
- **3 distinct engine modules** exist on disk <!-- CM-PLUGIN-COUNT: engines -->
MDEOF
run_gate "$BAD4"
assert_rc "golden-bad-engines (4th engine on disk, doc says 3 — must FAIL)" 1

# ---------------------------------------------------------------------------
# Fixture 6 (golden-good-utility): a NON-engine utility module is added. The
# engine count must NOT move. §11.4.201(1) false-POSITIVE guard — a naive
# count-every-*.py gate would refuse this healthy tree.
# ---------------------------------------------------------------------------
GOOD2="$(make_fixture golden_good_utility alpha beta gamma)"
cat > "$GOOD2/plugins/helpers.py" <<'PYEOF'
def helper():
    return 1
PYEOF
cat > "$GOOD2/CLAUDE.md" <<'MDEOF'
## Plugin System

- **3 search-plugin engines** are managed by `install-plugin.sh` <!-- CM-PLUGIN-COUNT: curated -->
- **3 distinct engine modules** exist on disk <!-- CM-PLUGIN-COUNT: engines -->
- **4 files** sit directly in `plugins/` <!-- CM-PLUGIN-COUNT: toplevel -->
MDEOF
run_gate "$GOOD2"
assert_rc "golden-good-utility (utility module must not move engine count)" 0

# ---------------------------------------------------------------------------
# Fixture 7 (golden-good-carrier): prose MENTIONING other plugin numbers with
# no marker must not be read as a roster count (§11.4.201(7)(a)).
# ---------------------------------------------------------------------------
GOOD3="$(make_fixture golden_good_carrier alpha beta gamma)"
cat > "$GOOD3/CLAUDE.md" <<'MDEOF'
## Plugin System

- **3 search-plugin engines** are managed by `install-plugin.sh` <!-- CM-PLUGIN-COUNT: curated -->

History: the retired canonical 12-plugin roster was replaced; a later round
added `download_torrent()` to 5 plugins, and 29 plugins work with the WebUI.
Those are 12, 5 and 29 — none of them is the roster count.
MDEOF
run_gate "$GOOD3"
assert_rc "golden-good-carrier (unmarked numbers are carriers, not counts)" 0

# ---------------------------------------------------------------------------
# Fixture 8 (golden-bad-multimarker): THREE markers crammed onto ONE line. The
# parser pairs one marker with one bolded number per line, so the 2nd and 3rd
# would be silently unchecked. This fixture exists because that exact shape was
# authored during the BOB-149 fix and initially slipped through: on this host
# `grep -coE` (ugrep 7.8.4) returns 3 at top level but 1 inside a
# `set -euo pipefail` subshell — a context-dependent instrument reading
# (§11.4.201(12)). The gate now counts occurrences via `grep -oE | wc -l` and
# FAILs closed. Note the stated numbers here are all CORRECT: the failure must
# come from the cramming alone, proving the multi-marker rule is what fires and
# not an incidental count mismatch.
# ---------------------------------------------------------------------------
BAD5="$(make_fixture golden_bad_multimarker alpha beta gamma)"
cat > "$BAD5/CLAUDE.md" <<'MDEOF'
## Plugin System

- **3 search-plugin engines** <!-- CM-PLUGIN-COUNT: curated --> and **3 modules** <!-- CM-PLUGIN-COUNT: engines --> and **3 files** <!-- CM-PLUGIN-COUNT: toplevel -->
MDEOF
run_gate "$BAD5"
assert_rc "golden-bad-multimarker (3 markers on one line, all counts correct — must still FAIL)" 1

# ---------------------------------------------------------------------------
# Real-tree smoke check: the gate MUST pass the actual boba checkout after the
# BOB-149 documentation fix (§11.4.108 — the runtime signature of the fix).
# ---------------------------------------------------------------------------
run_gate "$REPO_ROOT"
assert_rc "real-tree (boba checkout after the BOB-149 fix)" 0

echo
if [[ $fails -ne 0 ]]; then
    echo "$HARNESS_NAME: FAIL — $fails check(s) diverged from expected outcome" >&2
    exit 1
fi
echo "$HARNESS_NAME: PASS — CM-PLUGIN-COUNT honest across 8 fixtures + real tree (§11.4.107(10))"
exit 0
