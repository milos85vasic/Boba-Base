#!/bin/bash
# check-no-suspend-calls.sh — CONST-033 static scanner.
#
# Walks the project tree and fails if ANY file invokes a host-level
# power-state transition (suspend, hibernate, hybrid-sleep, poweroff,
# halt, reboot, kexec, suspend-then-hibernate) via systemctl, loginctl,
# pm-*, shutdown, DBus (login1 / UPower), or gsettings sleep-inactive-*
# set to anything other than 'nothing'.
#
# Usage:
#   bash check-no-suspend-calls.sh [project_root]
#
# Exit:
#   0 = clean
#   1 = one or more violations found (printed)
#   2 = invocation error

set -uo pipefail
ROOT="${1:-.}"

if [[ ! -d "$ROOT" ]]; then
  echo "ERROR: $ROOT is not a directory" >&2
  exit 2
fi

# Directories never scanned (third-party / generated / large binary).
EXCLUDE_DIRS=(
  ".git" ".svn" ".hg"
  "node_modules" "vendor" "third_party" "Upstreams" "upstreams"
  "cli_agents" "MCP" "MCP_Module/submodules"
  ".cache" ".gradle" ".idea" ".vscode" ".venv" "venv" "__pycache__"
  "build" "dist" "target" "out" "bin" "obj"
  "releases"
)

# File-path substrings allowlisted (the canonical artifacts and
# governance docs ARE allowed to mention these patterns).
EXCLUDE_PATHS=(
  "host-power-management/"
  "host_no_auto_suspend_challenge.sh"
  "no_suspend_calls_challenge.sh"
  "HOST_POWER_MANAGEMENT.md"
  "HOST_POWER_MANAGEMENT.html"
  "CONSTITUTION.md"
  "Constitution.md"
  "CONSTITUTION.html"
  "Constitution.html"
  "CONSTITUTION.json"
  "AGENTS.md"
  "AGENTS.html"
  "CLAUDE.md"
  "CLAUDE.html"
  "QWEN.md"
  "GEMINI.md"
  ".html"
  ".pdf"
  "/docs/issues/fixed/BUGFIXES.md"
  "/CHANGELOG.md"
  "/CHALLENGE.md"
  "/docs/superpowers/plans/"
  "anthropic-quickstarts/"
  "tests/hooks/"
  # This doc documents/enforces the forbidden verbs (guard-forbidden-commands
  # hook reference) — it quotes them, it does not invoke them. GA-24.
  "/constitution/docs/scripts/guard-forbidden-commands.md"
  # CONST-033 incident/triage reports are prose forensics: by construction they
  # QUOTE the forbidden verbs they are triaging, and they paste this scanner's
  # own FAIL transcript as captured evidence. A Markdown incident report cannot
  # invoke a power-state transition — it is a §11.4.201(7)(a) CARRIER, not the
  # thing. Without this entry every future CONST-033 incident write-up
  # re-breaks the gate (a §11.4.201(1) false-positive refusal = FAIL-bluff).
  # Justification per CLAUDE.md "non-host-context" rule. Verified 2026-08-08:
  # zero real forbidden invocations exist in executable code (control-needle
  # grep over *.sh/*.py/*.go/*.ts/*.yml — only hits are the guard hook's own
  # test fixtures under tests/hooks/, already allowlisted above).
  "/docs/incidents/"
  # SDD review diffs are captured evidence of what a reviewer read — they
  # QUOTE the constitution's rule text, they do not invoke anything (a
  # unified diff can never fork/exec, §11.4.201(7)(a) CARRIER).
  "/.superpowers/sdd/"
  # Session-scratch working files (agent transcripts, false-positive-audit
  # fixtures, verification transcripts). These files are the audit trail
  # that PROVES the guard hook fired on golden-bad inputs — they quote what
  # was blocked, they don't invoke anything. Verified 2026-08-18: scratchpad
  # is gitignored per §11.4.11 + §11.4.30, hosts session-local artefacts only.
  "/scratchpad/"
)

# Forbidden grep -E patterns. Real, tight regexes — not bare words.
FORBIDDEN=(
  '\bsystemctl[[:space:]]+(suspend|hibernate|hybrid-sleep|suspend-then-hibernate|poweroff|halt|reboot|kexec)\b'
  '\bloginctl[[:space:]]+(suspend|hibernate|hybrid-sleep|suspend-then-hibernate|poweroff|halt|reboot)\b'
  '\bpm-(suspend|hibernate|suspend-hybrid)\b'
  '\bshutdown[[:space:]]+(-h|-r|-P|-H|now|--halt|--poweroff|--reboot)\b'
  'org\.freedesktop\.login1\.Manager\.(Suspend|Hibernate|HybridSleep|SuspendThenHibernate|PowerOff|Reboot)'
  'org\.freedesktop\.UPower\.(Suspend|Hibernate|HybridSleep)'
  '(sleep-inactive-(ac|battery)-type)[[:space:]]+["'\'']?(suspend|hibernate|shutdown|hybrid-sleep|interactive)["'\'']?'
  '\bdbus-send\b.*\b(Suspend|Hibernate|PowerOff|Reboot|HybridSleep)\b'
  '\bbusctl\b.*\bcall\b.*\b(Suspend|Hibernate|PowerOff|Reboot|HybridSleep)\b'
)

# Build grep arguments
EXCL_ARGS=()
for d in "${EXCLUDE_DIRS[@]}"; do EXCL_ARGS+=( --exclude-dir="$d" ); done
PATTERN=$(IFS='|'; echo "${FORBIDDEN[*]}")

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

# Scan
grep -RInE "$PATTERN" "${EXCL_ARGS[@]}" -- "$ROOT" 2>/dev/null > "$TMP" || true

# Filter allowlist substrings
VIOLATIONS=$(awk -v root="$ROOT" -v EXCLUDE_PATHS_PIPED="$(IFS='|'; echo "${EXCLUDE_PATHS[*]}")" '
  BEGIN {
    n = split(EXCLUDE_PATHS_PIPED, arr, "|")
    for (i=1;i<=n;i++) ex[i] = arr[i]
    excount = n
  }
  {
    skip = 0
    for (i=1;i<=excount;i++) {
      if (ex[i] != "" && index($0, ex[i]) > 0) { skip = 1; break }
    }
    # STRUCTURAL carrier filter (§11.4.201(7)(a) — match the THING, not a
    # token that MENTIONS it). grep emits "path:lineno:content"; strip that
    # prefix and skip when the matched line is a WHOLE-LINE COMMENT (shell/
    # python/yaml "#") or a Markdown heading. A line whose first non-blank
    # character is "#" cannot invoke anything under any shell — it is inert
    # by language semantics, so skipping it removes ZERO detection power
    # while killing the recurrence class that a per-file allowlist cannot:
    # governance prose, incident write-ups, and INHERITED submodule comments
    # (e.g. constitution/scripts/hooks/*.sh documenting the verbs it blocks)
    # that this project does not control and cannot pre-enumerate.
    # Proven 2026-08-12 by the paired §1.1 golden-bad fixture: a real
    # invocation on a NON-comment line still FAILs the scanner.
    # Known narrow limit (stated, not hidden): a trailing comment on a line
    # that also contains real code is still scanned — deliberate, so
    # `systemctl poweroff  # cleanup` is never silently excused.
    if (!skip) {
      content = $0
      sub(/^[^:]*:[0-9]+:/, "", content)
      if (content ~ /^[[:space:]]*#/) skip = 1
    }
    if (!skip) print
  }
' "$TMP")

if [[ -z "$VIOLATIONS" ]]; then
  echo "OK: no forbidden host-power-management calls in $ROOT"
  exit 0
fi

echo "FAIL: forbidden host-power-management invocations (CONST-033):"
echo "$VIOLATIONS"
echo
echo "If a hit is a legitimate non-host context (e.g. a container's"
echo "internal init, a documentation example), add the file path to"
echo "EXCLUDE_PATHS at the top of this script."
exit 1
