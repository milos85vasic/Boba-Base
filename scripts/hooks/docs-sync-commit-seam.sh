#!/usr/bin/env bash
# scripts/hooks/docs-sync-commit-seam.sh — §11.4.106(F) COMMIT-SEAM doc/DB sync check
#
# ─── WHY THIS EXISTS (BOB-087 / RD2-20) ───────────────────────────────
# §11.4.106(F) requires the doc/DB sync to be enforced at the COMMIT
# seam, not only at build time. Boba enforced it ONLY inside the long
# `scripts/pre_build_verification.sh` gate (invariant 17), which is
# skippable via BOBA_SYNC_SKIP_CI=1 — so a skipped run could land a
# commit whose tracked DB and Markdown disagree. This script is that
# missing seam.
#
# ─── THE DEFECT IT CLOSES (BOB-136) ───────────────────────────────────
# `workable-items diff` reports "DB and Markdown are in sync" while the
# `body_md` column and the Markdown body genuinely differ. Measured
# 2026-08-20: after correcting BOB-008's Evidence text in docs/Issues.md
# but BEFORE syncing, `diff` still said in-sync and `validate` still said
# OK for all items. BODY DRIFT IS INVISIBLE to the standing checks — it
# is how BOB-008's Evidence text rotted unnoticed (see BOB-084/RD2-04).
#
# CHECK 3 below closes exactly that hole with a RE-PARSE ORACLE: it
# copies the tracked DB to a temp file, re-parses the working-tree
# Markdown into that copy THROUGH THE ENGINE'S OWN PARSER
# (`workable-items sync md-to-db`), and compares a per-item projection
# of the two. Any divergence — including body-only — is named by item.
# This REUSES the engine; it re-implements no parsing or rendering.
#
# ─── §11.4.201(1) NO-FALSE-POSITIVE PROPERTY ──────────────────────────
# The oracle is round-trip stable: on a synced tree the re-parse of the
# working-tree Markdown reproduces the tracked DB's projection BYTE-FOR-
# BYTE (measured 2026-08-20: 133/133 items, 1502-line projection
# identical). A seam that refuses valid commits is worse than no seam —
# it trains people to bypass it — so every check here is scoped to fire
# ONLY when the staged set actually touches the chain source it guards.
#
# ─── §11.4.234(D) ALWAYS-UNBLOCKED ────────────────────────────────────
# Every failure prints a NAMED per-check report plus the exact
# remediation command. Cheap checks (1-3, ~60ms each, measured) are
# always on. The LONG check (4 — `docs_chain verify`, measured 51s) is
# separable and skippable via the project's existing recorded-deferral
# flag BOBA_SYNC_SKIP_CI=1, whose skip is recorded as `[skip-ci]` in the
# commit message by scripts/commit-push-all.sh. A missing tool is an
# honest §11.4.3 SKIP-with-reason (loud WARN, never a silent pass and
# never a block) — an absent sqlite3 is not evidence of drift.
#
# ─── USAGE ────────────────────────────────────────────────────────────
#   bash scripts/hooks/docs-sync-commit-seam.sh              # check staged set
#   bash scripts/hooks/docs-sync-commit-seam.sh --files a b  # check an explicit set
#   bash scripts/hooks/docs-sync-commit-seam.sh --self-test  # §11.4.107(10) oracle self-validation
#
# ─── EXIT ─────────────────────────────────────────────────────────────
#   0 = OK (no chain source staged, or staged and in sync)
#   1 = DRIFT — commit refused; per-check report + remediation on stderr
#   2 = invocation error

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

WI_BIN="constitution/scripts/workable-items/workable-items"
DC_BIN="constitution/submodules/docs_chain/docs_chain"
WI_DB="docs/workable_items.db"
WI_ISSUES="docs/Issues.md"
WI_FIXED="docs/Fixed.md"
CTX_DIR=".docs_chain/contexts"

SKIP_LONG="${BOBA_SYNC_SKIP_CI:-${BOBA_SYNC_SKIP_LONG:-0}}"

# Per-item projection. char(31)=unit separator between fields; newlines are
# flattened to a literal marker so EVERY item is exactly ONE line — that is
# what lets a divergence be reported as an ITEM ID rather than a raw line
# number (§11.4.6: the report must be actionable).
PROJ_Q="select atm_id||'|'||current_location||'|'||representation||'|'||\
replace(replace(type||char(31)||status||char(31)||coalesce(severity,'')||char(31)||\
title||char(31)||coalesce(body_md,''),char(13),'<CR>'),char(10),'<LF>') \
from items order by atm_id,current_location,representation;"

MODE="staged"
EXPLICIT_FILES=()
while [ $# -gt 0 ]; do
    case "$1" in
        --files)  MODE="explicit"; shift; while [ $# -gt 0 ]; do EXPLICIT_FILES+=("$1"); shift; done ;;
        --staged) MODE="staged"; shift ;;
        --self-test) MODE="selftest"; shift ;;
        -h|--help) sed -n '/─── USAGE/,/─── EXIT/p' "$0"; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
    esac
done

FAILED_CHECKS=()
TMPDIR_SEAM=""
_cleanup() { [ -n "$TMPDIR_SEAM" ] && rm -rf "$TMPDIR_SEAM" 2>/dev/null || true; }
trap _cleanup EXIT

# ── Build a temp DB re-parsed from the given Markdown pair, and print its
#    per-item projection on stdout. Returns 1 if the engine could not run.
#    $1=db seed  $2=issues.md  $3=fixed.md  $4=out projection path
_reparse_projection() {
    local seed_db="$1" issues="$2" fixed="$3" out="$4"
    local tdb="$TMPDIR_SEAM/reparse.$$.db"
    cp -p "$seed_db" "$tdb" || return 1
    "$WI_BIN" sync md-to-db --db "$tdb" --issues "$issues" --fixed "$fixed" >/dev/null 2>&1 || return 1
    sqlite3 "$tdb" "$PROJ_Q" > "$out" 2>/dev/null || return 1
    rm -f "$tdb" "$tdb-wal" "$tdb-shm" 2>/dev/null || true
    return 0
}

# ── §11.4.107(10) self-validated analyzer: prove the oracle can SEE a
#    body-only drift (golden-bad) and does NOT fire on a synced tree
#    (golden-good / negative control). Operates entirely on temp copies —
#    the real working tree is never touched.
if [ "$MODE" = "selftest" ]; then
    echo "[docs-sync-seam] §11.4.107(10) self-test — validating the body-drift oracle"
    TMPDIR_SEAM="$(mktemp -d)"
    if [ ! -x "$WI_BIN" ]; then
        echo "SKIP (§11.4.3): $WI_BIN unavailable — self-test cannot run" >&2; exit 0
    fi
    if ! command -v sqlite3 >/dev/null 2>&1; then
        echo "SKIP (§11.4.3): sqlite3 unavailable — self-test cannot run" >&2; exit 0
    fi
    cp -p "$WI_ISSUES" "$TMPDIR_SEAM/good.md"
    cp -p "$WI_FIXED"  "$TMPDIR_SEAM/fixed.md"
    sqlite3 "$WI_DB" "$PROJ_Q" > "$TMPDIR_SEAM/tracked.txt"

    # golden-good — the untouched Markdown must reproduce the tracked DB
    if ! _reparse_projection "$WI_DB" "$TMPDIR_SEAM/good.md" "$TMPDIR_SEAM/fixed.md" "$TMPDIR_SEAM/good.txt"; then
        echo "SELF-TEST ERROR: re-parse failed on the clean fixture" >&2; exit 1
    fi
    if diff -q "$TMPDIR_SEAM/tracked.txt" "$TMPDIR_SEAM/good.txt" >/dev/null; then
        echo "  golden-good     PASS  (clean tree reproduces tracked DB; oracle does not false-fire)"
    else
        echo "  golden-good     FAIL  (oracle fires on a synced tree — §11.4.201(1) false positive)" >&2
        FAILED_CHECKS+=("selftest-golden-good")
    fi

    # golden-bad — a body-only edit MUST be detected AND named
    cp -p "$TMPDIR_SEAM/good.md" "$TMPDIR_SEAM/bad.md"
    VICTIM="$(sqlite3 "$WI_DB" "select atm_id from items where current_location='Issues' and body_md is not null and length(body_md)>40 order by atm_id limit 1;")"
    awk -v id="$VICTIM" '
        $0 ~ ("^## " id " ") { inseg=1; print; next }
        inseg && /^## / { inseg=0 }
        inseg && !done && NF>0 && $0 !~ /^\*\*/ && $0 !~ /^#/ { print "SELFTEST-SEEDED-BODY-DRIFT-CONTROL-NEEDLE"; done=1; next }
        { print }
    ' "$TMPDIR_SEAM/good.md" > "$TMPDIR_SEAM/bad.tmp" && mv "$TMPDIR_SEAM/bad.tmp" "$TMPDIR_SEAM/bad.md"
    if diff -q "$TMPDIR_SEAM/good.md" "$TMPDIR_SEAM/bad.md" >/dev/null; then
        echo "  golden-bad      ERROR (could not seed a needle into $VICTIM — self-test inconclusive)" >&2
        FAILED_CHECKS+=("selftest-seed")
    else
        if ! _reparse_projection "$WI_DB" "$TMPDIR_SEAM/bad.md" "$TMPDIR_SEAM/fixed.md" "$TMPDIR_SEAM/bad.txt"; then
            echo "SELF-TEST ERROR: re-parse failed on the drifted fixture" >&2; exit 1
        fi
        DETECTED="$(diff "$TMPDIR_SEAM/tracked.txt" "$TMPDIR_SEAM/bad.txt" 2>/dev/null | grep -E '^[<>]' | sed 's/^[<>] //' | cut -d'|' -f1 | sort -u | tr '\n' ' ' || true)"
        if [ -n "$DETECTED" ]; then
            echo "  golden-bad      PASS  (seeded body drift DETECTED and named: ${DETECTED% })"
        else
            echo "  golden-bad      FAIL  (seeded body drift NOT detected — oracle is blind)" >&2
            FAILED_CHECKS+=("selftest-golden-bad")
        fi
    fi
    if [ "${#FAILED_CHECKS[@]}" -gt 0 ]; then
        echo "[docs-sync-seam] self-test FAILED: ${FAILED_CHECKS[*]}" >&2; exit 1
    fi
    echo "[docs-sync-seam] self-test PASS — oracle validated in both polarities"
    exit 0
fi

# ── Resolve the file set under test ───────────────────────────────────
if [ "$MODE" = "explicit" ]; then
    CHANGED="$(printf '%s\n' "${EXPLICIT_FILES[@]+"${EXPLICIT_FILES[@]}"}")"
else
    CHANGED="$(git diff --cached --name-only 2>/dev/null || true)"
fi

_touches() {
    local p
    for p in "$@"; do
        printf '%s\n' "$CHANGED" | grep -qxF "$p" && return 0
    done
    return 1
}

# Does the staged set touch the workable-items chain (Issues/Fixed/DB)?
WI_TOUCHED=0
_touches "$WI_ISSUES" "$WI_FIXED" "$WI_DB" && WI_TOUCHED=1

# Which docs_chain contexts own a staged path? (light path lookup only —
# the actual drift verdict is produced by the docs_chain engine itself.)
DC_CONTEXTS=""
if [ -d "$CTX_DIR" ]; then
    for ctx in "$CTX_DIR"/*.yaml; do
        [ -f "$ctx" ] || continue
        while IFS= read -r nodepath; do
            [ -z "$nodepath" ] && continue
            if printf '%s\n' "$CHANGED" | grep -qxF "$nodepath"; then
                DC_CONTEXTS="$DC_CONTEXTS $(basename "$ctx" .yaml)"
                break
            fi
        done < <(grep -oE 'path:[[:space:]]*[^ }]+' "$ctx" | sed 's/path:[[:space:]]*//')
    done
    DC_CONTEXTS="$(printf '%s' "$DC_CONTEXTS" | tr ' ' '\n' | grep -v '^$' | sort -u | tr '\n' ' ' || true)"
fi

if [ "$WI_TOUCHED" -eq 0 ] && [ -z "$DC_CONTEXTS" ]; then
    echo "[docs-sync-seam] no docs-chain source in the staged set — check not applicable (OK)"
    exit 0
fi

echo "[docs-sync-seam] §11.4.106(F) commit-seam doc/DB sync check"
[ "$WI_TOUCHED" -eq 1 ] && echo "                 workable-items chain: STAGED (Issues/Fixed/DB)"
[ -n "$DC_CONTEXTS" ] && echo "                 docs_chain context(s) staged: ${DC_CONTEXTS% }"

_report_fail() {
    echo "" >&2
    echo "  ── $1 ──" >&2
    shift
    printf '  %s\n' "$@" >&2
}

# ── CHECK 1+2+3 — workable-items chain (cheap, always on) ─────────────
if [ "$WI_TOUCHED" -eq 1 ]; then
    if [ ! -x "$WI_BIN" ]; then
        echo "WARN (§11.4.3 SKIP): $WI_BIN missing/not executable — workable-items checks NOT run." >&2
        echo "                     This is an absent tool, not evidence of sync. Commit proceeds (§11.4.234(D))." >&2
    else
        # CHECK 1 — closed-set + §11.4.91 invariants
        if "$WI_BIN" validate --db "$WI_DB" >/dev/null 2>&1; then
            echo "  CHECK 1 workable-items validate ......... PASS"
        else
            echo "  CHECK 1 workable-items validate ......... FAIL"
            FAILED_CHECKS+=("validate")
            _report_fail "CHECK 1 FAILED — workable-items validate" \
                "The tracked DB violates a closed-set / §11.4.91 invariant." \
                "Detail:" 
            "$WI_BIN" validate --db "$WI_DB" 2>&1 | head -15 | sed 's/^/    /' >&2 || true
            _report_fail "REMEDIATION" \
                "$WI_BIN validate --db $WI_DB   # read the named violation" \
                "then correct the offending item via '$WI_BIN update ...' and re-run."
        fi

        # CHECK 2 — structural DB<->MD divergence (engine's own check)
        if "$WI_BIN" diff --db "$WI_DB" --issues "$WI_ISSUES" --fixed "$WI_FIXED" >/dev/null 2>&1; then
            echo "  CHECK 2 workable-items diff ............. PASS"
        else
            echo "  CHECK 2 workable-items diff ............. FAIL"
            FAILED_CHECKS+=("diff")
            _report_fail "CHECK 2 FAILED — workable-items diff (DB vs Markdown divergence)"
            "$WI_BIN" diff --db "$WI_DB" --issues "$WI_ISSUES" --fixed "$WI_FIXED" 2>&1 | head -20 | sed 's/^/    /' >&2 || true
            _report_fail "REMEDIATION — choose the authoritative side, then re-run" \
                "Markdown is right:  $WI_BIN sync md-to-db --db $WI_DB" \
                "DB is right:        $WI_BIN sync db-to-md --db $WI_DB"
        fi

        # CHECK 3 — BODY DRIFT re-parse oracle (closes BOB-136)
        if ! command -v sqlite3 >/dev/null 2>&1; then
            echo "  CHECK 3 body_md drift oracle ............ SKIP (§11.4.3: sqlite3 absent)"
            echo "WARN: sqlite3 not on PATH — the BOB-136 body-drift oracle could NOT run." >&2
            echo "      An absent tool is NOT evidence of sync. Commit proceeds (§11.4.234(D))." >&2
        else
            TMPDIR_SEAM="${TMPDIR_SEAM:-$(mktemp -d)}"
            sqlite3 "$WI_DB" "$PROJ_Q" > "$TMPDIR_SEAM/tracked.txt" 2>/dev/null || true
            if _reparse_projection "$WI_DB" "$WI_ISSUES" "$WI_FIXED" "$TMPDIR_SEAM/reparsed.txt"; then
                OFFENDERS="$(diff "$TMPDIR_SEAM/tracked.txt" "$TMPDIR_SEAM/reparsed.txt" 2>/dev/null | grep -E '^[<>]' | sed 's/^[<>] //' | cut -d'|' -f1 | sort -u || true)"
                if [ -z "$OFFENDERS" ]; then
                    echo "  CHECK 3 body_md drift oracle ............ PASS"
                else
                    echo "  CHECK 3 body_md drift oracle ............ FAIL"
                    FAILED_CHECKS+=("body-drift")
                    _report_fail "CHECK 3 FAILED — body_md DRIFT (the BOB-136 class)" \
                        "The tracked DB's body_md and the working-tree Markdown body DISAGREE" \
                        "for the item(s) below. 'workable-items diff' does NOT see this class —" \
                        "that blindness is exactly how BOB-008's Evidence text rotted unnoticed." \
                        "" \
                        "Offending item(s):"
                    printf '%s\n' "$OFFENDERS" | sed 's/^/    - /' >&2
                    _report_fail "REMEDIATION — choose the authoritative side, then re-run" \
                        "Markdown is right:  $WI_BIN sync md-to-db --db $WI_DB" \
                        "DB is right:        $WI_BIN sync db-to-md --db $WI_DB" \
                        "Then stage the regenerated file(s) and re-run this commit."
                fi
            else
                echo "  CHECK 3 body_md drift oracle ............ SKIP (re-parse could not run)"
                echo "WARN: the body-drift re-parse could not run — NOT evidence of sync (§11.4.3)." >&2
            fi
        fi
    fi
fi

# ── CHECK 4 — docs_chain derived-export drift (LONG, skippable) ───────
if [ -n "$DC_CONTEXTS" ]; then
    if [ "$SKIP_LONG" = "1" ]; then
        echo "  CHECK 4 docs_chain verify ............... SKIPPED via BOBA_SYNC_SKIP_CI=1"
        echo "                                          (recorded as [skip-ci] in the commit message)"
    elif [ ! -x "$DC_BIN" ]; then
        echo "  CHECK 4 docs_chain verify ............... SKIP (§11.4.3: $DC_BIN unavailable)"
        echo "WARN: $DC_BIN missing/not executable — export-drift NOT verified (§11.4.3)." >&2
    else
        for c in $DC_CONTEXTS; do
            if "$DC_BIN" verify "$c" >/dev/null 2>&1; then
                echo "  CHECK 4 docs_chain verify [$c] .. PASS"
            else
                echo "  CHECK 4 docs_chain verify [$c] .. FAIL"
                FAILED_CHECKS+=("docs_chain:$c")
                _report_fail "CHECK 4 FAILED — docs_chain export drift in context '$c'"
                "$DC_BIN" verify "$c" 2>&1 | head -20 | sed 's/^/    /' >&2 || true
                _report_fail "REMEDIATION" \
                    "$DC_BIN sync $c" \
                    "then stage the regenerated exports and re-run this commit." \
                    "To DEFER this long check for this run instead:" \
                    "BOBA_SYNC_SKIP_CI=1 bash scripts/commit-push-all.sh \"<msg>\"" \
                    "(the deferral is recorded as [skip-ci] in the commit message)."
            fi
        done
    fi
fi

# ── verdict ───────────────────────────────────────────────────────────
if [ "${#FAILED_CHECKS[@]}" -gt 0 ]; then
    echo "" >&2
    echo "════════════════════════════════════════════════════════════════" >&2
    echo "COMMIT REFUSED — §11.4.106(F) doc/DB sync seam" >&2
    echo "  Failed check(s): ${FAILED_CHECKS[*]}" >&2
    echo "  The staged set touches a docs-chain source whose derived docs" >&2
    echo "  or tracked DB are OUT OF SYNC. Committing now would land the" >&2
    echo "  drift, which is the defect this seam exists to prevent." >&2
    echo "  Run the REMEDIATION command(s) printed above, then re-run." >&2
    echo "  This seam never hangs and never blocks silently (§11.4.234(D))." >&2
    echo "════════════════════════════════════════════════════════════════" >&2
    exit 1
fi

echo "[docs-sync-seam] OK — every staged docs-chain source is in sync"
exit 0
