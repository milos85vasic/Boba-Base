#!/usr/bin/env bash
# scripts/lib/ownership.sh — shared helpers for feature 002-user-owned-downloads.
#
# Purpose:
#   Resolve the declared ownership scope (config/owned_paths.yaml), resolve the
#   operator's uid, and PROBE a location by actually creating a file in it and
#   reading the owner back.
#
# Usage:
#   source "${PROJECT_ROOT}/scripts/lib/ownership.sh"
#
# Inputs:   OWNED_PATHS_FILE (optional) overrides the scope file path.
# Outputs:  functions only; no side effects at source time.
# Side-effects: probe_location() creates and REMOVES one temporary file in the
#   probed directory. Nothing else writes.
# Dependencies: bash, stat, mktemp, python3 with PyYAML (for scope parsing).
# Cross-references:
#   specs/002-user-owned-downloads/contracts/startup-precondition.md
#   specs/002-user-owned-downloads/data-model.md (E1 scope, E4 probe result)
#
# WHY probe_location() WRITES A REAL FILE (FR-010b — the load-bearing rule):
#   Ownership of a location cannot be inferred from the location itself. A
#   directory owned by the operator can still receive files owned by someone
#   else, which is EXACTLY the defect this feature exists to fix: the download
#   root's children were uid 1000 while new writes landed at uid 100999.
#   Checking the directory's own owner, or the configured PUID, or "no error
#   occurred", are all PROXIES for the real condition. §11.4.201 forbids
#   asserting a proxy in place of the condition, and a probe that passes
#   because it never wrote anything is a false pass.

set -uo pipefail

# ---------------------------------------------------------------------------
# ownership_project_root — resolve the repository root from this file's path.
# ---------------------------------------------------------------------------
ownership_project_root() {
    local d
    d="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    printf '%s\n' "${d}"
}

# ---------------------------------------------------------------------------
# ownership_operator_uid / _gid — the identity everything must end up owned by.
#
# This is the uid of the account RUNNING the check, deliberately: the feature's
# definition of "correct owner" is "whoever started the system" (spec
# Assumptions), not a configured constant that could drift from reality.
# ---------------------------------------------------------------------------
ownership_operator_uid() { id -u; }
ownership_operator_gid() { id -g; }

# ---------------------------------------------------------------------------
# ownership_scope_file — path to the declared scope, overridable for tests.
# ---------------------------------------------------------------------------
ownership_scope_file() {
    printf '%s\n' "${OWNED_PATHS_FILE:-$(ownership_project_root)/config/owned_paths.yaml}"
}

# ---------------------------------------------------------------------------
# ownership_python — first interpreter that can actually import yaml.
#
# PROBED, not assumed: an interpreter that exists but lacks PyYAML cannot parse
# the scope, and treating it as usable produces a confusing downstream failure
# instead of an honest one here.
# ---------------------------------------------------------------------------
ownership_python() {
    local root cand
    root="$(ownership_project_root)"
    for cand in "${PYTHON_BIN:-}" "${root}/.venv/bin/python" python3; do
        [[ -n "${cand}" ]] || continue
        if command -v "${cand}" >/dev/null 2>&1 && "${cand}" -c 'import yaml' >/dev/null 2>&1; then
            printf '%s\n' "${cand}"; return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# ownership_scope_entries — emit one TAB-separated row per declared entry:
#     <resolved-path>\t<kind>\t<optional>\t<preserve_mode>\t<recursive>
#
# `${VAR:-default}` in a declared path is expanded against the environment, so
# the host-specific download root is resolved at run time rather than hardcoded
# into shared logic (§11.4.35).
#
# Returns 2 (not 1, and never 0) when the scope cannot be read: a caller must be
# able to distinguish "scope says nothing is wrong" from "I could not read the
# scope at all" (§11.4.201(6)).
# ---------------------------------------------------------------------------
ownership_scope_entries() {
    local py scope
    scope="$(ownership_scope_file)"
    [[ -f "${scope}" ]] || { echo "ownership: scope file not found: ${scope}" >&2; return 2; }
    py="$(ownership_python)" || {
        echo "ownership: no python3 with PyYAML — cannot parse ${scope}" >&2
        echo "ownership: this is a BLIND read, not an empty scope" >&2
        return 2
    }
    "${py}" - "${scope}" <<'PYEOF'
import os, sys, re, yaml
doc = yaml.safe_load(open(sys.argv[1])) or {}
for e in (doc.get("paths") or []):
    raw = str(e.get("path", ""))
    # expand ${VAR} and ${VAR:-default} against the live environment
    def sub(m):
        var, dflt = m.group(1), m.group(3)
        return os.environ.get(var) or (dflt if dflt is not None else "")
    path = re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}', sub, raw)
    if not path:
        continue
    print("\t".join([
        path,
        str(e.get("kind", "")),
        "1" if e.get("optional", False) else "0",
        "1" if e.get("preserve_mode", False) else "0",
        "1" if e.get("recursive", True) else "0",
    ]))
PYEOF
}

# ---------------------------------------------------------------------------
# probe_location <dir> — create a real file, read its owner back, remove it.
#
# Echoes one of: ok | wrong-owner:<uid> | unwritable | absent   (data-model E4)
# Return: 0 for ok, 1 for every other verdict.
#
# The probe file is created inside the probed directory ON PURPOSE — ownership
# is a property of the filesystem and mount the file lands on, so probing
# anywhere else would answer a different question.
# ---------------------------------------------------------------------------
probe_location() {
    local dir="$1" want probe got
    want="$(ownership_operator_uid)"

    [[ -e "${dir}" ]] || { echo "absent"; return 1; }
    if [[ -f "${dir}" ]]; then
        # A declared FILE (e.g. the credential store): read its owner directly.
        # There is nothing to create, so this is the one case where reading the
        # target itself IS the real condition rather than a proxy for it.
        got="$(stat -c '%u' "${dir}" 2>/dev/null)" || { echo "unwritable"; return 1; }
        [[ "${got}" == "${want}" ]] && { echo "ok"; return 0; }
        echo "wrong-owner:${got}"; return 1
    fi

    probe="$(mktemp "${dir}/.ownership-probe.XXXXXX" 2>/dev/null)" || { echo "unwritable"; return 1; }
    got="$(stat -c '%u' "${probe}" 2>/dev/null)"
    rm -f "${probe}"
    [[ -n "${got}" ]] || { echo "unwritable"; return 1; }
    [[ "${got}" == "${want}" ]] && { echo "ok"; return 0; }
    echo "wrong-owner:${got}"
    return 1
}

# ---------------------------------------------------------------------------
# ownership_scope_fingerprint — sha256 over the sorted declared scope.
#
# Used by the repair marker (data-model E2). A change to the scope MUST
# invalidate the marker, otherwise a newly-declared path is silently never
# repaired: the marker would say "already done" about work never performed.
# ---------------------------------------------------------------------------
ownership_scope_fingerprint() {
    ownership_scope_entries | LC_ALL=C sort | sha256sum | cut -d' ' -f1
}
