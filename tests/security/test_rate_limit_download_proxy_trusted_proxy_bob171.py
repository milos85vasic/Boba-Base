"""BOB-171 — the :7186 stdlib rate limiter's client-identity resolution MUST
NOT trust the LEFTMOST X-Forwarded-For element.

Sibling of `tests/unit/test_rate_limit_client_identity_bob171.py`, which
covers the SAME defect and the SAME fix at :7187
(`api.rate_limit._client_key`). This file covers :7186's parallel
implementation, `plugins/download_proxy.py::DownloadHandler._rate_limit_client`
— built to EXACT policy parity with :7187's limiter (§11.4.251), including
this same leftmost-element-parsing bug and, now, this same
trusted-proxy-CIDR-allowlist fix. Both sites get their own same-shape
RED / GREEN / paired-mutation / negative-control coverage so a regression at
either port is caught independently of the other's guard.

THE BUG (pre-fix). `DownloadHandler._rate_limit_client` keyed the per-client
bucket on `fwd.split(",")[0]` — the LEFTMOST XFF element, CLIENT-SUPPLIED and
therefore forgeable — whenever `TRUST_FORWARDED_FOR=1`. Rotating a forged
leftmost value from one real socket minted an unlimited sequence of fresh
rate-limit buckets.

THE FIX. XFF is honoured ONLY when (1) `TRUST_FORWARDED_FOR=1` AND (2) the
REAL socket peer address (`self.client_address[0]`) is inside a
`TRUSTED_PROXY_CIDRS` allowlist, and then uses the RIGHTMOST XFF element.
Unset/empty `TRUSTED_PROXY_CIDRS`, or a peer outside the allowlist, degrades
to the raw peer address — identical to `TRUST_FORWARDED_FOR` being off.

EVIDENCE CLASS (§11.4.226): this file drives `DownloadHandler`'s key-
resolution methods DIRECTLY against a lightweight stand-in for the stdlib
`BaseHTTPRequestHandler` instance (a plain object carrying the two
attributes those methods actually read — `self.headers` and
`self.client_address`) rather than opening a real socket. The FULL
socket-level rate-limit-bucket behaviour (burst, per-class budgets, 429
bodies) for :7186 is already covered end-to-end by
`tests/security/test_rate_limit_download_proxy.py`
(`test_per_ip_isolation_under_explicit_forwarded_for_optin`,
`test_forwarded_for_is_ignored_without_the_optin`); this file's job is to
prove the KEY-RESOLUTION LOGIC itself resists the rotating-forged-leftmost
attack and stays honest with the flag off, matching the level this bug was
actually reported at.

§11.4.263: no subprocess/proc object is mocked anywhere in this file, so no
`mock.pid` is involved.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DP_PATH = os.path.join(_REPO_ROOT, "plugins", "download_proxy.py")


def _load_download_proxy(env: dict[str, str]):
    """Import a FRESH `download_proxy` module under the given env.

    `TRUST_FORWARDED_FOR` / `TRUSTED_PROXY_CIDRS` are resolved to module-level
    constants at IMPORT time (matching the module's existing pattern for
    `TRUST_FORWARDED_FOR` / `RATE_LIMIT_IDLE_REAP_SECONDS`), so each case gets
    its own fresh module object rather than mutating shared state.
    """
    env = dict(env)
    env.setdefault("QBITTORRENT_HOST", "127.0.0.1")
    env.setdefault("QBITTORRENT_PORT", "1")  # never dialled by these cases
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        spec = importlib.util.spec_from_file_location("download_proxy_bob171_case", _DP_PATH)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["download_proxy_bob171_case"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _FakeHandler:
    """Carries exactly the attributes `_rate_limit_client` (and the
    `_rate_limit_peer` it calls) read.

    `self.headers.get("X-Forwarded-For")` and `self.client_address[0]` — a
    plain dict + tuple duck-type the stdlib `BaseHTTPRequestHandler`
    interface those reads actually need; nothing about this stands in for
    `_rate_limit_client`'s OWN logic, which stays the real, unmodified method
    under test (accessed as `mod.DownloadHandler._rate_limit_client(handler)`
    — an unbound-function call with this object as `self`).
    """

    def __init__(self, client_ip: str, xff: str | None = None):
        self.client_address = (client_ip, 12345)
        self.headers = {} if xff is None else {"X-Forwarded-For": xff}

    def _rate_limit_peer(self):
        try:
            return self.client_address[0]
        except (AttributeError, IndexError, TypeError):
            return "unknown"


def _rotating_xff_keys(mod, key_method_name: str, real_peer: str, rightmost: str, forged_values) -> list[str]:
    keys = []
    for forged in forged_values:
        handler = _FakeHandler(real_peer, xff=f"{forged}, {rightmost}")
        keys.append(getattr(mod.DownloadHandler, key_method_name)(handler))
    return keys


REAL_PEER = "198.51.100.9"
TRUSTED_CIDR = "198.51.100.0/24"
UNTRUSTED_PEER = "203.0.113.200"
ROTATING_FORGED_LEFTMOST = ("1.1.1.1", "2.2.2.2", "9.9.9.9", "6.6.6.6")
FIXED_RIGHTMOST = "192.0.2.55"


# ---------------------------------------------------------------------------
# (b) GREEN — rotating leftmost XFF must NOT rotate the resolved bucket key.
# ---------------------------------------------------------------------------


def test_green_rotating_leftmost_xff_does_not_rotate_the_bucket_key():
    mod = _load_download_proxy(
        {"TRUST_FORWARDED_FOR": "1", "TRUSTED_PROXY_CIDRS": TRUSTED_CIDR}
    )
    try:
        keys = _rotating_xff_keys(
            mod, "_rate_limit_client", REAL_PEER, FIXED_RIGHTMOST, ROTATING_FORGED_LEFTMOST
        )
        assert len(set(keys)) == 1, (
            f"resolved bucket key rotated across a rotating forged leftmost "
            f"XFF value from ONE real peer: {keys} — this is the BOB-171 "
            f"bypass at :7186"
        )
        assert keys[0] == FIXED_RIGHTMOST, keys
    finally:
        sys.modules.pop("download_proxy_bob171_case", None)


def test_green_key_is_not_any_forged_leftmost_value():
    mod = _load_download_proxy(
        {"TRUST_FORWARDED_FOR": "1", "TRUSTED_PROXY_CIDRS": TRUSTED_CIDR}
    )
    try:
        keys = _rotating_xff_keys(
            mod, "_rate_limit_client", REAL_PEER, FIXED_RIGHTMOST, ROTATING_FORGED_LEFTMOST
        )
        for forged, key in zip(ROTATING_FORGED_LEFTMOST, keys):
            assert key != forged, f"resolved key equalled the attacker-forged leftmost value {forged!r}"
    finally:
        sys.modules.pop("download_proxy_bob171_case", None)


# ---------------------------------------------------------------------------
# (c) Paired §1.1 mutation — restore leftmost parsing -> the (b) assertion
# must then FAIL.
# ---------------------------------------------------------------------------


def _pre_fix_rate_limit_client(handler, trust_forwarded_for: bool) -> str:
    """VERBATIM reproduction of the pre-BOB-171 `_rate_limit_client` body."""
    if trust_forwarded_for:
        fwd = (handler.headers.get("X-Forwarded-For") or "").strip()
        if fwd:
            return fwd.split(",")[0].strip()
    try:
        return handler.client_address[0]
    except (AttributeError, IndexError, TypeError):
        return "unknown"


def test_mutation_restoring_leftmost_parsing_fails():
    keys = [
        _pre_fix_rate_limit_client(
            _FakeHandler(REAL_PEER, xff=f"{forged}, {FIXED_RIGHTMOST}"), trust_forwarded_for=True
        )
        for forged in ROTATING_FORGED_LEFTMOST
    ]

    assert keys == list(ROTATING_FORGED_LEFTMOST), (
        f"paired-mutation sanity check failed: the reproduced pre-fix "
        f"function did not exhibit leftmost-parsing behaviour ({keys})"
    )

    with pytest.raises(AssertionError):
        assert len(set(keys)) == 1, (
            f"resolved bucket key rotated across a rotating forged leftmost "
            f"XFF value from ONE real peer: {keys} — this is the BOB-171 "
            f"bypass at :7186"
        )


# ---------------------------------------------------------------------------
# (d) NEGATIVE CONTROL — TRUST_FORWARDED_FOR off (the default): XFF is
# ignored ENTIRELY, keying MUST fall back to the raw peer address.
# ---------------------------------------------------------------------------


def test_negative_control_flag_off_ignores_xff_entirely():
    mod = _load_download_proxy({"TRUSTED_PROXY_CIDRS": TRUSTED_CIDR})  # TRUST_FORWARDED_FOR unset
    try:
        handler = _FakeHandler(REAL_PEER, xff=f"9.9.9.9, {FIXED_RIGHTMOST}")
        key = mod.DownloadHandler._rate_limit_client(handler)
        assert key == REAL_PEER, (
            f"TRUST_FORWARDED_FOR is OFF but the resolved key ({key!r}) was "
            f"not the raw peer address ({REAL_PEER!r})"
        )
    finally:
        sys.modules.pop("download_proxy_bob171_case", None)


def test_negative_control_default_env_state_ignores_xff():
    mod = _load_download_proxy({})  # nothing set at all — true out-of-the-box default
    try:
        handler = _FakeHandler(REAL_PEER, xff="9.9.9.9")
        assert mod.DownloadHandler._rate_limit_client(handler) == REAL_PEER
    finally:
        sys.modules.pop("download_proxy_bob171_case", None)


# ---------------------------------------------------------------------------
# Empty/unset TRUSTED_PROXY_CIDRS, and an out-of-allowlist peer, both degrade
# to the safe default even with the flag ON.
# ---------------------------------------------------------------------------


def test_flag_on_but_empty_allowlist_still_ignores_xff():
    mod = _load_download_proxy({"TRUST_FORWARDED_FOR": "1"})  # TRUSTED_PROXY_CIDRS unset
    try:
        handler = _FakeHandler(REAL_PEER, xff=f"9.9.9.9, {FIXED_RIGHTMOST}")
        key = mod.DownloadHandler._rate_limit_client(handler)
        assert key == REAL_PEER, (
            "an unset TRUSTED_PROXY_CIDRS with TRUST_FORWARDED_FOR=1 must "
            "degrade to the raw peer address"
        )
    finally:
        sys.modules.pop("download_proxy_bob171_case", None)


def test_flag_on_but_peer_outside_allowlist_ignores_xff():
    mod = _load_download_proxy(
        {"TRUST_FORWARDED_FOR": "1", "TRUSTED_PROXY_CIDRS": TRUSTED_CIDR}
    )
    try:
        handler = _FakeHandler(UNTRUSTED_PEER, xff=f"9.9.9.9, {FIXED_RIGHTMOST}")
        key = mod.DownloadHandler._rate_limit_client(handler)
        assert key == UNTRUSTED_PEER, (
            "a peer OUTSIDE the trusted-proxy allowlist must never have its "
            "XFF header honoured, even with TRUST_FORWARDED_FOR=1"
        )
    finally:
        sys.modules.pop("download_proxy_bob171_case", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
