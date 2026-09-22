#!/usr/bin/env bash
# test_check_gitignore_swallow.sh — §11.4.107(10) self-validated-analyzer
# harness for scripts/pre_build/check_gitignore_swallow.sh (BOB-212).
#
# WHY THIS DRIVES THE REAL GUARD (§11.4.249 producer != oracle != gate): this
# harness EXECUTES the guard script and reads its exit code + stdout/stderr.
# It does NOT reimplement the guard's own detection logic inside itself — a
# harness that restates the detector is a producer=oracle collapse and
# cannot see the guard drift from what it is supposed to do.
#
# Every scratch tree is built under a real `mktemp -d` directory and
# destroyed on EXIT (trap). Nothing inside the REAL project checkout's
# tracked tree is ever created, staged, or touched by this harness.
#
# Cases (BOB-212 brief step 5, §11.4.107(10)):
#   1. golden-GOOD    — a swallowed first-party source file -> guard exits
#                        non-zero, names the file + the .gitignore:<N> rule.
#   2. golden-BAD      — the only ignored+untracked files are genuinely
#      (false-positive)  secret-shaped -> guard exits ZERO (never flags them).
#   3. clean tree      — nothing ignored+untracked at all -> guard exits ZERO.
#   4. excluded root   — a swallowed file lives under an excluded root
#                        (submodules/, node_modules/) -> guard exits ZERO.
#   5. paired mutation — break the guard (comment out its detection loop /
#      (§1.1)            hardcode exit 0) -> this test's ARM 1 assertion MUST
#                        itself flip to FAIL against the broken guard, then
#                        PASS again once restored — proving this test is
#                        load-bearing, not decorative.
#
# Exit: 0 every case behaved as specified | 1 a case diverged | 2 harness error.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD_SRC="$REPO_ROOT/scripts/pre_build/check_gitignore_swallow.sh"

if [[ ! -x "$GUARD_SRC" ]]; then
  echo "HARNESS ERROR: guard missing or not executable at $GUARD_SRC" >&2
  exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bob212_selftest.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

fails=0
pass() { printf 'PASS: %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*"; fails=$((fails + 1)); }

# ---------------------------------------------------------------- scratch tree
# new_tree <name> -> creates and inits a fresh git repo under $WORK/<name>,
# seeded with the REAL project's own .gitignore (real rules, no mock,
# §11.4.27), and prints its path.
new_tree() {
  local dir="$WORK/$1"
  rm -rf "$dir"
  mkdir -p "$dir"
  git -C "$dir" init -q .
  git -C "$dir" config user.email bob212-selftest@local
  git -C "$dir" config user.name  bob212-selftest
  cp "$REPO_ROOT/.gitignore" "$dir/.gitignore"
  printf '%s' "$dir"
}

run_guard() {  # $1 = guard path, $2 = tree -> sets OUT / RC
  OUT="$("$1" "$2" 2>&1)"
  RC=$?
}

# ======================================================= CASE 1: golden-GOOD
echo "-- case 1: golden-GOOD (swallowed first-party source file) --"
T1="$(new_tree case1_golden_good)"
mkdir -p "$T1/qBitTorrent-go/internal/jackettapi"
printf 'package jackettapi // BOB-212 golden-good subject\n' \
  > "$T1/qBitTorrent-go/internal/jackettapi/credentials_failclosed_test.go"

run_guard "$GUARD_SRC" "$T1"
if [ "$RC" -ne 0 ] \
   && printf '%s' "$OUT" | grep -qF -- "qBitTorrent-go/internal/jackettapi/credentials_failclosed_test.go" \
   && printf '%s' "$OUT" | grep -qE 'gitignore:[0-9]+'; then
  pass "case 1: guard exited non-zero ($RC) and named the file + gitignore:<N> rule"
else
  fail "case 1: expected non-zero exit naming file+rule; got rc=$RC out=$(printf '%s' "$OUT" | tr '\n' '|')"
fi
echo

# ================================================== CASE 2: golden-BAD (FP guard)
echo "-- case 2: golden-BAD / false-positive guard (only secret-shaped files) --"
T2="$(new_tree case2_golden_bad)"
mkdir -p "$T2/qBitTorrent-go/internal/jackettapi" "$T2/config" "$T2/secrets"
printf 'SECRET-PLACEHOLDER\n' > "$T2/.env"
printf 'SECRET-PLACEHOLDER\n' > "$T2/qBitTorrent-go/internal/jackettapi/tracker_creds.json"
printf 'SECRET-PLACEHOLDER\n' > "$T2/secrets/api.key"
printf 'SECRET-PLACEHOLDER\n' > "$T2/my_password.txt"

run_guard "$GUARD_SRC" "$T2"
if [ "$RC" -eq 0 ]; then
  pass "case 2: guard exited zero on a tree whose ONLY ignored+untracked files are secret-shaped"
else
  fail "case 2: expected exit 0 (never flag secret shapes); got rc=$RC out=$(printf '%s' "$OUT" | tr '\n' '|')"
fi
echo

# ============================================================= CASE 3: clean
echo "-- case 3: genuinely clean tree (nothing ignored+untracked) --"
T3="$(new_tree case3_clean)"
mkdir -p "$T3/scripts" "$T3/tests"
printf '#!/usr/bin/env bash\necho hi\n' > "$T3/scripts/hello.sh"
printf '#!/usr/bin/env bash\necho hi\n' > "$T3/tests/test_hello.sh"
git -C "$T3" add -A >/dev/null

run_guard "$GUARD_SRC" "$T3"
if [ "$RC" -eq 0 ]; then
  pass "case 3: guard exited zero on a clean tree with no ignored+untracked files"
else
  fail "case 3: expected exit 0 on a clean tree; got rc=$RC out=$(printf '%s' "$OUT" | tr '\n' '|')"
fi
echo

# ==================================================== CASE 4: excluded root
echo "-- case 4: swallowed file under an excluded root (not first-party) --"
T4="$(new_tree case4_excluded_root)"
mkdir -p "$T4/submodules/jackett/internal/jackettapi" \
         "$T4/frontend/node_modules/some-pkg"
printf 'package jackettapi // credentials-named but vendored/submodule\n' \
  > "$T4/submodules/jackett/internal/jackettapi/credentials_helper.go"
printf 'module.exports = {} // credentials-named but node_modules\n' \
  > "$T4/frontend/node_modules/some-pkg/credentials.js"

run_guard "$GUARD_SRC" "$T4"
if [ "$RC" -eq 0 ]; then
  pass "case 4: guard exited zero — excluded-root swallows are correctly NOT first-party"
else
  fail "case 4: expected exit 0 for excluded-root files; got rc=$RC out=$(printf '%s' "$OUT" | tr '\n' '|')"
fi
echo

# ===================================================== CASE 5: fail-closed
echo "-- case 5: fail-closed on unresolvable input (§11.4.252) --"
run_guard "$GUARD_SRC" "$WORK/does-not-exist-$$"
if [ "$RC" -eq 2 ]; then
  pass "case 5a: guard exited 2 on a nonexistent repo root"
else
  fail "case 5a: expected exit 2 on a nonexistent path; got rc=$RC"
fi

NOTGIT="$WORK/not_a_git_repo"
mkdir -p "$NOTGIT"
run_guard "$GUARD_SRC" "$NOTGIT"
if [ "$RC" -eq 2 ]; then
  pass "case 5b: guard exited 2 on a directory that is not a git repo"
else
  fail "case 5b: expected exit 2 on a non-git directory; got rc=$RC"
fi
echo

# =============================================== CASE 6: paired §1.1 mutation
# Proves case 1's assertion is load-bearing: a broken guard must make THIS
# harness's case-1-equivalent check FAIL, and the restored guard must make
# it PASS again.
echo "-- case 6: paired §1.1 mutation (guard broken -> this test detects it) --"
MUT_DIR="$WORK/mutated_guard"
mkdir -p "$MUT_DIR"
MUT_GUARD="$MUT_DIR/check_gitignore_swallow.sh"
cp "$GUARD_SRC" "$MUT_GUARD"
chmod +x "$MUT_GUARD"

# Mutation: hardcode a successful, empty verdict immediately after argument
# validation — the exact "always-pass" shape §11.4.120/§11.4.1 forbid a real
# gate from collapsing into. This neuters the detection loop entirely.
python3 - "$MUT_GUARD" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    text = f.read()
marker = 'if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then'
idx = text.index(marker)
end = text.index("fi\n", idx) + len("fi\n")
mutated = text[:end] + '\n# --- BOB-212 §1.1 MUTATION: always-pass shortcut ---\necho "MUTATED: always pass"\nexit 0\n' + text[end:]
with open(path, "w") as f:
    f.write(mutated)
PYEOF

T1MUT="$T1"  # reuse case 1's swallowed-file tree
run_guard "$MUT_GUARD" "$T1MUT"
if [ "$RC" -eq 0 ]; then
  pass "case 6a: mutated (always-pass) guard exits 0 on the swallowed-file tree — mutation confirmed live"
else
  fail "case 6a: mutation did not neuter the guard as expected; rc=$RC (mutation harness itself broken)"
fi

# This harness's own case-1 assertion, re-run against the MUTATED guard,
# MUST now report the divergence (i.e. the same check that passed in case 1
# must fail here) — that is what proves this test is load-bearing.
if [ "$RC" -ne 0 ] \
   && printf '%s' "$OUT" | grep -qF -- "qBitTorrent-go/internal/jackettapi/credentials_failclosed_test.go" \
   && printf '%s' "$OUT" | grep -qE 'gitignore:[0-9]+'; then
  fail "case 6b: mutated guard STILL satisfied the golden-good assertion — the mutation is not detectable (test is decorative)"
else
  pass "case 6b: mutated guard correctly FAILS the golden-good assertion (this test would catch a broken guard)"
fi

# Restore: confirm the REAL (unmutated) guard still passes the same check —
# proving the mutation, not the harness, was the thing that changed.
run_guard "$GUARD_SRC" "$T1MUT"
if [ "$RC" -ne 0 ] \
   && printf '%s' "$OUT" | grep -qF -- "qBitTorrent-go/internal/jackettapi/credentials_failclosed_test.go" \
   && printf '%s' "$OUT" | grep -qE 'gitignore:[0-9]+'; then
  pass "case 6c: restored (real, unmutated) guard passes the golden-good assertion again"
else
  fail "case 6c: real guard failed to re-pass after mutation removed; rc=$RC"
fi
echo

# ================================================================== SUMMARY
echo "===================================================================="
if [ "$fails" -eq 0 ]; then
  echo "RESULT: PASS — all cases behaved as specified (0 failures)."
  exit 0
fi
echo "RESULT: FAIL — $fails case(s) diverged from spec."
exit 1
