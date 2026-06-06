"""Guards that the 'Made with ❤ by Vasic Digital' footer is wired into
every page of the Angular dashboard.

Original TDD coverage (commit 368d7fe,
tests/integration/test_manual_issues.py::TestFooter) verified the
legacy server-rendered template. That template was abandoned during
the Angular 19 port (bb2aec4), and the footer was lost silently
because no CI test watched the Angular shell.

This suite protects the restoration:

1. The source component file exists and references the brand fields.
2. AppComponent mounts ``<app-site-footer>`` so the footer appears on
   every page (AppComponent is the SPA shell).
3. The Angular test suite ships a site-footer spec so the footer's
   rendered DOM is asserted by Vitest every run.
4. The built bundle (Angular build output) contains the footer's footprint
   (read from disk, no running stack required).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FOOTER_TS = REPO_ROOT / "frontend" / "src" / "app" / "components" / "site-footer" / "site-footer.component.ts"
FOOTER_SPEC = REPO_ROOT / "frontend" / "src" / "app" / "components" / "site-footer" / "site-footer.component.spec.ts"
APP_TS = REPO_ROOT / "frontend" / "src" / "app" / "app.component.ts"
BUILT_BROWSER = REPO_ROOT / "download-proxy" / "src" / "ui" / "dist" / "frontend" / "browser"


@pytest.fixture(scope="module")
def footer_source() -> str:
    assert FOOTER_TS.is_file(), FOOTER_TS
    return FOOTER_TS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_source() -> str:
    assert APP_TS.is_file(), APP_TS
    return APP_TS.read_text(encoding="utf-8")


def test_footer_component_source_exists(footer_source: str) -> None:
    assert footer_source, "site-footer.component.ts is empty"


def test_footer_source_contains_made_with(footer_source: str) -> None:
    assert "Made with" in footer_source


def test_footer_source_contains_heart_symbol(footer_source: str) -> None:
    heart_indicators = ["\u2764", "&#10084;", "&hearts;", "\u2665"]
    assert any(h in footer_source for h in heart_indicators), (
        "site-footer.component.ts must contain a heart symbol or HTML entity"
    )


def test_footer_source_contains_vasic_digital_link(footer_source: str) -> None:
    assert "Vasic Digital" in footer_source
    assert "https://www.vasic.digital" in footer_source
    assert re.search(
        r"<a[^>]*href=[\"']https://www\.vasic\.digital[\"']",
        footer_source,
    ), "Vasic Digital must be wired as an anchor with href=https://www.vasic.digital"


def test_footer_link_has_security_rels(footer_source: str) -> None:
    assert 'target="_blank"' in footer_source or "target='_blank'" in footer_source
    rel_match = re.search(r'rel=["\']([^"\']*)["\']', footer_source)
    assert rel_match is not None, "footer link must declare a rel attribute"
    rel = rel_match.group(1)
    assert "noopener" in rel and "noreferrer" in rel


def test_app_component_imports_site_footer(app_source: str) -> None:
    assert "SiteFooterComponent" in app_source
    assert "site-footer.component" in app_source


def test_app_template_mounts_app_site_footer(app_source: str) -> None:
    assert "<app-site-footer>" in app_source


def test_vitest_spec_exists_for_footer() -> None:
    assert FOOTER_SPEC.is_file(), FOOTER_SPEC
    spec = FOOTER_SPEC.read_text(encoding="utf-8")
    for marker in ("Made with", "Vasic Digital", "https://www.vasic.digital", "heart"):
        assert marker in spec, f"site-footer.component.spec.ts missing check for {marker!r}"


def test_footer_styles_use_design_system_tokens(footer_source: str) -> None:
    """The restored footer MUST follow the palette-switch feature — no
    hardcoded brand red like the legacy version had.
    """
    assert "var(--color-accent)" in footer_source
    assert "var(--color-border)" in footer_source
    # No #e94560 (the legacy hardcoded accent).
    assert "#e94560" not in footer_source


def test_footer_appears_in_served_bundle() -> None:
    """The compiled dashboard bundle must carry the footer footprint.

    Reads the built ``index.html`` and ``main-*.js`` bundle directly
    from disk so this test runs without a live stack. Build the
    frontend with ``npx ng build`` to keep it current.
    """
    assert BUILT_BROWSER.is_dir(), (
        f"Built browser directory not found at {BUILT_BROWSER}. "
        "Run `cd frontend && npx ng build` first."
    )
    index_html = BUILT_BROWSER / "index.html"
    assert index_html.is_file(), f"Built {index_html} not found"

    body = index_html.read_text(encoding="utf-8")
    m = re.search(r"main-[A-Z0-9]+\.js", body)
    assert m, "main-*.js bundle link must be in built index.html"

    bundle_path = BUILT_BROWSER / m.group(0)
    assert bundle_path.is_file(), f"Built JS bundle not found at {bundle_path}"

    bundle = bundle_path.read_text(encoding="utf-8")
    assert "site-footer" in bundle or "www.vasic.digital" in bundle, (
        "Built bundle predates the footer restoration — rebuild with `cd frontend && npx ng build`"
    )
    assert "www.vasic.digital" in bundle, "footer URL must be in the compiled bundle"
    assert "Vasic Digital" in bundle, "footer brand text must be in the compiled bundle"
