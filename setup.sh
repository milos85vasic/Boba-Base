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
print_info "Step 1/5: Checking prerequisites..."

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
print_info "Step 2/5: Setting up environment..."

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
print_info "Step 3/5: Creating directories..."

mkdir -p config/qBittorrent/nova3/engines
mkdir -p config/qBittorrent/config
mkdir -p downloads/Incomplete
mkdir -p downloads/Torrents/All
mkdir -p downloads/Torrents/Completed

print_success "Directories created"

# Step 4: Install plugins
print_info "Step 4/5: Installing search plugins..."

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
print_info "Step 5/5: Starting qBittorrent container..."

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
