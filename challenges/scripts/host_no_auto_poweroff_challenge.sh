#!/bin/bash
# host_no_auto_poweroff_challenge.sh — CONST-033 / CONST-034 reproduction guard.
#
# Asserts the host this challenge runs on cannot be suspended,
# hibernated, hybrid-slept, OR powered off by any user, session, DE,
# greeter, or cron job. Defence in depth: target masking + sleep.conf
# override + logind IdleAction / HandlePowerKey override.
#
# Self-contained — no framework.sh dependency. Drop-in for any project's
# challenges/scripts/ directory.
#
# Pass criteria:
#   1. systemctl is-enabled sleep.target / suspend.target /
#      hibernate.target / hybrid-sleep.target ALL == "masked"
#   2. AllowSuspend=no found in /etc/systemd/sleep.conf or any
#      /etc/systemd/sleep.conf.d/*.conf drop-in
#   3. logind IdleAction == "ignore" AND HandlePowerKey == "ignore"
#   4. journalctl shows no "The system will power off now" events since
#      the fix marker (/etc/systemd/logind.conf.d/00-no-idle-suspend.conf)
#      was written
#
# Exit:
#   0 = all PASS
#   1 = one or more FAIL
#   2 = invocation error

set -uo pipefail

# Platform guard: these checks require systemd/Linux
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "=== host_no_auto_poweroff_challenge ==="
  echo "SKIP: systemd/Linux required (uname=$(uname -s))"
  exit 0
fi

PASS_COUNT=0
FAIL_COUNT=0
FAIL_DETAILS=()

assert_pass() { echo "PASS: $*"; PASS_COUNT=$((PASS_COUNT + 1)); }
assert_fail() { echo "FAIL: $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); FAIL_DETAILS+=("$*"); }

echo "=== host_no_auto_poweroff_challenge ==="
echo

# --- Test 1: sleep targets masked ---
echo "[1/4] sleep / suspend / hibernate / hybrid-sleep targets masked?"
unmasked=()
for tgt in sleep.target suspend.target hibernate.target hybrid-sleep.target; do
  state=$( { systemctl is-enabled "$tgt" 2>/dev/null || true; } | head -n1 | tr -d '[:space:]')
  [[ -z "$state" ]] && state="unknown"
  echo "    $tgt: $state"
  [[ "$state" != "masked" ]] && unmasked+=( "$tgt($state)" )
done
if [[ ${#unmasked[@]} -eq 0 ]]; then
  assert_pass "all 4 sleep targets masked"
else
  assert_fail "unmasked targets: ${unmasked[*]}"
fi

# --- Test 2: sleep.conf forbids suspend ---
echo "[2/4] AllowSuspend=no in sleep.conf or drop-in?"
if grep -shqE "^AllowSuspend[[:space:]]*=[[:space:]]*no" \
     /etc/systemd/sleep.conf /etc/systemd/sleep.conf.d/*.conf 2>/dev/null; then
  assert_pass "AllowSuspend=no present"
else
  assert_fail "AllowSuspend=no NOT found in sleep.conf or any drop-in"
fi

# --- Test 3: logind IdleAction=ignore + HandlePowerKey=ignore ---
echo "[3/4] logind IdleAction and HandlePowerKey safe?"
idle_action=$( { grep -shE "^IdleAction[[:space:]]*=" \
  /etc/systemd/logind.conf /etc/systemd/logind.conf.d/*.conf 2>/dev/null || true; } \
  | tail -n1 | cut -d= -f2 | tr -d '[:space:]')
idle_action=${idle_action:-"<unset>"}

power_key=$( { grep -shE "^HandlePowerKey[[:space:]]*=" \
  /etc/systemd/logind.conf /etc/systemd/logind.conf.d/*.conf 2>/dev/null || true; } \
  | tail -n1 | cut -d= -f2 | tr -d '[:space:]')
power_key=${power_key:-"<unset>"}

echo "    logind IdleAction: $idle_action"
echo "    logind HandlePowerKey: $power_key"

if [[ "$idle_action" == "ignore" ]] || [[ "$idle_action" == "<unset>" ]]; then
  assert_pass "IdleAction=$idle_action (safe)"
else
  assert_fail "IdleAction=$idle_action — could trigger suspend/poweroff"
fi

if [[ "$power_key" == "ignore" ]]; then
  assert_pass "HandlePowerKey=ignore (safe)"
else
  assert_fail "HandlePowerKey=$power_key — physical button can power off the host"
fi

# --- Test 4: no poweroff events since fix ---
echo "[4/4] journal: any 'will power off' broadcast since fix?"
fix_marker="/etc/systemd/logind.conf.d/00-no-idle-suspend.conf"
if [[ -f "$fix_marker" ]]; then
  fix_iso=$(date -d "@$(stat -c %Y "$fix_marker")" -Iseconds 2>/dev/null \
    || stat -c %y "$fix_marker" | head -c 19 | tr ' ' 'T')
  echo "    fix applied at: $fix_iso"
  count=$( { journalctl --since "$fix_iso" 2>/dev/null || true; } \
    | { grep -cE "The system will (suspend|power off) now" || true; })
  count=${count:-0}
  echo "    'will suspend/power off' broadcasts since fix: $count"
  if [[ "$count" -eq 0 ]]; then
    assert_pass "no suspend/poweroff events since fix at $fix_iso"
  else
    assert_fail "$count suspend/poweroff events since fix — guarding didn't take"
  fi
else
  assert_fail "fix marker $fix_marker missing — run install-host-power-guard.sh"
fi

echo
echo "=== summary: $PASS_COUNT pass, $FAIL_COUNT fail ==="
[[ $FAIL_COUNT -eq 0 ]] && exit 0 || exit 1
