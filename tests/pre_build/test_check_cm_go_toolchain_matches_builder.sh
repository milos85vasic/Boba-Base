#!/usr/bin/env bash
# test_check_cm_go_toolchain_matches_builder.sh — §1.1 paired-mutation
# meta-test for scripts/pre_build/check_cm_go_toolchain_matches_builder.sh
# (CM-GO-TOOLCHAIN-MATCHES-BUILDER).
#
# TDD (§11.4.43/§11.4.115/§11.4.224): this meta-test is authored BEFORE the
# gate is trusted, and was observed to FAIL (rc 2, "gate script not found")
# before the gate existed. A gate whose mutation was never observed to make it
# FAIL is unvalidated instrumentation and mints no verdicts (§11.4.115(F)).
#
# WHY A GATE AT ALL (BOB-153): qBitTorrent-go/go.mod declared `go 1.26.2` while
# qBitTorrent-go/Dockerfile built `FROM golang:1.23-alpine`. The two values are
# a floor and its satisfier, but NOTHING IN THE REPOSITORY COMPARED THEM — so
# they were introduced already-divergent in the same commit (4002c57) and
# stayed that way for four months, until the Go profile was actually needed and
# could not build. That is the §11.4.227 prose-not-seam gap exactly: the
# invariant was real, nobody had written it down as a check.
#
# WHAT THE GATE ASSERTS — THE REAL CONDITION, NOT A PROXY (§11.4.201):
#   builder_toolchain_version >= go.mod_go_directive
# NOT string equality. Equality would refuse `golang:1.27-alpine` against a
# `go 1.26.2` directive — a builder that satisfies the floor perfectly well.
# §11.4.201(1) makes that false-POSITIVE refusal exactly as forbidden as a
# false pass, so the comparison is a real version comparison in both
# directions.
#
# Fixtures (each a self-contained fake repo root):
#   good-exact          -> rc 0  directive 1.26.2, builder 1.26.2  (the fix)
#   good-newer-patch    -> rc 0  directive 1.26.2, builder 1.26.7
#   good-newer-minor    -> rc 0  directive 1.26.2, builder 1.27.0
#                                  ^ the §11.4.201(1) FALSE-POSITIVE GUARD: a
#                                    strictly-newer builder satisfies the floor
#                                    and MUST NOT be refused.
#   good-floating-ok    -> rc 0  directive 1.26 (no patch), builder 1.26-alpine
#                                  ^ a patch-less tag DOES satisfy a patch-less
#                                    directive; refusing it would be a false
#                                    positive.
#   good-carrier        -> rc 0  a COMMENT quoting `FROM golang:1.23-alpine`
#                                above a real `FROM golang:1.26.2-alpine`.
#                                §11.4.201(7)(a) carrier-vs-thing: a line that
#                                MENTIONS the old builder is not the builder.
#                                A substring-matching gate fails this fixture.
#   warn-floating       -> rc 0  directive 1.26.2, builder 1.26-alpine. Cannot
#                                be PROVEN statically (tag 1.26 names no patch)
#                                but is not known-broken, so it is a
#                                NON-BLOCKING WARN, never a FAIL. The harness
#                                asserts the WARN is actually EMITTED — a warn
#                                that is silently dropped is a §11.4.201(6)
#                                false-null.
#   bad-bob153          -> rc 1  directive 1.26.2, builder 1.23  (THE DEFECT.
#                                This fixture is the regression guard: it must
#                                FAIL against the pre-fix shape forever.)
#   bad-inverted        -> rc 1  directive 1.27.0, builder 1.26.2 — drift in
#                                the OTHER direction, i.e. someone raises
#                                go.mod and forgets the Dockerfile. This is the
#                                likelier future recurrence and is guarded.
#   bad-lower-patch     -> rc 1  directive 1.26.5, builder 1.26.2
#   bad-unparseable-tag -> rc 1  `FROM golang:latest` names no version, so the
#                                invariant is unresolvable. §11.4.201(4):
#                                conservative-safe refusal WITH an honest
#                                message, never a silent pass.
#   bad-zero-pairs      -> rc 1  a go.mod with no golang Dockerfile anywhere:
#                                zero pairs checked. A blind instrument and a
#                                clean tree both return a quiet zero
#                                (§11.4.201(6)), so zero MUST fail loudly.
#   real-tree           -> rc 0  the actual boba checkout after the BOB-153 fix.
#
# A gate that PASSes any golden-bad, or FAILs any golden-good or the real tree,
# is itself the bluff (§11.4.107(10)) and this harness reports it.
#
# Usage:   bash tests/pre_build/test_check_cm_go_toolchain_matches_builder.sh
# Inputs:  none (no stdin, no env input).
# Outputs: per-case PASS/FAIL lines on stdout; failure diagnostics on stdout.
# Side-effects: creates and removes one `mktemp -d` tree; the real-tree case is
#               a read-only scan and mutates nothing in the repository.
# Dependencies: bash, mktemp, sed, grep.
#
# Exit codes:
#   0 — every fixture (+ the real-tree smoke check) matched its expectation.
#   1 — one or more checks diverged from the expected outcome.
#   2 — harness/environment error (gate missing or not executable).
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.18 §11.4.43 §11.4.107(10) §11.4.115
#             §11.4.135 §11.4.201 §11.4.224 §11.4.227 §11.4.246 §11.4.264.

set -euo pipefail

HARNESS_NAME="test_check_cm_go_toolchain_matches_builder"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GATE="$REPO_ROOT/scripts/pre_build/check_cm_go_toolchain_matches_builder.sh"

if [[ ! -f "$GATE" ]]; then
    echo "FAIL($HARNESS_NAME): gate script not found at $GATE" >&2
    echo "  (expected on the RED run — this meta-test is authored FIRST per" >&2
    echo "   §11.4.115/§11.4.224; implement the gate next)" >&2
    exit 2
fi
if [[ ! -x "$GATE" ]]; then
    echo "FAIL($HARNESS_NAME): gate script not executable at $GATE" >&2
    exit 2
fi

TMPDIR_ROOT="$(mktemp -d -t go_toolchain_meta.XXXXXX)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

fails=0

run_gate() {
    # $1 = fixture root. Results returned via globals rather than $(...) so a
    # non-zero gate exit is not swallowed by command substitution under `set -e`.
    local root="$1" out err rc
    out="$(mktemp -p "$TMPDIR_ROOT")"
    err="$(mktemp -p "$TMPDIR_ROOT")"
    set +e
    "$GATE" --root "$root" >"$out" 2>"$err"
    rc=$?
    set -e
    GOT_RC="$rc"; GOT_OUT="$out"; GOT_ERR="$err"
}

assert_rc() {
    local name="$1" want_rc="$2"
    if [[ "$GOT_RC" -eq "$want_rc" ]]; then
        echo "PASS: $name (rc=$GOT_RC as expected)"
    else
        echo "FAIL: $name — expected rc=$want_rc got rc=$GOT_RC"
        echo "  --- stdout ---"; sed 's/^/    /' "$GOT_OUT"
        echo "  --- stderr ---"; sed 's/^/    /' "$GOT_ERR"
        fails=$((fails + 1))
    fi
}

assert_output_matches() {
    # Asserts the gate SAID something, not merely that it exited a certain way.
    # A WARN that no longer prints is invisible, and an invisible warn is the
    # §11.4.201(6) false-null this guards against.
    local name="$1" pattern="$2"
    if grep -qE "$pattern" "$GOT_OUT" "$GOT_ERR"; then
        echo "PASS: $name (output matched /$pattern/)"
    else
        echo "FAIL: $name — expected output matching /$pattern/"
        echo "  --- stdout ---"; sed 's/^/    /' "$GOT_OUT"
        echo "  --- stderr ---"; sed 's/^/    /' "$GOT_ERR"
        fails=$((fails + 1))
    fi
}

# ---------------------------------------------------------------------------
# make_fixture <name> <go-directive> <dockerfile-body>
#   Builds a minimal fake repo root holding one Go module whose Dockerfile
#   sits beside its go.mod — the same layout as qBitTorrent-go/.
# ---------------------------------------------------------------------------
make_fixture() {
    local name="$1" directive="$2" body="$3"
    local root="$TMPDIR_ROOT/$name"
    mkdir -p "$root/svc"
    cat > "$root/svc/go.mod" <<EOF
module example.com/$name

go $directive

require github.com/stretchr/testify v1.11.1
EOF
    printf '%s\n' "$body" > "$root/svc/Dockerfile"
    echo "$root"
}

echo "=== $HARNESS_NAME — CM-GO-TOOLCHAIN-MATCHES-BUILDER §1.1 meta-test ==="
echo

# --- golden-good ------------------------------------------------------------
r="$(make_fixture good-exact 1.26.2 'FROM golang:1.26.2-alpine AS builder
RUN go build ./...

FROM alpine:3.19')"
run_gate "$r"; assert_rc "good-exact (1.26.2 builder satisfies 1.26.2 directive)" 0

r="$(make_fixture good-newer-patch 1.26.2 'FROM golang:1.26.7-alpine AS builder
RUN go build ./...')"
run_gate "$r"; assert_rc "good-newer-patch (1.26.7 satisfies 1.26.2)" 0

r="$(make_fixture good-newer-minor 1.26.2 'FROM golang:1.27.0-alpine AS builder
RUN go build ./...')"
run_gate "$r"; assert_rc "good-newer-minor FALSE-POSITIVE GUARD (1.27.0 satisfies 1.26.2)" 0

r="$(make_fixture good-floating-ok 1.26 'FROM golang:1.26-alpine AS builder
RUN go build ./...')"
run_gate "$r"; assert_rc "good-floating-ok (patch-less tag satisfies patch-less directive)" 0

r="$(make_fixture good-carrier 1.26.2 '# Historical note: this image used to be FROM golang:1.23-alpine
# before BOB-153. Do not reintroduce that.
FROM golang:1.26.2-alpine AS builder
RUN go build ./...')"
run_gate "$r"; assert_rc "good-carrier CARRIER-VS-THING (a comment quoting the old builder is not the builder)" 0

# --- non-blocking WARN ------------------------------------------------------
r="$(make_fixture warn-floating 1.26.2 'FROM golang:1.26-alpine AS builder
RUN go build ./...')"
run_gate "$r"
assert_rc "warn-floating (unprovable but not known-broken -> non-blocking)" 0
assert_output_matches "warn-floating EMITS the warn (a silent warn is a false-null)" 'WARN'

# --- golden-bad -------------------------------------------------------------
r="$(make_fixture bad-bob153 1.26.2 'FROM golang:1.23-alpine AS builder
RUN go build ./...')"
run_gate "$r"; assert_rc "bad-bob153 REGRESSION GUARD (the exact pre-fix shape)" 1

r="$(make_fixture bad-inverted 1.27.0 'FROM golang:1.26.2-alpine AS builder
RUN go build ./...')"
run_gate "$r"; assert_rc "bad-inverted (go.mod raised, Dockerfile forgotten)" 1

r="$(make_fixture bad-lower-patch 1.26.5 'FROM golang:1.26.2-alpine AS builder
RUN go build ./...')"
run_gate "$r"; assert_rc "bad-lower-patch (1.26.2 does not satisfy 1.26.5)" 1

r="$(make_fixture bad-unparseable-tag 1.26.2 'FROM golang:latest AS builder
RUN go build ./...')"
run_gate "$r"; assert_rc "bad-unparseable-tag (unresolvable -> conservative refusal)" 1

# zero-pairs: a Go module with no golang Dockerfile anywhere in the tree.
zp="$TMPDIR_ROOT/bad-zero-pairs"
mkdir -p "$zp/svc"
printf 'module example.com/zp\n\ngo 1.26.2\n' > "$zp/svc/go.mod"
printf 'FROM alpine:3.19\nRUN echo no-go-builder-here\n' > "$zp/svc/Dockerfile"
run_gate "$zp"; assert_rc "bad-zero-pairs BLIND-INSTRUMENT GUARD (zero checked must fail loudly)" 1

# --- real tree --------------------------------------------------------------
run_gate "$REPO_ROOT"
assert_rc "real-tree (the actual boba checkout, post-BOB-153-fix)" 0

echo
if [[ "$fails" -ne 0 ]]; then
    echo "=== $HARNESS_NAME: $fails check(s) FAILED ==="
    exit 1
fi
echo "=== $HARNESS_NAME: all checks passed ==="
exit 0
