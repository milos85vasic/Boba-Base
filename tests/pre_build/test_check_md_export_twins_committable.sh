#!/usr/bin/env bash
# test_check_md_export_twins_committable.sh — §11.4.107(10) self-validated
# harness for scripts/pre_build/check_md_export_twins_committable.sh
# (BOB-219 acceptance criterion 4).
#
# WHY THIS DRIVES THE REAL GUARD (§11.4.249 producer != oracle != gate): this
# harness EXECUTES the guard script and reads its exit code + stdout/stderr.
# It does NOT reimplement the guard's own scan/scope logic inside itself.
#
# Every scratch tree is built under a real `mktemp -d` directory and
# destroyed on EXIT (trap). Nothing inside the REAL project checkout's
# tracked tree is ever created, staged, or touched by this harness — except
# the one read-only invocation of the real repo root in ARM 6, which never
# mutates anything (the guard itself is read-only: it only ever calls
# `git check-ignore`).
#
# Cases:
#   1. RED   (golden-GOOD)   — a tracked .md whose existing .html twin is
#                              silently swallowed by .gitignore (no rescue
#                              entry) -> guard exits non-zero, names the
#                              swallowed twin + the source .md + the exact
#                              blocking .gitignore:<line> rule.
#   2. GREEN (fix applied)   — same fixture, PLUS an explicit `!` rescue
#                              line for the twin -> guard exits 0.
#   3. golden-FALSE (no twin) — a tracked .md with NO existing export twins
#                              at all -> guard exits 0 (never flags a merely
#                              MISSING twin — that is a different, already-
#                              owned invariant, not this one).
#   4. golden-FALSE (twin OK) — a tracked .md whose existing .html twin is
#                              NOT matched by any deny rule -> guard exits 0.
#   5. fail-closed            — no positional arg / nonexistent repo root /
#                              non-git directory -> guard exits 2 in all
#                              three cases.
#   6. real-repo GREEN        — the actual project checkout, as it stands
#                              right now, has zero swallowed §11.4.65 export
#                              twins -> guard exits 0 against the real root.
#   7. paired mutation (§1.1) — break the guard (force its detection branch
#                              to a no-op) -> ARM 1's assertion MUST itself
#                              flip to FAIL against the broken guard, then
#                              PASS again once restored — proving this test
#                              is load-bearing, not decorative.
#
# Exit: 0 every case behaved as specified | 1 a case diverged | 2 harness error.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD_SRC="$REPO_ROOT/scripts/pre_build/check_md_export_twins_committable.sh"

if [[ ! -x "$GUARD_SRC" ]]; then
  echo "HARNESS ERROR: guard missing or not executable at $GUARD_SRC" >&2
  exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bob219_twins.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

fail=0
ok()   { printf '  [ok]   %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; fail=1; }

# ------------------------------------------------------------- build fixture
#
# Reproduces the EXACT pre-BOB-219 state rather than an invented filename:
# real .gitignore, minus the two rescue lines this session's fix (criterion
# 1, already committed upstream of this test) added for
# docs/guides/tracker-credentials.{html,pdf}. The .md source keeps its own
# pre-existing rescue (line 38, `!docs/guides/tracker-credentials.md`) —
# only the TWIN rescue lines are removed — so the fixture faithfully
# recreates "source is rescued, its own twins are not" without guessing at
# a substitute filename collision.
build_fixture() {
  local dir="$WORK/fixture"
  rm -rf "$dir"; mkdir -p "$dir"
  git -C "$dir" init -q .
  git -C "$dir" config user.email bob219@local
  git -C "$dir" config user.name  bob219

  grep -vF -e '!docs/guides/tracker-credentials.html' \
           -e '!docs/guides/tracker-credentials.pdf' \
    "$REPO_ROOT/.gitignore" > "$dir/.gitignore"

  mkdir -p "$dir/docs/guides"
  printf '# Fixture guide\n\nSome content.\n' > "$dir/docs/guides/tracker-credentials.md"
  git -C "$dir" add docs/guides/tracker-credentials.md .gitignore
  git -C "$dir" commit -q -m 'fixture: tracked in-scope .md (pre-BOB-219 gitignore state)'

  # The twin: the reconstructed pre-fix .gitignore does NOT rescue it
  # (untracked, ignored by *credentials*) — the swallowed-twin defect.
  printf '<html><body>rendered</body></html>\n' > "$dir/docs/guides/tracker-credentials.html"

  # A second, control .md whose twin is NOT secret-shaped and NOT swallowed
  # by anything (golden-FALSE case 4).
  printf '# Clean guide\n\nNothing suspicious.\n' > "$dir/docs/README-clean.md"
  git -C "$dir" add docs/README-clean.md
  git -C "$dir" commit -q -m 'fixture: clean .md with no twin yet'
  printf '<html><body>clean</body></html>\n' > "$dir/docs/README-clean.html"

  printf '%s' "$dir"
}

FIX="$(build_fixture)"

echo "BOB-219 criterion-4 guard test — $GUARD_SRC"
echo "fixture: $FIX"
echo

# ============================================================ ARM 1: RED ====
echo "-- ARM 1 (RED): swallowed twin, no rescue -> guard must FAIL loudly --"
out1="$("$GUARD_SRC" "$FIX" 2>&1)"; rc1=$?
if [ "$rc1" -eq 1 ] \
   && printf '%s' "$out1" | grep -qF 'docs/guides/tracker-credentials.html' \
   && printf '%s' "$out1" | grep -qF 'docs/guides/tracker-credentials.md' \
   && printf '%s' "$out1" | grep -qE 'gitignore:[0-9]+'; then
  ok "guard exited 1 and named the swallowed twin, its source .md, and the blocking rule"
else
  bad "guard did not fail loudly on the swallowed twin (rc=$rc1)"
  printf '%s\n' "$out1" | sed 's/^/    /'
fi
echo

# ========================================================== ARM 2: GREEN ===
echo "-- ARM 2 (GREEN): fix applied (rescue line added) -> guard must PASS --"
printf '\n!docs/guides/tracker-credentials.html\n' >> "$FIX/.gitignore"
out2="$("$GUARD_SRC" "$FIX" 2>&1)"; rc2=$?
if [ "$rc2" -eq 0 ]; then
  ok "guard exited 0 after the rescue line was added"
else
  bad "guard still fails after the rescue line was added (rc=$rc2)"
  printf '%s\n' "$out2" | sed 's/^/    /'
fi
echo

# ============================================== ARM 3: golden-FALSE, no twin
echo "-- ARM 3 (golden-FALSE): tracked .md with NO existing twin at all --"
NOTWIN="$WORK/notwin"
rm -rf "$NOTWIN"; mkdir -p "$NOTWIN/docs"
git -C "$NOTWIN" init -q .
git -C "$NOTWIN" config user.email t@t; git -C "$NOTWIN" config user.name t
cp "$REPO_ROOT/.gitignore" "$NOTWIN/.gitignore"
printf '# No twin yet\n' > "$NOTWIN/docs/no-twin.md"
git -C "$NOTWIN" add docs/no-twin.md .gitignore
git -C "$NOTWIN" commit -q -m 'fixture: .md with no export twin on disk'
out3="$("$GUARD_SRC" "$NOTWIN" 2>&1)"; rc3=$?
if [ "$rc3" -eq 0 ]; then
  ok "guard exited 0 — a merely-absent twin is never flagged"
else
  bad "guard incorrectly flagged an absent twin (rc=$rc3)"
  printf '%s\n' "$out3" | sed 's/^/    /'
fi
echo

# =========================================== ARM 4: golden-FALSE, twin is OK
echo "-- ARM 4 (golden-FALSE): twin exists and is NOT swallowed --"
out4="$("$GUARD_SRC" "$FIX" 2>&1)"; rc4=$?
# FIX now has: tracker-credentials.{md,html} rescued (ARM 2) + README-clean.{md,html} (never swallowed)
if [ "$rc4" -eq 0 ] && printf '%s' "$out4" | grep -qE '^OK:'; then
  ok "guard exits 0 on the whole fixture once every twin is committable"
else
  bad "guard did not confirm a clean state on the fully-rescued fixture (rc=$rc4)"
  printf '%s\n' "$out4" | sed 's/^/    /'
fi
echo

# ==================================================== ARM 5: fail-closed ===
echo "-- ARM 5: fail-closed on unresolvable input --"
set +e
"$GUARD_SRC" >/dev/null 2>&1; rc_noargs=$?
"$GUARD_SRC" "$WORK/does-not-exist" >/dev/null 2>&1; rc_missing=$?
mkdir -p "$WORK/not-a-git-repo"
"$GUARD_SRC" "$WORK/not-a-git-repo" >/dev/null 2>&1; rc_notgit=$?
set -e
if [ "$rc_noargs" -eq 2 ] && [ "$rc_missing" -eq 2 ] && [ "$rc_notgit" -eq 2 ]; then
  ok "guard exits 2 on: no args, nonexistent root, non-git directory"
else
  bad "fail-closed exit codes wrong: noargs=$rc_noargs missing=$rc_missing notgit=$rc_notgit (want 2/2/2)"
fi
echo

# ============================================== ARM 6: real-repo GREEN =====
echo "-- ARM 6: the real project checkout, as it stands, is clean --"
out6="$("$GUARD_SRC" "$REPO_ROOT" 2>&1)"; rc6=$?
if [ "$rc6" -eq 0 ]; then
  ok "guard exits 0 against the real repo root ($REPO_ROOT)"
  printf '%s\n' "$out6" | sed 's/^/    /'
else
  bad "guard reports a violation in the REAL repo (rc=$rc6) — genuine defect, not a harness bug"
  printf '%s\n' "$out6" | sed 's/^/    /'
fi
echo

# =========================================== ARM 7: paired mutation (§1.1) =
echo "-- ARM 7 (§1.1 paired mutation): a guard that never detects is itself a defect --"
MUT="$WORK/mutated_guard.sh"
# Force the detection branch to a permanent no-op (violations always 0),
# leaving everything else (arg parsing, scope walk, output prefix) intact —
# a targeted mutation of the load-bearing check, not a full rewrite.
sed 's/violations=\$((violations + 1))/violations=0 #MUTATED for paired §1.1/' "$GUARD_SRC" > "$MUT"
chmod +x "$MUT"
mut_out="$("$MUT" "$FIX" 2>&1)"; mut_rc=$?
# Re-run ARM 1's fixture through the MUTATED guard by rebuilding a fresh
# swallowed-twin fixture (the FIX dir was already rescued in ARM 2).
FIX_RED="$(build_fixture)"
mut_red_out="$("$MUT" "$FIX_RED" 2>&1)"; mut_red_rc=$?
if [ "$mut_red_rc" -eq 0 ]; then
  ok "mutated guard PASSES on the RED (swallowed-twin) fixture — confirms the"
  ok "  real guard's detection branch is load-bearing, not decorative"
else
  bad "mutated guard still FAILED on the RED fixture (rc=$mut_red_rc) — the mutation"
  bad "  did not neutralise detection; this test cannot prove the real guard matters"
fi
rm -f "$MUT"
echo

echo "======================================================================="
if [ "$fail" -eq 0 ]; then
  echo "RESULT: PASS (exit 0) — all arms behaved as specified"
  exit 0
else
  echo "RESULT: FAIL (exit 1) — see [FAIL] lines above"
  exit 1
fi
