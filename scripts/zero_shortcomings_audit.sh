#!/usr/bin/env bash
set -euo pipefail

print_info()    { printf '\033[0;34m[INFO]\033[0m %s\n' "$*"; }
print_success() { printf '\033[0;32m[ OK ]\033[0m %s\n' "$*"; }
print_warning() { printf '\033[0;33m[WARN]\033[0m %s\n' "$*"; }
print_error()   { printf '\033[0;31m[FAIL]\033[0m %s\n' "$*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/audit_ledger_parser.sh
source "$SCRIPT_DIR/lib/audit_ledger_parser.sh"
# shellcheck source=lib/audit_execution_policy.sh
source "$SCRIPT_DIR/lib/audit_execution_policy.sh"
# shellcheck source=lib/audit_run_id.sh
source "$SCRIPT_DIR/lib/audit_run_id.sh"

WORKABLE_ITEMS_BIN="$REPO_ROOT/constitution/scripts/workable-items/workable-items"
# Overridable for testability (risk-order test builds a temp DB).
WORKABLE_ITEMS_DB="${WORKABLE_ITEMS_DB_OVERRIDE:-$REPO_ROOT/docs/workable_items.db}"
# Overridable for testability (Task 4+4B review, 2026-09-25): the false-null
# regression test points this at a genuinely non-existent script to prove
# count_gates_unimplemented fails loud rather than silently reporting 0.
GATE_LEDGER_SCRIPT="${GATE_LEDGER_SCRIPT_OVERRIDE:-$REPO_ROOT/constitution/scripts/gates/cm_gate_ledger_ratchet.sh}"
COVERAGE_ESCAPE_LEDGER="$REPO_ROOT/docs/QA_DISCOVERY_LEDGER.md"

# Exit-code contract (specs/003-zero-shortcomings-audit/contracts/cli.md).
# Usage and internal refusals are deliberately DIFFERENT from the genuine
# mismatch code 1, so a caller can tell "the defect is back" from "the tool
# was misused or could not run" without parsing the message.
AUDIT_EXIT_USAGE=4      # bad mode/option/value, invalid item id
AUDIT_EXIT_INTERNAL=5   # the tool refused to run (mktemp, snapshot, lock busy)
AUDIT_EXIT_TIMEOUT=6    # the recorded command exceeded its bound: inconclusive

usage() {
    cat <<'USAGE'
Usage: zero_shortcomings_audit.sh <mode> [options]

Modes:
  enumerate [--json] [--surface backlog|gates|escapes|blocked] [--sort-by-risk]
      Read-only. Enumerates the three tracked surfaces. See
      specs/003-zero-shortcomings-audit/contracts/cli.md for the full contract.
      --surface blocked   list each Operator-blocked item with its unblock
                          condition (id|unblock_condition) instead of counts.
      --sort-by-risk      list open backlog item ids most-reopened first, then
                          most recently modified; valid only with
                          --surface backlog (rejected otherwise).
  verify-closure <item-id> [--reopen-on-mismatch] [--require-layer <layer>]
      Independently re-runs one item's recorded closure evidence. The
      evidence file's **Command:** runs as shell in a fresh bash process
      with cwd = the repository root (evidence files are trusted input).
      <item-id> must match ^[A-Za-z0-9][A-Za-z0-9._-]*$ and contain no '..'.
      --require-layer     minimum evidence layer the closure must carry:
                          source|artifact|runtime (default: runtime).
      --reopen-on-mismatch
                          reopen the item in the tracker on a mismatch.
      The command runs niced (nice/ionice), without BASH_ENV/ENV, bounded
      by $AUDIT_VERIFY_COMMAND_TIMEOUT seconds when set, and only while
      holding the per-repository FR-011 lock ($AUDIT_VERIFY_LOCK_FILE,
      waiting up to $AUDIT_VERIFY_LOCK_WAIT seconds, default 60).
      Exit: 0 match, 1 mismatch, 2 no/insufficient evidence, 3 mismatch but
      the tracker reopen FAILED, 4 usage error / invalid id, 5 internal
      refusal (mktemp, snapshot, lock held by another run), 6 the recorded
      command timed out (inconclusive).
      Corruption incidents are logged under $AUDIT_QA_ROOT/zero_shortcomings_audit
      (or $AUDIT_INCIDENT_LOG_DIR when set).
  standing-check [--reverify N]
      The recurring, non-blocking mode wired into pre_build_verification.sh.
      Counts the three surfaces AND re-runs verify-closure (never reopening)
      over the N highest-risk CLOSED items whose evidence records a command
      (default N=$AUDIT_REVERIFY_DEFAULT or 2; 0 disables). Each command is
      bounded by $AUDIT_REVERIFY_ITEM_TIMEOUT (150 s) and an item starts only
      if it fits in $AUDIT_REVERIFY_BUDGET (210 s). A mismatch, timeout,
      invalid evidence or refusal marks the run status=degraded. Always
      exits 0 once its arguments are valid. Writes its run log to
      $AUDIT_STANDING_LOG_DIR when set.

Usage errors in any mode exit 4.

Options:
  -h, --help    Show this help and exit.
USAGE
}

count_backlog_open() {
    sqlite3 "$WORKABLE_ITEMS_DB" \
        "SELECT count(*) FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete';"
}

# audit_severity_rank_sql <column> — an SQL expression ranking the tracker's
# free-text severity column (case-insensitive; the live tracker mixes
# "Critical"/"critical", "High"/"Major"/"Important", ...): 0 critical,
# 1 high|major|important, 2 medium, 3 low|minor, 4 anything else or NULL.
audit_severity_rank_sql() {
    printf "CASE lower(trim(coalesce(%s,''))) WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'major' THEN 1 WHEN 'important' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 WHEN 'minor' THEN 3 ELSE 4 END" "$1"
}

list_backlog_risk_ordered() {
    # FR-012: reopens DESC, then last_modified DESC, then severity (most
    # severe first), then atm_id. items has no reopens_count column; the count
    # is derived from item_history 'Reopened' events. The open predicate is
    # identical to count_backlog_open above.
    sqlite3 "$WORKABLE_ITEMS_DB" \
        "SELECT i.atm_id FROM items i
         WHERE i.status NOT LIKE '%(→ Fixed.md)' AND i.status != 'Obsolete'
         ORDER BY (SELECT count(*) FROM item_history h WHERE h.atm_id = i.atm_id AND h.event_type = 'Reopened') DESC,
                  i.last_modified DESC, $(audit_severity_rank_sql i.severity), i.atm_id;"
}

count_gates_unimplemented() {
    # cm_gate_ledger_ratchet.sh's underlying engine (gate_ledger.sh) prints
    # its "LEDGER: unimplemented=N ..." summary line on BOTH its pass and
    # fail paths -- so a genuinely missing line means the script itself
    # failed before reaching that point, NEVER "genuinely zero unimplemented
    # gates" (Task 4+4B combined review, Critical finding, 2026-09-25: the
    # original `|| printf '0\n'` fallback conflated the two, exactly the
    # §11.4.201(6) false-null class this audit tool exists to catch).
    local output
    output="$(bash "$GATE_LEDGER_SCRIPT" 2>&1)"
    local count
    count="$(printf '%s\n' "$output" | grep -oE 'unimplemented=[0-9]+' | head -1 | grep -oE '[0-9]+')"
    if [[ -n "$count" ]]; then
        printf '%s\n' "$count"
        return 0
    fi
    print_error "count_gates_unimplemented: ${GATE_LEDGER_SCRIPT} produced no parseable 'unimplemented=N' line — cannot distinguish a genuine zero from a broken gate script"
    printf '%s\n' "$(audit_redact_before_write "$output")" >&2
    return 1
}

count_escapes_open() {
    audit_ledger_count_open_escapes "$COVERAGE_ESCAPE_LEDGER"
}

cmd_enumerate() {
    local json=false
    local surface="all"
    local sort_by_risk=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --json) json=true; shift ;;
            --surface)
                # m2: a missing value must be a clear usage error, never a
                # set -u "unbound variable" abort.
                if [[ $# -lt 2 || -z "$2" ]]; then
                    print_error "enumerate: --surface requires a value (all|backlog|gates|escapes|blocked)"
                    return "$AUDIT_EXIT_USAGE"
                fi
                surface="$2"; shift 2 ;;
            --sort-by-risk) sort_by_risk=true; shift ;;
            *) print_error "enumerate: unknown option: $1"; return "$AUDIT_EXIT_USAGE" ;;
        esac
    done

    case "$surface" in
        blocked)
            # FR-007: honestly report every Operator-blocked item's specific,
            # observable unblock condition -- NEVER collapse to a bare count.
            audit_require_db || return 1
            print_info "Operator-blocked items (id|unblock_condition):"
            count_blocked_with_conditions
            return 0
            ;;
        all|backlog|gates|escapes)
            ;;
        *)
            # Task 4+4B combined review, Important finding, 2026-09-25: an
            # unrecognized --surface value previously fell through the
            # if-chain below with no match, and the resulting `false` exit
            # of the chain's final statement propagated silently through
            # set -e with zero explanatory output. Fail loud, by name.
            print_error "enumerate: unrecognized --surface value: '$surface' (expected all|backlog|gates|escapes|blocked)"
            return "$AUDIT_EXIT_USAGE"
            ;;
    esac

    if [[ "$surface" == "all" || "$surface" == "backlog" ]]; then
        audit_require_db || return 1
    fi

    if [[ "$sort_by_risk" == "true" ]]; then
        if [[ "$surface" != "backlog" ]]; then
            print_error "enumerate: --sort-by-risk applies only to --surface backlog (got '$surface')"
            return "$AUDIT_EXIT_USAGE"
        fi
        if [[ "$json" == "true" ]]; then
            # JSON array of atm_ids in risk order.
            list_backlog_risk_ordered | awk 'BEGIN{printf "["} {printf "%s\"%s\"", (NR>1?",":""), $0} END{print "]"}'
        else
            list_backlog_risk_ordered
        fi
        return 0
    fi

    local backlog="" gates="" escapes=""
    # A failing count MUST propagate (an `A && x="$(f)"` list swallows f's
    # failure under set -e and leaves the value empty -- a false-null).
    if [[ "$surface" == "all" || "$surface" == "backlog" ]]; then backlog="$(count_backlog_open)" || return 1; fi
    if [[ "$surface" == "all" || "$surface" == "gates" ]]; then gates="$(count_gates_unimplemented)" || return 1; fi
    if [[ "$surface" == "all" || "$surface" == "escapes" ]]; then escapes="$(count_escapes_open)" || return 1; fi

    if [[ "$json" == "true" ]]; then
        local body=""
        [[ -n "$backlog" ]] && body+="\"backlog_open\":${backlog},"
        [[ -n "$gates" ]] && body+="\"gates_unimplemented\":${gates},"
        [[ -n "$escapes" ]] && body+="\"escapes_open\":${escapes},"
        body="${body%,}"
        printf '{%s}\n' "$body"
    else
        print_info "Zero-shortcomings audit — enumeration ($(audit_run_id))"
        [[ -n "$backlog" ]] && print_info "Open backlog items:        $backlog"
        [[ -n "$gates" ]] && print_info "Unimplemented gates:       $gates"
        [[ -n "$escapes" ]] && print_info "Open coverage-escapes:     $escapes"
    fi
}

main() {
    local mode="${1:-}"
    case "$mode" in
        -h|--help) usage; return 0 ;;
        "") usage; return "$AUDIT_EXIT_USAGE" ;;
        enumerate) shift; cmd_enumerate "$@" ;;
        verify-closure) shift; cmd_verify_closure "$@" ;;
        standing-check) shift; cmd_standing_check "$@" ;;
        *) print_error "unknown mode: $mode"; usage; return "$AUDIT_EXIT_USAGE" ;;
    esac
}


count_blocked_with_conditions() {
    # LEFT JOIN (never an inner join): an Operator-blocked item with NO
    # details row, or with a blank/whitespace-only condition, is SURFACED as
    # an explicit `<id>|MISSING-UNBLOCK-CONDITION` defect line rather than
    # silently dropped (FR-007/SC-006 -- an inner join made such an item
    # vanish from the report, reading as "every blocked item is fine").
    # Output is "id|condition", one row per item, ordered by id. The number
    # of MISSING rows is announced on stderr; the exit status stays 0
    # because enumerate reports findings rather than gating on them.
    #
    # BOB-248 hardening: SQLite trim() strips only spaces by default, so a
    # condition made of tabs/newlines read as a real condition -- the trim set
    # below is space, tab, LF and CR. And an item with more than one details
    # row (a table without the PRIMARY KEY, or the item stored twice in items)
    # is listed ONCE: its distinct non-blank conditions are joined with " ; ",
    # and embedded line breaks become spaces so every item stays one line.
    local ws="' '||char(9)||char(10)||char(13)"
    local rows missing
    rows="$(sqlite3 -separator '|' "$WORKABLE_ITEMS_DB" \
        "SELECT i.atm_id,
                coalesce((SELECT group_concat(c, ' ; ')
                          FROM (SELECT DISTINCT replace(replace(trim(b.unblock_condition, ${ws}), char(10), ' '), char(13), ' ') AS c
                                FROM operator_block_details b
                                WHERE b.atm_id = i.atm_id
                                  AND trim(coalesce(b.unblock_condition, ''), ${ws}) <> ''
                                ORDER BY c)),
                         'MISSING-UNBLOCK-CONDITION')
         FROM items i
         WHERE i.status = 'Operator-blocked'
         GROUP BY i.atm_id
         ORDER BY i.atm_id;")" || return 1
    [[ -n "$rows" ]] && printf '%s\n' "$rows"
    missing="$(printf '%s\n' "$rows" | grep -c '|MISSING-UNBLOCK-CONDITION$' || true)"
    if [[ "$missing" -gt 0 ]]; then
        print_warning "enumerate: ${missing} Operator-blocked item(s) lack an unblock condition (FR-007 defect)" >&2
    fi
    return 0
}

# audit_require_db — fail loud when the tracker DB is absent or unreadable.
# Checked BEFORE any sqlite3 call: sqlite3 silently CREATES a missing file,
# which would both litter a 0-byte DB and turn absence into a healthy-looking
# empty result (the §11.4.201(6) false-null this audit exists to catch).
audit_require_db() {
    if [[ ! -f "$WORKABLE_ITEMS_DB" || ! -r "$WORKABLE_ITEMS_DB" ]]; then
        print_error "tracker DB missing or unreadable: $WORKABLE_ITEMS_DB"
        return 1
    fi
}

AUDIT_QA_ROOT="${AUDIT_QA_ROOT:-$REPO_ROOT/docs/qa}"

# audit_find_evidence_file <item-id> — prints the item's closure evidence file
# (the lexically last closure_evidence_*.md, so the choice is deterministic
# when more than one exists), or nothing when there is none.
audit_find_evidence_file() {
    local qa_root_abs f last=""
    qa_root_abs="$(cd "$AUDIT_QA_ROOT" 2>/dev/null && pwd -P)" || qa_root_abs="$AUDIT_QA_ROOT"
    for f in "$qa_root_abs/$1"/closure_evidence_*.md; do
        [[ -f "$f" ]] && last="$f"
    done
    printf '%s' "$last"
}

# audit_exercised_test_types <command> — prints, one per line and without
# duplicates, the closed-set test types a recorded command visibly runs:
# a `tests/<type>/` path token for unit|integration|e2e|security|stress|chaos|
# scaling, and a `challenges/` path token for challenge. Prints nothing when
# none is present (the honest "not decidable" case). The `|| true` / `if`
# forms matter: a grep with no match exits 1, and under the inherited
# errexit/pipefail a bare pipeline would end this function before the
# challenges/ check runs (§11.4.201(12)).
audit_exercised_test_types() {
    {
        printf '%s\n' "$1" | grep -oE '(^|[^A-Za-z0-9_./-])tests/(unit|integration|e2e|security|stress|chaos|scaling)/' \
            | sed -E 's#.*tests/([a-z0-9]+)/$#\1#' || true
        if printf '%s\n' "$1" | grep -qE '(^|[^A-Za-z0-9_./-])challenges/'; then printf 'challenge\n'; fi
    } | sort -u
    return 0
}

# audit_take_verify_lock — FR-011 serialization of closure checks. Opens the
# per-repository lock file on a fresh descriptor and holds it for the rest of
# this process. Returns non-zero (after naming the reason) when the lock
# cannot be opened or is held by another verify-closure.
audit_take_verify_lock() {
    if ! command -v flock >/dev/null 2>&1; then
        print_warning "verify-closure: flock(1) not available -- FR-011 serialization is NOT enforced on this host"
        return 0
    fi
    local repo_key lock_file wait="${AUDIT_VERIFY_LOCK_WAIT:-60}"
    if [[ ! "$wait" =~ ^[0-9]+$ ]]; then
        print_error "verify-closure: AUDIT_VERIFY_LOCK_WAIT must be a non-negative integer (got '$wait')"
        return 1
    fi
    repo_key="$(printf '%s' "$REPO_ROOT" | cksum | cut -d' ' -f1)"
    lock_file="${AUDIT_VERIFY_LOCK_FILE:-${TMPDIR:-/tmp}/zero_shortcomings_audit_verify_${repo_key}.lock}"
    # Brace-scoped so the side redirection never leaks into the caller's
    # shell (§11.4.67(6)); the descriptor itself is meant to stay open.
    if ! { exec {AUDIT_VERIFY_LOCK_FD}>>"$lock_file"; } 2>/dev/null; then
        print_error "verify-closure: cannot open the FR-011 lock file $lock_file"
        return 1
    fi
    if ! flock -w "$wait" "$AUDIT_VERIFY_LOCK_FD"; then
        print_error "verify-closure: another verify-closure holds $lock_file -- refusing to run a second corruption guard over the same tree (FR-011)"
        return 1
    fi
    return 0
}

cmd_verify_closure() {
    local item_id="${1:-}"
    local reopen_on_mismatch=false
    local require_layer="runtime"
    if [[ -z "$item_id" ]]; then
        print_error "verify-closure: an item id is required"
        return "$AUDIT_EXIT_USAGE"
    fi
    # m3: the id is used to build a filesystem path below, so validate it
    # BEFORE any path use: [A-Za-z0-9._-] only, starting with a letter or
    # digit (no option-like leading `-`, no `.`/`..` directory names), and
    # never containing `..` or `/`.
    if [[ ! "$item_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ || "$item_id" == *..* ]]; then
        print_error "verify-closure: invalid item id '$item_id' (allowed: ^[A-Za-z0-9][A-Za-z0-9._-]*\$, no '..' or '/')"
        return "$AUDIT_EXIT_USAGE"
    fi
    shift
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --reopen-on-mismatch) reopen_on_mismatch=true; shift ;;
            --require-layer)
                if [[ $# -lt 2 || -z "$2" ]]; then
                    print_error "verify-closure: --require-layer requires a value (source|artifact|runtime)"
                    return "$AUDIT_EXIT_USAGE"
                fi
                require_layer="$2"; shift 2 ;;
            *) print_error "verify-closure: unknown option: $1"; return "$AUDIT_EXIT_USAGE" ;;
        esac
    done
    case "$require_layer" in
        source|artifact|runtime) ;;
        *) print_error "verify-closure: unrecognized --require-layer value '$require_layer' (expected source|artifact|runtime)"; return "$AUDIT_EXIT_USAGE" ;;
    esac

    # Resolve the evidence root to an absolute path once, so neither the
    # recorded command's cwd (below) nor the incident-log location depends
    # on the directory this was invoked from.
    local qa_root_abs
    qa_root_abs="$(cd "$AUDIT_QA_ROOT" 2>/dev/null && pwd -P)" || qa_root_abs="$AUDIT_QA_ROOT"

    # audit_find_evidence_file prints nothing (status 0) when the item has no
    # evidence directory at all; the `|| true` is kept so a future failure mode
    # of the finder still reaches the deliberate "no evidence -> exit 2"
    # contract below instead of a bare set -e abort (§11.4.201(12)).
    local evidence_file
    evidence_file="$(audit_find_evidence_file "$item_id")" || true
    if [[ -z "$evidence_file" ]]; then
        print_error "verify-closure: no recorded evidence for $item_id under $AUDIT_QA_ROOT/$item_id"
        return 2
    fi

    # audit_layer_rank <layer> — a plain case statement, not a bash-4.3+
    # nameref (`local -n`), so this runs on any bash this project already
    # requires (§11.4.analyze finding C1: no other script here was confirmed
    # to depend on namerefs, and plan.md's Technical Context states no bash
    # version floor — a case statement has zero version dependency).
    audit_layer_rank() {
        case "$1" in
            source)   printf '0\n' ;;
            artifact) printf '1\n' ;;
            runtime)  printf '2\n' ;;
            *)        printf '0\n' ;;  # an unrecognized label is treated as weakest
        esac
    }

    # `|| true` guards against the same set -e/pipefail footgun fixed above
    # for `evidence_file`: `grep -oP` exits non-zero when an evidence file
    # carries no **Evidence Layer:** field at all (the documented "treat as
    # declaring source" case this clause exists to handle) -- an unguarded
    # pipeline here would abort the function BEFORE the `:-source` default
    # ever applies, silently skipping the FR-005 rank check entirely.
    local declared_layer
    declared_layer="$(grep -oP '(?<=\*\*Evidence Layer:\*\* ).*' "$evidence_file" | head -1)" || true
    declared_layer="${declared_layer:-source}"
    local declared_rank required_rank
    declared_rank="$(audit_layer_rank "$declared_layer")"
    required_rank="$(audit_layer_rank "$require_layer")"
    if [[ "$declared_rank" -lt "$required_rank" ]]; then
        print_error "verify-closure: $item_id declares evidence layer '$declared_layer' but '$require_layer' is required — a lower-rigor substitute is not accepted (FR-005)"
        return 2
    fi

    # FR-010: every closure must DECLARE the test type its evidence exercises.
    # `|| true`: a missing field makes grep -oP exit 1; under pipefail an
    # unguarded assignment would abort here (§11.4.201(12)) before the -z check.
    local declared_test_type
    declared_test_type="$(grep -oP '^\*\*Test Type:\*\* \K.*' "$evidence_file" | head -1)" || true
    if [[ -z "$declared_test_type" ]]; then
        print_error "verify-closure: $item_id declares no **Test Type:** — FR-010 requires every closure to name which test type its evidence exercises"
        return 2
    fi
    # The field is a comma-separated list (FR-010: a closure declares EVERY
    # type its evidence exercises). Each member is trimmed, lower-cased and
    # validated against the closed set; a whitespace-only or unknown member,
    # or a list with no members, is not a declaration.
    local -a declared_types=()
    local member normalized_test_type
    normalized_test_type="$(printf '%s' "$declared_test_type" | tr '[:upper:]' '[:lower:]' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    while IFS= read -r member; do
        member="$(printf '%s' "$member" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
        [[ -n "$member" ]] || continue
        case "$member" in
            unit|integration|e2e|security|stress|chaos|scaling|ui|challenge) declared_types+=("$member") ;;
            *)
                print_error "verify-closure: $item_id declares an invalid **Test Type:** '${member}' — allowed: unit|integration|e2e|security|stress|chaos|scaling|ui|challenge (FR-010)"
                return 2
                ;;
        esac
    done < <(printf '%s\n' "$normalized_test_type" | tr ',' '\n')
    if [[ ${#declared_types[@]} -eq 0 ]]; then
        print_error "verify-closure: $item_id declares an invalid **Test Type:** '${normalized_test_type}' — allowed: unit|integration|e2e|security|stress|chaos|scaling|ui|challenge (FR-010)"
        return 2
    fi

    local recorded_command recorded_summary
    # `|| true` guards against the same set -e/pipefail footgun already
    # fixed twice above for evidence_file/declared_layer (§11.4.201(12)):
    # a missing **Command:**/**Result Summary:** field makes grep -oP exit 1
    # with no match, and under pipefail (with head -1 exiting 0) the
    # pipeline's exit status is 1 -- set -e would abort HERE, before the
    # deliberate -z check below ever runs, silently degrading the documented
    # exit-2 contract into an unexplained bare exit 1. Previously flagged as
    # a latent, unexercised instance of this class; closed here with a
    # dedicated regression fixture (BOB-FIXTURE-NO-COMMAND).
    recorded_command="$(grep -oP '(?<=\*\*Command:\*\* `).*(?=`)' "$evidence_file" | head -1)" || true
    recorded_summary="$(grep -oP '(?<=\*\*Result Summary:\*\* ).*' "$evidence_file" | head -1)" || true

    if [[ -z "$recorded_command" ]]; then
        print_error "verify-closure: $evidence_file has no **Command:** field to re-run"
        return 2
    fi

    # FR-010 coverage: every test type the command MECHANICALLY exercises must
    # be declared. Decidable only from the project's own test-path tokens
    # (tests/<type>/ and challenges/); a command with none of them (go test,
    # pytest -k, an ad-hoc pipeline, tests/audit/ ...) is an honest limit and
    # is said to be one -- never guessed either way.
    local -a exercised=() undeclared=()
    local t d found
    mapfile -t exercised < <(audit_exercised_test_types "$recorded_command")
    if [[ ${#exercised[@]} -eq 0 ]]; then
        print_info "verify-closure: FR-010 coverage for $item_id is not mechanically decidable from its command; its declared type(s) '${declared_types[*]}' are taken as stated"
    else
        for t in "${exercised[@]}"; do
            found=false
            for d in "${declared_types[@]}"; do [[ "$d" == "$t" ]] && found=true; done
            [[ "$found" == "true" ]] || undeclared+=("$t")
        done
        if [[ ${#undeclared[@]} -gt 0 ]]; then
            local IFS=,
            print_error "verify-closure: $item_id declares **Test Type:** '${declared_types[*]}' but its command exercises undeclared test type(s): ${undeclared[*]} (FR-010)"
            return 2
        fi
    fi

    # Review Focus item 3: compare the SEMANTIC result_summary, never raw
    # bytes — a legitimately time-varying command (a timestamp, a duration)
    # would otherwise false-positive-reopen every time (§11.4.201(1)).
    #
    # Task 6 (FR-008, [REVIEW] — this runs on every future closure, so a
    # defect here could itself corrupt evidence, per plan.md's Review
    # Gates): snapshot every git-tracked docs/qa/ evidence file BEFORE
    # running the recorded command, then detect + revert any corruption the
    # command causes as a side effect outside THIS item's own evidence
    # directory. Formalizes the real BOB-109 incident this feature is
    # modeled on (research.md §5): a diagnostic test run had a live side
    # effect of overwriting a DIFFERENT item's tracked evidence, caught only
    # because an operator happened to run `git status` first. Any incident
    # is appended to docs/qa/zero_shortcomings_audit/<run-id>.log rather
    # than silently absorbed -- never allowed to block the closure check
    # itself, since a corrupted OTHER item's evidence is a separate finding
    # from whether THIS item's own recorded command still reproduces.
    # The repository the recorded command runs in (and whose tracked
    # docs/qa the guard protects) is THIS script's repository, resolved from
    # $REPO_ROOT -- never from the caller's cwd, so the result of a closure
    # check does not depend on where it was invoked (review finding I-6).
    local cmd_root
    cmd_root="$(git -C "$REPO_ROOT" rev-parse --show-toplevel 2>/dev/null)" || cmd_root="$REPO_ROOT"

    # FR-011: two concurrent closure checks would each snapshot, run, and then
    # REVERT the same tracked docs/qa tree -- one run's revert could undo a
    # write the other is legitimately making. Serialize them with one lock per
    # repository. The lock lives outside the repository (never tracked) and is
    # released when this process exits. A busy lock is an internal refusal,
    # never a wait-forever: AUDIT_VERIFY_LOCK_WAIT (seconds, default 60) bounds
    # how long to wait. Without flock(1) the check runs unlocked and SAYS so.
    audit_take_verify_lock || return "$AUDIT_EXIT_INTERNAL"

    local corruption_snapshot corruption_backup
    corruption_backup="$(mktemp -d)" || { print_error "verify-closure: mktemp failed -- cannot run the corruption guard"; return "$AUDIT_EXIT_INTERNAL"; }
    if ! corruption_snapshot="$(audit_snapshot_tracked_evidence "$corruption_backup" "$cmd_root")"; then
        rm -rf "$corruption_backup"
        print_error "verify-closure: could not snapshot tracked evidence -- refusing to run $item_id's command unguarded"
        return "$AUDIT_EXIT_INTERNAL"
    fi

    local fresh_summary cmd_stderr
    cmd_stderr="$(mktemp)" || { rm -rf "$corruption_backup"; print_error "verify-closure: mktemp failed"; return "$AUDIT_EXIT_INTERNAL"; }
    # FR-006 (review finding I-6): run the recorded command in a FRESH bash
    # process with cwd = the repository root and stdin closed -- never
    # `eval`ed in this shell, where it would inherit set -euo pipefail, this
    # script's functions and non-exported variables, and the caller's cwd.
    # Only the exported environment is inherited (as for any child process).
    # `|| true`: a non-zero exit from the recorded command must NOT abort
    # this function under set -e before the corruption guard's detect step
    # runs (review finding 2) -- the commands most likely to corrupt evidence
    # are also the most likely to fail. A failing command yields a partial
    # summary that then MISMATCHes, which is the correct outcome.
    #
    # The fresh process is started with BASH_ENV and ENV REMOVED: bash sources
    # $BASH_ENV before running a non-interactive `bash -c`, so a startup file
    # exported by the caller could otherwise rewrite the very result being
    # verified. It runs under the ExecutionPolicy bounds (nice/ionice via
    # audit_dispatch_bounded, Principle XIII) and, when
    # AUDIT_VERIFY_COMMAND_TIMEOUT is set, under timeout(1) -- whose process-
    # group kill also reaches the command's own children. A timeout is an
    # INCONCLUSIVE result (exit 6), reported after the corruption guard below
    # has run, never read as a match or a mismatch.
    local -a runner=(env -u BASH_ENV -u ENV bash -c "$recorded_command")
    local cmd_timeout="${AUDIT_VERIFY_COMMAND_TIMEOUT:-}"
    if [[ -n "$cmd_timeout" ]]; then
        if [[ ! "$cmd_timeout" =~ ^[1-9][0-9]*$ ]]; then
            rm -rf "$corruption_backup" "$cmd_stderr"
            print_error "verify-closure: AUDIT_VERIFY_COMMAND_TIMEOUT must be a positive integer of seconds (got '$cmd_timeout')"
            return "$AUDIT_EXIT_USAGE"
        fi
        runner=(timeout -k 5 "$cmd_timeout" "${runner[@]}")
    fi
    local cmd_rc=0
    fresh_summary="$(cd "$cmd_root" && audit_dispatch_bounded "${runner[@]}" </dev/null 2>"$cmd_stderr")" || cmd_rc=$?
    # Constitution Principle III (review finding I-4): the command's stderr
    # is shown to the operator, but only AFTER it passes through the redactor.
    if [[ -s "$cmd_stderr" ]]; then
        printf '%s\n' "$(audit_redact_before_write "$(cat "$cmd_stderr")")" >&2
    fi
    rm -f "$cmd_stderr"

    local own_evidence_dir corruption_incidents
    own_evidence_dir="${qa_root_abs#"$cmd_root"/}/$item_id"
    corruption_incidents="$(audit_detect_and_revert_corruption "$corruption_snapshot" "$own_evidence_dir" "$corruption_backup" "$cmd_root")" || true
    rm -rf "$corruption_backup"
    if [[ -n "$corruption_incidents" ]]; then
        # m4: the incident log lives under the evidence tree being audited
        # (AUDIT_QA_ROOT), or AUDIT_INCIDENT_LOG_DIR when set -- never
        # unconditionally under this repo's real docs/qa.
        local run_log_dir="${AUDIT_INCIDENT_LOG_DIR:-$qa_root_abs/zero_shortcomings_audit}"
        mkdir -p "$run_log_dir"
        local run_log="$run_log_dir/$(audit_run_id).log"
        {
            printf '[%s] verify-closure %s: command `%s` corrupted and reverted the following tracked evidence file(s) outside %s:\n' \
                "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$item_id" \
                "$(audit_redact_before_write "$recorded_command")" "$own_evidence_dir"
            printf '%s' "$corruption_incidents"
        } >> "$run_log"
        print_warning "verify-closure: $item_id's command corrupted $(printf '%s' "$corruption_incidents" | grep -c .) tracked evidence file(s) outside its own evidence dir — reverted; incident logged to $run_log"
    fi

    if [[ -n "$cmd_timeout" && ( "$cmd_rc" -eq 124 || "$cmd_rc" -eq 137 ) ]]; then
        print_error "verify-closure: $item_id's recorded command timed out after ${cmd_timeout}s -- INCONCLUSIVE, neither a match nor a mismatch"
        return "$AUDIT_EXIT_TIMEOUT"
    fi

    if [[ "$fresh_summary" == "$recorded_summary" ]]; then
        print_success "verify-closure: $item_id reproduced its recorded evidence"
        return 0
    fi

    # Constitution Principle III / /speckit-analyze finding D2: redact any
    # credential-shaped VALUE before either summary ever reaches a print
    # line -- a credential-adjacent item's result_summary could otherwise
    # leak a secret value into the tracked run log. Comparison above uses
    # the RAW (unredacted) values so a real, non-credential mismatch is
    # still detected correctly; only what gets PRINTED is redacted.
    local recorded_summary_safe fresh_summary_safe
    recorded_summary_safe="$(audit_redact_before_write "$recorded_summary")"
    fresh_summary_safe="$(audit_redact_before_write "$fresh_summary")"
    print_error "verify-closure: $item_id MISMATCH — recorded '$recorded_summary_safe', got '$fresh_summary_safe'"
    if [[ "$reopen_on_mismatch" == "true" ]]; then
        print_warning "verify-closure: reopening $item_id (--reopen-on-mismatch)"
        # FR-013: a failing reopen is REPORTED, never swallowed -- the
        # mismatch would otherwise exist nowhere but this terminal.
        if ! "$WORKABLE_ITEMS_BIN" reopen --id "$item_id" --db "$WORKABLE_ITEMS_DB" \
            --why "test-failed" --who "AI" --when "$(date -u '+%Y-%m-%d')" \
            --incident "$evidence_file"; then
            print_error "verify-closure: reopen FAILED for $item_id -- the mismatch is NOT recorded in the tracker ($WORKABLE_ITEMS_DB); reopen it manually"
            return 3
        fi
    fi
    return 1
}

# audit_redact_before_write <text> -- reuses this project's own established
# §11.4.10.A credential-shape detection -- the keyword alternation this
# project's credential_scan_lib.sh (the shared §11.4.10/§11.4.10.A leak-audit
# library at constitution/scripts/hooks/credential_scan_lib.sh, exported as
# HELIX_CRED_VALUE_PATTERN) already defines and uses to DETECT a credential --
# to REDACT the VALUE half of a keyword=value credential-shaped pair while
# preserving the keyword/variable NAME, per constitution Principle III
# ("No secret values MAY appear in log output ... "; names stay loggable, only
# values are secret). This function's keyword set is a CITATION of that
# library's own detector-1 keyword alternation
# (password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|
# client[_-]?secret), never a second, independently-invented pattern set
# (§11.4.251 byte-identical-fork-prohibition / role-as-data-pack applied to
# detection logic: one detection vocabulary, cited by reference, not forked).
#
# The library itself (helix_cred_scan_file / HELIX_CRED_VALUE_PATTERN) is a
# whole-file/whole-stream binary DETECTOR (grep-shaped: "does this file
# contain a credential?"), consumed elsewhere in this project (e.g.
# constitution/scripts/gates/lib/execution_record.sh's `_xr_redact`) by
# blanking the ENTIRE captured stream on a hit -- correct for an opaque
# captured stream, but it would erase the variable NAME too, which Principle
# III requires to remain loggable. This function performs the narrower,
# name-preserving redaction the brief for this task requires, using the SAME
# cited keyword vocabulary rather than the whole-file blank-out strategy.
#
# EXTENSION (Task 5C security review, agent a3c502c254c1b2ffc, Critical
# finding): the cited library's keyword alternation alone does not cover
# this project's own documented credential-variable surface --
# BOBA_MASTER_KEY ("Loss = total credential loss", CLAUDE.md) does not
# contain "api_key"/"access_token"/"auth_token" as a substring; BOBA_API_TOKEN
# likewise (no "access"/"auth" prefix on "token"); and per-tracker
# `<TRACKER>_COOKIES` ("cookie values NEVER enter logs", CLAUDE.md) is a
# shape the upstream credential_scan_lib.sh detector never covers either
# (confirmed absent there by direct grep). Per §11.4.251 (cite, don't fork),
# this is NOT a second independently-invented detector: the cited generic
# keyword set is kept in full, and three bare keywords -- `key`, `token`,
# `cookies` -- are added as an explicit, documented project-specific
# extension covering exactly the named gap, not a silent divergent pattern
# set. Bare `key`/`token` favor recall over precision (a non-credential
# "...key=" or "...token=" value is over-redacted rather than a real secret
# passing through) -- the same tradeoff the cited `secret` keyword already
# makes.
#
# Prints <text> to stdout with the VALUE half of every
# `<keyword><sep><value>` credential-shaped match replaced with
# `<redacted-per-§11.4.10>`; ordinary text with no such match passes through
# byte-identical. The `I` sed flag (GNU sed case-insensitive substitution) is
# required so RUTRACKER_PASSWORD / KINOZAL_PASSWORD / etc. match the
# lowercase `password` alternation -- CLAUDE.md's own credential variable
# list is exactly this shape (RUTRACKER_*, KINOZAL_*, NNMCLUB_*, IPTORRENTS_*,
# BOBA_MASTER_KEY, BOBA_API_TOKEN, <TRACKER>_COOKIES -- every one of those
# names CONTAINS one of the cited-or-extended keywords).
audit_redact_before_write() {
    # Minor finding, Task 5C security review (agent a3c502c254c1b2ffc): under
    # this file's `set -euo pipefail`, `$1` on a no-argument call is an
    # unbound-variable abort rather than a clear, callable-with-no-input
    # no-op. No current caller invokes this with zero arguments, but a
    # redaction helper failing loudly-but-uninformatively on empty input is
    # itself worth hardening cheaply.
    local text="${1:-}"
    # Review finding I-4 (2026-09-26): a single `keyword<sep>\S+` rule leaked
    # (a) a JSON quoted key `"api_key": "v"` (the closing quote sat between
    # keyword and separator), (b) the tail of a quoted multi-word value
    # `password='a b'`, (c) everything after the first token of a cookie
    # string `X_COOKIES=a=1 b=2`, (d) URL `user:pass@host` credentials and
    # (e) `Bearer <token>` values. The rules below run IN ORDER, one sed
    # expression each, rather than one giant regex:
    #   1. cookie keys (`*_COOKIES=`, `Cookie:` headers) redact to end of line,
    #      because a cookie string is `k=v; k2=v2 ...` with spaces inside it;
    #   2. `Authorization:` header lines redact to end of line;
    #   3. URL userinfo `scheme://user:PASS@` keeps the user, drops PASS; a
    #      token-only `scheme://TOKEN@` (GitHub PAT clone form) is dropped
    #      whole; `curl -u user:PASS` keeps the user, drops PASS;
    #   4. `Bearer`/`Basic` followed by a credential token;
    #   5. `<keyword>["']?<sep>"quoted value"` (double-quoted, multi-word);
    #   6. the same with single quotes;
    #   7. `<keyword>["']?<sep>unquoted-token` (original rule; skips a value
    #      that starts with a quote, which 5/6 already handled);
    #   8. a space-separated CLI flag `--<...keyword> value`;
    #   9. (after rule 3) a password glued to a mysql-family `-p` flag
    #      (`mysql -uroot -pSECRET`) -- case-SENSITIVE on purpose, so the
    #      port flag `-P3306` is never touched, and only on a line that runs
    #      a mysql-family client, so `mkdir -p dir` / `git log -p` stay intact.
    # Known limits (stated, not hidden -- see docs/scripts guide): an escaped
    # quote inside a quoted value (`"a\"b"`) ends the match early; a secret
    # split across lines, a secret with no recognisable keyword in front of
    # it (a bare token or base64 blob), and a value introduced by a separator
    # other than `:`/`=`/whitespace-after-a-flag are NOT redacted. Bare
    # `key`/`token`/`bearer` favour recall: some non-secret text is
    # over-redacted rather than a secret passing through.
    local kw='(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|key|token|cookies)'
    # Separators: `:`, `=`, the fat arrow `=>` (Perl/Ruby hash style) and the
    # URL-encoded `%3D` (=) / `%3A` (:) -- the latter two were review misses
    # (BOB-248): `db_password => x` kept `x`, `key%3DSECRET` kept `SECRET`.
    local sep="[\"']?[[:space:]]*(=>|[:=]|%3[AaDd])[[:space:]]*"
    local r='<redacted-per-§11.4.10>'
    printf '%s' "$text" | sed -E \
        -e "s/([A-Za-z0-9_-]*cookies?${sep})(.*)/\\1${r}/I" \
        -e "s/(authorization${sep})(.*)/\\1${r}/I" \
        -e "s#([A-Za-z][A-Za-z0-9+.-]*://[^/:@[:space:]]+:)[^@/[:space:]]+@#\\1${r}@#g" \
        -e "s#([A-Za-z][A-Za-z0-9+.-]*://)[^/:@[:space:]]+@#\\1${r}@#g" \
        -e "s#([[:space:]]-u[[:space:]]+[^:[:space:]]+:)[^[:space:]]+#\\1${r}#g" \
        -e "s#((^|[[:space:]/])(mysql|mysqldump|mysqladmin|mysqlimport|mysqlshow|mariadb|mariadb-dump)[[:space:]].*[[:space:]]-p)[^[:space:]<]+#\\1${r}#" \
        -e "s/((bearer|basic)[[:space:]]+)[^[:space:]\"',;<]+/\\1${r}/Ig" \
        -e "s/(${kw}${sep})\"[^\"]*\"/\\1\"${r}\"/Ig" \
        -e "s/(${kw}${sep})'[^']*'/\\1'${r}'/Ig" \
        -e "s/(${kw}${sep})[^[:space:]\"'<][^[:space:]]*/\\1${r}/Ig" \
        -e "s/(--?[A-Za-z0-9_-]*${kw}[[:space:]]+)[^-[:space:]<][^[:space:]]*/\\1${r}/Ig"
}

# audit_snapshot_tracked_evidence [<backup-dir>] [<repo-root>] — prints every
# git-tracked file under docs/qa/ as one "<blob-hash><TAB><path>" line, and
# (with <backup-dir>) copies every already-dirty tracked file there.
#
# Resolves the repo root FRESH at call time via `git rev-parse
# --show-toplevel` (falling back to the fixed $REPO_ROOT anchor only if the
# current working directory is not inside a git worktree at all), rather
# than using the fixed $REPO_ROOT captured when this file was sourced.
# Root-caused during Task 6 TDD (RED-run 2, §11.4.102): $REPO_ROOT is set
# once, from the PHYSICAL location of this script file on disk, at source
# time -- it does not track a later `cd`. The test for this guard
# deliberately sources this file from the real repo root and then `cd`s
# into a disposable, throwaway git repository so it can exercise real
# corruption-and-revert behaviour without any risk to this project's own
# tracked evidence; with the fixed $REPO_ROOT, the guard silently inspected
# the real boba checkout instead of that throwaway repo and could never see
# the corruption the test injects. This also matches how this exact guard
# behaves correctly in production: cmd_verify_closure always runs with the
# working directory inside this repo, where `git rev-parse --show-toplevel`
# resolves to the same path $REPO_ROOT already does.
audit_snapshot_tracked_evidence() {
    local backup_dir="${1:-}"
    local repo_root="${2:-}"
    if [[ -z "$repo_root" ]]; then
        repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || repo_root="$REPO_ROOT"
    fi
    # Task 6 review finding 1 (Critical): a file that is ALREADY modified vs
    # HEAD holds uncommitted legitimate work; `git checkout --` restores from
    # HEAD and would destroy it. Save a byte copy of every already-dirty file
    # so detect can restore the PRE-COMMAND bytes instead. NUL-delimited
    # (`-z`) so a path with spaces or other special characters round-trips.
    if [[ -n "$backup_dir" ]]; then
        local d
        while IFS= read -r -d '' d; do
            [[ -f "$repo_root/$d" ]] || continue
            mkdir -p "$backup_dir/$(dirname "$d")"
            cp -p "$repo_root/$d" "$backup_dir/$d"
        done < <(git -C "$repo_root" diff -z --name-only -- 'docs/qa' 2>/dev/null || true)
    fi
    # Snapshot format: one line per file, "<blob-hash><TAB><path>". The hash
    # comes FIRST and the path is everything after the first tab, so a path
    # containing spaces (or tabs) is carried verbatim (review finding I-2(b):
    # the old space-delimited "<path> <hash>" format split such a path).
    # Paths are enumerated NUL-delimited via `ls-files -z`. A path containing
    # a NEWLINE cannot be carried by `git hash-object --stdin-paths` (which is
    # newline-delimited) nor by this line format; such a path is skipped with
    # an explicit warning, never silently.
    #
    # One batched `git hash-object --stdin-paths` process for the whole set
    # (a per-file subprocess was measured at ~2m31s over this repo's 1511
    # tracked docs/qa files, twice per closure check). Files listed by
    # ls-files but absent from the worktree are filtered first, since
    # --stdin-paths would abort on a missing path.
    local -a paths=()
    local f nl=$'\n'
    while IFS= read -r -d '' f; do
        if [[ "$f" == *"$nl"* ]]; then
            print_warning "corruption guard: cannot snapshot a path containing a newline, skipped: ${f//$nl/\\n}" >&2
            continue
        fi
        [[ -f "$repo_root/$f" ]] && paths+=("$f")
    done < <(git -C "$repo_root" ls-files -z -- 'docs/qa' 2>/dev/null || true)
    [[ ${#paths[@]} -gt 0 ]] || return 0
    local -a hashes=()
    mapfile -t hashes < <(cd "$repo_root" && printf '%s\n' "${paths[@]}" | git hash-object --stdin-paths)
    if [[ ${#hashes[@]} -ne ${#paths[@]} ]]; then
        print_error "corruption guard: hashed ${#hashes[@]} of ${#paths[@]} tracked evidence files -- snapshot incomplete"
        return 1
    fi
    local i
    for i in "${!paths[@]}"; do
        printf '%s\t%s\n' "${hashes[$i]}" "${paths[$i]}"
    done
}

# audit_detect_and_revert_corruption <snapshot> <own-item-evidence-dir>
#     [<backup-dir>] [<repo-root>] —
# diffs the current tracked docs/qa/ state against <snapshot> (the
# "<hash><TAB><path>" lines from audit_snapshot_tracked_evidence). Any file
# OUTSIDE <own-item-evidence-dir> that was MODIFIED or DELETED is restored --
# from <backup-dir> when the file was already dirty before the command
# (preserving uncommitted work), otherwise via `git checkout --` -- and its
# path is printed (one per line) as an incident. A change INSIDE
# <own-item-evidence-dir> is a legitimate write and is left untouched
# (Review Focus item 2). <repo-root> defaults to the same fresh
# `git rev-parse --show-toplevel` resolution as the snapshot function.
#
# History (kept because it explains the format): an earlier version looked
# the pre-command hash up with `grep -F "^$f "`, which treats `^` as a
# literal caret and therefore never matched -- silently reporting "no
# corruption" on every call (a §11.4.201(6) false-null, masked because the
# failure happened mid-pipeline inside `$(...)`). The later awk `$1 == path`
# lookup fixed that but split paths containing spaces (review finding
# I-2(b)); the tab-delimited, hash-first format below removes both classes.
audit_detect_and_revert_corruption() {
    local snapshot="$1" own_dir="$2" backup_dir="${3:-}" repo_root="${4:-}"
    if [[ -z "$repo_root" ]]; then
        repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || repo_root="$REPO_ROOT"
    fi
    local incidents="" line before f after
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        before="${line%%$'\t'*}"
        f="${line#*$'\t'}"
        case "$f" in
            "$own_dir"/*) continue ;;
        esac
        if [[ -f "$repo_root/$f" ]]; then
            after="$(git -C "$repo_root" hash-object -- "$repo_root/$f")"
            [[ "$before" == "$after" ]] && continue
        fi
        # Modified OR deleted (review finding I-2(a): a deletion was
        # previously skipped by `[[ -f ]] || continue` and never restored).
        if [[ -n "$backup_dir" && -f "$backup_dir/$f" ]]; then
            mkdir -p "$(dirname "$repo_root/$f")"
            cp -p "$backup_dir/$f" "$repo_root/$f"
        else
            git -C "$repo_root" checkout -- "$f"
        fi
        incidents+="$f"$'\n'
    done <<< "$snapshot"
    printf '%s' "$incidents"
}

# Standing-check re-verification bounds (SC-005). The defaults keep the
# advisory pre-build stage inside its own 300 s timeout: at most
# AUDIT_REVERIFY_DEFAULT closed items per run, each recorded command bounded
# by AUDIT_REVERIFY_ITEM_TIMEOUT seconds, and an item is only STARTED when its
# full timeout still fits inside AUDIT_REVERIFY_BUDGET seconds of re-verify
# time. The item timeout is sized from a measurement, not a guess: the one
# closed item on the live tracker that records a command took 130 s at nice 19
# (2026-09-26), so 150 s lets it finish instead of reading as a timeout.
AUDIT_REVERIFY_DEFAULT="${AUDIT_REVERIFY_DEFAULT:-2}"
AUDIT_REVERIFY_ITEM_TIMEOUT="${AUDIT_REVERIFY_ITEM_TIMEOUT:-150}"
AUDIT_REVERIFY_BUDGET="${AUDIT_REVERIFY_BUDGET:-210}"

# audit_evidence_has_command <item-id> — true when the item's closure evidence
# file carries a re-runnable **Command:** field (the same file and the same
# pattern verify-closure uses).
audit_evidence_has_command() {
    local f
    f="$(audit_find_evidence_file "$1")" || return 1
    [[ -n "$f" ]] || return 1
    grep -qP '\*\*Command:\*\* `.*`' "$f"
}

# list_closed_risk_ordered — every CLOSED (…(→ Fixed.md)) item, never an
# Obsolete one, highest risk first with the same ordering rule as the open
# backlog (reopens DESC, last_modified DESC, severity rank, id).
list_closed_risk_ordered() {
    sqlite3 "$WORKABLE_ITEMS_DB" \
        "SELECT i.atm_id FROM items i
         WHERE i.status LIKE '%(→ Fixed.md)' AND i.status NOT LIKE 'Obsolete%'
         GROUP BY i.atm_id
         ORDER BY (SELECT count(*) FROM item_history h WHERE h.atm_id = i.atm_id AND h.event_type = 'Reopened') DESC,
                  max(i.last_modified) DESC,
                  min($(audit_severity_rank_sql i.severity)),
                  i.atm_id;"
}

# audit_standing_reverify <max-items> — re-runs verify-closure over the
# highest-risk closed items whose evidence records a command. Each re-run is
# a separate, bounded verify-closure process: its own corruption guard runs,
# its incidents are logged beside the standing log, and --reopen-on-mismatch
# is NEVER passed (the standing mode reports; it never edits the tracker).
# Prints ONE space-separated marker fragment; returns 1 when any re-run was
# not a clean match (the caller turns that into status=degraded).
audit_standing_reverify() {
    local max="$1" logdir="$2"
    if [[ "$max" -eq 0 ]]; then
        printf 'reverify=off'
        return 0
    fi
    local -a ids=() mismatch=() invalid=() timedout=() refused=() skipped=()
    local id checked=0 matched=0 rc started=$SECONDS
    local all
    all="$(list_closed_risk_ordered)" || { printf 'reverify=failed'; return 1; }
    while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        [[ "${#ids[@]}" -ge "$max" ]] && break
        audit_evidence_has_command "$id" && ids+=("$id")
    done <<< "$all"
    for id in "${ids[@]}"; do
        if (( SECONDS - started + AUDIT_REVERIFY_ITEM_TIMEOUT > AUDIT_REVERIFY_BUDGET )); then
            skipped+=("$id"); continue
        fi
        rc=0
        # A fresh process per item; the recorded command inside it runs under
        # the ExecutionPolicy bounds. The outer timeout is only a backstop (the
        # inner one lets the corruption guard still run). A busy FR-011 lock
        # is not waited for here (wait 0): it is recorded as a refusal so the
        # run stays inside the pre-build stage's own timeout.
        AUDIT_VERIFY_COMMAND_TIMEOUT="$AUDIT_REVERIFY_ITEM_TIMEOUT" AUDIT_INCIDENT_LOG_DIR="$logdir" \
            AUDIT_VERIFY_LOCK_WAIT=0 \
            timeout -k 5 $((AUDIT_REVERIFY_ITEM_TIMEOUT + 60)) \
            bash "$SCRIPT_DIR/zero_shortcomings_audit.sh" verify-closure "$id" >/dev/null 2>&1 || rc=$?
        checked=$((checked + 1))
        case "$rc" in
            0) matched=$((matched + 1)) ;;
            1) mismatch+=("$id") ;;
            2) invalid+=("$id") ;;
            6|124|137) timedout+=("$id") ;;
            *) refused+=("$id") ;;
        esac
    done
    local out="reverify=checked:${checked},match:${matched},mismatch:${#mismatch[@]}"
    local IFS=,
    [[ ${#mismatch[@]} -gt 0 ]] && out+=" reverify_mismatch=${mismatch[*]}"
    [[ ${#invalid[@]} -gt 0 ]] && out+=" reverify_invalid_evidence=${invalid[*]}"
    [[ ${#timedout[@]} -gt 0 ]] && out+=" reverify_timeout=${timedout[*]}"
    [[ ${#refused[@]} -gt 0 ]] && out+=" reverify_refused=${refused[*]}"
    [[ ${#skipped[@]} -gt 0 ]] && out+=" reverify_skipped_budget=${skipped[*]}"
    printf '%s' "$out"
    [[ $((checked - matched + ${#skipped[@]})) -eq 0 ]]
}

cmd_standing_check() {
    # Advisory and non-blocking by design (always exit 0 once the arguments
    # are valid), but NEVER a false-null (§11.4.201(6)): a failing sub-check
    # or a closed item that no longer reproduces its evidence is recorded as
    # an explicit status=degraded marker, not a normal-looking line.
    local reverify="$AUDIT_REVERIFY_DEFAULT"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --reverify)
                if [[ $# -lt 2 || ! "$2" =~ ^[0-9]+$ ]]; then
                    print_error "standing-check: --reverify requires a non-negative integer (the number of closed items to re-verify; 0 disables)"
                    return "$AUDIT_EXIT_USAGE"
                fi
                reverify="$2"; shift 2 ;;
            *) print_error "standing-check: unknown option: $1"; return "$AUDIT_EXIT_USAGE" ;;
        esac
    done
    local v
    for v in AUDIT_REVERIFY_DEFAULT AUDIT_REVERIFY_ITEM_TIMEOUT AUDIT_REVERIFY_BUDGET; do
        if [[ ! "${!v}" =~ ^[0-9]+$ ]]; then
            print_error "standing-check: $v must be a non-negative integer (got '${!v}')"
            return "$AUDIT_EXIT_USAGE"
        fi
    done
    if [[ "$AUDIT_REVERIFY_ITEM_TIMEOUT" -eq 0 ]]; then
        print_error "standing-check: AUDIT_REVERIFY_ITEM_TIMEOUT must be at least 1 second"
        return "$AUDIT_EXIT_USAGE"
    fi
    local logdir="${AUDIT_STANDING_LOG_DIR:-$REPO_ROOT/docs/qa/zero_shortcomings_audit}"
    mkdir -p "$logdir"
    local run_id status="ok" reasons="" failed="" body="" surface out rc
    run_id="$(audit_run_id)"
    for surface in backlog gates escapes; do
        if [[ "$surface" == "backlog" && ! -r "$WORKABLE_ITEMS_DB" ]]; then
            # Checked BEFORE any sqlite3 call: sqlite3 silently creates a
            # missing file, which would turn absence into a healthy empty DB.
            status="degraded"; reasons+="db_missing,"; failed+="backlog,"
            continue
        fi
        rc=0
        out="$(cmd_enumerate --json --surface "$surface")" || rc=$?
        if [[ "$rc" -ne 0 ]]; then
            status="degraded"; reasons+="${surface}_rc${rc},"; failed+="${surface},"
            continue
        fi
        out="${out#\{}"; out="${out%\}}"
        [[ -n "$out" ]] && body+="${out},"
    done
    body="{${body%,}}"
    # SC-005: re-verify the highest-risk closed items. A closed item that no
    # longer reproduces its recorded evidence is a finding; so is one that
    # could not be checked (timeout, invalid evidence, refusal) -- none of
    # those may read as a clean run.
    local reverify_marker=""
    if [[ -r "$WORKABLE_ITEMS_DB" ]]; then
        if ! reverify_marker="$(audit_standing_reverify "$reverify" "$logdir")"; then
            status="degraded"; reasons+="reverify,"
        fi
    elif [[ "$reverify" -gt 0 ]]; then
        reverify_marker="reverify=skipped_db_missing"
    fi
    local marker="status=${status}"
    if [[ "$status" == "degraded" ]]; then
        marker+=" reason=${reasons%,}"
        [[ -n "$failed" ]] && marker+=" failed=${failed%,}"
        print_warning "standing-check degraded (${reasons%,}) -- advisory only, exiting 0"
    fi
    [[ -n "$reverify_marker" ]] && marker+=" ${reverify_marker}"
    local line
    # Constitution Principle III: redact BEFORE the value touches the log file.
    line="$(audit_redact_before_write "$run_id mode=standing-check $marker $body")" || line="$run_id mode=standing-check status=degraded reason=redaction_failed"
    printf '%s\n' "$line" >> "$logdir/${run_id}.log"
    print_info "standing-check: $line"
    return 0
}
main "$@"
