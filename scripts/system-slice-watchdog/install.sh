#!/usr/bin/env bash
# install.sh — install the boba user@1000 watchdog into system.slice
#
# Runs as the current user; PRINTS the su -c commands you need to execute at
# your terminal (§6.U + §11.4.109 — no agent invokes su/sudo on your behalf).
#
# What gets installed:
#   /usr/local/bin/boba-user1000-watchdog         (the monitor script)
#   /etc/systemd/system/boba-user1000-watchdog.service
#   /var/log/boba-watchdog/                        (evidence root, chmod 700)
#
# Uninstall: see uninstall.sh

set -o errexit
set -o nounset
set -o pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly WATCHDOG_SRC="$SCRIPT_DIR/user1000-watchdog.sh"
readonly SERVICE_SRC="$SCRIPT_DIR/boba-user1000-watchdog.service"

# Pre-flight: source files must exist
for f in "$WATCHDOG_SRC" "$SERVICE_SRC"; do
    if [[ ! -f "$f" ]]; then
        echo "ERROR: missing $f" >&2
        exit 1
    fi
done

cat <<EOF
=========================================================================
boba user@1000 out-of-scope watchdog — install commands

Copy/paste the block below at your terminal. su will prompt for the root
password ONCE. No agent tool invokes su/sudo on your behalf per §6.U +
§11.4.109 — you control this action.

Source files present:
  script:  $WATCHDOG_SRC
  service: $SERVICE_SRC

Install commands:
=========================================================================

su -c '
  set -e
  echo "--- installing watchdog script ---"
  install -m 0755 -o root -g root "$WATCHDOG_SRC" /usr/local/bin/boba-user1000-watchdog
  echo "  installed: /usr/local/bin/boba-user1000-watchdog"

  echo "--- installing systemd unit ---"
  install -m 0644 -o root -g root "$SERVICE_SRC" /etc/systemd/system/boba-user1000-watchdog.service
  echo "  installed: /etc/systemd/system/boba-user1000-watchdog.service"

  echo "--- creating evidence root ---"
  mkdir -p /var/log/boba-watchdog
  chmod 700 /var/log/boba-watchdog
  chown root:root /var/log/boba-watchdog
  echo "  ready:     /var/log/boba-watchdog/"

  echo "--- systemd daemon-reload + enable + start ---"
  systemctl daemon-reload
  systemctl enable boba-user1000-watchdog.service
  systemctl start boba-user1000-watchdog.service
  sleep 1
  systemctl status boba-user1000-watchdog.service --no-pager | head -15
  echo
  echo "--- verify slice is system.slice (NOT user.slice) ---"
  systemctl show boba-user1000-watchdog.service -p Slice -p ActiveState
'

=========================================================================
After running: check "systemctl status boba-user1000-watchdog" reports:
  - ActiveState=active
  - Slice=system.slice  (NOT user.slice — this is the whole point)
  - Sub=running
=========================================================================
EOF
