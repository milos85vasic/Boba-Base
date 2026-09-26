#!/usr/bin/env bash
# test_bob194_agent_worktree_immunity.sh — BOB-194: prove, by measurement, that
# no tree-walking pre-build gate can be failed by a stale agent worktree under
# .claude/worktrees/, and that each gate still sees the SAME defect in scope.
#
# WHY (§11.4.201(1)): agent worktrees are ephemeral copies pinned at arbitrary
# commits. On 2026-08-25 CM-GO-TOOLCHAIN-MATCHES-BUILDER failed the main build
# on a finding that existed ONLY in .claude/worktrees/agent-afda1df906c537ab4.
# That gate now prunes .claude (its own test proves it). This test covers every
# OTHER gate that walks the filesystem, which the item left UNMEASURED or
# "clean in practice today" — practice today is not a guarantee.
#
# ORACLE (§11.4.245, METAMORPHIC with control needles). For each gate, three
# arms run in a scratch copy of the gate (the gates derive REPO_ROOT from their
# own location, so a copy under a temp tree scans only that tree):
#   A  golden-FALSE : a REAL violation planted ONLY under
#                     .claude/worktrees/agent-probe/<scan-root>/  -> gate exit 0
#   B  control      : the SAME violation planted inside the gate's scan root
#                     -> gate exit 1 (the gate is not blind to this defect)
#   M  paired §1.1 mutation: the gate copy's scan root widened to the repo root,
#                     with ONLY the arm-A plant present -> gate exit 1. This
#                     proves the arm-A plant is genuinely detectable, so arm A's
#                     exit 0 is immunity-by-scope and not a toothless fixture;
#                     and it is exactly the regression (a gate re-scoped to the
#                     repo root) this test exists to catch.
#
# Gates covered (every scripts/pre_build gate that calls find(1) or drives a
# find-based engine, plus invariant 39's repo-root arm):
#   check_cm_killpg_pgid_guard, check_cm_test_mock_pid_explicit_int,
#   check_cm_test_mock_pid_patched_when_real_pid,
#   check_cm_no_production_mutation_residue,
#   CM-DANGEROUS-COMBINATION-FAIL-CLOSED on "." with --max-depth 1 (invariant 39),
#   check_gitignore_swallow (git ls-files --others --ignored: .claude/* is
#   ignored, so worktree sources would otherwise read as "swallowed")
# Covered elsewhere: check_cm_go_toolchain_matches_builder (prunes .claude; its
#   own test_check_cm_go_toolchain_matches_builder.sh carries the pair).
# Structurally immune, stated not assumed: check_cm_plugin_count walks only
#   $PLUGINS_DIR; check_cm_workable_items_binary_fresh walks only the
#   workable-items source dir; gates using `git ls-files` never see untracked
#   worktrees. W1 below re-checks the first two find roots statically.
#
# Usage: bash tests/pre_build/test_bob194_agent_worktree_immunity.sh
# Exit:  0 every arm behaved; 1 any arm wrong; 3 precondition unmet.
# Constitution: §1.1, §11.4.107(10), §11.4.201(1)(6)(7)(b), §11.4.224, §11.4.245.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()  { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT   # §11.4.14 cleanup on every exit path

WT=".claude/worktrees/agent-probe"

# ---- fixture bodies (real defects each gate's own suite already uses) ------
killpg_bad() { printf 'import os\nfrom signal import SIGKILL\n\n\ndef _cleanup(proc):\n    os.killpg(1, SIGKILL)\n'; }
clean_py()   { printf 'def ok():\n    return 1\n'; }
mockpid_bad() {
    cat <<'PY'
import asyncio
from unittest.mock import AsyncMock, MagicMock


async def _hang():
    await asyncio.sleep(999)


async def fake_subprocess(*args, **kwargs):
    mock = AsyncMock()
    mock.returncode = None
    mock.stdout = MagicMock()
    mock.stdout.readline = AsyncMock(side_effect=_hang)
    mock.stderr = MagicMock()
    mock.stderr.read = AsyncMock(return_value=b"")
    mock.wait = AsyncMock(return_value=-9)
    mock.kill = MagicMock()
    return mock
PY
}
realpid_bad() {
    cat <<'PY'
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


async def _hang():
    await asyncio.sleep(999)


async def test_stuck_subprocess_killed_and_abandoned() -> None:
    proc = AsyncMock()
    proc.returncode = None
    proc.pid = 12345
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(side_effect=_hang)
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.wait = AsyncMock(return_value=-9)
    proc.kill = MagicMock()

    with (
        patch("asyncio.create_subprocess_exec", return_value=proc),
    ):
        pass
PY
}
M="MUT""ATED"   # assembled so this file never literally holds the marker
residue_bad() { printf 'def f():\n    # %s for RED\n    return True\n' "$M"; }
failopen_bad() { printf 'def f():\n    try:\n        return 1\n    except Exception:\n        pass\n'; }

# ---- sandbox helpers --------------------------------------------------------
# new_sb <name> <gate-rel> [engine-rel...] : fresh scratch repo with the gate copied
new_sb() {
    local sb="${TMP}/$1"; shift
    local rel
    rm -rf "${sb}"; mkdir -p "${sb}"
    for rel in "$@"; do
        mkdir -p "${sb}/$(dirname "${rel}")"
        cp "${REPO}/${rel}" "${sb}/${rel}"
    done
    echo "${sb}"
}
plant() { mkdir -p "$(dirname "$1")"; "$2" > "$1"; }   # plant <path> <body-fn>

# arm <label> <want-rc> <cmd...>
arm() {
    local label="$1" want="$2"; shift 2
    local out rc
    out="$("$@" 2>&1)"; rc=$?
    if [[ "${rc}" -eq "${want}" ]]; then
        ok "${label} (exit ${rc})"
    else
        bad "${label}: wanted exit ${want}, got ${rc}"
        printf '%s\n' "${out}" | sed -n '1,12p' | sed 's/^/          /'
    fi
}

run_three() {  # <name> <gate-rel> <scan-root> <badfile-name> <body-fn> <mut-sed> <clean-name> [engine-rel...]
    local name="$1" gate="$2" root="$3" bf="$4" body="$5" mut="$6" cleanf="$7"; shift 7
    local sb
    echo "-- ${name}"
    # A: plant only in the worktree (plus a clean in-scope file so the walk is never empty)
    sb="$(new_sb "${name}-A" "${gate}" "$@")"
    plant "${sb}/${root}/${cleanf}" clean_py
    plant "${sb}/${WT}/${root}/${bf}" "${body}"
    arm "${name} A golden-FALSE: defect only inside ${WT} does not fail the gate" 0 bash "${sb}/${gate}"
    # B: the same defect in scope
    sb="$(new_sb "${name}-B" "${gate}" "$@")"
    plant "${sb}/${root}/${cleanf}" clean_py
    plant "${sb}/${root}/${bf}" "${body}"
    arm "${name} B control: the same defect inside ${root}/ IS caught" 1 bash "${sb}/${gate}"
    # M: widen the scan root to the repo root; only the worktree plant present
    sb="$(new_sb "${name}-M" "${gate}" "$@")"
    plant "${sb}/${root}/${cleanf}" clean_py
    plant "${sb}/${WT}/${root}/${bf}" "${body}"
    sed -i "${mut}" "${sb}/${gate}"
    if cmp -s "${sb}/${gate}" "${REPO}/${gate}"; then
        bad "${name} M: mutation sed did not change the gate copy — mutation not applied"
    else
        arm "${name} M mutation (scan root widened to repo root) sees the worktree plant" 1 bash "${sb}/${gate}"
    fi
}

echo "BOB-194 — agent-worktree immunity, measured per gate"

run_three killpg scripts/pre_build/check_cm_killpg_pgid_guard.sh scripts bad.py killpg_bad \
    's|^DEFAULT_SCAN_ROOTS=(.*)$|DEFAULT_SCAN_ROOTS=(".")|' clean.py \
    constitution/scripts/gates/cm_killpg_pgid_guard.sh

run_three mockpid scripts/pre_build/check_cm_test_mock_pid_explicit_int.sh tests test_bad.py mockpid_bad \
    's|^DEFAULT_SCAN_ROOTS=(.*)$|DEFAULT_SCAN_ROOTS=(".")|' test_clean.py \
    constitution/scripts/gates/cm_test_mock_pid_explicit_int.sh

run_three realpid scripts/pre_build/check_cm_test_mock_pid_patched_when_real_pid.sh tests test_bad.py realpid_bad \
    's|^DEFAULT_SCAN_ROOTS=(.*)$|DEFAULT_SCAN_ROOTS=(".")|' test_clean.py

run_three residue scripts/pre_build/check_cm_no_production_mutation_residue.sh scripts bad.py residue_bad \
    's|"\${REPO_ROOT}/scripts" \\|"${REPO_ROOT}" \\|' clean.py

# ---- invariant 39's repo-root arm (depth-1) ---------------------------------
echo "-- dangerous-combination repo-root arm (invariant 39)"
DG="constitution/scripts/gates/cm_dangerous_combination_fail_closed.sh"
sb="$(new_sb danger-A "${DG}")"
plant "${sb}/${WT}/webui.py" failopen_bad
plant "${sb}/clean.py" clean_py
arm "danger A golden-FALSE: fail-open only inside ${WT} is not reported at depth 1" 0 \
    bash "${sb}/${DG}" --root "${sb}" --max-depth 1 --quiet
sb="$(new_sb danger-B "${DG}")"
plant "${sb}/webui.py" failopen_bad
arm "danger B control: the same fail-open at the repo root IS reported" 1 \
    bash "${sb}/${DG}" --root "${sb}" --max-depth 1 --quiet
sb="$(new_sb danger-M "${DG}")"
plant "${sb}/${WT}/webui.py" failopen_bad
plant "${sb}/clean.py" clean_py
arm "danger M mutation (--max-depth 1 dropped) sees the worktree plant" 1 \
    bash "${sb}/${DG}" --root "${sb}" --quiet
# Wiring: the REAL sweep must still bound the "." root at depth 1.
if grep -qF '[[ "${_dr}" == "." ]] && _dr_extra_args=(--max-depth 1)' "${REPO}/scripts/pre_build_verification.sh"; then
    ok "danger W: pre_build_verification.sh still scans the repo-root arm with --max-depth 1"
else
    bad "danger W: the '.' DANGER_ROOTS arm is no longer depth-bounded — worktrees would be walked"
fi

# ---- git-based walk: check_gitignore_swallow (ls-files --others --ignored) ----
# .claude/* is gitignored, so a worktree's source files ARE "ignored + untracked"
# — exactly what this guard refuses on. It must skip them by path segment.
echo "-- gitignore swallow guard (git-based walk)"
SG="scripts/pre_build/check_gitignore_swallow.sh"
mk_git_sb() {  # <name> -> sandbox git repo with the real .claude ignore rule
    local sb; sb="$(new_sb "$1" "${SG}")"
    git -C "${sb}" init -q
    printf '.claude/*\n!.claude/settings.json\nscripts/swallowed.sh\n' > "${sb}/.gitignore"
    git -C "${sb}" add .gitignore "${SG}" && git -C "${sb}" -c user.email=t@t -c user.name=t commit -qm init
    echo "${sb}"
}
sb="$(mk_git_sb swallow-A)"
plant "${sb}/${WT}/scripts/tool.sh" clean_py
arm "swallow A golden-FALSE: ignored source inside ${WT} is not reported as swallowed" 0 bash "${sb}/${SG}" "${sb}"
sb="$(mk_git_sb swallow-B)"
plant "${sb}/scripts/swallowed.sh" clean_py
arm "swallow B control: an ignored first-party source outside the worktree IS reported" 1 bash "${sb}/${SG}" "${sb}"
sb="$(mk_git_sb swallow-M)"
plant "${sb}/${WT}/scripts/tool.sh" clean_py
sed -i 's/ \.worktrees worktrees$/ .worktrees/' "${sb}/${SG}"
if cmp -s "${sb}/${SG}" "${REPO}/${SG}"; then
    bad "swallow M: mutation sed did not change the gate copy — mutation not applied"
else
    arm "swallow M mutation ('worktrees' dropped from the excluded names) sees the worktree file" 1 bash "${sb}/${SG}" "${sb}"
fi

# ---- W1: structurally-immune gates keep their narrow find roots -------------
if grep -qE "find \"\\\$PLUGINS_DIR\"" "${REPO}/scripts/pre_build/check_cm_plugin_count.sh"; then
    ok "W1a check_cm_plugin_count walks only \$PLUGINS_DIR"
else
    bad "W1a check_cm_plugin_count find root changed — re-measure worktree exposure"
fi
if grep -qF 'cd "${WI_DIR}" && find .' "${REPO}/scripts/pre_build/check_cm_workable_items_binary_fresh.sh"; then
    ok "W1b check_cm_workable_items_binary_fresh walks only the workable-items source dir"
else
    bad "W1b check_cm_workable_items_binary_fresh find root changed — re-measure worktree exposure"
fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
