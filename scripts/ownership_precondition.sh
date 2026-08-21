#!/usr/bin/env bash
# ============================================================================
# scripts/ownership_precondition.sh — refuse to start when a declared location
# cannot produce operator-owned files (FR-010, FR-010a, FR-010b).
# ============================================================================
#
# Purpose:
#   Startup precondition for feature 002-user-owned-downloads. Every location
#   declared in the ownership scope (config/owned_paths.yaml, E1) is PROBED —
#   a real file is created and its owner read back — and startup is refused
#   when any location cannot produce a file owned by the operator who started
#   the system. Fail-closed by operator decision: starting with a warning was
#   explicitly rejected, because a missed warning silently reproduces the
#   defect this feature exists to remove.
#
# Usage:
#   scripts/ownership_precondition.sh [--scope <path-to-owned_paths.yaml>] [--quiet]
#
#   --scope <path>  Override the declared scope file. Takes precedence over the
#                   OWNED_PATHS_FILE environment variable.
#   --quiet         Suppress the per-location OK detail and the success banner.
#                   It NEVER suppresses a refusal or a probe-coverage gap — see
#                   "WHY --quiet HIDES ONLY GOOD NEWS" below.
#
# Inputs:
#   argv              --scope / --quiet as above.
#   OWNED_PATHS_FILE  Scope file path when --scope is absent (read by
#                     scripts/lib/ownership.sh).
#   CONTAINER_RUNTIME The project's canonical runtime sentinel. An explicitly
#                     EMPTY value means "there is no container runtime" and is
#                     honoured as such (start.sh:335 sets it, start.sh:698
#                     refuses on it). Unset means "not decided yet" and this
#                     script detects podman/docker itself. Absent and empty are
#                     deliberately different states.
#   Environment referenced by the scope's ${VAR:-default} placeholders
#                     (e.g. QBITTORRENT_DATA_DIR) and by docker-compose.yml.
#
# Outputs:
#   stdout  A per-location verdict report, a probe-coverage report whenever a
#           probe could not be run, and one of:
#             OWNERSHIP-PRECONDITION: OK
#             OWNERSHIP-PRECONDITION: FAIL          (+ the offending locations)
#             OWNERSHIP-PRECONDITION: CANNOT-RUN    (+ why)
#   exit 0  every declared location can produce operator-owned files
#   exit 1  at least one cannot — startup MUST NOT proceed
#   exit 2  the check could not run (scope missing/unparseable/empty, no
#           interpreter). 2 is NOT a pass: a check that could not run has
#           asserted nothing, and reporting that as success is the
#           §11.4.201(6) blind-instrument failure this feature exists to
#           prevent.
#
# Side-effects:
#   One probe file per declared DIRECTORY, created and removed (P2). When a
#   container runtime is available, one throwaway container per probed
#   directory that creates and removes one further probe file (P1). Declared
#   FILES are only stat'ed — nothing is created beside them.
#
# Dependencies:
#   bash, stat, mktemp, python3 with PyYAML (scope + compose parsing),
#   scripts/lib/ownership.sh, optionally podman/docker for P1.
#
# Cross-references:
#   specs/002-user-owned-downloads/contracts/startup-precondition.md
#   specs/002-user-owned-downloads/data-model.md   (E1 scope, E4 verdicts, E5 routes)
#   tests/unit/test_ownership_precondition.sh      (the paired suite)
#   scripts/lib/ownership.sh                       (scope + probe helpers, reused not forked)
#
# ── WHY THIS PROBES INSTEAD OF INSPECTING (FR-010b, §11.4.201) ──────────────
#   Ownership of a location cannot be read off the location itself. The
#   download root was owned by the operator's uid and still received files at
#   uid 100999 — which IS the defect. So the directory's own owner, the
#   configured PUID, and "no error occurred" are all PROXIES for the condition,
#   and a probe that passes because it never wrote anything is a false pass.
#   Every verdict below therefore comes from probe_location(), which creates a
#   real file and reads the owner back.
#
# ── WHY TWO PROBES, AND WHY NEITHER SPEAKS FOR THE OTHER (contract X1) ──────
#   P2 (host write, run as the operator) proves the location is writable and on
#   a filesystem that carries ownership. It is necessary and NOT sufficient: a
#   host-side write by the operator produces an operator-owned file even in the
#   directory whose CONTAINER writes land at 100999. P1 (a write from inside a
#   throwaway container, as the service's declared identity) is the only probe
#   that can observe the real defect. This script keeps them separate in the
#   report so a P2 pass is never dressed up as a P1 pass.
#
# ── WHY AN UNAVAILABLE P1 IS A SKIP, NOT A REFUSAL AND NOT A PASS ──────────
#   With no runtime (or no usable image, or no declared route to reproduce),
#   P1 cannot run. Reporting that as a pass is the blind-instrument bluff;
#   refusing on it would refuse every host without a runtime — a §11.4.201(1)
#   false-positive refusal, which is exactly as forbidden as a false pass. The
#   check therefore SKIPs P1 with a named reason, says out loud that the
#   fallback (asserting the declared ownership route) verifies CONFIGURATION
#   and not BEHAVIOUR, and refuses only on evidence it actually holds.
#
# ── WHY PUID=0 ON A ROOTFUL RUNTIME IS A THIRD REFUSAL TRIGGER ─────────────
#   Added 2026-08-21 (independent review finding IMPORTANT-2). PUID=0 is safe
#   ONLY because container uid 0 maps to the unprivileged operator under
#   ROOTLESS podman. Under a ROOTFUL runtime that premise is false — container
#   uid 0 is real host root — so PUID=0 would run the linuxserver application
#   as genuine root, writing into the bind-mounted ./config (the encrypted
#   credential store) and the download tree as uid 0: strictly WORSE than the
#   PUID=1000 it replaced, which at least ran unprivileged. Nothing enforced
#   the rootless premise: start.sh falls back to docker with no rootless
#   assertion, and the FR-011 pre-build gate checks that PUID=0 is PRESENT
#   while knowing nothing about the runtime.
#
#   This is a refusal trigger and a route reading is not, because the two are
#   different in kind: a route reading INFERS ownership from configuration,
#   whereas assert_rootless_runtime MEASURES the runtime (`podman info` /
#   `docker info`, field names read from real output, never guessed) and
#   refuses only on the dangerous COMBINATION of a measured-rootful runtime
#   AND a parsed PUID=0 declaration (§11.4.252 fail-closed). Rootlessness that
#   cannot be determined is a NAMED SKIP — neither a pass nor a refusal
#   (§11.4.201(1)/(6)).
#
# ── WHY A FAILED ROUTE ASSERTION DOES NOT, BY ITSELF, REFUSE ───────────────
#   The contract enumerates two OWNERSHIP refusal triggers: P1 fails, or P2
#   fails. A route assertion reads docker-compose.yml — configuration — and the
#   same contract forbids inferring ownership from configuration alone. Turning
#   a config reading into a refusal would make this check refuse on a proxy,
#   inside the check written to forbid proxies. Route COMPLETENESS is enforced
#   where it belongs: the FR-011/FR-016 pre-build gate
#   (scripts/pre_build/check_cm_ownership_invariants.sh, task T034). Here the
#   route is reported as the honest, clearly-labelled fallback it is.
#
# ── WHY --quiet HIDES ONLY GOOD NEWS ───────────────────────────────────────
#   A quiet flag that could hide a refusal, or hide the fact that the real
#   probe never ran, would re-create the missed-warning failure the fail-closed
#   decision was made to avoid. --quiet therefore suppresses passing detail
#   only; refusals, cannot-run reports and probe-coverage gaps always print.
#
# §11.4.263: this script signals no processes. There is no kill/pkill/killpg
# anywhere in it, so the pgid<=1 hazard cannot arise here.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# scripts/lib/ownership.sh owns scope resolution, the operator uid and the
# probe itself. It is SOURCED, never re-implemented: a second copy of that
# logic would be the near-identical fork §11.4.251 forbids, and would drift
# from the repair and the gate that read the same scope.
# shellcheck source=scripts/lib/ownership.sh
source "${SCRIPT_DIR}/lib/ownership.sh"

# Re-arm the strict mode the sourced library relaxes (it sets `-uo pipefail`
# for its own callers and deliberately does not set -e).
set -euo pipefail

readonly EXIT_OK=0
readonly EXIT_REFUSE=1
readonly EXIT_CANNOT_RUN=2

QUIET=0
SCOPE_ARG=""
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"

# Collected during the run. FAILURES drives the exit code; the others exist so
# the report can state what was checked and what was not.
FAILURES=()
P1_SKIPS=()
P1_OBSERVED=()
ROUTE_NOTES=()

# ---------------------------------------------------------------------------
# say / say_always — say() is silenced by --quiet, say_always() never is.
# ---------------------------------------------------------------------------
say() { [[ "${QUIET}" -eq 1 ]] || printf '%s\n' "$*"; }
say_always() { printf '%s\n' "$*"; }

usage() {
    cat <<'USAGE'
Usage: scripts/ownership_precondition.sh [--scope <path-to-owned_paths.yaml>] [--quiet]

  --scope <path>   scope file to check (default: config/owned_paths.yaml)
  --quiet          suppress passing detail; refusals are always printed
  -h, --help       this text

Exit: 0 = every declared location can produce operator-owned files
      1 = at least one cannot, startup must not proceed
      2 = the check could not run (2 is NOT a pass)
USAGE
}

# ---------------------------------------------------------------------------
# cannot_run <reason...> — exit 2 with the reason named.
#
# Named, never bare: "could not run" without the cause sends the operator on a
# second diagnosis, which FR-010a exists to prevent.
# ---------------------------------------------------------------------------
cannot_run() {
    say_always "OWNERSHIP-PRECONDITION: CANNOT-RUN"
    local line
    for line in "$@"; do
        say_always "  - ${line}"
    done
    say_always "This check asserted NOTHING. It is not a pass — fix the cause above and re-run."
    exit "${EXIT_CANNOT_RUN}"
}

# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --scope)
                [[ $# -ge 2 ]] || cannot_run "--scope requires a path argument"
                SCOPE_ARG="$2"; shift 2 ;;
            --scope=*)
                SCOPE_ARG="${1#--scope=}"; shift ;;
            --quiet) QUIET=1; shift ;;
            -h|--help) usage; exit "${EXIT_OK}" ;;
            *)
                # An unrecognised flag means the caller asked for something
                # this script does not do. Ignoring it would silently run a
                # different check than the one requested.
                usage >&2
                cannot_run "unknown argument: $1"
                ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# resolve_runtime — decide whether a container runtime is available for P1.
#
# The distinction between UNSET and EMPTY is load-bearing and is the project's
# own convention: start.sh sets CONTAINER_RUNTIME="" precisely to mean "none
# found" and refuses on that value. Re-detecting podman behind an explicitly
# empty value would ignore a decision the caller already made — and would make
# this script launch real containers from contexts (the unit suite, the
# pre-build gate) that deliberately declare there is no runtime.
# Echoes the runtime command, or nothing when there is none.
# ---------------------------------------------------------------------------
resolve_runtime() {
    if [[ "${CONTAINER_RUNTIME+set}" == "set" && -z "${CONTAINER_RUNTIME}" ]]; then
        return 0   # explicitly declared absent
    fi
    if [[ -n "${CONTAINER_RUNTIME:-}" ]]; then
        printf '%s\n' "${CONTAINER_RUNTIME}"
        return 0
    fi
    local cand
    for cand in podman docker; do
        if command -v "${cand}" >/dev/null 2>&1; then
            printf '%s\n' "${cand}"
            return 0
        fi
    done
    return 0
}

# ---------------------------------------------------------------------------
# detect_rootless <runtime> — MEASURE whether the runtime is rootless.
#
# Echoes exactly one of:  rootless | rootful | unknown:<reason>
#
# WHY MEASURED AND NOT ASSUMED (§11.4.201, §11.4.6):
#   "podman means rootless" is a GUESS. Podman runs rootful when invoked by
#   root, and Docker runs rootless when installed in rootless mode — so the
#   runtime's NAME is a proxy for the condition, not the condition. The real
#   condition is what the daemon/engine reports about itself, so that is what
#   is read. Field names were READ FROM REAL OUTPUT on this host (2026-08-21),
#   never guessed:
#     podman -> `.Host.Security.Rootless`, a bool; measured `true` here.
#     docker -> `.SecurityOptions`, a []string carrying the standalone token
#               `name=rootless` in rootless mode. HONEST GAP (§11.4.6): docker
#               is NOT INSTALLED on the host where this was authored, so the
#               docker branch is written from Docker's documented rootless
#               indicator and is UNMEASURED here. It is deliberately built to
#               fail toward `unknown` (a named skip) rather than toward a
#               confident `rootful`, so an unverified reading can never
#               manufacture a refusal.
#
# WHY EVERY AMBIGUITY BECOMES `unknown`, NEVER `rootful` (§11.4.201(1)/(6)):
#   A refusal is only earned by a POSITIVE reading that the runtime is rootful.
#   A failed command, an unparseable value, an empty option list or an
#   unrecognised runtime are all the instrument failing to see — and a blind
#   instrument and a genuinely-rootful engine return the same quiet nothing.
#   Reading that silence as "rootful" would refuse healthy hosts; reading it as
#   "rootless" would wave through the very case this exists to catch. It is
#   therefore reported as neither.
# ---------------------------------------------------------------------------
detect_rootless() {
    local runtime="$1"
    [[ -n "${runtime}" ]] || { printf 'unknown:no_container_runtime\n'; return 0; }

    local base out="" rc=0 line field
    base="$(basename -- "${runtime}")"

    case "${base}" in
        podman)
            # `timeout` wraps a real binary here, never a shell function, so the
            # §11.4.201(12) exec-wrapper footgun (rc=127 on a function) cannot
            # arise; and no background watchdog subshell is spawned inside this
            # command substitution, so it cannot stall on an orphaned sleep.
            out="$(timeout 30 "${runtime}" info --format '{{.Host.Security.Rootless}}' 2>/dev/null)" || rc=$?
            if [[ "${rc}" -ne 0 ]]; then
                printf 'unknown:podman_info_failed(exit %s)\n' "${rc}"
                return 0
            fi
            case "$(printf '%s' "${out}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')" in
                true)  printf 'rootless\n' ;;
                false) printf 'rootful\n' ;;
                *)     printf 'unknown:podman_rootless_field_unrecognised(%s)\n' \
                              "$(printf '%s' "${out}" | tr '\n' ' ' | cut -c1-60)" ;;
            esac
            return 0
            ;;
        docker)
            out="$(timeout 30 "${runtime}" info --format '{{range .SecurityOptions}}{{println .}}{{end}}' 2>/dev/null)" || rc=$?
            if [[ "${rc}" -ne 0 ]]; then
                printf 'unknown:docker_info_failed(exit %s)\n' "${rc}"
                return 0
            fi
            if [[ -z "${out//[[:space:]]/}" ]]; then
                # An engine that reported NO security options told us nothing.
                printf 'unknown:docker_security_options_empty\n'
                return 0
            fi
            # Structural match on a comma-separated FIELD, never a substring:
            # a profile path containing the word "rootless" must not read as
            # the `name=rootless` marker.
            while IFS= read -r line; do
                [[ -n "${line}" ]] || continue
                local IFS_SAVE="${IFS}"
                IFS=','
                # shellcheck disable=SC2206
                local fields=(${line})
                IFS="${IFS_SAVE}"
                for field in "${fields[@]:-}"; do
                    if [[ "${field//[[:space:]]/}" == "name=rootless" ]]; then
                        printf 'rootless\n'
                        return 0
                    fi
                done
            done <<< "${out}"
            printf 'rootful\n'
            return 0
            ;;
        *)
            printf 'unknown:unrecognised_runtime(%s)\n' "${base}"
            return 0
            ;;
    esac
}

# ---------------------------------------------------------------------------
# puid_zero_services — names of compose services that declare PUID=0.
#
# Prints nothing when there are none (an empty line would read as one unnamed
# service). Read from the already-parsed COMPOSE_ROWS so the PUID value comes
# from a YAML parse, never a grep: a comment mentioning PUID=0 is not a
# declaration.
# ---------------------------------------------------------------------------
puid_zero_services() {
    local row svc puid
    local -a found=()
    [[ -n "${COMPOSE_ROWS}" ]] || return 0
    while IFS= read -r row; do
        [[ -n "${row}" ]] || continue
        split_tsv "${row}"
        svc="${TSV_FIELDS[0]:-}"; puid="${TSV_FIELDS[3]:-}"
        [[ -n "${svc}" ]] || continue
        if [[ "${puid}" == "0" ]]; then
            found+=("${svc}")
        fi
    done <<< "${COMPOSE_ROWS}"
    [[ "${#found[@]}" -gt 0 ]] || return 0
    printf '%s\n' "${found[@]}"
}

# ---------------------------------------------------------------------------
# assert_rootless_runtime — refuse to let PUID=0 take effect on a ROOTFUL
# runtime (§11.4.252 fail-closed on a dangerous combination).
#
# ── WHY THIS IS A REFUSAL TRIGGER AND A ROUTE READING IS NOT ────────────────
#   The header warns that a route assertion must never refuse, because it
#   INFERS ownership from configuration. This check is a different kind: it
#   does not infer anything about ownership from the compose file — it MEASURES
#   the runtime (detect_rootless) and combines that measurement with a parsed
#   fact (a service declares PUID=0). The harm it prevents is also different:
#   not "files land at the wrong uid" but "the application runs as GENUINE host
#   root". Under rootless podman container uid 0 IS the unprivileged operator,
#   which is the entire basis for PUID=0. Under a ROOTFUL runtime that premise
#   is false: container uid 0 is real host root, and PUID=0 would run the
#   linuxserver app as root writing into the bind-mounted ./config — which
#   holds the encrypted credential store — and into the download tree as uid 0.
#   That is STRICTLY WORSE than the PUID=1000 this feature replaced, which at
#   least ran unprivileged. So the compose comment's no-privilege claim is
#   CONDITIONAL on rootlessness, and this is the check that enforces the
#   condition instead of asserting the conclusion.
#
# ── WHY IT RUNS BEFORE THE PROBES ──────────────────────────────────────────
#   p1_probe launches a container with `--user <PUID>`. On a rootful runtime
#   with PUID=0 that probe would itself create a ROOT-OWNED file inside a
#   declared location and then fail to remove it as the operator. The check
#   that exists to prevent root writes must not perform one first.
#
# ── WHY IT REFUSES ONLY WHEN PUID=0 IS ACTUALLY DECLARED ───────────────────
#   A rootful runtime is not, by itself, this feature's business. The dangerous
#   COMBINATION is rootful + PUID=0. Refusing a rootful host that declares no
#   PUID=0 anywhere would be the §11.4.201(1) false-positive refusal, so the
#   trigger is the combination, and the refusal names both halves.
# ---------------------------------------------------------------------------
assert_rootless_runtime() {
    local verdict
    verdict="$(detect_rootless "${RUNTIME}")"

    local -a puid0=()
    readarray -t puid0 < <(puid_zero_services)

    case "${verdict}" in
        rootless)
            say "  runtime: ${RUNTIME} measured ROOTLESS — container uid 0 is the operator, PUID=0 grants no host privilege"
            return 0
            ;;
        rootful)
            if [[ "${#puid0[@]}" -eq 0 ]]; then
                # Measured rootful, but nothing declares PUID=0, so the
                # dangerous combination does not exist. Said out loud rather
                # than passed in silence.
                say_always "  runtime: ${RUNTIME} measured ROOTFUL, but no compose service declares PUID=0 — nothing to refuse"
                return 0
            fi
            say_always "OWNERSHIP-PRECONDITION: FAIL"
            say_always "  - runtime ${RUNTIME} measured ROOTFUL, and these service(s) declare PUID=0: ${puid0[*]}"
            say_always "    Under a rootful runtime container uid 0 is REAL HOST ROOT — not the"
            say_always "    unprivileged operator it is under rootless podman. PUID=0 would run"
            say_always "    the application as genuine root, writing into the bind-mounted"
            say_always "    ./config (which holds the encrypted credential store) and into the"
            say_always "    download tree as uid 0. That is strictly worse than the PUID=1000"
            say_always "    this feature replaced, so startup is refused rather than allowed to"
            say_always "    silently escalate."
            say_always "    Fix by running the stack rootless (§11.4.161 — podman as the"
            say_always "    operator, or docker in rootless mode), which is what PUID=0 assumes."
            say_always "Startup refused."
            exit "${EXIT_REFUSE}"
            ;;
        *)
            # unknown:<reason> — a NAMED, honest skip. Not a pass (nothing was
            # asserted) and not a refusal (nothing was observed). Printed even
            # under --quiet: a safety assertion that did not run is not good
            # news, and --quiet only hides good news.
            say_always "  rootless assertion: SKIP (${verdict#unknown:})"
            if [[ "${#puid0[@]}" -gt 0 ]]; then
                say_always "    ${#puid0[@]} service(s) declare PUID=0 (${puid0[*]}), and PUID=0 is safe"
                say_always "    ONLY on a rootless runtime. Rootlessness could NOT be determined"
                say_always "    here, so this run asserts NOTHING about it — it neither confirms"
                say_always "    the runtime is safe nor observes that it is not."
            fi
            return 0
            ;;
    esac
}

# ---------------------------------------------------------------------------
# compose_routes — emit one TAB-separated row per compose service:
#     <service>\t<image>\t<userns_mode>\t<PUID>\t<mount-src,mount-src,...>
#
# Read from docker-compose.yml because that file IS the E5 route declaration.
# Returns non-zero when the file is missing or unreadable; the caller reports
# that as "no route information", never as "no route declared" — an unread file
# and a file declaring nothing are different findings (§11.4.201(6)).
# ---------------------------------------------------------------------------
compose_routes() {
    local py
    [[ -f "${COMPOSE_FILE}" ]] || return 1
    py="$(ownership_python)" || return 1
    "${py}" - "${PROJECT_ROOT}" "${COMPOSE_FILE}" <<'PYEOF'
import os, re, sys, yaml

root, compose = sys.argv[1], sys.argv[2]
try:
    doc = yaml.safe_load(open(compose)) or {}
except Exception as exc:                       # unreadable/unparseable compose
    print("compose: %s" % exc, file=sys.stderr)
    sys.exit(1)

def expand(value):
    def sub(m):
        var, dflt = m.group(1), m.group(3)
        return os.environ.get(var) or (dflt if dflt is not None else "")
    return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}', sub, str(value))

def norm(path):
    if not path:
        return ""
    if not os.path.isabs(path):
        path = os.path.join(root, path)
    return os.path.normpath(path)

for name, svc in (doc.get("services") or {}).items():
    if not isinstance(svc, dict):
        continue
    image  = expand(svc.get("image") or "")
    userns = expand(svc.get("userns_mode") or "")

    puid = ""
    env = svc.get("environment") or []
    pairs = env.items() if isinstance(env, dict) else [
        tuple(str(e).split("=", 1)) for e in env
    ]
    for kv in pairs:
        if len(kv) == 2 and str(kv[0]).strip() == "PUID":
            puid = expand(kv[1]).strip()

    sources = []
    for vol in (svc.get("volumes") or []):
        if isinstance(vol, dict):
            src = expand(vol.get("source", ""))
        else:
            # Expand BEFORE splitting: a `${VAR:-/mnt/DATA}:/downloads` entry
            # carries a colon inside the placeholder, so splitting first would
            # tear the default value in half and yield a bogus mount source.
            src = expand(vol).split(":")[0]
        src = norm(src)
        if src:
            sources.append(src)

    print("\t".join([name, image, userns, puid, ",".join(sources)]))
PYEOF
}

# ---------------------------------------------------------------------------
# split_tsv <line> — fill the array TSV_FIELDS with the line's TAB-separated
# fields, EMPTY FIELDS PRESERVED.
#
# WHY NOT `IFS=$'\t' read -r a b c d e`: TAB is an IFS *whitespace* character,
# so bash collapses a RUN of tabs into ONE delimiter. A row whose middle fields
# are empty — a compose service built from a Dockerfile has no `image:`, and a
# route-A service has no PUID, so its row is `name\t\t\t\t<mounts>` — then
# shifts every later field to the left and the mounts column reads as EMPTY.
# MEASURED on this repository's own docker-compose.yml (2026-08-21): the first
# version of this script used the collapsing read and reported "no compose
# service mounts this location" for `config/` and for the download root while
# five services mount them. That is a false statement about what was checked
# (§11.4.6), produced by the instrument rather than the system — exactly the
# §11.4.201(7)(c) "the path is part of the instrument" failure. The fixture
# scope in the unit suite has no compose service at all, so the suite cannot
# see this: only running the real invocation against the real scope did.
# ---------------------------------------------------------------------------
split_tsv() {
    TSV_FIELDS=()
    readarray -d $'\t' -t TSV_FIELDS < <(printf '%s' "$1")
}

# ---------------------------------------------------------------------------
# path_related <a> <b> — true when a write inside one lands inside the other.
#
# Containment is checked in BOTH directions on purpose: a service that mounts
# an ancestor of a declared location writes into it, and a service that mounts
# a subdirectory of a declared location also writes into it. Matching only one
# direction would silently drop half the services that can produce files there.
# ---------------------------------------------------------------------------
path_related() {
    local a="$1" b="$2"
    [[ -n "${a}" && -n "${b}" ]] || return 1
    [[ "${a}" == "${b}" || "${a}" == "${b}"/* || "${b}" == "${a}"/* ]]
}

# ---------------------------------------------------------------------------
# absolutise <path> — declared paths may be repo-relative (E1 allows both).
# ---------------------------------------------------------------------------
absolutise() {
    local p="$1"
    [[ "${p}" == /* ]] || p="${PROJECT_ROOT}/${p}"
    printf '%s\n' "${p%/}"
}

# ---------------------------------------------------------------------------
# route_for <abs-path> — describe the declared ownership route of every compose
# service that writes into this location. Report-only (see the header note on
# why a route reading never refuses on its own).
# ---------------------------------------------------------------------------
route_for() {
    local target="$1" svc image userns puid mounts src found=0
    if [[ -z "${COMPOSE_ROWS}" ]]; then
        printf '%s\n' "route information unavailable (${COMPOSE_STATUS})"
        return 0
    fi
    local row
    while IFS= read -r row; do
        [[ -n "${row}" ]] || continue
        split_tsv "${row}"
        svc="${TSV_FIELDS[0]:-}"; image="${TSV_FIELDS[1]:-}"
        userns="${TSV_FIELDS[2]:-}"; puid="${TSV_FIELDS[3]:-}"
        mounts="${TSV_FIELDS[4]:-}"
        [[ -n "${svc}" ]] || continue
        local IFS_SAVE="${IFS}"
        IFS=','
        # shellcheck disable=SC2206
        local srcs=(${mounts})
        IFS="${IFS_SAVE}"
        for src in "${srcs[@]:-}"; do
            if path_related "${target}" "${src}"; then
                found=1
                if [[ "${userns}" == "keep-id" ]]; then
                    printf '%s\n' "${svc}: route A declared (userns_mode: keep-id)"
                elif [[ "${puid}" == "0" ]]; then
                    printf '%s\n' "${svc}: route B declared (PUID=0)"
                else
                    printf '%s\n' "${svc}: NO route declared (neither userns_mode: keep-id nor PUID=0)"
                fi
                break
            fi
        done
    done <<< "${COMPOSE_ROWS}"
    [[ "${found}" -eq 1 ]] || printf '%s\n' "no compose service mounts this location — no route to assert"
}

# ---------------------------------------------------------------------------
# p1_probe <abs-dir> — the container-write probe: the only probe that can
# observe the real defect.
#
# Echoes "ok", "wrong-owner:<uid>", or "skip:<reason>". Return 0 for ok, 1 for
# a real wrong-owner observation, 2 for a skip.
#
# EVERY failure OF THE PROBE ITSELF (missing runtime, no local image, no
# declared route to reproduce, runtime error) is a SKIP with a named reason,
# never a refusal: the probe not running is not evidence that the location is
# broken, and refusing on it would refuse healthy hosts (§11.4.201(1)). Only a
# probe file that really appeared with the wrong owner refuses.
# ---------------------------------------------------------------------------
p1_probe() {
    local dir="$1"
    local svc image userns puid mounts src
    local use_svc="" use_image="" use_userns="" use_puid="" matched=0

    [[ -n "${RUNTIME}" ]] || { printf 'skip:runtime_unavailable\n'; return 2; }
    [[ -n "${COMPOSE_ROWS}" ]] || { printf 'skip:route_unavailable\n'; return 2; }

    # Reproduce the identity the SERVICE is declared to use — never a guessed
    # uid. A guessed identity would answer a question nobody asked.
    local row
    while IFS= read -r row; do
        [[ -n "${row}" ]] || continue
        split_tsv "${row}"
        svc="${TSV_FIELDS[0]:-}"; image="${TSV_FIELDS[1]:-}"
        userns="${TSV_FIELDS[2]:-}"; puid="${TSV_FIELDS[3]:-}"
        mounts="${TSV_FIELDS[4]:-}"
        [[ -n "${svc}" ]] || continue
        local IFS_SAVE="${IFS}"
        IFS=','
        # shellcheck disable=SC2206
        local srcs=(${mounts})
        IFS="${IFS_SAVE}"
        for src in "${srcs[@]:-}"; do
            if path_related "${dir}" "${src}"; then
                matched=1
                # Only a service with a pullable-free, locally-present image can
                # be reproduced without a network pull at startup time.
                if [[ -n "${image}" ]] && "${RUNTIME}" image exists "${image}" >/dev/null 2>&1; then
                    use_svc="${svc}"; use_image="${image}"
                    use_userns="${userns}"; use_puid="${puid}"
                fi
                break
            fi
        done
        [[ -n "${use_image}" ]] && break
    done <<< "${COMPOSE_ROWS}"

    [[ "${matched}" -eq 1 ]] || { printf 'skip:route_undeclared\n'; return 2; }
    [[ -n "${use_image}" ]] || { printf 'skip:service_image_unavailable\n'; return 2; }

    local marker=".ownership-probe-p1.$$.$RANDOM"
    local args=(run --rm --network=none)
    [[ -n "${use_userns}" ]] && args+=("--userns=${use_userns}")
    [[ -n "${use_puid}" ]] && args+=(--user "${use_puid}")
    # The image's own entrypoint is bypassed on purpose: the probe must perform
    # a bare write, not boot the service.
    args+=(--entrypoint /bin/sh -v "${dir}:/ownership-probe:z" "${use_image}"
           -c "touch /ownership-probe/${marker}")

    local err
    err="$(timeout 120 "${RUNTIME}" "${args[@]}" 2>&1 >/dev/null)" || {
        rm -f "${dir}/${marker}" 2>/dev/null || true
        printf 'skip:probe_container_failed(%s: %s)\n' "${use_svc}" "$(printf '%s' "${err}" | tr '\n' ' ' | cut -c1-120)"
        return 2
    }

    local got want
    want="$(ownership_operator_uid)"
    got="$(stat -c '%u' "${dir}/${marker}" 2>/dev/null || true)"
    rm -f "${dir}/${marker}" 2>/dev/null || true
    if [[ -z "${got}" ]]; then
        # The container reported success but nothing landed on the host — the
        # probe observed nothing, so it asserts nothing.
        printf 'skip:probe_file_not_found(%s)\n' "${use_svc}"
        return 2
    fi
    if [[ "${got}" == "${want}" ]]; then
        printf 'ok:%s\n' "${use_svc}"
        return 0
    fi
    printf 'wrong-owner:%s:%s\n' "${got}" "${use_svc}"
    return 1
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
    parse_args "$@"

    # --scope wins over the environment. Exported because the shared library
    # reads OWNED_PATHS_FILE — this is the library's documented override, not a
    # private backdoor.
    if [[ -n "${SCOPE_ARG}" ]]; then
        export OWNED_PATHS_FILE="${SCOPE_ARG}"
    fi
    local scope
    scope="$(ownership_scope_file)"

    # A scope that cannot be read is NOT an empty scope. ownership_scope_entries
    # returns 2 for "could not read" and its parser exits non-zero on malformed
    # YAML; both mean this check asserted nothing, so both are exit 2.
    local entries rc=0
    entries="$(ownership_scope_entries 2>/dev/null)" || rc=$?
    if [[ "${rc}" -ne 0 ]]; then
        cannot_run \
            "the declared scope could not be read: ${scope}" \
            "cause: missing file, malformed YAML, or no python3 with PyYAML (reader exit ${rc})" \
            "this is a BLIND read, not an empty scope"
    fi
    if [[ -z "${entries//[[:space:]]/}" ]]; then
        cannot_run \
            "the declared scope contains no locations: ${scope}" \
            "a precondition that checked zero locations has verified nothing"
    fi

    RUNTIME="$(resolve_runtime)"
    COMPOSE_ROWS=""
    COMPOSE_STATUS=""
    if COMPOSE_ROWS="$(compose_routes 2>/dev/null)"; then
        COMPOSE_STATUS="read from docker-compose.yml"
    else
        COMPOSE_ROWS=""
        COMPOSE_STATUS="docker-compose.yml missing or unparseable — routes NOT read"
    fi

    local operator_uid
    operator_uid="$(ownership_operator_uid)"
    say "Ownership precondition: scope ${scope}, operator uid ${operator_uid}"

    # BEFORE any probe: p1_probe launches a container with `--user <PUID>`, so
    # on a rootful runtime with PUID=0 it would create a root-owned file inside
    # a declared location. The check that exists to prevent root writes must
    # not perform one first. Refuses (exit 1) on rootful + PUID=0; otherwise
    # returns, having either confirmed rootless or named an honest skip.
    assert_rootless_runtime

    # Row shape (scripts/lib/ownership.sh):
    #   <path>\t<kind>\t<optional>\t<preserve_mode>\t<recursive>
    # preserve_mode and recursive belong to the repair, not to this check, and
    # are deliberately not read here. split_tsv is used rather than a
    # tab-delimited `read` for the empty-field reason documented on that helper:
    # an entry that omits `kind` would otherwise shift `optional` out of place
    # and silently change which absences count as errors.
    local row path kind optional abs verdict prc p1 p1rc
    while IFS= read -r row; do
        [[ -n "${row}" ]] || continue
        split_tsv "${row}"
        path="${TSV_FIELDS[0]:-}"; kind="${TSV_FIELDS[1]:-}"
        optional="${TSV_FIELDS[2]:-0}"
        [[ -n "${path}" ]] || continue
        abs="$(absolutise "${path}")"

        # ---- P2: the host-write probe (necessary, never sufficient) --------
        if verdict="$(probe_location "${abs}")"; then prc=0; else prc=$?; fi

        case "${verdict}" in
            ok)
                : ;;
            absent)
                if [[ "${optional}" == "1" ]]; then
                    # E1: an absent OPTIONAL path is not an error. This is the
                    # negative control the whole check must not trip over —
                    # config/boba.db is exactly this shape before first boot.
                    say "  - ${abs}: absent, declared optional — not a failure"
                    continue
                fi
                FAILURES+=("${abs}: declared (kind=${kind}) but ABSENT, and it is not marked optional — E1 makes an absent non-optional path an error, not a skip")
                continue ;;
            unwritable)
                FAILURES+=("${abs}: P2 host-write probe could not create a file there (unwritable, or the owner does not resolve) — the location is unusable regardless of P1")
                continue ;;
            wrong-owner:*)
                FAILURES+=("${abs}: P2 host-write probe created a file owned by uid ${verdict#wrong-owner:}, expected ${operator_uid}")
                continue ;;
            *)
                FAILURES+=("${abs}: probe returned an unrecognised verdict '${verdict}' (rc=${prc}) — unrecognised is not clean")
                continue ;;
        esac

        # ---- Declared FILES have no write to probe ------------------------
        # The contract carves this out: reading the target's own owner IS the
        # real condition for a file, not a proxy for it. Creating something
        # beside it would answer a question about its parent directory.
        if [[ -f "${abs}" ]]; then
            say "  - ${abs}: OK (declared file, owned by uid ${operator_uid}; no write probe applies)"
            continue
        fi

        # ---- P1: the container-write probe (the real condition) -----------
        if p1="$(p1_probe "${abs}")"; then p1rc=0; else p1rc=$?; fi
        case "${p1}" in
            ok:*)
                P1_OBSERVED+=("${abs}: a write from inside the ${p1#ok:} container landed at uid ${operator_uid}")
                say "  - ${abs}: OK (P2 host write and P1 in-container write both landed at uid ${operator_uid})" ;;
            wrong-owner:*)
                local rest="${p1#wrong-owner:}"
                FAILURES+=("${abs}: a write performed inside the ${rest#*:} container landed at uid ${rest%%:*}, expected ${operator_uid} — this is the condition FR-010 names")
                continue ;;
            skip:*)
                P1_SKIPS+=("${abs}|${p1#skip:}")
                # Single-character delimiter on purpose: paste -d takes a
                # CYCLING list, so a two-character "; " would alternate the two
                # separators between lines instead of joining with both.
                ROUTE_NOTES+=("${abs}|$(route_for "${abs}" | paste -sd ';' -)")
                say "  - ${abs}: P2 host write landed at uid ${operator_uid}; P1 not run (${p1#skip:}) — see the probe-coverage report below" ;;
            *)
                FAILURES+=("${abs}: P1 returned an unrecognised verdict '${p1}' (rc=${p1rc})")
                continue ;;
        esac
    done <<< "${entries}"

    # ---- Probe-coverage report: what was NOT checked, said out loud -------
    # Always printed, --quiet included. Hiding the fact that the probe which
    # observes the real defect never ran is precisely the bluff finding X1 was
    # raised for.
    if [[ "${#P1_SKIPS[@]}" -gt 0 ]]; then
        say_always "Probe coverage:"
        local entry loc reason
        for entry in "${P1_SKIPS[@]}"; do
            loc="${entry%%|*}"; reason="${entry#*|}"
            say_always "  P1: SKIP (${reason}) for ${loc}"
        done
        say_always "  P1 is the probe that writes from inside a throwaway container as the"
        say_always "  service's declared identity, and it is the only one that reproduces the"
        say_always "  reported defect. It did not run for the locations above, so NOTHING here"
        say_always "  asserts that a service write would land at uid ${operator_uid}."
        say_always "  Fallback used instead: the per-service ownership route declared in"
        say_always "  docker-compose.yml. A route assertion verifies CONFIGURATION, not"
        say_always "  BEHAVIOUR — it reports what the compose file asks for, never what a"
        say_always "  service write actually produces on disk."
        for entry in "${ROUTE_NOTES[@]:-}"; do
            [[ -n "${entry}" ]] || continue
            loc="${entry%%|*}"; reason="${entry#*|}"
            say_always "    route for ${loc}: ${reason}"
        done
    fi

    if [[ "${#FAILURES[@]}" -gt 0 ]]; then
        say_always "OWNERSHIP-PRECONDITION: FAIL"
        local f
        for f in "${FAILURES[@]}"; do
            say_always "  - ${f}"
        done
        say_always "Startup refused. Fix the location(s) above, or run scripts/ownership_repair.sh."
        exit "${EXIT_REFUSE}"
    fi

    say "OWNERSHIP-PRECONDITION: OK"
    exit "${EXIT_OK}"
}

main "$@"
