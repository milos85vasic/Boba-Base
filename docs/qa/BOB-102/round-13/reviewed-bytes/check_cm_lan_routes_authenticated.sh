#!/usr/bin/env bash
# check_cm_lan_routes_authenticated.sh — CM-LAN-ROUTES-AUTHENTICATED
# static pre-build gate (§11.4.135 permanent regression guard).
#
# Purpose:
#   Protect the operator's BOB-102 decision of 2026-08-26 — "Keep 0.0.0.0 +
#   auth guard". The tunnel STAYS LAN-reachable, and the operator accepted
#   that exposure ON THE CONDITION that a permanent guard fails the build if
#   any LAN-reachable route ever stops demanding authentication. This gate is
#   that condition. It enumerates every route served by a listener declared
#   LAN-bound and refuses the build when a route is neither auth-wired nor
#   covered by a justified, checked-in exemption.
#
#   The route set is DERIVED FROM SOURCE on every run, never hand-maintained:
#   a hand-kept inventory drifts silently, and silent drift is the exact
#   failure this guard exists to prevent. A route added tomorrow is in
#   neither the auth-wired set nor the exemption list, so it FAILS until
#   somebody consciously protects it or justifies exempting it.
#
# Why this is not a grep for "auth" (§11.4.201):
#   A gate that greps for a token MENTIONING auth asserts a PROXY SIGNAL, not
#   the real condition — a comment, a variable name or a log string satisfies
#   it while the route stays wide open. This gate resolves the REAL wiring
#   from the authoritative source: FastAPI routes are parsed with `ast` and a
#   route counts as protected only when a `Depends(<marker>)` genuinely
#   reaches it (handler parameter, decorator `dependencies=`, or its
#   `APIRouter(dependencies=...)`); gin routes are resolved against the
#   middleware actually installed via `.Use(...)` on the owning engine or
#   group; stdlib-mux routes count as protected only when the constructor's
#   returned handler is really wrapped by an auth marker. Every refusal
#   prints its resolved evidence (file:line + how the verdict was reached)
#   so a false positive is diagnosable in one step.
#
# False positives are failures too (§11.4.201(1)):
#   A refusal on a genuinely-public route is a FAIL-bluff of the same
#   severity as a missed route. Deliberately-public routes are therefore
#   declarable in the checked-in policy's exemption list — but never
#   silently: every entry needs a `class` (public-by-design | known-gap) AND
#   a non-empty `justification`, both gate-enforced. `known-gap` entries are
#   real holes carried honestly and counted loudly on every run; they are
#   never allowed to be mistaken for "fine".
#
# Per-mux wrap resolution (gomux):
#   Wrapping is resolved for the SPECIFIC http.NewServeMux() value a route was
#   registered on, never by asking whether an auth wrap appears somewhere in
#   the file. A second, bare mux beside a genuinely wrapped one is therefore
#   reported UNSAFE. Falsely attributing safety to an open route is
#   categorically worse than failing to see a route at all, so an unresolvable
#   wrap resolves to UNWRAPPED (fail closed).
#
# HONEST BOUNDARY — static wiring is not runtime arming (§11.4.6):
#   This gate asserts that a LAN-reachable route is ATTACHED to an auth
#   mechanism. It does NOT assert that the mechanism is ARMED at runtime. The
#   merge-service marker `require_api_token` is env-conditional and returns
#   immediately when BOBA_API_TOKEN is unset, so a statically-protected route
#   can still be open in a running deployment. Arming BOBA_API_TOKEN and
#   backing it with a boot-time invariant (§11.4.254) is tracked separately as
#   BOB-197; this gate does not cover it, and claiming otherwise would be the
#   bluff it exists to prevent.
#
# Usage:
#   check_cm_lan_routes_authenticated.sh                    # default policy
#   check_cm_lan_routes_authenticated.sh --policy P --root R # explicit scope
#   check_cm_lan_routes_authenticated.sh --list             # inventory as JSON
#   check_cm_lan_routes_authenticated.sh --help
#
# Inputs:
#   --policy PATH  policy + exemption list. Default: config/lan_route_auth_policy.yaml
#   --root   PATH  tree the service roots resolve against. Default: repo root.
#   --list         emit the resolved route inventory as JSON and exit 0.
#   No stdin. No environment input.
#
# Outputs:
#   stdout — route/service counts, honest-gap count, verdict line.
#   stderr — one FINDING block per violation, each with resolved evidence.
#
# Side-effects:
#   None. Read-only static analysis: no file is written, no service is
#   contacted, no container is started, no process is signalled.
#
# Dependencies:
#   bash, python3 (>= 3.9), PyYAML, and the sibling analyzer engine
#   scripts/pre_build/lan_route_auth_analyzer.py.
#
# Verdict:
#   0 — PASS  (every LAN-reachable route is auth-wired or justly exempted)
#   1 — FAIL  (one or more findings; each reported on stderr with evidence)
#   2 — ERROR (usage error, missing analyzer/policy, or unusable interpreter)
#
# Cross-references:
#   §1.1 §11.4.6 §11.4.10 §11.4.18 §11.4.35 §11.4.107(10) §11.4.115(F)
#   §11.4.135 §11.4.142 §11.4.201 §11.4.224 §11.4.226 §11.4.238 §11.4.252
#   §11.4.254 §11.4.264. Paired meta-test:
#   tests/pre_build/test_check_cm_lan_routes_authenticated.sh
#   Guide: docs/scripts/check_cm_lan_routes_authenticated.md

set -euo pipefail

SCRIPT_NAME="check_cm_lan_routes_authenticated"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ANALYZER="$SCRIPT_DIR/lan_route_auth_analyzer.py"
POLICY="$REPO_ROOT/config/lan_route_auth_policy.yaml"
ROOT="$REPO_ROOT"
LIST=0

print_help() { sed -n '2,95p' "${BASH_SOURCE[0]}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)   print_help; exit 0 ;;
    --policy)    POLICY="${2:?--policy needs a value}"; shift 2 ;;
    --root)      ROOT="${2:?--root needs a value}"; shift 2 ;;
    --list)      LIST=1; shift ;;
    *) echo "ERROR($SCRIPT_NAME): unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$ANALYZER" ]]; then
  echo "ERROR($SCRIPT_NAME): analyzer engine not found at $ANALYZER" >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR($SCRIPT_NAME): python3 not on PATH — cannot resolve routes." >&2
  echo "  Refusing rather than reporting an unverified PASS (§11.4.201(4))." >&2
  exit 2
fi
if [[ ! -f "$POLICY" ]]; then
  echo "ERROR($SCRIPT_NAME): policy file not found at $POLICY" >&2
  echo "  The policy declares which listeners are LAN-bound and which routes" >&2
  echo "  are deliberately public. Without it this gate cannot assert its" >&2
  echo "  condition, so it refuses instead of passing blind (§11.4.201(4))." >&2
  exit 2
fi

if [[ "$LIST" -eq 1 ]]; then
  nice -n 19 python3 "$ANALYZER" --policy "$POLICY" --root "$ROOT" --json || true
  exit 0
fi

echo "[$SCRIPT_NAME] policy: ${POLICY#"$REPO_ROOT"/}"
echo "[$SCRIPT_NAME] root  : $ROOT"

rc=0
nice -n 19 python3 "$ANALYZER" --policy "$POLICY" --root "$ROOT" || rc=$?

case "$rc" in
  0) echo "PASS($SCRIPT_NAME): every LAN-reachable route is auth-wired or justly exempted." ;;
  1) echo "FAIL($SCRIPT_NAME): blocking finding(s) — see the FINDING block(s) above." >&2
     echo "  Each is one of:" >&2
     echo "    * a LAN-reachable route that does not demand authentication;" >&2
     echo "    * an UNMODELLED registration idiom this gate cannot resolve," >&2
     echo "      and therefore refuses rather than call it clean (§11.4.201(7)(c));" >&2
     echo "    * an exemption-list defect (empty justification, missing field," >&2
     echo "      bad class, duplicate entry, or stale entry);" >&2
     echo "    * a declared LAN service that resolved ZERO routes — refused as" >&2
     echo "      BLIND, since a blind extractor and a route-free service return" >&2
     echo "      the same quiet zero (§11.4.201(6) FALSE-NULL);" >&2
     echo "    * a service declaring a 'kind' this gate has no extractor for." >&2
     echo "  BOB-102 (operator, 2026-08-26) kept the 0.0.0.0 bind ON THE" >&2
     echo "  CONDITION that this never regresses. Fix the wiring, re-express" >&2
     echo "  the registration in a modelled form, or add a justified entry to" >&2
     echo "  ${POLICY#"$REPO_ROOT"/}." >&2 ;;
  *) echo "ERROR($SCRIPT_NAME): analyzer failed (exit $rc)." >&2; rc=2 ;;
esac
exit "$rc"
