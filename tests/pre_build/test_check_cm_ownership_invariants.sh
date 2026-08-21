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
#                        the image's `abc` (911) default -> host 100910, the
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
#   BUILD-RESOLVED SCOPE (the FROM-chain resolver of commit 649622a; every
#   golden-bad below is DISCRIMINATING — measured to exit 0 against the pre-fix
#   gate at 0e5aca5 and 1 against the current one, so reverting the resolver
#   turns this suite red. See the section comment for why each fixture carries
#   a second, healthy, image:-based linuxserver service):
#     build-puid1000        -> exit 1 (build base resolves to linuxserver and
#                              the service declares PUID=1000 — the formerly
#                              BLIND case: no `image:` key, so the image-only
#                              derivation classified it not-linuxserver and
#                              never PUID-checked it)
#     build-no-puid         -> exit 1 (same, declaring no PUID at all)
#     build-alias-chain     -> exit 1 (last stage names an `AS` alias that
#                              resolves back to a linuxserver stage)
#     build-arg-default     -> exit 1 (global `ARG BASE=lscr.io/...` expanded
#                              into `FROM ${BASE}`)
#     build-platform-flag   -> exit 1 (`--platform=` is a FROM flag, not the
#                              image reference)
#     build-inline          -> exit 1 (`build.dockerfile_inline` carries the
#                              FROM; no Dockerfile exists on disk)
#     build-arg-nodefault   -> exit 1 (`ARG BASE` with no default: the base is
#                              UNVERIFIABLE, and §11.4.201(6) forbids reading
#                              that silence as "not linuxserver")
#     build-dockerfile-absent -> exit 1 (no Dockerfile at either candidate
#                              path: UNVERIFIABLE, refusal reports what it
#                              tried)
#   BUILD-RESOLVED GOLDEN-FALSE (the resolver must widen the SCOPE without
#   changing the VERDICT for a healthy tree — a resolver that refused every
#   build-based service would satisfy every golden-bad above and still be a
#   §11.4.201(1) false-positive engine):
#     build-comment-carrier -> exit 0 (a Dockerfile COMMENT mentioning
#                              lscr.io/linuxserver; the real base is alpine)
#     build-alpine-base     -> exit 0 (multi-stage golang -> alpine, boba's own
#                              boba-jackett / qbittorrent-proxy-go shape)
#     build-linuxserver-puid0-ok -> exit 0 (resolved linuxserver base that is
#                              CORRECTLY held at PUID=0/PGID=0)
#
#   MOUNT-SCOPE / RUN-AS-USER (invariant 4, E5 route completeness, T034 —
#   added 2026-08-21 for independent review finding IMPORTANT-1; every
#   golden-bad below was MEASURED to exit 0 against the pre-fix gate, so the
#   §11.4.115(F) revert of invariant 4 turns this suite red):
#     mount-user-attack     -> exit 1 (the reviewer's verbatim four-line
#                              attack: `user: "1000:1000"` + a mount of the
#                              declared download root, appended to a copy of
#                              the real compose. The pre-fix gate PASSED it.)
#     mount-user-config     -> exit 1 (the plausible hardening pass: `user:
#                              1000` on a service mounting `./config`, the
#                              tree that holds the credential store)
#     mount-user-with-puid0 -> exit 1 (a compose `user:` overrides the image
#                              entrypoint's uid, so PUID=0 cannot rescue it)
#     mount-user-unresolvable -> exit 1 (`user: "${SVC_UID}"` cannot be proven
#                              root; the quiet "cannot tell" must not be read
#                              as "runs as root" — §11.4.201(6))
#     mount-dockerfile-user -> exit 1 (the downgrade hidden in a Dockerfile
#                              `USER appuser`, invisible to a compose-key-only
#                              reader)
#   MOUNT-SCOPE GOLDEN-FALSE (a rule that fired on every `user:` would satisfy
#   every golden-bad above and still be a §11.4.201(1) false-positive engine):
#     mount-real-compose    -> exit 0 (the real tree: five services mount
#                              in-scope paths, none declares a `user:`)
#     mount-user-root       -> exit 0 (explicit `user: "0:0"`)
#     mount-linuxserver-puid0 -> exit 0 (the sanctioned PUID=0 pattern with an
#                              in-scope mount)
#     mount-user-out-of-scope -> exit 0 (non-root `user:` on a service that
#                              mounts NOTHING in scope — an ordinary hardened
#                              sidecar is none of this gate's business)
#     mount-dockerfile-user-root -> exit 0 (a trailing `USER root` is a root
#                              declaration, not a downgrade)
#     mount-build-no-user   -> exit 0 (boba-jackett's real shape: a build with
#                              no USER directive at all)
#     mount-dockerfile-user-carrier -> exit 0 (a Dockerfile COMMENT mentioning
#                              `USER appuser` — the BOB-138 carrier class, one
#                              more time, against the new reader)
#
# A gate that PASSes any golden-bad, or FAILs any golden-FALSE, is itself the
# bluff (§11.4.107(10)) and this harness reports it.
#
# ACCEPTANCE (§11.4.115(F) — the canonical §1.1 mutation for a landed fix is
# that fix's own revert). This suite was run against the PRE-FIX gate,
# extracted read-only with
#     git show 0e5aca5:scripts/pre_build/check_cm_ownership_invariants.sh
# and it FAILS there on the eight build-resolved golden-bad fixtures. Before
# this section existed it passed 19/19 against that same pre-fix gate, which is
# what made the resolver revert-invisible.
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
# BUILD-RESOLVED SCOPE (the FROM-chain resolver, commit 649622a)
#
# WHY THIS SECTION EXISTS AND WHY EVERY FIXTURE IN IT CARRIES A SECOND,
# HEALTHY, image:-BASED LINUXSERVER SERVICE — this is the load-bearing detail,
# not decoration:
#
#   The resolver was landed with its validation living only in a commit
#   message, and an independent re-review PROVED the omission was not cosmetic:
#   it extracted the PRE-FIX gate (`git show 0e5aca5:...`), pointed THIS
#   harness at it, and got 19/19 PASS. Every fixture above classifies through
#   the `image:` key, so the entire resolver could be reverted wholesale and
#   this suite stayed green. Per §11.4.115(F) the canonical §1.1 mutation for a
#   landed fix IS that fix's own revert — and that mutation was invisible to
#   everything in the repository.
#
#   The trap that made it invisible is worth naming, because it is easy to walk
#   back into: a fixture whose ONLY linuxserver-ish service is the build-based
#   one is NOT discriminating. The pre-fix gate classifies it not-linuxserver,
#   then trips its own "N service(s) parsed but ZERO are linuxserver-based"
#   clause and ALSO exits 1 — the right answer for the wrong reason, and an
#   exit-code assertion cannot tell the two apart. Anchoring each fixture with
#   a correct `image:`-based linuxserver service keeps linuxserver_checked >= 1
#   on BOTH gates, so the ONLY thing left that can move the verdict is whether
#   the build base was resolved. Measured against 0e5aca5, every golden-bad
#   fixture below exits 0 on the pre-fix gate and 1 on the current one.
#
#   Do not "simplify" these fixtures by deleting the anchor service.
# --------------------------------------------------------------------------

# mk_ctx <dirname> — write a Dockerfile into a build context from stdin.
# The context lives inside TMP_ROOT, and the compose fixtures reference it
# relatively, so locate_dockerfile()'s compose-relative resolution finds it
# without the repo-root fallback ever being consulted.
mk_ctx() {
    local dir="${TMP_ROOT}/$1"
    mkdir -p "${dir}"
    cat >"${dir}/Dockerfile"
}

# compose_build <file> <context-or-inline-block> — emit a compose fixture with
# the healthy anchor service plus a `svc-under-test` carrying the given build
# stanza and environment lines (passed as the remaining arguments, verbatim).
compose_build() {
    local out="${TMP_ROOT}/$1"; shift
    local build_stanza="$1"; shift
    {
        printf 'services:\n'
        printf '  qbittorrent:\n'
        printf '    image: lscr.io/linuxserver/qbittorrent:latest\n'
        printf '    environment:\n'
        printf '      - PUID=0\n'
        printf '      - PGID=0\n'
        printf '  svc-under-test:\n'
        printf '%s\n' "${build_stanza}"
        local line
        for line in "$@"; do
            printf '%s\n' "${line}"
        done
    } >"${out}"
    echo "${out}"
}

# --- GOLDEN-BAD: a resolved linuxserver base with a reverted PUID ----------
mk_ctx ctx_build_puid <<'DOCKERFILE'
FROM lscr.io/linuxserver/qbittorrent:latest
RUN echo "derived image"
DOCKERFILE
C_BUILD_PUID="$(compose_build compose_build_puid.yml \
    '    build:
      context: ./ctx_build_puid' \
    '    environment:' '      - PUID=1000' '      - PGID=1000')"
expect_rc "build-puid1000 (build base resolves to linuxserver, PUID reverted)" 1 \
    "${C_BUILD_PUID}" "${OWNED_OK}" \
    "svc-under-test: PUID=1000, expected 0" \
    "svc-under-test: PGID=1000, expected 0"

# --- GOLDEN-BAD: resolved linuxserver base with NO PUID at all -------------
# The defect reached by OMISSION rather than by a wrong value: the image then
# runs the app as its `abc` default (911) -> host uid 100910.
mk_ctx ctx_build_nopuid <<'DOCKERFILE'
FROM lscr.io/linuxserver/jackett:latest
DOCKERFILE
C_BUILD_NOPUID="$(compose_build compose_build_nopuid.yml \
    '    build:
      context: ./ctx_build_nopuid')"
expect_rc "build-no-puid (resolved linuxserver base declaring no PUID at all)" 1 \
    "${C_BUILD_NOPUID}" "${OWNED_OK}" \
    "svc-under-test: linuxserver service (build base=lscr.io/linuxserver/jackett:latest" \
    "declares NO PUID" "declares NO PGID"

# --- GOLDEN-BAD: multi-stage AS-alias chain resolving to linuxserver -------
# The LAST stage is the runtime image, and it names an alias rather than a
# registry reference. A resolver that read only the first or only the last
# FROM literal would miss this.
mk_ctx ctx_build_chain <<'DOCKERFILE'
FROM lscr.io/linuxserver/qbittorrent:latest AS runtime-base
FROM golang:1.23-alpine AS builder
RUN echo "compile something"
FROM runtime-base
COPY --from=builder /out /out
DOCKERFILE
C_BUILD_CHAIN="$(compose_build compose_build_chain.yml \
    '    build:
      context: ./ctx_build_chain' \
    '    environment:' '      - PUID=1000' '      - PGID=0')"
expect_rc "build-alias-chain (last stage -> AS alias -> linuxserver)" 1 \
    "${C_BUILD_CHAIN}" "${OWNED_OK}" \
    "svc-under-test: PUID=1000, expected 0"

# --- GOLDEN-BAD: global ARG default substituted into FROM ------------------
mk_ctx ctx_build_argdflt <<'DOCKERFILE'
ARG BASE=lscr.io/linuxserver/jackett:latest
FROM ${BASE}
DOCKERFILE
C_BUILD_ARGDFLT="$(compose_build compose_build_argdflt.yml \
    '    build:
      context: ./ctx_build_argdflt' \
    '    environment:' '      - PUID=1000' '      - PGID=0')"
expect_rc "build-arg-default (ARG default expands to a linuxserver base)" 1 \
    "${C_BUILD_ARGDFLT}" "${OWNED_OK}" \
    "svc-under-test: PUID=1000, expected 0"

# --- GOLDEN-BAD: `--platform=` is a FROM flag, not the image reference -----
mk_ctx ctx_build_platform <<'DOCKERFILE'
FROM --platform=linux/amd64 lscr.io/linuxserver/qbittorrent:latest
DOCKERFILE
C_BUILD_PLATFORM="$(compose_build compose_build_platform.yml \
    '    build:
      context: ./ctx_build_platform')"
expect_rc "build-platform-flag (--platform operand skipped, base still resolved)" 1 \
    "${C_BUILD_PLATFORM}" "${OWNED_OK}" \
    "svc-under-test: linuxserver service (build base=lscr.io/linuxserver/qbittorrent:latest" \
    "declares NO PUID"

# --- GOLDEN-BAD: build.dockerfile_inline carries the FROM ------------------
# No Dockerfile exists on disk at all here; the base lives in the compose file.
C_BUILD_INLINE="$(compose_build compose_build_inline.yml \
    '    build:
      context: .
      dockerfile_inline: |
        FROM lscr.io/linuxserver/qbittorrent:latest
        RUN echo "inline"' \
    '    environment:' '      - PUID=1000' '      - PGID=0')"
expect_rc "build-inline (dockerfile_inline base resolves to linuxserver)" 1 \
    "${C_BUILD_INLINE}" "${OWNED_OK}" \
    "svc-under-test: PUID=1000, expected 0"

# --- GOLDEN-BAD: UNVERIFIABLE base — ARG with no default -------------------
# §11.4.201(6): an unresolvable base is precisely where a linuxserver image
# would hide, so the quiet "not linuxserver" the pre-fix gate returned was a
# FALSE-NULL. The refusal must NAME the argument it could not resolve.
mk_ctx ctx_build_argless <<'DOCKERFILE'
ARG BASE
FROM ${BASE}
DOCKERFILE
C_BUILD_ARGLESS="$(compose_build compose_build_argless.yml \
    '    build:
      context: ./ctx_build_argless')"
expect_rc "build-arg-nodefault (FROM \${BASE} with no default -> UNVERIFIABLE)" 1 \
    "${C_BUILD_ARGLESS}" "${OWNED_OK}" \
    "svc-under-test: base image UNVERIFIABLE" \
    "build argument(s) BASE that have no default"

# --- GOLDEN-BAD: UNVERIFIABLE base — no Dockerfile anywhere ----------------
# The context name is deliberately one that exists neither under TMP_ROOT nor
# at the repo root, so BOTH locate_dockerfile candidates genuinely miss and the
# refusal reports what it tried (§11.4.201(5)).
C_BUILD_NODF="$(compose_build compose_build_nodf.yml \
    '    build:
      context: ./ctx_build_absent_no_such_context_zz')"
expect_rc "build-dockerfile-absent (no Dockerfile found -> UNVERIFIABLE)" 1 \
    "${C_BUILD_NODF}" "${OWNED_OK}" \
    "svc-under-test: builds from \`Dockerfile\`" \
    "UNVERIFIABLE — no Dockerfile was found"

# --- GOLDEN-FALSE: a Dockerfile COMMENT naming a linuxserver image ---------
# The compose-side carrier guard already exists above; this is its Dockerfile-
# side twin. A substring scan of the build context would fire here; a token
# parse that drops comment lines before reading instructions must not.
mk_ctx ctx_build_comment <<'DOCKERFILE'
# This image used to be FROM lscr.io/linuxserver/qbittorrent:latest back when
# PUID=1000 was needed. Recording the history in a comment must not make the
# gate treat this alpine build as a linuxserver service.
FROM alpine:3.20
RUN echo "not linuxserver"
DOCKERFILE
C_BUILD_COMMENT="$(compose_build compose_build_comment.yml \
    '    build:
      context: ./ctx_build_comment')"
expect_rc "build-comment-carrier (Dockerfile comment mentions lscr.io/linuxserver)" 0 \
    "${C_BUILD_COMMENT}" "${OWNED_OK}" \
    "svc-under-test: build base=alpine:3.20" \
    "not linuxserver-based, PUID not required" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

# --- GOLDEN-FALSE: a genuinely non-linuxserver build base -----------------
# boba's own locally-built services (boba-jackett, qbittorrent-proxy-go) have
# this exact shape. Demanding a PUID here would be the §11.4.201(1) false-
# positive refusal — as broken as passing a reverted tree.
mk_ctx ctx_build_alpine <<'DOCKERFILE'
FROM golang:1.23-alpine AS builder
RUN echo "build the binary"
FROM alpine:3.20
COPY --from=builder /app /app
DOCKERFILE
C_BUILD_ALPINE="$(compose_build compose_build_alpine.yml \
    '    build:
      context: ./ctx_build_alpine')"
expect_rc "build-alpine-base (resolved base is genuinely not linuxserver)" 0 \
    "${C_BUILD_ALPINE}" "${OWNED_OK}" \
    "svc-under-test: build base=alpine:3.20" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

# --- GOLDEN-FALSE: resolved linuxserver base that is CORRECTLY set --------
# Proves the resolver widens the SCOPE without changing the VERDICT for a
# healthy service: it is classified linuxserver, PUID/PGID are checked, and
# they pass. A resolver that refused every build-based service would satisfy
# every golden-bad above and still be broken.
mk_ctx ctx_build_ok <<'DOCKERFILE'
FROM lscr.io/linuxserver/qbittorrent:latest
RUN echo "derived, and correctly configured"
DOCKERFILE
C_BUILD_OK="$(compose_build compose_build_ok.yml \
    '    build:
      context: ./ctx_build_ok' \
    '    environment:' '      - PUID=0' '      - PGID=0')"
expect_rc "build-linuxserver-puid0-ok (resolved linuxserver base, PUID=0)" 0 \
    "${C_BUILD_OK}" "${OWNED_OK}" \
    "svc-under-test: build base=lscr.io/linuxserver/qbittorrent:latest" \
    "linuxserver, PUID=0, PGID=0 OK" \
    "PASS: CM-OWNERSHIP-INVARIANTS"


# --------------------------------------------------------------------------
# MOUNT-SCOPE / RUN-AS-USER COMPLETENESS (E5, task T034 — FR-011/FR-016)
#
# WHY THIS SECTION EXISTS (independent review finding IMPORTANT-1, reproduced
# 2026-08-21 against the pre-fix gate):
#
#   The gate asserted PUID on linuxserver services and forbade keep-id, and it
#   NEVER READ `volumes:` OR `user:`. The reviewer appended four lines to a copy
#   of the real docker-compose.yml —
#
#       attack-writer:
#         image: python:3.12-alpine
#         user: "1000:1000"
#         volumes:
#           - ${QBITTORRENT_DATA_DIR:-/mnt/DATA}:/downloads
#
#   — and the gate printed `PASS: CM-OWNERSHIP-INVARIANTS`, exit 0. That
#   service's writes land at host uid 100999: the reported defect, verbatim,
#   waved through by the gate that exists to make it un-revertable.
#
#   This is not an exotic construction. A well-meaning "don't run containers as
#   root" hardening pass that adds `user: "1000:1000"` to download-proxy would
#   silently reintroduce the defect for `config/` — including the encrypted
#   credential store — while every existing invariant stayed green.
#
#   tasks.md T034 and data-model.md E5 BOTH describe the gate as asserting that
#   every compose service mounting an in-scope path declares a route. The
#   shipped gate contained no mount analysis at all, so T034 was marked done
#   for a strictly weaker gate than it described.
#
# WHY EVERY FIXTURE HERE CARRIES A HEALTHY ANCHOR LINUXSERVER SERVICE:
#   the same reason the build-resolved section does — without it the pre-fix
#   gate trips its own "ZERO are linuxserver-based" clause and exits 1 for the
#   WRONG reason, and an exit-code assertion cannot tell the two apart. Each
#   golden-bad below was MEASURED to exit 0 on the pre-fix gate.
# --------------------------------------------------------------------------

# compose_mount <file> <service-body-lines...> — emit a compose fixture with
# the healthy anchor service plus `svc-under-test` carrying the given lines.
compose_mount() {
    local out="${TMP_ROOT}/$1"; shift
    {
        printf 'services:\n'
        printf '  qbittorrent:\n'
        printf '    image: lscr.io/linuxserver/qbittorrent:latest\n'
        printf '    environment:\n'
        printf '      - PUID=0\n'
        printf '      - PGID=0\n'
        printf '  svc-under-test:\n'
        local line
        for line in "$@"; do
            printf '%s\n' "${line}"
        done
    } >"${out}"
    echo "${out}"
}

# --- GOLDEN-BAD: the reviewer's exact attack, verbatim --------------------
C_ATTACK="${TMP_ROOT}/compose_attack_writer.yml"
{
    cat "${REAL_COMPOSE}"
    printf '\n  attack-writer:\n'
    printf '    image: python:3.12-alpine\n'
    printf '    user: "1000:1000"\n'
    printf '    volumes:\n'
    printf '      - ${QBITTORRENT_DATA_DIR:-/mnt/DATA}:/downloads\n'
} >"${C_ATTACK}"
expect_rc "mount-user-attack (reviewer's verbatim user:1000:1000 + in-scope mount)" 1 \
    "${C_ATTACK}" "${OWNED_OK}" \
    "attack-writer: mounts the declared location" \
    'declares `user: 1000:1000`' \
    "NOT container-root"

# --- GOLDEN-BAD: the plausible hardening pass on config/ ------------------
# `config/` holds the encrypted credential store, so a non-root `user:` here
# reproduces the exact state that made config/boba.db unreadable to its owner.
C_USER_CONFIG="$(compose_mount compose_user_config.yml \
    '    image: python:3.12-alpine' \
    '    user: "1000"' \
    '    volumes:' \
    '      - ./config:/config')"
expect_rc "mount-user-config (hardening pass adds user: 1000 to a config/ writer)" 1 \
    "${C_USER_CONFIG}" "${OWNED_OK}" \
    "svc-under-test: mounts the declared location" \
    'declares `user: 1000`' \
    "host uid 100999"

# --- GOLDEN-BAD: PUID=0 does NOT rescue a compose `user:` override --------
# A compose `user:` replaces the container's entrypoint uid outright, so the
# linuxserver entrypoint never runs as root and never drops to PUID. Reading
# PUID=0 as sufficient here would be a gate that passes its own defect.
C_USER_PUID0="$(compose_mount compose_user_with_puid0.yml \
    '    image: lscr.io/linuxserver/jackett:latest' \
    '    user: "1000:1000"' \
    '    environment:' \
    '      - PUID=0' \
    '      - PGID=0' \
    '    volumes:' \
    '      - ${QBITTORRENT_DATA_DIR:-/mnt/DATA}:/downloads')"
expect_rc "mount-user-with-puid0 (user: override defeats PUID=0)" 1 \
    "${C_USER_PUID0}" "${OWNED_OK}" \
    "svc-under-test: mounts the declared location" \
    "NOT container-root" \
    "overrides the image entrypoint"

# --- GOLDEN-BAD: a `user:` nobody can resolve is not a proven root --------
# §11.4.201(6): the quiet "cannot tell" must not be read as "runs as root".
C_USER_VAR="$(compose_mount compose_user_var.yml \
    '    image: python:3.12-alpine' \
    '    user: "${SVC_UID}"' \
    '    volumes:' \
    '      - ./config:/config')"
expect_rc "mount-user-unresolvable (user: \${SVC_UID} cannot be proven root)" 1 \
    "${C_USER_VAR}" "${OWNED_OK}" \
    "svc-under-test: mounts the declared location" \
    'declares `user: ${SVC_UID}`' \
    "not statically resolvable"

# --- GOLDEN-BAD: the downgrade hidden in a Dockerfile USER directive ------
# A build-based service has no compose `user:` at all; the downgrade lives in
# its Dockerfile. Reading only the compose key would leave this blind.
mk_ctx ctx_user_dockerfile <<'DOCKERFILE'
FROM alpine:3.20
RUN adduser -D -u 1000 appuser
USER appuser
DOCKERFILE
C_USER_DF="$(compose_mount compose_user_dockerfile.yml \
    '    build:' \
    '      context: ./ctx_user_dockerfile' \
    '    volumes:' \
    '      - ./config:/config')"
expect_rc "mount-dockerfile-user (USER appuser downgrade in the build)" 1 \
    "${C_USER_DF}" "${OWNED_OK}" \
    "svc-under-test: mounts the declared location" \
    "USER appuser" \
    "NOT container-root"

# --------------------------------------------------------------------------
# MOUNT-SCOPE GOLDEN-FALSE (§11.4.201(1) — the mount rule must not refuse a
# healthy tree; a rule that fired on every `user:` would satisfy every
# golden-bad above and still be a false-positive engine)
# --------------------------------------------------------------------------

# (a) the real docker-compose.yml as it stands today — five services mount
#     in-scope paths and NONE declares a `user:`; every one runs as container
#     root, which is the measured-correct route. Covered by golden-good above
#     and by real-tree below; asserted here on the INFO line so the pass is
#     positive evidence rather than a bare exit code (§11.4.245).
expect_rc "mount-real-compose (every in-scope mounter runs as container root)" 0 \
    "${COMPOSE_GOOD}" "${OWNED_OK}" \
    "runs as container root" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

# (b) an EXPLICIT root user: is the sanctioned way to say it out loud.
C_USER_ROOT="$(compose_mount compose_user_root.yml \
    '    image: python:3.12-alpine' \
    '    user: "0:0"' \
    '    volumes:' \
    '      - ./config:/config')"
expect_rc "mount-user-root (explicit user: \"0:0\" is container root)" 0 \
    "${C_USER_ROOT}" "${OWNED_OK}" \
    'svc-under-test: mounts declared scope' \
    "runs as container root" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

# (c) the sanctioned linuxserver pattern: PUID=0, no `user:`, mounts in scope.
C_LS_PUID0_MOUNT="$(compose_mount compose_ls_puid0_mount.yml \
    '    image: lscr.io/linuxserver/jackett:latest' \
    '    environment:' \
    '      - PUID=0' \
    '      - PGID=0' \
    '    volumes:' \
    '      - ${QBITTORRENT_DATA_DIR:-/mnt/DATA}:/downloads')"
expect_rc "mount-linuxserver-puid0 (sanctioned PUID=0 pattern, in-scope mount)" 0 \
    "${C_LS_PUID0_MOUNT}" "${OWNED_OK}" \
    "svc-under-test: image=lscr.io/linuxserver/jackett:latest -> linuxserver, PUID=0, PGID=0 OK" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

# (d) a non-root `user:` on a service that mounts NOTHING in scope is none of
#     this gate's business. Refusing it would be the §11.4.201(1) false
#     positive — and would refuse a perfectly ordinary hardened sidecar.
C_USER_OOS="$(compose_mount compose_user_out_of_scope.yml \
    '    image: python:3.12-alpine' \
    '    user: "1000:1000"' \
    '    volumes:' \
    '      - ./frontend:/app')"
expect_rc "mount-user-out-of-scope (non-root user:, no in-scope mount)" 0 \
    "${C_USER_OOS}" "${OWNED_OK}" \
    "svc-under-test: mounts nothing in the declared ownership scope" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

# (e) `USER root` in a Dockerfile is a root declaration, not a downgrade.
mk_ctx ctx_user_root_df <<'DOCKERFILE'
FROM alpine:3.20
RUN adduser -D -u 1000 appuser
USER appuser
USER root
DOCKERFILE
C_USER_ROOT_DF="$(compose_mount compose_user_root_df.yml \
    '    build:' \
    '      context: ./ctx_user_root_df' \
    '    volumes:' \
    '      - ./config:/config')"
expect_rc "mount-dockerfile-user-root (last USER root is not a downgrade)" 0 \
    "${C_USER_ROOT_DF}" "${OWNED_OK}" \
    "runs as container root" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

# (f) boba-jackett's real shape: build-based, no USER directive anywhere,
#     mounts ./config. It was MEASURED to write as host uid 1000 as-is.
C_USER_NO_DF="$(compose_mount compose_user_no_directive.yml \
    '    build:' \
    '      context: ./ctx_build_alpine' \
    '    volumes:' \
    '      - ./config:/config')"
expect_rc "mount-build-no-user (build service with no USER directive)" 0 \
    "${C_USER_NO_DF}" "${OWNED_OK}" \
    "runs as container root" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

# (g) a Dockerfile COMMENT mentioning USER must not read as a downgrade —
#     the carrier guard, one more time, on the new reader (BOB-138 class).
mk_ctx ctx_user_comment_df <<'DOCKERFILE'
FROM alpine:3.20
# We used to run `USER appuser` here before the ownership fix landed.
RUN echo "runs as root on purpose"
DOCKERFILE
C_USER_COMMENT_DF="$(compose_mount compose_user_comment_df.yml \
    '    build:' \
    '      context: ./ctx_user_comment_df' \
    '    volumes:' \
    '      - ./config:/config')"
expect_rc "mount-dockerfile-user-carrier (comment mentioning USER appuser)" 0 \
    "${C_USER_COMMENT_DF}" "${OWNED_OK}" \
    "runs as container root" \
    "PASS: CM-OWNERSHIP-INVARIANTS"

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
