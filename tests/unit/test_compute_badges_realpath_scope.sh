#!/usr/bin/env bash
# test_compute_badges_realpath_scope.sh — scripts/compute-badges.sh must classify
# --readme/--testing-md targets as in-repo or fixture by the FULLY RESOLVED real
# path of the FILE (BOB-249 follow-up, M7).
#
# THE DEFECT: only the file's dirname was resolved (`pwd -P`), so a README that is
# a SYMLINK inside the repo pointing at a file OUTSIDE it was still classified
# in-repo and its exports were regenerated (twins written next to the outside
# target's path). Shapes: symlink file (out / in), symlinked dir, `..`, relative,
# spaces in path, ROOT_DIR reached through a symlink, dangling symlink.
# Controls: genuinely in-repo targets must STILL get their exports regenerated.
# Observable: the script's own announcement plus twins actually written/not.
# Needs pandoc; absent -> honest SKIP (§11.4.3). Constitution: §11.4.65, §11.4.115, §11.4.273.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
PASS=0; FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }
command -v pandoc >/dev/null || { echo "SKIP: pandoc absent"; exit 0; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
# Base sandbox lives under a path WITH A SPACE so every case also covers spaces.
BASE="$TMP/base dir/tree"
mkdir -p "$BASE/scripts/lib" "$BASE/docs"
cp "${PROJECT_ROOT}/scripts/compute-badges.sh" "${PROJECT_ROOT}/scripts/generate_markdown_exports.sh" "$BASE/scripts/"
cp "${PROJECT_ROOT}/scripts/lib/export_staleness.sh" "$BASE/scripts/lib/"
printf '# Sandbox README\n\n<img alt="tests" src="x">\n' > "$BASE/README.md"
printf '# Sandbox TESTING\n' > "$BASE/docs/TESTING.md"
printf '# Real doc\n' > "$BASE/docs/real_readme.md"
n=0
new_sb() { n=$((n+1)); SB="$TMP/case $n/tree"; mkdir -p "$(dirname "$SB")"; cp -a "$BASE" "$SB"; OUT="$TMP/out $n"; mkdir -p "$OUT"; }
twins_in() { find "$1" \( -name '*.html' -o -name '*.docx' -o -name '*.pdf' \) 2>/dev/null | wc -l; }

# expect_skip <label> <run-dir> <script> <args...>: run, want the skip line, 0 twins under OUT and SB
run() { local dir="$1" script="$2"; shift 2; (cd "$dir" && bash "$script" "$@" >"$TMP/log" 2>&1); echo $?; }
expect_skip() {
    local label="$1" rc="$2"
    if (( rc == 0 )) && grep -q 'export skipped' "$TMP/log" && ! grep -q 'regenerating exports' "$TMP/log" \
       && (( $(twins_in "$OUT") == 0 )) && (( $(twins_in "$SB") == 0 )); then pass "$label: classified as fixture, nothing exported"
    else fail "$label: expected skip + 0 twins (rc=$rc twins_out=$(twins_in "$OUT") twins_sb=$(twins_in "$SB")); log: $(tr '\n' '|' <"$TMP/log")"; fi
}
expect_export() {
    local label="$1" rc="$2" twin="$3"
    if (( rc == 0 )) && grep -q 'regenerating exports' "$TMP/log" && [[ -f "$twin" ]]; then pass "$label: in-repo, exports regenerated ($(basename "$twin"))"
    else fail "$label: expected export + $twin (rc=$rc); log: $(tr '\n' '|' <"$TMP/log")"; fi
}

# 1 symlink FILE in repo -> target OUTSIDE (the defect)
new_sb; printf '# Outside\n' > "$OUT/target.md"; printf '# T\n' > "$OUT/t.md"
ln -s "$OUT/target.md" "$SB/linked.md"
rc=$(run "$SB" scripts/compute-badges.sh --readme "$SB/linked.md" --testing-md "$OUT/t.md"); expect_skip "M7-1 symlink file -> outside" "$rc"
# 2 symlinked DIR -> outside
new_sb; printf '# Outside\n' > "$OUT/README.md"; printf '# T\n' > "$OUT/T.md"; ln -s "$OUT" "$SB/linkdir"
rc=$(run "$SB" scripts/compute-badges.sh --readme "$SB/linkdir/README.md" --testing-md "$SB/linkdir/T.md"); expect_skip "M7-2 symlinked dir -> outside" "$rc"
# 3 `..` escaping the repo
new_sb; printf '# Outside\n' > "$OUT/README.md"; printf '# T\n' > "$OUT/T.md"
rc=$(run "$SB" scripts/compute-badges.sh --readme "$SB/docs/../../../out $n/README.md" --testing-md "$SB/docs/../../../out $n/T.md"); expect_skip "M7-3 '..' escape" "$rc"
# 4 relative path escaping the repo
new_sb; printf '# Outside\n' > "$OUT/README.md"; printf '# T\n' > "$OUT/T.md"
rc=$(run "$SB" scripts/compute-badges.sh --readme "../../out $n/README.md" --testing-md "../../out $n/T.md"); expect_skip "M7-4 relative path outside" "$rc"
# 5 dangling symlink: the script rejects a missing README (exit != 0, by design); nothing exported
new_sb; ln -s "$OUT/nope.md" "$SB/dangling.md"; printf '# T\n' > "$OUT/T.md"
rc=$(run "$SB" scripts/compute-badges.sh --readme "$SB/dangling.md" --testing-md "$OUT/T.md")
if (( rc != 0 )) && (( $(twins_in "$OUT") == 0 )) && (( $(twins_in "$SB") == 0 )); then pass "M7-5 dangling symlink rejected, nothing exported"
else fail "M7-5 dangling symlink (rc=$rc)"; fi

# Controls: genuinely in-repo
# 6 default targets, path has a space
new_sb; rc=$(run "$SB" scripts/compute-badges.sh); expect_export "C-6 default targets (spaces in path)" "$rc" "$SB/README.html"
# 7 `..` staying inside
new_sb; rc=$(run "$SB" scripts/compute-badges.sh --readme "$SB/docs/../README.md"); expect_export "C-7 '..' inside repo" "$rc" "$SB/README.html"
# 8 relative path inside
new_sb; rc=$(run "$SB" scripts/compute-badges.sh --readme "README.md" --testing-md "docs/TESTING.md"); expect_export "C-8 relative inside" "$rc" "$SB/docs/TESTING.html"
# 9 in-repo symlink -> in-repo real file: symlink is written through; twins land next to the real file
new_sb; ln -s "docs/real_readme.md" "$SB/README.md.lnk"; rm "$SB/README.md"; ln -s docs/real_readme.md "$SB/README.md"
rc=$(run "$SB" scripts/compute-badges.sh); expect_export "C-9 in-repo symlink -> in-repo" "$rc" "$SB/docs/real_readme.html"
# 10 ROOT_DIR reached through a symlink
new_sb; ln -s "$SB" "$TMP/rootlink"
rc=$(run "$TMP/rootlink" scripts/compute-badges.sh); expect_export "C-10 ROOT_DIR is a symlink" "$rc" "$SB/README.html"
# 11 symlinked ROOT and outside fixture still skipped
new_sb; ln -s "$SB" "$TMP/rootlink2"; printf '# O\n' > "$OUT/README.md"; printf '# T\n' > "$OUT/T.md"
rc=$(run "$TMP/rootlink2" scripts/compute-badges.sh --readme "$OUT/README.md" --testing-md "$OUT/T.md"); expect_skip "M7-11 symlinked ROOT + outside fixture" "$rc"

echo "RESULT: ${PASS} passed, ${FAIL} failed"
(( FAIL == 0 )) || exit 1
exit 0
