#!/usr/bin/env python3
"""sse_route_rate_limit_class_analyzer.py — the CM-SSE-ROUTE-RATE-LIMIT-CLASSED
detection engine (BOB-167).

WHY THIS EXISTS
----------------
Two FastAPI routes in ``download-proxy/src/api/routes.py`` share the SAME
expensive shape: a long-lived Server-Sent-Events connection that pins a
worker + a generator for the connection's lifetime (``GET /theme/stream``
and ``GET /search/stream/{search_id}``). Only one of the two carried an
explicit rate-limit class (``@_rl("sse_stream")``) — the other silently
fell through to the application's ``default`` class, a strictly looser
budget the route's own resource shape does not justify (BOB-167).

A one-off decorator fix closes the two routes that exist TODAY. It does
NOT stop a THIRD SSE-shaped route from landing tomorrow with the same
silent gap — nothing forces a route author to remember the classification
rule. This analyzer is the GENERAL form: it enumerates every route whose
response is SSE-shaped and FAILS the build if any of them carries no
explicit rate-limit class, so the gap this file fixes today can never
recur unnoticed (§11.4.135 permanent regression guard; §11.4.227 the
general form is what earns "closed", not the one-off patch).

HOW "SSE-SHAPED" IS RESOLVED (§11.4.201 — the REAL condition, not a proxy)
---------------------------------------------------------------------------
This module already has TWO distinct, already-established idioms for
building an SSE response, and this analyzer recognises both rather than
grepping for one literal string (a grep for one idiom is exactly the kind
of proxy-signal false-negative §11.4.201(7)(a) warns about — it would have
been BLIND to ``/search/stream`` on day one, since that route never writes
the literal string ``"text/event-stream"`` in routes.py at all):

  (A) An inline ``StreamingResponse(..., media_type="text/event-stream")``
      call in a route's own ``return`` statement — the shape
      ``/theme/stream`` uses.
  (B) A call to a helper named (or attribute-ending-in) ``…
      create_streaming_response(...)`` — the shared idiom
      ``api/streaming.py::SSEHandler.create_streaming_response`` defines,
      whose own default ``media_type`` is ``"text/event-stream"`` (verified
      by reading that helper's signature, not assumed). The shape
      ``/search/stream/{search_id}`` uses.

A route counts as SSE-shaped if ANY of its own ``return`` statements
(walked at the route function's own level — NOT descending into a nested
generator function's body, since the generator never itself returns a
``Response``) matches (A) or (B), and the matched call's ``media_type``
keyword (if present) is either absent (idiom default) or a string literal
equal to ``"text/event-stream"``. A call that explicitly overrides
``media_type`` to something else (``"application/json"`` for
``/search/sync``'s keepalive-heartbeat response, ``"application/x-bittorrent"``
for the torrent-download streams) is correctly EXCLUDED — those are
streaming responses of a different resource shape, not SSE.

HOW "RATE-LIMIT CLASSED" IS RESOLVED
--------------------------------------
Two mechanisms this codebase already uses to attach a per-IP rate-limit
class to a route (``download-proxy/src/api/rate_limit.py`` documents both,
and ``routes.py`` uses both across its surface — ``POST /search`` uses the
dependency form specifically to close the 422-validation bypass a
decorator cannot see):

  * a ``@_rl("<class>")``-shaped decorator on the route function, OR
  * a ``Depends(rate_limit_dependency("<class>"))`` reachable from either
    the route decorator's ``dependencies=[...]`` kwarg or one of the route
    function's own parameter defaults.

Either counts as "classed". Neither is preferred — this gate asserts a
route was CONSCIOUSLY classed, not which mechanism was used.

FALSE-NULL GUARD (§11.4.201(6))
---------------------------------
A run that resolves ZERO SSE-shaped routes is refused as BLIND rather than
reported PASS — a blind extractor and a genuinely SSE-route-free file
return the identical quiet zero, and this project has at least two such
routes today. Zero found is therefore ERROR (exit 2), never a silent PASS.

Usage
-----
    sse_route_rate_limit_class_analyzer.py [--file PATH] [--json] [-v]

Exit codes
----------
    0 — PASS  every SSE-shaped route resolved carries an explicit class.
    1 — FAIL  one or more SSE-shaped routes carry no explicit class.
    2 — ERROR usage error, missing/unparsable file, or zero SSE-shaped
        routes resolved (blind-instrument refusal, §11.4.201(6)).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}
_SSE_TEXT_EVENT_STREAM = "text/event-stream"


@dataclass
class RouteFinding:
    name: str
    path: str | None
    lineno: int
    sse_shaped: bool
    classed: bool
    sse_evidence: list[str] = field(default_factory=list)
    class_evidence: list[str] = field(default_factory=list)


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_target_name(call: ast.Call) -> str | None:
    """Return a dotted-ish, human readable name for ``call.func``.

    ``Name`` nodes return their id; ``Attribute`` nodes return the final
    attribute name — the discriminator this analyzer needs is the LAST
    component (``create_streaming_response``), never the full receiver
    chain, since the receiver may be ``SSEHandler``, a module alias, or a
    locally imported symbol.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _media_type_kw(call: ast.Call) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg == "media_type":
            return kw.value
    return None


def _is_sse_call(call: ast.Call) -> tuple[bool, str | None]:
    """Return (is_sse_shaped, evidence) for one Call node found in a
    route's own return statements."""
    target = _call_target_name(call)
    if target is None:
        return False, None

    media = _media_type_kw(call)
    media_str = _const_str(media)

    if target == "StreamingResponse":
        # Idiom (A): direct StreamingResponse(..., media_type=...) call.
        # No media_type kw at all -> not SSE-shaped (this codebase always
        # sets it explicitly for every StreamingResponse call site, so an
        # absent kw here is deliberately NOT treated as an SSE default —
        # that would be a false-positive proxy signal, §11.4.201(1)).
        if media is None:
            return False, None
        if media_str == _SSE_TEXT_EVENT_STREAM:
            return True, f"StreamingResponse(media_type={media_str!r})"
        return False, None

    if target == "create_streaming_response":
        # Idiom (B): the shared SSEHandler helper. Its own default
        # media_type is "text/event-stream" (api/streaming.py); an
        # explicit override to something else is honoured and excludes
        # the route, an explicit confirmation or an absent kw both count.
        if media is None or media_str == _SSE_TEXT_EVENT_STREAM:
            return True, "create_streaming_response(...) [SSE-default media_type]"
        return False, None

    return False, None


def _own_level_returns(func: ast.AST) -> list[ast.Return]:
    """Every ``return`` statement that belongs to ``func`` ITSELF — never
    descending into a nested (generator) function/lambda's own body, since
    a nested generator's ``return`` cannot produce the outer handler's
    Response object.

    ``ast.iter_child_nodes(func)`` yields ``func``'s OWN direct children
    (its arguments, decorators, body statements, ...) — ``func`` itself is
    never re-tested against the nested-callable check, so its own body is
    always walked. Any child that IS itself a nested
    ``FunctionDef``/``AsyncFunctionDef``/``Lambda`` (e.g. the SSE
    generator ``gen()``/``_wrapped()`` defined inside the route handler)
    is skipped entirely rather than recursed into — a ``return`` inside
    that nested callable ends ITS OWN call, not the route handler's.
    """
    found: list[ast.Return] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Return):
                found.append(child)
            walk(child)

    walk(func)
    return found


def _decorator_call(dec: ast.expr) -> ast.Call | None:
    return dec if isinstance(dec, ast.Call) else None


def _is_rl_decorator(call: ast.Call) -> str | None:
    target = _call_target_name(call)
    if target != "_rl":
        return None
    for arg in call.args:
        s = _const_str(arg)
        if s:
            return f"@_rl({s!r})"
    return "@_rl(...)"


def _find_rate_limit_dependency(node: ast.AST) -> str | None:
    """Search a subtree for ``Depends(rate_limit_dependency("<class>"))``."""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        if _call_target_name(sub) != "Depends":
            continue
        for arg in list(sub.args) + [kw.value for kw in sub.keywords]:
            if isinstance(arg, ast.Call) and _call_target_name(arg) == "rate_limit_dependency":
                cls = None
                for inner in arg.args:
                    cls = _const_str(inner)
                    if cls:
                        break
                return f"Depends(rate_limit_dependency({cls!r}))" if cls else "Depends(rate_limit_dependency(...))"
    return None


def _is_route_decorator(dec: ast.expr) -> tuple[bool, str | None]:
    call = _decorator_call(dec)
    if call is None:
        return False, None
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in _HTTP_METHODS:
        return False, None
    path = None
    if call.args:
        path = _const_str(call.args[0])
    return True, path


def analyze(source: str, filename: str) -> list[RouteFinding]:
    tree = ast.parse(source, filename=filename)
    findings: list[RouteFinding] = []

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_path: str | None = None
        is_route = False
        for dec in node.decorator_list:
            matched, path = _is_route_decorator(dec)
            if matched:
                is_route = True
                if path:
                    route_path = path
        if not is_route:
            continue

        sse_evidence: list[str] = []
        for ret in _own_level_returns(node):
            if ret.value is not None and isinstance(ret.value, ast.Call):
                ok, ev = _is_sse_call(ret.value)
                if ok and ev:
                    sse_evidence.append(ev)
        sse_shaped = bool(sse_evidence)

        class_evidence: list[str] = []
        for dec in node.decorator_list:
            call = _decorator_call(dec)
            if call is None:
                continue
            ev = _is_rl_decorator(call)
            if ev:
                class_evidence.append(ev)
            for dep_kw in call.keywords:
                if dep_kw.arg == "dependencies":
                    ev2 = _find_rate_limit_dependency(dep_kw.value)
                    if ev2:
                        class_evidence.append(ev2)
        for default in list(node.args.defaults) + list(node.args.kw_defaults):
            if default is None:
                continue
            ev3 = _find_rate_limit_dependency(default)
            if ev3:
                class_evidence.append(ev3)

        findings.append(
            RouteFinding(
                name=node.name,
                path=route_path,
                lineno=node.lineno,
                sse_shaped=sse_shaped,
                classed=bool(class_evidence),
                sse_evidence=sse_evidence,
                class_evidence=class_evidence,
            )
        )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--file",
        default="download-proxy/src/api/routes.py",
        help="path to the FastAPI routes module to scan (default: %(default)s)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON on stdout")
    parser.add_argument("-v", "--verbose", action="store_true", help="print every resolved route, not only findings")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR(sse_route_rate_limit_class_analyzer): file not found: {path}", file=sys.stderr)
        return 2

    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR(sse_route_rate_limit_class_analyzer): cannot read {path}: {exc}", file=sys.stderr)
        return 2

    try:
        all_routes = analyze(source, str(path))
    except SyntaxError as exc:
        print(f"ERROR(sse_route_rate_limit_class_analyzer): {path} does not parse: {exc}", file=sys.stderr)
        return 2

    sse_routes = [r for r in all_routes if r.sse_shaped]

    if args.json:
        print(
            json.dumps(
                {
                    "file": str(path),
                    "total_routes": len(all_routes),
                    "sse_shaped_routes": len(sse_routes),
                    "routes": [
                        {
                            "name": r.name,
                            "path": r.path,
                            "line": r.lineno,
                            "sse_shaped": r.sse_shaped,
                            "classed": r.classed,
                            "sse_evidence": r.sse_evidence,
                            "class_evidence": r.class_evidence,
                        }
                        for r in all_routes
                    ],
                },
                indent=2,
            )
        )

    if not args.json:
        print(f"[sse-route-rate-limit-class-analyzer] file: {path}")
        print(f"[sse-route-rate-limit-class-analyzer] routes resolved: {len(all_routes)}")
        print(f"[sse-route-rate-limit-class-analyzer] SSE-shaped routes resolved: {len(sse_routes)}")

    if not sse_routes:
        if not args.json:
            print(
                "ERROR(sse_route_rate_limit_class_analyzer): zero SSE-shaped routes "
                "resolved — refusing rather than reporting an unverified PASS "
                "(§11.4.201(6) false-null: a blind extractor and an SSE-route-free "
                "file return the identical quiet zero).",
                file=sys.stderr,
            )
        return 2

    findings = [r for r in sse_routes if not r.classed]

    if not args.json:
        for r in sse_routes:
            status = "OK    " if r.classed else "FINDING"
            if r.classed or args.verbose:
                print(
                    f"  {status} {r.path or r.name!r} ({path}:{r.lineno}) "
                    f"sse={r.sse_evidence} class={r.class_evidence or ['<none>']}"
                )

    if findings:
        if not args.json:
            print("\n=== FINDINGS ===", file=sys.stderr)
            for r in findings:
                print(
                    f"  {path}:{r.lineno} — {r.path or r.name!r} is SSE-shaped "
                    f"(evidence: {r.sse_evidence}) but carries no explicit "
                    f"rate-limit class (no @_rl(...) decorator and no "
                    f"Depends(rate_limit_dependency(...)) dependency). An unclassed "
                    f"SSE route silently falls through to the application default "
                    f"class — the cheapest way to pin server resources (BOB-167).",
                    file=sys.stderr,
                )
            print(
                f"\nFAIL(CM-SSE-ROUTE-RATE-LIMIT-CLASSED): {len(findings)} "
                f"unclassed SSE-shaped route(s) of {len(sse_routes)} resolved.",
                file=sys.stderr,
            )
        return 1

    if not args.json:
        print(
            f"\nPASS(CM-SSE-ROUTE-RATE-LIMIT-CLASSED): all {len(sse_routes)} "
            f"SSE-shaped route(s) carry an explicit rate-limit class."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
