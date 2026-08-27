#!/usr/bin/env bash
# test_check_cm_lan_routes_authenticated.sh — §1.1 paired-mutation meta-test for
# scripts/pre_build/check_cm_lan_routes_authenticated.sh
# (CM-LAN-ROUTES-AUTHENTICATED, §11.4.135 permanent regression guard for the
# operator's BOB-102 decision of 2026-08-26: "Keep 0.0.0.0 + auth guard").
#
# TDD (§11.4.224/§11.4.43/§11.4.115): this harness is authored BEFORE the gate
# is trusted. A guard never observed FAILing on a genuinely-broken input is
# unvalidated instrumentation and mints nothing (§11.4.115(F)).
#
# Fixtures (hermetic; each is a throwaway tree + its own policy file):
#
#   golden-good-fastapi   -> exit 0  every mutating route carries
#                            Depends(require_api_token); the one GET is
#                            exempted WITH a justification.
#   MUTATION-fastapi      -> exit 1  THE §1.1 PAIRED MUTATION. Byte-for-byte
#                            golden-good-fastapi with the
#                            `Depends(require_api_token)` DELETED — i.e. a
#                            LAN-reachable route that "stops demanding
#                            authentication", the exact regression the
#                            operator's decision is conditioned on. The gate
#                            MUST FAIL here or it protects nothing.
#   golden-bad-fastapi-new-> exit 1  a NEW unauthenticated mutating route that
#                            nobody exempted (the silent-drift shape).
#   golden-good-gomux     -> exit 0  stdlib mux wrapped in WithAuth.
#   MUTATION-gomux        -> exit 1  the WithAuth wrap REMOVED from the
#                            router's return (boba-jackett's real shape).
#   golden-bad-gin        -> exit 1  gin mutating route on a LAN bind with no
#                            auth middleware at all.
#   golden-bad-unjustified-> exit 1  an exemption entry whose justification is
#                            empty — silent exemption is forbidden
#                            (§11.4.201(1): honest gaps, never blanket skips).
#   golden-bad-stale      -> exit 1  an exemption for a route that no longer
#                            exists (a rotting list stops describing reality).
#   golden-bad-blind      -> exit 1  a declared LAN service whose scan yields
#                            ZERO routes. A blind instrument and a clean tree
#                            both return a quiet zero (§11.4.201(6) FALSE-NULL)
#                            so the gate must refuse the zero, not bless it.
#   golden-false-loopback -> exit 0  a service explicitly declared
#                            lan_bound:false with an unauthenticated mutating
#                            route. The gate scopes to LAN-reachable listeners
#                            only; firing here would be the §11.4.201(1)
#                            false-positive refusal.
#   real-tree             -> gate runs against the actual checkout and its
#                            verdict is REPORTED (informational; the real
#                            posture is reported by the gate itself, not
#                            asserted by this harness).
#
# A gate that PASSes any golden-bad/MUTATION fixture, or FAILs any golden-good
# fixture, is itself the bluff (§11.4.107(10)) and this harness reports it.
#
# Exit codes:
#   0 — every fixture matched its expected outcome (the gate is honest).
#   1 — one or more checks diverged from the expected outcome.
#   2 — harness/environment error (gate missing / not executable).
#
# Cross-refs: §1.1 §11.4.1 §11.4.6 §11.4.43 §11.4.107(10) §11.4.115(F)
#             §11.4.135 §11.4.201 §11.4.224 §11.4.226 §11.4.238.

set -euo pipefail

HARNESS_NAME="test_check_cm_lan_routes_authenticated"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE="$REPO_ROOT/scripts/pre_build/check_cm_lan_routes_authenticated.sh"

if [[ ! -f "$GATE" ]]; then
  echo "FAIL($HARNESS_NAME): gate script not found at $GATE" >&2
  echo "  (expected RED at this point if the gate has not been authored yet)" >&2
  exit 2
fi
if [[ ! -x "$GATE" ]]; then
  echo "FAIL($HARNESS_NAME): gate script is not executable: $GATE" >&2
  exit 2
fi

TMPROOT="$(mktemp -d -t lanauth-meta-XXXXXX)"
cleanup() { rm -rf "$TMPROOT"; }
trap cleanup EXIT

PASS_N=0; FAIL_N=0

# run_case <name> <expected_exit> <fixture_dir>
run_case() {
  local name="$1" expected="$2" dir="$3" actual=0 out
  out="$(nice -n 19 "$GATE" --policy "$dir/policy.yaml" --root "$dir" 2>&1)" || actual=$?
  if [[ "$actual" == "$expected" ]]; then
    PASS_N=$((PASS_N + 1))
    printf 'ok   %-24s expected=%s actual=%s\n' "$name" "$expected" "$actual"
  else
    FAIL_N=$((FAIL_N + 1))
    printf 'NOT-OK %-22s expected=%s actual=%s\n' "$name" "$expected" "$actual" >&2
    printf '%s\n' "$out" | sed 's/^/       | /' >&2
  fi
}

# ---------------------------------------------------------------- fastapi ---
mk_fastapi() {  # mk_fastapi <dir> <auth_dep_or_empty> <extra_route>
  local d="$1" dep="$2" extra="${3:-}"
  mkdir -p "$d/app/api"
  cat > "$d/app/api/routes.py" <<PYEOF
from fastapi import APIRouter, Depends, Request
router = APIRouter(tags=["t"])

def require_api_token(request: Request) -> None:
    return

@router.get("/health")
async def health():
    return {"ok": True}

@router.post("/download")
async def download(req: Request${dep}):
    return {"ok": True}
${extra}
PYEOF
  cat > "$d/app/api/__init__.py" <<'PYEOF'
from fastapi import FastAPI
from .routes import router as api_router
app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
PYEOF
}

mk_policy_fastapi() {  # mk_policy_fastapi <dir> <exemptions_block>
  cat > "$1/policy.yaml" <<PYEOF
schema_version: 1
services:
  - id: svc
    kind: fastapi
    lan_bound: true
    roots: ["app/api"]
    auth_markers: ["require_api_token"]
exemptions:
$2
PYEOF
}

EXEMPT_HEALTH='  - service: svc
    method: GET
    path: /api/v1/health
    class: public-by-design
    justification: "Unauthenticated liveness probe; returns no state."'

D="$TMPROOT/golden-good-fastapi";    mk_fastapi "$D" ", _: None = Depends(require_api_token)"; mk_policy_fastapi "$D" "$EXEMPT_HEALTH"
D="$TMPROOT/mutation-fastapi";       mk_fastapi "$D" ""                                      ; mk_policy_fastapi "$D" "$EXEMPT_HEALTH"
D="$TMPROOT/golden-bad-fastapi-new"; mk_fastapi "$D" ", _: None = Depends(require_api_token)" '
@router.delete("/torrents/{tid}")
async def wipe(tid: str):
    return {"ok": True}
'; mk_policy_fastapi "$D" "$EXEMPT_HEALTH"

D="$TMPROOT/golden-bad-unjustified"; mk_fastapi "$D" ", _: None = Depends(require_api_token)"
mk_policy_fastapi "$D" '  - service: svc
    method: GET
    path: /api/v1/health
    class: public-by-design
    justification: ""'

D="$TMPROOT/golden-bad-stale"; mk_fastapi "$D" ", _: None = Depends(require_api_token)"
mk_policy_fastapi "$D" "$EXEMPT_HEALTH
  - service: svc
    method: GET
    path: /api/v1/gone
    class: public-by-design
    justification: \"Route deleted in a prior refactor; entry never cleaned up.\""

D="$TMPROOT/golden-bad-blind"; mkdir -p "$D/app/api"; echo "# no routes here" > "$D/app/api/empty.py"
mk_policy_fastapi "$D" "  []"

D="$TMPROOT/golden-false-loopback"; mk_fastapi "$D" ""
cat > "$D/policy.yaml" <<'PYEOF'
schema_version: 1
services:
  - id: svc
    kind: fastapi
    lan_bound: false
    roots: ["app/api"]
    auth_markers: ["require_api_token"]
exemptions: []
PYEOF

# ------------------------------------------------------------------- go ----
mk_gomux() {  # mk_gomux <dir> <wrap_open> <wrap_close>
  local d="$1"
  mkdir -p "$d/jackettapi"
  cat > "$d/jackettapi/router.go" <<GOEOF
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return $2mux$3
}
GOEOF
}
mk_policy_go() {  # mk_policy_go <dir> <kind> <root> <markers> <exemptions>
  cat > "$1/policy.yaml" <<GOEOF
schema_version: 1
services:
  - id: svc
    kind: $2
    lan_bound: true
    roots: ["$3"]
    auth_markers: [$4]
exemptions:
$5
GOEOF
}

EXEMPT_HEALTHZ='  - service: svc
    method: ANY
    path: /healthz
    class: public-by-design
    justification: "Container healthcheck probe; returns no state."'

D="$TMPROOT/golden-good-gomux"; mk_gomux "$D" "WithAuth(" ")"; mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"
D="$TMPROOT/mutation-gomux";    mk_gomux "$D" ""          "" ; mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

D="$TMPROOT/golden-bad-gin"; mkdir -p "$D/cmd"
cat > "$D/cmd/main.go" <<'GOEOF'
package main

func main() {
	r := gin.Default()
	r.GET("/health", api.HealthHandler)
	r.POST("/api/v1/download", api.DownloadHandler)
	r.Run(":7187")
}
GOEOF
mk_policy_go "$D" gin cmd '' '  - service: svc
    method: GET
    path: /health
    class: public-by-design
    justification: "Liveness probe."'

# ============================ REVIEW-ROUND-2 FIXTURES ======================
# Each fixture below was authored BEFORE the corresponding analyzer fix and
# observed to FAIL against the pre-fix engine (§11.4.224 test-first).

# --- IMPORTANT-2: per-mux wrap resolution -----------------------------------
# The reviewer added a SECOND, bare mux to the same file that carries the real
# WithAuth wrap. A whole-file "does a wrap appear anywhere" test marks the bare
# mux's routes auth_wired=True — a FALSE ATTRIBUTION OF SAFETY, categorically
# worse than failing to see a route at all.
D="$TMPROOT/gomux-second-bare-mux"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'GO2EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithCORS(nil, WithAuth(mux))
}

func NewDebugMux(d *Deps) http.Handler {
	dbg := http.NewServeMux()
	dbg.HandleFunc("/api/v1/jackett/debug/wipe", d.Debug.HandleWipe)
	return dbg
}
GO2EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

# false-positive guard: BOTH muxes wrapped => must NOT fire.
D="$TMPROOT/gomux-two-wrapped"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'GO3EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithCORS(nil, WithAuth(mux))
}

func NewDebugMux(d *Deps) http.Handler {
	dbg := http.NewServeMux()
	dbg.HandleFunc("/api/v1/jackett/debug/wipe", d.Debug.HandleWipe)
	return WithAuth(dbg)
}
GO3EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' ""

# --- IMPORTANT-1: unmodeled registration idioms must FAIL CLOSED ------------
# A guard whose stated purpose is catching TOMORROW's drift must not be blind
# to registration forms its own frameworks support (§11.4.201(7)(c)).
mk_unmodeled_fastapi() {  # <dir> <tail>
  local d="$1"; mkdir -p "$d/app/api"
  cat > "$d/app/api/routes.py" <<PY3EOF
from fastapi import APIRouter, Depends, Request
router = APIRouter(tags=["t"])

def require_api_token(request: Request) -> None:
    return

@router.get("/health")
async def health():
    return {"ok": True}
$2
PY3EOF
  cat > "$d/app/api/__init__.py" <<'PY4EOF'
from fastapi import FastAPI
from .routes import router as api_router
app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
PY4EOF
  mk_policy_fastapi "$d" "$EXEMPT_HEALTH"
}

mk_unmodeled_fastapi "$TMPROOT/unmodeled-add-api-route" '
async def sneaky(req: Request):
    return {"ok": True}

router.add_api_route("/sneaky", sneaky, methods=["POST"])'

mk_unmodeled_fastapi "$TMPROOT/unmodeled-nonliteral-path" '
DYNAMIC_PATH = "/dynamic"

@router.post(DYNAMIC_PATH)
async def dyn(req: Request):
    return {"ok": True}'

mk_unmodeled_gin() {  # <dir> <tail>
  local d="$1"; mkdir -p "$d/cmd"
  cat > "$d/cmd/main.go" <<GO4EOF
package main

func main() {
	r := gin.Default()
	r.GET("/health", api.HealthHandler)
$2
	r.Run(":7187")
}
GO4EOF
  mk_policy_go "$d" gin cmd '' '  - service: svc
    method: GET
    path: /health
    class: public-by-design
    justification: "Liveness probe."'
}
mk_unmodeled_gin "$TMPROOT/unmodeled-gin-any"       '	r.Any("/api/v1/evil-any", api.EvilHandler)'
mk_unmodeled_gin "$TMPROOT/unmodeled-gin-multiline" '	r.POST(
		"/api/v1/evil-multiline", api.EvilHandler)'

# --- MINOR-1: aliased Depends must NOT be a false positive -----------------
D="$TMPROOT/aliased-depends"; mkdir -p "$D/app/api"
cat > "$D/app/api/routes.py" <<'PY5EOF'
from fastapi import APIRouter, Depends, Request
router = APIRouter(tags=["t"])

def require_api_token(request: Request) -> None:
    return

_token_guard = Depends(require_api_token)

@router.get("/health")
async def health():
    return {"ok": True}

@router.post("/download")
async def download(req: Request, _: None = _token_guard):
    return {"ok": True}
PY5EOF
cat > "$D/app/api/__init__.py" <<'PY6EOF'
from fastapi import FastAPI
from .routes import router as api_router
app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
PY6EOF
mk_policy_fastapi "$D" "$EXEMPT_HEALTH"

# --- MINOR-2: duplicate/conflicting exemptions must be a finding ------------
D="$TMPROOT/dup-exemption"; mk_fastapi "$D" ", _: None = Depends(require_api_token)"
mk_policy_fastapi "$D" "$EXEMPT_HEALTH
  - service: svc
    method: GET
    path: /api/v1/health
    class: known-gap
    justification: \"Conflicting duplicate of the entry above; silently last-wins.\""

# --- MINOR-3: malformed policy must ERROR (2), not read as a route finding --
D="$TMPROOT/malformed-policy"; mk_fastapi "$D" ", _: None = Depends(require_api_token)"
printf 'schema_version: 1\nservices: [unclosed\n  - id: svc\n' > "$D/policy.yaml"

# ============================ REVIEW-ROUND-3 FIXTURES ======================
# BLOCKING-1: a `return` inside a COMMENT or a CLOSURE is not a function-level
# return. Accepting either is a false attribution of SAFETY — the exact class
# IMPORTANT-2 existed to kill, reintroduced inside its own fix.
D="$TMPROOT/gomux-comment-carrier"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'GO5EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/admin/wipe", d.Admin.Wipe)
	// TODO: return WithAuth(mux) once BOB-197 lands
	return mux
}
GO5EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' ""

D="$TMPROOT/gomux-closure-return"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'GO6EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/admin/wipe", d.Admin.Wipe)
	makeAuthed := func() http.Handler { return WithAuth(mux) }
	_ = makeAuthed
	return mux
}
GO6EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' ""

# false-positive guard: the REAL jackett shape — HandleFunc closures around a
# genuine wrap — must still PASS, or the BLOCKING fix breaks production.
D="$TMPROOT/gomux-real-closure-ok"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'GO7EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			d.Credentials.HandleList(w, r)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})
	return WithCORS(nil, WithAuth(mux))
}
GO7EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' ""

# IMPORTANT-1: gin owner blanket + registration-order semantics.
mk_gin_case() {  # <dir> <body>
  local d="$1"; mkdir -p "$d/cmd"
  cat > "$d/cmd/main.go" <<GO8EOF
package main

func main() {
$2
	r.Run(":7187")
}
GO8EOF
  mk_policy_go "$d" gin cmd '"AuthMW"' '  - service: svc
    method: GET
    path: /health
    class: public-by-design
    justification: "Liveness probe."'
}
mk_gin_case "$TMPROOT/gin-second-engine" '	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	r2 := gin.New()
	r2.POST("/api/v1/evil", api.EvilHandler)'
mk_gin_case "$TMPROOT/gin-use-after-route" '	r := gin.Default()
	r.POST("/api/v1/early", api.EarlyHandler)
	r.Use(middleware.AuthMW())
	r.POST("/api/v1/late", api.LateHandler)'
mk_gin_case "$TMPROOT/gin-group-inherit" '	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	v1 := r.Group("/api/v1")
	v1.POST("/download", api.DownloadHandler)'

# MINOR-A: a guard alias that is conditional or re-assigned must fail CLOSED.
mk_alias_case() {  # <dir> <alias_block>
  local d="$1"; mkdir -p "$d/app/api"
  cat > "$d/app/api/routes.py" <<PY7EOF
import os
from fastapi import APIRouter, Depends, Request
router = APIRouter(tags=["t"])

def require_api_token(request: Request) -> None:
    return

def noop_guard(request: Request) -> None:
    return

$2

@router.get("/health")
async def health():
    return {"ok": True}

@router.post("/download")
async def download(req: Request, _: None = _g):
    return {"ok": True}
PY7EOF
  cat > "$d/app/api/__init__.py" <<'PY8EOF'
from fastapi import FastAPI
from .routes import router as api_router
app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
PY8EOF
  mk_policy_fastapi "$d" "$EXEMPT_HEALTH"
}
mk_alias_case "$TMPROOT/alias-conditional" 'if os.getenv("DISABLE_AUTH"):
    _g = Depends(noop_guard)
else:
    _g = Depends(require_api_token)'
mk_alias_case "$TMPROOT/alias-reassigned" '_g = Depends(require_api_token)
_g = Depends(noop_guard)'


# ============================ REVIEW-ROUND-4 FIXTURES ======================
# BLOCKING-4 (round 3): Go's lexical modes carry ACROSS lines. The pre-fix
# engine modelled them with a MISMATCHED mix — a whole-text DOTALL regex for
# /* */ but LINE-scoped scanners for // and for string literals — so a
# multi-line RAW STRING (backticks), which is the string analogue of a block
# comment, lost its state at every newline and each interior line was re-read
# as FRESH CODE. A `return WithAuth(mux)` sitting inside a doc string then
# PROVED a wrap that does not exist: the carrier-proves-authentication class
# round 2 killed for `//`, reintroduced through the one string form a
# line-scoped blanker cannot see (§11.4.201(7)(a)).
#
# Two further defects share that one root:
#   * `/*` inside a `//` comment — the whole-text regex ran BEFORE `//`
#     handling, so it blanked the intervening REAL wrap and reported a
#     genuinely-authenticated route as UNAUTHENTICATED (a §11.4.201(1)
#     FAIL-bluff: a gate that cries wolf gets bypassed).
#   * an UNTERMINATED `/*` never matched `/\*.*?\*/`, so a fake wrap inside it
#     survived and PROVED the wrap — a fail-OPEN on exactly the "cannot lex
#     this" construct where the discipline is to fail CLOSED (§11.4.252).
#
# Every fixture below ships with its content-flip control, so a verdict change
# is proven caused by STRING/COMMENT CONTENT and by nothing else.

mk_r4() {  # mk_r4 <name> [exemptions]   — router.go body arrives on STDIN
  local d="$TMPROOT/$1"
  mkdir -p "$d/jackettapi"
  { printf 'package jackettapi\n\nimport "net/http"\n\n'; cat; } > "$d/jackettapi/router.go"
  mk_policy_go "$d" gomux jackettapi '"WithAuth"' "${2:-}"
}

# --- R4-1 multi-line raw string carrying a fake wrap (THE BLOCKING shape) ---
mk_r4 gomux-rawstring-carrier <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/debug/wipe", d.Debug.HandleWipe)
	const usage = `boba-jackett debug mux
	  the authenticated variant would
	  return WithAuth(mux)
	`
	_ = usage
	return mux
}
R4EOF

# control: byte-identical but for the raw string's CONTENT. Still a finding,
# and it already was one pre-fix — so the pre-fix flip to PASS on the fixture
# above is attributable to the string content alone.
mk_r4 gomux-rawstring-innocuous <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/debug/wipe", d.Debug.HandleWipe)
	const usage = `boba-jackett debug mux
	  the authenticated variant would
	  be documented over here
	`
	_ = usage
	return mux
}
R4EOF

# false-positive guard (§11.4.201(1)): a multi-line raw string beside a GENUINE
# wrap must still PASS — the new lexer must not eat real code after a string.
mk_r4 gomux-rawstring-real-wrap-ok <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/debug/wipe", d.Debug.HandleWipe)
	const usage = `boba-jackett debug mux
	  be documented over here
	`
	_ = usage
	return WithAuth(mux)
}
R4EOF

# --- R4-2 `/*` opened inside a `//` line comment (the FAIL-bluff minor) -----
# `//` wins: everything after it on that line is comment TEXT, so the `/*` is
# not a block-comment open and the real wrap below survives.
mk_r4 gomux-blockopen-in-linecomment <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	// legacy note: /* the pre-BOB-102 shim lived here
	return WithAuth(mux)
	// and its trailing marker was */ left behind
}
R4EOF

# --- R4-3 unterminated /* — fail CLOSED, never fail open -------------------
# security-relevant: the dangling comment hides a fake wrap.
mk_r4 gomux-unterminated-block-hides-wrap <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/admin/wipe", d.Admin.Wipe)
	return mux
}

/* dangling block comment, never closed:
   the authenticated variant would
   return WithAuth(mux)
R4EOF

# the discriminator: the routes here are GENUINELY wrapped and the dangling
# comment is innocuous, so ONLY the fail-closed unlexable rule can fail this.
mk_r4 gomux-unterminated-block-otherwise-clean <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}

/* dangling block comment, never closed — a truncated file nothing can lex
R4EOF

# same discipline for the string half of the grammar.
mk_r4 gomux-unterminated-rawstring <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}

const truncated = `never closed
R4EOF

# --- R4-4 `/*` INSIDE a raw string is not a comment open -------------------
# pre-fix the whole-text regex paired the two markers and SWALLOWED the route
# registration between them: the mutating route simply vanished from the scan
# and the gate blessed a tree it could not see (§11.4.201(6) FALSE-NULL).
mk_r4 gomux-blockmarker-in-rawstring "$EXEMPT_HEALTHZ" <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	const openDoc = `usage: /* example block starts`
	mux.HandleFunc("/api/v1/jackett/debug/wipe", d.Debug.HandleWipe)
	const closeDoc = `example block ends */`
	_, _ = openDoc, closeDoc
	return mux
}
R4EOF

# --- R4-5 `//` inside a raw string is not a comment open -------------------
mk_r4 gomux-linecomment-marker-in-rawstring <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	const doc = `see http://example.invalid // not a comment
	  still inside the raw string`
	_ = doc
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}
R4EOF

# --- R4-6 a backtick INSIDE a block comment must not open a raw string -----
# if it did, raw mode would swallow the registration AND the wrap below.
mk_r4 gomux-backtick-in-blockcomment <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	/*
	   legacy: the shim printed a `raw string banner
	   and then returned the mux
	*/
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}
R4EOF

# --- R4-7 escapes apply in an interpreted string ---------------------------
mk_r4 gomux-escaped-quote-carrier <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/admin/wipe", d.Admin.Wipe)
	msg := "he said \" return WithAuth(mux) \" and left"
	_ = msg
	return mux
}
R4EOF

# --- R4-8 escapes DO NOT apply in a raw string -----------------------------
# a trailing backslash must not consume the closing backtick; if it did, raw
# mode would run on and swallow the registration and the wrap.
mk_r4 gomux-rawstring-trailing-backslash <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	const winPath = `C:\jackett\config\`
	_ = winPath
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}
R4EOF

# --- R4-9 a backtick inside a RUNE literal must not open a raw string ------
mk_r4 gomux-backtick-in-rune <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	sep := '`'
	_ = sep
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}
R4EOF

# --- R4-10 an unterminated "..." / '...' at END OF LINE is also unlexable ----
# Neither form may span a line in Go. The routes here are GENUINELY wrapped, so
# only the fail-closed rule can fail this fixture (it is what kills a mutation
# that stops refusing the truncated literal).
mk_r4 gomux-unterminated-interpreted-string <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	msg := "never closed
	_ = msg
	return WithAuth(mux)
}
R4EOF

# --- R4-11 a route path written as a RAW string must FAIL CLOSED ------------
# Every route regex reads its path out of a "..." literal, so a backtick path
# is not resolvable. It must surface as an unmodelled registration — never
# silently vanish from the scan (§11.4.201(6) FALSE-NULL).
mk_r4 gomux-rawstring-route-path <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc(`/api/v1/jackett/debug/wipe`, d.Debug.HandleWipe)
	return WithAuth(mux)
}
R4EOF

# --- R4-12 the SAME carrier class in the gin extractor ----------------------
# COVERAGE ESCAPE found 2026-08-26 while fixing the raw-string BLOCKING, and
# closed with it (§11.4.238): `code` keeps interpreted-string literals because
# route paths are read out of them, so scanning `code` for a CALL let a literal
# carry the call. Measured: a single log line reading
#   log.Println("hint: r.Use(middleware.AuthMW())")
# flipped the gate to PASS — every route on `r` marked covered by a string —
# while the byte-identical innocuous-content control correctly FAILED. The rule
# now is uniform across both Go extractors: a construct counts only when its
# CODE SKELETON survives in `bare`; a literal may supply the PATH, never the call.
mk_gin_case "$TMPROOT/gin-use-carrier-in-string" '	r := gin.Default()
	r.GET("/health", api.HealthHandler)
	log.Println("hint: r.Use(middleware.AuthMW())")
	r.POST("/api/v1/download", api.DownloadHandler)'

mk_gin_case "$TMPROOT/gin-use-carrier-in-rawstring" '	r := gin.Default()
	r.GET("/health", api.HealthHandler)
	const usage = `to protect every route add
	r.Use(middleware.AuthMW())
	`
	_ = usage
	r.POST("/api/v1/download", api.DownloadHandler)'

# control: identical shape, innocuous string content — still a finding, and it
# was one before the fix too, so the pre-fix PASS above is attributable to the
# string content alone.
mk_gin_case "$TMPROOT/gin-use-carrier-control" '	r := gin.Default()
	r.GET("/health", api.HealthHandler)
	log.Println("hint: nothing to see here")
	r.POST("/api/v1/download", api.DownloadHandler)'

# false-positive guard: a GENUINE .Use(marker) must still cover its routes.
mk_gin_case "$TMPROOT/gin-real-use-ok" '	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	r.POST("/api/v1/download", api.DownloadHandler)'

# the FAIL-bluff direction of the same rule: a doc string that merely MENTIONS
# an unmodelled form must not mint a refusal (§11.4.201(1)).
mk_gin_case "$TMPROOT/gin-any-mentioned-in-string" '	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	log.Println("note: r.Any(\"/x\", h) is not modelled")
	r.POST("/api/v1/download", api.DownloadHandler)'

# and the gomux half: a registration written inside a raw string must not mint
# a PHANTOM route (a route the tree does not actually serve).
mk_r4 gomux-route-carrier-in-rawstring <<'R4EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	const legacy = `the retired shim did other.HandleFunc("/admin/wipe", h)`
	_ = legacy
	return WithAuth(mux)
}
R4EOF

# ============================ REVIEW-ROUND-5 FIXTURES ======================
# ROUND-4 IMPORTANT: a route could still VANISH into a PASS.
#
# `extract_gin` skipped every route on a line that also carried `.Group(`.
# On a normal two-line group declaration `GIN_VERB` never matches the decl
# line, so that skip was only ever REACHED on a compound line — where its sole
# effect was to DROP a route the resolver could otherwise resolve completely:
#
#     g := r.Group("/api/v1"); g.POST("/wipe", api.WipeHandler)
#
# resolved to route_count=1 (the exempted /health alone) and the gate returned
# PASS, so an unauthenticated, mutating, LAN-reachable POST /api/v1/wipe was
# INVISIBLE. The §11.4.201(6) zero-routes FALSE-NULL net cannot fire, because
# the service still resolves its other route. Same defect CLASS as the round-3
# BLOCKING (a route the gate cannot see, blessed SAFE), reached by another door.
#
# The fix REFUSES the whole multi-statement line instead of narrowing the skip,
# because narrowing it alone would have traded a silent DROP for a silent
# FALSE-SAFE: gin middleware is order-dependent and this resolver's ordering
# model is LINE-granular, so `r.POST(...); r.Use(auth)` on one line reads as
# covered when gin gives that route no middleware at all (R5-2 — a door that
# was ALREADY open, with no `.Group(` involved). One rule closes both.

# --- R5-1  gin: a group declaration SHARING A LINE with a registration ------
# THE round-4 IMPORTANT, verbatim. Pre-fix: exit 0 (route dropped).
mk_gin_case "$TMPROOT/gin-compound-group-route" '	r := gin.Default()
	r.GET("/health", api.HealthHandler)
	g := r.Group("/api/v1"); g.POST("/wipe", api.WipeHandler)'

# --- R5-2  gin: `.Use` sharing a line with an EARLIER registration ----------
# The false-SAFE half of the same primitive, reachable with no `.Group(` at
# all: gin applies only middleware installed BEFORE a route, and line-granular
# ordering cannot see the order of two statements on ONE line.
# Pre-fix: exit 0 (route blessed by a `.Use` that does not cover it).
mk_gin_case "$TMPROOT/gin-compound-use-after-route" '	r := gin.Default()
	r.GET("/health", api.HealthHandler)
	r.POST("/api/v1/early", api.EarlyHandler); r.Use(middleware.AuthMW())'

# --- R5-3  false-positive guard for R5-1/R5-2 (§11.4.201(1)) ---------------
# A `;` inside a PATH LITERAL (legal — matrix parameters) or inside a trailing
# `//` comment is NOT a statement separator. The compound test reads `bare`,
# where both are blanked, so neither may mint a refusal. This is the direction
# that kills a mutation moving the test onto `code` or onto the raw line — a
# gate that cries wolf gets bypassed, which is how the whole class comes back.
mk_gin_case "$TMPROOT/gin-semicolon-not-compound" '	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	r.POST("/api/v1/matrix;v=2", api.MatrixHandler) // beware: r.Use(x); order'

# --- R5-4  Mr-A: the gomux fail-closed DEFAULT must be pinned ---------------
# A mux arriving as a FUNCTION PARAMETER (idiomatic dependency injection) is
# not a resolvable `http.NewServeMux()`, so its wrap cannot be resolved and the
# route must fail closed. The shipped engine already gets this right, but no
# fixture killed a flip of `wrapped.get(owner, False)` -> `True`: an invariant
# the gate honours and nothing pins is unvalidated instrumentation
# (§11.4.115(F)). This fixture is that pin.
mk_r4 gomux-param-mux <<'R5EOF'
func Register(mux *http.ServeMux, d *Deps) {
	mux.HandleFunc("/api/v1/jackett/wipe", d.Debug.HandleWipe)
}
R5EOF

# --- R5-5  Mr-H: the gomux skeleton rule's FALSE-POSITIVE direction --------
# The only gomux carrier fixture used a RAW string, whose content is blanked in
# BOTH projections — so it never exercised `MUX_ANY.search(bln)` vs `ln`. An
# INTERPRETED string merely MENTIONING `.HandleFunc(` mints a false refusal
# under that mutation while the shipped gate correctly PASSes. Mirrors the gin
# `gin-any-mentioned-in-string` guard, which had no gomux twin.
mk_r4 gomux-any-mentioned-in-string <<'R5EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	msg := "the retired shim did other.HandleFunc(stuff)"
	_ = msg
	return WithAuth(mux)
}
R5EOF

# --- R5-6  fastapi: a route registered on a DOTTED router expression --------
# THE SAME SILENT-DROP CLASS in the third extractor, found by the round-4
# mirror sweep: `owner = getattr(dec.func.value, "id", None)` is None for
# `@<expr>.<attr>.post(...)`, and the pre-fix engine simply `continue`d — a
# literal-path, mutating route dropped with no finding. Pre-fix: exit 0.
mk_unmodeled_fastapi "$TMPROOT/fastapi-dotted-owner" '
class _Bundle:
    router = router

@_Bundle.router.post("/dotted-wipe")
async def dotted_wipe(req: Request):
    return {"ok": True}'

# --- R5-7  fastapi: `@router.api_route(...)` is a REAL registration deco ----
# Verified against the installed FastAPI source (§11.4.201 authoritative
# source, not memory): fastapi/routing.py:1419 and fastapi/applications.py:1222
# both define `api_route`. Its path IS a literal but its METHODS come from a
# `methods=[...]` kwarg this model does not read, so the route's method set is
# unresolvable -> refuse. Pre-fix it fell through `meth not in HTTP_METHODS`
# and vanished: exit 0.
mk_unmodeled_fastapi "$TMPROOT/fastapi-api-route-deco" '
@router.api_route("/api-route-wipe", methods=["POST"])
async def api_route_wipe(req: Request):
    return {"ok": True}'

# --- R5-8  fastapi: `@router.trace(...)` is a real HTTP verb ---------------
# Verified the same way: fastapi/routing.py:4490 and applications.py:4193
# define `trace`. It was absent from HTTP_METHODS, so a TRACE route vanished
# exactly like R5-7. Pre-fix: exit 0.
mk_unmodeled_fastapi "$TMPROOT/fastapi-trace-unauth" '
@router.trace("/trace-me")
async def trace_me(req: Request):
    return {"ok": True}'

# --- R5-9  ... and TRACE is MODELLED, not merely refused -------------------
# The discriminator between the two possible fixes: refusing `trace` as
# unmodelled would also make R5-8 exit 1, but would mint a FAIL-bluff here on
# a genuinely-wired route. Only modelling it passes both directions.
mk_unmodeled_fastapi "$TMPROOT/fastapi-trace-authed" '
@router.trace("/trace-me")
async def trace_me(req: Request, _: None = Depends(require_api_token)):
    return {"ok": True}'

# --- R5-10 the policy's OWN zero is a FALSE-NULL too ------------------------
# Found by the round-5 skip enumeration, in main() rather than an extractor:
# with `services: []` the scan loop never runs, `blind` never fills, findings
# stay empty and the gate returns PASS — so DELETING the service declarations
# turns the gate green over an open, mutating, LAN-reachable route. Exactly the
# §11.4.201(6) FALSE-NULL the per-service zero-routes check already refuses,
# one level up. `golden-false-loopback` (a service deliberately declared
# lan_bound:false) is the false-positive guard that keeps the rule narrow: this
# refuses an EMPTY declaration list, never a policy that scopes itself.
D="$TMPROOT/policy-no-services"; mkdir -p "$D/app/api"
cat > "$D/app/api/routes.py" <<'PY7EOF'
from fastapi import APIRouter, Request
router = APIRouter()

@router.post("/wipe")
async def wipe(req: Request):
    return {"ok": True}
PY7EOF
printf 'schema_version: 1\nservices: []\nexemptions: []\n' > "$D/policy.yaml"

# --- R5-11 a DOTTED gin receiver must not inherit a same-named engine ------
# Also surfaced by the round-5 enumeration, and REPRODUCED before being called
# a defect: GIN_ROUTE's `(\w+)\.` captures only the LAST identifier of a
# dotted chain, so `s.router.POST("/wipe", h)` resolved to owner "router" and
# inherited the `.Use(marker)` installed on the unrelated LOCAL `router`
# engine. Measured pre-fix: BOTH routes reported auth_wired=true, findings 0,
# gate PASS — a FALSE ATTRIBUTION OF SAFETY on an unauthenticated mutating LAN
# route, which this engine's own docstring calls categorically worse than
# failing to see a route. Not reachable in the shipped gin root (zero
# dotted-receiver registrations, grep-confirmed) — closed anyway, because
# leaving a demonstrated false-SAFE open beside a docstring claiming the
# silent-drop column is empty would be the bluff.
mk_gin_case "$TMPROOT/gin-dotted-owner-false-safe" '	router := gin.Default()
	router.Use(middleware.AuthMW())
	router.GET("/health", api.HealthHandler)
	s := newServer()
	s.router.POST("/api/v1/wipe", api.WipeHandler)'

# false-positive guard (§11.4.201(1)): a DOTTED HANDLER argument is not a
# dotted RECEIVER. The handler position deliberately carries a two-level dotted
# CALL (`s.api.Wrap(...)`, the shape of any middleware-chaining helper), not
# merely a dotted VALUE — an earlier draft of this fixture used
# `s.api.DownloadHandler` and a reviewer-style mutation dropping the verb
# requirement from GIN_DOTTED_OWNER SURVIVED it, because a dotted value is
# followed by `)` and never by `(`. A guard that cannot see the mutation it
# exists for is unvalidated instrumentation (§11.4.115(F)), so it was
# strengthened until the mutation died.
mk_gin_case "$TMPROOT/gin-dotted-handler-ok" '	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	r.POST("/api/v1/download", s.api.Wrap(api.DownloadHandler))'

# ===========================================================================
# review round 6 — THE CREDIT-BEARING PRIMITIVE (§11.4.250)
# ===========================================================================
# Round 5 fixed ONE dotted-receiver leak (GIN_ROUTE) because that was the one
# reported. Round 6's review named the real primitive: *a credit must never be
# attributed across a scope boundary the resolver cannot see* — and that has to
# hold for EVERY construct able to mark a route protected, not just the one
# that was reported. The credit-bearing constructs this engine uses were walked
# against that rule; the four that leaked are pinned below, each REPRODUCED
# against the shipped analyzer before being called a defect (§11.4.199), each
# with its §11.4.201(1) false-positive guard.
#
# ROUND-7 CORRECTION: this comment used to read "EVERY credit-bearing construct
# ... was audited", which is a completeness claim, and round 7 falsified it in
# two constructs that same audit had recorded as "measured fail-closed" (see
# the round-7 section below). "Audited" records where somebody looked; it does
# not establish that nothing else leaks (§11.4.118). The wording is now a
# stated method over an enumerated set — the same form round 6 had already
# adopted for the DROPS column, one column too late.
#
# A false attribution of SAFETY is categorically worse than a dropped route:
# the gate does not merely fail to see the route, it asserts the route is
# protected. All four fixtures below are that class.

mk_gin_file() {  # mk_gin_file <name> — WHOLE file body arrives on STDIN
  local d="$TMPROOT/$1"; mkdir -p "$d/cmd"
  { printf 'package main\n\n'; cat; } > "$d/cmd/main.go"
  mk_policy_go "$d" gin cmd '"AuthMW"' '  - service: svc
    method: GET
    path: /health
    class: public-by-design
    justification: "Liveness probe."'
}

# --- R6-1  gin: a DOTTED `.Use` must not credit a same-named local engine ---
# The round-5 fix put the `(?<![\w.])` lookbehind on GIN_ROUTE and left
# GIN_USE without one, so the CREDIT side of the same primitive stayed open.
# Reproduced against the shipped analyzer before this fixture was written:
# a local `router := gin.New()` carrying NO middleware, a `.Use(marker)` on the
# unrelated struct field `s.router`, and `router.POST("/api/v1/wipe", …)` came
# back auth_wired=true, resolution "owner 'router' carries .Use(marker)",
# findings 0, exit 0 — an unauthenticated mutating LAN route blessed SAFE.
mk_gin_case "$TMPROOT/gin-dotted-use-false-safe" '	router := gin.New()
	router.GET("/health", api.HealthHandler)
	s := newServer()
	s.router.Use(middleware.AuthMW())
	router.POST("/api/v1/wipe", api.WipeHandler)'

# false-positive guard (§11.4.201(1)): dropping the dotted credit must not
# drop the BARE one. Same file carries both spellings on the same identifier;
# the bare `.Use` still covers the route, so this must PASS. Without this
# guard, a mutation replacing the lookbehind with something that kills every
# `.Use` would go unnoticed — and a gate that cries wolf gets bypassed.
mk_gin_case "$TMPROOT/gin-bare-use-still-credits" '	r := gin.New()
	r.Use(middleware.AuthMW())
	s.r.Use(middleware.SomethingElse())
	r.GET("/health", api.HealthHandler)
	r.POST("/api/v1/ok", api.OkHandler)'

# --- R6-2  gomux: a DOTTED mux receiver must not inherit a local mux wrap ---
# The identical primitive in the third extractor, found by this round's audit
# rather than reported: MUX_ROUTE's `(\w+)\.` also captures only the LAST name
# of a chain, so `s.mux.HandleFunc("/api/v1/wipe", …)` resolved to owner "mux"
# and inherited the `return WithAuth(mux)` wrap of an unrelated LOCAL mux.
# Measured pre-fix: auth_wired=true on the mutating route, findings 0, exit 0.
mk_r4 gomux-dotted-receiver-false-safe <<'R6EOF'
func NewMux(s *Server) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", s.Health)
	s.mux.HandleFunc("/api/v1/wipe", s.Wipe)
	return WithAuth(mux)
}
R6EOF

# false-positive guard: a BARE receiver on the wrapped mux must still be
# credited, so the refusal is proven to key on the DOTTED spelling and not on
# `.HandleFunc` in general.
mk_r4 gomux-bare-receiver-still-credits <<'R6EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health)
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}
R6EOF

# --- R6-3  gin: two engines with the SAME NAME in one file must refuse ------
# `engines` was keyed by NAME, so two functions each declaring `r := gin.New()`
# collapsed to ONE entry, the multi-engine refusal never fired, and `uses` is
# file-scoped — so `setupAdmin`'s `r.Use(auth)` credited `setupPublic`'s
# unauthenticated route. Measured pre-fix: BOTH routes auth_wired=true,
# findings 0, exit 0. Keying on DECLARATION SITES rather than names closes it;
# refusing is correct, because cross-engine sharing is exactly what the
# existing multi-engine message already says this model does not resolve.
mk_gin_file gin-two-engines-same-name <<'R6EOF'
func setupAdmin() {
	r := gin.New()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
}

func setupPublic() {
	r := gin.New()
	r.POST("/api/v1/wipe", api.WipeHandler)
}
R6EOF

# false-positive guard: ONE declaration site whose engine is used in two
# functions must NOT refuse — the rule keys on sites, not on how widely the
# value travels.
mk_gin_file gin-one-engine-two-funcs <<'R6EOF'
func setup() *gin.Engine {
	r := gin.New()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	return r
}

func more(r *gin.Engine) {
	r.POST("/api/v1/ok", api.OkHandler)
}
R6EOF

# --- R6-4  fastapi: a RE-ASSIGNED router must not back-credit earlier routes -
# `router_authed[(mod, name)]` is a dict keyed on the NAME, so a later
# `router = APIRouter(dependencies=[Depends(marker)])` overwrote the entry for
# the earlier bare `router = APIRouter()` and credited every route registered
# on it. Measured pre-fix: POST /early-wipe — registered on the router that
# carries NO dependencies — reported auth_wired=true with resolution
# "router-level dependencies=[Depends(marker)]", findings 0, exit 0.
# This is the ROUTER analogue of the guard-alias rule that already refuses a
# re-assigned alias; the same fail-closed treatment now applies to the router.
D="$TMPROOT/fastapi-router-reassign"; mkdir -p "$D/app/api"
cat > "$D/app/api/routes.py" <<'R6EOF'
from fastapi import APIRouter, Depends, Request

def require_api_token(request: Request) -> None:
    return

router = APIRouter()

@router.post("/early-wipe")
async def early_wipe(req: Request):
    return {"ok": True}

router = APIRouter(dependencies=[Depends(require_api_token)])

@router.post("/late-wipe")
async def late_wipe(req: Request):
    return {"ok": True}
R6EOF
mk_policy_fastapi "$D" "  []"

# false-positive guard: a SINGLE router carrying router-level dependencies
# must still credit its routes, so the refusal is proven to key on
# RE-ASSIGNMENT and not on router-level dependencies as such.
D="$TMPROOT/fastapi-router-level-deps-ok"; mkdir -p "$D/app/api"
cat > "$D/app/api/routes.py" <<'R6EOF'
from fastapi import APIRouter, Depends, Request

def require_api_token(request: Request) -> None:
    return

router = APIRouter(dependencies=[Depends(require_api_token)])

@router.post("/guarded")
async def guarded(req: Request):
    return {"ok": True}
R6EOF
mk_policy_fastapi "$D" "  []"

# --- R6-5..R6-8  fastapi: FOUR demonstrated silent drops -------------------
# Round 6's review went into extract_fastapi — a surface no earlier round had
# attacked — and found four registration idioms that vanish into exit 0. Each
# was verified to be a REAL registration in the INSTALLED FastAPI source
# (§11.4.201 authoritative source, never memory) before being called a defect,
# then reproduced against the shipped analyzer: all four gave exit 0 PASS with
# the mutating route gone and zero findings.
#
# They also falsify TWO of the enumeration's FILTER justifications, which are
# corrected in the analyzer's own skip table this round:
#   * "caught separately by FASTAPI_UNMODELLED_CALLS" — false: R6-5 and R6-7
#     register through `post`, which is not in that tuple.
#   * "a bare-name … decorator cannot be `@router.get("/p")`" — false: R6-8's
#     `@reg(...)` IS a bare-name Call that registers a route.

# R6-5  immediate-call registration: `router.post("/wipe")(wipe)`.
# `post()` returns `self.api_route(..., methods=["POST"])` (routing.py:2945),
# whose returned decorator calls `add_api_route` — a genuine registration that
# never passes through a decorator_list at all.
mk_unmodeled_fastapi "$TMPROOT/fastapi-immediate-call" '
async def wipe(req: Request):
    return {"ok": True}

router.post("/wipe")(wipe)'

# R6-6  `@router.route("/wipe", methods=["POST"])`.
# A REAL registration decorator at routing.py:1317 — 102 lines ABOVE the
# `api_route` at 1419 that round 5 cited. Round 5 ran the right method (check
# the verb list against the installed source) but ran it INCOMPLETELY, catching
# `trace` and `api_route` and missing their sibling in the same file. `route`
# calls `add_route`, which builds a plain starlette Route: FastAPI dependency
# injection never runs on it, so `Depends` can NEVER reach it and it can never
# be modelled as protected. It therefore belongs in the refused set, not in
# HTTP_METHODS.
mk_unmodeled_fastapi "$TMPROOT/fastapi-route-deco" '
@router.route("/route-wipe", methods=["POST"])
async def route_wipe(req: Request):
    return {"ok": True}'

# R6-7  a route decorator on a ClassDef: the decorator loop visits only
# FunctionDef/AsyncFunctionDef, so `@router.post("/wipe")` above a class was
# stepped over with no finding.
mk_unmodeled_fastapi "$TMPROOT/fastapi-classdef-deco" '
@router.post("/class-wipe")
class WipeEndpoint:
    pass'

# R6-8  bound-method alias: `reg = router.post` then `@reg("/alias-wipe")`.
# The decorator IS a Call, but its func is a bare Name, so the
# "decorator is not `<attr-expr>(...)`" filter stepped over it.
mk_unmodeled_fastapi "$TMPROOT/fastapi-bound-alias" '
reg = router.post

@reg("/alias-wipe")
async def alias_wipe(req: Request):
    return {"ok": True}'

# false-positive guard for R6-5/R6-7/R6-8 (§11.4.201(1)) — LOAD-BEARING.
# The review's suggested remedy shape ("refuse any Call whose func.attr is an
# HTTP verb outside modelled decorator position") could NOT ship as written:
# `.get` is an HTTP verb AND the most common method name in Python. A blanket
# rule fires on `d.get(k)`, `os.environ.get(k)`, `requests.post(...)`,
# `self.session.get(...)` — the §11.4.201(1) false-positive machine this
# engine's own docstring warns about two lines below the filter it would
# replace. The shipped rule is narrowed by OWNER: the attribute only counts
# when its owner is a router this module actually declared. This fixture is
# what proves the narrowing, and it must PASS.
mk_unmodeled_fastapi "$TMPROOT/fastapi-verbnames-not-routers" '
import os
import requests

_cfg = {"a": 1}

async def helper(req: Request):
    _ = _cfg.get("a")
    _ = os.environ.get("HOME")
    _ = requests.get("http://example.invalid")
    _ = requests.post("http://example.invalid", json={})
    return {"ok": True}'

# --- R6-9  the websocket refusals were UNPINNED (round-6 MINOR) ------------
# Dropping "websocket" from FASTAPI_UNMODELLED_DECOS makes `@router.websocket`
# vanish into a PASS, and that mutation SURVIVED the whole round-5 harness
# (63 fixtures at the time) — the count is history, not a claim about today's.
# An invariant the engine honours and nothing pins is unvalidated
# instrumentation (§11.4.115(F)) — the same class as the round-5 Mr-A gap.
mk_unmodeled_fastapi "$TMPROOT/fastapi-websocket-refused" '
@router.websocket("/ws-wipe")
async def ws_wipe(ws):
    return None'

# --- R6-10  gin: a selector split across lines is NOT "no verb skeleton" ---
# The "line has no HTTP-verb call skeleton" FILTER justified itself with "the
# verb+`(` pair cannot span a newline in gofmt'd Go". That rests on a gofmt
# assumption nothing in this gate enforces: Go inserts no semicolon after a
# trailing `.`, so `r.` on one line and `POST("/api/v1/wipe", …)` on the next
# is legal, compiles, and was silently dropped. The registration is now
# refused, and the FILTER's justification is corrected to say what actually
# holds.
mk_gin_case "$TMPROOT/gin-selector-continuation" '	r := gin.New()
	r.GET("/health", api.HealthHandler)
	r.
		POST("/api/v1/wipe", api.WipeHandler)'

# false-positive guard: an ordinary trailing-dot continuation that is NOT a
# route registration (a fluent builder chain) must not mint a refusal.
mk_gin_case "$TMPROOT/gin-continuation-not-a-route" '	r := gin.New()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	cfg := builder.
		WithTimeout(5).
		Build()
	_ = cfg
	r.POST("/api/v1/ok", api.OkHandler)'

# --- R6-11  the multi-statement refusal's BOUNDARY, pinned ----------------
# Round 6 flagged that the whole-line refusal also fires on a gofmt-stable,
# single-registration line whose `;` lives inside a closure body:
#     r.POST("/p", func(c *gin.Context) { c.Status(200); c.Done() })
# That is ONE registration whose coverage IS line-decidable, so the refusal is
# conservative rather than necessary here. It is loud and fail-closed, so it is
# not a defect — but it was undocumented, and an undocumented boundary is how a
# gate acquires a reputation for crying wolf. The behaviour is now OWNED in the
# source comment and PINNED here, so a future narrowing has to change this
# fixture deliberately rather than drift past it.
mk_gin_case "$TMPROOT/gin-semicolon-in-closure-body" '	r := gin.New()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	r.POST("/api/v1/inline", func(c *gin.Context) { c.Status(200); c.Done() })'


# --- R6-12  EVERY refusal must be PINNED, not merely present --------------
# Round 6's review found `websocket` unpinned (dropping it from the refused set
# made `@router.websocket("/ws-wipe")` vanish into a PASS while surviving the
# whole harness). Writing the retraction above forced the obvious question:
# is that the ONLY unpinned refusal? It was not. Measured by removal-mutation
# against a scratch copy, SIX refusals survived their own deletion:
#   websocket_route · gin `.Match` · gin `.NoRoute` · http.DefaultServeMux ·
#   unknown service kind · exemption missing service/path
# Each is a REFUSES verdict the engine honours and nothing held it to — the
# §11.4.115(F) unvalidated-instrumentation class. They are pinned below, so
# the docstring's "every REFUSES verdict is pinned by a fixture that dies when
# the refusal is removed" is a MEASURED statement rather than another
# unearned claim of the kind this round exists to retract.

mk_unmodeled_fastapi "$TMPROOT/fastapi-websocket-route-refused" '
@router.websocket_route("/ws-route-wipe")
async def ws_route_wipe(ws):
    return None'

# one fixture per gin form this engine refuses — the whole GIN_UNMODELLED set,
# so no single member can be dropped from it unnoticed.
for _v in Any Match Handle Static StaticFile StaticFS StaticFileFS NoRoute NoMethod; do
  mk_unmodeled_gin "$TMPROOT/gin-unmodelled-$_v" "	r.$_v(\"/api/v1/evil-$_v\", api.EvilHandler)"
done

# the global http.DefaultServeMux: no returned handler can wrap it, so a route
# registered there is unprotectable by construction.
#
# THE EXEMPTION IS LOAD-BEARING, not decoration. Without it this fixture cannot
# fail: with the refusal removed the route still resolves UNAUTHENTICATED and
# still exits 1, so the fixture passes either way and pins nothing — the
# could-not-fail shape (§11.4.115(F)). Exempting the route suppresses the
# unauthenticated finding, leaving the REFUSAL as the only thing that can make
# this fixture exit 1. Measured: it now kills the removal mutation.
mk_r4 gomux-defaultservemux '  - service: svc
    method: ANY
    path: /api/v1/global-wipe
    class: known-gap
    justification: "Fixture-only: isolates the DefaultServeMux refusal."' <<'R6EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health)
	http.HandleFunc("/api/v1/global-wipe", d.Debug.HandleWipe)
	return WithAuth(mux)
}
R6EOF

# a policy naming an extractor this engine does not have must REFUSE, never
# quietly resolve zero routes for that service.
D="$TMPROOT/policy-unknown-kind"; mkdir -p "$D/app/api"
cat > "$D/app/api/routes.py" <<'R6EOF'
from fastapi import APIRouter, Request
router = APIRouter()

@router.post("/wipe")
async def wipe(req: Request):
    return {"ok": True}
R6EOF
cat > "$D/policy.yaml" <<'R6EOF'
schema_version: 1
services:
  - id: svc
    kind: express
    lan_bound: true
    roots: ["app/api"]
    auth_markers: ["require_api_token"]
exemptions: []
R6EOF

# an exemption missing its required fields is not a silent no-op: an entry
# nobody can match is an entry nobody can review.
D="$TMPROOT/exemption-missing-path"; mkdir -p "$D/app/api"
cat > "$D/app/api/routes.py" <<'R6EOF'
from fastapi import APIRouter, Depends, Request
router = APIRouter()

def require_api_token(request: Request) -> None:
    return

@router.post("/wipe")
async def wipe(req: Request, _: None = Depends(require_api_token)):
    return {"ok": True}
R6EOF
mk_policy_fastapi "$D" '  - service: svc
    method: GET
    class: public-by-design
    justification: "Missing its path field entirely."'

# ===========================================================================
# review round 7 — THE CREDIT-BEARING PRIMITIVE, THE REMAINING DOORS
# ===========================================================================
# Round 6 fixed the four credit leaks its own audit found and then wrote a
# FRESH completeness claim on the credit side ("every construct able to mark a
# route protected was audited; the four that leaked are pinned"). Round 7's
# review falsified it twice, in two constructs that audit had explicitly
# recorded as "measured fail-closed" — so the claim is retracted here in the
# same enumerated-set / stated-method / honest-gap form round 6 built for the
# DROPS column (§11.4.118: an absolute is the one thing inspection cannot
# earn). Each fixture below was REPRODUCED against the shipped analyzer before
# being called a defect (§11.4.199), and each is paired with its
# §11.4.201(1) false-positive guard.

# --- R7-1  gin: a group NAME re-bound by an UNRESOLVABLE declaration --------
# `groups` was keyed on the NAME and scoped to the FILE. A dotted-parent group
# declaration is correctly invisible to GIN_GROUP, so the name silently kept
# its EARLIER binding and the later registration inherited that binding's
# prefix AND its coverage. Pre-fix (measured 2026-08-26):
#   POST /admin/wipe auth_wired=true, findings 0, exit 0
# — a wrong path AND an unauthenticated mutating LAN route blessed SAFE. The
# A2/A3 per-declaration-SITE rule, applied one construct over (§11.4.250).
mk_gin_file gin-group-dotted-parent-false-safe <<'R7EOF'
func setup() {
	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	g := r.Group("/admin")
	g.GET("/status", api.StatusHandler)
}

func setupPublic(s *Server) {
	g := s.pub.Group("/public")
	g.POST("/wipe", api.WipeHandler)
}
R7EOF

# --- R7-2  gin: the same name bound TWICE, both resolvable ------------------
# The half that needs no dotted receiver at all: two bare `Group(` declarations
# of one name. Last-wins meant the EARLIER route inherited the LATER group, so
# ordering alone decided whether the leak fired. Pre-fix, with the public group
# declared first: POST /wipe resolved to /admin/wipe, auth_wired=true, exit 0.
mk_gin_file gin-group-rebound-false-safe <<'R7EOF'
func setupPublic(pub *gin.RouterGroup) {
	g := pub.Group("/public")
	g.POST("/wipe", api.WipeHandler)
}

func setup() {
	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	g := r.Group("/admin")
	g.GET("/status", api.StatusHandler)
}
R7EOF

# --- R7-3  false-positive guard for R7-1/R7-2 (§11.4.201(1)) ---------------
# TWO groups, DISTINCT names, each declared exactly once: both must still
# inherit the engine's `.Use` and the gate must PASS. Without this guard a
# mutation widening the ambiguity rule to "any file with more than one group"
# — or dropping every group credit outright — would go unnoticed, and a gate
# that cries wolf on the real tree's own shape (`v1` + `schedules`) gets
# bypassed. This IS the real tree's shape.
mk_gin_file gin-two-groups-distinct-names-ok <<'R7EOF'
func main() {
	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	v1 := r.Group("/api/v1")
	v1.POST("/download", api.DownloadHandler)
	schedules := r.Group("/api/v1/schedules")
	schedules.POST("", api.CreateScheduleHandler)
}
R7EOF

# --- R7-4  gomux: MUX_DECL had no lookbehind -------------------------------
# Round 6 put `(?<![\w.])` on MUX_ROUTE and MUX_ANY and left MUX_DECL bare, so
# `s.mux = http.NewServeMux()` declared a bare-name mux that does not exist and
# a genuinely separate local `mux` inherited its wrap. Pre-fix (measured):
# ANY /api/v1/wipe auth_wired=true, findings 0, exit 0.
mk_r4 gomux-dotted-decl-false-safe <<'R7EOF'
func NewMux(s *Server) http.Handler {
	s.mux = http.NewServeMux()
	mux := newBareMux()
	mux.HandleFunc("/api/v1/wipe", s.Debug.HandleWipe)
	return WithAuth(s.mux)
}
R7EOF

# --- R7-5  gomux: the RETURN scan credited through the dot ------------------
# The other half of the same primitive, with a perfectly ordinary declaration:
# `.` is a word boundary, so `return WithAuth(s.mux)` matched `\bmux\b` and
# wrapped the unrelated LOCAL `mux`. Pre-fix: auth_wired=true, exit 0.
mk_r4 gomux-dotted-return-false-safe <<'R7EOF'
func NewMux(s *Server) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/wipe", s.Debug.HandleWipe)
	return WithAuth(s.mux)
}
R7EOF

# --- R7-6  false-positive guard for R7-4/R7-5 ------------------------------
# A field mux BESIDE a bare one: the bare declaration must still be seen and
# its genuine wrap must still credit its own route. Kills a mutation that
# closes the dotted door by dropping every declaration or every return credit.
mk_r4 gomux-bare-decl-still-credits <<'R7EOF'
func NewMux(s *Server) http.Handler {
	s.mux = http.NewServeMux()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", s.Credentials.Handle)
	return WithAuth(mux)
}
R7EOF

# --- R7-7  gomux MINOR-2: the RETURN scan's trailing `\b` -------------------
# Round-6 mutation X1 (drop the trailing `\b` from the return-scan name match)
# SURVIVED all 93 fixtures while restoring a measured false credit:
# `WithAuth(muxAdmin)` credits `mux` by prefix. An invariant the engine honours
# and nothing pins is unvalidated instrumentation (§11.4.115(F)) — this is that
# pin. The shipped engine reports `mux` unwrapped; under X1 both muxes come
# back wrapped and the gate turns green.
mk_r4 gomux-return-prefix-not-a-credit <<'R7EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/wipe", d.Debug.HandleWipe)
	muxAdmin := http.NewServeMux()
	muxAdmin.HandleFunc("/admin/ping", d.Admin.Ping)
	return WithAuth(muxAdmin)
}
R7EOF

# --- R7-8  gomux MINOR-1: a COMPOSITE-LITERAL receiver was a SILENT DROP ----
# The dotted-receiver refusal's leading class `[\w)\]]` was an enumerated
# allowlist of "characters an expression can end with", and `}` was not in it.
# `Server{}.mux.HandleFunc(...)` therefore matched neither the refusal nor the
# bare-owner path (whose lookbehind excludes it), so the route vanished:
# pre-fix exit 0, findings 0, the mutating route absent from the inventory.
# The gin analogue was already refused via its GIN_VERB catch-all, which is
# what falsified the skip-table's "FILTER mirrors gin" justification.
mk_r4 gomux-complit-receiver-refused '  - service: svc
    method: ANY
    path: /healthz
    class: public-by-design
    justification: "Container healthcheck probe; returns no state."' <<'R7EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	Server{}.mux.HandleFunc("/api/v1/wipe", d.Debug.HandleWipe)
	return WithAuth(mux)
}
R7EOF

# --- R7-9  gin NIT-2: the same allowlist, and the LABEL it produced ---------
# `Wrapper{}.engine.POST("/p", h)` was refused (right verdict) under
# "path is not a string literal on the same line" — untrue of that line, the
# second instance of the F8 mislabel class round 6 fixed once. The exit code
# alone cannot see a wrong label, so the diagnostic assertion below is what
# actually pins this one.
mk_gin_file gin-complit-receiver-labelled <<'R7EOF'
func main() {
	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	Wrapper{}.engine.POST("/api/v1/wipe", api.WipeHandler)
}
R7EOF

# --- R7-10 fastapi IMPORTANT-3: the router-attribute rule was SAME-MODULE ---
# `(mod, name) in router_prefix` asks "did THIS module declare it?", so
# `from .routers import router` + `router.post("/wipe")(wipe)` in the importing
# module resolved to no router, minted no refusal, and the mutating route
# VANISHED — R6-5 resurrected through a one-line import. Pre-fix: findings 0,
# exit 0, route absent. The engine already resolved imports for guard aliases
# and for mounts, so same-module keying was an omission, not a necessity.
D="$TMPROOT/fastapi-imported-router-immediate-call"; mkdir -p "$D/app/api"
cat > "$D/app/api/routers.py" <<'R7EOF'
from fastapi import APIRouter, Request
router = APIRouter(tags=["t"])

def require_api_token(request: Request) -> None:
    return

@router.get("/health")
async def health():
    return {"ok": True}
R7EOF
cat > "$D/app/api/extra.py" <<'R7EOF'
from fastapi import Request
from .routers import router

async def wipe(req: Request):
    return {"ok": True}

router.post("/wipe")(wipe)
R7EOF
cat > "$D/app/api/__init__.py" <<'R7EOF'
from fastapi import FastAPI
from .routers import router as api_router
app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
R7EOF
mk_policy_fastapi "$D" "$EXEMPT_HEALTH"

# --- R7-11 false-positive guard for R7-10 (§11.4.201(1)) -------------------
# Resolving the owner THROUGH imports must not drop the owner qualification
# that makes the rule shippable: `.get`/`.post` are the two commonest method
# names in Python, so an IMPORTED NON-ROUTER using them must stay silent. This
# is `fastapi-verbnames-not-routers` re-aimed at the new import hop — without
# it, a mutation that resolves any imported name would fire on every cache and
# every HTTP client in the tree, and a gate that cries wolf gets bypassed.
D="$TMPROOT/fastapi-imported-nonrouter-quiet"; mkdir -p "$D/app/api"
cat > "$D/app/api/store.py" <<'R7EOF'
class _Store:
    def get(self, k):
        return None

    def post(self, k, v):
        return None

cache = _Store()
R7EOF
cat > "$D/app/api/routes.py" <<'R7EOF'
from fastapi import APIRouter, Depends, Request
from .store import cache
router = APIRouter(tags=["t"])

def require_api_token(request: Request) -> None:
    return

@router.get("/health")
async def health():
    return {"ok": True}

@router.post("/download")
async def download(req: Request, _: None = Depends(require_api_token)):
    cache.get("k")
    cache.post("k", 1)
    return {"ok": True}
R7EOF
cat > "$D/app/api/__init__.py" <<'R7EOF'
from fastapi import FastAPI
from .routes import router as api_router
app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
R7EOF
mk_policy_fastapi "$D" "$EXEMPT_HEALTH"

# --- R7-12/13 MINOR-3: two UNPINNED members of FASTAPI_UNMODELLED_CALLS -----
# Deleting `mount`, and deleting `add_route`, each SURVIVED all 93 fixtures:
# only `add_api_route` had a fixture, in contrast to gin, where every
# GIN_UNMODELLED member is deliberately pinned by a per-member loop. A refusal
# nothing kills is a verdict the engine honours with nothing holding it to it.
mk_unmodeled_fastapi "$TMPROOT/fastapi-unmodelled-mount" '
router.mount("/static", StaticFiles(directory="s"), name="static")'

mk_unmodeled_fastapi "$TMPROOT/fastapi-unmodelled-add-route" '
async def sneaky(req: Request):
    return {"ok": True}

router.add_route("/sneaky", sneaky, methods=["POST"])'

# --- R7-14 MINOR-3(iii): the exemption CLASS validation was unpinned --------
# Neutralising the class check survived all 93 fixtures. A typo'd class would
# then be accepted silently and simply stop counting toward the honest-gap
# census the gate prints on every run (§11.4.261) — the number quietly
# understating the real holes, which is the one thing that census exists to
# prevent. The entry below MATCHES a live route, so a stale-exemption finding
# cannot be what makes this fixture exit 1.
D="$TMPROOT/exemption-bad-class"; mk_fastapi "$D" ", _: None = Depends(require_api_token)"
mk_policy_fastapi "$D" '  - service: svc
    method: GET
    path: /api/v1/health
    class: known-gapp
    justification: "Typo in the class name; must not be accepted silently."'

# --- R7-15/16 NIT-1: the *_test.go FILTER was claimed but never exercised ---
# The retraction asserts every skip in the table has a fixture; no fixture
# contained a `*_test.go` at all, so the FILTER in BOTH Go extractors was
# unexercised in either direction. Each fixture carries an unauthenticated
# mutating route in a TEST file beside a clean production file: the gate must
# PASS, and it must FAIL the moment the filter stops filtering.
D="$TMPROOT/gin-test-file-skipped"; mkdir -p "$D/cmd"
cat > "$D/cmd/main.go" <<'R7EOF'
package main

func main() {
	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	r.POST("/api/v1/download", api.DownloadHandler)
}
R7EOF
cat > "$D/cmd/main_test.go" <<'R7EOF'
package main

func TestWipe(t *testing.T) {
	r := gin.New()
	r.POST("/api/v1/test-only-wipe", api.WipeHandler)
}
R7EOF
mk_policy_go "$D" gin cmd '"AuthMW"' '  - service: svc
    method: GET
    path: /health
    class: public-by-design
    justification: "Liveness probe."'

D="$TMPROOT/gomux-test-file-skipped"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'R7EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}
R7EOF
cat > "$D/jackettapi/router_test.go" <<'R7EOF'
package jackettapi

import "net/http"

func TestNewMux(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/test-only-wipe", d.Debug.HandleWipe)
	_ = mux
}
R7EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' ''

# --- R7-17 false-positive guard: GIN_GROUP_DECL must stop at a `;` ---------
# `GIN_GROUP_DECL` is consulted only on a line whose SKELETON contains
# `.Group(`, and its `[^;]*?` bound is what keeps it from claiming an
# UNRELATED assignment that merely shares that line. Widening it to
# `(\w+)\s*:?=` survived every other fixture (measured), so this is its pin:
# `n := 0` is not a group declaration and must mint no refusal.
mk_gin_file gin-group-decl-stops-at-semicolon <<'R7EOF'
func main() {
	r := gin.Default()
	r.Use(middleware.AuthMW())
	r.GET("/health", api.HealthHandler)
	n := 0; v1 := r.Group("/api/v1")
	_ = n
	v1.POST("/download", api.DownloadHandler)
}
R7EOF

# --- R7-18 false-positive guard: an IMPORT CYCLE must not hang the resolver -
# `_router_key` walks the import graph transitively so a re-export cannot
# re-open the round-7 bypass; a cycle is a real thing to meet in a package and
# an unbounded walk would recurse until the interpreter stops it. The seen-set
# is what makes the walk terminate, and this fixture is what proves it: the
# gate must still reach a verdict.
D="$TMPROOT/fastapi-import-cycle"; mkdir -p "$D/app/api"
cat > "$D/app/api/a.py" <<'R7EOF'
from .b import router

def _unused():
    return router
R7EOF
cat > "$D/app/api/b.py" <<'R7EOF'
from .a import router

def _unused():
    return router
R7EOF
cat > "$D/app/api/routes.py" <<'R7EOF'
from fastapi import APIRouter, Depends, Request
router = APIRouter(tags=["t"])

def require_api_token(request: Request) -> None:
    return

@router.get("/health")
async def health():
    return {"ok": True}

@router.post("/download")
async def download(req: Request, _: None = Depends(require_api_token)):
    return {"ok": True}
R7EOF
cat > "$D/app/api/__init__.py" <<'R7EOF'
from fastapi import FastAPI
from .routes import router as api_router
app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
R7EOF
mk_policy_fastapi "$D" "$EXEMPT_HEALTH"

# --- R7-19 MINOR-4: the `_carriers` OVER-APPROXIMATION, pinned as-is --------
# THIS FIXTURE PINS A KNOWN FAIL-OPEN PATH. It is green because the shipped
# engine credits it, not because crediting it is right: `describe(mux)` returns
# a `*Stats`, nothing wrapping `mux` is ever returned, and `mux` still comes
# back wrapped. The propagation is lexical — any RHS that MENTIONS a carrier
# name adopts the LHS — and the round-6 audit recorded the construct as
# "fail-closed", which is true of the MISS direction and false of this one.
# The behaviour is unchanged this round by design (a Go return-value model is a
# second parser with its own failure modes); what changed is that it is now
# stated in `_carriers`, in the skip table, and in the guide. The pin is what
# makes a future narrowing a DELIBERATE fixture change rather than drift —
# the same treatment F6 gave the gin multi-statement rule.
mk_r4 gomux-carrier-over-approximates <<'R7EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	stats := describe(mux)
	_ = stats
	return WithAuth(stats)
}
R7EOF

# ============================ ROUND 9 =======================================
# --- R9-1 BLOCKING-1: an UNATTRIBUTABLE RECEIVER must refuse, not drop ------
# Round 8 measured the silent drop that this whole analyzer exists to prevent:
# `newServeMux().HandleFunc("/wipe", h)` beside a healthy `mux.HandleFunc(
# "/ok", h)` gave exit 0 / routes 1 / findings 0 / unmodelled 0, with the
# mutating route ABSENT from the inventory. gin refuses its twin
# (`newEngine().POST(...)`) because GIN_VERB is a receiver-agnostic catch-all;
# gomux had none, so `()`-chained, method-call and index receivers all matched
# nothing and the skeleton filter's `continue` stepped over them.
# The §11.4.201(6) BLIND net cannot substitute: it fires on a FILE that yields
# ZERO routes, and the healthy sibling keeps the file non-empty — a drop hides
# behind a healthy neighbour. Pin: MUX_CALL vs MUX_ANY+MUX_DOTTED_OWNER counts.
mk_r4 gomux-call-receiver-refused <<'R9EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	newServeMux().HandleFunc("/api/v1/jackett/wipe", d.Credentials.Handle)
	return WithAuth(mux)
}
R9EOF

# --- R9-2 BLOCKING-1, second spelling: a METHOD-CALL receiver --------------
# `s.buildMux().HandleFunc(...)` defeats MUX_DOTTED_OWNER for a different
# reason than R9-1 does: the `()` breaks the `.word.HandleFunc` adjacency the
# dotted rule needs. Same drop, different cause — pinned separately so a fix
# that only handles one spelling cannot pass.
mk_r4 gomux-methodcall-receiver-refused <<'R9EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	d.buildMux().HandleFunc("/api/v1/jackett/wipe", d.Credentials.Handle)
	return WithAuth(mux)
}
R9EOF

# --- R9-3 BLOCKING-1, third spelling: an INDEX-EXPRESSION receiver ---------
# The round-7 lesson applied to itself: `}` was not in the old character
# allowlist, and `]` is not a selector. Keying on "can this model NAME the
# receiver" covers both without enumerating either.
mk_r4 gomux-index-receiver-refused <<'R9EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	muxes[0].HandleFunc("/api/v1/jackett/wipe", d.Credentials.Handle)
	return WithAuth(mux)
}
R9EOF

# --- R9-4 BLOCKING-1: a line holding BOTH a nameable and an unnameable site -
# Why the check counts call sites instead of asking "is ANY site nameable".
# A boolean turns green here while still dropping `/wipe`; the count refuses.
mk_r4 gomux-mixed-line-refused <<'R9EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth); newServeMux().HandleFunc("/api/v1/jackett/wipe", d.Credentials.Handle)
	return WithAuth(mux)
}
R9EOF

# --- R9-5 BLOCKING-1 FALSE-POSITIVE GUARD (§11.4.201(1)) -------------------
# The catch-all must not refuse a healthy file. Load-bearing detail: the
# handler ARGUMENT `d.Health.HandleHealth` is a dotted name too, and it must
# NOT count as a call site — the verb has to be followed by `(`, and an
# argument is followed by `,` or `)`. This is the exact shape of real-tree
# router.go:60, so a fix that over-refuses here breaks the live gate.
# The closure body calls `HandleListCredentials`, not `Handle`: a bare
# `d.Credentials.Handle(w, r)` is a dotted `.Handle(` CALL SITE, which the
# SHIPPED round-6 MUX_DOTTED_OWNER rule already refuses (measured) — a
# pre-existing over-refusal, unrelated to the round-9 catch-all, and one the
# real tree does not hit because its handlers are named `Handle<Thing>`.
mk_r4 gomux-dotted-handler-arg-ok "$EXEMPT_HEALTHZ" <<'R9EOF'
func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	mux.HandleFunc("/api/v1/jackett/credentials", func(w http.ResponseWriter, r *http.Request) {
		d.Credentials.HandleListCredentials(w, r)
	})
	return WithAuth(mux)
}
R9EOF

# --- R9-6 IMPORTANT-1: a mux built inside a METHOD must not be FALSE-REFUSED
# `FUNC_LIT = \bfunc\s*\(` matched a METHOD'S RECEIVER CLAUSE, so
# `_closure_spans` swallowed the whole method body and
# `_function_level_returns` dropped the method's own `return WithAuth(mux)`.
# Measured round 8 with byte-identical bodies: free func exit 0, method exit 1
# ("returned WITHOUT an auth marker"). Method-scoped mux construction is
# idiomatic Go; a gate that cries wolf on an idiom gets bypassed, and
# bypassing is how R9-1's silent-drop class comes back.
mk_r4 gomux-method-receiver-wrapped-ok "$EXEMPT_HEALTHZ" <<'R9EOF'
func (s *Server) NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}
R9EOF

# --- R9-7 IMPORTANT-1 CONTROL: methods did NOT become exempt ---------------
# The fix must credit a method's OWN return, not every method. Identical to
# R9-6 except the mux comes back BARE — this must still FAIL, or R9-6 would be
# pinning "methods always pass" rather than "a method's return is its own".
mk_r4 gomux-method-receiver-unwrapped-fails <<'R9EOF'
func (s *Server) NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return mux
}
R9EOF

# --- R9-8 IMPORTANT-1 CONTROL: a REAL closure inside a method still cannot --
# ---           prove the method's return (the round-4 rule, preserved) ------
# The method-vs-literal discriminator keys on what FOLLOWS the first balanced
# paren group, so genuine `func(){...}` literals nested in a method are still
# closures and their returns are still excluded. Without this pin the
# IMPORTANT-1 fix could have been "stop excluding closure returns", which
# would re-open the round-4 false-SAFE.
mk_r4 gomux-method-closure-return-still-excluded <<'R9EOF'
func (s *Server) NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	_ = func() http.Handler { return WithAuth(mux) }
	return mux
}
R9EOF

# --- R9-9 MINOR-1: an import cycle `_router_key` ACTUALLY WALKS -------------
# `fastapi-import-cycle` (R7-18) builds a cycle in the IMPORT GRAPH but never
# puts a VERB ATTRIBUTE on a cyclically-imported name, so `_router_key` is
# never called on it and the seen-set is never exercised. Round 8 measured it:
# deleting the seen-set guard left that fixture green (exit 0 both ways).
# Here `api.post(...)` is a verb attribute on a Name whose import chain cycles
# a -> b -> a, so the resolver really recurses. Pristine terminates and exits
# 0; with the guard removed the mutant raises RecursionError — a §11.4.1
# FAIL-bluff shape (a crash, not a verdict), which this expected-0 case sees.
D="$TMPROOT/fastapi-import-cycle-traversed"; mkdir -p "$D/app/api"
cat > "$D/app/api/a.py" <<'R9EOF'
from .b import api

api.post("/wipe")(wipe)
R9EOF
cat > "$D/app/api/b.py" <<'R9EOF'
from .a import api
R9EOF
cat > "$D/app/api/routes.py" <<'R9EOF'
from fastapi import APIRouter, Depends, Request
router = APIRouter(tags=["t"])

def require_api_token(request: Request) -> None:
    return

@router.get("/health")
async def health():
    return {"ok": True}

@router.post("/download")
async def download(req: Request, _: None = Depends(require_api_token)):
    return {"ok": True}
R9EOF
cat > "$D/app/api/__init__.py" <<'R9EOF'
from fastapi import FastAPI
from .routes import router as api_router
app = FastAPI()
app.include_router(api_router, prefix="/api/v1")
R9EOF
mk_policy_fastapi "$D" "$EXEMPT_HEALTH"

# --- R9-10 the `len(sites) == 1` CREDIT FILTER, finally pinned --------------
# Round 8 recorded mutation M-A (drop `len(sites) == 1`) as SURVIVING, and
# read that as "redundant with unresolvable_groups, belt-and-braces". MEASURED
# 2026-08-26, that reading is WRONG and the filter is load-bearing:
#   GIN_GROUP      = r'(\w+)\s*:?=\s*(\w+)\.Group\(\s*"([^"]*)"'      <- NO lookbehind
#   GIN_GROUP_DECL = r'(?<![\w.])(\w+)\s*:?=\s*[^;]*?\.Group\s*\('    <- HAS one
# so a DOTTED assignment target (`s.g = r.Group("/safe")`) lands in
# `group_sites` but NEVER in `decl_sites`. The "'g' is bound 2 times" refusal
# is keyed on `decl_sites`, so it never fires, `g` never reaches
# `unresolvable_groups`, and only `len(sites) == 1` keeps the name out of
# `groups`. GIN_GROUP is therefore NOT a subset of GIN_GROUP_DECL — the two do
# not move in lockstep, which is the premise the redundancy reading rested on.
# Measured consequence with M-A applied: the route resolves as `/safe/wipe`
# (FIRST-wins across a re-binding) instead of `/wipe`, an operator exemption
# written for the auth'd `/safe` group then MATCHES it, and the whole gate goes
# green — exit 0, zero findings, over an unauthenticated mutating LAN route,
# while the pristine engine reports BOTH the route AND the exemption as stale.
# A survived mutation on a filter that can flip FAIL to PASS is unvalidated
# instrumentation (§11.4.115(F)); this is the pin that ends that.
D="$TMPROOT/gin-group-dotted-target-first-wins"; mkdir -p "$D/cmd"
cat > "$D/cmd/main.go" <<'R9EOF'
package main

func setup(r *gin.Engine, s *Srv, t *Srv) {
	s.g = r.Group("/safe")
	s.g.Use(middleware.AuthMW())
	t.g = r.Group("/danger")
	g.POST("/wipe", WipeHandler)
}
R9EOF
mk_policy_go "$D" gin cmd '"AuthMW"' '  - service: svc
    method: POST
    path: "/safe/wipe"
    class: public-by-design
    justification: "Under the /safe group, which carries AuthMW."
    evidence: "cmd/main.go:7"'

# ======================= ROUND 11 FIXTURES ================================
# THE SPLIT-SELECTOR PRIMITIVE (BLOCKING-1 + IMPORTANT-1). A Go selector may be
# separated from its member by whitespace, INCLUDING A NEWLINE. Round 6 met
# this in gin and fixed gin only; the gomux twin was still a silent DROP five
# rounds later. Every shape below was run against the shipped analyzer BEFORE
# its fix and against the real Go parser (`gofmt -e`) to prove it is legal Go.

# BLOCKING-1, the reviewer's exact sequence: a split selector beside a HEALTHY
# WRAPPED SIBLING, so the §11.4.201(6) zero-routes net cannot see the drop.
# Pre-fix measured: exit 0, 1 route, 0 findings, 0 unmodelled, `/wipe` ABSENT.
# gofmt-STABLE: gofmt returns this file byte-identical.
D="$TMPROOT/gomux-split-selector"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'R11EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	open := http.NewServeMux()
	open.
		HandleFunc("/wipe", d.Wipe.Handle)
	return WithAuth(mux)
}
R11EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

# The same drop with a TAB on the continuation line — gofmt normalises the
# INDENT but keeps the SPLIT, so this spelling survives a formatter too.
D="$TMPROOT/gomux-split-tab"; mkdir -p "$D/jackettapi"
printf 'package jackettapi\n\nimport "net/http"\n\nfunc NewMux(d *Deps) http.Handler {\n\tmux := http.NewServeMux()\n\tmux.HandleFunc("/healthz", d.Health.HandleHealth)\n\topen := http.NewServeMux()\n\topen.\n\tHandleFunc("/wipe", d.Wipe.Handle)\n\treturn WithAuth(mux)\n}\n' > "$D/jackettapi/router.go"
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

# THE NEGATIVE CONTROL (§11.4.201(1)). A fix that starts refusing legitimate
# code is a FAIL-bluff of equal severity to the drop it closed. Ordinary
# registrations, a dotted handler ARGUMENT (`d.Health.HandleHealth`) and a
# `.Handle(` registration must ALL stay resolvable: this fixture MUST PASS.
D="$TMPROOT/gomux-split-negctl"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'R11EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	mux.Handle("/api/v1/jackett/indexers", d.Indexers)
	return WithAuth(mux)
}
R11EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

# IMPORTANT-1: the SAME-LINE half of the same primitive, both extractors.
D="$TMPROOT/gomux-ws-selector"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'R11EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	open := http.NewServeMux()
	open.  HandleFunc("/wipe", d.Wipe.Handle)
	return WithAuth(mux)
}
R11EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

# Whitespace on the OTHER side of the dot — equally legal, equally dropped.
D="$TMPROOT/gomux-ws-before-dot"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'R11EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	open := http.NewServeMux()
	open .HandleFunc("/wipe", d.Wipe.Handle)
	return WithAuth(mux)
}
R11EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

# The gin twin, as the reviewer measured it: `r.Use(AuthMW())` ABOVE the split
# and a healthy sibling route, so pre-fix the gate was a clean exit 0 / zero
# findings over an unauthenticated mutating LAN route.
D="$TMPROOT/gin-ws-selector"; mkdir -p "$D/cmd"
cat > "$D/cmd/main.go" <<'R11EOF'
package main

func main() {
	r := gin.Default()
	r.Use(AuthMW())
	r.GET("/ok", api.OK)
	r.  POST("/wipe", api.WipeHandler)
	r.Run(":7187")
}
R11EOF
mk_policy_go "$D" gin cmd '"AuthMW"' '  []'

# Its negative control: identical file, ordinary spelling — MUST PASS.
D="$TMPROOT/gin-ws-negctl"; mkdir -p "$D/cmd"
cat > "$D/cmd/main.go" <<'R11EOF'
package main

func main() {
	r := gin.Default()
	r.Use(AuthMW())
	r.GET("/ok", api.OK)
	r.POST("/wipe", api.WipeHandler)
	r.Run(":7187")
}
R11EOF
mk_policy_go "$D" gin cmd '"AuthMW"' '  []'

# THE DOOR ROUND 10 DID NOT OPEN. The same primitive on `.Group(` is not a
# loud fail-closed drop like `.Use(` — it corrupts the route PATH. A split
# `.Group("/admin")` makes `POST /admin/wipe` resolve as `POST /wipe`, where an
# exemption written for a genuinely-public `POST /wipe` MATCHES it. Measured
# pre-fix: exit 0, zero findings, over an unauthenticated `/admin/wipe`.
D="$TMPROOT/gin-group-split-exempt"; mkdir -p "$D/cmd"
cat > "$D/cmd/main.go" <<'R11EOF'
package main

func main() {
	r := gin.Default()
	r.Use(AuthMW())
	g := r.
		Group("/admin")
	g.POST("/wipe", api.WipeHandler)
	r.POST("/wipe", api.PublicWipe)
}
R11EOF
mk_policy_go "$D" gin cmd '"AuthMW"' '  - service: svc
    method: POST
    path: /wipe
    class: public-by-design
    justification: "Public wipe endpoint, deliberately open."'

D="$TMPROOT/gin-group-ws-exempt"; mkdir -p "$D/cmd"
cat > "$D/cmd/main.go" <<'R11EOF'
package main

func main() {
	r := gin.Default()
	r.Use(AuthMW())
	g := r.  Group("/admin")
	g.POST("/wipe", api.WipeHandler)
	r.POST("/wipe", api.PublicWipe)
}
R11EOF
mk_policy_go "$D" gin cmd '"AuthMW"' '  - service: svc
    method: POST
    path: /wipe
    class: public-by-design
    justification: "Public wipe endpoint, deliberately open."'

# Its negative control — the SAME file with an ordinary `.Group(`. The prefixed
# route resolves to `/admin/wipe`, inherits AuthMW, and the exemption applies
# only to the genuinely-public `/wipe`: MUST PASS. Without this, a fix that
# simply refused every `.Group(` line would pass the two fixtures above.
D="$TMPROOT/gin-group-negctl"; mkdir -p "$D/cmd"
cat > "$D/cmd/main.go" <<'R11EOF'
package main

func main() {
	r := gin.Default()
	r.Use(AuthMW())
	g := r.Group("/admin")
	g.POST("/wipe", api.WipeHandler)
	r.POST("/wipe", api.PublicWipe)
}
R11EOF
mk_policy_go "$D" gin cmd '"AuthMW"' '  - service: svc
    method: POST
    path: /wipe
    class: public-by-design
    justification: "Public wipe endpoint, deliberately open."'

# THE HOLE THE FIRST CUT OF THE ROUND-11 FIX LEFT, found by probing my own
# patch rather than the report. Go permits ARBITRARY whitespace after a
# selector dot and `bare` blanks comments to spaces, so a split with a COMMENT
# or a BLANK LINE in the gap is legal Go (`gofmt -e`) that an
# immediate-next-line check still dropped: measured exit 0, 1 route, `/wipe`
# absent — the BLOCKING shape one gap wider. `_selector_is_split` now scans
# forward to the first line carrying code.
D="$TMPROOT/gomux-split-comment-gap"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'R11EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	open := http.NewServeMux()
	open.
		// the wipe endpoint
		HandleFunc("/wipe", d.Wipe.Handle)
	return WithAuth(mux)
}
R11EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

D="$TMPROOT/gomux-split-blank-gap"; mkdir -p "$D/jackettapi"
printf 'package jackettapi\n\nimport "net/http"\n\nfunc NewMux(d *Deps) http.Handler {\n\tmux := http.NewServeMux()\n\tmux.HandleFunc("/healthz", d.Health.HandleHealth)\n\topen := http.NewServeMux()\n\topen.\n\n\t\tHandleFunc("/wipe", d.Wipe.Handle)\n\treturn WithAuth(mux)\n}\n' > "$D/jackettapi/router.go"
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

D="$TMPROOT/gin-split-comment-gap"; mkdir -p "$D/cmd"
cat > "$D/cmd/main.go" <<'R11EOF'
package main

func main() {
	r := gin.Default()
	r.Use(AuthMW())
	r.GET("/ok", api.OK)
	r.
		// danger
		POST("/wipe", api.WipeHandler)
}
R11EOF
mk_policy_go "$D" gin cmd '"AuthMW"' '  []'

# ---- IMPORTANT-2: a func TYPE owns no body brace ----------------------------
# `FUNC_LIT` matches `func(`, which introduces a TYPE as often as a LITERAL.
# Round 9 point-fixed ONE shape (the method receiver); round 10 reported two
# more; the 2026-08-27 audit found ELEVEN. Each fixture below carries a real
# `return WithAuth(mux)` that the pre-fix engine could not see, so each exited
# 1 with "mux 'mux' is returned WITHOUT an auth marker" on idiomatic Go — the
# §11.4.201(1) cries-wolf class. All MUST PASS.
mk_gomux_sig() {  # mk_gomux_sig <dir> <signature-line>
  local d="$1" sig="$2"
  mkdir -p "$d/jackettapi"
  cat > "$d/jackettapi/router.go" <<GOEOF
package jackettapi

import "net/http"

${sig}
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	return WithAuth(mux)
}
GOEOF
  mk_policy_go "$d" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"
}
mk_gomux_sig "$TMPROOT/gomux-method-funcparam" \
  'func (s *Server) routes(mw func(http.Handler) http.Handler) http.Handler {'
mk_gomux_sig "$TMPROOT/gomux-method-funcresult" \
  'func (s *Server) routes() func(int) int {'
# Round 10 asserted "plain / receiverless / generic / multiline-receiver
# methods correctly skip". A RECEIVERLESS function with a func-typed parameter
# does NOT — the defect never needed a receiver at all.
mk_gomux_sig "$TMPROOT/gomux-free-funcparam" \
  'func routes(mw func(http.Handler) http.Handler) http.Handler {'
mk_gomux_sig "$TMPROOT/gomux-variadic-functype" \
  'func routes(opts ...func(*Server)) http.Handler {'
mk_gomux_sig "$TMPROOT/gomux-named-func-result" \
  'func routes() (h func(int) int, e error) {'

# The four BODY shapes round 10 tested none of: a func TYPE declared inside the
# body hijacks the brace of a FOLLOWING `if`/`for` block and hides a real
# `return WithAuth(mux)` sitting inside it.
D="$TMPROOT/gomux-body-functype"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'R11EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	var mw func(http.Handler) http.Handler
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	if mw == nil {
		return WithAuth(mux)
	}
	return nil
}
R11EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

D="$TMPROOT/gomux-body-typedecl-functype"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'R11EOF'
package jackettapi

import "net/http"

func NewMux(d *Deps) http.Handler {
	type MW func(http.Handler) http.Handler
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	if d.On {
		return WithAuth(mux)
	}
	return nil
}
R11EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

# THE NEGATIVE CONTROL for IMPORTANT-2 (§11.4.201(1) in the OTHER direction):
# a return inside a GENUINE closure literal must STILL be excluded, or the fix
# has traded a cries-wolf defect for a false attribution of SAFETY. MUST FAIL.
D="$TMPROOT/gomux-r11-closure-still-excluded"; mkdir -p "$D/jackettapi"
cat > "$D/jackettapi/router.go" <<'R11EOF'
package jackettapi

import "net/http"

func (s *Server) routes(mw func(http.Handler) http.Handler) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", d.Health.HandleHealth)
	mux.HandleFunc("/api/v1/jackett/credentials", d.Credentials.Handle)
	build := func() http.Handler {
		return WithAuth(mux)
	}
	_ = build
	return mux
}
R11EOF
mk_policy_go "$D" gomux jackettapi '"WithAuth"' "$EXEMPT_HEALTHZ"

# ------------------------------------------------------------------ run ----
echo "=== $HARNESS_NAME: fixture matrix ==="
run_case golden-good-fastapi    0 "$TMPROOT/golden-good-fastapi"
run_case MUTATION-fastapi       1 "$TMPROOT/mutation-fastapi"
run_case golden-bad-fastapi-new 1 "$TMPROOT/golden-bad-fastapi-new"
run_case golden-bad-unjustified 1 "$TMPROOT/golden-bad-unjustified"
run_case golden-bad-stale       1 "$TMPROOT/golden-bad-stale"
run_case golden-bad-blind       1 "$TMPROOT/golden-bad-blind"
run_case golden-false-loopback  0 "$TMPROOT/golden-false-loopback"
run_case golden-good-gomux      0 "$TMPROOT/golden-good-gomux"
run_case MUTATION-gomux         1 "$TMPROOT/mutation-gomux"
run_case golden-bad-gin         1 "$TMPROOT/golden-bad-gin"
run_case gomux-second-bare-mux  1 "$TMPROOT/gomux-second-bare-mux"
run_case gomux-two-wrapped      0 "$TMPROOT/gomux-two-wrapped"
run_case unmodeled-add-api-route 1 "$TMPROOT/unmodeled-add-api-route"
run_case unmodeled-nonliteral   1 "$TMPROOT/unmodeled-nonliteral-path"
run_case unmodeled-gin-any      1 "$TMPROOT/unmodeled-gin-any"
run_case unmodeled-gin-multiline 1 "$TMPROOT/unmodeled-gin-multiline"
run_case aliased-depends        0 "$TMPROOT/aliased-depends"
run_case dup-exemption          1 "$TMPROOT/dup-exemption"
run_case malformed-policy       2 "$TMPROOT/malformed-policy"
run_case gomux-comment-carrier  1 "$TMPROOT/gomux-comment-carrier"
run_case gomux-closure-return   1 "$TMPROOT/gomux-closure-return"
run_case gomux-real-closure-ok  0 "$TMPROOT/gomux-real-closure-ok"
run_case gin-second-engine      1 "$TMPROOT/gin-second-engine"
run_case gin-use-after-route    1 "$TMPROOT/gin-use-after-route"
run_case gin-group-inherit      0 "$TMPROOT/gin-group-inherit"
run_case alias-conditional      1 "$TMPROOT/alias-conditional"
run_case alias-reassigned       1 "$TMPROOT/alias-reassigned"

# --- review round 4: Go lexical-mode state must carry across lines ---------
run_case gomux-rawstring-carrier            1 "$TMPROOT/gomux-rawstring-carrier"
run_case gomux-rawstring-innocuous          1 "$TMPROOT/gomux-rawstring-innocuous"
run_case gomux-rawstring-real-wrap-ok       0 "$TMPROOT/gomux-rawstring-real-wrap-ok"
run_case gomux-blockopen-in-linecomment     0 "$TMPROOT/gomux-blockopen-in-linecomment"
run_case gomux-unterm-block-hides-wrap      1 "$TMPROOT/gomux-unterminated-block-hides-wrap"
run_case gomux-unterm-block-clean           1 "$TMPROOT/gomux-unterminated-block-otherwise-clean"
run_case gomux-unterm-rawstring             1 "$TMPROOT/gomux-unterminated-rawstring"
run_case gomux-blockmarker-in-rawstring     1 "$TMPROOT/gomux-blockmarker-in-rawstring"
run_case gomux-linecomment-in-rawstring     0 "$TMPROOT/gomux-linecomment-marker-in-rawstring"
run_case gomux-backtick-in-blockcomment     0 "$TMPROOT/gomux-backtick-in-blockcomment"
run_case gomux-escaped-quote-carrier        1 "$TMPROOT/gomux-escaped-quote-carrier"
run_case gomux-rawstring-trailing-backslash 0 "$TMPROOT/gomux-rawstring-trailing-backslash"
run_case gomux-backtick-in-rune             0 "$TMPROOT/gomux-backtick-in-rune"
run_case gomux-unterm-interpreted-string    1 "$TMPROOT/gomux-unterminated-interpreted-string"
run_case gomux-rawstring-route-path         1 "$TMPROOT/gomux-rawstring-route-path"
run_case gin-use-carrier-in-string          1 "$TMPROOT/gin-use-carrier-in-string"
run_case gin-use-carrier-in-rawstring       1 "$TMPROOT/gin-use-carrier-in-rawstring"
run_case gin-use-carrier-control            1 "$TMPROOT/gin-use-carrier-control"
run_case gin-real-use-ok                    0 "$TMPROOT/gin-real-use-ok"
run_case gin-any-mentioned-in-string        0 "$TMPROOT/gin-any-mentioned-in-string"
run_case gomux-route-carrier-in-rawstring   0 "$TMPROOT/gomux-route-carrier-in-rawstring"

# --- review round 5: no route may vanish into a PASS ----------------------
run_case gin-compound-group-route           1 "$TMPROOT/gin-compound-group-route"
run_case gin-compound-use-after-route       1 "$TMPROOT/gin-compound-use-after-route"
run_case gin-semicolon-not-compound         0 "$TMPROOT/gin-semicolon-not-compound"
run_case gomux-param-mux                    1 "$TMPROOT/gomux-param-mux"
run_case gomux-any-mentioned-in-string      0 "$TMPROOT/gomux-any-mentioned-in-string"
run_case fastapi-dotted-owner               1 "$TMPROOT/fastapi-dotted-owner"
run_case fastapi-api-route-deco             1 "$TMPROOT/fastapi-api-route-deco"
run_case fastapi-trace-unauth               1 "$TMPROOT/fastapi-trace-unauth"
run_case fastapi-trace-authed               0 "$TMPROOT/fastapi-trace-authed"
run_case policy-no-services                 1 "$TMPROOT/policy-no-services"
run_case gin-dotted-owner-false-safe        1 "$TMPROOT/gin-dotted-owner-false-safe"
run_case gin-dotted-handler-ok              0 "$TMPROOT/gin-dotted-handler-ok"

# --- review round 6: the credit-bearing primitive + the fastapi drop class --
run_case gin-dotted-use-false-safe       1 "$TMPROOT/gin-dotted-use-false-safe"
run_case gin-bare-use-still-credits      0 "$TMPROOT/gin-bare-use-still-credits"
run_case gomux-dotted-recv-false-safe    1 "$TMPROOT/gomux-dotted-receiver-false-safe"
run_case gomux-bare-recv-still-credits   0 "$TMPROOT/gomux-bare-receiver-still-credits"
run_case gin-two-engines-same-name       1 "$TMPROOT/gin-two-engines-same-name"
run_case gin-one-engine-two-funcs        0 "$TMPROOT/gin-one-engine-two-funcs"
run_case fastapi-router-reassign         1 "$TMPROOT/fastapi-router-reassign"
run_case fastapi-router-level-deps-ok    0 "$TMPROOT/fastapi-router-level-deps-ok"
run_case fastapi-immediate-call          1 "$TMPROOT/fastapi-immediate-call"
run_case fastapi-route-deco              1 "$TMPROOT/fastapi-route-deco"
run_case fastapi-classdef-deco           1 "$TMPROOT/fastapi-classdef-deco"
run_case fastapi-bound-alias             1 "$TMPROOT/fastapi-bound-alias"
run_case fastapi-verbnames-not-routers   0 "$TMPROOT/fastapi-verbnames-not-routers"
run_case fastapi-websocket-refused       1 "$TMPROOT/fastapi-websocket-refused"
run_case gin-selector-continuation       1 "$TMPROOT/gin-selector-continuation"
run_case gin-continuation-not-a-route     0 "$TMPROOT/gin-continuation-not-a-route"
run_case gin-semicolon-in-closure-body   1 "$TMPROOT/gin-semicolon-in-closure-body"
run_case fastapi-websocket-route-refused 1 "$TMPROOT/fastapi-websocket-route-refused"
for _v in Any Match Handle Static StaticFile StaticFS StaticFileFS NoRoute NoMethod; do
  run_case "gin-unmodelled-$_v" 1 "$TMPROOT/gin-unmodelled-$_v"
done
run_case gomux-defaultservemux           1 "$TMPROOT/gomux-defaultservemux"
run_case policy-unknown-kind             1 "$TMPROOT/policy-unknown-kind"
run_case exemption-missing-path          1 "$TMPROOT/exemption-missing-path"

# --- review round 7: the credit primitive's remaining doors + the pins -----
run_case gin-group-dotted-parent-false-safe  1 "$TMPROOT/gin-group-dotted-parent-false-safe"
run_case gin-group-rebound-false-safe        1 "$TMPROOT/gin-group-rebound-false-safe"
run_case gin-two-groups-distinct-ok          0 "$TMPROOT/gin-two-groups-distinct-names-ok"
run_case gomux-dotted-decl-false-safe        1 "$TMPROOT/gomux-dotted-decl-false-safe"
run_case gomux-dotted-return-false-safe      1 "$TMPROOT/gomux-dotted-return-false-safe"
run_case gomux-bare-decl-still-credits       0 "$TMPROOT/gomux-bare-decl-still-credits"
run_case gomux-return-prefix-not-credit      1 "$TMPROOT/gomux-return-prefix-not-a-credit"
run_case gomux-complit-receiver-refused      1 "$TMPROOT/gomux-complit-receiver-refused"
run_case gin-complit-receiver-labelled       1 "$TMPROOT/gin-complit-receiver-labelled"
run_case fastapi-imported-router-call        1 "$TMPROOT/fastapi-imported-router-immediate-call"
run_case fastapi-imported-nonrouter-quiet    0 "$TMPROOT/fastapi-imported-nonrouter-quiet"
run_case fastapi-unmodelled-mount            1 "$TMPROOT/fastapi-unmodelled-mount"
run_case fastapi-unmodelled-add-route        1 "$TMPROOT/fastapi-unmodelled-add-route"
run_case exemption-bad-class                 1 "$TMPROOT/exemption-bad-class"
run_case gin-test-file-skipped               0 "$TMPROOT/gin-test-file-skipped"
run_case gomux-test-file-skipped             0 "$TMPROOT/gomux-test-file-skipped"
run_case gin-group-decl-semicolon            0 "$TMPROOT/gin-group-decl-stops-at-semicolon"
run_case fastapi-import-cycle               0 "$TMPROOT/fastapi-import-cycle"
run_case gomux-carrier-over-approx          0 "$TMPROOT/gomux-carrier-over-approximates"

echo
echo "=== round 9: gomux receiver shapes this model cannot NAME must refuse ==="
run_case gomux-call-receiver-refused        1 "$TMPROOT/gomux-call-receiver-refused"
run_case gomux-methodcall-recv-refused      1 "$TMPROOT/gomux-methodcall-receiver-refused"
run_case gomux-index-receiver-refused       1 "$TMPROOT/gomux-index-receiver-refused"
run_case gomux-mixed-line-refused           1 "$TMPROOT/gomux-mixed-line-refused"
run_case gomux-dotted-handler-arg-ok        0 "$TMPROOT/gomux-dotted-handler-arg-ok"
run_case gomux-method-wrapped-ok            0 "$TMPROOT/gomux-method-receiver-wrapped-ok"
run_case gomux-method-unwrapped-fails       1 "$TMPROOT/gomux-method-receiver-unwrapped-fails"
run_case gomux-method-closure-excluded      1 "$TMPROOT/gomux-method-closure-return-still-excluded"
run_case fastapi-cycle-traversed            0 "$TMPROOT/fastapi-import-cycle-traversed"
run_case gin-group-dotted-first-wins        1 "$TMPROOT/gin-group-dotted-target-first-wins"

echo
echo "=== round 9: an unnameable receiver must be refused UNDER ITS OWN NAME ==="
# The exit code cannot see a wrong label. Pre-fix this line produced NO
# finding at all; a fix that refused it as "path is not a string literal"
# would send the reader to fix the wrong thing (the F8 class, third instance).
r9_out="$(nice -n 19 "$GATE" --policy "$TMPROOT/gomux-call-receiver-refused/policy.yaml" \
                             --root "$TMPROOT/gomux-call-receiver-refused" 2>&1 || true)"
if printf '%s' "$r9_out" | grep -q 'cannot name the mux it registers on' \
   && printf '%s' "$r9_out" | grep -q 'newServeMux()' \
   && ! printf '%s' "$r9_out" | grep -q 'path is not a string literal'; then
  PASS_N=$((PASS_N + 1)); printf 'ok   %-24s refused as an unnameable receiver, and the line is shown\n' r9-unnameable-label
else
  FAIL_N=$((FAIL_N + 1))
  printf 'NOT-OK %-22s wrong or missing refusal label for an unnameable receiver\n' r9-unnameable-label >&2
  printf '%s\n' "$r9_out" | sed 's/^/       | /' >&2
fi

echo
echo "=== round 7: an UNRESOLVABLE group declaration must be named, not implied ==="
# The credit-DROP for a re-bound group name is pinned by
# `gin-group-rebound-false-safe` (remove the ambiguity rule and it turns
# green). The REFUSAL that explains WHY is a second, separate invariant, and
# an exit code cannot see it: with the refusal gone the fixture still exits 1,
# just without ever telling the reader that a group name was silently
# re-bound. Pinned here rather than left to a comment (§11.4.115(F)).
gd_out="$(nice -n 19 "$GATE" --policy "$TMPROOT/gin-group-dotted-parent-false-safe/policy.yaml" \
                             --root "$TMPROOT/gin-group-dotted-parent-false-safe" 2>&1 || true)"
if printf '%s' "$gd_out" | grep -q "group 'g' is declared from a parent reached"; then
  PASS_N=$((PASS_N + 1)); printf 'ok   %-24s the unresolvable group declaration is named\n' group-rebind-label
else
  FAIL_N=$((FAIL_N + 1))
  printf 'NOT-OK %-22s unresolvable group declaration not reported\n' group-rebind-label >&2
  printf '%s\n' "$gd_out" | sed 's/^/       | /' >&2
fi

echo
echo "=== round 7: a RE-BOUND group name must be named, with its lines ==="
# Companion pin to the one above, for the other half of the same rule. The
# credit DROP is pinned by the fixture (the faithful pre-fix revert — ambiguity
# rule out, last-wins back — turns it green); this pins the REFUSAL that tells
# the reader which name was re-bound and where, which no exit code can see.
gr_out="$(nice -n 19 "$GATE" --policy "$TMPROOT/gin-group-rebound-false-safe/policy.yaml" \
                             --root "$TMPROOT/gin-group-rebound-false-safe" 2>&1 || true)"
if printf '%s' "$gr_out" | grep -q "'g' is bound 2 times in this file"; then
  PASS_N=$((PASS_N + 1)); printf 'ok   %-24s the re-bound group name and its lines are reported\n' group-ambiguity-label
else
  FAIL_N=$((FAIL_N + 1))
  printf 'NOT-OK %-22s re-bound group name not reported\n' group-ambiguity-label >&2
  printf '%s\n' "$gr_out" | sed 's/^/       | /' >&2
fi

echo
echo "=== round 7: a composite-literal receiver must be refused UNDER ITS OWN NAME ==="
# NIT-2 / the F8 class, second instance. The exit code cannot see a wrong
# label: pre-fix this line was refused as "path is not a string literal",
# which is untrue of it and sends the reader to fix the wrong thing.
cl_out="$(nice -n 19 "$GATE" --policy "$TMPROOT/gin-complit-receiver-labelled/policy.yaml" \
                             --root "$TMPROOT/gin-complit-receiver-labelled" 2>&1 || true)"
if printf '%s' "$cl_out" | grep -q 'reached through a field or selector' \
   && ! printf '%s' "$cl_out" | grep -q 'path is not a string literal'; then
  PASS_N=$((PASS_N + 1)); printf 'ok   %-24s refused as a selector receiver, not as a bad path\n' complit-label
else
  FAIL_N=$((FAIL_N + 1))
  printf 'NOT-OK %-22s wrong refusal label for a composite-literal receiver\n' complit-label >&2
  printf '%s\n' "$cl_out" | sed 's/^/       | /' >&2
fi

echo
echo "=== round 4: a raw-string path refusal must still name the delimiters ==="
rp_out="$(nice -n 19 "$GATE" --policy "$TMPROOT/gomux-rawstring-route-path/policy.yaml" \
                            --root "$TMPROOT/gomux-rawstring-route-path" 2>&1 || true)"
if printf '%s' "$rp_out" | grep -q 'mux.HandleFunc(`.*`'; then
  PASS_N=$((PASS_N + 1)); printf 'ok   %-24s backticks preserved in the refusal\n' rawpath-diagnostic
else
  FAIL_N=$((FAIL_N + 1))
  printf 'NOT-OK %-22s refusal does not show the raw-string delimiters\n' rawpath-diagnostic >&2
  printf '%s\n' "$rp_out" | sed 's/^/       | /' >&2
fi

echo
echo "=== MINOR-4: runtime-arming boundary stated in the gate's OWN source ==="
for f in "$REPO_ROOT/scripts/pre_build/check_cm_lan_routes_authenticated.sh" \
         "$REPO_ROOT/scripts/pre_build/lan_route_auth_analyzer.py"; do
  if nice -n 19 grep -q 'BOB-197' "$f" && nice -n 19 grep -qi 'runtime' "$f"; then
    PASS_N=$((PASS_N + 1)); printf 'ok   %-24s %s\n' boundary-in-source "$(basename "$f")"
  else
    FAIL_N=$((FAIL_N + 1))
    printf 'NOT-OK %-22s %s (no runtime-arming boundary / no BOB-197 ref)\n' \
      boundary-in-source "$(basename "$f")" >&2
  fi
done

echo
echo "=== round 11: the SPLIT-SELECTOR primitive, both Go extractors ==="
run_case gomux-split-selector    1 "$TMPROOT/gomux-split-selector"
run_case gomux-split-tab         1 "$TMPROOT/gomux-split-tab"
run_case gomux-split-negctl      0 "$TMPROOT/gomux-split-negctl"
run_case gomux-ws-selector       1 "$TMPROOT/gomux-ws-selector"
run_case gomux-ws-before-dot     1 "$TMPROOT/gomux-ws-before-dot"
run_case gin-ws-selector         1 "$TMPROOT/gin-ws-selector"
run_case gin-ws-negctl           0 "$TMPROOT/gin-ws-negctl"
run_case gin-group-split-exempt  1 "$TMPROOT/gin-group-split-exempt"
run_case gin-group-ws-exempt     1 "$TMPROOT/gin-group-ws-exempt"
run_case gin-group-negctl        0 "$TMPROOT/gin-group-negctl"
run_case gomux-split-comment-gap 1 "$TMPROOT/gomux-split-comment-gap"
run_case gomux-split-blank-gap   1 "$TMPROOT/gomux-split-blank-gap"
run_case gin-split-comment-gap   1 "$TMPROOT/gin-split-comment-gap"

echo
echo "=== round 11: a func TYPE owns no body brace (IMPORTANT-2) ==="
run_case gomux-method-funcparam  0 "$TMPROOT/gomux-method-funcparam"
run_case gomux-method-funcresult 0 "$TMPROOT/gomux-method-funcresult"
run_case gomux-free-funcparam    0 "$TMPROOT/gomux-free-funcparam"
run_case gomux-variadic-functype 0 "$TMPROOT/gomux-variadic-functype"
run_case gomux-named-func-result 0 "$TMPROOT/gomux-named-func-result"
run_case gomux-body-functype     0 "$TMPROOT/gomux-body-functype"
run_case gomux-body-typedecl     0 "$TMPROOT/gomux-body-typedecl-functype"
run_case r11-closure-excluded    1 "$TMPROOT/gomux-r11-closure-still-excluded"

echo
echo "=== round 11: each refusal must carry ITS OWN label, not a borrowed one ==="
# An exit code cannot see a wrong label, and this engine has now met the F8
# class three times: a right verdict under a false label sends the reader to
# fix the wrong thing. `open.  HandleFunc("/wipe", h)` has a perfectly good
# string-literal path AND a perfectly ordinary bare-identifier receiver, so
# BOTH neighbouring labels would be untrue of it.
r11_label() {  # r11_label <name> <fixture> <must-contain> <must-NOT-contain...>
  local name="$1" fx="$2" want="$3"; shift 3
  local out ok=1
  out="$(nice -n 19 "$GATE" --policy "$TMPROOT/$fx/policy.yaml" --root "$TMPROOT/$fx" 2>&1 || true)"
  printf '%s' "$out" | grep -q "$want" || ok=0
  local bad
  for bad in "$@"; do printf '%s' "$out" | grep -q "$bad" && ok=0; done
  if [[ "$ok" == 1 ]]; then
    PASS_N=$((PASS_N + 1)); printf 'ok   %-24s refused under its own label\n' "$name"
  else
    FAIL_N=$((FAIL_N + 1))
    printf 'NOT-OK %-22s wrong or missing refusal label\n' "$name" >&2
    printf '%s\n' "$out" | sed 's/^/       | /' >&2
  fi
}
r11_label r11-split-label     gomux-split-selector   'separated from the member by whitespace or a'   'path is not a string literal' 'cannot name the mux it registers on'
r11_label r11-ws-label        gomux-ws-selector   'separated from the member by whitespace or a'   'path is not a string literal' 'cannot name the mux it registers on'
r11_label r11-gin-ws-label    gin-ws-selector   'separated from the verb by whitespace'   'path is not a string literal on the same line'
r11_label r11-group-label     gin-group-split-exempt   'path prefix and the middleware it inherits are not resolvable'   'path is not a string literal on the same line'
# The `\s\.` half of the whitespace detector (`open .HandleFunc(`) is pinned by
# the LABEL, never by the exit code: measured 2026-08-27, narrowing the detector
# to `\.\s+` leaves the fixture exiting 1 anyway, because round 9's
# `_sites > _named` counter catches it — but under "receiver is neither a bare
# identifier nor a dotted selector", which is FALSE of `open .HandleFunc(`,
# whose receiver is a perfectly ordinary bare identifier. A mutation that
# SURVIVES on an exit code is not evidence the code is redundant when the
# VERDICT TEXT is what moved (§11.4.115(F)); this is that pin.
r11_label r11-before-dot-label gomux-ws-before-dot   'separated from the member by whitespace or a'   'neither a bare identifier nor a dotted selector'

echo
echo "=== round 11: the negative controls resolve REAL routes, not zero ==="
# A negative control that passes because the extractor went BLIND proves
# nothing (§11.4.201(6) FALSE-NULL). Each must resolve its routes for real.
r11_routes() {  # r11_routes <name> <fixture> <expected-count>
  local name="$1" fx="$2" want="$3" got
  got="$(nice -n 19 python3 "$REPO_ROOT/scripts/pre_build/lan_route_auth_analyzer.py" \
          --policy "$TMPROOT/$fx/policy.yaml" --root "$TMPROOT/$fx" --json 2>/dev/null \
        | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["routes"]))')"
  if [[ "$got" == "$want" ]]; then
    PASS_N=$((PASS_N + 1)); printf 'ok   %-24s resolved %s route(s)\n' "$name" "$got"
  else
    FAIL_N=$((FAIL_N + 1))
    printf 'NOT-OK %-22s expected %s route(s), resolved %s\n' "$name" "$want" "$got" >&2
  fi
}
r11_routes r11-negctl-gomux    gomux-split-negctl 3
r11_routes r11-negctl-gin      gin-ws-negctl      2
r11_routes r11-negctl-group    gin-group-negctl   2

echo
echo "=== round 11: the .Group negative control keeps its PREFIX ==="
# The cheap wrong fix is to refuse every `.Group(` line. That passes the two
# bluff fixtures above and silently destroys prefix resolution, so this asserts
# the prefixed path SURVIVES — the property the refusal exists to protect.
gp_out="$(nice -n 19 python3 "$REPO_ROOT/scripts/pre_build/lan_route_auth_analyzer.py" \
           --policy "$TMPROOT/gin-group-negctl/policy.yaml" \
           --root "$TMPROOT/gin-group-negctl" --json 2>/dev/null || true)"
if printf '%s' "$gp_out" | grep -q '"/admin/wipe"'; then
  PASS_N=$((PASS_N + 1)); printf 'ok   %-24s ordinary .Group() still resolves /admin/wipe\n' r11-group-prefix
else
  FAIL_N=$((FAIL_N + 1))
  printf 'NOT-OK %-22s ordinary .Group() lost its prefix\n' r11-group-prefix >&2
  printf '%s\n' "$gp_out" | sed 's/^/       | /' >&2
fi

echo
echo "=== real-tree run (informational; gate reports the live posture) ==="
rt=0; nice -n 19 "$GATE" >/dev/null 2>&1 || rt=$?
echo "real-tree exit: $rt"

echo
echo "=== $HARNESS_NAME summary: PASS=$PASS_N FAIL=$FAIL_N ==="
[[ "$FAIL_N" -eq 0 ]] || exit 1
exit 0
