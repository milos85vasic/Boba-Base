#!/usr/bin/env bash
#
# ci-ext.sh — BobaLink browser-extension MANUAL pre-release gate
# =============================================================================
# Purpose:
#   Manual, all-in-one release-readiness gate for the BobaLink (Boba/BobaLink)
#   browser extension. Runs the type gate, lint gate, full unit suite, both
#   store builds (Chrome MV3 + Firefox), an anti-bluff artifact-asset
#   verification (Constitution §11.4.38), and the per-store zip packaging,
#   FAILing loudly on the first failing step. There is NO CI/CD pipeline and
#   none may be created (Constitution Hard Stop §1 + project CLAUDE.md) — this
#   script is the ONLY gate and is invoked by hand before any release.
#
# Usage:
#   cd extension && bash ci-ext.sh
#   (run from the extension/ directory, or any cwd — the script cd's to its own
#    directory first)
#
# Inputs:
#   - The extension source tree under ./src, ./wxt.config.ts, ./vitest.config.ts.
#   - A populated ./node_modules (run `npm install` first).
#   - Tools on PATH: node, npx, jq.
#   No CLI arguments, no env-var configuration.
#
# Outputs:
#   - Console log of each step with PASS/FAIL markers.
#   - Build artifacts under .output/chrome-mv3/ and .output/firefox-mv2/.
#   - Per-store .zip packages under .output/ (e.g. bobalink-<ver>-chrome.zip,
#     bobalink-<ver>-firefox.zip).
#   - Final line "CI-EXT: PASS" ONLY if every step passed; otherwise the script
#     exits non-zero at the first failing step with a "CI-EXT: FAIL" diagnostic.
#
# Side-effects:
#   - Writes/overwrites the .output/ build + zip artifacts.
#   - Runs the full vitest suite (no network, no live services).
#   - Does NOT touch git, does NOT commit, does NOT start any container.
#
# Dependencies:
#   - bash (set -euo pipefail), node + npx (wxt, tsc, vitest, eslint), jq.
#   - npm scripts: lint, zip, zip:firefox (declared in package.json).
#   - wxt for build (`wxt build`, `wxt build -b firefox`) and zip.
#
# Cross-references:
#   - docs/scripts/ci-ext.md            (this script's §11.4.18 companion doc)
#   - Constitution §11.4.38             (installable-asset evidence mandate —
#                                         step 5 opens the artifact + verifies
#                                         every declared user-visible asset)
#   - Constitution §11.4.18             (script documentation mandate)
#   - Constitution Hard Stop §1         (NO CI/CD — this is a MANUAL gate)
#   - project CLAUDE.md "CI IS MANUAL"  (permanent rule)
# =============================================================================

set -euo pipefail

# Always operate from the script's own directory (the extension root) so the
# gate is invocable from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
_step=0
step() {
  _step=$((_step + 1))
  printf '\n========== STEP %d: %s ==========\n' "$_step" "$1"
}
ok()   { printf '  [PASS] %s\n' "$1"; }
fail() {
  printf '  [FAIL] %s\n' "$1" >&2
  printf '\nCI-EXT: FAIL (step %d)\n' "$_step" >&2
  exit 1
}

# Verify a hard tool dependency is present (FAIL loudly if missing — never skip).
require_tool() {
  command -v "$1" >/dev/null 2>&1 || fail "required tool '$1' not found on PATH"
}

# ---------------------------------------------------------------------------
# Pre-flight: required tools
# ---------------------------------------------------------------------------
step "pre-flight tool check"
for t in node npx jq; do
  require_tool "$t"
done
ok "node, npx, jq present"

# ---------------------------------------------------------------------------
# STEP 1 — TypeScript type gate
# ---------------------------------------------------------------------------
step "type gate (tsc --noEmit)"
npx tsc --noEmit || fail "tsc reported type errors"
ok "no type errors"

# ---------------------------------------------------------------------------
# STEP 2 — ESLint gate
# ---------------------------------------------------------------------------
step "lint gate (npm run lint)"
npm run lint || fail "eslint reported problems"
ok "lint clean"

# ---------------------------------------------------------------------------
# STEP 3 — full unit suite (vitest). Require exit 0; do NOT hardcode count.
# ---------------------------------------------------------------------------
step "unit suite (vitest run)"
npx vitest run || fail "vitest suite did not pass"
ok "vitest suite passed"

# ---------------------------------------------------------------------------
# STEP 4 — both store builds. Both must succeed.
# ---------------------------------------------------------------------------
step "build chrome (wxt build)"
npx wxt build || fail "chrome build failed"
ok "chrome build succeeded"

step "build firefox (wxt build -b firefox)"
npx wxt build -b firefox || fail "firefox build failed"
ok "firefox build succeeded"

# ---------------------------------------------------------------------------
# STEP 5 — §11.4.38 installable-asset verification (ANTI-BLUFF CORE).
#
#   Opens the produced manifest.json (NOT the source), enumerates every
#   user-visible asset the manifest declares, follows the HTML pages it
#   references to enumerate THEIR local asset references, and asserts every
#   one EXISTS on disk and is NON-ZERO. A build that exits 0 but ships a
#   stripped icon / missing chunk / empty page FAILs here.
# ---------------------------------------------------------------------------
verify_artifact() {
  local out_dir="$1"
  local manifest="$out_dir/manifest.json"
  local failures=0

  [[ -f "$manifest" ]] || { printf '  [FAIL] manifest.json absent: %s\n' "$manifest" >&2; return 1; }
  [[ -s "$manifest" ]] || { printf '  [FAIL] manifest.json is empty: %s\n' "$manifest" >&2; return 1; }

  # manifest_version must be 3 (Chrome MV3).
  local mv
  mv="$(jq -r '.manifest_version' "$manifest")"
  if [[ "$mv" == "3" ]]; then
    printf '  [PASS] manifest_version == 3\n'
  else
    printf '  [FAIL] manifest_version is "%s", expected 3\n' "$mv" >&2
    failures=$((failures + 1))
  fi

  # background.service_worker must be present.
  local sw
  sw="$(jq -r '.background.service_worker // empty' "$manifest")"
  if [[ -n "$sw" ]]; then
    printf '  [PASS] background.service_worker declared: %s\n' "$sw"
  else
    printf '  [FAIL] background.service_worker missing from manifest\n' >&2
    failures=$((failures + 1))
  fi

  # Assert a single referenced file exists on disk and is non-zero.
  # Paths are manifest-relative; strip a leading slash if present.
  assert_asset() {
    local rel="${1#/}"
    local abs="$out_dir/$rel"
    if [[ ! -e "$abs" ]]; then
      printf '  [FAIL] referenced asset MISSING: %s\n' "$rel" >&2
      failures=$((failures + 1))
    elif [[ ! -s "$abs" ]]; then
      printf '  [FAIL] referenced asset EMPTY (0 bytes): %s\n' "$rel" >&2
      failures=$((failures + 1))
    else
      printf '  [PASS] asset present + non-zero: %s\n' "$rel"
    fi
  }

  # Collect every asset the manifest declares (icons, service worker, content
  # scripts, action popup, options page, web-accessible resources, default
  # locale messages). jq emits one manifest-relative path per line.
  local -a manifest_assets=()
  while IFS= read -r p; do
    [[ -n "$p" ]] && manifest_assets+=("$p")
  done < <(jq -r '
    [
      ( .icons // {} | .[] ),
      ( .action.default_icon // {} | if type=="object" then .[] else . end ),
      ( .background.service_worker // empty ),
      ( .action.default_popup // empty ),
      ( .options_ui.page // empty ),
      ( .options_page // empty ),
      ( .content_scripts // [] | .[] | (.js // [])[] , (.css // [])[] ),
      ( .web_accessible_resources // [] | .[] | (.resources // [])[] ),
      # Chrome HARD-REQUIRES _locales/<default_locale>/messages.json whenever
      # default_locale is set + __MSG_*__ placeholders are used (else the
      # extension is rejected at load). A build that drops it is the exact
      # §11.4.38 stripped-asset failure mode — so we assert it explicitly.
      ( if (.default_locale // empty) != "" then "_locales/" + .default_locale + "/messages.json" else empty end )
    ] | .[]
  ' "$manifest")

  # The HTML pages that the manifest points at are themselves verified, AND
  # parsed for their local src/href references (chunks/assets/icons).
  local -a html_pages=()
  for a in "${manifest_assets[@]}"; do
    case "$a" in
      *.html) html_pages+=("$a") ;;
    esac
  done

  printf '  -- verifying %d manifest-declared asset(s) --\n' "${#manifest_assets[@]}"
  for a in "${manifest_assets[@]}"; do
    assert_asset "$a"
  done

  # Follow each HTML page's local references.
  for page in "${html_pages[@]}"; do
    local page_abs="$out_dir/${page#/}"
    [[ -f "$page_abs" ]] || continue
    printf '  -- following local refs in %s --\n' "$page"
    # Extract src="..." / href="..." values; keep only local refs (leading /
    # or relative path) — skip http(s):, data:, mailto:, and bare anchors (#).
    while IFS= read -r ref; do
      case "$ref" in
        http://*|https://*|data:*|mailto:*|"#"*|"") continue ;;
      esac
      assert_asset "$ref"
    done < <(grep -oE '(src|href)="[^"]+"' "$page_abs" \
             | sed -E 's/^(src|href)="//; s/"$//')
  done

  if [[ "$failures" -gt 0 ]]; then
    printf '  [FAIL] %d asset verification failure(s) in %s\n' "$failures" "$out_dir" >&2
    return 1
  fi
  return 0
}

step "§11.4.38 artifact asset verification (chrome-mv3)"
verify_artifact ".output/chrome-mv3" || fail "chrome-mv3 artifact asset verification failed"
ok "all chrome-mv3 declared + referenced assets present and non-zero"

# ---------------------------------------------------------------------------
# STEP 6 — per-store zip packaging + size assertion.
# ---------------------------------------------------------------------------
# Minimum trustworthy zip size (bytes). A real packed extension is tens of KB+;
# anything under this floor indicates an empty/stub archive.
MIN_ZIP_BYTES=10240

assert_zip() {
  local pattern="$1"
  local label="$2"
  # Find the newest zip matching the pattern under .output/.
  local zip
  zip="$(ls -t .output/${pattern} 2>/dev/null | head -n1 || true)"
  if [[ -z "$zip" || ! -f "$zip" ]]; then
    printf '  [FAIL] %s zip not found (pattern: .output/%s)\n' "$label" "$pattern" >&2
    return 1
  fi
  local size
  size="$(wc -c < "$zip" | tr -d '[:space:]')"
  if [[ "$size" -lt "$MIN_ZIP_BYTES" ]]; then
    printf '  [FAIL] %s zip too small (%s bytes < %s): %s\n' "$label" "$size" "$MIN_ZIP_BYTES" "$zip" >&2
    return 1
  fi
  printf '  [PASS] %s zip present (%s bytes): %s\n' "$label" "$size" "$zip"
  return 0
}

step "package chrome zip (npm run zip)"
npm run zip || fail "wxt zip (chrome) failed"
assert_zip "*chrome*.zip" "chrome" || fail "chrome zip artifact invalid"

step "package firefox zip (npm run zip:firefox)"
npm run zip:firefox || fail "wxt zip (firefox) failed"
# wxt firefox zip emits a -firefox.zip and a -sources.zip; verify the store zip.
assert_zip "*firefox*.zip" "firefox" || fail "firefox zip artifact invalid"

# ---------------------------------------------------------------------------
# All steps passed.
# ---------------------------------------------------------------------------
printf '\nCI-EXT: PASS\n'
