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

# Simulate a PreToolUse payload and run the hook.
# Usage: simulate <description> <tool_name> <command> <expected_exit> [expected_stderr_substring...]
simulate() {
    local desc="$1" tool="$2" cmd="$3" expected_exit="$4"
    shift 4
    local json
    # Build a minimal PreToolUse JSON payload
    json=$(printf '{"tool_name":"%s","tool_input":{"command":"%s"}}' "$tool" "$cmd")
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
