#!/usr/bin/env bash
# audit_ledger_parser.sh — reads docs/QA_DISCOVERY_LEDGER.md's own documented
# "## Schema" (channel/escape-audit/new-check per `### `-headed entry) without
# ever rewriting the ledger itself. The ledger stays a human/agent-edited
# document (research.md §3); this is read-only enumeration, per FR-003.
#
# Entry-splitting approach: split the file on lines starting with "### ",
# discarding everything before the first such heading (the ledger's own
# preamble/schema-doc section, which is not an entry).

_audit_ledger_require_readable() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        printf 'audit_ledger_parser: ledger file not found: %s\n' "$path" >&2
        return 1
    fi
    if [[ ! -s "$path" ]]; then
        printf 'audit_ledger_parser: ledger file is empty: %s\n' "$path" >&2
        return 1
    fi
}

# _audit_ledger_entries <path> — prints each entry's body (everything after
# its "### " heading line, up to the next "### " or end of file) separated by
# a NUL-safe delimiter line "@@@AUDIT_ENTRY@@@".
_audit_ledger_entries() {
    local path="$1"
    awk '
        /^### / { if (started) { print "@@@AUDIT_ENTRY@@@" } started = 1; next }
        started { print }
        END { if (started) { print "@@@AUDIT_ENTRY@@@" } }
    ' "$path"
}

_audit_ledger_field_present() {
    local entry="$1" field="$2"
    printf '%s\n' "$entry" | grep -qE "\\*\\*${field}:\\*\\*[[:space:]]*[^[:space:]]"
}

_audit_ledger_channel_is_automated() {
    local entry="$1"
    printf '%s\n' "$entry" | grep -qE '\*\*channel:\*\*[[:space:]]*`?automated-helixqa`?'
}

audit_ledger_count_open_escapes() {
    local path="$1"
    _audit_ledger_require_readable "$path" || return 1
    local count=0
    local entry=""
    while IFS= read -r line; do
        if [[ "$line" == "@@@AUDIT_ENTRY@@@" ]]; then
            if ! _audit_ledger_channel_is_automated "$entry" \
               && ! _audit_ledger_field_present "$entry" "new-check"; then
                count=$((count + 1))
            fi
            entry=""
        else
            entry+="$line"$'\n'
        fi
    done < <(_audit_ledger_entries "$path")
    printf '%d\n' "$count"
}

audit_ledger_count_malformed() {
    local path="$1"
    _audit_ledger_require_readable "$path" || return 1
    local count=0
    local entry=""
    while IFS= read -r line; do
        if [[ "$line" == "@@@AUDIT_ENTRY@@@" ]]; then
            if ! _audit_ledger_channel_is_automated "$entry" \
               && ! _audit_ledger_field_present "$entry" "escape-audit"; then
                count=$((count + 1))
            fi
            entry=""
        else
            entry+="$line"$'\n'
        fi
    done < <(_audit_ledger_entries "$path")
    printf '%d\n' "$count"
}
