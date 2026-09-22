"""BOB-171 — rate-limiter client-identity resolution MUST NOT trust the
LEFTMOST X-Forwarded-For element.

THE BUG (pre-fix). `_client_key` in `download-proxy/src/api/rate_limit.py`
keyed the per-client bucket on `fwd.split(",")[0]` — the LEFTMOST XFF
element — whenever `TRUST_FORWARDED_FOR=1`. That element is CLIENT-SUPPLIED:
an honest reverse proxy APPENDS the real peer address to the RIGHT of
whatever arrived, so the leftmost entry is always whatever the ORIGINAL
CLIENT sent. A caller rotating a forged leftmost value therefore minted an
unlimited sequence of fresh rate-limit buckets from ONE real socket,
bypassing the limit entirely and evicting real clients' buckets out of the
LRU cap in the process.

THE FIX. `_client_key` now trusts XFF only when (1) `TRUST_FORWARDED_FOR=1`
AND (2) the REAL, socket-level peer address is inside a
`TRUSTED_PROXY_CIDRS` allowlist — and when trusted, uses the RIGHTMOST
element (what the directly-connected trusted proxy itself appended, which an
attacker in front of it cannot set). Empty/unset `TRUSTED_PROXY_CIDRS`, or a
peer outside every allowlisted CIDR, degrades to the raw peer address —
IDENTICAL to `TRUST_FORWARDED_FOR` being off.

THIS FILE covers ONLY the :7187 merge-service limiter
(`api.rate_limit._client_key`). The :7186 stdlib proxy's parallel fix
(`plugins/download_proxy.py::DownloadHandler._rate_limit_client`) is covered
by its own sibling file,
`tests/security/test_rate_limit_download_proxy_trusted_proxy_bob171.py` —
BOTH sites are fixed identically (§11.4.251) and each gets its own
same-shape RED / GREEN / paired-mutation / negative-control coverage so
neither surface can silently regress without the other's guard also
catching it.

§11.4.115(F): every case below is a machine-written verdict (an equality
assertion on the resolved key string) built directly against the real,
production `_client_key` function — no app, no HTTP, no TestClient — so
the RED/GREEN/mutation distinction is about the KEY-RESOLUTION LOGIC itself,
not about slowapi's bucket bookkeeping (that is already covered end-to-end by
`tests/unit/test_rate_limit.py` and
`tests/security/test_rate_limit_public_endpoints.py`).

§1.1 paired mutation (criterion c): `_PRE_FIX_CLIENT_KEY` below is the
BYTE-FOR-BYTE pre-fix implementation of `_client_key` (leftmost-element
parsing, no CIDR gate). `test_mutation_restoring_leftmost_parsing_fails`
drives the SAME rotating-XFF scenario the GREEN test in criterion (b) uses,
through that pre-fix function instead of the real one, and asserts the
assertion from (b) then FAILS — proving the GREEN test genuinely catches the
regression rather than passing trivially.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from starlette.requests import Request

_DP_SRC = Path(__file__).resolve().parents[2] / "download-proxy" / "src"
if str(_DP_SRC) not in sys.path:
    sys.path.insert(0, str(_DP_SRC))

import api.rate_limit as rl  # noqa: E402 - path setup must precede this import


def _make_request(client_ip: str, xff: str | None = None) -> Request:
    """Build a minimal real Starlette `Request` — real `.client`, real headers.

    No mock/stub of the request object's OWN attributes: `.client` and
    `.headers` are genuine Starlette machinery reading a real ASGI scope, so
    `_client_key` is exercised through its real code path
    (`slowapi.util.get_remote_address` + `request.headers.get(...)`), not a
    hand-rolled substitute.
    """
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "headers": headers,
        "client": (client_ip, 12345),
        "method": "GET",
        "path": "/api/v1/search",
        "query_string": b"",
        "http_version": "1.1",
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)


def _pre_fix_client_key(request: Request) -> str:
    """VERBATIM reproduction of the pre-BOB-171 `_client_key` body.

    Copied, not imported: the real module no longer contains this logic
    anywhere, so this is the only way to drive the exact defective behaviour
    for the paired-mutation check (criterion c). Any future edit to this
    function is a change to the TEST, never to production code.
    """
    from slowapi.util import get_remote_address

    if os.getenv("TRUST_FORWARDED_FOR", "").strip().lower() in ("1", "true", "yes"):
        fwd = request.headers.get("x-forwarded-for", "").strip()
        if fwd:
            return fwd.split(",")[0].strip()
    return get_remote_address(request)


_ENV_KEYS = ("TRUST_FORWARDED_FOR", "TRUSTED_PROXY_CIDRS")


@pytest.fixture(autouse=True)
def _clean_env():
    saved = {k: os.environ.get(k) for k in _ENV_KEYS}
    for k in _ENV_KEYS:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


REAL_PEER = "198.51.100.9"  # the honest client<->trusted-proxy socket peer
TRUSTED_CIDR = "198.51.100.0/24"
UNTRUSTED_PEER = "203.0.113.200"
ROTATING_FORGED_LEFTMOST = ("1.1.1.1", "2.2.2.2", "9.9.9.9", "6.6.6.6")
FIXED_RIGHTMOST = "192.0.2.55"  # what the trusted proxy itself appended


def _rotating_xff_keys(key_func) -> list[str]:
    """Resolve the client key across N requests with the SAME real peer but a
    DIFFERENT forged leftmost XFF element each time (the attack)."""
    keys = []
    for forged in ROTATING_FORGED_LEFTMOST:
        xff = f"{forged}, {FIXED_RIGHTMOST}"
        req = _make_request(REAL_PEER, xff=xff)
        keys.append(key_func(req))
    return keys


# ---------------------------------------------------------------------------
# (b) GREEN — rotating leftmost XFF must NOT rotate the resolved bucket key,
# when the peer is an allowlisted trusted proxy.
# ---------------------------------------------------------------------------


def test_green_rotating_leftmost_xff_does_not_rotate_the_bucket_key():
    os.environ["TRUST_FORWARDED_FOR"] = "1"
    os.environ["TRUSTED_PROXY_CIDRS"] = TRUSTED_CIDR

    keys = _rotating_xff_keys(rl._client_key)

    assert len(set(keys)) == 1, (
        f"resolved bucket key rotated across a rotating forged leftmost XFF "
        f"value from ONE real peer: {keys} — this is the BOB-171 bypass"
    )
    # And it must be the RIGHTMOST (trusted-proxy-appended) address, not a
    # forged one and not the raw peer — proving the fix reads the right
    # component, not merely a constant.
    assert keys[0] == FIXED_RIGHTMOST, keys


def test_green_key_is_not_any_forged_leftmost_value():
    os.environ["TRUST_FORWARDED_FOR"] = "1"
    os.environ["TRUSTED_PROXY_CIDRS"] = TRUSTED_CIDR

    keys = _rotating_xff_keys(rl._client_key)
    for forged, key in zip(ROTATING_FORGED_LEFTMOST, keys):
        assert key != forged, f"resolved key equalled the attacker-forged leftmost value {forged!r}"


# ---------------------------------------------------------------------------
# (c) Paired §1.1 mutation — restore leftmost parsing -> the (b) assertion
# must then FAIL, proving the GREEN test is not trivially satisfied.
# ---------------------------------------------------------------------------


def test_mutation_restoring_leftmost_parsing_fails():
    os.environ["TRUST_FORWARDED_FOR"] = "1"
    os.environ["TRUSTED_PROXY_CIDRS"] = TRUSTED_CIDR

    keys = _rotating_xff_keys(_pre_fix_client_key)

    # The pre-fix function keys on the leftmost (forged) element, so it MUST
    # rotate in lock-step with the attacker's forged values.
    assert keys == list(ROTATING_FORGED_LEFTMOST), (
        f"paired-mutation sanity check failed: the reproduced pre-fix "
        f"function did not exhibit leftmost-parsing behaviour ({keys}) — "
        f"the mutation itself is not faithful to the original bug"
    )

    with pytest.raises(AssertionError):
        assert len(set(keys)) == 1, (
            f"resolved bucket key rotated across a rotating forged leftmost XFF "
            f"value from ONE real peer: {keys} — this is the BOB-171 bypass"
        )


# ---------------------------------------------------------------------------
# (d) NEGATIVE CONTROL — TRUST_FORWARDED_FOR off (the default): XFF is
# ignored ENTIRELY, keying MUST fall back to the raw peer address.
# ---------------------------------------------------------------------------


def test_negative_control_flag_off_ignores_xff_entirely():
    # TRUST_FORWARDED_FOR intentionally left unset (the default) by the
    # autouse _clean_env fixture. TRUSTED_PROXY_CIDRS is ALSO set, to prove
    # the flag itself — not merely an empty allowlist — is what gates XFF.
    os.environ["TRUSTED_PROXY_CIDRS"] = TRUSTED_CIDR

    req = _make_request(REAL_PEER, xff=f"9.9.9.9, {FIXED_RIGHTMOST}")
    key = rl._client_key(req)

    assert key == REAL_PEER, (
        f"TRUST_FORWARDED_FOR is OFF but the resolved key ({key!r}) was not "
        f"the raw peer address ({REAL_PEER!r}) — a guard that starts "
        f"honouring XFF even when the flag is off is a worse defect than the "
        f"one being fixed (§11.4.201(1))"
    )


def test_negative_control_default_env_state_ignores_xff():
    """Same as above but with NO env vars set at all — the true out-of-the-box
    default (`TRUST_FORWARDED_FOR` unset, `TRUSTED_PROXY_CIDRS` unset)."""
    req = _make_request(REAL_PEER, xff="9.9.9.9")
    assert rl._client_key(req) == REAL_PEER


# ---------------------------------------------------------------------------
# Empty/unset TRUSTED_PROXY_CIDRS with the flag ON degrades to the safe
# default too — "trust nothing" is the honest empty-allowlist reading.
# ---------------------------------------------------------------------------


def test_flag_on_but_empty_allowlist_still_ignores_xff():
    os.environ["TRUST_FORWARDED_FOR"] = "1"
    # TRUSTED_PROXY_CIDRS left unset.
    req = _make_request(REAL_PEER, xff=f"9.9.9.9, {FIXED_RIGHTMOST}")
    assert rl._client_key(req) == REAL_PEER, (
        "an unset TRUSTED_PROXY_CIDRS with TRUST_FORWARDED_FOR=1 must degrade "
        "to the raw peer address, not honour XFF from an unvetted peer"
    )


def test_flag_on_but_peer_outside_allowlist_ignores_xff():
    os.environ["TRUST_FORWARDED_FOR"] = "1"
    os.environ["TRUSTED_PROXY_CIDRS"] = TRUSTED_CIDR
    req = _make_request(UNTRUSTED_PEER, xff=f"9.9.9.9, {FIXED_RIGHTMOST}")
    assert rl._client_key(req) == UNTRUSTED_PEER, (
        "a peer OUTSIDE the trusted-proxy allowlist must never have its XFF "
        "header honoured, even with TRUST_FORWARDED_FOR=1"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
