#!/usr/bin/env bash
# test_check_cm_ownership_invariants.sh — §1.1 paired-mutation meta-test for
# scripts/pre_build/check_cm_ownership_invariants.sh (CM-OWNERSHIP-INVARIANTS,
# FR-011 of specs/002-user-owned-downloads/).
#
# TDD (§11.4.43/§11.4.115): this meta-test proves the gate is not a bluff by
# exercising it against hermetic fixtures with KNOWN outcomes. §11.4.201(1) is
# load-bearing in BOTH directions here — a gate that refuses a healthy tree is
# exactly as broken as one that passes a reverted one — so the golden-FALSE
# set is as large as the golden-bad set.
#
#   REVERT MUTATION (the canonical §11.4.115(F) mutation: the fix's own
#   revert, applied to a COPY of the real docker-compose.yml — the real file
#   is NEVER written, because other work streams edit it concurrently and the
#   pre-build NO-TRACE assertion forbids a test from touching tracked files):
#     revert-puid     -> exit 1, finding names the service and PUID=1000
#     revert-pgid     -> exit 1, finding names the service and PGID=1000
#
#   GOLDEN-BAD (synthetic, one defect class each):
#     no-puid         -> exit 1 (linuxserver service declaring NO PUID at all:
#                        the image's `abc` (911) default -> host 101910, the
#                        same defect reached by omission)
#     keep-id         -> exit 1 (`userns_mode: keep-id` reintroduced)
#     keep-id-uid     -> exit 1 (the `keep-id:uid=...,gid=...` spelling)
#     env-mapping     -> exit 1 (mapping-form `environment:` with PUID: 1000 —
#                        proves the parse is structural, not list-shaped luck)
#     puid-passthru   -> exit 1 (bare `- PUID` pass-through: present but NOT
#                        statically resolvable, so not provably 0)
#     zero-services   -> exit 1 (blind parse must not read as a clean tree)
#     no-linuxserver  -> exit 1 (services parsed but none linuxserver: the
#                        PUID clause asserted nothing)
#     owned-missing   -> exit 1 (ownership scope file absent)
#     owned-empty     -> exit 1 (parses to None — the FALSE-NULL shape)
#     owned-no-paths  -> exit 1 (`paths:` empty)
#
#   GOLDEN-FALSE (the gate MUST NOT fire — false-positive guards):
#     golden-good     -> exit 0 (copy of the real compose + owned_paths)
#     no-puid-ok      -> exit 0 (NON-linuxserver service with no PUID at all —
#                        download-proxy's real shape, explicitly required by
#                        FR-011: it runs as root and was measured to write as
#                        host uid 1000)
#     carrier-comment -> exit 0 (comments MENTIONING `userns_mode: keep-id`
#                        and `PUID=1000`; a substring scan would fire, a
#                        structural parse must not — BOB-138/BOB-141 class)
#     substring-image -> exit 0 (`acme/mylinuxserverfork` — repository name
#                        CONTAINS "linuxserver" but the namespace is not it)
#     registry-port   -> exit 0 (`reg.example:5000/linuxserver/x:1` — the
#                        registry port colon must not break tag stripping,
#                        and the service is correctly held to PUID=0)
#     real-tree       -> exit 0 (the gate with no arguments, against the
#                        actual checkout)
#
# A gate that PASSes any golden-bad, or FAILs any golden-FALSE, is itself the
# bluff (§11.4.107(10)) and this harness reports it.
#
# Usage:   bash tests/pre_build/test_check_cm_ownership_invariants.sh
# Inputs:  none (no stdin, no env input).
# Outputs: per-case ok/FAIL lines on stdout; a summary line last.
# Side-effects: writes ONLY inside a mktemp directory, removed on every exit
#           path (§11.4.14). Never writes into the repository tree. Never
#           signals a process (§11.4.263 vacuous — no kill call exists here).
# Dependencies: bash, python3 with PyYAML (via the gate), mktemp, sed.
#
# Exit codes:
#   0 — every fixture matched its expected outcome (the gate is honest)
#   1 — one or more checks diverged
#   2 — harness/environment error (gate missing or not executable)
#
# Cross-refs: §11.4.1 §11.4.4 §11.4.6 §11.4.14 §11.4.43 §11.4.69 §11.4.107(10)
#             §11.4.108 §11.4.115 §11.4.135 §11.4.201 §11.4.245.

set -euo pipefail

HARNESS_NAME="test_check_cm_ownership_invariants"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

GATE="${REPO_ROOT}/scripts/pre_build/check_cm_ownership_invariants.sh"
REAL_COMPOSE="${REPO_ROOT}/docker-compose.yml"
REAL_OWNED="${REPO_ROOT}/config/owned_paths.yaml"

if [[ ! -f "${GATE}" ]]; then
    echo "FAIL(${HARNESS_NAME}): gate script not found at ${GATE}" >&2
    exit 2
fi
if [[ ! -x "${GATE}" ]]; then
    echo "FAIL(${HARNESS_NAME}): gate script not executable at ${GATE}" >&2
    exit 2
fi
for required in "${REAL_COMPOSE}" "${REAL_OWNED}"; do
    if [[ ! -f "${required}" ]]; then
        echo "FAIL(${HARNESS_NAME}): required input missing: ${required}" >&2
        exit 2
    fi
done

TMP_ROOT="$(mktemp -d -t ownership_invariants_meta.XXXXXX)"
trap 'rm -rf "${TMP_ROOT}"' EXIT

fails=0
checks=0

GOT_RC=0
GOT_OUT=""

run_gate() {
    # $1 compose path, $2 owned-paths path. Captures rc without tripping
    # `set -e` (a $(...) of a nonzero-exit command would abort the harness
    # before the assertion runs).
    local compose="$1" owned="$2" out rc
    out="$(mktemp -p "${TMP_ROOT}")"
    set +e
    "${GATE}" "${compose}" "${owned}" >"${out}" 2>&1
    rc=$?
    set -e
    GOT_RC="${rc}"
    GOT_OUT="${out}"
}

# expect_rc <label> <expected_rc> <compose> <owned> [required_substring...]
expect_rc() {
    local label="$1" expected="$2" compose="$3" owned="$4"
    shift 4
    checks=$((checks + 1))
    run_gate "${compose}" "${owned}"
    if [[ "${GOT_RC}" -ne "${expected}" ]]; then
        echo "FAIL: ${label}: expected exit ${expected}, got ${GOT_RC}"
        sed 's/^/      /' "${GOT_OUT}"
        fails=$((fails + 1))
        return 0
    fi
    # A non-zero exit alone is not proof the gate refused for the RIGHT
    # reason (§11.4.245 — the oracle must be independent of "it errored").
    local needle
    for needle in "$@"; do
        if ! grep -qF -- "${needle}" "${GOT_OUT}"; then
            echo "FAIL: ${label}: exit ${GOT_RC} correct, but the report never mentions '${needle}'"
            sed 's/^/      /' "${GOT_OUT}"
            fails=$((fails + 1))
            return 0
        fi
    done
    echo "ok:   ${label} (exit ${GOT_RC})"
}

mk() { # mk <name> <<'YAML' ... ; prints the path
    local path="${TMP_ROOT}/$1"
    cat >"${path}"
    echo "${path}"
}

# --------------------------------------------------------------------------
# Shared owned-paths fixtures
# --------------------------------------------------------------------------
OWNED_OK="${TMP_ROOT}/owned_ok.yaml"
cp "${REAL_OWNED}" "${OWNED_OK}"

OWNED_EMPTY="${TMP_ROOT}/owned_empty.yaml"
: >"${OWNED_EMPTY}"

OWNED_NO_PATHS="${TMP_ROOT}/owned_no_paths.yaml"
printf 'schema_version: 1\npaths: []\n' >"${OWNED_NO_PATHS}"

OWNED_ABSENT="${TMP_ROOT}/owned_absent.yaml"   # deliberately never created

# --------------------------------------------------------------------------
# GOLDEN-FALSE: a verbatim copy of the real, fixed tree must PASS
# --------------------------------------------------------------------------
COMPOSE_GOOD="${TMP_ROOT}/compose_good.yml"
cp "${REAL_COMPOSE}" "${COMPOSE_GOOD}"
expect_rc "golden-good (copy of the real compose)" 0 "${COMPOSE_GOOD}" "${OWNED_OK}" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

# --------------------------------------------------------------------------
# REVERT MUTATION: flip the fix back on a COPY (never the real file)
# --------------------------------------------------------------------------
COMPOSE_REVERT_PUID="${TMP_ROOT}/compose_revert_puid.yml"
sed 's/- PUID=0/- PUID=1000/' "${REAL_COMPOSE}" >"${COMPOSE_REVERT_PUID}"
if ! grep -q 'PUID=1000' "${COMPOSE_REVERT_PUID}"; then
    echo "FAIL: revert-puid fixture did not mutate — the harness is blind, not the tree clean"
    fails=$((fails + 1))
fi
expect_rc "revert-puid (PUID=0 -> 1000 on the real compose copy)" 1 \
    "${COMPOSE_REVERT_PUID}" "${OWNED_OK}" \
    "qbittorrent: PUID=1000, expected 0" "jackett: PUID=1000, expected 0"

COMPOSE_REVERT_PGID="${TMP_ROOT}/compose_revert_pgid.yml"
sed 's/- PGID=0/- PGID=1000/' "${REAL_COMPOSE}" >"${COMPOSE_REVERT_PGID}"
expect_rc "revert-pgid (PGID=0 -> 1000 on the real compose copy)" 1 \
    "${COMPOSE_REVERT_PGID}" "${OWNED_OK}" \
    "PGID=1000, expected 0"

# --------------------------------------------------------------------------
# GOLDEN-BAD fixtures
# --------------------------------------------------------------------------
C_NO_PUID="$(mk compose_no_puid.yml <<'YAML'
services:
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    environment:
      - WEBUI_PORT=7185
YAML
)"
expect_rc "no-puid (linuxserver service declares no PUID)" 1 "${C_NO_PUID}" "${OWNED_OK}" \
    "declares NO PUID" "declares NO PGID"

C_KEEPID="$(mk compose_keepid.yml <<'YAML'
services:
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    userns_mode: keep-id
    environment:
      - PUID=0
      - PGID=0
YAML
)"
expect_rc "keep-id (userns_mode reintroduced)" 1 "${C_KEEPID}" "${OWNED_OK}" \
    "userns_mode: keep-id" "NO USABLE ROOT"

C_KEEPID_UID="$(mk compose_keepid_uid.yml <<'YAML'
services:
  download-proxy:
    image: python:3.12-alpine
    userns_mode: "keep-id:uid=1000,gid=1000"
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    environment:
      - PUID=0
      - PGID=0
YAML
)"
expect_rc "keep-id-uid (keep-id:uid=...,gid=... spelling)" 1 "${C_KEEPID_UID}" "${OWNED_OK}" \
    "download-proxy: declares \`userns_mode: keep-id:uid=1000,gid=1000\`"

C_ENV_MAP="$(mk compose_env_mapping.yml <<'YAML'
services:
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    environment:
      PUID: 1000
      PGID: 0
YAML
)"
expect_rc "env-mapping (mapping-form environment with PUID: 1000)" 1 "${C_ENV_MAP}" "${OWNED_OK}" \
    "qbittorrent: PUID=1000, expected 0"

C_PASSTHRU="$(mk compose_passthru.yml <<'YAML'
services:
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    environment:
      - PUID
      - PGID=0
YAML
)"
expect_rc "puid-passthru (bare '- PUID', not statically resolvable)" 1 "${C_PASSTHRU}" "${OWNED_OK}" \
    "NOT statically resolvable"

C_ZERO_SVC="$(mk compose_zero_services.yml <<'YAML'
version: "3.9"
YAML
)"
expect_rc "zero-services (blind parse must not read as clean)" 1 "${C_ZERO_SVC}" "${OWNED_OK}" \
    "ZERO services parsed"

C_NO_LS="$(mk compose_no_linuxserver.yml <<'YAML'
services:
  download-proxy:
    image: python:3.12-alpine
YAML
)"
expect_rc "no-linuxserver (PUID clause asserted nothing)" 1 "${C_NO_LS}" "${OWNED_OK}" \
    "ZERO are linuxserver-based"

expect_rc "owned-missing (ownership scope file absent)" 1 "${COMPOSE_GOOD}" "${OWNED_ABSENT}" \
    "owned-paths: file not found"

expect_rc "owned-empty (parses to None — the FALSE-NULL shape)" 1 "${COMPOSE_GOOD}" "${OWNED_EMPTY}" \
    "parsed to EMPTY"

expect_rc "owned-no-paths (paths: is empty)" 1 "${COMPOSE_GOOD}" "${OWNED_NO_PATHS}" \
    "is missing or empty"

# --------------------------------------------------------------------------
# GOLDEN-FALSE fixtures (§11.4.201(1): refusing a healthy tree is a defect)
# --------------------------------------------------------------------------
C_NO_PUID_OK="$(mk compose_no_puid_ok.yml <<'YAML'
services:
  # download-proxy's real shape: runs as root, measured to write as host uid
  # 1000, has no PUID and needs none. The gate MUST NOT demand one.
  download-proxy:
    image: python:3.12-alpine
  boba-jackett:
    build:
      context: ./qBitTorrent-go
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    environment:
      - PUID=0
      - PGID=0
YAML
)"
expect_rc "no-puid-ok (non-linuxserver service with no PUID)" 0 "${C_NO_PUID_OK}" "${OWNED_OK}" \
    "download-proxy: image=python:3.12-alpine -> not linuxserver-based"

C_CARRIER="$(mk compose_carrier.yml <<'YAML'
services:
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    # userns_mode: keep-id  <- considered and REJECTED; a comment is not a
    # declaration. Historically PUID=1000 here; the 0 below is the fix.
    environment:
      - PUID=0
      - PGID=0
YAML
)"
expect_rc "carrier-comment (prose mentioning keep-id / PUID=1000)" 0 "${C_CARRIER}" "${OWNED_OK}" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

C_SUBSTR="$(mk compose_substring_image.yml <<'YAML'
services:
  forked:
    image: acme/mylinuxserverfork:latest
  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    environment:
      - PUID=0
      - PGID=0
YAML
)"
expect_rc "substring-image (repo name contains 'linuxserver')" 0 "${C_SUBSTR}" "${OWNED_OK}" \
    "forked: image=acme/mylinuxserverfork:latest -> not linuxserver-based"

C_REGPORT="$(mk compose_registry_port.yml <<'YAML'
services:
  mirrored:
    image: reg.example:5000/linuxserver/qbittorrent:1
    environment:
      - PUID=0
      - PGID=0
YAML
)"
expect_rc "registry-port (host:port/linuxserver/img:tag still matched)" 0 "${C_REGPORT}" "${OWNED_OK}" \
    "mirrored: image=reg.example:5000/linuxserver/qbittorrent:1 -> linuxserver"

# --------------------------------------------------------------------------
# Real-tree smoke: the gate with NO arguments, against the actual checkout
# --------------------------------------------------------------------------
checks=$((checks + 1))
set +e
REAL_OUT="$(mktemp -p "${TMP_ROOT}")"
"${GATE}" >"${REAL_OUT}" 2>&1
REAL_RC=$?
set -e
if [[ "${REAL_RC}" -ne 0 ]]; then
    echo "FAIL: real-tree: gate exited ${REAL_RC} against the actual checkout (expected 0)"
    sed 's/^/      /' "${REAL_OUT}"
    fails=$((fails + 1))
else
    echo "ok:   real-tree (exit 0)"
fi

# --------------------------------------------------------------------------
# Residue check: the real compose must be byte-identical to where we started.
# This harness only ever wrote inside ${TMP_ROOT}; asserting it is the cheap
# proof (§11.4.84 — no mutation residue may survive a mutation experiment).
# --------------------------------------------------------------------------
checks=$((checks + 1))
if cmp -s "${REAL_COMPOSE}" "${COMPOSE_GOOD}"; then
    echo "ok:   no-residue (docker-compose.yml unchanged by this harness)"
else
    echo "FAIL: no-residue: docker-compose.yml differs from the copy taken at harness start"
    fails=$((fails + 1))
fi

echo
if [[ "${fails}" -gt 0 ]]; then
    echo "FAIL(${HARNESS_NAME}): ${fails}/${checks} check(s) diverged"
    exit 1
fi
echo "PASS(${HARNESS_NAME}): ${checks}/${checks} checks matched their expected outcome"
exit 0
