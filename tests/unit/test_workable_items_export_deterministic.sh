#!/usr/bin/env bash
# test_workable_items_export_deterministic.sh — byte-stable tracker twins from
# scripts/workable-items-export.sh (BOB-249, item 6).
#
# THE DEFECT (measured 2026-09-26): Step 1 of the wrapper runs the Go
# `workable-items export`, which shells out to pandoc/weasyprint UNCONDITIONALLY
# for Issues / Fixed / Issues_Summary / Fixed_Summary. pandoc stamps the
# wall-clock time into every .docx (docProps/core.xml), so each run rewrote four
# byte-different .docx files with zero content change. The Go binary lives in
# constitution/ and is not edited here; the Go runPandoc() inherits the process
# environment, so the wrapper pins SOURCE_DATE_EPOCH for that one invocation.
#
# ASSERTIONS (mktemp sandbox git repo: copies of the wrapper + generator + oracle
# lib and a COPY of the tracker DB — the real docs tree is never written):
#   D1  two consecutive runs produce byte-identical .md/.html/.docx/.pdf for all
#       four tracker documents.                                  [RED before fix]
#   D2  the .docx creation date is the DB's last-commit time — a meaningful,
#       history-derived date, not a frozen magic number.         [RED before fix]
#   D3  control needle: the produced .md files are non-empty and contain the
#       tracker heading, so D1's equality is not the equality of two empty runs.
#
# Needs: git, pandoc, the workable-items binary. Absent -> honest SKIP (§11.4.3).
# Constitution: §11.4.65, §11.4.115 RED-first, §11.4.246 reproducible builds,
# §11.4.273 needled measurement.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
WRAP="${PROJECT_ROOT}/scripts/workable-items-export.sh"
DB="${PROJECT_ROOT}/docs/workable_items.db"

PASS=0; FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }

BIN="${WORKABLE_ITEMS_BIN:-}"
for cand in "$BIN" "${PROJECT_ROOT}/constitution/scripts/workable-items/bin/workable-items" \
            "${PROJECT_ROOT}/constitution/scripts/workable-items/workable-items"; do
    [[ -n "$cand" && -x "$cand" ]] && { BIN="$cand"; break; }
done
command -v git >/dev/null || { echo "SKIP: git absent"; exit 0; }
command -v pandoc >/dev/null || { echo "SKIP: pandoc absent"; exit 0; }
[[ -n "$BIN" && -x "$BIN" ]] || { echo "SKIP: workable-items binary not found"; exit 0; }
[[ -f "$WRAP" && -f "$DB" ]] || { echo "FAIL: wrapper or tracker DB missing"; exit 1; }

SB="$(mktemp -d)"
trap 'rm -rf "$SB"' EXIT
mkdir -p "$SB/scripts/lib" "$SB/docs"
cp "$WRAP" "$SB/scripts/"
cp "${PROJECT_ROOT}/scripts/generate_markdown_exports.sh" "$SB/scripts/"
cp "${PROJECT_ROOT}/scripts/lib/export_staleness.sh" "$SB/scripts/lib/"
cp "$DB" "$SB/docs/workable_items.db"
G() { git -C "$SB" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }
G init -q && G add -A && G commit -q -m sandbox
DB_CT="$(G log -1 --format=%ct -- docs/workable_items.db)"

DOCS=(Issues Fixed Issues_Summary Fixed_Summary)
snapshot() {
    local d e
    for d in "${DOCS[@]}"; do for e in md html docx pdf; do
        [[ -f "$SB/docs/$d.$e" ]] && printf '%s %s\n' "$(sha256sum "$SB/docs/$d.$e" | cut -d' ' -f1)" "$d.$e"
    done; done
}
run_wrap() { env -u SOURCE_DATE_EPOCH WORKABLE_ITEMS_BIN="$BIN" GOMAXPROCS=2 nice -n 19 bash "$SB/scripts/workable-items-export.sh" > "$SB/run.log" 2>&1; }

run_wrap || { tail -20 "$SB/run.log"; echo "FAIL: wrapper run 1 exited non-zero"; exit 1; }
S1="$(snapshot)"
sleep 1.1
run_wrap || { tail -20 "$SB/run.log"; echo "FAIL: wrapper run 2 exited non-zero"; exit 1; }
S2="$(snapshot)"

# D3 control needle first: a D1 PASS over nothing would be a bluff.
nd=0; for d in "${DOCS[@]}"; do [[ -s "$SB/docs/$d.md" ]] && nd=$((nd+1)); done
ndocx="$(grep -c '\.docx$' <<<"$S1" || true)"
if (( nd == 4 )) && grep -q '^#' "$SB/docs/Issues.md" && (( ndocx == 4 )); then
    pass "D3 control: 4 non-empty tracker .md and 4 .docx produced"
else
    fail "D3 control: expected 4 .md + 4 .docx, got md=$nd docx=$ndocx"
fi

if [[ -n "$S1" && "$S1" == "$S2" ]]; then
    pass "D1 two runs byte-identical ($(wc -l <<<"$S1") files)"
else
    fail "D1 runs differ:"; diff <(echo "$S1") <(echo "$S2") | grep '^[<>]' | sed 's/^/    /'
fi

want="$(date -u -d "@${DB_CT}" +%Y-%m-%dT%H:%M:%SZ)"
got="$(unzip -p "$SB/docs/Issues.docx" docProps/core.xml 2>/dev/null | grep -o '<dcterms:created[^>]*>[^<]*' | sed 's/.*>//')"
if [[ "$got" == "$want" ]]; then pass "D2 docx created date = DB last-commit time ($want)"
else fail "D2 docx created date '$got' != DB last-commit time '$want'"; fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
(( FAIL == 0 )) || exit 1
exit 0
