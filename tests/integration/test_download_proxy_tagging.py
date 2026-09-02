#!/usr/bin/env python3
"""Content-tagging guard for the :7186 tracker-intercept add path.

CONTEXT (remediation 2026-09-01, IMPORTANT-2 of the independent re-review).
Three `/api/v2/torrents/add` call sites in `download-proxy/src/api/routes.py`
were wired to the shared tag builder. Two others were not:

* `webui-bridge.py:handle_torrent_download` — fixed and guarded in
  `tests/integration/test_webui_bridge_auth_live.py`.
* `plugins/download_proxy.py` — the :7186 proxy's private-tracker intercept,
  guarded HERE. It already rewrote `params["urls"]` to the locally downloaded
  `file://` path and re-encoded the form, so it is the last point that can
  attach tags before qBittorrent sees the add; it attached none, so a
  RuTracker download performed through the browser's own WebUI landed with
  `tags=''`.

SCOPE, STATED HONESTLY (§11.4.6 / §11.4.108). This file exercises the
REPOSITORY SOURCE at `plugins/download_proxy.py` — the SOURCE layer. It does
NOT by itself prove the fix reached the RUNTIME layer: the running :7186 proxy
imports its copy from `/config/qBittorrent/nova3/engines`, which
`install-plugin.sh` stages. A source-green run here therefore means "the code
is correct", never "the deployed proxy is tagging".

The runtime layer was verified separately, in the live container, before this
guard was written — `merge_service` is importable from the engines working
directory inside `qbittorrent-proxy` (measured 2026-09-01: the shared builder
returned `720p,Boba,Боба` there). Deploying the fixed bytes is the operator's
documented `./install-plugin.sh` + `./start.sh --reload-plugins` step and is
recorded as owed, not claimed done.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SOURCE = REPO_ROOT / "plugins" / "download_proxy.py"
MERGE_SERVICE_SRC = REPO_ROOT / "download-proxy" / "src"


@pytest.fixture(scope="module")
def proxy_module():
    """Import `plugins/download_proxy.py` under a private module name."""
    if not PLUGIN_SOURCE.is_file():
        pytest.skip(f"SKIP-REASON hardware_not_present: {PLUGIN_SOURCE} missing")
    if str(MERGE_SERVICE_SRC) not in sys.path:
        sys.path.insert(0, str(MERGE_SERVICE_SRC))
    spec = importlib.util.spec_from_file_location(
        "boba_download_proxy_under_test", PLUGIN_SOURCE
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _tags(value):
    return {t.strip() for t in (value or "").split(",") if t.strip()}


def test_intercept_helper_exists(proxy_module):
    """RED before the fix: the intercept has no tag builder at all."""
    assert hasattr(proxy_module, "build_tag_field"), (
        "plugins/download_proxy.py exposes no tag builder — its tracker "
        "intercept rewrites urls and re-encodes the form but attaches no "
        "tags, so every intercepted download lands with tags='' (IMPORTANT-2)"
    )


def test_derived_tags_come_from_the_shared_builder(proxy_module):
    """The dimensions must match `merge_service.tagging`, not a local fork."""
    from merge_service.tagging import build_tags, tags_to_qbittorrent_field

    name = "/tmp/Some.Movie.2019.1080p.BluRay.x264-GRP.torrent"
    derived = _tags(proxy_module.build_tag_field(name))

    assert derived, "no tags derived from a filename that carries a quality tier"
    assert derived == _tags(
        tags_to_qbittorrent_field(build_tags(name="Some.Movie.2019.1080p.BluRay.x264-GRP.torrent"))
    ), (
        f"derived tags {derived!r} diverge from the shared builder — the "
        "intercept has forked the algorithm (§11.4.251)"
    )
    assert {"Boba", "Боба", "1080p"} <= derived, f"expected tags missing from {derived!r}"
    assert not any(t.startswith("boba-") for t in derived), (
        f"`boba-` prefixed tag leaked into {derived!r} — reserved debris shape"
    )


def test_tagging_never_raises_on_a_hostile_name(proxy_module):
    """Tagging must NEVER block an add — a bad input yields '' , never an error."""
    for hostile in (None, "", "   ", "/tmp/", "a" * 4096, "/tmp/no,commas,allowed.torrent"):
        result = proxy_module.build_tag_field(hostile)
        assert isinstance(result, str), f"build_tag_field({hostile!r}) returned {result!r}"


def test_client_tags_are_preserved_not_overwritten(proxy_module):
    """A tag the user typed in the WebUI add dialog must survive the merge."""
    merged = _tags(proxy_module.merge_tag_values("my-own-tag,Another", "1080p,Boba,Боба"))
    assert {"my-own-tag", "Another"} <= merged, (
        f"client tags were dropped: {merged!r} — the intercept must union, not replace"
    )
    assert {"1080p", "Boba", "Боба"} <= merged, f"derived tags missing from {merged!r}"


def test_merge_is_order_stable_and_deduplicated(proxy_module):
    """Client first, derived second, no duplicates, no empty entries."""
    assert proxy_module.merge_tag_values("Boba, ,x", "1080p,Boba") == "Boba,x,1080p"
    assert proxy_module.merge_tag_values("", "Boba") == "Boba"
    assert proxy_module.merge_tag_values("Boba", "") == "Boba"
    assert proxy_module.merge_tag_values("", "") == ""


def test_intercept_attaches_tags_to_the_reencoded_form(proxy_module, tmp_path, monkeypatch):
    """The call site itself must place the tags into the body it forwards.

    Drives the REAL `do_POST` intercept branch with nova2dl stubbed, and
    asserts on the FORM BODY that reaches `proxy_to_qbittorrent` — the bytes
    qBittorrent actually receives, not an intermediate variable.
    """
    import types
    import urllib.parse

    torrent = tmp_path / "Some.Show.S01E02.720p.WEB-DL.torrent"
    torrent.write_bytes(b"d4:fake3:onee")

    monkeypatch.setattr(proxy_module, "identify_plugin", lambda url: "rutracker")
    monkeypatch.setattr(
        proxy_module, "download_via_nova2dl", lambda plugin, url: str(torrent)
    )

    forwarded = {}
    handler = types.SimpleNamespace()
    handler.command = "POST"
    handler.path = "/api/v2/torrents/add"
    handler.headers = {"Content-Length": "0"}
    handler.proxy_to_qbittorrent = lambda body: forwarded.setdefault("body", body)
    handler.rfile = types.SimpleNamespace(read=lambda n: b"")
    handler._is_multipart_file_upload = lambda: False
    handler.send_error = lambda *a, **k: pytest.fail(f"intercept errored: {a} {k}")

    body = urllib.parse.urlencode(
        {"urls": "https://rutracker.org/forum/viewtopic.php?t=42", "tags": "user-typed"}
    ).encode()
    proxy_module.DownloadHandler.handle_request(handler, body)

    assert "body" in forwarded, "the intercept never forwarded a body"
    params = urllib.parse.parse_qs(forwarded["body"].decode())
    assert params["urls"][0].startswith("file://"), "the local file rewrite was lost"

    landed = _tags(params.get("tags", [""])[0])
    assert landed, (
        "the re-encoded form carries NO tags — qBittorrent will store "
        "tags='' for this download (IMPORTANT-2)"
    )
    assert "user-typed" in landed, f"the client's own tag was dropped: {landed!r}"
    assert {"Boba", "Боба", "720p"} <= landed, f"derived tags missing from {landed!r}"
