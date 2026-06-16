#!/bin/bash
# Install search plugins for qBittorrent
# This script ensures all plugins are properly installed and recognized

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

# List of all supported plugins (official + Russian trackers)
PLUGINS=(
  "academictorrents"
  "ali213"
  "anilibra"
  "audiobookbay"
  "bitru"
  "bt4g"
  "btsow"
  "bitsearch"
  "extratorrent"
  "eztv"
  "gamestorrents"
  "glotorrents"
  "iptorrents"
  "jackett"
  "kickass"
  "kinozal"
  "limetorrents"
  "linuxtracker"
  "megapeer"
  "nnmclub"
  "nyaa"
  "one337x"
  "pctorrent"
  "piratebay"
  "pirateiro"
  "rockbox"
  "rutor"
  "rutracker"
  "snowfl"
  "solidtorrents"
  "therarbg"
  "tokyotoshokan"
  "torlock"
  "torrentdownload"
  "torrentfunk"
  "torrentgalaxy"
  "torrentkitty"
  "torrentproject"
  "torrentscsv"
  "xfsub"
  "yihua"
  "yourbittorrent"
  "yts"
)
LOCAL_MODE=false
INSTALL_ALL=false
SELECTED_PLUGINS=()
VERIFY_MODE=false
TEST_MODE=false

usage() {
    cat << EOF
Usage: $0 [OPTIONS] [PLUGIN...]

Install search plugins for qBittorrent.

OPTIONS:
    --local, -l       Install for local qBittorrent (not container)
    --all, -a         Install all available plugins
    --verify          Verify plugin installation
    --test            Test plugin functionality
    --help, -h        Show this help message

Available plugins: ${PLUGINS[*]}

Examples:
    $0 rutracker                    # Install RuTracker plugin
    $0 --all                        # Install all plugins
    $0 --local rutracker rutor      # Install locally
    $0 --verify                     # Verify installation
    $0 --test                       # Test all plugins

EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --local|-l)
            LOCAL_MODE=true
            shift
            ;;
        --all|-a)
            INSTALL_ALL=true
            shift
            ;;
        --verify)
            VERIFY_MODE=true
            shift
            ;;
        --test)
            TEST_MODE=true
            shift
            ;;
        --help|-h)
            usage
            ;;
        -*)
            print_error "Unknown option: $1"
            usage
            ;;
        *)
            SELECTED_PLUGINS+=("$1")
            shift
            ;;
    esac
done

# Determine target directories
if [[ "$LOCAL_MODE" == "true" ]]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        ENGINES_DIR="$HOME/Library/Application Support/qBittorrent/nova3/engines"
    else
        ENGINES_DIR="$HOME/.local/share/qBittorrent/nova3/engines"
    fi
else
    ENGINES_DIR="$SCRIPT_DIR/config/qBittorrent/nova3/engines"
fi

verify_installation() {
    print_info "Verifying plugin installation..."
    
    local all_ok=true
    
    for plugin in "${PLUGINS[@]}"; do
        local plugin_file="$ENGINES_DIR/${plugin}.py"
        if [[ -f "$plugin_file" ]]; then
            print_success "$plugin: Installed"
            
            # Check file permissions
            local perms size
            perms=$(stat -c "%a" "$plugin_file" 2>/dev/null || stat -f "%A" "$plugin_file" 2>/dev/null)
            if [[ -n "$perms" ]]; then
                print_info "  Permissions: $perms"
            fi

            # Check file size
            size=$(stat -c "%s" "$plugin_file" 2>/dev/null || stat -f "%z" "$plugin_file" 2>/dev/null)
            if [[ $size -gt 0 ]]; then
                print_info "  Size: $size bytes"
            fi
            
            # Validate Python syntax. Use compile() (in-memory) NOT
            # `py_compile`: py_compile writes a __pycache__/.pyc next to the
            # source, which fails with "Permission denied" when the engines dir
            # is owned by the qBittorrent container user (PUID) on a remote host
            # — turning a VALID plugin into a false "Syntax: Invalid", returning
            # 1, and (under deploy-remote's set -e) aborting the whole deploy
            # before the containers come up (§11.4.1 FAIL-bluff + §11.4.108).
            if python3 -c "import sys; compile(open(sys.argv[1]).read(), sys.argv[1], 'exec')" "$plugin_file" 2>/dev/null; then
                print_success "  Syntax: Valid"
            else
                print_error "  Syntax: Invalid"
                all_ok=false
            fi
        else
            print_error "$plugin: Not installed"
            all_ok=false
        fi
    done
    
    if [[ "$all_ok" == "true" ]]; then
        print_success "\nAll plugins installed and valid!"
        return 0
    else
        print_error "\nSome plugins are missing or invalid"
        return 1
    fi
}

test_plugins() {
    print_info "Testing plugin functionality..."
    
    for plugin in "${PLUGINS[@]}"; do
        local plugin_file="$ENGINES_DIR/${plugin}.py"
        if [[ ! -f "$plugin_file" ]]; then
            print_warning "$plugin: Not installed, skipping test"
            continue
        fi
        
        print_info "Testing $plugin..."
        
        # Test Python import
        if python3 -c "import sys; sys.path.insert(0, '$ENGINES_DIR'); from ${plugin} import ${plugin^}; print('Import OK')" 2>/dev/null; then
            print_success "  Import: OK"
        else
            print_error "  Import: Failed"
            continue
        fi
        
        # Check if plugin class exists
        if python3 -c "import sys; sys.path.insert(0, '$ENGINES_DIR'); from ${plugin} import ${plugin^}; c=${plugin^}(); print('Class OK')" 2>/dev/null; then
            print_success "  Class: OK"
        else
            print_error "  Class: Failed"
        fi
    done
}

# Run verification if requested
if [[ "$VERIFY_MODE" == "true" ]]; then
    verify_installation
    exit $?
fi

# Run tests if requested
if [[ "$TEST_MODE" == "true" ]]; then
    test_plugins
    exit 0
fi

# Check if plugins were specified
if [[ "${#SELECTED_PLUGINS[@]}" -eq 0 ]] && [[ "$INSTALL_ALL" == "false" ]]; then
    print_info "No plugins specified. Use --all to install all plugins or specify plugin names."
    print_info "Available plugins: ${PLUGINS[*]}"
    exit 1
fi

# Use all plugins if --all flag is set
if [[ "$INSTALL_ALL" == "true" ]]; then
    SELECTED_PLUGINS=("${PLUGINS[@]}")
fi

# Validate plugin names
for plugin in "${SELECTED_PLUGINS[@]}"; do
    if [[ ! " ${PLUGINS[*]} " =~ \ ${plugin}\  ]]; then
        print_error "Unknown plugin: $plugin"
        print_info "Available plugins: ${PLUGINS[*]}"
        exit 1
    fi
done

# Create engines directory
mkdir -p "$ENGINES_DIR"
print_info "Installing to: $ENGINES_DIR"

# Install each plugin
for plugin in "${SELECTED_PLUGINS[@]}"; do
    plugin_file="plugins/${plugin}.py"
    plugin_icon="plugins/${plugin}.png"
    
    if [[ ! -f "$plugin_file" ]]; then
        plugin_file="plugins/community/${plugin}.py"
        plugin_icon="plugins/community/${plugin}.png"
        if [[ ! -f "$plugin_file" ]]; then
            print_error "Plugin file not found: plugins/${plugin}.py or plugins/community/${plugin}.py"
            continue
        fi
    fi
    
    print_info "Installing ${plugin}..."

    # Copy plugin file to the host engines dir. This is BEST-EFFORT: when the
    # qBittorrent container owns the bind-mounted config/ (e.g. a remote host
    # where PUID-owned config is not writable by the SSH user), this host cp
    # fails with "Permission denied". Under `set -e` that previously KILLED the
    # whole script before the authoritative "Install to running container" block
    # below — so a remote deploy silently installed zero plugins. Make it
    # non-fatal: warn and fall through to the container-cp path.
    if ! cp "$plugin_file" "$ENGINES_DIR/" 2>/dev/null; then
        print_warning "host copy to $ENGINES_DIR failed (container-owned?) — will install via the running container if present"
    else
        chmod 644 "$ENGINES_DIR/$(basename "$plugin_file")" 2>/dev/null || true
    fi

    # Copy icon if exists (best-effort)
    if [[ -f "$plugin_icon" ]]; then
        cp "$plugin_icon" "$ENGINES_DIR/" 2>/dev/null && \
            chmod 644 "$ENGINES_DIR/$(basename "$plugin_icon")" 2>/dev/null || true
    fi

    # Copy JSON config if exists (e.g. jackett.json, kinozal.json) (best-effort)
    plugin_json="plugins/${plugin}.json"
    if [[ ! -f "$plugin_json" ]]; then
        plugin_json="plugins/community/${plugin}.json"
    fi
    if [[ -f "$plugin_json" ]]; then
        if cp "$plugin_json" "$ENGINES_DIR/" 2>/dev/null; then
            chmod 644 "$ENGINES_DIR/$(basename "$plugin_json")" 2>/dev/null || true
            print_info "  Config: $(basename "$plugin_json") copied"
        fi
    fi

    print_success "${plugin} staged"
done

# Install to running container if applicable
if [[ "$LOCAL_MODE" == "false" ]]; then
    CONTAINER_NAME="qbittorrent"
    
    # Check for podman
    if command -v podman &> /dev/null; then
        if podman ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
            print_info "Installing to running Podman container..."
            
            # Create directory in container
            podman exec "$CONTAINER_NAME" mkdir -p /config/qBittorrent/nova3/engines 2>/dev/null || true
            
            # Copy all plugins
            for plugin in "${SELECTED_PLUGINS[@]}"; do
                plugin_file="plugins/${plugin}.py"
                plugin_icon="plugins/${plugin}.png"
                
                podman cp "$plugin_file" "${CONTAINER_NAME}:/config/qBittorrent/nova3/engines/" 2>/dev/null || {
                    print_error "Failed to copy ${plugin} to container"
                    continue
                }
                
                if [[ -f "$plugin_icon" ]]; then
                    podman cp "$plugin_icon" "${CONTAINER_NAME}:/config/qBittorrent/nova3/engines/" 2>/dev/null || true
                fi
                
                # Fix permissions in container
                podman exec "$CONTAINER_NAME" chmod 644 "/config/qBittorrent/nova3/engines/${plugin}.py" 2>/dev/null || true
                
                print_success "${plugin} copied to container"
            done
            
            # Restart nova3 service or container to reload plugins
            print_info "Restarting qBittorrent to load new plugins..."
            podman restart "$CONTAINER_NAME" 2>/dev/null || true
            sleep 2
        else
            print_warning "Container '$CONTAINER_NAME' not running. Plugins will be available after next start."
        fi
    fi
    
    # Check for docker
    if command -v docker &> /dev/null; then
        if docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
            print_info "Installing to running Docker container..."
            
            # Create directory in container
            docker exec "$CONTAINER_NAME" mkdir -p /config/qBittorrent/nova3/engines 2>/dev/null || true
            
            # Copy all plugins
            for plugin in "${SELECTED_PLUGINS[@]}"; do
                plugin_file="plugins/${plugin}.py"
                plugin_icon="plugins/${plugin}.png"
                
                docker cp "$plugin_file" "${CONTAINER_NAME}:/config/qBittorrent/nova3/engines/" 2>/dev/null || {
                    print_error "Failed to copy ${plugin} to container"
                    continue
                }
                
                if [[ -f "$plugin_icon" ]]; then
                    docker cp "$plugin_icon" "${CONTAINER_NAME}:/config/qBittorrent/nova3/engines/" 2>/dev/null || true
                fi
                
                # Fix permissions in container
                docker exec "$CONTAINER_NAME" chmod 644 "/config/qBittorrent/nova3/engines/${plugin}.py" 2>/dev/null || true
                
                print_success "${plugin} copied to container"
            done
            
            # Restart container to reload plugins
            print_info "Restarting qBittorrent to load new plugins..."
            docker restart "$CONTAINER_NAME" 2>/dev/null || true
            sleep 2
        else
            print_warning "Container '$CONTAINER_NAME' not running. Plugins will be available after next start."
        fi
    fi
fi

# Verify installation
print_info "Verifying installation..."
verify_installation

print_success "Plugin installation complete!"

if [[ "$LOCAL_MODE" == "false" ]]; then
    print_info ""
    print_info "NOTE: If using WebUI, plugins may require a browser refresh."
    print_info "Search plugins should now be visible in: Search > Search Plugins"
fi
