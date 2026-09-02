"""Runtime verification for the theme system.

Opens the live dashboard in a real browser, picks different palettes
from the dropdown, and asserts the CSS custom properties on the root
element actually change to the values shipped in the catalogue. Also
asserts localStorage gets populated with the `qbit.theme` payload.

Gated behind a Playwright import so the rest of the suite still runs
when `playwright` is not installed. When Playwright IS installed but
the live merge service isn't reachable, the test fails (loud) rather
than silently skipping — per the project's "no false positives"
mandate.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

# playwright is a hard requirement; import directly so a missing
# install surfaces as a clear ImportError instead of a silent skip.
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
PALETTE_TS = REPO_ROOT / "frontend" / "src" / "app" / "models" / "palette.model.ts"

DASHBOARD_URL = os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187/")

REQUIRED_CSS_VARS = (
    "--color-accent",
    "--color-bg-primary",
    "--color-text-primary",
    "--color-contrast",
)


def _parse_palette_tokens() -> dict[str, dict[str, dict[str, str]]]:
    """Return {id: {'dark': {...}, 'light': {...}}} for every palette in
    the catalogue. Reuses the parser from the unit test so both suites
    stay in lockstep."""
    import importlib.util as _imp

    spec = _imp.spec_from_file_location(
        "palette_catalog_parser",
        Path(__file__).resolve().parent.parent / "unit" / "test_palette_catalog.py",
    )
    mod = _imp.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    text = PALETTE_TS.read_text(encoding="utf-8")
    raw = mod._slice_palettes_array(text)
    data = mod._ts_literal_to_python(raw)
    out: dict[str, dict[str, dict[str, str]]] = {}
    for p in data:
        out[p["id"]] = {"dark": p["dark"], "light": p["light"]}
    return out


TOKEN_CAMEL_TO_VAR = {
    "bgPrimary": "--color-bg-primary",
    "bgSecondary": "--color-bg-secondary",
    "bgTertiary": "--color-bg-tertiary",
    "border": "--color-border",
    "textPrimary": "--color-text-primary",
    "textSecondary": "--color-text-secondary",
    "accent": "--color-accent",
    "accentHover": "--color-accent-hover",
    "contrast": "--color-contrast",
    "success": "--color-success",
    "danger": "--color-danger",
    "warning": "--color-warning",
    "info": "--color-info",
    "purple": "--color-purple",
    "shadow": "--color-shadow",
}


@pytest.fixture(scope="module")
def palettes() -> dict[str, dict[str, dict[str, str]]]:
    return _parse_palette_tokens()


def _read_var(page, name: str) -> str:
    return (
        page.evaluate(
            "(n) => getComputedStyle(document.documentElement).getPropertyValue(n)",
            name,
        )
        or ""
    ).strip()


def _read_local_storage(page, key: str) -> str | None:
    return page.evaluate("(k) => window.localStorage.getItem(k)", key)


def test_theme_switching_applies_tokens_and_persists(palettes: dict[str, dict[str, dict[str, str]]]) -> None:
    # Quick availability probe — we want a loud failure if the merge
    # service is down, not a silent skip.
    import json as _json
    import urllib.request

    # Force dark mode upfront so the test compares against the dark
    # palette tokens. Without this, whichever mode was persisted last
    # leaks in and the bgPrimary etc. assertions fail because the
    # bridge applied the LIGHT variant.
    _put = urllib.request.Request(
        f"{DASHBOARD_URL.rstrip('/')}/api/v1/theme",
        data=_json.dumps({"paletteId": "darcula", "mode": "dark"}).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(_put, timeout=10) as r:
        assert r.status == 200

    try:
        with urllib.request.urlopen(DASHBOARD_URL, timeout=10) as resp:
            assert resp.status == 200, f"Dashboard returned {resp.status}"
            body = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        pytest.fail(f"Merge service at {DASHBOARD_URL} not reachable: {exc}")

    # Angular SPAs serve a near-empty index.html; the theme-picker
    # component is defined inside the compiled main-*.js bundle. To
    # check whether the served bundle actually has the feature we
    # must grep the bundle, not the shell.
    m = re.search(r"main-[A-Z0-9]+\.js", body)
    assert m, "Could not locate main-*.js in the index HTML — rebuild the frontend (`cd frontend && ng build`)"
    try:
        with urllib.request.urlopen(f"{DASHBOARD_URL.rstrip('/')}/{m.group(0)}", timeout=10) as r:
            bundle = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        pytest.fail(f"Dashboard bundle {m.group(0)} not reachable: {exc}")

    assert "theme-picker" in bundle or "palette-dropdown" in bundle, (
        "Dashboard bundle does not include the theme-picker — rebuild + restart qbittorrent-proxy and re-run"
    )

    with sync_playwright() as pw:
        # A MISSING BROWSER BINARY IS AN ENVIRONMENT CONDITION, NOT A DEFECT
        # (§11.4.3 / §11.4.27(11)). Playwright itself IS installed here; only
        # the Chromium download is absent, and on this host Playwright's
        # bundled build refuses to install at all ("does not support chromium
        # on ubuntu26.04-x64"). Hard-failing on that reports a green product as
        # broken — a §11.4.201(1) false-positive refusal.
        #
        # tests/e2e/test_crossapp_theme.py already skips honestly here; this
        # file was missed, so the same run showed one skip and one failure for
        # the identical cause. Mirrored.
        try:
            browser = pw.chromium.launch(headless=True)
        except PlaywrightError as exc:
            if "executable doesn't exist" not in str(exc).lower():
                raise
            pytest.skip(
                "SKIP-reason=browser_binary_not_installed: Playwright's Chromium "
                "binary is not installed on this host (Playwright itself IS "
                "installed — only the browser download is missing). Install it "
                "with:\n"
                "    .venv/bin/python -m playwright install chromium\n"
                "or point BOBA_CHROMIUM_PATH at a system Chromium."
            )
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            # Wait for the theme picker to appear.
            page.wait_for_selector("app-theme-picker .palette-dropdown", timeout=15000)
            # Open the dropdown.
            page.click("app-theme-picker .palette-dropdown")
            page.wait_for_selector("app-theme-picker .palette-menu li", timeout=5000)

            # Pick Nord explicitly.
            page.click('app-theme-picker li[data-palette-id="nord"]')
            # Allow ThemeService to apply.
            page.wait_for_function(
                "() => document.documentElement.getAttribute('data-palette') === 'nord'",
                timeout=5000,
            )
            # Pick up the runtime mode so we compare against the right variant.
            mode = page.evaluate("() => document.documentElement.getAttribute('data-mode')") or "dark"
            nord_tokens = palettes["nord"][mode]
            for css_var in REQUIRED_CSS_VARS:
                # Reverse lookup token key from css var.
                key = next(k for k, v in TOKEN_CAMEL_TO_VAR.items() if v == css_var)
                expected = nord_tokens[key].lower()
                actual = _read_var(page, css_var).lower()
                assert actual == expected, f"{css_var}: expected {expected}, got {actual!r}"

            stored = _read_local_storage(page, "qbit.theme")
            assert stored, "qbit.theme missing from localStorage"
            parsed = json.loads(stored)
            assert parsed["paletteId"] == "nord"

            # Swap to Gruvbox and confirm the tokens differ from Nord.
            page.click("app-theme-picker .palette-dropdown")
            page.wait_for_selector("app-theme-picker .palette-menu li", timeout=5000)
            page.click('app-theme-picker li[data-palette-id="gruvbox"]')
            page.wait_for_function(
                "() => document.documentElement.getAttribute('data-palette') === 'gruvbox'",
                timeout=5000,
            )
            gruvbox_tokens = palettes["gruvbox"][mode]
            for css_var in REQUIRED_CSS_VARS:
                key = next(k for k, v in TOKEN_CAMEL_TO_VAR.items() if v == css_var)
                expected = gruvbox_tokens[key].lower()
                actual = _read_var(page, css_var).lower()
                assert actual == expected, f"{css_var}: expected {expected}, got {actual!r}"
        finally:
            browser.close()
