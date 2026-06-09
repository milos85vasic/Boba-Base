import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_PATH = REPO_ROOT / "plugins" / "theme_injector.py"
DOWNLOAD_PROXY_PATH = REPO_ROOT / "plugins" / "download_proxy.py"


def _load_theme_injector():
    stubs = {}
    for mod_name in ("novaprinter", "helpers"):
        if mod_name not in sys.modules:
            stub = type(sys)("_stub_" + mod_name)
            stub.print = lambda *a, **kw: None
            sys.modules[mod_name] = stub
            stubs[mod_name] = stub
    spec = importlib.util.spec_from_file_location("theme_injector_under_test", PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["theme_injector_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ti():
    return _load_theme_injector()


SAMPLE_HTML = (
    b"<!doctype html><html><head>"
    b"<meta charset='utf-8'><title>qBittorrent</title>"
    b"</head><body><div id='desktop'></div></body></html>"
)


class TestThemeInjectionDisabled:
    def test_returns_false_by_default(self, ti):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DISABLE_THEME_INJECTION", None)
            assert ti.theme_injection_disabled() is False

    def test_returns_true_when_set_to_1(self, ti):
        with mock.patch.dict(os.environ, {"DISABLE_THEME_INJECTION": "1"}):
            assert ti.theme_injection_disabled() is True

    def test_returns_false_for_other_values(self, ti):
        with mock.patch.dict(os.environ, {"DISABLE_THEME_INJECTION": "yes"}):
            assert ti.theme_injection_disabled() is False


class TestInjectThemeAssets:
    def test_injects_before_head_close(self, ti):
        out = ti.inject_theme_assets(SAMPLE_HTML, "text/html")
        text = out.decode("utf-8")
        assert "/__qbit_theme__/skin.css" in text
        assert "/__qbit_theme__/bootstrap.js" in text
        head_close = text.lower().rfind("</head>")
        link_pos = text.find("/__qbit_theme__/skin.css")
        script_pos = text.find("/__qbit_theme__/bootstrap.js")
        assert 0 < link_pos < head_close
        assert 0 < script_pos < head_close

    def test_idempotent(self, ti):
        once = ti.inject_theme_assets(SAMPLE_HTML, "text/html")
        twice = ti.inject_theme_assets(once, "text/html")
        text = twice.decode("utf-8")
        assert text.count("/__qbit_theme__/skin.css") == 1
        assert text.count("/__qbit_theme__/bootstrap.js") == 1

    def test_non_html_passthrough(self, ti):
        payload = b"\xff\xd8\xff\xe0 binary"
        assert ti.inject_theme_assets(payload, "image/jpeg") == payload

    def test_no_head_tag_passthrough(self, ti):
        html = b"<div>fragment</div>"
        assert ti.inject_theme_assets(html, "text/html") == html

    def test_disabled_flag_passthrough(self, ti, monkeypatch):
        monkeypatch.setenv("DISABLE_THEME_INJECTION", "1")
        assert ti.inject_theme_assets(SAMPLE_HTML, "text/html") == SAMPLE_HTML

    def test_case_insensitive_head(self, ti):
        html = b"<HTML><HEAD><TITLE>x</TITLE></HEAD><BODY>ok</BODY></HTML>"
        out = ti.inject_theme_assets(html, "text/html")
        assert b"/__qbit_theme__/skin.css" in out

    def test_no_content_type_passthrough(self, ti):
        assert ti.inject_theme_assets(SAMPLE_HTML, "") == SAMPLE_HTML
        assert ti.inject_theme_assets(SAMPLE_HTML, None) == SAMPLE_HTML


class TestServeThemeAsset:
    def test_css_returns_200(self, ti):
        status, headers, body = ti.serve_theme_asset("/__qbit_theme__/skin.css")
        assert status == 200
        ci = {k.lower(): v for k, v in headers.items()}
        assert ci["content-type"].startswith("text/css")
        assert "no-cache" in ci["cache-control"]
        assert b":root" in body

    def test_js_returns_200(self, ti):
        status, headers, body = ti.serve_theme_asset("/__qbit_theme__/bootstrap.js")
        assert status == 200
        ci = {k.lower(): v for k, v in headers.items()}
        assert ci["content-type"].startswith("application/javascript")
        assert "no-cache" in ci["cache-control"]
        assert b"EventSource" in body

    def test_unknown_returns_404(self, ti):
        status, _, body = ti.serve_theme_asset("/__qbit_theme__/missing.png")
        assert status == 404
        assert body == b"Not Found"


class TestRewriteCsp:
    def test_adds_connect_src_when_missing(self, ti):
        csp = "default-src 'self'; script-src 'self';"
        out = ti.rewrite_csp(csp)
        assert "connect-src" in out
        assert ti.merge_service_origin() in out

    def test_extends_existing_connect_src(self, ti):
        origin = ti.merge_service_origin()
        csp = f"default-src 'self'; connect-src 'self' https://other.example;"
        out = ti.rewrite_csp(csp)
        assert "https://other.example" in out
        assert origin in out

    def test_idempotent(self, ti):
        origin = ti.merge_service_origin()
        csp = f"default-src 'self'; connect-src 'self' {origin};"
        out = ti.rewrite_csp(csp)
        assert out.count(origin) == 1

    def test_empty_input_passthrough(self, ti):
        assert ti.rewrite_csp("") == ""
        assert ti.rewrite_csp(None) is None

    def test_disabled_flag_passthrough(self, ti, monkeypatch):
        monkeypatch.setenv("DISABLE_THEME_INJECTION", "1")
        csp = "default-src 'self';"
        assert ti.rewrite_csp(csp) == csp

    def test_preserves_all_directives(self, ti):
        csp = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; script-src 'self';"
        out = ti.rewrite_csp(csp)
        assert "style-src" in out
        assert "img-src" in out
        assert "script-src" in out

    def test_creates_connect_from_default_src(self, ti):
        csp = "default-src 'self' https://example.com;"
        out = ti.rewrite_csp(csp)
        assert "connect-src" in out
        assert ti.merge_service_origin() in out
        assert "https://example.com" in out


class TestMaybeDecodeBody:
    def test_gzip_decode(self, ti):
        import gzip

        compressed = gzip.compress(SAMPLE_HTML)
        decoded, flag = ti.maybe_decode_body(compressed, "gzip")
        assert flag is True
        assert decoded == SAMPLE_HTML

    def test_deflate_decode(self, ti):
        import zlib

        compressed = zlib.compress(SAMPLE_HTML)
        decoded, flag = ti.maybe_decode_body(compressed, "deflate")
        assert flag is True
        assert decoded == SAMPLE_HTML

    def test_raw_deflate_decode(self, ti):
        import zlib

        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        raw = compressor.compress(SAMPLE_HTML) + compressor.flush()
        decoded, flag = ti.maybe_decode_body(raw, "deflate")
        assert flag is True
        assert decoded == SAMPLE_HTML

    def test_unknown_encoding_returns_false(self, ti):
        decoded, flag = ti.maybe_decode_body(b"\x00\x01\x02", "br")
        assert flag is False
        assert decoded == b"\x00\x01\x02"

    def test_empty_encoding_returns_true(self, ti):
        decoded, flag = ti.maybe_decode_body(SAMPLE_HTML, "")
        assert flag is True
        assert decoded == SAMPLE_HTML

    def test_none_encoding_returns_true(self, ti):
        decoded, flag = ti.maybe_decode_body(SAMPLE_HTML, None)
        assert flag is True
        assert decoded == SAMPLE_HTML


class TestRebrandHtml:
    def test_title_replaced(self, ti):
        html = b"<html><head><title>qBittorrent WebUI</title></head></html>"
        out = ti.rebrand_html(html, "text/html")
        assert b"\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0" in out

    def test_svg_logo_src_replaced(self, ti):
        html = b'<img src="images/qbittorrent-tray.svg">'
        out = ti.rebrand_html(html, "text/html")
        assert b"/images/boba-logo.jpeg" in out

    def test_png_logo_src_replaced(self, ti):
        html = b'<img src="images/qbittorrent32.png">'
        out = ti.rebrand_html(html, "text/html")
        assert b"/images/boba-logo.jpeg" in out

    def test_alt_text_replaced(self, ti):
        html = b'<img alt="qBittorrent logo">'
        out = ti.rebrand_html(html, "text/html")
        assert b"\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0 logo" in out

    def test_meta_description_replaced(self, ti):
        html = b'<meta content="qBittorrent WebUI">'
        out = ti.rebrand_html(html, "text/html")
        assert b"\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0 WebUI" in out

    def test_fallback_replaces_remaining(self, ti):
        html = b"<p>Welcome to qBittorrent</p>"
        out = ti.rebrand_html(html, "text/html")
        assert b"\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0" in out
        assert b"qBittorrent" not in out

    def test_non_html_passthrough(self, ti):
        body = b"\xff\xd8\xff\xe0 image"
        assert ti.rebrand_html(body, "image/jpeg") == body

    def test_unicode_decode_error_passthrough(self, ti):
        bad = bytes(range(256))
        assert ti.rebrand_html(bad, "text/html") == bad

    def test_no_content_type_passthrough(self, ti):
        assert ti.rebrand_html(SAMPLE_HTML, "") == SAMPLE_HTML
        assert ti.rebrand_html(SAMPLE_HTML, None) == SAMPLE_HTML

    def test_single_quotes_replaced(self, ti):
        html = b"<img src='images/qbittorrent-tray.svg' alt='qBittorrent logo'>"
        out = ti.rebrand_html(html, "text/html")
        assert b"/images/boba-logo.jpeg" in out
        assert b"\xd0\x91\xd0\xbe\xd0\xb1\xd0\xb0 logo" in out

    def test_href_replaced(self, ti):
        html = b'<link rel="icon" href="images/qbittorrent32.png">'
        out = ti.rebrand_html(html, "text/html")
        assert b"/images/boba-logo.jpeg" in out


class TestBuildPaletteCatalog:
    def test_returns_download_proxy_palettes(self, ti):
        cat = ti._build_palette_catalog()
        assert isinstance(cat, dict)
        assert "darcula" in cat
        assert "dark" in cat["darcula"]
        assert "light" in cat["darcula"]
        required_keys = {
            "bgPrimary", "bgSecondary", "bgTertiary", "border",
            "textPrimary", "textSecondary", "accent", "accentHover",
            "contrast", "success", "danger", "warning", "info", "purple", "shadow",
        }
        assert required_keys == set(cat["darcula"]["dark"].keys())


class TestBuildThemeBootstrapJs:
    def test_valid_js_output(self, ti):
        js = ti._build_theme_bootstrap_js()
        assert "function" in js
        assert "MERGE" in js
        assert "CATALOG" in js
        assert "darcula" in js

    def test_includes_all_palettes(self, ti):
        js = ti._build_theme_bootstrap_js()
        for name in ("darcula", "dracula", "solarized", "nord", "monokai", "gruvbox", "one-dark", "tokyo-night"):
            assert name in js

    def test_theme_bootstrap_js_is_string(self, ti):
        assert isinstance(ti.THEME_BOOTSTRAP_JS, str)
        assert len(ti.THEME_BOOTSTRAP_JS) > 100


class TestMergeServiceOrigin:
    def test_default_origin(self, ti):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MERGE_SERVICE_URL", None)
            mod = _load_theme_injector()
            origin = mod.merge_service_origin()
            assert origin.startswith("http://")
            assert ":7187" in origin

    def test_custom_url(self, ti):
        with mock.patch.dict(os.environ, {"MERGE_SERVICE_URL": "https://myhost:9999"}):
            mod = _load_theme_injector()
            origin = mod.merge_service_origin()
            assert origin == "https://myhost:9999"


class TestIsBobaLogoRequest:
    def test_matches_logo_path(self, ti):
        assert ti.is_boba_logo_request("/images/boba-logo.jpeg") is True

    def test_rejects_other_path(self, ti):
        assert ti.is_boba_logo_request("/images/other.png") is False
        assert ti.is_boba_logo_request("/") is False


class TestServeBobaLogo:
    def test_returns_404_when_no_logo(self, ti):
        with mock.patch.object(ti, "_BOBA_LOGO_BYTES", None):
            with mock.patch("builtins.open", side_effect=FileNotFoundError):
                ti._BOBA_LOGO_BYTES = None
                status, headers, body = ti.serve_boba_logo()
                assert status == 404
                assert body == b"Not Found"

    def test_returns_200_when_logo_exists(self, ti):
        with mock.patch.object(ti, "_BOBA_LOGO_BYTES", b"\xff\xd8\xff\xe0 fake"):
            status, headers, body = ti.serve_boba_logo()
            assert status == 200
            assert body == b"\xff\xd8\xff\xe0 fake"
            ci = {k.lower(): v for k, v in headers.items()}
            assert ci["content-type"] == "image/jpeg"
