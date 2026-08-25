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
#   scripts/ownership_repair.sh --state-dir <p>  # keep marker+record out of the live tree
#
# Inputs:
#   config/owned_paths.yaml   the declared scope (E1). Overridable by --scope or
#                             the OWNED_PATHS_FILE environment variable.
#   CONTAINER_RUNTIME         optional. SET-BUT-EMPTY means "no container runtime
#                             is available" and suppresses the `<runtime> unshare`
#                             fallback entirely. UNSET means "detect one".
#   OWNERSHIP_STATE_DIR       optional. Where the marker and change record live.
#                             Defaults to <project-root>/logs/ownership — the
#                             live path. Set it (or pass --state-dir) so an
#                             ad-hoc invocation does not share the operator's
#                             marker and trail.
#
# Outputs:
#   stdout                                       progress (items processed / discovered)
#   <state-dir>/repair-changes.ndjson            the E3 change record of the run IN FLIGHT
#   <state-dir>/repair-changes.<UTC-ts>.ndjson   that record once its run COMPLETED
#   <state-dir>/repair-marker.json               the E2 completion marker, which names
#                                                the record file of the run it marks
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
# WHAT "DURABLE" HONESTLY MEANS FOR THE CHANGE RECORD (data-model E3)
#   E3 calls the record durable and append-only. Measured 2026-08-21, that
#   overclaims, and the honest statement is narrower:
#
#     GUARANTEED — this script only ever APPENDS to the record of a run in
#       flight; it never rewrites or truncates one, and it never deletes a
#       record belonging to a run that completed. Each COMPLETED run's record is
#       rotated to its own timestamped, thereafter-immutable artifact, so one
#       run can never overwrite, truncate or interleave with another's, and one
#       deletion can destroy at most one run's trail.
#     NOT GUARANTEED — that the artifact still EXISTS later. The record lives in
#       a gitignored logs/ tree that repo actors demonstrably clean: on
#       2026-08-21 a marker and record written at 17:20 were both gone by 20:32
#       (logs/ empty, dir mtime 19:21), deleted by a project actor, and NOTHING
#       noticed. This script cannot defend a directory it does not own.
#
#   So the marker NAMES the record file of the run it marks, and a later run
#   that finds that named file gone REPORTS the loss loudly instead of quietly
#   opening a fresh one. Detection is what is offered; prevention is not, and
#   claiming otherwise would be the §11.4/§11.4.6 bluff at the durability layer.
#   HONEST BOUNDARY: if the whole state directory is removed, the marker goes
#   with the record and there is nothing left to detect the loss against.
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
# WHY A REPO-RELATIVE DECLARED PATH IS RESOLVED AGAINST THE PROJECT ROOT
#   data-model E1 allows a declared path to be absolute or repo-relative, and
#   the shipped scope uses relative paths for `config`, `config/boba.db`,
#   `.env`, `tmp` and `download-proxy`. An earlier revision passed those to
#   `find` verbatim, so they resolved against the CALLER'S cwd: measured
#   2026-08-21, a run started from `/` reported
#     FAILED fixture/... - declared path does not exist and is not optional
#   and exited 1 on a path that plainly exists — the §11.4.201(1) false-positive
#   refusal, a guard refusing on a condition that is absent. The sibling
#   consumer scripts/ownership_precondition.sh already absolutises (its
#   `absolutise()` helper), so the two readers of ONE scope file disagreed about
#   what a relative entry means. This script now resolves the same way.
#
#   The FINGERPRINT is deliberately computed BEFORE this resolution — from the
#   scope's PARSED, ENVIRONMENT-EXPANDED entry rows (scripts/lib/ownership.sh
#   `ownership_scope_fingerprint`, which hashes `ownership_scope_entries`), NOT
#   from the scope file's literal bytes. Two consequences, and both are
#   deliberate:
#
#     * It is independent of the caller's CWD, because relative entries are
#       still relative at that point — a marker is not invalidated by a change
#       of directory.
#     * It DOES move with the ENVIRONMENT, because `${VAR}` in a declared path
#       is expanded before hashing. MEASURED 2026-08-25 on one unchanged scope
#       file whose only entry is `${QBITTORRENT_DATA_DIR:-/mnt/DATA}`:
#           env unset                     -> 76b3930629a1e422...
#           QBITTORRENT_DATA_DIR=/tmp/aaa -> cc412df3ff7e2435...
#           sha256 of the file's bytes    -> a73b307a006a3117...  (matches neither)
#       That is the correct behaviour — repointing the download root MUST
#       re-arm the repair — but it has an operational edge worth knowing: a
#       hand-run repair from a shell that has NOT sourced `.env` computes a
#       different fingerprint, so its marker does not satisfy start.sh's check,
#       and vice versa. Source the environment the stack runs with, or pass
#       --state-dir so the ad-hoc run keeps its own trail.
#
# WHY chown -h
#   `-h` acts on a symlink itself rather than its target. Without it a symlink
#   inside the declared scope pointing anywhere on the filesystem would let the
#   repair mutate a file OUTSIDE the scope. `-h`, plus find's default -P (which
#   does not descend a symlinked directory), closes the SYMLINK dimension of
#   FR-005 by construction.
#
# THE ONE OUT-OF-SCOPE REACH THAT REMAINS: HARDLINKS
#   An earlier revision of this header claimed FR-005 makes out-of-scope reach
#   "impossible by construction". That was an OVERCLAIM (§11.4.6), and it is
#   corrected here rather than left standing.
#
#   MEASURED against this script, 2026-08-25: a hardlink INSIDE the declared
#   scope names an inode whose other link lives OUTSIDE every declared path.
#   chown(2) acts on the INODE, not on the name, so the out-of-scope file's
#   ownership changed with it:
#       BEFORE 1000:10 links=2   ->   AFTER 1000:1000 links=2
#
#   The reach is BOUNDED and the bounds are what make it tolerable:
#     * hard links cannot cross filesystems, so the reach cannot leave the
#       device the declared path lives on;
#     * it needs a writer INSIDE the declared scope able to create the link —
#       a container running as root in a declared bind mount is exactly such a
#       writer, so this is not theoretical;
#     * it moves OWNERSHIP only. Content is never read or written by this
#       script (machine-checked: tests/unit/test_ownership_repair.sh Case 18
#       asserts the out-of-scope file's bytes are unchanged), and the new owner
#       is always the operator — the repair can only ever hand an inode TO the
#       operator, never away from them.
#
#   FENCING IT WAS CONSIDERED AND REJECTED, and the reason is recorded so the
#   decision is not silently re-litigated: refusing every item with st_nlink > 1
#   would refuse the ORDINARY case, because hardlinking is how a torrent client
#   and a media manager share one payload between the download tree and the
#   library. A fence there would break the feature for its primary user in
#   order to close a bounded, ownership-only, same-device escape. The claim is
#   corrected instead, and Case 18 machine-checks that this text and the real
#   behaviour still agree.

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
# The DEFAULT is the live path and MUST NOT move: the operator, the journal line
# and docs/scripts/ownership_repair.md all already name logs/ownership/. It is
# overridable (OWNERSHIP_STATE_DIR / --state-dir) for one reason: state was a
# fixed constant, so ANY ad-hoc invocation shared the live operator's marker and
# change record — a hand-run repair could mark the live scope "complete", or
# interleave its entries into the operator's recovery trail. An override makes
# an ad-hoc run harmless. Resolved after argument parsing, so --state-dir can
# set it.
STATE_DIR_DEFAULT="${PROJECT_ROOT}/logs/ownership"
STATE_DIR=""
RECORD_FILE=""
MARKER_FILE=""

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
  --state-dir <p>  override where the marker and change record live
                   (default: <project-root>/logs/ownership). Use it so an
                   ad-hoc run does not share the live operator's trail.
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
        --state-dir)
            if [[ $# -lt 2 ]]; then
                log_err "--state-dir requires a path"
                exit 2
            fi
            OWNERSHIP_STATE_DIR="$2"
            export OWNERSHIP_STATE_DIR
            shift 2
            ;;
        --state-dir=*)
            OWNERSHIP_STATE_DIR="${1#--state-dir=}"
            export OWNERSHIP_STATE_DIR
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

# Resolved here, not at definition, so --state-dir has been parsed. An empty
# OWNERSHIP_STATE_DIR is treated as unset rather than as "the current
# directory": silently writing the operator's trail into $PWD would be worse
# than either honouring the default or refusing.
STATE_DIR="${OWNERSHIP_STATE_DIR:-${STATE_DIR_DEFAULT}}"
RECORD_FILE="${STATE_DIR}/repair-changes.ndjson"
MARKER_FILE="${STATE_DIR}/repair-marker.json"

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

# ...and a scope that READS fine but yields ZERO entries is the OTHER half of
# the same rule. The paragraph above defended only the unreadable case, so a
# scope that was valid YAML declaring nothing walked nothing, asserted nothing,
# and — MEASURED 2026-08-25 against the pre-fix script — exited 0 and wrote a
# completion marker carrying fingerprint
#   e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
# which is sha256("") — the fingerprint of nothing. start.sh then reads that
# marker as "already repaired" and skips the walk on every subsequent start.
# Three real shapes produce it: `paths: []`, the top-level key mistyped as
# `path:`, and every entry's ${VAR} expanding empty (the shipped scope's FIRST
# entry is ${QBITTORRENT_DATA_DIR:-/mnt/DATA}, so that shape is live).
#
# The DECISION is mirrored from the sibling consumer of this same scope file,
# scripts/ownership_precondition.sh:1011-1013, which already refuses all three
# with exit 2 — §11.4.251: one predicate, both callers, never a second dialect.
# The test is byte-identical to that one, deliberately.
#
# exit 2 and NOT exit 1: exit 1 means "an item could not be repaired" and
# invites a retry. No item is wrong here; the SCOPE is unusable, and 2 is what
# the contract reserves for "could not run" (§11.4.201(6) — a run that asserted
# nothing must never be coloured the same as a clean tree).
if [[ -z "${ENTRIES_RAW//[[:space:]]/}" ]]; then
    log_err "the declared scope contains no locations: ${SCOPE_FILE}"
    log_err "a repair that walked zero locations has asserted nothing"
    log_err "refusing to write a completion marker — nothing was touched"
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

# absolutise <path> — a declared path may be absolute or repo-relative (E1).
# Deliberately identical in behaviour to scripts/ownership_precondition.sh's
# helper of the same name, because both read the SAME scope file and a
# divergence there means the two consumers disagree about what a relative entry
# denotes. The `|| p="/"` guard only fires for the literal input "/", where
# stripping the trailing slash would otherwise yield an empty path — an empty
# path is a silent nothing, and a silent nothing is the one outcome forbidden.
absolutise() {
    local p="$1"
    [[ "${p}" == /* ]] || p="${PROJECT_ROOT}/${p}"
    p="${p%/}"
    [[ -n "${p}" ]] || p="/"
    printf '%s' "${p}"
}

# THE DECLARED PATH IS ITSELF FENCED (§11.4.252 fail-closed).
#
# The walk filter below only ever names items UNDER a declared path, and an
# earlier revision called that "the scope fence". It is circular: it fences to
# the declared path and nothing constrained what a declared path may BE.
# `absolutise()` prepends the project root to a relative entry and otherwise
# passes text through — no normalisation, no bound. MEASURED 2026-08-25, with
# the shipped `${QBITTORRENT_DATA_DIR:-/mnt/DATA}` entry unchanged and only the
# environment moved, this script really did launch
#     find / \( ! -uid 1000 -o ! -gid 1000 \) -printf '%U\t%G\t%m\t%p\0'
# — a recursive walk of the entire filesystem, observed in `ps` and killed by
# pid. `.env` is untracked and unreviewed, so an unreviewed file fully
# determined which tree got recursively chowned.
#
# ownership_path_fence() (scripts/lib/ownership.sh) holds the rule and the
# reasoning; it lives in the shared library so there can never be a second
# dialect of it (§11.4.251). It normalises `..` first, requires a repo-relative
# entry to stay inside the project root, and bounds an absolute entry by shape
# (depth floor + system-tree denylist).
#
# ONE BAD ENTRY REFUSES THE WHOLE RUN, and exit 2 ("could not run"), not 1: a
# scope containing a path of that shape is a scope this script does not trust
# at all, and nothing has been touched at this point. Refusing per-entry and
# proceeding with the rest would silently repair a partial scope while writing
# a marker that claims the whole one.
declare -a E_PATH=() E_KIND=() E_OPTIONAL=() E_PRESERVE=() E_RECURSIVE=()
FENCE_REFUSALS=0
while IFS=$'\t' read -r e_path e_kind e_opt e_pres e_rec; do
    [[ -n "${e_path}" ]] || continue

    # Captured BEFORE absolutise(), because "was this written as a repo-relative
    # entry?" is unrecoverable once the project root has been prepended.
    e_was_rel=1
    [[ "${e_path}" == /* ]] && e_was_rel=0

    e_abs="$(absolutise "${e_path}")"
    if ! fence_reason="$(ownership_path_fence "${e_abs}" "${e_was_rel}" "${PROJECT_ROOT}" 2>&1)"; then
        log_err "REFUSED ${e_path} — ${fence_reason}"
        FENCE_REFUSALS=$((FENCE_REFUSALS + 1))
        continue
    fi

    E_PATH+=("$(ownership_normalise_path "${e_abs}")")
    E_KIND+=("${e_kind}")
    E_OPTIONAL+=("${e_opt}")
    E_PRESERVE+=("${e_pres}")
    E_RECURSIVE+=("${e_rec}")
done <<< "${ENTRIES_RAW}"

if [[ "${FENCE_REFUSALS}" -gt 0 ]]; then
    log_err "the declared scope names ${FENCE_REFUSALS} path(s) this repair must never walk: ${SCOPE_FILE}"
    log_err "nothing was touched, no record was written, no marker was written"
    exit 2
fi

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

# marker_write <items-changed> <record-basename-or-empty>
#
# `record_file` NAMES the change record of the run this marker marks, and is the
# only thing that makes a destroyed trail detectable: a later run compares the
# name against the state directory and reports a miss. It is JSON null when the
# run changed nothing, because there is then no trail to lose and inventing a
# name for an absent file would create a false MISSING report on the next run.
marker_write() {
    local items="$1" rec="$2" tmp rec_json
    tmp="$(mktemp "${STATE_DIR}/.repair-marker.XXXXXX")"
    if [[ -n "${rec}" ]]; then
        rec_json="\"$(json_escape "${rec}")\""
    else
        rec_json="null"
    fi
    printf '{\n  "completed_at": "%s",\n  "scope_fingerprint": "%s",\n  "items_changed": %d,\n  "record_file": %s\n}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${FINGERPRINT}" "${items}" "${rec_json}" > "${tmp}"
    # Atomic publish: a half-written marker read by the next start would be a
    # marker whose fingerprint field cannot be trusted.
    mv -f "${tmp}" "${MARKER_FILE}"
}

# rotate_record — retire the completed run's record to its own timestamped,
# thereafter-immutable artifact and echo that basename (empty when there was
# nothing to retire).
#
# Rotation happens at COMPLETION, never at startup, and that ordering is
# load-bearing three ways:
#   * a name written into a marker is never renamed afterwards, so the marker's
#     pointer can never go stale and produce a FALSE "record MISSING" report —
#     which would be the §11.4.201(1) false positive, in the very check whose
#     job is to detect a real loss;
#   * an INTERRUPTED run leaves its partial record in place under the plain
#     name, so the resuming run appends to it and ONE logical repair keeps ONE
#     record (data-model E3), rather than fragmenting across attempts;
#   * two completed runs can therefore never share an artifact, so a single
#     deletion destroys at most one run's trail instead of all of them.
#
# An EMPTY record is removed rather than rotated: a run that changed nothing
# produced no trail, and preserving a stream of empty files would bury the ones
# that carry evidence.
rotate_record() {
    local ts base cand n
    if [[ ! -s "${RECORD_FILE}" ]]; then
        rm -f -- "${RECORD_FILE}" 2>/dev/null || true
        printf ''
        return 0
    fi
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    base="repair-changes.${ts}.ndjson"
    cand="${STATE_DIR}/${base}"
    n=1
    while [[ -e "${cand}" ]]; do
        base="repair-changes.${ts}-${n}.ndjson"
        cand="${STATE_DIR}/${base}"
        n=$((n + 1))
    done
    if mv -f -- "${RECORD_FILE}" "${cand}" 2>/dev/null; then
        printf '%s' "${base}"
        return 0
    fi
    # Rotation failed. The record still EXISTS under its plain name, so name
    # THAT in the marker: the trail is intact and must not be reported missing
    # on the next run just because it could not be renamed.
    log_err "could not rotate the change record to ${cand} — it remains at ${RECORD_FILE}"
    printf '%s' "repair-changes.ndjson"
}

# report_lost_record — say so, loudly, when the record the previous marker names
# is gone. Runs BEFORE this run's record is opened, so it reads the OLD marker.
#
# This detects the 2026-08-21 incident class and nothing more: it cannot detect
# a loss when the marker was destroyed alongside the record, and it does not
# attempt recovery. Reporting a trail we do not have would be the bluff; saying
# it is gone is the honest alternative.
report_lost_record() {
    local prior
    [[ -f "${MARKER_FILE}" ]] || return 0
    prior="$(sed -n 's/.*"record_file"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${MARKER_FILE}" 2>/dev/null | head -n1)"
    [[ -n "${prior}" ]] || return 0
    [[ -e "${STATE_DIR}/${prior}" ]] && return 0
    log_err "WARNING: the change record named by the completion marker is MISSING: ${prior}"
    log_err "  expected at ${STATE_DIR}/${prior}"
    log_err "  The FR-004b recovery trail of the previously-completed repair was removed by"
    log_err "  something other than this script — logs/ is gitignored and repo tooling has"
    log_err "  cleaned it before. This run cannot restore that trail and does not pretend to;"
    log_err "  it opens a NEW record so the loss stays visible instead of being absorbed."
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
    # Before anything is opened for append: the OLD marker is still on disk here,
    # and it is the only thing that can testify that a trail once existed.
    report_lost_record
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

# WHY chown's STDERR IS CAPTURED AND NOT DISCARDED
#   An earlier revision sent it to /dev/null, so the per-item report read
#       FAILED <path> — cannot change ownership to 1000:1000 (<label>)
#   and nothing else. MEASURED 2026-08-25 with an injected EROFS from chown: the
#   string "Read-only file system" appeared ZERO times in the entire run output.
#   EPERM (the identity is wrong), EROFS (the filesystem is mounted read-only)
#   and ENOENT (it vanished under us) are three DIFFERENT remediations behind
#   one undifferentiated sentence, and §11.4.201(5) requires every refusal to
#   print its resolved evidence. The reason is now carried to the operator.
#
#   Captured via command substitution rather than a temp file so it has no
#   lifetime to manage and cannot outlive the call. No background subshell is
#   involved, so the §11.4.201(12) command-substitution/watchdog footgun does
#   not apply here.
#
#   CHOWN_ERR / UNSHARE_ERR are deliberately globals: flush_batch reads them
#   after the call, and a `local` would be invisible to it.
CHOWN_ERR=""
UNSHARE_ERR=""

# chown_paths <paths…> — plain chown over a whole batch. Returns non-zero if any
# path failed; chown itself continues past individual failures. Sets CHOWN_ERR
# to whatever chown said on the way out.
chown_paths() {
    CHOWN_ERR=""
    CHOWN_ERR="$(chown -h -- "${OP_UID}:${OP_GID}" "$@" 2>&1 >/dev/null)" && return 0
    return 1
}

# unshare_chown_paths <paths…> — the namespace fallback. Inside `<runtime> unshare`
# the host operator uid IS uid 0, so 0:0 is what makes the item host-operator-owned.
unshare_chown_paths() {
    UNSHARE_ERR=""
    if [[ -z "${RUNTIME}" ]]; then
        UNSHARE_ERR="no container runtime available for the namespace fallback"
        return 1
    fi
    UNSHARE_ERR="$("${RUNTIME}" unshare chown -h -- 0:0 "$@" 2>&1 >/dev/null)" && return 0
    return 1
}

# failure_reason — the operator-facing WHY for the item that just failed, built
# from what chown and the namespace fallback actually said. Never empty: a
# refusal that cannot say why must say THAT, rather than say nothing.
failure_reason() {
    local r=""
    [[ -n "${CHOWN_ERR}" ]]   && r="chown: ${CHOWN_ERR}"
    if [[ -n "${UNSHARE_ERR}" ]]; then
        [[ -n "${r}" ]] && r="${r}; "
        r="${r}fallback: ${UNSHARE_ERR}"
    fi
    [[ -n "${r}" ]] || r="no reason reported by chown or the namespace fallback"
    printf '%s' "${r//$'\n'/; }"
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
# FR-015 mode restores that failed. Distinct from TOTAL_FAILED because the item
# WAS chowned: it is a broken preservation promise, not an unrepaired item.
TOTAL_MODE_FAILED=0
# The declared root of the entry currently being walked, so a failure ON that
# root can be diagnosed differently from a failure on a file inside it (NIT-2).
CURRENT_ENTRY_ROOT=""
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
                log_err "FAILED ${p} — cannot change ownership to ${OP_UID}:${OP_GID} (${label}): $(failure_reason)"
                # NIT-2: the walk names the DECLARED ROOT itself, so the single
                # most likely failure here is a root-owned mount point — the
                # ordinary state of a removable disk before its filesystem hands
                # ownership over. Reported identically to a bad file, the
                # operator could not tell the two apart, and the consequence is
                # not cosmetic: the run exits 1, no marker is written, and the
                # whole library is re-walked on EVERY subsequent start.
                #
                # The failure itself is PRESERVED, deliberately. An in-scope item
                # that could not be repaired must not be reported as repaired
                # (§11.4.201), and §11.4.120 forbids weakening an assertion to
                # make a gate pass. What is added is the diagnosis, so the
                # remediation — fix the MOUNT, not the files — is reachable from
                # the message instead of requiring the operator to know that the
                # declared root is walked alongside its contents.
                if [[ "${p}" == "${CURRENT_ENTRY_ROOT}" ]]; then
                    log_err "  ^ that path is the DECLARED ROOT of this entry, not a file inside it."
                    log_err "    A declared root that cannot be chowned is usually a mount point owned by another"
                    log_err "    identity: the remedy is the mount (mount options / ownership of the mountpoint),"
                    log_err "    not the files under it. Until it is resolved this run exits 1, writes no marker,"
                    log_err "    and the next start re-walks the whole declared scope."
                fi
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

            # STRIP setuid/setgid WHEN THE OWNER CHANGED — the mode is not the
            # whole story, and this is the one place where restoring the exact
            # bits is the WRONG thing to do.
            #
            # The kernel clears S_ISUID/S_ISGID on chown(2) deliberately: the
            # bit's MEANING is "run as the owner", so it changes meaning when
            # the owner changes. Restoring it verbatim under the new uid
            # inverts the protection the kernel just applied.
            #
            # Measured against this script: a wrongly-owned `4755` file came
            # out of the repair as `4755` owned by the OPERATOR. Before the
            # repair its setuid granted uid 100999 — an identity nobody has,
            # so inert. After, it grants THE OPERATOR to anyone who can
            # execute it, and the download root is world-traversable.
            # Numerically the mode never widened; semantically it inverted,
            # and FR-015 is about the semantics ("MUST NOT relax access
            # restrictions"), not the octal.
            #
            # preserve_mode entries are exempt because the caller has
            # explicitly asked for the exact bits — and the only shipped
            # preserve_mode entry is a mode-600 data file with no special
            # bits, so nothing shipped loses anything.
            _mode="${BATCH_MODES[${i}]}"
            if [[ "${BATCH_RESTORE_MODE}" -ne 1 && ${#_mode} -gt 3 ]]; then
                # keep sticky (1000), drop setuid+setgid (6000)
                _mode="$(( 8#${_mode} & 8#1777 ))"
                _mode="$(printf '%o' "${_mode}")"
            fi
            # A FAILED MODE RESTORE IS NOT SWALLOWED.
            #
            # This is the step that DELIVERS FR-015 ("the exact bits are
            # preserved"). An earlier revision ended it with `2>/dev/null || true`,
            # so it reported nothing at all: no log line, no record entry, no
            # effect on the exit code. MEASURED 2026-08-25 with an injected chmod
            # failure on a preserve_mode entry, every restore failed and the run
            # still printed "complete: 2 item(s) repaired", exited 0, and WROTE A
            # COMPLETION MARKER — FR-015 claimed and never delivered.
            #
            # The direction is narrowing-only (chown(2) can only CLEAR
            # setuid/setgid, never set them), so a failed restore is not an
            # access WIDENING and is not a security regression. It is a broken
            # promise, and §11.4/§11.4.1 make an unkept promise reported as
            # success the defect — so it is named, recorded, and it blocks the
            # marker so the next run retries.
            #
            # Counted separately from TOTAL_FAILED: the item WAS chowned and is
            # already counted in TOTAL_CHANGED, and adding it to the failure
            # count as well would report one item twice.
            if ! _chmod_err="$(chmod "${_mode}" -- "${BATCH_PATHS[${i}]}" 2>&1 >/dev/null)"; then
                TOTAL_MODE_FAILED=$((TOTAL_MODE_FAILED + 1))
                RC=1
                log_err "FAILED ${BATCH_PATHS[${i}]} — ownership repaired, but mode ${_mode} could not be restored (FR-015): ${_chmod_err:-no reason reported by chmod}"
                record_emit "${BATCH_PATHS[${i}]}" "${BATCH_PUID[${i}]}" "${BATCH_PGID[${i}]}" "${BATCH_MODES[${i}]}" "mode-restore-failed"
            fi
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
    CURRENT_ENTRY_ROOT="${e_path}"

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
    ROTATED_RECORD="$(rotate_record)"
    marker_write "${TOTAL_CHANGED}" "${ROTATED_RECORD}"
    if [[ -n "${ROTATED_RECORD}" ]]; then
        log_info "complete: ${TOTAL_CHANGED} item(s) repaired; record ${STATE_DIR#"${PROJECT_ROOT}"/}/${ROTATED_RECORD}; marker ${MARKER_FILE#"${PROJECT_ROOT}"/}"
    else
        log_info "complete: ${TOTAL_CHANGED} item(s) repaired; no change record (nothing was changed); marker ${MARKER_FILE#"${PROJECT_ROOT}"/}"
    fi
    exit 0
fi

# No marker: this pass did not fully succeed, so the next start must resume.
log_err "incomplete: ${TOTAL_CHANGED} item(s) repaired, ${TOTAL_FAILED} item(s) could not be repaired, ${TOTAL_MODE_FAILED} item(s) repaired but could not have their mode restored (all listed above)"
log_err "no marker written — the next run will retry the whole declared scope"
exit 1
