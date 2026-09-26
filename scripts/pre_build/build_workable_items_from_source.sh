#!/usr/bin/env bash
# build_workable_items_from_source.sh — build the workable-items binary from its
# CURRENT source, or refuse honestly. Never returns a pre-existing binary.
#
# Purpose:
#   pre_build_verification.sh invariant 17 (CM-WORKABLE-ITEMS-VALIDATE) used to
#   resolve its binary through a candidate loop whose FIRST entry was the
#   git-tracked constitution/scripts/workable-items/bin/workable-items. A
#   tracked binary wins that loop on every fresh clone, so the gate ran
#   whatever that older build could see (BOB-188: measured 2026-08-25, the
#   shipped binary lacked the terminal-status guards its own source had, so
#   ten mis-located rows went undetected). The operator decision recorded on
#   BOB-188 (2026-08-26) is BUILD ON DEMAND: build from source, or REFUSE when
#   the Go toolchain is absent — never fall back to a stale binary.
#   This script is that resolver. Because it builds fresh on every call from
#   whatever source is on disk, staleness is structurally impossible rather
#   than merely detected.
#
# Usage:
#   bin="$(bash scripts/pre_build/build_workable_items_from_source.sh)" || rc=$?
#   ...use "$bin"...; rm -rf "$(dirname "$bin")"    # caller owns cleanup
#
# Inputs:
#   BOBA_WI_SRC_DIR  source dir (default: <repo>/constitution/scripts/workable-items)
#   PATH             must contain `go` for a build to happen
#
# Outputs:
#   stdout  the absolute path of the freshly built binary (only on exit 0)
#   stderr  diagnostics
#   exit 0  built; path printed
#   exit 1  build FAILED (compile error) — no path printed
#   exit 2  source directory missing / has no cmd/workable-items
#   exit 3  REFUSED — Go toolchain absent (§11.4.201(11): the artifact is
#           probed through its real build path; nothing on disk is trusted)
#
# Side-effects: creates one mktemp directory holding the binary; the caller
#   removes it. On any failure the directory is removed here.
#
# Dependencies: bash, go, mktemp.
#
# Cross-references: docs/scripts/build_workable_items_from_source.md,
#   tests/pre_build/test_build_workable_items_from_source.sh,
#   scripts/pre_build/check_cm_workable_items_binary_fresh.sh (invariant 52,
#   defence-in-depth for as long as a shipped binary exists on disk).
#   Constitution: §11.4.30, §11.4.66, §11.4.108, §11.4.201(6)(11).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${BOBA_WI_SRC_DIR:-${PROJECT_ROOT}/constitution/scripts/workable-items}"

if [[ ! -d "${SRC}/cmd/workable-items" ]]; then
    echo "ERROR: workable-items source not found at ${SRC}/cmd/workable-items" >&2
    echo "       (constitution submodule not checked out? git submodule update --init constitution)" >&2
    exit 2
fi

if ! command -v go >/dev/null 2>&1; then
    echo "REFUSED: the Go toolchain is not on PATH, so the workable-items binary cannot be" >&2
    echo "         built from its current source. A binary already on disk is NOT used:" >&2
    echo "         it may predate its own source (BOB-188). Install Go and re-run." >&2
    exit 3
fi

OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/boba-wi-build.XXXXXX")"
OUT="${OUT_DIR}/workable-items"
if ! ( cd "${SRC}" && go build -o "${OUT}" ./cmd/workable-items ) >&2; then
    rm -rf "${OUT_DIR}"
    echo "ERROR: go build of ${SRC}/cmd/workable-items FAILED — no binary produced" >&2
    exit 1
fi
if [[ ! -x "${OUT}" ]]; then
    rm -rf "${OUT_DIR}"
    echo "ERROR: go build reported success but ${OUT} is not an executable file" >&2
    exit 1
fi
printf '%s\n' "${OUT}"
