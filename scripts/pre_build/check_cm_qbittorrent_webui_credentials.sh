#!/usr/bin/env bash
# check_cm_qbittorrent_webui_credentials.sh — CM-QBITTORRENT-WEBUI-CREDENTIALS
#
# INVARIANT: the qBittorrent WebUI must be reachable with the documented
# admin/admin credentials, AND that must be REAL authentication — not an
# auth bypass that accepts anything.
#
# RETROACTIVE CATCHER for the 2026-09-01 login outage. Four independent
# defects had to line up, and no gate could see any of them:
#
#   1. The credentials were authored into config/qBittorrent/config/qBittorrent.conf,
#      but the linuxserver image reads /config/qBittorrent/qBittorrent.conf and
#      launches qbittorrent-nox with NO --profile flag. The credential file was
#      read by nothing.
#   2. docker-compose.yml set WEBUI_USERNAME / WEBUI_PASSWORD. The image
#      implements neither (control-needle-proven: the same grep over the image
#      finds WEBUI_PORT and finds nothing for those two). They are inert.
#   3. start.sh's _ensure_webui_credentials was grep-then-sed, i.e.
#      REPLACE-ONLY, so on a config lacking the keys it wrote nothing and
#      still returned 0.
#   4. With no WebUI\Password_PBKDF2 in the live config, qBittorrent 5.x mints
#      a random temporary password on every boot and logs it to stdout, so
#      admin/admin could never work.
#
# ...and the "fix" for (3) initially shipped a SECURITY REGRESSION: enforcing
# WebUI\LocalHostAuth=false + AuthSubnetWhitelistEnabled=true (whitelist =
# loopback + all RFC1918) does not relax the brute-force ban, it DISABLES
# AUTHENTICATION for those subnets. Measured with the bypass on: a WRONG
# password returned HTTP 204 (accepted). Hence invariant 3 below.
#
# SCOPE IS DATA (§11.4.35): the live config path is the one the image reads.
#
# BLOCKING: this is availability + auth integrity of the primary user-facing
# capability (§11.4.239 critical-invariant work class). It deliberately FAILs —
# never SKIPs — when it cannot read the config, because a quiet zero from a
# blind instrument is not a clean tree (§11.4.201(6)/(7)(b)).
#
# Exit: 0 all invariants hold | 1 an invariant is violated | 2 harness error.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${1:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

LIVE_CONF="$REPO_ROOT/config/qBittorrent/qBittorrent.conf"
START_SH="$REPO_ROOT/start.sh"
COMPOSE="$REPO_ROOT/docker-compose.yml"

fails=0
note() { echo "  $*"; }
bad()  { echo "  VIOLATION: $*"; fails=$((fails + 1)); }

# --- CONTROL NEEDLE (§11.4.201(7)(b)) -------------------------------------
# Prove the reader can see a WebUI key before trusting any "key absent"
# reading. A blind grep and a genuinely-missing key both return a quiet zero.
NEEDLE_TMP="$(mktemp)"
printf 'WebUI\\Username=admin\n' > "$NEEDLE_TMP"
if ! grep -q '^WebUI\\Username=' "$NEEDLE_TMP"; then
    echo "HARNESS ERROR: control needle not seen — reader is blind, refusing to report" >&2
    exit 2
fi

# --- Invariant 1: start.sh must write credentials INSERT-OR-REPLACE -------
if [[ ! -f "$START_SH" ]]; then
    echo "HARNESS ERROR: start.sh not found at $START_SH" >&2
    exit 2
fi

# CODE-ONLY VIEW (§11.4.201(7)(a)). Every start.sh pattern below is matched
# against a comment-stripped copy. The first version of this gate grepped the
# raw file, so writing an ACCURATE comment describing the removed auth bypass
# made the gate report a violation — a detector that punishes truthful
# documentation of the defect it guards.
START_CODE="$(mktemp)"
trap 'rm -f "$NEEDLE_TMP" "$START_CODE"' EXIT
sed 's/[[:space:]]*#.*$//' "$START_SH" > "$START_CODE"

# Control needle for the code-only reader: the real calls must still be visible
# after comment-stripping, or every "clean" reading below is a false null.
if ! grep -qE '_enforce_config_line .*LocalHostAuth' "$START_CODE"; then
    echo "HARNESS ERROR: code-only reader sees no LocalHostAuth call at all — refusing to report" >&2
    exit 2
fi
# M3: accept EITHER quote style — the single-quoted form previously evaded this.
if grep -qE "grep -q ['\"]\\^WebUI\\\\+(Username|Password_PBKDF2)=" "$START_CODE"; then
    bad "start.sh guards a credential write behind a grep (replace-only). On a config lacking the key nothing is written and admin/admin cannot work."
else
    note "OK: start.sh does not gate credential writes behind a presence grep"
fi
# NOTE: start.sh writes the key as "WebUI\\\\Username" (four literal
# backslashes, because the value crosses bash -> sed). Match loosely on the
# backslash run rather than a fixed count — an exact-count pattern silently
# matched nothing here and produced a false violation (§11.4.201(7)(c)).
if grep -qE '_enforce_config_line .*WebUI\\+Username' "$START_SH" \
   && grep -qE '_enforce_config_line .*WebUI\\+Password_PBKDF2' "$START_SH"; then
    note "OK: username and password hash are written insert-or-replace"
else
    bad "start.sh does not write WebUI\\Username and WebUI\\Password_PBKDF2 via _enforce_config_line (insert-or-replace)"
fi

# --- Invariant 2: no reliance on the inert image env vars -----------------
if [[ -f "$COMPOSE" ]]; then
    if grep -qE '^\s*-\s*WEBUI_(USERNAME|PASSWORD)=' "$COMPOSE"; then
        bad "docker-compose.yml sets WEBUI_USERNAME/WEBUI_PASSWORD. lscr.io/linuxserver/qbittorrent implements NEITHER — they are inert and create a false belief that credentials are configured."
    else
        note "OK: compose does not rely on the inert WEBUI_USERNAME/WEBUI_PASSWORD vars"
    fi
fi

# --- Invariant 3: authentication must NOT be bypassed ---------------------
# CARRIER GUARD (§11.4.201(7)(a)): match the CODE shape only, never a mention.
# The first version of this gate grepped `LocalHostAuth=false` anywhere in
# start.sh, so writing an ACCURATE comment describing the removed bypass made
# the gate report a violation — a detector that punishes truthful documentation
# of the very defect it guards. Comment lines are stripped before matching, and
# the pattern now requires the actual _enforce_config_line call shape.
if grep -qE '_enforce_config_line[^#]*LocalHostAuth[^#]*"false"' "$START_CODE"; then
    bad "start.sh sets WebUI\\LocalHostAuth=false — this DISABLES authentication for localhost, it does not relax the ban. Measured: a wrong password then returns HTTP 204 (accepted)."
else
    note "OK: localhost authentication is not disabled"
fi
if grep -qE '_enforce_config_line[^#]*AuthSubnetWhitelistEnabled[^#]*"true"' "$START_CODE"; then
    bad "start.sh enables WebUI\\AuthSubnetWhitelistEnabled — combined with an RFC1918 whitelist this disables authentication across the LAN."
else
    note "OK: subnet auth-whitelist is not enabled"
fi
# The legitimate need (test-suite login probes must not trip an IP ban) must
# still be met, or this gate would push the project back into the ban problem.
if grep -q 'MaxAuthenticationFailCount' "$START_SH"; then
    note "OK: brute-force lockout still relaxed via MaxAuthenticationFailCount (check kept, lockout loosened)"
else
    bad "MaxAuthenticationFailCount is no longer enforced — repeated login probes may trip qBittorrent's IP ban"
fi

# --- Invariant 4: if a live config exists, it must carry the credentials ---
# Honest boundary (§11.4.69): on a fresh clone the live config does not exist
# yet — that is artifact_not_yet_built, not a violation. start.sh creates it.
if [[ -f "$LIVE_CONF" ]]; then
    # M4: distinguish "cannot read" from "key absent". Reporting an unreadable
    # file as missing-credentials is a wrong diagnosis, and the header promises
    # this gate FAILs loudly rather than guessing when it cannot read.
    if [[ ! -r "$LIVE_CONF" ]]; then
        echo "HARNESS ERROR: live config exists but is not readable: $LIVE_CONF" >&2
        exit 2
    fi
    if grep -q '^WebUI\\Username=admin$' "$LIVE_CONF"; then
        note "OK: live config carries WebUI\\Username=admin"
    else
        bad "live config $LIVE_CONF has no WebUI\\Username=admin — qBittorrent will mint a random temporary password on boot"
    fi
    # qBittorrent rewrites this key in QUOTED form (="@ByteArray(...)") when it
    # persists its config on shutdown, so the quote is optional here. An
    # unquoted-only pattern produced a false violation against a working stack.
    if grep -qE '^WebUI\\Password_PBKDF2="?@ByteArray\(' "$LIVE_CONF"; then
        note "OK: live config carries a WebUI\\Password_PBKDF2 hash"
    else
        bad "live config $LIVE_CONF has no WebUI\\Password_PBKDF2 — admin/admin cannot work"
    fi
    if grep -qE '^WebUI\\(LocalHostAuth=false|AuthSubnetWhitelistEnabled=true)' "$LIVE_CONF"; then
        bad "live config disables WebUI authentication (LocalHostAuth=false or AuthSubnetWhitelistEnabled=true)"
    else
        note "OK: live config does not bypass authentication"
    fi
else
    note "SKIP-with-reason: live config not present yet (artifact_not_yet_built) — start.sh creates it on first boot"
fi

echo
if [[ "$fails" -gt 0 ]]; then
    echo "CM-QBITTORRENT-WEBUI-CREDENTIALS: FAIL ($fails violation(s))"
    exit 1
fi
echo "CM-QBITTORRENT-WEBUI-CREDENTIALS: PASS (credentials enforced insert-or-replace; authentication not bypassed)"
exit 0
