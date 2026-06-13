"""§11.4.135 regression guard — qBittorrent modern-204 login compatibility.

The live :7187 round-trip surfaced a real product defect: the download proxy
reported ``status='auth_failed'`` for every download because its login-success
check required ``resp.status == 200 and body == 'Ok.'``. Modern qBittorrent
(``linuxserver/qbittorrent:latest``, 5.x) returns ``204 No Content`` with an
EMPTY body plus the ``QBT_SID`` session cookie — so the old check rejected a
SUCCESSFUL login. Captured live evidence (2026-06-13):

    HTTP/1.1 204 OK
    set-cookie: QBT_SID_7185=...; HttpOnly; SameSite=Lax; path=/

``_qbit_login_succeeded`` keys off the issued session cookie (the authoritative,
version-independent success signal), with the legacy ``Ok.`` body as fallback.
"""

import os
import sys
from http.cookies import SimpleCookie

_src = os.path.join(os.path.dirname(__file__), "..", "..", "download-proxy", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from api.routes import _qbit_add_succeeded, _qbit_login_succeeded


def _cookies(*names):
    jar = SimpleCookie()
    for n in names:
        jar[n] = "deadbeefdeadbeef"
    return jar


def test_modern_204_with_sid_cookie_is_success():
    # The exact captured behaviour of linuxserver/qbittorrent:latest (5.x).
    assert _qbit_login_succeeded(204, "", _cookies("QBT_SID_7185")) is True


def test_legacy_200_ok_body_is_success():
    assert _qbit_login_succeeded(200, "Ok.", _cookies()) is True


def test_legacy_200_ok_with_cookie_is_success():
    assert _qbit_login_succeeded(200, "Ok.", _cookies("QBT_SID_7185")) is True


def test_failed_login_200_fails_no_cookie_is_failure():
    # qBittorrent rejects a bad password with 200 "Fails." and no cookie.
    assert _qbit_login_succeeded(200, "Fails.", _cookies()) is False


def test_204_without_any_cookie_is_failure():
    # 204 alone is not proof — without a session cookie we are not authenticated.
    assert _qbit_login_succeeded(204, "", _cookies()) is False


def test_401_with_cookie_is_failure():
    # A non-2xx status is never a success even if some cookie tags along.
    assert _qbit_login_succeeded(401, "", _cookies("QBT_SID_7185")) is False


def test_403_is_failure():
    assert _qbit_login_succeeded(403, "Forbidden", _cookies()) is False


def test_reproduces_pre_fix_defect_old_check_rejected_modern_204():
    """§11.4.115 polarity: the OLD inline predicate mis-classified the modern
    204 as auth_failed; the new helper accepts it. Proves this guard catches
    the exact defect (not a tautology agreeing with the fix)."""
    status, body, cookies = 204, "", _cookies("QBT_SID_7185")
    # The pre-fix inline check, verbatim, as it lived in routes.py:
    old_check_reports_auth_failed = status != 200 or body.strip() != "Ok."
    assert old_check_reports_auth_failed is True  # the defect: rejected a real login
    assert _qbit_login_succeeded(status, body, cookies) is True  # the fix: accepts it


# --- /api/v2/torrents/add success detection (the second modern-qBittorrent defect) ---

_MODERN_ADD_OK = (
    '{"added_torrent_ids":["a808a213d51f19888adba014778fb7088396e8e5"],'
    '"failure_count":0,"pending_count":0,"success_count":1}'
)


def test_modern_json_add_success_is_added():
    # Exact captured body of linuxserver/qbittorrent:latest (5.x) on add.
    assert _qbit_add_succeeded(200, _MODERN_ADD_OK) is True


def test_modern_json_add_pending_only_is_added():
    # A magnet whose metadata is still resolving is still ACCEPTED.
    body = '{"added_torrent_ids":[],"failure_count":0,"pending_count":1,"success_count":0}'
    assert _qbit_add_succeeded(200, body) is True


def test_modern_json_add_all_failed_is_failure():
    body = '{"added_torrent_ids":[],"failure_count":1,"pending_count":0,"success_count":0}'
    assert _qbit_add_succeeded(200, body) is False


def test_legacy_ok_add_is_added():
    assert _qbit_add_succeeded(200, "Ok.") is True


def test_legacy_fails_add_is_failure():
    assert _qbit_add_succeeded(200, "Fails.") is False


def test_add_409_conflict_duplicate_is_success_idempotent():
    # qBittorrent returns 409 "Conflict" for a torrent already in the session.
    # The torrent IS present (the user's goal) — so a duplicate add is success,
    # making a client retry of the non-idempotent POST safe. Captured live:
    # attempt 1 added the magnet, BobaClient timed out + retried, attempt 2 → 409.
    assert _qbit_add_succeeded(409, "Conflict") is True


def test_add_other_non_2xx_is_failure():
    # 415 (invalid/unsupported torrent), 400, etc. are genuine failures.
    assert _qbit_add_succeeded(415, "") is False
    assert _qbit_add_succeeded(400, "Bad Request") is False


def test_add_garbage_body_is_failure():
    assert _qbit_add_succeeded(200, "<html>not json</html>") is False


def test_add_non_numeric_count_is_failure_not_crash():
    # A malformed JSON body with non-numeric count fields must classify as
    # failure, NEVER raise (``int("N/A")`` would crash the live add path).
    body = '{"added_torrent_ids":[],"success_count":"N/A","pending_count":"?"}'
    assert _qbit_add_succeeded(200, body) is False


def test_login_foreign_sid_cookie_is_not_accepted():
    # A loose ``"SID" in key`` substring test would treat a foreign *SID* cookie
    # (PHPSESSID, BSSID, …) as a successful login. Only QBT_SID(_<port>) counts.
    assert _qbit_login_succeeded(204, "", _cookies("PHPSESSID")) is False
    assert _qbit_login_succeeded(204, "", _cookies("BSSID")) is False
    assert _qbit_login_succeeded(200, "", _cookies("QBT_SID")) is True


def test_reproduces_pre_fix_defect_old_check_rejected_modern_json_add():
    """§11.4.115 polarity: the OLD inline check (``body.lower().startswith('ok')``)
    rejected the modern JSON success even though the torrent landed; the new
    helper accepts it. Not a tautology."""
    status, body = 200, _MODERN_ADD_OK
    old_check_reports_added = status in (200, 201) and body.lower().startswith("ok")
    assert old_check_reports_added is False  # the defect: real success seen as failed
    assert _qbit_add_succeeded(status, body) is True  # the fix: accepts it
