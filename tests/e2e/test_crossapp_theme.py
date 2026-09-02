"""
Dashboard theme e2e test (:7187 only).

Opens the Angular dashboard at :7187, picks Nord in the palette
dropdown, asserts the choice is persisted and reflected in the
shared theme STATE (``/api/v1/theme``), then flips to Gruvbox and
asserts the flip.

SCOPE NOTE (2026-09-01): the :7186 half of this test — which asserted
that the proxied qBittorrent WebUI mirrored the dashboard palette via
an injected ``/__qbit_theme__/`` CSS+JS bridge — was REMOVED with the
themed-WebUI overlay itself by operator decision. The proxy on :7186
now serves the STOCK vanilla qBittorrent WebUI byte-for-byte
(guard: ``tests/integration/test_vanilla_webui_unmodified.py``).
The cross-app theme STATE (this file, ``theme_state.py``, the
``/api/v1/theme`` endpoints, ``qBitTorrent-go/internal/api/theme.go``
and the Angular theme service + picker) is UNAFFECTED and still under
test here.

Any real failure in the dashboard theme path (palette not applied, not
persisted, state not round-tripped) makes the test fail — *not* skip —
so the signal is trustworthy.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

# playwright is a hard requirement for these e2e tests. If the import
# fails, the tests legitimately cannot run and the failure is visible
# rather than hidden behind a skip. (The missing browser BINARY is a
# different case — see _launch_chromium below.)
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

DASHBOARD_URL = os.environ.get("MERGE_SERVICE_URL", "http://localhost:7187").rstrip("/")

# Nord + Gruvbox dark bg-primary values from the catalogue — these
# must match frontend/src/app/models/palette.model.ts exactly.
NORD_DARK_BG = "#2e3440"
GRUVBOX_DARK_BG = "#282828"


def _preflight() -> None:
    """Fail loudly when the dashboard or its theme picker is missing."""
    with urllib.request.urlopen(DASHBOARD_URL + "/", timeout=5) as resp:
        assert resp.status == 200, f"Dashboard returned {resp.status}"
        body = resp.read().decode("utf-8", errors="ignore")

    import re as _re

    m = _re.search(r"main-[A-Z0-9]+\.js", body)
    assert m, (
        "Could not locate main-*.js in the index HTML — rebuild the "
        "frontend (`cd frontend && ng build`) and restart qbittorrent-proxy"
    )
    with urllib.request.urlopen(f"{DASHBOARD_URL}/{m.group(0)}", timeout=10) as r:
        bundle = r.read().decode("utf-8", errors="ignore")
    assert "theme-picker" in bundle or "palette-dropdown" in bundle, (
        "Dashboard bundle does not include the theme-picker — rebuild + "
        "restart qbittorrent-proxy and re-run"
    )


@pytest.fixture(scope="module", autouse=True)
def _check_environment() -> None:
    _preflight()


def _select_palette(page, palette_id: str) -> None:
    page.click("app-theme-picker .palette-dropdown")
    page.wait_for_selector("app-theme-picker .palette-menu li", timeout=5000)
    page.click(f'app-theme-picker li[data-palette-id="{palette_id}"]')
    page.wait_for_function(
        f"() => document.documentElement.getAttribute('data-palette') === {palette_id!r}",
        timeout=5000,
    )


def _launch_chromium(pw):
    """Launch headless Chromium, skipping ONLY when its binary is absent.

    A missing browser executable is an ENVIRONMENT condition, not a product
    defect: the code under test is fine and there is nothing to fix in this
    repo, so reporting FAIL here would be a false-positive refusal
    (§11.4.201(1) / §11.4.27(11)) that teaches readers to ignore red. It
    becomes an honest SKIP-with-reason (§11.4.3) naming the exact install
    command instead.

    The predicate is deliberately NARROW — it matches only Playwright's
    "Executable doesn't exist" message. EVERY other launch failure (sandbox
    denied, missing shared library, OOM, crash on start) is re-raised and
    still FAILS, because those are real conditions a skip would hide.
    """
    try:
        return pw.chromium.launch(headless=True)
    except PlaywrightError as exc:
        if "executable doesn't exist" not in str(exc).lower():
            raise
        pytest.skip(
            "SKIP-reason=browser_binary_not_installed: Playwright's Chromium "
            "binary is not installed on this host (Playwright itself IS "
            "installed — only the browser download is missing). Install it "
            "with:\n"
            "    .venv/bin/python -m playwright install chromium\n"
            "(add `--with-deps` only if system libraries are also missing; "
            "that variant needs root and is an operator action).\n"
            f"Playwright reported: {exc}",
            allow_module_level=False,
        )


def _theme_state() -> dict:
    with urllib.request.urlopen(f"{DASHBOARD_URL}/api/v1/theme", timeout=10) as r:
        assert r.status == 200, f"GET /api/v1/theme returned {r.status}"
        return json.loads(r.read().decode("utf-8"))


def _assert_bg_primary(page, expected_hex: str, timeout_ms: int) -> None:
    page.wait_for_function(
        "(expectedHex) => {\n"
        "  const v = getComputedStyle(document.documentElement)"
        ".getPropertyValue('--color-bg-primary').trim().toLowerCase();\n"
        "  return v === expectedHex.toLowerCase();\n"
        "}",
        arg=expected_hex,
        timeout=timeout_ms,
    )


def test_dashboard_theme_switch_nord_then_gruvbox() -> None:
    # Force dark mode before the test. Without this, whichever mode was
    # last persisted in /api/v1/theme leaks in and the NORD_DARK_BG /
    # GRUVBOX_DARK_BG assertions fail because the palette's LIGHT
    # bg-primary is what gets applied.
    req = urllib.request.Request(
        f"{DASHBOARD_URL}/api/v1/theme",
        data=json.dumps({"paletteId": "nord", "mode": "dark"}).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200, f"PUT /api/v1/theme returned {r.status}"

    with sync_playwright() as pw:
        browser = _launch_chromium(pw)
        try:
            context = browser.new_context()
            dashboard = context.new_page()
            dashboard.goto(DASHBOARD_URL + "/", wait_until="domcontentloaded")
            dashboard.wait_for_selector("app-theme-picker .palette-dropdown", timeout=15000)

            # Nord.
            _select_palette(dashboard, "nord")
            _assert_bg_primary(dashboard, NORD_DARK_BG, 15000)
            stored = dashboard.evaluate("() => window.localStorage.getItem('qbit.theme')")
            assert stored and '"nord"' in stored, f"dashboard did not persist Nord: {stored!r}"
            state = _theme_state()
            assert state.get("paletteId") == "nord", f"shared theme state is {state!r}"

            # Flip to Gruvbox.
            _select_palette(dashboard, "gruvbox")
            _assert_bg_primary(dashboard, GRUVBOX_DARK_BG, 15000)
            stored2 = dashboard.evaluate("() => window.localStorage.getItem('qbit.theme')")
            assert stored2 and '"gruvbox"' in stored2
            state2 = _theme_state()
            assert state2.get("paletteId") == "gruvbox", f"shared theme state is {state2!r}"
        finally:
            browser.close()
