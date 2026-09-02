"""§11.4.111 / §11.4.99 — NNM-Club base-domain must resolve / be live.

RED-first regression guard for the DNS NXDOMAIN defect: the integration
hardcoded ``nnm-club.me`` which no longer resolves (NXDOMAIN from the
podman VM), so nnmclub login + search died with
``Cannot connect to host nnm-club.me:443 [Name does not resolve]``.

The verified live domain (§11.4.99 verify-before-changing-a-credential
-target, confirmed 2026-06-16 by VM probe: HTTP/2 200, title
``Торрент-трекер :: NNM-Club``, real ``login.php`` form + ``tracker.php``)
is ``nnmclub.to`` — which also matches the BobaLink extension content
match ``*://*.nnmclub.to/*``.

These tests assert every nnmclub default base URL is the verified live
domain and is NOT the dead ``nnm-club.me``. They scan the SOURCE files
directly (no module import — the proxy targets Python 3.12 while the test
host may be older, so an import-time syntax artifact must not mask the
real product assertion, per §11.4.1). They FAIL against the pre-fix
source (RED) and pass once the hardcoded domain is replaced (GREEN).
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "download-proxy" / "src"

# The dead domain that broke the integration — must never be a default again.
DEAD_DOMAIN = "nnm-club.me"
# The verified live domain (VM-probed + extension content-match cross-ref).
LIVE_DOMAIN = "nnmclub.to"


def _read(rel: Path) -> str:
    return rel.read_text(encoding="utf-8")


def test_search_module_has_no_dead_domain():
    src = _read(_SRC / "merge_service" / "search.py")
    assert DEAD_DOMAIN not in src, f"search.py still hardcodes dead {DEAD_DOMAIN}"
    assert f"https://{LIVE_DOMAIN}" in src, f"search.py must reference live {LIVE_DOMAIN}"


def test_search_private_trackers_default_is_live():
    """The nnmclub DEFAULT base URL is the live domain.

    RECONCILED 2026-09-01 (§11.4.120 — the fix broke this gate's precondition,
    so the gate is rewritten to assert the NEW mechanism rather than fake-passed
    or reverted). The literal ``"nnmclub": "https://nnmclub.to"`` no longer
    exists in ``search.py``: ``PRIVATE_TRACKERS`` is now DERIVED from the one
    roster in ``merge_service/trackers.py``, whose per-tracker tuple is ordered
    ``(primary, *aliases)`` and whose primary IS the default base URL.

    So the assertion moves to where the value now lives, and it is checked on
    the RESOLVED value (not a source substring), which is strictly stronger:
    a derivation that silently picked an alias would pass a text scan of
    ``search.py`` and fail here.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "trackers_dead_domain_probe", str(_SRC / "merge_service" / "trackers.py")
    )
    trackers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trackers)

    primary = trackers.PRIVATE_TRACKER_DOMAINS["nnmclub"][0]
    assert primary == LIVE_DOMAIN, f"nnmclub PRIMARY domain must be {LIVE_DOMAIN}, got {primary}"
    assert primary != DEAD_DOMAIN
    assert trackers.PRIVATE_TRACKER_BASE_URLS["nnmclub"] == f"https://{LIVE_DOMAIN}"

    # NOTE (deliberate, not an oversight): the dead domain MAY appear in the
    # roster as a recognition ALIAS. Recognising it routes the URL through
    # AUTHENTICATION, where it fails cleanly ("could not fetch torrent file
    # from tracker"), instead of through the anonymous fetch that saves a login
    # page as a ``.torrent``. What this test forbids is the dead domain being
    # the PRIMARY — i.e. a default the code actually talks to — which is what
    # the three assertions above pin, and what the original defect was.

    # And the derived map in search.py really is the roster's (no second copy).
    import sys

    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from merge_service.search import PRIVATE_TRACKERS

    assert PRIVATE_TRACKERS["nnmclub"] == f"https://{LIVE_DOMAIN}"


def test_search_nnmclub_mirrors_default_is_live():
    src = _read(_SRC / "merge_service" / "search.py")
    assert f'"NNMCLUB_MIRRORS", "https://{DEAD_DOMAIN}"' not in src, (
        f"_search_nnmclub still defaults NNMCLUB_MIRRORS to dead {DEAD_DOMAIN}"
    )
    assert f'"NNMCLUB_MIRRORS", "https://{LIVE_DOMAIN}"' in src, (
        f"_search_nnmclub must default NNMCLUB_MIRRORS to https://{LIVE_DOMAIN}"
    )


def test_auth_module_has_no_dead_domain():
    src = _read(_SRC / "api" / "auth.py")
    assert f'"https://{DEAD_DOMAIN}"' not in src, (
        f"api/auth.py still hardcodes dead {DEAD_DOMAIN}"
    )
    assert LIVE_DOMAIN in src, f"api/auth.py must reference live {LIVE_DOMAIN}"


def test_routes_module_has_no_dead_domain():
    """The API router recognises the LIVE nnmclub domain.

    RECONCILED 2026-09-01 (§11.4.120). ``api/routes.py`` no longer types ANY
    tracker domain — its ``TRACKER_DOMAINS`` is re-exported from the one roster
    — so a source-text scan of that file can no longer see this property and
    would have become a §11.4.201 false-null (a clean zero from a blind
    instrument). The check therefore moves to the RESOLVED value the router
    actually routes on, which is what the property was always about.
    """
    src = _read(_SRC / "api" / "routes.py")
    assert f'"{DEAD_DOMAIN}"' not in src, f"api/routes.py still lists dead {DEAD_DOMAIN}"

    import sys

    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    from api.routes import TRACKER_DOMAINS, _is_tracker_url

    assert LIVE_DOMAIN in TRACKER_DOMAINS, f"api/routes.py must recognise live {LIVE_DOMAIN}"
    assert _is_tracker_url(f"https://{LIVE_DOMAIN}/forum/viewtopic.php?t=1") == "nnmclub"


def test_plugin_nnmclub_has_no_dead_domain():
    src = _read(_ROOT / "plugins" / "nnmclub.py")
    assert DEAD_DOMAIN not in src, f"plugins/nnmclub.py still hardcodes dead {DEAD_DOMAIN}"
    assert LIVE_DOMAIN in src, f"plugins/nnmclub.py must reference live {LIVE_DOMAIN}"
