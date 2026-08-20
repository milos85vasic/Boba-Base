#!/usr/bin/env bash
# test_start_reload_harness.sh — shared PATH-shim harness for the
# start.sh maintenance-subcommand tests (BOB-089 / RD2-24), PLUS its own
# control-needle self-test when executed directly.
#
# WHY A SANDBOX SCRIPT_DIR (§11.4.201(11) probe the artifact, not a proxy):
#   start.sh does `cd "$SCRIPT_DIR"` and, BEFORE the reload dispatch, runs
#   ensure_boba_master_key() which APPENDS to "$SCRIPT_DIR/.env" (start.sh
#   "ensure_boba_master_key"). Invoking the repo copy in place would mutate
#   the operator's real .env. We therefore copy start.sh BYTE-IDENTICALLY
#   (sha256-verified, harness_new_sandbox) into a throwaway SCRIPT_DIR. The
#   bytes under test are the real artifact; only its cwd is relocated, so
#   the REAL invocation path is preserved: `bash start.sh --reload-python`
#   runs real arg parsing -> real load_environment -> real
#   detect_container_runtime -> real check_prerequisites -> real
#   reload_python. No function is stubbed.
#
# WHY A SANITIZED PATH (§12 host safety, §11.4.201(6) false-null guard):
#   Tests must never touch the operator's live containers. PATH is rebuilt
#   as "<shims>:<sanitized sysbin>" where sysbin holds symlinks ONLY to the
#   coreutils start.sh needs. Real podman/docker are therefore UNREACHABLE
#   unless a test explicitly installs a recorder shim for them -- so a
#   "no runtime detected" reading is a real absence, not an accident.
#
# Recorded argv format, one line per invocation:
#     NAME|arg1|arg2|...
#   Pipe-joined rather than space-joined so word-splitting defects are
#   visible (a mangled `-exec rm -rf {} +` cannot hide behind a space).
#
# §1.1 / §11.4.115 RED: harness_mutate() sed-patches the SANDBOX COPY only,
#   never the repo's start.sh; the consuming tests use it to prove every
#   assertion can FAIL.

# SC2034: HARNESS_OUT/HARNESS_RC/CHECK_DIAG are set here and read by the
# sourcing test files (and by harness_drive) through bash dynamic scope,
# which shellcheck cannot follow across the `source` boundary.
# shellcheck disable=SC2034
set -euo pipefail

HARNESS_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_PROJECT_ROOT="$(cd "${HARNESS_HERE}/../.." && pwd)"
HARNESS_START_SH="${HARNESS_PROJECT_ROOT}/start.sh"

# Coreutils start.sh actually reaches for on the reload/recreate paths
# (uname via default_data_dir; grep/touch/chmod/head/xxd via
# ensure_boba_master_key; the rest are defensive).
HARNESS_SYSBIN_UTILS=(
    uname grep egrep fgrep touch chmod head tail xxd cat sed awk tr cut sort
    rm mkdir cp ln ls basename dirname find env printf sha256sum id stat date
    sh bash true false
)

harness_sha256() { sha256sum "$1" | cut -d' ' -f1; }

# One registered root per run, created in THIS shell (never in a subshell --
# harness_new_sandbox is called via $(...), so anything it appended to an array
# would be lost). Every sandbox is a child of the root, so a single EXIT/INT/TERM
# trap reaps them all even when the run is killed mid-check (§11.4.14 cleanup on
# every exit path -- a timed-out run must not leave a sandbox behind).
HARNESS_RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/boba_start_reload.XXXXXXXX")"
harness_cleanup_all() {
    [[ -n "${HARNESS_RUN_ROOT:-}" && "$HARNESS_RUN_ROOT" == *boba_start_reload.* ]] \
        && rm -rf "$HARNESS_RUN_ROOT"
    return 0
}
trap harness_cleanup_all EXIT INT TERM

# Build an isolated SCRIPT_DIR containing a byte-identical start.sh.
# Echoes the sandbox root. Caller must harness_cleanup it.
harness_new_sandbox() {
    local sb
    sb="$(mktemp -d "$HARNESS_RUN_ROOT/sb.XXXXXXXX")"
    mkdir -p "$sb/repo/scripts" "$sb/bin" "$sb/sysbin" "$sb/home"

    cp "$HARNESS_START_SH" "$sb/repo/start.sh"
    chmod +x "$sb/repo/start.sh"
    # Fail closed if the copy is not the artifact (§11.4.6 no assumption).
    if [[ "$(harness_sha256 "$HARNESS_START_SH")" != "$(harness_sha256 "$sb/repo/start.sh")" ]]; then
        echo "harness: sandbox start.sh is NOT byte-identical to the artifact" >&2
        rm -rf "$sb"
        return 1
    fi

    # check_prerequisites() requires this file to exist.
    printf '# sandbox stub for check_prerequisites (never parsed - compose is shimmed)\n' \
        > "$sb/repo/docker-compose.yml"

    # Pre-seed a syntactically valid 64-hex key so ensure_boba_master_key()
    # takes its early-return branch: deterministic (§11.4.50), and no
    # /dev/urandom or xxd dependency in the hot path.
    printf 'BOBA_MASTER_KEY=%s\n' "$(printf '0%.0s' {1..64})" > "$sb/repo/.env"
    chmod 0600 "$sb/repo/.env"

    # Default COMPOSE_CMD is "$SCRIPT_DIR/scripts/boba-ctl.sh" -- an
    # absolute path, NOT PATH-resolved, so it needs its own recorder.
    harness_write_shim "$sb/repo/scripts/boba-ctl.sh"

    for util in "${HARNESS_SYSBIN_UTILS[@]}"; do
        local real
        real="$(PATH="/usr/bin:/bin:/usr/sbin:/sbin" command -v "$util" 2>/dev/null || true)"
        [[ -n "$real" ]] && ln -sf "$real" "$sb/sysbin/$util"
    done

    : > "$sb/argv.log"
    printf '%s\n' "$sb"
}

# Write a recorder shim at an explicit path.
harness_write_shim() {
    local path="$1"
    cat > "$path" <<'SHIM'
#!/usr/bin/env bash
_n="$(basename "$0")"
_line="$_n"
for _a in "$@"; do _line="$_line|$_a"; done
printf '%s\n' "$_line" >> "${BOBA_SHIM_LOG:?BOBA_SHIM_LOG unset}"
if [[ -n "${BOBA_SHIM_FAIL:-}" && "$_line" == ${BOBA_SHIM_FAIL} ]]; then
    printf 'shim: simulated failure for %s\n' "$_line" >&2
    exit 1
fi
exit 0
SHIM
    chmod +x "$path"
}

# Install a PATH-resolved recorder shim (podman, docker, podman-compose...).
harness_add_shim() { harness_write_shim "$1/bin/$2"; }

# Run the sandboxed start.sh through its REAL entry point.
# Sets HARNESS_RC and HARNESS_OUT (combined stdout+stderr).
harness_run() {
    local sb="$1"; shift
    local out rc=0
    set +e
    out="$(
        cd "$sb/repo" && \
        PATH="$sb/bin:$sb/sysbin" \
        HOME="$sb/home" \
        BOBA_SHIM_LOG="$sb/argv.log" \
        BOBA_SHIM_FAIL="${BOBA_SHIM_FAIL:-}" \
        bash "$sb/repo/start.sh" "$@" 2>&1
    )"
    rc=$?
    set -e
    HARNESS_OUT="$out"
    HARNESS_RC="$rc"
}

harness_log()     { cat "$1/argv.log"; }
harness_mutate()  { sed -i "$2" "$1/repo/start.sh"; }
harness_cleanup() { [[ -n "${1:-}" && "$1" == *boba_start_reload.* ]] && rm -rf "$1"; }

# --- assertion primitives: echo PASS/FAIL, never exit -----------------------
harness_verdict() { # key, condition-result(0/1)
    if [[ "$2" -eq 0 ]]; then printf '%s=PASS\n' "$1"; else printf '%s=FAIL\n' "$1"; fi
}
harness_log_has() { grep -qxF "$2" "$1/argv.log"; }
harness_log_count() { grep -cxF "$2" "$1/argv.log" 2>/dev/null || true; }
harness_log_before() { # sandbox, lineA, lineB -> A strictly before B
    local a b
    a="$(grep -nxF "$2" "$1/argv.log" | head -1 | cut -d: -f1)"
    b="$(grep -nxF "$3" "$1/argv.log" | head -1 | cut -d: -f1)"
    [[ -n "$a" && -n "$b" && "$a" -lt "$b" ]]
}

# --- §1.1 paired-mutation driver -------------------------------------------
# GREEN mode: every check must PASS against the pristine artifact.
# RED   mode: every check must FAIL against its paired mutation of the
#             SANDBOX COPY. A check with no mutation, or whose mutation
#             SURVIVES, is a bluff (§11.4.115) and is reported as a failure.
# Consuming test files define: CHECK_NAMES[], CHECK_DESC[], CHECK_MUTATION[]
# and one check_<NAME>() per entry, each taking a sed mutation expr (or "").
harness_drive() {
    local mode="${1:-green}" pass=0 fail=0 name mut
    for name in "${CHECK_NAMES[@]}"; do
        CHECK_DIAG=""
        if [[ "$mode" == green ]]; then
            if "check_$name" ""; then
                pass=$((pass+1)); echo "  PASS: $name — ${CHECK_DESC[$name]}"
            else
                fail=$((fail+1)); echo "  FAIL: $name — ${CHECK_DESC[$name]}"
                [[ -n "$CHECK_DIAG" ]] && echo "        $CHECK_DIAG"
            fi
        else
            mut="${CHECK_MUTATION[$name]:-}"
            if [[ -z "$mut" ]]; then
                fail=$((fail+1)); echo "  FAIL: $name — no paired mutation (§1.1)"; continue
            fi
            if "check_$name" "$mut"; then
                fail=$((fail+1)); echo "  BLUFF: $name — mutation SURVIVED: $mut"
            else
                pass=$((pass+1)); echo "  RED-OK: $name — killed by: $mut"
            fi
        fi
    done
    echo "RESULT: ${pass} passed, ${fail} failed"
    [[ "$fail" -eq 0 ]]
}

# ---------------------------------------------------------------------------
# Executed directly => CONTROL-NEEDLE self-test (§11.4.201(7)(b)): proves the
# instrument can SEE before any test trusts a null reading from it.
# ---------------------------------------------------------------------------
harness_selftest() {
    local pass=0 fail=0
    _p() { pass=$((pass+1)); echo "  PASS: $1"; }
    _f() { fail=$((fail+1)); echo "  FAIL: $1"; }

    echo "== harness control-needle self-test =="
    local repo_sha_before repo_sha_after sb
    repo_sha_before="$(harness_sha256 "$HARNESS_START_SH")"

    sb="$(harness_new_sandbox)"

    # 1. the copy IS the artifact
    if [[ "$(harness_sha256 "$sb/repo/start.sh")" == "$repo_sha_before" ]]; then
        _p "sandbox start.sh is byte-identical to the repo artifact"
    else
        _f "sandbox start.sh diverged from the repo artifact"
    fi

    # 2. NEEDLE: the recorder captures argv losslessly, including the
    #    find(1) terminator tokens `{}` and `+` that a space-joined
    #    recorder would blur.
    harness_add_shim "$sb" needleprobe
    BOBA_SHIM_LOG="$sb/argv.log" "$sb/bin/needleprobe" -exec rm -rf '{}' '+'
    if harness_log_has "$sb" 'needleprobe|-exec|rm|-rf|{}|+'; then
        _p "recorder captures argv losslessly (needle seen)"
    else
        _f "recorder did NOT capture the needle -- instrument is BLIND"
    fi

    # 3. NEEDLE: the failure-injection channel works
    if BOBA_SHIM_LOG="$sb/argv.log" BOBA_SHIM_FAIL='needleprobe|boom' \
        "$sb/bin/needleprobe" boom 2>/dev/null; then
        _f "BOBA_SHIM_FAIL did not make the shim exit non-zero"
    else
        _p "BOBA_SHIM_FAIL makes the shim exit non-zero"
    fi

    # 4. NEGATIVE CONTROL: with no shim installed, the sanitized PATH must
    #    hide the host's real podman/docker -- otherwise every "no runtime"
    #    assertion downstream would be a false null (§11.4.201(6)).
    local seen=""
    PATH="$sb/bin:$sb/sysbin" command -v podman >/dev/null 2>&1 && seen="podman"
    PATH="$sb/bin:$sb/sysbin" command -v docker >/dev/null 2>&1 && seen="$seen docker"
    if [[ -z "$seen" ]]; then
        _p "sanitized PATH hides the host's real container runtimes"
    else
        _f "sanitized PATH leaks real runtime(s):$seen -- HOST SAFETY RISK"
    fi

    # 5. sanity: the utilities start.sh needs ARE reachable (so a failure
    #    downstream is a product defect, not a starved PATH -- §11.4.1)
    local missing=""
    for u in uname grep sed cat head chmod touch; do
        PATH="$sb/bin:$sb/sysbin" command -v "$u" >/dev/null 2>&1 || missing="$missing $u"
    done
    if [[ -z "$missing" ]]; then
        _p "sanitized PATH still provides start.sh's coreutils"
    else
        _f "sanitized PATH is missing:$missing"
    fi

    # 6. the harness must not have touched the repo artifact
    harness_cleanup "$sb"
    repo_sha_after="$(harness_sha256 "$HARNESS_START_SH")"
    if [[ "$repo_sha_before" == "$repo_sha_after" ]]; then
        _p "repo start.sh unmodified by the harness"
    else
        _f "repo start.sh WAS MODIFIED by the harness"
    fi

    echo "RESULT: ${pass} passed, ${fail} failed"
    [[ "$fail" -eq 0 ]]
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    harness_selftest
fi
