#!/usr/bin/env bash
# scripts/build-releases.sh — non-interactive release builder.
#
# Produces artefacts under releases/<version>/<app>/<channel>/ along
# with SHA256SUMS + BUILD_INFO.json. See releases/README.md for layout.
#
# Strictly non-interactive: never prompts, never escalates privileges,
# never reads from stdin. Missing toolchains cause a WARN + skip of
# that target; at least one successful build is required for exit 0.

set -euo pipefail

# ---------------------------------------------------------------------------
# Runtime detection (constitution IV)
# ---------------------------------------------------------------------------
detect_container_runtime() {
    if command -v podman >/dev/null 2>&1; then
        CONTAINER_RUNTIME="podman"
    elif command -v docker >/dev/null 2>&1; then
        CONTAINER_RUNTIME="docker"
    else
        CONTAINER_RUNTIME=""
    fi
}

print_info()    { printf '\033[0;34m[INFO]\033[0m %s\n' "$*"; }
print_success() { printf '\033[0;32m[ OK ]\033[0m %s\n' "$*"; }
print_warning() { printf '\033[0;33m[WARN]\033[0m %s\n' "$*"; }
print_error()   { printf '\033[0;31m[FAIL]\033[0m %s\n' "$*" >&2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Read project.version from pyproject.toml. tomllib is stdlib only on Python
# >= 3.11; on an older host python3 (e.g. 3.9) fall back to a grep so the
# distribution build is never blocked by the host interpreter version.
VERSION="$(python3 -c 'import tomllib, pathlib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])' 2>/dev/null \
  || grep -m1 -E '^version *= *' pyproject.toml | sed -E 's/^version *= *"?([^"]+)"?.*/\1/')"
COMMIT_SHA="$(git rev-parse --short=12 HEAD)"
FULL_SHA="$(git rev-parse HEAD)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
BUILT_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BUILDER="$(hostname)"
OUT_ROOT="releases/$VERSION"

usage() {
    cat <<'USAGE'
Usage:
  ./scripts/build-releases.sh [TARGETS...] [--channel debug|release|all]

Targets (space-separated, omit for all):
  frontend         Angular dashboard builds (debug + release)
  extension        BobaLink browser extension (WXT) zips — Chrome + Firefox (debug + release)
  download-proxy   Python source tarball (+ container image if podman/docker present)
  plugins          Canonical 12 nova3 plugins tarball
  docs-site        `mkdocs build` output tarball (requires mkdocs installed)

Flags:
  --channel  debug, release, or all (default)
  --help, -h
USAGE
}

CHANNELS="all"
declare -a TARGETS=()
while (( $# )); do
    case "$1" in
        --channel) CHANNELS="$2"; shift 2 ;;
        --channel=*) CHANNELS="${1#*=}"; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) print_error "unknown flag: $1"; usage; exit 2 ;;
        *) TARGETS+=("$1"); shift ;;
    esac
done

if (( ${#TARGETS[@]} == 0 )); then
    TARGETS=(frontend extension download-proxy plugins docs-site)
fi

detect_container_runtime
mkdir -p "$OUT_ROOT"

builds_done=0
builds_skipped=0

write_build_info() {
    local dest="$1" artifact="$2" channel="$3" extra="${4:-}"
    cat > "$dest/BUILD_INFO.json" <<JSON
{
  "artifact": "$artifact",
  "channel": "$channel",
  "commit": "$FULL_SHA",
  "short_commit": "$COMMIT_SHA",
  "branch": "$BRANCH",
  "built_at": "$BUILT_AT",
  "builder": "$BUILDER",
  "version": "$VERSION"$extra
}
JSON
}

build_frontend() {
    if [[ ! -d frontend ]] || [[ ! -f frontend/package.json ]]; then
        print_warning "frontend/ not found — skipping"
        builds_skipped=$((builds_skipped + 1)); return 0
    fi
    if ! command -v npx >/dev/null 2>&1; then
        print_warning "npx not on PATH — skipping frontend"
        builds_skipped=$((builds_skipped + 1)); return 0
    fi

    local channels=()
    case "$CHANNELS" in
        all) channels=(debug release) ;;
        debug) channels=(debug) ;;
        release) channels=(release) ;;
        *) print_error "unknown channel: $CHANNELS"; exit 2 ;;
    esac

    (
        cd frontend
        if [[ ! -d node_modules ]]; then
            print_info "installing frontend deps (npm ci)"
            npm ci --no-audit --no-fund --no-progress
        fi

        for channel in "${channels[@]}"; do
            local dest="$REPO_ROOT/$OUT_ROOT/frontend/$channel"
            mkdir -p "$dest"
            print_info "building frontend ($channel)"
            local ng_cfg
            case "$channel" in
                debug)   ng_cfg="development" ;;
                release) ng_cfg="production" ;;
            esac
            local tmpdir
            tmpdir="$(mktemp -d)"
            npx ng build --configuration "$ng_cfg" --output-path "$tmpdir" \
                >"$dest/build.log" 2>&1 || {
                    print_error "ng build --configuration $ng_cfg failed; see $dest/build.log"
                    return 1
                }
            local archive="frontend-${COMMIT_SHA}.tar.gz"
            tar -C "$tmpdir" -czf "$dest/$archive" .
            (cd "$dest" && sha256sum "$archive" > SHA256SUMS)
            write_build_info "$dest" "$archive" "$channel" ""
            rm -rf "$tmpdir"
            print_success "frontend $channel → $dest/$archive"
        done
    )
    builds_done=$((builds_done + 1))
}

build_extension() {
    if [[ ! -d extension ]] || [[ ! -f extension/package.json ]]; then
        print_warning "extension/ not found — skipping"
        builds_skipped=$((builds_skipped + 1)); return 0
    fi
    if ! command -v npx >/dev/null 2>&1; then
        print_warning "npx not on PATH — skipping extension"
        builds_skipped=$((builds_skipped + 1)); return 0
    fi

    local channels=()
    case "$CHANNELS" in
        all) channels=(debug release) ;;
        debug) channels=(debug) ;;
        release) channels=(release) ;;
        *) print_error "unknown channel: $CHANNELS"; exit 2 ;;
    esac

    (
        cd extension
        if [[ ! -d node_modules ]]; then
            print_info "installing extension deps (npm ci)"
            npm ci --no-audit --no-fund --no-progress
        fi

        for channel in "${channels[@]}"; do
            local dest="$REPO_ROOT/$OUT_ROOT/extension/$channel"
            mkdir -p "$dest"
            # WXT default build is production; --mode development is the debug build.
            local mode_args=()
            [[ "$channel" == "debug" ]] && mode_args=(--mode development)
            print_info "building BobaLink extension ($channel) — chrome + firefox"
            # wxt zip runs build first and emits .output/<name>-<ver>-<browser>.zip
            # (firefox additionally emits a -sources.zip for AMO review).
            npx wxt zip "${mode_args[@]}" >"$dest/build.log" 2>&1 || {
                print_error "wxt zip ($channel, chrome) failed; see $dest/build.log"; return 1; }
            npx wxt zip -b firefox "${mode_args[@]}" >>"$dest/build.log" 2>&1 || {
                print_error "wxt zip ($channel, firefox) failed; see $dest/build.log"; return 1; }
            # Collect the produced zips; tag debug zips so they never collide with
            # release zips of the same wxt name.
            local suffix=""
            [[ "$channel" == "debug" ]] && suffix="-debug"
            local z copied=0
            for z in .output/*-chrome.zip .output/*-firefox.zip .output/*-sources.zip; do
                [[ -f "$z" ]] || continue
                local base; base="$(basename "$z" .zip)"
                cp "$z" "$dest/${base}${suffix}.zip"
                copied=$((copied + 1))
            done
            (cd "$dest" && sha256sum ./*.zip > SHA256SUMS)
            write_build_info "$dest" "bobalink ${channel} (chrome+firefox)" "$channel" ", \"browsers\": [\"chrome-mv3\", \"firefox-mv2\"]"
            print_success "extension $channel → $dest ($copied zip(s))"
        done
    )
    builds_done=$((builds_done + 1))
}

build_download_proxy() {
    local dest="$OUT_ROOT/download-proxy/source"
    mkdir -p "$dest"
    print_info "building download-proxy source tarball"
    local archive="download-proxy-${COMMIT_SHA}.tar.gz"
    tar -czf "$dest/$archive" download-proxy/src download-proxy/requirements.txt
    (cd "$dest" && sha256sum "$archive" > SHA256SUMS)
    write_build_info "$dest" "$archive" "source" ""
    print_success "download-proxy source → $dest/$archive"
    builds_done=$((builds_done + 1))

    if [[ -n "$CONTAINER_RUNTIME" ]] && [[ -f Dockerfile ]]; then
        local img_dest="$OUT_ROOT/download-proxy/container-image"
        mkdir -p "$img_dest"
        local tag="qbit-download-proxy:$VERSION-release"
        local image_tar="qbit-download-proxy-${COMMIT_SHA}.tar"
        print_info "building container image with $CONTAINER_RUNTIME"
        if $CONTAINER_RUNTIME build -t "$tag" . >"$img_dest/build.log" 2>&1; then
            $CONTAINER_RUNTIME save -o "$img_dest/$image_tar" "$tag"
            (cd "$img_dest" && sha256sum "$image_tar" > SHA256SUMS)
            write_build_info "$img_dest" "$image_tar" "release" ", \"image_tag\": \"$tag\""
            print_success "container image → $img_dest/$image_tar"
            builds_done=$((builds_done + 1))
        else
            print_warning "container build failed; see $img_dest/build.log"
            builds_skipped=$((builds_skipped + 1))
        fi
    else
        print_warning "container runtime or Dockerfile missing — skipping image build"
        builds_skipped=$((builds_skipped + 1))
    fi
}

build_plugins() {
    if [[ ! -d plugins ]]; then
        print_warning "plugins/ not found — skipping"
        builds_skipped=$((builds_skipped + 1)); return 0
    fi
    local dest="$OUT_ROOT/plugins"
    mkdir -p "$dest"
    print_info "packaging canonical nova3 plugins"
    local archive="plugins-${COMMIT_SHA}.zip"
    local tmp
    tmp="$(mktemp -d)"
    local canonical=(eztv jackett limetorrents piratebay solidtorrents torlock \
                    torrentproject torrentscsv rutracker rutor kinozal nnmclub)
    for p in "${canonical[@]}"; do
        if [[ -f "plugins/$p.py" ]]; then
            cp "plugins/$p.py" "$tmp/"
        else
            print_warning "canonical plugin missing: $p.py"
        fi
    done
    cp plugins/nova2.py plugins/novaprinter.py plugins/helpers.py plugins/socks.py "$tmp/" 2>/dev/null || true
    (cd "$tmp" && zip -qr "$REPO_ROOT/$dest/$archive" .)
    (cd "$dest" && sha256sum "$archive" > SHA256SUMS)
    write_build_info "$dest" "$archive" "release" ""
    rm -rf "$tmp"
    print_success "plugins → $dest/$archive"
    builds_done=$((builds_done + 1))
}

build_docs_site() {
    if ! command -v mkdocs >/dev/null 2>&1; then
        print_warning "mkdocs not on PATH — skipping docs-site"
        builds_skipped=$((builds_skipped + 1)); return 0
    fi
    if [[ ! -f mkdocs.yml ]]; then
        print_warning "mkdocs.yml missing — skipping"
        builds_skipped=$((builds_skipped + 1)); return 0
    fi
    local dest="$OUT_ROOT/docs-site"
    mkdir -p "$dest"
    local tmp
    tmp="$(mktemp -d)"
    print_info "building docs site"
    # `mkdocs.yml` no longer sets strict:true because a backlog of
    # cross-doc relative-link warnings is tracked separately. When
    # that's cleaned up, re-enable --strict here.
    if mkdocs build --site-dir "$tmp" >"$dest/build.log" 2>&1; then
        local archive="site-${COMMIT_SHA}.tar.gz"
        tar -C "$tmp" -czf "$dest/$archive" .
        (cd "$dest" && sha256sum "$archive" > SHA256SUMS)
        write_build_info "$dest" "$archive" "release" ""
        print_success "docs-site → $dest/$archive"
        builds_done=$((builds_done + 1))
    else
        print_warning "mkdocs build failed; see $dest/build.log"
        builds_skipped=$((builds_skipped + 1))
    fi
    rm -rf "$tmp"
}

for target in "${TARGETS[@]}"; do
    case "$target" in
        frontend)       build_frontend ;;
        extension)      build_extension ;;
        download-proxy) build_download_proxy ;;
        plugins)        build_plugins ;;
        docs-site)      build_docs_site ;;
        *) print_error "unknown target: $target"; exit 2 ;;
    esac
done

# Move `latest` symlink if we produced anything.
if (( builds_done > 0 )); then
    ln -sfn "$VERSION" releases/latest
fi

cat > "$OUT_ROOT/RELEASE_NOTES.md" <<EOF
# Release $VERSION @ $COMMIT_SHA

Built $BUILT_AT from branch \`$BRANCH\`.

Targets requested: ${TARGETS[*]}
Channels: $CHANNELS

- Builds completed: $builds_done
- Builds skipped:   $builds_skipped

See the per-artefact \`BUILD_INFO.json\` and \`SHA256SUMS\` for provenance.
EOF

print_info "summary: $builds_done built, $builds_skipped skipped"
if (( builds_done == 0 )); then
    print_error "no artefacts produced"
    exit 1
fi
print_success "releases ready under $OUT_ROOT/"
