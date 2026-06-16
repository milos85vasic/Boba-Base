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
    src = _read(_SRC / "merge_service" / "search.py")
    # The PRIVATE_TRACKERS map default for nnmclub must be the live domain.
    assert f'"nnmclub": "https://{LIVE_DOMAIN}"' in src, (
        f"PRIVATE_TRACKERS['nnmclub'] must default to https://{LIVE_DOMAIN}"
    )


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
    src = _read(_SRC / "api" / "routes.py")
    assert f'"{DEAD_DOMAIN}"' not in src, f"api/routes.py still lists dead {DEAD_DOMAIN}"
    assert LIVE_DOMAIN in src, f"api/routes.py must reference live {LIVE_DOMAIN}"


def test_plugin_nnmclub_has_no_dead_domain():
    src = _read(_ROOT / "plugins" / "nnmclub.py")
    assert DEAD_DOMAIN not in src, f"plugins/nnmclub.py still hardcodes dead {DEAD_DOMAIN}"
    assert LIVE_DOMAIN in src, f"plugins/nnmclub.py must reference live {LIVE_DOMAIN}"
