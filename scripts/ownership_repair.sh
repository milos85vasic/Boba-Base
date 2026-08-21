#!/usr/bin/env bash
# scripts/ownership_repair.sh — bring pre-existing content under the operator's
# ownership (feature 002-user-owned-downloads, T019/T020/T021/T022/T023).
#
# Purpose:
#   Walk every location declared in the ownership scope (config/owned_paths.yaml)
#   and chown every item that is NOT owned by the operator back to the operator's
#   uid:gid. Each change is written to the change record BEFORE it is applied, and
#   the completion marker is written ONLY after a fully successful pass so an
#   interrupted run resumes instead of being silently marked done.
#
# Usage:
#   scripts/ownership_repair.sh                  # normal run; no-op if the marker is valid
#   scripts/ownership_repair.sh --force          # ignore the marker and re-walk
#   scripts/ownership_repair.sh --dry-run        # report what would change; change nothing
#   scripts/ownership_repair.sh --scope <path>   # override the declared scope file
#
# Inputs:
#   config/owned_paths.yaml   the declared scope (E1). Overridable by --scope or
#                             the OWNED_PATHS_FILE environment variable.
#   CONTAINER_RUNTIME         optional. SET-BUT-EMPTY means "no container runtime
#                             is available" and suppresses the `<runtime> unshare`
#                             fallback entirely. UNSET means "detect one".
#
# Outputs:
#   stdout                                 progress (items processed / discovered)
#   logs/ownership/repair-changes.ndjson   the E3 change record (append-only)
#   logs/ownership/repair-marker.json      the E2 completion marker
#   exit 0                                 every in-scope item is operator-owned
#   exit 1                                 at least one item could not be repaired
#                                          (each one named individually)
#   exit 2                                 could not run (scope missing/unparseable,
#                                          or the state directory is unwritable)
#
# Side-effects:
#   chown(2) on in-scope items only. Never chmod, EXCEPT restoring an item's own
#   original bits after a chown that could have cleared its setuid/setgid bits
#   (see "MODE IS NEVER WIDENED" below). Creates logs/ownership/.
#
# Dependencies:
#   bash 4+, coreutils (find, chown, chmod, mktemp, sha256sum, date, tr, wc),
#   scripts/lib/ownership.sh, python3 with PyYAML (used by the shared scope parser).
#
# Cross-references:
#   specs/002-user-owned-downloads/contracts/repair-cli.md
#   specs/002-user-owned-downloads/data-model.md  (E1 scope, E2 marker, E3 record)
#   tests/unit/test_ownership_repair.sh
#   scripts/lib/ownership.sh
#
# ---------------------------------------------------------------------------
# WHY THE MARKER IS WRITTEN LAST AND NOWHERE ELSE (data-model E2)
#   Writing it at START would let a single interruption mark the repair "done"
#   forever, so the remainder is silently skipped — the run-once optimisation
#   would defeat the repair it optimises. The marker therefore exists only as
#   the LAST act of a fully successful pass: interrupted ⇒ absent ⇒ next start
#   resumes. This is also the operator's escape hatch from a long run.
#
# WHY THE MARKER CARRIES THE SCOPE FINGERPRINT
#   A marker keyed on mere existence would report "already done" about work that
#   was never performed the moment a NEW path is declared. Keying it on the
#   sha256 of the sorted scope re-arms the repair whenever the scope changes.
#
# WHY RECORDS PRECEDE MUTATION (FR-004b)
#   The record is the operator's recovery trail for an automatic repair they did
#   not individually approve. A record written AFTER the chown is lost exactly
#   when it matters — a crash mid-repair. So a batch's records are flushed to
#   disk first and the chown follows. The recorded `outcome` is therefore the
#   INTENT ("changed"); if the mutation then fails, a corrective `failed` entry
#   is appended for that path. Claiming success we have not yet earned would be
#   the bluff §11.4/§11.4.1 forbids, so the failure is recorded, not swallowed.
#
# WHY PRESERVE_MODE ENTRIES ARE PROCESSED FIRST
#   The real scope nests: `config/boba.db` (preserve_mode) lives inside `config/`
#   (not preserve_mode). Whichever entry reaches an item first is the one whose
#   rules apply — and after that item is repaired it no longer matches the
#   wrongly-owned filter, so the later entry never sees it. Ordering the strictest
#   constraint first therefore makes the strictest rule win AND gives exactly one
#   change-record entry per altered item, with no cross-entry deduplication pass.
#
# MODE IS NEVER WIDENED (FR-015)
#   This script does not change permission bits as a goal. The one way bits could
#   move is chown(2) itself: a non-root chown clears setuid/setgid. So the original
#   bits are restored after the chown when the entry is `preserve_mode`, or when
#   the item actually carried special bits (a 4-digit octal mode). A credential
#   store brought under the operator while widening who can read it would trade a
#   usability defect for a security one — strictly worse than the defect.
#
# WHY chown -h
#   `-h` acts on a symlink itself rather than its target. Without it a symlink
#   inside the declared scope pointing anywhere on the filesystem would let the
#   repair mutate a file OUTSIDE the scope — FR-005 requires out-of-scope reach to
#   be impossible by construction, not merely unintended.

set -euo pipefail

# ---------------------------------------------------------------------------
# Host-safety re-exec (contract: runs under nice -n 19 / ionice -c 3).
#
# Done here rather than left to every caller so a repair started from boot, from
# a script, or by hand is equally incapable of starving the operator's session.
# `exec` keeps the same pid, so a supervisor that captured this pid can still
# signal it. Guarded by an env flag so the re-exec happens exactly once, and
# skipped entirely when either tool is absent rather than dying on it.
# ---------------------------------------------------------------------------
if [[ -z "${OWNERSHIP_REPAIR_RENICED:-}" ]]; then
    export OWNERSHIP_REPAIR_RENICED=1
    if command -v nice >/dev/null 2>&1 && command -v ionice >/dev/null 2>&1; then
        exec nice -n 19 ionice -c 3 bash "${BASH_SOURCE[0]}" "$@"
    fi
fi

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/ownership.sh disable=SC1091
source "${SELF_DIR}/lib/ownership.sh"
# ownership.sh calls `set -uo pipefail` at source time; re-assert our own option
# set so the sourced file can never silently relax this script's error handling.
set -euo pipefail

PROJECT_ROOT="$(ownership_project_root)"

# ---------------------------------------------------------------------------
# T021 — change-record and marker location (deferred from clarify by design).
#
# `logs/ownership/` at the PROJECT ROOT, because:
#   * operator-readable and on the HOST — the project root is not a container
#     path, so the record never lives only inside a container (E3 rule);
#   * `logs/` is already gitignored, so an operational log never becomes an
#     untracked-file nuisance nor a §11.4.30 versioned-artifact violation, and
#     no .gitignore change is owed for it;
#   * NOT `docs/qa/` — that tree is curated QA evidence (§11.4.83) and is the
#     wrong home for an operational log (research.md R7 states this constraint);
#   * relative to the project root as resolved by ownership.sh, so a test or a
#     relocated checkout gets its own state rather than sharing the live one.
#
# Serialisation: NDJSON for the record (append-only, one E3 entry per line, greppable
# by path, parseable by any tool) and a small JSON object for the marker. Both hold
# paths, uids, gids and modes ONLY — never file contents, never credential values
# (§11.4.10). `boba.db` appears as a path; nothing of its contents ever does.
# ---------------------------------------------------------------------------
STATE_DIR="${PROJECT_ROOT}/logs/ownership"
RECORD_FILE="${STATE_DIR}/repair-changes.ndjson"
MARKER_FILE="${STATE_DIR}/repair-marker.json"

# Batch size for the record-then-chown cycle. Not a micro-optimisation knob: it
# is the width of the window in which records exist for items not yet mutated,
# traded against one fork per batch instead of one per item. 256 keeps a 100k-item
# tree to ~400 forks while keeping that window small enough to stay auditable.
BATCH_SIZE=256

FORCE=0
DRY_RUN=0

TMP_DIR=""

usage() {
    cat <<'USAGE'
Usage: scripts/ownership_repair.sh [--force] [--dry-run] [--scope <path>]

  --force          ignore a valid completion marker and re-walk the scope
  --dry-run        report what would change; change nothing, record nothing
  --scope <path>   override the declared scope file (config/owned_paths.yaml)
  -h, --help       this text

Exit codes: 0 every in-scope item is operator-owned; 1 at least one item could
not be repaired (named individually); 2 could not run.
USAGE
}

log_info() { printf '[ownership-repair] %s\n' "$*"; }
log_err()  { printf '[ownership-repair] %s\n' "$*" >&2; }

cleanup() {
    local rc=$?
    if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
        rm -rf "${TMP_DIR}"
    fi
    # Explicit exit with the captured status: an EXIT trap whose last command
    # fails must never be able to turn a failed run into a reported success.
    exit "${rc}"
}
trap cleanup EXIT
# An interrupted pass must die WITHOUT writing the marker (E2). The marker is the
# last act of main(), so these traps need only stop the run honestly.
trap 'log_err "interrupted (SIGTERM) — no marker written; the next run resumes"; exit 143' TERM
trap 'log_err "interrupted (SIGINT) — no marker written; the next run resumes";  exit 130' INT

# ---------------------------------------------------------------------------
# json_escape <string> — escape a value for a JSON string literal.
#
# Pure bash so it costs no fork per record. Covers the characters a filesystem
# path can actually carry into JSON: backslash, quote, and the control characters
# a shell would otherwise mangle.
# ---------------------------------------------------------------------------
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    printf '%s' "${s}"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)   FORCE=1;   shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --scope)
            if [[ $# -lt 2 ]]; then
                log_err "--scope requires a path"
                exit 2
            fi
            OWNED_PATHS_FILE="$2"
            export OWNED_PATHS_FILE
            shift 2
            ;;
        --scope=*)
            OWNED_PATHS_FILE="${1#--scope=}"
            export OWNED_PATHS_FILE
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *)
            log_err "unknown argument: $1"
            usage >&2
            exit 2
            ;;
    esac
done

OP_UID="$(ownership_operator_uid)"
OP_GID="$(ownership_operator_gid)"
SCOPE_FILE="$(ownership_scope_file)"

# ---------------------------------------------------------------------------
# Container runtime for the `unshare` fallback.
#
# The production defect is content at a rootless-podman SUBUID (e.g. 100999). An
# unprivileged chown cannot touch those — only re-entering the same user namespace
# can, where the host operator uid maps to uid 0. So the fallback is
# `<runtime> unshare chown 0:0`, and it runs ONLY after a plain chown has already
# failed: a run that needs no fallback never invokes the runtime at all.
#
# A SET-BUT-EMPTY CONTAINER_RUNTIME is honoured as "no runtime available" rather
# than re-detected. Gates run this script's suites; probing for a runtime there
# would be work the caller explicitly said not to do (§11.4.201 — assert the real
# condition the caller declared, not a proxy re-derived behind their back).
# ---------------------------------------------------------------------------
detect_runtime() {
    if [[ -n "${CONTAINER_RUNTIME+set}" ]]; then
        printf '%s' "${CONTAINER_RUNTIME}"
        return 0
    fi
    local cand
    for cand in podman docker; do
        if command -v "${cand}" >/dev/null 2>&1; then
            printf '%s' "${cand}"
            return 0
        fi
    done
    printf '%s' ""
}
RUNTIME="$(detect_runtime)"

# ---------------------------------------------------------------------------
# Scope. A scope that cannot be read is exit 2 — "could not run". Reporting an
# unreadable scope as an empty scope would be the §11.4.201(6) false-null: a
# blind instrument and a clean tree return the same quiet zero.
# ---------------------------------------------------------------------------
ENTRIES_RAW=""
if ! ENTRIES_RAW="$(ownership_scope_entries)"; then
    log_err "cannot read the declared scope: ${SCOPE_FILE}"
    log_err "refusing to guess a scope — nothing was touched"
    exit 2
fi

FINGERPRINT=""
if ! FINGERPRINT="$(ownership_scope_fingerprint)" || [[ -z "${FINGERPRINT}" ]]; then
    log_err "cannot compute the scope fingerprint from ${SCOPE_FILE}"
    exit 2
fi

# ---------------------------------------------------------------------------
# Entry table, preserve_mode first (see the header for why the order is load-bearing).
# ---------------------------------------------------------------------------
declare -a E_PATH=() E_KIND=() E_OPTIONAL=() E_PRESERVE=() E_RECURSIVE=()
while IFS=$'\t' read -r e_path e_kind e_opt e_pres e_rec; do
    [[ -n "${e_path}" ]] || continue
    E_PATH+=("${e_path}")
    E_KIND+=("${e_kind}")
    E_OPTIONAL+=("${e_opt}")
    E_PRESERVE+=("${e_pres}")
    E_RECURSIVE+=("${e_rec}")
done <<< "${ENTRIES_RAW}"

declare -a ORDER=()
for idx in "${!E_PATH[@]}"; do
    if [[ "${E_PRESERVE[${idx}]}" == "1" ]]; then
        ORDER+=("${idx}")
    fi
done
for idx in "${!E_PATH[@]}"; do
    if [[ "${E_PRESERVE[${idx}]}" != "1" ]]; then
        ORDER+=("${idx}")
    fi
done

# ---------------------------------------------------------------------------
# Marker
# ---------------------------------------------------------------------------
marker_is_valid() {
    [[ -f "${MARKER_FILE}" ]] || return 1
    grep -qF -- "\"scope_fingerprint\": \"${FINGERPRINT}\"" "${MARKER_FILE}"
}

marker_write() {
    local tmp
    tmp="$(mktemp "${STATE_DIR}/.repair-marker.XXXXXX")"
    printf '{\n  "completed_at": "%s",\n  "scope_fingerprint": "%s",\n  "items_changed": %d\n}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${FINGERPRINT}" "$1" > "${tmp}"
    # Atomic publish: a half-written marker read by the next start would be a
    # marker whose fingerprint field cannot be trusted.
    mv -f "${tmp}" "${MARKER_FILE}"
}

if [[ "${FORCE}" -eq 0 && "${DRY_RUN}" -eq 0 ]] && marker_is_valid; then
    log_info "already complete for this scope (marker: ${MARKER_FILE#"${PROJECT_ROOT}"/}) — nothing to do"
    exit 0
fi

# ---------------------------------------------------------------------------
# State directory + append-only change record.
# ---------------------------------------------------------------------------
# A dry run creates NOTHING — not even the state directory. "Change nothing"
# includes the filesystem side effects of getting ready to change something;
# a dry run that leaves a new directory behind has already changed the tree it
# claimed only to report on. Measured 2026-08-21: an earlier revision created
# logs/ownership/ under --dry-run, which the unit suite does not observe.
RECORD_FD_OPEN=0
if [[ "${DRY_RUN}" -eq 0 ]]; then
    if ! mkdir -p "${STATE_DIR}" 2>/dev/null; then
        log_err "cannot create the state directory: ${STATE_DIR}"
        log_err "the change record (FR-004b) cannot be written, so the repair does not start"
        exit 2
    fi
    if ! exec 3>>"${RECORD_FILE}"; then
        log_err "cannot open the change record for append: ${RECORD_FILE}"
        exit 2
    fi
    RECORD_FD_OPEN=1
fi

record_line() {
    # $1 path, $2 previous_uid, $3 previous_gid, $4 previous_mode, $5 outcome
    local esc
    esc="$(json_escape "$1")"
    printf '{"path":"%s","previous_uid":%s,"previous_gid":%s,"previous_mode":"%s","new_uid":%s,"new_gid":%s,"changed_at":"%s","outcome":"%s"}\n' \
        "${esc}" "$2" "$3" "$4" "${OP_UID}" "${OP_GID}" "${NOW}" "$5"
}

record_emit() {
    if [[ "${RECORD_FD_OPEN}" -eq 1 ]]; then
        record_line "$@" >&3
    fi
}

# record_absent <path> <outcome> — an entry for a DECLARED path that has no
# previous ownership state to record, because it does not exist.
#
# Every field is JSON `null` rather than a sentinel: `-1` is a plausible-looking
# uid and a later reader would have no way to tell a sentinel from a real one.
# `outcome` is the authoritative field here, and null says "nothing was known and
# nothing was applied" without inviting a misreading.
record_absent() {
    local esc
    if [[ "${RECORD_FD_OPEN}" -eq 1 ]]; then
        esc="$(json_escape "$1")"
        printf '{"path":"%s","previous_uid":null,"previous_gid":null,"previous_mode":null,"new_uid":null,"new_gid":null,"changed_at":"%s","outcome":"%s"}\n' \
            "${esc}" "${NOW}" "$2" >&3
    fi
}

# ---------------------------------------------------------------------------
# Ownership mutation
# ---------------------------------------------------------------------------

# chown_paths <paths…> — plain chown over a whole batch. Returns non-zero if any
# path failed; chown itself continues past individual failures.
chown_paths() {
    chown -h -- "${OP_UID}:${OP_GID}" "$@" 2>/dev/null
}

# unshare_chown_paths <paths…> — the namespace fallback. Inside `<runtime> unshare`
# the host operator uid IS uid 0, so 0:0 is what makes the item host-operator-owned.
unshare_chown_paths() {
    [[ -n "${RUNTIME}" ]] || return 1
    "${RUNTIME}" unshare chown -h -- 0:0 "$@" >/dev/null 2>&1
}

# repair_one <path> — plain first, namespace fallback second. Returns non-zero
# when neither can repair the item; the caller then names it individually.
repair_one() {
    if chown_paths "$1"; then
        return 0
    fi
    if unshare_chown_paths "$1"; then
        return 0
    fi
    return 1
}

# ---------------------------------------------------------------------------
# Main walk
# ---------------------------------------------------------------------------
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ownership_repair.XXXXXXXX")"
TMP_ITEMS="${TMP_DIR}/items"
TMP_ERR="${TMP_DIR}/find_err"

TOTAL_CHANGED=0
TOTAL_FAILED=0
RC=0
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ "${DRY_RUN}" -eq 1 ]]; then
    log_info "DRY RUN — nothing will be changed and nothing will be recorded"
fi
log_info "operator ${OP_UID}:${OP_GID}; scope ${SCOPE_FILE} (${#ORDER[@]} declared locations)"

# batch state
declare -a BATCH_PATHS=() BATCH_MODES=() BATCH_PUID=() BATCH_PGID=()
BATCH_BLOB=""
BATCH_RESTORE_MODE=0   # 1 when the CURRENT entry must have its bits restored

# flush_batch <entry-label> — records first, then the mutation (FR-004b).
flush_batch() {
    local label="$1" i p
    if [[ ${#BATCH_PATHS[@]} -eq 0 ]]; then
        return 0
    fi

    if [[ "${RECORD_FD_OPEN}" -eq 1 ]]; then
        printf '%s' "${BATCH_BLOB}" >&3
    fi

    if chown_paths "${BATCH_PATHS[@]}" || unshare_chown_paths "${BATCH_PATHS[@]}"; then
        TOTAL_CHANGED=$((TOTAL_CHANGED + ${#BATCH_PATHS[@]}))
    else
        # A batch failure does not say WHICH path failed, and FR-006 requires items
        # be listed individually — so degrade to per-path only for this batch.
        for i in "${!BATCH_PATHS[@]}"; do
            p="${BATCH_PATHS[${i}]}"
            if repair_one "${p}"; then
                TOTAL_CHANGED=$((TOTAL_CHANGED + 1))
            else
                TOTAL_FAILED=$((TOTAL_FAILED + 1))
                RC=1
                log_err "FAILED ${p} — cannot change ownership to ${OP_UID}:${OP_GID} (${label})"
                # `new_uid`/`new_gid` here are the identity that was ATTEMPTED;
                # `outcome: failed` is what says it was not applied.
                record_emit "${p}" "${BATCH_PUID[${i}]}" "${BATCH_PGID[${i}]}" "${BATCH_MODES[${i}]}" "failed"
            fi
        done
    fi

    # Restore bits chown could have cleared. Only for preserve_mode entries or
    # items that actually carried setuid/setgid/sticky bits, so the common case
    # costs nothing.
    for i in "${!BATCH_PATHS[@]}"; do
        if [[ "${BATCH_RESTORE_MODE}" -eq 1 || ${#BATCH_MODES[${i}]} -gt 3 ]]; then
            # NEVER chmod a symlink. `chmod` has no `-h` counterpart on Linux, so
            # it ALWAYS follows the link and changes the TARGET — and the target
            # may be outside the declared scope, which breaks the scope fence in
            # the one dimension `chown -h` does not cover.
            #
            # This is not theoretical; it was reproduced against this script:
            # a symlink's `find -printf '%m'` is 777, so "restoring its mode"
            # meant chmod 777 ON THE TARGET. With the shipped
            # config/owned_paths.yaml, whose ONLY preserve_mode entry is the
            # encrypted credential store config/boba.db, an operator who had
            # relocated that DB and symlinked it into config/ would have had the
            # real store go 600 -> 777. Measured: BEFORE 600, AFTER 777.
            #
            # That inverts FR-015, whose whole purpose is to never trade a
            # usability defect for a security one — so skipping symlinks here is
            # not a special case, it is the rule the fence already implies.
            # Nothing is lost: a symlink's own mode is meaningless on Linux
            # (always 777) and cannot be set, so the ONLY effect chmod could
            # ever have here is on the target, which is never what we want.
            [[ -L "${BATCH_PATHS[${i}]}" ]] && continue
            chmod "${BATCH_MODES[${i}]}" -- "${BATCH_PATHS[${i}]}" 2>/dev/null || true
        fi
    done

    BATCH_PATHS=()
    BATCH_MODES=()
    BATCH_PUID=()
    BATCH_PGID=()
    BATCH_BLOB=""
    return 0
}

entry_no=0
for idx in "${ORDER[@]}"; do
    entry_no=$((entry_no + 1))
    e_path="${E_PATH[${idx}]}"
    e_opt="${E_OPTIONAL[${idx}]}"
    e_pres="${E_PRESERVE[${idx}]}"
    e_rec="${E_RECURSIVE[${idx}]}"
    label="${entry_no}/${#ORDER[@]} ${e_path}"

    if [[ ! -e "${e_path}" ]]; then
        if [[ "${e_opt}" == "1" ]]; then
            log_info "${label}: absent, declared optional — skipped"
            record_absent "${e_path}" "skipped"
        else
            # E1: an absent NON-optional path is an error, not a skip.
            log_err "FAILED ${e_path} — declared path does not exist and is not optional"
            record_absent "${e_path}" "failed"
            TOTAL_FAILED=$((TOTAL_FAILED + 1))
            RC=1
        fi
        continue
    fi

    declare -a find_args=("${e_path}")
    if [[ "${e_rec}" != "1" || -f "${e_path}" ]]; then
        find_args+=(-maxdepth 0)
    fi
    # The filter IS the scope fence: only items under a declared path are ever
    # named, so an out-of-scope item cannot be reached even by accident (FR-005).
    find_args+=(\( ! -uid "${OP_UID}" -o ! -gid "${OP_GID}" \) -printf '%U\t%G\t%m\t%p\0')

    : > "${TMP_ITEMS}"
    : > "${TMP_ERR}"
    if ! find "${find_args[@]}" > "${TMP_ITEMS}" 2> "${TMP_ERR}"; then
        # find reports what it could read AND a non-zero status. Both halves are
        # honoured: the readable part is repaired below, the unreadable part is a
        # named failure rather than a silent gap.
        while IFS= read -r errline; do
            [[ -n "${errline}" ]] || continue
            log_err "FAILED ${e_path} — cannot fully walk: ${errline}"
        done < "${TMP_ERR}"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
        RC=1
    fi

    discovered="$(tr -cd '\0' < "${TMP_ITEMS}" | wc -c)"
    if [[ "${discovered}" -eq 0 ]]; then
        log_info "${label}: 0/0 items need repair"
        continue
    fi

    BATCH_RESTORE_MODE=0
    if [[ "${e_pres}" == "1" ]]; then
        BATCH_RESTORE_MODE=1
    fi

    processed=0
    last_report="${SECONDS}"
    # `-d ''` (NUL-terminated) with a TAB IFS and the path LAST: read assigns the
    # remainder verbatim to the last variable, so a path containing a tab or a
    # newline survives intact. find emits the three fixed numeric fields first for
    # exactly this reason.
    while IFS=$'\t' read -r -d '' prev_uid prev_gid prev_mode item; do
        [[ -n "${item}" ]] || continue

        if [[ "${DRY_RUN}" -eq 1 ]]; then
            printf '[ownership-repair] would chown %s:%s (was %s:%s) %s\n' \
                "${OP_UID}" "${OP_GID}" "${prev_uid}" "${prev_gid}" "${item}"
            processed=$((processed + 1))
            continue
        fi

        BATCH_PATHS+=("${item}")
        BATCH_MODES+=("${prev_mode}")
        BATCH_PUID+=("${prev_uid}")
        BATCH_PGID+=("${prev_gid}")
        BATCH_BLOB+="$(record_line "${item}" "${prev_uid}" "${prev_gid}" "${prev_mode}" "changed")"$'\n'
        processed=$((processed + 1))

        if [[ ${#BATCH_PATHS[@]} -ge ${BATCH_SIZE} ]]; then
            flush_batch "${label}"
            # FR-004e: real work completed against work discovered, so a long run
            # on a large library is distinguishable from a hang. Throttled to once
            # per second so a huge tree does not drown the operator in output.
            if [[ $((SECONDS - last_report)) -ge 1 ]]; then
                log_info "${label}: ${processed}/${discovered} items processed (${TOTAL_CHANGED} changed overall)"
                last_report="${SECONDS}"
            fi
        fi
    done < "${TMP_ITEMS}"

    flush_batch "${label}"
    log_info "${label}: ${processed}/${discovered} items processed"
done

if [[ "${RECORD_FD_OPEN}" -eq 1 ]]; then
    exec 3>&-
    RECORD_FD_OPEN=0
fi

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
if [[ "${DRY_RUN}" -eq 1 ]]; then
    log_info "dry run complete — nothing changed, no record written, no marker written"
    # A dry run still reports what it FOUND. Exiting 0 while the preview named a
    # declared path that cannot be repaired would make --dry-run useless as a
    # pre-flight check and would be the §11.4.201(1) false-negative in reverse.
    exit "${RC}"
fi

if [[ "${RC}" -eq 0 ]]; then
    marker_write "${TOTAL_CHANGED}"
    log_info "complete: ${TOTAL_CHANGED} item(s) repaired; record ${RECORD_FILE#"${PROJECT_ROOT}"/}; marker ${MARKER_FILE#"${PROJECT_ROOT}"/}"
    exit 0
fi

# No marker: this pass did not fully succeed, so the next start must resume.
log_err "incomplete: ${TOTAL_CHANGED} item(s) repaired, ${TOTAL_FAILED} item(s) could not be repaired (listed above)"
log_err "no marker written — the next run will retry the whole declared scope"
exit 1
