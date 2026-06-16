"""Shared harness for stress + chaos tests of the multi-word query
URL-encoding fix (§11.4.85 stress + chaos mandate).

This conftest provides the PROVEN plugin-driving harness from
``tests/unit/test_plugin_multiword_query_encoding.py`` (read + reused, not
re-invented) so the stress/chaos suites drive the REAL plugin ``search()``
and capture the exact URL handed to ``helpers.retrieve_url``.

Captured-evidence (§11.4.5/§11.4.69): every test writes a small artifact
under ``$BOBA_SC_EVIDENCE_DIR`` (default ``/Volumes/T7/tmp/stress_chaos_evidence``);
the per-test fixture exposes ``evidence_dir`` + an ``emit()`` helper.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGINS = REPO / "plugins"
COMMUNITY = PLUGINS / "community"
MERGE_SRC = REPO / "download-proxy" / "src"

# The AUTHORITATIVE oracle: this is the exact regex http.client uses in
# putrequest() to reject a URL — it raises ``InvalidURL`` (a ValueError /
# HTTPException subclass) on any char it matches. In Python 3.13
# urllib.request.Request() does NOT validate at construction time (the check
# fires at urlopen), so we replicate urllib's real check here rather than
# relying on Request() raising (which it no longer does). Pattern = [\x00-\x20\x7f].
_DISALLOWED_URL_CHAR_RE = http.client._contains_disallowed_url_pchar_re  # noqa: SLF001


def url_is_urllib_acceptable(url: str) -> bool:
    """True iff urllib/http.client would accept this URL's path without
    raising InvalidURL — i.e. it contains none of urllib's disallowed
    control characters. This is the same predicate urllib applies."""
    return _DISALLOWED_URL_CHAR_RE.search(url) is None


def url_has_raw_space(url: str) -> bool:
    """The specific defect class the session fix addressed: a raw space in
    the constructed URL (the multi-word-query crash trigger)."""
    return " " in url


def load_classifier():
    """Import _classify_plugin_stderr as a proper package member.

    The merge_service.search module uses relative imports, so it must be
    imported as ``merge_service.search`` with download-proxy/src on the path
    (NOT via spec_from_file_location, which has no parent package)."""
    if str(MERGE_SRC) not in sys.path:
        sys.path.insert(0, str(MERGE_SRC))
    try:
        from merge_service.search import _classify_plugin_stderr
    except Exception as exc:  # pragma: no cover - dependency gap
        pytest.skip(  # allow-skip: import-time dependency gap (unit harness, not a runtime-service availability skip)
            f"merge_service.search not importable: {exc}"
        )
    return _classify_plugin_stderr

# Representative subset of the fixed plugins that interpolate the raw query
# into a request URL/path AND are directly drivable under a retrieve_url stub
# (snowfl is covered separately via its Parser-fake path — its token bootstrap
# fetches index.html before the query URL, so a capture pass would be
# misleading per §11.4.6).
FIXED_PLUGINS = [
    "eztv",
    "torlock",
    "glotorrents",
    "torrentscsv",
    "limetorrents",
]


def _evidence_dir() -> Path:
    d = Path(os.environ.get("BOBA_SC_EVIDENCE_DIR", "/Volumes/T7/tmp/stress_chaos_evidence"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _plugin_path(name: str) -> Path:
    p = PLUGINS / f"{name}.py"
    if p.exists():
        return p
    cp = COMMUNITY / f"{name}.py"
    if cp.exists():
        return cp
    raise FileNotFoundError(f"Plugin {name} not found")


def _load_plugin(name: str):
    """Import a plugin outside the nova3 harness with stubbed deps."""
    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: None  # type: ignore[attr-defined]

    class _SR:
        pass

    np_mod.SearchResults = _SR  # type: ignore[attr-defined]
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url, *a, **k: ""  # type: ignore[attr-defined]
    helpers_mod.download_file = lambda url: url  # type: ignore[attr-defined]
    sys.modules["helpers"] = helpers_mod

    spec = importlib.util.spec_from_file_location(f"plugin_sc_{name}", _plugin_path(name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def drive_search(name: str, query: str) -> list[str]:
    """Run the plugin's real search() with ``query`` and return every URL
    it tried to fetch. retrieve_url is replaced by a URL-capturing no-op
    that returns an empty body so the pagination loop terminates."""
    mod = _load_plugin(name)
    captured: list[str] = []

    def _capture(url, *a, **k):
        captured.append(url)
        return ""

    sys.modules["helpers"].retrieve_url = _capture  # type: ignore[attr-defined]
    # Some plugins bound the helper at import time as a module global.
    if hasattr(mod, "retrieve_url"):
        mod.retrieve_url = _capture  # type: ignore[attr-defined]

    cls = getattr(mod, name)
    instance = cls()
    # Capture every URL the plugin BUILDS, even if it raises afterwards
    # (e.g. torrentscsv json.loads("") -> JSONDecodeError on the empty stub
    # body AFTER the request URL was already constructed + captured). The
    # URL-encoding assertion inspects the constructed URL regardless of any
    # downstream parse fault on the stubbed empty body.
    try:
        instance.search(query, "all")
    except Exception:
        pass
    return captured


class _Evidence:
    def __init__(self, name: str) -> None:
        self.dir = _evidence_dir()
        self._name = name
        self.records: list[dict] = []

    def add(self, **kw) -> None:
        self.records.append(kw)

    def emit(self, summary: dict) -> Path:
        path = self.dir / f"{self._name}.json"
        payload = {"summary": summary, "records": self.records}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return path


@pytest.fixture
def evidence(request) -> _Evidence:
    safe = request.node.name.replace("/", "_").replace("[", "_").replace("]", "_")
    return _Evidence(safe)
