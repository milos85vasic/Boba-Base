"""Standing regression guard — sys.modules injection coverage (§11.4.135/§11.4.238).

WHAT THIS CATCHES
-----------------
``tests/conftest.py``'s ``_POLLUTING_ROOTS`` names the module roots that
``_isolate_download_proxy_modules`` snapshots + restores around every
``tests/unit/`` test. A unit test that injects ``sys.modules["<name>"] = mod``
for a name NOT in that tuple leaks that entry into every later test in the
session.

The leak is dangerous because it is INVISIBLE: ``plugins/`` is not on
``sys.path`` by default, so a bare ``import <plugin>`` cannot resolve from
disk. A test doing a bare import therefore passes only when some earlier test
happened to register the module — i.e. it passes or fails on the
``pytest-randomly`` seed. That is exactly the defect fixed in
``tests/unit/test_plugin_rutracker.py`` (7 tests resolving ``from rutracker
import ...`` purely off an earlier test's side effect).

WHY A GUARD, NOT JUST A LONGER LIST
-----------------------------------
Until 2026-09-01 ``_POLLUTING_ROOTS`` was a REACTIVE denylist — a name was
appended only after its leak had already produced a measured failure. Nothing
tied the tuple to the real set of injection sites, so it drifted: measured by
AST scan on 2026-09-01, 49 top-level names were injected by ``tests/unit/`` and
only 11 were covered. Extending the tuple fixes today's 36; only a mechanical
re-derivation stops the 37th from being minted silently tomorrow. This guard is
that mechanism (§11.4.238 — the class was found by an agent, not by a gate).

SCOPE — function-scope injections only
--------------------------------------
``_isolate_download_proxy_modules`` snapshots at setup and restores at
teardown. A name already present at setup (registered at MODULE/collection
scope) is RESTORED, not purged, so listing it in ``_POLLUTING_ROOTS`` would not
stop its leak; those need the dedicated handling ``pirateiro`` already has.
This guard therefore asserts coverage for names injected from inside a function
body, and carries an explicit, justified exemption set for the rest.

Keep this file as the permanent §11.4.135 standing regression test — do NOT
delete it.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_TESTS_UNIT = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_UNIT.parent.parent

# Names injected at MODULE (collection) scope. A _POLLUTING_ROOTS entry cannot
# clean these -- the fixture's snapshot already contains them at every test's
# setup, so teardown restores rather than purges. Each needs its own handling
# and each is justified here (§11.4.6 — enumerated, never silently skipped).
_MODULE_SCOPE_EXEMPT: dict[str, str] = {
    # Re-registered before pirateiro-file tests and popped after EVERY unit test
    # by _isolate_download_proxy_modules; guarded by
    # tests/unit/test_pirateiro_isolation_guard.py.
    "pirateiro": "explicitly re-registered + popped by conftest",
    # tests/unit/_download_proxy_harness.py is a SHARED harness that other test
    # files import; purging it between tests would break those importers.
    "download_proxy": "shared cross-file harness, must persist",
}


def _sys_modules_key(node: ast.AST) -> str | None:
    """Return the literal key of a ``sys.modules[<key>]`` subscript, else None.

    A non-literal key (``sys.modules[spec.name]``) returns ``None`` — it cannot
    be resolved statically and is reported separately by the scanner below
    rather than silently treated as absent (§11.4.201(6) false-null).
    """
    if not isinstance(node, ast.Subscript):
        return None
    value = node.value
    if not (
        isinstance(value, ast.Attribute)
        and value.attr == "modules"
        and isinstance(value.value, ast.Name)
        and value.value.id == "sys"
    ):
        return None
    key = node.slice
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    return None


class _InjectionScanner(ast.NodeVisitor):
    """Collect ``sys.modules`` injections, split by module vs function scope."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._depth = 0
        self.module_scope: set[str] = set()
        self.func_scope: set[str] = set()
        self.dynamic: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def _record(self, name: str) -> None:
        (self.func_scope if self._depth else self.module_scope).add(name)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            key = _sys_modules_key(target)
            if key is not None:
                self._record(key)
            elif isinstance(target, ast.Subscript) and _is_sys_modules(target):
                self.dynamic.add(ast.unparse(target.slice))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "setdefault"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "modules"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "sys"
            and node.args
        ):
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                self._record(arg.value)
            else:
                self.dynamic.add(ast.unparse(arg))
        self.generic_visit(node)


def _is_sys_modules(node: ast.Subscript) -> bool:
    value = node.value
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "modules"
        and isinstance(value.value, ast.Name)
        and value.value.id == "sys"
    )


def _scan_unit_tests() -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    """AST-scan every ``tests/unit/`` source file for sys.modules injections.

    Returns ``(func_scope, module_scope, dynamic)`` where the first two map a
    top-level module name to the set of files that inject it.
    """
    func_scope: dict[str, set[str]] = {}
    module_scope: dict[str, set[str]] = {}
    dynamic: set[str] = set()
    for path in sorted(_TESTS_UNIT.rglob("*.py")):
        if path.name == "conftest.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        scanner = _InjectionScanner(str(path))
        scanner.visit(tree)
        rel = str(path.relative_to(_REPO_ROOT))
        for name in scanner.func_scope:
            func_scope.setdefault(name.split(".")[0], set()).add(rel)
        for name in scanner.module_scope:
            module_scope.setdefault(name.split(".")[0], set()).add(rel)
        dynamic |= scanner.dynamic
    return func_scope, module_scope, dynamic


def _polluting_roots() -> tuple[str, ...]:
    """Read ``_POLLUTING_ROOTS`` from the live conftest module."""
    from tests import conftest as _conftest

    return tuple(_conftest._POLLUTING_ROOTS)


def test_scanner_is_not_blind():
    """CONTROL NEEDLE (§11.4.201(7)(b)) — a NULL result is not evidence.

    A scanner that silently matched nothing would make the coverage assertion
    below pass vacuously. Prove the instrument can see through the SAME code
    path before trusting any zero it reports: a known-present function-scope
    injection MUST be found, and a name nobody injects MUST NOT be.
    """
    func_scope, module_scope, _ = _scan_unit_tests()

    # Positive needle: test_plugin_rutracker.py registers "rutracker" inside its
    # _import_rutracker_module() helper -- a function-scope injection.
    assert "rutracker" in func_scope, (
        "control needle MISSING: the scanner found no function-scope injection "
        "of 'rutracker', but tests/unit/test_plugin_rutracker.py has one. The "
        "scanner is blind -- every coverage result it produces is a false null."
    )
    # Positive needle for the other arm: pirateiro is module-scope.
    assert "pirateiro" in module_scope, (
        "control needle MISSING: the scanner found no module-scope injection of "
        "'pirateiro', but tests/unit/test_plugin_pirateiro.py has one."
    )
    # Negative control: the scanner must not report a name nobody injects.
    assert "zzz_not_injected_anywhere" not in func_scope
    assert "zzz_not_injected_anywhere" not in module_scope


def test_every_function_scope_injection_is_cleaned_between_tests():
    """Every function-scope ``sys.modules`` injection is covered by conftest.

    An uncovered name survives ``_isolate_download_proxy_modules``' teardown and
    leaks into every later test in the session, silently satisfying bare
    ``import <name>`` statements that could never resolve from ``sys.path``.
    That makes any test relying on it pass or fail on the RNG seed.
    """
    func_scope, _, _ = _scan_unit_tests()
    roots = set(_polluting_roots())

    uncovered = {
        name: sorted(files)
        for name, files in sorted(func_scope.items())
        if name not in roots and name not in _MODULE_SCOPE_EXEMPT
    }

    assert not uncovered, (
        "These module names are injected into sys.modules from inside a "
        "tests/unit/ function body but are NOT in conftest._POLLUTING_ROOTS, so "
        "they leak across test files (§11.4.50):\n"
        + "\n".join(f"  {n}: {files}" for n, files in uncovered.items())
        + "\n\nFix: add each name to _POLLUTING_ROOTS in tests/conftest.py. If a "
        "name genuinely must persist across tests, add it to "
        "_MODULE_SCOPE_EXEMPT in this file WITH a justification."
    )


def test_module_scope_injections_stay_enumerated():
    """Module-scope injections are enumerated, never silently absorbed.

    A name registered at collection time cannot be cleaned by a
    ``_POLLUTING_ROOTS`` entry (the fixture restores its setup snapshot). Each
    one therefore needs bespoke handling, and a NEW one appearing without that
    handling must be surfaced rather than assumed safe (§11.4.6).
    """
    _, module_scope, _ = _scan_unit_tests()
    roots = set(_polluting_roots())

    unaccounted = {
        name: sorted(files)
        for name, files in sorted(module_scope.items())
        if name not in roots and name not in _MODULE_SCOPE_EXEMPT
    }

    assert not unaccounted, (
        "These module names are injected into sys.modules at MODULE (collection) "
        "scope and are neither in _POLLUTING_ROOTS nor in this file's "
        "_MODULE_SCOPE_EXEMPT:\n"
        + "\n".join(f"  {n}: {files}" for n, files in unaccounted.items())
        + "\n\nA _POLLUTING_ROOTS entry does NOT clean a module-scope injection "
        "(the fixture restores the setup snapshot). Give it dedicated handling "
        "like conftest does for 'pirateiro', then record it in "
        "_MODULE_SCOPE_EXEMPT with a justification."
    )


@pytest.mark.parametrize(
    "name",
    ["rutracker", "kinozal", "piratebay", "nnmclub", "eztv", "torlock"],
)
def test_plugin_stub_not_leaked_into_this_test(name: str):
    """RUNTIME arm — no plugin stub is live at the START of an unrelated test.

    Source-layer coverage (above) proves the LIST is complete; this proves the
    FIXTURE actually acts on it. A leftover entry here means the teardown did
    not purge a plugin stub some earlier test installed — the §11.4.50 leak
    itself, observed at runtime rather than inferred from the source
    (§11.4.226 evidence class).

    Generalises tests/unit/test_pirateiro_isolation_guard.py from one name to
    the plugin family. Reproduce a RED with explicit ordering, e.g.:

        .venv/bin/python -m pytest \\
            tests/unit/test_plugin_kinozal.py \\
            tests/unit/test_sys_modules_isolation_guard.py \\
            -p no:randomly -q
    """
    import sys

    leaked = sys.modules.get(name)
    assert leaked is None, (
        f"sys.modules[{name!r}] leaked into this test (value: {leaked!r}). "
        f"conftest._POLLUTING_ROOTS must include {name!r} so "
        "_isolate_download_proxy_modules purges it after every tests/unit/ test "
        "(§11.4.50/§11.4.135)."
    )
