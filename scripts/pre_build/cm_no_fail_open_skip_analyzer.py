#!/usr/bin/env python3
"""cm_no_fail_open_skip_analyzer.py — detection engine for the §11.4.69
CM-NO-FAIL-OPEN-SKIP pre-build gate (BOB-161).

WHAT IT FINDS
    A *fail-open skip*: a test that turns evidence the far side ANSWERED — a
    response status, an empty / absent body, or an exception class that also
    carries answered HTTP errors — into a SKIP. A skip is PASS-counting in
    every summary a human reads ("N passed, M skipped, 0 failed"), so a
    defect the product really exhibited leaves the run green. §11.4.69 names
    this gate; BOB-092 removed two instances one at a time, which is the
    §11.4.146 / §11.4.238 signal that the CLASS needs a corpus-wide detector.

THE RULE (decidable, AST-based — never a text grep)
    A skip site is ``pytest.skip(...)``, a bare ``skip(...)``,
    ``<x>.skipTest(...)`` or ``raise [unittest.]SkipTest(...)``. It is a
    FINDING when one of these encloses it inside the same function:

    STATUS   an ``if``/``elif``/``while``/ternary whose test reads a status of
             response-derived data: ``.status``/``.status_code``/``.ok``/
             ``.code``/``.reason``, a ``["status"]``-style key (or
             ``.get("status")``) from the key set below, or a comparison
             against an HTTP-range int literal (100..599).
    EMPTY    such a test that checks response-derived data for emptiness or
             absence: ``not x``, ``x is None``, ``len(x) == 0``,
             ``x == ""``, ``"k" not in x``, or bare truthiness of ``x``.
    UNREACH  an ``except`` whose ``try`` body performs a network call and
             whose caught types include an ANSWER-CAPABLE class — one that
             also carries answered HTTP errors (``HTTPError``, ``URLError``,
             ``RequestException``, ``OSError``, ``Exception``, bare
             ``except``, ...). ``urllib`` raises ``HTTPError`` (a
             ``URLError`` subclass) for every 4xx/5xx, so catching
             ``URLError`` silently converts an answered 500 into a skip.

    "Response-derived" is intra-module taint: names bound from a network
    call (``requests.*``, ``httpx.*``, ``urlopen``, ``<client>.get`` ...),
    from a call to a module function that transitively performs one, or
    from an expression over an already-tainted name. Environment-derived
    evidence (``os.environ``, ``shutil.which``, a file's existence, a TCP
    ``socket`` connect) is never tainted — a skip on it is the legitimate
    §11.4.3 topology SKIP. Catching ONLY connection-class exceptions
    (``ConnectionError``, ``ConnectError``, ``Timeout``...) is likewise
    topology-absent, not answered, and is not a finding.

    Shell: a bare ``ab_skip`` at command position, or ``ab_skip_with_reason``
    whose reason is outside the §11.4.69 closed set or is
    ``network_unreachable_external`` (forbidden for sink-probed features;
    the feature class is not statically knowable, so it is refused
    conservatively). Comments, strings and heredoc bodies are CARRIERS and
    never findings (§11.4.201(7)(a)).

    The free-text reason of a pytest skip, and any ``# allow-skip:`` marker,
    NEVER absolve a finding: they are carriers, and BOB-192 records that the
    marked sites at test_tracker_auth_live.py are genuinely fail-open.

KEYS AND THE BASELINE
    A finding key is ``<path>:<qualname>:<TRIGGERS>#<n>`` (n = ordinal of that
    trigger within that function, by line). Keys, not line numbers, so an
    edit elsewhere in the file does not churn the ratchet. The baseline is a
    SET compared in BOTH directions: a finding not in it is NEW (FAIL), a
    baseline row with no live finding is STALE (FAIL — the ratchet must be
    tightened in the same change that removes a finding). A count-only
    baseline would absorb a one-out-one-in swap (BOB-192 MINOR-1).

    Honest residual (§11.4.6): a swap of two same-trigger skips INSIDE ONE
    function keeps the same key set and is not distinguishable; taint does
    not cross module boundaries or pytest-fixture parameters.

EXIT
    0 PASS  finding SET == baseline SET, control needle seen.
    1 FAIL  NEW and/or STALE rows.
    2 ERROR root not enumerable, unparseable test file, control needle not
            seen (the instrument is blind), or zero skip sites in the corpus
            (a blind extractor and a clean corpus return the same zero —
            §11.4.201(6); this project has dozens of skip sites).
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shlex
import subprocess
import sys

# Mutation knobs for the paired §1.1 harness — keep these literal lines exact.
TRIGGERS_ENABLED = True
CONTROL_NEEDLE_ENABLED = True
BASELINE_ENFORCED = True

STATUS_ATTRS = {"status", "status_code", "ok", "code", "reason"}
STATUS_KEYS = {"status", "status_code", "http_status", "code", "ok", "error", "error_type"}
NET_ROOTS = {"requests", "httpx", "aiohttp", "urllib", "urllib3"}
NET_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream", "send"}
CLIENTISH = {"session", "sess", "client", "http", "api", "test_client", "async_client", "app_client"}
RESPONSE_VOCAB = {"resp", "response", "reply"}
ANSWER_CAPABLE = {
    "HTTPError",
    "URLError",
    "RequestException",
    "HTTPStatusError",
    "Exception",
    "BaseException",
    "OSError",
    "IOError",
    "EnvironmentError",
    "ClientError",
    "ClientResponseError",
    "HTTPException",
    "TransportError",
}
# §11.4.69 closed reason set; network_unreachable_external is excluded
# because it is forbidden for features that carry a sink-side probe.
SHELL_OK_REASONS = {
    "geo_restricted",
    "operator_attended",
    "hardware_not_present",
    "topology_unsupported",
    "feature_disabled_by_config",
    "artifact_not_yet_built",
}


# ----------------------------------------------------------------- helpers
def dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append(dotted(node.func) + "()")
    else:
        parts.append("?")
    return ".".join(reversed(parts))


def is_direct_net_call(call: ast.Call, tainted: set[str]) -> bool:
    name = dotted(call.func)
    segs = name.split(".")
    if segs[-1] == "urlopen":
        return True
    if segs[0] in NET_ROOTS:
        return True
    if segs[-1] in NET_METHODS and len(segs) >= 2:
        recv = segs[-2]
        if recv in CLIENTISH or segs[0] in tainted:
            return True
    return False


def called_local(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in {"self", "cls"}:
        return f.attr
    return None


def network_functions(tree: ast.AST) -> set[str]:
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    net: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, fn in funcs.items():
            if name in net:
                continue
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Call) and (is_direct_net_call(sub, set()) or called_local(sub) in net):
                    net.add(name)
                    changed = True
                    break
    return net


def expr_tainted(e: ast.AST | None, tainted: set[str], netfns: set[str]) -> bool:
    if e is None:
        return False
    for sub in ast.walk(e):
        if isinstance(sub, ast.Name) and sub.id in tainted:
            return True
        if isinstance(sub, ast.Call) and (is_direct_net_call(sub, tainted) or called_local(sub) in netfns):
            return True
    return False


def target_names(t: ast.AST) -> list[str]:
    return [n.id for n in ast.walk(t) if isinstance(n, ast.Name)]


def function_taint(fn: ast.AST, netfns: set[str]) -> set[str]:
    tainted = set(RESPONSE_VOCAB)
    for _ in range(6):
        before = len(tainted)
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and expr_tainted(n.value, tainted, netfns):
                for t in n.targets:
                    tainted.update(target_names(t))
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and expr_tainted(
                n.value, tainted, netfns
            ):
                tainted.update(target_names(n.target))
            elif (
                isinstance(n, ast.withitem)
                and n.optional_vars is not None
                and expr_tainted(n.context_expr, tainted, netfns)
            ):
                tainted.update(target_names(n.optional_vars))
            elif isinstance(n, (ast.For, ast.AsyncFor)) and expr_tainted(n.iter, tainted, netfns):
                tainted.update(target_names(n.target))
        if len(tainted) == before:
            break
    return tainted


def _is_http_int(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int and 100 <= node.value <= 599


def status_trigger(test: ast.AST, tainted: set[str], netfns: set[str]) -> bool:
    for sub in ast.walk(test):
        if isinstance(sub, ast.Attribute) and sub.attr in STATUS_ATTRS and expr_tainted(sub.value, tainted, netfns):
            return True
        if (
            isinstance(sub, ast.Subscript)
            and isinstance(sub.slice, ast.Constant)
            and sub.slice.value in STATUS_KEYS
            and expr_tainted(sub.value, tainted, netfns)
        ):
            return True
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "get"
            and sub.args
            and isinstance(sub.args[0], ast.Constant)
            and sub.args[0].value in STATUS_KEYS
            and expr_tainted(sub.func.value, tainted, netfns)
        ):
            return True
        if isinstance(sub, ast.Compare):
            operands = [sub.left, *sub.comparators]
            if any(_is_http_int(o) for o in operands) and any(
                expr_tainted(o, tainted, netfns) for o in operands if not _is_http_int(o)
            ):
                return True
    return False


def _truthiness_nodes(test: ast.AST):
    if isinstance(test, ast.BoolOp):
        for v in test.values:
            yield from _truthiness_nodes(v)
    elif isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        yield from _truthiness_nodes(test.operand)
    else:
        yield test


def empty_trigger(test: ast.AST, tainted: set[str], netfns: set[str]) -> bool:
    for node in _truthiness_nodes(test):
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)) and expr_tainted(node, tainted, netfns):
            return True
        if isinstance(node, ast.Compare):
            left, ops, comps = node.left, node.ops, node.comparators
            for op, right in zip(ops, comps, strict=True):
                # Only ABSENCE ("k" not in body) is an emptiness check. Presence
                # ("x" in listing) is a data-safety guard shape (e.g. "the
                # operator already owns this torrent — do not mutate it").
                if isinstance(op, ast.NotIn) and expr_tainted(right, tainted, netfns):
                    return True
                if (
                    isinstance(op, (ast.Is, ast.IsNot))
                    and isinstance(right, ast.Constant)
                    and right.value is None
                    and expr_tainted(left, tainted, netfns)
                ):
                    return True
                if (
                    isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE))
                    and isinstance(right, ast.Constant)
                    and right.value in ("", b"", 0, 1)
                    and expr_tainted(left, tainted, netfns)
                ):
                    return True
                if (
                    isinstance(op, (ast.Eq, ast.NotEq))
                    and isinstance(right, (ast.List, ast.Dict, ast.Tuple))
                    and not getattr(right, "elts", getattr(right, "keys", [1]))
                    and expr_tainted(left, tainted, netfns)
                ):
                    return True
    return False


def handler_answer_capable(h: ast.ExceptHandler) -> bool:
    if h.type is None:
        return True
    types = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return any(dotted(t).split(".")[-1] in ANSWER_CAPABLE for t in types)


def is_skip_site(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute):
            if f.attr == "skipTest":
                return True
            if f.attr == "skip" and dotted(f.value).split(".")[-1] == "pytest":
                return True
        if isinstance(f, ast.Name) and f.id == "skip":
            return True
    if isinstance(node, ast.Raise) and node.exc is not None:
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        name = dotted(exc)
        if name.split(".")[-1] == "SkipTest" or name == "pytest.skip.Exception":
            return True
    return False


# ------------------------------------------------------------ python scan
def analyze_python_source(src: str, path: str) -> tuple[list[tuple[str, str, int]], int]:
    """Return ([(qualname, triggers, lineno)], skip_site_count). Raises SyntaxError."""
    tree = ast.parse(src, filename=path)
    parent: dict[ast.AST, ast.AST] = {}
    for p in ast.walk(tree):
        for ch in ast.iter_child_nodes(p):
            parent[ch] = p
    netfns = network_functions(tree)
    taint_cache: dict[ast.AST, set[str]] = {}
    hits: list[tuple[str, str, int]] = []
    sites = 0
    for node in ast.walk(tree):
        if not is_skip_site(node):
            continue
        # A raise of a skip-call is one site, not two.
        if isinstance(node, ast.Call) and isinstance(parent.get(node), ast.Raise):
            continue
        sites += 1
        fn = None
        cur = node
        chain: list[tuple[ast.AST, ast.AST]] = []
        while cur in parent:
            p = parent[cur]
            chain.append((p, cur))
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and fn is None:
                fn = p
                break
            cur = p
        names = []
        cur = node
        while cur in parent:
            cur = parent[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(cur.name)
        qual = ".".join(reversed(names)) or "<module>"
        scope = fn if fn is not None else tree
        if scope not in taint_cache:
            taint_cache[scope] = function_taint(scope, netfns)
        tainted = taint_cache[scope]
        triggers: set[str] = set()
        if TRIGGERS_ENABLED:
            for p, child in chain:
                if isinstance(p, (ast.If, ast.While, ast.IfExp)) and child is not p.test:
                    if status_trigger(p.test, tainted, netfns):
                        triggers.add("STATUS")
                    elif empty_trigger(p.test, tainted, netfns):
                        triggers.add("EMPTY")
                if isinstance(p, ast.ExceptHandler) and handler_answer_capable(p):
                    tr = parent.get(p)
                    if isinstance(tr, (ast.Try, getattr(ast, "TryStar", ast.Try))) and any(
                        expr_tainted(stmt, set(), netfns) for stmt in tr.body
                    ):
                        triggers.add("UNREACH")
        if triggers:
            hits.append((qual, "+".join(sorted(triggers)), node.lineno))
    return hits, sites


# ------------------------------------------------------------- shell scan
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_CMD_POS = re.compile(r"(?:^|[;&|({]\s*|\b(?:then|do|else|elif|if|while|until)\s+)(ab_skip(?:_with_reason)?)(?=\s|$|;)")


def _blank_strings_and_comment(line: str) -> str:
    out, i, q = [], 0, None
    while i < len(line):
        c = line[i]
        if q:
            if c == "\\" and q == '"' and i + 1 < len(line):
                out.append("  ")
                i += 2
                continue
            if c == q:
                q = None
                out.append(c)
            else:
                out.append(" ")
        else:
            if c in "'\"":
                q = c
                out.append(c)
            elif c == "#" and (i == 0 or line[i - 1] in " \t;&|("):
                break
            else:
                out.append(c)
        i += 1
    return "".join(out)


def analyze_shell_source(src: str, path: str) -> tuple[list[tuple[str, str, int]], int]:
    hits: list[tuple[str, str, int]] = []
    sites = 0
    heredoc_end: str | None = None
    for lineno, raw in enumerate(src.splitlines(), 1):
        if heredoc_end is not None:
            if raw.strip() == heredoc_end:
                heredoc_end = None
            continue
        code = _blank_strings_and_comment(raw)
        # The heredoc operator is found in the de-stringed line (so "<<X"
        # inside a string is ignored) but its quoted terminator word is read
        # from the raw line, where the quotes were not blanked.
        hd = code.find("<<")
        m = _HEREDOC.search(raw, hd) if hd >= 0 else None
        for cm in _CMD_POS.finditer(code):
            sites += 1
            if not TRIGGERS_ENABLED:
                continue
            if cm.group(1) == "ab_skip":
                hits.append(("<sh>", "SHELL_BARE_SKIP", lineno))
                continue
            try:
                toks = shlex.split(raw[cm.start(1) :], comments=True)
            except ValueError:
                toks = []
            reason = toks[2] if len(toks) >= 3 else ""
            if reason not in SHELL_OK_REASONS:
                hits.append(("<sh>", "SHELL_REASON", lineno))
        if m:
            heredoc_end = m.group(2)
    return hits, sites


# ---------------------------------------------------------- key assembly
def keys_for(path: str, hits: list[tuple[str, str, int]]) -> list[tuple[str, int]]:
    out, counter = [], {}
    for qual, trig, line in sorted(hits, key=lambda h: (h[0], h[1], h[2])):
        counter[(qual, trig)] = counter.get((qual, trig), 0) + 1
        out.append((f"{path}:{qual}:{trig}#{counter[(qual, trig)]}", line))
    return out


# -------------------------------------------------------- control needle
_NEEDLE_TRUE_PY = """
import pytest, requests, urllib.request
def t_status():
    r2 = requests.get("http://x")
    if r2.status_code == 503:
        pytest.skip("x")
def t_empty():
    with urllib.request.urlopen("http://x") as h:
        data = h.read()
    if not data:
        pytest.skip("x")
def t_unreach():
    try:
        requests.get("http://x").raise_for_status()
    except requests.RequestException:
        pytest.skip("x")
"""
_NEEDLE_FALSE_PY = '''
"""if resp.status_code >= 500: pytest.skip("x")"""
import os, shutil, pytest, requests
S = "pytest.skip('x') if resp.status_code else 0"
def t_env():
    # if resp.status_code >= 500: pytest.skip("x")
    if shutil.which("go") is None or not os.environ.get("K"):
        pytest.skip("env")
    try:
        requests.get("http://x")
    except requests.ConnectionError:
        pytest.skip("topology absent")
'''
_NEEDLE_TRUE_SH = 'if [[ -z "$x" ]]; then ab_skip "empty"; fi\n'
_NEEDLE_FALSE_SH = (
    '# ab_skip "c"\necho "ab_skip s"\ncat <<EOF\nab_skip heredoc\nEOF\nab_skip_with_reason "d" hardware_not_present\n'
)


def control_needle() -> tuple[bool, str]:
    hits, _ = analyze_python_source(_NEEDLE_TRUE_PY, "<needle>")
    got = {(q, t) for q, t, _ in hits}
    want = {("t_status", "STATUS"), ("t_empty", "EMPTY"), ("t_unreach", "UNREACH")}
    sh_true, _ = analyze_shell_source(_NEEDLE_TRUE_SH, "<needle>")
    f_py, f_py_sites = analyze_python_source(_NEEDLE_FALSE_PY, "<needle>")
    f_sh, f_sh_sites = analyze_shell_source(_NEEDLE_FALSE_SH, "<needle>")
    problems = []
    if not want <= got:
        problems.append(f"golden-TRUE python classes not seen: {sorted(want - got)}")
    if [t for _, t, _ in sh_true] != ["SHELL_BARE_SKIP"]:
        problems.append("golden-TRUE shell bare ab_skip not seen")
    if f_py or f_sh:
        problems.append(f"golden-FALSE produced findings: {f_py + f_sh}")
    if f_py_sites != 2 or f_sh_sites != 1:
        problems.append(f"golden-FALSE skip sites not all seen (py={f_py_sites}/2 sh={f_sh_sites}/1)")
    return (not problems), "; ".join(problems)


# ------------------------------------------------------------------ main
def enumerate_files(root: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "tests"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "git ls-files failed")
    files = sorted({p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p.endswith((".py", ".sh"))})
    return [p for p in files if os.path.isfile(os.path.join(root, p))]


def load_baseline(path: str) -> set[str]:
    rows = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                rows.add(line)
    return rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="CM-NO-FAIL-OPEN-SKIP detection engine")
    ap.add_argument("--root", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--list", action="store_true", help="print the current finding SET only")
    a = ap.parse_args(argv)
    tag = "CM-NO-FAIL-OPEN-SKIP"

    if CONTROL_NEEDLE_ENABLED:
        ok, why = control_needle()
        if not ok:
            print(f"ERROR({tag}): control needle NOT seen — the instrument is blind: {why}", file=sys.stderr)
            return 2
        needle = "control-needle: seen"
    else:
        needle = "control-needle: DISABLED"

    try:
        files = enumerate_files(a.root)
    except (RuntimeError, OSError) as exc:
        print(f"ERROR({tag}): cannot enumerate tests/ under {a.root}: {exc}", file=sys.stderr)
        return 2

    findings: dict[str, tuple[int, str]] = {}
    sites = 0
    unverified = []
    for rel in files:
        try:
            with open(os.path.join(a.root, rel), encoding="utf-8") as fh:
                src = fh.read()
            if rel.endswith(".py"):
                hits, n = analyze_python_source(src, rel)
            else:
                hits, n = analyze_shell_source(src, rel)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            unverified.append(f"{rel}: {exc.__class__.__name__}: {exc}")
            continue
        sites += n
        for key, line in keys_for(rel, hits):
            findings[key] = (line, rel)

    if unverified:
        for u in unverified:
            print(f"UNVERIFIED: {u}", file=sys.stderr)
        print(
            f"ERROR({tag}): {len(unverified)} test file(s) could not be parsed — the tree is UNVERIFIED, not clean",
            file=sys.stderr,
        )
        return 2
    if sites == 0:
        print(
            f"ERROR({tag}): zero skip sites across {len(files)} test file(s) — refused as a BLIND zero "
            "(§11.4.201(6)); a clean corpus and a broken extractor look identical here",
            file=sys.stderr,
        )
        return 2

    current = set(findings)
    if a.list:
        for k in sorted(current):
            print(k)
        return 0

    try:
        baseline = load_baseline(a.baseline)
    except OSError as exc:
        print(f"ERROR({tag}): cannot read baseline {a.baseline}: {exc}", file=sys.stderr)
        return 2

    new = current - baseline
    stale = baseline - current
    if not BASELINE_ENFORCED:
        new, stale = set(), set()
    for k in sorted(current):
        state = "NEW" if k in new else "BASELINED"
        print(f"{state}: {k} (line {findings[k][0]})")
    for k in sorted(stale):
        print(f"STALE: {k} — no live finding; remove the row (the ratchet must tighten, §11.4.227(A))")
    if new:
        print(
            f"FAIL({tag}): {len(new)} NEW fail-open skip(s). A skip that fires on evidence the far side "
            "ANSWERED must classify the response and FAIL, or skip only on environment-derived evidence "
            "(§11.4.69 / §11.4.3). Never add a row to the baseline to silence a new finding.",
            file=sys.stderr,
        )
    rc = 1 if (new or stale) else 0
    verdict = "PASS" if rc == 0 else "FAIL"
    print(
        f"{verdict}: {tag}: {len(current)} finding(s) ({len(current) - len(new)} baselined, {len(new)} new, "
        f"{len(stale)} stale) across {len(files)} test files, {sites} skip sites; {needle}"
    )
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
