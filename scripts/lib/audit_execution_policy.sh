#!/usr/bin/env bash
# audit_execution_policy.sh — the single source of truth for this feature's
# Principle XIII host-resource bounds (data-model.md ExecutionPolicy entity).
# Changing a bound touches exactly this file, never a copy of these numbers
# scattered across the orchestrator (constitution §11.4.6 single-source-of-truth).
readonly AUDIT_MAX_PARALLEL_ITEMS=3
readonly AUDIT_NICE_LEVEL=19
readonly AUDIT_IONICE_CLASS=3
readonly AUDIT_RESOURCE_CEILING_PCT=40

# audit_dispatch_bounded <command...> — runs a command under the nice/ionice
# bounds above. ionice is optional (not present on every host); its absence
# MUST NOT fail the dispatch (host-portability, mirrors Principle IV's
# runtime-detection discipline applied to a resource-control tool instead of
# a container runtime).
audit_dispatch_bounded() {
    if command -v ionice >/dev/null 2>&1; then
        nice -n "$AUDIT_NICE_LEVEL" ionice -c "$AUDIT_IONICE_CLASS" -- "$@"
    else
        nice -n "$AUDIT_NICE_LEVEL" -- "$@"
    fi
}
