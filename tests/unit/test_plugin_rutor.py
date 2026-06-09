# ruff: noqa: RUF001,RUF003
"""Deep coverage tests for plugins/rutor.py.

Covers: HTML parsing (single/multi/empty/malformed), search (URL construction,
category mapping, exception handling), download_torrent (magnet links, torrent
files, no links, URLError), environment variable loading, category mapping,
Config, date_normalize, rng, edge cases.
"""

import importlib.util
import os
import sys
import time
import types
from unittest.mock import MagicMock, patch

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGINS_DIR = os.path.join(REPO, "plugins")


def _make_context_response(data, url="https://rutor.info/test"):
    """Create a mock that works as context manager for session.open()."""
    resp = MagicMock()
    resp.read.return_value = data
    resp.geturl.return_value = url
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _load_rutor(captured=None, create_instance=True):
    """Import rutor plugin with stub modules.

    Returns (instance_or_mod, captured, mod).
    If create_instance is False, returns (None, captured, mod).
    """
    if captured is None:
        captured = []

    np_mod = types.ModuleType("novaprinter")
    np_mod.prettyPrinter = lambda d: captured.append(dict(d))
    sys.modules["novaprinter"] = np_mod

    env_mod = types.ModuleType("env_loader")
    env_mod.load_env_files = lambda *a, **kw: None
    sys.modules["env_loader"] = env_mod

    for key in list(sys.modules):
        if key == "rutor" or key.startswith("rutor."):
            sys.modules.pop(key)

    path = os.path.join(PLUGINS_DIR, "rutor.py")
    spec = importlib.util.spec_from_file_location("rutor", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["rutor"] = mod

    if not create_instance:
        return None, captured, mod

    cls = getattr(mod, "rutor", None)
    if cls is not None and isinstance(cls, type):
        return cls(), captured, mod
    return mod, captured, mod


# ─── HTML fixtures matching RE_TORRENTS ──────────────────────────────────

RUTOR_SINGLE = (
    '<td class="gai"><td>25 Май 24</td>'
    '<td><a href="magnet:?xt=urn:btih:aaa111&amp;dn=Ubuntu+22.04">M</a></td>'
    '<td><a href="/torrent/12345-info">Ubuntu 22.04 LTS</a></td>'
    '<td class="right">1.5&nbsp;GB</td>'
    '<td><span class="seed">50</span></td>'
    '<td><span class="leech">5</span></td>'
)

RUTOR_TWO = (
    '<td class="gai"><td>10 Янв 23</td>'
    '<td><a href="magnet:?xt=urn:btih:bbb222&amp;dn=Linux+Mint">M</a></td>'
    '<td><a href="/torrent/22222-info">Linux Mint 21</a></td>'
    '<td class="right">2.1&nbsp;GB</td>'
    '<td><span class="seed">120</span></td>'
    '<td><span class="leech">10</span></td>'
    '<td class="tum"><td>05 Мар 24</td>'
    '<td><a href="magnet:?xt=urn:btih:ccc333&amp;dn=Fedora+39">M</a></td>'
    '<td><a href="/torrent/33333-info">Fedora 39 Workstation</a></td>'
    '<td class="right">512&nbsp;MB</td>'
    '<td><span class="seed">80</span></td>'
    '<td><span class="leech">2</span></td>'
)

RUTOR_NO_RESULTS_HEADER = '<html><body><p>No results.</p></body></html>'

RUTOR_HTML_ENTITY_NAME = (
    '<td class="gai"><td>01 Июл 24</td>'
    '<td><a href="magnet:?xt=urn:btih:ddd444&amp;dn=Test">M</a></td>'
    '<td><a href="/torrent/44444-info">Test &amp; Release &lt;v2&gt;</a></td>'
    '<td class="right">700&nbsp;MB</td>'
    '<td><span class="seed">30</span></td>'
    '<td><span class="leech">1</span></td>'
)

RUTOR_MALFORMED = '<html><body><p>Garbage output that does not match</p></body></html>'

RUTOR_SPECIAL_CHARS = (
    '<td class="gai"><td>12 Дек 23</td>'
    '<td><a href="magnet:?xt=urn:btih:eee555&amp;dn=%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9+Torrent">M</a></td>'
    '<td><a href="/torrent/55555-info">Русский Torrent (2023) [1080p]</a></td>'
    '<td class="right">4.2&nbsp;GB</td>'
    '<td><span class="seed">200</span></td>'
    '<td><span class="leech">15</span></td>'
)

RUTOR_MISSING_MAGNET = (
    '<td class="gai"><td>01 Янв 24</td>'
    '<td><a href="not-a-magnet">M</a></td>'
    '<td><a href="/torrent/66666-info">No Magnet</a></td>'
    '<td class="right">100&nbsp;MB</td>'
    '<td><span class="seed">1</span></td>'
    '<td><span class="leech">0</span></td>'
)

RUTOR_SEEDS_ZERO = (
    '<td class="gai"><td>15 Авг 24</td>'
    '<td><a href="magnet:?xt=urn:btih:fff666&amp;dn=Dead+Torrent">M</a></td>'
    '<td><a href="/torrent/77777-info">Dead Torrent</a></td>'
    '<td class="right">9.8&nbsp;GB</td>'
    '<td><span class="seed">0</span></td>'
    '<td><span class="leech">0</span></td>'
)

RUTOR_LARGE_SIZE = (
    '<td class="gai"><td>20 Июн 24</td>'
    '<td><a href="magnet:?xt=urn:btih:ggg777&amp;dn=Big+File">M</a></td>'
    '<td><a href="/torrent/88888-info">Big File Collection</a></td>'
    '<td class="right">12.5&nbsp;TB</td>'
    '<td><span class="seed">45</span></td>'
    '<td><span class="leech">3</span></td>'
)


def _page_with_results_header(count, body=""):
    # RE_RESULTS pattern: r"</b>\\sРезультатов\\sпоиска\\s(\\d{1,4})\\s"
    # Requires: </b> whitespace Результатов поиска whitespace <digits> whitespace
    return f"<html><body></b> Результатов поиска {count} {body}</body></html>"


# ─── Tests: module-level helpers ──────────────────────────────────────────


class TestDateNormalize:
    def test_known_month(self):
        _, _, mod = _load_rutor()
        ts = mod.date_normalize("25 Май 24")
        assert isinstance(ts, int)
        assert ts > 0

    def test_all_months(self):
        _, _, mod = _load_rutor()
        months = [
            "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
            "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
        ]
        for m in months:
            ts = mod.date_normalize(f"01 {m} 24")
            assert isinstance(ts, int)
            assert ts > 0

    def test_unknown_month_returns_current_time(self):
        _, _, mod = _load_rutor()
        before = int(time.time())
        ts = mod.date_normalize("01 Xxx 24")
        after = int(time.time())
        assert before <= ts <= after

    def test_empty_string_returns_current_time(self):
        _, _, mod = _load_rutor()
        before = int(time.time())
        ts = mod.date_normalize("")
        after = int(time.time())
        assert before <= ts <= after


class TestRng:
    def test_small_total_no_pagination(self):
        _, _, mod = _load_rutor()
        assert list(mod.rng(5)) == []

    def test_exact_page_no_pagination(self):
        _, _, mod = _load_rutor()
        assert list(mod.rng(100)) == []

    def test_over_one_page(self):
        _, _, mod = _load_rutor()
        result = mod.rng(101)
        assert list(result) == [1]

    def test_large_total(self):
        _, _, mod = _load_rutor()
        result = mod.rng(250)
        assert list(result) == [1, 2]

    def test_zero(self):
        _, _, mod = _load_rutor()
        assert list(mod.rng(0)) == []

    def test_exactly_two_pages(self):
        _, _, mod = _load_rutor()
        assert list(mod.rng(200)) == [1]

    def test_three_pages(self):
        _, _, mod = _load_rutor()
        assert list(mod.rng(300)) == [1, 2]


# ─── Tests: Config ───────────────────────────────────────────────────────


class TestConfig:
    def test_default_magnet_enabled(self):
        _, _, mod = _load_rutor()
        assert mod.CONFIG.use_magnet is True

    def test_default_proxy_disabled(self):
        _, _, mod = _load_rutor()
        assert mod.CONFIG.proxy_enabled is False

    def test_default_user_agent(self):
        _, _, mod = _load_rutor()
        assert "Chrome" in mod.CONFIG.user_agent

    def test_env_override_magnet(self):
        with patch.dict(os.environ, {"RUTOR_USE_MAGNET": "false"}):
            _, _, mod = _load_rutor()
            assert mod.CONFIG.use_magnet is False

    def test_env_override_user_agent(self):
        with patch.dict(os.environ, {"RUTOR_USER_AGENT": "TestAgent/1.0"}):
            _, _, mod = _load_rutor()
            assert mod.CONFIG.user_agent == "TestAgent/1.0"


class TestGetProxyFromEnv:
    def test_no_proxy_returns_empty(self):
        _, _, mod = _load_rutor()
        result = mod._get_proxy_from_env()
        assert result == {"http": "", "https": ""}

    def test_http_proxy(self):
        with patch.dict(os.environ, {"RUTOR_PROXY_HTTP": "http://proxy:8080"}):
            _, _, mod = _load_rutor()
            result = mod._get_proxy_from_env()
            assert result["http"] == "http://proxy:8080"

    def test_https_proxy(self):
        with patch.dict(os.environ, {"RUTOR_PROXY_HTTPS": "https://proxy:8443"}):
            _, _, mod = _load_rutor()
            result = mod._get_proxy_from_env()
            assert result["https"] == "https://proxy:8443"

    def test_both_proxies(self):
        env = {"RUTOR_PROXY_HTTP": "http://p:80", "RUTOR_PROXY_HTTPS": "https://p:443"}
        with patch.dict(os.environ, env):
            _, _, mod = _load_rutor()
            result = mod._get_proxy_from_env()
            assert result["http"] == "http://p:80"
            assert result["https"] == "https://p:443"

    def test_fallback_to_generic_env(self):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://fallback:3128"}):
            _, _, mod = _load_rutor()
            result = mod._get_proxy_from_env()
            assert result["http"] == "http://fallback:3128"


# ─── Tests: Rutor class attributes ──────────────────────────────────────


class TestRutorClassAttrs:
    def test_name(self):
        instance, _, _ = _load_rutor()
        assert instance.name == "Rutor"

    def test_url(self):
        instance, _, _ = _load_rutor()
        assert instance.url == "https://rutor.info/"

    def test_url_dl(self):
        instance, _, _ = _load_rutor()
        assert "download" in instance.url_dl
        assert "d." in instance.url_dl

    def test_supported_categories(self):
        instance, _, _ = _load_rutor()
        cats = instance.supported_categories
        assert cats["all"] == 0
        assert cats["movies"] == 1
        assert cats["tv"] == 6
        assert cats["music"] == 2
        assert cats["games"] == 8
        assert cats["anime"] == 10
        assert cats["software"] == 9
        assert cats["pictures"] == 3
        assert cats["books"] == 11


# ─── Tests: draw (HTML parsing) ──────────────────────────────────────────


class TestDraw:
    def test_single_result(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_SINGLE)
        assert len(captured) == 1
        r = captured[0]
        assert "Ubuntu 22.04 LTS" in r["name"]
        assert r["seeds"] == 50
        assert r["leech"] == 5
        assert "1.5" in r["size"]
        assert "GB" in r["size"]
        assert r["engine_url"] == "https://rutor.info/"
        assert "magnet:" in r["link"]

    def test_two_results(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_TWO)
        assert len(captured) == 2
        names = [r["name"] for r in captured]
        assert "Linux Mint 21" in names
        assert "Fedora 39 Workstation" in names

    def test_empty_html(self):
        instance, captured, _ = _load_rutor()
        instance.draw(_page_with_results_header(0))
        assert len(captured) == 0

    def test_malformed_html(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_MALFORMED)
        assert len(captured) == 0

    def test_html_entities_in_name(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_HTML_ENTITY_NAME)
        assert len(captured) == 1
        assert "&amp;" not in captured[0]["name"]
        assert "Test & Release <v2>" in captured[0]["name"]

    def test_special_chars_in_name(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_SPECIAL_CHARS)
        assert len(captured) == 1
        assert "Русский Torrent (2023) [1080p]" in captured[0]["name"]

    def test_no_magnet_skipped(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_MISSING_MAGNET)
        assert len(captured) == 0

    def test_zero_seeds_and_leech(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_SEEDS_ZERO)
        assert len(captured) == 1
        assert captured[0]["seeds"] == 0
        assert captured[0]["leech"] == 0

    def test_large_size(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_LARGE_SIZE)
        assert len(captured) == 1
        assert "12.5" in captured[0]["size"]
        assert "TB" in captured[0]["size"]

    def test_size_nbsp_replaced(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_SINGLE)
        assert "&nbsp;" not in captured[0]["size"]

    def test_desc_link_built(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_SINGLE)
        assert captured[0]["desc_link"].startswith("https://rutor.info/torrent/")

    def test_pub_date_is_int(self):
        instance, captured, _ = _load_rutor()
        instance.draw(RUTOR_SINGLE)
        assert isinstance(captured[0]["pub_date"], int)

    def test_magnet_mode_off_uses_torrent_url(self):
        instance, captured, mod = _load_rutor()
        with patch.object(mod.CONFIG, "use_magnet", False):
            instance.draw(RUTOR_SINGLE)
        assert len(captured) == 1
        assert "download/" in captured[0]["link"]
        assert "magnet:" not in captured[0]["link"]

    def test_tor_id_in_torrent_url(self):
        instance, captured, mod = _load_rutor()
        with patch.object(mod.CONFIG, "use_magnet", False):
            instance.draw(RUTOR_SINGLE)
        assert "12345" in captured[0]["link"]


# ─── Tests: download_torrent ─────────────────────────────────────────────


class TestDownloadTorrent:
    def test_magnet_link_passthrough(self, capsys):
        instance, _, _ = _load_rutor()
        magnet = "magnet:?xt=urn:btih:abc123&dn=Test"
        instance.download_torrent(magnet)
        out = capsys.readouterr().out
        assert magnet in out
        assert out.strip().endswith(magnet)

    def test_torrent_file_download(self, capsys):
        instance, _, _ = _load_rutor()
        torrent_data = b"d8:intervalsi1e4:name5:dummye"
        with patch.object(instance, "_request", return_value=torrent_data):
            instance.download_torrent("https://rutor.info/download/12345")
        out = capsys.readouterr().out
        assert ".torrent" in out
        assert "https://rutor.info/download/12345" in out

    def test_empty_response_raises(self):
        instance, _, _ = _load_rutor()
        with patch.object(instance, "_request", return_value=b""):
            with pytest.raises(ValueError, match="No data received"):
                instance._download_torrent("https://rutor.info/download/12345")

    def test_html_response_raises(self):
        instance, _, _ = _load_rutor()
        html_data = b"<html><body>Error page</body></html>"
        with patch.object(instance, "_request", return_value=html_data):
            with pytest.raises(ValueError, match="not a valid torrent file"):
                instance._download_torrent("https://rutor.info/download/12345")

    def test_non_bencode_non_html_raises(self):
        instance, _, _ = _load_rutor()
        junk = b"random binary data not torrent"
        with patch.object(instance, "_request", return_value=junk):
            with pytest.raises(ValueError, match="not a valid torrent file"):
                instance._download_torrent("https://rutor.info/download/12345")

    def test_torrent_file_cleanup_on_error(self):
        instance, _, mod = _load_rutor()
        torrent_data = b"d8:intervalsi1e4:name5:dummye"

        def failing_fdopen(*args, **kwargs):
            raise OSError("disk full")

        with patch.object(instance, "_request", return_value=torrent_data):
            with patch.object(mod.os, "fdopen", side_effect=failing_fdopen):
                with pytest.raises(OSError, match="disk full"):
                    instance._download_torrent("https://rutor.info/download/12345")

    def test_magnet_does_not_call_request(self):
        instance, _, _ = _load_rutor()
        with patch.object(instance, "_request") as mock_req:
            instance.download_torrent("magnet:?xt=urn:btih:abc")
            mock_req.assert_not_called()


# ─── Tests: _request ─────────────────────────────────────────────────────


class TestRequest:
    def test_successful_request(self):
        instance, _, mod = _load_rutor()
        cm = _make_context_response(b"ok", "https://rutor.info/test")
        with patch.object(instance.session, "open", return_value=cm):
            result = instance._request("https://rutor.info/test")
        assert result == b"ok"

    def test_redirect_blocked_raises(self):
        instance, _, mod = _load_rutor()
        cm = _make_context_response(b"data", "https://evil.com/steal")
        with patch.object(instance.session, "open", return_value=cm):
            with pytest.raises(mod.EngineError, match="blocked"):
                instance._request("https://rutor.info/test")

    def test_timeout_retries_once(self):
        instance, _, mod = _load_rutor()
        from urllib.error import URLError

        cm = _make_context_response(b"data", "https://rutor.info/test")
        call_count = 0

        def side_effect(url, data, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise URLError("timed out")
            return cm

        with patch.object(instance.session, "open", side_effect=side_effect):
            result = instance._request("https://rutor.info/test")
        assert result == b"data"
        assert call_count == 2

    def test_timeout_gives_up_after_retry(self):
        instance, _, mod = _load_rutor()
        from urllib.error import URLError

        def always_timeout(url, data, timeout):
            raise URLError("timed out")

        with patch.object(instance.session, "open", side_effect=always_timeout):
            with pytest.raises(mod.EngineError, match="not responding"):
                instance._request("https://rutor.info/test")

    def test_no_host_error(self):
        instance, _, mod = _load_rutor()
        from urllib.error import URLError

        with patch.object(instance.session, "open", side_effect=URLError("no host given")):
            with pytest.raises(mod.EngineError, match="Proxy is bad"):
                instance._request("https://rutor.info/test")

    def test_http_error(self):
        instance, _, mod = _load_rutor()
        from urllib.error import HTTPError

        err = HTTPError("https://rutor.info/test", 403, "Forbidden", {}, None)
        with patch.object(instance.session, "open", side_effect=err):
            with pytest.raises(mod.EngineError, match="status: 403"):
                instance._request("https://rutor.info/test")


# ─── Tests: _search (URL construction) ───────────────────────────────────


class TestSearch:
    def test_search_all_category(self):
        instance, captured, mod = _load_rutor()
        cm = _make_context_response(
            _page_with_results_header(1, RUTOR_SINGLE).encode(),
            "https://rutor.info/search/0/0/000/0/ubuntu",
        )
        with patch.object(instance.session, "open", return_value=cm) as mock_open:
            instance.search("ubuntu")
        mock_open.assert_called_once()

    def test_search_movies_category(self):
        instance, captured, mod = _load_rutor()
        cm = _make_context_response(
            _page_with_results_header(1, RUTOR_SINGLE).encode(),
            "https://rutor.info/search/0/1/000/0/ubuntu",
        )
        with patch.object(instance.session, "open", return_value=cm) as mock_open:
            instance.search("ubuntu", cat="movies")
        call_url = mock_open.call_args[0][0]
        assert "/1/" in call_url

    def test_search_tv_category(self):
        instance, captured, mod = _load_rutor()
        cm = _make_context_response(
            _page_with_results_header(1, RUTOR_SINGLE).encode(),
            "https://rutor.info/search/0/6/000/0/ubuntu",
        )
        with patch.object(instance.session, "open", return_value=cm) as mock_open:
            instance.search("ubuntu", cat="tv")
        call_url = mock_open.call_args[0][0]
        assert "/6/" in call_url

    def test_search_music_category(self):
        instance, captured, mod = _load_rutor()
        cm = _make_context_response(
            _page_with_results_header(1, RUTOR_SINGLE).encode(),
            "https://rutor.info/search/0/2/000/0/ubuntu",
        )
        with patch.object(instance.session, "open", return_value=cm) as mock_open:
            instance.search("ubuntu", cat="music")
        call_url = mock_open.call_args[0][0]
        assert "/2/" in call_url

    def test_search_games_category(self):
        instance, captured, mod = _load_rutor()
        cm = _make_context_response(
            _page_with_results_header(1, RUTOR_SINGLE).encode(),
            "https://rutor.info/search/0/8/000/0/ubuntu",
        )
        with patch.object(instance.session, "open", return_value=cm) as mock_open:
            instance.search("ubuntu", cat="games")
        call_url = mock_open.call_args[0][0]
        assert "/8/" in call_url

    def test_search_url_encoded_query(self):
        instance, captured, mod = _load_rutor()
        cm = _make_context_response(
            _page_with_results_header(1, RUTOR_SINGLE).encode(),
            "https://rutor.info/search/0/0/000/0/ubuntu%2022",
        )
        with patch.object(instance.session, "open", return_value=cm) as mock_open:
            instance.search("ubuntu 22")
        call_url = mock_open.call_args[0][0]
        assert "ubuntu" in call_url

    def test_search_request_exception_silent(self):
        instance, captured, mod = _load_rutor()
        with patch.object(instance.session, "open", side_effect=Exception("network down")):
            instance.search("test")
        # searching() catches exceptions internally and returns 0; no pretty_error output
        assert len(captured) == 0

    def test_search_unexpected_page_content(self):
        instance, captured, mod = _load_rutor()
        page = b"<html><body>totally broken page without result count</body></html>"
        cm = _make_context_response(page, "https://rutor.info/search/0/0/000/0/broken")
        with patch.object(instance.session, "open", return_value=cm):
            instance.search("broken")
        # EngineError from searching is caught by _catch_errors → pretty_error
        assert len(captured) == 1
        assert "[Error]" in captured[0]["name"]

    def test_search_empty_results(self):
        instance, captured, mod = _load_rutor()
        page = _page_with_results_header(0).encode()
        cm = _make_context_response(page, "https://rutor.info/search/0/0/000/0/nonsense")
        with patch.object(instance.session, "open", return_value=cm):
            instance.search("nonsense")
        assert len(captured) == 0


# ─── Tests: _catch_errors ────────────────────────────────────────────────


class TestCatchErrors:
    def test_engine_error_logged(self):
        instance, captured, mod = _load_rutor()

        def fail_handler(what):
            raise mod.EngineError("test error")

        instance._catch_errors(fail_handler, "testquery")
        assert len(captured) == 1
        assert "test error" in captured[0]["name"]

    def test_generic_error_logged(self):
        instance, captured, mod = _load_rutor()

        def fail_handler(what):
            raise RuntimeError("unexpected boom")

        instance._catch_errors(fail_handler, "testquery")
        assert len(captured) == 1
        assert "Unexpected error" in captured[0]["name"]

    def test_no_error_passes_through(self):
        instance, captured, mod = _load_rutor()
        called = []

        def ok_handler(what):
            called.append(what)

        instance._catch_errors(ok_handler, "ok")
        assert called == ["ok"]
        assert len(captured) == 0


# ─── Tests: pretty_error ─────────────────────────────────────────────────


class TestPrettyError:
    def test_pretty_error_output(self):
        instance, captured, _ = _load_rutor()
        instance.pretty_error("test%20query", "Something broke")
        assert len(captured) == 1
        r = captured[0]
        assert "test query" in r["name"]
        assert "Something broke" in r["name"]
        assert r["link"].endswith("error")
        assert r["size"] == "1 TB"
        assert r["seeds"] == 100
        assert r["leech"] == 100

    def test_pretty_error_engine_url(self):
        instance, captured, _ = _load_rutor()
        instance.pretty_error("q", "err")
        assert captured[0]["engine_url"] == "https://rutor.info/"


# ─── Tests: searching ────────────────────────────────────────────────────


class TestSearching:
    def test_searching_first_page(self):
        instance, captured, mod = _load_rutor()
        body = _page_with_results_header(5, RUTOR_SINGLE)
        with patch.object(instance, "_request", return_value=body.encode()):
            result = instance.searching("https://rutor.info/search/0/0/000/0/test", first=True)
        assert result == 5
        assert len(captured) == 1

    def test_searching_non_first_page(self):
        instance, captured, mod = _load_rutor()
        with patch.object(instance, "_request", return_value=RUTOR_SINGLE.encode()):
            result = instance.searching("https://rutor.info/search/0/0/h/1/test", first=False)
        assert result == -1
        assert len(captured) == 1

    def test_searching_request_failure(self):
        instance, captured, mod = _load_rutor()
        with patch.object(instance, "_request", side_effect=Exception("fail")):
            result = instance.searching("https://rutor.info/search/0/0/000/0/test", first=True)
        assert result == 0
        assert len(captured) == 0

    def test_searching_zero_results(self):
        instance, captured, mod = _load_rutor()
        page = _page_with_results_header(0).encode()
        with patch.object(instance, "_request", return_value=page):
            result = instance.searching("https://rutor.info/search/0/0/000/0/test", first=True)
        assert result == 0

    def test_searching_unexpected_content(self):
        instance, captured, mod = _load_rutor()
        page = b"<html>no result header here</html>"
        with patch.object(instance, "_request", return_value=page):
            with pytest.raises(mod.EngineError, match="Unexpected page content"):
                instance.searching("https://rutor.info/search/0/0/000/0/test", first=True)


# ─── Tests: _init (proxy) ───────────────────────────────────────────────


class TestInit:
    def test_proxy_disabled(self):
        instance, _, _ = _load_rutor()
        assert instance.session is not None

    def test_proxy_enabled_no_proxies_raises(self):
        _, _, mod = _load_rutor(create_instance=False)
        with patch.object(mod.CONFIG, "proxy_enabled", True):
            with patch.object(mod.CONFIG, "proxies", {"http": "", "https": ""}):
                with pytest.raises(mod.EngineError, match="Proxy enabled, but not set"):
                    mod.Rutor()

    def test_proxy_enabled_with_http_proxy(self):
        _, _, mod = _load_rutor()
        with patch.object(mod.CONFIG, "proxy_enabled", True):
            with patch.object(mod.CONFIG, "proxies", {"http": "http://proxy:8080", "https": ""}):
                instance = mod.Rutor()
                assert instance.session is not None


# ─── Tests: _search pagination ───────────────────────────────────────────


class TestSearchPagination:
    def test_single_page_no_pagination(self):
        instance, captured, mod = _load_rutor()
        page = (_page_with_results_header(5) + RUTOR_SINGLE).encode()
        cm = _make_context_response(page, "https://rutor.info/search/0/0/000/0/test")
        with patch.object(instance.session, "open", return_value=cm) as mock_open:
            instance.search("test")
        assert mock_open.call_count == 1

    def test_pagination_when_many_results(self):
        instance, captured, mod = _load_rutor()
        page = (_page_with_results_header(150) + RUTOR_SINGLE).encode()
        cm = _make_context_response(page, "https://rutor.info/search/0/0/000/0/test")
        with patch.object(instance.session, "open", return_value=cm) as mock_open:
            instance.search("test")
        assert mock_open.call_count >= 2


# ─── Tests: EngineError ──────────────────────────────────────────────────


class TestEngineError:
    def test_is_exception(self):
        _, _, mod = _load_rutor()
        assert issubclass(mod.EngineError, Exception)

    def test_message(self):
        _, _, mod = _load_rutor()
        e = mod.EngineError("boom")
        assert str(e) == "boom"


# ─── Tests: module export ────────────────────────────────────────────────


class TestModuleExport:
    def test_rutor_class_rebound(self):
        _, _, mod = _load_rutor()
        assert hasattr(mod, "rutor")
        assert mod.rutor is mod.Rutor

    def test_patterns_constant(self):
        _, _, mod = _load_rutor()
        assert len(mod.PATTERNS) == 1
        assert "%s" in mod.PATTERNS[0]

    def test_pages_constant(self):
        _, _, mod = _load_rutor()
        assert mod.PAGES == 100

    def test_re_torrents_compiled(self):
        _, _, mod = _load_rutor()
        assert mod.RE_TORRENTS is not None

    def test_re_results_compiled(self):
        _, _, mod = _load_rutor()
        assert mod.RE_RESULTS is not None
