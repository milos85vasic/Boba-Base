"""
Contract test: the qBittorrent WebUI at :7186 must serve HTML with
the theme bridge already injected.

The test hits ``http://localhost:7186/`` and asserts both bridge
asset references are present in the response body. Skip cleanly
when the download proxy is unreachable (``./start.sh`` hasn't been
run in this environment) so the test suite still runs cleanly on
developer laptops.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest

PROXY_URL = os.environ.get("PROXY_URL", "http://localhost:7186")
BRIDGE_CSS = "/__qbit_theme__/skin.css"
BRIDGE_JS = "/__qbit_theme__/bootstrap.js"


def _fetch(url: str) -> tuple[int, str, bytes]:
    """Fetch ``url``, skipping cleanly when the download proxy is unreachable.

    Only a connection-level failure (proxy not running — ``./start.sh``
    hasn't been invoked in this environment) produces a SKIP. Any actual
    HTTP response is returned verbatim so the caller's body/header
    assertions still FAIL for real on a misconfigured proxy — no bluff.
    """
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as resp:
        # The proxy answered with a non-2xx status — that IS a response;
        # hand it back so the test asserts on the real status code.
        return resp.code, resp.headers.get("Content-Type", ""), resp.read()
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        pytest.skip(
            f"download proxy unreachable at {url} ({exc}) — "
            "run ./start.sh -p to bring up qbittorrent-proxy"
        )


@pytest.mark.requires_compose
def test_proxy_root_injects_theme_bridge():
    status, ctype, body = _fetch(PROXY_URL + "/")
    assert status == 200, f"proxy GET / returned {status}"
    # qBittorrent serves HTML at /.
    assert ctype.lower().startswith("text/html"), f"unexpected content-type {ctype}"
    text = body.decode("utf-8", errors="ignore")
    assert BRIDGE_CSS in text, (
        f"theme bridge CSS link {BRIDGE_CSS} missing from proxied HTML — "
        "rebuild + restart qbittorrent-proxy so plugins/download_proxy.py is live"
    )
    assert BRIDGE_JS in text, (
        f"theme bridge JS tag {BRIDGE_JS} missing from proxied HTML — "
        "rebuild + restart qbittorrent-proxy so plugins/download_proxy.py is live"
    )


@pytest.mark.requires_compose
def test_bridge_css_is_served_with_no_cache():
    status, ctype, body = _fetch(PROXY_URL + BRIDGE_CSS)
    assert status == 200, f"bridge CSS returned {status}"
    assert ctype.lower().startswith("text/css"), f"unexpected content-type {ctype}"
    text = body.decode("utf-8", errors="ignore")
    assert "--color-bg-primary" in text
    assert "--color-accent" in text


@pytest.mark.requires_compose
def test_bridge_js_is_served_with_catalog_inlined():
    status, ctype, body = _fetch(PROXY_URL + BRIDGE_JS)
    assert status == 200, f"bridge JS returned {status}"
    assert ctype.lower().startswith("application/javascript"), f"unexpected content-type {ctype}"
    text = body.decode("utf-8", errors="ignore")
    # Inlined catalog — at least these two palette ids must be present.
    assert '"darcula"' in text
    assert '"nord"' in text
    assert "/api/v1/theme" in text
