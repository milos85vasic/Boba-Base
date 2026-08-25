#!/usr/bin/env bash
# §1.1 paired mutations for CM-SERVED-BUNDLE-FRESH (BOB-183).
#
# A gate is UNVALIDATED INSTRUMENTATION until it has been OBSERVED to FAIL on a
# genuinely broken artifact (§11.4.115(F)). These cases plant real staleness and
# require the refusal — and, symmetrically, plant a genuinely FRESH bundle and
# require the PASS, because a gate that refuses everything is a §11.4.201(1)
# FAIL-bluff exactly as forbidden as one that passes everything.
#
# The BLIND cases are the load-bearing ones (§11.4.201(6)): a blind instrument
# and a fresh bundle otherwise return the identical quiet green. That is the hole
# that let 301 charset-less exports sit behind a green export gate (BOB-169), and
# the hole install.sh:133 left open by asserting only that a directory EXISTS.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
GATE="${PROJECT_ROOT}/scripts/pre_build/check_cm_served_bundle_fresh.sh"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
bad(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
[[ -f "$GATE" ]] || { echo "FAIL: gate missing at $GATE"; exit 1; }

FIX="$(mktemp -d)"; trap 'rm -rf "$FIX"' EXIT

DIST_REL="download-proxy/src/ui/dist/frontend/browser"

# make_fixture <name> [--no-src] [--no-dist] [--empty-dist]
# Builds a self-contained project root with frontend sources and a served bundle.
make_fixture() {
  local name="$1"; shift
  local r="${FIX}/${name}"
  local no_src=0 no_dist=0 empty_dist=0
  for a in "$@"; do
    case "$a" in
      --no-src) no_src=1 ;;
      --no-dist) no_dist=1 ;;
      --empty-dist) empty_dist=1 ;;
    esac
  done
  mkdir -p "${r}/frontend" || return 1
  if [[ "$no_src" -eq 0 ]]; then
    mkdir -p "${r}/frontend/src/app/models" || return 1
    printf 'export const PALETTE = { onSuccess: "#000000" };\n' > "${r}/frontend/src/app/models/palette.model.ts"
    printf 'export const APP = 1;\n' > "${r}/frontend/src/app/app.ts"
    printf '{"projects":{"frontend":{"architect":{"build":{"options":{"outputPath":"../%s"}}}}}}\n' "$DIST_REL" \
      > "${r}/frontend/angular.json"
    printf '{"name":"frontend","version":"1.0.0"}\n' > "${r}/frontend/package.json"
  fi
  if [[ "$no_dist" -eq 0 ]]; then
    mkdir -p "${r}/${DIST_REL}" || return 1
    if [[ "$empty_dist" -eq 0 ]]; then
      printf 'var a=1;//--color-on-success\n' > "${r}/${DIST_REL}/main-AAAA.js"
      printf ':root{--color-on-success:#000}\n'  > "${r}/${DIST_REL}/styles-AAAA.css"
      printf '<!DOCTYPE html><html><body></body></html>\n' > "${r}/${DIST_REL}/index.html"
    fi
  fi
  echo "$r"
}

run_gate() { # $1=root, rest=extra args before root
  local root="$1"; shift
  [[ -n "${root:-}" && -d "${root}" ]] || { OUT="fixture setup failed for root='${root:-}' — gate NOT executed"; RC=97; return; }
  OUT="$(GOMAXPROCS=2 nice -n 19 ionice -c 3 bash "$GATE" "$@" "$root" 2>&1)"; RC=$?
}

echo "=== CM-SERVED-BUNDLE-FRESH — paired §1.1 mutations ==="

# ─────────────────────────────────────────────────────────────────────
# 1. NEGATIVE CONTROL (§11.4.201(1)) — a genuinely FRESH bundle must PASS.
#    Without this the gate could refuse everything and look rigorous.
# ─────────────────────────────────────────────────────────────────────
R_FRESH="$(make_fixture fresh)"
run_gate "$R_FRESH" --write
if [[ "$RC" -eq 0 ]]; then
  ok "--write records a fingerprint for a real artifact (exit 0)"
else
  bad "--write failed on a valid fixture (exit ${RC}) — the re-arm path is broken"
fi
run_gate "$R_FRESH"
[[ "$RC" -eq 0 ]] && ok "NEGATIVE CONTROL: fresh bundle -> gate PASSES (no false-positive refusal, §11.4.201(1))" \
                 || bad "a genuinely fresh bundle was REFUSED (exit ${RC}) — FAIL-bluff: ${OUT}"

# ─────────────────────────────────────────────────────────────────────
# 2. RED / golden-TRUE — a source changes after the build. The served bundle is
#    now stale. The gate must REFUSE and name the non-correspondence.
# ─────────────────────────────────────────────────────────────────────
R_STALE="$(make_fixture stale)"
run_gate "$R_STALE" --write
if [[ "$RC" -ne 0 ]]; then
  bad "fixture setup: --write failed on stale fixture (exit ${RC}); RED not executed"
else
  # the BOB-164 shape exactly: a palette source gains a token the bundle lacks
  printf 'export const PALETTE = { onSuccess: "#000000", onDanger: "#ffffff" };\n' \
    > "${R_STALE}/frontend/src/app/models/palette.model.ts"
  run_gate "$R_STALE"
  [[ "$RC" -ne 0 ]] && ok "MUTATION/RED: source changed after build -> gate REFUSES the stale bundle (exit ${RC})" \
                    || bad "a STALE bundle was ACCEPTED (exit ${RC}) — the gate does not bite"
  grep -q 'does NOT correspond to current sources' <<<"$OUT" \
    && ok "refusal names the non-correspondence and prints both fingerprints" \
    || bad "refusal message does not name the non-correspondence: ${OUT}"
fi

# ─────────────────────────────────────────────────────────────────────
# 3. BLIND #1 (§11.4.201(6)) — ZERO build inputs discovered.
#    A fingerprint over an empty input set is a stable, confident, WRONG value
#    that would match any sidecar recorded the same way. Must REFUSE, not report
#    a clean zero. This is the single most important case.
#
#    THE FIXTURE ISOLATES THE BLIND CONDITION DELIBERATELY. An earlier version
#    of this case simply omitted the sources — but then the bundle also had no
#    sidecar, so the sidecar-missing guard refused first and MASKED the blind
#    guard entirely. A reviewer-authored mutation (deleting the blind guard)
#    still produced exit 1, and only the message assertion caught it
#    (§11.4.194(6)(d)). So here the fixture is built COMPLETE and fingerprinted
#    first, and only THEN are the sources removed: sidecar valid, artifact
#    present and non-empty, and the sole remaining defect is zero inputs.
# ─────────────────────────────────────────────────────────────────────
R_BLIND="$(make_fixture blindsrc)"
run_gate "$R_BLIND" --write
if [[ "$RC" -ne 0 ]]; then
  bad "fixture setup: --write failed on blind fixture (exit ${RC}); BLIND case NOT executed"
else
  rm -rf "${R_BLIND}/frontend/src" "${R_BLIND}/frontend/angular.json" "${R_BLIND}/frontend/package.json"
  run_gate "$R_BLIND"
  [[ "$RC" -ne 0 ]] && grep -q 'BLIND' <<<"$OUT" \
    && ok "BLIND corpus (zero build inputs, sidecar VALID) -> REFUSES rather than reporting a clean zero (§11.4.201(6))" \
    || bad "an empty input set reported CLEAN — the false-null the needle exists to prevent (exit ${RC}): ${OUT}"
fi

# ─────────────────────────────────────────────────────────────────────
# 4. BLIND #2 — no served bundle at all. Nothing is being served to verify.
# ─────────────────────────────────────────────────────────────────────
R_NODIST="$(make_fixture nodist --no-dist)"
run_gate "$R_NODIST"
[[ "$RC" -ne 0 ]] && grep -q 'no served bundle' <<<"$OUT" \
  && ok "absent bundle -> REFUSES (a missing artifact is not a fresh artifact)" \
  || bad "an absent bundle did not refuse (exit ${RC}): ${OUT}"

# ─────────────────────────────────────────────────────────────────────
# 5. BLIND #3 — the install.sh:133 hole EXACTLY: directory exists, contents do
#    not. The old check printed "dist present" and moved on.
# ─────────────────────────────────────────────────────────────────────
R_EMPTY="$(make_fixture emptydist --empty-dist)"
run_gate "$R_EMPTY"
[[ "$RC" -ne 0 ]] && grep -q 'ZERO js/css/html' <<<"$OUT" \
  && ok "empty bundle DIRECTORY -> REFUSES (closes the install.sh:133 exists-only hole)" \
  || bad "an empty bundle directory passed — the exists-only hole is still open (exit ${RC}): ${OUT}"

# ─────────────────────────────────────────────────────────────────────
# 6. NEVER FINGERPRINTED — sources and bundle both present, but nothing ever
#    recorded what the bundle was built from. UNKNOWN is not CLEAN.
#    (This is the real-world state of the main checkout at adoption.)
# ─────────────────────────────────────────────────────────────────────
R_NOSIDE="$(make_fixture nosidecar)"
run_gate "$R_NOSIDE"
[[ "$RC" -ne 0 ]] && grep -q 'NEVER fingerprinted' <<<"$OUT" \
  && ok "no fingerprint sidecar -> REFUSES: UNKNOWN is not CLEAN (§11.4.201(6))" \
  || bad "an unfingerprinted bundle passed (exit ${RC}): ${OUT}"

# ─────────────────────────────────────────────────────────────────────
# 7. MALFORMED sidecar — a truncated/garbage fingerprint must not be treated as
#    a match, and must not crash the comparison into a quiet pass.
# ─────────────────────────────────────────────────────────────────────
R_MAL="$(make_fixture malformed)"
run_gate "$R_MAL" --write
if [[ "$RC" -ne 0 ]]; then
  bad "fixture setup: --write failed on malformed fixture (exit ${RC})"
else
  printf 'not-a-sha256\n' > "${R_MAL}/download-proxy/src/ui/dist/frontend/.build-inputs.sha256"
  run_gate "$R_MAL"
  [[ "$RC" -ne 0 ]] && grep -q 'malformed' <<<"$OUT" \
    && ok "malformed sidecar -> REFUSES rather than silently mismatching or passing" \
    || bad "a malformed sidecar did not refuse cleanly (exit ${RC}): ${OUT}"
fi

# ─────────────────────────────────────────────────────────────────────
# 8. --write cannot certify a bundle that was never produced. Otherwise the
#    re-arm path becomes a laundering channel: run --write, get a green gate,
#    ship nothing (§11.4.249 — the producer must not be able to write its own
#    passing verdict out of thin air).
# ─────────────────────────────────────────────────────────────────────
R_WEMPTY="$(make_fixture writeempty --empty-dist)"
run_gate "$R_WEMPTY" --write
[[ "$RC" -ne 0 ]] \
  && ok "--write REFUSES to fingerprint an empty artifact (cannot certify what was never built)" \
  || bad "--write certified an EMPTY bundle (exit ${RC}) — the re-arm path launders a green verdict"

# ─────────────────────────────────────────────────────────────────────
# 9. SEAM SEMANTICS (--if-present, §11.4.120 / §11.4.69). At a PRE-build seam an
#    absent artifact is `artifact_not_yet_built`, not a failure. But the flag
#    must relax EXACTLY that and nothing else — if it became a blanket bypass it
#    would be a far worse hole than the one this ticket closes.
# ─────────────────────────────────────────────────────────────────────
R_IFP="$(make_fixture ifpresent --no-dist)"
run_gate "$R_IFP" --if-present
[[ "$RC" -eq 0 ]] && grep -q 'artifact_not_yet_built' <<<"$OUT" \
  && ok "--if-present + absent bundle -> honest non-blocking SKIP (§11.4.69), not a failure" \
  || bad "--if-present did not skip cleanly on an absent bundle (exit ${RC}): ${OUT}"

# --if-present must NOT excuse a bundle that IS present and IS stale.
R_IFP2="$(make_fixture ifpresentstale)"
run_gate "$R_IFP2" --write
if [[ "$RC" -ne 0 ]]; then
  bad "fixture setup: --write failed on ifpresentstale (exit ${RC})"
else
  printf 'export const PALETTE = { onSuccess: "#000000", onInfo: "#ffffff" };\n' \
    > "${R_IFP2}/frontend/src/app/models/palette.model.ts"
  run_gate "$R_IFP2" --if-present
  [[ "$RC" -ne 0 ]] \
    && ok "--if-present + PRESENT but STALE bundle -> still REFUSES (not a blanket bypass)" \
    || bad "--if-present excused a stale bundle (exit ${RC}) — the flag is a bypass, not a seam"
fi

# --if-present must NOT relax BLINDNESS. A blind instrument is unacceptable at
# every seam; only artifact ABSENCE is seam-dependent.
R_IFP3="$(make_fixture ifpresentblind)"
run_gate "$R_IFP3" --write
if [[ "$RC" -ne 0 ]]; then
  bad "fixture setup: --write failed on ifpresentblind (exit ${RC})"
else
  rm -rf "${R_IFP3}/frontend/src" "${R_IFP3}/frontend/angular.json" "${R_IFP3}/frontend/package.json"
  run_gate "$R_IFP3" --if-present
  [[ "$RC" -ne 0 ]] && grep -q 'BLIND' <<<"$OUT" \
    && ok "--if-present + BLIND input enumeration -> still REFUSES (blindness is never seam-dependent)" \
    || bad "--if-present turned a BLIND scan into a pass (exit ${RC}) — the flag became a blindness bypass: ${OUT}"
fi

# ─────────────────────────────────────────────────────────────────────
# 10. WIRING (§11.4.196(F) — CONFIGURED IS NOT IN USE). A gate nothing invokes
#    protects nothing. These are STRUCTURAL assertions on install.sh, and they
#    are labelled as such: the BEHAVIOURAL proof that the gate bites is cases
#    1-8 above, which execute it. An end-to-end `install.sh` run is NOT executed
#    here — install.sh installs systemd units and drives containers, which the
#    container Hard Stop forbids from a test (§11.4.3 honest SKIP-with-reason,
#    never a silent pass).
# ─────────────────────────────────────────────────────────────────────
INSTALL="${PROJECT_ROOT}/scripts/install.sh"
if [[ ! -f "$INSTALL" ]]; then
  bad "WIRING: scripts/install.sh not found — cannot verify the gate is invoked"
else
  grep -q 'check_cm_served_bundle_fresh.sh' "$INSTALL" \
    && ok "WIRING(structural): install.sh invokes the served-bundle gate" \
    || bad "WIRING: install.sh does NOT invoke the gate — it is configured, not in use (§11.4.196(F))"

  # Fail-closed: the verify invocation must abort the install, not warn past it.
  grep -q '_fail "CM-SERVED-BUNDLE-FRESH' "$INSTALL" \
    && ok "WIRING(structural): a stale bundle ABORTS install via _fail (fail-closed, §11.4.252)" \
    || bad "WIRING: the gate result is not bound to _fail — a stale bundle would only warn"

  # No laundering: --write must be reachable only when the build actually succeeded.
  grep -q '_fe_built" = "1"' "$INSTALL" \
    && ok "WIRING(structural): --write is guarded by build success (cannot certify a failed build, §11.4.249)" \
    || bad "WIRING: --write is not guarded by build success — a failed build could fingerprint the OLD bundle as fresh"

  # The exists-only check this ticket removed must not have crept back.
  if grep -q 'dist present at download-proxy/src/ui/dist/frontend' "$INSTALL"; then
    bad "WIRING: the exists-only 'dist present' check is back — install.sh:133's hole reopened"
  else
    ok "WIRING(structural): the exists-only 'dist present' check is gone (BOB-183 root cause)"
  fi
fi

echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
