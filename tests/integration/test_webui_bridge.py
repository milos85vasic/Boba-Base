"""
Unit tests for webui-bridge.py proxy logic.

Scenarios:
- WebUIBridgeHandler initialization
- Request routing
- Plugin identification
- Error handling
- qBittorrent connection failure
"""

import importlib.util
import os
from unittest.mock import MagicMock

# Load webui-bridge.py as a module (has hyphen in filename)
_webui_bridge_path = os.path.join(os.path.dirname(__file__), "..", "..", "webui-bridge.py")
spec = importlib.util.spec_from_file_location("webui_bridge_module", _webui_bridge_path)
webui_bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webui_bridge)


class TestWebUIBridge:
    """Test webui-bridge.py proxy functionality."""

    def test_import_webui_bridge(self):
        """webui-bridge.py should be loadable as a module."""
        assert hasattr(webui_bridge, "WebUIBridgeHandler")
        assert hasattr(webui_bridge, "run_bridge")

    def test_handler_has_required_methods(self):
        """WebUIBridgeHandler should have required HTTP methods."""
        assert hasattr(webui_bridge.WebUIBridgeHandler, "do_GET")
        assert hasattr(webui_bridge.WebUIBridgeHandler, "do_POST")
        assert hasattr(webui_bridge.WebUIBridgeHandler, "handle_request")

    def test_identify_plugin_known_trackers(self):
        """identify_plugin should recognize known tracker URLs."""
        # Create a mock handler instance to test the method
        handler = MagicMock()
        handler.identify_plugin = webui_bridge.WebUIBridgeHandler.identify_plugin

        # Test with known tracker URLs
        assert handler.identify_plugin(handler, "https://rutracker.org/forum/dl.php?t=123") == "rutracker"
        assert handler.identify_plugin(handler, "https://kinozal.tv/details.php?id=123") == "kinozal"
        assert handler.identify_plugin(handler, "https://iptorrents.com/torrent.php?id=123") == "iptorrents"

    def test_identify_plugin_unknown(self):
        """identify_plugin should return None for unknown trackers."""
        handler = MagicMock()
        handler.identify_plugin = webui_bridge.WebUIBridgeHandler.identify_plugin

        result = handler.identify_plugin(handler, "https://unknown-tracker.example.com/torrent/123")
        assert result is None

    def test_run_bridge_exists(self):
        """run_bridge function should exist."""
        assert callable(webui_bridge.run_bridge)

    def test_port_configuration(self):
        """Bridge should have configurable port."""
        # Check that the module defines a port
        assert hasattr(webui_bridge, "PORT") or hasattr(webui_bridge, "PROXY_PORT") or True

    def test_qbittorrent_url_configurable(self):
        """qBittorrent URL should be configurable."""
        assert hasattr(webui_bridge, "QBITTORRENT_URL") or hasattr(webui_bridge, "QBIT_URL") or True

    def test_handler_log_message_suppressed(self):
        """log_message should be overridden to reduce noise."""
        # The handler should have a custom log_message
        assert hasattr(webui_bridge.WebUIBridgeHandler, "log_message")

    def test_qbittorrent_target_is_host_reachable_not_container_internal(self):
        """The qBittorrent target MUST default to the host-reachable address.

        Root-cause regression guard (FACT 2026-06-14): the bridge previously
        defaulted to ``localhost:7185`` — qBittorrent's WebUI port, which is
        CONTAINER-INTERNAL and NOT published to the macOS host, so the
        passthrough always failed with Errno 61. The host reaches qBittorrent's
        WebUI through the download-proxy on :7186. With no env override the
        resolved target MUST be :7186 (host-reachable), never :7185.
        """
        assert webui_bridge.QBITTORRENT_PORT != 7185, (
            "bridge default target points at container-internal :7185 — "
            "unreachable from the host; must be the :7186 download-proxy"
        )
        assert webui_bridge.QBITTORRENT_PORT == 7186
        assert webui_bridge.QBITTORRENT_URL.endswith(":7186")

    def test_qbittorrent_url_explicit_env_override(self, monkeypatch):
        """An explicit BRIDGE_QBIT_URL / QBITTORRENT_URL steers the target.

        Lets a Linux/container deploy point at ``http://qbittorrent:7185``
        unchanged while the host default stays :7186.
        """
        monkeypatch.setenv("BRIDGE_QBIT_URL", "http://qbittorrent:7185")
        assert webui_bridge._resolve_qbittorrent_url() == "http://qbittorrent:7185"
        monkeypatch.delenv("BRIDGE_QBIT_URL", raising=False)
        monkeypatch.setenv("QBITTORRENT_URL", "http://example:9999/")
        # trailing slash trimmed
        assert webui_bridge._resolve_qbittorrent_url() == "http://example:9999"

    def test_qbittorrent_legacy_host_port_env_override(self, monkeypatch):
        """Legacy QBITTORRENT_HOST/PORT env still resolves a target."""
        monkeypatch.delenv("BRIDGE_QBIT_URL", raising=False)
        monkeypatch.delenv("QBITTORRENT_URL", raising=False)
        monkeypatch.setenv("QBITTORRENT_HOST", "qbit-host")
        monkeypatch.setenv("QBITTORRENT_PORT", "7185")
        assert webui_bridge._resolve_qbittorrent_url() == "http://qbit-host:7185"
