"""API-token plumbing for integration tests that hit the live merge service (BOB-234).

The merge service's mutating routes (hooks, magnet, download, schedules, theme)
are gated by ``download-proxy/src/api/routes.py::require_api_token``: when the
service runs with ``BOBA_API_TOKEN`` set (BOB-197 mandatory-auth guard), a
request must carry the matching token in ``Authorization: Bearer <token>`` or
``X-Boba-Token: <token>``, else it gets 401.

This module:

* resolves the token from the environment first, then the repo ``.env``;
* provides :class:`MergeTokenSession`, a ``requests.Session`` that adds
  ``X-Boba-Token`` ONLY to requests aimed at the merge-service base URL (never
  implicitly to any other host);
* provides :func:`assert_token_usable`, which probes the live service once and
  FAILS loudly (never skips) when the service demands a token that is absent
  or rejected;
* provides :func:`qbit_delete_confirmed`, the authenticated + verified test
  torrent cleanup through the :7186 download-proxy (which gates deletes with
  the same token and strips the header before forwarding to qBittorrent).

§11.4.10: the token value is never printed, logged, or put in any message. Only
its SOURCE (``"environment"`` or the ``.env`` path) is ever reported.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import requests

TOKEN_VAR = "BOBA_API_TOKEN"
TOKEN_HEADER = "X-Boba-Token"
REPO_DOTENV = Path(__file__).resolve().parents[2] / ".env"


def _read_dotenv_value(path: Path, key: str) -> str:
    """Return the LAST assignment of ``key`` in a dotenv file ('' if absent).

    Handles ``export KEY=...``, surrounding single/double quotes, blank lines
    and ``#`` comment lines. Values are never logged.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return ""
    value = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, sep, rest = line.partition("=")
        if not sep or name.strip() != key:
            continue
        rest = rest.strip()
        if len(rest) >= 2 and rest[0] == rest[-1] and rest[0] in ("'", '"'):
            rest = rest[1:-1]
        value = rest.strip()
    return value


def resolve_api_token(
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> tuple[str, str]:
    """Return ``(token, source)``; ``("", "")`` when no token is available.

    Priority mirrors the project convention (shell env -> ./.env): a non-blank
    ``BOBA_API_TOKEN`` in the environment wins, otherwise the repo ``.env``.
    """
    env = os.environ if environ is None else environ
    from_env = (env.get(TOKEN_VAR) or "").strip()
    if from_env:
        return from_env, "environment"
    path = REPO_DOTENV if dotenv_path is None else Path(dotenv_path)
    from_file = _read_dotenv_value(path, TOKEN_VAR)
    if from_file:
        return from_file, str(path)
    return "", ""


class MergeTokenSession(requests.Session):
    """``requests.Session`` that sends the API token to the merge service only.

    The token is attached per request (not via ``session.headers``) and only
    when the request URL's scheme+host+port equals the merge base URL's, so a
    shared session can also talk to the qBittorrent proxy without leaking it.
    """

    def __init__(self, base_url: str, token: str) -> None:
        super().__init__()
        parts = urlsplit(base_url)
        self._origin = (parts.scheme.lower(), (parts.hostname or "").lower(), parts.port)
        self._token = token

    def _targets_merge(self, url: str) -> bool:
        parts = urlsplit(url)
        return (parts.scheme.lower(), (parts.hostname or "").lower(), parts.port) == self._origin

    def request(self, method: str | bytes, url: str | bytes, *args: Any, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        target = url.decode() if isinstance(url, bytes) else url
        if self._token and self._targets_merge(target):
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault(TOKEN_HEADER, self._token)
            kwargs["headers"] = headers
        return super().request(method, url, *args, **kwargs)


def assert_token_usable(base_url: str, token: str, source: str) -> None:
    """Probe the live merge service and FAIL loudly if auth cannot work.

    Probes ``POST /api/v1/magnet`` (a token-gated, side-effect-free route) with
    an invalid body: 401 means the token gate rejected the request; any other
    status (400 for the bad body) means the gate let it through.

    * armed + no token available -> ``pytest.fail`` (never skip);
    * token available but rejected -> ``pytest.fail``;
    * open (unarmed) service + no token -> fine, nothing to send.
    """
    probe_url = f"{base_url.rstrip('/')}/api/v1/magnet"
    headers = {TOKEN_HEADER: token} if token else {}
    resp = requests.post(probe_url, data="bob234-auth-probe", headers=headers, timeout=15)
    if resp.status_code != 401:
        return
    if not token:
        pytest.fail(
            f"merge service at {base_url} demands an API token (POST /api/v1/magnet -> HTTP 401) "
            f"but no {TOKEN_VAR} is available: set it in the environment or in {REPO_DOTENV} "
            "(BOB-234). Refusing to skip -- the token-gated tests would otherwise be unverifiable."
        )
    pytest.fail(
        f"merge service at {base_url} rejected the {TOKEN_VAR} taken from {source} "
        "(POST /api/v1/magnet -> HTTP 401): the test token does not match the one the running "
        "service was started with (BOB-234). Value not shown (§11.4.10)."
    )


def qbit_snapshot_hashes(session: requests.Session, qbit_url: str, token: str):
    """Hashes currently in qBittorrent, or ``None`` when the list is unreadable.

    ``None`` DISARMS every later delete (CM-NO-UNSCOPED-LIVE-DESTRUCTION): a
    test that cannot prove what was already there must not remove anything.
    """
    headers = {TOKEN_HEADER: token} if token else {}
    try:
        resp = session.get(f"{qbit_url}/api/v2/torrents/info", headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        return {str(r.get("hash", "")).lower() for r in resp.json()}
    except (requests.RequestException, ValueError):
        return None


def qbit_delete_confirmed(
    session: requests.Session,
    qbit_url: str,
    infohash: str,
    token: str,
    before,
    timeout: float = 15.0,
) -> None:
    """Delete ONLY the torrent this test added and PROVE it is gone.

    ``before`` is the :func:`qbit_snapshot_hashes` taken BEFORE the test added
    anything. The delete is scoped by a set difference against it
    (``added = after - before``): a hash that was already present is an
    operator's torrent and is never touched, and an unreadable baseline
    (``None``) disarms the delete entirely.

    The proxy gates ``/api/v2/torrents/delete`` with the same ``BOBA_API_TOKEN``
    (``plugins/download_proxy.py``; it strips ``X-Boba-Token`` before forwarding
    to qBittorrent, BOB-203), so an unauthenticated cleanup gets 401 and — when
    its response is not checked — silently leaves the torrent behind (observed
    live 2026-09-23 while fixing BOB-234). This helper sends the token, asserts
    the delete was accepted, and polls until the hash is absent; anything else
    FAILS (§11.4.14 quiescent-target mandate).
    """
    import time

    h = infohash.lower()
    if before is None:
        return  # baseline unreadable -> delete disarmed
    after = qbit_snapshot_hashes(session, qbit_url, token)
    if after is None:
        return
    added = after - before
    if h not in added:
        return  # not added by this test (absent, or pre-existing) -> never delete
    headers = {TOKEN_HEADER: token} if token else {}
    resp = session.post(
        f"{qbit_url}/api/v2/torrents/delete",
        data={"hashes": h, "deleteFiles": "true"},
        headers=headers,
        timeout=15,
    )
    if resp.status_code != 200:
        pytest.fail(
            f"cleanup of test torrent {h} was REFUSED by {qbit_url}: HTTP {resp.status_code} "
            "(the torrent is left behind in qBittorrent; token value not shown, §11.4.10)"
        )
    deadline = time.monotonic() + timeout
    while True:
        now = qbit_snapshot_hashes(session, qbit_url, token)
        if now is not None and h not in now:
            return
        if time.monotonic() >= deadline:
            pytest.fail(f"test torrent {h} is still present in qBittorrent {timeout}s after an accepted delete")
        time.sleep(0.5)
