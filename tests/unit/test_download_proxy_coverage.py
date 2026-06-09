import gzip
import importlib.util
import os
import re
import sys
import zlib
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_PATH = REPO_ROOT / "plugins" / "download_proxy.py"


def _load_download_proxy():
    stubs = {}
    for mod_name in ("novaprinter", "helpers"):
        if mod_name not in sys.modules:
            stub = type(sys)("_stub_" + mod_name)
            stub.print = lambda *a, **kw: None
            sys.modules[mod_name] = stub
            stubs[mod_name] = stub
    spec = importlib.util.spec_from_file_location("download_proxy_cov", PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["download_proxy_cov"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dp():
    return _load_download_proxy()


SAMPLE_HTML = (
    b"<!doctype html><html><head>"
    b"<meta charset='utf-8'><title>qBittorrent</title>"
    b"</head><body><div id='desktop'></div></body></html>"
)


class TestIdentifyPlugin:
    def test_rutracker_org(self, dp):
        assert dp.identify_plugin("https://rutracker.org/forum/t123.html") == "rutracker"

    def test_rutracker_net(self, dp):
        assert dp.identify_plugin("https://rutracker.net/forum/t123.html") == "rutracker"

    def test_rutracker_nl(self, dp):
        assert dp.identify_plugin("https://rutracker.nl/forum/t123.html") == "rutracker"

    def test_kinozal_tv(self, dp):
        assert dp.identify_plugin("https://kinozal.tv/details.php?id=123") == "kinozal"

    def test_kinozal_me(self, dp):
        assert dp.identify_plugin("https://kinozal.me/details.php?id=123") == "kinozal"

    def test_nnmclub_to(self, dp):
        assert dp.identify_plugin("https://nnmclub.to/forum/viewtopic.php?t=1") == "nnmclub"

    def test_nnmclub_me(self, dp):
        assert dp.identify_plugin("https://nnm-club.me/forum/viewtopic.php?t=1") == "nnmclub"

    def test_iptorrents_com(self, dp):
        assert dp.identify_plugin("https://iptorrents.com/torrents/12345") == "iptorrents"

    def test_iptorrents_me(self, dp):
        assert dp.identify_plugin("https://iptorrents.me/torrents/12345") == "iptorrents"

    def test_iptorrents_org(self, dp):
        assert dp.identify_plugin("https://iptorrents.org/torrents/12345") == "iptorrents"

    def test_unknown_url(self, dp):
        assert dp.identify_plugin("https://example.com/torrent/123") is None

    def test_empty_string(self, dp):
        assert dp.identify_plugin("") is None

    def test_case_insensitive(self, dp):
        assert dp.identify_plugin("https://RUTRACKER.ORG/forum/1") == "rutracker"

    def test_partial_match_not_enough(self, dp):
        assert dp.identify_plugin("https://example.com/nottracker") is None

    def test_in_url_path(self, dp):
        assert dp.identify_plugin("https://proxy.example.com/redirect?to=rutracker.org") == "rutracker"


class TestPluginPatternsStructure:
    def test_all_plugins_have_patterns(self, dp):
        assert len(dp.PLUGIN_PATTERNS) == 4
        for plugin, patterns in dp.PLUGIN_PATTERNS.items():
            assert len(patterns) >= 1
            for p in patterns:
                assert isinstance(p, str)

    def test_compiled_patterns_match(self, dp):
        for plugin, patterns in dp.PLUGIN_PATTERNS.items():
            assert plugin in dp.COMPILED_PATTERNS
            compiled = dp.COMPILED_PATTERNS[plugin]
            assert len(compiled) == len(patterns)
            for c in compiled:
                assert isinstance(c, re.Pattern)


class TestRewriteCsp:
    def test_adds_connect_src_when_missing(self, dp):
        csp = "default-src 'self'; script-src 'self';"
        out = dp.rewrite_csp(csp)
        assert "connect-src" in out
        assert dp.MERGE_SERVICE_ORIGIN in out

    def test_empty_input_passthrough(self, dp):
        assert dp.rewrite_csp("") == ""
        assert dp.rewrite_csp(None) is None

    def test_extends_existing_connect_src(self, dp):
        origin = dp.MERGE_SERVICE_ORIGIN
        csp = f"default-src 'self'; connect-src 'self' https://other.example;"
        out = dp.rewrite_csp(csp)
        assert "https://other.example" in out
        assert origin in out

    def test_idempotent(self, dp):
        origin = dp.MERGE_SERVICE_ORIGIN
        csp = f"default-src 'self'; connect-src 'self' {origin};"
        out = dp.rewrite_csp(csp)
        assert out.count(origin) == 1

    def test_disabled_flag_passthrough(self, dp, monkeypatch):
        monkeypatch.setenv("DISABLE_THEME_INJECTION", "1")
        csp = "default-src 'self';"
        assert dp.rewrite_csp(csp) == csp

    def test_preserves_all_directives(self, dp):
        csp = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
        out = dp.rewrite_csp(csp)
        assert "style-src" in out
        assert "img-src" in out
        assert "default-src" in out

    def test_creates_connect_from_default_src(self, dp):
        csp = "default-src 'self' https://example.com;"
        out = dp.rewrite_csp(csp)
        assert "connect-src" in out
        assert dp.MERGE_SERVICE_ORIGIN in out
        assert "https://example.com" in out


class TestInjectThemeAssets:
    def test_injects_before_head_close(self, dp):
        out = dp.inject_theme_assets(SAMPLE_HTML, "text/html")
        text = out.decode("utf-8")
        assert "/__qbit_theme__/skin.css" in text
        assert "/__qbit_theme__/bootstrap.js" in text

    def test_idempotent(self, dp):
        once = dp.inject_theme_assets(SAMPLE_HTML, "text/html")
        twice = dp.inject_theme_assets(once, "text/html")
        text = twice.decode("utf-8")
        assert text.count("/__qbit_theme__/skin.css") == 1
        assert text.count("/__qbit_theme__/bootstrap.js") == 1

    def test_non_html_passthrough(self, dp):
        assert dp.inject_theme_assets(b"\xff\xd8\xff\xe0", "image/jpeg") == b"\xff\xd8\xff\xe0"

    def test_no_head_tag_passthrough(self, dp):
        html = b"<div>fragment</div>"
        assert dp.inject_theme_assets(html, "text/html") == html

    def test_disabled_flag_passthrough(self, dp, monkeypatch):
        monkeypatch.setenv("DISABLE_THEME_INJECTION", "1")
        assert dp.inject_theme_assets(SAMPLE_HTML, "text/html") == SAMPLE_HTML

    def test_no_content_type_passthrough(self, dp):
        assert dp.inject_theme_assets(SAMPLE_HTML, "") == SAMPLE_HTML
        assert dp.inject_theme_assets(SAMPLE_HTML, None) == SAMPLE_HTML


class TestServeThemeAsset:
    def test_css_returns_200(self, dp):
        status, headers, body = dp.serve_theme_asset("/__qbit_theme__/skin.css")
        assert status == 200
        ci = {k.lower(): v for k, v in headers.items()}
        assert ci["content-type"].startswith("text/css")
        assert "no-cache" in ci["cache-control"]
        assert b":root" in body

    def test_js_returns_200(self, dp):
        status, headers, body = dp.serve_theme_asset("/__qbit_theme__/bootstrap.js")
        assert status == 200
        ci = {k.lower(): v for k, v in headers.items()}
        assert ci["content-type"].startswith("application/javascript")
        assert "no-cache" in ci["cache-control"]
        assert b"EventSource" in body

    def test_unknown_returns_404(self, dp):
        status, _, body = dp.serve_theme_asset("/__qbit_theme__/missing.png")
        assert status == 404
        assert body == b"Not Found"


class TestMaybeDecodeBody:
    def test_gzip_decode(self, dp):
        compressed = gzip.compress(SAMPLE_HTML)
        decoded, flag = dp._maybe_decode_body(compressed, "gzip")
        assert flag is True
        assert decoded == SAMPLE_HTML

    def test_deflate_decode(self, dp):
        compressed = zlib.compress(SAMPLE_HTML)
        decoded, flag = dp._maybe_decode_body(compressed, "deflate")
        assert flag is True
        assert decoded == SAMPLE_HTML

    def test_raw_deflate_decode(self, dp):
        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        raw = compressor.compress(SAMPLE_HTML) + compressor.flush()
        decoded, flag = dp._maybe_decode_body(raw, "deflate")
        assert flag is True
        assert decoded == SAMPLE_HTML

    def test_unknown_encoding_returns_false(self, dp):
        decoded, flag = dp._maybe_decode_body(b"\x00\x01\x02", "br")
        assert flag is False
        assert decoded == b"\x00\x01\x02"

    def test_empty_encoding_returns_true(self, dp):
        decoded, flag = dp._maybe_decode_body(SAMPLE_HTML, "")
        assert flag is True
        assert decoded == SAMPLE_HTML

    def test_none_encoding_returns_true(self, dp):
        decoded, flag = dp._maybe_decode_body(SAMPLE_HTML, None)
        assert flag is True
        assert decoded == SAMPLE_HTML


class TestRebrandHtml:
    def test_title_replaced(self, dp):
        html = b"<html><head><title>qBittorrent WebUI</title></head></html>"
        out = dp.rebrand_html(html, "text/html")
        assert b"<title>\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0" in out

    def test_svg_logo_src_replaced(self, dp):
        html = b'<img src="images/qbittorrent-tray.svg">'
        out = dp.rebrand_html(html, "text/html")
        assert b"/images/boba-logo.jpeg" in out

    def test_png_logo_src_replaced(self, dp):
        html = b'<img src="images/qbittorrent32.png">'
        out = dp.rebrand_html(html, "text/html")
        assert b"/images/boba-logo.jpeg" in out

    def test_alt_text_replaced(self, dp):
        html = b'<img alt="qBittorrent logo">'
        out = dp.rebrand_html(html, "text/html")
        assert b"\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0 logo" in out

    def test_meta_description_replaced(self, dp):
        html = b'<meta content="qBittorrent WebUI">'
        out = dp.rebrand_html(html, "text/html")
        assert b"\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0 WebUI" in out

    def test_non_html_passthrough(self, dp):
        body = b"\xff\xd8\xff\xe0 image"
        assert dp.rebrand_html(body, "image/jpeg") == body

    def test_unicode_decode_error_passthrough(self, dp):
        bad = bytes(range(256))
        assert dp.rebrand_html(bad, "text/html") == bad

    def test_no_content_type_passthrough(self, dp):
        assert dp.rebrand_html(SAMPLE_HTML, "") == SAMPLE_HTML
        assert dp.rebrand_html(SAMPLE_HTML, None) == SAMPLE_HTML

    def test_single_quotes_replaced(self, dp):
        html = b"<img src='images/qbittorrent-tray.svg' alt='qBittorrent logo'>"
        out = dp.rebrand_html(html, "text/html")
        assert b"/images/boba-logo.jpeg" in out
        assert b"\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0 logo" in out

    def test_href_replaced(self, dp):
        html = b'<link rel="icon" href="images/qbittorrent32.png">'
        out = dp.rebrand_html(html, "text/html")
        assert b"/images/boba-logo.jpeg" in out

    def test_fallback_replaces_remaining(self, dp):
        html = b"<p>Welcome to qBittorrent</p>"
        out = dp.rebrand_html(html, "text/html")
        assert b"\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0" in out
        assert b"qBittorrent" not in out


class TestThemePalettes:
    def test_all_8_palettes_present(self, dp):
        expected = {"darcula", "dracula", "solarized", "nord", "monokai", "gruvbox", "one-dark", "tokyo-night"}
        assert set(dp.THEME_PALETTES.keys()) == expected

    def test_all_palettes_have_dark_and_light(self, dp):
        required_modes = {"dark", "light"}
        for name, modes in dp.THEME_PALETTES.items():
            assert required_modes == set(modes.keys()), f"{name} missing modes"

    def test_all_palettes_have_required_keys(self, dp):
        required = {
            "bgPrimary", "bgSecondary", "bgTertiary", "border",
            "textPrimary", "textSecondary", "accent", "accentHover",
            "contrast", "success", "danger", "warning", "info", "purple", "shadow",
        }
        for name, modes in dp.THEME_PALETTES.items():
            for mode, tokens in modes.items():
                assert required == set(tokens.keys()), f"{name}/{mode} missing keys"


class TestBuildThemeBootstrapJs:
    def test_valid_js_output(self, dp):
        js = dp._build_theme_bootstrap_js()
        assert "function" in js
        assert "MERGE" in js
        assert "CATALOG" in js

    def test_includes_all_palettes(self, dp):
        js = dp._build_theme_bootstrap_js()
        for name in dp.THEME_PALETTES:
            assert name in js

    def test_theme_bootstrap_js_is_string(self, dp):
        assert isinstance(dp.THEME_BOOTSTRAP_JS, str)
        assert len(dp.THEME_BOOTSTRAP_JS) > 100


class TestMergeServiceOrigin:
    def test_default_origin(self, dp):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MERGE_SERVICE_URL", None)
            mod = _load_download_proxy()
            assert mod.MERGE_SERVICE_ORIGIN.startswith("http://")
            assert ":7187" in mod.MERGE_SERVICE_ORIGIN

    def test_custom_url(self, dp):
        with mock.patch.dict(os.environ, {"MERGE_SERVICE_URL": "https://myhost:9999"}):
            mod = _load_download_proxy()
            assert mod.MERGE_SERVICE_ORIGIN == "https://myhost:9999"


class TestIsBobaLogoRequest:
    def test_matches(self, dp):
        assert dp.is_boba_logo_request("/images/boba-logo.jpeg") is True

    def test_rejects(self, dp):
        assert dp.is_boba_logo_request("/images/other.png") is False
        assert dp.is_boba_logo_request("/") is False


class TestServeBobaLogo:
    def test_404_when_no_logo(self, dp):
        with mock.patch.object(dp, "_BOBA_LOGO_BYTES", None):
            dp._BOBA_LOGO_BYTES = None
            with mock.patch("builtins.open", side_effect=FileNotFoundError):
                dp._BOBA_LOGO_BYTES = None
                status, _, body = dp.serve_boba_logo()
                assert status == 404
                assert body == b"Not Found"

    def test_200_when_logo_exists(self, dp):
        with mock.patch.object(dp, "_BOBA_LOGO_BYTES", b"\xff\xd8\xff\xe0 fake"):
            status, headers, body = dp.serve_boba_logo()
            assert status == 200
            assert body == b"\xff\xd8\xff\xe0 fake"
            ci = {k.lower(): v for k, v in headers.items()}
            assert ci["content-type"] == "image/jpeg"
