#!/usr/bin/env python3
"""lan_route_auth_analyzer.py — resolve LAN-reachable HTTP routes and their
authentication wiring from the AUTHORITATIVE source (§11.4.201).

Purpose:
    Detection engine behind the CM-LAN-ROUTES-AUTHENTICATED pre-build gate
    (§11.4.135 permanent regression guard for the operator's BOB-102 decision
    of 2026-08-26: "Keep 0.0.0.0 + auth guard"). It enumerates every route a
    LAN-bound listener serves and resolves, per route, whether that route is
    genuinely wired to an authentication mechanism.

    It does NOT grep for the string "auth". Greping for a token that MENTIONS
    auth asserts a proxy signal, and a proxy signal is exactly the §11.4.201
    failure this gate exists to avoid.

MODELLED REGISTRATION IDIOMS (the honest scope — §11.4.6):
    This engine understands a BOUNDED set of registration forms. It does not
    claim to see every route a framework can express; it claims to see the
    forms below AND to FAIL CLOSED when it meets one it does not model.

      fastapi  decorator registration with a STRING-LITERAL path
               (`@router.post("/p")`), parsed with `ast`. A route is protected
               iff a `Depends(<marker>)` genuinely reaches it: as a handler
               parameter default, as the decorator's `dependencies=[...]`, via
               its `APIRouter(dependencies=[...])`, or through a module-level
               alias (`_g = Depends(marker)`; `_: None = _g`).
      gin      single-line registration with a string-literal path
               (`r.POST("/p", h)`), including `Group(...)` prefix resolution.
               A route is protected iff an auth marker is really installed via
               `.Use(...)` on the owning engine or group.
      gomux    `mux.HandleFunc("/p", h)` with a string-literal path. Wrapping
               is resolved PER MUX VARIABLE: a route is protected iff the
               specific `http.NewServeMux()` value it was registered on is the
               one an auth marker actually wraps in a `return`. A second, bare
               mux in the same file is therefore correctly reported UNSAFE —
               a whole-file "does a wrap appear anywhere" test would falsely
               attribute safety to it, which is worse than missing a route.

    Anything outside that set — `add_api_route`, `.mount`, `.websocket`,
    gin `.Any` / `.Match` / `.Handle` / `.Static*` / `.NoRoute`, a multi-line
    or non-literal path expression, or a registration on the global
    `http.DefaultServeMux` — is reported as an UNMODELLED REGISTRATION IDIOM
    and FAILS the gate. It is not silently skipped: a guard whose stated
    purpose is catching tomorrow's drift must never answer "clean" about a
    construct it cannot see (§11.4.201(7)(c) — the path is part of the
    instrument).

EVERY SKIP IN EVERY EXTRACTOR, CLASSIFIED (§11.4.250 — the primitive, not
another door):
    Silent-drop defects keep arriving on this gate through a different
    `continue` each round: three by round 5, four more in extract_fastapi in
    round 6, plus four FALSE-CREDIT leaks found by round 6's audit. Repetition
    of one shape is not N bugs; it says the PRIMITIVE was wrong. There are two
    primitives here and both are now stated as rules:

      (1) a route resolver has exactly one honest way to step over a line or a
          node, and that is to have PROVEN the thing is not a resolvable
          registration; and
      (2) a CREDIT — anything that marks a route protected — must never be
          attributed across a scope boundary this resolver cannot see: not
          across a dotted receiver, not across a re-binding, not across a
          function.

    So every skip below is enumerated and given one of three verdicts, and the
    enumeration is part of the source so a reviewer can check it against the
    code rather than take it on faith.

      REFUSES  emits an UNMODELLED finding first, so the gate FAILS. The
               construct is visible; nothing is blessed.
      FILTER   steps over something PROVEN not to be a route registration.
               Not a drop: there is no route here to lose.
      DROPS    steps over a construct that COULD carry a route, with no
               finding. This is the defect class.

    WHAT THIS ENUMERATION CLAIMS, AND WHAT IT NO LONGER CLAIMS
    (§11.4.118 / §11.4.6 — round-6 RETRACTION):
      Earlier revisions of this table asserted "There are none left; any future
      entry in this column is a release blocker." THAT CLAIM IS WITHDRAWN.
      It was never earnable by inspection — absence of evidence of looking is
      not evidence of absence — and three consecutive reviews falsified it by
      attacking a surface the previous round had not attacked (round 6 found
      four drops in extract_fastapi alone, in minutes). It was also actively
      harmful: it turned every newly-discovered idiom into a standing release
      blocker, which is a promise this engine cannot keep and which penalises
      exactly the discovery that keeps it honest.

      What is claimed instead is this, and nothing more:
        * ENUMERATED SET — the skips listed below are the ones actually
          exercised. Each has a fixture in
          tests/pre_build/test_check_cm_lan_routes_authenticated.sh, and every
          REFUSES verdict in this table is pinned by a fixture that DIES when
          that refusal is removed (§11.4.115(F) — an invariant nothing pins is
          unvalidated instrumentation).
          HOW THAT WAS ESTABLISHED, and how to re-establish it: each refusal
          was DELETED one at a time in a scratch copy and the harness re-run;
          a refusal whose deletion the harness survives is unpinned. Round 6
          ran that sweep because writing this paragraph raised the question,
          and it found SIX unpinned refusals — websocket_route, gin `.Match`,
          gin `.NoRoute`, http.DefaultServeMux, unknown service kind, and an
          exemption missing service/path — every one of them a verdict this
          engine honoured with nothing holding it to it. All six now have
          fixtures, and each fixture was itself checked to FAIL under the
          deletion (the DefaultServeMux one needed an exemption added before
          it could fail at all: without it the route resolved unauthenticated
          and the fixture exited 1 either way — a could-not-fail shape that
          pins nothing). Re-run the sweep after adding any refusal; a claim of
          this kind is only worth what its last measurement is.
        * METHOD — the registration and credit surfaces below were derived by
          reading the INSTALLED framework source (§11.4.201 authoritative
          source, never memory), by walking the constructs this engine uses to
          mark a route protected against primitive (2) above, and by
          REPRODUCING each candidate against the shipped analyzer before
          calling it a defect (§11.4.199). That is a STATED METHOD over an
          ENUMERATED SET, not a survey that terminated.
        * THE CREDIT-SIDE COMPLETENESS CLAIM IS WITHDRAWN TOO (round 7).
          Round 6 retracted the DROPS-completeness assertion and then wrote a
          fresh absolute one column over — "every construct able to mark a
          route protected was audited; the four that leaked are pinned". Round
          7 falsified it TWICE, in two constructs that same audit had recorded
          as "measured fail-closed": a gin group NAME re-bound by a declaration
          the modelled pattern cannot see, and a gomux `http.NewServeMux()`
          declaration reached through a selector. Both came back auth_wired=
          true, findings 0, exit 0 on an unauthenticated mutating route. The
          lesson is the one the DROPS retraction already recorded and this
          engine had to learn a second time: "audited" is a record of where
          somebody LOOKED, and inspection cannot convert that into "there are
          no others" (§11.4.118). What is claimed for the credit side is
          exactly what is claimed for the drop side — an enumerated set, a
          stated method, and an honest gap — and a credit construct discovered
          later is a TRACKED COVERAGE ESCAPE (§11.4.238), not a broken promise.
          The per-construct verdicts below are dated measurements, and a
          verdict of "fail-closed" means "measured fail-closed on the shapes
          tried", never "cannot leak".
        * HONEST GAP — an idiom outside that enumerated set is UN-SURVEYED,
          not proven absent. These frameworks are large and this method samples
          them. A newly-found idiom is a TRACKED COVERAGE GAP, to be closed
          with a fixture and a coverage-escape note (§11.4.238 — the escape is
          itself the finding), NOT a broken promise. The DROPS column stays in
          this table and stays filled in honestly; only the completeness
          assertion is gone.

    extract_fastapi
      not a FunctionDef/AsyncFunctionDef ......... FILTER  the decorator loop
          only visits functions. CORRECTION (round 6): the previous
          justification here — "caught separately by FASTAPI_UNMODELLED_CALLS"
          — was PROVEN FALSE. A `@router.post("/p")` above a CLASS, and an
          immediate-call `router.post("/p")(fn)`, both register through `post`,
          which is not in that tuple; both were DROPS, reproduced against the
          shipped engine as exit-0 PASSes with the mutating route gone. They
          are now caught by the router-attribute rule below, and THAT is what
          makes this line a FILTER instead of a DROP.
      decorator is not `<attr-expr>(...)` ........ FILTER  the loop reads the
          router name off `dec.func.value`. CORRECTION (round 6): the previous
          justification — "a bare-name or non-call decorator cannot be
          `@router.get("/p")`" — was also PROVEN FALSE: `reg = router.post`
          followed by `@reg("/p")` is a bare-name decorator that registers a
          route. Caught by the same rule below, via the `router.post`
          ATTRIBUTE in the assignment rather than the decorator.
      `<router>.<verb>` / `<router>.route` used
          OUTSIDE a modelled decorator ........... REFUSES (round 6). Closes
          all three shapes above. Deliberately keyed on the OWNER being a
          router THIS module declared: a rule keyed on the verb NAME alone —
          the shape first proposed for this fix — fires on `d.get(k)`,
          `os.environ.get(k)` and `requests.post(...)`, because `.get` is both
          an HTTP verb and the most common method name in Python. That
          unqualified form is the §11.4.201(1) false-positive machine this
          table warns about two entries down; the owner qualification is what
          makes the rule shippable, and `fastapi-verbnames-not-routers` is the
          fixture that holds it to it.
      meth in FASTAPI_UNMODELLED_DECOS ........... REFUSES (websocket,
          websocket_route, api_route, route). `route` was added in round 6:
          it is a REAL registration decorator (routing.py:1317 in the installed
          FastAPI — 102 lines ABOVE the `api_route` at 1419 that round 5 cited)
          and it was DROPPED. It can never be MODELLED as protected, because it
          calls `add_route()`, which builds a plain starlette Route that
          FastAPI's dependency injection never runs on — so no `Depends(marker)`
          can reach it. Refusal is the only honest verdict for it.
      meth not in HTTP_METHODS ................... FILTER  the decorator is
          not one of FastAPI's route verbs. The verb list is checked against
          the INSTALLED FastAPI source rather than memory — that check is what
          surfaced `trace` (dropped) and `api_route` (dropped) in round 5, and
          it is also where round 5 fell short: it was run INCOMPLETELY and
          missed `route`, sitting in the same file 102 lines above `api_route`.
          Running the right method is not the same as running it to
          exhaustion. A
          blanket refusal here would instead fire on every ordinary decorator
          (@app.exception_handler, @_rl(...), @dataclass) — the §11.4.201(1)
          false-positive machine.
      owner is None (dotted/computed router) ..... REFUSES (was a DROP; fixed
          round 5)
      path is not a string literal ............... REFUSES

    extract_gin
      *_test.go .................................. FILTER  a Go test file is
          not compiled into the shipped binary, so it serves no LAN route.
      line has no HTTP-verb call skeleton ........ FILTER  no `.VERB(` pair on
          this line. CORRECTION (round 6): the previous justification — "the
          verb+`(` pair cannot span a newline in gofmt'd Go" — rested on a
          gofmt assumption nothing in this gate enforces. Go inserts no
          semicolon after a trailing `.`, so `r.` on one line with
          `POST("/p", h)` on the next is legal, compiles, and was DROPPED. The
          split form is now REFUSED explicitly by the selector-continuation
          rule below, rather than assumed impossible.
      selector split across lines (`r.` then a
          `VERB(` line) .......................... REFUSES (round 6, was a DROP)
      `.Use(marker)` on a dotted receiver ........ FILTER  the CREDIT is
          dropped, never granted (round 6, was a silent FALSE-SAFE: GIN_USE had
          no lookbehind, so `s.router.Use(auth)` credited an unrelated LOCAL
          `router` engine and an unauthenticated mutating route came back
          auth_wired=true). A dotted `.Use` is not a route registration, so
          there is no route to lose here; withholding the credit leaves any
          route on that receiver uncovered, which is the fail-closed direction.
      more than one gin ENGINE DECLARATION SITE
          in one file ............................ REFUSES (round 6 widened
          this from one-entry-per-NAME to one-per-SITE: two functions each
          declaring `r := gin.New()` collapsed to a single entry, the refusal
          never fired, and `uses` is file-scoped — so one function's
          `r.Use(auth)` credited the other function's unauthenticated route).
      line holds more than one statement ......... REFUSES (was a DROP on
          `.Group(` lines and a silent FALSE-SAFE on `; .Use(...)` lines; both
          fixed round 5 — see the comment at the check itself)
      route on a dotted receiver (`x.y.VERB(`) ... REFUSES (was a silent
          FALSE-SAFE: the owner regex captured only the last name of the
          chain, so the route inherited a same-named local engine's `.Use`;
          fixed round 5)
      verb call with no literal path ............. REFUSES
      gin form in GIN_UNMODELLED ................. REFUSES

    extract_gomux
      *_test.go .................................. FILTER  as above.
      line holds NO `.HandleFunc(`/`.Handle(`
          call site at all ......................... FILTER  there is no
          registration on this line, so there is no route to lose.
      call site whose RECEIVER this model
          cannot NAME .............................. REFUSES (round 9, was a
          SILENT DROP). CORRECTION (round 9): this row previously read "line
          has no mux-registration skeleton ... FILTER  no route to lose", and
          that was FALSE BY THIS TABLE'S OWN TAXONOMY — the construct DROPS a
          route, it does not filter a non-route. The round-7 entry it replaces
          correctly identified the cause (gin has the lookbehind-free catch-all
          `GIN_VERB`, "gomux had no such catch-all") and then widened only the
          DOTTED spelling, so every OTHER unnameable receiver kept dropping.
          Measured 2026-08-26: `newServeMux().HandleFunc("/wipe", h)` beside a
          healthy `mux.HandleFunc("/ok", h)` gave exit 0 / routes 1 /
          findings 0 with the mutating route ABSENT from the inventory;
          `s.buildMux().HandleFunc(...)` and `muxes[0].HandleFunc(...)`
          dropped identically. `MUX_CALL` is now the catch-all gomux lacked,
          and the count comparison against MUX_ANY + MUX_DOTTED_OWNER makes
          "cannot name the receiver" decidable per CALL SITE, so a line
          holding both a nameable and an unnameable one refuses instead of
          half-registering. Pins: `gomux-call-receiver-refused`,
          `gomux-methodcall-receiver-refused`,
          `gomux-index-receiver-refused`, `gomux-mixed-line-refused`, with
          `gomux-dotted-handler-arg-ok` as the false-positive control.
      _carriers: line is not an assignment ....... FILTER  a non-assignment
          cannot propagate a mux value. A carrier this pass MISSES shrinks the
          name set, which can only move a verdict toward UNWRAPPED — that
          direction is fail closed. CORRECTION (round 7): earlier revisions
          stopped there and recorded the construct as fail-closed FULL STOP.
          The other direction is fail-OPEN and was not recorded: the
          propagation is lexical, so `stats := describe(mux)` makes `stats`
          carry `mux` and `return WithAuth(stats)` credits it (measured
          auth_wired=true). Owned in full at `_carriers` and pinned by
          `gomux-carrier-over-approximates`; carried as an honest gap, not as
          a solved problem.
      _carriers: name already in the set ......... FILTER  fixpoint bookkeeping.
      owner == "http" (DefaultServeMux) .......... REFUSES
      registration on a dotted receiver
          (`s.mux.HandleFunc(...)`) .............. REFUSES (round 6, was a
          silent FALSE-SAFE — the exact GIN_ROUTE defect of round 5 living in
          the third extractor: MUX_ROUTE's bare-name-then-dot capture also
          took only the LAST name of the chain, so `s.mux.HandleFunc("/wipe")`
          resolved to
          owner "mux" and inherited an unrelated LOCAL mux's
          `return WithAuth(mux)`. Found by round 6's credit audit, not by a
          report.)
      path is not a string literal ............... REFUSES

    main()
      policy declares zero services .............. REFUSES (was a silent PASS
          — deleting the declaration list turned the gate green over a
          wide-open tree; fixed round 5. It is not a `continue`, but it is the
          same shape and the enumeration would be dishonest without it.)
      exemption missing service/path ............. REFUSES (records a finding)
      unknown service kind ....................... REFUSES (records a finding)
      service not lan_bound ...................... FILTER  declared scope
          (§11.4.6). NOTE the residual: this reads the POLICY's claim, not the
          binary's real bind address. A service wrongly declared
          `lan_bound: false` is invisible to this gate — the policy carries
          per-service BIND EVIDENCE for exactly that reason, and keeping that
          evidence true is the policy's job, not this engine's.
      route is auth-wired ........................ FILTER  nothing to report.
      route matched an exemption ................. FILTER  by design, and the
          exemption itself is validated (class + non-empty justification).
      exemption already matched / route live ..... FILTER  staleness accounting.

HONEST BOUNDARY — static wiring is not runtime arming (§11.4.6):
    This engine asserts that a route is ATTACHED to an auth mechanism. It does
    NOT assert the mechanism is ARMED at runtime. The merge-service marker
    `require_api_token` is env-conditional and returns immediately when
    `BOBA_API_TOKEN` is unset, so a statically-protected route can still be
    open in a running deployment. Arming `BOBA_API_TOKEN` and backing it with
    a boot-time invariant (§11.4.254) is tracked separately as BOB-197.
    Claiming that coverage here would be the bluff this guard exists to
    prevent.

Usage:
    lan_route_auth_analyzer.py --policy <policy.yaml> --root <tree> [--json]

Inputs:
    --policy  checked-in policy: LAN-bound service declarations + the
              exemption list (consumer-owned DATA, §11.4.35).
    --root    tree the declared service roots resolve against.
    --json    emit the machine-readable finding record instead of prose.

Outputs:
    Resolved route inventory + per-finding evidence on stdout/stderr.

Side-effects:
    None. Read-only static analysis. No process is signalled, no service is
    contacted, no file is written.

Dependencies:
    python3 (>= 3.9) stdlib `ast` + `re`, plus PyYAML for the policy file.

Exit codes:
    0 PASS · 1 FAIL (findings) · 2 ERROR (unusable policy/interpreter).

Cross-references:
    §11.4.6 §11.4.35 §11.4.107(10) §11.4.135 §11.4.201 §11.4.224 §11.4.226
    §11.4.254 (BOB-197 runtime arming).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

# Verified against the INSTALLED FastAPI source, never memory (§11.4.201
# authoritative source): `trace` is a real route decorator on both
# APIRouter (fastapi/routing.py:4490) and FastAPI (applications.py:4193).
# It was absent here, so a `@router.trace("/p")` route was silently
# DROPPED — the round-5 mirror of the gin compound-line defect.
HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options",
                "trace")
MUTATING = {"POST", "PUT", "DELETE", "PATCH"}

# fastapi registration calls this engine does not model.
FASTAPI_UNMODELLED_CALLS = (
    "add_api_route", "add_route", "add_websocket_route",
    "add_api_websocket_route", "mount", "host",
)
# `api_route` (routing.py:1419 / applications.py:1222) IS a real
# registration decorator with a literal path, but its METHOD SET comes
# from a `methods=[...]` kwarg this model does not read — so the route
# cannot be resolved to a method and is REFUSED, never dropped.
#
# `route` (routing.py:1317) is a real registration decorator too, and it
# was DROPPED until round 6 — 102 lines ABOVE the `api_route` round 5
# found, in the same file, missed because the verb-list check was run
# once rather than to exhaustion. It belongs here PERMANENTLY, never in
# HTTP_METHODS: it calls `add_route()`, which builds a plain starlette
# Route, and FastAPI's dependency injection never runs on one — so a
# `Depends(marker)` can NEVER reach it and it can never be modelled as
# protected. Refusal is the only verdict here that is not a lie.
FASTAPI_UNMODELLED_DECOS = ("websocket", "websocket_route", "api_route", "route")

# Why each refused decorator is refused. A refusal that prints the wrong
# reason is still a correct verdict, but it costs the reader a wrong
# investigation — and a gate nobody trusts to explain itself gets bypassed.
_DECO_REFUSAL_REASON = {
    "websocket": "websocket routes are not modelled",
    "websocket_route": "websocket routes are not modelled",
    "api_route": "the method set comes from a `methods=[...]` kwarg this model "
                 "does not read, so the route cannot be resolved to a method",
    "route": "`route` registers a plain starlette Route via add_route(), which "
             "FastAPI's dependency injection never runs on, so no "
             "Depends(marker) can ever reach it",
}

# gin registration forms this engine does not model.
GIN_UNMODELLED = (
    "Any", "Match", "Handle", "Static", "StaticFile", "StaticFS",
    "StaticFileFS", "NoRoute", "NoMethod",
)


class Route:
    __slots__ = ("auth", "evidence", "method", "path", "service", "why")

    def __init__(self, service, method, path, auth, evidence, why):
        self.service = service
        self.method = method
        self.path = path
        self.auth = auth
        self.evidence = evidence
        self.why = why

    def key(self):
        return (self.service, self.method, self.path)

    def as_dict(self):
        return {
            "service": self.service,
            "method": self.method,
            "path": self.path,
            "auth_wired": self.auth,
            "evidence": self.evidence,
            "resolution": self.why,
        }


def _norm(p: str) -> str:
    """Canonical path key.

    NOTE (deliberate, not a bug): this collapses "/x" and "/x/" onto one key,
    so a stdlib-mux exact+subtree pair shares a single exemption entry. That
    is correct today because both are registered on the same mux and share its
    auth fate. If a framework is ever added where the two can diverge, this
    collapse must be revisited.
    """
    return "/" + "/".join(seg for seg in p.split("/") if seg)


def _const_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _unmod(svc_id, where, what, detail):
    return (
        f"UNMODELLED REGISTRATION IDIOM  {svc_id}  {what}\n"
        f"    declared at : {where}\n"
        f"    detail      : {detail}\n"
        f"    why it fails: this engine cannot resolve the route or its auth\n"
        f"                  wiring from this form, so it refuses rather than\n"
        f"                  reporting a confident, wrong 'clean' "
        f"(§11.4.201(7)(c)).\n"
        f"    remedy      : re-express the registration in a modelled form, or\n"
        f"                  extend the analyzer to model this idiom (and add a\n"
        f"                  fixture for it) before shipping the route."
    )


def _call_arg_spans(text, fname):
    """Balanced-paren argument text of every `fname(...)` call in `text`."""
    spans = []
    for m in re.finditer(r"\b" + re.escape(fname) + r"\s*\(", text):
        i, depth = m.end() - 1, 0
        for j in range(i, len(text)):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    spans.append(text[i + 1:j])
                    break
    return spans


def _walk_files(root, svc, suffix, skip_test=False):
    out = []
    for base in svc.get("roots", []):
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, base)):
            dirnames[:] = [
                d for d in dirnames
                if d not in ("__pycache__", ".git", "node_modules", "vendor")
            ]
            for fn in sorted(filenames):
                if not fn.endswith(suffix):
                    continue
                if skip_test and fn.endswith("_test" + suffix):
                    continue
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


# ------------------------------------------------------- go lexical utils ---
FUNC_LIT = re.compile(r"\bfunc\s*\(")
# ROUND 9 (IMPORTANT-1) — `func\s*\(` also matches a METHOD'S RECEIVER CLAUSE.
# `func (s *Server) Build() http.Handler {` opens with `func (`, so
# `_closure_spans` treated the WHOLE METHOD BODY as a `func(){}` literal and
# `_function_level_returns` then excluded the method's OWN
# `return WithAuth(mux)`. Measured 2026-08-26 with byte-identical bodies:
# the free-function spelling exited 0 (correct), the method spelling exited 1
# claiming "mux 'mux' is returned WITHOUT an auth marker" — a §11.4.201(1)
# FALSE REFUSAL on `func (s *Server) routes() http.Handler`, which is
# idiomatic Go. Fail-closed is not a defence: a gate that cries wolf on an
# idiom gets bypassed, and bypassing is how the silent-drop class returns.
# THE DISCRIMINATOR is what FOLLOWS the first balanced paren group: a method
# declaration continues with its NAME immediately followed by `(`
# (`) Build(`), while a func literal continues with `{` or with a result type
# (`) int {`, `) (a, b int) {`). `func` is excluded from the name position so
# a literal returning a function type (`func() func(int) int {`) is still read
# as a literal, not as a method.
#
# ROUND 11 (MINOR-1 follow-up) — THIS NOTE'S OWN MECHANISM WAS THE DEFECT.
# The round-9 wording called the `func` exclusion "BELT-AND-BRACES ... removing
# it changes no verdict, because when the outer `func(` is skipped the RETURN
# TYPE'S OWN `func(` is the next FUNC_LIT match and re-establishes the
# identical body span". The verdict-neutrality was TRUE and the reason was the
# problem: re-establishing that body span WAS the live IMPORTANT-2 defect —
# the note was describing a bug as a safety property. `_body_brace` (RULE D)
# now refuses that re-established span, so the sentence is no longer true of
# the current engine and has been retired rather than left standing.
# HONEST LABEL (§11.4.115(F)) as it stands today: `_METHOD_AFTER_RECV` is
# reachable only in the file PREAMBLE block or when `_signature_end` returns -1
# (a body-less declaration), because RULE S skips every receiver clause in a
# block that opens with a func declaration. It is kept as the fallback RULE S
# deliberately does not cover, and is recorded as UNPINNED rather than claimed
# as pinned.
_METHOD_AFTER_RECV = re.compile(r"\s*(?!func\b)\w+\s*\(")

# ROUND 11 (IMPORTANT-2) — THE PRIMITIVE `_METHOD_AFTER_RECV` only point-fixed.
# `func(` in Go introduces a func TYPE at least as often as a func LITERAL, and
# a TYPE HAS NO BODY. `_closure_spans` took `text.find("{", j)` on every match,
# so on a TYPE it walked forward and anchored the span on WHOEVER OWNS THE NEXT
# BRACE. Round 9 fixed exactly one shape of that (the method RECEIVER clause)
# and left the primitive; round 10 reported two more. Audited 2026-08-27
# against the real Go parser (`gofmt -e`, every shape below LEGAL), ELEVEN
# shapes were defective, not two:
#   in a SIGNATURE  — func-typed PARAM (method AND free function), func-typed
#                     RESULT (method AND free function), variadic
#                     `...func(*Server)`, named result `(h func(int) int, e error)`
#   in a BODY       — `var mw func(...)`, `type MW func(...)`,
#                     `make(chan func(int))`, `struct{ F func(int) int }`
#                     — each hijacked the brace of a FOLLOWING `if`/`for` block
#                     and hid a real `return WithAuth(mux)` inside it.
# Round 10 tested none of the four body shapes and neither free-function shape.
# Direction is uniformly fail-CLOSED (a bogus span only ever REMOVES returns,
# never adds one), so every instance CRIES WOLF on idiomatic Go — the §11.4.201(1)
# class round 9 itself argued gets gates bypassed.
#
# TWO RULES, because ONE cannot do it (measured, not assumed):
#   RULE S (signature position) — in a block that opens with a `func`
#     DECLARATION, everything before that declaration's OWN body brace is
#     SIGNATURE, so every `func(` there is a receiver clause or a TYPE.
#   RULE D (delimiter escape) — for a match anywhere else, a depth-0 `)` `]`
#     `}` `,` `;` `=` or NEWLINE between its parameter list and the candidate
#     `{` proves that brace belongs to an enclosing construct.
# Neither subsumes the other. RULE D alone cannot see the func-RESULT case:
# `func routes() func(int) int {` puts nothing but ` int ` between the inner
# `func(int)` and the body brace, and `func(int) int { return 0 }` IS a legal
# func literal (verified with `gofmt -e` — unnamed parameters are permitted in
# a literal), so that text is locally AMBIGUOUS and only its position inside a
# signature settles it. RULE S alone cannot see any of the four BODY shapes,
# which sit after the signature by construction.
_TYPE_BRACE_HEAD = re.compile(r"\b(?:struct|interface)\s*$")


def _body_brace(text, start):
    """Index of the `{` that opens the body of the construct whose header ends
    at ``start``, or ``-1`` when the next brace demonstrably belongs to
    something else (RULE D above).

    Go's semicolon insertion is what makes NEWLINE a member of the escape set:
    a func literal's `{` may never be separated from its signature by a line
    break (`h := func() int` + newline + `{` inserts a semicolon and does not
    compile), so a newline at depth 0 proves the brace is not ours.
    `struct{...}` / `interface{...}` is a TYPE in a constraint or result
    position rather than a body, so its balanced group is stepped over.
    """
    depth, i, n = 0, start, len(text)
    while i < n:
        ch = text[i]
        if ch == "{" and depth == 0:
            if _TYPE_BRACE_HEAD.search(text[max(0, i - 16):i]):
                d, j = 0, i
                while j < n:
                    if text[j] == "{":
                        d += 1
                    elif text[j] == "}":
                        d -= 1
                        if d == 0:
                            break
                    j += 1
                i = j + 1
                continue
            return i
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return -1
            depth -= 1
        elif depth == 0 and ch in ",;=\n":
            return -1
        i += 1
    return -1


def _signature_end(text):
    """Index of the `{` opening the body of the func DECLARATION this block
    starts with (RULE S above), or ``-1`` when the block does not start with
    one.

    `_go_func_blocks` splits on lines beginning `func `, so a block either
    OPENS with a declaration — receiver, type parameters, parameters and result
    all precede its body brace — or is the file preamble, which has no
    signature and where RULE D alone decides. A declaration with NO body
    (`func add(x, y int) int`, legal for assembly stubs) yields -1, which
    disables RULE S for that block rather than skipping the whole block: the
    conservative direction, since skipping everything would make MORE returns
    visible and that is the fail-OPEN one.
    """
    if not re.match(r"\s*func\b", text):
        return -1
    return _body_brace(text, 0)

# ---- ROUND 11 (BLOCKING-1 / IMPORTANT-1): THE SPLIT-SELECTOR PRIMITIVE ----
# A Go selector may be separated from its member by ARBITRARY WHITESPACE,
# including a NEWLINE. Every registration regex in both Go extractors requires
# the member to follow the dot IMMEDIATELY, so every such spelling matches
# NOTHING — and matching nothing is a SILENT DROP, never a refusal.
#
# Round 6 met this once, in gin, and fixed it in gin ONLY (`GIN_VERB_HEAD`).
# Five rounds later the gomux twin still dropped, because the fix was a DOOR
# and not the PRIMITIVE (§11.4.250). Measured 2026-08-27 against the real Go
# parser, `gofmt -e` accepting every spelling:
#
#   open.                       LEGAL, gofmt-STABLE (byte-identical through
#       HandleFunc("/wipe", h)  gofmt) — a mutating route ABSENT from the
#                               inventory, exit 0, zero findings, zero
#                               unmodelled, hidden behind a healthy sibling so
#                               the §11.4.201(6) zero-routes net cannot see it.
#   open.  HandleFunc(...)      LEGAL, gofmt NORMALISES it away — same drop.
#   open .HandleFunc(...)       LEGAL, gofmt normalises — same drop.
#   open . HandleFunc(...)      LEGAL, gofmt normalises — same drop.
#   r.  POST("/wipe", h)        the gin twin: with `r.Use(AuthMW())` above and
#                               one healthy sibling route, a clean exit 0 /
#                               zero findings over an unauthenticated mutating
#                               LAN route.
#
# THE DECISION (IMPORTANT-1 asked for it explicitly): REFUSE, do not resolve.
#   * Refusing is what the SHIPPED gin code already does for the newline half,
#     so refusing the whitespace half makes one primitive behave one way — the
#     §11.4.250 requirement. Resolving would have made the two halves diverge
#     again, in the opposite direction.
#   * Resolving means widening the NAMING regexes (`MUX_ANY`, `MUX_ROUTE`,
#     `GIN_ROUTE`, `GIN_USE`, `GIN_GROUP`) to `\.\s*`. Those carry the
#     `(?<![\w.])` carrier lookbehinds and the MUX_ANY/MUX_DOTTED_OWNER mutual
#     exclusivity the `_sites`/`_named` arithmetic rests on; widening them
#     widens the CREDIT side and would require re-proving all of it. A refusal
#     is a strictly smaller blast radius for the same closure.
#   * None of the whitespace spellings survives gofmt, so resolving them buys
#     no coverage of code anyone actually commits.
# The DETECTORS below are therefore new and separate: nothing that grants
# credit is touched, so no carrier-safety property moves (re-verified — see the
# harness's `r11-mux-exclusivity-fuzz` needle).
#
# HONEST SCOPE (§11.4.6), the rest of the audit round 10 did not run. The same
# primitive also hits `.Use(`, `gin.Default()` and `http.NewServeMux()`.
# Measured 2026-08-27, each DROPS THE CREDIT and is therefore fail-CLOSED and
# LOUD — the route is still inventoried, reads unwrapped, and the gate exits 1
# naming it — so they are documented here rather than refused, which would add
# a second finding for a hole the first one already reports. `.Group(` is NOT
# in that set: it corrupts the route PATH and can be blessed by a stale
# exemption, so it is refused alongside the verbs.


def _selector_head(members):
    """A continuation line that OPENS with `<member>(` — the far half of a
    selector whose dot ended the previous line."""
    return re.compile(r"\s*(?:" + members + r")\s*\(")


def _ws_selector(members):
    """A selector whose dot is separated from `<member>(` by whitespace on ONE
    line — `x.  M(`, `x .M(`, `x . M(`.

    Deliberately keyed on whitespace TOUCHING the dot, so the ordinary
    `x.M(` never matches and no false refusal is minted (§11.4.201(1)). A
    dotted handler ARGUMENT cannot match either: the member must be followed by
    `(`, and an argument is followed by `,` or `)`.
    """
    return re.compile(r"(?:\s\.\s*|\.\s+)(?:" + members + r")\s*\(")


GO_TRAILING_DOT = re.compile(r"\.\s*$")
# Assignment TARGETS on a line, bare names only. Used to poison a group name
# whose declaration this model refused, so no later registration on that name
# can inherit a prefix that was never resolved. A DOTTED target
# (`s.g = r.Group(...)`) is deliberately not captured — the same lookbehind
# rule the credit-bearing regexes carry — and the refusal still fires, so the
# hole is reported either way.
GO_ASSIGN_TARGET = re.compile(r"(?<![\w.])(\w+)\s*:?=")


def _selector_is_split(bare_lines, idx, head_re):
    """True when the `bare` line at 0-based ``idx`` ends in a selector dot whose
    member opens the next line THAT CARRIES CODE.

    Lines are read from the `bare` projection, so a trailing `.` inside a
    comment or a string literal can never mint this refusal.

    THE SCAN IS FORWARD-OVER-BLANKS, and that is load-bearing rather than
    tidiness. Go permits ARBITRARY whitespace after a selector dot, and `bare`
    has already blanked comments to spaces, so BOTH of these are legal Go
    (`gofmt -e`) that an immediate-next-line check silently drops. Measured
    2026-08-27 against the FIRST CUT OF THIS VERY FIX — exit 0, 1 route,
    `/wipe` absent from the inventory: the same BLOCKING shape, one gap wider.

        open.                             open.
            // wipe endpoint
            HandleFunc("/wipe", h)            HandleFunc("/wipe", h)

    Scanning to the first line with content models the LANGUAGE instead of the
    common case, which is the difference between closing a primitive and moving
    its door one line over (§11.4.250). The walk stops at that first non-blank
    line, so a trailing dot at end of file costs one pass over the remaining
    blanks and nothing more.
    """
    if not GO_TRAILING_DOT.search(bare_lines[idx]):
        return False
    for k in range(idx + 1, len(bare_lines)):
        if not bare_lines[k].strip():
            continue
        return bool(head_re.match(bare_lines[k]))
    return False


# Go's lexical modes. Only `block` and `raw` CARRY ACROSS a newline: a `//`
# comment ends at end-of-line, and neither an interpreted string ("...") nor a
# rune literal ('...') may span a line in Go.
_GO_LINE_CROSSING = ("block", "raw")


def _go_lex(text):
    """One stateful pass over Go's lexical modes.

    Returns ``(code_lines, bare_lines, lex_gaps)``.

    ``code_lines``  comments blanked; interpreted-string and rune literals KEPT
                    verbatim (every route regex reads its path out of a "..."
                    literal); raw-string CONTENT blanked with the backticks
                    kept, so a route registration written inside a doc string
                    can never mint a phantom route, and a genuine raw-string
                    path degrades to a registration whose path is not a string
                    literal — which the extractors already refuse (fail closed).
    ``bare_lines``  comments AND every literal blanked — the projection the
                    return/decl scans read, so no literal can ever prove code.
    ``lex_gaps``    ``[(lineno, what)]``, one per construct that cannot be
                    lexed to a close. Refused, never silently swallowed.

    Every substitution is length-preserving (content replaced by spaces), so
    column offsets and line numbers survive for the callers that report them.

    HONEST LIMIT (§11.4.6, measured — stated, not half-fixed): `splitlines()`
    also breaks on lone \r, \f and \x85, which Go treats as ordinary bytes
    inside a literal. A Go literal containing one of those would therefore
    shift this engine's reported line NUMBERS relative to an editor. It cannot
    change a VERDICT: both projections come from the same split, so they stay
    index-aligned with each other, and the callers only ever compare lines to
    lines. Re-measured 2026-08-27 over every non-vendor .go file under
    qBitTorrent-go/ (107 files, a superset of the 19 the policy scans):
    zero occurrences of \r, \f, \x85, U+2028 or U+2029, and 0 lex gaps
    with a control needle proving the scan was not blind.
    THE COUNT IS DATED FOR A REASON (round 11, NIT-2): the round-9 figure of
    106 was correct when taken and had drifted to 107 by the next day — the
    delta is one concurrently-added `*_test.go`, which `skip_test=True` keeps
    OUT of the 19-path scan set, so the scan-list digest below is unchanged.
    A census is a dated MEASUREMENT, never a standing claim.

    THE RECIPE, BESIDE THE NUMBERS (round 6). A digest whose command is not
    recorded is not reproducible, and an unreproducible digest is decoration
    that looks like evidence. Both figures above regenerate with:

        # the 106 — every non-vendor .go file, tests included
        find qBitTorrent-go -name '*.go' -not -path '*/vendor/*' | wc -l

        # the 19 — the set this policy actually scans, and its digest
        python3 - <<'EOF' | tee /tmp/scanlist.txt | wc -l
        import sys, yaml
        sys.path.insert(0, "scripts/pre_build")
        import lan_route_auth_analyzer as A
        pol = yaml.safe_load(open("config/lan_route_auth_policy.yaml"))
        out = []
        for svc in pol["services"]:
            if not svc.get("lan_bound"):
                continue
            suf = ".py" if svc["kind"] == "fastapi" else ".go"
            out += A._walk_files(".", svc, suf, skip_test=(svc["kind"] != "fastapi"))
        for p in sorted(out):
            print(p)
        EOF
        sha256sum < /tmp/scanlist.txt | cut -c1-16

    Re-measured 2026-08-27: the scan list is 19 paths (8 .py + 11 .go) and its
    sha256 head is c7a793a0021c3804 — unchanged. The
    effect is diagnostic-only and is left stated rather than patched, because
    a partial line-splitter would be a new instrument with no fixture.

    WHY THIS IS ONE PASS (review round 4, BLOCKING).
      The previous revision modelled this grammar with a MISMATCHED mix: a
      whole-text DOTALL regex for ``/* */`` but LINE-scoped scanners for ``//``
      and for string literals. Go's backtick RAW STRING spans lines — it is the
      string analogue of a block comment — so a line-scoped scanner lost its
      state at every newline and re-read each interior line as FRESH CODE. A
      ``return WithAuth(mux)`` sitting in a doc string then PROVED a wrap that
      does not exist: the carrier-proves-the-thing class (§11.4.201(7)(a)) that
      round 2 killed for ``//``, returning through the one string form a
      line-scoped blanker cannot see. Measured on the real gomux root, that
      channel was one moved mux away from arming — credentials.go carries 56
      backticks, indexers.go 34, catalog.go 30.
      The same mismatch produced two more defects with the same root: a ``/*``
      written inside a ``//`` comment let the regex blank the intervening REAL
      wrap (a §11.4.201(1) FAIL-bluff — a gate that cries wolf gets bypassed),
      and an UNTERMINATED ``/*`` never matched ``/\\*.*?\\*/`` at all, so a fake
      wrap inside it survived and proved the wrap (a fail-OPEN on exactly the
      "cannot lex this" construct where the discipline is to fail CLOSED).
      Modelling the modes once, statefully, closes all three at the root.
    """
    code_out, bare_out, gaps = [], [], []
    mode = "code"
    lineno = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        code_buf, bare_buf = [], []
        i, n = 0, len(line)
        while i < n:
            ch = line[i]

            if mode == "block":
                if ch == "*" and i + 1 < n and line[i + 1] == "/":
                    mode = "code"
                    code_buf.append("  ")
                    bare_buf.append("  ")
                    i += 2
                    continue
                code_buf.append(" ")
                bare_buf.append(" ")
                i += 1
                continue

            if mode == "raw":
                # No escape processing inside a raw string: a trailing `\` is a
                # literal backslash and must NOT consume the closing backtick.
                if ch == "`":
                    mode = "code"
                    code_buf.append("`")
                else:
                    code_buf.append(" ")
                bare_buf.append(" ")
                i += 1
                continue

            # --- mode == "code": whichever opener comes FIRST wins ----------
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                pad = " " * (n - i)          # a `//` comment runs to EOL, and a
                code_buf.append(pad)         # `/*` or a backtick inside it is
                bare_buf.append(pad)         # comment TEXT, never an opener.
                i = n
                continue

            if ch == "/" and i + 1 < n and line[i + 1] == "*":
                mode = "block"
                code_buf.append("  ")
                bare_buf.append("  ")
                i += 2
                continue

            if ch == "`":
                mode = "raw"
                code_buf.append("`")
                bare_buf.append(" ")
                i += 1
                continue

            if ch in ('"', "'"):
                j, closed = i + 1, False
                while j < n:
                    if line[j] == "\\":      # escapes DO apply here
                        j += 2
                        continue
                    if line[j] == ch:
                        j += 1
                        closed = True
                        break
                    j += 1
                if not closed:
                    # Neither form may span a line in Go, so this file is not
                    # lexable. Refuse it (§11.4.252 fail closed) and resync at
                    # the next line rather than cascading the error.
                    gaps.append((
                        lineno,
                        "unterminated %s literal" % (
                            "interpreted-string" if ch == '"' else "rune"),
                    ))
                    j = n
                seg = line[i:j]
                code_buf.append(seg)
                bare_buf.append(" " * len(seg))
                i = j
                continue

            code_buf.append(ch)
            bare_buf.append(ch)
            i += 1

        code_out.append("".join(code_buf))
        bare_out.append("".join(bare_buf))

    if mode in _GO_LINE_CROSSING:
        gaps.append((
            max(lineno, 1),
            "unterminated %s at end of file" % (
                "/* block comment" if mode == "block" else "` raw string"),
        ))
    return code_out, bare_out, gaps


def _go_lexical(path):
    """(raw_lines, code_lines, bare_lines, lex_gaps), line numbering preserved.

    code_lines : comments blanked, interpreted-string/rune literals kept,
                 raw-string content blanked  (route extraction)
    bare_lines : comments AND every literal blanked  (return/decl scans)
    lex_gaps   : constructs that could not be lexed to a close — the caller
                 turns each into a refusal, never a silent pass.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    raw = text.splitlines()
    code, bare, gaps = _go_lex(text)
    return raw, code, bare, gaps


def _closure_spans(text):
    """Character spans of every `func(...) ... { ... }` literal body.

    A `return` inside one belongs to the CLOSURE, not to the enclosing
    function, so it can never prove the enclosing function's return value.

    A `func(` that is a TYPE rather than a LITERAL owns no body brace, and
    round 11 replaced the `text.find("{", j)` that silently borrowed somebody
    else's with RULE S + RULE D — see `_signature_end` / `_body_brace` for the
    eleven measured shapes and why neither rule subsumes the other.
    """
    sig_end = _signature_end(text)
    spans = []
    for m in FUNC_LIT.finditer(text):
        # RULE S — inside this block's own signature: a receiver clause or a
        # func TYPE in a parameter, result or type-parameter position.
        if sig_end != -1 and m.start() < sig_end:
            continue
        depth, j = 0, m.end() - 1
        while j < len(text):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        # ROUND 9 (IMPORTANT-1): a METHOD declaration, not a closure literal.
        # Its body's returns are the enclosing function's own and must count.
        # HONEST LABEL (§11.4.115(F), round 11): RULE S now skips every method
        # receiver in a block that opens with a declaration, so this check is
        # reachable only in the file PREAMBLE block or when `_signature_end`
        # returned -1. Measured 2026-08-27 — see the harness's
        # `r11-method-after-recv-*` probes for its live-vs-dead status; it is
        # kept because it is the fallback RULE S deliberately does not cover.
        if _METHOD_AFTER_RECV.match(text, j + 1):
            continue
        # RULE D — is the next `{` actually OURS?
        k = _body_brace(text, j + 1)
        if k == -1:
            continue
        d, e = 0, k
        while e < len(text):
            if text[e] == "{":
                d += 1
            elif text[e] == "}":
                d -= 1
                if d == 0:
                    break
            e += 1
        spans.append((k, e))
    return spans


def _function_level_returns(bare_block):
    """Return statements at the function's OWN scope.

    Comments and string literals are already blanked by the caller, and
    returns inside closure literals are excluded. Accepting either would let a
    comment such as `// TODO: return WithAuth(mux)` prove authentication —
    a false attribution of SAFETY (§11.4.201(7)(a)).
    """
    text = "\n".join(bare_block)
    spans = _closure_spans(text)
    out = []
    for m in re.finditer(r"\breturn\b", text):
        pos = m.start()
        if any(a <= pos <= b for a, b in spans):
            continue
        eol = text.find("\n", pos)
        out.append(text[pos: eol if eol != -1 else len(text)])
    return out


# --------------------------------------------------------------- fastapi ---
def _depends_call_has_marker(node, markers):
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
    if name != "Depends":
        return False
    for a in node.args:
        an = a.attr if isinstance(a, ast.Attribute) else getattr(a, "id", None)
        if an in markers:
            return True
    return False


def _default_is_guard(node, markers, guard_aliases):
    """True for `Depends(marker)` OR a Name bound to one (MINOR-1)."""
    if _depends_call_has_marker(node, markers):
        return True
    return isinstance(node, ast.Name) and node.id in guard_aliases


def _kw_dependencies_have_marker(keywords, markers, guard_aliases):
    for kw in keywords or []:
        if kw.arg == "dependencies" and isinstance(kw.value, (ast.List, ast.Tuple)):
            for el in kw.value.elts:
                if _default_is_guard(el, markers, guard_aliases):
                    return True
    return False


def extract_fastapi(root, svc, markers):
    files = _walk_files(root, svc, ".py")
    trees, router_prefix, router_authed = {}, {}, {}
    imports, mount, guard_aliases = {}, {}, {}
    assign_count, marker_bind, top_bind = {}, {}, {}
    unmodelled = []

    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"ERROR: cannot parse {path}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        trees[path] = tree
        mod = os.path.splitext(os.path.basename(path))[0]
        imports.setdefault(mod, {})
        guard_aliases.setdefault(mod, set())
        assign_count.setdefault(mod, {})
        marker_bind.setdefault(mod, {})
        # A guard alias is trustworthy only as a single MODULE-LEVEL binding.
        top_bind[mod] = {
            t.id for n in tree.body if isinstance(n, ast.Assign)
            and _depends_call_has_marker(n.value, markers)
            for t in n.targets if isinstance(t, ast.Name)
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                src = node.module.split(".")[-1]
                for al in node.names:
                    imports[mod][al.asname or al.name] = (src, al.name)
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        assign_count[mod][tgt.id] = assign_count[mod].get(tgt.id, 0) + 1
                        if _depends_call_has_marker(node.value, markers):
                            marker_bind[mod][tgt.id] = node.lineno

    # MINOR-A: a conditional or re-assigned alias may bind a DIFFERENT guard at
    # runtime, so trusting it would be a fail-OPEN read. Qualify only a single
    # module-level binding; anything else fails closed with an explicit finding.
    for mod, binds in marker_bind.items():
        for name in binds:
            if name in top_bind.get(mod, set()) and assign_count[mod].get(name, 0) == 1:
                guard_aliases[mod].add(name)
            else:
                unmodelled.append(_unmod(
                    svc["id"], f"{mod}.py:{binds[name]}",
                    f"guard alias '{name}' is not a single module-level binding",
                    "assigned more than once and/or bound inside a conditional, "
                    "so which dependency it carries at runtime is not statically "
                    "decidable"))

    # KNOWN LIMIT, RECORDED WHERE ITS SYMPTOM APPEARS (round-7 NIT-3).
    # Every one of these maps is keyed on the module BASENAME, so two modules
    # with the same basename in different packages (`a/util.py`, `b/util.py`)
    # COLLIDE into one entry. Measured 2026-08-26: the collision is FAIL-CLOSED
    # — the merged entry trips the "not a single module-level binding" rule
    # above and REFUSES with a finding, so no credit crosses a package
    # boundary. That is incidental rather than designed, and it means a
    # perfectly correct alias can be refused because an unrelated package has
    # a same-named module. This note lived only in the round-6 evidence file,
    # which is not where a reader hitting that refusal will look; it is
    # restated here, beside the rule that produces it.
    #
    # Resolve guard aliases imported across modules within the service.
    for mod, imp in imports.items():
        for local, (src, orig) in imp.items():
            if orig in guard_aliases.get(src, set()):
                guard_aliases[mod].add(local)

    for path, tree in trees.items():
        mod = os.path.splitext(os.path.basename(path))[0]
        ga = guard_aliases[mod]
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fnn = node.value.func
                cname = fnn.attr if isinstance(fnn, ast.Attribute) else getattr(fnn, "id", None)
                if cname in ("APIRouter", "FastAPI"):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            pref = ""
                            for kw in node.value.keywords or []:
                                if kw.arg == "prefix":
                                    pref = _const_str(kw.value) or ""
                            # ROUND 6 — a router bound MORE THAN ONCE in a
                            # module is refused, not last-wins. These are
                            # plain dicts keyed on the NAME, so a later
                            # `router = APIRouter(dependencies=[Depends(m)])`
                            # OVERWROTE the entry for an earlier bare
                            # `router = APIRouter()` and back-credited every
                            # route registered on it. Measured pre-fix: a POST
                            # on the unguarded router came back auth_wired=true
                            # with resolution "router-level
                            # dependencies=[Depends(marker)]", findings 0,
                            # exit 0 — a false attribution of SAFETY, which
                            # this engine treats as worse than a missed route.
                            # This is the ROUTER analogue of the guard-alias
                            # rule that already refuses a re-assigned alias;
                            # the same fail-closed treatment now applies here.
                            if (mod, tgt.id) in router_prefix:
                                unmodelled.append(_unmod(
                                    svc["id"],
                                    f"{os.path.relpath(path, root)}:{node.lineno}",
                                    f"router '{tgt.id}' is bound more than once",
                                    "which router object a decorator on this "
                                    "name refers to is not statically decidable, "
                                    "so its prefix and its router-level "
                                    "dependencies cannot be attributed to any "
                                    "particular route"))
                            router_prefix[(mod, tgt.id)] = pref
                            router_authed[(mod, tgt.id)] = _kw_dependencies_have_marker(
                                node.value.keywords, markers, ga
                            )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "include_router"
                and node.args
            ):
                aname = getattr(node.args[0], "id", None)
                pref = ""
                for kw in node.keywords or []:
                    if kw.arg == "prefix":
                        pref = _const_str(kw.value) or ""
                if aname:
                    mount[aname] = pref
            # IMPORTANT-1: registration idioms this engine does not model.
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in FASTAPI_UNMODELLED_CALLS
            ):
                unmodelled.append(
                    _unmod(
                        svc["id"],
                        f"{os.path.relpath(path, root)}:{node.lineno}",
                        f".{node.func.attr}(...)",
                        "programmatic route registration is not parsed by the "
                        "decorator model",
                    )
                )

    # ROUND 6 — the fastapi silent-drop class, closed at the primitive.
    #
    # The decorator loop below reaches a route only when it is (a) a decorator
    # (b) in a FunctionDef/AsyncFunctionDef decorator_list (c) written as
    # `<name>.<verb>(...)`. Round 6 demonstrated FOUR registrations that are
    # real in the INSTALLED FastAPI and satisfy none of those, each reproduced
    # against the shipped engine as an exit-0 PASS with the mutating route gone:
    #
    #   router.post("/wipe")(wipe)     — never enters any decorator_list
    #   @router.post("/wipe") class X  — decorator_list of a ClassDef
    #   reg = router.post; @reg("/p")  — decorator func is a bare Name
    #   @router.route("/p", methods=…) — a verb this model did not know
    #
    # The last is handled by FASTAPI_UNMODELLED_DECOS. The first three share
    # one shape: the ROUTER's registration attribute is reached somewhere the
    # decorator model does not look. So the rule is written on the ATTRIBUTE,
    # not on the call shape — any `<router>.<verb>` that is not the func of a
    # modelled decorator is an unmodelled registration and is REFUSED.
    #
    # KEYED ON THE OWNER, DELIBERATELY (§11.4.201(1)). The obvious form of this
    # rule — "any Call whose func.attr is an HTTP verb outside decorator
    # position" — cannot ship: `.get` is an HTTP verb AND the most common
    # method name in Python, so that rule fires on `d.get(k)`,
    # `os.environ.get(k)`, `requests.post(...)` and every HTTP-client call in
    # the tree. Requiring the owner to be a router THIS module declared is what
    # separates a registration from a dictionary lookup. Measured on the real
    # policy roots: zero occurrences, so this rule changes no live verdict —
    # it closes tomorrow's drift, which is the whole job.
    # ROUND 7 (IMPORTANT-3) — the rule's owner test was SAME-MODULE ONLY.
    #
    # `(mod, name) in router_prefix` asks "did THIS module declare a router
    # called `name`?", so the whole rule was one `import` away from being
    # bypassed: `from .routers import router` followed by
    # `router.post("/wipe")(wipe)` in the IMPORTING module resolved to no
    # router, minted no refusal, and the mutating route VANISHED — measured
    # 2026-08-26 as findings 0, exit 0, the route absent from the inventory,
    # i.e. exactly the R6-5 immediate-call defect resurrected through a
    # one-line import. The classdef and bound-alias variants slip identically,
    # because all three are gated on this same test.
    #
    # The engine ALREADY resolves imports for guard aliases and for
    # `include_router` mounts, so same-module keying here was an omission
    # rather than a limitation. The resolution is transitive (bounded by a
    # seen-set) so a re-export chain cannot re-open the same door, and it
    # PRESERVES the owner qualification that makes the rule shippable at all
    # (§11.4.201(1)): the name must still resolve to a router some module in
    # this service DECLARED, so `d.get(k)` and `requests.post(...)` stay
    # untouched. The real tree imports routers by name four times, with zero
    # out-of-decorator uses, so this changes no live verdict — it closes the
    # bypass, which is the whole job.
    def _router_key(mod, name, _seen=None):
        seen = _seen if _seen is not None else set()
        if (mod, name) in router_prefix:
            return (mod, name)
        if (mod, name) in seen:
            return None            # import cycle — refuse to loop
        seen.add((mod, name))
        nxt = imports.get(mod, {}).get(name)
        return _router_key(nxt[0], nxt[1], seen) if nxt else None

    _VERB_ATTRS = set(HTTP_METHODS) | set(FASTAPI_UNMODELLED_DECOS)
    for path, tree in trees.items():
        mod = os.path.splitext(os.path.basename(path))[0]
        modelled = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        modelled.add(id(dec.func))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in _VERB_ATTRS
                and isinstance(node.value, ast.Name)
                and _router_key(mod, node.value.id) is not None
                and id(node) not in modelled
            ):
                unmodelled.append(_unmod(
                    svc["id"],
                    f"{os.path.relpath(path, root)}:{node.lineno}",
                    f"{node.value.id}.{node.attr} outside a modelled decorator",
                    "a route registration reached through a declared router but "
                    "not through a `@router.verb(\"/literal\")` decorator on a "
                    "function — an immediate call, a class decorator or a "
                    "bound-method alias — which this model cannot resolve to a "
                    "route or to its auth wiring"))

    routes = []
    for path, tree in trees.items():
        mod = os.path.splitext(os.path.basename(path))[0]
        ga = guard_aliases[mod]
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                meth = dec.func.attr
                where = f"{os.path.relpath(path, root)}:{node.lineno}"
                if meth in FASTAPI_UNMODELLED_DECOS:
                    # Round-6 NIT: this printed "websocket routes are not
                    # modelled" for `api_route` and `route` too — the right
                    # verdict under a wrong reason, which is what sends a
                    # reader looking for a websocket that is not there.
                    unmodelled.append(
                        _unmod(svc["id"], where, f"@....{meth}(...)",
                               _DECO_REFUSAL_REASON[meth])
                    )
                    continue
                if meth not in HTTP_METHODS:
                    continue
                owner = getattr(dec.func.value, "id", None)
                if owner is None:
                    # REFUSE, never DROP (round-5 mirror sweep). `dec.func.value`
                    # is not a Name for `@<expr>.<attr>.post("/p")`, and the
                    # previous revision simply `continue`d — a literal-path,
                    # possibly mutating route vanished with no finding, the same
                    # silent-drop class as the gin compound line.
                    unmodelled.append(_unmod(
                        svc["id"], where, f"@<expr>.{meth}(...)",
                        "the router is a dotted or computed expression rather "
                        "than a simple name, so its prefix and its router-level "
                        "dependencies cannot be resolved statically"))
                    continue
                raw = _const_str(dec.args[0]) if dec.args else None
                if raw is None:
                    unmodelled.append(
                        _unmod(
                            svc["id"], where, f"@{owner}.{meth}(<non-literal>)",
                            "the path is not a string literal, so the route "
                            "cannot be resolved statically",
                        )
                    )
                    continue

                local = router_prefix.get((mod, owner), "")
                mnt = ""
                for alias, pref in mount.items():
                    src = imports.get(mod, {}).get(alias) or next(
                        (v for m2, im in imports.items() for k, v in im.items() if k == alias),
                        None,
                    )
                    if src and src[0] == mod and src[1] == owner:
                        mnt = pref
                        break

                why, authed = [], False
                if router_authed.get((mod, owner)):
                    authed = True
                    why.append("router-level dependencies=[Depends(marker)]")
                if _kw_dependencies_have_marker(dec.keywords, markers, ga):
                    authed = True
                    why.append("decorator dependencies=[Depends(marker)]")
                a = node.args
                positional = (a.posonlyargs + a.args)[-len(a.defaults):] if a.defaults else []
                for arg, dflt in zip(positional, a.defaults, strict=False):
                    if _default_is_guard(dflt, markers, ga):
                        authed = True
                        why.append(f"param '{arg.arg}' = Depends(marker)")
                for arg, dflt in zip(a.kwonlyargs, a.kw_defaults or [], strict=False):
                    if dflt is not None and _default_is_guard(dflt, markers, ga):
                        authed = True
                        why.append(f"kwarg '{arg.arg}' = Depends(marker)")

                routes.append(
                    Route(
                        svc["id"], meth.upper(), _norm(f"{mnt}/{local}/{raw}"), authed, where,
                        "; ".join(why) if why
                        else "no Depends(marker) on handler, decorator or router",
                    )
                )
    return routes, unmodelled


# ------------------------------------------------------------------ gin ----
# The owner must be a BARE identifier: `(\w+)\.` alone captures only the LAST
# name of a dotted chain, so `s.router.POST("/p", h)` resolved to owner "router"
# and inherited the `.Use(marker)` installed on an unrelated LOCAL `router`
# engine — a FALSE ATTRIBUTION OF SAFETY (reproduced round 5: both routes
# auth_wired=true, findings 0, gate PASS on an unauthenticated mutating route).
# The lookbehind makes the dotted form stop matching here; GIN_DOTTED_OWNER
# below then REFUSES it explicitly, so it is refused rather than dropped.
#
# MEASURED EQUIVALENCE, RECORDED SO NOBODY DELETES IT AS DEAD (round 7).
# Removing THIS lookbehind alone leaves all 115 fixtures green, because
# GIN_DOTTED_OWNER refuses and `continue`s before GIN_ROUTE is ever consulted
# — so on its own it is unreachable defence. Removing BOTH kills
# `gin-dotted-owner-false-safe`. The pair is load-bearing as a unit and each
# half is a genuine belt for the other's braces; the same relationship round 6
# recorded for MUX_ROUTE, whose gin twin nobody had measured until now. Do not
# read the surviving single mutation as evidence this lookbehind is redundant.
GIN_ROUTE = re.compile(r'(?<![\w.])(\w+)\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\(\s*"([^"]*)"')
# A receiver reached through a field/selector (`s.router.POST(`). The leading
# class is deliberately narrow so a dotted HANDLER ARGUMENT (`api.XHandler`,
# `s.api.XHandler`) — which carries no verb call — can never match it.
# ROUND 7 (NIT-2) — the leading class `[\w)\]]` was an ENUMERATED ALLOWLIST of
# "characters a Go expression can end with", and it was incomplete:
# `Wrapper{}.engine.POST("/p", h)` ends the receiver with `}`, so this check
# missed it and the line fell through to the NON-LITERAL-PATH refusal — the
# right verdict under a label that is untrue of that line (its path IS a
# literal), which is the F8 class round 6 fixed once and this is its second
# instance. The load-bearing condition was never the leading character: it is
# that the receiver identifier is REACHED THROUGH A SELECTOR, i.e. preceded by
# a dot. A dotted HANDLER ARGUMENT still cannot match, because the verb+`(`
# pair — not the leading class — is what excludes it.
GIN_DOTTED_OWNER = re.compile(
    r'\.\w+\.(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(')
GIN_VERB = re.compile(r'\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(')
GIN_GROUP = re.compile(r'(\w+)\s*:?=\s*(\w+)\.Group\(\s*"([^"]*)"')
# ROUND 7 (IMPORTANT-1) — EVERY group declaration, modelled or not.
# `groups` was a dict keyed on the NAME and scoped to the FILE, so a name the
# modelled pattern could not see was invisibly RE-BOUND and every later
# registration on it inherited the previous binding's prefix AND its coverage.
# Measured pre-fix on `g := r.Group("/admin")` in one function and
# `g := s.pub.Group("/public")` in another (the dotted parent is correctly
# invisible to GIN_GROUP above): `POST /admin/wipe auth_wired=true`,
# findings 0, exit 0 — a wrong path AND a false attribution of safety on an
# unauthenticated mutating route. This is the A2/A3 per-declaration-SITE rule
# (engines, FastAPI routers) applied to the construct one door over
# (§11.4.250): a declaration site is counted whether or not its parent chain
# and prefix are resolvable, so an unresolvable one can no longer hide.
GIN_GROUP_DECL = re.compile(r'(?<![\w.])(\w+)\s*:?=\s*[^;]*?\.Group\s*\(')
# ROUND 6 — the same lookbehind, on the CREDIT side. Round 5 put `(?<![\w.])`
# on GIN_ROUTE because that was the leak that was reported, and left GIN_USE
# without one — so `s.router.Use(middleware.AuthMW())` still credited an
# unrelated LOCAL `router` engine, and a mutating route with no middleware
# came back auth_wired=true, findings 0, gate PASS. Fixing the door and not
# the primitive is what round 6's review called out: the rule "a dotted
# receiver must not alias a local name" has to hold for EVERY credit-bearing
# construct, not only the one that was reported. Dropping the credit is the
# fail-closed direction — the route simply stays uncovered.
GIN_USE = re.compile(r"(?<![\w.])(\w+)\.Use\(\s*([\w.]+)")
# A selector split across lines: `r.` at end of line, `POST("/p", h)` on the
# next. Go inserts no semicolon after a trailing `.`, so this is legal and
# gofmt-stable — the "a verb+`(` pair cannot span a newline" assumption the
# skeleton FILTER used to rest on is simply not true. Refused, not dropped.
# ROUND 11: spelled by the shared `_selector_head` factory so the gin and gomux
# halves of ONE primitive can no longer drift apart (§11.4.250) — round 6 fixed
# this for gin ONLY, and the gomux twin was still a silent DROP five rounds
# later.
GIN_VERB_HEAD = _selector_head("GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS")
GIN_WS_SELECTOR = _ws_selector("GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS")
# `.Group(` carries the SAME primitive and a WORSE consequence than the verbs.
# Measured 2026-08-27 on `g := r.` + newline + `Group("/admin")` (gofmt-STABLE)
# and on `g := r.  Group("/admin")`: `GIN_GROUP_DECL` needs `\.Group\s*\(` on one
# line, and the enclosing `if ".Group(" in bln` is a literal substring test, so
# BOTH the declaration and its refusal were missed — `g.POST("/wipe", h)` then
# resolved as `POST /wipe` instead of `POST /admin/wipe`, and an exemption
# written for a genuinely-public `POST /wipe` MATCHED it: exit 0, zero findings,
# over an unauthenticated mutating `/admin/wipe`. That is a PASS-BLUFF, not the
# loud fail-closed drop the verbs degrade to, and round 10 did not enumerate it.
GIN_GROUP_HEAD = _selector_head("Group")
GIN_GROUP_WS_SELECTOR = _ws_selector("Group")
GIN_ENGINE = re.compile(r"(\w+)\s*:?=\s*gin\.(?:New|Default)\(\)")


def extract_gin(root, svc, markers):
    """Resolve gin auth per OWNER, honouring registration order (IMPORTANT-1).

    The previous revision treated any of {r, router, engine} as authenticated
    once ANY of them carried `.Use(marker)` — the same blanket-attribution
    defect the gomux resolver had. Coverage is now resolved for the exact
    owner, inherited down the `Group(...)` chain, and gated on gin's real
    registration-order semantics: a route registered BEFORE `.Use` on its
    owner does not receive that middleware, and a group only inherits what
    its parent carried at Group() time.

    Honest scope: a file declaring more than one engine fails closed, because
    cross-engine handler sharing is not modelled.
    """
    routes, unmodelled = [], []
    for p in _walk_files(root, svc, ".go", skip_test=True):
        _raw, code, bare, lex_gaps = _go_lexical(p)
        rel = os.path.relpath(p, root)
        for gap_line, gap_what in lex_gaps:
            unmodelled.append(_unmod(
                svc["id"], f"{rel}:{gap_line}", gap_what,
                "the file cannot be lexed to a close, so every comment/string "
                "boundary after this point is unknown and no verdict about "
                "the file is trustworthy",
            ))

        # ROUND 6 — `engines` was a dict keyed on the NAME, so two functions
        # each declaring `r := gin.New()` collapsed into ONE entry and the
        # multi-engine refusal below never fired. `uses` is FILE-scoped, so one
        # function's `r.Use(auth)` then credited the other function's route.
        # Measured pre-fix: both routes auth_wired=true, findings 0, exit 0.
        # Keyed on DECLARATION SITES now: two sites means two engines, whatever
        # they are called, which is exactly what the refusal message already
        # claimed this model cannot resolve.
        # ROUND 7 (IMPORTANT-1) — `group_sites` and `decl_sites` replace the
        # name-keyed `groups` dict. A NAME that is bound more than once, or
        # bound by a declaration this model cannot resolve, no longer silently
        # last-wins: it is REFUSED and its credit is DROPPED (a route on it
        # resolves to uncovered), which is the fail-closed direction. `uses` is
        # keyed on owner names too, so making every group NAME provably
        # unambiguous is what keeps a `.Use` credit from crossing a re-binding
        # it cannot see — primitive (2), enforced rather than restated.
        engines, uses = [], []
        group_sites, decl_sites, unresolvable_groups = {}, {}, set()
        # A construct counts only when its CODE SKELETON survives in `bare`.
        # `code` keeps interpreted-string literals (route paths are read out of
        # them), so scanning it for a CALL lets a literal carry the call: a log
        # line reading "hint: r.Use(middleware.AuthMW())" would otherwise mark
        # every route on `r` as covered — a false attribution of SAFETY, the
        # same carrier class as a comment proving a wrap (§11.4.201(7)(a)).
        # Reproduced 2026-08-26: that one log line flipped the gate to PASS
        # while its innocuous-content control correctly FAILED.
        for i, (ln, bln) in enumerate(zip(code, bare), 1):
            for var in GIN_ENGINE.findall(bln):
                engines.append((var, i))
                decl_sites.setdefault(var, []).append((i, "engine"))
            # Gated on the SKELETON (`bln`) so a literal that merely MENTIONS
            # `.Group(` can never mint a declaration or a refusal; the prefix
            # itself is then read from `ln`, which keeps literals.
            # ROUND 11 (BLOCKING-1 audit) — the split-selector primitive on
            # `.Group(`. `GIN_GROUP_DECL` needs `\.Group\s*\(` on ONE line and
            # the substring test below is literal, so a split or
            # whitespace-separated `.Group(` missed BOTH the declaration and
            # its refusal, and every route on that group silently lost its
            # prefix. Measured: `POST /admin/wipe` reported as `POST /wipe`,
            # matched by an exemption written for a genuinely-public
            # `POST /wipe` — exit 0, zero findings, over an unauthenticated
            # mutating route. Refused, and the name is poisoned so no later
            # registration can inherit a prefix that was never resolved.
            if (GIN_GROUP_WS_SELECTOR.search(bln)
                    or _selector_is_split(bare, i - 1, GIN_GROUP_HEAD)):
                for _v in GO_ASSIGN_TARGET.findall(bln):
                    unresolvable_groups.add(_v)
                unmodelled.append(_unmod(
                    svc["id"], f"{rel}:{i}", ln.strip()[:70],
                    "router-group declaration whose parent is separated from "
                    ".Group( by whitespace or a newline; the group's path "
                    "prefix and the middleware it inherits are not resolvable, "
                    "and every route registered on it would silently resolve "
                    "at an UNPREFIXED path that a stale exemption can match"))
                continue
            if ".Group(" in bln:
                modelled_here = {v for v, _p, _pf in GIN_GROUP.findall(ln)}
                for var in GIN_GROUP_DECL.findall(bln):
                    decl_sites.setdefault(var, []).append((i, "group"))
                    if var in modelled_here:
                        continue
                    unresolvable_groups.add(var)
                    unmodelled.append(_unmod(
                        svc["id"], f"{rel}:{i}", ln.strip()[:70],
                        f"group '{var}' is declared from a parent reached "
                        f"through a field or selector, or with a prefix that "
                        f"is not a string literal on this line; neither its "
                        f"path prefix nor the middleware it inherits is "
                        f"resolvable, and letting the name keep an earlier "
                        f"binding would attribute that binding's prefix AND "
                        f"its coverage to a different group"))
                for var, parent, pref in GIN_GROUP.findall(ln):
                    group_sites.setdefault(var, []).append((parent, _norm(pref), i))
            for owner, mw in GIN_USE.findall(bln):
                if mw.split(".")[-1] in markers:
                    uses.append((owner, i))

        # A name bound more than once is not statically decidable, exactly as
        # for a re-bound FastAPI router (A3). Scoped to names carrying at least
        # one GROUP site: a doubly-declared ENGINE is already refused below, and
        # reporting it twice would be noise, not rigour.
        for var in sorted(decl_sites):
            sites = decl_sites[var]
            if len(sites) < 2 or not any(k == "group" for _ln, k in sites):
                continue
            unresolvable_groups.add(var)
            unmodelled.append(_unmod(
                svc["id"], f"{rel}:{min(ln for ln, _k in sites)}",
                f"'{var}' is bound {len(sites)} times in this file "
                f"(line(s) {', '.join(str(ln) for ln, _k in sites)})",
                "which router group a registration on this name refers to is "
                "not statically decidable, so neither its prefix nor the "
                "middleware it inherits can be attributed to any particular "
                "route"))

        # The credit filter is deliberately SELF-STANDING rather than relying
        # on the refusal loop above having run: `len(sites) == 1` is what makes
        # `sites[0]` mean "the only site", so no reader can mistake it for a
        # first-wins RESOLUTION strategy (last-wins is what the pre-fix engine
        # did, and it is exactly what let the earlier route inherit the later
        # group). The two rules are independent — the refusal explains, the
        # filter decides.
        # ROUND 9 — that independence is now MEASURED, not asserted, and the
        # second half of the old sentence ("each is pinned separately") was
        # simply UNTRUE: dropping `len(sites) == 1` survived all 115 round-8
        # fixtures. It is NOT redundant with `unresolvable_groups`. `GIN_GROUP`
        # carries NO leading lookbehind while `GIN_GROUP_DECL` carries
        # `(?<![\w.])`, so a DOTTED assignment target
        # (`s.g = r.Group("/safe")`) lands in `group_sites` and never in
        # `decl_sites` — the "'g' is bound N times" refusal above is keyed on
        # `decl_sites`, so it never fires and `unresolvable_groups` never
        # learns the name. GIN_GROUP is therefore NOT a subset of
        # GIN_GROUP_DECL and the two do not move in lockstep. Measured with the
        # filter removed: the route resolves as `/safe/wipe` (FIRST-wins across
        # a re-binding) instead of `/wipe`, an operator exemption written for
        # the auth'd `/safe` group MATCHES it, and the gate goes green — exit 0,
        # zero findings, over an unauthenticated mutating LAN route, while the
        # pristine engine reports both the route AND the stale exemption.
        # Pinned by `gin-group-dotted-target-first-wins` (§11.4.115(F)).
        groups = {
            var: sites[0]
            for var, sites in group_sites.items()
            if len(sites) == 1 and var not in unresolvable_groups
        }

        if len(engines) > 1:
            _names = sorted({v for v, _ln in engines})
            unmodelled.append(_unmod(
                svc["id"], f"{rel}:{min(ln for _v, ln in engines)}",
                f"{len(engines)} gin engine declarations in one file "
                f"({', '.join(_names)})",
                "cross-engine handler/middleware sharing is not modelled"))

        def prefix_of(owner, seen=None, groups=groups):
            seen = seen or set()
            if owner in seen or owner not in groups:
                return ""
            seen.add(owner)
            parent, pref, _ln = groups[owner]
            return _norm(prefix_of(parent, seen) + "/" + pref)

        def covered(owner, at_line, seen=None, groups=groups, uses=uses):
            seen = seen or set()
            if owner in seen:
                return False
            seen.add(owner)
            if any(o == owner and uln <= at_line for o, uln in uses):
                return True
            if owner in groups:
                parent, _pref, created = groups[owner]
                return covered(parent, created, seen)
            return False

        for i, (ln, bln) in enumerate(zip(code, bare), 1):
            # Detected on `bare` too: a doc string that merely MENTIONS `.Any(`
            # must not mint a refusal either (§11.4.201(1) — a gate that cries
            # wolf gets bypassed, which is how the whole class comes back).
            for verb in GIN_UNMODELLED:
                if re.search(r"\w\." + verb + r"\s*\(", bln):
                    unmodelled.append(_unmod(
                        svc["id"], f"{rel}:{i}", f".{verb}(...)",
                        "this gin registration form is not modelled"))
            # ROUND 6 (F8): the dotted-receiver refusal used to sit BELOW the
            # non-literal-path rule, so a `}`-preceded dotted registration was
            # refused under "path is not a string literal on the same line" —
            # untrue of that line, a right verdict wearing a misleading label,
            # and a reader sent to fix the wrong thing. Checked FIRST now.
            if GIN_DOTTED_OWNER.search(bln):
                unmodelled.append(_unmod(
                    svc["id"], f"{rel}:{i}", ln.strip()[:70],
                    "the route is registered on a receiver reached through a "
                    "field or selector (`x.y.VERB(...)`), whose middleware "
                    "chain this resolver cannot follow; attributing it to a "
                    "same-named local engine or group would falsely mark it "
                    "authenticated"))
                continue
            # ROUND 6 (F4): `r.` at end of line with `POST("/p", h)` on the
            # next is legal, gofmt-stable Go — Go inserts no semicolon after a
            # trailing `.` — and the skeleton FILTER dropped it silently while
            # justifying itself with "the pair cannot span a newline". Read the
            # NEXT line off `bare`, so a trailing `.` inside a comment or a
            # literal can never mint this refusal.
            if _selector_is_split(bare, i - 1, GIN_VERB_HEAD):
                unmodelled.append(_unmod(
                    svc["id"], f"{rel}:{i}", ln.strip()[:70],
                    "HTTP-verb registration whose receiver and verb are split "
                    "across lines by a trailing selector dot; the owner and "
                    "its middleware chain are not resolvable from either line "
                    "alone"))
                continue
            # ROUND 11 (IMPORTANT-1) — the SAME-LINE half of the same
            # primitive. Checked HERE, above the non-literal-path rule, and
            # under its OWN label: `r.  POST("/wipe", h)` has a perfectly good
            # string-literal path, so refusing it as "path is not a string
            # literal" would be a right verdict wearing a false label and would
            # send the reader to fix the wrong thing — the F8 class, which this
            # engine has now met three times.
            if GIN_WS_SELECTOR.search(bln):
                unmodelled.append(_unmod(
                    svc["id"], f"{rel}:{i}", ln.strip()[:70],
                    "HTTP-verb registration whose receiver is separated from "
                    "the verb by whitespace (`r . POST(`, `r.  POST(`); the "
                    "owner is not resolvable by this model, and dropping the "
                    "line would hide the route entirely"))
                continue
            if GIN_VERB.search(bln) and not GIN_ROUTE.search(ln):
                unmodelled.append(_unmod(
                    svc["id"], f"{rel}:{i}", ln.strip()[:70],
                    "HTTP-verb registration whose path is not a string literal "
                    "on the same line (multi-line or computed)"))
            if not GIN_VERB.search(bln):
                continue
            # REFUSE (never DROP) a MULTI-STATEMENT line. Round-5 IMPORTANT.
            #
            # The previous revision skipped every route on a line that also
            # carried `.Group(`. On a normal two-line group declaration
            # GIN_VERB never matches the decl line, so that skip was only ever
            # REACHED on a compound line — where its one effect was to DROP a
            # fully-resolvable route:
            #     g := r.Group("/api/v1"); g.POST("/wipe", api.WipeHandler)
            # resolved to route_count=1 and the gate returned PASS, so an
            # unauthenticated mutating LAN route was INVISIBLE. The §11.4.201(6)
            # zero-routes FALSE-NULL net cannot fire, because the service still
            # resolves its other routes.
            #
            # Merely narrowing the skip would have traded a silent DROP for a
            # silent FALSE-SAFE: gin applies only middleware installed BEFORE a
            # route, this resolver's ordering model is LINE-granular, and on one
            # line `r.POST(...); r.Use(auth)` reads as covered when gin gives
            # that route no middleware at all — a door already open with no
            # `.Group(` involved. Refusing the whole line closes both, and is
            # what the guide already documents unmodelled forms to do.
            #
            # Read from `bare`, so a `;` inside a PATH LITERAL (legal — matrix
            # parameters) or inside a trailing `//` comment is blanked and can
            # never mint a refusal (§11.4.201(1): a gate that cries wolf gets
            # bypassed). Go's other `;` uses — `for a; b; c`, `if a; b`,
            # `switch a; b` — are multi-clause lines whose ordering this model
            # equally cannot resolve, so refusing them is correct, not collateral.
            #
            # THE BOUNDARY, OWNED (round 6). This rule is deliberately WIDER
            # than the defect that motivated it. It also fires on a
            # gofmt-stable line carrying exactly ONE registration whose `;`
            # lives inside an inline handler closure:
            #     r.POST("/p", func(c *gin.Context) { c.Status(200); c.Done() })
            # There is one registration there and its coverage IS
            # line-decidable, so the refusal is CONSERVATIVE rather than
            # necessary. It is kept because it is loud and fail-closed, and
            # because brace-balanced closure-body exclusion is a second parser
            # this engine would then have to validate and pin. What is NOT
            # acceptable is leaving the boundary undocumented: an unexplained
            # refusal on legal code is how a gate earns a reputation for crying
            # wolf, and a gate with that reputation gets bypassed. The
            # behaviour is pinned by `gin-semicolon-in-closure-body`, so
            # narrowing it later is a deliberate fixture change, not a drift.
            if ";" in bln or ".Group(" in bln:
                unmodelled.append(_unmod(
                    svc["id"], f"{rel}:{i}", ln.strip()[:70],
                    "HTTP-verb registration sharing a line with another "
                    "statement; gin middleware is order-dependent and this "
                    "resolver's ordering model is line-granular, so neither "
                    "the route's coverage nor a same-line .Group()/.Use() "
                    "ordering is decidable here"))
                continue
            for owner, meth, path in GIN_ROUTE.findall(ln):
                ok = covered(owner, i)
                routes.append(Route(
                    svc["id"], meth, _norm(prefix_of(owner) + "/" + path), ok,
                    f"{rel}:{i}",
                    f"owner '{owner}' carries .Use(marker) at or above this line"
                    if ok else
                    f"no .Use(marker) covers owner '{owner}' at this registration "
                    f"(gin applies only middleware installed BEFORE the route)"))
    return routes, unmodelled


# ---------------------------------------------------------------- gomux ----
# ROUND 6 — the same lookbehind, third extractor. Round 6's credit audit (not
# a report) found that MUX_ROUTE's bare-name capture also took only the LAST
# name of a chain, so `s.mux.HandleFunc("/api/v1/wipe", …)` resolved to owner
# "mux" and inherited the `return WithAuth(mux)` of an unrelated LOCAL mux.
# Measured pre-fix: auth_wired=true on the mutating route, findings 0, exit 0
# — the identical FALSE ATTRIBUTION OF SAFETY that round 5 fixed in gin and
# round 6 fixed in GIN_USE. MUX_DOTTED_OWNER then REFUSES the form explicitly,
# so it is refused rather than dropped.
MUX_ROUTE = re.compile(r'(?<![\w.])(\w+)\.(?:HandleFunc|Handle)\(\s*"([^"]*)"')
MUX_ANY = re.compile(r"(?<![\w.])(\w+)\.(?:HandleFunc|Handle)\s*\(")
# ROUND 7 (MINOR-1 / NIT-2) — the leading character class was an ENUMERATED
# ALLOWLIST of "things a Go expression can end with", and an allowlist is the
# same primitive defect as a bare-name capture: it is complete until the next
# spelling arrives. `Server{}.mux.HandleFunc("/p", h)` ends the receiver with
# `}`, which is not in `[\w)\]]`, so this refusal MISSED it while MUX_ANY's
# lookbehind made the bare-owner path miss it too — a SILENT DROP, measured
# 2026-08-26 as exit 0 / findings 0 with the mutating route absent from the
# inventory. The load-bearing condition was never the leading character: it is
# that the receiver identifier is itself REACHED THROUGH A SELECTOR, i.e. is
# preceded by a dot. Requiring that dot and nothing else removes the allowlist
# without widening the rule: a dotted HANDLER ARGUMENT (`d.Health.HandleHealth`)
# still cannot match, because the verb+`(` pair is what does the work.
MUX_DOTTED_OWNER = re.compile(
    r'\.\w+\.(?:HandleFunc|Handle)\s*\(')
# ROUND 7 (IMPORTANT-2) — the lookbehind, on the DECLARATION.
# Round 6 put `(?<![\w.])` on MUX_ROUTE and MUX_ANY and left MUX_DECL bare, so
# `s.mux = http.NewServeMux()` captured `mux` THROUGH the dot and declared a
# bare-name mux that does not exist. A genuinely separate local `mux` then
# registered a mutating route and `return WithAuth(s.mux)` credited it (the dot
# is a word boundary, so the return-scan's `\bmux\b` matched the field too).
# Measured pre-fix: `ANY /api/v1/wipe auth_wired=true`, findings 0, exit 0 —
# the same FALSE ATTRIBUTION OF SAFETY the round-5/6 lookbehinds closed one
# door over (§11.4.250). Dropping the declaration is the fail-closed direction:
# a dotted mux declaration registers no route, so nothing is lost, and any
# route on that receiver is refused by MUX_DOTTED_OWNER above.
MUX_DECL = re.compile(r"(?<![\w.])(\w+)\s*:?=\s*http\.NewServeMux\(\)")
# ROUND 9 (BLOCKING-1) — THE CATCH-ALL gomux never had.
# Round 7 fixed the `}` complit spelling by re-keying MUX_DOTTED_OWNER on "the
# receiver is reached through a selector", and recorded in the skip table that
# gin's advantage is a lookbehind-free catch-all `GIN_VERB` while "gomux had no
# such catch-all". That sentence was true and was left true: only the DOTTED
# spelling was widened, so a receiver that is neither a bare identifier nor a
# dotted identifier still matched NOTHING and the skeleton filter stepped over
# it with no finding. Measured 2026-08-26 on `newServeMux().HandleFunc("/wipe",
# h)` beside a healthy `mux.HandleFunc("/ok", h)`: exit 0, routes 1,
# findings 0, unmodelled 0 — `/wipe` ABSENT from the inventory entirely. The
# §11.4.201(6) BLIND net cannot see it either: that net fires when a FILE
# yields zero routes, and the sibling route kept the file non-empty, so a drop
# hides behind a healthy neighbour. `s.buildMux().HandleFunc(...)` and
# `muxes[0].HandleFunc(...)` dropped the same way.
#
# THE INVARIANT, stated so it cannot rot again: a `.HandleFunc(`/`.Handle(`
# CALL SITE this resolver cannot attribute to a mux owner must REFUSE, never
# skip (§11.4.252 fail-closed). MUX_CALL is the receiver-agnostic counter that
# makes "cannot attribute" decidable, exactly as GIN_VERB does for gin.
#
# WHY COUNTS AND NOT A BOOLEAN: a boolean "some registration is attributable"
# still drops the unattributable one on a line that holds BOTH
# (`mux.HandleFunc("/ok", h); newServeMux().HandleFunc("/wipe", h)` — legal Go).
# Comparing the TOTAL number of call sites against the number this model can
# name refuses the whole line the moment even one site is unnameable. MUX_ANY
# and MUX_DOTTED_OWNER are mutually exclusive per call site — MUX_ANY requires
# the identifier NOT be preceded by a dot, MUX_DOTTED_OWNER requires that it IS
# — so the two counts sum without double-counting.
#
# HONEST OVER-REFUSAL (§11.4.6, §11.4.201(1)): a plain CALL to a method named
# `Handle` on an unnameable receiver (`getHandler().Handle(w, r)`) is
# statically indistinguishable from a registration and is refused too. This is
# not a new class — the shipped MUX_DOTTED_OWNER already refuses the dotted
# twin `x.y.Handle(w, r)` on the same reasoning, and GIN_VERB over-refuses
# identically. A dotted handler ARGUMENT (`d.Health.HandleHealth`) is still
# untouched: the verb must be followed by `(` to count, and an argument is
# followed by `,` or `)`. Measured on the real tree: all 13 registrations under
# the gomux root are total=1 bare=1 dotted=0, so this changes no live verdict.
MUX_CALL = re.compile(r"\.(?:HandleFunc|Handle)\s*\(")
# ROUND 11 (BLOCKING-1) — THE GOMUX TWIN OF GIN'S ROUND-6 FIX.
# `MUX_CALL`, `MUX_ANY` and `MUX_DOTTED_OWNER` every one require dot+member on
# ONE line, so a selector split at a trailing dot matched NOTHING: not the
# naming regexes, not the catch-all counter, not the refusal. `_sites` and
# `_named` were both 0, `_sites > _named` was false, and the line fell through
# to `if not MUX_ANY.search(bln): continue` — the silent drop. Measured
# 2026-08-27 beside a healthy wrapped sibling: exit 0, 1 route resolved, zero
# findings, zero unmodelled, `/wipe` ABSENT from the inventory, while the
# one-line control correctly exited 1. Spelled by the SHARED factory so this
# and `GIN_VERB_HEAD` can never drift apart again (§11.4.250).
MUX_CALL_HEAD = _selector_head("HandleFunc|Handle")
MUX_WS_SELECTOR = _ws_selector("HandleFunc|Handle")
GO_ASSIGN = re.compile(r"^\s*(\w+)\s*:?=\s*(.+?)\s*$")


def _go_func_blocks(lines):
    """Split a Go file into top-level `func` blocks: [(offset, [lines])]."""
    blocks, cur, start = [], [], 0
    for i, ln in enumerate(lines):
        if ln.startswith("func "):
            if cur:
                blocks.append((start, cur))
            cur, start = [ln], i
        else:
            cur.append(ln)
    if cur:
        blocks.append((start, cur))
    return blocks


def _carriers(block, decls):
    """Vars that transitively carry each mux value (one fixpoint pass set).

    THE BOUNDARY, OWNED (round 7, MINOR-4 — the F6 treatment, second instance).
    This propagation is an OVER-APPROXIMATION, and over-approximating the
    CARRIER set is fail-OPEN, not fail-closed. It is a purely LEXICAL rule: any
    assignment whose right-hand side MENTIONS a carrier name adds its left-hand
    side to that mux's name set, with no model of what the right-hand side
    actually computes or returns. So::

        stats := describe(mux)      // returns *Stats, not an http.Handler
        return WithAuth(stats)      // credits `mux` — measured auth_wired=true

    the wrap is credited to `mux` even though nothing wrapping `mux` was ever
    returned. Earlier revisions recorded this construct as "lhs anchored bare
    -> fail-closed"; that is TRUE of the MISS direction and FALSE of this one,
    and the two were conflated. The miss direction genuinely is fail-closed —
    a carrier this pass fails to find only SHRINKS the name set, which can move
    a verdict toward UNWRAPPED and never toward WRAPPED.

    WHY IT IS KEPT. The alternative is a Go type/return-value model: a second
    parser with its own failure modes, its own fixtures and its own way of
    being wrong, standing between this gate and the one question it answers.
    The over-approximation is bounded by two rules that do hold — only
    FUNCTION-LEVEL returns count (§`_function_level_returns`) and both
    boundaries of the name match are anchored (`(?<![\\w.])name\\b`), so neither
    a closure's return nor a same-prefix or field-qualified name can carry a
    credit — and the residual is one function's own local chain.

    WHAT IS NOT ACCEPTABLE is leaving it unstated: an undocumented fail-OPEN
    path in a gate whose entire purpose is refusing false attributions of
    safety is the §11.4.6 mis-record this round is correcting. The behaviour is
    pinned by `gomux-carrier-over-approximates`, so narrowing it later is a
    deliberate fixture change rather than drift, and it is carried as an
    honest open gap (§11.4.118) rather than as a solved problem.
    """
    carry = {v: {v} for v in decls}
    changed = True
    while changed:
        changed = False
        for ln in block:
            m = GO_ASSIGN.match(ln)
            if not m:
                continue
            lhs, rhs = m.group(1), m.group(2)
            for names in carry.values():
                if lhs in names:
                    continue
                if any(re.search(r"\b" + re.escape(c) + r"\b", rhs) for c in names):
                    names.add(lhs)
                    changed = True
    return carry


def extract_gomux(root, svc, markers):
    """Resolve wrapping PER MUX VARIABLE, never per file (IMPORTANT-2).

    A second, bare `http.NewServeMux()` in the same file that carries a real
    `return WithAuth(mux)` must NOT inherit that wrap. Falsely attributing
    safety is categorically worse than failing to see a route, so an
    unresolvable wrap resolves to UNWRAPPED (fail closed).
    """
    routes, unmodelled = [], []
    for p in _walk_files(root, svc, ".go", skip_test=True):
        raw, code, bare, lex_gaps = _go_lexical(p)
        rel = os.path.relpath(p, root)
        for gap_line, gap_what in lex_gaps:
            unmodelled.append(_unmod(
                svc["id"], f"{rel}:{gap_line}", gap_what,
                "the file cannot be lexed to a close, so every comment/string "
                "boundary after this point is unknown and no verdict about "
                "the file is trustworthy",
            ))

        for offset, block in _go_func_blocks(code):
            bare_block = bare[offset:offset + len(block)]
            decls = {m for ln in bare_block for m in MUX_DECL.findall(ln)}
            carry = _carriers(bare_block, decls)
            # BLOCKING-1: comments and string literals are blanked, and returns
            # inside closure literals are excluded, so neither can prove a wrap.
            returns = _function_level_returns(bare_block)

            wrapped = {}
            for v in decls:
                names = carry.get(v, {v})
                hit = False
                for ln in returns:
                    for mk in markers:
                        for span in _call_arg_spans(ln, mk):
                            # ROUND 7 (IMPORTANT-2 / MINOR-2) — BOTH boundaries
                            # are load-bearing and BOTH are now pinned.
                            # Leading `(?<![\w.])`: without it `WithAuth(s.mux)`
                            # credits a bare local `mux`, because `.` is a word
                            # boundary (measured false-safe, exit 0).
                            # Trailing `\b`: without it `WithAuth(muxAdmin)`
                            # credits `mux` by prefix (round-6 mutation X1,
                            # which survived all 93 fixtures).
                            if any(re.search(r"(?<![\w.])" + re.escape(n) + r"\b", span)
                                   for n in names):
                                hit = True
                wrapped[v] = hit

            for j, ln in enumerate(block):
                lineno = offset + j + 1
                # Same skeleton-in-`bare` rule as the gin extractor: a string
                # literal may supply the PATH, never the registration call.
                bln = bare_block[j] if j < len(bare_block) else ""
                # Checked BEFORE the skeleton filter: the lookbehind above now
                # makes MUX_ANY miss the dotted form entirely, so without this
                # the refusal would become a DROP — trading one silent failure
                # for another, which is the whole mistake this round is about.
                # ROUND 11 (BLOCKING-1) — the split-selector refusal, FIRST.
                # It must precede both the dotted-owner rule and the
                # `_sites > _named` counter: on the split form line N is a bare
                # `open.` that no other rule matches at all, and on the
                # whitespace form the counter WOULD fire but under the label
                # "receiver is neither a bare identifier nor a dotted
                # selector" — untrue of `open.  HandleFunc(`, whose receiver is
                # a perfectly ordinary bare identifier. A right verdict under a
                # false label is the F8 class, so this carries its own.
                if (MUX_WS_SELECTOR.search(bln)
                        or _selector_is_split(bare, lineno - 1, MUX_CALL_HEAD)):
                    unmodelled.append(_unmod(
                        svc["id"], f"{rel}:{lineno}", ln.strip()[:70],
                        "a .HandleFunc(/.Handle( registration whose receiver "
                        "is separated from the member by whitespace or a "
                        "newline (`mux.` at end of line, `mux . Handle(`); "
                        "neither line names an owner this resolver can attach "
                        "a wrap to, and dropping it would hide the route"))
                    continue
                if MUX_DOTTED_OWNER.search(bln):
                    unmodelled.append(_unmod(
                        svc["id"], f"{rel}:{lineno}", ln.strip()[:70],
                        "the route is registered on a mux reached through a "
                        "field or selector (`x.y.HandleFunc(...)`), whose wrap "
                        "this resolver cannot follow; attributing it to a "
                        "same-named local mux would falsely mark it wrapped"))
                    continue
                # ROUND 9 (BLOCKING-1) — the unattributable-receiver refusal.
                # Checked BEFORE the bare-owner filter below, because that
                # filter's `continue` is precisely the silent drop.
                _sites = len(MUX_CALL.findall(bln))
                # ROUND 11 (MINOR-1) — HONEST LABEL, to the same standard the
                # M-E9 note set. The `MUX_DOTTED_OWNER` term is DEAD BY
                # PREEMPTION: the dotted refusal above `continue`s on
                # `.search()`, and `.search()` is truthy for EVERY line
                # `.findall()` would count, so at THIS comparison the term is
                # provably 0. Verified independently 2026-08-27 (not taken on
                # report): across every dotted spelling this engine models, the
                # number of lines that reach here with a non-zero dotted count
                # is 0, and deleting the term leaves the whole fixture matrix
                # green — it is semantically unreachable, so no fixture CAN
                # kill it.
                # It is KEPT, not deleted, and recorded as UNPINNED rather than
                # claimed as pinned: the mutual exclusivity it relies on is
                # real and MEASURED (`named <= sites` held over 20,000
                # adversarial lines with a control needle proving the
                # instrument was seeing), so the term is the correct arithmetic
                # the moment a future edit reorders the dotted refusal below
                # this comparison — which is exactly the reordering that would
                # otherwise turn `_sites > _named` into a spurious refusal on
                # every dotted registration.
                _named = len(MUX_ANY.findall(bln)) + len(MUX_DOTTED_OWNER.findall(bln))
                if _sites > _named:
                    unmodelled.append(_unmod(
                        svc["id"], f"{rel}:{lineno}", ln.strip()[:70],
                        "a .HandleFunc(/.Handle( registration whose receiver "
                        "is neither a bare identifier nor a dotted selector "
                        "(a call result, an index expression, ...), so this "
                        "resolver cannot name the mux it registers on; "
                        "skipping it would drop the route silently"))
                    continue
                if not MUX_ANY.search(bln):
                    continue
                if not MUX_ROUTE.search(ln):
                    unmodelled.append(
                        _unmod(svc["id"], f"{rel}:{lineno}", ln.strip()[:70],
                               "mux registration whose path is not a string literal")
                    )
                # `mux_path`, not `raw`: `raw` is this function's file-lines
                # variable and the loop was shadowing it (round-6 NIT).
                for owner, mux_path in MUX_ROUTE.findall(ln):
                    if owner == "http":
                        unmodelled.append(
                            _unmod(
                                svc["id"], f"{rel}:{lineno}", "http.Handle/HandleFunc(...)",
                                "registers on the global http.DefaultServeMux, which "
                                "no returned handler wraps",
                            )
                        )
                        continue
                    w = wrapped.get(owner, False)
                    known = owner in decls
                    routes.append(
                        Route(
                            svc["id"], "ANY", _norm(mux_path), w, f"{rel}:{lineno}",
                            f"mux '{owner}' is returned wrapped in an auth marker" if w
                            else (
                                f"mux '{owner}' is returned WITHOUT an auth marker"
                                if known
                                else f"mux '{owner}' is not a resolvable "
                                     f"http.NewServeMux() in this function "
                                     f"(fail-closed: treated as unwrapped)"
                            ),
                        )
                    )
    return routes, unmodelled


EXTRACTORS = {"fastapi": extract_fastapi, "gin": extract_gin, "gomux": extract_gomux}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Resolve LAN route auth wiring.")
    ap.add_argument("--policy", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)

    try:
        import yaml
    except ImportError:
        print("ERROR: PyYAML is required (python3 -m pip install --user pyyaml)", file=sys.stderr)
        return 2

    if not os.path.isfile(ns.policy):
        print(f"ERROR: policy file not found: {ns.policy}", file=sys.stderr)
        return 2
    # MINOR-3: an unparseable policy is an ERROR (2), never a route finding (1).
    try:
        with open(ns.policy, encoding="utf-8") as fh:
            policy = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        print(f"ERROR: policy file is not valid YAML: {ns.policy}", file=sys.stderr)
        print(f"  {str(exc).splitlines()[0]}", file=sys.stderr)
        print("  Refusing rather than reporting an unverified verdict (§11.4.201(5)).",
              file=sys.stderr)
        return 2
    if not isinstance(policy, dict):
        print(f"ERROR: policy root must be a mapping, got {type(policy).__name__}",
              file=sys.stderr)
        return 2

    services = policy.get("services") or []
    exemptions = policy.get("exemptions") or []
    findings, all_routes, blind = [], [], []

    # The POLICY's own zero is a FALSE-NULL too (§11.4.201(6), round 5). With an
    # empty `services` list the scan loop never runs, `blind` never fills, and
    # the gate returns PASS — so deleting the declarations turns it green over
    # a wide-open tree. That is the same refuse-the-quiet-zero rule the
    # per-service check below already applies, one level up. Deliberately
    # narrow: it refuses an EMPTY declaration list, never a policy that scopes
    # itself with `lan_bound: false` (which is a real, tested scoping statement
    # — refusing that would be the §11.4.201(1) false-positive refusal).
    if not services:
        findings.append(
            "policy declares ZERO services. An empty declaration list and a "
            "system with no LAN listener return the same quiet PASS here, so "
            "this zero is REFUSED rather than blessed (§11.4.201(6) "
            "FALSE-NULL). Declare the LAN-bound listeners this gate must "
            "cover; a listener that is genuinely not LAN-reachable is declared "
            "with 'lan_bound: false', not by deleting it."
        )

    exempt_index = {}
    for idx, ex in enumerate(exemptions):
        just = (ex.get("justification") or "").strip()
        cls = (ex.get("class") or "").strip()
        sid, meth, pth = ex.get("service"), (ex.get("method") or "ANY").upper(), ex.get("path")
        if not sid or not pth:
            findings.append(f"exemption[{idx}]: missing required 'service' or 'path' field")
            continue
        if not just:
            findings.append(
                f"exemption[{idx}] {sid} {meth} {pth}: EMPTY justification — a silent "
                f"exemption is forbidden (§11.4.201(1): honest gaps, never blanket skips)"
            )
        if cls not in ("public-by-design", "known-gap"):
            findings.append(
                f"exemption[{idx}] {sid} {meth} {pth}: class must be "
                f"'public-by-design' or 'known-gap', got {cls!r}"
            )
        key = (sid, meth, _norm(pth))
        # MINOR-2: a duplicate can silently mask a known-gap and skew the count.
        if key in exempt_index:
            prev = exempt_index[key]
            findings.append(
                f"DUPLICATE EXEMPTION  {sid} {meth} {pth}: declared more than once "
                f"(class {prev.get('class')!r} then {cls!r}). Last-wins would let a "
                f"'known-gap' be silently masked and skew the honest-gap count "
                f"(§11.4.261). Keep exactly one entry per route."
            )
        exempt_index[key] = ex

    for svc in services:
        if not svc.get("lan_bound", False):
            continue  # not LAN-reachable => out of this gate's scope (§11.4.6)
        kind = svc.get("kind")
        if kind not in EXTRACTORS:
            findings.append(f"service {svc.get('id')}: unknown kind {kind!r}")
            continue
        rs, unmod = EXTRACTORS[kind](ns.root, svc, set(svc.get("auth_markers") or []))
        findings.extend(unmod)
        if not rs:
            blind.append(svc.get("id"))
        all_routes.extend(rs)

    for sid in blind:
        findings.append(
            f"service {sid}: declared LAN-bound but the scan resolved ZERO routes. "
            f"A blind extractor and a route-free service are indistinguishable here, "
            f"so this zero is REFUSED rather than blessed (§11.4.201(6) FALSE-NULL). "
            f"Fix the service 'roots'/'kind', or remove the service from the policy."
        )

    matched = set()
    for r in all_routes:
        if r.auth:
            continue
        hit = exempt_index.get(r.key()) or exempt_index.get((r.service, "ANY", r.path))
        if hit is not None:
            matched.add((hit.get("service"), (hit.get("method") or "ANY").upper(),
                         _norm(hit["path"])))
            continue
        findings.append(
            f"UNAUTHENTICATED LAN-REACHABLE ROUTE  {r.service}  {r.method} {r.path}\n"
            f"    declared at : {r.evidence}\n"
            f"    resolved    : {r.why}\n"
            f"    mutating    : {'YES' if r.method in MUTATING or r.method == 'ANY' else 'no'}\n"
            f"    remedy      : wire an auth marker for this route, OR add a justified "
            f"entry to the exemption list in the policy file."
        )

    live = {r.key() for r in all_routes} | {(r.service, "ANY", r.path) for r in all_routes}
    for key in exempt_index:
        if key in matched:
            continue
        sid, meth, pth = key
        if key in live or any(k[0] == sid and k[2] == pth for k in live):
            continue  # route exists (and is auth-wired) — redundant, not stale
        findings.append(
            f"STALE EXEMPTION  {sid} {meth} {pth}: no such route exists in the "
            f"current source. Remove the entry so the list keeps describing reality."
        )

    if ns.json:
        print(json.dumps(
            {"routes": [r.as_dict() for r in all_routes], "findings": findings,
             "route_count": len(all_routes)}, indent=2))
    else:
        print(f"resolved {len(all_routes)} LAN-reachable route(s) across "
              f"{len({r.service for r in all_routes})} service(s)")
        n_gap = sum(1 for e in exemptions if (e.get("class") or "") == "known-gap")
        if n_gap:
            print(f"HONEST GAPS: {n_gap} route(s) exempted as class 'known-gap' "
                  f"(real holes, tracked — must never grow)")
        for f in findings:
            print(f"FINDING: {f}", file=sys.stderr)

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
