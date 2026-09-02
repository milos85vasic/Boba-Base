#!/usr/bin/env bash
# check_cm_no_unscoped_live_destruction.sh — CM-NO-UNSCOPED-LIVE-DESTRUCTION
#
# INVARIANT: no file in the test/challenge tree may delete from the live
# qBittorrent instance on the basis of an UNFILTERED full-instance listing
# unless it first computes a set difference against a baseline snapshot.
#
# ---------------------------------------------------------------------------
# THE DEFECT THIS GATE MAKES IMPOSSIBLE TO REINTRODUCE
# ---------------------------------------------------------------------------
# tests/stress/test_search_stress.py:_purge_qbittorrent_torrents() (landed
# a684b2f, 2026-04-20) did exactly this:
#
#     torrents = json.loads(GET /api/v2/torrents/info)   # EVERY torrent
#     hashes   = "|".join(t["hash"] for t in torrents)   # including the
#     POST /api/v2/torrents/delete  hashes=<all>         # operator's own
#
# from an `autouse` fixture running before every stress test. On the
# operator's live instance that silently de-registered their entire library.
# `deleteFiles=false` spared the bytes on disk; the session, categories, tags,
# ratio history and seeding state were destroyed and are not recoverable from
# the files. It was found by an agent reading source — NO gate caught it,
# which per §11.4.238 makes the coverage escape itself a defect of equal
# standing. This gate is the closing half of that escape.
#
# ---------------------------------------------------------------------------
# THE RULE (decidable, source-level, no live stack required)
# ---------------------------------------------------------------------------
# For every scanned file that calls a DESTRUCTIVE endpoint
# (torrents/delete, torrents/deleteTags, torrents/deleteCategories):
#
#   (a) If the file never performs an UNFILTERED full-instance read — that is,
#       every `torrents/info` / `torrents/tags` it issues is narrowed by
#       ?tag= / ?hashes= / ?category= / ?filter=, or it has no such read at
#       all — then its delete targets are scoped BY CONSTRUCTION (a specific
#       infohash it just added, a tag it just minted). PASS.
#
#   (b) If the file DOES perform an unfiltered full-instance read AND deletes,
#       it MUST also contain a SET DIFFERENCE against a baseline
#       (`added = after - before` shaped). Without one, the delete list is
#       "whatever the operator happens to own". FAIL.
#
# Comments are STRIPPED before matching (§11.4.201(7)(a)): a token that merely
# MENTIONS a set difference in prose is a CARRIER, not the thing. A file whose
# only `- before` lives in a docstring explaining the rule must still FAIL.
#
# ---------------------------------------------------------------------------
# HONEST BOUNDARY (§11.4.6) — what this gate does NOT prove
# ---------------------------------------------------------------------------
# Scoping evidence is matched at FILE granularity, not per-call-site. A file
# that legitimately diff-scopes one delete and unscopes another would pass.
# That is a deliberate, conservative approximation: it eliminates the entire
# unscoped-purge shape without generating false-positive refusals on the
# repo's existing correct code, and per §11.4.201(1) a gate that refuses
# correct code is as bad as one that misses the defect. Per-call-site scoping
# is a tracked strengthening, not a claim made here.
#
# This gate reads SOURCE. It cannot know whether the cleanup actually ran.
# The runtime-layer observer for its sibling defect class is
# scripts/pre_build/check_cm_no_test_tag_debris.sh.
#
# Exit: 0 clean | 1 unscoped destruction present | 2 harness/blind error.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${CM_UNSCOPED_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# Scan roots: every tree that may drive the live instance.
SCAN_ROOTS=(tests challenges)

DESTRUCTIVE_RE='api/v2/torrents/(delete|deleteTags|deleteCategories)'
# An unfiltered read: an ENDPOINT PATH `api/v2/torrents/info|tags` NOT
# immediately narrowed by a query string. `torrents/info?hashes=x` is scoped;
# `torrents/info"` is not.
#
# The `api/v2/` prefix is load-bearing (§11.4.201(7)(a) carrier-vs-thing): the
# bare token `torrents/info` also occurs in PROSE — a comment, or an operator
# message such as
#     QBIT_NOTE="infohash not (yet) in torrents/info — ..."
# in challenges/extension/*.sh, which issue only the SCOPED
# `/api/v2/torrents/info?hashes=${INFOHASH}`. Without the prefix this gate
# refused both of those correct files: a §11.4.201(1) false-positive refusal,
# caught by running the gate against the real tree during authoring.
UNFILTERED_READ_RE='api/v2/torrents/(info|tags)([^?A-Za-z0-9_-]|$)'
# A set difference against a baseline. Python `after - before`, shell/other
# `${AFTER} - ${BEFORE}`; the right-hand name must END in `before`/`BEFORE`
# so the token names a baseline rather than any subtraction.
SETDIFF_RE='-[[:space:]]*[A-Za-z_$({]*[A-Za-z0-9_]*[Bb][Ee][Ff][Oo][Rr][Ee]'

# strip_comments <file> — remove whole-line and trailing `#` comments so a
# prose mention can never satisfy the SETDIFF check.
strip_comments() {
    sed -e 's/[[:space:]]#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

# code_only <file> — the body used for the SETDIFF check ONLY.
#
# Comments are not the only carrier: a Python DOCSTRING is neither a `#`
# comment nor code, and a docstring reading "added = after - before" satisfied
# a comment-stripping check while the file contained no such operation. Caught
# during authoring against tests/unit/test_stress_purge_scoping.py, whose
# module docstring alone was carrying the pass.
#
# So for .py files this additionally drops every STRING LITERAL via the
# tokenizer. Applied to the SETDIFF check only — never to the endpoint checks,
# because an endpoint path legitimately lives inside a string
# (f"{url}/api/v2/torrents/delete") whereas a set-difference operation never
# does. Stripping strings for the endpoint checks would blind the gate
# completely.
code_only() {
    local f="$1"
    if [[ "$f" == *.py ]] && command -v python3 >/dev/null 2>&1; then
        python3 - "$f" <<'PYEOF' 2>/dev/null || strip_comments "$f"
import io, sys, tokenize
src = open(sys.argv[1], "rb").read()
out = []
try:
    for tok in tokenize.tokenize(io.BytesIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        if tok.type == tokenize.FSTRING_MIDDLE:
            continue
        out.append(tok.string)
except Exception:
    # Unparseable source: fall back to the raw text rather than reporting an
    # empty body, which would read as "no set difference" and FAIL a file the
    # gate simply could not tokenize.
    sys.stdout.write(src.decode("utf-8", "replace"))
    raise SystemExit(0)
sys.stdout.write(" ".join(out))
PYEOF
    else
        strip_comments "$f"
    fi
}

# --- EXEMPTION FENCE (§11.4.224(E) exclusion-list discipline) ---------------
# Some files match the endpoint patterns without ever being a CLIENT of a live
# instance: a stub HTTP SERVER matches `self.path.startswith("/api/v2/
# torrents/delete")`, and this gate's own meta-test embeds the pre-fix shape
# as a fixture on purpose. Refusing those is a §11.4.201(1) false-positive.
#
# An exemption is legal ONLY via a marker line IN THE FILE naming a reason
# from the CLOSED set below. It is never a silent skip: every exemption is
# printed on every run, so a marker slapped onto a genuine destroyer is
# visible in the gate's own output rather than hidden in a side list.
#
#     # CM-NO-UNSCOPED-LIVE-DESTRUCTION: EXEMPT reason=<reason> — <why>
#
# Closed reason set:
#   stub_server_not_a_client — the file IMPLEMENTS the endpoints (a test
#       double); it issues no request against any live instance.
#   gate_fixture — the file deliberately embeds the forbidden shape as a
#       detector fixture (this gate's own meta-test).
EXEMPT_RE='CM-NO-UNSCOPED-LIVE-DESTRUCTION:[[:space:]]+EXEMPT[[:space:]]+reason=(stub_server_not_a_client|gate_fixture)[[:space:]]'

# classify <file> -> prints "PASS" | "EXEMPT:<reason>" | "FAIL" ; used by both
# the scan and the control needle so the needle exercises the SAME path
# (§11.4.201(7)(b)).
classify() {
    local f="$1" body setdiff_body marker
    marker="$(grep -oE -- "$EXEMPT_RE" "$f" 2>/dev/null | head -1 || true)"
    if [[ -n "$marker" ]]; then
        echo "EXEMPT:$(printf "%s" "${marker#*reason=}" | tr -d "[:space:]")"
        return
    fi
    body="$(strip_comments "$f")"
    setdiff_body="$(code_only "$f")"
    # `--` is load-bearing: SETDIFF_RE begins with `-`, which grep would
    # otherwise read as an option flag, erroring out and silently classifying
    # every scoped file as a violation. The golden-FALSE needle below caught
    # exactly that during authoring (§11.4.201(1)).
    printf '%s' "$body" | grep -qE -- "$DESTRUCTIVE_RE" || { echo "PASS"; return; }
    printf '%s' "$body" | grep -qE -- "$UNFILTERED_READ_RE" || { echo "PASS"; return; }
    printf '%s' "$setdiff_body" | grep -qE -- "$SETDIFF_RE" || { echo "FAIL"; return; }
    echo "PASS"
}

# --- CONTROL NEEDLE (§11.4.201(7)(b)) ---------------------------------------
# A "no violations" result is a NULL, and a blind classifier returns the same
# quiet zero as a genuinely clean tree. Prove the classifier can SEE the
# pre-fix shape, and does NOT fire on the diff-scoped shape, through the same
# strip+grep path — before trusting any zero.
NEEDLE_DIR="$(mktemp -d)"
trap 'rm -rf "$NEEDLE_DIR"' EXIT

cat > "$NEEDLE_DIR/needle_bad.py" <<'NEEDLE_BAD'
resp = opener.open(f"{qbit_url}/api/v2/torrents/info", timeout=10)
hashes = "|".join(t["hash"] for t in json.loads(resp.read()))
opener.open(urllib.request.Request(f"{qbit_url}/api/v2/torrents/delete", data=hashes))
NEEDLE_BAD

cat > "$NEEDLE_DIR/needle_good.py" <<'NEEDLE_GOOD'
resp = opener.open(f"{qbit_url}/api/v2/torrents/info", timeout=10)
after = {t["hash"] for t in json.loads(resp.read())}
added = after - before
opener.open(urllib.request.Request(f"{qbit_url}/api/v2/torrents/delete", data=added))
NEEDLE_GOOD

# The false-positive guard: a file whose ONLY set-difference token is inside a
# comment must still be seen as a violation (carrier, not the thing).
cat > "$NEEDLE_DIR/needle_carrier.py" <<'NEEDLE_CARRIER'
# The correct shape here would be: added = after - before
resp = opener.open(f"{qbit_url}/api/v2/torrents/info", timeout=10)
hashes = "|".join(t["hash"] for t in json.loads(resp.read()))
opener.open(urllib.request.Request(f"{qbit_url}/api/v2/torrents/delete", data=hashes))
NEEDLE_CARRIER

NEEDLE_ERR=0
[[ "$(classify "$NEEDLE_DIR/needle_bad.py")" == "FAIL" ]] || {
    echo "HARNESS ERROR: control needle not seen — the unscoped shape did not classify FAIL" >&2
    NEEDLE_ERR=1
}
[[ "$(classify "$NEEDLE_DIR/needle_good.py")" == "PASS" ]] || {
    echo "HARNESS ERROR: golden-FALSE needle fired — the diff-scoped shape classified FAIL" >&2
    NEEDLE_ERR=1
}
[[ "$(classify "$NEEDLE_DIR/needle_carrier.py")" == "FAIL" ]] || {
    echo "HARNESS ERROR: carrier needle passed — a commented-out set difference satisfied the check" >&2
    NEEDLE_ERR=1
}
[[ "$NEEDLE_ERR" -eq 0 ]] || exit 2

# --- Scan -------------------------------------------------------------------
CANDIDATES="$(mktemp)"
trap 'rm -rf "$NEEDLE_DIR" "$CANDIDATES"' EXIT

FOUND_ROOT=0
for root in "${SCAN_ROOTS[@]}"; do
    [[ -d "$REPO_ROOT/$root" ]] || continue
    FOUND_ROOT=1
    # `--include`/`--exclude-dir` MUST precede `--`; placed after it they are
    # read as filenames and the filter silently vanishes, which pulled stale
    # `__pycache__/*.pyc` bytecode of the PRE-FIX source into the candidate
    # list during authoring. Compiled artifacts are not source and can carry a
    # defect that no longer exists in the tree.
    grep -rlE --include='*.py' --include='*.sh' --include='*.bash' \
        --exclude-dir='__pycache__' --exclude-dir='.git' --exclude-dir='node_modules' \
        -- "$DESTRUCTIVE_RE" "$REPO_ROOT/$root" 2>/dev/null >> "$CANDIDATES" || true
done

if [[ "$FOUND_ROOT" -eq 0 ]]; then
    echo "HARNESS ERROR: none of the scan roots (${SCAN_ROOTS[*]}) exist under $REPO_ROOT" >&2
    exit 2
fi

sort -u -o "$CANDIDATES" "$CANDIDATES"
CANDIDATE_COUNT=$(grep -c . "$CANDIDATES" || true)

VIOLATIONS=()
EXEMPTIONS=()
while IFS= read -r f; do
    [[ -n "$f" ]] || continue
    verdict="$(classify "$f")"
    case "$verdict" in
        FAIL)    VIOLATIONS+=("${f#"$REPO_ROOT"/}") ;;
        EXEMPT:*) EXEMPTIONS+=("${f#"$REPO_ROOT"/} [${verdict#EXEMPT:}]") ;;
    esac
done < "$CANDIDATES"

# Exemptions are ALWAYS printed, pass or fail — an exemption nobody sees is a
# silent skip, which is what the fence exists to prevent.
if [[ "${#EXEMPTIONS[@]}" -gt 0 ]]; then
    echo "CM-NO-UNSCOPED-LIVE-DESTRUCTION: ${#EXEMPTIONS[@]} exempted file(s):"
    for e in "${EXEMPTIONS[@]}"; do echo "    $e"; done
fi

if [[ "${#VIOLATIONS[@]}" -gt 0 ]]; then
    echo "CM-NO-UNSCOPED-LIVE-DESTRUCTION: FAIL — ${#VIOLATIONS[@]} file(s) delete from the live instance without diff-scoping"
    for v in "${VIOLATIONS[@]}"; do
        echo "    $v"
        grep -nE -- "$UNFILTERED_READ_RE|$DESTRUCTIVE_RE" "$REPO_ROOT/$v" 2>/dev/null \
            | head -6 | sed 's/^/        /'
    done
    echo
    echo "  Each of these reads the FULL torrent list and deletes from it. On the"
    echo "  operator's live instance that destroys THEIR library, not test debris."
    echo
    echo "  Fix: snapshot before, diff after, delete only the difference —"
    echo "       before = <snapshot>()                   # taken while pristine"
    echo "       added  = <snapshot>() - before          # this suite's own adds"
    echo "       delete(added)                           # never a hash in before"
    echo "  A baseline that could not be READ must disarm the delete entirely"
    echo "  (None is not an empty set). See the worked pattern in:"
    echo "       tests/integration/test_webui_bridge_auth_live.py"
    echo "       tests/stress/test_search_stress.py"
    exit 1
fi

echo "CM-NO-UNSCOPED-LIVE-DESTRUCTION: PASS — ${CANDIDATE_COUNT} file(s) issue destructive calls, all scoped"
exit 0
