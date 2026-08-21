"""Ownership tests for feature 002-user-owned-downloads.

Deliberately NOT under tests/integration/: that package's conftest installs an
autouse fixture that waits for the live merge service to report idle, so every
test there requires the full stack to be UP. These tests need only a container
RUNTIME — no stack, no services. Placing them under tests/integration/ made
them error after a 60s hang whenever the stack was down, which is a dependency
they do not actually have.
"""
