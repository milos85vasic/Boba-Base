# scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh — CM-HEALTHCHECK-COVERS-SERVED-PORTS

**Revision:** 1
**Last modified:** 2026-08-20T17:30:00Z
**Status:** active
**Item:** BOB-138 (defect fixed) / BOB-140 (engine upstreamed per §11.4.177)

## Overview

Asserts that every port a compose service SERVES appears in that service's
health check. A check probing only a subset asserts a PROXY signal ("one port
answers") in place of the REAL condition ("this service is serving"), so a
service can report healthy indefinitely while its primary capability is dead
(§11.4.201).

Wired as **pre-build invariant 44**, BLOCKING.

## Why it exists — the forensic anchor (BOB-138, measured 2026-08-20)

The `download-proxy` service serves 7186 and 7187 from ONE process, but its
health check probed only 7186. On a container reporting `Up 4 hours (healthy)`:

```
curl --max-time 6 http://localhost:7186/       -> HTTP 200 in 0.096s
curl --max-time 6 http://localhost:7187/health -> HTTP 000 after 6.004s
```

The merge search service — the product's primary capability — had been dead for
roughly two hours, and nothing in the stack could observe it. An operator, a
restart policy, and any `depends_on: service_healthy` all read "healthy".

## Prerequisites

- `bash`
- `python3` with **PyYAML**. If no interpreter with PyYAML is reachable the gate
  **FAILs** — it does not SKIP. A gate that cannot parse cannot assert, and a
  quiet zero from a blind instrument is indistinguishable from a clean tree
  (§11.4.201(6)).
- The constitution submodule checked out (the detection engine lives there).

## Usage

```bash
bash scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh
bash scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh --help
bash scripts/pre_build/check_cm_healthcheck_covers_served_ports.sh COMPOSE MANIFEST
```

Exit codes: `0` PASS · `1` FAIL · `2` engine missing or engine usage error.
Invariant 44 treats any non-zero (other than a timeout) as FAIL, so a missing
submodule blocks rather than silently passes.

## Internal behaviour

This file is a **thin delegator** (§11.4.177 / §11.4.28): it holds only boba's
scope DATA and `exec`s the shared engine at
`constitution/scripts/gates/cm_healthcheck_covers_served_ports.sh`. No detection
logic lives here, so it cannot drift from the engine. The engine carries no
project literal; both the compose file and the manifest are inputs.

The engine reports a finding when a service:

- serves a declared port its health check does not probe;
- serves ports but declares no health check at all;
- is declared in the manifest but absent from the compose file (stale entry);
- publishes ports or declares a health check but is **UNDECLARED** in the
  manifest — silence is not an exemption.

Ports match as whole numbers, so 7187 never matches inside 71870 or 17187.

## The served-port manifest is DATA, and why it is declared not derived

`config/served_ports.yaml` (§11.4.35) lists, per compose service, the ports it
serves. These services use `network_mode: host`, so there is no `ports:` mapping
to derive from, and the environment mixes two indistinguishable meanings:

```
PROXY_PORT=7186          <- a port this service SERVES
MERGE_SERVICE_PORT=7187  <- a port this service SERVES
QBITTORRENT_PORT=7185    <- a port this service CONNECTS TO
```

A gate sweeping `*_PORT` would demand a health check for a port the service does
not serve — a false-positive refusal, which §11.4.201(1) forbids exactly as
firmly as a false pass.

**This trap is not hypothetical.** The manifest's first version declared
`qbittorrent-proxy-go: serves [7186, 7187, 7188]`, taken from CLAUDE.md prose.
The Dockerfile runs one binary binding 7187, so the gate failed a service whose
health check was already correct. The manifest is now derived from source, and
the doc was corrected (BOB-141).

## Edge cases

- **Zero services checked** → FAIL, not PASS. The gate refuses to call a blind
  run clean.
- **Both `test:` spellings** (list form and string form) are handled.
- **Compose parsing limits** (pre-existing, unchanged): a single compose file,
  with no `extends`, overlay or profile resolution. Not currently exercised by
  boba, but a consumer using overlays should know the manifest is checked against
  the base file only.

## Related

- Engine: `constitution/scripts/gates/cm_healthcheck_covers_served_ports.sh`
- Paired §1.1 mutation test: `constitution/scripts/gates/cm_healthcheck_covers_served_ports_mutation_test.sh` (13 fixtures: 11 FAIL-on-mutation, 2 PASS-on-clean negative controls)
- Data: `config/served_ports.yaml`
- Evidence: `docs/qa/BOB-138/closure-evidence.md`, `docs/qa/BOB-140/closure-evidence.md`
- Wiring: `scripts/pre_build_verification.sh` invariant 44

**Last verified:** 2026-08-20 — delegator `PASS (5 services verified)`, mutation
test `META PASS` 13/13, both fail-closed properties confirmed through the
delegator.
