#!/usr/bin/env bash
# check_cm_healthcheck_covers_served_ports.sh — CM-HEALTHCHECK-COVERS-SERVED-PORTS
# pre-build gate (§11.4.201 guard-asserts-the-real-condition, §11.4.254
# boot-time invariants / capability matrix).
#
# Purpose:
#   Assert that every port a compose service SERVES appears in that service's
#   health check. A health check that probes only a subset of the ports its
#   service publishes asserts a PROXY signal ("one port answers") in place of
#   the REAL condition ("this service is serving"), so the service can report
#   healthy indefinitely while its primary capability is dead.
#
# FORENSIC ANCHOR (BOB-138, measured 2026-08-20):
#   The `download-proxy` service serves 7186 and 7187 from ONE process, but its
#   health check probed only 7186. Live measurement on a container reporting
#   "Up 4 hours (healthy)":
#       curl --max-time 6 localhost:7186/  -> HTTP 200 in 0.096s
#       curl --max-time 6 localhost:7187/  -> HTTP 000 after 6.0s
#   The merge service — the product's primary capability — had been dead for
#   roughly two hours and no signal anywhere in the stack could see it.
#
# WHY THE SERVED SET IS DECLARED, NOT DERIVED (§11.4.6 / §11.4.201(1)):
#   These services use `network_mode: host`, so there is no `ports:` mapping to
#   derive from, and the env vars mix served ports (PROXY_PORT) with upstream
#   dependency ports (QBITTORRENT_PORT) under one indistinguishable naming
#   shape. Sweeping `*_PORT` would demand a health check for a port the service
#   does not serve — a false-positive refusal, which §11.4.201(1) forbids just
#   as firmly as a false pass. The served set therefore comes from consumer-owned
#   DATA at config/served_ports.yaml (§11.4.35).
#
# REUSABILITY (§11.4.177 / §11.4.28 — HONEST STATUS):
#   The detection logic below carries no boba literal: both the compose file and
#   the manifest are inputs. It is NOT yet upstreamed into
#   `constitution/scripts/gates/` because a concurrent agent is editing that
#   directory and a two-writer race there risks losing work. Upstreaming is
#   tracked as a work item, NOT silently skipped (§11.4.197).
#
# Usage:
#   check_cm_healthcheck_covers_served_ports.sh [COMPOSE_FILE] [MANIFEST]
#   check_cm_healthcheck_covers_served_ports.sh --help
#
# Inputs:   optional compose path + manifest path (defaults below). No stdin.
# Outputs:  per-service verdict on stdout; findings + FAIL summary on stderr.
# Side-effects: none (read-only; never contacts a network or a container).
# Dependencies: bash, python3 with PyYAML.
# Cross-references: docs/scripts/check_cm_healthcheck_covers_served_ports.md
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,50p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi

COMPOSE_FILE="${1:-${PROJECT_ROOT}/docker-compose.yml}"
MANIFEST="${2:-${PROJECT_ROOT}/config/served_ports.yaml}"

PY="${PYTHON_BIN:-}"
if [[ -z "$PY" ]]; then
    for cand in "${PROJECT_ROOT}/.venv/bin/python" python3; do
        if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import yaml' >/dev/null 2>&1; then
            PY="$cand"; break
        fi
    done
fi
# §11.4.201(4): an unresolvable signal takes the conservative-safe outcome and
# says so honestly. A missing YAML parser means the gate CANNOT SEE — that is
# never reported as a pass.
if [[ -z "$PY" ]]; then
    echo "CM-HEALTHCHECK-COVERS-SERVED-PORTS: FAIL — no python3 with PyYAML available;" >&2
    echo "  the gate cannot parse the compose file, so it cannot assert anything." >&2
    echo "  This is a BLIND gate, not a clean tree (§11.4.201(6))." >&2
    exit 1
fi

exec "$PY" - "$COMPOSE_FILE" "$MANIFEST" <<'PYEOF'
import sys, re, pathlib
try:
    import yaml
except ImportError:
    print("CM-HEALTHCHECK-COVERS-SERVED-PORTS: FAIL — PyYAML missing (blind gate)", file=sys.stderr)
    sys.exit(1)

compose_path, manifest_path = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
for p in (compose_path, manifest_path):
    if not p.is_file():
        print(f"CM-HEALTHCHECK-COVERS-SERVED-PORTS: FAIL — missing input: {p}", file=sys.stderr)
        sys.exit(1)

compose = yaml.safe_load(compose_path.read_text()) or {}
manifest = yaml.safe_load(manifest_path.read_text()) or {}
services = compose.get("services") or {}
declared = (manifest.get("services") or {})

findings, checked = [], 0

for name, decl in declared.items():
    serves = [int(p) for p in (decl.get("serves") or [])]
    if not serves:
        continue
    svc = services.get(name)
    if svc is None:
        findings.append(f"{name}: declared in the manifest but ABSENT from {compose_path.name} "
                        f"(stale manifest entry — remove it or restore the service)")
        continue

    hc = svc.get("healthcheck") or {}
    test = hc.get("test")
    if not test:
        findings.append(f"{name}: serves {serves} but declares NO healthcheck at all")
        continue
    blob = " ".join(test) if isinstance(test, list) else str(test)

    # Match the port as a whole number so 7187 never matches inside 71870.
    missing = [p for p in serves if not re.search(rf"(?<!\d){p}(?!\d)", blob)]
    checked += 1
    if missing:
        findings.append(
            f"{name}: serves {serves} but its healthcheck probes none of {missing}\n"
            f"      healthcheck: {blob}\n"
            f"      -> a dead port in {missing} reports HEALTHY forever (§11.4.201 proxy signal)"
        )
    else:
        print(f"  ok  {name}: healthcheck covers all served ports {serves}")

# A service that publishes ports but is absent from the manifest is UNDECLARED,
# not exempt — silence is never an exemption (§11.4.201(6)).
for name, svc in services.items():
    if name in declared:
        continue
    if svc.get("healthcheck") or svc.get("ports"):
        findings.append(f"{name}: has a healthcheck and/or ports but is UNDECLARED in "
                        f"{manifest_path.name} — add its served ports (silence is not an exemption)")

if findings:
    print("CM-HEALTHCHECK-COVERS-SERVED-PORTS: FAIL", file=sys.stderr)
    for f in findings:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)

if checked == 0:
    # §11.4.201(6): zero services checked means the gate saw nothing. A quiet
    # zero from a blind instrument is indistinguishable from a clean tree.
    print("CM-HEALTHCHECK-COVERS-SERVED-PORTS: FAIL — checked 0 services; the gate is "
          "blind (empty manifest or no matching services), not clean", file=sys.stderr)
    sys.exit(1)

print(f"CM-HEALTHCHECK-COVERS-SERVED-PORTS: PASS ({checked} services verified)")
PYEOF
