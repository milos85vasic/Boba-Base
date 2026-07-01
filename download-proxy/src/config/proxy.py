"""Configurable outbound proxy for tracker-bound egress (download-proxy).

The Boba stack may run from an egress IP that some upstream trackers block at
the network layer (DNS failure / TLS interception). To let the operator route
tracker-bound calls around the block with a residential / VPN / SOCKS egress,
this module reads a single knob and applies it to the tracker-bound HTTP
clients only.

Knob (precedence):

1. ``BOBA_UPSTREAM_PROXY`` — ``socks5://host:1080`` | ``http://host:8080`` |
   ``https://host:8080``.
2. fallback to the standard ``ALL_PROXY`` / ``HTTPS_PROXY`` / ``HTTP_PROXY``
   environment variables when ``BOBA_UPSTREAM_PROXY`` is unset.

Loopback / sidecar bypass: the internal sidecars (qBittorrent, Jackett,
FlareSolverr) are reached at ``127.0.0.1`` / ``localhost`` or by their service
name (``qbittorrent`` / ``jackett``). Those hosts are NEVER routed through the
upstream proxy — an external proxy cannot reach the operator's loopback, and a
sidecar call must stay direct. ``NO_PROXY`` ALWAYS contains the default bypass
hosts (merged with any operator-supplied ``NO_PROXY``).

How it is applied:

* ``apply_proxy_env()`` maps ``BOBA_UPSTREAM_PROXY`` onto the standard
  ``HTTP_PROXY`` / ``HTTPS_PROXY`` / ``NO_PROXY`` variables. The public-tracker
  nova3 plugin subprocesses use ``urllib`` (via ``helpers.retrieve_url``), which
  honors those variables natively, so they egress through the proxy with the
  loopback bypass — no per-plugin edit needed.
* ``aiohttp_session_kwargs()`` returns ``{"trust_env": True}`` so the private
  tracker ``aiohttp.ClientSession`` clients (rutracker / kinozal / nnmclub /
  iptorrents) read the same env vars and honor ``NO_PROXY``. aiohttp does NOT
  read proxy env unless ``trust_env=True`` is set explicitly.

§6.R / CONST-XII: no proxy address is hardcoded; everything derives from env.
The loopback/sidecar names below are egress-bypass POLICY, not client-facing
URLs (CONST-XII rule 11 targets URLs rendered to a browser, which these are not).
"""

from __future__ import annotations

import ipaddress
import os

UPSTREAM_PROXY_ENV = "BOBA_UPSTREAM_PROXY"

# Always-bypassed egress hosts: loopback aliases + in-stack sidecar service
# names. Merged into NO_PROXY by apply_proxy_env() and honored by
# proxy_for_url()/is_bypassed().
DEFAULT_NO_PROXY_HOSTS: tuple[str, ...] = (
    "localhost",
    "127.0.0.1",
    "::1",
    "qbittorrent",
    "jackett",
    "flaresolverr",
)

# Standard proxy env vars consulted (in order) when BOBA_UPSTREAM_PROXY is unset.
_FALLBACK_PROXY_ENVS: tuple[str, ...] = (
    "ALL_PROXY",
    "all_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
)


def upstream_proxy() -> str | None:
    """Return the configured upstream proxy URL, or ``None`` when unset.

    ``BOBA_UPSTREAM_PROXY`` wins; otherwise the first non-empty standard proxy
    env var is used so an operator who already exports ``HTTPS_PROXY`` gets the
    expected fallback behaviour.
    """
    explicit = os.environ.get(UPSTREAM_PROXY_ENV, "").strip()
    if explicit:
        return explicit
    for name in _FALLBACK_PROXY_ENVS:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return None


def _no_proxy_entries() -> set[str]:
    """The bypass set: defaults plus operator NO_PROXY (lower-cased, trimmed)."""
    entries = {h.lower() for h in DEFAULT_NO_PROXY_HOSTS}
    for var in ("NO_PROXY", "no_proxy"):
        raw = os.environ.get(var, "")
        for part in raw.split(","):
            part = part.strip().lower()
            if part:
                entries.add(part)
    return entries


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_bypassed(host: str | None) -> bool:
    """True when ``host`` must stay DIRECT (never routed through the proxy).

    Matches loopback, an exact NO_PROXY/sidecar entry, or a ``.suffix`` domain
    entry (e.g. ``.corp.local`` matches ``api.corp.local``).
    """
    if not host:
        return True
    host = host.strip().lower()
    if _is_loopback(host):
        return True
    entries = _no_proxy_entries()
    if host in entries:
        return True
    return any(e.startswith(".") and host.endswith(e) for e in entries)


def proxy_for_url(url: str) -> str | None:
    """Return the proxy URL to use for ``url``, or ``None`` for a direct call.

    ``None`` when no proxy is configured OR the target host is bypassed
    (loopback / sidecar / NO_PROXY). This is the explicit decision used to pass
    ``proxy=`` to an aiohttp request when a caller wants per-request control.
    """
    proxy = upstream_proxy()
    if not proxy:
        return None
    from urllib.parse import urlparse

    host = urlparse(url).hostname
    if is_bypassed(host):
        return None
    return proxy


def apply_proxy_env() -> None:
    """Map ``BOBA_UPSTREAM_PROXY`` onto the standard proxy env vars in-place.

    Idempotent. When the explicit knob is set it populates ``HTTP_PROXY`` /
    ``HTTPS_PROXY`` (upper + lower case) so urllib-based plugin subprocesses and
    requests/aiohttp(trust_env) honor it. It ALWAYS ensures ``NO_PROXY`` carries
    the default loopback/sidecar bypass list (merged with any existing value) so
    internal calls stay direct even when only the fallback ``*_PROXY`` vars are
    set. Operator-supplied ``HTTP_PROXY``/``HTTPS_PROXY`` are never overwritten.
    """
    explicit = os.environ.get(UPSTREAM_PROXY_ENV, "").strip()
    if explicit:
        for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
            if not os.environ.get(name, "").strip():
                os.environ[name] = explicit

    # Ensure NO_PROXY always carries the bypass defaults (merged, de-duped,
    # order-stable) whenever ANY proxy is active.
    if upstream_proxy():
        merged: list[str] = []
        seen: set[str] = set()
        for src in (os.environ.get("NO_PROXY", ""), os.environ.get("no_proxy", "")):
            for part in src.split(","):
                p = part.strip()
                if p and p.lower() not in seen:
                    seen.add(p.lower())
                    merged.append(p)
        for h in DEFAULT_NO_PROXY_HOSTS:
            if h.lower() not in seen:
                seen.add(h.lower())
                merged.append(h)
        value = ",".join(merged)
        os.environ["NO_PROXY"] = value
        os.environ["no_proxy"] = value


def aiohttp_session_kwargs() -> dict[str, bool]:
    """kwargs to spread into ``aiohttp.ClientSession(...)`` for tracker clients.

    Returns ``{"trust_env": True}`` so the session reads ``HTTP(S)_PROXY`` /
    ``NO_PROXY`` from the environment (which ``apply_proxy_env()`` populates from
    ``BOBA_UPSTREAM_PROXY``). aiohttp ignores proxy env unless ``trust_env`` is
    set, so this is the switch that wires the private-tracker sessions to the
    proxy while honoring the loopback/sidecar bypass.
    """
    return {"trust_env": True}
