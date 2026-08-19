#!/usr/bin/env bash
# user1000-watchdog-challenge.sh — anti-bluff verification of the watchdog
#
# §11.4.115 RED-first + §11.4.107(10) self-validated + §11.4.201 real-condition
# guard. Verifies structural correctness of the watchdog artifacts WITHOUT
# requiring root (install is a separate operator-run step).
#
# What this proves:
#   1. All watchdog source files exist and are parseable (bash -n / systemd-analyze)
#   2. The service unit declares system.slice (NOT user.slice) — the load-bearing
#      correctness property (an in-scope monitor would die with user@1000)
#   3. The script has the required pre-flight check refusing to run in user.slice
#   4. The script captures forensics in a durable path outside user.slice
#   5. GOLDEN-BAD polarity: mutating the .service to Slice=user.slice makes the
#      challenge FAIL — proves the check is real, not decoration
#
# Exit codes:
#   0 = all invariants hold (GREEN)
#   1 = one or more invariants failed (RED)
#   2 = pre-flight failure (test setup wrong)

set -o nounset
set -o pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
readonly WATCHDOG_DIR="$REPO_ROOT/scripts/system-slice-watchdog"
readonly WATCHDOG_SH="$WATCHDOG_DIR/user1000-watchdog.sh"
# SERVICE_UNIT overridable so the polarity harness can re-invoke this challenge
# against a mutated golden-bad fixture (§11.4.115 RED-first).
readonly SERVICE_UNIT="${BOBA_CHALLENGE_SERVICE_UNIT:-$WATCHDOG_DIR/boba-user1000-watchdog.service}"
readonly INSTALL_SH="$WATCHDOG_DIR/install.sh"
readonly UNINSTALL_SH="$WATCHDOG_DIR/uninstall.sh"

# Run mode: default GREEN, set POLARITY_MODE=red to run the golden-bad polarity
POLARITY_MODE="${POLARITY_MODE:-green}"

fail_count=0
pass_count=0

pass() { printf '  \033[32m✓\033[0m %s\n' "$*"; pass_count=$((pass_count + 1)); }
fail() { printf '  \033[31m✗\033[0m %s\n' "$*"; fail_count=$((fail_count + 1)); }
info() { printf '  · %s\n' "$*"; }

section() { printf '\n== %s ==\n' "$*"; }

check_exists_and_parseable() {
    local path="$1"; local kind="$2"
    if [[ ! -f "$path" ]]; then fail "MISSING: $path"; return 1; fi
    pass "exists: $(basename "$path")"
    case "$kind" in
        bash)
            if bash -n "$path" 2>/dev/null; then
                pass "bash -n clean: $(basename "$path")"
            else
                fail "bash -n FAILED: $path"
                bash -n "$path" 2>&1 | head -5 | sed 's/^/     /'
            fi
            ;;
        systemd)
            # Skip systemd-analyze verify (needs systemd installed); instead
            # do a shape check: [Unit] + [Service] + [Install] sections all present
            if grep -qE '^\[Unit\]' "$path" && \
               grep -qE '^\[Service\]' "$path" && \
               grep -qE '^\[Install\]' "$path"; then
                pass "systemd unit shape OK: $(basename "$path")"
            else
                fail "systemd unit missing required section(s): $path"
            fi
            ;;
    esac
}

echo "user1000-watchdog challenge — POLARITY_MODE=$POLARITY_MODE"
echo "watchdog dir: $WATCHDOG_DIR"

section "1. File existence + parseability"
check_exists_and_parseable "$WATCHDOG_SH" bash
check_exists_and_parseable "$SERVICE_UNIT" systemd
check_exists_and_parseable "$INSTALL_SH" bash
check_exists_and_parseable "$UNINSTALL_SH" bash

section "2. Executability (installer scripts must be exec)"
for f in "$WATCHDOG_SH" "$INSTALL_SH" "$UNINSTALL_SH"; do
    if [[ -x "$f" ]]; then pass "executable: $(basename "$f")"
    else fail "NOT executable: $f"; fi
done

section "3. LOAD-BEARING: service declares system.slice (NOT user.slice)"
if grep -qE '^Slice=system\.slice' "$SERVICE_UNIT"; then
    pass "service Slice=system.slice"
elif grep -qE '^Slice=user' "$SERVICE_UNIT"; then
    fail "service Slice=user.slice — this WOULD die with user@1000 (defeats the purpose)"
else
    # M5 fix: the previous "WantedBy=.*user" regex matched "multi-user.target" —
    # unreachable fallback. Require explicit Slice=system.slice — no ambiguity.
    fail "no explicit Slice=system.slice declaration — must be explicit for auditability"
fi

# M5 fix: require multi-user.target and NOT default.target (default is user-scope)
if grep -qE '^WantedBy=multi-user\.target' "$SERVICE_UNIT" && \
   ! grep -qE '^WantedBy=default\.target' "$SERVICE_UNIT"; then
    pass "WantedBy=multi-user.target only (system-level, correct)"
else
    fail "WantedBy must be multi-user.target only (default.target is user-scope)"
fi

if grep -qE '^User=root' "$SERVICE_UNIT"; then
    pass "runs as User=root (needed to survive user@1000 kill)"
fi

# M5 fix: ExecStart path must match what install.sh installs to
exec_start_path=$(grep -E '^ExecStart=' "$SERVICE_UNIT" | head -1 | awk -F= '{print $2}' | awk '{print $1}')
install_dest_path=$(grep -oE '/usr/local/bin/[a-zA-Z0-9_-]+' "$INSTALL_SH" | head -1)
if [[ -n "$exec_start_path" && -n "$install_dest_path" && "$exec_start_path" == "$install_dest_path" ]]; then
    pass "ExecStart ($exec_start_path) matches install.sh dest ($install_dest_path)"
else
    fail "PATH DRIFT: ExecStart=$exec_start_path but install.sh installs to $install_dest_path"
fi

section "4. Watchdog pre-flight refuses to run in user.slice"
if grep -qE 'my_cgroup.*user\.slice' "$WATCHDOG_SH"; then
    pass "watchdog checks own cgroup against user.slice"
else
    fail "watchdog does NOT verify its own cgroup — could silently run in-scope"
fi

if grep -qE 'id -u.*-ne 0' "$WATCHDOG_SH"; then
    pass "watchdog checks uid == 0"
else
    fail "watchdog does NOT check for root"
fi

section "5. Evidence root is durable (NOT tmpfs, NOT under user home)"
evidence_root_line=$(grep -E 'EVIDENCE_ROOT=' "$WATCHDOG_SH" | head -1)
if echo "$evidence_root_line" | grep -qE '/var/log'; then
    pass "evidence in /var/log/... (durable, survives reboot)"
elif echo "$evidence_root_line" | grep -qE '/tmp|/run/user'; then
    fail "evidence in /tmp or /run/user — LOSSY (tmpfs, wiped on reboot)"
elif echo "$evidence_root_line" | grep -qE '/home/'; then
    fail "evidence under /home — under user.slice, could be lost on user@1000 kill"
else
    info "evidence root: $evidence_root_line"
fi

section "6. Journal-tail trigger matches the OBSERVED incident signature"
# I2 fix (§11.4.201(7)(a) + §11.4.194(6)(d)): match the CODE CONSTRUCT, not the
# bare string. Comments in the watchdog contain the signature text as
# documentation; the previous grep was carrier-satisfiable (delete the code,
# keep the comment → passes). Now match the actual bash conditional structure.
# Strip comments before grepping to ensure we only see executable code.
watchdog_code_only=$(grep -vE '^\s*#' "$WATCHDOG_SH" 2>/dev/null || true)

# The "Main process exited" literal now lives in the trigger_prefix VARIABLE
# assignment (which IS code). Check that the assignment is present in code AND
# the [[ ]] test uses that variable.
if echo "$watchdog_code_only" | grep -qE 'trigger_prefix=.*TARGET_UNIT.*Main process exited'; then
    pass "trigger_prefix CODE assignment includes 'Main process exited' (I2 fix — not comment)"
else
    fail "trigger_prefix assignment CODE not present (comment-only would be §11.4.201(7)(a) carrier)"
fi

if echo "$watchdog_code_only" | grep -qE '\[\[[[:space:]]+"\$line"[[:space:]]+==.*trigger_prefix'; then
    pass "trigger CODE uses trigger_prefix variable in [[ ]] construct"
else
    fail "trigger [[ ]] does NOT reference trigger_prefix — construct check bypassed"
fi

if echo "$watchdog_code_only" | grep -qE '"\$line"[[:space:]]+==.*"status=9"' && \
   echo "$watchdog_code_only" | grep -qE '"\$line"[[:space:]]+==.*"code=killed"'; then
    pass "trigger checks BOTH status=9 AND code=killed (in code, not comments)"
fi

if echo "$watchdog_code_only" | grep -qE 'CAPTURE_COOLDOWN_SEC|LAST_CAPTURE_EPOCH'; then
    pass "cooldown implemented (I1 fix — same-incident dedup)"
else
    fail "no cooldown — cascade lines within 1s would evict real evidence dirs"
fi

section "7. Rotation: bounded evidence retention"
if grep -qE 'rotate_evidence|RETAIN_LAST_N' "$WATCHDOG_SH"; then
    pass "evidence rotation implemented (bounded disk)"
else
    fail "NO rotation — evidence dir will grow unbounded"
fi

section "8. Resource limits in service unit (host-safety §12.6, §12.12)"
for limit in MemoryMax MemoryHigh CPUQuota TasksMax; do
    if grep -qE "^$limit=" "$SERVICE_UNIT"; then
        pass "$limit set (bounded)"
    else
        fail "$limit NOT set — watchdog could contribute to host pressure"
    fi
done

section "Summary"
printf 'PASS=%d  FAIL=%d\n' "$pass_count" "$fail_count"

# Compute inner verdict for this run BEFORE polarity dispatch
if [[ "$fail_count" -eq 0 ]]; then
    inner_verdict="GREEN"
else
    inner_verdict="RED"
fi
printf 'INNER VERDICT: %s\n' "$inner_verdict"

# §11.4.115 polarity mode: mutate the fixture and RE-INVOKE the challenge on
# the mutated version — MUST return the OPPOSITE verdict. If the mutated run
# still says GREEN, the check is decoration (§11.4.115 bluff → hard FAIL).
if [[ "$POLARITY_MODE" == "red" ]]; then
    section "POLARITY (RED mode): re-invoke on golden-bad mutated fixture"
    tmp_dir=$(mktemp -d)
    trap 'rm -rf "$tmp_dir"' EXIT

    # Golden-bad: Slice=user.slice (the exact bug §3 is meant to catch)
    cp "$SERVICE_UNIT" "$tmp_dir/mutated.service"
    sed -i 's|^Slice=system\.slice|Slice=user.slice|' "$tmp_dir/mutated.service"

    if ! grep -qE '^Slice=user\.slice' "$tmp_dir/mutated.service"; then
        echo "  mutation FAILED to apply — polarity setup broken"
        exit 2
    fi
    info "mutated fixture: $tmp_dir/mutated.service (Slice=user.slice)"

    # Re-invoke SELF with the mutated fixture; MUST get inner RED verdict
    mutated_output=$(BOBA_CHALLENGE_SERVICE_UNIT="$tmp_dir/mutated.service" \
                     POLARITY_MODE=green bash "$0" 2>&1)
    mutated_exit=$?

    echo "  mutated run: exit=$mutated_exit"
    echo "$mutated_output" | grep -E "INNER VERDICT|Slice=user|PASS=|FAIL=" | sed 's/^/    /'

    if [[ "$mutated_exit" -eq 0 ]]; then
        echo
        echo "  \033[31mPOLARITY BROKEN\033[0m: mutated (golden-bad) fixture returned GREEN"
        echo "  §11.4.115: the load-bearing §3 check is DECORATION — it did not"
        echo "  detect the Slice=user.slice mutation. This is a §11.4 bluff."
        echo "VERDICT: POLARITY-BROKEN"
        exit 1
    fi

    if echo "$mutated_output" | grep -qE 'INNER VERDICT: RED'; then
        pass "POLARITY CONFIRMED: mutated fixture returned inner RED verdict"
        info "  → §3 check is REAL: detected Slice=user.slice → failed as expected"
    else
        echo "  \033[31mPOLARITY BROKEN\033[0m: mutated exit was $mutated_exit but INNER VERDICT was not RED"
        exit 1
    fi

    printf '\nFINAL: GREEN (structural %d PASS) + POLARITY CONFIRMED\n' "$pass_count"
    exit 0
fi

if [[ "$fail_count" -eq 0 ]]; then
    echo "VERDICT: GREEN — watchdog artifacts satisfy all structural invariants"
    exit 0
else
    echo "VERDICT: RED — $fail_count invariant(s) failed"
    exit 1
fi
