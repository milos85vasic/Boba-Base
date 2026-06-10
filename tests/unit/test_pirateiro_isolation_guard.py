"""Standing regression guard — pirateiro test-isolation (§11.4.115/§11.4.135).

`tests/unit/test_plugin_pirateiro.py` injects ``sys.modules["pirateiro"]``
at module scope (import time) with NO teardown. Unless conftest's
``_isolate_download_proxy_modules`` snapshots+restores ``pirateiro`` (i.e.
``pirateiro`` is in ``_POLLUTING_ROOTS``), that stub persists into later
``tests/unit/`` tests — sys.modules pollution exactly of the class
§11.4.50 forbids.

This guard FAILs on a tree where ``pirateiro`` is NOT in
``_POLLUTING_ROOTS`` (the leak survives conftest teardown) and PASSes once
the conftest cleans it. Reproduce the RED with explicit ordering so the
pirateiro test runs first:

    .venv/bin/python -m pytest \\
        tests/unit/test_plugin_pirateiro.py \\
        tests/unit/test_pirateiro_isolation_guard.py \\
        -p no:randomly -q --import-mode=importlib

Keep this file as the permanent §11.4.135 standing regression test — do
NOT delete it.
"""

import sys


def test_pirateiro_not_leaked_into_sys_modules():
    """At the START of a fresh unit test, conftest must have cleaned the
    pirateiro stub installed by ``test_plugin_pirateiro.py`` at import time.

    A leftover ``sys.modules["pirateiro"]`` here means conftest's
    per-unit-test isolation did NOT cover the ``pirateiro`` root → the
    §11.4.50 pollution this guard exists to prevent is live.
    """
    leaked = sys.modules.get("pirateiro")
    assert leaked is None, (
        "sys.modules['pirateiro'] leaked into this test "
        f"(value: {leaked!r}). conftest._POLLUTING_ROOTS must include "
        "'pirateiro' so _isolate_download_proxy_modules snapshots+restores "
        "it around every tests/unit/ test (§11.4.50/§11.4.135)."
    )
