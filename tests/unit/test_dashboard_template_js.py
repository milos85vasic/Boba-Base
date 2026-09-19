"""Guard the Jinja dashboard's inline JavaScript against scope/syntax defects.

WHY THIS EXISTS (review #3 finding F1, 2026-09-01)
--------------------------------------------------
A tagging helper `_tagFacts` was added to
``download-proxy/src/ui/templates/dashboard.html`` and was accidentally placed
INSIDE ``generateMagnet()`` while being called from three SIBLING functions
(``doSchedule`` / ``doDownload`` / ``doDownloadTorrent``). A function
declaration nested in another function is invisible to its siblings, so every
one of those buttons would have thrown

    ReferenceError: _tagFacts is not defined

synchronously, BEFORE its fetch fired — regressing them from
working-but-untagged to not working at all.

Nothing caught it. The edit was applied at a text anchor whose first match
happened to fall inside ``generateMagnet``; HTML has no compile step; and NO
TEST ANYWHERE READ THIS TEMPLATE'S JAVASCRIPT (§11.4.224 — a code change
shipped with zero coverage). "The patch applied cleanly" was mistaken for
"the code works".

These tests close that hole for the whole script block, not just for
`_tagFacts`: a syntax error or a newly-nested helper now fails here.

HONEST BOUNDARY (§11.4.6): this asserts the script PARSES and that helpers used
across functions are reachable at top-level scope. It does NOT execute the
dashboard against a live DOM — that is the browser suite's job
(``frontend/e2e/``). It is a cheap structural guard, not a functional one.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / "download-proxy" / "src" / "ui" / "templates" / "dashboard.html"


def _script_block() -> str:
    """Return the largest inline <script> body from the template."""
    html = _TEMPLATE.read_text(encoding="utf-8")
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
    assert blocks, "dashboard.html has no inline <script> block"
    return max(blocks, key=len)


@pytest.fixture(scope="module")
def script() -> str:
    if not _TEMPLATE.is_file():
        pytest.skip(f"template not present at {_TEMPLATE}")
    return _script_block()


_TS_DIR = _REPO_ROOT / "frontend" / "node_modules" / "typescript"

#: Node program that parses the script with the REAL TypeScript parser and
#: prints every function reachable at top-level scope, one per line.
#: Covers both `function f(){}` and `var f = function(){}` / `const f = () => {}`,
#: because all three are callable from a sibling and the earlier scanner only
#: understood the first (a §11.4.201(1) false-negative on the other two).
_TS_PROBE = r"""
const ts = require(process.argv[2]);
const fs = require('fs');
const src = fs.readFileSync(process.argv[3], 'utf8');
const sf = ts.createSourceFile('d.js', src, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
const names = new Set();
for (const st of sf.statements) {
  if (ts.isFunctionDeclaration(st) && st.name) names.add(st.name.text);
  if (ts.isVariableStatement(st)) {
    for (const d of st.declarationList.declarations) {
      if (!d.name || !d.initializer) continue;
      if (ts.isFunctionExpression(d.initializer) || ts.isArrowFunction(d.initializer)) {
        names.add(d.name.getText(sf));
      }
    }
  }
}
for (const n of names) console.log(n);
"""


def _top_level_function_names(src: str) -> set[str]:
    """Names of functions reachable at TOP-LEVEL scope, per a real JS parser.

    WHY A PARSER AND NOT A SCANNER (review #4, IMPORTANT-3)
    ------------------------------------------------------
    Two hand-rolled versions of this helper were wrong in two different ways,
    which is the tell §11.4.250 names: when layer after layer is needed to prop
    up a heuristic, the heuristic is the defect.

      v1 used INDENTATION as a proxy for scope. A paired mutation proved it
      worthless — re-nesting the helper without changing its indentation left
      it completely blind.

      v2 counted BRACE DEPTH while skipping strings and comments, but had no
      REGEX-LITERAL handling. `/filename="?([^"]+)"?/` at dashboard.html:1155
      contains a double quote, so the scanner opened a phantom string there and
      went blind over ~170 lines. Inside that region it FAILED CORRECT CODE —
      a §11.4.201(1) false-positive refusal, the same defect class this suite
      exists to catch. Its depth happened to land back on 0, so the tests still
      passed and nothing revealed the blindness.

    A JavaScript tokenizer is genuinely hard: regex-vs-division is ambiguous
    without parser context, and template literals nest arbitrarily. Rather than
    add a third layer, this asks TypeScript — already vendored for the Angular
    app — which is the same parser the real toolchain uses.

    HONEST SKIP (§11.4.3): when node or the vendored TypeScript is absent this
    raises RuntimeError and the callers skip with a named reason. It never
    silently falls back to the broken scanner — a quiet downgrade to a known-bad
    instrument is worse than an honest "could not check" (§11.4.201(6)).
    """
    node = shutil.which("node")
    if not node or not _TS_DIR.is_dir():
        raise RuntimeError(
            f"node={'present' if node else 'ABSENT'}, "
            f"typescript={'present' if _TS_DIR.is_dir() else 'ABSENT'}"
        )
    with tempfile.TemporaryDirectory() as td:
        js = Path(td) / "d.js"
        js.write_text(src, encoding="utf-8")
        probe = Path(td) / "probe.js"
        probe.write_text(_TS_PROBE, encoding="utf-8")
        proc = subprocess.run(
            [node, str(probe), str(_TS_DIR), str(js)],
            capture_output=True, text=True, timeout=60,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"TypeScript parse failed: {proc.stderr[:400]}")
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


class TestDashboardScriptIntegrity:
    def test_script_block_parses(self, script: str) -> None:
        """The inline JS must be syntactically valid.

        Uses `node --check` when node is available; honest skip otherwise
        (§11.4.3) — a missing toolchain is an environment condition.
        """
        node = shutil.which("node")
        if not node:
            pytest.skip("SKIP-reason=node_absent: install Node to syntax-check the inline script")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(script)
            path = fh.name
        try:
            proc = subprocess.run([node, "--check", path], capture_output=True, text=True)
        finally:
            Path(path).unlink(missing_ok=True)
        assert proc.returncode == 0, f"dashboard inline JS is not valid:\n{proc.stderr}"

    def test_tag_facts_helper_is_top_level(self, script: str) -> None:
        """`_tagFacts` must be reachable from its sibling call sites.

        This is the direct F1 regression guard. It FAILS against the shipped
        defect (the helper nested inside `generateMagnet`) and passes once it
        is hoisted.
        """
        if "_tagFacts" not in script:
            pytest.skip("SKIP-reason=helper_absent: _tagFacts is not used in this template")
        try:
            top = _top_level_function_names(script)
        except RuntimeError as exc:
            pytest.skip(f"SKIP-reason=parser_absent: {exc}")
        assert "_tagFacts" in top, (
            "_tagFacts is declared but NOT at top-level scope — it is nested inside "
            "another function and its sibling call sites will throw "
            "'ReferenceError: _tagFacts is not defined' before their fetch fires"
        )

    def test_every_cross_function_helper_is_reachable(self, script: str) -> None:
        """Generalised guard: any `_`-prefixed helper CALLED in this script must
        be declared at top level.

        F1 was one instance of a class. Pinning only `_tagFacts` would let the
        next nested helper through, so the whole underscore-helper namespace is
        checked. (Underscore-prefixed only: that is this template's convention
        for its own helpers, and it keeps browser/library globals out of scope.)
        """
        try:
            top = _top_level_function_names(script)
        except RuntimeError as exc:
            pytest.skip(f"SKIP-reason=parser_absent: {exc}")
        declared = {
            m.group(1)
            for m in re.finditer(r"function\s+(_[A-Za-z_$][\w$]*)\s*\(", script)
        }
        called = {
            m.group(1)
            for m in re.finditer(r"(?<![\w$.])(_[A-Za-z_$][\w$]*)\s*\(", script)
        }
        nested_but_called = sorted((declared & called) - top)
        assert not nested_but_called, (
            "these helpers are called but declared inside another function, so "
            f"sibling call sites will throw ReferenceError: {nested_but_called}"
        )
