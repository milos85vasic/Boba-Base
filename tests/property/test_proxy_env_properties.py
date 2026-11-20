"""Property-based tests for ``config.proxy.proxy_env()``.

The new ``proxy_env()`` function must be deterministic and must NEVER mutate
the global ``os.environ``. Hypothesis generates varied proxy/NO_PROXY inputs
and asserts both invariants hold.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "download-proxy" / "src").is_dir():
            return parent
    raise RuntimeError("cannot find repo root with download-proxy/src")


import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_SRC = _repo_root() / "download-proxy" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config import proxy as proxy_config

pytestmark = pytest.mark.property


_URL_SAFE = st.characters(
    whitelist_categories=("L", "N", "P"),
    blacklist_characters="\x00 \t\n\r",
)

_PROXY_URLS = st.one_of(
    st.just(""),
    st.sampled_from(
        [
            "http://proxy.example:8080",
            "https://proxy.example:8443",
            "socks5://127.0.0.1:1080",
            "http://10.0.0.1:3128",
            "http://user:pass@proxy.example:8080",
        ]
    ),
    st.tuples(_URL_SAFE, _URL_SAFE).map(lambda parts: f"http://{parts[0]}:{parts[1]}").filter(lambda u: ":" in u),
)

_NO_PROXY = st.one_of(
    st.just(""),
    st.sampled_from(
        [
            "localhost",
            "127.0.0.1,.corp.local",
            "internal.example,api.internal",
            ".local",
        ]
    ),
    st.lists(_URL_SAFE, min_size=1, max_size=5).map(lambda parts: ",".join(parts)),
)


@given(proxy=_PROXY_URLS, no_proxy=_NO_PROXY)
@settings(
    max_examples=50,
    deadline=5_000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
def test_proxy_env_is_deterministic_and_non_mutating(monkeypatch, proxy, no_proxy):
    for v in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "BOBA_UPSTREAM_PROXY"):
        monkeypatch.delenv(v, raising=False)
    if proxy:
        monkeypatch.setenv("BOBA_UPSTREAM_PROXY", proxy)
    if no_proxy:
        monkeypatch.setenv("NO_PROXY", no_proxy)

    before = os.environ.copy()
    first = proxy_config.proxy_env()
    second = proxy_config.proxy_env()
    after = os.environ.copy()

    assert after == before, "proxy_env() mutated os.environ"
    assert first == second, "proxy_env() is non-deterministic"

    if proxy:
        assert first.get("HTTP_PROXY") == proxy.strip()
        assert first.get("HTTPS_PROXY") == proxy.strip()
        no_proxy_value = first.get("NO_PROXY", "").lower()
        assert "localhost" in no_proxy_value
        assert "127.0.0.1" in no_proxy_value
        assert "qbittorrent" in no_proxy_value
        assert "jackett" in no_proxy_value
    else:
        # When no proxy is configured, proxy_env should not invent one.
        assert first.get("HTTP_PROXY") in (None, "")
        assert first.get("HTTPS_PROXY") in (None, "")
