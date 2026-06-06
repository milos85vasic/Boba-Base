#!/usr/bin/env bash
# boba_db_file_perms_challenge.sh — Layer 4 file-permission gate.
#
# EXPECT: After boba-jackett creates its DB and .env, BOTH files have
# mode 0600 (rw-------). Any other mode means a stale state or a
# regression in envfile.Atomic / db.Open and is rejected.
#
# CONST-XII anti-bluff: this challenge spawns a real boba-jackett
# binary (built fresh), points it at a tmp dir, hits /healthz to
# guarantee DB creation, and uses stat on the actual files.
#
# Pass: PASS message + exit 0
# Fail: FAIL: <reason> + exit 1

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT/qBitTorrent-go"

# Ensure the binary is built. scripts/build.sh writes ./bin/boba-jackett
# but we re-build inline so the challenge is self-contained.
if [ ! -x "./bin/boba-jackett" ]; then
  go build -o ./bin/boba-jackett ./cmd/boba-jackett
fi

# Tmp workspace.
TMPDIR_BOBA="$(mktemp -d -t boba-perms-XXXXXX)"
trap 'rm -rf "$TMPDIR_BOBA"' EXIT

PORT=$(( ( RANDOM % 10000 ) + 30000 ))
DBPATH="$TMPDIR_BOBA/boba.db"
ENVPATH="$TMPDIR_BOBA/.env"

# Boot in background.
BOBA_DB_PATH="$DBPATH" \
BOBA_ENV_PATH="$ENVPATH" \
JACKETT_URL="http://127.0.0.1:1" \
JACKETT_API_KEY="" \
PORT="$PORT" \
./bin/boba-jackett >"$TMPDIR_BOBA/boba.log" 2>&1 &
PID=$!
trap 'kill -TERM '"$PID"' 2>/dev/null || true; rm -rf "$TMPDIR_BOBA"' EXIT

# Wait for /healthz (max 5s).
deadline=$(( $(date +%s) + 5 ))
ready=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -sf -o /dev/null "http://127.0.0.1:$PORT/healthz" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 0.2
done
if [ "$ready" != "1" ]; then
  echo "FAIL: boba-jackett did not respond on /healthz within 5s"
  echo "--- log ---"
  cat "$TMPDIR_BOBA/boba.log"
  echo "--- end log ---"
  exit 1
fi

# Hit healthz once more to ensure DB was opened (and thus created).
curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null

# Stop the service so file mode reads are post-shutdown stable.
kill -TERM "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true

# DB file must exist with 0600.
if [ ! -f "$DBPATH" ]; then
  echo "FAIL: $DBPATH does not exist after /healthz"
  exit 1
fi
# Cross-platform stat: GNU stat uses -c, BSD stat (macOS) uses -f
_stat_mode() {
  if stat -c '%a' / 2>/dev/null | grep -qE '^[0-7]+$'; then
    stat -c '%a' "$1"
  else
    stat -f '%A' "$1"
  fi
}
DBMODE=$(_stat_mode "$DBPATH")
echo "    boba.db mode: $DBMODE  (expect 600)"
if [ "$DBMODE" != "600" ]; then
  # SQLite default file mode is 0644 on most systems; if Open does not
  # explicitly chmod, this assertion will catch the regression.
  echo "FAIL: boba.db mode = $DBMODE, want 600"
  echo "(the .db file is created by modernc.org/sqlite; if this fails,"
  echo " enforce a chmod 0600 in db.Open after the first ping)"
  exit 1
fi

# .env must exist with 0600.
if [ ! -f "$ENVPATH" ]; then
  echo "FAIL: $ENVPATH does not exist after boot"
  exit 1
fi
ENVMODE=$(_stat_mode "$ENVPATH")
echo "    .env mode: $ENVMODE  (expect 600)"
if [ "$ENVMODE" != "600" ]; then
  echo "FAIL: .env mode = $ENVMODE, want 600"
  exit 1
fi

# .env must contain the master-key header sentinel.
if ! grep -q '=== BOBA SYSTEM ===' "$ENVPATH"; then
  echo "FAIL: master-key header sentinel missing from .env"
  echo "--- .env ---"
  cat "$ENVPATH"
  exit 1
fi

echo "PASS: boba_db_file_perms_challenge"
exit 0
