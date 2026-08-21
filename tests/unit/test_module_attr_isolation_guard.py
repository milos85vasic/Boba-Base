"""§11.4.135 regression guard for BOB-135 — one module per file, always.

BOB-135 was an order-dependent failure:
``tests/unit/test_merge_api_route_contracts.py::TestHooksEndpoint::test_list_hooks_after_create``
passed alone and failed in the bulk suite with
``Failed to save hooks: [Errno 13] Permission denied: '/config'``.

Root cause (proven, not inferred — see the BOB-135 investigation): importing
``api.hooks`` has TWO side effects, ``sys.modules["api.hooks"] = mod`` and
``sys.modules["api"].hooks = mod``. A test that purges ``sys.modules["api.hooks"]``
and re-imports it (``tests/unit/api_layer/test_hooks_coverage.py`` and its
siblings do exactly this) re-points BOTH at a FRESH module object. The
``tests/conftest.py::_isolate_download_proxy_modules`` teardown then restored
only the first: ``sys.modules.update(saved)`` put the ORIGINAL object back in
``sys.modules`` while the parent package attribute — an in-place mutation of a
module object the snapshot never copied — kept pointing at the fresh one.

From that moment on there were two live ``api.hooks`` modules with independent
``HOOKS_FILE`` globals, and which one you got depended on how you asked:
``monkeypatch.setattr("api.hooks.HOOKS_FILE", …)`` walks the parent ATTRIBUTE
(pytest's ``derive_importpath``/``resolve``), while ``from api.hooks import
router`` returns the ``sys.modules`` entry. The patch landed on the module the
app did not use, so the app kept the real ``/config/download-proxy/hooks.json``
path and the write was refused with EACCES.

These tests are the permanent guard on the repair. They are deterministic and
order-independent: the first drives the exact purge/re-import/restore sequence
in-process and carries its own control assertion (the divergence must really
occur before the repair, or the test proves nothing — §11.4.201(7)(b)); the
second asserts the invariant plainly, so it also fails if the leak returns via
some other route in a full-suite run.
"""

import os
import sys
import types

import pytest

_SRC_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src")
)
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)


def _live_conftest(request):
    """Return the ALREADY-LOADED root ``tests/conftest.py`` module.

    Deliberately not ``import tests.conftest`` — that would execute a SECOND
    copy of the conftest and test a module the suite does not actually use
    (§11.4.196(F) configured-is-not-in-use). Reaching through the plugin
    manager proves the repair is wired into the conftest pytest really ran.

    Matched by exact path rather than by suffix: another directory under the
    repo could grow its own ``*/tests/conftest.py`` and an ``endswith`` match
    would silently hand back the wrong module.
    """
    wanted = os.path.realpath(str(request.config.rootpath / "tests" / "conftest.py"))
    for plugin in request.config.pluginmanager.get_plugins():
        path = getattr(plugin, "__file__", None)
        if path and os.path.realpath(path) == wanted:
            return plugin
    raise AssertionError(f"{wanted} is not registered as a plugin")


def test_snapshot_restore_keeps_parent_attr_and_sys_modules_in_step(request):
    """The conftest restore must repair the two-module split it creates."""
    conftest = _live_conftest(request)
    resync = getattr(conftest, "_resync_submodule_attrs", None)
    assert resync is not None, (
        "tests/conftest.py must expose _resync_submodule_attrs(); without it the "
        "_isolate_download_proxy_modules restore desynchronises "
        "sys.modules['api.hooks'] from sys.modules['api'].hooks (BOB-135)"
    )

    import api.hooks  # noqa: F401

    original = sys.modules["api.hooks"]
    saved = {"api.hooks": original}

    # Exactly what tests/unit/api_layer/test_hooks_coverage.py does.
    del sys.modules["api.hooks"]
    import api.hooks  # noqa: F401,F811

    fresh = sys.modules["api.hooks"]
    assert fresh is not original, "purge + re-import did not produce a fresh module"

    # Exactly what _isolate_download_proxy_modules teardown does.
    del sys.modules["api.hooks"]
    sys.modules.update(saved)

    # Control needle: the divergence must genuinely exist here, otherwise the
    # assertion below would pass against a no-op repair and prove nothing.
    assert sys.modules["api"].hooks is not sys.modules["api.hooks"], (
        "control failed: the snapshot restore no longer produces the two-module "
        "split, so this test can no longer prove the repair works"
    )

    resync()

    assert sys.modules["api"].hooks is sys.modules["api.hooks"], (
        "BOB-135: sys.modules['api'].hooks and sys.modules['api.hooks'] are "
        "different module objects — a monkeypatch through one is invisible to "
        "code that imported the other"
    )


def test_orphaned_parent_attribute_is_dropped(request):
    """A parent attribute with no sys.modules entry must not survive.

    pytest's ``resolve()`` reads the parent attribute BEFORE it tries an
    import, so an orphan left behind by a purge would keep being handed to
    ``monkeypatch.setattr("api.hooks.…")`` forever.
    """
    conftest = _live_conftest(request)
    resync = getattr(conftest, "_resync_submodule_attrs", None)
    assert resync is not None

    import api.hooks  # noqa: F401

    orphan = sys.modules["api.hooks"]
    del sys.modules["api.hooks"]

    assert getattr(sys.modules["api"], "hooks", None) is orphan, (
        "control failed: the parent attribute was not left orphaned by the purge"
    )

    resync()

    assert not hasattr(sys.modules["api"], "hooks"), (
        "BOB-135: a parent-package attribute outlived its sys.modules entry"
    )


def test_api_hooks_module_identity_is_consistent():
    """Plain invariant — fails in a bulk run if the leak returns by any route."""
    import api.hooks  # noqa: F401

    if "api" not in sys.modules or "api.hooks" not in sys.modules:
        pytest.fail("api / api.hooks unexpectedly absent from sys.modules")

    assert sys.modules["api"].hooks is sys.modules["api.hooks"], (
        "BOB-135 regression: two live api.hooks module objects"
    )


def test_isolation_fixture_actually_invokes_the_resync(request):
    """§11.4.196(F): the repair must be WIRED, not merely present.

    The tests above reach into the conftest and CALL ``_resync_submodule_attrs``
    themselves, so they keep passing if someone deletes the two call sites in
    ``_isolate_download_proxy_modules`` and leaves the function behind — a
    perfectly plausible refactor that silently restores the BOB-135 defect in
    full. Validating the function is not validating the fixture.

    So this one drives the REAL fixture generator: setup, the exact
    purge-and-re-import an api_layer test performs, then a real teardown via
    ``gen.close()`` (which runs the fixture's ``finally:`` block), and asserts
    the invariant afterwards. A cut call site fails here.
    """
    conftest = _live_conftest(request)
    fixture_def = conftest._isolate_download_proxy_modules
    raw = getattr(fixture_def, "__wrapped__", None)
    assert raw is not None, (
        "cannot reach the undecorated _isolate_download_proxy_modules "
        f"generator: {type(fixture_def).__name__} exposes no __wrapped__ on "
        f"pytest {pytest.__version__}. The fixture-object API changed — "
        "re-point this test at the raw generator so the wiring stays guarded."
    )

    # Import BEFORE the fixture starts so api / api.hooks are guaranteed to be
    # in the snapshot it takes at setup, and therefore restored at teardown.
    # Otherwise the final assertion would hit a KeyError instead of measuring
    # what it is meant to measure.
    import api.hooks  # noqa: F401

    # The fixture only engages for tests under tests/unit/ — it reads
    # request.node.fspath — so hand it a probe path inside that tree.
    probe_path = str(request.config.rootpath / "tests" / "unit" / "wiring_probe.py")
    stub_request = types.SimpleNamespace(node=types.SimpleNamespace(fspath=probe_path))

    gen = raw(stub_request)
    next(gen)
    try:
        original = sys.modules["api.hooks"]
        del sys.modules["api.hooks"]
        import api.hooks  # noqa: F401,F811

        fresh = sys.modules["api.hooks"]
        # Control needle: with no genuine re-import there is nothing for the
        # teardown to desynchronise and the final assertion would be vacuous.
        assert fresh is not original, (
            "control failed: purge + re-import produced no fresh module, so "
            "this test cannot detect a missing resync"
        )
    finally:
        gen.close()

    # Control needle: the fixture must actually have taken its snapshot/restore
    # path — on the non-unit early return nothing is restored and this test
    # would measure nothing (§11.4.201(7)(b)).
    assert sys.modules["api.hooks"] is original, (
        "control failed: _isolate_download_proxy_modules never engaged for the "
        "probe path — probe not under tests/unit/? — so this test cannot "
        "detect a missing resync"
    )

    assert sys.modules["api"].hooks is sys.modules["api.hooks"], (
        "BOB-135 regression: _isolate_download_proxy_modules no longer invokes "
        "_resync_submodule_attrs, so its sys.modules restore leaves a stale "
        "parent-package attribute behind and api.hooks splits in two again"
    )
