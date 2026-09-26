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
      Exit: 0 match, 1 mismatch (or usage error), 2 no/insufficient
      evidence, 3 mismatch but the tracker reopen FAILED.
      Corruption incidents are logged under $AUDIT_QA_ROOT/zero_shortcomings_audit
      (or $AUDIT_INCIDENT_LOG_DIR when set).
  standing-check
      The recurring, non-blocking mode wired into pre_build_verification.sh.
      Writes its run log to $AUDIT_STANDING_LOG_DIR when set.

Options:
  -h, --help    Show this help and exit.
USAGE
}

count_backlog_open() {
    sqlite3 "$WORKABLE_ITEMS_DB" \
        "SELECT count(*) FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete';"
}

list_backlog_risk_ordered() {
    # FR-012: reopens DESC then last_modified DESC. items has no reopens_count
    # column; the count is derived from item_history 'Reopened' events. The open
    # predicate is identical to count_backlog_open above.
    sqlite3 "$WORKABLE_ITEMS_DB" \
        "SELECT i.atm_id FROM items i
         WHERE i.status NOT LIKE '%(→ Fixed.md)' AND i.status != 'Obsolete'
         ORDER BY (SELECT count(*) FROM item_history h WHERE h.atm_id = i.atm_id AND h.event_type = 'Reopened') DESC,
                  i.last_modified DESC, i.atm_id;"
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
                    return 1
                fi
                surface="$2"; shift 2 ;;
            --sort-by-risk) sort_by_risk=true; shift ;;
            *) print_error "enumerate: unknown option: $1"; return 1 ;;
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
            return 1
            ;;
    esac

    if [[ "$surface" == "all" || "$surface" == "backlog" ]]; then
        audit_require_db || return 1
    fi

    if [[ "$sort_by_risk" == "true" ]]; then
        if [[ "$surface" != "backlog" ]]; then
            print_error "enumerate: --sort-by-risk applies only to --surface backlog (got '$surface')"
            return 1
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
        -h|--help|"") usage; [[ "$mode" == "" ]] && return 1 || return 0 ;;
        enumerate) shift; cmd_enumerate "$@" ;;
        verify-closure) shift; cmd_verify_closure "$@" ;;
        standing-check) shift; cmd_standing_check "$@" ;;
        *) print_error "unknown mode: $mode"; usage; return 1 ;;
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
    local rows missing
    rows="$(sqlite3 -separator '|' "$WORKABLE_ITEMS_DB" \
        "SELECT DISTINCT i.atm_id,
                CASE WHEN b.unblock_condition IS NULL OR trim(b.unblock_condition) = ''
                     THEN 'MISSING-UNBLOCK-CONDITION'
                     ELSE b.unblock_condition END
         FROM items i
         LEFT JOIN operator_block_details b ON b.atm_id = i.atm_id
         WHERE i.status = 'Operator-blocked'
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

cmd_verify_closure() {
    local item_id="${1:-}"
    local reopen_on_mismatch=false
    local require_layer="runtime"
    if [[ -z "$item_id" ]]; then
        print_error "verify-closure: an item id is required"
        return 1
    fi
    # m3: the id is used to build a filesystem path below, so validate it
    # BEFORE any path use: [A-Za-z0-9._-] only, starting with a letter or
    # digit (no option-like leading `-`, no `.`/`..` directory names), and
    # never containing `..` or `/`.
    if [[ ! "$item_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ || "$item_id" == *..* ]]; then
        print_error "verify-closure: invalid item id '$item_id' (allowed: ^[A-Za-z0-9][A-Za-z0-9._-]*\$, no '..' or '/')"
        return 1
    fi
    shift
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --reopen-on-mismatch) reopen_on_mismatch=true; shift ;;
            --require-layer)
                if [[ $# -lt 2 || -z "$2" ]]; then
                    print_error "verify-closure: --require-layer requires a value (source|artifact|runtime)"
                    return 1
                fi
                require_layer="$2"; shift 2 ;;
            *) print_error "verify-closure: unknown option: $1"; return 1 ;;
        esac
    done
    case "$require_layer" in
        source|artifact|runtime) ;;
        *) print_error "verify-closure: unrecognized --require-layer value '$require_layer' (expected source|artifact|runtime)"; return 1 ;;
    esac

    # Resolve the evidence root to an absolute path once, so neither the
    # recorded command's cwd (below) nor the incident-log location depends
    # on the directory this was invoked from.
    local qa_root_abs
    qa_root_abs="$(cd "$AUDIT_QA_ROOT" 2>/dev/null && pwd -P)" || qa_root_abs="$AUDIT_QA_ROOT"

    # `|| true` guards against `find` exiting non-zero when the target
    # directory does not exist at all (GNU find: "No such file or
    # directory"); under this script's `set -euo pipefail`, an unguarded
    # pipeline here would otherwise abort the whole script with a bare
    # exit 1 BEFORE the `-z "$evidence_file"` check below ever runs,
    # silently short-circuiting the deliberate "no evidence -> exit 2"
    # contract (root-caused, not guessed, per §11.4.102/§11.4.201(12)).
    local evidence_file
    evidence_file="$(find "$qa_root_abs/$item_id" -maxdepth 1 -name 'closure_evidence_*.md' 2>/dev/null | head -1)" || true
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
    # Validate the trimmed, lower-cased value against the closed set; a
    # whitespace-only or unknown value is not a declaration.
    local normalized_test_type
    normalized_test_type="$(printf '%s' "$declared_test_type" | tr '[:upper:]' '[:lower:]' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    case "$normalized_test_type" in
        unit|integration|e2e|security|stress|chaos|scaling|ui|challenge) ;;
        *)
            print_error "verify-closure: $item_id declares an invalid **Test Type:** '${normalized_test_type}' — allowed: unit|integration|e2e|security|stress|chaos|scaling|ui|challenge (FR-010)"
            return 2
            ;;
    esac

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

    local corruption_snapshot corruption_backup
    corruption_backup="$(mktemp -d)" || { print_error "verify-closure: mktemp failed -- cannot run the corruption guard"; return 1; }
    if ! corruption_snapshot="$(audit_snapshot_tracked_evidence "$corruption_backup" "$cmd_root")"; then
        rm -rf "$corruption_backup"
        print_error "verify-closure: could not snapshot tracked evidence -- refusing to run $item_id's command unguarded"
        return 1
    fi

    local fresh_summary cmd_stderr
    cmd_stderr="$(mktemp)" || { rm -rf "$corruption_backup"; print_error "verify-closure: mktemp failed"; return 1; }
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
    fresh_summary="$(cd "$cmd_root" && bash -c "$recorded_command" </dev/null 2>"$cmd_stderr")" || true
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
    #   8. a space-separated CLI flag `--<...keyword> value`.
    # Known limits (stated, not hidden -- see docs/scripts guide): an escaped
    # quote inside a quoted value (`"a\"b"`) ends the match early; a secret
    # split across lines, a secret with no recognisable keyword in front of
    # it (a bare token or base64 blob), and a value introduced by a separator
    # other than `:`/`=`/whitespace-after-a-flag are NOT redacted. Bare
    # `key`/`token`/`bearer` favour recall: some non-secret text is
    # over-redacted rather than a secret passing through.
    local kw='(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|key|token|cookies)'
    local sep="[\"']?[[:space:]]*[:=][[:space:]]*"
    local r='<redacted-per-§11.4.10>'
    printf '%s' "$text" | sed -E \
        -e "s/([A-Za-z0-9_-]*cookies?${sep})(.*)/\\1${r}/I" \
        -e "s/(authorization${sep})(.*)/\\1${r}/I" \
        -e "s#([A-Za-z][A-Za-z0-9+.-]*://[^/:@[:space:]]+:)[^@/[:space:]]+@#\\1${r}@#g" \
        -e "s#([A-Za-z][A-Za-z0-9+.-]*://)[^/:@[:space:]]+@#\\1${r}@#g" \
        -e "s#([[:space:]]-u[[:space:]]+[^:[:space:]]+:)[^[:space:]]+#\\1${r}#g" \
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

cmd_standing_check() {
    # Advisory and non-blocking by design (always exit 0), but NEVER a
    # false-null (§11.4.201(6)): a failing sub-check is recorded as an
    # explicit status=degraded marker, not a normal-looking line.
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
    local marker="status=${status}"
    if [[ "$status" == "degraded" ]]; then
        marker+=" reason=${reasons%,} failed=${failed%,}"
        print_warning "standing-check degraded (${reasons%,}) -- advisory only, exiting 0"
    fi
    local line
    # Constitution Principle III: redact BEFORE the value touches the log file.
    line="$(audit_redact_before_write "$run_id mode=standing-check $marker $body")" || line="$run_id mode=standing-check status=degraded reason=redaction_failed"
    printf '%s\n' "$line" >> "$logdir/${run_id}.log"
    print_info "standing-check: $line"
    return 0
}
main "$@"
