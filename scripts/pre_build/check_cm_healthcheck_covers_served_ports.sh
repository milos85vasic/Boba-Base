#!/usr/bin/env bash
# check_cm_healthcheck_covers_served_ports.sh — CM-HEALTHCHECK-COVERS-SERVED-PORTS
# pre-build gate (§11.4.201 guard-asserts-the-real-condition, §11.4.254
# boot-time invariants / capability matrix), consumed BY REFERENCE from the
# constitution submodule.
#
# Purpose:
#   Assert that every port a compose service SERVES appears in that service's
#   health check. A health check that probes only a subset of the ports its
#   service serves asserts a PROXY signal ("one port answers") in place of the
#   REAL condition ("this service is serving"), so the service can report
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
# WHY THIS FILE IS THIN (§11.4.177 / §11.4.28 / §11.4.74) — BOB-140:
#   The DETECTION ENGINE is universal and now lives in the constitution
#   submodule at
#   `constitution/scripts/gates/cm_healthcheck_covers_served_ports.sh`,
#   with its paired §1.1 mutation test beside it. §11.4.177 mandates shared
#   tooling be consumed BY REFERENCE, never copied — a copy diverges silently.
#   This file is therefore a DELEGATOR: it owns only boba's consumer-side
#   SCOPE DATA (§11.4.35 — which compose file, which served-port manifest,
#   which python interpreters to try) and hands the whole analysis to the
#   shared engine. It contains NO detection logic of its own, so it cannot
#   drift from the engine.
#
#   The two load-bearing properties the local implementation carried are
#   properties of the ENGINE now, asserted by the engine's paired mutation
#   test (fixtures 6/7 and 8 respectively), not by prose here:
#     * ZERO SERVICES CHECKED => FAIL. A quiet zero from a blind instrument is
#       indistinguishable from a clean tree (§11.4.201(6)).
#     * NO PYTHON WITH PyYAML => FAIL, never SKIP (§11.4.201(4)).
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
# Usage:
#   check_cm_healthcheck_covers_served_ports.sh [COMPOSE_FILE] [MANIFEST]
#   check_cm_healthcheck_covers_served_ports.sh --help
#
# Inputs:   optional compose path + manifest path (defaults below). No stdin.
#           Optional env PYTHON_BIN — tried FIRST among the interpreter
#           candidates. It is now subject to the engine's `import yaml` probe
#           rather than trusted on sight (§11.4.201(11): probe the artifact
#           through its real invocation path); a PYTHON_BIN without PyYAML is
#           skipped in favour of the next candidate instead of producing a
#           confusing downstream failure.
# Outputs:  per-service verdict on stdout, the PASS line ALWAYS last (the
#           pre-build wiring reads it with `tail -n1`); findings + FAIL summary
#           on stderr.
# Side-effects: none (read-only; never contacts a network or a container).
# Dependencies: bash, python3 with PyYAML, and the constitution submodule gate.
#
# Scope DATA (consumer-owned, §11.4.35):
#   compose  : docker-compose.yml            (repo root; overridable, arg 1)
#   manifest : config/served_ports.yaml      (repo root; overridable, arg 2)
#   python   : $PYTHON_BIN, .venv/bin/python, python3, python  (in that order)
#
# Verdict:
#   0 — PASS  (>=1 service checked, every served port probed)
#   1 — FAIL  (a finding, zero services checked, a missing input, or no
#              usable YAML parser)
#   2 — ERROR (missing engine, or a usage error passed through from it)
#
# Cross-references: constitution/scripts/gates/cm_healthcheck_covers_served_ports.sh
#   (the engine, and the authoritative documentation of the rule + its schema —
#   run it with --help). Wired as pre-build invariant 44 in
#   scripts/pre_build_verification.sh. Companion guide (§11.4.18):
#   docs/scripts/check_cm_healthcheck_covers_served_ports.md — written
#   2026-08-20 to close the gap this header previously recorded as open.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONST_GATE="${PROJECT_ROOT}/constitution/scripts/gates/cm_healthcheck_covers_served_ports.sh"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,80p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi

if [[ ! -f "$CONST_GATE" ]]; then
    echo "CM-HEALTHCHECK-COVERS-SERVED-PORTS: ERROR — shared gate engine missing: $CONST_GATE" >&2
    echo "  (§11.4.177 — this gate is consumed by reference; run" >&2
    echo "   'git submodule update --init constitution' to restore it)" >&2
    exit 2
fi

# --- Consumer-owned scope DATA only (§11.4.35). No detection logic here. ---
COMPOSE_FILE="${1:-${PROJECT_ROOT}/docker-compose.yml}"
MANIFEST="${2:-${PROJECT_ROOT}/config/served_ports.yaml}"
PY_CANDIDATES="${PYTHON_BIN:-} ${PROJECT_ROOT}/.venv/bin/python python3 python"

exec env HEALTHCHECK_PORTS_PYTHON="$PY_CANDIDATES" \
    bash "$CONST_GATE" --compose "$COMPOSE_FILE" --manifest "$MANIFEST"
