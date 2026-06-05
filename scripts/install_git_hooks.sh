#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$(cd "$(dirname "$0")/.." && pwd)")
HOOK_SOURCE="$REPO_ROOT/scripts/git_hooks"
HOOK_TARGET="$REPO_ROOT/.git/hooks"
BYPASS_AUDIT_TRAIL="$HOOK_TARGET/ATMO_LAST_BYPASS_ATTEMPT"
AUDIT_LOG="$HOOK_TARGET/ATMO_CONSTITUTION_AUDIT_LOG"

if [ ! -d "$HOOK_SOURCE" ]; then
  echo "Creating $HOOK_SOURCE ..."
  mkdir -p "$HOOK_SOURCE"
fi

if [ ! -d "$HOOK_TARGET" ]; then
  echo "Fatal: $HOOK_TARGET does not exist — is this a git repository?"
  exit 1
fi

echo "Installing git hooks from $HOOK_SOURCE to $HOOK_TARGET ..."

installed=0
for hook in pre-commit pre-push commit-msg post-commit; do
  src="$HOOK_SOURCE/$hook"
  dst="$HOOK_TARGET/$hook"

  if [ -f "$src" ]; then
    cp "$src" "$dst"
    chmod +x "$dst"
    echo "  Installed: $hook"
    installed=$((installed + 1))
  else
    echo "  Warning: $src not found — skipping $hook"
  fi
done

if [ ! -f "$BYPASS_AUDIT_TRAIL" ]; then
  touch "$BYPASS_AUDIT_TRAIL"
  chmod 600 "$BYPASS_AUDIT_TRAIL"
  echo "  Created bypass-audit trail: $BYPASS_AUDIT_TRAIL"
fi

if [ ! -f "$AUDIT_LOG" ]; then
  touch "$AUDIT_LOG"
  chmod 600 "$AUDIT_LOG"
  {
    echo "# Constitution §11.4.75 audit log"
    echo "# Timestamp, commit, bypass, mutation"
    echo "# Created: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  } > "$AUDIT_LOG"
  echo "  Created audit log: $AUDIT_LOG"
fi

echo "Done — $installed hook(s) installed. Constitution §11.4.75 enforcement active."
exit 0
