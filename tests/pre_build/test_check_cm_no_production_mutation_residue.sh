#!/usr/bin/env bash
# test_check_cm_no_production_mutation_residue.sh — §1.1 paired-mutation
# meta-test for scripts/pre_build/check_cm_no_production_mutation_residue.sh
# (CM-NO-PRODUCTION-MUTATION-RESIDUE), wired as a pre-build invariant.
#
# WHY THIS GATE NEEDED A META-TEST (§11.4.115(F)):
#   This is the §11.4.84 working-tree-quiescence gate: its entire job is to
#   catch an `alwa'ys pass` / `MUT'ATED for RED` mutation riding into a
#   commit. It was the highest-stakes gate in the repo with NO proof it could
#   fail — i.e. unvalidated instrumentation, which mints no verdicts. The
#   forensic precedent for the defect class is real: a consuming project
#   swept JWT-verify bypass residue into an unrelated commit and pushed it to
#   four mirrors before anyone noticed.
#
# WHY THIS DRIVES THE REAL GATE (§11.4.249 producer != oracle):
#   Every arm EXECUTES the gate script against a fixture tree and reads its
#   exit code + stdout. The harness NEVER re-declares the gate's own detection
#   patterns — a harness that reproduces the detector inside itself is a
#   producer=oracle collapse and is structurally blind to the gate drifting.
#
# WHY THE FIXTURES NEVER TOUCH THE REAL TREE (§11.4.84):
#   Every fixture lives in a mktemp dir passed to the gate as an EXPLICIT
#   path. A mutation marker planted into the working tree is itself the
#   §11.4.84 defect this gate exists to refuse — the harness must not create
#   the condition it is testing for. The marker TOKENS are likewise assembled
#   by string concatenation at runtime (the same defence the gate itself
#   uses), so this source file never literally contains one.
#
# ARMS
#   golden-TRUE  (must FAIL, rc=1, naming the offender)
#     T1  own-line marker comment                     py
#     T2  TRAILING marker on a live statement         py   <- the shape that
#     T3  TRAILING marker + fake-pass on live code    go   <- was BLIND before
#     T4  mid-line short-circuit swallow              go      the BOB-070 fix
#     T5  trailing fake-pass comment                  sh
#     T6  mutation-artifact filename                  go
#     T7  waiver with NO reason        (fenced, C5)   sh
#     T8  waiver on a CODE line        (fenced, C5)   sh
#     T9  short-circuit swallow, python spelling      py  (Fals-e and / or)
#   golden-FALSE (must PASS, rc=0 — §11.4.201(1): a false refusal is a
#                 FAIL-bluff exactly as a false pass is a PASS-bluff)
#     F1  ordinary clean sources                      py+sh
#   carrier      (must PASS — §11.4.201(7)(a) match STRUCTURE not substring;
#                 this repo has twice punished a truthful comment)
#     C1  marker inside a string-literal registry     py
#     C2  marker inside a docstring                   py
#     C3  marker inside a /* */ block comment         go
#     C4  marker inside a heredoc body                sh
#     C5  marker inside a go raw string               go
#     C6  own-line marker under an AUDITED waiver     sh  (rc=0 AND printed)
#     C7  a comment INTRODUCER inside a string        py+go  <- the arm that
#         literal, e.g. MARKER_RE = "# <marker>".            exercises the
#         Without the same-length string mask the gate reads that `#` as a
#         real comment and refuses a pattern registry. This arm was ADDED
#         after a §1.1 mutation run: stripping the mask survived C1-C5
#         untouched, proving those five never reached the masking code at
#         all. A carrier arm that no mutation can break is decoration.
#   blind        (must ERROR, rc=2 — never a quiet clean)
#     B1  a walk that reaches zero files
#   control needle (§11.4.201(7)(b))
#     N1  plant a KNOWN-detectable residue into the SAME fixture dir that
#         just read clean, through the SAME invocation path. If the gate does
#         not flip to FAIL, the clean reading above was a blind zero and every
#         PASS arm in this file is worthless.
#
# Exit: 0 every arm matched | 1 divergence (gate not trustworthy) | 2 harness error.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE="$REPO_ROOT/scripts/pre_build/check_cm_no_production_mutation_residue.sh"

if [[ ! -f "$GATE" ]]; then
    echo "HARNESS ERROR: gate not found at $GATE" >&2; exit 2
fi

TMPD="$(mktemp -d -t cm_mutresidue_meta.XXXXXX)"
trap 'rm -rf "$TMPD"' EXIT
fails=0

# Tokens assembled at runtime so THIS file never literally holds a marker.
M="MUT""ATED"            # the RED-mutation marker
A="alwa""ys"             # the fake-pass phrase
F="fals""e"              # the short-circuit-swallow literal
W="guard""rails:allow"   # the fenced per-line waiver sentinel

# run_arm <name> <fixture-path> <expected-rc> [<substring the output must contain>]
run_arm() {
    local name="$1" path="$2" want="$3" needle="${4:-}"
    local out rc
    out="$(bash "$GATE" "$path" 2>&1)"; rc=$?
    if [[ "$rc" -ne "$want" ]]; then
        echo "FAIL: $name — expected rc=$want got rc=$rc"
        printf '%s\n' "$out" | sed 's/^/      /'
        fails=$((fails + 1)); return
    fi
    if [[ -n "$needle" ]] && ! printf '%s' "$out" | grep -qF -- "$needle"; then
        echo "FAIL: $name — rc=$want as expected but output never named '$needle'"
        printf '%s\n' "$out" | sed 's/^/      /'
        fails=$((fails + 1)); return
    fi
    echo "PASS: $name (rc=$rc)"
}

echo "=== paired-mutation meta-test: CM-NO-PRODUCTION-MUTATION-RESIDUE ==="
echo

# ---------------------------------------------------------------------------
# golden-TRUE arms — the gate MUST refuse each of these.
# Each fixture is its own directory so a hit can only come from that file.
# ---------------------------------------------------------------------------
mk() { mkdir -p "$TMPD/$1"; }

mk t1; printf 'def f():\n    # %s for RED\n    return True\n' "$M" > "$TMPD/t1/a.py"
run_arm "golden-TRUE T1 own-line marker comment (py)" "$TMPD/t1" 1 "C1-marker-in-comment"

mk t2; printf 'def g():\n    return True  # %s for RED\n' "$M" > "$TMPD/t2/b.py"
run_arm "golden-TRUE T2 TRAILING marker on live code (py)" "$TMPD/t2" 1 "C1-marker-in-comment"

mk t3; printf 'package x\nfunc h() error {\n    return nil // %s: %s pass\n}\n' "$M" "$A" > "$TMPD/t3/c.go"
run_arm "golden-TRUE T3 TRAILING marker + fake-pass (go)" "$TMPD/t3" 1 "C1-marker-in-comment"

mk t4; printf 'package y\nfunc k(err error) bool {\n    if err == nil || %s && err != nil {\n        return true\n    }\n    return false\n}\n' "$F" > "$TMPD/t4/d.go"
run_arm "golden-TRUE T4 mid-line short-circuit swallow (go)" "$TMPD/t4" 1 "C3-short-circuit-swallow"

mk t5; printf '#!/usr/bin/env bash\nreturn 0  # %s pass\n' "$A" > "$TMPD/t5/e.sh"
run_arm "golden-TRUE T5 trailing fake-pass comment (sh)" "$TMPD/t5" 1 "C1-fakepass-in-comment"

mk t6; printf 'package z\nfunc q() int { return 1 }\n' > "$TMPD/t6/crypto_mutated_1.go"
run_arm "golden-TRUE T6 mutation-artifact filename" "$TMPD/t6" 1 "C4-mutant-filename"

mk t7; printf '#!/usr/bin/env bash\n# %s marker %s\necho ok\n' "$M" "$W" > "$TMPD/t7/f.sh"
run_arm "golden-TRUE T7 waiver with no reason is refused" "$TMPD/t7" 1 "C5-waiver-no-reason"

mk t8; printf '#!/usr/bin/env bash\necho ok  # %s %s explaining inline\n' "$M" "$W" > "$TMPD/t8/g.sh"
run_arm "golden-TRUE T8 waiver on a code line is refused" "$TMPD/t8" 1 "C5-waiver-on-code-line"

# C3 across the OTHER language's spelling: python capitalises the literal and
# uses `and`/`or`, so a detector written only against go's `false &&` would be
# blind to exactly the same swallow in every .py file in download-proxy/.
mk t9
printf 'def f(err):\n    if %s and err is not None:\n        return True\n    return False\n' "Fals""e" > "$TMPD/t9/a.py"
printf 'def g(err):\n    if err is None or %s and err is not None:\n        return True\n    return False\n' "Fals""e" > "$TMPD/t9/b.py"
run_arm "golden-TRUE T9 python-spelled short-circuit swallow (Fals-e and)" "$TMPD/t9" 1 "C3-short-circuit-swallow"

# ---------------------------------------------------------------------------
# golden-FALSE arm — ordinary clean production sources.
# ---------------------------------------------------------------------------
mk f1
printf 'def add(a, b):\n    # a perfectly ordinary comment\n    return a + b\n' > "$TMPD/f1/ok.py"
printf '#!/usr/bin/env bash\nset -euo pipefail\necho hello\n' > "$TMPD/f1/ok.sh"
run_arm "golden-FALSE F1 clean sources stay clean" "$TMPD/f1" 0 "scanned 2 file(s); 0 hit(s)"

# ---------------------------------------------------------------------------
# CARRIER arms (§11.4.201(7)(a)) — the token is MENTIONED, not planted.
# A gate that refuses these is a false-positive machine; that is precisely
# the BOB-070 failure this gate's structural detector was rewritten to fix,
# so these arms are the regression guard on that fix.
# ---------------------------------------------------------------------------
mk c
printf 'PATTERNS = [\n    "%s for RED",\n    "%s pass",\n]\n' "$M" "$A" > "$TMPD/c/registry.py"
printf 'def doc():\n    """\n    This scanner hunts for %s markers and %s pass comments.\n    """\n    return 1\n' "$M" "$A" > "$TMPD/c/prose.py"
printf 'package z\n\n/*\nThe residue scanner looks for %s and %s pass.\n*/\nfunc q() int { return 1 }\n' "$M" "$A" > "$TMPD/c/block.go"
printf '#!/usr/bin/env bash\ncat <<EOF\nresidue looks like: %s for RED\nEOF\n' "$M" > "$TMPD/c/here.sh"
printf 'package z\nvar pat = `%s for RED`\n' "$M" > "$TMPD/c/raw.go"
run_arm "carrier C1-C5 string/docstring/block/heredoc/raw mentions stay clean" "$TMPD/c" 0 "scanned 5 file(s); 0 hit(s)"

# C7 is the arm that actually reaches the same-length string mask: the
# comment INTRODUCER itself lives inside the literal. Without the mask the
# gate treats `# <marker>` inside a pattern registry as a real comment and
# refuses the file — a false-positive refusal (§11.4.201(1)).
mk c7
printf 'MARKER_RE = "# %s for RED"\nFAKE_RE = "# %s pass"\n' "$M" "$A" > "$TMPD/c7/pat.py"
printf 'package z\nvar marker = "// %s for RED"\nvar fake = "// %s pass"\n' "$M" "$A" > "$TMPD/c7/pat.go"
run_arm "carrier C7 comment introducer inside a string literal stays clean" "$TMPD/c7" 0 "scanned 2 file(s); 0 hit(s)"

mk c6; printf '#!/usr/bin/env bash\n# the scanner hunts %s markers  %s documents the marker, not residue\necho ok\n' "$M" "$W" > "$TMPD/c6/h.sh"
run_arm "carrier C6 audited waiver passes AND is printed" "$TMPD/c6" 0 "1 audited waiver(s)"
# §11.4.201(5): a waiver that is silent is a bypass. Assert it is echoed.
OUT_C6="$(bash "$GATE" "$TMPD/c6" 2>&1)"
if printf '%s' "$OUT_C6" | grep -q '~ WAIVED'; then
    echo "PASS: carrier C6 waiver is visibly echoed (never a silent bypass)"
else
    echo "FAIL: carrier C6 waiver was honoured SILENTLY — §11.4.201(5) violated"
    printf '%s\n' "$OUT_C6" | sed 's/^/      /'; fails=$((fails + 1))
fi

# ---------------------------------------------------------------------------
# BLIND arm — a walk that sees nothing must ERROR, never report clean.
# §11.4.201(6): a blind instrument and a clean corpus return the same zero.
# ---------------------------------------------------------------------------
mk b1
run_arm "blind B1 zero-file walk ERRORs (rc=2), never 'clean'" "$TMPD/b1" 2 "walked ZERO files"

# ---------------------------------------------------------------------------
# CONTROL NEEDLE (§11.4.201(7)(b)) — the load-bearing arm.
# The golden-FALSE and carrier arms above assert an ABSENCE. An absence is
# not evidence until the instrument is proven able to SEE through the SAME
# path. So: plant a known-present residue INTO the directory that just read
# clean, invoke the gate identically, and require it to flip.
# ---------------------------------------------------------------------------
printf 'def h():\n    return True  # %s for RED\n' "$M" > "$TMPD/f1/needle.py"
NEEDLE_OUT="$(bash "$GATE" "$TMPD/f1" 2>&1)"; NEEDLE_RC=$?
if [[ "$NEEDLE_RC" -eq 1 ]] && printf '%s' "$NEEDLE_OUT" | grep -qF 'needle.py'; then
    echo "PASS: control needle — the same path that read clean DOES see a planted residue"
else
    echo "FAIL: control needle — gate did not fire on a known-present residue in the"
    echo "      directory that just read clean (rc=$NEEDLE_RC). Every clean arm above"
    echo "      is therefore a blind zero, not evidence (§11.4.201(6))."
    printf '%s\n' "$NEEDLE_OUT" | sed 's/^/      /'; fails=$((fails + 1))
fi
rm -f "$TMPD/f1/needle.py"

echo
if [[ "$fails" -gt 0 ]]; then
    echo "=== META-TEST FAIL: $fails arm(s) diverged — the gate is not trustworthy ==="
    exit 1
fi
echo "=== META-TEST PASS: gate fires on every residue shape, stays quiet on every"
echo "    carrier, refuses a blind walk, and is proven seeing by a control needle ==="
exit 0
