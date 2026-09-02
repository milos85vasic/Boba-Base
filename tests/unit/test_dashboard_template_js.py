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


def _top_level_function_names(src: str) -> set[str]:
    """Names of functions declared at BRACE DEPTH ZERO of the script block.

    SCOPE IS BRACES, NOT INDENTATION. The first version of this helper used
    indentation as a proxy for scope, and a paired mutation proved it worthless:
    re-nesting `_tagFacts` inside `generateMagnet` WITHOUT changing its
    indentation left the detector completely blind, so the guard passed against
    the exact defect it was written for (§1.1 — a test that cannot catch its own
    negation is a bluff). JavaScript scope is determined by braces, so braces
    are what this counts.

    String literals, template literals, regex-ish quotes and both comment forms
    are skipped so that a `{` inside them cannot shift the depth.
    """
    depth = 0
    names: set[str] = set()
    i = 0
    n = len(src)
    fn_re = re.compile(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")

    while i < n:
        ch = src[i]

        # line comment
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        # block comment
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        # string / template literal
        if ch in "\"'`":
            quote = ch
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            continue

        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth -= 1
            i += 1
            continue

        if depth == 0:
            m = fn_re.match(src, i)
            if m:
                names.add(m.group(1))
                i = m.end()
                continue
        i += 1

    return names


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
        assert "_tagFacts" in _top_level_function_names(script), (
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
        top = _top_level_function_names(script)
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
