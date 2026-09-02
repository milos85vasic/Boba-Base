"""The ONE roster of authenticated (private) tracker domains.

WHY THIS MODULE EXISTS (§11.4.251 — measured 2026-09-01)
--------------------------------------------------------
The set of domains that mean "this URL belongs to a private tracker and MUST
be fetched with credentials" was re-typed at FOUR independent sites, and all
four had already drifted apart:

===================  ======  ==============  =====================  ==========
domain               bridge  TRACKER_DOMAINS PLUGIN_PATTERNS        search.py
                             (api/routes.py) (plugins/download_...) (base URL)
===================  ======  ==============  =====================  ==========
rutracker.org        yes     yes             yes                    primary
rutracker.net        yes     **no**          yes                    -
rutracker.nl         yes     yes             yes                    -
kinozal.tv           yes     yes             yes                    primary
kinozal.me           **no**  **no**          yes                    -
kinozal.guru         **no**  yes             **no**                 -
nnmclub.to           yes     yes             yes                    primary
nnmclub.ro           yes     yes             **no**                 -
nnm-club.me          yes     **no**          yes                    -
iptorrents.com       yes     yes             yes                    primary
iptorrents.me        yes     yes             yes                    -
iptorrents.org       **no**  **no**          yes                    -
===================  ======  ==============  =====================  ==========

That drift is not cosmetic — it CORRUPTS DOWNLOADS. ``api/routes.py``'s
``download_torrent_file`` (merge service, :7187) routes a URL the roster
recognises through the AUTHENTICATED ``fetch_torrent`` path, and everything
else through a plain unauthenticated ``session.get``. A private-tracker URL
whose domain is missing from THAT roster therefore takes the anonymous path,
the tracker answers with an HTML login page (or a 401 body), and that body is
streamed back to the user as ``<tracker>_<id>.torrent``. The user gets a
corrupt torrent and no error. ``nnm-club.me`` was in exactly that state: the
bridge auth-routed it, the merge service did not.

This module is the single checked-in roster. Every consumer imports it; none
re-types it.

PRIMARY vs ALIAS (§11.4.111 — resolve by a stable name, and keep the LIVE one)
------------------------------------------------------------------------------
Each tracker's tuple is ordered ``(primary, *aliases)``:

* the **primary** is the canonical, VERIFIED-LIVE host. It is what
  :data:`PRIVATE_TRACKER_BASE_URLS` derives the default base URL from, so it
  is the domain the code actually TALKS TO by default.
* the **aliases** are additional hosts that must still be RECOGNISED as
  belonging to that tracker — mirrors, historical domains, and domains a
  stored search result or an operator paste may still carry.

The distinction is load-bearing. ``nnm-club.me`` is a *dead* domain (NXDOMAIN,
measured 2026-06-16 — see ``tests/unit/merge_service/test_nnmclub_domain_live.py``)
and MUST NEVER be a primary: defaulting to it broke nnmclub login outright.
But recognising it is strictly better than not: a recognised dead domain fails
CLEANLY through the authenticated path ("could not fetch torrent file from
tracker"), whereas an unrecognised one falls through to the anonymous fetch
that saves a login page as a ``.torrent``.

TWO MATCHERS, ONE ROSTER
------------------------
The consumers legitimately differ in HOW they match — that difference is
preserved deliberately, and is documented at each call site:

* :func:`identify_tracker` matches the URL's **host** (exact or subdomain).
  This is what the merge-service API uses: it decides whether to spend
  credentials on a fetch, so it must not be fooled by a tracker name appearing
  in a query string.
* :func:`identify_tracker_in_text` matches the domain **anywhere** in the URL
  text, case-insensitively. This is the historical behaviour of the
  WebUI bridge and of the in-container ``download_proxy`` engine, both of
  which intercept a WebUI "add by URL" whose payload can legitimately embed a
  tracker address in a parameter. Over-matching there is the safe direction
  (it routes through authentication); under-matching is the defect above.

Only the ROSTER was ever duplicated. The matchers are two named functions in
this file, not two copies of a list.

DEPENDENCIES: standard library only, and deliberately so — ``webui-bridge.py``
is a host process whose entire dependency set is the stdlib, and
``plugins/download_proxy.py`` is staged into the qBittorrent container. Never
add a third-party import here.
"""

from __future__ import annotations

from urllib.parse import urlparse

__all__ = [
    "PRIVATE_TRACKER_BASE_URLS",
    "PRIVATE_TRACKER_DOMAINS",
    "TRACKER_DOMAINS",
    "identify_tracker",
    "identify_tracker_in_text",
]


#: tracker name -> ``(primary, *aliases)``. The name is the qBittorrent nova3
#: plugin name (``plugins/<name>.py``) AND the merge-service tracker key, so
#: one roster serves the search orchestrator, the API router, the bridge and
#: the in-container proxy engine without a translation table.
PRIVATE_TRACKER_DOMAINS: dict[str, tuple[str, ...]] = {
    "rutracker": ("rutracker.org", "rutracker.net", "rutracker.nl"),
    "kinozal": ("kinozal.tv", "kinozal.me", "kinozal.guru"),
    # nnm-club.me is an ALIAS ONLY — dead since 2026-06-16, never a primary.
    "nnmclub": ("nnmclub.to", "nnmclub.ro", "nnm-club.me"),
    "iptorrents": ("iptorrents.com", "iptorrents.me", "iptorrents.org"),
}

#: Flat tuple of every authenticated tracker domain, in roster order — DERIVED,
#: never hand-maintained. (No de-duplication is applied because a domain
#: belonging to two trackers would be a roster defect, not something to hide;
#: ``identify_tracker`` would silently pick the first, so the roster must not
#: contain one.)
TRACKER_DOMAINS: tuple[str, ...] = tuple(
    domain for domains in PRIVATE_TRACKER_DOMAINS.values() for domain in domains
)

#: tracker name -> default base URL, derived from the PRIMARY domain. Callers
#: that support mirrors (``*_MIRRORS`` env vars) override this at runtime; this
#: is the built-in default, and it is live by construction.
PRIVATE_TRACKER_BASE_URLS: dict[str, str] = {
    name: f"https://{domains[0]}" for name, domains in PRIVATE_TRACKER_DOMAINS.items()
}


def identify_tracker(url: str) -> str | None:
    """Return the tracker name whose domain owns ``url``'s HOST, else ``None``.

    Matches the parsed hostname exactly, or as a subdomain of a roster domain
    (``dl.kinozal.tv`` -> ``kinozal``). A tracker domain that appears only in
    the path or query string does NOT match — use
    :func:`identify_tracker_in_text` where that is the intent.

    Never raises: an unparseable / empty / non-HTTP URL yields ``None``.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except (ValueError, AttributeError):
        return None
    if not host:
        return None
    for name, domains in PRIVATE_TRACKER_DOMAINS.items():
        for domain in domains:
            if host == domain or host.endswith("." + domain):
                return name
    return None


def identify_tracker_in_text(url: str) -> str | None:
    """Return the tracker name whose domain appears ANYWHERE in ``url``.

    Case-insensitive substring match over the whole URL string — the historical
    behaviour of the WebUI bridge and of the in-container proxy engine, both of
    which see WebUI "add by URL" payloads that can carry a tracker address in a
    parameter (``.../redirect?to=rutracker.org``). Deliberately more permissive
    than :func:`identify_tracker`; over-matching routes through authentication,
    which is the safe direction.

    Never raises: ``None`` / empty input yields ``None``.
    """
    if not url:
        return None
    lowered = str(url).lower()
    for name, domains in PRIVATE_TRACKER_DOMAINS.items():
        for domain in domains:
            if domain in lowered:
                return name
    return None
