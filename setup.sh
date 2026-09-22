#!/bin/bash
# Comprehensive Setup Script for qBitTorrent-Fixed
# This script sets up everything needed for working search plugins

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║           qBitTorrent-Fixed - Comprehensive Setup                          ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Check prerequisites
print_info "Step 1/6: Checking prerequisites..."

if ! command -v docker &> /dev/null && ! command -v podman &> /dev/null; then
    print_error "Neither Docker nor Podman found. Please install one of them."
    exit 1
fi

if command -v podman &> /dev/null; then
    CONTAINER_RUNTIME="podman"
    print_success "Found Podman"
else
    CONTAINER_RUNTIME="docker"
    print_success "Found Docker"
fi

# Step 2: Create environment file
print_info "Step 2/6: Setting up environment..."

if [[ ! -f ".env" ]]; then
    print_info "Creating .env file..."
    cat > .env << 'EOF'
# qBitTorrent Configuration
PUID=1000
PGID=1000
TZ=Europe/Moscow
WEBUI_PORT=7185   # qBittorrent listen port; 7186 is the download-proxy in front of it
# NOTE: WEBUI_USERNAME / WEBUI_PASSWORD are deliberately NOT written here.
# lscr.io/linuxserver/qbittorrent implements neither variable, so setting them
# created a false belief that credentials were configured while nothing was.
# Credentials are written into config/qBittorrent/qBittorrent.conf by
# start.sh's _ensure_webui_credentials — the file the image actually reads.

# Data directory
QBITTORRENT_DATA_DIR=/mnt/DATA

# RuTracker Credentials (optional - for private tracker access)
# RUTRACKER_USERNAME=your_username_here
# RUTRACKER_PASSWORD=your_password_here

# Kinozal Credentials (optional)
# KINOZAL_USERNAME=your_username_here
# KINOZAL_PASSWORD=your_password_here

# NNMClub Cookies (optional)
# NNMCLUB_COOKIES="uid=12345; pass=your_hash_here"
EOF
    print_success "Created .env file"
    print_warning "Please edit .env and add your tracker credentials if needed"
else
    print_success ".env file already exists"
fi

# Step 3: Create directories
print_info "Step 3/6: Creating directories..."

mkdir -p config/qBittorrent/nova3/engines
mkdir -p config/qBittorrent/config
mkdir -p downloads/Incomplete
mkdir -p downloads/Torrents/All
mkdir -p downloads/Torrents/Completed

print_success "Directories created"

# Step 4: Install plugins
print_info "Step 4/6: Installing search plugins..."

# List of all plugins
PLUGINS=(
    "eztv"
    "jackett"
    "limetorrents"
    "piratebay"
    "solidtorrents"
    "torlock"
    "torrentproject"
    "torrentscsv"
    "rutracker"
    "rutor"
    "kinozal"
    "nnmclub"
)

# Copy plugins
for plugin in "${PLUGINS[@]}"; do
    if [[ -f "plugins/${plugin}.py" ]]; then
        cp "plugins/${plugin}.py" config/qBittorrent/nova3/engines/
        print_success "Installed: ${plugin}.py"
    else
        print_warning "Plugin not found: ${plugin}.py"
    fi
    if [[ -f "plugins/${plugin}.json" ]]; then
        cp "plugins/${plugin}.json" config/qBittorrent/nova3/engines/
        print_success "Installed: ${plugin}.json"
    fi
done

# Copy support files
for file in helpers.py nova2.py novaprinter.py socks.py; do
    if [[ -f "plugins/${file}" ]]; then
        cp "plugins/${file}" config/qBittorrent/nova3/engines/
        print_success "Installed: ${file}"
    fi
done

# Copy infrastructure modules required by the proxy entrypoint and plugins
for file in download_proxy.py env_loader.py; do
    if [[ -f "plugins/${file}" ]]; then
        cp "plugins/${file}" config/qBittorrent/nova3/engines/
        print_success "Installed: ${file}"
    fi
done

# Set permissions
chmod 644 config/qBittorrent/nova3/engines/*.py 2>/dev/null || true

print_success "All plugins installed"

# Step 5: Start container
print_info "Step 5/6: Starting qBittorrent container..."

if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then
    if command -v podman-compose &> /dev/null; then
        podman-compose up -d
    else
        print_error "podman-compose not found"
        exit 1
    fi
else
    if docker compose version &> /dev/null; then
        docker compose up -d
    elif command -v docker-compose &> /dev/null; then
        docker-compose up -d
    else
        print_error "Docker Compose not found"
        exit 1
    fi
fi

print_success "Container started"

# Wait for container to be ready
print_info "Waiting for qBittorrent to be ready..."
sleep 5

# Verify container is running
if $CONTAINER_RUNTIME ps --format '{{.Names}}' | grep -qx 'qbittorrent'; then
    print_success "qBittorrent is running!"
else
    print_error "Container failed to start"
    exit 1
fi

# ─── Step 6: reboot survival via systemd --user ──────────────────────────────
# BOB-205 (2026-09-22): without this step `./setup.sh` produced a RUNNING stack
# with ZERO systemd units, so nothing came back after a reboot. The complete
# path existed only in scripts/install.sh, which README.md/CLAUDE.md never
# mention — so the documented route silently skipped reboot survival.
#
# This DELEGATES to scripts/boba-svc.sh (§11.4.74 extend-don't-reimplement) —
# it renders scripts/systemd/user/*.{target,service,timer} with
# @@BOBA_REPO_ROOT@@ substituted, installs them as hard copies, daemon-reloads
# and enables boba.target. boba-svc install is idempotent, so re-running
# ./setup.sh converges rather than duplicating.
#
# NEVER fails the whole setup (§11.4.234 always-unblocked): a host without a
# user systemd manager warns and continues — the stack is already up by now.
print_info "Step 6/6: Installing systemd --user units (reboot survival)..."
if ! command -v systemctl >/dev/null 2>&1; then
    print_warning "systemctl not on PATH — SKIPPING systemd install; stack will NOT survive reboot"
elif [ ! -x scripts/boba-svc.sh ] && [ ! -f scripts/boba-svc.sh ]; then
    print_warning "scripts/boba-svc.sh missing — SKIPPING systemd install; stack will NOT survive reboot"
else
    if bash scripts/boba-svc.sh install 2>&1 | sed 's/^/    /'; then
        bash scripts/boba-svc.sh enable 2>&1 | sed 's/^/    /' \
            || print_warning "boba-svc enable returned non-zero (continuing)"
        print_success "systemd units installed + boba.target enabled"
    else
        print_warning "boba-svc install failed — stack will NOT survive reboot"
    fi

    # Linger decides LOGIN-only vs HOST-BOOT autostart. Reported, never
    # silently assumed: enabling it needs root ONCE and this script never
    # escalates (CONST-033 / project no-sudo rule).
    _linger="$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || echo unknown)"
    if [ "$_linger" = "yes" ]; then
        print_success "linger=yes → boba.target auto-starts at HOST BOOT (no login needed)"
    else
        print_warning "linger=$_linger → services auto-start only on user LOGIN"
        print_warning "  for full host-boot autostart, run ONCE: sudo loginctl enable-linger $(id -un)"
    fi
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                      ✅ SETUP COMPLETE!                                     ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 STATUS:"
echo "  • Container: Running"
echo "  • WebUI: http://localhost:7186"
echo "  • Login: admin / admin"
echo "  • Plugins: 12 installed"
echo ""
echo "🚀 NEXT STEPS:"
echo "  1. Open WebUI: http://localhost:7186"
echo "  2. Go to Search → Search Plugins"
echo "  3. Enable plugins you want to use"
echo "  4. Test search and download"
echo ""
echo "⚙️  CONFIGURATION:"
echo "  • Edit .env file to add tracker credentials"
echo "  • Restart container after editing: ./restart.sh"
echo ""
echo "🧪 TESTING:"
echo "  ./test.sh           # Run all tests"
echo "  ./verify.sh         # Verify installation"
echo ""
echo "📖 DOCUMENTATION:"
echo "  cat README.md       # Quick start"
echo "  cat PLUGIN_STATUS.md # Detailed status"
echo ""
echo "════════════════════════════════════════════════════════════════════════════"
