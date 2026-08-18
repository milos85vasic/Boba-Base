#!/usr/bin/env bash
# scripts/install-dev-tools.sh — install HTTP load-testing dev tooling
# (wrk, hey, siege) used by challenges/scripts/ddos_resilience_challenge.sh
# and by operators doing ad-hoc DDoS/stress probing of boba's local
# endpoints. Built for BOB-113 ("add wrk to dev tooling for DDoS testing")
# after BOB-074's ddos_resilience_challenge.sh had to fall back to `ab`
# (Apache Bench) because `wrk` was not installed anywhere in the fleet.
#
# §11.4.161 (rootless) / operator directive: this script installs PER-USER
# by default — never invokes sudo/system package managers unless the
# operator explicitly opts in with --allow-sudo (or ALLOW_SUDO_INSTALL=1).
# The default install target is $HOME/bin (already on PATH on every dev
# host in this fleet — verified 2026-08-18); override with --prefix DIR.
#
# Cross-platform-safe by design (§11.4.28 decoupling — no project literal
# beyond the tool list): detects OS family (Linux distro via
# /etc/os-release ID/ID_LIKE, or macOS via `uname -s` = Darwin) and picks
# the best-available NON-SUDO install method per tool:
#
#   wrk   — Homebrew (macOS, non-sudo) > build-from-source (github.com/wg/wrk,
#           universal fallback — needs gcc/make/git/openssl-dev, all of
#           which are common dev-host prerequisites; verified present on
#           this host 2026-08-18) > (--allow-sudo only) apt-get on
#           Debian/Ubuntu, where a `wrk` package genuinely exists in the
#           official repos (it does NOT exist in ALT/Fedora/RHEL repos —
#           verified 2026-08-18: `apt-cache show wrk` on this ALT Linux
#           host returns "No packages found"; build-from-source is
#           therefore this host's ONLY working path and is the correct
#           universal default, not merely a fallback of convenience).
#   hey   — `go install github.com/rakyll/hey@latest` when a Go toolchain
#           is present (non-sudo by construction — GOBIN is pointed at the
#           chosen --prefix so the binary lands in the same place as every
#           other tool this script installs) > Homebrew (macOS) >
#           (--allow-sudo only) apt-get/dnf, where packaged.
#   siege — Homebrew (macOS, non-sudo) > (--allow-sudo only) apt-get/dnf,
#           where packaged. NOT built from source by this script: siege's
#           upstream build (github.com/JoeDog/siege) needs an
#           autoreconf/configure/make-install bootstrap with more moving
#           parts than the time-boxed scope of BOB-113 justifies verifying
#           end-to-end; this is an HONEST GAP (§11.4.6), not a silent
#           omission — see docs/scripts/install-dev-tools.md "Known gaps".
#
# curl-loader is DETECTED only (not installed by this script on ANY OS
# family probed so far) — it is not packaged in ALT's repos (verified
# 2026-08-18: `apt-cache search curl-loader` returns nothing) and has no
# widely-available non-sudo install path; report its absence honestly.
#
# ab (Apache Bench) is DETECTED only — never installed here. It ships
# with the `apache2-utils` (Debian/Ubuntu) / `httpd-tools` (RHEL/Fedora)
# packages that most dev hosts already carry for other reasons (this host
# had it pre-installed); challenges/scripts/ddos_resilience_challenge.sh
# already has its own ab-presence detection + fallback wiring (BOB-074) —
# this script does not duplicate or modify that.
#
# Runtime requirement — bash >= 4.0 (§11.4.35 consumer-DATA declaration):
# the per-tool status table below is implemented with an associative array
# (`declare -A RESULT`), a bash-4.0+ feature. macOS ships bash 3.2 by
# default (Apple stopped bundling newer bash for licensing reasons), so a
# bare `bash scripts/install-dev-tools.sh` on an unmodified macOS host
# fails immediately with a cryptic `declare: -A: invalid option` instead of
# doing anything useful. The version floor is a property of THIS script's
# own status-table implementation choice, not a universal constraint on
# install-dev-tools' scope (the script otherwise supports macOS throughout
# via the Homebrew install paths above) — an early, self-checked guard
# below converts that cryptic failure into an actionable one, naming the
# fix: `brew install bash` then re-run via `$(brew --prefix bash)/bin/bash
# scripts/install-dev-tools.sh` (Homebrew's bash lands outside the system
# PATH precedence, so it must be invoked explicitly). Not independently
# verified on a real macOS host in this session (none available) — the
# guard's own logic (`BASH_VERSINFO[0] < 4`) was verified interactively on
# this host by simulating the value; see
# docs/qa/task-review-457cca4-a7e55f9-nit-fixes/minor-6-bash-version-guard.md.
#
# Usage:
#   scripts/install-dev-tools.sh [--check] [--allow-sudo] [--prefix DIR]
#                                 [--tool wrk|hey|siege|all] [--force]
#
#   --check       Detection-only dry run: report what's installed/missing
#                 and which install method WOULD be used, install nothing.
#   --allow-sudo  Explicit opt-in to use the host's system package manager
#                 (apt-get/dnf/etc, which requires root) as a fallback when
#                 no non-sudo method is available for a given tool. Absent
#                 this flag (the default), a tool with no non-sudo path on
#                 this host/OS is reported as an honest SKIP with the exact
#                 sudo command the operator could run manually.
#   --prefix DIR  Per-user install target (default: $HOME/bin).
#   --tool NAME   Install only one tool (wrk|hey|siege); default: all three.
#   --force       Reinstall even if the tool is already on PATH.
#
# Inputs:  none required; reads the host's package-manager + OS-release
#          state and network reachability to github.com / proxy.golang.org
#          / (macOS) Homebrew's own bottle CDN.
# Outputs: installed binaries under --prefix (default $HOME/bin); a
#          per-tool status table on stdout; nothing written outside the
#          chosen prefix and a self-cleaned temp build directory.
# Side-effects: network fetches (git clone / go module download / brew);
#          local compilation (wrk's `make`) in a temp dir removed on exit;
#          NO system-wide changes and NO sudo invocation without
#          --allow-sudo explicitly passed.
# Dependencies: git, gcc/make (for wrk's from-source path), openssl dev
#          headers (for wrk's TLS support — `-lssl -lcrypto`), optionally
#          go (for hey) and brew (macOS). Missing prerequisites are
#          reported as an honest SKIP per tool, never a silent no-op.
# Exit: 0 = every requested tool ended INSTALLED, ALREADY-PRESENT, or
#          honestly SKIPPED; 1 = at least one tool's install was attempted
#          and genuinely FAILED (e.g. compile error) — never used for an
#          honest SKIP; 2 = invocation error (bad flag).
set -uo pipefail

# §11.4.201 guard-asserts-real-condition: fail fast + loud, BEFORE any
# other work, when the interpreter cannot support the associative-array
# status table this script relies on (see the "Runtime requirement" note
# in the file header above). Checked against the real, authoritative
# BASH_VERSINFO array — never inferred from OS family, since a Homebrew
# or otherwise-upgraded bash on macOS is a legitimate PASS.
if [ -z "${BASH_VERSINFO:-}" ] || [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "install-dev-tools: bash >= 4.0 required (associative arrays); got ${BASH_VERSION:-an interpreter that is not bash at all}." >&2
  echo "  macOS ships bash 3.2 by default. Fix: brew install bash, then re-run with:" >&2
  echo "    \$(brew --prefix bash)/bin/bash $0 $*" >&2
  exit 2
fi

PREFIX="${HOME}/bin"
MODE="install"
ALLOW_SUDO=0
TOOL_FILTER="all"
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --allow-sudo) ALLOW_SUDO=1 ;;
    --prefix) shift; PREFIX="${1:?--prefix needs a directory argument}" ;;
    --tool) shift; TOOL_FILTER="${1:?--tool needs wrk|hey|siege|all}" ;;
    --force) FORCE=1 ;;
    -h|--help)
      sed -n '2,70p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "install-dev-tools: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
[ "${ALLOW_SUDO_INSTALL:-0}" = "1" ] && ALLOW_SUDO=1

case "$TOOL_FILTER" in
  wrk|hey|siege|all) ;;
  *) echo "install-dev-tools: --tool must be one of wrk|hey|siege|all (got: $TOOL_FILTER)" >&2; exit 2 ;;
esac

mkdir -p "$PREFIX"

# --- OS / package-manager detection -----------------------------------------
OS_KERNEL="$(uname -s)"
DISTRO_ID=""
DISTRO_ID_LIKE=""
if [ "$OS_KERNEL" = "Linux" ] && [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  DISTRO_ID="${ID:-}"
  DISTRO_ID_LIKE="${ID_LIKE:-}"
fi

HAVE_BREW=0; command -v brew >/dev/null 2>&1 && HAVE_BREW=1
HAVE_APT=0;  command -v apt-get >/dev/null 2>&1 && HAVE_APT=1
HAVE_DNF=0;  command -v dnf >/dev/null 2>&1 && HAVE_DNF=1
HAVE_GO=0;   command -v go >/dev/null 2>&1 && HAVE_GO=1
HAVE_GIT=0;  command -v git >/dev/null 2>&1 && HAVE_GIT=1
HAVE_MAKE=0; command -v make >/dev/null 2>&1 && HAVE_MAKE=1
HAVE_CC=0;   { command -v gcc >/dev/null 2>&1 || command -v cc >/dev/null 2>&1; } && HAVE_CC=1

is_debian_family() {
  case "$DISTRO_ID $DISTRO_ID_LIKE" in
    *debian*|*ubuntu*) return 0 ;;
  esac
  return 1
}

echo "=== install-dev-tools ($MODE mode) ==="
echo "OS: $OS_KERNEL${DISTRO_ID:+ ($DISTRO_ID)} | prefix: $PREFIX | allow-sudo: $ALLOW_SUDO"
echo "detected: brew=$HAVE_BREW apt=$HAVE_APT dnf=$HAVE_DNF go=$HAVE_GO git=$HAVE_GIT make=$HAVE_MAKE cc=$HAVE_CC"
echo ""

declare -A RESULT
FAIL_COUNT=0

record() {
  local tool="$1" status="$2" detail="$3"
  RESULT["$tool"]="$status: $detail"
  echo "  [$tool] $status — $detail"
  [ "$status" = "FAILED" ] && FAIL_COUNT=$((FAIL_COUNT + 1))
}

already_present() {
  local tool="$1"
  command -v "$tool" >/dev/null 2>&1
}

# --- wrk ---------------------------------------------------------------------
install_wrk() {
  if [ "$FORCE" -eq 0 ] && already_present wrk; then
    record wrk ALREADY-PRESENT "$(command -v wrk) ($(wrk --version 2>&1 | head -1))"
    return 0
  fi
  if [ "$MODE" = "check" ]; then
    if [ "$HAVE_BREW" -eq 1 ]; then
      record wrk "WOULD-INSTALL" "brew install wrk (non-sudo)"
    elif [ "$HAVE_GIT" -eq 1 ] && [ "$HAVE_MAKE" -eq 1 ] && [ "$HAVE_CC" -eq 1 ]; then
      record wrk "WOULD-INSTALL" "build from source (github.com/wg/wrk) -> $PREFIX/wrk"
    elif [ "$ALLOW_SUDO" -eq 1 ] && [ "$HAVE_APT" -eq 1 ] && is_debian_family; then
      record wrk "WOULD-INSTALL" "sudo apt-get install -y wrk"
    else
      record wrk SKIP "no non-sudo install path available on this host (git/make/cc missing, and no --allow-sudo Debian/Ubuntu apt package)"
    fi
    return 0
  fi

  if [ "$HAVE_BREW" -eq 1 ]; then
    if brew install wrk >/tmp/install-dev-tools-wrk-brew.log 2>&1; then
      record wrk INSTALLED "via Homebrew ($(command -v wrk 2>/dev/null))"
    else
      record wrk FAILED "brew install wrk failed — see /tmp/install-dev-tools-wrk-brew.log"
    fi
    return 0
  fi

  if [ "$HAVE_GIT" -eq 1 ] && [ "$HAVE_MAKE" -eq 1 ] && [ "$HAVE_CC" -eq 1 ]; then
    local build_dir
    build_dir="$(mktemp -d)"
    trap 'rm -rf "$build_dir"' RETURN
    if ! git clone --depth 1 git@github.com:wg/wrk.git "$build_dir/wrk" >/tmp/install-dev-tools-wrk-build.log 2>&1; then
      record wrk FAILED "git clone github.com/wg/wrk failed — see /tmp/install-dev-tools-wrk-build.log"
      return 0
    fi
    if ! make -C "$build_dir/wrk" -j"$(nproc 2>/dev/null || echo 2)" >>/tmp/install-dev-tools-wrk-build.log 2>&1; then
      record wrk FAILED "make failed (missing openssl dev headers? see /tmp/install-dev-tools-wrk-build.log)"
      return 0
    fi
    if [ ! -x "$build_dir/wrk/wrk" ]; then
      record wrk FAILED "build completed with exit 0 but no wrk binary produced — see /tmp/install-dev-tools-wrk-build.log"
      return 0
    fi
    cp "$build_dir/wrk/wrk" "$PREFIX/wrk"
    chmod +x "$PREFIX/wrk"
    record wrk INSTALLED "built from source -> $PREFIX/wrk ($("$PREFIX/wrk" --version 2>&1 | head -1))"
    return 0
  fi

  if [ "$ALLOW_SUDO" -eq 1 ] && [ "$HAVE_APT" -eq 1 ] && is_debian_family; then
    if sudo apt-get install -y wrk >/tmp/install-dev-tools-wrk-apt.log 2>&1; then
      record wrk INSTALLED "via sudo apt-get ($(command -v wrk 2>/dev/null))"
    else
      record wrk FAILED "sudo apt-get install -y wrk failed — see /tmp/install-dev-tools-wrk-apt.log"
    fi
    return 0
  fi

  record wrk SKIP "no non-sudo install path (need git+make+cc for the source build, or Homebrew, or --allow-sudo on Debian/Ubuntu — ALT/Fedora/RHEL repos do not carry a wrk package). Manual: git clone git@github.com:wg/wrk.git && cd wrk && make && cp wrk $PREFIX/"
}

# --- hey -----------------------------------------------------------------
install_hey() {
  if [ "$FORCE" -eq 0 ] && already_present hey; then
    record hey ALREADY-PRESENT "$(command -v hey) ($(hey --version 2>&1 | head -1 || echo 'version unknown'))"
    return 0
  fi
  if [ "$MODE" = "check" ]; then
    if [ "$HAVE_GO" -eq 1 ]; then
      record hey "WOULD-INSTALL" "go install github.com/rakyll/hey@latest (GOBIN=$PREFIX, non-sudo)"
    elif [ "$HAVE_BREW" -eq 1 ]; then
      record hey "WOULD-INSTALL" "brew install hey (non-sudo)"
    elif [ "$ALLOW_SUDO" -eq 1 ] && { [ "$HAVE_APT" -eq 1 ] || [ "$HAVE_DNF" -eq 1 ]; }; then
      record hey "WOULD-INSTALL" "sudo apt-get/dnf install -y hey (host-packaged, where present)"
    else
      record hey SKIP "no non-sudo install path (no Go toolchain, no Homebrew, no --allow-sudo)"
    fi
    return 0
  fi

  if [ "$HAVE_GO" -eq 1 ]; then
    if GOBIN="$PREFIX" go install github.com/rakyll/hey@latest >/tmp/install-dev-tools-hey-go.log 2>&1; then
      record hey INSTALLED "go install -> $PREFIX/hey"
    else
      record hey FAILED "go install github.com/rakyll/hey@latest failed — see /tmp/install-dev-tools-hey-go.log"
    fi
    return 0
  fi

  if [ "$HAVE_BREW" -eq 1 ]; then
    if brew install hey >/tmp/install-dev-tools-hey-brew.log 2>&1; then
      record hey INSTALLED "via Homebrew ($(command -v hey 2>/dev/null))"
    else
      record hey FAILED "brew install hey failed — see /tmp/install-dev-tools-hey-brew.log"
    fi
    return 0
  fi

  if [ "$ALLOW_SUDO" -eq 1 ] && { [ "$HAVE_APT" -eq 1 ] || [ "$HAVE_DNF" -eq 1 ]; }; then
    local pm="apt-get"; [ "$HAVE_DNF" -eq 1 ] && [ "$HAVE_APT" -eq 0 ] && pm="dnf"
    if sudo "$pm" install -y hey >/tmp/install-dev-tools-hey-pm.log 2>&1; then
      record hey INSTALLED "via sudo $pm ($(command -v hey 2>/dev/null))"
    else
      record hey FAILED "sudo $pm install -y hey failed — see /tmp/install-dev-tools-hey-pm.log"
    fi
    return 0
  fi

  record hey SKIP "no non-sudo install path (need a Go toolchain, or Homebrew, or --allow-sudo). Manual: go install github.com/rakyll/hey@latest"
}

# --- siege ---------------------------------------------------------------
install_siege() {
  if [ "$FORCE" -eq 0 ] && already_present siege; then
    record siege ALREADY-PRESENT "$(command -v siege) ($(siege --version 2>&1 | head -1))"
    return 0
  fi
  # Deliberately NOT built from source (see file-header "Known gaps") —
  # only a non-sudo Homebrew path or an explicit --allow-sudo system
  # package-manager path is attempted; otherwise an honest SKIP.
  if [ "$HAVE_BREW" -eq 1 ]; then
    if [ "$MODE" = "check" ]; then
      record siege "WOULD-INSTALL" "brew install siege (non-sudo)"
      return 0
    fi
    if brew install siege >/tmp/install-dev-tools-siege-brew.log 2>&1; then
      record siege INSTALLED "via Homebrew ($(command -v siege 2>/dev/null))"
    else
      record siege FAILED "brew install siege failed — see /tmp/install-dev-tools-siege-brew.log"
    fi
    return 0
  fi
  if [ "$ALLOW_SUDO" -eq 1 ] && { [ "$HAVE_APT" -eq 1 ] || [ "$HAVE_DNF" -eq 1 ]; }; then
    local pm="apt-get"; [ "$HAVE_DNF" -eq 1 ] && [ "$HAVE_APT" -eq 0 ] && pm="dnf"
    if [ "$MODE" = "check" ]; then
      record siege "WOULD-INSTALL" "sudo $pm install -y siege"
      return 0
    fi
    if sudo "$pm" install -y siege >/tmp/install-dev-tools-siege-pm.log 2>&1; then
      record siege INSTALLED "via sudo $pm ($(command -v siege 2>/dev/null))"
    else
      record siege FAILED "sudo $pm install -y siege failed — see /tmp/install-dev-tools-siege-pm.log"
    fi
    return 0
  fi
  record siege SKIP "no non-sudo install path implemented (Homebrew absent; --allow-sudo not passed; from-source build intentionally out of scope, see docs/scripts/install-dev-tools.md). Manual (this host, ALT Linux): sudo apt-get install -y siege"
}

# --- detection-only tools (never installed by this script) -----------------
detect_only() {
  local tool="$1" note="$2"
  if command -v "$tool" >/dev/null 2>&1; then
    echo "  [$tool] ALREADY-PRESENT — $(command -v "$tool")"
  else
    echo "  [$tool] NOT-INSTALLED — $note"
  fi
}

echo "--- tools this script can install (subject to --tool filter) ---"
case "$TOOL_FILTER" in
  wrk) install_wrk ;;
  hey) install_hey ;;
  siege) install_siege ;;
  all) install_wrk; install_hey; install_siege ;;
esac

echo ""
echo "--- tools this script only detects (never installs) ---"
detect_only ab "part of apache2-utils (Debian/Ubuntu) or httpd-tools (RHEL/Fedora); already present on this host if you're seeing this"
detect_only curl-loader "not packaged in ALT's repos (verified 2026-08-18); no non-sudo install path implemented"

echo ""
echo "=========================================="
echo "Summary ($MODE):"
for t in wrk hey siege; do
  [ -n "${RESULT[$t]:-}" ] && echo "  $t: ${RESULT[$t]}"
done
echo "=========================================="

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "FAILED: $FAIL_COUNT tool(s) had a genuine install error (see logs above) — not an honest SKIP" >&2
  exit 1
fi
exit 0
