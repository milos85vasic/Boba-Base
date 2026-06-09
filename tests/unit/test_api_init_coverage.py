"""
Additional coverage for api/__init__.py — lifespan, config, health, stats, SPA.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))


class TestParseAllowedOrigins:
    def test_default_when_none(self):
        from api import _DEFAULT_ORIGINS, _parse_allowed_origins

        assert _parse_allowed_origins(None) == list(_DEFAULT_ORIGINS)

    def test_custom_origins(self):
        from api import _parse_allowed_origins

        result = _parse_allowed_origins("http://a.com, http://b.com")
        assert result == ["http://a.com", "http://b.com"]

    def test_empty_parts_fall_back(self):
        from api import _DEFAULT_ORIGINS, _parse_allowed_origins

        assert _parse_allowed_origins(",,,") == list(_DEFAULT_ORIGINS)

    def test_whitespace_only_parts_fall_back(self):
        from api import _DEFAULT_ORIGINS, _parse_allowed_origins

        assert _parse_allowed_origins(" , , ") == list(_DEFAULT_ORIGINS)

    def test_wildcard_origin(self):
        """Wildcard '*' origin should be passed through."""
        from api import _parse_allowed_origins

        result = _parse_allowed_origins("*")
        assert result == ["*"]


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_returns_healthy(self):
        from api import health_check

        result = await health_check()
        assert result["status"] == "healthy"
        assert result["service"] == "merge-search"
        assert result["version"] == "1.0.0"


class TestBridgeHealth:
    @pytest.mark.asyncio
    async def test_bridge_health_success(self):
        from api import bridge_health

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict(os.environ, {"BRIDGE_URL": "http://localhost:7188", "BRIDGE_PORT": "7188"}),
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            result = await bridge_health()
            assert result["healthy"] is True
            assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_bridge_health_failure(self):
        from api import bridge_health

        with (
            patch.dict(os.environ, {"BRIDGE_URL": "http://localhost:7188", "BRIDGE_PORT": "7188"}),
            patch("aiohttp.ClientSession", side_effect=Exception("connection refused")),
        ):
            result = await bridge_health()
            assert result["healthy"] is False
            assert "connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_bridge_health_5xx_status(self):
        """Bridge health returns unhealthy when status >= 500."""
        from api import bridge_health

        mock_resp = AsyncMock()
        mock_resp.status = 503
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict(os.environ, {"BRIDGE_URL": "http://localhost:7188", "BRIDGE_PORT": "7188"}),
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            result = await bridge_health()
            assert result["healthy"] is False


class TestGetConfig:
    @pytest.mark.asyncio
    async def test_get_config_default(self):
        from api import get_config
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"host": "localhost:7187"}

        with patch.dict(os.environ, {"PROXY_PORT": "7186"}, clear=False):
            result = await get_config(mock_request)
            assert "qbittorrent_url" in result
            assert "7186" in result["qbittorrent_url"]
            assert "proxy_port" in result


class TestStatsEndpoint:
    @pytest.mark.asyncio
    async def test_stats_no_orchestrator(self):
        from api import app, stats

        with patch.dict(app.state._state, clear=True):
            result = await stats()
            assert result["active_searches"] == 0
            assert result["completed_searches"] == 0
            assert result["trackers"] == []

    @pytest.mark.asyncio
    async def test_stats_with_orchestrator(self):
        from api import app, stats

        meta1 = MagicMock()
        meta1.status = "running"
        meta2 = MagicMock()
        meta2.status = "completed"
        meta3 = MagicMock()
        meta3.status = "aborted"

        mock_orch = MagicMock()
        mock_orch._active_searches = {"s1": meta1, "s2": meta2, "s3": meta3}
        mock_tracker = MagicMock()
        mock_tracker.name = "rutor"
        mock_tracker.url = "https://rutor.info"
        mock_tracker.enabled = True
        mock_orch._get_enabled_trackers.return_value = [mock_tracker]

        with patch.object(app.state, "search_orchestrator", mock_orch, create=True):
            result = await stats()
            assert result["active_searches"] == 1
            assert result["completed_searches"] == 1
            assert result["aborted_searches"] == 1
            assert result["total_searches"] == 3
            assert len(result["trackers"]) == 1


class TestServeIndexHtml:
    def test_serve_no_angular(self):
        from api import _serve_index_html

        with patch("api._angular_available", False):
            result = _serve_index_html()
            assert isinstance(result, dict)
            assert result["dashboard"] == "not found"

    def test_serve_with_angular(self):
        """_serve_index_html returns FileResponse when Angular is available."""
        from api import _serve_index_html

        with patch("api._angular_available", True):
            with patch("api._angular_index_path", "/fake/index.html"):
                with patch("api.FileResponse") as mock_fr:
                    result = _serve_index_html()
                    mock_fr.assert_called_once()


class TestGlobalExceptionHandler:
    @pytest.mark.asyncio
    async def test_exception_handler_returns_500(self):
        from api import global_exception_handler

        mock_request = MagicMock()
        exc = RuntimeError("test error")
        response = await global_exception_handler(mock_request, exc)
        assert response.status_code == 500


class TestLifespan:
    """Test lifespan startup and shutdown."""

    @pytest.mark.asyncio
    async def test_lifespan_startup_with_jackett_key(self):
        """Lifespan should start all services when JACKETT_API_KEY is set."""
        from types import SimpleNamespace
        from api import lifespan

        mock_app = MagicMock()
        mock_app.state = SimpleNamespace()

        mock_sched = MagicMock()
        mock_sched.load = AsyncMock()
        mock_sched.start = AsyncMock()
        mock_sched.stop = AsyncMock()

        with (
            patch.dict(os.environ, {"JACKETT_API_KEY": "valid_key"}),
            patch("merge_service.search.SearchOrchestrator") as mock_orch_cls,
            patch("merge_service.validator.TrackerValidator") as mock_val_cls,
            patch("merge_service.enricher.MetadataEnricher") as mock_enr_cls,
            patch("merge_service.scheduler.Scheduler", return_value=mock_sched),
            patch("merge_service.jackett_autoconfig.autoconfigure_jackett", AsyncMock(return_value=MagicMock())),
        ):
            mock_orch = mock_orch_cls.return_value
            mock_val = mock_val_cls.return_value
            mock_val.close = AsyncMock()

            async with lifespan(mock_app):
                pass

            mock_orch_cls.assert_called_once()
            mock_val_cls.assert_called_once()
            mock_enr_cls.assert_called_once()
            mock_sched.load.assert_called_once()
            mock_sched.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_no_jackett_key(self):
        """Lifespan should skip jackett autoconfig when no key is set."""
        from types import SimpleNamespace
        from api import lifespan

        mock_app = MagicMock()
        mock_app.state = SimpleNamespace()

        mock_sched = MagicMock()
        mock_sched.load = AsyncMock()
        mock_sched.start = AsyncMock()
        mock_sched.stop = AsyncMock()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("merge_service.search.SearchOrchestrator"),
            patch("merge_service.validator.TrackerValidator"),
            patch("merge_service.enricher.MetadataEnricher"),
            patch("merge_service.scheduler.Scheduler", return_value=mock_sched),
            patch("merge_service.validator.TrackerValidator") as mock_val_cls,
        ):
            mock_val = mock_val_cls.return_value
            mock_val.close = AsyncMock()

            async with lifespan(mock_app):
                assert mock_app.state.jackett_autoconfig_last is None

    @pytest.mark.asyncio
    async def test_lifespan_jackett_autoconfig_error(self):
        """Lifespan should handle jackett autoconfig exception gracefully."""
        from types import SimpleNamespace
        from api import lifespan

        mock_app = MagicMock()
        mock_app.state = SimpleNamespace()

        mock_sched = MagicMock()
        mock_sched.load = AsyncMock()
        mock_sched.start = AsyncMock()
        mock_sched.stop = AsyncMock()

        with (
            patch.dict(os.environ, {"JACKETT_API_KEY": "valid_key"}),
            patch("merge_service.search.SearchOrchestrator"),
            patch("merge_service.validator.TrackerValidator"),
            patch("merge_service.enricher.MetadataEnricher"),
            patch("merge_service.scheduler.Scheduler", return_value=mock_sched),
            patch("merge_service.validator.TrackerValidator") as mock_val_cls,
            patch(
                "merge_service.jackett_autoconfig.autoconfigure_jackett",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            mock_val = mock_val_cls.return_value
            mock_val.close = AsyncMock()

            async with lifespan(mock_app):
                assert mock_app.state.jackett_autoconfig_last is None

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_cleanup(self):
        """Lifespan shutdown should stop scheduler and close validator."""
        from types import SimpleNamespace
        from api import lifespan

        mock_app = MagicMock()
        mock_app.state = SimpleNamespace()

        mock_validator = MagicMock()
        mock_validator.close = AsyncMock()

        mock_sched = MagicMock()
        mock_sched.load = AsyncMock()
        mock_sched.start = AsyncMock()
        mock_sched.stop = AsyncMock()

        with (
            patch.dict(os.environ, {"JACKETT_API_KEY": "valid_key"}),
            patch("merge_service.search.SearchOrchestrator"),
            patch("merge_service.validator.TrackerValidator", return_value=mock_validator),
            patch("merge_service.enricher.MetadataEnricher"),
            patch("merge_service.scheduler.Scheduler", return_value=mock_sched),
            patch("merge_service.jackett_autoconfig.autoconfigure_jackett", AsyncMock(return_value=MagicMock())),
        ):
            async with lifespan(mock_app):
                pass

            mock_sched.stop.assert_called_once()
            mock_validator.close.assert_called_once()


class TestSPACatchAll:
    """Test the SPA catch-all route."""

    @pytest.mark.asyncio
    async def test_dashboard_root_route(self):
        """Root route should serve dashboard."""
        from api import dashboard

        with patch("api._serve_index_html") as mock_serve:
            mock_serve.return_value = {"message": "dashboard"}
            result = await dashboard()
            assert result == mock_serve.return_value

    @pytest.mark.asyncio
    async def test_dashboard_page_route(self):
        """Dashboard page route should serve index."""
        from api import dashboard_page

        with patch("api._serve_index_html") as mock_serve:
            mock_serve.return_value = {"message": "dashboard"}
            result = await dashboard_page()
            assert result == mock_serve.return_value

    @pytest.mark.asyncio
    async def test_spa_catch_all_api_path_returns_404(self):
        """Catch-all should raise 404 for /api/ paths."""
        from api import spa_catch_all
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await spa_catch_all("api/v1/search")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_spa_catch_all_health_returns_404(self):
        """Catch-all should raise 404 for health path."""
        from api import spa_catch_all
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await spa_catch_all("health")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_spa_catch_all_existing_file(self):
        """Catch-all should return FileResponse for existing files."""
        from api import spa_catch_all

        with patch("api._angular_dist_path", "/tmp/spa"):
            with patch("os.path.isfile", return_value=True):
                with patch("api.FileResponse") as mock_fr:
                    await spa_catch_all("assets/app.js")
                    mock_fr.assert_called_once()

    @pytest.mark.asyncio
    async def test_spa_catch_all_fallback_to_index(self):
        """Catch-all should serve index.html for unknown paths."""
        from api import spa_catch_all

        with patch("api._angular_dist_path", "/tmp/spa"):
            with patch("os.path.isfile", return_value=False):
                with patch("api._serve_index_html") as mock_serve:
                    await spa_catch_all("some/unknown/path")
                    mock_serve.assert_called_once()
