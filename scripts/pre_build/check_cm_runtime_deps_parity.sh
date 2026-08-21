#!/usr/bin/env bash
# check_cm_runtime_deps_parity.sh — CM-RUNTIME-DEPS-PARITY pre-build gate
# (BOB-154). §11.4.201 guard-asserts-the-real-condition, §11.4.246/§11.4.264
# the-thing-you-tested-must-be-the-thing-you-ship.
#
# Purpose:
#   Assert that the interpreter+dependency set the TESTS run against is the
#   same one PRODUCTION serves. It compares the two REAL resolved sets — read
#   live out of the host virtualenv and live out of the running container —
#   never a requirements file against itself. A spec compared to itself is a
#   check that cannot fail.
#
# FORENSIC ANCHOR (BOB-154, measured 2026-08-21):
#   host .venv (installed 2026-08-07 23:12)  ->  Python 3.14.6, starlette 1.4.1
#   container   (installed 2026-08-21 15:20)  ->  Python 3.12.13, starlette 1.6.0
#   Eight packages diverged — precisely those that shipped a release in the 14
#   days between the two install dates — plus a TWO-MINOR interpreter gap that
#   the original report did not see at all. Because start-proxy.sh pip-installs
#   at every container start from a then-unpinned file, the divergence was not
#   a one-off: it regenerated itself on every restart, differently each time,
#   and no signal anywhere in the stack could see it. Every green suite was
#   evidence about a stack nobody was running.
#
# WHY A CHECK AND NOT ONLY A PIN (the design decision, recorded):
#   BOB-154 shipped both, and the check is the load-bearing half.
#     * A pin freezes one side; it cannot notice that the OTHER side moved.
#       The host venv is created by whoever ran `python -m venv` and is not
#       governed by download-proxy/requirements.txt at all.
#     * A pin cannot reach the interpreter — the single largest divergence
#       measured. No entry in a requirements file constrains CPython's minor
#       version.
#     * A pin that nothing maintains rots, and a rotted pin is its own defect.
#       A check fails LOUDLY when the two sides drift rather than freezing one
#       of them forever.
#   The pin makes production reproducible; this check makes any future
#   divergence VISIBLE. Neither substitutes for the other.
#
# WHAT IS COMPARED (and what is deliberately NOT):
#   1. INTERPRETER, on major.minor. A minor gap changes language and stdlib
#      behaviour and is treated as a divergence. A PATCH difference is
#      reported but is NOT fatal: alpine's point release and the host's will
#      legitimately differ by days, and failing on it would make the gate
#      unusable — a gate that cries wolf gets switched off within a week,
#      which is a worse outcome than the patch gap it was reporting.
#   2. Every package present in BOTH sets must agree on version EXACTLY.
#   3. Every package present in the CONTAINER must exist in the venv. A
#      production dependency absent from the host is worse than a version
#      skew: the tests cannot exercise it at all.
#   4. Installer/bootstrap packages (pip, setuptools, wheel) are excluded by
#      name — see IGNORED_PACKAGES below for why.
#   5. Packages present ONLY in the venv are IGNORED. The venv legitimately
#      carries developer tooling (pytest, ruff, mypy, playwright) that has no
#      business in a production image. Flagging those would be a §11.4.201(1)
#      false-positive refusal — the gate would refuse a perfectly healthy tree.
#
# DECLARED DIVERGENCES (§11.4.66 / the BOB-154 acceptance criterion):
#   The ticket sanctions a divergence that is DECLARED rather than eliminated.
#   A key listed in DECLARED_DIVERGENCES below is reported loudly on every run
#   and does not fail the gate. Two properties stop that becoming an off
#   switch:
#     * a declaration carries a reason and a tracked item, so it is a debt
#       with an owner and not a shrug;
#     * a STALE declaration — one that no longer matches any real divergence —
#       is itself a FAIL. Declarations cannot be filed pre-emptively and
#       cannot outlive the condition they excuse. That is the same
#       monotone-ratchet property §11.4.227 requires of gate ledgers.
#
# EMBEDDED CONTROL NEEDLE (§11.4.201(7)(b)):
#   A "0 divergences" verdict from a blind comparator is indistinguishable
#   from real parity — both are a quiet zero. Before ANY pass is reported the
#   comparator is re-run against a copy of the container snapshot carrying one
#   synthetic package the host cannot have, and the finding count MUST rise by
#   exactly one. If it does not, the comparator is not seeing and the gate
#   FAILs rather than reporting the parity it cannot actually observe.
#
# HONEST SKIP (§11.4.3 / §11.4.69 artifact_not_yet_built):
#   No container runtime, no running container, or no host venv => SKIP with a
#   reason, exit 0. A stopped stack is a legitimate state, not evidence of
#   drift, and a gate that hard-fails on it would be disabled by the first
#   person who ran the build with the stack down. SKIP is never silent: the
#   reason is printed and the verdict line says SKIP, so the wiring can tell a
#   skip from a pass.
#
# Usage:
#   check_cm_runtime_deps_parity.sh
#   check_cm_runtime_deps_parity.sh --help
#
# Inputs:  no arguments, no stdin. Optional env (consumer DATA, §11.4.35):
#            VENV_PYTHON       host interpreter (default .venv/bin/python)
#            PROXY_CONTAINER   container name  (default qbittorrent-proxy)
#            CONTAINER_RUNTIME podman|docker   (default: autodetect, podman first)
#          TEST-ONLY injection, used by the paired meta-test to build hermetic
#          fixtures — when set, the snapshot is READ FROM THE FILE instead of
#          probed. Never set these in a real run; the whole point of the gate
#          is that it reads reality:
#            CM_DEPS_HOST_SNAPSHOT / CM_DEPS_CONTAINER_SNAPSHOT
# Outputs: findings + reasons on stderr; the verdict line ALWAYS last on
#          stdout (the pre-build wiring reads it with `tail -n1`).
# Side-effects: none. Read-only. Runs `pip list` inside the container via
#          `exec`; never starts, stops, restarts or mutates it.
# Dependencies: bash 4+, and (for a non-SKIP run) podman or docker.
#
# Verdict:
#   0 — PASS (parity holds, comparator proven seeing) or an honest SKIP
#   1 — FAIL (an undeclared divergence, a stale declaration, or a blind
#             comparator)
#   2 — ERROR (usage)
#
# Cross-references: docs/scripts/check_cm_runtime_deps_parity.md (§11.4.18
#   companion), tests/pre_build/test_check_cm_runtime_deps_parity.sh (the §1.1
#   paired mutation), download-proxy/requirements.txt (the pinned set this
#   gate keeps honest), BOB-154.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
GATE="CM-RUNTIME-DEPS-PARITY"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,120p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi
if [[ $# -gt 0 ]]; then
    echo "$GATE: ERROR — this gate takes no arguments (got: $*). Try --help." >&2
    exit 2
fi

# --- Consumer-owned scope DATA (§11.4.35) ----------------------------------
VENV_PYTHON="${VENV_PYTHON:-${PROJECT_ROOT}/.venv/bin/python}"
PROXY_CONTAINER="${PROXY_CONTAINER:-qbittorrent-proxy}"

# Installer/bootstrap packages, excluded from the comparison by NAME (never by
# pattern — a pattern could silently swallow a real dependency). These ship
# with the base image and the venv respectively, are not application
# dependencies, and do not affect what download-proxy/src does at runtime.
# Critically, download-proxy/requirements.txt deliberately does NOT pin `pip`
# (pinning the installer inside the file it is installing is a
# self-modification footgun), so flagging it would report a divergence the fix
# cannot reach and force a permanent declaration. A gate that demands action
# on something unactionable is the §11.4.201(1) false-positive refusal, and it
# is how gates get switched off.
IGNORED_PACKAGES=(pip setuptools wheel)

# Declared, deliberately-tolerated divergences. Format: "key|reason|tracked-item".
# `key` is either the literal `python` or a PEP 503-normalised package name.
# EVERY entry must correspond to a real, currently-observed divergence — a
# stale one FAILs (see the header). Empty array = nothing tolerated.
DECLARED_DIVERGENCES=(
)

# ---------------------------------------------------------------------------
# PEP 503 name normalisation. `typing_extensions`, `typing-extensions` and
# `Typing.Extensions` are ONE package; comparing the raw strings would report
# a divergence that does not exist (a §11.4.201(1) false positive) and, worse,
# would MISS a real version skew by treating the two spellings as unrelated
# packages that simply appear on one side each.
# ---------------------------------------------------------------------------
normalise_snapshot() {
    # stdin: `pip list --format=freeze` output plus a leading `#python X.Y.Z`.
    # stdout: normalised `#python ...` line then sorted `name==version` lines.
    awk '
        /^#python /  { print; next }
        /^[^#]/ && /==/ {
            split($0, p, "==")
            n = tolower(p[1])
            gsub(/[-_.]+/, "-", n)
            print n "==" p[2]
        }
    ' | sort
}

probe_host() {
    "$VENV_PYTHON" -c 'import sys; print("#python " + ".".join(map(str, sys.version_info[:3])))'
    "$VENV_PYTHON" -m pip list --format=freeze 2>/dev/null
}

probe_container() {
    "$RUNTIME" exec "$PROXY_CONTAINER" python -c \
        'import sys; print("#python " + ".".join(map(str, sys.version_info[:3])))'
    "$RUNTIME" exec "$PROXY_CONTAINER" python -m pip list --format=freeze 2>/dev/null
}

# ---------------------------------------------------------------------------
# The comparator. Kept as a pure function of two snapshot files so the control
# needle can re-run the IDENTICAL code path against a doctored input — a needle
# that exercised a different path would certify nothing about the real one.
# Emits one `key<TAB>description` finding per line.
# ---------------------------------------------------------------------------
compare_snapshots() {
    local host_file="$1" cont_file="$2"
    local ignore_csv
    ignore_csv="$(IFS=,; echo "${IGNORED_PACKAGES[*]:-}")"
    awk -F'==' -v ignore_csv="$ignore_csv" '
        function minor(v,   a) { split(v, a, "."); return a[1] "." a[2] }
        BEGIN {
            n = split(ignore_csv, ig, ",")
            for (i = 1; i <= n; i++) if (ig[i] != "") ignored[ig[i]] = 1
        }
        FNR == NR {
            if ($0 ~ /^#python /) { hpy = substr($0, 9); next }
            host[$1] = $2; next
        }
        /^#python / { cpy = substr($0, 9); next }
        {
            name = $1; cver = $2
            if (name in ignored) next
            if (!(name in host)) {
                printf "%s\tproduction dependency %s==%s is ABSENT from the host venv — the tests cannot exercise it at all\n", name, name, cver
            } else if (host[name] != cver) {
                printf "%s\t%s: venv has %s, container runs %s\n", name, name, host[name], cver
            }
        }
        END {
            if (hpy == "" || cpy == "") {
                printf "python\tinterpreter version missing from a snapshot (host=%s container=%s) — a snapshot without it is not evidence\n", (hpy == "" ? "?" : hpy), (cpy == "" ? "?" : cpy)
            } else if (minor(hpy) != minor(cpy)) {
                printf "python\tinterpreter: venv runs CPython %s, container runs CPython %s — a minor-version gap changes language and stdlib behaviour\n", hpy, cpy
            }
        }
    ' "$host_file" "$cont_file"
}

# --- Honest SKIP conditions (§11.4.3) --------------------------------------
HOST_SNAP="$(mktemp)"; CONT_SNAP="$(mktemp)"
NEEDLE_SNAP="$(mktemp)"
trap 'rm -f "$HOST_SNAP" "$CONT_SNAP" "$NEEDLE_SNAP"' EXIT

skip() {
    echo "SKIP(§11.4.3): $1" >&2
    echo "  A stack that is not running is not evidence of drift (§11.4.201(1))." >&2
    echo "SKIP(§11.4.3): $GATE — $1"
    exit 0
}

if [[ -n "${CM_DEPS_HOST_SNAPSHOT:-}" && -n "${CM_DEPS_CONTAINER_SNAPSHOT:-}" ]]; then
    # Injected snapshots: hermetic fixture mode, used only by the meta-test.
    [[ -f "$CM_DEPS_HOST_SNAPSHOT" ]] || { echo "$GATE: ERROR — injected host snapshot not found: $CM_DEPS_HOST_SNAPSHOT" >&2; exit 2; }
    [[ -f "$CM_DEPS_CONTAINER_SNAPSHOT" ]] || { echo "$GATE: ERROR — injected container snapshot not found: $CM_DEPS_CONTAINER_SNAPSHOT" >&2; exit 2; }
    normalise_snapshot < "$CM_DEPS_HOST_SNAPSHOT" > "$HOST_SNAP"
    normalise_snapshot < "$CM_DEPS_CONTAINER_SNAPSHOT" > "$CONT_SNAP"
    SOURCE_NOTE="injected snapshots (fixture mode)"
else
    RUNTIME=""
    for candidate in "${CONTAINER_RUNTIME:-}" podman docker; do
        [[ -n "$candidate" ]] || continue
        if command -v "$candidate" >/dev/null 2>&1; then RUNTIME="$candidate"; break; fi
    done
    [[ -n "$RUNTIME" ]] || skip "no container runtime (podman/docker) on PATH — production's resolved set is unreadable"

    if ! "$RUNTIME" inspect -f '{{.State.Running}}' "$PROXY_CONTAINER" 2>/dev/null | grep -qx true; then
        skip "container '$PROXY_CONTAINER' is not running — production's resolved set is unreadable"
    fi
    [[ -x "$VENV_PYTHON" ]] || skip "host interpreter not found or not executable at $VENV_PYTHON"

    probe_host      | normalise_snapshot > "$HOST_SNAP" || skip "host probe failed at $VENV_PYTHON"
    probe_container | normalise_snapshot > "$CONT_SNAP" || skip "container probe failed in '$PROXY_CONTAINER'"
    SOURCE_NOTE="live: $VENV_PYTHON vs $RUNTIME exec $PROXY_CONTAINER"
fi

# A snapshot with no packages means the probe returned nothing useful. Trusting
# that as "parity" is the §11.4.201(6) false-null: a blind probe and a matching
# stack both produce a quiet zero.
HOST_PKGS="$(grep -cE '^[^#]' "$HOST_SNAP" || true)"
CONT_PKGS="$(grep -cE '^[^#]' "$CONT_SNAP" || true)"
if [[ "$HOST_PKGS" -eq 0 || "$CONT_PKGS" -eq 0 ]]; then
    echo "$GATE: FAIL — a snapshot came back empty (host=$HOST_PKGS packages, container=$CONT_PKGS)." >&2
    echo "  An empty resolved set is a blind probe, not parity (§11.4.201(6))." >&2
    echo "FAIL: $GATE — empty snapshot, parity NOT established"
    exit 1
fi

# --- Control needle (§11.4.201(7)(b)) --------------------------------------
# Prove the comparator can SEE before its silence is read as parity.
BASE_FINDINGS="$(compare_snapshots "$HOST_SNAP" "$CONT_SNAP" | wc -l | tr -d ' ')"
cp "$CONT_SNAP" "$NEEDLE_SNAP"
echo "cm-parity-control-needle==0.0.0" >> "$NEEDLE_SNAP"
NEEDLE_FINDINGS="$(compare_snapshots "$HOST_SNAP" "$NEEDLE_SNAP" | wc -l | tr -d ' ')"
if [[ "$NEEDLE_FINDINGS" -ne $((BASE_FINDINGS + 1)) ]]; then
    echo "$GATE: FAIL — control needle not detected." >&2
    echo "  A synthetic package absent from the host was added to the container" >&2
    echo "  snapshot; findings went $BASE_FINDINGS -> $NEEDLE_FINDINGS, expected $((BASE_FINDINGS + 1))." >&2
    echo "  The comparator is not seeing, so its silence proves nothing (§11.4.201(7)(b))." >&2
    echo "FAIL: $GATE — comparator blind, parity NOT established"
    exit 1
fi

# --- Classify findings against the declarations ----------------------------
FINDINGS="$(mktemp)"; DECLARED_HIT="$(mktemp)"
trap 'rm -f "$HOST_SNAP" "$CONT_SNAP" "$NEEDLE_SNAP" "$FINDINGS" "$DECLARED_HIT"' EXIT
: > "$FINDINGS"; : > "$DECLARED_HIT"

is_declared() {
    local key="$1" entry
    for entry in ${DECLARED_DIVERGENCES+"${DECLARED_DIVERGENCES[@]}"}; do
        [[ "${entry%%|*}" == "$key" ]] && return 0
    done
    return 1
}

while IFS=$'\t' read -r key desc; do
    [[ -n "$key" ]] || continue
    if is_declared "$key"; then
        printf '%s\n' "$key" >> "$DECLARED_HIT"
        echo "  DECLARED: $desc"
    else
        printf '%s\n' "$desc" >> "$FINDINGS"
    fi
done < <(compare_snapshots "$HOST_SNAP" "$CONT_SNAP")

# A declaration that excuses nothing is debt with no condition attached, and it
# would silently pre-authorise a future divergence on that key. It FAILs.
for entry in ${DECLARED_DIVERGENCES+"${DECLARED_DIVERGENCES[@]}"}; do
    key="${entry%%|*}"
    if ! grep -qxF "$key" "$DECLARED_HIT" 2>/dev/null; then
        echo "stale declaration '$key' matches no current divergence — remove it (a declaration must not outlive the condition it excuses)" >> "$FINDINGS"
    fi
done

# --- Verdict ---------------------------------------------------------------
echo "  source: $SOURCE_NOTE"
echo "  compared: $CONT_PKGS container package(s) against $HOST_PKGS host package(s); host-only dev tooling ignored by design"
echo "  control needle: seen (findings $BASE_FINDINGS -> $NEEDLE_FINDINGS)"

if [[ -s "$FINDINGS" ]]; then
    echo "=== FINDINGS ===" >&2
    sed 's/^/  /' "$FINDINGS" >&2
    echo >&2
    n="$(wc -l < "$FINDINGS" | tr -d ' ')"
    echo "  The tests and production are not running the same stack, so a green" >&2
    echo "  suite is evidence about a set nobody serves (BOB-154)." >&2
    echo "  Reconcile with: .venv/bin/python -m pip install -r download-proxy/requirements.txt" >&2
    echo "FAIL: $GATE — $n undeclared divergence(s) between the test stack and production"
    exit 1
fi

DECL_N="$(wc -l < "$DECLARED_HIT" | tr -d ' ')"
echo "PASS: $GATE — test stack and production agree ($CONT_PKGS packages + interpreter; $DECL_N declared divergence(s))"
exit 0
