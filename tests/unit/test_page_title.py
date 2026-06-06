"""Guards the user-visible browser tab title.

Per owner directive (2026-04-19): the tab title must read exactly
"Боба Dashboard" — not "qBittorrent-Fixed" and not the
compound "qBittorrent-Fixed — Боба Dashboard".

Also guards the built bundle so a rebuild gap can't leak the old
title back in silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INDEX_HTML = REPO / "frontend" / "src" / "index.html"
DASHBOARD_HTML = REPO / "frontend" / "src" / "app" / "components" / "dashboard" / "dashboard.component.html"
BUILT_INDEX_HTML = REPO / "download-proxy" / "src" / "ui" / "dist" / "frontend" / "browser" / "index.html"

EXPECTED_TITLE = "Боба Dashboard"


@pytest.fixture(scope="module")
def index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_index_html_title_is_exact(index_html: str) -> None:
    m = re.search(r"<title>([^<]+)</title>", index_html)
    assert m is not None, "index.html must have a <title>"
    assert m.group(1) == EXPECTED_TITLE, f"<title> must be exactly {EXPECTED_TITLE!r}, got {m.group(1)!r}"


def test_index_html_has_no_qbittorrent_fixed_leak(index_html: str) -> None:
    assert "qBittorrent-Fixed" not in index_html, (
        "index.html contains the legacy 'qBittorrent-Fixed' string — owner "
        "renamed this to 'Боба Dashboard' on 2026-04-23"
    )


def test_dashboard_template_has_no_qbittorrent_fixed_leak() -> None:
    tpl = DASHBOARD_HTML.read_text(encoding="utf-8")
    assert "qBittorrent-Fixed" not in tpl


def test_served_bundle_title_matches() -> None:
    """Built bundle (Angular build output) must carry the renamed title.

    Reads the compiled ``index.html`` directly from disk so this test
    runs without a live stack. Build the frontend with ``npx ng build``
    to keep it current.
    """
    assert BUILT_INDEX_HTML.is_file(), (
        f"Built index.html not found at {BUILT_INDEX_HTML}. "
        "Run `cd frontend && npx ng build` first."
    )
    body = BUILT_INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(r"<title>([^<]+)</title>", body)
    assert m is not None, "built index.html has no <title>"
    assert m.group(1) == EXPECTED_TITLE, (
        f"built bundle advertises {m.group(1)!r} instead of "
        f"{EXPECTED_TITLE!r}. Rebuild + restart qbittorrent-proxy to "
        "pick up the rename."
    )
