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
WORKABLE_ITEMS_DB="$REPO_ROOT/docs/workable_items.db"
# Overridable for testability (Task 4+4B review, 2026-09-25): the false-null
# regression test points this at a genuinely non-existent script to prove
# count_gates_unimplemented fails loud rather than silently reporting 0.
GATE_LEDGER_SCRIPT="${GATE_LEDGER_SCRIPT_OVERRIDE:-$REPO_ROOT/constitution/scripts/gates/cm_gate_ledger_ratchet.sh}"
COVERAGE_ESCAPE_LEDGER="$REPO_ROOT/docs/QA_DISCOVERY_LEDGER.md"

usage() {
    cat <<'USAGE'
Usage: zero_shortcomings_audit.sh <mode> [options]

Modes:
  enumerate [--json] [--surface backlog|gates|escapes]
      Read-only. Enumerates the three tracked surfaces. See
      specs/003-zero-shortcomings-audit/contracts/cli.md for the full contract.
  verify-closure <item-id> [--reopen-on-mismatch]
      Independently re-runs one item's recorded closure evidence.
  standing-check
      The recurring, non-blocking mode wired into pre_build_verification.sh.

Options:
  -h, --help    Show this help and exit.
USAGE
}

count_backlog_open() {
    sqlite3 "$WORKABLE_ITEMS_DB" \
        "SELECT count(*) FROM items WHERE status NOT LIKE '%(→ Fixed.md)' AND status != 'Obsolete';"
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
    printf '%s\n' "$output" >&2
    return 1
}

count_escapes_open() {
    audit_ledger_count_open_escapes "$COVERAGE_ESCAPE_LEDGER"
}

cmd_enumerate() {
    local json=false
    local surface="all"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --json) json=true; shift ;;
            --surface) surface="$2"; shift 2 ;;
            *) print_error "enumerate: unknown option: $1"; return 1 ;;
        esac
    done

    case "$surface" in
        blocked)
            # FR-007: honestly report every Operator-blocked item's specific,
            # observable unblock condition -- NEVER collapse to a bare count.
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

    local backlog="" gates="" escapes=""
    [[ "$surface" == "all" || "$surface" == "backlog" ]] && backlog="$(count_backlog_open)"
    [[ "$surface" == "all" || "$surface" == "gates" ]] && gates="$(count_gates_unimplemented)"
    [[ "$surface" == "all" || "$surface" == "escapes" ]] && escapes="$(count_escapes_open)"

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
        verify-closure) shift; print_error "verify-closure: not yet implemented (Task 5)"; return 2 ;;
        standing-check) shift; print_error "standing-check: not yet implemented (Task 7)"; return 2 ;;
        *) print_error "unknown mode: $mode"; usage; return 1 ;;
    esac
}


count_blocked_with_conditions() {
    sqlite3 -separator '|' "$WORKABLE_ITEMS_DB" \
        "SELECT i.atm_id, b.unblock_condition FROM items i
         JOIN operator_block_details b ON b.atm_id = i.atm_id
         WHERE i.status = 'Operator-blocked';"
}
main "$@"
