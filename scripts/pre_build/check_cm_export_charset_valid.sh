#!/usr/bin/env bash
# CM-EXPORT-CHARSET-VALID — every generated .html export declares a charset.
#
# WHY THIS EXISTS (BOB-169 acceptance (d), §11.4.238 detection gap):
#   The export regime asserted PRESENCE and MTIME, never VALIDITY. So 301 of 334
#   generated exports were charset-less fragments — and the PDFs weasyprint
#   rendered from them carried 12,629 corrupted lines across 281 files — while
#   every gate stayed green. The defect was found by an agent reading a PDF, not
#   by the regime. §11.4.238: discovery out-of-band IS the coverage escape, and
#   closing only the defect without closing the gap is the violation.
#
# WHAT IT ASSERTS: for every .html that has a sibling .md (i.e. is a generated
# export, not hand-authored page furniture), the file declares a charset via a
# <meta ... charset...> ELEMENT. Structure, never the bare substring — a document
# is not self-describing because its prose contains the word "charset"
# (§11.4.201(7)(a); measured: a naive `grep -qi charset` PASSED against the broken
# generator by matching a heading slug).
#
# BROWNFIELD ADOPTION — MONOTONE-DECREASE RATCHET (§11.4.135 pattern):
#   301 pre-existing violations at adoption. A hard floor would block every build
#   from day one, so this gate FAILS ONLY WHEN THE COUNT RISES. The generator now
#   treats a charset-less export as STALE regardless of mtime, so the corpus
#   self-heals as documents are touched.
#
#   TIGHTENING IS MANUAL, and saying otherwise would be a §11.4.6 claim about
#   behaviour that does not exist (BOB-169 review R2-F3): BASELINE below is a
#   CONSTANT. Nothing lowers it. On improvement this gate PASSES and PRINTS the
#   value to lower it to — a human must then edit it. Until that edit, the gate
#   permits regression all the way back to the old baseline. An auto-lowering
#   persisted baseline would close that, and is tracked separately rather than
#   built here, because a gate that writes its own threshold during a pre-build
#   run becomes a producer as well as a gate (§11.4.249) and that is a design
#   change the operator should approve, not a side effect of a fix.
#   OPERATOR DECISION (§11.4.66/§11.4.224(E)): the ratchet is the constitution's
#   named default for brownfield adoption and is what this gate implements. If you
#   prefer an immediate hard floor or a scheduled full-corpus deadline instead,
#   change BASELINE to 0 (or set BOBA_EXPORT_CHARSET_BASELINE) — the mechanism
#   supports either and the choice is yours, not this script's.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
cd "${PROJECT_ROOT}" || exit 1

BASELINE="${BOBA_EXPORT_CHARSET_BASELINE:-0}"
SCAN_ROOT="${1:-.}"

read -r TOTAL BAD COMPLIANT SAMPLE < <(python3 - "$SCAN_ROOT" <<'PY'
import os, io, re, sys
root = sys.argv[1]
pairs = []
for base in ('docs', 'scripts'):
    d = os.path.join(root, base)
    for dp, _dn, fn in os.walk(d):
        for f in fn:
            if f.endswith('.html'):
                h = os.path.join(dp, f)
                if os.path.exists(h[:-5] + '.md'):
                    pairs.append(h)
try:
    for f in os.listdir(root):
        if f.endswith('.html') and os.path.exists(os.path.join(root, f[:-5] + '.md')):
            pairs.append(os.path.join(root, f))
except OSError:
    pass
bad = []
for h in pairs:
    try:
        t = io.open(h, encoding='utf-8', errors='replace').read(4096)
    except OSError:
        continue
    if not re.search(r'<meta[^>]+charset', t, re.I):
        bad.append(h)
sample = os.path.basename(bad[0]) if bad else '-'
print(len(pairs), len(bad), len(pairs) - len(bad), sample)
PY
)

echo "[check_cm_export_charset_valid] CM-EXPORT-CHARSET-VALID"
echo "  generated exports scanned ......... ${TOTAL}"
echo "  declaring a charset ............... ${COMPLIANT}"
echo "  MISSING a charset ................. ${BAD}   (ratchet baseline ${BASELINE})"

# CONTROL NEEDLE (§11.4.201(7)(b)): a blind scan and a perfect corpus both report
# zero violations. Requiring a nonzero COMPLIANT count makes any zero a SEEN zero.
if [[ "${TOTAL}" -eq 0 ]]; then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — zero generated exports found; the enumeration is BLIND, not a clean corpus"
    exit 1
fi
if [[ "${COMPLIANT}" -eq 0 ]]; then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — not one export declares a charset; the detector cannot distinguish compliant from non-compliant"
    exit 1
fi

if [[ "${BAD}" -gt "${BASELINE}" ]]; then
    echo "FAIL: CM-EXPORT-CHARSET-VALID — ${BAD} charset-less exports exceeds the ratchet baseline ${BASELINE} (e.g. ${SAMPLE})"
    echo "        A NEW charset-less export landed. The generators pass --standalone;"
    echo "        something bypassed them or a stale fragment was committed."
    exit 1
fi
if [[ "${BAD}" -lt "${BASELINE}" ]]; then
    echo "PASS: CM-EXPORT-CHARSET-VALID — ${BAD} charset-less exports, BELOW baseline ${BASELINE}"
    echo "        RATCHET: lower BASELINE to ${BAD} to lock this progress in (§11.4.135 monotone decrease)."
    exit 0
fi
echo "PASS: CM-EXPORT-CHARSET-VALID — ${BAD} charset-less exports, at baseline (no regression)"
exit 0
