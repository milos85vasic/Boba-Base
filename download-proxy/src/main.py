#!/usr/bin/env python3
"""
Main entry point for the Боба Search Service.

Starts both:
1. The original download proxy (HTTP server)
2. The FastAPI merge service (REST API)
"""

import logging
import os
import signal
import sys
import threading

from config.log_filter import CredentialScrubber

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger().addFilter(CredentialScrubber())
logger = logging.getLogger(__name__)

_shutdown_event = threading.Event()


def _signal_handler(signum: int, frame: object) -> None:
    _shutdown_event.set()


def start_original_proxy() -> None:
    """Start the original download_proxy.py."""
    logger.info("Starting original download proxy...")
    try:
        engines_dir = os.environ.get("ENGINES_DIR", "/config/qBittorrent/nova3/engines")
        if engines_dir not in sys.path:
            sys.path.insert(0, engines_dir)
        from download_proxy import run_server  # type: ignore[import-not-found]

        run_server()
    except Exception as e:
        logger.error(f"Original proxy failed: {e}")


def start_fastapi_server() -> None:
    """Start the FastAPI merge service."""
    logger.info("Starting FastAPI merge service...")
    try:
        src_dir = os.path.dirname(os.path.abspath(__file__))
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        import uvicorn

        from api import app

        # Configure uvicorn. MERGE_SERVICE_HOST defaults to 0.0.0.0 because
        # the container uses network_mode: host and external requests arrive
        # on 7187 from any interface (the host port is firewalled per the
        # constitution Security Requirements). Override with
        # MERGE_SERVICE_HOST=127.0.0.1 in deployments where the merge
        # service should be localhost-only.
        merge_port = int(os.environ.get("MERGE_SERVICE_PORT", "7187"))
        merge_host = os.environ.get("MERGE_SERVICE_HOST", "0.0.0.0")  # nosec B104  # noqa: S104
        config = uvicorn.Config(
            app,
            host=merge_host,
            port=merge_port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        # Run in async mode
        import asyncio

        asyncio.run(server.serve())
    except Exception as e:
        logger.error(f"FastAPI server failed: {e}")


def main() -> None:
    """Main entry point."""
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info("=" * 60)
    logger.info("Боба Search Service Starting")
    logger.info("=" * 60)

    # Map BOBA_UPSTREAM_PROXY → HTTP(S)_PROXY/NO_PROXY before any worker thread
    # starts, so tracker-bound urllib + aiohttp egress honors the configured
    # outbound proxy with the loopback/sidecar bypass. No-op when unset.
    try:
        src_dir = os.path.dirname(os.path.abspath(__file__))
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from config.proxy import apply_proxy_env, upstream_proxy

        apply_proxy_env()
        if upstream_proxy():
            logger.info("Tracker-bound egress routed through upstream proxy (BOBA_UPSTREAM_PROXY/*_PROXY)")
    except Exception as e:  # pragma: no cover - never block startup on proxy setup
        logger.warning(f"Upstream proxy setup skipped: {e}")

    proxy_thread = threading.Thread(target=start_original_proxy, daemon=True)
    fastapi_thread = threading.Thread(target=start_fastapi_server, daemon=True)

    proxy_thread.start()
    logger.info("Original proxy thread started")

    fastapi_thread.start()
    logger.info("FastAPI thread started")

    while not _shutdown_event.is_set():
        _shutdown_event.wait(60)

    logger.info("Shutting down...")
    proxy_thread.join(timeout=5)
    fastapi_thread.join(timeout=5)
    logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
