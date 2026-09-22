#!/usr/bin/env bash
# test_check_cm_qbittorrent_webui_credentials.sh — §1.1 paired-mutation
# meta-test for scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh.
#
# WHY THIS DRIVES THE REAL GATE (§11.4.249): this harness EXECUTES the gate
# script against synthesised repo trees and reads its exit code. It does not
# re-declare the gate's patterns — a harness that reproduces the detector
# inside itself is a producer=oracle collapse and cannot see the gate drift.
#
# WHY IT EXISTS (§11.4.115(F)): a gate never observed FAILing on a genuinely
# broken artifact is unvalidated instrumentation and mints no verdicts. This
# gate ALREADY produced one false violation in development — its patterns
# missed a four-backslash source form and a quoted config value, and it
# refused a tree whose login demonstrably worked (measured: admin/admin -> 204,
# wrong password -> 401). The golden-good arm below is the guard against that
# recurring (§11.4.201(1): a false-positive refusal is as forbidden as a false
# pass).
#
# FIXTURE ARMS:
#   golden-good        -> gate MUST exit 0 (a correct tree)
#   golden-bad-1       -> gate MUST exit 1 (replace-only credential writer)
#   golden-bad-2       -> gate MUST exit 1 (auth bypass: LocalHostAuth=false)
#   golden-bad-3       -> gate MUST exit 1 (live config has no password hash)
#   golden-bad-4       -> gate MUST exit 1 (inert WEBUI_USERNAME in compose)
#   negative-control   -> gate MUST exit 0 (quoted hash form + no live config)
#
# Exit: 0 every arm matched | 1 divergence | 2 harness/environment error.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE="$REPO_ROOT/scripts/pre_build/check_cm_qbittorrent_webui_credentials.sh"

if [[ ! -f "$GATE" ]]; then
    echo "HARNESS ERROR: gate not found at $GATE" >&2; exit 2
fi

TMPD="$(mktemp -d -t cm_qbt_creds_meta.XXXXXX)"
trap 'rm -rf "$TMPD"' EXIT
fails=0

# Build a synthetic repo tree. $1=name, $2=variant
make_tree() {
    local name="$1" variant="$2"
    local root="$TMPD/$name"
    mkdir -p "$root/config/qBittorrent"

    # --- start.sh ---
    {
        echo '#!/usr/bin/env bash'
        echo '_ensure_webui_credentials() {'
        if [[ "$variant" == "replace-only" ]]; then
            # The pre-fix shape: guarded, replace-only.
            echo '    if grep -q "^WebUI\\\\Username=" "$config_file"; then'
            echo '        sed_inplace "s/x/y/" "$config_file"'
            echo '    fi'
        else
            echo '    _enforce_config_line "$config_file" "WebUI\\\\Username" "admin" "[Preferences]"'
            echo '    _enforce_config_line "$config_file" "WebUI\\\\Password_PBKDF2" "$h" "[Preferences]"'
        fi
        if [[ "$variant" == "carrier-comment" ]]; then
            # The literal appears ONLY in a comment — a carrier, not code.
            echo '    # historical note: this used to force WebUI\\LocalHostAuth=false'
            echo '    # and WebUI\\AuthSubnetWhitelistEnabled=true across all RFC1918'
        fi
        if [[ "$variant" == "auth-bypass" ]]; then
            echo '    _enforce_config_line "$config_file" "WebUI\\\\LocalHostAuth" "false" "[Preferences]"'
        else
            echo '    _enforce_config_line "$config_file" "WebUI\\\\LocalHostAuth" "true" "[Preferences]"'
        fi
        echo '    _enforce_config_line "$config_file" "WebUI\\\\MaxAuthenticationFailCount" "1000000" "[Preferences]"'
        echo '}'
    } > "$root/start.sh"

    # --- docker-compose.yml ---
    {
        echo 'services:'
        echo '  qbittorrent:'
        echo '    environment:'
        echo '      - WEBUI_PORT=7185'
        if [[ "$variant" == "inert-envvars" ]]; then
            echo '      - WEBUI_USERNAME=admin'
            echo '      - WEBUI_PASSWORD=admin'
        fi
    } > "$root/docker-compose.yml"

    # --- live config ---
    case "$variant" in
        no-live-config) : ;;  # deliberately absent
        no-password-hash)
            printf '[Preferences]\nWebUI\\Username=admin\nWebUI\\Port=7185\n' \
                > "$root/config/qBittorrent/qBittorrent.conf" ;;
        quoted-hash)
            # qBittorrent's own normalised on-shutdown form.
            printf '[Preferences]\nWebUI\\Username=admin\nWebUI\\Password_PBKDF2="@ByteArray(c2FsdA==:aGFzaA==)"\n' \
                > "$root/config/qBittorrent/qBittorrent.conf" ;;
        *)
            printf '[Preferences]\nWebUI\\Username=admin\nWebUI\\Password_PBKDF2=@ByteArray(c2FsdA==:aGFzaA==)\n' \
                > "$root/config/qBittorrent/qBittorrent.conf" ;;
    esac
    echo "$root"
}

check_arm() {
    # $1 = arm name, $2 = variant, $3 = expected exit code
    local name="$1" variant="$2" want="$3"
    local root out rc
    root="$(make_tree "$name" "$variant")"
    out="$TMPD/$name.out"
    set +e
    bash "$GATE" "$root" > "$out" 2>&1
    rc=$?
    set -e
    if [[ "$rc" -eq "$want" ]]; then
        echo "PASS: $name (rc=$rc as expected)"
    else
        echo "FAIL: $name — expected rc=$want got rc=$rc"
        sed 's/^/      /' "$out"
        fails=$((fails + 1))
    fi
}

echo "=== paired-mutation meta-test: CM-QBITTORRENT-WEBUI-CREDENTIALS ==="
echo

check_arm golden-good      correct            0
check_arm golden-bad-1     replace-only       1
check_arm golden-bad-2     auth-bypass        1
check_arm golden-bad-3     no-password-hash   1
check_arm golden-bad-4     inert-envvars      1
# Negative controls: BOTH must stay clean. The quoted-hash arm is the exact
# shape that produced a false violation before the pattern fix; the
# no-live-config arm is the fresh-clone case (artifact_not_yet_built).
check_arm negative-control-quoted quoted-hash    0
# The carrier arm: start.sh legitimately DOCUMENTS the removed bypass in a
# comment. A gate that flags that is a false-positive refusal (§11.4.201(1)).
check_arm negative-control-carrier carrier-comment 0
check_arm negative-control-fresh  no-live-config 0

echo
if [[ "$fails" -gt 0 ]]; then
    echo "=== META-TEST FAIL: $fails arm(s) diverged — the gate is not trustworthy ==="
    exit 1
fi
echo "=== META-TEST PASS: gate fires on every broken arm and stays clean on every good arm ==="
exit 0
