"""The ONE predicate for "did qBittorrent really accept this torrents/add?".

WHY THIS MODULE EXISTS (§11.4.251 — measured 2026-09-01)
--------------------------------------------------------
``_qbit_add_succeeded`` had TWO implementations — ``api/routes.py`` and
``webui-bridge.py`` — and they drifted until they recorded OPPOSITE verdicts
for the same status code: ``routes.py`` read ``409`` as SUCCESS (a duplicate
add), the bridge read it as FAILURE (a malformed request). Three separate
review findings traced back to that single duplication, and each was
"fixed" on one side while the other stayed wrong, because a mutation of
either copy left the other's tests green.

The bridge's 409-as-failure clause was argued from a claim that a duplicate
add returns ``200`` with a success summary. That claim is FALSE and was
re-measured 2/2 against qBittorrent v5.2.3 / WebAPI 2.15.1: a duplicate add
returns ``409``. The divergence is therefore removed, not preserved.

MEASURED CONTRACT (qBittorrent v5.2.3 / WebAPI 2.15.1, 2026-09-01)
------------------------------------------------------------------
=========================  ==========================  =====================
case                       response                    meaning
=========================  ==========================  =====================
valid file add             ``200 {"success_count":1}`` added
``.torrent`` URL add       ``202 {"pending_count":1}`` added, fetching async
magnet add                 ``200 {"success_count":1}`` added
duplicate add              ``409 Conflict``            already present (OK)
**no payload sent**        ``409 Conflict``            **nothing added (FAIL)**
corrupt/truncated/empty    ``415``                     rejected
=========================  ==========================  =====================

THE 409 AMBIGUITY IS LOAD-BEARING, AND THE STATUS ALONE CANNOT RESOLVE IT
--------------------------------------------------------------------------
The same ``409`` means success or failure depending on whether the request
carried a payload — information this function does not receive and cannot
recover from the response. ``409`` is read as SUCCESS here, which is correct
ONLY while every caller genuinely attaches a payload. That is an INVARIANT
this module depends on and does not itself enforce; it is enforced upstream,
at each caller's entry point:

* ``api/routes.py`` — ``DownloadRequest.download_urls`` has a
  ``field_validator`` (``_reject_empty_urls``) that strips empty/whitespace
  URLs and raises when nothing survives. Before it existed, ``{"download_urls":
  [""]}`` reached qBittorrent as ``urls=""``, drew the no-payload ``409``, and
  this predicate reported ``{"status":"added"}`` for a torrent that never
  existed — a live-proven PASS-bluff on the primary download path.
* ``webui-bridge.py`` — ``upload_to_qbittorrent`` reads the ``.torrent`` file
  from disk and always writes a ``torrents`` multipart part, so it structurally
  cannot emit a no-payload add. (An EMPTY file is still a payload part, and
  this build answers it ``415``, not ``409``.)

**The warning stands** (§11.4.6): a FUTURE caller able to emit an empty add,
added anywhere that does not pass through one of the two enforcement points
above, would silently read failure as success. The validator closed the one
known such caller; it did not make the predicate self-sufficient. Any new
call site MUST guarantee a payload, or must not use this function.

DEPENDENCIES: standard library only — ``webui-bridge.py`` is a host process
whose entire dependency set is the stdlib. Never add a third-party import.
"""

from __future__ import annotations

import json

__all__ = ["qbit_add_succeeded"]


def qbit_add_succeeded(status: int, body: str) -> bool:
    """Return ``True`` only when qBittorrent really accepted the add.

    Args:
        status: HTTP status of the ``/api/v2/torrents/add`` response.
        body: the response body, decoded as text (may be empty).

    Cross-version body handling: legacy qBittorrent (<5.x) answers ``200`` with
    ``Ok.`` (``Fails.`` on rejection); modern qBittorrent (5.x) answers with a
    JSON summary. The torrent landed when ``added_torrent_ids`` is non-empty,
    or ``success_count`` / ``pending_count`` is >= 1 — ``pending_count`` covers
    a magnet or ``.torrent`` URL whose metadata is still resolving; it IS
    accepted into the session.

    A ``2xx`` with an unparseable, non-``Ok.`` body is NOT evidence the torrent
    landed and returns ``False`` — defaulting to ``True`` there is precisely
    the bluff this predicate exists to remove.
    """
    if status == 409:
        # Duplicate add -> already present -> success from the user's view (and
        # what makes a client retry of this non-idempotent POST safe). Correct
        # ONLY under the payload invariant documented in this module's
        # docstring; see the enforcement points named there.
        return True
    # 202 is the measured shape of an accepted-but-still-resolving URL add.
    # Excluding it made every successful non-tracker URL add report
    # "failed"/"added_count":0 while the download was already running. The BODY
    # still decides below — a 202 carrying zero counts is still a failure.
    if status not in (200, 201, 202):
        return False
    text = (body or "").strip()
    if text.lower().startswith("ok"):
        return True
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("added_torrent_ids"):
        return True
    # Coerce defensively — a malformed body like ``{"success_count":"N/A"}``
    # must classify as failure, never raise (``int("N/A")`` would crash the
    # add path).
    try:
        success = int(payload.get("success_count") or 0)
        pending = int(payload.get("pending_count") or 0)
    except (ValueError, TypeError):
        return False
    return success >= 1 or pending >= 1
