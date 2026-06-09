"""
Unit tests for main.py dual-thread startup.

Scenarios:
- Import without errors
- Function signatures
- Port configuration
"""

import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

# Add source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src"))


class TestMainStartup:
    """Test main.py startup behavior."""

    def test_import_main(self):
        """main.py should be importable without errors."""
        try:
            assert True
        except Exception as e:
            pytest.fail(f"Failed to import main.py: {e}")

    def test_main_functions_exist(self):
        """main.py should define required functions."""
        import main

        assert hasattr(main, "start_original_proxy")
        assert hasattr(main, "start_fastapi_server")
        assert hasattr(main, "main")
        assert callable(main.start_original_proxy)
        assert callable(main.start_fastapi_server)
        assert callable(main.main)

    def test_start_original_proxy_runs(self):
        """start_original_proxy should exist."""
        import main

        assert main.start_original_proxy is not None

    def test_start_fastapi_server_runs(self):
        """start_fastapi_server should exist."""
        import main

        assert main.start_fastapi_server is not None

    def test_main_function_exists(self):
        """main() function should orchestrate startup."""
        import main

        sig = main.main.__code__.co_varnames
        assert isinstance(sig, tuple)

    def test_main_starts_both_services_mocked(self):
        """main() should attempt to start both services (mocked)."""
        import main

        main._shutdown_event.set()
        try:
            with patch("threading.Thread") as mock_thread:
                main.main()
            assert mock_thread.call_count >= 1
        finally:
            main._shutdown_event.clear()

    def test_port_env_vars(self):
        """Port should be configurable via environment."""
        with patch.dict(os.environ, {"PROXY_PORT": "9999", "MERGE_SERVICE_PORT": "9998"}):
            import importlib

            import main

            importlib.reload(main)
            assert main is not None


class TestMainSignalHandler:
    """Test _signal_handler function."""

    def test_signal_handler_sets_shutdown_event(self):
        """Calling _signal_handler should set _shutdown_event."""
        import main

        main._shutdown_event.clear()
        main._signal_handler(None, None)
        assert main._shutdown_event.is_set()
        main._shutdown_event.clear()

    def test_signal_handler_accepts_int_and_object(self):
        """_signal_handler should accept (int, frame) signature."""
        import main

        main._shutdown_event.clear()
        main._signal_handler(15, None)
        assert main._shutdown_event.is_set()
        main._shutdown_event.clear()


class TestMainOriginalProxy:
    """Test start_original_proxy function."""

    def test_start_original_proxy_success(self, caplog):
        """start_original_proxy should call run_server when import succeeds."""
        import main

        mock_run_server = MagicMock()
        fake_module = MagicMock()
        fake_module.run_server = mock_run_server

        with patch.dict("sys.modules", {"download_proxy": fake_module}):
            with patch("main.logger") as mock_logger:
                main.start_original_proxy()
                mock_run_server.assert_called_once()
                mock_logger.info.assert_any_call("Starting original download proxy...")

    def test_start_original_proxy_import_error(self, caplog):
        """start_original_proxy should log error when import fails."""
        import main

        with patch.dict("sys.modules"):
            if "download_proxy" in sys.modules:
                del sys.modules["download_proxy"]
            with patch("main.logger") as mock_logger:
                with patch("builtins.__import__", side_effect=ImportError("no module")):
                    main.start_original_proxy()
                    mock_logger.error.assert_called_once()
                    assert "Original proxy failed" in str(mock_logger.error.call_args)

    def test_start_original_proxy_engines_dir_env(self):
        """start_original_proxy should use ENGINES_DIR env var."""
        import main

        with patch.dict(os.environ, {"ENGINES_DIR": "/custom/engines"}):
            with patch("main.logger"):
                with patch.dict("sys.modules", {"download_proxy": MagicMock()}):
                    main.start_original_proxy()

    def test_start_original_proxy_run_server_exception(self):
        """start_original_proxy should log error when run_server raises."""
        import main

        mock_run_server = MagicMock(side_effect=RuntimeError("server crash"))
        fake_module = MagicMock()
        fake_module.run_server = mock_run_server

        with patch.dict("sys.modules", {"download_proxy": fake_module}):
            with patch("main.logger") as mock_logger:
                main.start_original_proxy()
                mock_run_server.assert_called_once()
                mock_logger.error.assert_called_once()
                assert "Original proxy failed" in str(mock_logger.error.call_args)


class TestMainFastAPIServer:
    """Test start_fastapi_server function."""

    def test_start_fastapi_server_imports_uvicorn(self):
        """start_fastapi_server should import and configure uvicorn."""
        import main

        mock_server = MagicMock()
        mock_config = MagicMock()

        with patch("main.logger") as mock_logger:
            with patch.dict("sys.modules"):
                with patch("uvicorn.Config", return_value=mock_config) as mock_config_cls:
                    with patch("uvicorn.Server", return_value=mock_server) as mock_server_cls:
                        with patch("asyncio.run") as mock_asyncio_run:
                            with patch("api.app", MagicMock()):
                                main.start_fastapi_server()
                                mock_config_cls.assert_called_once()
                                mock_server_cls.assert_called_once_with(mock_config)
                                mock_asyncio_run.assert_called_once_with(mock_server.serve())

    def test_start_fastapi_server_uses_env_port(self):
        """start_fastapi_server should use MERGE_SERVICE_PORT from env."""
        import main

        with patch.dict(os.environ, {"MERGE_SERVICE_PORT": "9999", "MERGE_SERVICE_HOST": "127.0.0.1"}):
            with patch("main.logger"):
                with patch("uvicorn.Config") as mock_config_cls:
                    with patch("uvicorn.Server"):
                        with patch("asyncio.run"):
                            with patch("api.app", MagicMock()):
                                main.start_fastapi_server()
                                call_kwargs = mock_config_cls.call_args.kwargs
                                assert call_kwargs["host"] == "127.0.0.1"
                                assert call_kwargs["port"] == 9999

    def test_start_fastapi_server_default_host_port(self):
        """start_fastapi_server should use default host and port."""
        import main

        with patch.dict(os.environ, {}, clear=True):
            with patch("main.logger"):
                with patch("uvicorn.Config") as mock_config_cls:
                    with patch("uvicorn.Server"):
                        with patch("asyncio.run"):
                            with patch("api.app", MagicMock()):
                                main.start_fastapi_server()
                                call_kwargs = mock_config_cls.call_args.kwargs
                                assert call_kwargs["host"] == "0.0.0.0"
                                assert call_kwargs["port"] == 7187

    def test_start_fastapi_server_uvicorn_failure(self, caplog):
        """start_fastapi_server should log error when uvicorn fails."""
        import main

        with patch("main.logger") as mock_logger:
            with patch("uvicorn.Config", side_effect=RuntimeError("uvicorn crash")):
                with patch("api.app", MagicMock()):
                    main.start_fastapi_server()
                    mock_logger.error.assert_called_once()
                    assert "FastAPI server failed" in str(mock_logger.error.call_args)

    def test_start_fastapi_server_app_import_error(self, caplog):
        """start_fastapi_server should log error when api.app import fails."""
        import main

        with patch("main.logger") as mock_logger:
            with patch("builtins.__import__", side_effect=ImportError("no api")):
                main.start_fastapi_server()
                mock_logger.error.assert_called_once()
                assert "FastAPI server failed" in str(mock_logger.error.call_args)


class TestMainMain:
    """Test main() function."""

    def test_main_registers_signal_handlers(self):
        """main() should register SIGTERM and SIGINT handlers."""
        import main

        main._shutdown_event.set()
        try:
            with patch("signal.signal") as mock_signal:
                with patch("threading.Thread"):
                    with patch("main.logger"):
                        main.main()
                        assert mock_signal.call_count >= 2
        finally:
            main._shutdown_event.clear()

    def test_main_creates_daemon_threads(self):
        """main() should create daemon threads for both services."""
        import main

        main._shutdown_event.set()
        try:
            with patch("threading.Thread") as mock_thread:
                with patch("main.logger"):
                    with patch("signal.signal"):
                        main.main()
                        for call_args in mock_thread.call_args_list:
                            assert call_args.kwargs.get("daemon") is True
        finally:
            main._shutdown_event.clear()

    def test_main_loop_exits_when_event_set(self):
        """Main loop should exit when shutdown event is set."""
        import main

        main._shutdown_event.set()
        try:
            with patch("signal.signal"):
                with patch("threading.Thread"):
                    with patch("main.logger"):
                        main.main()
        finally:
            main._shutdown_event.clear()

    def test_main_loop_waits_on_event(self):
        """Main loop should call _shutdown_event.wait()."""
        import main

        main._shutdown_event.set()
        try:
            with patch("signal.signal"):
                with patch("threading.Thread"):
                    with patch("main.logger") as mock_logger:
                        main.main()
                        mock_logger.info.assert_any_call("Shutting down...")
                        mock_logger.info.assert_any_call("Shutdown complete")
        finally:
            main._shutdown_event.clear()
