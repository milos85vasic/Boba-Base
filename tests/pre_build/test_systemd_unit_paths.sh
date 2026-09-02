#!/usr/bin/env bash
# test_systemd_unit_paths.sh — RED-first guard for the systemd unit-path
# defect (§11.4.115 test-first, §11.4.224 test-first-for-all-work).
#
# PURPOSE
#   Every filesystem path a boba systemd unit references MUST resolve to
#   something that actually exists. Before this guard, all five units under
#   scripts/systemd/user/ hardcoded the absolute prefix
#   /run/media/milosvasic/DATA4TB/Projects/boba — a path that does NOT exist
#   on this host — across WorkingDirectory=, ExecStart=, ExecStop=,
#   EnvironmentFile= and Documentation=. Nothing checked it, so the units
#   were installable, loadable, and would have failed only at activation
#   time with a bare status=200/CHDIR after a reboot: the exact
#   §11.4.108 SOURCE-looks-fine / RUNTIME-broken gap.
#
# WHAT THIS ASSERTS (the oracle — §11.4.245)
#   Strategy: INVARIANT, and the oracle is STRUCTURALLY INDEPENDENT of the
#   code under test. The expected value is not read from the units, from
#   boba-svc.sh, or from any project constant — it is the kernel/filesystem
#   itself answering `test -e`. A unit cannot make this test pass by
#   asserting anything about itself; only a real file at the real path does.
#
#   Two arms, both required:
#     ARM 1 (SOURCE)    every path in scripts/systemd/user/*, after
#                       resolving the two legal placeholders, exists.
#     ARM 2 (INSTALLED) every path in ~/.config/systemd/user/boba-* — the
#                       files systemd will ACTUALLY read at boot — exists,
#                       and contains NO unsubstituted placeholder. Skipped
#                       with an honest reason (§11.4.3) when nothing is
#                       installed; a skip here is never a pass.
#
#   ARM 2 is the load-bearing one. ARM 1 alone would be satisfiable by a
#   correct template that the installer then copies verbatim, placeholder
#   and all — a file systemd cannot use. Checking only the repo copy is the
#   §11.4.108 layer-1-only mistake this guard exists to prevent.
#
# LEGAL PLACEHOLDERS (exactly two, closed set)
#   %h                  systemd's own home-directory specifier, expanded by
#                       systemd at load time. Resolved here to $HOME.
#   @@BOBA_REPO_ROOT@@  this project's install-time substitution token,
#                       replaced by scripts/boba-svc.sh with the real repo
#                       root. Resolved here to the repo root. It is legal in
#                       ARM 1 (the template) and ILLEGAL in ARM 2 (the
#                       installed copy) — an installed unit still carrying
#                       it means the installer failed to substitute, which
#                       is precisely the failure mode that would otherwise
#                       ship silently.
#   Any OTHER %-specifier makes a path UNRESOLVABLE here; such a path is
#   reported and FAILS rather than being skipped, because a path this
#   harness cannot resolve is a path it cannot vouch for (§11.4.6 — an
#   unverifiable claim is never reported as verified).
#
# INSTRUMENT VIABILITY (§11.4.201(7)(b) — control needle)
#   A null result from a broken extractor is indistinguishable from a clean
#   tree: both are silence. Before reporting any verdict this harness
#   asserts its extractor found at least MIN_EXPECTED_PATHS paths across the
#   source units. If it finds fewer, the extractor is blind and the script
#   ABORTS with exit 3 (INSTRUMENT FAILURE) rather than printing a PASS.
#
# EXIT
#   0 = every referenced path resolves and exists (GREEN)
#   1 = at least one path is missing or unresolvable (RED — real defect)
#   3 = instrument failure / blind extractor (verdict withheld, not a pass)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
UNIT_SRC="$REPO_ROOT/scripts/systemd/user"
UNIT_DST="$HOME/.config/systemd/user"
PLACEHOLDER='@@BOBA_REPO_ROOT@@'

# Control-needle floor. The five shipped units reference far more than this;
# the floor only has to be high enough that a silently-broken extractor
# cannot clear it. Measured 2026-09-01: 24 paths extracted from source.
MIN_EXPECTED_PATHS=12

fail_count=0
path_count=0

_pass() { printf '  [ OK ] %s\n' "$*"; }
_fail() { printf '  [FAIL] %s\n' "$*"; fail_count=$((fail_count + 1)); }

# Extract every filesystem path referenced by a unit file.
#
# Directives handled:
#   WorkingDirectory=   one path
#   EnvironmentFile=    one path; a leading '-' means "optional, do not fail
#                       if absent" — that is systemd's own semantics, so an
#                       optional file that is missing is NOT a failure here.
#                       Its DIRECTORY must still exist, which is what makes a
#                       wrong prefix detectable even on an optional file.
#   ExecStart=/ExecStop= the executable (first token, after stripping
#                       systemd's -/@/+/!/: prefix characters) plus every
#                       further token that looks like a path.
#   Documentation=      file:// URIs only; http(s) and man: are not
#                       filesystem paths and are ignored.
#
# Emits TAB-separated: <kind>\t<raw-path> where kind is REQUIRED or OPTDIR.
_extract_paths() {
    local unit_file="$1"
    awk -v token="$PLACEHOLDER" '
        # Strip a trailing CR so CRLF files do not produce phantom paths.
        { sub(/\r$/, "") }

        /^WorkingDirectory=/ {
            sub(/^WorkingDirectory=/, "")
            if (length($0)) print "REQUIRED\t" $0
            next
        }
        /^EnvironmentFile=/ {
            sub(/^EnvironmentFile=/, "")
            # A leading dash makes the file optional to systemd. We then
            # assert on its PARENT DIRECTORY instead: a wrong prefix is
            # still caught, while a legitimately-absent optional file is not
            # reported as a defect.
            if (substr($0, 1, 1) == "-") { sub(/^-/, ""); print "OPTDIR\t" $0 }
            else if (length($0))          { print "REQUIRED\t" $0 }
            next
        }
        /^Documentation=file:\/\// {
            sub(/^Documentation=file:\/\//, "")
            if (length($0)) print "REQUIRED\t" $0
            next
        }
        /^(ExecStart|ExecStop|ExecStartPre|ExecStopPost|ExecReload)=/ {
            sub(/^[A-Za-z]+=/, "")
            # Strip systemd exec-prefix characters (-@+!:) from the
            # executable — but NOT when the value begins with the repo-root
            # token, whose own leading "@@" is part of the token and not a
            # systemd prefix. Stripping it unconditionally silently ate the
            # one ExecStart= that is written as a bare token
            # (boba-webui-bridge.service), leaving ARM 1 blind to it while
            # ARM 2 saw it — a measured 18-vs-19 divergence between the two
            # arms, which is what surfaced this bug.
            if (index($0, token) != 1) { sub(/^[-@+!:]+/, "") }
            n = split($0, tok, /[ \t]+/)
            for (i = 1; i <= n; i++) {
                t = tok[i]
                gsub(/^"|"$/, "", t)
                # Checkable roots: an absolute path, a %-specifier root, or
                # the repo-root token. The token case is NOT optional: it
                # does not start with "/", so omitting it made ARM 1 blind
                # to exactly the ExecStart= binaries that the template
                # parameterises (measured: ARM 1 saw 17 paths where ARM 2
                # saw 19). A template arm that cannot see the template'"'"'s own
                # parameterised paths is the §11.4.201(6) false-null this
                # suite is supposed to prevent, not commit.
                if (t ~ /^\//)  { print "REQUIRED\t" t; continue }
                if (t ~ /^%[a-zA-Z]\//) { print "REQUIRED\t" t; continue }
                if (index(t, token) == 1) { print "REQUIRED\t" t; continue }
            }
            next
        }
    ' "$unit_file"
}

# Resolve the closed set of legal placeholders. Prints the resolved path on
# stdout and returns 0; returns 1 (printing nothing) when the path contains a
# specifier this harness cannot resolve.
_resolve() {
    local raw="$1" allow_repo_placeholder="$2" resolved="$raw"

    if [[ "$resolved" == *"$PLACEHOLDER"* ]]; then
        if [ "$allow_repo_placeholder" != "yes" ]; then
            return 1
        fi
        resolved="${resolved//$PLACEHOLDER/$REPO_ROOT}"
    fi
    resolved="${resolved//%h/$HOME}"

    # Any surviving %-specifier is unresolvable by this harness.
    if [[ "$resolved" =~ %[a-zA-Z] ]]; then
        return 1
    fi
    printf '%s' "$resolved"
}

# Check one unit file. $2=yes permits the repo placeholder (source arm only).
_check_unit() {
    local unit_file="$1" allow_repo_placeholder="$2"
    local kind raw resolved

    while IFS=$'\t' read -r kind raw; do
        [ -n "${raw:-}" ] || continue
        path_count=$((path_count + 1))

        if ! resolved="$(_resolve "$raw" "$allow_repo_placeholder")"; then
            if [[ "$raw" == *"$PLACEHOLDER"* ]]; then
                _fail "$(basename "$unit_file"): UNSUBSTITUTED PLACEHOLDER — $raw"
                printf '         systemd cannot expand %s; the installer must substitute it.\n' "$PLACEHOLDER"
            else
                _fail "$(basename "$unit_file"): unresolvable specifier — $raw"
            fi
            continue
        fi

        case "$kind" in
            REQUIRED)
                if [ -e "$resolved" ]; then
                    _pass "$(basename "$unit_file"): $resolved"
                else
                    _fail "$(basename "$unit_file"): MISSING — $resolved"
                    [ "$raw" != "$resolved" ] && printf '         (from: %s)\n' "$raw"
                fi
                ;;
            OPTDIR)
                local parent; parent="$(dirname "$resolved")"
                if [ -d "$parent" ]; then
                    _pass "$(basename "$unit_file"): optional file, parent dir exists: $parent"
                else
                    _fail "$(basename "$unit_file"): optional-file PARENT DIR MISSING — $parent"
                    printf '         (from: %s)\n' "$raw"
                fi
                ;;
        esac
    done < <(_extract_paths "$unit_file")
}

echo "=== test_systemd_unit_paths.sh ==="
echo "repo root : $REPO_ROOT"
echo "unit src  : $UNIT_SRC"
echo "unit dst  : $UNIT_DST"
echo

# ─── ARM 1: source units in the repo ────────────────────────────────────
echo "--- ARM 1: source units (scripts/systemd/user/) ---"
if [ ! -d "$UNIT_SRC" ]; then
    echo "INSTRUMENT FAILURE: unit source dir does not exist: $UNIT_SRC" >&2
    exit 3
fi
src_units=("$UNIT_SRC"/*)
if [ ! -e "${src_units[0]}" ]; then
    echo "INSTRUMENT FAILURE: no unit files under $UNIT_SRC" >&2
    exit 3
fi
for u in "${src_units[@]}"; do
    [ -f "$u" ] || continue
    _check_unit "$u" yes
done

# ─── control needle (§11.4.201(7)(b)) ───────────────────────────────────
echo
if [ "$path_count" -lt "$MIN_EXPECTED_PATHS" ]; then
    echo "INSTRUMENT FAILURE: extractor found only $path_count paths" >&2
    echo "  (expected >= $MIN_EXPECTED_PATHS). A near-zero result from a blind" >&2
    echo "  extractor is indistinguishable from a clean tree, so no verdict" >&2
    echo "  is reported. Fix the extractor before trusting this suite." >&2
    exit 3
fi
echo "control needle OK: extractor saw $path_count path(s) (floor $MIN_EXPECTED_PATHS)"

# ─── ARM 2: installed units systemd will actually read ──────────────────
echo
echo "--- ARM 2: installed units ($UNIT_DST) ---"
installed_found=0
if [ -d "$UNIT_DST" ]; then
    for u in "$UNIT_DST"/boba*; do
        [ -e "$u" ] || continue
        installed_found=$((installed_found + 1))
        # Placeholder is ILLEGAL here: systemd never expands it.
        _check_unit "$u" no
    done
fi
if [ "$installed_found" -eq 0 ]; then
    echo "  SKIP: no boba units installed under $UNIT_DST"
    echo "        reason=artifact_not_yet_built (§11.4.69) — install with:"
    echo "        bash scripts/boba-svc.sh install"
    echo "        NOTE: a skip is NOT a pass. Reboot survival is unproven"
    echo "        until units are installed AND this arm runs green."
else
    echo "  ($installed_found installed unit file(s) checked)"
fi

# ─── verdict ────────────────────────────────────────────────────────────
echo
echo "=== RESULT ==="
echo "paths checked : $path_count"
echo "failures      : $fail_count"
if [ "$fail_count" -eq 0 ]; then
    echo "VERDICT: PASS — every referenced path resolves and exists."
    exit 0
fi
echo "VERDICT: FAIL — $fail_count path(s) do not resolve to anything on disk."
echo "A systemd unit whose WorkingDirectory/ExecStart/EnvironmentFile does not"
echo "exist fails at ACTIVATION, not at load: it installs clean, enables clean,"
echo "and dies on the next boot. That is the defect this guard exists to catch."
exit 1
