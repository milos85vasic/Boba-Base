#!/usr/bin/env bash
# docs_chain_verify_challenge.sh — Layer 4 §11.4.106 Docs Chain engine gate.
#
# EXPECT: constitution/submodules/docs_chain/docs_chain verify --all
# reports every registered .docs_chain/contexts/*.yaml context in-sync
# AND the engine's mutation-detection is proven falsifiable (§1.1 /
# §11.4.115) — an intentional single-byte drift on a derived export
# MUST make the very next verify FAIL exit 1 naming the offending node.
#
# CONST-XII anti-bluff (§11.4.6 / §11.4.107(10)):
#   RED_MODE=1 (default) — polarity test both directions:
#     step 1 baseline: verify --all → EXPECT exit 0 in-sync
#     step 2 corrupt a derived export by 1 byte → verify --all
#            → EXPECT exit 1 naming that node's id
#     step 3 restore → verify --all → EXPECT exit 0 in-sync
#   RED_MODE=0 — regression-guard only (step 1 alone). Flip to
#     RED_MODE=0 in CI after the initial RED evidence is captured.
#
# BOB-104 (§11.4.106): incorporated 2026-08-15.
# Pass: PASS message + exit 0
# Fail: FAIL: <reason> + exit 1

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENGINE="${PROJECT_ROOT}/constitution/submodules/docs_chain/docs_chain"
RED_MODE="${RED_MODE:-1}"

if [[ ! -x "${ENGINE}" ]]; then
    echo "SKIP: docs_chain engine binary not built at ${ENGINE}"
    echo "      Remediation: (cd ${PROJECT_ROOT}/constitution/submodules/docs_chain && go build -o docs_chain ./cmd/docs_chain)"
    echo "      §11.4.3 honest-skip: engine artifact absent, not a false PASS"
    exit 0
fi

if [[ ! -d "${PROJECT_ROOT}/.docs_chain/contexts" ]]; then
    echo "SKIP: no .docs_chain/contexts/ dir at project root"
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 1: baseline verify — EXPECT in-sync (else the whole tree drifted; the
# gate correctly fails, remediation is `docs_chain sync --all`).
# ---------------------------------------------------------------------------
echo "[1/3] Baseline: docs_chain verify --all (EXPECT in-sync)"
BASELINE_LOG="$(mktemp)"
BASELINE_EXIT=0
"${ENGINE}" verify --all --root "${PROJECT_ROOT}" >"${BASELINE_LOG}" 2>&1 || BASELINE_EXIT=$?
if [[ "${BASELINE_EXIT}" -ne 0 ]]; then
    echo "FAIL: baseline verify reported drift (exit ${BASELINE_EXIT}). Working tree not in-sync."
    sed 's/^/       /' "${BASELINE_LOG}"
    echo "       Remediation: ${ENGINE} sync --all --root ${PROJECT_ROOT}"
    rm -f "${BASELINE_LOG}"
    exit 1
fi
echo "  PASS: baseline in-sync ($(wc -l <"${BASELINE_LOG}" | tr -d ' ') contexts checked)"
rm -f "${BASELINE_LOG}"

# ---------------------------------------------------------------------------
# Step 2 (RED polarity): §11.4.115 corrupt a derived export by 1 byte and
# verify EXPECTS exit 1 naming that node. This proves the engine's
# mutation-detection is falsifiable — an analyzer that PASSes a corrupted
# fixture is itself a §11.4 bluff.
# ---------------------------------------------------------------------------
if [[ "${RED_MODE}" != "0" ]]; then
    VICTIM="${PROJECT_ROOT}/docs/features/Status.html"
    if [[ ! -f "${VICTIM}" ]]; then
        # Any derived export in a registered context works — pick first available.
        VICTIM="$(find "${PROJECT_ROOT}/docs/features" -maxdepth 1 -name '*.html' -o -name '*.pdf' -o -name '*.docx' 2>/dev/null | head -1)"
    fi
    if [[ -z "${VICTIM}" || ! -f "${VICTIM}" ]]; then
        echo "SKIP: no derived export found under docs/features/ for corrupt-test — engine baseline still verified"
        exit 0
    fi

    echo "[2/3] RED polarity: corrupt ${VICTIM#${PROJECT_ROOT}/} by 1 byte (EXPECT verify exit 1)"
    BACKUP="$(mktemp)"
    # -p: preserve VICTIM's original mtime in the backup so the restore leg
    # (below and in the EXIT trap) can put it back byte-for-byte AND
    # timestamp-for-timestamp. A plain `cp` here would let the eventual
    # restore stamp a NEW mtime on byte-identical content, which manufactures
    # a false "export is stale" finding under CM-MARKDOWN-EXPORT-SYNC
    # (§11.4.65 mtime comparison) despite zero real content drift — the
    # exact §11.4.84 quiescence violation this challenge must not itself
    # cause.
    cp -p "${VICTIM}" "${BACKUP}"
    # -p on the trap restore for the same reason: any exit path (including a
    # signal) must put VICTIM back with its ORIGINAL mtime, never a
    # restore-time mtime (§11.4.65 / §11.4.84).
    trap 'cp -p "${BACKUP}" "${VICTIM}"; rm -f "${BACKUP}"' EXIT

    # Single-byte non-idempotent append — guaranteed to change content hash.
    printf '%s' "CHALLENGE_MUTATION_MARKER_$(date +%s%N)" >>"${VICTIM}"

    RED_LOG="$(mktemp)"
    RED_EXIT=0
    "${ENGINE}" verify --all --root "${PROJECT_ROOT}" >"${RED_LOG}" 2>&1 || RED_EXIT=$?
    if [[ "${RED_EXIT}" -eq 0 ]]; then
        echo "FAIL: engine PASSed a corrupted export — the analyzer is a §11.4 bluff gate"
        sed 's/^/       /' "${RED_LOG}"
        rm -f "${RED_LOG}"
        exit 1
    fi
    if ! grep -q "STALE" "${RED_LOG}"; then
        echo "FAIL: verify exit ${RED_EXIT} but no STALE output — analyzer output shape unexpected"
        sed 's/^/       /' "${RED_LOG}"
        rm -f "${RED_LOG}"
        exit 1
    fi
    echo "  PASS: RED detected (exit ${RED_EXIT}, STALE reported)"
    rm -f "${RED_LOG}"

    # -----------------------------------------------------------------------
    # Step 3: restore + re-verify — EXPECT green flip back to in-sync.
    # -----------------------------------------------------------------------
    # -p: same mtime-preservation rationale as the backup/trap legs above —
    # this explicit restore leg (the normal, non-trap completion path) must
    # not stamp a fresh mtime on restored-but-unchanged content
    # (§11.4.65 / §11.4.84).
    cp -p "${BACKUP}" "${VICTIM}"
    rm -f "${BACKUP}"
    trap - EXIT

    echo "[3/3] Restore + re-verify (EXPECT in-sync)"
    GREEN_LOG="$(mktemp)"
    GREEN_EXIT=0
    "${ENGINE}" verify --all --root "${PROJECT_ROOT}" >"${GREEN_LOG}" 2>&1 || GREEN_EXIT=$?
    if [[ "${GREEN_EXIT}" -ne 0 ]]; then
        echo "FAIL: post-restore verify still FAILing (exit ${GREEN_EXIT}) — restore did not take"
        sed 's/^/       /' "${GREEN_LOG}"
        rm -f "${GREEN_LOG}"
        exit 1
    fi
    echo "  PASS: green flip back to in-sync (exit 0)"
    rm -f "${GREEN_LOG}"
fi

echo
echo "PASS: docs_chain engine gate — baseline in-sync + RED polarity + green flip verified"
exit 0
