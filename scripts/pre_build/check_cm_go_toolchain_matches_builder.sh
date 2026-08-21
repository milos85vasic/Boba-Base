#!/usr/bin/env bash
# check_cm_go_toolchain_matches_builder.sh — CM-GO-TOOLCHAIN-MATCHES-BUILDER
# static pre-build gate (BOB-153).
#
# Purpose:
#   Refuse any tree in which a Dockerfile's Go BUILDER IMAGE cannot satisfy the
#   `go` directive of the go.mod it builds. The two values are a floor and its
#   satisfier and must move together, but nothing in this repository compared
#   them — which is precisely why they drifted.
#
# FORENSIC ANCHOR (BOB-153, measured 2026-08-21):
#   qBitTorrent-go/go.mod declared `go 1.26.2` while qBitTorrent-go/Dockerfile
#   built `FROM golang:1.23-alpine`, so the Go profile could not build:
#       go: go.mod requires go >= 1.26.2 (running go 1.23.12; GOTOOLCHAIN=local)
#   `git log -p --follow` shows BOTH values were introduced by the SAME commit
#   (4002c57, 2026-04-22). This was never a drift over time — the two were born
#   divergent and nothing ever compared them, so the defect sat unnoticed for
#   four months until the profile was actually needed. That is the §11.4.227
#   prose-not-seam gap in its purest form: a real invariant that nobody had
#   written down as a check.
#
#   Beyond the build breakage, the mismatch blocked feature 002's quickstart
#   Scenario 6, which exists to confirm the operator-owned-writes fix reaches
#   EVERY service (FR-016). With the profile unbuildable, that service's
#   coverage rested on surface-equivalent reasoning rather than a live probe.
#
# WHY `go 1.26.2` WAS THE CORRECT FLOOR, NOT AN ASPIRATIONAL BUMP:
#   The directive is not an author's preference — it is forced by the
#   dependency graph. `github.com/getkin/kin-openapi v0.136.0`, a DIRECT
#   dependency, declares `go 1.26` in its own go.mod; gin v1.12.0,
#   modernc.org/sqlite and golang.org/x/net declare `go 1.25.0`. Go 1.21+
#   refuses to build a module whose dependency requires a newer toolchain, and
#   `go get` RAISES the directive automatically to satisfy it — reproduced in a
#   throwaway module, where `go get kin-openapi@v0.136.0` wrote exactly
#   `go 1.26.2` unprompted. So "lower the directive to match the builder" is
#   not an available option; it is dependency downgrades wearing a one-line
#   disguise. The builder image is the value that was wrong.
#
# WHAT THIS GATE ASSERTS — THE REAL CONDITION, NOT A PROXY (§11.4.201):
#       builder_toolchain_version >= go.mod `go` directive
#   NOT string equality. Equality is the tempting implementation and it is
#   wrong: it would refuse `golang:1.27-alpine` against a `go 1.26.2` directive
#   even though that builder satisfies the floor completely. §11.4.201(1) makes
#   such a false-POSITIVE refusal exactly as forbidden as a false pass — it
#   halts real work and teaches people to route around gates — so this compares
#   versions properly, in both directions.
#
# THE THREE-VALUED VERDICT, AND WHY THE MIDDLE VALUE EXISTS:
#   A tag naming only major.minor (`golang:1.26-alpine`) floats: today it
#   resolves to the newest 1.26.x, which satisfies a `go 1.26.2` directive, but
#   NOTHING IN THE TREE PROVES THAT — statically `1.26` reads as 1.26.0, which
#   does not. Failing it would refuse a build that demonstrably works
#   (§11.4.201(1)); passing it silently would assert something unverified
#   (§11.4.6). So it is a NON-BLOCKING WARN naming the fix (pin the patch),
#   following the precedent already set by check_cm_plugin_count.sh for the
#   README badge and §11.4.234's rule that a pre-build gate must not become the
#   reason a build cannot proceed over something that is not actually broken.
#   qBitTorrent-go/Dockerfile.jackett is exactly this shape today.
#
#   A tag naming NO version at all (`golang:latest`, `golang:alpine`) is
#   different: the invariant is unresolvable AND the build is unreproducible
#   (§11.4.246). That takes the conservative-safe refusal of §11.4.201(4) — a
#   FAIL that says honestly that it could not resolve, never a quiet pass.
#
# CARRIER VS THING (§11.4.201(7)(a)):
#   Only a real instruction line matches — `^[[:space:]]*FROM[[:space:]]+golang:`.
#   A comment MENTIONING an old builder ("this used to be FROM golang:1.23-alpine")
#   is a carrier, not a builder, and must not trip the gate. A substring scan
#   for `golang:1.23` would fail that distinction, and the paired meta-test's
#   `good-carrier` fixture holds the gate to it.
#
# EMBEDDED CONTROL NEEDLE (§11.4.201(7)(b)):
#   A quiet zero from a blind extractor is indistinguishable from a clean tree
#   (§11.4.201(6)). Before ANY result is trusted, both extractors are proven
#   able to SEE: a synthetic `FROM golang:` line is injected into an in-memory
#   copy of each Dockerfile and the extracted count must rise by exactly one,
#   and a synthetic directive is injected into each go.mod and must be read
#   back. Zero pairs discovered is likewise a FAIL, never a pass.
#
# SCOPE (consumer-owned DATA, §11.4.35 / §11.4.28 / §11.4.177):
#   FIRST-PARTY modules only. `submodules/` and `constitution/` are consumed BY
#   REFERENCE and owned upstream; refusing this repository's build over an
#   upstream repo's Dockerfile would be a refusal its owner here cannot fix.
#   A Go module with no golang-builder Dockerfile (cmd/boba-ctl, built on the
#   host) has no builder image to reconcile and is correctly not a pair.
#
# Usage:
#   check_cm_go_toolchain_matches_builder.sh              # this repository
#   check_cm_go_toolchain_matches_builder.sh --root DIR   # treat DIR as root
#   check_cm_go_toolchain_matches_builder.sh -v           # show every pair
#   check_cm_go_toolchain_matches_builder.sh --help
#
# Inputs:   optional --root DIR; no stdin; no env input.
# Outputs:  per-pair verdict table on stdout, the PASS line ALWAYS last (the
#           pre-build wiring reads it with `tail -n1`); findings + FAIL summary
#           on stderr.
# Side-effects: none (read-only; writes only to mktemp files it removes).
#           Signals nothing, so §11.4.263 has no surface here.
# Dependencies: bash, sed, grep, find, wc, mktemp.
#
# Verdict:
#   0 — PASS  (>=1 pair checked; every builder satisfies its go directive)
#   1 — FAIL  (a builder cannot satisfy its directive, a tag names no version,
#              or zero pairs were discovered)
#   2 — ERROR (usage error, or the embedded control needle proved an extractor
#              blind — in which case no count it returns is evidence)
#
# Cross-refs: §11.4.1 §11.4.6 §11.4.18 §11.4.35 §11.4.107(10) §11.4.115
#             §11.4.201 §11.4.224 §11.4.227 §11.4.234 §11.4.246 §11.4.264.

set -euo pipefail

SCRIPT_NAME="check_cm_go_toolchain_matches_builder"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Consumer-owned scope DATA (§11.4.35): directory names pruned from discovery.
# `submodules` and `constitution` are upstream-owned (§11.4.28/§11.4.177).
PRUNE_DIRS=".git node_modules vendor submodules constitution"

ROOT="$DEFAULT_ROOT"
VERBOSE=0

print_help() { sed -n '2,120p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) print_help; exit 0 ;;
        -v|--verbose) VERBOSE=1; shift ;;
        --root)
            [[ $# -ge 2 ]] || { echo "ERROR: --root requires a directory" >&2; exit 2; }
            ROOT="$2"; shift 2 ;;
        -*) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
        *) echo "ERROR: unexpected positional argument: $1" >&2; exit 2 ;;
    esac
done

[[ -d "$ROOT" ]] || { echo "ERROR: root is not a directory: $ROOT" >&2; exit 2; }
ROOT="$(cd "$ROOT" && pwd)"

TMP_DIR="$(mktemp -d -t cm_go_toolchain.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

# ---------------------------------------------------------------------------
# Extractors. Each is deliberately anchored to a real instruction line so a
# carrier that merely MENTIONS a value cannot be read as that value.
# ---------------------------------------------------------------------------

# builder_tags <dockerfile> — emit the raw image tag of every golang builder
# stage, one per line. Anchored at FROM, so comment lines never match.
builder_tags() {
    grep -E '^[[:space:]]*FROM[[:space:]]+golang:' "$1" 2>/dev/null \
        | sed -E 's/^[[:space:]]*FROM[[:space:]]+golang:([^[:space:]]+).*/\1/' || true
}

# go_directive <go.mod> — emit the version on the `go` line (first match).
go_directive() {
    grep -m1 -E '^go[[:space:]]+[0-9]' "$1" 2>/dev/null \
        | sed -E 's/^go[[:space:]]+([0-9][0-9.]*).*/\1/' || true
}

# tag_version <tag> — the leading numeric version of an image tag, or empty.
#   1.26.2-alpine   -> 1.26.2
#   1.26-alpine3.24 -> 1.26
#   latest / alpine -> (empty: names no version)
tag_version() {
    printf '%s' "${1%%-*}" | grep -E '^[0-9]+(\.[0-9]+)*$' || true
}

# ver_field <version> <n> — n'th dotted field, defaulting to 0 when absent.
ver_field() {
    local v="$1" n="$2" f
    f="$(printf '%s' "$v" | cut -d. -f"$n")"
    [[ -n "$f" && "$f" =~ ^[0-9]+$ ]] && printf '%s' "$f" || printf '0'
}

# has_patch <version> — true when the version names a third field.
has_patch() { [[ "$(printf '%s' "$1" | grep -o '\.' | wc -l | tr -d ' ')" -ge 2 ]]; }

# ---------------------------------------------------------------------------
# CONTROL NEEDLES (§11.4.201(7)(b)). A result from an unproven extractor is
# not evidence — prove each can SEE through the SAME code path first.
# ---------------------------------------------------------------------------
needle_dockerfile() {
    local file="$1" base needled probe
    base="$(builder_tags "$file" | wc -l | tr -d ' ')"
    probe="$TMP_DIR/needle_df_$$_$RANDOM"
    # The LEADING newline is load-bearing, not cosmetic. qBitTorrent-go/Dockerfile
    # ends WITHOUT a trailing newline (last byte `]`), so a bare `echo` appended
    # the synthetic stage onto the end of `CMD [...]` and the extractor correctly
    # did not see it — the needle caught a flaw in its own injection before any
    # verdict was trusted, which is precisely what a needle is for.
    { cat "$file"; printf '\nFROM golang:9.99.99-alpine AS synthetic_needle\n'; } > "$probe"
    needled="$(builder_tags "$probe" | wc -l | tr -d ' ')"
    rm -f "$probe"
    [[ "$needled" -eq $((base + 1)) ]]
}

needle_gomod() {
    local file="$1" probe got
    probe="$TMP_DIR/needle_gm_$$_$RANDOM"
    sed -E 's/^go[[:space:]]+[0-9][0-9.]*/go 9.99.99/' "$file" > "$probe"
    got="$(go_directive "$probe")"
    rm -f "$probe"
    [[ "$got" == "9.99.99" ]]
}

# ---------------------------------------------------------------------------
# Discovery. NOTE: `find` on this host is bfs, not GNU findutils. Only
# portable primaries (-name/-type/-prune/-print) are used; relative -newermt
# forms are REJECTED by bfs while printing nothing to stdout, which would turn
# a hard failure into a clean-looking empty result (§11.4.201(6)). find's
# stderr is therefore treated as fatal rather than ignored.
# ---------------------------------------------------------------------------
PRUNE_EXPR=()
for d in $PRUNE_DIRS; do
    [[ ${#PRUNE_EXPR[@]} -gt 0 ]] && PRUNE_EXPR+=(-o)
    PRUNE_EXPR+=(-name "$d")
done

FIND_ERR="$TMP_DIR/find.err"
DOCKERFILES="$TMP_DIR/dockerfiles.txt"
find "$ROOT" \( "${PRUNE_EXPR[@]}" \) -prune -o -type f -name 'Dockerfile*' -print \
    > "$DOCKERFILES" 2>"$FIND_ERR" || true
if [[ -s "$FIND_ERR" ]]; then
    echo "ERROR: find emitted diagnostics; a discovery derived from it is not evidence:" >&2
    sed 's/^/       /' "$FIND_ERR" >&2
    exit 2
fi
sort -o "$DOCKERFILES" "$DOCKERFILES"

echo "$SCRIPT_NAME — CM-GO-TOOLCHAIN-MATCHES-BUILDER static pre-build gate (BOB-153)"
echo "  root: $ROOT"
echo "  rule: builder image version MUST satisfy (>=) its module's go directive"
echo

FINDINGS="$TMP_DIR/findings.txt"
WARNINGS="$TMP_DIR/warnings.txt"
: > "$FINDINGS"
: > "$WARNINGS"
checked=0

while IFS= read -r df; do
    [[ -n "$df" ]] || continue
    # Only Dockerfiles that actually build with a golang image are pairs.
    tags="$(builder_tags "$df")"
    [[ -n "$tags" ]] || continue

    if ! needle_dockerfile "$df"; then
        echo "ERROR: control needle FAILED on ${df#"$ROOT"/} — the FROM golang:" >&2
        echo "       extractor did not see an injected synthetic stage, so any" >&2
        echo "       result it returns is not evidence (§11.4.201(7)(b))." >&2
        exit 2
    fi

    # Pair with the NEAREST enclosing go.mod, walking up from the Dockerfile's
    # directory. This matches how the compose build context is declared
    # (docker-compose.yml sets `context: ./qBitTorrent-go` for both of that
    # directory's Dockerfiles), so the module found here is the module the
    # builder actually compiles.
    dir="$(cd "$(dirname "$df")" && pwd)"
    gomod=""
    probe_dir="$dir"
    while [[ "$probe_dir" == "$ROOT"* ]]; do
        if [[ -f "$probe_dir/go.mod" ]]; then gomod="$probe_dir/go.mod"; break; fi
        [[ "$probe_dir" == "$ROOT" ]] && break
        probe_dir="$(dirname "$probe_dir")"
    done

    if [[ -z "$gomod" ]]; then
        # A golang builder with no module to build is itself suspicious, but it
        # is not this gate's invariant; report it verbosely and move on rather
        # than refuse a build over it (§11.4.201(1)).
        [[ $VERBOSE -eq 1 ]] && echo "    skip ${df#"$ROOT"/}: golang builder but no enclosing go.mod"
        continue
    fi

    if ! needle_gomod "$gomod"; then
        echo "ERROR: control needle FAILED on ${gomod#"$ROOT"/} — the go-directive" >&2
        echo "       extractor did not read back an injected synthetic version," >&2
        echo "       so any result it returns is not evidence (§11.4.201(7)(b))." >&2
        exit 2
    fi

    directive="$(go_directive "$gomod")"
    if [[ -z "$directive" ]]; then
        echo "${gomod#"$ROOT"/}: no parseable 'go <version>' directive — cannot resolve the floor (§11.4.201(4))" >> "$FINDINGS"
        continue
    fi

    d_maj="$(ver_field "$directive" 1)"; d_min="$(ver_field "$directive" 2)"
    d_pat="$(ver_field "$directive" 3)"

    while IFS= read -r tag; do
        [[ -n "$tag" ]] || continue
        checked=$((checked + 1))
        rel_df="${df#"$ROOT"/}"; rel_gm="${gomod#"$ROOT"/}"

        tver="$(tag_version "$tag")"
        if [[ -z "$tver" ]]; then
            echo "$rel_df: builder tag 'golang:$tag' names no version, so it cannot be shown to satisfy '$rel_gm' (go $directive), and the build is not reproducible (§11.4.246). Pin an explicit version, e.g. golang:${directive}-alpine." >> "$FINDINGS"
            continue
        fi

        t_maj="$(ver_field "$tver" 1)"; t_min="$(ver_field "$tver" 2)"
        t_pat="$(ver_field "$tver" 3)"

        verdict=""
        if [[ "$t_maj" -gt "$d_maj" ]] || { [[ "$t_maj" -eq "$d_maj" ]] && [[ "$t_min" -gt "$d_min" ]]; }; then
            verdict="ok"          # strictly newer minor: satisfies any patch
        elif [[ "$t_maj" -lt "$d_maj" ]] || { [[ "$t_maj" -eq "$d_maj" ]] && [[ "$t_min" -lt "$d_min" ]]; }; then
            verdict="fail"        # strictly older minor: provably cannot build
        elif has_patch "$tver"; then
            if [[ "$t_pat" -ge "$d_pat" ]]; then verdict="ok"; else verdict="fail"; fi
        elif [[ "$d_pat" -eq 0 ]]; then
            verdict="ok"          # patch-less tag satisfies a patch-less floor
        else
            verdict="warn"        # floating minor tag vs a patch-level floor
        fi

        case "$verdict" in
            ok)
                [[ $VERBOSE -eq 1 ]] && echo "    ok   $rel_df: golang:$tag satisfies $rel_gm (go $directive)"
                ;;
            fail)
                echo "$rel_df: builder 'golang:$tag' (Go $tver) CANNOT satisfy '$rel_gm' which requires go >= $directive. Raise the builder to golang:${directive}-alpine (or newer), or lower the directive — but only if every dependency's own go directive allows it." >> "$FINDINGS"
                ;;
            warn)
                echo "$rel_df: builder 'golang:$tag' names no patch level, so it cannot be PROVEN to satisfy '$rel_gm' (go $directive) — it floats to the newest ${tver}.x, which does satisfy it today but is not verifiable here and is not reproducible (§11.4.246). Pin it: golang:${directive}-alpine." >> "$WARNINGS"
                ;;
        esac
    done <<< "$tags"
done < "$DOCKERFILES"

# A quiet zero from a blind instrument reads exactly like a clean tree
# (§11.4.201(6)), so zero pairs is a FAIL and never a pass.
if [[ "$checked" -eq 0 ]]; then
    echo "FAIL: CM-GO-TOOLCHAIN-MATCHES-BUILDER — zero (go.mod, golang builder) pairs discovered under $ROOT." >&2
    echo "      A clean tree and a blind discovery both return zero, so zero cannot be" >&2
    echo "      reported as a pass (§11.4.201(6)). Either the scope data is wrong or" >&2
    echo "      the Go profile's Dockerfile has moved." >&2
    exit 1
fi

if [[ -s "$WARNINGS" ]]; then
    while IFS= read -r w; do
        echo "  WARN (non-blocking): $w"
    done < "$WARNINGS"
    echo "       Not a FAIL: the builder is not known-broken, and §11.4.234 forbids a"
    echo "       pre-build gate from blocking a build over something that works."
    echo
fi

if [[ -s "$FINDINGS" ]]; then
    echo "=== FINDINGS ===" >&2
    sed 's/^/  /' "$FINDINGS" >&2
    echo >&2
    n="$(wc -l < "$FINDINGS" | tr -d ' ')"
    echo "FAIL: $n Go toolchain/builder mismatch(es) (CM-GO-TOOLCHAIN-MATCHES-BUILDER, BOB-153)" >&2
    exit 1
fi

echo "PASS: CM-GO-TOOLCHAIN-MATCHES-BUILDER — $checked builder stage(s) satisfy their go directive"
exit 0
