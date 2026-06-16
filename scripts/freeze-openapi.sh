#!/usr/bin/env bash
# scripts/freeze-openapi.sh — export the FastAPI /openapi.json into
# docs/api/openapi.json so CI (or a contract test) can diff drift.
#
# Non-interactive, never uses sudo.

set -euo pipefail

print_info()    { printf '\033[0;34m[INFO]\033[0m %s\n' "$*"; }
print_success() { printf '\033[0;32m[ OK ]\033[0m %s\n' "$*"; }
print_error()   { printf '\033[0;31m[FAIL]\033[0m %s\n' "$*" >&2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

dest="docs/api/openapi.json"
mkdir -p "$(dirname "$dest")"

export PYTHONPATH="$REPO_ROOT/download-proxy/src:${PYTHONPATH:-}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://localhost}"

print_info "exporting OpenAPI schema"
# Prefer the project venv interpreter: the app source uses py3.10+ syntax
# (e.g. `str | None`), which the host's bare `python3` (3.9) cannot import.
PY_BIN="$REPO_ROOT/.venv/bin/python"; [[ -x "$PY_BIN" ]] || PY_BIN="python3"
"$PY_BIN" - "$dest" <<'PY'
import json, os, sys
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost")
from api import app
schema = app.openapi()
target = sys.argv[1]
with open(target, "w", encoding="utf-8") as fh:
    json.dump(schema, fh, indent=2, sort_keys=True)
    fh.write("\n")
print(f"wrote {target}")
PY

print_success "frozen at $dest"
