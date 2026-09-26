#!/usr/bin/env bash
# test_compute_badges_export_scope.sh — scripts/compute-badges.sh must export
# ONLY the files it modifies, and nothing at all for out-of-tree fixtures
# (BOB-249, item 7).
#
# THE DEFECT (bisected 2026-09-26): after rewriting README.md / docs/TESTING.md,
# compute-badges.sh ran `bash generate_markdown_exports.sh` with NO path
# argument — a full sweep of root + docs/ + scripts/ of the REAL tree — even
# when invoked with --readme/--testing-md pointing at temp fixtures (exactly what
# tests/unit/test_compute_badges_carrier_match.sh does). Measured in a scratch
# copy: that one test regenerated 42 tracked docx/pdf twins across the tree.
#
# SANDBOX: a throwaway tree (NOT a git repo, so staleness is the generator's
# documented mtime fallback and a decoy is genuinely stale) holding copies of
# compute-badges.sh + generate_markdown_exports.sh + the oracle lib, a README.md
# and docs/TESTING.md, and a DECOY docs/decoy.md whose twins are older than it.
#   S1  fixture run (--readme/--testing-md outside the tree): decoy twins NOT
#       regenerated, no twins created next to the fixtures, and the output says
#       the export was skipped.                                    [RED before fix]
#   S2  in-tree run (default targets): decoy twins NOT regenerated. [RED before fix]
#   S3  in-tree run: README and docs/TESTING twins ARE regenerated after their
#       .md content changed (anti-bluff: the fix must not become a no-op).
#
# Needs pandoc (docx leg + html). Absent -> honest SKIP (§11.4.3).
# Constitution: §11.4.65, §11.4.115 RED-first, §11.4.201(6), §11.4.273.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"

PASS=0; FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }

command -v pandoc >/dev/null || { echo "SKIP: pandoc absent"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SB="$TMP/tree"; FIX="$TMP/fixtures"
mkdir -p "$SB/scripts/lib" "$SB/docs" "$FIX"
cp "${PROJECT_ROOT}/scripts/compute-badges.sh" "${PROJECT_ROOT}/scripts/generate_markdown_exports.sh" "$SB/scripts/"
cp "${PROJECT_ROOT}/scripts/lib/export_staleness.sh" "$SB/scripts/lib/"

mt() { stat -c %Y.%y "$1" 2>/dev/null; }
readme_body='# Sandbox README

<img alt="tests" src="x">
'
printf '%s' "$readme_body" > "$SB/README.md"
printf '# Sandbox TESTING\n' > "$SB/docs/TESTING.md"
printf '# Decoy\n\nnot touched by compute-badges\n' > "$SB/docs/decoy.md"
# Give every .md twins, then make the decoy genuinely newer than its twins.
(cd "$SB" && bash scripts/generate_markdown_exports.sh README.md docs/TESTING.md docs/decoy.md >/dev/null 2>&1)
for e in html docx; do [[ -f "$SB/docs/decoy.$e" ]] || { echo "FAIL: setup produced no decoy.$e"; exit 1; }; done
decoy_twins() { for e in html pdf docx; do [[ -f "$SB/docs/decoy.$e" ]] && echo "$e=$(mt "$SB/docs/decoy.$e")"; done; }
age_decoy() { for e in html pdf docx; do [[ -f "$SB/docs/decoy.$e" ]] && touch -d '2020-01-01 00:00:00' "$SB/docs/decoy.$e"; done; touch "$SB/docs/decoy.md"; }

# ---- S1: fixture run -----------------------------------------------------------
printf '%s' "$readme_body" > "$FIX/README.md"; printf '# Fixture TESTING\n' > "$FIX/TESTING.md"
age_decoy; D0="$(decoy_twins)"; sleep 1.1
(cd "$SB" && bash scripts/compute-badges.sh --readme "$FIX/README.md" --testing-md "$FIX/TESTING.md" > "$TMP/s1.log" 2>&1)
rc=$?
if [[ "$(decoy_twins)" == "$D0" ]]; then pass "S1 fixture run left the decoy's twins untouched"
else fail "S1 fixture run regenerated an unrelated in-tree decoy (whole-tree sweep)"; fi
nfix="$(find "$FIX" -name '*.html' -o -name '*.docx' -o -name '*.pdf' | wc -l)"
if (( nfix == 0 )) && (( rc == 0 )) && grep -qi 'export.*skip' "$TMP/s1.log"; then
    pass "S1 no twins written next to out-of-tree fixtures; skip announced"
else fail "S1 expected skip message + 0 fixture twins + exit 0 (got twins=$nfix rc=$rc)"; fi

# ---- S2 + S3: in-tree run -------------------------------------------------------
printf '%s' "$readme_body" > "$SB/README.md"; printf '# Sandbox TESTING v2\n' > "$SB/docs/TESTING.md"
for f in README docs/TESTING; do for e in html docx; do touch -d '2020-01-01 00:00:00' "$SB/$f.$e"; done; done
age_decoy; D0="$(decoy_twins)"; R0="$(mt "$SB/README.html")|$(mt "$SB/README.docx")|$(mt "$SB/docs/TESTING.html")|$(mt "$SB/docs/TESTING.docx")"
sleep 1.1
(cd "$SB" && bash scripts/compute-badges.sh > "$TMP/s2.log" 2>&1)
if [[ "$(decoy_twins)" == "$D0" ]]; then pass "S2 in-tree run left the decoy's twins untouched"
else fail "S2 in-tree run regenerated an unrelated decoy (whole-tree sweep)"; fi
R1="$(mt "$SB/README.html")|$(mt "$SB/README.docx")|$(mt "$SB/docs/TESTING.html")|$(mt "$SB/docs/TESTING.docx")"
bad=""
IFS='|' read -r a b c d <<<"$R0"; IFS='|' read -r A B C D <<<"$R1"
[[ "$a" != "$A" ]] || bad+=" README.html"; [[ "$b" != "$B" ]] || bad+=" README.docx"
[[ "$c" != "$C" ]] || bad+=" TESTING.html"; [[ "$d" != "$D" ]] || bad+=" TESTING.docx"
grep -q 'Test counts' "$SB/docs/TESTING.html" || bad+=" TESTING.html-lacks-new-section"
if [[ -z "$bad" ]]; then pass "S3 README + TESTING twins regenerated after their content changed"
else fail "S3 owned exports NOT regenerated:$bad"; fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
(( FAIL == 0 )) || exit 1
exit 0
