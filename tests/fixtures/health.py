"""Shared health-check helper for test suites that need the live merge service.

Usage::

    from tests.fixtures.health import merge_service_required

    @merge_service_required
    class TestSomething:
        ...
"""

from __future__ import annotations

import socket

import pytest
import requests

_MERGE_SERVICE_URL = "http://localhost:7187"


def _check_service_healthy(
    url: str = _MERGE_SERVICE_URL,
    timeout: float = 3.0,
) -> bool:
    """Return True iff the service at *url* responds 200 on /health."""
    clean = url.removeprefix("http://")
    host = clean
    port = 80
    if ":" in clean:
        host, port_str = clean.split(":", 1)
        port = int(port_str)
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect((host, port))
        sock.close()
        sock = None
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
    try:
        resp = requests.get(f"{url.rstrip('/')}/health", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


merge_service_required = pytest.mark.skipif(
    not _check_service_healthy(),
    reason="Merge search service not available — start with ./start.sh -p",
)
