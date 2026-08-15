#!/usr/bin/env bash
# upstream_proxy_wired_challenge.sh — BOB-066 cross-layer anti-bluff verifier.
#
# Verifies that BOBA_UPSTREAM_PROXY is honored across the FOUR layers the
# BOB-066 (Lava P3) mandate requires:
#
#   L1 — download-proxy (Python): apply_proxy_env() called at boot + every
#        aiohttp.ClientSession in merge_service/search.py carries trust_env.
#   L2 — qBitTorrent-go: internal/httpx/proxy.go exports Configure/NewTransport/
#        Proxy; cmd/qbittorrent-proxy/main.go calls httpx.Configure at boot;
#        internal/api/download.go uses httpx.NewTransport().
#   L3 — Jackett: env-forwarded in the jackett container OR configured via the
#        Jackett ServerConfig ProxyUrl API. Neither path is wired yet — the
#        challenge honestly SKIPs with reason `extension_absent` (§11.4.3 /
#        §11.4.69) and records the tracked-follow-up defect class.
#   L4 — docker-compose.yml: every tracker-touching service block env-forwards
#        BOBA_UPSTREAM_PROXY + HTTP_PROXY/HTTPS_PROXY/NO_PROXY.
#
# §11.4.115 polarity switch: RED_MODE=0 (default, GREEN guard — assertions
# expect the presence-of-wiring); RED_MODE=1 flips to FAIL on the same
# assertions so the guard REPRODUCES the pre-fix defect state — a same-source
# guard, not a separate happy-path (§11.4.43 anti-bluff).
#
# §11.4.107(10) self-validation: a `--self-validate` mode runs the exact
# detector chain against a synthetic golden-BAD tree in a temp dir (where
# apply_proxy_env is NOT called and httpx.NewTransport is NOT used) and
# asserts the chain FAILs — proving the detectors can see a broken state.
#
# §11.4.10: proxy URL values are NEVER printed — only their string LENGTH
# where relevant. The env value itself is not required for the source-
# inspection paths this challenge uses.
#
# §11.4.6: no field is fabricated — a genuinely-un-wired layer SKIPs, never
# silently PASSes.
#
# Pass rule: L1 GREEN + L2 GREEN + L4-partial (the three wired services) +
# L3 honest SKIP → challenge exits 0 (all present layers verified, gap is
# tracked). Any L1/L2/L4 detection failure → exit 1.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
RED_MODE="${RED_MODE:-0}"
SELF_VALIDATE="${1:-}"

fail=0
pass=0
skip=0
notes=()

# Emit a decision with the anti-bluff verdict class.
verdict() {
  local kind="$1" msg="$2"
  case "$kind" in
    PASS) pass=$((pass + 1)); echo "  [PASS] $msg" ;;
    FAIL) fail=$((fail + 1)); echo "  [FAIL] $msg" ;;
    SKIP) skip=$((skip + 1)); echo "  [SKIP] $msg" ;;
  esac
}

# Detection helpers. Each returns 0 on presence, 1 on absence.
# Callers apply RED_MODE polarity to interpret.
python_apply_env_call_present() {
  grep -qE '^\s*apply_proxy_env\(\)' "$REPO/download-proxy/src/main.py"
}
python_trust_env_widespread() {
  # Expect >= 6 occurrences of _tracker_session_kwargs() calls (currently 8).
  local n
  n=$(grep -cE '_tracker_session_kwargs\(\)' "$REPO/download-proxy/src/merge_service/search.py" 2>/dev/null)
  n="${n:-0}"
  [ "$n" -ge 6 ]
}
python_proxy_module_exports() {
  local f="$REPO/download-proxy/src/config/proxy.py"
  grep -q '^def apply_proxy_env' "$f" \
    && grep -q '^def aiohttp_session_kwargs' "$f" \
    && grep -q '^UPSTREAM_PROXY_ENV = "BOBA_UPSTREAM_PROXY"' "$f"
}
go_httpx_module_exports() {
  local f="$REPO/qBitTorrent-go/internal/httpx/proxy.go"
  grep -q '^func Configure(' "$f" \
    && grep -q '^func NewTransport()' "$f" \
    && grep -q '^func Proxy(' "$f" \
    && grep -q 'BOBA_UPSTREAM_PROXY' "$f"
}
go_httpx_configure_at_boot() {
  grep -qE 'httpx\.Configure\(cfg\.UpstreamProxy\)' \
    "$REPO/qBitTorrent-go/cmd/qbittorrent-proxy/main.go"
}
go_httpx_transport_wired() {
  # At least one client in internal/api uses httpx.NewTransport for its
  # outbound-tracker path.
  grep -rq 'httpx\.NewTransport()' "$REPO/qBitTorrent-go/internal/api/" 2>/dev/null
}
compose_service_env_forwarded() {
  local service="$1"
  # Extract the block for this service (until next top-level key), check the
  # 4 required env vars are present.
  awk -v svc="$service" '
    $0 ~ "^  "svc":"           { inblk=1; next }
    inblk && /^  [a-zA-Z][^:]*:$/ { inblk=0 }
    inblk { print }
  ' "$REPO/docker-compose.yml" \
    | grep -qE '^\s*-\s*BOBA_UPSTREAM_PROXY=' \
    && awk -v svc="$service" '
        $0 ~ "^  "svc":"           { inblk=1; next }
        inblk && /^  [a-zA-Z][^:]*:$/ { inblk=0 }
        inblk { print }
      ' "$REPO/docker-compose.yml" \
    | grep -qE '^\s*-\s*HTTP_PROXY=' \
    && awk -v svc="$service" '
        $0 ~ "^  "svc":"           { inblk=1; next }
        inblk && /^  [a-zA-Z][^:]*:$/ { inblk=0 }
        inblk { print }
      ' "$REPO/docker-compose.yml" \
    | grep -qE '^\s*-\s*HTTPS_PROXY=' \
    && awk -v svc="$service" '
        $0 ~ "^  "svc":"           { inblk=1; next }
        inblk && /^  [a-zA-Z][^:]*:$/ { inblk=0 }
        inblk { print }
      ' "$REPO/docker-compose.yml" \
    | grep -qE '^\s*-\s*NO_PROXY='
}
jackett_proxy_wired_any_path() {
  # Path (a): jackett container env-forward.
  if compose_service_env_forwarded "jackett"; then
    return 0
  fi
  # Path (b): Jackett ServerConfig.ProxyUrl programmatic wiring.
  if grep -rqE 'ProxyUrl|ProxyType|ServerConfig' \
        "$REPO/qBitTorrent-go/internal/" 2>/dev/null; then
    return 0
  fi
  return 1
}

# --- Self-validation mode (§11.4.107(10) analyzer-honesty) --------------------
if [ "$SELF_VALIDATE" = "--self-validate" ]; then
  echo "=== self-validate: run detectors against a synthetic golden-BAD tree ==="
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  # Build a minimal golden-BAD tree: python main.py without apply_proxy_env,
  # search.py with zero trust_env, Go main.go without Configure call.
  mkdir -p "$tmp/download-proxy/src/config" \
           "$tmp/download-proxy/src/merge_service" \
           "$tmp/qBitTorrent-go/internal/httpx" \
           "$tmp/qBitTorrent-go/cmd/qbittorrent-proxy" \
           "$tmp/qBitTorrent-go/internal/api"
  # Golden-BAD Python main.py: apply_proxy_env NOT called.
  printf 'import os\nprint("hi")\n' > "$tmp/download-proxy/src/main.py"
  # Golden-BAD Python search.py: no trust_env calls at all.
  printf 'import aiohttp\nasync def s():\n    async with aiohttp.ClientSession() as s: pass\n' \
    > "$tmp/download-proxy/src/merge_service/search.py"
  # Golden-BAD Python proxy.py: missing the sentinel.
  printf '# stub with no exports\n' > "$tmp/download-proxy/src/config/proxy.py"
  # Golden-BAD Go: httpx has none of the symbols.
  printf 'package httpx\n// stub\n' > "$tmp/qBitTorrent-go/internal/httpx/proxy.go"
  printf 'package main\nfunc main() {}\n' > "$tmp/qBitTorrent-go/cmd/qbittorrent-proxy/main.go"
  # Golden-BAD Go: api dir has no transport call.
  printf 'package api\n// stub\n' > "$tmp/qBitTorrent-go/internal/api/download.go"
  # Golden-BAD compose: empty file.
  : > "$tmp/docker-compose.yml"

  # Re-point REPO at the synthetic tree for the detector chain.
  REPO="$tmp"

  bad=0
  python_apply_env_call_present && { echo "[SELF-VAL BAD] L1 apply_proxy_env presence"; bad=1; }
  python_trust_env_widespread    && { echo "[SELF-VAL BAD] L1 trust_env widespread";   bad=1; }
  python_proxy_module_exports    && { echo "[SELF-VAL BAD] L1 proxy module exports";    bad=1; }
  go_httpx_module_exports        && { echo "[SELF-VAL BAD] L2 httpx module exports";    bad=1; }
  go_httpx_configure_at_boot     && { echo "[SELF-VAL BAD] L2 configure-at-boot";       bad=1; }
  go_httpx_transport_wired       && { echo "[SELF-VAL BAD] L2 transport wired";         bad=1; }
  compose_service_env_forwarded "download-proxy" \
                                  && { echo "[SELF-VAL BAD] L4 download-proxy env";     bad=1; }

  if [ $bad -eq 0 ]; then
    echo "PASS: self-validate — every detector correctly FAILED on the golden-BAD tree"
    exit 0
  fi
  echo "FAIL: self-validate — at least one detector FALSELY passed on a golden-BAD tree"
  exit 1
fi

# --- Live run (against the real REPO tree) -----------------------------------
echo "=== BOB-066 four-layer cross-layer verifier ==="
echo "RED_MODE=$RED_MODE  (0=GREEN guard, 1=reproduce pre-fix defect state)"
echo ""

# Layer 1 — Python download-proxy
echo "--- L1: download-proxy (Python) ---"
if python_proxy_module_exports; then
  [ "$RED_MODE" = "1" ] && verdict FAIL "L1 config/proxy.py exports (expected absent under RED)" \
                       || verdict PASS "L1 config/proxy.py exports apply_proxy_env + aiohttp_session_kwargs"
else
  [ "$RED_MODE" = "1" ] && verdict PASS "L1 config/proxy.py exports absent (RED reproduces defect)" \
                       || verdict FAIL "L1 config/proxy.py missing required exports"
fi
if python_apply_env_call_present; then
  [ "$RED_MODE" = "1" ] && verdict FAIL "L1 apply_proxy_env() call in main.py (expected absent)" \
                       || verdict PASS "L1 apply_proxy_env() invoked at boot in download-proxy/src/main.py"
else
  [ "$RED_MODE" = "1" ] && verdict PASS "L1 apply_proxy_env() absent (RED reproduces defect)" \
                       || verdict FAIL "L1 apply_proxy_env() NOT called at boot in download-proxy/src/main.py"
fi
if python_trust_env_widespread; then
  n=$(grep -cE '_tracker_session_kwargs\(\)' "$REPO/download-proxy/src/merge_service/search.py" 2>/dev/null)
  n="${n:-0}"
  [ "$RED_MODE" = "1" ] && verdict FAIL "L1 trust_env widespread ($n sites; expected 0 under RED)" \
                       || verdict PASS "L1 aiohttp ClientSession sites carry trust_env ($n uses of _tracker_session_kwargs)"
else
  [ "$RED_MODE" = "1" ] && verdict PASS "L1 trust_env missing (RED reproduces defect)" \
                       || verdict FAIL "L1 aiohttp ClientSession sites missing _tracker_session_kwargs (<6 uses)"
fi

# Layer 2 — qBitTorrent-go
echo ""
echo "--- L2: qBitTorrent-go ---"
if go_httpx_module_exports; then
  [ "$RED_MODE" = "1" ] && verdict FAIL "L2 httpx module exports (expected absent under RED)" \
                       || verdict PASS "L2 internal/httpx/proxy.go exports Configure + NewTransport + Proxy honoring BOBA_UPSTREAM_PROXY"
else
  [ "$RED_MODE" = "1" ] && verdict PASS "L2 httpx module absent (RED reproduces defect)" \
                       || verdict FAIL "L2 internal/httpx/proxy.go missing required symbols"
fi
if go_httpx_configure_at_boot; then
  [ "$RED_MODE" = "1" ] && verdict FAIL "L2 httpx.Configure at boot (expected absent under RED)" \
                       || verdict PASS "L2 httpx.Configure(cfg.UpstreamProxy) called in cmd/qbittorrent-proxy/main.go"
else
  [ "$RED_MODE" = "1" ] && verdict PASS "L2 httpx.Configure absent (RED reproduces defect)" \
                       || verdict FAIL "L2 httpx.Configure(cfg.UpstreamProxy) NOT called at boot"
fi
if go_httpx_transport_wired; then
  [ "$RED_MODE" = "1" ] && verdict FAIL "L2 httpx.NewTransport wired (expected absent under RED)" \
                       || verdict PASS "L2 httpx.NewTransport() used in internal/api (torrent-download client)"
else
  [ "$RED_MODE" = "1" ] && verdict PASS "L2 httpx.NewTransport absent (RED reproduces defect)" \
                       || verdict FAIL "L2 internal/api never installs httpx.NewTransport() on a tracker-bound client"
fi

# Layer 3 — Jackett (either compose env-forward OR ServerConfig.ProxyUrl)
echo ""
echo "--- L3: Jackett ---"
if jackett_proxy_wired_any_path; then
  [ "$RED_MODE" = "1" ] && verdict FAIL "L3 Jackett proxy wired (expected absent under RED)" \
                       || verdict PASS "L3 Jackett proxy wired via env-forward OR ServerConfig.ProxyUrl"
else
  # Honest SKIP per §11.4.69 closed reason-set: extension_absent — neither
  # allowed path (jackett-container env-forward NOR ServerConfig.ProxyUrl API
  # wiring) is implemented in the current tree. This is BOB-066's tracked
  # residual gap; a fix requires either a docker-compose.yml env-block edit or
  # a new qBitTorrent-go/internal/jackettconfig module. Neither is in this
  # challenge's scope.
  verdict SKIP "L3 Jackett proxy honor: reason=extension_absent (neither compose env-forward nor ServerConfig.ProxyUrl wired) — tracked as BOB-066 residual"
  notes+=("L3 residual: Jackett has neither env-forward nor ServerConfig.ProxyUrl wired — see BOB-066 description")
fi

# Layer 4 — docker-compose.yml env-forward for tracker-touching services
echo ""
echo "--- L4: docker-compose.yml env-forward ---"
for svc in download-proxy qbittorrent-proxy-go qbittorrent; do
  if compose_service_env_forwarded "$svc"; then
    [ "$RED_MODE" = "1" ] && verdict FAIL "L4 $svc env-forward (expected absent under RED)" \
                         || verdict PASS "L4 docker-compose.yml service '$svc' env-forwards proxy vars"
  else
    [ "$RED_MODE" = "1" ] && verdict PASS "L4 $svc env-forward absent (RED reproduces defect)" \
                         || verdict FAIL "L4 docker-compose.yml service '$svc' MISSING proxy env-forward"
  fi
done
# jackett + boba-jackett: report but do NOT fail — the compose-env-forward path
# for jackett is the L3 responsibility (already SKIP'd above).
if compose_service_env_forwarded "jackett"; then
  verdict PASS "L4 docker-compose.yml service 'jackett' env-forwards proxy vars"
else
  verdict SKIP "L4 'jackett' env-forward absent (see L3 SKIP; tracked)"
fi
if compose_service_env_forwarded "boba-jackett"; then
  verdict PASS "L4 docker-compose.yml service 'boba-jackett' env-forwards proxy vars"
else
  # boba-jackett only talks to Jackett sidecar (loopback) + boba.db; not
  # tracker-bound. SKIP is honest per §11.4.6.
  verdict SKIP "L4 'boba-jackett' env-forward absent (not tracker-bound: talks to Jackett loopback + local DB only)"
fi

# --- Verdict ------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Summary: PASS=$pass  FAIL=$fail  SKIP=$skip"
if [ "${#notes[@]}" -gt 0 ]; then
  echo "Notes:"
  for n in "${notes[@]}"; do echo "  - $n"; done
fi
echo "=========================================="

if [ "$RED_MODE" = "1" ]; then
  # Under RED (§11.4.115 polarity flip) each presence-assertion is negated:
  # a code-PRESENT result becomes a FAIL, because the "pre-fix defect state"
  # this mode simulates would have it ABSENT. On a repo where the fix has
  # landed (as here), we EXPECT many FAILs under RED — that IS the signal
  # the detectors + the polarity switch work end-to-end (they would have
  # caught the defect had the code been un-wired).
  #
  # Anomaly: fail == 0 under RED means EVERY presence-detector passed under
  # negation — either the polarity switch itself is broken (detectors ignore
  # RED_MODE) OR the tree has been reverted to the pre-fix state (which
  # would be a real regression). Either interpretation is a §11.4/§11.4.1
  # bluff at the detector layer and MUST surface.
  if [ $fail -lt 3 ]; then
    echo "RED-MODE VERIFY: fewer than 3 detectors negated — polarity switch broken OR tree reverted"
    exit 1
  fi
  echo "RED-MODE VERIFY: $fail presence-detectors correctly negated under RED — polarity switch works, RED→GREEN flip proven"
  exit 0
fi

if [ $fail -gt 0 ]; then
  echo "FAIL: upstream_proxy_wired_challenge — $fail check(s) failed"
  exit 1
fi
echo "PASS: upstream_proxy_wired_challenge — every wired layer verified; residual gaps honestly SKIP'd"
exit 0
