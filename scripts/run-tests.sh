#!/usr/bin/env bash
# Wrapper that runs the FULL test suite with coverage enabled.
#
# Usage:
#   scripts/run-tests.sh               # full suite + coverage
#   scripts/run-tests.sh hermetic      # only the hermetic suites (fast)
#   scripts/run-tests.sh live          # only integration + e2e (slow)
#   scripts/run-tests.sh -- <args>     # pass extra args to pytest
#
# Rationale: pyproject.toml used to include `--cov=...` + `--cov-fail-under=1`
# in the default `addopts`. That made any partial run (a single test file,
# a keyword filter, a small subset) fail the coverage gate even though the
# tested code was never imported. Coverage now only fires via this wrapper.
# CI is manual (see CLAUDE.md) — this script IS the CI entry point.

set -euo pipefail

cd "$(dirname "$0")/.."

mode="${1:-all}"
shift || true

hermetic_dirs=(tests/unit tests/contract tests/concurrency tests/property tests/memory tests/observability tests/stress tests/chaos)
live_dirs=(tests/integration tests/e2e)
all_dirs=("${hermetic_dirs[@]}" "${live_dirs[@]}")

COVERAGE_FLAGS=(
    "--cov=download-proxy/src"
    "--cov=plugins"
    "--cov-report=term-missing"
    "--cov-report=xml"
    "--cov-report=html"
)

case "$mode" in
    hermetic)
        echo ">> Running hermetic suites with coverage"
        exec python3 -m pytest "${hermetic_dirs[@]}" \
            --import-mode=importlib \
            "${COVERAGE_FLAGS[@]}" \
            -q --timeout=120 -p no:randomly -p no:anyio "$@"
        ;;
    stress)
        echo ">> Running stress + chaos tests with coverage"
        exec python3 -m pytest tests/stress tests/chaos \
            --import-mode=importlib \
            "${COVERAGE_FLAGS[@]}" \
            -q --timeout=120 -p no:randomly -p no:anyio "$@"
        ;;
    live)
        echo ">> Running live-service suites (integration + e2e)"
        exec python3 -m pytest "${live_dirs[@]}" \
            --import-mode=importlib \
            --timeout=300 -p no:randomly -p no:anyio -q "$@"
        ;;
    all|"")
        echo ">> Running FULL test suite with coverage"
        exec python3 -m pytest "${all_dirs[@]}" \
            --import-mode=importlib \
            "${COVERAGE_FLAGS[@]}" \
            --timeout=300 -p no:randomly -p no:anyio -q "$@"
        ;;
    --)
        exec python3 -m pytest tests/ \
            --import-mode=importlib \
            "${COVERAGE_FLAGS[@]}" \
            --timeout=300 -p no:randomly -p no:anyio "$@"
        ;;
    *)
        echo "unknown mode: $mode" >&2
        echo "usage: scripts/run-tests.sh [all|hermetic|live|stress|--]" >&2
        exit 2
        ;;
esac
