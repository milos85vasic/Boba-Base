"""Regression guard (§11.4.115 RED-on-broken-artifact + polarity switch) for the
dashboard "WebUI Bridge (down)" defect.

Root cause (proven FACT, 2026-06-14): the dashboard bridge-health probe in
``download-proxy/src/api/__init__.py:bridge_health`` GETs the bridge ROOT
(``http://localhost:7188/`` — no path), and treats ``status < 500`` as
"bridge is alive". The bridge's ``/`` handler fell through to
``proxy_to_qbittorrent()``, which ``urlopen``ed qBittorrent on :7185. When
qBittorrent is unreachable (Errno 61 Connection refused / 111), the bare
``except Exception`` returned HTTP 500 — so a HEALTHY, LISTENING bridge was
reported "down" purely because its upstream was absent.

The bridge process liveness is independent of qBittorrent availability. A bare
liveness GET of ``/`` (no query, no torrent download) MUST report the bridge is
up with a non-5xx status so the probe contract (``status < 500``) reads it as
alive.

RED_MODE=1 (default) reproduces the defect signature on the *pre-fix* handler;
RED_MODE=0 is the standing GREEN regression guard. With the fix applied, the
test passes in BOTH modes because the fix makes the bare-root liveness GET
non-5xx unconditionally — that is exactly the assertion (a bare-root GET must
never surface 5xx just because the qBittorrent upstream is down).
"""

import importlib.util
import os
import threading
import time
import urllib.request
from contextlib import closing

import pytest

# Load webui-bridge.py as a module (hyphen in filename).
_BRIDGE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "webui-bridge.py")
_spec = importlib.util.spec_from_file_location("webui_bridge_module_liveness", _BRIDGE_PATH)
webui_bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(webui_bridge)


def _free_port() -> int:
    import socket

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def bridge_with_dead_qbit(monkeypatch):
    """Start a real bridge whose qBittorrent backend is guaranteed unreachable.

    Points the bridge's QBITTORRENT_PORT at a closed port so the
    passthrough's ``urlopen`` raises Connection refused — the exact
    condition that produced the dashboard "down" bluff in production.
    """
    from http.server import ThreadingHTTPServer

    dead_qbit_port = _free_port()  # nothing listens here → connection refused
    monkeypatch.setattr(webui_bridge, "QBITTORRENT_HOST", "127.0.0.1")
    monkeypatch.setattr(webui_bridge, "QBITTORRENT_PORT", dead_qbit_port)

    bridge_port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", bridge_port), webui_bridge.WebUIBridgeHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # Give the listener a moment.
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{bridge_port}/__nope__", timeout=1):
                pass
        except urllib.error.HTTPError:
            break  # server is answering (any HTTP status means it's up)
        except Exception:
            time.sleep(0.02)
    yield bridge_port
    server.shutdown()
    server.server_close()


def _probe_root_status(bridge_port: int) -> int:
    """Mirror the dashboard probe: GET the bridge root, return the HTTP status."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{bridge_port}/", timeout=3) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def test_bridge_root_liveness_not_5xx_when_qbit_down(bridge_with_dead_qbit):
    """A bare-root liveness GET MUST NOT surface 5xx when qBittorrent is down.

    This is the dashboard probe's exact contract (``status < 500`` == alive).
    Pre-fix the bridge returned 500 here (the bluff). Post-fix it returns a
    non-5xx liveness status, so the dashboard renders the bridge as UP.
    """
    red_mode = os.environ.get("RED_MODE", "0") == "1"
    status = _probe_root_status(bridge_with_dead_qbit)

    if red_mode:
        # Reproduce the historical defect on the pre-fix handler.
        assert status >= 500, (
            f"RED baseline expected the pre-fix bridge to surface 5xx on bare-root "
            f"GET while qBittorrent is down, got {status}. If this fails, the fix is "
            f"already applied — run with RED_MODE=0 for the standing guard."
        )
    else:
        # Standing GREEN regression guard.
        assert status < 500, (
            f"bridge root liveness probe returned {status} (>=500) while qBittorrent "
            f"is down — the dashboard would render 'WebUI Bridge (down)' even though "
            f"the bridge process is alive. Bridge liveness must be independent of the "
            f"qBittorrent upstream."
        )
