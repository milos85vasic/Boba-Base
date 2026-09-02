"""Shared health-check helper for test suites that need the live merge service.

Usage::

    from tests.fixtures.health import merge_service_required

    @merge_service_required
    class TestSomething:
        ...
"""

from __future__ import annotations

import socket
import warnings

import pytest
import requests

_MERGE_SERVICE_URL = "http://localhost:7187"


class ProbeBrokenWarning(UserWarning):
    """The health PROBE failed — this says nothing about the service.

    Raised as a warning (never an error) so a broken probe is impossible to
    miss in pytest's warnings summary while still leaving the suite runnable.
    """


def _check_service_healthy(
    url: str = _MERGE_SERVICE_URL,
    timeout: float = 3.0,
) -> bool:
    """Return True iff the service at *url* responds 200 on /health.

    A ``False`` from this function gates whole suites into SKIP, so the two ways
    of reaching ``False`` must not be conflated (§11.4.201(6) — the false-null):

    * **The service is down.** Legitimate. Returns ``False`` silently; a
      developer with the stack down gets a clean, honest skip and no noise.
      Refusing or shouting here would be the §11.4.201(1) false-positive
      refusal — the failure mode this fix must NOT introduce.
    * **The probe itself is broken** (a bad URL constant, a TypeError from a
      changed ``requests`` signature, an AttributeError after a refactor). NOT
      legitimate: the suite silently stops running and reports the same green
      as a suite that had nothing to run. That case now emits a loud
      ``ProbeBrokenWarning`` naming the exception, and still returns ``False``
      so the session stays usable rather than collapsing at collection time.

    Only the enumerated network-down exceptions are treated as "service down".
    Everything else is a probe defect by construction — the closed set is the
    discriminator, not a catch-all ``except Exception``.
    """
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
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.TooManyRedirects,
        requests.exceptions.ChunkedEncodingError,
        requests.exceptions.ContentDecodingError,
    ):
        # SERVICE DOWN / unreachable — the legitimate skip. Stay quiet.
        return False
    except Exception as exc:  # noqa: BLE001 - deliberately broad; see below
        # PROBE BROKEN. The TCP pre-check above already proved something is
        # listening on this host:port, so an exception here is not the service
        # being absent — it is this probe failing to ask the question. Reporting
        # it as a plain skip is the exact bluff this guard exists to prevent.
        warnings.warn(
            f"HEALTH PROBE BROKEN for {url} — {type(exc).__name__}: {exc}. "
            "A TCP connection to this host:port SUCCEEDED, so the service is "
            "reachable; the probe itself failed. Suites gated on this fixture "
            "are being SKIPPED for a reason that is NOT 'the service is down'. "
            "Fix the probe — do not read the skip as coverage.",
            ProbeBrokenWarning,
            stacklevel=2,
        )
        return False


merge_service_required = pytest.mark.skipif(
    not _check_service_healthy(),
    reason="Merge search service not available — start with ./start.sh -p",
)
