#!/usr/bin/env bash
# test_export_staleness_parser_edges.sh — edge coverage for the two git parsers in
# scripts/lib/export_staleness.sh (BOB-249 follow-up, stream A).
#   1. `git status -z` rename/copy records: the ORIGINAL path must be marked dirty
#      too, and an original path starting with R/C must not swallow the next entry.
#   2. history keys: paths with tab / newline / double-quote / backslash must be
#      keyed EXACTLY (git log C-quotes them unless -z), else a clean file silently
#      falls back to mtime.
#   3. no awk dependency (RS="\0" is not portable: busybox awk truncates at NUL).
# All fixtures are mktemp git repos; nothing touches the real checkout.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
HELPER="${EXPORT_STALENESS_HELPER:-${PROJECT_ROOT}/scripts/lib/export_staleness.sh}"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
[[ -f "$HELPER" ]] || { echo "  FAIL: helper missing: $HELPER"; exit 1; }

# awk trap: any awk invocation is a loud failure marker (item 3).
TRAP="$(mktemp -d)"; FIX="$(mktemp -d)"
trap 'rm -rf "$TRAP" "$FIX"' EXIT
printf '#!/bin/sh\necho AWK_INVOKED >>"%s/awk_used"\nexit 99\n' "$TRAP" > "$TRAP/awk"
chmod +x "$TRAP/awk"
for a in gawk mawk nawk original-awk; do cp "$TRAP/awk" "$TRAP/$a"; done
# EXPORT_STALENESS_NO_AWK_TRAP=1 disables the trap (used to show items 1/2 RED on the
# old awk parser independently of item 3).
[[ -n "${EXPORT_STALENESS_NO_AWK_TRAP:-}" ]] || PATH="$TRAP:$PATH"
# shellcheck disable=SC1090
source "$HELPER"
_reset() { _EXPORT_MAPS_ROOT=""; }

cd "$FIX" && git init -q . && git config user.email t@t && git config user.name t
git config core.quotePath true
commit() { git add -A >/dev/null && git commit -qm "$1"; }

# ---------- item 1: rename / copy records ----------
mkdir r && printf 'v1\n' > "r/old name.md"; printf 'v1\n' > "r/old name.html"
printf 'v1\n' > r/Rold.md; printf 'v1\n' > r/Rold.html; printf 'v1\n' > r/Cfoo.md
commit base
git mv "r/old name.md" "r/new name.md"      # staged rename, original has a space
git mv r/Rold.md r/Rnew.md                  # original path starts with R
git mv r/Cfoo.md r/Cbar.md                  # original path starts with C
printf 'v2\n' > r/zz_untracked.md           # entry after the renames must survive
_reset; _export_build_maps "$FIX"
chk() { [[ -n "${_EXPORT_DIRTY[$1]:-}" ]] && pass "dirty: $1" || fail "NOT marked dirty: $1"; }
chk "r/new name.md"; chk "r/old name.md"          # ORIGINAL path of a staged rename
chk "r/Rnew.md";     chk "r/Rold.md"              # original starts with R
chk "r/Cbar.md";     chk "r/Cfoo.md"              # original starts with C
chk "r/zz_untracked.md"                            # next real entry not swallowed
[[ -z "${_EXPORT_DIRTY[Cfoo.md]:-}" && -z "${_EXPORT_DIRTY[old name.md]:-}" && -z "${_EXPORT_DIRTY[d.md]:-}" ]] \
    && pass "no garbage keys from mis-split records" || fail "garbage dirty key present"
commit renames

# ---------- item 2: history keys with hostile names ----------
mk_pair() { # name  -> writes name.md / name.html at v1
    printf 'v1\n' > "$1.md"; printf '<p>v1</p>\n' > "$1.html"; }
hostile=( $'tab\tname' 'quo"te' 'back\slash' $'new\nline' 'sp ace' 'Ünï cödé' $'mix\t"q"\\ \nz' )
mkdir h
i=0
for n in "${hostile[@]}"; do
    i=$((i+1)); mk_pair "h/$n"; mk_pair "h/sync$i"
done
commit hist-base
git commit -q --allow-empty -m "empty commit"
git checkout -qb side; printf 'side\n' > h/side.md; commit side
git checkout -q -; git merge -q --no-ff --no-edit side
i=0
for n in "${hostile[@]}"; do
    i=$((i+1)); printf 'v2 changed\n' > "h/$n.md"     # source-only change
done
commit "source-only updates"
for n in "${hostile[@]}"; do
    touch -d '2031-01-01 00:00:00' "h/$n.md" "h/$n.html"      # identical mtimes
done
_reset
for n in "${hostile[@]}"; do
    label="$(printf '%q' "$n")"
    if export_is_stale "$FIX/h/$n.md" "$FIX/h/$n.html" "$FIX"; then
        pass "history-stale clean pair detected: $label"
    else
        fail "history-stale clean pair reported FRESH (history key mis-quoted -> mtime fallback): $label"
    fi
done
# negative control: in-sync (same commit) hostile pair with checkout-order mtimes stays FRESH
mkdir h2; for n in "${hostile[@]}"; do mk_pair "h2/$n"; done; commit sync-hostile
for n in "${hostile[@]}"; do
    touch -d '2020-01-01 00:00:01' "h2/$n.html"; touch -d '2020-01-01 00:00:02' "h2/$n.md"
done
_reset
for n in "${hostile[@]}"; do
    label="$(printf '%q' "$n")"
    if export_is_stale "$FIX/h2/$n.md" "$FIX/h2/$n.html" "$FIX"; then
        fail "CONTROL: in-sync hostile-name pair reported STALE: $label"
    else
        pass "in-sync hostile-name pair stays fresh: $label"
    fi
done
# merge / empty commits do not disturb ordinals: side.md (merge-brought) resolves
printf '<p>s</p>\n' > h/side.html; commit side-export
touch -d '2031-01-01' h/side.md h/side.html; _reset
export_is_stale "$FIX/h/side.md" "$FIX/h/side.html" "$FIX" \
    && fail "side.md (older than side.html in history) reported STALE" || pass "merge/empty commits keep ordinals sane"

# ---------- item 4 (M6): verdicts must not depend on whether '*.docx' is in the pathspec ----------
# Shape (measured with 120 fuzzed merge histories: default walk diverged 3x): base has a.{md,html,pdf,docx};
# branch f: f1 regenerates html+pdf+docx, f2 edits md; main gets an unrelated commit; f is merged
# --no-ff with a.md/a.html/a.pdf resolved to main's (base) content and a.docx taken from f. The default
# walk is history-SIMPLIFIED, so whether f's commits are visited depends on whether the pathspec
# includes docx -> the html/pdf verdict flipped with an unrelated pattern. The walk must use
# --full-history so the verdict is a function of the twins alone. (Which verdict is "right" for this
# shape is undecidable from commit names: all three files equal base content, so the content-truth is
# FRESH, but the oracle only sees paths; --full-history says STALE = the safe direction, a regen.
# -m / --first-parent would say FRESH here but give false-FRESH for the common "regen then edit md on a
# branch" shape D below, so they are rejected.)
NODOCX="$TRAP/export_staleness_nodocx.sh"
sed "s/ '\*\.docx'//" "$HELPER" > "$NODOCX"
grep -q "'\*.docx'" "$NODOCX" && { fail "could not derive no-docx helper variant"; }
verdict() { # helper repo md sib -> STALE|fresh (fresh subshell: no cache leakage)
    ( source "$1"; export_is_stale "$3/$4" "$3/$5" "$3" && echo STALE || echo fresh ); }
R6="$(mktemp -d)"
(
  cd "$R6" && git init -q -b main . && git config user.email t@t && git config user.name t
  cm() { git add -A >/dev/null && git commit -qm "$1"; }
  for e in md html pdf docx; do echo base > "a.$e"; done; cm base
  git checkout -qb f; for e in html pdf docx; do echo f1 > "a.$e"; done; cm f1; echo f2 > a.md; cm f2
  git checkout -q main; echo x > u.txt; cm unrelated
  git merge --no-commit --no-ff -q f >/dev/null 2>&1
  for e in md html pdf; do git show "HEAD:a.$e" > "a.$e"; done; cm merge
) >/dev/null 2>&1
touch -d '2031-01-01' "$R6"/a.*   # mtimes must be irrelevant for a clean tree
for sib in html pdf; do
    w="$(verdict "$HELPER" md "$R6" a.md "a.$sib")"; n="$(verdict "$NODOCX" md "$R6" a.md "a.$sib")"
    [[ "$w" == "$n" ]] && pass "M6 a.md/a.$sib verdict independent of docx in pathspec ($w)" \
        || fail "M6 a.md/a.$sib verdict flips with pathspec: with-docx=$w without-docx=$n"
done
# shape D guard: regen then further md edit on a merged branch must stay STALE (kills first-parent / -m)
RD="$(mktemp -d)"
(
  cd "$RD" && git init -q -b main . && git config user.email t@t && git config user.name t
  cm() { git add -A >/dev/null && git commit -qm "$1"; }
  for e in md html pdf docx; do echo base > "a.$e"; done; cm base
  git checkout -qb f; echo f1 > a.md; cm f1; for e in html pdf docx; do echo f1 > "a.$e"; done; cm regen; echo f2 > a.md; cm f3
  git checkout -q main; echo x > u.txt; cm unrelated; git merge --no-ff -q f -m merge
) >/dev/null 2>&1
touch -d '2031-01-01' "$RD"/a.*
for h in "$HELPER" "$NODOCX"; do
    [[ "$(verdict "$h" md "$RD" a.md a.html)" == STALE ]] && pass "shape D (md edited after regen on merged branch) stays STALE [$(basename "$h")]" \
        || fail "shape D reported fresh (false-fresh) [$(basename "$h")]"
done
rm -rf "$R6" "$RD"

# ---------- item 3: no awk anywhere ----------
[[ -n "${EXPORT_STALENESS_NO_AWK_TRAP:-}" ]] && pass "awk trap disabled (skipped)" || { [[ ! -e "$TRAP/awk_used" ]] && pass "helper never invoked awk (portable across gawk/mawk/busybox)" \
    || fail "helper invoked awk ($(wc -l < "$TRAP/awk_used") times)"; }

echo "RESULT: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
