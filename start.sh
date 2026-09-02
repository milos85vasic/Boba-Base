#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONTAINER_RUNTIME=""
COMPOSE_CMD=""
BOBA_CTL_MODE=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Portable in-place sed (§11.4.67/§11.4.81). GNU sed accepts `sed_inplace SCRIPT`,
# but BSD/macOS sed treats the script as the backup-extension and fails with
# "invalid command code" — which aborted the boot before `compose up`. Using
# `-i.bak` (extension attached, no space) works on BOTH, then we drop the
# backup. Last argument is the target file; everything before it is sed args.
sed_inplace() {
    local file="${*: -1}"
    local args=("${@:1:$#-1}")
    sed -i.bobabak "${args[@]}" "$file"
    rm -f "${file}.bobabak"
}

# `podman unshare` only works for LOCAL rootless podman. The macOS podman
# machine is a REMOTE client and rejects it ("cannot use command podman
# unshare with the remote podman client"), which aborted plugin install.
# Detect support once and let callers fall back to plain cp/chmod (§11.4.81).
_podman_unshare_works() {
    [[ "$CONTAINER_RUNTIME" == "podman" ]] || return 1
    podman unshare true >/dev/null 2>&1
}

load_env_file() {
    local env_file="$1"
    if [[ -f "$env_file" ]]; then
        print_info "Loading environment from: $env_file"
        set -a
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ "$line" =~ ^[[:space:]]*$ ]] && continue
            if [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
                local key="${BASH_REMATCH[1]}"
                local value="${BASH_REMATCH[2]}"
                key="${key//[[:space:]]/}"
                value="${value#\"}"
                value="${value%\"}"
                value="${value#\'}"
                value="${value%\'}"
                if [[ -z "${!key:-}" ]]; then
                    export "$key"="$value"
                fi
            fi
        done < "$env_file"
        set +a
    fi
}

load_environment() {
    local env_priority=(
        "$SCRIPT_DIR/.env"
        "$HOME/.qbit.env"
    )
    
    for env_file in "${env_priority[@]}"; do
        load_env_file "$env_file"
    done
    
    QBITTORRENT_DATA_DIR="${QBITTORRENT_DATA_DIR:-$(default_data_dir)}"
    export QBITTORRENT_DATA_DIR

    print_info "Data directory: $QBITTORRENT_DATA_DIR"
}

# Platform-aware default download directory (§11.4.81 cross-platform parity).
# Linux keeps the historical /mnt/DATA mount point; macOS has no /mnt and
# can't create one, so it gets a writable HOME-relative default. An explicit
# QBITTORRENT_DATA_DIR always wins (applied by the caller).
default_data_dir() {
    local os="${1:-$(uname -s)}"
    case "$os" in
        Darwin) echo "$HOME/qbit-data" ;;
        *)      echo "/mnt/DATA" ;;
    esac
}

create_data_directories() {
    print_info "Creating data directories..."
    
    local data_dir="$QBITTORRENT_DATA_DIR"
    
    if [[ ! -d "$data_dir" ]]; then
        print_warning "Data directory does not exist: $data_dir"
        print_info "Attempting to create: $data_dir"
        mkdir -p "$data_dir" 2>/dev/null || {
            print_warning "Could not create data directory. This is expected if it's a mounted volume."
        }
    fi
    
    local subdirs=(
        "Incomplete"
        "Torrents/All"
        "Torrents/Completed"
    )
    
    for subdir in "${subdirs[@]}"; do
        local full_path="$data_dir/$subdir"
        if [[ ! -d "$full_path" ]]; then
            print_info "Creating: $full_path"
            mkdir -p "$full_path" 2>/dev/null || {
                print_warning "Could not create subdirectory: $full_path"
            }
        fi
    done
    
    print_success "Data directories verified"
}

cleanup_stale_config() {
    local active_config="$SCRIPT_DIR/config/qBittorrent/qBittorrent.conf"

    # BOB-LOGIN-FIX (2026-09-01): this function used to DELETE the active
    # config on every boot. Its staleness predicate was
    #     grep -q "SavePath=/downloads/"
    # but qBittorrent NORMALISES SavePath to a trailing slash when it writes
    # its own config, while the template writes it without one. The predicate
    # therefore matched qBittorrent's OWN CORRECT OUTPUT — a §11.4.201
    # false-positive: a guard whose condition is satisfied by the system
    # working properly. Measured 2026-09-01: the live config matched twice and
    # three .backup.* files had accumulated from repeated boots.
    #
    # The destruction was self-healing (update_qbittorrent_config re-copied the
    # template right after), which is why it went unnoticed — but it silently
    # discarded every operator setting on each start.
    #
    # Deleting is no longer needed at all: _ensure_webui_credentials is now
    # insert-or-replace, so the active config is corrected IN PLACE.
    # This function is now non-destructive; it only prunes stale backups the
    # old behaviour left behind.
    if [[ -f "$active_config" ]]; then
        print_info "Active qBittorrent config present; settings will be enforced in place"
    fi

    # Prune backups produced by the old destructive path, keeping the 3 newest
    # so nothing an operator may still want is removed without trace.
    local -a backups=()
    while IFS= read -r b; do
        [[ -n "$b" ]] && backups+=("$b")
    done < <(ls -1t "${active_config}".backup.* 2>/dev/null || true)

    if (( ${#backups[@]} > 3 )); then
        local i
        for (( i = 3; i < ${#backups[@]}; i++ )); do
            rm -f "${backups[$i]}" 2>/dev/null || true
        done
        print_info "Pruned $(( ${#backups[@]} - 3 )) old qBittorrent config backup(s)"
    fi
}

_ensure_webui_credentials() {
    local config_file="$1"
    local webui_port="${WEBUI_PORT:-7185}"

    # M5 (review): setup.sh once wrote WEBUI_PORT=7186 into .env — but 7186 is
    # the download-proxy that sits IN FRONT of qBittorrent, not qBittorrent's
    # own listen port. A legacy .env still carrying it would make this function
    # enforce WebUI\\Port=7186 and collide with the proxy. Newly generated .env
    # files are fixed; an existing one is surfaced rather than silently obeyed.
    if [[ "$webui_port" == "7186" ]]; then
        print_warning "WEBUI_PORT=7186 in your .env is the DOWNLOAD-PROXY port, not qBittorrent's"
        print_warning "  Using 7185 for qBittorrent's WebUI\\Port instead. Fix .env to silence this."
        webui_port=7185
    fi

    if [[ ! -f "$config_file" ]]; then
        return 0
    fi

    # N3 (review): qBittorrent PERSISTS its in-memory settings to this file when
    # it shuts down. So a warm `./start.sh` over an already-running stack edits
    # the config underneath a live process, and those edits are overwritten at
    # the next container stop — enforcement takes effect only from the following
    # container START. This is self-healing on the normal cold path (main()
    # writes the config well before start_container), but it is why editing
    # qBittorrent.conf by hand while the container runs appears to do nothing.
    print_info "Ensuring WebUI credentials and port in: $config_file"

    # BOB-LOGIN-FIX (2026-09-01): these three keys were previously written with
    # grep-then-sed, i.e. REPLACE-ONLY. On a config that LACKS the key — which
    # is exactly the shape qBittorrent 5.x writes on a fresh install — the sed
    # never fired and the function still returned 0, so the credentials were
    # silently never written and qBittorrent minted a random temporary password
    # on every boot. _enforce_config_line is insert-or-replace, so a fresh
    # config now gets the credentials it needs. Measured RED->GREEN in
    # tests/unit/test_start_sh_boot_integrity.sh.
    local pbkdf2_hash='@ByteArray(XGCniD5hOQPEcE510BED2Q==:jLIBnLj5eCBZjRCvtE7dTSutDtS8mBQNKQ6rq/W3MszKNsKBjM2/8Ur9fxsADvQeh1wntKorznkorETYAFZawQ==)'
    _enforce_config_line "$config_file" "WebUI\\\\Port" "${webui_port}" "[Preferences]"
    _enforce_config_line "$config_file" "WebUI\\\\Username" "admin" "[Preferences]"
    _enforce_config_line "$config_file" "WebUI\\\\Password_PBKDF2" "${pbkdf2_hash}" "[Preferences]"
    _enforce_config_line "$config_file" "WebUI\\\\Enabled" "true" "[Preferences]"

    # Brute-force lockout relaxation, WITHOUT disabling authentication.
    #
    # SECURITY FIX (2026-09-01). This block used to force:
    #     WebUI\LocalHostAuth=false
    #     WebUI\AuthSubnetWhitelistEnabled=true    (whitelist = loopback + ALL RFC1918)
    # to stop the test suite's repeated login probes tripping qBittorrent's
    # 5-failures-then-ban default. But those two settings do not relax the ban —
    # they DISABLE AUTHENTICATION outright for every listed subnet. Combined
    # with `network_mode: host` and WebUI\Address=*, that left the WebUI
    # unauthenticated across the entire LAN.
    #
    # MEASURED 2026-09-01: with the old settings a deliberately WRONG password
    # returned HTTP 204 (accepted). With the settings below, admin/admin
    # returns 204 while a wrong password returns 401 and an unauthenticated
    # API call returns Forbidden — i.e. auth genuinely works.
    #
    # The lockout concern is addressed by MaxAuthenticationFailCount and
    # BanDuration below, which relax the LOCKOUT without removing the CHECK.
    _enforce_config_line "$config_file" "WebUI\\\\LocalHostAuth" "true" "[Preferences]"
    _enforce_config_line "$config_file" "WebUI\\\\AuthSubnetWhitelistEnabled" "false" "[Preferences]"
    _enforce_config_line "$config_file" "WebUI\\\\AuthSubnetWhitelist" "127.0.0.1/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16" "[Preferences]"
    _enforce_config_line "$config_file" "WebUI\\\\MaxAuthenticationFailCount" "1000000" "[Preferences]"
    _enforce_config_line "$config_file" "WebUI\\\\BanDuration" "1" "[Preferences]"

    local dup_lines
    dup_lines=$(grep -n "^\\[Application\\]$" "$config_file" 2>/dev/null | tail -n +2 | cut -d: -f1 | sort -rn || true)
    for line_num in $dup_lines; do
        sed_inplace "${line_num}d" "$config_file"
    done
}

# Insert-or-replace a key=value under a given [section] header.
# Handles the qBittorrent backslash-escaped keys (e.g. WebUI\LocalHostAuth).
_enforce_config_line() {
    local config_file="$1"
    local key="$2"     # backslash-escaped for sed regex
    local value="$3"
    local section="$4"

    # N2 (review): the value is interpolated raw into a sed replacement, so a
    # value containing `|` (the delimiter) or `&` (the whole-match backref)
    # would corrupt the file. Every value this project passes is safe (base64
    # alphabet, digits, commas, slashes), but refuse loudly rather than corrupt
    # a config if that ever changes.
    case "$value" in
        *"|"*|*"&"*|*"\\"*)
            print_error "_enforce_config_line: value for ${key} contains '|', '&' or a backslash, which would corrupt the sed replacement"
            return 1
            ;;
    esac

    if grep -qE "^${key}=" "$config_file" 2>/dev/null; then
        sed_inplace -E "s|^${key}=.*|${key}=${value}|" "$config_file"
    else
        # Insert under the section header if it exists; otherwise
        # append at EOF.
        local literal_section
        literal_section=$(printf '%s' "$section" | sed 's/[][]/\\&/g')
        if grep -qE "^${literal_section}" "$config_file" 2>/dev/null; then
            # Insert immediately after the section header.
            awk -v sec="$section" -v line="${key}=${value}" '
                BEGIN { inserted = 0 }
                { print }
                !inserted && $0 == sec { print line; inserted = 1 }
            ' "$config_file" > "${config_file}.tmp" && mv "${config_file}.tmp" "$config_file"
        else
            printf '\n%s\n%s=%s\n' "$section" "$key" "$value" >> "$config_file"
        fi
    fi
}

update_qbittorrent_config() {
    local template_config="$SCRIPT_DIR/config/qBittorrent/config/qBittorrent.conf"
    local active_config="$SCRIPT_DIR/config/qBittorrent/qBittorrent.conf"
    local config_dir
    config_dir=$(dirname "$template_config")

    if [[ ! -d "$config_dir" ]]; then
        mkdir -p "$config_dir"
    fi

    if [[ ! -f "$template_config" ]]; then
        print_info "Creating default qBittorrent configuration..."
        cat > "$template_config" << EOF
[LegalNotice]
Accepted=true

[BitTorrent]
Session\DefaultSavePath=/downloads
Session\TempPath=/downloads/Incomplete
Session\TempPathEnabled=true
Session\IncompleteFilesExtension=.!qB

[Preferences]
Downloads\SavePath=/downloads
Downloads\TempPath=/downloads/Incomplete
Downloads\TempPathEnabled=true
Downloads\IncompleteFilesExt=!qB
Downloads\PreAllocation=false
Downloads\UseIncompleteExtension=true

Advanced\AnnounceToAllTrackers=true
Advanced\AnnounceToAllTiers=true
Advanced\AnonymousMode=false
Advanced\AsyncIOThreadsCount=10
Advanced\FilePoolSize=5000
Advanced\CheckingMemoryUse=512
Advanced\OutgoingPortsMin=0
Advanced\OutgoingPortsMax=0

Connection\GlobalDLLimit=0
Connection\GlobalDLLimitAlt=0
Connection\GlobalUPLimit=0
Connection\GlobalUPLimitAlt=0
Connection\MaxConnections=500
Connection\MaxConnectionsPerTorrent=100
Connection\MaxUploads=20
Connection\MaxUploadsPerTorrent=4

General\Locale=en
General\UseRandomPort=true
General\ExitCheckDownloads=true

WebUI\Enabled=true
WebUI\Port=${WEBUI_PORT:-7185}
WebUI\Address=*
WebUI\Username=admin
WebUI\Password_PBKDF2="@ByteArray(XGCniD5hOQPEcE510BED2Q==:jLIBnLj5eCBZjRCvtE7dTSutDtS8mBQNKQ6rq/W3MszKNsKBjM2/8Ur9fxsADvQeh1wntKorznkorETYAFZawQ==)"
WebUI\LocalHostAuth=true
WebUI\AuthSubnetWhitelistEnabled=false
WebUI\AuthSubnetWhitelist=127.0.0.1/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
WebUI\MaxAuthenticationFailCount=1000000
WebUI\BanDuration=1
WebUI\ServerDomains=*
WebUI\UseUPNP=true
WebUI\UseHTTPS=false

MailNotification\Enabled=false

RSS\AutoDownloader\Enabled=false

Search\PluginManager\UseProxy=false
Search\PluginManager\Enabled=true
EOF
        print_success "Default configuration created"
    fi

    _ensure_webui_credentials "$template_config"
    _ensure_webui_credentials "$active_config"

    # If the active config was removed by cleanup_stale_config (or never
    # existed), seed it from the template so qBittorrent starts with the
    # correct ban-prevention and path settings.
    if [[ ! -f "$active_config" ]]; then
        cp "$template_config" "$active_config"
        print_info "Copied template config to active config"
    fi

    print_success "qBittorrent configuration ready"
}

detect_container_runtime() {
    if command -v podman &> /dev/null; then
        CONTAINER_RUNTIME="podman"
        if command -v podman-compose &> /dev/null; then
            COMPOSE_CMD="podman-compose"
        else
            print_error "podman-compose not found. Please install it."
            exit 1
        fi
        print_info "Using Podman with podman-compose"
    elif command -v docker &> /dev/null; then
        CONTAINER_RUNTIME="docker"
        if docker compose version &> /dev/null; then
            COMPOSE_CMD="docker compose"
        elif command -v docker-compose &> /dev/null; then
            COMPOSE_CMD="docker-compose"
        else
            print_error "Docker Compose not found. Please install it."
            exit 1
        fi
        print_info "Using Docker with Docker Compose"
    else
        if [[ "$BOBA_CTL_MODE" == false ]]; then
            print_error "Neither Podman nor Docker found. Please install one of them."
            exit 1
        fi
        CONTAINER_RUNTIME=""
    fi

    if [[ "$BOBA_CTL_MODE" == true ]]; then
        COMPOSE_CMD="$SCRIPT_DIR/scripts/boba-ctl.sh"
        print_info "Using boba-ctl for container orchestration"
    fi
}

check_prerequisites() {
    if [[ ! -f "docker-compose.yml" ]]; then
        print_error "docker-compose.yml not found in $SCRIPT_DIR"
        exit 1
    fi

    if ! $COMPOSE_CMD config &> /dev/null; then
        print_error "Invalid docker-compose.yml syntax"
        $COMPOSE_CMD config
        exit 1
    fi
}

create_directories() {
    print_info "Creating necessary directories..."
    mkdir -p config/qBittorrent
    mkdir -p config/qBittorrent/nova3/engines

    harden_config_permissions

    print_success "Directories created"
}

# ---------------------------------------------------------------------------
# harden_config_permissions — NARROW config/ permissions; never widen them.
# Feature 002-user-owned-downloads (FR-015), security regression fixed
# 2026-08-21.
#
# WHAT THIS REPLACED, AND WHY REMOVAL IS PROVEN SAFE (§11.4.124 —
# investigate before removing, never "no references ⇒ delete"):
#
#   This function replaces `podman unshare chmod -R a+rw config/`, added
#   2026-04-14 in commit 00f1fa6 ("Fix start.sh config/ permissions for podman
#   unshare"). Git archaeology places it squarely in the PRE-fix world this
#   feature exists to end: container writes landed at host uid 100999, the
#   operator could not access config/, and the workaround blanket-widened the
#   whole tree so that *somebody* could write it.
#
#   That premise is now false. Every compose service that mounts anything under
#   ./config was enumerated from docker-compose.yml and each one writes as host
#   uid 1000 — the operator, who OWNS the tree:
#       qbittorrent           PUID=0/PGID=0        -> container root = host uid 1000
#       jackett               PUID=0/PGID=0        -> container root = host uid 1000
#       download-proxy        no PUID (root)       -> container root = host uid 1000
#       boba-jackett          no PUID (root)       -> container root = host uid 1000
#       qbittorrent-proxy-go  no PUID (root)       -> container root = host uid 1000  [profile: go]
#   Under rootless Podman container-root IS the host operator, which is the same
#   measured fact the ownership precondition's in-container probe asserts on every
#   start. Owner permissions therefore suffice and `a+rw` buys nothing.
#
#   What it COST was not nothing: it left the AES-256-GCM credential store
#   config/boba.db at mode 666 — world-readable AND world-writable — so any
#   local user could read or REPLACE it. That is strictly worse than the
#   ownership defect it was compensating for, and it contradicts FR-015, which
#   requires the credential store stay no more permissive than 600.
#
#   `_podman_unshare_works` is NOT orphaned by this removal: copy_plugins still
#   calls it for `podman unshare cp`.
#
# DIRECTION, STATED PRECISELY (FR-015) — and stated precisely BECAUSE an earlier
# version of this comment was measurably false, which in a security-invariant
# comment is the very defect class this feature exists to close.
#
# WHAT HOLDS: no group/other principal can gain any access here. `go-w` only ever
# clears bits, and the credential store is forced DOWN to 600 whenever it is more
# permissive. That is the guarantee, and it is the one FR-015 asks for.
#
# WHAT DOES NOT HOLD: this function does NOT "only ever remove permission bits",
# and it is NOT true that "nothing here can grant access that did not already
# exist" — both were claimed here and both are false. MEASURED: a 400 store comes
# out 600, which GRANTS OWNER-WRITE. Materially harmless, since the owner can
# chmod at will; but an unqualified absolute in a comment like this is exactly
# what a reader relies on and must not be left standing (T018 re-review MINOR-5,
# and its NIT-3 successor when the first correction was appended while the false
# sentences were left in place).
harden_config_permissions() {
    local cfg="$SCRIPT_DIR/config"
    [[ -d "$cfg" ]] || return 0

    # Strip group/other WRITE across the tree. Read bits are left alone: this
    # change is scoped to the write vector the old widening opened, and blindly
    # stripping read from a running stack's config would be a different, riskier
    # change than the defect warrants.
    chmod -R go-w "$cfg" 2>/dev/null || true

    # The credential store is held to FR-015's floor explicitly, because
    # "no more permissive than 600" is the whole requirement for this one file.
    if [[ -f "$cfg/boba.db" ]]; then
        chmod 600 "$cfg/boba.db" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# assert_credential_store_mode — the regression check that makes FR-015
# enforced rather than merely documented.
#
# WHY AN ASSERTION AND NOT A COMMENT: the mode is changed at RUNTIME, by this
# script and by whatever the containers do while they run, so inspecting the
# source proves nothing about the file on disk. A comment saying "must be 600"
# is exactly how the 666 regression survived unnoticed. This reads the REAL
# mode off the REAL file after the stack is up and FAILS LOUDLY when it is more
# permissive than 600 (§11.4.201 — assert the real condition).
#
# An ABSENT store is not a failure: config/boba.db does not exist before first
# boot, which is why the ownership scope declares it optional: true. Refusing on
# absence would be the false-positive refusal §11.4.201(1) forbids.
assert_credential_store_mode() {
    local db="$SCRIPT_DIR/config/boba.db"
    [[ -f "$db" ]] || { print_info "Credential store not created yet — mode check skipped (absent, not a failure)"; return 0; }

    local mode owner
    mode="$(stat -c '%a' "$db" 2>/dev/null || true)"
    owner="$(stat -c '%U:%G' "$db" 2>/dev/null || true)"
    if [[ -z "$mode" ]]; then
        print_error "Could not read the mode of $db — refusing to report success on an unverified credential store."
        exit 1
    fi

    # FR-015 IS ABOUT SEMANTICS, NOT THE OCTAL (T018 re-review, MINOR-4).
    #
    # The former test was `(mode & 0177) != 0`, which includes OWNER-EXECUTE. It
    # therefore REFUSED mode 700 and mode 500 — while neither grants a non-owner
    # principal anything, and 500 is strictly LESS permissive than 600 in the
    # write dimension. Refusing a mode that widens nothing is a §11.4.201(1)
    # FALSE-POSITIVE REFUSAL, forbidden at the same severity as a false pass, and
    # the message it printed ("mode 700 — more permissive than 600") was simply
    # untrue. Conversely 2600 PASSED silently, though setgid is a real widening
    # and scripts/ownership_repair.sh:689 already strips setuid/setgid on exactly
    # this reasoning — two implementations of one requirement disagreeing.
    #
    # The requirement is: NO NON-OWNER PRINCIPAL MAY HAVE ANY ACCESS, and no
    # special bit may be set. Owner bits are irrelevant to it. Sticky (1000) is
    # inert on a regular file and is not treated as a widening, matching the
    # repair's own 8#1777 mask.
    local nonowner special
    nonowner="$((8#$mode & 8#77))"
    special="$((8#$mode & 8#6000))"
    if [[ "$nonowner" -ne 0 || "$special" -ne 0 ]]; then
        if [[ "$nonowner" -ne 0 ]]; then
            print_error "SECURITY: credential store $db is mode $mode (owner $owner) — grants access to group/other (FR-015)."
        else
            print_error "SECURITY: credential store $db is mode $mode (owner $owner) — carries a setuid/setgid bit (FR-015)."
        fi
        print_error "  This store holds the AES-256-GCM master-key-encrypted tracker credentials."
        print_error "  Refusing to report a successful start on a widened credential store."
        print_error "  Remediate with: bash scripts/ownership_repair.sh"
        exit 1
    fi
    print_success "Credential store $db mode $mode owner $owner — no non-owner access, no special bits (FR-015)"
}

pull_image() {
    if [[ "$BOBA_CTL_MODE" == true ]]; then
        print_warning "Image pull not available in boba-ctl mode — pull manually or use compose directly"
        return 0
    fi
    print_info "Pulling latest image..."
    $COMPOSE_CMD pull
    print_success "Image pulled successfully"
}

copy_plugins() {
    print_info "Installing search plugins..."
    
    local engines_dir="config/qBittorrent/nova3/engines"
    
    if [[ ! -d "plugins" ]]; then
        print_warning "No plugins directory found"
        return 0
    fi
    
    local copy_cmd="cp"
    if _podman_unshare_works; then
        copy_cmd="podman unshare cp"
    fi
    
    for plugin in plugins/*.py; do
        if [[ -f "$plugin" ]]; then
            $copy_cmd "$plugin" "$engines_dir/"
            print_success "Installed: $(basename "$plugin")"
        fi
    done

    # The nova3 framework modules (novaprinter, helpers) must live at the
    # nova3 ROOT, not under engines/. The merge service runs each public
    # plugin via `python3 -c` with sys.path=<nova3 root> and does
    # `import novaprinter`; every plugin does `from helpers import ...`.
    # qBittorrent's own container ships these at the root, but the
    # python-alpine download-proxy container does not — so without this every
    # public-tracker plugin failed with ModuleNotFoundError (BOB-005).
    local nova3_root="config/qBittorrent/nova3"
    for fw in novaprinter.py helpers.py; do
        if [[ -f "plugins/$fw" ]]; then
            $copy_cmd "plugins/$fw" "$nova3_root/"
            print_success "Installed framework module at nova3 root: $fw"
        fi
    done

    for icon in plugins/*.png; do
        if [[ -f "$icon" ]]; then
            $copy_cmd "$icon" "$engines_dir/"
        fi
    done
    
    # Copy JSON configs (jackett, kinozal, nnmclub)
    for cfg in plugins/*.json; do
        if [[ -f "$cfg" ]]; then
            $copy_cmd "$cfg" "$engines_dir/"
            print_success "Installed: $(basename "$cfg")"
        fi
    done
    
    # Copy community plugins and their configs
    if [[ -d "plugins/community" ]]; then
        for plugin in plugins/community/*.py; do
            if [[ -f "$plugin" ]]; then
                $copy_cmd "$plugin" "$engines_dir/"
                print_success "Installed: $(basename "$plugin")"
            fi
        done
        for cfg in plugins/community/*.json; do
            if [[ -f "$cfg" ]]; then
                $copy_cmd "$cfg" "$engines_dir/"
                print_success "Installed: $(basename "$cfg")"
            fi
        done
    fi
}

start_container() {
    print_info "Starting qBitTorrent container..."
    
    if $COMPOSE_CMD up -d; then
        print_success "Container started successfully"
    else
        print_error "Failed to start container"
        exit 1
    fi
}

wait_for_container() {
    print_info "Waiting for container to be ready..."
    # M1 (review): overridable so the boot-integrity unit test can exercise the
    # loop without burning the full production budget. Defaults unchanged.
    local max_attempts="${BOBA_WAIT_MAX_ATTEMPTS:-30}"
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        if $CONTAINER_RUNTIME ps --format '{{.Names}}' | grep -q "^qbittorrent$"; then
            sleep 2
            print_success "Container is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    print_warning "Container may not be fully ready yet"
    return 0
}

wait_for_jackett() {
    print_info "Waiting for Jackett to be ready..."
    local max_attempts="${BOBA_WAIT_MAX_ATTEMPTS:-60}"
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        if curl -sf "http://localhost:9117/health" > /dev/null 2>&1; then
            print_success "Jackett is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    print_warning "Jackett may not be fully ready yet"
    return 0
}

ensure_boba_master_key() {
    # Auto-generates BOBA_MASTER_KEY (32-byte hex) into ./.env if missing
    # or malformed. The Go binary (cmd/boba-jackett) ALSO generates on
    # startup via bootstrap.EnsureMasterKey — this host-side path is the
    # earlier defense in depth so the docker-compose env-var interpolation
    # has a value before the container starts.
    #
    # Safe to run repeatedly. Existing valid key (64 hex chars) is left
    # alone. File mode is forced to 0600 — never world-readable.
    local env_file="$SCRIPT_DIR/.env"
    if [[ ! -f "$env_file" ]]; then
        touch "$env_file"
        chmod 0600 "$env_file"
    fi
    if grep -qE '^BOBA_MASTER_KEY=[0-9a-fA-F]{64}$' "$env_file"; then
        # BOB-LOGIN-FIX (2026-09-01): this early return used to skip BOTH
        # chmod sites, so on an already-provisioned host .env stayed at the
        # umask default (measured: 664 — world-readable) while holding
        # BOBA_MASTER_KEY (which decrypts config/boba.db) plus every tracker
        # password. The function's own docstring claimed "forced to 0600".
        # Enforce it unconditionally on the path actually taken (§11.4.10).
        chmod 0600 "$env_file" 2>/dev/null || print_warning "Could not chmod 0600 $env_file"
        return 0
    fi
    print_info "Generating BOBA_MASTER_KEY (32-byte hex) for boba-jackett credential encryption..."
    local key
    key=$(head -c 32 /dev/urandom | xxd -p -c 64)
    {
        echo ""
        echo "# === BOBA SYSTEM ==="
        echo "# Master key for credential encryption-at-rest in config/boba.db."
        echo "# DO NOT LOSE THIS — credentials become unrecoverable without it."
        echo "# To rotate: see docs/BOBA_DATABASE.md § \"Key Rotation\"."
        echo "BOBA_MASTER_KEY=$key"
    } >> "$env_file"
    chmod 0600 "$env_file"
    print_success "BOBA_MASTER_KEY persisted to .env (mode 0600)"
}

extract_jackett_key() {
    local config_file="$SCRIPT_DIR/config/jackett/Jackett/ServerConfig.json"
    if [[ ! -f "$config_file" ]]; then
        return 0
    fi
    
    local key
    key=$(python3 -c "
import json, sys
try:
    with open('$config_file') as f:
        data = json.load(f)
    key = data.get('APIKey', '')
    if key and key.strip().lower() != 'your_api_key_here':
        print(key.strip())
except Exception:
    pass
" 2>/dev/null)
    
    if [[ -z "$key" ]]; then
        return 0
    fi
    
    echo "$key"
}

update_env_jackett_key() {
    local key="$1"
    local env_file="$SCRIPT_DIR/.env"
    
    if [[ -z "$key" ]]; then
        return 0
    fi
    
    if [[ ! -f "$env_file" ]]; then
        return 0
    fi
    
    # only update if missing or still placeholder
    if grep -q "^JACKETT_API_KEY=YOUR_API_KEY_HERE" "$env_file" 2>/dev/null || ! grep -q "^JACKETT_API_KEY=" "$env_file" 2>/dev/null; then
        # ATTEMPT. Neither writer's exit status is trustworthy on its own:
        # `sed_inplace` ends in `rm -f "${file}.bobabak"`, which SUCCEEDS after a
        # failed `sed -i` and masks it (MEASURED 2026-09-01: with the .env
        # directory read-only, sed printed "Permission denied", sed_inplace still
        # returned 0, and this function printed [SUCCESS] on a write that never
        # landed). So the attempt is best-effort and the VERIFY below — not the
        # writer's rc — decides what the operator is told (§11.4.201: assert the
        # REAL condition from the authoritative source, which is the file).
        if grep -q "^JACKETT_API_KEY=" "$env_file" 2>/dev/null; then
            sed_inplace "s|^JACKETT_API_KEY=.*|JACKETT_API_KEY=$key|" "$env_file" || true
        else
            echo "JACKETT_API_KEY=$key" >> "$env_file" || true
        fi

        # VERIFY the key actually landed by READING IT BACK. The comparison is
        # done in-shell against $key so the value never reaches a command line,
        # an argv visible in `ps`, or any log line (§11.4.10 — names only).
        #
        # The `|| true` is load-bearing, not decoration: this whole function is
        # called UNGUARDED from main() under `set -euo pipefail`, so a bare
        # assignment whose command substitution exits non-zero ABORTS THE BOOT.
        # MEASURED 2026-09-01: with .env mode 0000 the first draft of this fix
        # killed start.sh at exit 2 before the container came up — trading a
        # silent failure for a total one, which is strictly worse. An unreadable
        # .env must yield an EMPTY read that the check below reports LOUDLY, and
        # boot must continue. Same reasoning as the arithmetic-increment repair
        # that removed the unsafe post-increment sites from this file.
        local env_now
        env_now="$(sed -n 's/^JACKETT_API_KEY=//p' "$env_file" 2>/dev/null | tail -n1 || true)"
        if [[ "$env_now" == "$key" ]]; then
            print_success "Jackett API key auto-configured in .env"
        else
            print_error "JACKETT_API_KEY was NOT written to $env_file"
            print_warning "  The write was attempted and did not land (check permissions on"
            print_warning "  $env_file and its directory)."
            print_warning "  CONSEQUENCE: an EMPTY JACKETT_API_KEY is injected into the proxy and"
            print_warning "  every Jackett-backed search will fail at runtime with no other signal."
            print_warning "  Boot continues; fix the file and re-run ./start.sh to retry."
        fi
    fi

    # also update plugins/jackett.json for local installs
    local plugin_json="$SCRIPT_DIR/config/qBittorrent/nova3/engines/jackett.json"
    if [[ -f "$plugin_json" ]]; then
        # The key is passed through the ENVIRONMENT, never interpolated into the
        # python source: interpolation put the secret on the command line (argv
        # is world-readable via `ps`, §11.4.10) and broke on any quote in the key.
        local py_err=""
        if ! py_err="$(BOBA_JACKETT_KEY="$key" PLUGIN_JSON="$plugin_json" python3 -c '
import json, os, sys
path = os.environ["PLUGIN_JSON"]
with open(path) as f:
    data = json.load(f)
if data.get("api_key") in (None, "", "YOUR_API_KEY_HERE"):
    data["api_key"] = os.environ["BOBA_JACKETT_KEY"]
    with open(path, "w") as f:
        json.dump(data, f, indent=4, sort_keys=True)
' 2>&1)"; then
            print_error "Jackett API key was NOT written to $plugin_json"
            # py_err is python diagnostics (path/errno), never the key value.
            [[ -n "$py_err" ]] && print_warning "  ${py_err##*$'\n'}"
            print_warning "  CONSEQUENCE: the local jackett plugin keeps its placeholder key and"
            print_warning "  its searches will fail. Boot continues; re-run ./start.sh after fixing."
        fi
    fi
    return 0
}

# Decide whether a qBittorrent WebUI login SUCCEEDED.
#
# MEASURED 2026-09-01 against the real image (qBittorrent v5.2.3, WebAPI
# 2.15.1): a SUCCESSFUL login returns HTTP 204 with an EMPTY body and sets
# cookie QBT_SID_<port>. qBittorrent 4.x returned HTTP 200 with body "Ok.".
# The previous code compared the body to the literal "Ok." and therefore read
# every real 5.x success as a failure — then `return 0`'d anyway, so the
# failure was invisible. Accept BOTH signals, and treat the session cookie as
# authoritative (the repo's own download-proxy already does: see
# download-proxy/src/api/routes.py and tests/unit/test_qbit_login_compat.py).
#
# Args: $1 = http status, $2 = response body, $3 = cookie-jar path
_qbit_login_succeeded() {
    local http_code="$1" body="$2" jar="$3"

    # Authoritative: the server issued a session cookie.
    if [[ -f "$jar" ]] && grep -q 'QBT_SID' "$jar" 2>/dev/null; then
        return 0
    fi
    # qBittorrent 5.x: 204 No Content, empty body.
    if [[ "$http_code" == "204" ]]; then
        return 0
    fi
    # qBittorrent 4.x: 200 with the literal body "Ok.".
    if [[ "$http_code" == "200" && "$body" == "Ok." ]]; then
        return 0
    fi
    return 1
}

# POST a login and report success via _qbit_login_succeeded.
# Args: $1 = port, $2 = username, $3 = password, $4 = cookie-jar path
_qbit_try_login() {
    local port="$1" user="$2" pass="$3" jar="$4"
    local body_file http_code body
    body_file="$(mktemp)"
    rm -f "$jar" 2>/dev/null || true

    http_code=$(curl -s -o "$body_file" -w '%{http_code}' \
        -c "$jar" \
        -H "Referer: http://localhost:${port}" \
        --data-urlencode "username=${user}" \
        --data-urlencode "password=${pass}" \
        "http://localhost:${port}/api/v2/auth/login" 2>/dev/null || echo "000")
    body="$(cat "$body_file" 2>/dev/null || true)"
    rm -f "$body_file" 2>/dev/null || true

    _qbit_login_succeeded "$http_code" "$body" "$jar"
}

ensure_webui_password() {
    local webui_port="${WEBUI_PORT:-7185}"
    local max_attempts="${BOBA_WAIT_MAX_ATTEMPTS:-30}"
    local attempt=0
    local jar
    jar="$(mktemp -t qbit_setup.XXXXXX)"

    print_info "Waiting for WebUI to be ready..."
    while [[ $attempt -lt $max_attempts ]]; do
        local probe
        probe=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${webui_port}/" 2>/dev/null || echo "000")
        if [[ "$probe" == "200" || "$probe" == "401" || "$probe" == "403" ]]; then
            break
        fi
        attempt=$((attempt + 1))
        sleep 1
    done

    if [[ $attempt -ge $max_attempts ]]; then
        print_warning "WebUI not ready after ${max_attempts}s, skipping password setup"
        rm -f "$jar" 2>/dev/null || true
        return 0
    fi

    # Happy path: the config already carries admin/admin.
    if _qbit_try_login "$webui_port" "admin" "admin" "$jar"; then
        print_success "WebUI login with admin/admin verified"
        rm -f "$jar" 2>/dev/null || true
        return 0
    fi

    # Fallback: qBittorrent minted a temporary password because the config
    # carried no WebUI\Password_PBKDF2. Recover it from the container log and
    # set the intended password through the API.
    local temp_pass
    temp_pass=$($CONTAINER_RUNTIME logs qbittorrent 2>&1 \
        | grep "temporary password" | tail -1 \
        | grep -oP 'temporary password is provided for this session: \K.*' || true)

    if [[ -z "$temp_pass" ]]; then
        print_warning "admin/admin login failed and no temporary password was found in the container log"
        print_warning "The WebUI config may be missing WebUI\\Password_PBKDF2 — check ${SCRIPT_DIR}/config/qBittorrent/qBittorrent.conf"
        rm -f "$jar" 2>/dev/null || true
        return 0
    fi

    # M2 (review): the temporary password is a live credential. `./start.sh -v`
    # turns on `set -x`, which would trace it as argv to stderr and into the
    # journal. Disable tracing across the credential-bearing call, then restore
    # whatever the caller had (§11.4.10 — credentials never enter logs).
    local _xtrace_was_on=0
    case "$-" in *x*) _xtrace_was_on=1 ;; esac
    set +x
    if ! _qbit_try_login "$webui_port" "admin" "$temp_pass" "$jar"; then
        [[ "$_xtrace_was_on" == 1 ]] && set -x
        print_warning "Could not log in with the recovered temporary password"
        rm -f "$jar" 2>/dev/null || true
        return 0
    fi
    [[ "$_xtrace_was_on" == 1 ]] && set -x

    local set_code
    set_code=$(curl -s -o /dev/null -w '%{http_code}' -b "$jar" \
        -H "Referer: http://localhost:${webui_port}" \
        -X POST "http://localhost:${webui_port}/api/v2/app/setPreferences" \
        -d 'json={"web_ui_password":"admin"}' 2>/dev/null || echo "000")

    rm -f "$jar" 2>/dev/null || true

    if [[ "$set_code" != "200" ]]; then
        print_warning "setPreferences returned HTTP ${set_code} — password may not have been changed"
        return 0
    fi

    # Anti-bluff (§11.4): do not claim success — re-login and PROVE it.
    local verify_jar
    verify_jar="$(mktemp -t qbit_verify.XXXXXX)"
    if _qbit_try_login "$webui_port" "admin" "admin" "$verify_jar"; then
        print_success "WebUI password set to admin (verified by re-login)"
    else
        print_warning "Password was set but the admin/admin re-login did NOT succeed"
    fi
    rm -f "$verify_jar" 2>/dev/null || true
}

show_status() {
    echo ""
    print_info "Container Status:"
    $COMPOSE_CMD ps
    echo ""
    print_success "qBitTorrent Web UI: http://localhost:${WEBUI_PORT:-7185}"
    print_success "Боба Dashboard: http://localhost:${MERGE_SERVICE_PORT:-7187}/"
    print_success "Jackett Admin: http://localhost:9117/UI/Dashboard"
    print_info "Default credentials: admin / admin"
    print_warning "Remember to change the default password!"
    echo ""
    print_info "Data Directory: $QBITTORRENT_DATA_DIR"
    print_info "  Downloads:     $QBITTORRENT_DATA_DIR"
    print_info "  Incomplete:    $QBITTORRENT_DATA_DIR/Incomplete"
    print_info "  Torrents:      $QBITTORRENT_DATA_DIR/Torrents"
    echo ""
    
    if [[ -f "config/qBittorrent/nova3/engines/rutracker.py" ]]; then
        print_info "RuTracker plugin installed"
        if [[ -f ".env" ]] && grep -q "^RUTRACKER_USERNAME=.\+" ".env" 2>/dev/null; then
            print_success "RuTracker credentials configured"
        else
            print_warning "Configure RuTracker credentials in .env file"
        fi
    fi
}

build_frontend() {
    local fe="$SCRIPT_DIR/frontend"

    if [[ ! -d "$fe" ]]; then
        print_warning "frontend/ directory not found, skipping Angular build"
        return 0
    fi

    # The merge service serves the Angular SPA from
    #   download-proxy/src/ui/dist/frontend/browser/index.html
    # (frontend/angular.json outputPath = ../download-proxy/src/ui/dist/frontend).
    # If that file is absent, api/__init__.py sets _angular_available=False and
    # http://localhost:7187/ answers with the stub {"dashboard":"not found"}
    # instead of the dashboard.
    #
    # BOB-DASHBOARD-FIX (2026-09-01): this function used to test ONLY for a
    # GLOBAL `ng` and skip with a non-actionable warning. Angular CLI is a
    # PROJECT dependency, not a global one, so on a fresh clone `ng` is never
    # on PATH, the build never ran, and the dashboard was dead while :7187
    # still answered HTTP 200 — a §11.4.201 false-null (a healthy status code
    # over an empty page). Resolve the CLI the way the project actually
    # provides it, and install dependencies if they are missing.
    local expected_index="$SCRIPT_DIR/download-proxy/src/ui/dist/frontend/browser/index.html"

    local ng_cmd=""
    if [[ -x "$fe/node_modules/.bin/ng" ]]; then
        ng_cmd="$fe/node_modules/.bin/ng"
    elif command -v ng &> /dev/null; then
        ng_cmd="ng"
    fi

    if [[ -z "$ng_cmd" ]]; then
        if ! command -v npm &> /dev/null; then
            print_warning "Angular frontend NOT built: neither a local nor global 'ng', and npm is unavailable."
            print_warning "  Consequence: http://localhost:${MERGE_SERVICE_PORT:-7187}/ will serve {\"dashboard\":\"not found\"}."
            print_warning "  Fix: install Node.js + npm, then re-run ./start.sh"
            return 0
        fi
        print_info "Angular CLI not present locally — installing frontend dependencies (npm)..."
        # Host-safety: keep the install off the interactive scheduler's back
        # (§12.6/§12.11) — it is a heavy, bursty job.
        if ! ( cd "$fe" && nice -n 19 ionice -c 3 npm install --no-audit --no-fund ); then
            print_warning "npm install failed in frontend/ — dashboard will be unavailable"
            print_warning "  Fix manually: cd frontend && npm install && npm run build"
            return 0
        fi
        if [[ -x "$fe/node_modules/.bin/ng" ]]; then
            ng_cmd="$fe/node_modules/.bin/ng"
        else
            print_warning "npm install completed but node_modules/.bin/ng is still absent"
            return 0
        fi
    fi

    print_info "Building Angular frontend (this can take a few minutes)..."
    if ( cd "$fe" && nice -n 19 ionice -c 3 "$ng_cmd" build --configuration production ); then
        # ANTI-BLUFF (§11.4.108 SOURCE->ARTIFACT): a zero exit from the builder
        # is not proof the artifact landed where the server reads it. Assert the
        # actual file the merge service will open.
        if [[ -f "$expected_index" ]]; then
            print_success "Angular frontend built and present at download-proxy/src/ui/dist/frontend/browser/index.html"
        else
            print_warning "Angular build reported success but $expected_index is MISSING"
            print_warning "  The dashboard will still be unavailable — check frontend/angular.json outputPath"
        fi
    else
        print_warning "Angular build failed — the dashboard at :${MERGE_SERVICE_PORT:-7187} will be unavailable"
        print_warning "  Reproduce with: cd frontend && npm run build"
    fi
}

# Maintenance subcommand — restart level 1 (see CLAUDE.md "Pick the right
# restart level"). download-proxy/src/ (including merge_service/*.py) is
# bind-mounted into the qbittorrent-proxy container at
# /config/download-proxy — a source edit is already live on disk inside
# the container, but a stale __pycache__ can shadow it, so the cache MUST
# be cleared before the restart picks up the change. Requires the
# detected CLI (podman/docker) — boba-ctl has no exec/restart verb, so
# this always talks to the runtime directly, exactly like
# wait_for_container()/ensure_webui_password() already do elsewhere in
# this script.
reload_python() {
    if [[ -z "$CONTAINER_RUNTIME" ]]; then
        print_error "No container runtime (podman/docker) detected on PATH — cannot reload Python source."
        print_error "Install podman or docker, or clear __pycache__ + restart qbittorrent-proxy manually."
        exit 1
    fi

    print_info "Clearing __pycache__ inside qbittorrent-proxy (download-proxy/src/ is bind-mounted)..."
    if ! $CONTAINER_RUNTIME exec qbittorrent-proxy find /config/download-proxy -name __pycache__ -type d -exec rm -rf {} +; then
        print_error "Failed to clear __pycache__ inside qbittorrent-proxy"
        exit 1
    fi
    print_success "__pycache__ cleared"

    print_info "Restarting qbittorrent-proxy container..."
    if ! $CONTAINER_RUNTIME restart qbittorrent-proxy; then
        print_error "Failed to restart qbittorrent-proxy container"
        exit 1
    fi
    print_success "qbittorrent-proxy restarted — Python source changes under download-proxy/src/ are now live"
}

# Maintenance subcommand — restart level 2 (see CLAUDE.md "Pick the right
# restart level"). plugins/*.py is bind-mounted through ./config:/config,
# but the plugin loader reads from config/qBittorrent/nova3/engines/, so
# an edited plugins/X.py is NOT live until ./install-plugin.sh has copied
# it there — this subcommand only performs the restart step. The operator
# MUST run ./install-plugin.sh first; restarting alone will just reload
# whatever is already installed.
reload_plugins() {
    if [[ -z "$CONTAINER_RUNTIME" ]]; then
        print_error "No container runtime (podman/docker) detected on PATH — cannot reload plugins."
        print_error "Install podman or docker, or restart qbittorrent-proxy manually."
        exit 1
    fi

    print_warning "This only restarts qbittorrent-proxy — it does NOT copy plugin files."
    print_warning "Run ./install-plugin.sh FIRST so plugins/X.py lands in config/qBittorrent/nova3/engines/, THEN run this."

    print_info "Restarting qbittorrent-proxy container to pick up installed plugins..."
    if ! $CONTAINER_RUNTIME restart qbittorrent-proxy; then
        print_error "Failed to restart qbittorrent-proxy container"
        exit 1
    fi
    print_success "qbittorrent-proxy restarted"
}

# Maintenance subcommand — restart level 3 (see CLAUDE.md "Pick the right
# restart level"). Full recreate, required after docker-compose.yml,
# start-proxy.sh, env var, or base image changes. Reuses $COMPOSE_CMD —
# the same boba-ctl/podman-compose/docker-compose invocation
# start_container()/stop_container() already use — so this stays routed
# through the sanctioned orchestrator instead of a raw `compose` call.
# ---------------------------------------------------------------------------
# Ownership gate — feature 002-user-owned-downloads (FR-010, FR-010a, FR-010b,
# FR-004d).
#
# WHY IT LIVES HERE AND DELIBERATELY NOWHERE ELSE:
#   start.sh is the project's single container-orchestration entry point
#   (CLAUDE.md Hard Stop #3), and scripts/systemd/user/boba-stack.service
#   delegates to this script rather than driving containers itself. Placing the
#   gate here therefore gives BOTH start paths — `./start.sh` and
#   `systemctl --user start boba.target` — the identical guarantee BY
#   CONSTRUCTION. There is deliberately NO second copy inside the unit: two
#   copies are two things that can drift, and a systemd path that could bypass
#   the gate is exactly the contradiction FR-009 forbids.
#
# WHY FAIL-CLOSED:
#   Operator decision recorded in FR-010: starting with a warning was
#   explicitly rejected, because a missed warning silently reproduces the
#   defect this feature exists to remove. Exit 2 (the check could not run) is
#   NOT a pass either — a check that asserted nothing has proven nothing, and
#   reporting that as success is the blind-instrument failure of §11.4.201(6).
#
# WHY nice/ionice:
#   The repair may walk a large library and this host runs mission-critical
#   work (Constitution Principle XIII / §12).
#
# ORDERING:
#   Called AFTER the directory-creation stages on the normal path, because the
#   declared download root and config/ are `optional: false` — probing them
#   before they exist would refuse a healthy fresh checkout, which is the
#   false-positive refusal §11.4.201(1) forbids just as firmly as a false pass.
# ---------------------------------------------------------------------------
# THE OWNERSHIP GATE IS TWO HALVES WITH DIFFERENT QUIESCENCE REQUIREMENTS.
# They are separate functions for that reason, not for tidiness (T041 IMPORTANT-2):
#
#   precondition  READS docker-compose.yml. It needs no quiescence, and it must
#                 run FIRST so a bad compose is refused BEFORE the operator's
#                 stack is taken down rather than after (FR-010).
#
#   repair        WALKS AND CHOWNS the declared tree. A container that is still
#                 up can write a new non-operator-owned file BEHIND the walk,
#                 after which the completion marker records "complete" over a
#                 tree that is not -- and those stragglers are never repaired
#                 without a manual --force. FR-004g calls repair-vs-download
#                 concurrency out of scope "by construction"; the construction
#                 only EXISTS if the repair runs while nothing can write, which
#                 is what the --recreate ordering below guarantees (FR-004d).
#
# The worst case is precisely the migration moment this feature exists for: the
# first `--recreate` after the fix, with the OLD PUID=1000 qbittorrent still up
# and mid-download.
#
# Ordering is asserted behaviourally, not by convention:
#   tests/unit/test_start_reload_recreate.sh
#     PRECONDITION_BEFORE_DOWN / REPAIR_AFTER_DOWN / REPAIR_BEFORE_UP
# ---------------------------------------------------------------------------

# One definition shared by both halves (§11.4.251 -- not two near-identical
# copies). §11.4.24/§12: a multi-thousand-item walk must never compete with the
# operator's interactive session.
OWNERSHIP_NICE=()
ownership_set_nice_prefix() {
    OWNERSHIP_NICE=()
    if command -v nice >/dev/null 2>&1 && command -v ionice >/dev/null 2>&1; then
        OWNERSHIP_NICE=(nice -n 19 ionice -c 3)
    fi
}

run_ownership_precondition() {
    local precondition="$SCRIPT_DIR/scripts/ownership_precondition.sh"
    local rc
    ownership_set_nice_prefix

    if [[ ! -f "$precondition" ]]; then
        print_error "Ownership precondition script missing: $precondition"
        print_error "Refusing to start — FR-010 cannot be asserted without it."
        exit 1
    fi

    print_info "Ownership precondition: probing every declared location (FR-010)..."
    set +e
    "${OWNERSHIP_NICE[@]}" bash "$precondition"
    rc=$?
    set -e
    case "$rc" in
        0)
            print_success "Ownership precondition OK — every declared location produces operator-owned files"
            ;;
        1)
            print_error "Ownership precondition FAILED — refusing to start (FR-010)."
            print_error "  The offending location(s) are named in the report above (FR-010a)."
            print_error "  Remediate with: bash scripts/ownership_repair.sh"
            exit 1
            ;;
        *)
            print_error "Ownership precondition COULD NOT RUN (exit $rc) — refusing to start."
            print_error "  A check that asserted nothing is not a pass (FR-010b, §11.4.201(6))."
            exit 1
            ;;
    esac

}

run_ownership_repair() {
    local repair="$SCRIPT_DIR/scripts/ownership_repair.sh"
    local rc
    ownership_set_nice_prefix

    if [[ ! -f "$repair" ]]; then
        print_error "Ownership repair script missing: $repair"
        print_error "Refusing to start — pre-existing content cannot be brought under the operator (FR-004d)."
        exit 1
    fi

    print_info "Ownership repair: bringing any pre-existing content under the operator (FR-004d)..."
    set +e
    "${OWNERSHIP_NICE[@]}" bash "$repair"
    rc=$?
    set -e
    if [[ "$rc" -ne 0 ]]; then
        print_error "Ownership repair did not complete (exit $rc) — refusing to start."
        print_error "  Each item it could not repair is named in the report above (FR-006)."
        exit 1
    fi
    print_success "Ownership repair complete — every in-scope item is operator-owned"
}

# Cold-start / warm-start entry point: the declared locations have just been
# created and no container has been brought up yet by THIS invocation, so both
# halves run back to back. The --recreate path does NOT use this wrapper -- it
# interleaves `down` between the halves; see the dispatch below.
run_ownership_gate() {
    run_ownership_precondition
    run_ownership_repair
}

# ---------------------------------------------------------------------------
# Systemd state reconciliation notice — feature 002-user-owned-downloads
# (FR-009), US3 acceptance scenario 3.
#
# THE DEFECT THIS ADDRESSES, MEASURED 2026-08-21:
#   boba-stack.service is Type=oneshot + RemainAfterExit=yes, so systemd's
#   notion of "active" means "this unit ran start.sh once and it exited 0" —
#   NOT "the containers are up". Start the stack directly with ./start.sh and
#   systemd keeps reporting `inactive` while four containers are healthy. The
#   two paths then disagree about what is running, and nothing says so.
#
#   systemd cannot be made to report a stack it did not start as active, so the
#   disagreement is not removed by hiding it — it is removed by making the
#   containers the single source of truth and refusing to leave the divergence
#   SILENT. This prints the real state, the systemd state, and the one command
#   that reconciles them.
#
#   No-op when start.sh is itself being run BY boba-stack.service — in that case
#   the two already agree and a notice would be noise. The signal is the unit's
#   own `Environment=BOBA_STARTED_BY=boba-stack.service`, NOT systemd's
#   INVOCATION_ID: INVOCATION_ID is inherited by anything spawned under ANY
#   unit, including the operator's own terminal session, so it answers "is some
#   systemd unit an ancestor of me" rather than "did boba-stack.service start
#   me". Measured on this host 2026-08-21: an interactive shell already carried
#   INVOCATION_ID, so the first version of this guard silenced the notice on the
#   direct ./start.sh path — the very path it exists to report on. That is the
#   §11.4.201(7) failure of asserting a proxy instead of the real condition, and
#   it is why the marker is set explicitly by the unit.
report_systemd_state() {
    [[ "${BOBA_STARTED_BY:-}" != "boba-stack.service" ]] || return 0
    command -v systemctl >/dev/null 2>&1 || return 0
    systemctl --user list-unit-files boba-stack.service >/dev/null 2>&1 || return 0

    local unit_state
    unit_state="$(systemctl --user is-active boba-stack.service 2>/dev/null || true)"
    [[ -n "$unit_state" ]] || return 0

    if [[ "$unit_state" == "active" ]]; then
        print_info "systemd: boba-stack.service is active — the session-scoped path agrees with the running stack (FR-009)."
        return 0
    fi

    print_warning "systemd state DIVERGES from the running stack (FR-009):"
    print_warning "  reality  : the stack was just started by ./start.sh and its containers are up"
    print_warning "  systemd  : boba-stack.service = $unit_state"
    print_warning "  The containers are the source of truth. systemd cannot observe a stack it did"
    print_warning "  not start, so this is reported rather than hidden."
    print_warning "  Reconcile with:  bash scripts/boba-svc.sh up      (re-runs this same start.sh)"
}

# down and up are SEPARATE so the ownership repair can run BETWEEN them, in the
# one window where no container can write to the declared tree (FR-004d). The
# print/warn/error lines are kept verbatim: the recreate suite's paired §1.1
# mutations anchor on them, and reconciling a fix must not silently disarm the
# mutations that prove the gate has teeth (§11.4.120).
stack_down() {
    print_info "Recreating the full stack ($COMPOSE_CMD down && $COMPOSE_CMD up -d)..."

    if ! $COMPOSE_CMD down; then
        print_warning "Stack may not have been running — continuing to bring it up"
    fi
}

stack_up() {
    if ! $COMPOSE_CMD up -d; then
        print_error "Failed to bring the stack back up"
        exit 1
    fi

    print_success "Stack recreated successfully"
}

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Start qBitTorrent container using Podman or Docker (auto-detected).

OPTIONS:
    -h, --help          Show this help message
    -p, --pull          Pull latest image before starting
    -v, --verbose       Enable verbose output
    -s, --status        Show container status only
    --no-plugins        Skip plugin installation
    --no-build          Skip Angular frontend build
    --no-boba-ctl       Use raw podman-compose/docker compose instead of boba-ctl CLI
    --reload-python     Clear __pycache__ + restart qbittorrent-proxy (download-proxy/src/ edits)
    --reload-plugins    Restart qbittorrent-proxy to pick up plugins (run ./install-plugin.sh FIRST)
    --recreate          Full recreate: compose down && compose up -d (compose/env/base-image changes)

EXAMPLES:
    $(basename "$0")                  Start container (default: boba-ctl)
    $(basename "$0") -p               Pull latest image and start
    $(basename "$0") --verbose        Start with verbose output
    $(basename "$0") --no-boba-ctl    Start using raw compose
    $(basename "$0") --reload-python  Reload edited download-proxy/src/ Python source
    $(basename "$0") --reload-plugins Reload after ./install-plugin.sh copied plugins/*.py
    $(basename "$0") --recreate       Full recreate after compose/env/base-image changes

EOF
    exit 0
}

main() {
    local pull_image_flag=false
    local verbose=false
    local status_only=false
    local install_plugins=true
    local build_frontend_flag=true
    local reload_python_flag=false
    local reload_plugins_flag=false
    local recreate_flag=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                ;;
            -p|--pull)
                pull_image_flag=true
                shift
                ;;
            -v|--verbose)
                verbose=true
                shift
                ;;
            -s|--status)
                status_only=true
                shift
                ;;
            --no-plugins)
                install_plugins=false
                shift
                ;;
            --no-build)
                build_frontend_flag=false
                shift
                ;;
            --no-boba-ctl)
                BOBA_CTL_MODE=false
                shift
                ;;
            --reload-python)
                reload_python_flag=true
                shift
                ;;
            --reload-plugins)
                reload_plugins_flag=true
                shift
                ;;
            --recreate)
                recreate_flag=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                ;;
        esac
    done

    if [[ "$verbose" == true ]]; then
        set -x
    fi

    # Cookie autoload (operator mandate 2026-08-15): refresh per-tracker
    # cookies from ${TRACKER_COOKIE_DIR:-$HOME/Downloads}/cookies_<tracker>.txt
    # into .env BEFORE load_environment so freshly-exported browser cookies
    # propagate to containers on the next `compose up`. Loader failure never
    # blocks the boot (§11.4.234 always-unblocked) — a warning surfaces and
    # start.sh continues with whatever cookies .env already holds.
    if [[ -x "$SCRIPT_DIR/scripts/load-tracker-cookies.sh" ]]; then
        print_info "Refreshing per-tracker cookies from \${TRACKER_COOKIE_DIR:-\$HOME/Downloads}..."
        bash "$SCRIPT_DIR/scripts/load-tracker-cookies.sh" || \
            print_warning "cookie loader had non-zero exit — continuing with existing .env"
    fi

    load_environment
    ensure_boba_master_key
    detect_container_runtime
    check_prerequisites

    if [[ "$status_only" == true ]]; then
        $COMPOSE_CMD ps
        exit 0
    fi

    if [[ "$reload_python_flag" == true ]]; then
        reload_python
        exit 0
    fi

    if [[ "$reload_plugins_flag" == true ]]; then
        reload_plugins
        exit 0
    fi

    if [[ "$recreate_flag" == true ]]; then
        run_ownership_precondition
        stack_down
        run_ownership_repair
        stack_up
        harden_config_permissions
        assert_credential_store_mode
        report_systemd_state
        exit 0
    fi

    create_directories
    cleanup_stale_config
    update_qbittorrent_config
    create_data_directories

    # Ownership gate runs here — after the declared locations exist, and before
    # THIS invocation brings anything up (FR-010 / FR-004d).
    #
    # HONEST BOUNDARY (§11.4.6), do not read more into this than it says: the
    # claim above is about what THIS invocation starts. If the operator runs a
    # warm `./start.sh` over an ALREADY-RUNNING stack, containers are writing
    # while the repair walks, and the FR-004d window the --recreate path closes
    # by interleaving `down` is NOT closed here.
    #
    # Bounded in practice, not by luck: after any successful pass the completion
    # marker is valid for the scope fingerprint and the repair short-circuits
    # without walking at all (scripts/ownership_repair.sh marker_is_valid), so
    # the window needs a STALE-or-absent marker AND a live stack together. That
    # is a real combination — a newly declared scope entry re-arms the marker —
    # so it is tracked, not dismissed.
    run_ownership_gate

    if [[ "$build_frontend_flag" == true ]]; then
        build_frontend
    fi

    if [[ "$install_plugins" == true ]]; then
        copy_plugins
    fi

    if [[ "$pull_image_flag" == true ]]; then
        pull_image
    fi

    start_container
    wait_for_jackett
    local jackett_key
    jackett_key=$(extract_jackett_key)
    if [[ -n "$jackett_key" ]]; then
        update_env_jackett_key "$jackett_key"
    fi
    wait_for_container
    ensure_webui_password
    ensure_macos_tunnel
    assert_credential_store_mode
    show_status
    report_systemd_state
}

# On macOS, podman runs containers in a Linux VM and `network_mode: host`
# does NOT forward ports to the macOS host. Bridge them via the SSH tunnel
# helper. Best-effort: never fail the whole start if the tunnel can't come
# up (e.g. podman machine not running) — the operator can run the script
# manually. No-op on Linux. (CONTINUATION known-issue #1.)
ensure_macos_tunnel() {
    [[ "$(uname -s)" == "Darwin" ]] || return 0
    local tunnel_script="$SCRIPT_DIR/scripts/ensure-macos-tunnel.sh"
    [[ -x "$tunnel_script" ]] || return 0
    print_info "macOS detected — bridging container ports via SSH tunnel..."
    if "$tunnel_script"; then
        print_success "macOS port tunnel ready"
    else
        print_warning "macOS port tunnel could not be established — run '$tunnel_script' manually"
    fi
}

# Only run main when executed directly — allows hermetic sourcing for tests.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
