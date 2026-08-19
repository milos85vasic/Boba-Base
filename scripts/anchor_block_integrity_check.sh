#!/usr/bin/env bash
# anchor_block_integrity_check.sh — §11.4.227(B) mechanical anchor-block-integrity check.
#
# Purpose (per BOB-105 / §11.4.238 followup):
#   Enforce §11.4.227(B) "propagation-class gates count BLOCK-STARTS,
#   never bare literals" mechanically on a declared lockstep mirror set.
#
# Checks:
#   1. EXACTLY-ONCE per anchor per file.
#        - 0 block-starts of an anchor present in one file but absent in
#          another mirror = LOCKSTEP GAP (FAIL).
#        - >1 block-starts of the same anchor in one file = DUPLICATE or
#          COLLISION (FAIL).
#   2. Lockstep CONTENT-HASH equality across the mirror set.
#        - For each anchor present in every mirror, sha256 of its block
#          body MUST be identical across all mirrors. Divergence = FAIL.
#   3. ANCHOR-NUMBER COLLISION detection.
#        - Two different-titled block-starts for the same §11.4.NNN in one
#          file = COLLISION (FAIL). Detected as a case of check 1's >1.
#   4. ZERO block-starts extracted from any listed file = BLIND (FAIL)
#        (§11.4.201(6) false-null guard — an empty extractor is not clean).
#   5. Sub-anchor prefix-match protection.
#        - Full dotted ids are captured (`§11.4.10.A` ≠ `§11.4.10`);
#          `§11.4.115(F)` mid-body citations are NEVER block-starts.
#
# Anti-bluff (§11.4.201):
#   - The extractor's own null is guarded: refusing zero block-starts
#     from a listed file with a resolved diagnostic (which regex, which
#     file, sample first 3 lines).
#   - Consumer supplies the mirror-set + block-start regex as DATA
#     (§11.4.35) via a config file — never hardcoded per project.
#
# Config resolution order (first match wins):
#   1. --config <path>
#   2. $ANCHOR_INTEGRITY_CONFIG env var
#   3. <repo_root>/scripts/anchor_block_integrity_check.conf
#
# Exit codes:
#   0  — all invariants hold; report emitted to stdout.
#   1  — one or more invariant violations; findings emitted to stderr.
#   2  — configuration error (missing config, unreadable file, invalid
#        regex). Distinct from finding-level FAIL per §11.4.201(4)
#        "conservative-safe default on an unresolvable signal".
#
# Cross-refs: §11.4.6 §11.4.35 §11.4.54 §11.4.107(10) §11.4.157
#             §11.4.201 §11.4.227(B).

set -euo pipefail

SCRIPT_NAME="anchor_block_integrity_check"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ------------------------------------------------------------------------------
# Argument parsing
# ------------------------------------------------------------------------------
CONFIG_PATH=""
VERBOSE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_PATH="$2"; shift 2 ;;
    --verbose|-v) VERBOSE=1; shift ;;
    -h|--help)
      sed -n '2,60p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# ------------------------------------------------------------------------------
# Config resolution (§11.4.35 consumer DATA)
# ------------------------------------------------------------------------------
if [[ -z "$CONFIG_PATH" && -n "${ANCHOR_INTEGRITY_CONFIG:-}" ]]; then
  CONFIG_PATH="$ANCHOR_INTEGRITY_CONFIG"
fi
if [[ -z "$CONFIG_PATH" ]]; then
  CONFIG_PATH="$SCRIPT_DIR/anchor_block_integrity_check.conf"
fi

if [[ ! -r "$CONFIG_PATH" ]]; then
  echo "ERROR: config not found or unreadable: $CONFIG_PATH" >&2
  echo "  Supply --config <path>, \$ANCHOR_INTEGRITY_CONFIG, or a default" >&2
  echo "  config at scripts/anchor_block_integrity_check.conf ." >&2
  exit 2
fi

# Config file MUST set:
#   BASE_DIR                 — resolves file paths relative to this dir
#   MIRROR_SET               — array of paths (byte-identical lockstep set)
#   CANONICAL_FILE           — path, checked for exactly-once + collision,
#                              EXCLUDED from mirror-lockstep equality
#                              (§11.4.227(B) canonical-vs-mirror variance)
#   BLOCK_START_RE           — ERE matching an anchor block-start line
#   ANCHOR_ID_RE             — ERE capturing the dotted anchor id ONLY
# Optional:
#   ANCHOR_NUMBER_RANGE_RE   — ERE matching just the §-prefix (default
#                              §11\.4\.); helps future §-classes.

BASE_DIR=""
CANONICAL_FILE=""
BLOCK_START_RE=""
ANCHOR_ID_RE=""
ANCHOR_NUMBER_RANGE_RE='§11\.4\.'
MIRROR_SET=()

# shellcheck source=/dev/null
source "$CONFIG_PATH"

if [[ -z "$BASE_DIR" ]]; then
  echo "ERROR: config $CONFIG_PATH missing BASE_DIR" >&2
  exit 2
fi
if [[ "${#MIRROR_SET[@]}" -eq 0 ]]; then
  echo "ERROR: config $CONFIG_PATH declares empty MIRROR_SET" >&2
  exit 2
fi
if [[ -z "$BLOCK_START_RE" || -z "$ANCHOR_ID_RE" ]]; then
  echo "ERROR: config $CONFIG_PATH missing BLOCK_START_RE / ANCHOR_ID_RE" >&2
  exit 2
fi

# Resolve paths relative to config-declared BASE_DIR (which itself is
# either absolute or resolved relative to the config file's directory).
if [[ "$BASE_DIR" != /* ]]; then
  BASE_DIR="$(cd "$(dirname "$CONFIG_PATH")/$BASE_DIR" && pwd)"
fi

# ------------------------------------------------------------------------------
# Working state
# ------------------------------------------------------------------------------
TMPDIR_ROOT="$(mktemp -d -t anchor_integrity.XXXXXX)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT
FINDINGS_FILE="$TMPDIR_ROOT/findings"
: > "$FINDINGS_FILE"

report_fail() {
  echo "FAIL: $*" >> "$FINDINGS_FILE"
}

# extract_blocks <file> <state_dir>
#   Writes one line per block-start into <state_dir>/blocks.tsv:
#     anchor_id \t line_no \t title_line
#   Writes one file per block into <state_dir>/hash/<anchor_id>_<n>.sha
#     containing the sha256sum of the block body (block-start through the
#     line before the next block-start OR EOF).
extract_blocks() {
  local file="$1" sdir="$2"
  mkdir -p "$sdir/hash" "$sdir/bodies"
  : > "$sdir/blocks.tsv"

  awk -v RE_START="$BLOCK_START_RE" -v RE_ID="$ANCHOR_ID_RE" \
      -v out_tsv="$sdir/blocks.tsv" -v bodies_dir="$sdir/bodies" '
    function flush(  i, fname, n, safe_id) {
      if (cur_id != "") {
        # sanitize any accidental slashes in the anchor id ONLY (not the
        # full path — mangling the path would silently drop the body,
        # a §11.4.201(6) FALSE-NULL the extractor cannot see).
        safe_id = cur_id
        gsub("/", "_", safe_id)
        occ_seen[safe_id]++
        n = occ_seen[safe_id]
        fname = bodies_dir "/" safe_id "__" n ".body"
        printf "%s\t%d\t%s\n", cur_id, cur_line, cur_title >> out_tsv
        for (i = 1; i <= body_n; i++) {
          print body[i] >> fname
        }
        close(fname)
        body_n = 0
        cur_id = ""
      }
    }
    {
      if ($0 ~ RE_START) {
        flush()
        cur_line = NR
        cur_title = $0
        match($0, RE_ID)
        cur_id = substr($0, RSTART, RLENGTH)
        # Strip the leading § so the id key is stable regardless of
        # marker prefix. (Keep the number path §11.4.NNN[.suffix].)
        gsub(/^§/, "", cur_id)
        body_n = 1
        body[body_n] = $0
      } else if (cur_id != "") {
        body_n++
        body[body_n] = $0
      }
    }
    END { flush() }
  ' "$file"

  # Hash each body file.
  local body
  for body in "$sdir"/bodies/*.body; do
    [[ -e "$body" ]] || continue
    local base sha
    base="$(basename "$body" .body)"
    sha="$(sha256sum "$body" | awk '{print $1}')"
    printf '%s\n' "$sha" > "$sdir/hash/$base.sha"
  done
}

# check_exactly_once <file_label> <state_dir>
check_exactly_once() {
  local label="$1" sdir="$2"
  awk -F'\t' '
    { count[$1]++; sample_line[$1] = (sample_line[$1] ? sample_line[$1] "," $2 : $2) }
    END {
      for (k in count) if (count[k] > 1) {
        printf "%s\t%d\t%s\n", k, count[k], sample_line[k]
      }
    }
  ' "$sdir/blocks.tsv" | while IFS=$'\t' read -r anchor_id count lines; do
    report_fail "DUPLICATE-OR-COLLISION: $label — anchor §$anchor_id appears $count times at lines $lines"
  done
}

# check_zero_blocks <file_label> <state_dir>
check_zero_blocks() {
  local label="$1" sdir="$2"
  if [[ ! -s "$sdir/blocks.tsv" ]]; then
    report_fail "BLIND-EXTRACTOR: $label — zero block-starts extracted with regex '$BLOCK_START_RE' — refusing to declare clean (§11.4.201(6) false-null guard)"
  fi
}

# check_lockstep_equality — cross-mirror hash comparison
check_lockstep_equality() {
  local hashes_all="$TMPDIR_ROOT/lockstep_hashes.tsv"
  : > "$hashes_all"
  local idx label sdir sha_file sha anchor_id
  for idx in "${!MIRROR_SET[@]}"; do
    label="${MIRROR_SET[$idx]}"
    sdir="$TMPDIR_ROOT/state_$idx"
    if [[ -d "$sdir/hash" ]]; then
      for sha_file in "$sdir"/hash/*.sha; do
        [[ -e "$sha_file" ]] || continue
        local base
        base="$(basename "$sha_file" .sha)"
        anchor_id="${base%__*}"
        local occ="${base#*__}"
        sha="$(cat "$sha_file")"
        printf '%s\t%s\t%s\t%s\n' "$anchor_id" "$occ" "$label" "$sha" >> "$hashes_all"
      done
    fi
  done

  # For each (anchor_id, occurrence=1), check equality across all mirrors.
  awk -F'\t' '$2 == "1"' "$hashes_all" | sort -k1,1 | awk -F'\t' '
    {
      anchor = $1; file = $3; sha = $4
      if (anchor != prev_anchor) {
        if (prev_anchor != "" && n_files > 0) {
          emit_verdict()
        }
        prev_anchor = anchor
        n_files = 0
        n_shas = 0
        delete files
        delete shas
        delete sha_by_file
      }
      files[++n_files] = file
      sha_by_file[file] = sha
      if (!(sha in shas_seen)) { shas[++n_shas] = sha; shas_seen[sha] = 1 }
    }
    END {
      if (prev_anchor != "" && n_files > 0) emit_verdict()
    }
    function emit_verdict(   i, msg) {
      # A mirror missing from the anchor is a lockstep GAP.
      if (n_files != TOTAL_MIRRORS) {
        msg = "LOCKSTEP-GAP: anchor §" prev_anchor " present in " n_files " of " TOTAL_MIRRORS " mirrors ("
        for (i = 1; i <= n_files; i++) {
          msg = msg files[i] (i<n_files?", ":"")
        }
        msg = msg ")"
        print msg > "/dev/stderr"
        fails++
      } else if (n_shas > 1) {
        msg = "LOCKSTEP-DIVERGENCE: anchor §" prev_anchor " has " n_shas " distinct content-hashes across " TOTAL_MIRRORS " mirrors:"
        for (i = 1; i <= n_files; i++) {
          msg = msg " " files[i] "=" substr(sha_by_file[files[i]], 1, 12)
        }
        print msg > "/dev/stderr"
        fails++
      }
      delete shas_seen
    }
  ' TOTAL_MIRRORS="${#MIRROR_SET[@]}" 2> "$TMPDIR_ROOT/lockstep_findings"

  # Rewrite the awk-emitted findings into the canonical findings file.
  if [[ -s "$TMPDIR_ROOT/lockstep_findings" ]]; then
    while IFS= read -r line; do
      report_fail "$line"
    done < "$TMPDIR_ROOT/lockstep_findings"
  fi
}

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
echo "$SCRIPT_NAME — §11.4.227(B) anchor-block-integrity check"
echo "  config:         $CONFIG_PATH"
echo "  base-dir:       $BASE_DIR"
echo "  mirror-set:     ${#MIRROR_SET[@]} file(s)"
echo "  canonical:      ${CANONICAL_FILE:-<none>}"
echo "  block-start-re: $BLOCK_START_RE"
echo "  anchor-id-re:   $ANCHOR_ID_RE"
echo

# Resolve + extract for every mirror file.
for idx in "${!MIRROR_SET[@]}"; do
  rel="${MIRROR_SET[$idx]}"
  full="$BASE_DIR/$rel"
  sdir="$TMPDIR_ROOT/state_$idx"
  mkdir -p "$sdir"
  if [[ ! -f "$full" ]]; then
    report_fail "MISSING-FILE: mirror '$rel' does not exist at '$full'"
    continue
  fi
  extract_blocks "$full" "$sdir"
  check_zero_blocks "$rel" "$sdir"
  check_exactly_once "$rel" "$sdir"
  if [[ $VERBOSE -eq 1 ]]; then
    echo "  $rel — $(wc -l < "$sdir/blocks.tsv") block-start(s)"
  fi
done

# Canonical file — checked for exactly-once + zero-blocks only.
if [[ -n "$CANONICAL_FILE" ]]; then
  full="$BASE_DIR/$CANONICAL_FILE"
  sdir="$TMPDIR_ROOT/state_canonical"
  mkdir -p "$sdir"
  if [[ ! -f "$full" ]]; then
    report_fail "MISSING-FILE: canonical '$CANONICAL_FILE' does not exist at '$full'"
  else
    extract_blocks "$full" "$sdir"
    check_zero_blocks "$CANONICAL_FILE" "$sdir"
    check_exactly_once "$CANONICAL_FILE" "$sdir"
    if [[ $VERBOSE -eq 1 ]]; then
      echo "  $CANONICAL_FILE — $(wc -l < "$sdir/blocks.tsv") block-start(s) [canonical]"
    fi
  fi
fi

# Cross-mirror lockstep equality — mirrors ONLY, canonical excluded.
check_lockstep_equality

# ------------------------------------------------------------------------------
# Verdict
# ------------------------------------------------------------------------------
if [[ -s "$FINDINGS_FILE" ]]; then
  echo
  echo "=== FINDINGS ==="
  cat "$FINDINGS_FILE" >&2
  echo
  count=$(wc -l < "$FINDINGS_FILE" | tr -d ' ')
  echo "FAIL: $count anchor-block-integrity finding(s) (§11.4.227(B))" >&2
  exit 1
fi

echo "PASS: anchor-block-integrity clean across ${#MIRROR_SET[@]} mirror(s)${CANONICAL_FILE:+ + canonical}"
exit 0
