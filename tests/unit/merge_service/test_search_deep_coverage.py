"""
Deep coverage for merge_service/search.py — targets the 143 missing lines:
HTML parser deep branches, start_search tracker-error handling, session
encryption setup, fetch_torrent redirect paths, _search_tracker exception
branches, and _load_env fallback paths.

Per §11.4.132 risk-ordered validation: search.py is the highest-risk
module (most-recently-worked, most complex). Tests run FIRST.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SRC_PATH = os.path.join(_REPO_ROOT, "download-proxy", "src")
_MS_PATH = os.path.join(_SRC_PATH, "merge_service")

if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [_MS_PATH]


def _import_search_module():
    spec = importlib.util.spec_from_file_location("merge_service.search", os.path.join(_MS_PATH, "search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_service.search"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def search_mod():
    return _import_search_module()


# --------------------------------------------------------------------------
# start_search — tracker-error handling (line 695)
# --------------------------------------------------------------------------


class TestStartSearchTrackerError:
    def test_start_search_survives_tracker_enumeration_failure(self, search_mod):
        """Lines 695-697: start_search must not crash if _get_enabled_trackers throws."""
        orch = search_mod.SearchOrchestrator()
        with patch.object(orch, "_get_enabled_trackers", side_effect=RuntimeError("boom")):
            meta = orch.start_search("test query")
            assert meta.query == "test query"
            assert meta.search_id
            assert meta.status == "running"
            assert meta.tracker_stats == {}

    def test_start_search_seeds_tracker_stats(self, search_mod):
        """Lines 683-694: start_search seeds tracker_stats for each enabled tracker."""
        orch = search_mod.SearchOrchestrator()
        fake_trackers = [
            search_mod.TrackerSource(name="rutracker", url="https://rutracker.org", enabled=True),
            search_mod.TrackerSource(name="piratebay", url="https://thepiratebay.org", enabled=True),
        ]
        with patch.object(orch, "_get_enabled_trackers", return_value=fake_trackers):
            with patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False):
                meta = orch.start_search("linux", category="all")
                assert "rutracker" in meta.tracker_stats
                assert "piratebay" in meta.tracker_stats
                assert meta.tracker_stats["rutracker"].query == "linux"
                assert meta.tracker_stats["rutracker"].status == "pending"
                assert meta.tracker_stats["rutracker"].authenticated is True


# --------------------------------------------------------------------------
# EncryptedSessionStore — deep paths
# --------------------------------------------------------------------------


class TestEncryptedSessionStoreDeep:
    def test_init_with_explicit_key(self, search_mod):
        """Lines 514-521: explicit key passed to __init__."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        cache = MagicMock()
        store = search_mod.EncryptedSessionStore(cache, key=key)
        assert store._cache is cache
        assert store._fernet is not None

    def test_init_with_env_key(self, search_mod):
        """Lines 518-520: SESSION_ENCRYPTION_KEY env var used."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"SESSION_ENCRYPTION_KEY": key}):
            cache = MagicMock()
            store = search_mod.EncryptedSessionStore(cache)
            assert store._fernet is not None

    def test_encrypt_decrypt_roundtrip(self, search_mod):
        """Lines 523-531: _encrypt and _decrypt."""
        from cachetools import TTLCache

        store = search_mod.EncryptedSessionStore(TTLCache(maxsize=8, ttl=60))
        data = {"cookies": {"sid": "abc123"}, "base_url": "https://example.com"}
        encrypted = store._encrypt(data)
        assert isinstance(encrypted, bytes)
        decrypted = store._decrypt(encrypted)
        assert decrypted == data

    def test_setitem_getitem(self, search_mod):
        """Lines 533-537: __setitem__ and __getitem__."""
        from cachetools import TTLCache

        store = search_mod.EncryptedSessionStore(TTLCache(maxsize=8, ttl=60))
        store["rutracker"] = {"cookies": {"sid": "abc"}}
        result = store["rutracker"]
        assert result == {"cookies": {"sid": "abc"}}

    def test_get_default(self, search_mod):
        """Lines 539-547: get() with default."""
        from cachetools import TTLCache

        store = search_mod.EncryptedSessionStore(TTLCache(maxsize=8, ttl=60))
        assert store.get("missing", "fallback") == "fallback"
        assert store.get("missing") is None

    def test_contains(self, search_mod):
        """Lines 549-550: __contains__."""
        from cachetools import TTLCache

        store = search_mod.EncryptedSessionStore(TTLCache(maxsize=8, ttl=60))
        store["key"] = "value"
        assert "key" in store
        assert "missing" not in store

    def test_delitem(self, search_mod):
        """Lines 552-553: __delitem__."""
        from cachetools import TTLCache

        store = search_mod.EncryptedSessionStore(TTLCache(maxsize=8, ttl=60))
        store["key"] = "value"
        del store["key"]
        assert "key" not in store

    def test_len(self, search_mod):
        """Lines 555-556: __len__."""
        from cachetools import TTLCache

        store = search_mod.EncryptedSessionStore(TTLCache(maxsize=8, ttl=60))
        assert len(store) == 0
        store["a"] = 1
        store["b"] = 2
        assert len(store) == 2

    def test_raw_values(self, search_mod):
        """Lines 561-563: _raw_values."""
        from cachetools import TTLCache

        store = search_mod.EncryptedSessionStore(TTLCache(maxsize=8, ttl=60))
        store["key"] = "value"
        raw = store._raw_values()
        assert len(raw) == 1
        assert isinstance(raw[0], bytes)


# --------------------------------------------------------------------------
# _search_tracker — exception branches (lines 980-983)
# --------------------------------------------------------------------------


class TestSearchTrackerException:
    @pytest.mark.asyncio
    async def test_search_tracker_returns_empty_on_exception(self, search_mod):
        """Lines 980-983: _search_tracker catches exceptions from _search_*."""
        orch = search_mod.SearchOrchestrator()
        tracker = search_mod.TrackerSource(name="rutracker", url="https://rutracker.org", enabled=True)
        with patch.object(orch, "_load_env"):
            with patch.object(orch, "_search_rutracker", side_effect=RuntimeError("network error")):
                results = await orch._search_tracker(tracker, "query", "all")
                assert results == []

    @pytest.mark.asyncio
    async def test_search_tracker_dispatches_to_correct_method(self, search_mod):
        """Lines 962-970: _search_tracker dispatches to correct _search_* method."""
        orch = search_mod.SearchOrchestrator()
        for name in ["rutracker", "kinozal", "nnmclub", "iptorrents"]:
            tracker = search_mod.TrackerSource(name=name, url=f"https://{name}.example.com", enabled=True)
            with patch.object(orch, "_load_env"):
                with patch.object(orch, f"_search_{name}", return_value=[]) as mock_search:
                    await orch._search_tracker(tracker, "q", "all")
                    mock_search.assert_called_once()


# --------------------------------------------------------------------------
# _search_public_tracker — subprocess flow (lines 985-1135)
# --------------------------------------------------------------------------


class TestSearchPublicTracker:
    @pytest.mark.asyncio
    async def test_search_public_tracker_empty_result(self, search_mod):
        """Lines 985-1135: full subprocess flow returns empty list."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"PUBLIC_TRACKER_DEADLINE_SECONDS": "5"}, clear=False):
            proc_mock = AsyncMock()
            proc_mock.stdout.readline = AsyncMock(return_value=b"")
            proc_mock.stderr = AsyncMock()
            proc_mock.stderr.read = AsyncMock(return_value=b"")
            proc_mock.returncode = 0
            proc_mock.kill = MagicMock()
            proc_mock.pid = 12345
            with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
                with patch("os.killpg"):
                    results = await orch._search_public_tracker("rutor", "test", "all")
                    assert results == []

    @pytest.mark.asyncio
    async def test_search_public_tracker_with_ndjson_results(self, search_mod):
        """Lines 985-1135: subprocess returns NDJSON lines."""
        orch = search_mod.SearchOrchestrator()
        import json as _json

        result_line = _json.dumps({
            "name": "Test Movie 1080p",
            "size": "2.5 GB",
            "seeds": 100,
            "leech": 10,
            "link": "magnet:?xt=urn:btih:abc",
            "desc_link": "http://example.com/desc",
        })
        proc_mock = AsyncMock()
        call_count = {"n": 0}

        async def readline_side_effect():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return (result_line + "\n").encode()
            return b""

        proc_mock.stdout.readline = readline_side_effect
        proc_mock.stderr = AsyncMock()
        proc_mock.stderr.read = AsyncMock(return_value=b"")
        proc_mock.returncode = 0
        proc_mock.kill = MagicMock()
        proc_mock.pid = 12345
        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with patch("os.killpg"):
                results = await orch._search_public_tracker("rutor", "test", "all")
                assert len(results) == 1
                assert results[0].name == "Test Movie 1080p"
                assert results[0].tracker == "rutor"

    @pytest.mark.asyncio
    async def test_search_public_tracker_malformed_ndjson_skipped(self, search_mod):
        """Lines 1087-1088: malformed NDJSON is skipped."""
        orch = search_mod.SearchOrchestrator()
        proc_mock = AsyncMock()
        call_count = {"n": 0}

        async def readline_side_effect():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return b"this is not valid json\n"
            return b""

        proc_mock.stdout.readline = readline_side_effect
        proc_mock.stderr = AsyncMock()
        proc_mock.stderr.read = AsyncMock(return_value=b"")
        proc_mock.returncode = 0
        proc_mock.kill = MagicMock()
        proc_mock.pid = 12345
        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with patch("os.killpg"):
                results = await orch._search_public_tracker("rutor", "test", "all")
                assert results == []

    @pytest.mark.asyncio
    async def test_search_public_tracker_error_line_skipped(self, search_mod):
        """Lines 1035-1038: __error__ in JSON is skipped."""
        orch = search_mod.SearchOrchestrator()
        import json as _json

        error_line = _json.dumps({"__error__": "plugin crashed"})
        proc_mock = AsyncMock()
        call_count = {"n": 0}

        async def readline_side_effect():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return (error_line + "\n").encode()
            return b""

        proc_mock.stdout.readline = readline_side_effect
        proc_mock.stderr = AsyncMock()
        proc_mock.stderr.read = AsyncMock(return_value=b"")
        proc_mock.returncode = 0
        proc_mock.kill = MagicMock()
        proc_mock.pid = 12345
        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with patch("os.killpg"):
                results = await orch._search_public_tracker("rutor", "test", "all")
                assert results == []

    @pytest.mark.asyncio
    async def test_search_public_tracker_deadline_timeout(self, search_mod):
        """Lines 1071-1078: deadline timeout kills reading."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"PUBLIC_TRACKER_DEADLINE_SECONDS": "5"}, clear=False):
            proc_mock = AsyncMock()
            proc_mock.stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError)
            proc_mock.stderr = AsyncMock()
            proc_mock.stderr.read = AsyncMock(return_value=b"")
            proc_mock.returncode = 0
            proc_mock.kill = MagicMock()
            proc_mock.pid = 12345
            with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
                with patch("os.killpg"):
                    with patch("os.getpgid", return_value=12345):
                        results = await orch._search_public_tracker("rutor", "test", "all")
                        assert results == []
                        diag = orch._last_public_tracker_diag.get("rutor", {})
                        assert diag.get("deadline_hit") is True

    @pytest.mark.asyncio
    async def test_search_public_tracker_proc_cleanup_kill(self, search_mod):
        """Lines 1100-1115: process cleanup when proc is still running."""
        orch = search_mod.SearchOrchestrator()
        proc_mock = AsyncMock()
        proc_mock.stdout.readline = AsyncMock(return_value=b"")
        proc_mock.stderr = AsyncMock()
        proc_mock.stderr.read = AsyncMock(return_value=b"stderr output")
        proc_mock.returncode = None
        proc_mock.kill = MagicMock()
        proc_mock.pid = 12345
        with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
            with patch("os.killpg"):
                with patch("os.getpgid", return_value=12345):
                    results = await orch._search_public_tracker("rutor", "test", "all")
                    assert results == []
                    proc_mock.kill.assert_called()

    @pytest.mark.asyncio
    async def test_search_public_tracker_value_error_deadline(self, search_mod):
        """Lines 1028-1029: ValueError fallback for deadline env var."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"PUBLIC_TRACKER_DEADLINE_SECONDS": "not-a-number"}, clear=False):
            proc_mock = AsyncMock()
            proc_mock.stdout.readline = AsyncMock(return_value=b"")
            proc_mock.stderr = AsyncMock()
            proc_mock.stderr.read = AsyncMock(return_value=b"")
            proc_mock.returncode = 0
            proc_mock.kill = MagicMock()
            proc_mock.pid = 12345
            with patch("asyncio.create_subprocess_exec", return_value=proc_mock):
                with patch("os.killpg"):
                    results = await orch._search_public_tracker("rutor", "test", "all")
                    assert results == []


# --------------------------------------------------------------------------
# _search_tracker — public tracker deadline ValueError
# --------------------------------------------------------------------------


class TestSearchTrackerDeadline:
    @pytest.mark.asyncio
    async def test_deadline_value_error_fallback(self, search_mod):
        """Lines 972-974: ValueError in PUBLIC_TRACKER_DEADLINE_SECONDS."""
        orch = search_mod.SearchOrchestrator()
        tracker = search_mod.TrackerSource(name="piratebay", url="https://thepiratebay.org", enabled=True)
        with patch.dict(os.environ, {"PUBLIC_TRACKER_DEADLINE_SECONDS": "bad"}, clear=False):
            with patch.object(orch, "_search_public_tracker", return_value=[]) as mock_search:
                with patch.object(orch, "_load_env"):
                    result = await orch._search_tracker(tracker, "test", "all")
                    assert result == []
                    mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_tracker_name_no_dispatch(self, search_mod):
        """Lines 960-983: unknown tracker name returns empty."""
        orch = search_mod.SearchOrchestrator()
        tracker = search_mod.TrackerSource(name="unknown_tracker", url="https://unknown.invalid", enabled=True)
        with patch.object(orch, "_load_env"):
            results = await orch._search_tracker(tracker, "test", "all")
            assert results == []


# --------------------------------------------------------------------------
# HTML parsers — deep branches
# --------------------------------------------------------------------------


class TestParseRutrackerHtmlDeep:
    def test_negative_seeds_clamped_to_zero(self, search_mod):
        """Lines 1243-1244: negative seeds clamped to 0."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<tr id="trs-tr-123" class="hl-tr">'
            '<td class="topictitle">'
            '<a data-topic_id="123" href="/forum/viewtopic.php?t=123">Movie</a>'
            '</td>'
            '<td data-ts_text="10737418240"></td>'
            '<td data-ts_text="-5"></td>'
            '<td class="leechmed"><a>10</a></td>'
            '<td data-ts_text="1700000000"></td>'
            '</tr>'
        )
        results = orch._parse_rutracker_html(html, "https://rutracker.org")
        assert len(results) == 1
        assert results[0].seeds == 0

    def test_zero_size_result(self, search_mod):
        """Lines 1241, 1247-1251: size=0 fallback."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<tr id="trs-tr-123" class="hl-tr">'
            '<td class="topictitle">'
            '<a data-topic_id="123" href="/forum/viewtopic.php?t=123">Small</a>'
            '</td>'
            '<td data-ts_text="0"></td>'
            '<td data-ts_text="5"></td>'
            '<td class="leechmed"><a>1</a></td>'
            '<td data-ts_text="1700000000"></td>'
            '</tr>'
        )
        results = orch._parse_rutracker_html(html, "https://rutracker.org")
        assert len(results) == 1
        assert results[0].size == "0 B"

    def test_html_entities_in_title(self, search_mod):
        """Line 1239: html.unescape on title."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<tr id="trs-tr-123" class="hl-tr">'
            '<td class="topictitle">'
            '<a data-topic_id="123" href="/forum/viewtopic.php?t=123">Movie &amp; Friends</a>'
            '</td>'
            '<td data-ts_text="1073741824"></td>'
            '<td data-ts_text="10"></td>'
            '<td class="leechmed"><a>2</a></td>'
            '<td data-ts_text="1700000000"></td>'
            '</tr>'
        )
        results = orch._parse_rutracker_html(html, "https://rutracker.org")
        assert len(results) == 1
        assert results[0].name == "Movie & Friends"

    def test_multiple_rows(self, search_mod):
        """Lines 1234-1264: multiple rows parsed."""
        orch = search_mod.SearchOrchestrator()
        rows = []
        for i in range(5):
            rows.append(
                f'<tr id="trs-tr-{i}" class="hl-tr">'
                f'<td class="topictitle">'
                f'<a data-topic_id="{i}" href="/forum/viewtopic.php?t={i}">Movie {i}</a>'
                f'</td>'
                f'<td data-ts_text="{(i + 1) * 1073741824}"></td>'
                f'<td data-ts_text="{i * 10}"></td>'
                f'<td class="leechmed"><a>{i}</a></td>'
                f'<td data-ts_text="1700000000"></td>'
                f'</tr>'
            )
        html = "".join(rows)
        results = orch._parse_rutracker_html(html, "https://rutracker.org")
        assert len(results) == 5

    def test_empty_html(self, search_mod):
        """Lines 1234: empty HTML returns empty list."""
        orch = search_mod.SearchOrchestrator()
        results = orch._parse_rutracker_html("", "https://rutracker.org")
        assert results == []


class TestParseKinozalHtmlDeep:
    def test_html_entities_in_name(self, search_mod):
        """Lines 1377, 1373: unescape on name."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<td class="nam"><a href="/details.php?id=456" class="r0">Movie &lt;Special&gt;</a></td>'
            '<td class=s\'>&nbsp;</td>'
            "<td class=s'>1.5 GB</td>"
            "<td class=sl_s'>25</td>"
            "<td class=sl_p'>5</td>"
            "<td class=s'>2024-01-01</td>"
        )
        results = orch._parse_kinozal_html(html, "https://kinozal.tv")
        assert len(results) == 1
        assert results[0].name == "Movie <Special>"

    def test_cyrillic_size_translation(self, search_mod):
        """Lines 1373-1378: Cyrillic characters in size string translated."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<td class="nam"><a href="/details.php?id=456" class="r0">Movie</a></td>'
            '<td class=s\'>&nbsp;</td>'
            "<td class=s'>1.5 ГБ</td>"
            "<td class=sl_s'>25</td>"
            "<td class=sl_p'>5</td>"
            "<td class=s'>2024-01-01</td>"
        )
        results = orch._parse_kinozal_html(html, "https://kinozal.tv")
        assert len(results) == 1
        assert "GB" in results[0].size

    def test_empty_html(self, search_mod):
        """Lines 1369: empty HTML returns empty list."""
        orch = search_mod.SearchOrchestrator()
        results = orch._parse_kinozal_html("", "https://kinozal.tv")
        assert results == []

    def test_url_dl_uses_dl_subdomain(self, search_mod):
        """Lines 1367, 1381: dl URL uses dl. subdomain."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<td class="nam"><a href="/details.php?id=456" class="r0">Movie</a></td>'
            '<td class=s\'>&nbsp;</td>'
            "<td class=s'>1.5 GB</td>"
            "<td class=sl_s'>25</td>"
            "<td class=sl_p'>5</td>"
            "<td class=s'>2024-01-01</td>"
        )
        results = orch._parse_kinozal_html(html, "https://kinozal.tv")
        assert "dl.kinozal.tv" in results[0].link


class TestParseNnmclubHtmlDeep:
    def test_html_entities_in_name(self, search_mod):
        """Line 1511: unescape on name."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<a class="topictitle" href="viewtopic.php?t=789"><b>Show &amp; Tell</b></a></span>'
            '<td><a href="dlink.php?id=789">download</a></td>'
            '<td><u>500</u></td>'
            '<td><b>30</b></td>'
            '<td><b>2</b></td>'
            '<td><u>1609459200</u></td>'
        )
        results = orch._parse_nnmclub_html(html, "https://nnmclub.to")
        assert len(results) == 1
        assert results[0].name == "Show & Tell"

    def test_empty_html(self, search_mod):
        """Lines 1509: empty HTML returns empty list."""
        orch = search_mod.SearchOrchestrator()
        results = orch._parse_nnmclub_html("", "https://nnmclub.to")
        assert results == []


class TestParseIptorrentsHtmlDeep:
    def test_freeleech_already_has_tag(self, search_mod):
        """Lines 1630-1631: freeleech tag not duplicated."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<table id="torrents"><tr>'
            '<td><a class=" hv" href="/t/789">Free Torrent [free]</a></td>'
            '<td><a href="/download.php/789/free.torrent">dl</a></td>'
            '<td>1 GB</td>'
            '<td>20</td>'
            '<td>3</td>'
            '<td class="free">free</td>'
            '</tr></table>'
        )
        results = orch._parse_iptorrents_html(html, "https://iptorrents.com")
        assert len(results) == 1
        assert results[0].name.count("[free]") == 1

    def test_no_size_match(self, search_mod):
        """Lines 1621-1622, 1638: no size match defaults to 0 B."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<table id="torrents"><tr>'
            '<td><a class=" hv" href="/t/999">No Size</a></td>'
            '<td><a href="/download.php/999/nosize.torrent">dl</a></td>'
            '<td>unknown</td>'
            '<td>10</td>'
            '<td>1</td>'
            '</tr></table>'
        )
        results = orch._parse_iptorrents_html(html, "https://iptorrents.com")
        assert len(results) == 1
        assert results[0].size == "0 B"

    def test_no_leechers_column(self, search_mod):
        """Lines 1624-1625: missing leechers defaults to 0."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<table id="torrents"><tr>'
            '<td><a class=" hv" href="/t/888">Only Seeds</a></td>'
            '<td><a href="/download.php/888/onlyseeds.torrent">dl</a></td>'
            '<td>1 GB</td>'
            '<td>50</td>'
            '</tr></table>'
        )
        results = orch._parse_iptorrents_html(html, "https://iptorrents.com")
        assert len(results) == 1
        assert results[0].seeds == 50
        assert results[0].leechers == 0

    def test_empty_rows_only_th(self, search_mod):
        """Lines 1604-1607: header rows skipped."""
        orch = search_mod.SearchOrchestrator()
        html = (
            '<table id="torrents"><tr><th>Name</th><th>Size</th></tr></table>'
        )
        results = orch._parse_iptorrents_html(html, "https://iptorrents.com")
        assert results == []


# --------------------------------------------------------------------------
# fetch_torrent — deep paths (lines 1656-1750)
# --------------------------------------------------------------------------


class TestFetchTorrentDeep:
    @pytest.mark.asyncio
    async def test_fetch_torrent_no_session_no_probe(self, search_mod):
        """Lines 1679-1681: no session data returns None."""
        orch = search_mod.SearchOrchestrator()
        with patch.object(orch, "_load_env"):
            with patch.object(orch, "_search_rutracker", side_effect=RuntimeError("fail")):
                result = await orch.fetch_torrent("rutracker", "http://example.com/file.torrent")
                assert result is None

    @pytest.mark.asyncio
    async def test_fetch_torrent_torrent_file_detected(self, search_mod):
        """Lines 1695-1701: torrent file detected by content-type."""
        orch = search_mod.SearchOrchestrator()
        orch._tracker_sessions["rutracker"] = {
            "cookies": {"sid": "abc"},
            "base_url": "https://rutracker.org",
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "application/x-bittorrent"}
        mock_resp.read = AsyncMock(return_value=b"d8:announce4:test")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await orch.fetch_torrent("rutracker", "http://example.com/file.torrent")
            assert result is not None

    @pytest.mark.asyncio
    async def test_fetch_torrent_bencode_prefix_detected(self, search_mod):
        """Lines 1697-1700: bencode prefix detection."""
        orch = search_mod.SearchOrchestrator()
        orch._tracker_sessions["kinozal"] = {
            "cookies": {"sid": "abc"},
            "base_url": "https://kinozal.tv",
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.read = AsyncMock(return_value=b"d8:announce4:test")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await orch.fetch_torrent("kinozal", "http://example.com/file.torrent")
            assert result is not None

    @pytest.mark.asyncio
    async def test_fetch_torrent_http_error_returns_none(self, search_mod):
        """Lines 1690-1692: non-200 status returns None."""
        orch = search_mod.SearchOrchestrator()
        orch._tracker_sessions["rutracker"] = {
            "cookies": {"sid": "abc"},
            "base_url": "https://rutracker.org",
        }
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await orch.fetch_torrent("rutracker", "http://example.com/file.torrent")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_torrent_non_torrent_non_redirect(self, search_mod):
        """Lines 1706-1707: non-torrent response returns None."""
        orch = search_mod.SearchOrchestrator()
        orch._tracker_sessions["nnmclub"] = {
            "cookies": {"sid": "abc"},
            "base_url": "https://nnmclub.to",
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.read = AsyncMock(return_value=b"<html>not a torrent</html>")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await orch.fetch_torrent("nnmclub", "http://example.com/file.torrent")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_torrent_rutracker_redirect(self, search_mod):
        """Lines 1702-1703, 1714-1734: rutracker redirect fallback."""
        orch = search_mod.SearchOrchestrator()
        orch._tracker_sessions["rutracker"] = {
            "cookies": {"sid": "abc"},
            "base_url": "https://rutracker.org",
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.read = AsyncMock(return_value=b"<html>click download</html>")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        redirect_resp = AsyncMock()
        redirect_resp.status = 200
        redirect_resp.read = AsyncMock(return_value=b"d8:announce4:test")
        redirect_resp.__aenter__ = AsyncMock(return_value=redirect_resp)
        redirect_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=[mock_resp, redirect_resp])
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await orch.fetch_torrent("rutracker", "http://rutracker.org/forum/dl.php?t=123")
            assert result is not None

    @pytest.mark.asyncio
    async def test_fetch_torrent_kinozal_torrent(self, search_mod):
        """Lines 1704-1705, 1736-1750: kinozal torrent fetch."""
        orch = search_mod.SearchOrchestrator()
        orch._tracker_sessions["kinozal"] = {
            "cookies": {"sid": "abc"},
            "base_url": "https://kinozal.tv",
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.read = AsyncMock(return_value=b"<html>not torrent</html>")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        kinozal_resp = AsyncMock()
        kinozal_resp.status = 200
        kinozal_resp.read = AsyncMock(return_value=b"d10:created by4:test")
        kinozal_resp.__aenter__ = AsyncMock(return_value=kinozal_resp)
        kinozal_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=[mock_resp, kinozal_resp])
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await orch.fetch_torrent("kinozal", "https://kinozal.tv/download.php?id=456")
            assert result is not None

    @pytest.mark.asyncio
    async def test_fetch_torrent_client_error_reraises(self, search_mod):
        """Lines 1708-1709: aiohttp.ClientError re-raised (after retry exhaustion)."""
        import aiohttp as _aiohttp

        orch = search_mod.SearchOrchestrator()
        orch._tracker_sessions["rutracker"] = {
            "cookies": {"sid": "abc"},
            "base_url": "https://rutracker.org",
        }
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=_aiohttp.ClientError("connection refused"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=mock_session):
            from tenacity import RetryError
            with pytest.raises(RetryError):
                await orch.fetch_torrent("rutracker", "http://example.com/file.torrent")

    @pytest.mark.asyncio
    async def test_fetch_torrent_generic_exception_returns_none(self, search_mod):
        """Lines 1710-1712: generic exception returns None."""
        orch = search_mod.SearchOrchestrator()
        orch._tracker_sessions["rutracker"] = {
            "cookies": {"sid": "abc"},
            "base_url": "https://rutracker.org",
        }
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=RuntimeError("unexpected"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await orch.fetch_torrent("rutracker", "http://example.com/file.torrent")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_torrent_session_has_bounded_timeout(self, search_mod):
        """Regression guard (§11.4.135 / §11.4.69): fetch_torrent's ClientSession
        MUST be constructed with a non-None ClientTimeout (total≈30) so the
        download cannot hang the proxy event loop indefinitely. A regression
        that drops the ``timeout=`` argument (the latent enricher-hang twin)
        fails this test.
        """
        import aiohttp

        orch = search_mod.SearchOrchestrator()
        orch._tracker_sessions["rutracker"] = {
            "cookies": {"sid": "abc"},
            "base_url": "https://rutracker.org",
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.headers = {"Content-Type": "application/x-bittorrent"}
        mock_resp.read = AsyncMock(return_value=b"d8:announce4:test")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        spy = MagicMock(return_value=mock_session)
        with patch("aiohttp.ClientSession", spy):
            result = await orch.fetch_torrent("rutracker", "http://example.com/file.torrent")

        assert result is not None
        spy.assert_called_once()
        passed_timeout = spy.call_args.kwargs.get("timeout")
        assert passed_timeout is not None, "fetch_torrent ClientSession created with no timeout"
        assert isinstance(passed_timeout, aiohttp.ClientTimeout)
        assert passed_timeout.total == pytest.approx(30)


# --------------------------------------------------------------------------
# _fetch_rutracker_redirect — deep paths
# --------------------------------------------------------------------------


class TestFetchRutrackerRedirect:
    @pytest.mark.asyncio
    async def test_no_topic_id_returns_none(self, search_mod):
        """Lines 1720-1722: no topic ID in URL returns None."""
        orch = search_mod.SearchOrchestrator()
        session = AsyncMock()
        result = await orch._fetch_rutracker_redirect(session, "http://example.com/no-id", {}, "https://rutracker.org")
        assert result is None

    @pytest.mark.asyncio
    async def test_rss_not_torrent_returns_none(self, search_mod):
        """Lines 1727-1728: non-200 status returns None."""
        orch = search_mod.SearchOrchestrator()
        resp = AsyncMock()
        resp.status = 404
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)
        result = await orch._fetch_rutracker_redirect(
            session, "http://example.com/dl.php?t=123", {}, "https://rutracker.org"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_rss_torrent_content(self, search_mod):
        """Lines 1729-1731: valid torrent from RSS."""
        orch = search_mod.SearchOrchestrator()
        resp = AsyncMock()
        resp.status = 200
        resp.read = AsyncMock(return_value=b"d8:announce4:test")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)
        result = await orch._fetch_rutracker_redirect(
            session, "http://example.com/dl.php?t=123", {}, "https://rutracker.org"
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_rss_exception_returns_none(self, search_mod):
        """Lines 1732-1734: exception returns None."""
        orch = search_mod.SearchOrchestrator()
        session = AsyncMock()
        session.get = MagicMock(side_effect=RuntimeError("fail"))
        result = await orch._fetch_rutracker_redirect(
            session, "http://example.com/dl.php?t=123", {}, "https://rutracker.org"
        )
        assert result is None


# --------------------------------------------------------------------------
# _fetch_kinozal_torrent — deep paths
# --------------------------------------------------------------------------


class TestFetchKinozalTorrent:
    @pytest.mark.asyncio
    async def test_non_200_returns_none(self, search_mod):
        """Lines 1743-1744: non-200 returns None."""
        orch = search_mod.SearchOrchestrator()
        resp = AsyncMock()
        resp.status = 500
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)
        result = await orch._fetch_kinozal_torrent(
            session, "http://example.com/file.torrent", {}, "https://kinozal.tv"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_torrent_content(self, search_mod):
        """Lines 1745-1747: valid torrent content."""
        orch = search_mod.SearchOrchestrator()
        resp = AsyncMock()
        resp.status = 200
        resp.read = AsyncMock(return_value=b"d10:created by4:test")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)
        result = await orch._fetch_kinozal_torrent(
            session, "http://example.com/file.torrent", {}, "https://kinozal.tv"
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, search_mod):
        """Lines 1748-1750: exception returns None."""
        orch = search_mod.SearchOrchestrator()
        session = AsyncMock()
        session.get = MagicMock(side_effect=RuntimeError("fail"))
        result = await orch._fetch_kinozal_torrent(
            session, "http://example.com/file.torrent", {}, "https://kinozal.tv"
        )
        assert result is None


# --------------------------------------------------------------------------
# _search_rutracker — deep paths (lines 1137-1210)
# --------------------------------------------------------------------------


class TestSearchRutrackerDeep:
    @pytest.mark.asyncio
    async def test_rutracker_no_creds_returns_empty(self, search_mod):
        """Lines 1149-1150: no credentials returns empty."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {}, clear=True):
            result = await orch._search_rutracker("query", "all")
            assert result == []

    @pytest.mark.asyncio
    async def test_rutracker_captcha_page_returns_empty(self, search_mod):
        """Lines 1196-1204: CAPTCHA page detected."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False):
            login_cookie = MagicMock()
            login_cookie.key = "bb_session"
            login_cookie.value = "abc123"
            login_resp = AsyncMock()
            login_resp.status = 200
            login_resp.cookies = {"bb_session": login_cookie}
            login_resp.__aenter__ = AsyncMock(return_value=login_resp)
            login_resp.__aexit__ = AsyncMock(return_value=False)
            search_resp = AsyncMock()
            search_resp.status = 200
            search_resp.text = AsyncMock(return_value="captcha challenge page")
            search_resp.__aenter__ = AsyncMock(return_value=search_resp)
            search_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session = AsyncMock()
            mock_session.post = MagicMock(return_value=login_resp)
            mock_session.get = MagicMock(return_value=search_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await orch._search_rutracker("query", "all")
                assert result == []
                diag = orch._last_public_tracker_diag.get("rutracker", {})
                assert diag.get("error_type") == "upstream_captcha"

    @pytest.mark.asyncio
    async def test_rutracker_no_session_cookie(self, search_mod):
        """Lines 1183-1191: no bb_ session cookie detected."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"RUTRACKER_USERNAME": "u", "RUTRACKER_PASSWORD": "p"}, clear=False):
            login_resp = AsyncMock()
            login_resp.status = 200
            login_resp.cookies = {}
            login_resp.__aenter__ = AsyncMock(return_value=login_resp)
            login_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session = AsyncMock()
            mock_session.post = MagicMock(return_value=login_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await orch._search_rutracker("query", "all")
                assert result == []
                diag = orch._last_public_tracker_diag.get("rutracker", {})
                assert diag.get("error_type") == "auth_failure"


# --------------------------------------------------------------------------
# _search_kinozal — deep paths (lines 1298-1351)
# --------------------------------------------------------------------------


class TestSearchKinozalDeep:
    @pytest.mark.asyncio
    async def test_kinozal_login_failure_returns_empty(self, search_mod):
        """Lines 1325-1327: login failure returns empty."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"KINOZAL_USERNAME": "u", "KINOZAL_PASSWORD": "p"}, clear=False):
            login_resp = AsyncMock()
            login_resp.status = 401
            login_resp.cookies = {}
            login_resp.__aenter__ = AsyncMock(return_value=login_resp)
            login_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session = AsyncMock()
            mock_session.post = MagicMock(return_value=login_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await orch._search_kinozal("query", "all")
                assert result == []

    @pytest.mark.asyncio
    async def test_kinozal_gzip_response(self, search_mod):
        """Lines 1336-1337: gzip decompression of response."""
        import gzip

        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"KINOZAL_USERNAME": "u", "KINOZAL_PASSWORD": "p"}, clear=False):
            login_resp = AsyncMock()
            login_resp.status = 200
            login_resp.cookies = {}
            login_resp.__aenter__ = AsyncMock(return_value=login_resp)
            login_resp.__aexit__ = AsyncMock(return_value=False)
            search_resp = AsyncMock()
            search_resp.status = 200
            search_resp.read = AsyncMock(return_value=gzip.compress(b"<html>no results</html>"))
            search_resp.cookies = {}
            search_resp.__aenter__ = AsyncMock(return_value=search_resp)
            search_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session = AsyncMock()
            mock_session.post = MagicMock(return_value=login_resp)
            mock_session.get = MagicMock(return_value=search_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await orch._search_kinozal("query", "all")
                assert result == []


# --------------------------------------------------------------------------
# _nnmclub_login — deep paths (lines 1442-1493)
# --------------------------------------------------------------------------


class TestNnmclubLoginDeep:
    @pytest.mark.asyncio
    async def test_nnmclub_login_no_session_cookie(self, search_mod):
        """Lines 1478-1489: no phpbb2mysql_4_sid cookie."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"NNMCLUB_USERNAME": "u", "NNMCLUB_PASSWORD": "p"}, clear=False):
            login_resp = AsyncMock()
            login_resp.status = 200
            login_resp.cookies = {}
            login_resp.__aenter__ = AsyncMock(return_value=login_resp)
            login_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session = AsyncMock()
            mock_session.post = MagicMock(return_value=login_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await orch._nnmclub_login("https://nnmclub.to")
                assert result == {}
                diag = orch._last_public_tracker_diag.get("nnmclub", {})
                assert diag.get("error_type") == "auth_failure"

    @pytest.mark.asyncio
    async def test_nnmclub_login_exception_returns_empty(self, search_mod):
        """Lines 1491-1493: exception returns empty."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"NNMCLUB_USERNAME": "u", "NNMCLUB_PASSWORD": "p"}, clear=False):
            mock_session = AsyncMock()
            mock_session.post = MagicMock(side_effect=RuntimeError("network error"))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await orch._nnmclub_login("https://nnmclub.to")
                assert result == {}


# --------------------------------------------------------------------------
# _search_nnmclub — deep paths (lines 1395-1440)
# --------------------------------------------------------------------------


class TestSearchNnmclubDeep:
    @pytest.mark.asyncio
    async def test_nnmclub_with_cookies_raw(self, search_mod):
        """Lines 1408-1415: raw cookie parsing from NNMCLUB_COOKIES."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"NNMCLUB_COOKIES": "sid=abc123; phpbb2mysql_4_sid=def456"}, clear=False):
            search_resp = AsyncMock()
            search_resp.status = 200
            search_resp.read = AsyncMock(return_value=b"<html>no results</html>")
            search_resp.__aenter__ = AsyncMock(return_value=search_resp)
            search_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session = AsyncMock()
            mock_session.get = MagicMock(return_value=search_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await orch._search_nnmclub("query", "all")
                assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_nnmclub_no_session_cookie_returns_empty(self, search_mod):
        """Lines 1420-1421: missing phpbb2mysql_4_sid returns empty."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"NNMCLUB_COOKIES": "sid=abc123"}, clear=False):
            result = await orch._search_nnmclub("query", "all")
            assert result == []


# --------------------------------------------------------------------------
# _search_iptorrents — deep paths (lines 1532-1590)
# --------------------------------------------------------------------------


class TestSearchIptorrentsDeep:
    @pytest.mark.asyncio
    async def test_iptorrents_category_mapped(self, search_mod):
        """Lines 1575-1576: category mapping applied."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"IPTORRENTS_USERNAME": "u", "IPTORRENTS_PASSWORD": "p"}, clear=False):
            login_resp = AsyncMock()
            login_resp.status = 200
            login_resp.cookies = {}
            login_resp.__aenter__ = AsyncMock(return_value=login_resp)
            login_resp.__aexit__ = AsyncMock(return_value=False)
            search_resp = AsyncMock()
            search_resp.status = 200
            search_resp.text = AsyncMock(return_value="<html>no table</html>")
            search_resp.__aenter__ = AsyncMock(return_value=search_resp)
            search_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session = AsyncMock()
            mock_session.post = MagicMock(return_value=login_resp)
            mock_session.get = MagicMock(return_value=search_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await orch._search_iptorrents("query", "movies")
                assert result == []

    @pytest.mark.asyncio
    async def test_iptorrents_login_no_cookies(self, search_mod):
        """Lines 1566-1567: login failure logged."""
        orch = search_mod.SearchOrchestrator()
        with patch.dict(os.environ, {"IPTORRENTS_USERNAME": "u", "IPTORRENTS_PASSWORD": "p"}, clear=False):
            login_resp = MagicMock()
            login_resp.status = 403
            login_resp.cookies = {}
            login_resp.text = AsyncMock(return_value="")
            login_resp.__aenter__ = AsyncMock(return_value=login_resp)
            login_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=login_resp)
            mock_session.get = MagicMock(return_value=login_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await orch._search_iptorrents("query", "all")
                assert result == []


# --------------------------------------------------------------------------
# _run_search — deep paths (lines 716-869)
# --------------------------------------------------------------------------


class TestRunSearchDeep:
    @pytest.mark.asyncio
    async def test_run_search_cancelled_error(self, search_mod):
        """Lines 859-862: CancelledError sets status to aborted."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id

        async def fake_gather(*args, **kwargs):
            raise asyncio.CancelledError()

        with patch.object(orch, "_get_enabled_trackers", return_value=[]):
            with patch("asyncio.gather", side_effect=fake_gather):
                with pytest.raises(asyncio.CancelledError):
                    await orch._run_search(search_id, "test")
                assert meta.status == "aborted"

    @pytest.mark.asyncio
    async def test_run_search_generic_exception(self, search_mod):
        """Lines 863-866: generic exception sets status to failed."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id

        with patch.object(orch, "_get_enabled_trackers", side_effect=RuntimeError("boom")):
            await orch._run_search(search_id, "test")
            assert meta.status == "failed"

    @pytest.mark.asyncio
    async def test_run_search_aborted_before_start(self, search_mod):
        """Lines 834-836: aborted status skips fan-out."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        meta.status = "aborted"
        search_id = meta.search_id
        await orch._run_search(search_id, "test")
        assert meta.status == "aborted"

    @pytest.mark.asyncio
    async def test_run_search_aborted_after_gather(self, search_mod):
        """Lines 840-842: aborted status after gather skips merge."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id

        with patch.object(orch, "_get_enabled_trackers", return_value=[]):
            with patch("asyncio.gather", return_value=[]):
                meta.status = "aborted"
                await orch._run_search(search_id, "test")
                assert meta.status == "aborted"

    @pytest.mark.asyncio
    async def test_run_search_base_exception_in_results(self, search_mod):
        """Lines 846-848: BaseException in gather results is logged."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id

        with patch.object(orch, "_get_enabled_trackers", return_value=[]):
            with patch("asyncio.gather", new_callable=AsyncMock, return_value=[RuntimeError("tracker crashed")]):
                await orch._run_search(search_id, "test")
                assert any("uncaught exception" in e for e in meta.errors)


# --------------------------------------------------------------------------
# _search_one — exception branches (lines 782-822)
# --------------------------------------------------------------------------


class TestSearchOneException:
    @pytest.mark.asyncio
    async def test_search_one_timeout_exception(self, search_mod):
        """Lines 808-813: TimeoutError sets status to timeout."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id
        tracker = search_mod.TrackerSource(name="rutor", url="https://rutor.info", enabled=True)

        with patch.object(orch, "_search_tracker", side_effect=TimeoutError("deadline exceeded")):
            with patch.object(orch, "_get_enabled_trackers", return_value=[tracker]):
                with patch("asyncio.gather", wraps=None) as mock_gather:
                    async def fake_gather(*args, **kwargs):
                        coro = args[0]
                        return [await coro]

                    mock_gather.side_effect = fake_gather
                    await orch._run_search(search_id, "test")
                    stat = meta.tracker_stats.get("rutor")
                    if stat:
                        assert stat.status == "timeout"

    @pytest.mark.asyncio
    async def test_search_one_generic_exception(self, search_mod):
        """Lines 814-819: generic exception sets status to error."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id
        tracker = search_mod.TrackerSource(name="rutor", url="https://rutor.info", enabled=True)

        with patch.object(orch, "_search_tracker", side_effect=RuntimeError("network error")):
            with patch.object(orch, "_get_enabled_trackers", return_value=[tracker]):
                async def fake_gather(*args, **kwargs):
                    coro = args[0]
                    return [await coro]

                with patch("asyncio.gather", side_effect=fake_gather):
                    await orch._run_search(search_id, "test")
                    stat = meta.tracker_stats.get("rutor")
                    if stat:
                        assert stat.status == "error"

    @pytest.mark.asyncio
    async def test_search_one_aborted_returns_early(self, search_mod):
        """Lines 765-766: aborted search returns early."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id
        meta.status = "aborted"
        tracker = search_mod.TrackerSource(name="rutor", url="https://rutor.info", enabled=True)
        with patch.object(orch, "_get_enabled_trackers", return_value=[tracker]):
            await orch._run_search(search_id, "test")
            assert meta.status == "aborted"


# --------------------------------------------------------------------------
# _search_one — diag side-channel (lines 795-806)
# --------------------------------------------------------------------------


class TestSearchOneDiag:
    @pytest.mark.asyncio
    async def test_diag_with_error_type_sets_stat(self, search_mod):
        """Lines 796-806: diag side-channel populates stat after _search_tracker returns."""
        orch = search_mod.SearchOrchestrator()
        tracker = search_mod.TrackerSource(name="piratebay", url="https://thepiratebay.org", enabled=True)

        with patch.object(orch, "_get_enabled_trackers", return_value=[tracker]):
            with patch.object(orch, "_search_tracker", return_value=[]) as mock_search:
                # Set the diag AFTER _search_tracker is called but BEFORE
                # the code reads it. We use a side_effect on _search_tracker
                # to set the diag at the right moment.
                def set_diag_and_return(tracker, query, category):
                    orch._last_public_tracker_diag["piratebay"] = {
                        "error_type": "upstream_http_403",
                        "error": "upstream returned HTTP 403 Forbidden",
                        "stderr_tail": "HTTP Error 403",
                        "deadline_hit": False,
                        "deadline_seconds": 60.0,
                    }
                    return []

                mock_search.side_effect = set_diag_and_return
                meta = orch.start_search("test")
                search_id = meta.search_id
                await orch._run_search(search_id, "test")
                stat = meta.tracker_stats.get("piratebay")
                assert stat is not None
                assert stat.error_type == "upstream_http_403"
                assert stat.status == "error"
                assert stat.notes.get("stderr_tail") == "HTTP Error 403"

    @pytest.mark.asyncio
    async def test_diag_with_deadline_hit(self, search_mod):
        """Lines 804-806: deadline_hit in diag sets notes."""
        orch = search_mod.SearchOrchestrator()
        tracker = search_mod.TrackerSource(name="piratebay", url="https://thepiratebay.org", enabled=True)

        with patch.object(orch, "_get_enabled_trackers", return_value=[tracker]):
            with patch.object(orch, "_search_tracker", return_value=[]) as mock_search:
                def set_diag_and_return(tracker, query, category):
                    orch._last_public_tracker_diag["piratebay"] = {
                        "error_type": None,
                        "error": None,
                        "stderr_tail": "",
                        "deadline_hit": True,
                        "deadline_seconds": 60.0,
                    }
                    return []

                mock_search.side_effect = set_diag_and_return
                meta = orch.start_search("test")
                search_id = meta.search_id
                await orch._run_search(search_id, "test")
                stat = meta.tracker_stats.get("piratebay")
                assert stat is not None
                assert stat.notes.get("deadline_hit") is True
                assert stat.notes.get("deadline_seconds") == 60.0

    @pytest.mark.asyncio
    async def test_diag_no_stat_creats_one(self, search_mod):
        """Lines 768-778: defensive stat creation when missing."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id
        tracker = search_mod.TrackerSource(name="rutor", url="https://rutor.info", enabled=True)
        # Remove the stat that start_search seeded
        meta.tracker_stats.clear()

        with patch.object(orch, "_search_tracker", return_value=[]):
            with patch.object(orch, "_get_enabled_trackers", return_value=[tracker]):
                async def fake_gather(*args, **kwargs):
                    coro = args[0]
                    return [await coro]

                with patch("asyncio.gather", side_effect=fake_gather):
                    await orch._run_search(search_id, "test")
                    assert "rutor" in meta.tracker_stats


# --------------------------------------------------------------------------
# _search_one — aborted check after gather (line 840)
# --------------------------------------------------------------------------


class TestRunSearchAbortCheck:
    @pytest.mark.asyncio
    async def test_run_search_checks_abort_after_gather(self, search_mod):
        """Lines 840-842: abort checked after gather completes."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id

        async def fake_gather(*args, **kwargs):
            meta.status = "aborted"
            return []

        with patch.object(orch, "_get_enabled_trackers", return_value=[]):
            with patch("asyncio.gather", side_effect=fake_gather):
                await orch._run_search(search_id, "test")
                assert meta.status == "aborted"


# --------------------------------------------------------------------------
# _search_one — stat seeded by _run_search (lines 753-762)
# --------------------------------------------------------------------------


class TestRunSearchStatSeed:
    @pytest.mark.asyncio
    async def test_run_search_backfills_missing_stats(self, search_mod):
        """Lines 753-762: _run_search backfills missing tracker_stats."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id
        tracker = search_mod.TrackerSource(name="piratebay", url="https://thepiratebay.org", enabled=True)

        with patch.object(orch, "_get_enabled_trackers", return_value=[tracker]):
            with patch("asyncio.gather", return_value=[]):
                await orch._run_search(search_id, "test")
                assert "piratebay" in meta.tracker_stats
                stat = meta.tracker_stats["piratebay"]
                assert stat.status == "pending"


# --------------------------------------------------------------------------
# _run_search — clearing stale diag entries (line 747)
# --------------------------------------------------------------------------


class TestRunSearchDiagClear:
    @pytest.mark.asyncio
    async def test_run_search_clears_stale_diag(self, search_mod):
        """Lines 746-747: stale diag entries cleared before fan-out."""
        orch = search_mod.SearchOrchestrator()
        meta = orch.start_search("test")
        search_id = meta.search_id

        orch._last_public_tracker_diag["rutor"] = {"error_type": "stale"}
        orch._last_public_tracker_diag["piratebay"] = {"error_type": "stale"}

        tracker = search_mod.TrackerSource(name="rutor", url="https://rutor.info", enabled=True)
        with patch.object(orch, "_get_enabled_trackers", return_value=[tracker]):
            with patch("asyncio.gather", return_value=[]):
                await orch._run_search(search_id, "test")
                assert "rutor" not in orch._last_public_tracker_diag


# --------------------------------------------------------------------------
# SearchResult — tracker_display edge cases
# --------------------------------------------------------------------------


class TestSearchResultTrackerDisplay:
    def test_tracker_display_with_freeleech_and_tracker(self, search_mod):
        """Lines 130-131: freeleech + tracker → 'tracker [free]'."""
        r = search_mod.SearchResult(
            name="Test", link="http://x", size="1 GB", seeds=10, leechers=5,
            engine_url="http://x", tracker="iptorrents", freeleech=True,
        )
        assert r.to_dict()["tracker_display"] == "iptorrents [free]"

    def test_tracker_display_with_tracker_no_freeleech(self, search_mod):
        """Lines 132-133: tracker without freeleech → tracker name."""
        r = search_mod.SearchResult(
            name="Test", link="http://x", size="1 GB", seeds=10, leechers=5,
            engine_url="http://x", tracker="rutor", freeleech=False,
        )
        assert r.to_dict()["tracker_display"] == "rutor"

    def test_tracker_display_no_tracker(self, search_mod):
        """Lines 134-135: no tracker → None."""
        r = search_mod.SearchResult(
            name="Test", link="http://x", size="1 GB", seeds=10, leechers=5,
            engine_url="http://x", tracker=None, freeleech=False,
        )
        assert r.to_dict()["tracker_display"] is None


# --------------------------------------------------------------------------
# _detect_result_metadata — audiobook content type
# --------------------------------------------------------------------------


class TestDetectAudiobook:
    def test_audiobook_detected(self, search_mod):
        """Line 149: audiobook content type."""
        ct, q = search_mod._detect_result_metadata("Great Audiobook Unabridged", "500 MB")
        assert ct == "audiobook"


# --------------------------------------------------------------------------
# _load_env — fallback file not found
# --------------------------------------------------------------------------


class TestLoadEnvFallbackPaths:
    def test_fallback_all_files_missing(self, search_mod):
        """Lines 632-648: all fallback files missing."""
        orch = search_mod.SearchOrchestrator()
        mock_config = type(sys)("config")
        mock_config.load_env = lambda: (_ for _ in ()).throw(Exception("fail"))
        with patch.dict("sys.modules", {"config": mock_config}):
            with patch("os.path.isfile", return_value=False):
                orch._load_env()

    def test_fallback_file_read_error(self, search_mod):
        """Lines 647-648: file read error is caught."""
        orch = search_mod.SearchOrchestrator()
        mock_config = type(sys)("config")
        mock_config.load_env = lambda: (_ for _ in ()).throw(Exception("fail"))
        with patch.dict("sys.modules", {"config": mock_config}):
            with patch("os.path.isfile", return_value=True):
                with patch("builtins.open", side_effect=PermissionError("denied")):
                    orch._load_env()
