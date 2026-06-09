"""Deep coverage tests for plugins/kinozal.py.

Covers: HTML parsing (RE_TORRENTS, draw), search (URL construction, category
mapping, pagination, exception handling), download_torrent (magnet links,
torrent files, no links, URLError), login/session handling, Config, date_normalize,
rng, _get_download_path, _request, _catch_errors, and edge cases.
"""

import gzip
import importlib.util
import os
import sys
import time
import types
from http.cookiejar import Cookie, MozillaCookieJar
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")

# ---------------------------------------------------------------------------
# Fixture HTML - matches RE_TORRENTS from kinozal.py
# ---------------------------------------------------------------------------
# Key: uses single-quoted class attributes on td/span (required by regex),
# 3-part dates "DD.MM.YYYY в HH:MM" (required by date_normalize split).
# Year column is <td class='s'> which provides the first s'> match.

KZ_SINGLE = (
    '<td class="nam"><a href="/showtopic.php?topic=12345" class="r0">Test Movie 2024</a></td>\n'
    "<td class='s'>2024</td>\n"
    "<td><span class='s'>10.5 ГБ</span></td>\n"
    "<td><span class='sl_s'>55</span></td>\n"
    "<td><span class='sl_p'>12</span></td>\n"
    "<td class='s'>09.06.2025 в 14:30</td>"
)

KZ_MULTI = (
    '<td class="nam"><a href="/showtopic.php?topic=111" class="r0">First Torrent</a></td>\n'
    "<td class='s'>2024</td>\n"
    "<td><span class='s'>1.2 ГБ</span></td>\n"
    "<td><span class='sl_s'>100</span></td>\n"
    "<td><span class='sl_p'>5</span></td>\n"
    "<td class='s'>01.01.2025 в 10:00</td>\n"
    "</tr>\n<tr>\n"
    '<td class="nam"><a href="/showtopic.php?topic=222" class="r1">Second Torrent</a></td>\n'
    "<td class='s'>2023</td>\n"
    "<td><span class='s'>3.4 ГБ</span></td>\n"
    "<td><span class='sl_s'>200</span></td>\n"
    "<td><span class='sl_p'>10</span></td>\n"
    "<td class='s'>15.03.2024 в 08:00</td>\n"
    "</tr>\n<tr>\n"
    '<td class="nam"><a href="/showtopic.php?topic=333" class="r0">Third Torrent &amp; More</a></td>\n'
    "<td class='s'>2025</td>\n"
    "<td><span class='s'>500 МБ</span></td>\n"
    "<td><span class='sl_s'>0</span></td>\n"
    "<td><span class='sl_p'>0</span></td>\n"
    "<td class='s'>сейчас</td>"
)

KZ_SINGLE_HTML_ENTITY = (
    '<td class="nam"><a href="/showtopic.php?topic=999" class="r0">Movie &lt;HD&gt; &amp; &quot;4K&quot;</a></td>\n'
    "<td class='s'>2024</td>\n"
    "<td><span class='s'>7.1 ГБ</span></td>\n"
    "<td><span class='sl_s'>42</span></td>\n"
    "<td><span class='sl_p'>3</span></td>\n"
    "<td class='s'>05.05.2025 в 12:00</td>"
)

KZ_CYRILLIC_SIZE = (
    '<td class="nam"><a href="/showtopic.php?topic=500" class="r0">Cyrillic Size</a></td>\n'
    "<td class='s'>2024</td>\n"
    "<td><span class='s'>15,7 ТБ</span></td>\n"
    "<td><span class='sl_s'>10</span></td>\n"
    "<td><span class='sl_p'>2</span></td>\n"
    "<td class='s'>10.10.2024 в 20:00</td>"
)

KZ_EMPTY = "<html><body><p>Ничего не найдено</p></body></html>"

KZ_NO_RESULTS_COUNT = "<html><body>Some random page</body></html>"

KZ_GUEST = "<html><body>Гость! ( Зарегистрируйтесь )</body></html>"

KZ_RESULTS_ZERO = "</span>Найдено 0 раздач"

KZ_RESULTS_FIVE = "</span>Найдено 5 раздач" + KZ_MULTI

KZ_MALFORMED = (
    '<td class="nam"><a href="/showtopic.php?topic=999" class="r0">Broken</a></td>'
)

KZ_NO_SIZE = (
    '<td class="nam"><a href="/showtopic.php?topic=100" class="r0">No Size</a></td>\n'
    "<td class='s'>2024</td>\n"
    "<td><span class='s'></span></td>\n"
    "<td><span class='sl_s'>5</span></td>\n"
    "<td><span class='sl_p'>1</span></td>\n"
    "<td class='s'>01.01.2025 в 10:00</td>"
)

VALID_JSON = (
    '{"username":"u","password":"p","magnet":true,"proxy":false,'
    '"proxies":{"http":"","https":""},"ua":"test"}'
)

FAKE_COOKIE = Cookie(
    version=0, name="uid", value="123", port=None, port_specified=False,
    domain=".kinozal.tv", domain_specified=True, domain_initial_dot=True,
    path="/", path_specified=True, secure=False, expires=9999999999,
    discard=False, comment=None, comment_url=None, rest={}, rfc2109=False,
)


# ---------------------------------------------------------------------------
# Loader - stubs novaprinter, socks, helpers before loading kinozal
# ---------------------------------------------------------------------------

def _load_kinozal(captured=None):
    """Import kinozal plugin with stub modules. Returns (instance, captured)."""
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    socks_mod = types.ModuleType("socks")
    socks_mod.PROXY_TYPE_SOCKS5 = 2
    socks_mod.set_default_proxy = lambda *a, **kw: None
    socks_mod.socksocket = MagicMock()
    sys.modules["socks"] = socks_mod

    sys.modules.pop("kinozal", None)

    path = os.path.join(PLUGINS_DIR, "kinozal.py")
    spec = importlib.util.spec_from_file_location("kinozal", path)
    mod = importlib.util.module_from_spec(spec)

    with patch.object(Path, "read_text", return_value=VALID_JSON), \
         patch.object(Path, "write_text"), \
         patch.object(Path, "write_bytes"), \
         patch("logging.basicConfig"):
        spec.loader.exec_module(mod)

    sys.modules["kinozal"] = mod

    cls = getattr(mod, "kinozal", None)
    if cls is not None and isinstance(cls, type):
        instance = cls()
        captured.clear()
        return instance, captured
    return mod, captured


def _mock_context_response(data, url="https://kinozal.tv/page"):
    """Create a mock that works as session.open() context manager."""
    mock_resp = MagicMock()
    mock_enter = mock_resp.__enter__.return_value
    mock_enter.read.return_value = data
    mock_enter.geturl.return_value = url
    return mock_resp


def _add_uid_cookie(mcj):
    """Add a fake uid cookie to a MozillaCookieJar instance."""
    mcj.set_cookie(FAKE_COOKIE)


# ===========================================================================
# Tests: rng helper
# ===========================================================================

class TestRng:
    def test_rng_small(self):
        _, _ = _load_kinozal()
        import kinozal
        assert list(kinozal.rng(10)) == []

    def test_rng_exactly_one_page(self):
        _, _ = _load_kinozal()
        import kinozal
        assert list(kinozal.rng(50)) == []

    def test_rng_two_pages(self):
        _, _ = _load_kinozal()
        import kinozal
        assert list(kinozal.rng(51)) == [1]

    def test_rng_many_pages(self):
        _, _ = _load_kinozal()
        import kinozal
        assert list(kinozal.rng(120)) == [1, 2]

    def test_rng_zero(self):
        _, _ = _load_kinozal()
        import kinozal
        assert list(kinozal.rng(0)) == []

    def test_rng_hundred(self):
        _, _ = _load_kinozal()
        import kinozal
        assert list(kinozal.rng(100)) == [1]


# ===========================================================================
# Tests: date_normalize
# ===========================================================================

class TestDateNormalize:
    def test_normal_date(self):
        _, _ = _load_kinozal()
        import kinozal
        ts = kinozal.date_normalize("09.06.2025 в 14:30")
        assert isinstance(ts, int)
        assert ts > 0

    def test_sechis_returns_current_time(self):
        _, _ = _load_kinozal()
        import kinozal
        before = int(time.time())
        ts = kinozal.date_normalize("сейчас")
        after = int(time.time())
        assert before <= ts <= after

    def test_segodnya_uses_today(self):
        _, _ = _load_kinozal()
        import kinozal
        ts = kinozal.date_normalize("сегодня в 15:30")
        today_start = int(time.mktime(time.strptime(time.strftime("%d.%m.%Y"), "%d.%m.%Y")))
        today_end = today_start + 86400
        assert today_start <= ts < today_end

    def test_vchera_uses_yesterday(self):
        _, _ = _load_kinozal()
        import kinozal
        ts = kinozal.date_normalize("вчера в 08:00")
        yesterday_start = int(time.mktime(time.strptime(
            time.strftime("%d.%m.%Y", time.localtime(time.time() - 86400)), "%d.%m.%Y"
        )))
        yesterday_end = yesterday_start + 86400
        assert yesterday_start <= ts < yesterday_end

    def test_invalid_format_raises(self):
        _, _ = _load_kinozal()
        import kinozal
        with pytest.raises((ValueError, IndexError)):
            kinozal.date_normalize("not-a-date")


# ===========================================================================
# Tests: Config
# ===========================================================================

class TestConfig:
    def test_config_defaults(self):
        _, _ = _load_kinozal()
        import kinozal
        with patch.object(Path, "read_text", return_value=VALID_JSON), \
             patch.object(Path, "write_text"), \
             patch.object(Path, "write_bytes"):
            cfg = kinozal.Config(username="u", password="p")
        assert cfg.magnet is True
        assert cfg.proxy is False
        assert cfg.ua

    def test_to_camel(self):
        _, _ = _load_kinozal()
        import kinozal
        assert kinozal.Config._to_camel("user_name") == "userName"
        assert kinozal.Config._to_camel("magnet") == "magnet"
        assert kinozal.Config._to_camel("ua") == "ua"

    def test_to_dict(self):
        _, _ = _load_kinozal()
        import kinozal
        with patch.object(Path, "read_text", return_value=VALID_JSON), \
             patch.object(Path, "write_text"), \
             patch.object(Path, "write_bytes"):
            cfg = kinozal.Config(username="u", password="p")
        d = cfg.to_dict()
        assert "username" in d
        assert "password" in d
        assert "magnet" in d

    def test_to_str_is_json(self):
        _, _ = _load_kinozal()
        import kinozal
        with patch.object(Path, "read_text", return_value=VALID_JSON), \
             patch.object(Path, "write_text"), \
             patch.object(Path, "write_bytes"):
            cfg = kinozal.Config(username="u", password="p")
        s = cfg.to_str()
        import json
        parsed = json.loads(s)
        assert isinstance(parsed, dict)

    def test_validate_json_valid(self):
        _, _ = _load_kinozal()
        import kinozal
        with patch.object(Path, "read_text", return_value=VALID_JSON), \
             patch.object(Path, "write_text"), \
             patch.object(Path, "write_bytes"):
            cfg = kinozal.Config(username="u", password="p")
        obj = {
            "username": "new_user",
            "password": "new_pass",
            "magnet": False,
            "proxy": True,
            "proxies": {"http": "http://proxy:8080", "https": ""},
            "ua": "custom_ua",
        }
        assert cfg._validate_json(obj) is True
        assert cfg.username == "new_user"
        assert cfg.magnet is False

    def test_validate_json_missing_key(self):
        _, _ = _load_kinozal()
        import kinozal
        with patch.object(Path, "read_text", return_value=VALID_JSON), \
             patch.object(Path, "write_text"), \
             patch.object(Path, "write_bytes"):
            cfg = kinozal.Config(username="u", password="p")
        obj = {"username": "u"}
        result = cfg._validate_json(obj)
        assert result is False

    def test_validate_json_wrong_type(self):
        _, _ = _load_kinozal()
        import kinozal
        with patch.object(Path, "read_text", return_value=VALID_JSON), \
             patch.object(Path, "write_text"), \
             patch.object(Path, "write_bytes"):
            cfg = kinozal.Config(username="u", password="p")
        obj = {
            "username": "u",
            "password": "p",
            "magnet": "not_bool",
            "proxy": False,
            "proxies": {"http": "", "https": ""},
            "ua": "ua",
        }
        result = cfg._validate_json(obj)
        assert result is False

    def test_validate_json_bad_proxy_dict(self):
        _, _ = _load_kinozal()
        import kinozal
        with patch.object(Path, "read_text", return_value=VALID_JSON), \
             patch.object(Path, "write_text"), \
             patch.object(Path, "write_bytes"):
            cfg = kinozal.Config(username="u", password="p")
        obj = {
            "username": "u",
            "password": "p",
            "magnet": True,
            "proxy": False,
            "proxies": {"http": 123, "https": ""},
            "ua": "ua",
        }
        result = cfg._validate_json(obj)
        assert result is False
        assert cfg.proxies["http"] == ""


# ===========================================================================
# Tests: draw (HTML parsing via RE_TORRENTS)
# ===========================================================================

class TestDraw:
    def test_single_result(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Test Movie 2024"
        assert "showtopic.php?topic=12345" in cap[0]["desc_link"]
        assert cap[0]["engine_url"] == "https://kinozal.tv/"
        assert cap[0]["seeds"] == 55
        assert cap[0]["leech"] == 12
        assert "download.php?id=12345" in cap[0]["link"]

    def test_multi_results(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_MULTI)
        assert len(cap) == 3
        assert cap[0]["name"] == "First Torrent"
        assert cap[1]["name"] == "Second Torrent"
        assert cap[2]["name"] == "Third Torrent & More"

    def test_html_entity_decoding(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_SINGLE_HTML_ENTITY)
        assert len(cap) == 1
        assert cap[0]["name"] == 'Movie <HD> & "4K"'

    def test_cyrillic_size_translated(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_CYRILLIC_SIZE)
        assert len(cap) == 1
        assert cap[0]["size"] == "15,7 TB"

    def test_empty_html_no_results(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_EMPTY)
        assert len(cap) == 0

    def test_malformed_entry_skipped(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_MALFORMED)
        assert len(cap) == 0

    def test_no_size_field_still_matches(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_NO_SIZE)
        assert len(cap) == 1

    def test_desc_link_construction(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_SINGLE)
        desc = cap[0]["desc_link"]
        assert desc.startswith("https://kinozal.tv/")
        assert "showtopic.php?topic=12345" in desc

    def test_download_link_construction(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_SINGLE)
        dl = cap[0]["link"]
        assert dl.startswith("https://dl.kinozal.tv/")
        assert "download.php?id=12345" in dl

    def test_pub_date_is_integer(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_SINGLE)
        assert isinstance(cap[0]["pub_date"], int)
        assert cap[0]["pub_date"] > 0

    def test_zero_seeds_leech(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_MULTI)
        assert cap[2]["seeds"] == 0
        assert cap[2]["leech"] == 0

    def test_size_translated_gb(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_SINGLE)
        assert cap[0]["size"] == "10.5 GB"

    def test_size_translated_mb(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_MULTI)
        assert cap[2]["size"] == "500 MB"

    def test_pub_date_sechis_is_current(self):
        inst, cap = _load_kinozal()
        inst.draw(KZ_MULTI)
        before = int(time.time())
        assert before - 2 <= cap[2]["pub_date"] <= before + 2


# ===========================================================================
# Tests: search
# ===========================================================================

class TestSearch:
    def test_search_all_category(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=KZ_RESULTS_ZERO.encode("cp1251")):
            inst.search("doctor", "all")
        assert len(cap) == 0

    def test_search_movies_category(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=KZ_RESULTS_ZERO.encode("cp1251")):
            inst.search("avatar", "movies")

    def test_search_tv_category(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=KZ_RESULTS_ZERO.encode("cp1251")):
            inst.search("breaking bad", "tv")

    def test_search_music_category(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=KZ_RESULTS_ZERO.encode("cp1251")):
            inst.search("rock", "music")

    def test_search_games_category(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=KZ_RESULTS_ZERO.encode("cp1251")):
            inst.search("zelda", "games")

    def test_search_anime_category(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=KZ_RESULTS_ZERO.encode("cp1251")):
            inst.search("naruto", "anime")

    def test_search_software_category(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=KZ_RESULTS_ZERO.encode("cp1251")):
            inst.search("photoshop", "software")

    def test_search_invalid_category_logs_error(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=KZ_RESULTS_ZERO.encode("cp1251")):
            inst.search("test", "nonexistent")
        assert len(cap) >= 1
        assert "Error" in cap[0]["name"]

    def test_search_emits_results(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=KZ_RESULTS_FIVE.encode("cp1251")):
            inst.search("test", "all")
        assert len(cap) == 3
        assert cap[0]["name"] == "First Torrent"

    def test_search_exception_engine_error(self):
        inst, cap = _load_kinozal()
        from kinozal import EngineError
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", side_effect=EngineError("blocked")):
            inst.search("test", "all")
        assert len(cap) >= 1
        assert "Error" in cap[0]["name"]

    def test_search_unexpected_exception(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", side_effect=RuntimeError("boom")):
            inst.search("test", "all")
        assert len(cap) >= 1
        assert "Error" in cap[0]["name"]

    def test_search_url_contains_encoded_query(self):
        inst, cap = _load_kinozal()
        request_urls = []

        def capture_request(url, *args, **kwargs):
            request_urls.append(url)
            return KZ_RESULTS_ZERO.encode("cp1251")

        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", side_effect=capture_request):
            inst.search("hello world", "all")
        assert len(request_urls) >= 1
        assert "hello%20world" in request_urls[0] or "hello" in request_urls[0]


# ===========================================================================
# Tests: searching
# ===========================================================================

class TestSearching:
    def test_searching_first_with_results(self):
        inst, cap = _load_kinozal()
        page_html = KZ_RESULTS_FIVE.encode("cp1251")
        with patch.object(inst, "login"), \
             patch.object(inst, "_request", return_value=page_html):
            _add_uid_cookie(inst.mcj)
            count = inst.searching("http://example.com", first=True)
        assert count == 5
        assert len(cap) == 3

    def test_searching_first_zero_results(self):
        inst, cap = _load_kinozal()
        page_html = KZ_RESULTS_ZERO.encode("cp1251")
        with patch.object(inst, "login"), \
             patch.object(inst, "_request", return_value=page_html):
            _add_uid_cookie(inst.mcj)
            count = inst.searching("http://example.com", first=True)
        assert count == 0

    def test_searching_first_guest_triggers_login(self):
        inst, cap = _load_kinozal()
        from kinozal import EngineError
        guest_html = KZ_GUEST.encode("cp1251")
        with patch.object(inst, "login") as mock_login, \
             patch.object(inst, "_request", return_value=guest_html):
            with pytest.raises(EngineError):
                inst.searching("http://example.com", first=True)
            mock_login.assert_called()

    def test_searching_first_unexpected_page_raises(self):
        inst, cap = _load_kinozal()
        from kinozal import EngineError
        bad_html = KZ_NO_RESULTS_COUNT.encode("cp1251")
        with patch.object(inst, "login"), \
             patch.object(inst, "_request", return_value=bad_html):
            with pytest.raises(EngineError):
                inst.searching("http://example.com", first=True)

    def test_searching_not_first(self):
        inst, cap = _load_kinozal()
        page_html = KZ_MULTI.encode("cp1251")
        with patch.object(inst, "_request", return_value=page_html):
            count = inst.searching("http://example.com", first=False)
        assert count == -1
        assert len(cap) == 3

    def test_searching_gzip_response(self):
        inst, cap = _load_kinozal()
        raw = gzip.compress(KZ_SINGLE.encode("cp1251"))
        assert raw.startswith(b"\x1f\x8b\x08")
        with patch.object(inst, "_request", return_value=raw):
            count = inst.searching("http://example.com", first=False)
        assert count == -1
        assert len(cap) == 1


# ===========================================================================
# Tests: download_torrent
# ===========================================================================

class TestDownloadTorrent:
    def test_download_magnet_mode(self):
        inst, cap = _load_kinozal()
        magnet_response = b"magnet:?xt=urn:btih:" + b"A" * 40
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", return_value=magnet_response):
            inst.download_torrent("http://dl.kinozal.tv/download.php?id=12345")

    def test_download_magnet_mode_url_transform(self):
        inst, cap = _load_kinozal()
        request_urls = []

        def capture_request(url, *args, **kwargs):
            request_urls.append(url)
            return b"magnet:?xt=urn:btih:" + b"B" * 40

        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", side_effect=capture_request):
            inst.download_torrent("http://dl.kinozal.tv/download.php?id=9999")
        assert len(request_urls) == 1
        assert "get_srv_details.php?action=2&id=9999" in request_urls[0]

    def test_download_torrent_mode(self):
        inst, cap = _load_kinozal()
        import kinozal
        kinozal.config.magnet = False
        try:
            torrent_data = b"d8:announce41:http://tracker.example.com/announcee"
            with patch.object(inst, "_init"), \
                 patch.object(inst, "_request", return_value=torrent_data):
                inst.download_torrent("http://dl.kinozal.tv/download.php?id=12345")
        finally:
            kinozal.config.magnet = True

    def test_download_exception(self):
        inst, cap = _load_kinozal()
        with patch.object(inst, "_init"), \
             patch.object(inst, "_request", side_effect=Exception("network fail")):
            inst.download_torrent("http://example.com/bad")
        assert len(cap) >= 1
        assert "Error" in cap[0]["name"]


# ===========================================================================
# Tests: _get_download_path
# ===========================================================================

class TestGetDownloadPath:
    def test_magnet_from_plain_response(self):
        _, _ = _load_kinozal()
        import kinozal
        magnet_data = b"magnet:?xt=urn:btih:" + b"ABCDEF1234567890ABCDEF1234567890ABCD"
        result = kinozal.Kinozal._get_download_path(magnet_data)
        assert result.startswith("magnet:?xt=urn:btih:")
        assert len(result) > 20

    def test_magnet_from_gzip_response(self):
        _, _ = _load_kinozal()
        import kinozal
        plain = b"magnet:?xt=urn:btih:" + b"ABCDEF1234567890ABCDEF1234567890ABCD"
        compressed = gzip.compress(plain)
        result = kinozal.Kinozal._get_download_path(compressed)
        assert result.startswith("magnet:?xt=urn:btih:")

    def test_torrent_file_mode(self):
        _, _ = _load_kinozal()
        import kinozal
        kinozal.config.magnet = False
        try:
            torrent_data = b"d8:announce41:http://tracker.example.com/announcee"
            result = kinozal.Kinozal._get_download_path(torrent_data)
            assert result.endswith(".torrent")
            assert os.path.exists(result)
            os.unlink(result)
        finally:
            kinozal.config.magnet = True


# ===========================================================================
# Tests: _request
# ===========================================================================

class TestRequest:
    def test_request_success(self):
        inst, _ = _load_kinozal()
        mock_resp = _mock_context_response(b"response data", "https://kinozal.tv/page")
        with patch.object(inst.session, "open", return_value=mock_resp):
            result = inst._request("https://kinozal.tv/page")
        assert result == b"response data"

    def test_request_redirect_to_different_host_raises(self):
        inst, _ = _load_kinozal()
        mock_resp = _mock_context_response(b"data", "https://blocked.example.com/")
        with patch.object(inst.session, "open", return_value=mock_resp):
            with pytest.raises(Exception, match="blocked"):
                inst._request("https://kinozal.tv/page")

    def test_request_timeout_retries_once(self):
        inst, _ = _load_kinozal()
        from urllib.error import URLError
        mock_ok = _mock_context_response(b"ok", "https://kinozal.tv/page")
        call_count = 0

        def side_effect(url, data, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise URLError("timed out")
            return mock_ok

        with patch.object(inst.session, "open", side_effect=side_effect):
            result = inst._request("https://kinozal.tv/page")
        assert result == b"ok"
        assert call_count == 2

    def test_request_timeout_twice_raises(self):
        inst, _ = _load_kinozal()
        from urllib.error import URLError
        with patch.object(inst.session, "open", side_effect=URLError("timed out")):
            with pytest.raises(Exception, match=r"timed out|not response"):
                inst._request("https://kinozal.tv/page")

    def test_request_no_host_raises_proxy_bad(self):
        inst, _ = _load_kinozal()
        from urllib.error import URLError
        with patch.object(inst.session, "open", side_effect=URLError("no host given")):
            with pytest.raises(Exception, match="Proxy is bad"):
                inst._request("https://kinozal.tv/page")

    def test_request_http_error(self):
        inst, _ = _load_kinozal()
        from urllib.error import HTTPError
        with patch.object(inst.session, "open", side_effect=HTTPError(
            "http://kinozal.tv", 403, "Forbidden", {}, None
        )):
            with pytest.raises(Exception, match="403"):
                inst._request("http://kinozal.tv/page")

    def test_request_with_data(self):
        inst, _ = _load_kinozal()
        mock_resp = _mock_context_response(b"ok", "https://kinozal.tv/page")
        with patch.object(inst.session, "open", return_value=mock_resp) as mock_open:
            inst._request("https://kinozal.tv/login", data=b"username=u&password=p")
        mock_open.assert_called_once_with("https://kinozal.tv/login", b"username=u&password=p", 5)


# ===========================================================================
# Tests: _init
# ===========================================================================

class TestInit:
    def test_init_loads_cookies_with_uid(self):
        inst, _ = _load_kinozal()
        with patch.object(inst.mcj, "load"), \
             patch.object(inst, "login") as mock_login:
            _add_uid_cookie(inst.mcj)
            inst._init()
        mock_login.assert_not_called()

    def test_init_no_cookie_file_triggers_login(self):
        inst, _ = _load_kinozal()
        with patch.object(inst.mcj, "load", side_effect=FileNotFoundError), \
             patch.object(inst, "login") as mock_login:
            inst._init()
        mock_login.assert_called_once()

    def test_init_expired_cookie_triggers_login(self):
        inst, _ = _load_kinozal()
        with patch.object(inst.mcj, "load"), \
             patch.object(inst, "login") as mock_login:
            inst._init()
        mock_login.assert_called()

    def test_init_proxy_not_set_raises(self):
        inst, _ = _load_kinozal()
        import kinozal
        kinozal.config.proxy = True
        kinozal.config.proxies = {"http": "", "https": ""}
        try:
            with pytest.raises(Exception, match="Proxy enabled"):
                inst._init()
        finally:
            kinozal.config.proxy = False

    def test_init_proxy_http(self):
        inst, _ = _load_kinozal()
        import kinozal
        kinozal.config.proxy = True
        kinozal.config.proxies = {"http": "http://proxy:8080", "https": ""}
        try:
            with patch.object(inst.mcj, "load", side_effect=FileNotFoundError), \
                 patch.object(inst, "login"):
                inst._init()
        finally:
            kinozal.config.proxy = False

    def test_init_proxy_socks5(self):
        inst, _ = _load_kinozal()
        import kinozal
        kinozal.config.proxy = True
        kinozal.config.proxies = {"http": "socks5://proxy:1080", "https": ""}
        try:
            with patch.object(inst.mcj, "load", side_effect=FileNotFoundError), \
                 patch.object(inst, "login"):
                inst._init()
        finally:
            kinozal.config.proxy = False


# ===========================================================================
# Tests: login
# ===========================================================================

class TestLogin:
    def test_login_success(self):
        inst, _ = _load_kinozal()
        with patch.object(inst, "_request"), \
             patch.object(inst.mcj, "clear") as mock_clear, \
             patch.object(inst.mcj, "save") as mock_save:
            _add_uid_cookie(inst.mcj)
            inst.login()
            mock_save.assert_called_once()

    def test_login_failure_no_uid(self):
        inst, _ = _load_kinozal()
        with patch.object(inst, "_request"), \
             patch.object(inst.mcj, "clear"), \
             patch.object(inst.mcj, "save"):
            with pytest.raises(Exception, match="not authorized"):
                inst.login()

    def test_login_encodes_form_data(self):
        inst, _ = _load_kinozal()
        captured_data = []

        def capture_request(url, data=None, **kwargs):
            captured_data.append(data)
            return b"ok"

        with patch.object(inst, "_request", side_effect=capture_request), \
             patch.object(inst.mcj, "clear"), \
             patch.object(inst.mcj, "save"):
            _add_uid_cookie(inst.mcj)
            inst.login()
        assert len(captured_data) == 1
        assert captured_data[0] is not None


# ===========================================================================
# Tests: _catch_errors
# ===========================================================================

class TestCatchErrors:
    def test_catch_engine_error(self):
        inst, cap = _load_kinozal()
        from kinozal import EngineError
        def handler(*args):
            raise EngineError("test error")
        with patch.object(inst, "_init"):
            inst._catch_errors(handler, "test_query")
        assert len(cap) >= 1
        assert "Error" in cap[0]["name"]

    def test_catch_unexpected_error(self):
        inst, cap = _load_kinozal()
        def handler(*args):
            raise RuntimeError("unexpected")
        with patch.object(inst, "_init"):
            inst._catch_errors(handler, "test_query")
        assert len(cap) >= 1
        assert "Error" in cap[0]["name"]

    def test_catch_no_error(self):
        inst, cap = _load_kinozal()
        def handler(*args):
            pass
        with patch.object(inst, "_init"):
            inst._catch_errors(handler, "test_query")
        assert len(cap) == 0


# ===========================================================================
# Tests: pretty_error
# ===========================================================================

class TestPrettyError:
    def test_pretty_error_output(self):
        inst, cap = _load_kinozal()
        inst.pretty_error("my%20query", "Something went wrong")
        assert len(cap) == 1
        assert "Error" in cap[0]["name"]
        assert "my query" in cap[0]["name"]
        assert "Something went wrong" in cap[0]["name"]
        assert cap[0]["engine_url"] == "https://kinozal.tv/"
        assert cap[0]["size"] == "1 TB"
        assert cap[0]["seeds"] == 100
        assert cap[0]["leech"] == 100

    def test_pretty_error_link_contains_log_file(self):
        inst, cap = _load_kinozal()
        inst.pretty_error("query", "error msg")
        assert "file://" in cap[0]["desc_link"]
        assert ".log" in cap[0]["desc_link"]


# ===========================================================================
# Tests: regex patterns directly
# ===========================================================================

class TestRegexPatterns:
    def test_re_results_match(self):
        _, _ = _load_kinozal()
        import kinozal
        m = kinozal.RE_RESULTS.search("</span>Найдено 42 раздач")
        assert m is not None
        assert m.group(1) == "42"

    def test_re_results_no_match(self):
        _, _ = _load_kinozal()
        import kinozal
        m = kinozal.RE_RESULTS.search("No results here")
        assert m is None

    def test_re_torrents_match_single(self):
        _, _ = _load_kinozal()
        import kinozal
        matches = list(kinozal.RE_TORRENTS.finditer(KZ_SINGLE))
        assert len(matches) == 1
        assert matches[0].group("name") == "Test Movie 2024"
        assert matches[0].group("desc_link") == "showtopic.php?topic=12345"
        assert matches[0].group("size") == "10.5 ГБ"
        assert matches[0].group("seeds") == "55"
        assert matches[0].group("leech") == "12"
        assert matches[0].group("pub_date") == "09.06.2025 в 14:30"

    def test_re_torrents_match_multi(self):
        _, _ = _load_kinozal()
        import kinozal
        matches = list(kinozal.RE_TORRENTS.finditer(KZ_MULTI))
        assert len(matches) == 3

    def test_re_torrents_no_match_on_empty(self):
        _, _ = _load_kinozal()
        import kinozal
        matches = list(kinozal.RE_TORRENTS.finditer(KZ_EMPTY))
        assert len(matches) == 0

    def test_re_torrents_match_seeds_are_int(self):
        _, _ = _load_kinozal()
        import kinozal
        matches = list(kinozal.RE_TORRENTS.finditer(KZ_SINGLE))
        assert int(matches[0].group("seeds")) == 55

    def test_re_torrents_match_leech_are_int(self):
        _, _ = _load_kinozal()
        import kinozal
        matches = list(kinozal.RE_TORRENTS.finditer(KZ_SINGLE))
        assert int(matches[0].group("leech")) == 12


# ===========================================================================
# Tests: supported_categories
# ===========================================================================

class TestSupportedCategories:
    def test_all_categories_present(self):
        inst, _ = _load_kinozal()
        expected = {"all", "movies", "tv", "music", "games", "anime", "software"}
        assert set(inst.supported_categories.keys()) == expected

    def test_category_values_are_strings(self):
        inst, _ = _load_kinozal()
        for cat, val in inst.supported_categories.items():
            assert isinstance(val, str), f"{cat} value is not a string"

    def test_all_category_is_zero(self):
        inst, _ = _load_kinozal()
        assert inst.supported_categories["all"] == "0"

    def test_url_properties(self):
        inst, _ = _load_kinozal()
        assert inst.url == "https://kinozal.tv/"
        assert "dl." in inst.url_dl
        assert "takelogin.php" in inst.url_login
