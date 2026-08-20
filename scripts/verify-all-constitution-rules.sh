#!/usr/bin/env bash
# verify-all-constitution-rules.sh — boba's §11.4.32 post-constitution-pull
# validation sweep.
#
# ── Purpose ──────────────────────────────────────────────────────────────────
# §11.4.32 mandates that whenever the constitution submodule is fetched+pulled
# with any content change, the project MUST run a full validation sweep BEFORE
# the new constitution HEAD is treated as canonical, and it names this exact
# path as the canonical script. This file IS that sweep for boba.
#
# ── This script contains ZERO gate logic (§11.4.28(B) / §11.4.177) ───────────
# Every check executed here is the constitution submodule's OWN script,
# inherited BY REFERENCE and never copied:
#
#   1. The propagation family is delegated WHOLESALE to the constitution's own
#      batch runner:
#          constitution/scripts/gates/covenant_propagation_suite.sh gates --root <ROOT>
#      which is data-pack-driven (covenant_propagation_anchors.tsv), so anchors
#      added upstream are picked up here with no edit to this file.
#
#   2. Every remaining `constitution/scripts/gates/cm_*.sh` gate (the mechanism
#      gates, plus the propagation wrappers that predate the data pack and are
#      therefore NOT covered by the suite) is DISCOVERED mechanically and
#      executed as its own upstream script.
#
# boba-specific values (repository root, per-gate argv, declared-N/A gates)
# live in the consumer DATA file `config/constitution-sweep.conf` per §11.4.35 —
# they are DATA, never code, and never a fork of an upstream gate.
#
# ── Anti-bluff contract (§11.4 / §11.4.3 / §11.4.201) ────────────────────────
#   * Deterministic PASS / FAIL / SKIP-with-reason / ERROR / TIMEOUT per gate.
#   * A gate that cannot run SKIPs LOUDLY with a §11.4.69 reason — never a
#     silent pass, never a fabricated PASS.
#   * §11.4.201(6) BLIND-INSTRUMENT RULE: discovering ZERO gates is a FAILURE,
#     not a clean pass. A quiet zero from a blind instrument and a genuinely
#     clean tree are indistinguishable, so the zero is refused.
#   * COVERAGE RULE: every discovered gate must land in exactly one bucket.
#     A discovered gate that is neither run nor declared-N/A is a blind spot
#     and is reported as ERROR.
#   * Every gate is bounded by `timeout`; a timed-out gate is reported FAIL
#     (§11.4.232(C): a wedged long-op must never read as progress).
#   * Gate output is written to FILES, never captured through `$(...)`, to
#     avoid the §11.4.201(12) command-substitution watchdog/pipe stall.
#   * `set -e` is deliberately NOT used: a sweep that aborted on the first
#     non-zero gate would hide every later gate — partial coverage reported as
#     a complete run is exactly the §11.4 bluff this sweep exists to prevent.
#
# ── Usage ────────────────────────────────────────────────────────────────────
#   scripts/verify-all-constitution-rules.sh [options]
#     --root <dir>        repository root to validate   (default: this repo)
#     --gates-dir <dir>   constitution gate directory   (default: <root>/constitution/scripts/gates)
#     --config <file>     consumer DATA file            (default: <root>/config/constitution-sweep.conf)
#     --timeout <sec>     per-gate wall-clock budget    (default: 180)
#     --suite-timeout <s> budget for the delegated suite (default: 1800)
#     --evidence <dir>    where per-gate output lands   (default: mktemp -d)
#     --quiet             suppress per-gate PASS lines (FAIL/SKIP always shown)
#     -h|--help           print this header
#
# ── Environment overrides ────────────────────────────────────────────────────
#   CONSTITUTION_SWEEP_ROOT / CONSTITUTION_GATES_DIR / CONSTITUTION_SWEEP_CONFIG
#   CONSTITUTION_SWEEP_TIMEOUT / CONSTITUTION_SWEEP_SUITE_TIMEOUT
#
# ── Outputs ──────────────────────────────────────────────────────────────────
#   One `<verdict> <gate>` line per gate, a reason for every SKIP/ERROR/FAIL,
#   a machine-readable results TSV + full per-gate logs under the evidence dir,
#   and a summary line with counts (§11.4.262 machine-created evidence).
#
# ── Side-effects ─────────────────────────────────────────────────────────────
#   Read-only with respect to the repository. Writes only into the evidence
#   directory. Never commits, never pushes, never signals a process.
#   Gates run sequentially under `nice`/`ionice` to respect §12.6 / §12.12.
#
# ── Dependencies ─────────────────────────────────────────────────────────────
#   bash, timeout (coreutils), awk, sed, find. nice/ionice used when present.
#   Parses clean under `bash -n`.
#
# ── Cross-references ─────────────────────────────────────────────────────────
#   §11.4.32 (this sweep), §11.4.28(B)/§11.4.177 (inherit by reference, never
#   copy), §11.4.35 (consumer data), §11.4.3/§11.4.69 (SKIP-with-reason),
#   §11.4.201(1)(6)(12) (guard honesty, blind instrument, shell footguns),
#   §11.4.227 (gate custody), §11.4.232(C) (bounded long-ops), §11.4.262
#   (machine-created evidence), §12.6/§12.12 (host safety).
#
# ── Exit codes ───────────────────────────────────────────────────────────────
#   0 — every discovered gate PASSed or honestly SKIPped.
#   1 — at least one gate FAILed, TIMED OUT, or ERRORed.
#   2 — environment error (constitution absent, gate dir unreadable, bad arg).
#   3 — BLIND: zero gates discovered (§11.4.201(6)) — never reported as clean.
#
# Classification: project-specific (§11.4.17) — the consumer-side instantiation
# of the universal §11.4.32 mandate; all reusable logic stays upstream.

set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
DEFAULT_ROOT="$(cd "${SELF}/.." && pwd)"

root="${CONSTITUTION_SWEEP_ROOT:-$DEFAULT_ROOT}"
gates_dir="${CONSTITUTION_GATES_DIR:-}"
config="${CONSTITUTION_SWEEP_CONFIG:-}"
gate_timeout="${CONSTITUTION_SWEEP_TIMEOUT:-180}"
suite_timeout="${CONSTITUTION_SWEEP_SUITE_TIMEOUT:-1800}"
evidence=""
quiet=0

while [ $# -gt 0 ]; do
    case "$1" in
        --root)          root="$2"; shift 2 ;;
        --gates-dir)     gates_dir="$2"; shift 2 ;;
        --config)        config="$2"; shift 2 ;;
        --timeout)       gate_timeout="$2"; shift 2 ;;
        --suite-timeout) suite_timeout="$2"; shift 2 ;;
        --evidence)      evidence="$2"; shift 2 ;;
        --quiet)         quiet=1; shift ;;
        -h|--help)       sed -n '1,96p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "verify-all-constitution-rules: unknown arg '$1'" >&2; exit 2 ;;
    esac
done

for n in "$gate_timeout" "$suite_timeout"; do
    case "$n" in ''|*[!0-9]*) echo "sweep: timeouts must be integer seconds, got '$n'" >&2; exit 2 ;; esac
done

[ -d "$root" ] || { echo "sweep: --root not a directory: $root" >&2; exit 2; }
root="$(cd "$root" && pwd)"
: "${gates_dir:=${root}/constitution/scripts/gates}"
: "${config:=${root}/config/constitution-sweep.conf}"

command -v timeout >/dev/null 2>&1 || {
    echo "sweep: \`timeout\` (coreutils) is required to bound each gate; refusing to run unbounded (§11.4.232(C))" >&2
    exit 2
}

if [ ! -d "$gates_dir" ]; then
    echo "sweep: constitution gate directory not found: $gates_dir" >&2
    echo "sweep: the constitution submodule is absent or un-initialised — run 'git submodule update --init --recursive' (§11.4.36)" >&2
    exit 2
fi
gates_dir="$(cd "$gates_dir" && pwd)"

if [ -z "$evidence" ]; then
    evidence="$(mktemp -d "${TMPDIR:-/tmp}/constitution-sweep.XXXXXX")" || exit 2
fi
mkdir -p "$evidence" || exit 2
results="${evidence}/results.tsv"
: > "$results"

# ── Host-safety wrapper (§12.6 / §12.12): sequential, niced, io-idle ─────────
NICE=(); command -v nice   >/dev/null 2>&1 && NICE=(nice -n 19)
IONICE=(); command -v ionice >/dev/null 2>&1 && IONICE=(ionice -c 3)

pass=0; fail=0; skip=0; err=0; tmo=0; discovered=0

record() { # <verdict> <gate> <detail>
    printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$results"
    case "$1" in
        PASS)    pass=$((pass+1)); [ "$quiet" -eq 1 ] || echo "✅ PASS    $2" ;;
        FAIL)    fail=$((fail+1));  echo "❌ FAIL    $2 — $3" ;;
        TIMEOUT) tmo=$((tmo+1));    echo "❌ TIMEOUT $2 — exceeded ${gate_timeout}s budget (§11.4.232(C))" ;;
        SKIP)    skip=$((skip+1));  echo "⏭  SKIP    $2 — $3" ;;
        ERROR)   err=$((err+1));    echo "🛑 ERROR   $2 — $3" ;;
    esac
}

# ── Consumer DATA (§11.4.35) ────────────────────────────────────────────────
default_args=""
declare -A gate_args=()
declare -A gate_skip=()

if [ -r "$config" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue ;; esac
        directive="${line%%$'\t'*}"; rest="${line#*$'\t'}"
        case "$directive" in
            DEFAULT) default_args="$rest" ;;
            ARGS)    gate_args["${rest%%$'\t'*}"]="${rest#*$'\t'}" ;;
            SKIP)    gate_skip["${rest%%$'\t'*}"]="${rest#*$'\t'}" ;;
            *) echo "sweep: unknown directive '$directive' in $config" >&2; exit 2 ;;
        esac
    done < "$config"
else
    echo "⏭  NOTE: consumer DATA file not readable ($config) — every gate falls back to '--root <ROOT>' (§11.4.6: stated, not assumed)"
fi
[ -n "$default_args" ] || default_args="--root"$'\t'"@ROOT@"

expand_args() { # emits argv on stdout, one per line, @ROOT@ expanded
    printf '%s' "$1" | tr '\t' '\n' | sed "s|@ROOT@|${root}|g"
}

echo "======================================================================"
echo "§11.4.32 post-constitution-pull validation sweep"
echo "  repository root : $root"
echo "  gate directory  : $gates_dir"
echo "  consumer DATA   : $config"
echo "  evidence        : $evidence"
echo "  budgets         : ${gate_timeout}s/gate, ${suite_timeout}s/suite"
echo "======================================================================"

# ── Discover every upstream gate (mechanically — never a hand-kept list) ─────
declare -a all_gates=()
while IFS= read -r g || [ -n "$g" ]; do
    [ -n "$g" ] && all_gates+=("$g")
done < <(find "$gates_dir" -maxdepth 1 -type f -name 'cm_*.sh' ! -name '*_mutation_test.sh' -printf '%f\n' 2>/dev/null | sort)
discovered="${#all_gates[@]}"

# ── §11.4.201(6): a blind instrument must never report a clean tree ─────────
if [ "$discovered" -eq 0 ]; then
    echo "----------------------------------------------------------------------"
    echo "🛑 BLIND: zero constitution gates discovered under $gates_dir"
    echo "   A sweep that finds nothing to run has proven NOTHING. A blind"
    echo "   instrument and a clean repository return the identical quiet zero,"
    echo "   so this is reported as FAILURE, never as a pass (§11.4.201(6))."
    echo "SUMMARY: discovered=0 pass=0 fail=0 skip=0 error=0 timeout=0 — BLIND"
    exit 3
fi

declare -A covered=()

# ── PHASE A — delegate the propagation family to the constitution's runner ──
suite="${gates_dir}/covenant_propagation_suite.sh"
pack="${gates_dir}/covenant_propagation_anchors.tsv"
echo
echo "── Phase A: delegating to the constitution's own batch runner ──────────"
if [ ! -x "$suite" ] && [ ! -r "$suite" ]; then
    echo "⏭  SKIP    covenant_propagation_suite.sh — topology_unsupported: batch runner absent from $gates_dir"
elif [ ! -r "$pack" ]; then
    echo "⏭  SKIP    covenant_propagation_suite.sh — topology_unsupported: data pack absent ($pack)"
else
    suite_log="${evidence}/covenant_propagation_suite.log"
    "${NICE[@]}" "${IONICE[@]}" timeout "$suite_timeout" \
        bash "$suite" gates --root "$root" --quiet > "$suite_log" 2>&1
    src=$?
    if [ "$src" -eq 124 ] || [ "$src" -eq 137 ]; then
        record TIMEOUT "covenant_propagation_suite.sh" "suite exceeded ${suite_timeout}s"
    else
        rows=0
        while IFS= read -r ln; do
            set -- $ln
            [ $# -ge 2 ] || continue
            case "$1" in CM-COVENANT-*) ;; *) continue ;; esac
            gname="$1"; grc="$2"
            case "$grc" in ''|*[!0-9]*) continue ;; esac
            slug="$(printf '%s' "$gname" | sed -E 's/^CM-COVENANT-114-(.+)-PROPAGATION$/\1/')"
            gfile="cm_covenant_114_${slug}_propagation.sh"
            covered["$gfile"]=1
            rows=$((rows+1))
            if [ "$grc" -eq 0 ]; then
                record PASS "$gfile" "via suite"
            else
                record FAIL "$gfile" "suite exit $grc — see ${suite_log}"
            fi
        done < "$suite_log"
        if [ "$rows" -eq 0 ]; then
            record ERROR "covenant_propagation_suite.sh" "runner produced zero parseable gate rows (exit $src) — see ${suite_log} (§11.4.201(6))"
        else
            echo "   suite reported $rows gate rows (exit $src)"
        fi
    fi
fi

# ── PHASE B — every gate the runner does not cover, run individually ────────
echo
echo "── Phase B: gates not covered by the batch runner ──────────────────────"
for g in "${all_gates[@]}"; do
    [ -n "${covered[$g]+x}" ] && continue

    if [ -n "${gate_skip[$g]+x}" ]; then
        covered["$g"]=1
        record SKIP "$g" "${gate_skip[$g]} (declared in consumer DATA)"
        continue
    fi

    argstr="${gate_args[$g]:-$default_args}"
    declare -a argv=()
    # A literal `-` row means "invoke with NO arguments" — the correct DATA for
    # gates that audit the CONSTITUTION's own machinery and already default to
    # their sibling paths. Passing them `--root` makes them exit 2 (§11.4.201:
    # an un-runnable gate is reported, never silently absorbed).
    if [ "$argstr" = "-" ]; then argstr=""; fi
    # `|| [ -n "$a" ]` is load-bearing: expand_args emits no trailing newline,
    # so a bare `read` would silently DROP the final argv element (a gate then
    # sees `--root` with no value and dies on an unbound `$2`). Caught by this
    # sweep's own §1.1 fixture before the first real run.
    if [ -n "$argstr" ]; then
        while IFS= read -r a || [ -n "$a" ]; do
            [ -n "$a" ] && argv+=("$a")
        done < <(expand_args "$argstr")
    fi

    log="${evidence}/${g}.log"
    "${NICE[@]}" "${IONICE[@]}" timeout "$gate_timeout" \
        bash "${gates_dir}/${g}" ${argv[@]+"${argv[@]}"} > "$log" 2>&1
    rc=$?
    covered["$g"]=1

    reason="$(sed -e 's/\r$//' "$log" | grep -E '⏭|❌|🛑|FAIL —|SKIP —|ERROR' | tail -1)"
    [ -n "$reason" ] || reason="$(tail -1 "$log" 2>/dev/null)"
    [ -n "$reason" ] || reason="(no output; see ${log})"

    case "$rc" in
        0)
            if grep -qE '⏭|: SKIP —' "$log" 2>/dev/null && ! grep -qE '✅ .*: PASS' "$log" 2>/dev/null; then
                record SKIP "$g" "$reason"
            else
                record PASS "$g" "exit 0"
            fi
            ;;
        1)        record FAIL    "$g" "$reason" ;;
        124|137)  record TIMEOUT "$g" "killed after ${gate_timeout}s" ;;
        2)        record ERROR   "$g" "gate could not run (exit 2): $reason" ;;
        *)        record ERROR   "$g" "unexpected exit $rc: $reason" ;;
    esac
done

# ── COVERAGE — a discovered gate in no bucket is a blind spot ───────────────
uncovered=0
for g in "${all_gates[@]}"; do
    if [ -z "${covered[$g]+x}" ]; then
        uncovered=$((uncovered+1))
        record ERROR "$g" "discovered but never executed nor declared-N/A — sweep blind spot (§11.4.201(6))"
    fi
done

accounted=$((pass+fail+skip+err+tmo))
echo
echo "======================================================================"
echo "SUMMARY: discovered=${discovered} accounted=${accounted} pass=${pass} fail=${fail} skip=${skip} error=${err} timeout=${tmo}"
echo "Evidence: ${results}  (per-gate logs alongside it)"
if [ "$accounted" -lt "$discovered" ]; then
    echo "🛑 COVERAGE SHORTFALL: ${discovered} gates discovered, only ${accounted} accounted for"
    exit 1
fi
if [ "$((fail+err+tmo))" -gt 0 ]; then
    echo "❌ SWEEP FAIL — $((fail+tmo)) failing, ${err} un-runnable (§11.4.32 refuses the new constitution HEAD as canonical until resolved)"
    exit 1
fi
echo "✅ SWEEP PASS — ${pass} gates green, ${skip} honestly skipped, 0 failing"
exit 0
