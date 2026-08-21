#!/usr/bin/env bash
# check_cm_plugin_count.sh — CM-PLUGIN-COUNT static pre-build gate (BOB-149).
#
# Purpose:
#   Refuse any plugin-roster count stated in the governed documentation that
#   disagrees with the count DERIVED from the authoritative source. BOB-149:
#   the managed-plugin count had drifted three ways — 43 in the constitution,
#   42 in CLAUDE.md, 48 in the README badge — and nothing in the repository
#   equalled 48 at all.
#
# WHY THIS GATE EXISTS (the count is load-bearing, not merely present):
#   A number is not worth a gate just because it is written down. This one is
#   load-bearing in three places:
#     - constitution Principle II enumerates the roster BY NAME and asserts
#       its size, so a drifted count contradicts governance;
#     - constitution §11.4.86 requires derived docs to re-sync whenever
#       `install-plugin.sh`'s `PLUGINS=()` array changes — a rule with no
#       mechanical enforcement is exactly the §11.4.227 prose-not-seam gap;
#     - the release checklist step 3 ("every managed plugin (43 entries per
#       Principle II) MUST be installed") gates a RELEASE on the number.
#   CLAUDE.md is additionally the file agents read as project instruction, so
#   a wrong number there is the one most likely to propagate into new work.
#
# WHY THE COUNTS ARE PLURAL (the actual root cause of BOB-149):
#   "Managed plugins" was ambiguous, and the ambiguity WAS the bug. Five
#   different, individually-correct numbers were being compared as if they
#   answered one question. This gate therefore derives and checks each
#   separately, and the documentation must name which question it answers:
#     curated   — entries in `install-plugin.sh`'s PLUGINS=() array. THE
#                 canonical managed roster (constitution Principle II).
#     bootstrap — entries in `setup.sh`'s OWN, separate PLUGINS=() array: the
#                 retired "canonical 12" one-time-setup subset. A genuinely
#                 different roster, not a stale copy of the curated one.
#     engines   — distinct engine modules on disk across plugins/,
#                 plugins/community/ and plugins/webui_compatible/.
#     toplevel  — *.py files directly in plugins/ (engines PLUS utility
#                 modules — never a plugin count).
#     recursive — *.py files under plugins/ at any depth (additionally
#                 double-counts engines that have a community/ or
#                 webui_compatible/ variant — never a plugin count).
#
# HOW A COUNT IS CLAIMED IN THE DOCS:
#   A governed line carries an invisible marker naming the metric, and the
#   gate reads the bolded integer from that SAME line:
#
#     - **43 search-plugin engines** are managed by ... <!-- CM-PLUGIN-COUNT: curated -->
#
#   Exactly ONE marker per line. A second marker on the same line is a FAIL,
#   not a silent skip: this parser pairs one marker with one bolded number
#   per line, so a second would go unchecked — a false-null in the gate
#   itself (§11.4.201(6)).
#
#   Marker-based extraction is deliberate: it cannot carrier-match a number
#   in prose about something else (§11.4.201(7)(a)) — "the canonical 12" and
#   "added download_torrent() to 5 plugins" are correctly ignored — and it
#   survives rewording of the sentence around it.
#
#   The legacy unmarked wording `**<N> managed plugins**` is ALSO recognised
#   and checked against `curated`. Without that, the exact pre-fix CLAUDE.md
#   text this defect was filed against would have passed silently — a
#   §11.4.201(6) false-null in the gate itself.
#
#   The `curated` marker is MANDATORY in CLAUDE.md. Deleting the number must
#   not be a route to green (§11.4.227 metric-gaming channel).
#
# EMBEDDED CONTROL NEEDLE (§11.4.201(7)(b)):
#   Before ANY array count is trusted, the extractor is proven able to SEE:
#   a synthetic entry is appended to an in-memory copy of the array block and
#   the count must increase by exactly one. A count from an unproven
#   extractor is not evidence — the original BOB-149 investigation hit
#   precisely this, where an unquoted pattern returned a confident 0.
#
# SCOPE HONESTY (§11.4.6 — stated, never silent):
#   The README plugins badge (`plugins-48`) is REPORTED as a non-blocking
#   WARN, not a FAIL. It is genuinely wrong, but README.md and
#   scripts/compute-badges.sh are outside this gate's remediation scope, and
#   per §11.4.234 a pre-build gate must never become the reason a build
#   cannot proceed over a file its owner cannot fix. Deriving that badge is
#   BOB-149 acceptance criterion 2 and belongs to compute-badges.sh.
#
# Usage:
#   check_cm_plugin_count.sh                # default: this repository
#   check_cm_plugin_count.sh --root DIR     # treat DIR as the repo root
#   check_cm_plugin_count.sh -v             # verbose (show every derivation)
#   check_cm_plugin_count.sh --help
#
# Inputs:   optional --root DIR; no stdin; no env input.
# Outputs:  derivation table + verdict on stdout; findings + FAIL on stderr.
# Side-effects: none (read-only; writes only to mktemp files it removes).
# Dependencies: bash, sed, grep, find, sort, wc, mktemp.
#
# Consumer-owned scope DATA (§11.4.35):
#   plugin roots     : plugins, plugins/community, plugins/webui_compatible
#   utility modules  : see UTILITY_MODULES below
#   governed docs    : CLAUDE.md, AGENTS.md, docs/features/Status.md
#
# Verdict:
#   0 — PASS  (every documented count matches its derivation)
#   1 — FAIL  (one or more documented counts diverge, or the mandatory
#              `curated` marker is missing)
#   2 — ERROR (usage error, missing authoritative source, or the embedded
#              control needle proved the extractor blind)
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.35 §11.4.69 §11.4.86 §11.4.107(10)
#             §11.4.108 §11.4.115 §11.4.135 §11.4.201 §11.4.224 §11.4.227
#             §11.4.234 §11.4.238 §11.4.261.

set -euo pipefail

SCRIPT_NAME="check_cm_plugin_count"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Consumer-owned DATA (§11.4.35): modules that live under plugins/ but are
# NOT search engines. If a new utility module is added here without being
# listed, the `engines` derivation rises and this gate FAILs with an
# actionable message — fail-closed by design (§11.4.252), never a silent
# miscount.
UTILITY_MODULES="download_proxy env_loader helpers nova2 novaprinter socks theme_injector"

GOVERNED_DOCS="CLAUDE.md AGENTS.md docs/features/Status.md"

ROOT="$DEFAULT_ROOT"
VERBOSE=0

print_help() { sed -n '2,110p' "${BASH_SOURCE[0]}"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) print_help; exit 0 ;;
        -v|--verbose) VERBOSE=1; shift ;;
        --root)
            [[ $# -ge 2 ]] || { echo "ERROR: --root requires a directory" >&2; exit 2; }
            ROOT="$2"; shift 2 ;;
        -*) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
        *) echo "ERROR: unexpected positional argument: $1" >&2; exit 2 ;;
    esac
done

[[ -d "$ROOT" ]] || { echo "ERROR: root is not a directory: $ROOT" >&2; exit 2; }
ROOT="$(cd "$ROOT" && pwd)"

TMP_DIR="$(mktemp -d -t cm_plugin_count.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

# ---------------------------------------------------------------------------
# array_block <file> — emit the PLUGINS=( ... ) block of <file>.
# array_count <file> — count quoted entries in that block.
#
# The entry pattern requires the QUOTES. That is not incidental: the first
# BOB-149 extraction attempt omitted them and returned a confident 0 on a
# 43-entry array. The needle below is what makes that class of miss loud.
# ---------------------------------------------------------------------------
array_block() { sed -n '/^PLUGINS=(/,/^)/p' "$1"; }

count_entries() { grep -cE '^[[:space:]]*"[a-z0-9_]+"[[:space:]]*$' || true; }

array_count() {
    local file="$1" n
    n="$(array_block "$file" | count_entries)"
    echo "${n:-0}"
}

# needle_proven <file> — CONTROL NEEDLE (§11.4.201(7)(b)). Prove the
# extractor can see before its count is trusted: append one synthetic entry
# to an in-memory copy and require the count to rise by exactly one.
needle_proven() {
    local file="$1" base needled probe
    base="$(array_count "$file")"
    probe="$TMP_DIR/needle_$$_$RANDOM.sh"
    # Insert the synthetic entry immediately before the array's closing ')'.
    awk '
        /^PLUGINS=\(/ { inblk = 1 }
        inblk && /^\)/ { print "  \"zzz_synthetic_needle\""; inblk = 0 }
        { print }
    ' "$file" > "$probe"
    needled="$(array_count "$probe")"
    rm -f "$probe"
    [[ "$needled" -eq $((base + 1)) ]]
}

# ---------------------------------------------------------------------------
# Derive every metric from the authoritative sources.
# ---------------------------------------------------------------------------
INSTALL_SH="$ROOT/install-plugin.sh"
SETUP_SH="$ROOT/setup.sh"
PLUGINS_DIR="$ROOT/plugins"

for required in "$INSTALL_SH" "$PLUGINS_DIR"; do
    if [[ ! -e "$required" ]]; then
        echo "ERROR: authoritative source missing: ${required#"$ROOT"/}" >&2
        echo "       (cannot derive a roster count; refusing to guess — §11.4.6)" >&2
        exit 2
    fi
done

if ! needle_proven "$INSTALL_SH"; then
    echo "ERROR: control needle FAILED on install-plugin.sh — the PLUGINS=()" >&2
    echo "       extractor did not see an injected synthetic entry, so any" >&2
    echo "       count it returns is not evidence (§11.4.201(7)(b))." >&2
    exit 2
fi
N_CURATED="$(array_count "$INSTALL_SH")"

N_BOOTSTRAP="n/a"
if [[ -f "$SETUP_SH" ]] && array_block "$SETUP_SH" | grep -q 'PLUGINS=('; then
    if ! needle_proven "$SETUP_SH"; then
        echo "ERROR: control needle FAILED on setup.sh PLUGINS=() extractor" >&2
        exit 2
    fi
    N_BOOTSTRAP="$(array_count "$SETUP_SH")"
fi

# toplevel: *.py directly in plugins/
N_TOPLEVEL=0
for f in "$PLUGINS_DIR"/*.py; do [[ -f "$f" ]] && N_TOPLEVEL=$((N_TOPLEVEL + 1)); done

# recursive: *.py at any depth under plugins/, excluding bytecode caches.
# NOTE: `find` on this host is bfs, not GNU findutils. Only portable
# primaries are used here (-name/-type/-prune); relative -newermt forms are
# REJECTED by bfs while printing nothing to stdout, which would turn a hard
# failure into a clean-looking empty result (§11.4.201(6)).
FIND_ERR="$TMP_DIR/find.err"
N_RECURSIVE="$(find "$PLUGINS_DIR" -name '__pycache__' -prune -o -type f -name '*.py' -print 2>"$FIND_ERR" | wc -l | tr -d ' ')"
if [[ -s "$FIND_ERR" ]]; then
    echo "ERROR: find emitted diagnostics; a count derived from it is not evidence:" >&2
    sed 's/^/       /' "$FIND_ERR" >&2
    exit 2
fi

# engines: distinct module basenames across the plugin roots, minus the
# documented utility modules.
ENGINES_LIST="$TMP_DIR/engines.txt"
: > "$ENGINES_LIST"
for sub in "" "/community" "/webui_compatible"; do
    d="$PLUGINS_DIR$sub"
    [[ -d "$d" ]] || continue
    for f in "$d"/*.py; do
        [[ -f "$f" ]] || continue
        b="$(basename "$f" .py)"
        skip=0
        for u in $UTILITY_MODULES; do [[ "$b" == "$u" ]] && skip=1 && break; done
        [[ $skip -eq 0 ]] && echo "$b" >> "$ENGINES_LIST"
    done
done
sort -u -o "$ENGINES_LIST" "$ENGINES_LIST"
N_ENGINES="$(wc -l < "$ENGINES_LIST" | tr -d ' ')"

declare -A DERIVED=(
    [curated]="$N_CURATED"
    [bootstrap]="$N_BOOTSTRAP"
    [engines]="$N_ENGINES"
    [toplevel]="$N_TOPLEVEL"
    [recursive]="$N_RECURSIVE"
)

echo "$SCRIPT_NAME — CM-PLUGIN-COUNT static pre-build gate (BOB-149)"
echo "  root: $ROOT"
echo "  derived (control-needle proven):"
printf '    %-10s %s   (%s)\n' \
    "curated"   "$N_CURATED"   "install-plugin.sh PLUGINS=() — the canonical managed roster" \
    "bootstrap" "$N_BOOTSTRAP" "setup.sh PLUGINS=() — one-time-setup subset" \
    "engines"   "$N_ENGINES"   "distinct engine modules on disk" \
    "toplevel"  "$N_TOPLEVEL"  "plugins/*.py — engines PLUS utility modules" \
    "recursive" "$N_RECURSIVE" "plugins/**/*.py — also counts per-dir variants"
echo

FINDINGS="$TMP_DIR/findings.txt"
: > "$FINDINGS"
checked=0
curated_marker_seen=0

for doc in $GOVERNED_DOCS; do
    path="$ROOT/$doc"
    [[ -f "$path" ]] || continue

    # --- marker-based claims -------------------------------------------------
    while IFS= read -r line; do
        # Occurrence count, NOT `grep -c`. MEASURED on this host (ugrep 7.8.4,
        # 2026-08-21): `grep -coE` on this exact input returns 3 at top level
        # but 1 inside a `set -euo pipefail` subshell — a context-dependent
        # reading, the §11.4.201(12) shell-instrument footgun class. The
        # `-oE | wc -l` form returned 3 in BOTH contexts.
        nmark="$(printf '%s' "$line" | grep -oE '<!--[[:space:]]*CM-PLUGIN-COUNT:' | wc -l | tr -d ' ' || true)"
        if [[ "$nmark" -gt 1 ]]; then
            echo "$doc: $nmark CM-PLUGIN-COUNT markers on one line — put each on its own line; this parser checks one per line and would leave the rest silently unchecked" >> "$FINDINGS"
            continue
        fi
        metric="$(printf '%s' "$line" | sed -n 's/.*<!--[[:space:]]*CM-PLUGIN-COUNT:[[:space:]]*\([a-z]*\)[[:space:]]*-->.*/\1/p')"
        [[ -n "$metric" ]] || continue
        if [[ -z "${DERIVED[$metric]+set}" ]]; then
            echo "$doc: unknown metric '$metric' in CM-PLUGIN-COUNT marker (valid: ${!DERIVED[*]})" >> "$FINDINGS"
            continue
        fi
        stated="$(printf '%s' "$line" | grep -oE '\*\*[0-9]+' | head -n1 | tr -d '*' || true)"
        if [[ -z "$stated" ]]; then
            echo "$doc: CM-PLUGIN-COUNT marker for '$metric' has no bolded **<number>** on its line" >> "$FINDINGS"
            continue
        fi
        [[ "$metric" == "curated" ]] && curated_marker_seen=1
        checked=$((checked + 1))
        if [[ "$stated" != "${DERIVED[$metric]}" ]]; then
            echo "$doc: '$metric' documented as $stated but derives to ${DERIVED[$metric]}" >> "$FINDINGS"
        elif [[ $VERBOSE -eq 1 ]]; then
            echo "    ok  $doc: $metric = $stated"
        fi
    done < "$path"

    # --- legacy unmarked wording (the pre-fix BOB-149 shape) -----------------
    while IFS= read -r line; do
        stated="$(printf '%s' "$line" | sed -n 's/.*\*\*\([0-9][0-9]*\)[[:space:]]\+managed plugins\*\*.*/\1/p')"
        [[ -n "$stated" ]] || continue
        checked=$((checked + 1))
        if [[ "$stated" != "$N_CURATED" ]]; then
            echo "$doc: legacy '**$stated managed plugins**' disagrees with the array ($N_CURATED)" >> "$FINDINGS"
        else
            echo "$doc: legacy '**$stated managed plugins**' wording is deprecated — use the CM-PLUGIN-COUNT marker form so the claim names WHICH roster it counts" >> "$FINDINGS"
        fi
    done < "$path"
done

# Mandatory marker (§11.4.227 — deleting the number is not a route to green).
if [[ -f "$ROOT/CLAUDE.md" && $curated_marker_seen -eq 0 ]]; then
    echo "CLAUDE.md: mandatory '<!-- CM-PLUGIN-COUNT: curated -->' marker is absent — the managed-roster count must be stated and guarded, not omitted" >> "$FINDINGS"
fi

# --- non-blocking: README plugins badge (out of this gate's fix scope) -------
README="$ROOT/README.md"
if [[ -f "$README" ]]; then
    badge="$(sed -n 's/.*img\.shields\.io\/badge\/plugins-\([0-9][0-9]*\)-.*/\1/p' "$README" | head -n1)"
    if [[ -n "$badge" && "$badge" != "$N_CURATED" ]]; then
        echo "  WARN (non-blocking): README plugins badge reads $badge, curated roster is $N_CURATED."
        echo "       The badge is hand-maintained — scripts/compute-badges.sh does not derive it."
        echo "       Deriving it is BOB-149 acceptance criterion 2 and belongs to compute-badges.sh;"
        echo "       this gate does not FAIL on it (§11.4.234 — a pre-build gate must not block a"
        echo "       build over a file outside its remediation scope)."
        echo
    fi
fi

if [[ -s "$FINDINGS" ]]; then
    echo "=== FINDINGS ===" >&2
    sed 's/^/  /' "$FINDINGS" >&2
    echo >&2
    n="$(wc -l < "$FINDINGS" | tr -d ' ')"
    echo "FAIL: $n plugin-count divergence(s) (CM-PLUGIN-COUNT, BOB-149)" >&2
    exit 1
fi

echo "PASS: CM-PLUGIN-COUNT — $checked documented count(s) match their derivation"
exit 0
