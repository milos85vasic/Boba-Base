#!/usr/bin/env bash
# test_check_cm_closure_seam_binds.sh — §1.1 paired-mutation meta-test for
# scripts/pre_build/check_cm_closure_seam_binds.sh (CM-CLOSURE-SEAM-BINDS).
#
# WHY (§11.4.115(F)): a checker never observed FAILING is unvalidated
# instrumentation, and a checker never observed PASSING on a healthy tree
# is a FAIL-bluff waiting to be switched off (§11.4.201(1)). This harness
# drives the REAL gate against HERMETIC temp git repositories and temp
# SQLite DBs with KNOWN outcomes — never the live checkout, never the
# live docs/workable_items.db (which concurrent agents write).
#
# GOLDEN-BAD (gate MUST exit 1 — a miss here means stale rows ship):
#   bad-1  `closes <id>` + row Queued           -> CONTRADICTION
#   bad-2  `fix(<id>): ...` + row Queued        -> UNRECONCILED
#   bad-3  `<id>: ...` bare prefix + Queued     -> UNRECONCILED
#   bad-4  work commit declares an id with NO row -> UNTRACKED-ID
#   bad-5  compact run `closes <a>/<b>` + Queued -> both ids reported
#   bad-6  a genuine flagless `diff --db` caller -> CHECK B FAIL
#
# GOLDEN-GOOD (gate MUST exit 0 — a hit here is a false positive, and a
# gate that flags correctly-tracked work gets disabled within a week):
#   good-1 every declared id terminal
#   good-2 declared id is `In progress` (the row already tells the truth)
#
# CARRIER CONTROLS (gate MUST exit 0 — these merely MENTION an id):
#   car-1  `docs(tracker): file <id>`      filing is not doing
#   car-2  `docs/qa/<id>/evidence.md`      path component
#   car-3  work commit QUOTING "closes <id>" verbatim
#   car-4  `docs(<id>): ...`               non-work commit type
#   car-5  `<id>` mentioned only in body prose, no closure keyword
#   car-6  gerund: "closing <id> requires ..." -- the gerund heads a noun
#          phrase that is the SUBJECT of "requires", i.e. a statement of what
#          closure would TAKE, not a declaration that it happened. Lives HERE,
#          outside the gate, because the gate's own --self-test is the PRODUCER:
#          a coherent revert (restore the regex AND drop its self-test line, one
#          file, one edit) sailed through this meta-test at 29/29 while this case
#          was absent -- the producer==oracle collapse (§11.4.249/§11.4.240).
#
# Exit: 0 all cases matched expectation; 1 divergence; 2 harness error.
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.107(10) §11.4.115 §11.4.201(1)(7) §1.1

set -euo pipefail

HARNESS="test_check_cm_closure_seam_binds"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE="$REPO_ROOT/scripts/pre_build/check_cm_closure_seam_binds.sh"

[[ -f "$GATE" ]] || { echo "FAIL($HARNESS): gate not found at $GATE" >&2; exit 2; }
[[ -x "$GATE" ]] || { echo "FAIL($HARNESS): gate not executable at $GATE" >&2; exit 2; }
command -v sqlite3 >/dev/null 2>&1 || { echo "SKIP($HARNESS): sqlite3 unavailable" >&2; exit 0; }
command -v git     >/dev/null 2>&1 || { echo "SKIP($HARNESS): git unavailable" >&2; exit 2; }

TMPROOT="$(mktemp -d -t closure_seam_meta.XXXXXX)"
cleanup() { rm -rf "$TMPROOT" 2>/dev/null || true; }
trap cleanup EXIT

FAILS=0
PASSES=0
PFX="ZZQ"   # deliberately NOT the project prefix: fixtures cannot be
            # confused with, nor accidentally read from, real history.

# ── hermetic fixture builder ─────────────────────────────────────────
# $1 = case name ; stdin = one commit subject per line ("<TAB>body" optional)
# Never touches the project repo: a fresh `git init` under $TMPROOT with
# its own identity and no hooks.
mk_repo() {
    local name="$1"
    local dir="$TMPROOT/$name"
    local subj body line
    mkdir -p "$dir"
    git -C "$dir" init -q -b main
    git -C "$dir" config user.email "meta@example.invalid"
    git -C "$dir" config user.name  "meta"
    git -C "$dir" config commit.gpgsign false
    local n=0
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        subj="${line%%$'\t'*}"
        body=""
        [[ "$line" == *$'\t'* ]] && body="${line#*$'\t'}"
        n=$((n + 1))
        echo "$n" > "$dir/f$n.txt"
        git -C "$dir" add -A
        if [[ -n "$body" ]]; then
            git -C "$dir" commit -q -m "$subj" -m "$body"
        else
            git -C "$dir" commit -q -m "$subj"
        fi
    done
    echo "$dir"
}

# $1 = repo dir ; remaining args = "ID=STATUS" pairs
mk_db() {
    local dir="$1"; shift
    local pair
    mkdir -p "$dir/docs"
    local db="$dir/docs/workable_items.db"
    sqlite3 "$db" "CREATE TABLE items (atm_id TEXT, status TEXT);" 
    for pair in "$@"; do
        sqlite3 "$db" "INSERT INTO items VALUES ('${pair%%=*}', '${pair#*=}');"
    done
    echo "$db"
}

# $1 label  $2 expected-exit  $3.. gate args
expect() {
    local label="$1" want="$2"; shift 2
    local out rc
    set +e
    out="$("$GATE" "$@" 2>&1)"
    rc=$?
    set -e
    if [[ "$rc" -eq "$want" ]]; then
        printf '  ok   %-52s exit=%d\n' "$label" "$rc"
        PASSES=$((PASSES + 1))
    else
        printf '  FAIL %-52s exit=%d want=%d\n' "$label" "$rc" "$want" >&2
        printf '%s\n' "$out" | sed 's/^/       | /' >&2
        FAILS=$((FAILS + 1))
    fi
    LAST_OUT="$out"
}

# assert the last gate output mentions a token (proves the RIGHT class fired,
# not merely that SOME failure occurred — a gate that fails for the wrong
# reason is still a bluff)
expect_mentions() {
    local label="$1" token="$2"
    if [[ "${LAST_OUT:-}" == *"$token"* ]]; then
        printf '  ok   %-52s mentions %s\n' "$label" "$token"
        PASSES=$((PASSES + 1))
    else
        printf '  FAIL %-52s does NOT mention %s\n' "$label" "$token" >&2
        FAILS=$((FAILS + 1))
    fi
}

echo "[$HARNESS] hermetic golden set (prefix=$PFX)"
echo "  --- GOLDEN-BAD: the gate MUST refuse ---"

D="$(printf 'fix(core): fan-out closes %s-001\n' "$PFX" | mk_repo bad1)"
B="$(mk_db "$D" "$PFX-001=Queued")"
expect "bad-1 closes + Queued -> CONTRADICTION" 1 --repo "$D" --db "$B" --prefix "$PFX"
expect_mentions "bad-1 class" "CONTRADICTION"

D="$(printf 'fix(002,%s-002): the real fix\n' "$PFX" | mk_repo bad2)"
B="$(mk_db "$D" "$PFX-002=Queued")"
expect "bad-2 scope work commit + Queued -> UNRECONCILED" 1 --repo "$D" --db "$B" --prefix "$PFX"
expect_mentions "bad-2 class" "UNRECONCILED"

D="$(printf '%s-003: build the checker\n' "$PFX" | mk_repo bad3)"
B="$(mk_db "$D" "$PFX-003=Queued")"
expect "bad-3 bare-id subject prefix + Queued" 1 --repo "$D" --db "$B" --prefix "$PFX"

D="$(printf 'feat(x,%s-404): work under an unfiled id\n' "$PFX" | mk_repo bad4)"
B="$(mk_db "$D" "$PFX-001=Queued")"
expect "bad-4 declared id has no row -> UNTRACKED-ID" 1 --repo "$D" --db "$B" --prefix "$PFX"
expect_mentions "bad-4 class" "UNTRACKED-ID"

D="$(printf 'fix(q): closes %s-005/006\n' "$PFX" | mk_repo bad5)"
B="$(mk_db "$D" "$PFX-005=Queued" "$PFX-006=Queued")"
expect "bad-5 compact run -> both ids" 1 --repo "$D" --db "$B" --prefix "$PFX"
expect_mentions "bad-5 first id"  "$PFX-005"
expect_mentions "bad-5 second id" "$PFX-006"

# CHECK B: a genuine flagless `diff --db` caller must be refused, and the
# three-echo-string shape that lives in the real tree must NOT be.
D="$TMPROOT/bad6"; mkdir -p "$D"
git -C "$D" init -q -b main
git -C "$D" config user.email "meta@example.invalid"; git -C "$D" config user.name meta
git -C "$D" config commit.gpgsign false
cat > "$D/caller.sh" <<'CALLER'
#!/usr/bin/env bash
# a comment quoting workable-items diff --db X  (carrier: MUST be ignored)
echo "running workable-items diff --db X"   # string carrier: MUST be ignored
"$WI_BIN" diff --db "$WI_DB"
CALLER
git -C "$D" add -A; git -C "$D" commit -q -m "chore: add caller"
B="$(mk_db "$D" "$PFX-050=Fixed (→ Fixed.md)")"
expect "bad-6 genuine flagless diff caller -> CHECK B FAIL" 1 --repo "$D" --db "$B" --prefix "$PFX"
expect_mentions "bad-6 names the caller line" "FLAGLESS-DIFF-CALLER"
# the SAME file with the flags added must pass -> proves CHECK B is not
# simply "any file mentioning diff fails"
sed -i 's|diff --db "$WI_DB"|diff --db "$WI_DB" --issues I.md --fixed F.md|' "$D/caller.sh"
git -C "$D" add -A; git -C "$D" commit -q -m "chore: pass the flags"
expect "bad-6b same caller WITH the flags -> PASS" 0 --repo "$D" --db "$B" --prefix "$PFX"

echo "  --- GOLDEN-GOOD: the gate MUST NOT fire (§11.4.201(1)) ---"

D="$(printf 'fix(002,%s-010): the fix\nfix(q): closes %s-011\n' "$PFX" "$PFX" | mk_repo good1)"
B="$(mk_db "$D" "$PFX-010=Fixed (→ Fixed.md)" "$PFX-011=Implemented (→ Fixed.md)")"
expect "good-1 every declared id terminal" 0 --repo "$D" --db "$B" --prefix "$PFX"

D="$(printf 'feat(%s-012): first slice of ongoing work\n' "$PFX" | mk_repo good2)"
B="$(mk_db "$D" "$PFX-012=In progress")"
expect "good-2 row already says 'In progress'" 0 --repo "$D" --db "$B" --prefix "$PFX"

echo "  --- CARRIER CONTROLS: a MENTION is not a status move ---"

D="$(printf 'docs(tracker): file %s-020 — count diverges\n' "$PFX" | mk_repo car1)"
B="$(mk_db "$D" "$PFX-020=Queued")"
expect "car-1 filing commit" 0 --repo "$D" --db "$B" --prefix "$PFX"

D="$(printf 'fix(x): refresh docs/qa/%s-021/closure-evidence.md\n' "$PFX" | mk_repo car2)"
B="$(mk_db "$D" "$PFX-021=Queued")"
expect "car-2 id as a path component" 0 --repo "$D" --db "$B" --prefix "$PFX"

D="$(printf 'fix(x): the ticket quotes "closes %s-022" verbatim\n' "$PFX" | mk_repo car3)"
B="$(mk_db "$D" "$PFX-022=Queued")"
expect "car-3 work commit QUOTING a closure phrase" 0 --repo "$D" --db "$B" --prefix "$PFX"

D="$(printf 'docs(%s-023): correct the port table\n' "$PFX" | mk_repo car4)"
B="$(mk_db "$D" "$PFX-023=Queued")"
expect "car-4 docs-type commit scoped to the id" 0 --repo "$D" --db "$B" --prefix "$PFX"

D="$(printf 'chore(x): tidy\tsee %s-024 for background\n' "$PFX" | mk_repo car5)"
B="$(mk_db "$D" "$PFX-024=Queued")"
expect "car-5 body-prose mention, no closure keyword" 0 --repo "$D" --db "$B" --prefix "$PFX"

D="$(printf 'docs(x): tidy\tclosing %s-025 requires an out-of-user-scope watchdog\n' "$PFX" | mk_repo car6)"
B="$(mk_db "$D" "$PFX-025=Queued")"
expect "car-6 gerund states what closure would TAKE" 0 --repo "$D" --db "$B" --prefix "$PFX"

echo "  --- COMMIT-SEAM mode (the binding seam) ---"
D="$(printf 'chore: init\n' | mk_repo seam)"
B="$(mk_db "$D" "$PFX-030=Queued" "$PFX-031=Fixed (→ Fixed.md)" "$PFX-032=In progress")"
expect "seam refuses a message declaring a Queued id" 1 \
    --repo "$D" --db "$B" --prefix "$PFX" --message "fix($PFX-030): land it"
expect "seam allows a message declaring a terminal id" 0 \
    --repo "$D" --db "$B" --prefix "$PFX" --message "fix($PFX-031): follow-up"
expect "seam allows a message declaring an In-progress id" 0 \
    --repo "$D" --db "$B" --prefix "$PFX" --message "fix($PFX-032): next slice"
expect "seam allows a filing message (carrier)" 0 \
    --repo "$D" --db "$B" --prefix "$PFX" --message "docs(tracker): file $PFX-030"
expect "seam ignores the pre-existing backlog (monotone)" 0 \
    --repo "$D" --db "$B" --prefix "$PFX" --message "chore(x): unrelated tidy-up"

echo "  --- honest SKIP + report-only + self-test ---"
D="$(printf 'chore: init\n' | mk_repo skipcase)"
expect "absent DB -> honest SKIP, exit 0 (§11.4.3)" 0 \
    --repo "$D" --db "$D/docs/nope.db" --prefix "$PFX"
D="$(printf 'fix(002,%s-040): the fix\n' "$PFX" | mk_repo ronly)"
B="$(mk_db "$D" "$PFX-040=Queued")"
expect "--report-only surfaces findings without blocking" 0 \
    --repo "$D" --db "$B" --prefix "$PFX" --report-only
expect_mentions "--report-only still NAMES the stale row" "$PFX-040"
expect "gate self-test (§11.4.107(10)) passes" 0 --self-test

echo
if [[ "$FAILS" -eq 0 ]]; then
    echo "[$HARNESS] PASS — $PASSES/$PASSES checks matched expectation"
    exit 0
fi
echo "[$HARNESS] FAIL — $FAILS of $((PASSES + FAILS)) checks diverged" >&2
exit 1
