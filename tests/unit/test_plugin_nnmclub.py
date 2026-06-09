"""Deep coverage tests for plugins/nnmclub.py.

Covers: HTML parsing (single/multi/empty/malformed), search (URL construction,
category mapping, pagination, exception handling), download_torrent (magnet links,
torrent files, no links, URLError), login/session handling (cookie parse,
password fallback, missing creds, missing sid), category mapping, Config
validation, rng pagination helper, proxy init, and edge cases.
"""

import importlib.util
import os
import re
import sys
import types
from http.cookiejar import Cookie
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _load_nnmclub(captured=None):
    """Import nnmclub plugin with stub modules. Returns (instance, module, captured)."""
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    helpers_mod = types.ModuleType("helpers")
    helpers_mod.retrieve_url = lambda url: ""
    sys.modules["helpers"] = helpers_mod

    sys.modules.pop("nnmclub", None)

    with (
        patch("logging.basicConfig"),
        patch("pathlib.Path.write_text"),
        patch("pathlib.Path.write_bytes"),
    ):
        path = os.path.join(PLUGINS_DIR, "nnmclub.py")
        spec = importlib.util.spec_from_file_location("nnmclub", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["nnmclub"] = mod

    cls = getattr(mod, "nnmclub", None)
    if cls is not None and isinstance(cls, type):
        return cls(), mod, captured
    return mod, mod, captured


def _make_cookie(name="phpbb2mysql_4_sid", value="abc123"):
    return Cookie(
        0, name, value, None, False,
        "nnm-club.me", True, False, "/", True, False, None, False, None, None, {},
    )


# ─── HTML fixtures ───────────────────────────────────────────────────────
# Pages that go through searching() must be cp1251-encoded since the plugin
# decodes bytes with .decode("cp1251", "ignore").

NNM_SINGLE = (
    '<a class="topictitle" href="viewtopic.php?t=12345"><b>Ubuntu 24.04 LTS</b></a>'
    ' <a href="dl.php?t=12345">d12345</a> '
    '<u>1548578624</u> <b>50</b> <b>12</b> <u>1700000000</u>'
)

NNM_MULTI = (
    '<a class="topictitle" href="viewtopic.php?t=100"><b>Fedora 40</b></a>'
    ' <a href="dl.php?t=100">d100</a> '
    '<u>2147483648</u> <b>30</b> <b>5</b> <u>1700000001</u>'
    '<a class="topictitle" href="viewtopic.php?t=200"><b>Arch Linux 2024</b></a>'
    ' <a href="dl.php?t=200">d200</a> '
    '<u>524288000</u> <b>20</b> <b>3</b> <u>1700000002</u>'
    '<a class="topictitle" href="viewtopic.php?t=300"><b>Debian 12</b></a>'
    ' <a href="dl.php?t=300">d300</a> '
    '<u>1073741824</u> <b>40</b> <b>8</b> <u>1700000003</u>'
)

NNM_MULTI_FOUR = (
    '<a class="topictitle" href="viewtopic.php?t=401"><b>Linux Mint 21</b></a>'
    ' <a href="dl.php?t=401">d401</a> '
    '<u>800000000</u> <b>15</b> <b>2</b> <u>1700000004</u>'
    '<a class="topictitle" href="viewtopic.php?t=402"><b>Pop!_OS 22</b></a>'
    ' <a href="dl.php?t=402">d402</a> '
    '<u>900000000</u> <b>25</b> <b>4</b> <u>1700000005</u>'
    '<a class="topictitle" href="viewtopic.php?t=403"><b>Elementary OS 7</b></a>'
    ' <a href="dl.php?t=403">d403</a> '
    '<u>700000000</u> <b>10</b> <b>1</b> <u>1700000006</u>'
    '<a class="topictitle" href="viewtopic.php?t=404"><b>Zorin OS 17</b></a>'
    ' <a href="dl.php?t=404">d404</a> '
    '<u>600000000</u> <b>5</b> <b>0</b> <u>1700000007</u>'
)

NNM_EMPTY = '<html><body><p>No results</p></body></html>'

NNM_MALFORMED = (
    '<a class="topictitle" href="viewtopic.php?t=9999"><b>Broken Entry</b></a>'
)

NNM_SPECIAL_CHARS = (
    '<a class="topictitle" href="viewtopic.php?t=5555">'
    '<b>R&amp;D Suite &quot;Pro&quot; 2024</b></a>'
    ' <a href="dl.php?t=5555">d5555</a> '
    '<u>4294967296</u> <b>100</b> <b>25</b> <u>1700000100</u>'
)

NNM_UNICODE = (
    '<a class="topictitle" href="viewtopic.php?t=6666">'
    '<b>\u041c\u043e\u0439 \u0444\u0438\u043b\u044c\u043c 2024</b></a>'
    ' <a href="dl.php?t=6666">d6666</a> '
    '<u>2147483648</u> <b>55</b> <b>10</b> <u>1700000200</u>'
)

NNM_MPEGTS = (
    '<a class="topictitle" href="viewtopic.php?t=7777">'
    '<b>Concert.ts</b></a>'
    ' <a href="dl.php?t=7777">d7777</a> '
    '<u>1073741824</u> <b>33</b> <b>7</b> <u>1700000300</u>'
)

# Pages for searching() — include login marker + TP_VER count.
# searching() decodes bytes as cp1251, so these must be cp1251-encodable.

NNM_LOGGED_IN_PAGE_25 = (
    '<span class="gen">\u0412\u044b\u0445\u043e\u0434 [ USERNAME ]</span>'
    'TP_VER">Torrents: 25 '
    + NNM_SINGLE
)

NNM_LOGGED_IN_PAGE_ZERO = (
    '<span class="gen">\u0412\u044b\u0445\u043e\u0434 [ USERNAME ]</span>'
    'TP_VER">Torrents: 0'
)

NNM_LOGGED_IN_NO_TPVER = (
    '<span class="gen">\u0412\u044b\u0445\u043e\u0434 [ USERNAME ]</span>'
    '<p>Some content without results count.</p>'
)

NNM_NOT_LOGGED_IN = '<html><html>Welcome guest. Please login.</html>'

NNM_LOGIN_OK_RESPONSE = (
    '<html>\u0412\u044b\u0445\u043e\u0434 [ USERNAME ]</html>'
    + NNM_SINGLE
)

MAGNET_LINK = "magnet:?xt=urn:btih:da39a3ee5e6b4b0d3255bfef95601890afd80709&dn=test"

NNM_TOPIC_WITH_MAGNET = (
    '<html><body>'
    '<a href="magnet:?xt=urn:btih:da39a3ee5e6b4b0d3255bfef95601890afd80709'
    '&dn=ubuntu-24.04-desktop-amd64.iso">Magnet link</a>'
    '</body></html>'
)

NNM_TOPIC_NO_MAGNET = '<html><body><p>No magnet link here.</p></body></html>'


def _cp1251(text):
    """Encode text as cp1251 bytes (matching plugin's decode)."""
    return text.encode("cp1251")


# ═══════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════


class TestHelperRng:
    def test_rng_exact_multiple(self):
        _, mod, _ = _load_nnmclub()
        assert list(mod.rng(100)) == [50]

    def test_rng_partial_page(self):
        _, mod, _ = _load_nnmclub()
        assert list(mod.rng(120)) == [50, 100]

    def test_rng_small_total(self):
        _, mod, _ = _load_nnmclub()
        assert list(mod.rng(30)) == []

    def test_rng_large_total(self):
        _, mod, _ = _load_nnmclub()
        result = list(mod.rng(250))
        assert result[0] == 50
        assert result[-1] == 200
        assert all(v % 50 == 0 for v in result)

    def test_rng_one_result(self):
        _, mod, _ = _load_nnmclub()
        assert list(mod.rng(1)) == []

    def test_rng_returns_range(self):
        _, mod, _ = _load_nnmclub()
        assert isinstance(mod.rng(100), range)

    def test_rng_51_results(self):
        _, mod, _ = _load_nnmclub()
        assert list(mod.rng(51)) == [50]

    def test_rng_exactly_50(self):
        _, mod, _ = _load_nnmclub()
        assert list(mod.rng(50)) == []


# ═══════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════


class TestConfig:
    def test_default_values(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        assert c.username == "USERNAME"
        assert c.password == "PASSWORD"
        assert c.cookies == "COOKIES"
        assert c.proxy is False

    def test_to_dict_keys(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        d = c.to_dict()
        for key in ("username", "password", "cookies", "proxy", "proxies", "ua"):
            assert key in d

    def test_to_dict_values(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        d = c.to_dict()
        assert d["username"] == "USERNAME"
        assert d["proxy"] is False
        assert isinstance(d["proxies"], dict)

    def test_to_str_roundtrip(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        s = c.to_str()
        assert "USERNAME" in s
        assert "username" in s

    def test_validate_json_valid(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        valid = c.to_dict()
        assert c._validate_json(valid) is True

    def test_validate_json_missing_key(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        incomplete = {"username": "u", "password": "p"}
        assert c._validate_json(incomplete) is False

    def test_validate_json_wrong_type(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        bad = c.to_dict()
        bad["proxy"] = "not_a_bool"
        assert c._validate_json(bad) is False

    def test_validate_json_nested_dict_type_mismatch(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        d = c.to_dict()
        d["proxies"] = {"http": 123, "https": "ok"}
        c._validate_json(d)
        assert c.proxies["http"] == ""

    def test_validate_json_unknown_key_ignored(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        d = c.to_dict()
        d["NewField"] = "value"
        assert c._validate_json(d) is True

    def test_validate_json_sets_values(self):
        _, mod, _ = _load_nnmclub()
        c = mod.Config()
        d = c.to_dict()
        d["username"] = "new_user"
        c._validate_json(d)
        assert c.username == "new_user"

    def test_to_camel_single_word(self):
        _, mod, _ = _load_nnmclub()
        assert mod.Config._to_camel("username") == "username"

    def test_to_camel_multi_word(self):
        _, mod, _ = _load_nnmclub()
        assert mod.Config._to_camel("user_name") == "userName"

    def test_to_camel_empty(self):
        _, mod, _ = _load_nnmclub()
        assert mod.Config._to_camel("") == ""

    def test_to_camel_two_words(self):
        _, mod, _ = _load_nnmclub()
        assert mod.Config._to_camel("some_field") == "someField"


# ═══════════════════════════════════════════════════════════════════════════
# EngineError
# ═══════════════════════════════════════════════════════════════════════════


class TestEngineError:
    def test_is_exception(self):
        _, mod, _ = _load_nnmclub()
        assert issubclass(mod.EngineError, Exception)

    def test_raise_and_catch(self):
        _, mod, _ = _load_nnmclub()
        with pytest.raises(mod.EngineError):
            raise mod.EngineError("test")


# ═══════════════════════════════════════════════════════════════════════════
# draw() — HTML parsing
# ═══════════════════════════════════════════════════════════════════════════


class TestDraw:
    def test_single_result(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_SINGLE)
        assert len(cap) == 1
        assert cap[0]["name"] == "Ubuntu 24.04 LTS"
        assert cap[0]["link"] == "https://nnm-club.me/forum/dl.php?t=12345"
        assert cap[0]["desc_link"] == "https://nnm-club.me/forum/viewtopic.php?t=12345"
        assert cap[0]["size"] == "1548578624"
        assert cap[0]["seeds"] == 50
        assert cap[0]["leech"] == 12
        assert cap[0]["pub_date"] == 1700000000
        assert cap[0]["engine_url"] == "https://nnm-club.me/forum/"

    def test_multi_results(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_MULTI)
        assert len(cap) == 3
        names = [r["name"] for r in cap]
        assert "Fedora 40" in names
        assert "Arch Linux 2024" in names
        assert "Debian 12" in names

    def test_four_results(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_MULTI_FOUR)
        assert len(cap) == 4

    def test_empty_html(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_EMPTY)
        assert len(cap) == 0

    def test_malformed_entry_skipped(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_MALFORMED)
        assert len(cap) == 0

    def test_html_entities_decoded(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_SPECIAL_CHARS)
        assert len(cap) == 1
        assert cap[0]["name"] == 'R&D Suite "Pro" 2024'

    def test_unicode_name(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_UNICODE)
        assert len(cap) == 1
        assert cap[0]["name"] == "\u041c\u043e\u0439 \u0444\u0438\u043b\u044c\u043c 2024"

    def test_magnet_link_used_when_available(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=MAGNET_LINK):
            inst.draw(NNM_SINGLE)
        assert len(cap) == 1
        assert cap[0]["link"] == MAGNET_LINK

    def test_torrent_link_fallback_when_no_magnet(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_SINGLE)
        assert len(cap) == 1
        assert cap[0]["link"].startswith("https://nnm-club.me/forum/dl.php")

    def test_size_is_numeric_string(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_SINGLE)
        assert cap[0]["size"] == "1548578624"

    def test_seeds_and_leech_are_integers(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_SINGLE)
        assert isinstance(cap[0]["seeds"], int)
        assert isinstance(cap[0]["leech"], int)

    def test_pub_date_is_integer(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_SINGLE)
        assert isinstance(cap[0]["pub_date"], int)
        assert cap[0]["pub_date"] > 0

    def test_desc_link_always_points_to_topic(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_SINGLE)
        assert "viewtopic.php" in cap[0]["desc_link"]

    def test_dot_in_name(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_MPEGTS)
        assert len(cap) == 1
        assert cap[0]["name"] == "Concert.ts"

    def test_magnet_fetch_failure_still_emits_result(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_fetch_magnet_from_topic", return_value=""):
            inst.draw(NNM_SINGLE)
        assert len(cap) == 1
        assert cap[0]["link"].startswith("https://nnm-club.me/forum/dl.php")

    def test_multiple_torrent_links_are_independent(self):
        inst, mod, cap = _load_nnmclub()

        def magnet_side_effect(url):
            if "100" in url:
                return MAGNET_LINK
            return ""

        with patch.object(inst, "_fetch_magnet_from_topic", side_effect=magnet_side_effect):
            inst.draw(NNM_MULTI)
        assert len(cap) == 3
        fedora = next(r for r in cap if r["name"] == "Fedora 40")
        assert fedora["link"] == MAGNET_LINK
        arch = next(r for r in cap if r["name"] == "Arch Linux 2024")
        assert arch["link"].startswith("https://nnm-club.me/forum/dl.php")


# ═══════════════════════════════════════════════════════════════════════════
# _fetch_magnet_from_topic
# ═══════════════════════════════════════════════════════════════════════════


class TestFetchMagnet:
    def test_magnet_found(self):
        inst, mod, _ = _load_nnmclub()
        with patch.object(inst, "_request", return_value=NNM_TOPIC_WITH_MAGNET.encode("utf-8")):
            result = inst._fetch_magnet_from_topic("https://nnm-club.me/forum/viewtopic.php?t=12345")
        assert result.startswith("magnet:?xt=urn:btih:")
        assert "da39a3ee5e6b4b0d3255bfef95601890afd80709" in result

    def test_no_magnet_returns_empty(self):
        inst, mod, _ = _load_nnmclub()
        with patch.object(inst, "_request", return_value=NNM_TOPIC_NO_MAGNET.encode("utf-8")):
            result = inst._fetch_magnet_from_topic("https://nnm-club.me/forum/viewtopic.php?t=99999")
        assert result == ""

    def test_request_exception_returns_empty(self):
        inst, mod, _ = _load_nnmclub()
        with patch.object(inst, "_request", side_effect=Exception("network error")):
            result = inst._fetch_magnet_from_topic("https://nnm-club.me/forum/viewtopic.php?t=12345")
        assert result == ""

    def test_empty_response_returns_empty(self):
        inst, mod, _ = _load_nnmclub()
        with patch.object(inst, "_request", return_value=b""):
            result = inst._fetch_magnet_from_topic("https://nnm-club.me/forum/viewtopic.php?t=12345")
        assert result == ""

    def test_magnet_with_tracker_params(self):
        html = (
            '<a href="magnet:?xt=urn:btih:da39a3ee5e6b4b0d3255bfef95601890afd80709'
            '&dn=some+file&tr=udp://tracker.example.com:1337/announce">Magnet</a>'
        )
        inst, mod, _ = _load_nnmclub()
        with patch.object(inst, "_request", return_value=html.encode("utf-8")):
            result = inst._fetch_magnet_from_topic("https://nnm-club.me/forum/viewtopic.php?t=11111")
        assert "magnet:?xt=urn:btih:" in result
        assert "da39a3ee5e6b4b0d3255bfef95601890afd80709" in result

    def test_magnet_case_insensitive(self):
        html = (
            '<a href="MAGNET:?XT=URN:BTIH:DA39A3EE5E6B4B0D3255BFEF95601890AFD80709'
            '&DN=test">Magnet</a>'
        )
        inst, mod, _ = _load_nnmclub()
        with patch.object(inst, "_request", return_value=html.encode("utf-8")):
            result = inst._fetch_magnet_from_topic("https://nnm-club.me/forum/viewtopic.php?t=11111")
        assert result.startswith("MAGNET:")

    def test_cp1251_encoded_page(self):
        topic_html = (
            '<html><body>'
            '<a href="magnet:?xt=urn:btih:da39a3ee5e6b4b0d3255bfef95601890afd80709'
            '&dn=test">Magnet</a>'
            '</body></html>'
        )
        inst, mod, _ = _load_nnmclub()
        with patch.object(inst, "_request", return_value=topic_html.encode("cp1251")):
            result = inst._fetch_magnet_from_topic("https://nnm-club.me/forum/viewtopic.php?t=11111")
        assert "magnet:?xt=urn:btih:" in result


# ═══════════════════════════════════════════════════════════════════════════
# searching() — result count extraction and session check
# searching() decodes _request() bytes as cp1251
# ═══════════════════════════════════════════════════════════════════════════


class TestSearching:
    def _make_inst(self):
        inst, mod, cap = _load_nnmclub()
        return inst, mod, cap

    def test_first_page_returns_count(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(inst, "_request", return_value=_cp1251(NNM_LOGGED_IN_PAGE_25)),
            patch.object(inst, "_fetch_magnet_from_topic", return_value=""),
        ):
            result = inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&f=-1", first=True)
        assert result == 25
        assert len(cap) == 1

    def test_first_page_zero_results(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_request", return_value=_cp1251(NNM_LOGGED_IN_PAGE_ZERO)):
            result = inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&f=-1", first=True)
        assert result == 0

    def test_first_page_no_tpver_raises(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_request", return_value=_cp1251(NNM_LOGGED_IN_NO_TPVER)):
            with pytest.raises(mod.EngineError, match="Unexpected page content"):
                inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&f=-1", first=True)

    def test_unexpected_page_content_raises(self):
        inst, mod, cap = self._make_inst()
        page = '<span class="gen">\u0412\u044b\u0445\u043e\u0434 [ USERNAME ]</span><p>garbage</p>'
        with patch.object(inst, "_request", return_value=_cp1251(page)):
            with pytest.raises(mod.EngineError, match="Unexpected page content"):
                inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&f=-1", first=True)

    def test_subsequent_page_does_not_check_login(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(inst, "_request", return_value=_cp1251(NNM_SINGLE)),
            patch.object(inst, "_fetch_magnet_from_topic", return_value=""),
        ):
            result = inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&start=50")
        assert result == -1

    def test_missing_session_triggers_login(self):
        inst, mod, cap = self._make_inst()
        login_called = []

        def mock_login():
            login_called.append(True)

        with (
            patch.object(inst, "_request", return_value=_cp1251(NNM_NOT_LOGGED_IN)),
            patch.object(inst, "login", side_effect=mock_login),
        ):
            with pytest.raises(mod.EngineError):
                inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&f=-1", first=True)
        assert len(login_called) == 1

    def test_empty_page_returns_zero(self):
        inst, mod, cap = self._make_inst()
        page = (
            '<span class="gen">\u0412\u044b\u0445\u043e\u0434 [ USERNAME ]</span>'
            'TP_VER">Torrents: 0 '
            + NNM_EMPTY
        )
        with patch.object(inst, "_request", return_value=_cp1251(page)):
            result = inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&f=-1", first=True)
        assert result == 0

    def test_results_count_zero_returns_zero(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_request", return_value=_cp1251(NNM_LOGGED_IN_PAGE_ZERO)):
            result = inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&f=-1", first=True)
        assert result == 0

    def test_first_false_returns_negative(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(inst, "_request", return_value=_cp1251(NNM_SINGLE)),
            patch.object(inst, "_fetch_magnet_from_topic", return_value=""),
        ):
            result = inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&f=-1", first=False)
        assert result == -1

    def test_draw_called_for_each_page(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(inst, "_request", return_value=_cp1251(NNM_LOGGED_IN_PAGE_25)),
            patch.object(inst, "_fetch_magnet_from_topic", return_value=""),
        ):
            inst.searching("https://nnm-club.me/forum/tracker.php?nm=test&f=-1", first=True)
        assert len(cap) == 1


# ═══════════════════════════════════════════════════════════════════════════
# search() — URL construction and category mapping
# ═══════════════════════════════════════════════════════════════════════════


class TestSearch:
    def _make_inst(self):
        inst, mod, cap = _load_nnmclub()
        return inst, mod, cap

    def test_search_all_category(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("testquery", "all")
        called_url = mock_s.call_args[0][0]
        assert "tracker.php?nm=testquery" in called_url
        assert "f=-1" in called_url

    def test_search_movies_category(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("testquery", "movies")
        called_url = mock_s.call_args[0][0]
        assert "c=14" in called_url

    def test_search_tv_category(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("testquery", "tv")
        called_url = mock_s.call_args[0][0]
        assert "c=27" in called_url

    def test_search_music_category(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("testquery", "music")
        called_url = mock_s.call_args[0][0]
        assert "c=16" in called_url

    def test_search_games_category(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("testquery", "games")
        called_url = mock_s.call_args[0][0]
        assert "c=17" in called_url

    def test_search_anime_category(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("testquery", "anime")
        called_url = mock_s.call_args[0][0]
        assert "c=24" in called_url

    def test_search_software_category(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("testquery", "software")
        called_url = mock_s.call_args[0][0]
        assert "c=21" in called_url

    def test_search_special_chars_in_query(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("c++ & friends", "all")
        called_url = mock_s.call_args[0][0]
        assert "c%2B%2B" in called_url

    def test_search_url_starts_with_forum(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("query", "all")
        called_url = mock_s.call_args[0][0]
        assert called_url.startswith("https://nnm-club.me/forum/")

    def test_search_results_emitted(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_request", return_value=_cp1251(NNM_LOGGED_IN_PAGE_25)),
            patch.object(inst, "_fetch_magnet_from_topic", return_value=""),
        ):
            inst.search("ubuntu", "all")
        assert len(cap) >= 1

    def test_search_pagination_when_many_results(self):
        inst, mod, cap = self._make_inst()
        call_count = 0

        def mock_request(url, data=None, repeated=False):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _cp1251(NNM_LOGGED_IN_PAGE_25)
            return _cp1251(NNM_EMPTY)

        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_request", side_effect=mock_request),
            patch.object(inst, "_fetch_magnet_from_topic", return_value=""),
            patch("nnmclub.PAGES", 2),
        ):
            inst.search("test", "all")
        assert call_count > 1

    def test_search_fetches_magnets_for_results(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_request", return_value=_cp1251(NNM_LOGGED_IN_PAGE_25)),
            patch.object(inst, "_fetch_magnet_from_topic", return_value=MAGNET_LINK),
        ):
            inst.search("ubuntu", "all")
        assert len(cap) == 1
        assert cap[0]["link"] == MAGNET_LINK

    def test_search_encoded_query_in_url(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            with patch.object(inst, "searching", return_value=0) as mock_s:
                inst.search("hello world", "all")
        called_url = mock_s.call_args[0][0]
        assert "hello%20world" in called_url or "hello+world" in called_url


# ═══════════════════════════════════════════════════════════════════════════
# download_torrent
# ═══════════════════════════════════════════════════════════════════════════


class TestDownloadTorrent:
    def _make_inst(self):
        inst, mod, cap = _load_nnmclub()
        return inst, mod, cap

    def test_magnet_link_printed(self):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            inst.download_torrent(MAGNET_LINK)
        assert len(cap) == 0

    def test_magnet_link_printed_directly(self, capsys):
        inst, mod, cap = self._make_inst()
        with patch.object(inst, "_init"):
            inst.download_torrent(MAGNET_LINK)
        out = capsys.readouterr().out
        assert MAGNET_LINK in out

    def test_torrent_file_downloaded(self, capsys):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_request", return_value=b"torrent-file-content"),
        ):
            inst.download_torrent("https://nnm-club.me/forum/dl.php?t=12345")
        out = capsys.readouterr().out
        assert ".torrent" in out
        assert "https://nnm-club.me/forum/dl.php?t=12345" in out

    def test_request_error_caught_by_catch_errors(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_request", side_effect=mod.EngineError("blocked")),
        ):
            inst.download_torrent("https://nnm-club.me/forum/dl.php?t=12345")
        assert len(cap) == 1
        assert "[Error]" in cap[0]["name"]
        assert "blocked" in cap[0]["name"]

    def test_magnet_does_not_call_request(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_request") as mock_req,
        ):
            inst.download_torrent(MAGNET_LINK)
        mock_req.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# _catch_errors — error handling
# ═══════════════════════════════════════════════════════════════════════════


class TestCatchErrors:
    def test_engine_error_caught(self):
        inst, mod, cap = _load_nnmclub()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_search", side_effect=mod.EngineError("test error")),
        ):
            inst.search("test", "all")
        assert len(cap) == 1
        assert "[Error]" in cap[0]["name"]
        assert "test error" in cap[0]["name"]

    def test_unexpected_error_caught(self):
        inst, mod, cap = _load_nnmclub()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_search", side_effect=RuntimeError("unexpected")),
        ):
            inst.search("test", "all")
        assert len(cap) == 1
        assert "Unexpected error" in cap[0]["name"]

    def test_error_pretty_prints_metadata(self):
        inst, mod, cap = _load_nnmclub()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_search", side_effect=mod.EngineError("auth failed")),
        ):
            inst.search("myquery", "all")
        assert cap[0]["engine_url"] == "https://nnm-club.me/forum/"
        assert cap[0]["size"] == "1 TB"
        assert cap[0]["seeds"] == 100
        assert cap[0]["leech"] == 100

    def test_init_error_caught(self):
        inst, mod, cap = _load_nnmclub()
        with patch.object(inst, "_init", side_effect=mod.EngineError("proxy bad")):
            inst.search("test", "all")
        assert len(cap) == 1
        assert "proxy bad" in cap[0]["name"]


# ═══════════════════════════════════════════════════════════════════════════
# _init — proxy and session setup
# ═══════════════════════════════════════════════════════════════════════════


class TestInit:
    def test_proxy_not_set_no_handler(self):
        inst, mod, _ = _load_nnmclub()
        with (
            patch.object(mod.config, "proxy", False),
            patch.object(inst.mcj, "load", side_effect=FileNotFoundError),
            patch.object(inst, "login") as mock_login,
        ):
            inst._init()
        mock_login.assert_called_once()

    def test_proxy_enabled_no_proxies_raises(self):
        inst, mod, _ = _load_nnmclub()
        with (
            patch.object(mod.config, "proxy", True),
            patch.object(mod.config, "proxies", {"http": "", "https": ""}),
        ):
            with pytest.raises(mod.EngineError, match="Proxy enabled"):
                inst._init()

    def test_proxy_enabled_with_socks(self):
        inst, mod, _ = _load_nnmclub()
        with (
            patch.object(mod.config, "proxy", True),
            patch.object(mod.config, "proxies", {"http": "socks5://localhost:1080", "https": ""}),
            patch("nnmclub.socks") as mock_socks,
            patch("nnmclub.socket"),
            patch.object(inst.mcj, "load", side_effect=FileNotFoundError),
            patch.object(inst, "login"),
        ):
            mock_socks.PROXY_TYPE_SOCKS5 = 2
            inst._init()
            mock_socks.set_default_proxy.assert_called_once()

    def test_proxy_enabled_with_http_proxy(self):
        inst, mod, _ = _load_nnmclub()
        with (
            patch.object(mod.config, "proxy", True),
            patch.object(mod.config, "proxies", {"http": "http://proxy:8080", "https": ""}),
            patch.object(inst.session, "add_handler"),
            patch.object(inst.mcj, "load", side_effect=FileNotFoundError),
            patch.object(inst, "login"),
        ):
            inst._init()
            inst.session.add_handler.assert_called_once()

    def test_valid_cookies_skip_login(self):
        inst, mod, _ = _load_nnmclub()
        cookie = _make_cookie("phpbb2mysql_4_data", "session_data")

        def mock_load(*args, **kwargs):
            inst.mcj.set_cookie(cookie)

        with (
            patch.object(inst.mcj, "load", side_effect=mock_load),
            patch.object(inst, "login") as mock_login,
        ):
            inst._init()
        mock_login.assert_not_called()

    def test_expired_cookies_trigger_login(self):
        inst, mod, _ = _load_nnmclub()
        cookie = _make_cookie("phpbb2mysql_4_expired", "old")

        def mock_load(*args, **kwargs):
            inst.mcj.set_cookie(cookie)

        with (
            patch.object(inst.mcj, "load", side_effect=mock_load),
            patch.object(inst, "login") as mock_login,
        ):
            inst._init()
        mock_login.assert_called_once()

    def test_local_cookies_loaded(self):
        inst, mod, _ = _load_nnmclub()
        cookie = _make_cookie("phpbb2mysql_4_data", "valid_session")

        def mock_load(*args, **kwargs):
            inst.mcj.set_cookie(cookie)

        with (
            patch.object(inst.mcj, "load", side_effect=mock_load),
            patch.object(inst, "login") as mock_login,
        ):
            inst._init()
        mock_login.assert_not_called()

    def test_ua_set_on_session(self):
        inst, mod, _ = _load_nnmclub()
        with (
            patch.object(inst.mcj, "load", side_effect=FileNotFoundError),
            patch.object(inst, "login"),
        ):
            inst._init()
        assert ("User-Agent", mod.config.ua) in inst.session.addheaders


# ═══════════════════════════════════════════════════════════════════════════
# login — cookie and password paths
# ═══════════════════════════════════════════════════════════════════════════


class TestLogin:
    def _make_inst(self):
        inst, mod, cap = _load_nnmclub()
        return inst, mod, cap

    def test_cookie_login_sets_session_cookie(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(mod.config, "cookies", "phpbb2mysql_4_sid=abc123; phpbb2mysql_4_data=xyz"),
            patch.object(inst, "_request", return_value=b""),
            patch.object(inst.mcj, "save"),
        ):
            inst.login()
        cookie_names = [c.name for c in inst.mcj]
        assert "phpbb2mysql_4_sid" in cookie_names
        assert "phpbb2mysql_4_data" in cookie_names

    def test_cookie_login_missing_sid_raises(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(mod.config, "cookies", "some_cookie=value"),
            patch.object(inst, "_request", return_value=b""),
        ):
            with pytest.raises(mod.EngineError, match="not authorized"):
                inst.login()

    def test_password_login_fallback_succeeds(self):
        inst, mod, cap = self._make_inst()

        def mock_request(url, data=None, repeated=False):
            inst.mcj.set_cookie(_make_cookie("phpbb2mysql_4_sid", "session123"))
            return b""

        with (
            patch.object(mod.config, "cookies", "COOKIES"),
            patch.object(mod.config, "username", "user1"),
            patch.object(mod.config, "password", "pass1"),
            patch.object(inst, "_request", side_effect=mock_request),
            patch.object(inst.mcj, "save"),
        ):
            inst.login()
        cookie_names = [c.name for c in inst.mcj]
        assert "phpbb2mysql_4_sid" in cookie_names

    def test_password_login_no_creds_raises(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(mod.config, "cookies", "COOKIES"),
            patch.object(mod.config, "username", "USERNAME"),
            patch.object(mod.config, "password", "PASSWORD"),
        ):
            with pytest.raises(mod.EngineError, match="Empty cookies"):
                inst.login()

    def test_cookie_login_single_cookie(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(mod.config, "cookies", "phpbb2mysql_4_sid=single_value"),
            patch.object(inst, "_request", return_value=b""),
            patch.object(inst.mcj, "save"),
        ):
            inst.login()
        cookie_names = [c.name for c in inst.mcj]
        assert "phpbb2mysql_4_sid" in cookie_names

    def test_cookie_login_saves_to_file(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(mod.config, "cookies", "phpbb2mysql_4_sid=abc"),
            patch.object(inst, "_request", return_value=b""),
            patch.object(inst.mcj, "save") as mock_save,
        ):
            inst.login()
        mock_save.assert_called_once()

    def test_password_login_missing_sid_raises(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(mod.config, "cookies", "COOKIES"),
            patch.object(mod.config, "username", "user1"),
            patch.object(mod.config, "password", "pass1"),
            patch.object(inst, "_request", return_value=b""),
        ):
            with pytest.raises(mod.EngineError, match="not authorized"):
                inst.login()

    def test_password_login_encodes_cp1251(self):
        inst, mod, cap = self._make_inst()

        captured_data = []

        def mock_request(url, data=None, repeated=False):
            captured_data.append(data)
            inst.mcj.set_cookie(_make_cookie("phpbb2mysql_4_sid", "s"))
            return b""

        with (
            patch.object(mod.config, "cookies", "COOKIES"),
            patch.object(mod.config, "username", "user"),
            patch.object(mod.config, "password", "pass"),
            patch.object(inst, "_request", side_effect=mock_request),
            patch.object(inst.mcj, "save"),
        ):
            inst.login()
        assert len(captured_data) == 1
        assert captured_data[0] is not None

    def test_cookie_login_clears_existing_cookies(self):
        inst, mod, cap = self._make_inst()
        inst.mcj.set_cookie(_make_cookie("old_cookie", "old_value"))
        with (
            patch.object(mod.config, "cookies", "phpbb2mysql_4_sid=new"),
            patch.object(inst, "_request", return_value=b""),
            patch.object(inst.mcj, "save"),
        ):
            inst.login()
        cookie_names = [c.name for c in inst.mcj]
        assert "old_cookie" not in cookie_names

    def test_empty_cookies_string_raises_value_error(self):
        inst, mod, cap = self._make_inst()
        with (
            patch.object(mod.config, "cookies", ""),
            patch.object(mod.config, "username", "user"),
            patch.object(mod.config, "password", "pass"),
        ):
            with pytest.raises(ValueError):
                inst.login()

    def test_password_login_url_includes_login_php(self):
        inst, mod, cap = self._make_inst()

        captured_urls = []

        def mock_request(url, data=None, repeated=False):
            captured_urls.append(url)
            inst.mcj.set_cookie(_make_cookie("phpbb2mysql_4_sid", "s"))
            return b""

        with (
            patch.object(mod.config, "cookies", "COOKIES"),
            patch.object(mod.config, "username", "user"),
            patch.object(mod.config, "password", "pass"),
            patch.object(inst, "_request", side_effect=mock_request),
            patch.object(inst.mcj, "save"),
        ):
            inst.login()
        assert any("login.php" in u for u in captured_urls)


# ═══════════════════════════════════════════════════════════════════════════
# _request — network requests and error handling
# ═══════════════════════════════════════════════════════════════════════════


class TestRequest:
    def _make_inst(self):
        inst, mod, cap = _load_nnmclub()
        return inst, mod, cap

    def test_successful_request(self):
        inst, mod, _ = self._make_inst()
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.geturl.return_value = "https://nnm-club.me/forum/page"
        mock_response.read.return_value = b"response data"
        with patch.object(inst.session, "open", return_value=mock_response):
            result = inst._request("https://nnm-club.me/forum/page")
        assert result == b"response data"

    def test_blocked_url_raises(self):
        inst, mod, _ = self._make_inst()
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.geturl.return_value = "https://blocked-site.com/page"
        with patch.object(inst.session, "open", return_value=mock_response):
            with pytest.raises(mod.EngineError, match="blocked"):
                inst._request("https://blocked-site.com/page")

    def test_timeout_retries_once(self):
        inst, mod, _ = self._make_inst()
        from urllib.error import URLError

        call_count = 0

        def side_effect(url, data=None, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise URLError("timed out")
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.geturl.return_value = "https://nnm-club.me/forum/page"
            mock_resp.read.return_value = b"ok"
            return mock_resp

        with patch.object(inst.session, "open", side_effect=side_effect):
            result = inst._request("https://nnm-club.me/forum/page")
        assert result == b"ok"
        assert call_count == 2

    def test_timeout_double_raises(self):
        inst, mod, _ = self._make_inst()
        from urllib.error import URLError

        with patch.object(inst.session, "open", side_effect=URLError("timed out")):
            with pytest.raises(mod.EngineError, match="timed out"):
                inst._request("https://nnm-club.me/forum/page")

    def test_no_host_error(self):
        inst, mod, _ = self._make_inst()
        from urllib.error import URLError

        with patch.object(inst.session, "open", side_effect=URLError("no host given")):
            with pytest.raises(mod.EngineError, match="Proxy is bad"):
                inst._request("https://nnm-club.me/forum/page")

    def test_http_error(self):
        inst, mod, _ = self._make_inst()
        from urllib.error import HTTPError

        err = HTTPError("url", 403, "Forbidden", {}, None)
        with patch.object(inst.session, "open", side_effect=err):
            with pytest.raises(mod.EngineError, match="status: 403"):
                inst._request("https://nnm-club.me/forum/page")

    def test_generic_url_error(self):
        inst, mod, _ = self._make_inst()
        from urllib.error import URLError

        with patch.object(inst.session, "open", side_effect=URLError("connection refused")):
            with pytest.raises(mod.EngineError, match="not response"):
                inst._request("https://nnm-club.me/forum/page")

    def test_data_passed_to_open(self):
        inst, mod, _ = self._make_inst()
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.geturl.return_value = "https://nnm-club.me/forum/login.php"
        mock_response.read.return_value = b"ok"
        with patch.object(inst.session, "open", return_value=mock_response) as mock_open:
            inst._request("https://nnm-club.me/forum/login.php", data=b"payload")
        mock_open.assert_called_once_with("https://nnm-club.me/forum/login.php", b"payload", 5)

    def test_bulk_url_accepted(self):
        inst, mod, _ = self._make_inst()
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.geturl.return_value = "https://bulk.nnm-club.me/file.torrent"
        mock_response.read.return_value = b"torrent"
        with patch.object(inst.session, "open", return_value=mock_response):
            result = inst._request("https://bulk.nnm-club.me/file.torrent")
        assert result == b"torrent"

    def test_repeated_flag_prevents_double_retry(self):
        inst, mod, _ = self._make_inst()
        from urllib.error import URLError

        with patch.object(inst.session, "open", side_effect=URLError("timed out")):
            with pytest.raises(mod.EngineError, match="timed out"):
                inst._request("https://nnm-club.me/forum/page", repeated=True)


# ═══════════════════════════════════════════════════════════════════════════
# pretty_error
# ═══════════════════════════════════════════════════════════════════════════


class TestPrettyError:
    def test_pretty_error_output(self):
        inst, mod, cap = _load_nnmclub()
        inst.pretty_error("myquery", "some error")
        assert len(cap) == 1
        assert "[myquery][Error]: some error" in cap[0]["name"]
        assert cap[0]["link"] == "https://nnm-club.me/forum/error"
        assert cap[0]["engine_url"] == "https://nnm-club.me/forum/"

    def test_pretty_error_size_and_seeds(self):
        inst, mod, cap = _load_nnmclub()
        inst.pretty_error("q", "err")
        assert cap[0]["size"] == "1 TB"
        assert cap[0]["seeds"] == 100
        assert cap[0]["leech"] == 100

    def test_pretty_error_desc_link_is_logfile(self):
        inst, mod, cap = _load_nnmclub()
        inst.pretty_error("q", "err")
        assert cap[0]["desc_link"].startswith("file://")

    def test_pretty_error_pub_date_is_timestamp(self):
        import time

        inst, mod, cap = _load_nnmclub()
        before = int(time.time())
        inst.pretty_error("q", "err")
        after = int(time.time())
        assert before <= cap[0]["pub_date"] <= after

    def test_pretty_error_url_encoded_query_decoded(self):
        inst, mod, cap = _load_nnmclub()
        inst.pretty_error("c%2B%2B", "error msg")
        assert "[c++][Error]: error msg" in cap[0]["name"]

    def test_pretty_error_special_query(self):
        inst, mod, cap = _load_nnmclub()
        inst.pretty_error("test%20query", "err")
        assert "[test query][Error]: err" in cap[0]["name"]


# ═══════════════════════════════════════════════════════════════════════════
# Class-level attributes
# ═══════════════════════════════════════════════════════════════════════════


class TestClassAttributes:
    def test_name(self):
        inst, mod, _ = _load_nnmclub()
        assert inst.name == "NoNaMe-Club"

    def test_url(self):
        inst, mod, _ = _load_nnmclub()
        assert inst.url == "https://nnm-club.me/forum/"

    def test_url_dl(self):
        inst, mod, _ = _load_nnmclub()
        assert inst.url_dl == "https://bulk.nnm-club.me/"

    def test_supported_categories_keys(self):
        inst, mod, _ = _load_nnmclub()
        expected = {"all", "movies", "tv", "music", "games", "anime", "software"}
        assert set(inst.supported_categories.keys()) == expected

    def test_category_values_are_strings(self):
        inst, mod, _ = _load_nnmclub()
        for v in inst.supported_categories.values():
            assert isinstance(v, str)

    def test_module_level_nnmclub_alias(self):
        _, mod, _ = _load_nnmclub()
        assert hasattr(mod, "nnmclub")
        assert mod.nnmclub is mod.NNMClub


# ═══════════════════════════════════════════════════════════════════════════
# Integration-style: search → draw → prettyPrinter
# ═══════════════════════════════════════════════════════════════════════════


class TestSearchDrawIntegration:
    def test_full_search_flow(self):
        inst, mod, cap = _load_nnmclub()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_request", return_value=_cp1251(NNM_LOGGED_IN_PAGE_25)),
            patch.object(inst, "_fetch_magnet_from_topic", return_value=""),
        ):
            inst.search("ubuntu", "all")
        assert len(cap) == 1
        assert cap[0]["name"] == "Ubuntu 24.04 LTS"
        assert cap[0]["engine_url"] == "https://nnm-club.me/forum/"

    def test_search_with_magnet_preferred(self):
        inst, mod, cap = _load_nnmclub()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_request", return_value=_cp1251(NNM_LOGGED_IN_PAGE_25)),
            patch.object(inst, "_fetch_magnet_from_topic", return_value=MAGNET_LINK),
        ):
            inst.search("ubuntu", "all")
        assert cap[0]["link"] == MAGNET_LINK

    def test_search_error_emits_error_result(self):
        inst, mod, cap = _load_nnmclub()
        with (
            patch.object(inst, "_init"),
            patch.object(inst, "_search", side_effect=mod.EngineError("auth failed")),
        ):
            inst.search("q", "all")
        assert len(cap) == 1
        assert "Error" in cap[0]["name"]
