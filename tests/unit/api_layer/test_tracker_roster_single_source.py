"""B1 — the authenticated-tracker roster is ONE source, and it routes correctly.

THE DEFECT (§11.4.115 RED-first; measured 2026-09-01)
-----------------------------------------------------
The set of domains meaning "fetch this URL WITH credentials" was re-typed at
four sites, and they had drifted. ``nnm-club.me`` was present in
``webui-bridge.py`` and ``plugins/download_proxy.py`` but ABSENT from
``api/routes.py:TRACKER_DOMAINS``, so on the merge service (:7187)
``_is_tracker_url`` returned ``None`` for it and ``download_torrent_file``
fell through to the UNAUTHENTICATED ``aiohttp`` fetch. The tracker answers an
anonymous request with an HTML login page (or a 401 body), and that body was
streamed back to the user as ``<tracker>_<id>.torrent``: a corrupt torrent and
no error.

WHY THE ROSTER-EQUALITY TEST ALONE IS NOT ENOUGH (§11.4.245 oracle
independence). ``test_every_consumer_resolves_the_same_roster`` below is
NECESSARY but NOT SUFFICIENT — it would pass just as happily if all consumers
were equally WRONG. The load-bearing test is
``test_dead_alias_url_takes_the_authenticated_path``: it drives the real
``POST /api/v1/download/file`` handler and asserts the USER-OBSERVABLE
outcome — the bytes the user receives are the torrent from the authenticated
fetch, NOT the login page the anonymous path would have saved.

``test_non_tracker_url_still_takes_the_anonymous_path`` is the §11.4.201(1)
false-positive guard: a matcher that claimed every URL is a tracker would
satisfy the positive test and break every ordinary download.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_PATH = _REPO_ROOT / "download-proxy" / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

# The dead nnmclub alias that the merge service failed to recognise. Recognising
# it is what routes it through authentication; it must never be a PRIMARY (see
# tests/unit/merge_service/test_nnmclub_domain_live.py).
_DEAD_ALIAS_URL = "https://nnm-club.me/forum/viewtopic.php?t=1234567"

# What an unauthenticated request to a private tracker actually gets back — the
# body that used to be saved as a ".torrent".
_LOGIN_PAGE_HTML = b"<html><head><title></title></head><body><form action='login.php'></form></body></html>"

_TORRENT_BYTES = (
    b"d8:announce20:http://tracker.test"
    b"4:infod6:lengthi12e4:name8:demo.bin"
    b"12:piece lengthi16384e6:pieces20:" + (b"\x00" * 20) + b"ee"
)


def _purge_api_module() -> None:
    for key in [k for k in list(sys.modules) if k == "api" or k.startswith("api.")]:
        del sys.modules[key]


@pytest.fixture(autouse=True)
def _restore_api_module():
    yield
    _purge_api_module()


def _anonymous_session_returning_login_page():
    """An ``aiohttp.ClientSession`` whose GET yields the tracker's login page.

    If the routing decision sends the URL down the anonymous path, THIS is what
    the user receives — and the assertion on the response body catches it.
    """
    resp = AsyncMock()
    resp.status = 200
    resp.read = AsyncMock(return_value=_LOGIN_PAGE_HTML)
    resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _client_with(orch, tmp_path, monkeypatch):
    _purge_api_module()
    import api
    import api.hooks

    monkeypatch.setattr(api.hooks, "HOOKS_FILE", str(tmp_path / "hooks.json"))
    api.orchestrator_instance = orch
    return TestClient(api.app)


def test_dead_alias_url_takes_the_authenticated_path(tmp_path, monkeypatch):
    """An ``nnm-club.me`` URL is fetched WITH credentials, not anonymously.

    RED against the pre-fix roster: ``_is_tracker_url`` returned ``None``, the
    anonymous branch ran, and the response body was ``_LOGIN_PAGE_HTML``.
    """
    orch = MagicMock()
    orch.fetch_torrent = AsyncMock(return_value=_TORRENT_BYTES)

    client = _client_with(orch, tmp_path, monkeypatch)

    import api.routes as routes

    with patch.object(
        routes.aiohttp, "ClientSession", MagicMock(return_value=_anonymous_session_returning_login_page())
    ):
        resp = client.post(
            "/api/v1/download/file",
            json={"result_id": "r1", "download_urls": [_DEAD_ALIAS_URL]},
        )

    assert resp.status_code == 200
    # USER-OBSERVABLE OUTCOME: the bytes the user saves are the real torrent,
    # never the login page the anonymous path would have handed back.
    assert resp.content == _TORRENT_BYTES
    assert resp.content != _LOGIN_PAGE_HTML

    # And the routing decision itself: the authenticated fetch ran, keyed to
    # the right tracker.
    orch.fetch_torrent.assert_awaited_once()
    tracker_arg, url_arg = orch.fetch_torrent.await_args.args[:2]
    assert tracker_arg == "nnmclub"
    assert url_arg == _DEAD_ALIAS_URL


@pytest.mark.parametrize(
    ("url", "expected_tracker"),
    [
        ("https://rutracker.net/forum/dl.php?t=1", "rutracker"),
        ("https://kinozal.guru/details.php?id=2", "kinozal"),
        ("https://kinozal.me/details.php?id=3", "kinozal"),
        ("https://nnmclub.ro/forum/viewtopic.php?t=4", "nnmclub"),
        ("https://nnm-club.me/forum/viewtopic.php?t=5", "nnmclub"),
        ("https://iptorrents.org/t/6", "iptorrents"),
    ],
)
def test_previously_drifted_domains_now_route_authenticated(url, expected_tracker, tmp_path, monkeypatch):
    """Every domain that was in SOME roster but not the merge service's."""
    orch = MagicMock()
    orch.fetch_torrent = AsyncMock(return_value=_TORRENT_BYTES)

    client = _client_with(orch, tmp_path, monkeypatch)

    import api.routes as routes

    with patch.object(
        routes.aiohttp, "ClientSession", MagicMock(return_value=_anonymous_session_returning_login_page())
    ):
        resp = client.post("/api/v1/download/file", json={"result_id": "r", "download_urls": [url]})

    assert resp.status_code == 200
    assert resp.content == _TORRENT_BYTES
    orch.fetch_torrent.assert_awaited_once()
    assert orch.fetch_torrent.await_args.args[0] == expected_tracker


def test_non_tracker_url_still_takes_the_anonymous_path(tmp_path, monkeypatch):
    """§11.4.201(1) false-positive guard.

    A matcher that answered "tracker" for everything would pass the positive
    tests above while breaking every ordinary download. An ordinary URL MUST
    still be fetched anonymously and MUST NOT reach ``fetch_torrent``.
    """
    orch = MagicMock()
    orch.fetch_torrent = AsyncMock(return_value=_TORRENT_BYTES)

    client = _client_with(orch, tmp_path, monkeypatch)

    import api.routes as routes

    plain_body = b"d4:spam4:eggse"
    resp_obj = AsyncMock()
    resp_obj.status = 200
    resp_obj.read = AsyncMock(return_value=plain_body)
    resp_obj.headers = {}
    resp_obj.__aenter__ = AsyncMock(return_value=resp_obj)
    resp_obj.__aexit__ = AsyncMock(return_value=False)
    session = AsyncMock()
    session.get = MagicMock(return_value=resp_obj)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(routes, "_is_safe_fetch_url", return_value=True),
        patch.object(routes.aiohttp, "ClientSession", MagicMock(return_value=session)),
    ):
        resp = client.post(
            "/api/v1/download/file",
            json={"result_id": "r", "download_urls": ["https://example.test/linux.torrent"]},
        )

    assert resp.status_code == 200
    assert resp.content == plain_body
    orch.fetch_torrent.assert_not_awaited()


def test_every_consumer_resolves_the_same_roster():
    """Necessary-not-sufficient: all four consumers agree, domain by domain.

    This is the structural half of the fix — it catches a NEW divergence the
    moment one consumer stops reading the shared roster. It cannot catch a
    roster that is uniformly wrong; that is what the routing tests above are
    for.
    """
    import importlib.util

    from merge_service.trackers import (
        PRIVATE_TRACKER_DOMAINS,
        TRACKER_DOMAINS,
        identify_tracker,
        identify_tracker_in_text,
    )

    _purge_api_module()
    from api.routes import TRACKER_DOMAINS as ROUTES_DOMAINS
    from api.routes import _is_tracker_url

    bridge_spec = importlib.util.spec_from_file_location(
        "webui_bridge_roster_probe", str(_REPO_ROOT / "webui-bridge.py")
    )
    bridge = importlib.util.module_from_spec(bridge_spec)
    bridge_spec.loader.exec_module(bridge)

    plugin_spec = importlib.util.spec_from_file_location(
        "download_proxy_roster_probe", str(_REPO_ROOT / "plugins" / "download_proxy.py")
    )
    plugin = importlib.util.module_from_spec(plugin_spec)
    plugin_spec.loader.exec_module(plugin)

    # The flat tuple the API router exposes IS the shared one.
    assert tuple(ROUTES_DOMAINS) == tuple(TRACKER_DOMAINS)

    handler = MagicMock()
    for expected_tracker, domains in PRIVATE_TRACKER_DOMAINS.items():
        for domain in domains:
            url = f"https://{domain}/download.php?id=1"
            assert identify_tracker(url) == expected_tracker, domain
            assert identify_tracker_in_text(url) == expected_tracker, domain
            assert _is_tracker_url(url) == expected_tracker, f"api/routes.py disagrees on {domain}"
            assert bridge.WebUIBridgeHandler.identify_plugin(handler, url) == expected_tracker, (
                f"webui-bridge.py disagrees on {domain}"
            )
            assert plugin.identify_plugin(url) == expected_tracker, (
                f"plugins/download_proxy.py disagrees on {domain}"
            )

    # ... and none of them claims an unrelated host.
    for probe in ("https://example.test/x.torrent", "https://not-a-tracker.invalid/y"):
        assert identify_tracker(probe) is None
        assert _is_tracker_url(probe) is None
        assert bridge.WebUIBridgeHandler.identify_plugin(handler, probe) is None
        assert plugin.identify_plugin(probe) is None


def test_mirror_env_defaults_agree_with_the_roster_primaries():
    """The remaining ``*_MIRRORS`` fallback literals cannot drift unnoticed.

    HONEST BOUNDARY (§11.4.6). The recognition ROSTER is now single-source, but
    ``merge_service/search.py`` and ``api/auth.py`` still spell the PRIMARY host
    inline as the fallback of ``os.getenv("<TRACKER>_MIRRORS", "https://<host>")``
    — 8 literals at the time of writing. They are a DIFFERENT datum (which host
    to log in to, operator-overridable) and they all currently agree with the
    roster, so no drift exists today; they were left in place rather than
    rewritten because two of them are pinned by source-text assertions in
    ``tests/unit/merge_service/test_nnmclub_domain_live.py`` and ``auth.py`` is
    outside this change's scope.

    Leaving them un-derived is only acceptable if a divergence is DETECTED, so
    this gate makes it detected: every such literal must equal the roster's
    primary for that tracker.
    """
    import re

    from merge_service.trackers import PRIVATE_TRACKER_DOMAINS

    pattern = re.compile(r'os\.getenv\(\s*"([A-Z]+)_MIRRORS"\s*,\s*"https://([^"]+)"')
    checked = 0
    for rel in ("merge_service/search.py", "api/auth.py"):
        source = (_SRC_PATH / rel).read_text(encoding="utf-8")
        for env_name, host in pattern.findall(source):
            tracker = env_name.lower()
            assert tracker in PRIVATE_TRACKER_DOMAINS, f"{rel}: unknown tracker {tracker}"
            primary = PRIVATE_TRACKER_DOMAINS[tracker][0]
            assert host == primary, f"{rel}: {env_name} default {host!r} != roster primary {primary!r}"
            checked += 1

    # Control needle (§11.4.201(7)(b)): a zero here would mean the regex stopped
    # matching, not that the literals agree — a false-null this assertion closes.
    assert checked >= 8, f"expected to find the *_MIRRORS defaults, found {checked}"


def test_no_domain_belongs_to_two_trackers():
    """A domain in two trackers' tuples is a roster DEFECT, not a tie to break.

    ``identify_tracker`` would silently return whichever tracker came first in
    dict order, so the ambiguity must be impossible rather than resolved.
    """
    from merge_service.trackers import PRIVATE_TRACKER_DOMAINS, TRACKER_DOMAINS

    assert len(TRACKER_DOMAINS) == len(set(TRACKER_DOMAINS)), "duplicate domain in the roster"
    seen = {}
    for name, domains in PRIVATE_TRACKER_DOMAINS.items():
        for domain in domains:
            assert domain not in seen, f"{domain} claimed by both {seen.get(domain)} and {name}"
            seen[domain] = name


def test_search_base_urls_derive_from_roster_primaries():
    """``merge_service.search.PRIVATE_TRACKERS`` is derived, not re-typed."""
    from merge_service.search import PRIVATE_TRACKERS
    from merge_service.trackers import PRIVATE_TRACKER_BASE_URLS, PRIVATE_TRACKER_DOMAINS

    assert PRIVATE_TRACKERS == PRIVATE_TRACKER_BASE_URLS
    for name, domains in PRIVATE_TRACKER_DOMAINS.items():
        assert PRIVATE_TRACKERS[name] == f"https://{domains[0]}"
