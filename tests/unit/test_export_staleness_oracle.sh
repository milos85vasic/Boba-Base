#!/usr/bin/env bash
# test_export_staleness_oracle.sh — the CM-MARKDOWN-EXPORT-SYNC (§11.4.65)
# staleness oracle must be REPRODUCIBLE and must have TEETH.
#
# Forensic anchor (measured 2026-08-20, this repo):
#   FALSE POSITIVE — git does not preserve mtimes, and on checkout ".html"
#   sorts BEFORE ".md", so every export lands with an earlier mtime. Two
#   `git checkout-index` extractions of the SAME commit reported 65 and 68
#   stale pairs; split by extension it was .html 65/141 and 68/141 vs
#   .pdf 0/141 — a deterministic alphabetical-ordering artifact, not a race.
#   FALSE NEGATIVE — once an export's mtime drifts AHEAD of its source
#   (checkout order, a touch, a plain `cp`), generate_markdown_exports.sh
#   skips regenerating it forever and the gate reports "fresh" while the
#   content rots. Measured live: docs/scripts/extract-tracker-cookies.md
#   contains IPTORRENTS 9x, its committed .html 0x, .html last committed
#   2026-06-16 vs .md 2026-08-18. Self-perpetuating.
#
# §11.4.50 (deterministic across checkouts) + §11.4.201(1) (a check that
# refuses a clean tree is as broken as one that passes a dirty tree).
#
# §11.4.43 RED-first: against the mtime-only oracle, cases 2 and 3 FAIL.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
HELPER="${PROJECT_ROOT}/scripts/lib/export_staleness.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
finish(){ echo "RESULT: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ] || exit 1; exit 0; }

[[ -f "$HELPER" ]] || { fail "helper missing: scripts/lib/export_staleness.sh"; finish; }
# shellcheck disable=SC1090
source "$HELPER"


# NOTE: export_is_stale() caches its history/dirty maps per repo root, which is
# correct in production (pre_build never commits mid-run). This fixture commits
# BETWEEN cases, so each assertion must force a cache rebuild first — otherwise
# later cases silently read the first case's map and the oracle looks broken
# when it is not. (Diagnosed 2026-08-20: the helper returned STALE correctly in
# isolation while the suite reported FRESH.)
_reset_oracle_cache() { _EXPORT_MAPS_ROOT=""; }

FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT
cd "$FIX"
git init -q .; git config user.email t@t; git config user.name t

# ---- Case 1: NEGATIVE CONTROL — fresh checkout order (.html older than .md).
# Content is in sync (same commit); ONLY the mtimes differ, exactly as a real
# `git clone` produces. A correct oracle must NOT call this stale.
mkdir -p c1 && printf 'source v1\n' > c1/a.md && printf '<p>source v1</p>\n' > c1/a.html
git add -A >/dev/null && git commit -qm "c1 in sync"
touch -d '2020-01-01 00:00:01' c1/a.html
touch -d '2020-01-01 00:00:02' c1/a.md      # .html older, like a checkout
_reset_oracle_cache
if export_is_stale "$FIX/c1/a.md" "$FIX/c1/a.html" "$FIX"; then
    fail "NEGATIVE CONTROL: in-sync pair reported STALE purely from checkout mtime order (§11.4.201(1) false positive)"
else
    pass "in-sync pair with checkout-order mtimes is NOT reported stale"
fi

# ---- Case 2: TEETH — source genuinely changed AFTER the export was written,
# and the export's mtime was bumped ahead (the self-perpetuating trap).
mkdir -p c2 && printf 'source v1\n' > c2/b.md && printf '<p>source v1</p>\n' > c2/b.html
git add -A >/dev/null && git commit -qm "c2 in sync"
printf 'source v2 IPTORRENTS\n' > c2/b.md
git add -A >/dev/null && git commit -qm "c2 source updated, export NOT regenerated"
touch -d '2030-01-01 00:00:00' c2/b.html     # export mtime AHEAD of source
_reset_oracle_cache
if export_is_stale "$FIX/c2/b.md" "$FIX/c2/b.html" "$FIX"; then
    pass "genuinely-stale export detected despite its mtime being newer (teeth)"
else
    fail "genuinely-stale export reported FRESH — the self-perpetuating false negative"
fi

# ---- Case 3: TEETH on the real corpus shape — export committed earlier than
# source, mtimes untouched (what a fresh clone of a real repo looks like).
mkdir -p c3 && printf 'v1\n' > c3/d.md && printf '<p>v1</p>\n' > c3/d.html
git add -A >/dev/null && git commit -qm "c3 in sync"
printf 'v2 changed\n' > c3/d.md
git add -A >/dev/null && git commit -qm "c3 source-only update"
touch -d '2031-01-01 00:00:00' c3/d.html
touch -d '2031-01-01 00:00:00' c3/d.md      # identical mtimes: mtime says nothing
_reset_oracle_cache
if export_is_stale "$FIX/c3/d.md" "$FIX/c3/d.html" "$FIX"; then
    pass "history-stale export detected when mtimes are identical"
else
    fail "history-stale export missed when mtimes are identical (oracle blind)"
fi

# ---- Case 4: missing sibling is always stale (content-independent).
mkdir -p c4 && printf 'v1\n' > c4/e.md
_reset_oracle_cache
if export_is_stale "$FIX/c4/e.md" "$FIX/c4/e.html" "$FIX"; then
    pass "missing export sibling reported stale"
else
    fail "missing export sibling NOT reported stale"
fi

# ---- Case 5: locally-edited (dirty) source with an older export MUST be
# caught — mtime is the only signal here and it is meaningful.
mkdir -p c5 && printf 'v1\n' > c5/f.md && printf '<p>v1</p>\n' > c5/f.html
git add -A >/dev/null && git commit -qm "c5 in sync"
touch -d '2020-01-01 00:00:01' c5/f.html
printf 'v2 edited locally, uncommitted\n' > c5/f.md   # now newer than export
_reset_oracle_cache
if export_is_stale "$FIX/c5/f.md" "$FIX/c5/f.html" "$FIX"; then
    pass "locally-edited source with older export reported stale"
else
    fail "locally-edited source with older export NOT reported stale"
fi

finish
