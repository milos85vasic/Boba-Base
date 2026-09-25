#!/usr/bin/env bash
# audit_run_id.sh — the shared run-id convention for every audit artifact this
# feature writes, matching the timestamp+pid shape already used across
# docs/qa/**/ (e.g. 20260925T113437Z-pid3872998). Timestamp+pid, not a
# counter, so two concurrent invocations never collide (Review Focus item 5).
audit_run_id() {
    printf '%sZ-pid%d\n' "$(date -u '+%Y%m%dT%H%M%S')" "$$"
}
