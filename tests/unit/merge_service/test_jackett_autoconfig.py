"""Unit tests for merge_service.jackett_autoconfig.

All Jackett HTTP interactions are mocked via unittest.mock.AsyncMock —
matches the existing convention in tests/unit/test_private_tracker_search.py.
"""

import os
import sys

# Match the existing path-injection convention used across tests/unit/.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "download-proxy", "src"),
)

import importlib.util
import json
from datetime import datetime, timezone, UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Register merge_service and load jackett_autoconfig via importlib — same
# pattern as test_edge_case_challenges.py et al. Required because other
# tests in this collection install a lightweight 'api' stub; using
# spec_from_file_location lets us register jackett_autoconfig explicitly
# regardless.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_MS_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src", "merge_service")

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]

_ac_spec = importlib.util.spec_from_file_location(
    "merge_service.jackett_autoconfig",
    os.path.join(_MS_PATH, "jackett_autoconfig.py"),
)
_ac_mod = importlib.util.module_from_spec(_ac_spec)
sys.modules["merge_service.jackett_autoconfig"] = _ac_mod
_ac_spec.loader.exec_module(_ac_mod)

AutoconfigResult = _ac_mod.AutoconfigResult


# ------------------------------------------------------------------
# Task 1.1 — AutoconfigResult shape and redaction
# ------------------------------------------------------------------


def test_autoconfig_result_serializes_with_no_credentials():
    r = AutoconfigResult(
        ran_at=datetime(2026, 4, 26, 14, 23, 11, tzinfo=UTC),
        discovered_credentials=["RUTRACKER", "KINOZAL"],
        matched_indexers={"RUTRACKER": "rutracker", "KINOZAL": "kinozalbiz"},
        configured_now=["rutracker"],
        already_present=["kinozalbiz"],
        skipped_no_match=[],
        skipped_ambiguous=[],
        errors=[],
    )

    body = r.model_dump_json()
    parsed = json.loads(body)

    assert parsed["discovered_credentials"] == ["RUTRACKER", "KINOZAL"]
    assert parsed["configured_now"] == ["rutracker"]
    assert parsed["already_present"] == ["kinozalbiz"]
    assert parsed["ran_at"].startswith("2026-04-26T14:23:11")

    assert "password" not in body.lower()
    assert "username" not in body.lower()
    assert "cookie" not in body.lower()


def test_autoconfig_result_repr_excludes_credentials():
    r = AutoconfigResult(
        ran_at=datetime.now(UTC),
        discovered_credentials=["RUTRACKER"],
        matched_indexers={"RUTRACKER": "rutracker"},
        configured_now=["rutracker"],
        already_present=[],
        skipped_no_match=[],
        skipped_ambiguous=[],
        errors=[],
    )
    txt = repr(r)
    assert "password" not in txt.lower()
    assert "secret" not in txt.lower()


# ------------------------------------------------------------------
# Task 1.2 — Env scanner with denylist
# ------------------------------------------------------------------


def test_env_scan_finds_username_password_pair():
    _scan = _ac_mod._scan_env_credentials
    env = {
        "RUTRACKER_USERNAME": "u",
        "RUTRACKER_PASSWORD": "p",
        "PATH": "/usr/bin",
    }
    bundles = _scan(env, exclude=set())
    assert "RUTRACKER" in bundles
    assert bundles["RUTRACKER"]["username"] == "u"
    assert bundles["RUTRACKER"]["password"] == "p"


def test_env_scan_finds_cookies_alone():
    _scan = _ac_mod._scan_env_credentials
    env = {"NNMCLUB_COOKIES": "abc=def; xyz=uvw"}
    bundles = _scan(env, exclude=set())
    assert "NNMCLUB" in bundles
    assert bundles["NNMCLUB"]["cookies"] == "abc=def; xyz=uvw"


def test_env_scan_skips_incomplete_bundle_silently():
    _scan = _ac_mod._scan_env_credentials
    env = {"RUTRACKER_USERNAME": "u"}
    bundles = _scan(env, exclude=set())
    assert bundles == {}


def test_env_scan_respects_denylist():
    _scan = _ac_mod._scan_env_credentials
    env = {
        "QBITTORRENT_USERNAME": "admin",
        "QBITTORRENT_PASSWORD": "admin",
        "RUTRACKER_USERNAME": "u",
        "RUTRACKER_PASSWORD": "p",
    }
    bundles = _scan(env, exclude={"QBITTORRENT"})
    assert "QBITTORRENT" not in bundles
    assert "RUTRACKER" in bundles


def test_env_scan_ignores_lowercase_and_irrelevant_suffixes():
    _scan = _ac_mod._scan_env_credentials
    env = {
        "rutracker_username": "u",
        "RUTRACKER_USER": "u",
        "DEBUG_PASSWORD": "x",
    }
    bundles = _scan(env, exclude=set())
    assert bundles == {}


# ------------------------------------------------------------------
# Task 1.3 — Fuzzy matcher with override precedence
# ------------------------------------------------------------------


def test_fuzzy_match_exact_name_returns_indexer():
    _match = _ac_mod._match_indexers
    catalog = [
        {"id": "rutracker", "name": "RuTracker"},
        {"id": "kinozalbiz", "name": "KinoZal"},
    ]
    bundles = {"RUTRACKER": {"username": "u", "password": "p"}}
    matched, ambiguous, unmatched = _match(bundles, catalog, override={})
    assert matched == {"RUTRACKER": "rutracker"}
    assert ambiguous == []
    assert unmatched == []


def test_fuzzy_match_below_threshold_goes_to_unmatched():
    _match = _ac_mod._match_indexers
    catalog = [{"id": "demonoid", "name": "Demonoid"}]
    bundles = {"RUTRACKER": {"username": "u", "password": "p"}}
    matched, ambiguous, unmatched = _match(bundles, catalog, override={})
    assert matched == {}
    assert unmatched == ["RUTRACKER"]


def test_fuzzy_match_ambiguous_records_candidates():
    _match = _ac_mod._match_indexers
    # Two equally-close-to-"NNMCLUB" indexer names — at least one must
    # be flagged ambiguous OR a deterministic top wins.
    catalog = [
        {"id": "nnmclub", "name": "NNMClub"},
        {"id": "nnmclub2", "name": "NNMClub2"},
    ]
    bundles = {"NNMCLUB": {"cookies": "x"}}
    matched, ambiguous, unmatched = _match(bundles, catalog, override={})
    if matched:
        assert "NNMCLUB" in matched
    else:
        assert any(a.env_name == "NNMCLUB" for a in ambiguous)


def test_override_takes_precedence_over_fuzzy_match():
    _match = _ac_mod._match_indexers
    catalog = [
        {"id": "rutracker", "name": "RuTracker"},
        {"id": "rutrackerme", "name": "RutrackerMe"},
    ]
    bundles = {"RUTRACKER": {"username": "u", "password": "p"}}
    matched, _, _ = _match(bundles, catalog, override={"RUTRACKER": "rutrackerme"})
    assert matched == {"RUTRACKER": "rutrackerme"}


def test_override_to_unknown_id_falls_back_to_fuzzy():
    _match = _ac_mod._match_indexers
    catalog = [{"id": "rutracker", "name": "RuTracker"}]
    bundles = {"RUTRACKER": {"username": "u", "password": "p"}}
    matched, _, _ = _match(bundles, catalog, override={"RUTRACKER": "does-not-exist"})
    assert matched == {"RUTRACKER": "rutracker"}


# ------------------------------------------------------------------
# Task 1.4 — Per-indexer configure with idempotency + retry
# ------------------------------------------------------------------


def _mock_aiohttp_response(status: int, json_data: Any = None, text: str = ""):
    """Build an aiohttp-style async context-manager response."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.text = AsyncMock(return_value=text)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_idempotency_skips_already_configured():
    _configure_one = _ac_mod._configure_one

    session = MagicMock()
    session.get = MagicMock()
    session.post = MagicMock()

    result = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u", "password": "p"},
        already_configured={"rutracker"},
    )
    assert result == ("already_present", None)
    session.post.assert_not_called()
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_configure_posts_template_with_filled_credentials():
    _configure_one = _ac_mod._configure_one

    template = {
        "config": [
            {"id": "username", "value": ""},
            {"id": "password", "value": ""},
        ]
    }
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_aiohttp_response(200, json_data=template))
    session.post = MagicMock(return_value=_mock_aiohttp_response(200, json_data={"ok": True}))

    result = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u", "password": "p"},
        already_configured=set(),
    )
    assert result == ("configured", None)
    session.post.assert_called_once()
    posted_kwargs = session.post.call_args.kwargs
    payload = posted_kwargs.get("json") or {}
    config = payload.get("config", [])
    fields = {f["id"]: f["value"] for f in config}
    assert fields["username"] == "u"
    assert fields["password"] == "p"


@pytest.mark.asyncio
async def test_configure_records_4xx_as_error_no_retry():
    _configure_one = _ac_mod._configure_one

    template = {"config": [{"id": "username", "value": ""}]}
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_aiohttp_response(200, json_data=template))
    session.post = MagicMock(return_value=_mock_aiohttp_response(401, text="bad creds"))

    result = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u"},
        already_configured=set(),
    )
    status, err = result
    assert status == "error"
    assert err and "401" in err


# ------------------------------------------------------------------
# Task 1.5 — Top-level orchestrator
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autoconfigure_jackett_unreachable_returns_error_no_raise():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett

    result = await autoconfigure_jackett(
        jackett_url="http://127.0.0.1:1",
        api_key="fake",
        env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
        timeout=1.0,
    )
    assert result.errors  # at least one error
    assert any(
        "unreachable" in e or "network" in e.lower() for e in result.errors
    ), result.errors
    assert result.configured_now == []


@pytest.mark.asyncio
async def test_autoconfigure_jackett_total_timeout_caps_at_60s():
    """Outer asyncio.timeout(60s) prevents hangs."""
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett

    import time

    start = time.monotonic()
    result = await autoconfigure_jackett(
        jackett_url="http://127.0.0.1:1",
        api_key="fake",
        env={},
        timeout=1.0,
    )
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"took {elapsed}s — should be ≪ 60s outer cap"
    assert isinstance(result.ran_at, datetime)


@pytest.mark.asyncio
async def test_autoconfigure_jackett_no_creds_returns_empty():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett
    result = await autoconfigure_jackett(
        jackett_url="http://127.0.0.1:1",
        api_key="fake",
        env={"PATH": "/usr/bin"},
        timeout=1.0,
    )
    assert result.discovered_credentials == []
    assert result.configured_now == []
    assert result.errors == []


@pytest.mark.asyncio
async def test_autoconfigure_jackett_missing_api_key_emits_error():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett
    result = await autoconfigure_jackett(
        jackett_url="http://127.0.0.1:1",
        api_key="",
        env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
        timeout=1.0,
    )
    assert "jackett_auth_missing_key" in result.errors


def test_parse_indexer_map_handles_csv():
    parse = _ac_mod._parse_indexer_map
    assert parse("rutracker:rutracker.org,kinozal:kinozalbiz") == {
        "RUTRACKER": "rutracker.org",
        "KINOZAL": "kinozalbiz",
    }
    assert parse(None) == {}
    assert parse("") == {}
    assert parse("malformed_no_colon") == {}


def test_parse_exclude_returns_default_when_unset():
    parse = _ac_mod._parse_exclude
    assert "QBITTORRENT" in parse(None)
    assert "JACKETT" in parse(None)


def test_parse_exclude_overrides_default():
    parse = _ac_mod._parse_exclude
    out = parse("FOO,BAR")
    assert out == frozenset({"FOO", "BAR"})


# ------------------------------------------------------------------
# _configure_one edge cases
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_one_template_fetch_4xx():
    _configure_one = _ac_mod._configure_one
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_aiohttp_response(404, text="not found"))
    status, err = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u", "password": "p"},
        already_configured=set(),
    )
    assert status == "error"
    assert "404" in err


@pytest.mark.asyncio
async def test_configure_one_template_fetch_network_error():
    _configure_one = _ac_mod._configure_one
    session = MagicMock()
    session.get = MagicMock(side_effect=TimeoutError("conn timed out"))
    status, err = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u", "password": "p"},
        already_configured=set(),
    )
    assert status == "error"
    assert "TimeoutError" in err


@pytest.mark.asyncio
async def test_configure_one_template_bare_list():
    _configure_one = _ac_mod._configure_one
    template = [
        {"id": "username", "value": ""},
        {"id": "password", "value": ""},
    ]
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_aiohttp_response(200, json_data=template))
    session.post = MagicMock(return_value=_mock_aiohttp_response(200, json_data={"ok": True}))

    status, err = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u", "password": "p"},
        already_configured=set(),
    )
    assert status == "configured"
    assert err is None
    # POST body should be a bare list (not wrapped in {"config": ...})
    posted = session.post.call_args.kwargs.get("json")
    assert isinstance(posted, list)


@pytest.mark.asyncio
async def test_configure_one_template_neither_list_nor_dict():
    _configure_one = _ac_mod._configure_one
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_aiohttp_response(200, json_data="string"))
    status, err = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u", "password": "p"},
        already_configured=set(),
    )
    assert status == "error"
    assert "no_compatible" in err


@pytest.mark.asyncio
async def test_configure_one_no_compatible_fields():
    _configure_one = _ac_mod._configure_one
    template = {"config": [{"id": "apikey", "value": ""}]}
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_aiohttp_response(200, json_data=template))
    status, err = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u", "password": "p"},
        already_configured=set(),
    )
    assert status == "error"
    assert "no_compatible" in err


@pytest.mark.asyncio
async def test_configure_one_post_5xx_retry_then_success():
    _configure_one = _ac_mod._configure_one
    template = {"config": [{"id": "username", "value": ""}]}
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_aiohttp_response(200, json_data=template))
    session.post = MagicMock(
        side_effect=[
            _mock_aiohttp_response(503, text="overloaded"),
            _mock_aiohttp_response(200, json_data={"ok": True}),
        ]
    )
    status, err = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u"},
        already_configured=set(),
    )
    assert status == "configured"
    assert err is None
    assert session.post.call_count == 2


@pytest.mark.asyncio
async def test_configure_one_post_network_error_retry_then_success():
    _configure_one = _ac_mod._configure_one
    template = {"config": [{"id": "username", "value": ""}]}
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_aiohttp_response(200, json_data=template))
    session.post = MagicMock(
        side_effect=[
            TimeoutError("first attempt failed"),
            _mock_aiohttp_response(200, json_data={"ok": True}),
        ]
    )
    status, err = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u"},
        already_configured=set(),
    )
    assert status == "configured"
    assert err is None
    assert session.post.call_count == 2


@pytest.mark.asyncio
async def test_configure_one_post_retries_exhausted():
    _configure_one = _ac_mod._configure_one
    template = {"config": [{"id": "username", "value": ""}]}
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_aiohttp_response(200, json_data=template))
    session.post = MagicMock(
        side_effect=[
            TimeoutError("first"),
            TimeoutError("second"),
        ]
    )
    status, err = await _configure_one(
        session,
        jackett_url="http://jackett:9117",
        api_key="fake",
        indexer_id="rutracker",
        creds={"username": "u"},
        already_configured=set(),
    )
    assert status == "error"
    # Both attempts raise TimeoutError. Attempt 1 retries (attempt==1),
    # attempt 2 falls through to network error handler
    assert "TimeoutError" in err
    assert session.post.call_count == 2


# ------------------------------------------------------------------
# _parse_indexer_map edge case
# ------------------------------------------------------------------


def test_parse_indexer_map_skips_empty_value():
    parse = _ac_mod._parse_indexer_map
    result = parse("rutracker:")
    assert result == {}


# ------------------------------------------------------------------
# _match_indexers ambiguous tie
# ------------------------------------------------------------------


def test_fuzzy_match_ambiguous_tie():
    _match = _ac_mod._match_indexers
    # Two ids equidistant from env_name "abcdef" — both add 1 char to 6-char base
    catalog = [
        {"id": "abcdef1", "name": "A B C D E F 1"},
        {"id": "abcdef2", "name": "A B C D E F 2"},
    ]
    bundles = {"ABCDEF": {"username": "u", "password": "p"}}
    matched, ambiguous, unmatched = _match(bundles, catalog, override={})
    # Both score 12/13 ≈ 0.923 ≥ 0.85 threshold → must be tied
    assert len(ambiguous) == 1
    assert ambiguous[0].env_name == "ABCDEF"
    assert set(ambiguous[0].candidates) == {"abcdef1", "abcdef2"}
    assert matched == {}
    assert unmatched == []


# ------------------------------------------------------------------
# autoconfigure_jackett — catalog parse variants
# ------------------------------------------------------------------


def _mock_session(
    catalog_data: Any = None,
    catalog_status: int = 200,
    catalog_error: Exception | None = None,
    warmup_status: int = 200,
    template_data: Any = None,
    post_status: int = 200,
) -> MagicMock:
    """Build a mock session for autoconfigure_jackett testing."""
    warmup_resp = _mock_aiohttp_response(warmup_status)
    if catalog_error:
        catalog_resp = MagicMock()
        catalog_resp.__aenter__ = AsyncMock(side_effect=catalog_error)
        catalog_resp.__aexit__ = AsyncMock(return_value=False)
    else:
        catalog_resp = _mock_aiohttp_response(catalog_status, json_data=catalog_data)

    template_resp = _mock_aiohttp_response(200, json_data=template_data or {"config": [{"id": "username", "value": ""}]})
    post_resp = _mock_aiohttp_response(post_status, json_data={"ok": True})

    session = MagicMock()
    session.post = MagicMock(return_value=warmup_resp)

    def get_side_effect(url: str, *args, **kwargs):
        # Catalog URL is /api/v2.0/indexers (no /config suffix)
        if "indexers" in url and "/config" not in url:
            return catalog_resp
        return template_resp

    session.get = MagicMock(side_effect=get_side_effect)
    return session


@pytest.mark.asyncio
async def test_autoconfigure_jackett_catalog_dict_with_indexers_key():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett
    catalog = {"Indexers": [{"id": "rutracker", "name": "RuTracker", "configured": False}]}
    session = _mock_session(catalog_data=catalog)
    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await autoconfigure_jackett(
            jackett_url="http://jackett:9117",
            api_key="key",
            env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
            timeout=10.0,
        )
    assert "rutracker" in result.configured_now


@pytest.mark.asyncio
async def test_autoconfigure_jackett_catalog_401():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett
    session = _mock_session(catalog_status=401)
    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await autoconfigure_jackett(
            jackett_url="http://jackett:9117",
            api_key="key",
            env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
            timeout=10.0,
        )
    assert any("auth_failed" in e for e in result.errors)


@pytest.mark.asyncio
async def test_autoconfigure_jackett_catalog_5xx():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett
    session = _mock_session(catalog_status=500)
    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await autoconfigure_jackett(
            jackett_url="http://jackett:9117",
            api_key="key",
            env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
            timeout=10.0,
        )
    assert any("http_500" in e for e in result.errors)


@pytest.mark.asyncio
async def test_autoconfigure_jackett_catalog_parse_failure():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett
    # Indexers key has non-list value — triggers line 316-318
    session = _mock_session(catalog_data={"Indexers": "not_a_list"})
    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await autoconfigure_jackett(
            jackett_url="http://jackett:9117",
            api_key="key",
            env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
            timeout=10.0,
        )
    assert any("catalog_parse_failed" in e for e in result.errors)


@pytest.mark.asyncio
async def test_autoconfigure_jackett_catalog_content_type_error():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett

    import aiohttp
    from aiohttp import ContentTypeError

    raw_resp = MagicMock()
    raw_resp.status = 200
    req_info = MagicMock()
    raw_resp.json = AsyncMock(
        side_effect=ContentTypeError(req_info, [], message="not json")
    )
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=raw_resp)
    cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=_mock_aiohttp_response(200))
    session.get = MagicMock(return_value=cm)

    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await autoconfigure_jackett(
            jackett_url="http://jackett:9117",
            api_key="key",
            env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
            timeout=10.0,
        )
    assert any("catalog_parse_failed" in e for e in result.errors)


@pytest.mark.asyncio
async def test_autoconfigure_jackett_catalog_client_error():
    """Trigger non-connector ClientError (lines 323-324)."""
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett

    import aiohttp
    from aiohttp import InvalidURL

    cat_cm = MagicMock()
    cat_cm.__aenter__ = AsyncMock(
        side_effect=InvalidURL("bad url")
    )
    cat_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=_mock_aiohttp_response(200))
    session.get = MagicMock(return_value=cat_cm)

    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await autoconfigure_jackett(
            jackett_url="http://jackett:9117",
            api_key="key",
            env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
            timeout=10.0,
        )
    assert any("network" in e for e in result.errors)


@pytest.mark.asyncio
async def test_autoconfigure_jackett_configure_one_error():
    """Full flow where _configure_one returns error (line 363)."""
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett
    catalog = [
        {"id": "rutracker", "name": "RuTracker", "configured": False},
    ]
    # Template with no compatible fields → _configure_one returns error
    template = {"config": [{"id": "apikey", "value": ""}]}
    session = _mock_session(
        catalog_data=catalog,
        template_data=template,
        post_status=200,
    )
    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await autoconfigure_jackett(
            jackett_url="http://jackett:9117",
            api_key="key",
            env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
            timeout=10.0,
        )
    assert any("indexer_config_failed" in e for e in result.errors)


@pytest.mark.asyncio
async def test_autoconfigure_jackett_catalog_network_error():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett

    import aiohttp
    from aiohttp import ClientConnectorError
    from aiohttp.client_reqrep import ConnectionKey

    conn_key = ConnectionKey(
        host="localhost",
        port=9117,
        is_ssl=False,
        ssl=None,
        proxy=None,
        proxy_auth=None,
        proxy_headers_hash=None,
    )
    cat_cm = MagicMock()
    cat_cm.__aenter__ = AsyncMock(
        side_effect=ClientConnectorError(conn_key, OSError("conn refused"))
    )
    cat_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=_mock_aiohttp_response(200))
    session.get = MagicMock(return_value=cat_cm)

    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await autoconfigure_jackett(
            jackett_url="http://jackett:9117",
            api_key="key",
            env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
            timeout=10.0,
        )
    assert any("unreachable" in e for e in result.errors)


@pytest.mark.asyncio
async def test_autoconfigure_jackett_full_flow():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett
    catalog = [
        {"id": "rutracker", "name": "RuTracker", "configured": False},
        {"id": "kinozalbiz", "name": "KinoZal", "configured": True},
    ]
    template = {"config": [{"id": "username", "value": ""}, {"id": "password", "value": ""}]}
    session = _mock_session(
        catalog_data=catalog,
        template_data=template,
        post_status=200,
    )
    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await autoconfigure_jackett(
            jackett_url="http://jackett:9117",
            api_key="key",
            env={
                "RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p",
                "KINOZAL_USERNAME": "k", "KINOZAL_PASSWORD": "p",
            },
            timeout=10.0,
        )
    assert "rutracker" in result.configured_now
    assert result.already_present == ["kinozalbiz"]
    assert result.errors == []
    assert len(result.configured_now) == 1


@pytest.mark.asyncio
async def test_autoconfigure_jackett_total_timeout():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett

    # Make the inner session block forever so asyncio.timeout(60) triggers
    forever_cm = MagicMock()
    forever_cm.__aenter__ = AsyncMock(side_effect=lambda: asyncio.sleep(999))
    forever_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        # Make _scan_env_credentials return bundles so we enter the timeout block
        with patch.object(_ac_mod, "_scan_env_credentials", return_value={"FAKE": {"username": "u", "password": "p"}}):
            with patch.object(_ac_mod, "asyncio") as mock_asyncio:
                mock_asyncio.timeout.side_effect = TimeoutError("timed out")
                result = await autoconfigure_jackett(
                    jackett_url="http://jackett:9117",
                    api_key="key",
                    env={"FAKE_USERNAME": "u", "FAKE_PASSWORD": "p"},
                    timeout=10.0,
                )
    assert any("total_timeout" in e for e in result.errors)


@pytest.mark.asyncio
async def test_autoconfigure_jackett_unexpected_exception():
    autoconfigure_jackett = _ac_mod.autoconfigure_jackett

    # Patch _configure_one (called inside the try/except block) to
    # raise an unexpected exception, triggering the except Exception handler.
    with patch.object(_ac_mod, "_configure_one", side_effect=ValueError("boom")):
        # Also need to mock the session so the flow reaches _configure_one
        with patch("aiohttp.ClientSession") as mock_cls:
            mock_session = _mock_session(
                catalog_data=[{"id": "rutracker", "name": "RuTracker", "configured": False}],
                template_data={"config": [{"id": "username", "value": ""}]},
            )
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await autoconfigure_jackett(
                jackett_url="http://jackett:9117",
                api_key="key",
                env={"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"},
                timeout=10.0,
            )
    assert any("unexpected" in e for e in result.errors)
