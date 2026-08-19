#!/usr/bin/env bash
# uninstall.sh — clean removal of boba user@1000 watchdog
# Prints su -c commands for operator to run at their terminal.

set -o errexit
set -o nounset
set -o pipefail

cat <<'EOF'
=========================================================================
boba user@1000 watchdog — uninstall commands

Copy/paste at your terminal. su will prompt for the root password ONCE.
Evidence in /var/log/boba-watchdog/ is PRESERVED — remove manually if
you no longer need the captured forensics.
=========================================================================

su -c '
  set -e
  systemctl disable --now boba-user1000-watchdog.service 2>&1 || true
  rm -f /etc/systemd/system/boba-user1000-watchdog.service
  rm -f /usr/local/bin/boba-user1000-watchdog
  systemctl daemon-reload
  echo "--- watchdog uninstalled ---"
  echo "Evidence dir NOT removed: /var/log/boba-watchdog/"
  echo "  remove manually with: rm -rf /var/log/boba-watchdog"
  systemctl status boba-user1000-watchdog.service --no-pager 2>&1 | head -3 || true
'

=========================================================================
EOF
