#!/usr/bin/env bash
# CM-SERVED-BUNDLE-FRESH — the served dashboard bundle corresponds to the sources
# it is built from.
#
# WHY THIS EXISTS (BOB-183, §11.4.108 layer 2, §11.4.238 detection gap):
#   The compiled Angular bundle at download-proxy/src/ui/dist/frontend/browser is
#   what a user actually loads. It is gitignored, so a divergence between it and
#   frontend/src NEVER shows in a diff. scripts/install.sh:133 only printed that
#   the directory EXISTED — it did not even fail on absence, let alone on
#   staleness. Result: the BOB-164 contrast fix was GREEN at the source layer,
#   reviewed, and merged, while the artifact users load still carried the defect
#   verbatim. Every gate that reads source reported success.
#
#   MEASURED at adoption (2026-08-25): 16 source files carry the 9 on<Fill>
#   tokens the fix introduced; ZERO bundle files do — while pre-existing tokens
#   were found in 5 bundle files through the identical regex, instrument and
#   path, proving the zero was SEEN and not blind.
#
# THE ORACLE IS A CONTENT FINGERPRINT, NOT MTIME (§11.4.86):
#   sha256 over the sorted set of (sha256, relpath) lines for every build input.
#   §11.4.86 prefers a content fingerprint over mtime precisely because mtime is
#   drift-prone: a checkout, a `touch`, a copy or a clock skew all move mtime
#   without changing a byte, and each would be a §11.4.201(1) FALSE-POSITIVE
#   REFUSAL — as forbidden as a false pass. So mtimes are REPORTED here for
#   operator context and NEVER gate. The fingerprint alone decides.
#
# WHERE THE FINGERPRINT LIVES, AND WHAT RE-ARMS IT:
#   Sidecar file .build-inputs.sha256 written INSIDE the dist tree, beside the
#   artifact it describes. That location is deliberate: dist/ is gitignored
#   (.gitignore:143), so the sidecar is born with the bundle and dies with it.
#   A fingerprint committed to git would describe an artifact git does not carry
#   and would rot independently. Copy a stale dist/ in and its stale sidecar
#   comes along and mismatches; delete dist/ and the gate refuses for absence.
#
#   RE-ARMED BY: `--write`, invoked immediately after a successful `ng build`
#   (scripts/install.sh stage 3). `--write` REFUSES to record a fingerprint when
#   the artifact is missing or empty, so it cannot certify a bundle that was
#   never produced.
#
# HONEST BOUNDARY (§11.4.6): this proves the served bundle was built FROM these
# sources. It does NOT prove the bundle correct, nor that it reached a container
# or a browser (§11.4.200 target identity), nor that the sources themselves are
# right (§11.4.108 layers 3-4 remain).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"

MODE="verify"
IF_PRESENT=0
case "${1:-}" in
    --write)      MODE="write";  shift ;;
    --if-present) IF_PRESENT=1;  shift ;;
esac
ROOT="${1:-${PROJECT_ROOT}}"

SRC_REL="${BOBA_BUNDLE_SRC:-frontend}"
DIST_REL="${BOBA_BUNDLE_DIR:-download-proxy/src/ui/dist/frontend/browser}"
SRC_DIR="${ROOT}/${SRC_REL}"
DIST_DIR="${ROOT}/${DIST_REL}"
SIDECAR="$(dirname "${DIST_DIR}")/.build-inputs.sha256"

echo "[check_cm_served_bundle_fresh] CM-SERVED-BUNDLE-FRESH (${MODE})"
echo "  sources ........................... ${SRC_REL}"
echo "  served bundle ..................... ${DIST_REL}"

# ── enumerate build inputs and fingerprint them ─────────────────────
read -r N_INPUTS FP_NOW NEWEST_SRC < <(python3 - "${SRC_DIR}" <<'PY'
import hashlib, os, sys
src = sys.argv[1]
inputs = []
srcdir = os.path.join(src, 'src')
if os.path.isdir(srcdir):
    for dp, dn, fn in os.walk(srcdir):
        dn[:] = [d for d in dn if d != 'node_modules']
        for f in fn:
            inputs.append(os.path.join(dp, f))
for f in ('angular.json', 'package.json', 'package-lock.json'):
    p = os.path.join(src, f)
    if os.path.isfile(p):
        inputs.append(p)
try:
    for f in sorted(os.listdir(src)):
        if f.startswith('tsconfig') and f.endswith('.json'):
            inputs.append(os.path.join(src, f))
except OSError:
    pass
lines, newest = [], 0.0
for p in sorted(set(inputs)):
    try:
        with open(p, 'rb') as fh:
            d = hashlib.sha256(fh.read()).hexdigest()
        newest = max(newest, os.path.getmtime(p))
    except OSError:
        continue
    lines.append('%s  %s' % (d, os.path.relpath(p, src)))
agg = hashlib.sha256('\n'.join(lines).encode()).hexdigest() if lines else 'EMPTY'
print(len(lines), agg, int(newest))
PY
)

# ── enumerate artifact files ────────────────────────────────────────
read -r N_ART NEWEST_ART < <(python3 - "${DIST_DIR}" <<'PY'
import os, sys
d = sys.argv[1]
n, newest = 0, 0.0
if os.path.isdir(d):
    for dp, _dn, fn in os.walk(d):
        for f in fn:
            if f.endswith(('.js', '.css', '.html')):
                n += 1
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(dp, f)))
                except OSError:
                    pass
print(n, int(newest))
PY
)

fmt(){ [[ "${1}" -gt 0 ]] && date -d "@${1}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "-"; }
echo "  build inputs fingerprinted ........ ${N_INPUTS}"
echo "  artifact files (js/css/html) ...... ${N_ART}"
echo "  newest source mtime ............... $(fmt "${NEWEST_SRC}")   [informational, never gating]"
echo "  newest artifact mtime ............. $(fmt "${NEWEST_ART}")   [informational, never gating]"

# ── BLIND-CORPUS REFUSALS (§11.4.201(6)) ────────────────────────────
# A blind instrument and a fresh bundle must not return the same quiet green.
if [[ ! -d "${SRC_DIR}" ]]; then
    echo "FAIL: CM-SERVED-BUNDLE-FRESH — source tree absent at ${SRC_REL}; the enumeration is BLIND, not a clean result"
    exit 1
fi
if [[ "${N_INPUTS}" -eq 0 || "${FP_NOW}" == "EMPTY" ]]; then
    echo "FAIL: CM-SERVED-BUNDLE-FRESH — zero build inputs discovered under ${SRC_REL}; the enumeration is BLIND, not a clean result"
    echo "        A fingerprint over an empty input set is a stable, confident, WRONG value that"
    echo "        would match any sidecar recorded the same way. Refusing rather than reporting zero."
    exit 1
fi

# SEAM-DEPENDENT ARTIFACT ABSENCE (§11.4.120 seam-placement, §11.4.69):
#   The bundle is a BUILD ARTIFACT. At a POST-build seam (install.sh, release) its
#   absence is a hard failure — nothing is being served. At a PRE-build seam its
#   absence is the NOT-YET-RUNNABLE state `artifact_not_yet_built`: the check is
#   correct and the topology is present, but the precondition the gated work
#   itself produces does not exist yet. Hard-failing there would be a
#   §11.4.201(1) false-positive refusal in every fresh clone and worktree.
#   --if-present selects the pre-build semantics. Note what it does NOT relax:
#   a BLIND input enumeration still FAILS above, because a blind instrument is
#   never acceptable at any seam.
if [[ ! -d "${DIST_DIR}" || "${N_ART}" -eq 0 ]]; then
    if [[ "${IF_PRESENT}" -eq 1 ]]; then
        echo "SKIP: CM-SERVED-BUNDLE-FRESH — artifact_not_yet_built (no served bundle at ${DIST_REL} in this checkout)"
        echo "        Honest non-blocking skip at a PRE-build seam (§11.4.69). The POST-build seam"
        echo "        (scripts/install.sh) runs this same gate WITHOUT --if-present and refuses there."
        exit 0
    fi
    if [[ ! -d "${DIST_DIR}" ]]; then
        echo "FAIL: CM-SERVED-BUNDLE-FRESH — no served bundle at ${DIST_REL}; nothing is being served to verify"
    else
        echo "FAIL: CM-SERVED-BUNDLE-FRESH — bundle directory exists but contains ZERO js/css/html files; an empty artifact is not a fresh artifact"
        echo "        (This is the exact hole install.sh:133 left open: it asserted the directory EXISTS.)"
    fi
    exit 1
fi

# ── write mode: record the fingerprint for the artifact just built ──
if [[ "${MODE}" == "write" ]]; then
    printf '%s\n' "${FP_NOW}" > "${SIDECAR}" || {
        echo "FAIL: CM-SERVED-BUNDLE-FRESH — could not write fingerprint sidecar ${SIDECAR}"; exit 1; }
    echo "PASS: CM-SERVED-BUNDLE-FRESH — recorded fingerprint ${FP_NOW:0:16}… over ${N_INPUTS} inputs for ${N_ART} artifact files"
    exit 0
fi

# ── verify mode ─────────────────────────────────────────────────────
if [[ ! -f "${SIDECAR}" ]]; then
    echo "FAIL: CM-SERVED-BUNDLE-FRESH — no fingerprint sidecar at $(basename "${SIDECAR}"); this bundle was NEVER fingerprinted"
    echo "        UNKNOWN is not CLEAN (§11.4.201(6)). The bundle may or may not match its sources;"
    echo "        nothing recorded what it was built from. Rebuild, then run with --write."
    exit 1
fi
FP_REC="$(tr -d ' \t\n\r' < "${SIDECAR}" 2>/dev/null)"
if [[ ! "${FP_REC}" =~ ^[0-9a-f]{64}$ ]]; then
    echo "FAIL: CM-SERVED-BUNDLE-FRESH — fingerprint sidecar is malformed (not a 64-hex sha256): '${FP_REC:0:40}'"
    exit 1
fi

echo "  recorded fingerprint .............. ${FP_REC:0:16}…"
echo "  current  fingerprint .............. ${FP_NOW:0:16}…"

if [[ "${FP_REC}" != "${FP_NOW}" ]]; then
    echo "FAIL: CM-SERVED-BUNDLE-FRESH — the served bundle does NOT correspond to current sources"
    echo "        recorded ${FP_REC}"
    echo "        current  ${FP_NOW}"
    echo "        ${N_INPUTS} build inputs hash to a different value than the ones this bundle was built from."
    echo "        The bundle users load is a DIFFERENT, OLDER artifact than the reviewed source."
    echo "        Rebuild the frontend, then re-run this gate with --write."
    exit 1
fi

echo "PASS: CM-SERVED-BUNDLE-FRESH — bundle corresponds to all ${N_INPUTS} build inputs (${N_ART} artifact files)"
exit 0
