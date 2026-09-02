"""Version-independent oracle for a qBittorrent ``/api/v2/auth/login`` reply.

Mirrors the production predicate ``_qbit_login_succeeded`` in
``download-proxy/src/api/routes.py`` (guarded hermetically by
``tests/unit/test_qbit_login_compat.py``) so the LIVE integration tests judge a
login by the same rule the shipped code does, instead of by a literal body
string that only one qBittorrent generation ever emitted.

MEASURED REALITY (captured 2026-09-01 against the running stack,
``linuxserver/qbittorrent:latest`` → qBittorrent **v5.2.3**)::

    $ curl -i -X POST http://localhost:7185/api/v2/auth/login \
          -d 'username=admin&password=admin'
    HTTP/1.1 204 OK
    content-length: 0
    set-cookie: QBT_SID_7185=PNC5ruDrPJHgE+yo8f0AIrBf7qM8w6qC; HttpOnly; ...

    $ curl -i -X POST http://localhost:7185/api/v2/auth/login \
          -d 'username=admin&password=wrongwrong'
    HTTP/1.1 401 Unauthorized
    content-length: 12
    (no set-cookie)

    $ curl -o /dev/null -w '%{http_code}' http://localhost:7185/api/v2/app/version
    403                                   # unauthenticated
    $ curl -H 'Cookie: QBT_SID_7185=...' http://localhost:7185/api/v2/app/version
    v5.2.3                                # authenticated

So the body is EMPTY on success and the status is **204**, not ``200 "Ok."``.
Any test asserting ``resp.text == "Ok."`` asserts a falsehood about this
product and fails on a working login — a §11.4.1 FAIL-bluff (it condemns
healthy code).

The authoritative, version-independent success signal is *the server issued a
session cookie*, with the legacy ``Ok.`` body kept as a fallback so a rollback
to qBittorrent 4.x would still read as success. This is NOT a weakened
assertion: it is strictly narrower than "any 2xx", it rejects a 2xx that
carries no session cookie and no ``Ok.`` body, and it rejects a foreign
``*SID*`` cookie (``PHPSESSID``, ``BSSID``, …) that a loose substring test
would wave through.
"""

from __future__ import annotations

from typing import Any


def qbit_session_cookie_names(resp: Any) -> list[str]:
    """Names of qBittorrent session cookies the reply set.

    Only ``QBT_SID`` and ``QBT_SID_<port>`` count — matching production's exact
    /prefix test, never a loose ``"SID" in name`` substring.
    """
    # NOTE: iterate ``.keys()`` deliberately — a ``requests`` cookie jar yields
    # Cookie OBJECTS (not names) when iterated directly, so dropping ``.keys()``
    # here would silently compare a Cookie to a string and always find nothing
    # (a §11.4.201 false-null). Bound to a local so ruff's SIM118 does not
    # "simplify" it back into that bug.
    cookie_names = resp.cookies.keys()
    return [name for name in cookie_names if name == "QBT_SID" or name.startswith("QBT_SID_")]


def qbit_login_succeeded(resp: Any) -> bool:
    """True iff this ``/api/v2/auth/login`` reply represents a real login.

    Success == a 2xx status **and** (a ``QBT_SID*`` session cookie was issued
    **or** the legacy body is exactly ``Ok.``). Everything else — including a
    2xx with neither signal — is a failure.
    """
    if not (200 <= resp.status_code < 300):
        return False
    if qbit_session_cookie_names(resp):
        return True
    return resp.text.strip() == "Ok."


def describe_login(resp: Any) -> str:
    """Diagnostic string for an assertion message (never logs a credential)."""
    return (
        f"status={resp.status_code} "
        f"body={resp.text.strip()!r} "
        f"session_cookies={qbit_session_cookie_names(resp)}"
    )
