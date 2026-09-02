"""Fixture wiring for the security suite.

Exists for ONE reason: to make :func:`tests.fixtures.services.merge_service_client`
requestable by name from the live-service security tests, the same way
``tests/conftest.py`` re-exports the other live fixtures.

WHY HERE AND NOT IN ``tests/conftest.py``: this is a suite-local concern.
The rate-limit-aware client is the correct gate for the security suite's
live HTTP (see the BOB-152 block in ``tests/fixtures/services.py``), and
nothing outside ``tests/security/**`` needs it today. Adding it to the
root conftest would widen a suite-local mechanism into a project-wide one
before any second consumer exists.

The import is the wiring — pytest collects fixtures from every name bound
in a conftest module, so re-exporting is sufficient and no shim fixture is
needed (a shim would add a second, drift-capable definition of the same
gate, which is the §11.4.251 duplicate this file exists to avoid).
"""

from __future__ import annotations

from tests.fixtures.services import merge_service_client  # noqa: F401

__all__ = ["merge_service_client"]
