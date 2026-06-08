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

detect_container_runtime() {
    if command -v podman &> /dev/null; then
        CONTAINER_RUNTIME="podman"
        if command -v podman-compose &> /dev/null; then
            COMPOSE_CMD="podman-compose"
        else
            print_error "podman-compose not found"
            exit 1
        fi
    elif command -v docker &> /dev/null; then
        CONTAINER_RUNTIME="docker"
        if docker compose version &> /dev/null; then
            COMPOSE_CMD="docker compose"
        elif command -v docker-compose &> /dev/null; then
            COMPOSE_CMD="docker-compose"
        else
            print_error "Docker Compose not found"
            exit 1
        fi
    else
        if [[ "$BOBA_CTL_MODE" == false ]]; then
            print_error "Neither Podman nor Docker found"
            exit 1
        fi
        CONTAINER_RUNTIME=""
    fi

    if [[ "$BOBA_CTL_MODE" == true ]]; then
        COMPOSE_CMD="$SCRIPT_DIR/scripts/boba-ctl.sh"
        print_info "Using boba-ctl for container orchestration"
    else
        print_info "Using $CONTAINER_RUNTIME"
    fi
}

stop_container() {
    print_info "Stopping qBitTorrent container..."
    
    if $COMPOSE_CMD down; then
        print_success "Container stopped successfully"
    else
        print_warning "Container may not have been running"
    fi
}

remove_container() {
    print_info "Removing container..."

    if [[ "$BOBA_CTL_MODE" == true ]]; then
        $COMPOSE_CMD down
        print_info "Image removal not available in boba-ctl mode"
        print_success "Container stopped"
        return 0
    fi

    if $COMPOSE_CMD down --rmi local 2>/dev/null; then
        print_success "Container removed"
    else
        $COMPOSE_CMD down
        print_success "Container stopped and removed"
    fi
}

show_status() {
    echo ""
    print_info "Remaining containers:"
    $COMPOSE_CMD ps
}

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Stop qBitTorrent container.

OPTIONS:
    -h, --help      Show this help message
    -v, --verbose   Enable verbose output
    -r, --remove    Remove container after stopping
    -p, --purge     Remove container and local images
    --no-boba-ctl   Use raw podman-compose/docker compose instead of boba-ctl CLI

EXAMPLES:
    $(basename "$0")                  Stop container (default: boba-ctl)
    $(basename "$0") -r               Stop and remove container
    $(basename "$0") --purge          Stop, remove container and images
    $(basename "$0") --no-boba-ctl    Stop using raw compose

EOF
    exit 0
}

main() {
    local verbose=false
    local remove_flag=false
    local purge_flag=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                ;;
            -v|--verbose)
                verbose=true
                shift
                ;;
            -r|--remove)
                remove_flag=true
                shift
                ;;
            -p|--purge)
                purge_flag=true
                shift
                ;;
            --no-boba-ctl)
                BOBA_CTL_MODE=false
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

    detect_container_runtime

    if [[ "$purge_flag" == true ]]; then
        remove_container
        if [[ "$BOBA_CTL_MODE" == false ]]; then
            print_info "Removing local images..."
            $COMPOSE_CMD down --rmi local 2>/dev/null || true
        fi
        print_success "Cleanup complete"
    elif [[ "$remove_flag" == true ]]; then
        remove_container
    else
        stop_container
    fi

    show_status
}

main "$@"
