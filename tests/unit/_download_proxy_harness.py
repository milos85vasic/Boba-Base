"""Shared unit-test harness for ``plugins/download_proxy.py``.

Single source of truth for the pieces the ``download_proxy`` unit tests
share: the one-time module bootstrap (the plugin is not importable as a
normal package — it is loaded by path under the module name
``download_proxy``), the ``DownloadHandler`` factory with mocked socket
streams, and the urlopen response double.

Why this file exists (§11.4.251 — byte-identical-fork prohibition):
``_make_handler`` and ``_mock_response`` previously existed as
byte-identical copies in ``test_download_proxy_deep.py`` and
``test_download_proxy_extra_guards.py``, together with an identical
bootstrap block. One copy was deleted during the themed-UI removal on
2026-09-01 while 23 tests in the other file still called it, producing 23
``NameError``s. Factoring the fork into one module makes that failure
mode structurally impossible: there is now exactly one definition to
delete, and deleting it fails every dependent file loudly at import.

The leading underscore keeps pytest from collecting this as a test
module. It is imported by sibling test files after they insert this
directory on ``sys.path`` — required because the suite runs under
``--import-mode=importlib`` (see ``pyproject.toml``), where sibling
modules are not implicitly importable.

Not a fixture: the surviving call sites use ``_make_handler(...)`` as a
plain function inside ``with patch(...)`` blocks, so a conftest fixture
would force a rewrite of every call site without changing behaviour.
"""

from __future__ import annotations

import importlib.util
import io
import os
import sys
from unittest.mock import MagicMock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DP_PATH = os.path.join(_REPO_ROOT, "plugins", "download_proxy.py")

sys.path.insert(0, os.path.join(_REPO_ROOT, "plugins"))

if "download_proxy" not in sys.modules:
    _dp_spec = importlib.util.spec_from_file_location("download_proxy", _DP_PATH)
    _dp_mod = importlib.util.module_from_spec(_dp_spec)
    sys.modules["download_proxy"] = _dp_mod
    _dp_spec.loader.exec_module(_dp_mod)
else:
    _dp_mod = sys.modules["download_proxy"]

download_proxy = _dp_mod

DownloadHandler = _dp_mod.DownloadHandler
download_via_nova2dl = _dp_mod.download_via_nova2dl
identify_plugin = _dp_mod.identify_plugin
run_server = _dp_mod.run_server


def _make_handler(path="/test", method="GET", body=None, headers=None):
    """Create a ``DownloadHandler`` with mocked socket streams.

    ``wfile`` is a real ``BytesIO`` and therefore records ONLY the response
    BODY. ``send_response`` / ``send_header`` / ``end_headers`` are Mocks,
    so status lines and headers never reach ``wfile`` — assert on the
    corresponding mock's ``call_args_list`` for header behaviour.
    """
    handler = DownloadHandler.__new__(DownloadHandler)
    handler.path = path
    handler.command = method
    handler.headers = headers or {}
    handler.wfile = io.BytesIO()
    handler.rfile = io.BytesIO(body or b"")
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.client_address = ("127.0.0.1", 12345)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    handler.address_string = MagicMock(return_value="127.0.0.1")
    return handler


def _mock_response(status, headers, body):
    """Context-manager double for ``urllib.request.urlopen``'s response."""
    resp = MagicMock()
    resp.status = status
    resp.headers = headers
    resp.read = MagicMock(return_value=body)
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def sent_headers(handler):
    """Return ``[(name, value), ...]`` actually relayed via ``send_header``.

    The proxy relays upstream headers through ``send_header``, which the
    fixture mocks — so this, not ``handler.wfile``, is the recording
    surface for header assertions.
    """
    return [(c[0][0], c[0][1]) for c in handler.send_header.call_args_list]
