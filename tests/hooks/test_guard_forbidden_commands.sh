#!/usr/bin/env bash
# test_guard_forbidden_commands.sh — Hermetic test for the PreToolUse guard hook.
#
# Tests every blocked class exits 2, every allowed command exits 0,
# the escape hatch works for non-power classes, and the host-power class
# rejects even with the escape marker.
#
# §11.4.109 — Anti-Forgetting Enforcement
# §1.1 — Paired meta-test mutation: remove the emulator -avd pattern from
#        the hook → emulator gate test exits 0 → this test FAILs → restore.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
HOOK="${PROJECT_ROOT}/constitution/scripts/hooks/guard-forbidden-commands.sh"

PASS_COUNT=0
FAIL_COUNT=0

pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "  PASS: $1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $1"; }

# JSON-escape a raw command string for embedding as a JSON string literal
# value (escapes backslash, double-quote, and control characters --
# newline/tab/CR). Needed so test commands that themselves CONTAIN double
# quotes (e.g. `echo "need no sudo for list"`, the RD2-36/RD2-01 false-
# positive repro) OR embedded newlines (multi-line here-document test
# commands) build syntactically VALID JSON payloads instead of either
# truncating at the first embedded quote or -- the more dangerous failure
# mode, self-demonstrated live while authoring the heredoc test cases
# below -- producing JSON invalid enough that `jq` errors out, causing
# json_field() to return an EMPTY string, `$COMMAND` to become "", and the
# hook's "nothing to inspect -> allow" fast path to fire regardless of
# the test command's real content: a test that then reports PASS/FAIL for
# the WRONG reason (empty-command trivial-allow), never having exercised
# the guard logic under test at all -- a §11.4.1 FAIL-bluff/PASS-bluff at
# the test-harness layer, caught and fixed in the same session it was
# introduced.
_json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\r'/\\r}"
    printf '%s' "$s"
}

# Simulate a PreToolUse payload and run the hook.
# Usage: simulate <description> <tool_name> <command> <expected_exit> [expected_stderr_substring...]
simulate() {
    local desc="$1" tool="$2" cmd="$3" expected_exit="$4"
    shift 4
    local json escaped_cmd
    escaped_cmd="$(_json_escape "$cmd")"
    # Build a minimal PreToolUse JSON payload
    json=$(printf '{"tool_name":"%s","tool_input":{"command":"%s"}}' "$tool" "$escaped_cmd")
    local actual_exit=0
    local stderr_output
    # Capture stderr separately while running the hook with the JSON on stdin
    stderr_output=$(printf '%s' "$json" | bash "$HOOK" 2>&1 >/dev/null) || actual_exit=$?
    if [[ "$actual_exit" -ne "$expected_exit" ]]; then
        fail "$desc: expected exit $expected_exit, got $actual_exit (stderr: $stderr_output)"
        return
    fi
    # If expected stderr substrings were given, check they appear
    for substr in "$@"; do
        if ! printf '%s' "$stderr_output" | grep -qF "$substr"; then
            fail "$desc: expected stderr to contain '$substr', got: $stderr_output"
            return
        fi
    done
    pass "$desc"
}

echo "=== PreToolUse Guard Hook Tests ==="
echo

# --- Non-Bash tools pass through ---
simulate "non-Bash tool (Write) passes" "Write" "hello.txt" 0
simulate "non-Bash tool (Read) passes" "Read" "some/path" 0

# --- Empty command passes ---
simulate "empty Bash command passes" "Bash" "" 0

# --- Blocked class 1: emulator / device ---
simulate "raw emulator -avd blocked" "Bash" "emulator -avd test_device" 2 "BLOCKED"
simulate "adb install blocked" "Bash" "adb install app.apk" 2 "BLOCKED"
simulate "adb -s install blocked" "Bash" "adb -s emulator-5554 install app.apk" 2 "BLOCKED"
simulate "am instrument blocked" "Bash" "am instrument -w com.test/.Runner" 2 "BLOCKED"

# --- Blocked class 2: force-push / bypass ---
simulate "git push --force blocked" "Bash" "git push --force origin main" 2 "BLOCKED"
simulate "git push -f blocked" "Bash" "git push -f origin main" 2 "BLOCKED"
simulate "git push --force-with-lease blocked" "Bash" "git push --force-with-lease origin main" 2 "BLOCKED"
simulate "git commit --no-verify blocked" "Bash" "git commit --no-verify -m msg" 2 "BLOCKED"
simulate "git commit --no-gpg-sign blocked" "Bash" "git commit --no-gpg-sign -m msg" 2 "BLOCKED"

# --- Blocked class 3: sudo / su ---
simulate "sudo blocked" "Bash" "sudo apt install foo" 2 "BLOCKED"
simulate "su blocked" "Bash" "su -" 2 "BLOCKED"
simulate "su -l blocked" "Bash" "su -l root" 2 "BLOCKED"

# --- RD2-36 / RD2-01 / GA-24: false-positive class -- "sudo"/"su" appearing
# ONLY as a substring/word inside an unrelated quoted string or comment
# MUST NOT be blocked. A real sudo/su invocation, including one reached via
# `$(...)`/backtick command substitution (even nested inside double quotes),
# MUST still be blocked -- this is the paired no-regression check. ---
simulate "RD2-01 exact audit repro: sudo-in-quoted-echo-string allowed" \
    "Bash" 'echo "=== systemd system-level (may need no sudo for list) ==="' 0
simulate "sudo as a substring inside an unrelated quoted echo string allowed" \
    "Bash" 'echo "need no sudo for list"' 0
simulate "su as a standalone word inside an unrelated quoted string allowed" \
    "Bash" 'echo "no su needed here"' 0
simulate "sudo mentioned only in a shell comment allowed" \
    "Bash" 'ls -la # this does not need sudo at all' 0
simulate "real sudo invocation still blocked after word-boundary fix" \
    "Bash" "sudo rm -rf /something" 2 "BLOCKED"
simulate "real su invocation still blocked after word-boundary fix" \
    "Bash" "su - root" 2 "BLOCKED"
simulate "sudo reached via \$(...) command substitution still blocked" \
    "Bash" 'echo "$(sudo id)"' 2 "BLOCKED"
simulate "sudo reached via backtick substitution still blocked" \
    "Bash" 'echo "`sudo id`"' 2 "BLOCKED"
simulate "sudo chained after ; still blocked when the earlier clause quotes sudo" \
    "Bash" 'echo "no sudo needed"; sudo rm -rf /x' 2 "BLOCKED"

# --- Live-discovered sibling class: prose mentioning sudo/su inside a
# QUOTED-delimiter here-document body (this project's own documented
# `git commit -m "$(cat <<'EOF' ... EOF)"` idiom) must also be allowed;
# a real invocation inside the SAME construct must still be blocked. ---
simulate "sudo mentioned in prose inside a <<'EOF' heredoc body allowed" \
    "Bash" $'cat <<\'EOF\'\nno sudo invocation was present here\nEOF' 0
simulate "su mentioned in prose inside a <<\"EOF\" heredoc body allowed" \
    "Bash" $'cat <<"EOF"\nno su needed in this doc\nEOF' 0
simulate "real sudo invocation on a line BEFORE a heredoc still blocked" \
    "Bash" $'sudo id; cat <<\'EOF\'\nharmless prose\nEOF' 2 "BLOCKED"
simulate "unquoted-delimiter heredoc real sudo body still blocked (conservative default)" \
    "Bash" $'cat <<EOF\nsudo rm -rf /x\nEOF' 2 "BLOCKED"

# --- Blocked class 4: host-power ---
simulate "systemctl suspend blocked" "Bash" "systemctl suspend" 2 "BLOCKED"
simulate "systemctl poweroff blocked" "Bash" "systemctl poweroff" 2 "BLOCKED"
simulate "loginctl suspend blocked" "Bash" "loginctl suspend" 2 "BLOCKED"
simulate "pm-suspend blocked" "Bash" "pm-suspend" 2 "BLOCKED"
simulate "shutdown blocked" "Bash" "shutdown -h now" 2 "BLOCKED"

# --- Allowed commands (non-threatening) ---
simulate "git push (no force) allowed" "Bash" "git push origin main" 0
simulate "ls allowed" "Bash" "ls -la" 0
simulate "pip install allowed" "Bash" "pip install pytest" 0
simulate "python script allowed" "Bash" "python3 test.py" 0

# --- Escape hatch ---
simulate "emulator with guardrails:allow warns but passes" \
    "Bash" "adb install --user 0 app.apk  # guardrails:allow usb-debug-bypass" \
    0 "guardrails: WARNING"
simulate "sudo with guardrails:allow warns but passes" \
    "Bash" "sudo whoami  # guardrails:allow container-inside-sudo" \
    0 "guardrails: WARNING"

# --- Host-power escape hatch is non-overridable ---
simulate "systemctl poweroff with guardrails:allow still blocked" \
    "Bash" "systemctl poweroff  # guardrails:allow emergency" \
    2 "NOT overridable"

echo
echo "=== Result: ${PASS_COUNT} passed, ${FAIL_COUNT} failed ==="
if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
fi
exit 0
