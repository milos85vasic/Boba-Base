"""BOB-172 — a tracker that is REFUSED must not be reported as "empty".

FORENSIC ANCHOR (measured, docs/qa/BOB-172/rutracker_search_403_20260821.log,
all probes UNAUTHENTICATED — no credential value in any artifact, §11.4.10):

    GET /forum/index.php             -> 200, 96283 B, challenge markers 0
    GET /forum/tracker.php?nm=debian -> 403,  5351 B, challenge markers 1,
                                              login markers 0, trs-tr- 0

Zero login markers is load-bearing: the server is refusing the request BEFORE
authentication is considered, so credentials/cookies do not address it.

THE DEFECT THIS FILE PINS. `_search_rutracker` never inspects `resp.status`.
The 403 challenge body is handed straight to `_parse_rutracker_html`, which
finds no `trs-tr-` rows and returns []. `_run_search` then executes

    stat.status = "success" if results else "empty"

with no diagnostic on the side-channel, so a REFUSED tracker is reported to
the user as `status="empty", results_count=0, error=None`. That is the
§11.4.201(6) FALSE-NULL at the product layer: a blind instrument and a
genuinely empty tracker return the identical quiet zero. It is exactly the
`status=empty, results_count=0 in 164ms` that TWO prior investigations
(docs/qa/BOB-093/live_search_smoke.txt and the BOB-136 audit) recorded as an
unexplained anomaly without ever finding the cause — 164ms being far too fast
for a real remote search and entirely consistent with an immediate 403.

The pre-existing guard cannot catch it, on BOTH of its conditions:

    if len(html_content) < 1024 and "captcha" in html_content.lower():

the measured challenge body is 5351 B (not < 1024) and carries
`Just a moment` / `cf-chl` / `challenge-platform`, not `captcha`.

THE NEGATIVE CONTROL IS NOT OPTIONAL (§11.4.201(1)). A tracker that
legitimately returns HTTP 200 with zero rows for an obscure query MUST still
report empty-and-successful. Turning every empty tracker into an error would
be a false-positive refusal — a FAIL-bluff, and a worse defect than the
false-null being fixed here. `test_http_200_with_zero_rows_*` pins that
direction and must stay green both before and after the fix.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SRC = _REPO / "download-proxy" / "src"
_MS = _SRC / "merge_service"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

sys.modules.setdefault("merge_service", type(sys)("merge_service"))
sys.modules["merge_service"].__path__ = [str(_MS)]  # type: ignore[attr-defined]


def _import_search_module():
    spec = importlib.util.spec_from_file_location("merge_service.search", str(_MS / "search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["merge_service.search"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def search_mod():
    return _import_search_module()


# --------------------------------------------------------------------------
# Fixtures captured from the real measurement (docs/qa/BOB-172/...).
# Bodies are trimmed to their load-bearing markers; the SHAPE is what matters:
# a non-2xx status carrying a challenge page that parses to zero rows.
# --------------------------------------------------------------------------

_CLOUDFLARE_403_BODY = (
    "<!DOCTYPE html><html><head><title>Just a moment...</title>"
    '<meta http-equiv="refresh" content="35">'
    "</head><body>"
    '<div class="cf-chl-wrapper"><div id="challenge-platform">'
    "Enable JavaScript and cookies to continue"
    "</div></div></body></html>"
    # Pad past the pre-existing `len < 1024` CAPTCHA guard so the fixture
    # reproduces the measured 5351 B body's defeat of that condition too.
    + ("<!-- x -->" * 600)
)

# A real rutracker search page for a query with no hits: HTTP 200, full
# chrome, zero `trs-tr-` rows. This is the legitimate-empty case.
_EMPTY_BUT_OK_BODY = (
    "<!DOCTYPE html><html><head><title>RuTracker.org</title></head><body>"
    '<div id="search-results"><table class="forumline"><tbody>'
    "</tbody></table></div>"
    "<p>Поиск не дал результатов</p>"
    "</body></html>"
)


class _FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body
        self.cookies: dict = {}

    async def text(self, *a, **kw) -> str:
        return self._body

    async def read(self, *a, **kw) -> bytes:
        return self._body.encode("utf-8", "ignore")

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeSession:
    """Minimal aiohttp.ClientSession stand-in.

    Returns the configured (status, body) for the SEARCH GET. This is a unit
    test, so a stub is the sanctioned mechanism (§11.4.27(A)); the real
    upstream behaviour it encodes is the captured measurement in the QA log,
    not an assumption.
    """

    def __init__(self, status: int, body: str) -> None:
        self._status = status
        self._body = body
        self.requested_urls: list[str] = []

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def get(self, url: str, *a, **kw) -> _FakeResponse:
        self.requested_urls.append(url)
        return _FakeResponse(self._status, self._body)

    def post(self, url: str, *a, **kw) -> _FakeResponse:
        return _FakeResponse(200, "")


def _run_rutracker_search(search_mod, monkeypatch, *, status: int, body: str):
    """Drive a real single-tracker fan-out with a stubbed upstream.

    Returns the rutracker TrackerSearchStat as the user-visible merge result
    would carry it (§11.4.262: assert on the observable the caller reads, not
    on an internal flag).
    """
    # Synthetic fixture values only — never a real credential (§11.4.10).
    monkeypatch.setenv("RUTRACKER_USERNAME", "test-user-not-a-real-account")
    monkeypatch.setenv("RUTRACKER_PASSWORD", "test-value-not-a-real-secret")
    monkeypatch.setenv("RUTRACKER_COOKIES", "bb_session=SYNTHETIC-TEST-FIXTURE-VALUE")
    monkeypatch.setenv("RUTRACKER_MIRRORS", "https://rutracker.example")

    orch = search_mod.SearchOrchestrator()
    fake_session = _FakeSession(status, body)

    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: fake_session)

    metadata = orch.start_search(
        "debian",
        "all",
        enable_metadata=False,
        validate_trackers=False,
        trackers=["rutracker"],
    )
    assert "rutracker" in metadata.tracker_stats, (
        "rutracker was not selected for the fan-out — the fixture env did not "
        "enable it, so this test would vacuously pass. Fix the fixture."
    )

    asyncio.run(orch._run_search(metadata.search_id, "debian", "all"))
    return metadata, metadata.tracker_stats["rutracker"]


# ==========================================================================
# THE DEFECT — a refused tracker must be distinguishable from an empty one
# ==========================================================================


def test_rutracker_403_is_reported_as_error_not_empty(search_mod, monkeypatch):
    """A 403 challenge must surface as an ERROR, never fold into "empty"."""
    metadata, stat = _run_rutracker_search(
        search_mod, monkeypatch, status=403, body=_CLOUDFLARE_403_BODY
    )

    assert stat.status == "error", (
        f"rutracker returned HTTP 403 but the merge result reports "
        f"status={stat.status!r}. A tracker that REFUSED us is indistinguishable "
        f"from one that simply had no hits — the §11.4.201(6) false-null that "
        f"let this sit unexplained across two investigations."
    )
    assert stat.results_count == 0


def test_rutracker_403_records_the_upstream_status_code(search_mod, monkeypatch):
    """The refusing status code must be observable to the caller.

    `TrackerSearchStat.http_status` is already declared and already serialised
    by `to_dict()` — it was simply never assigned on this path. Populating the
    existing field is the §11.4.28 reuse-don't-invent move.
    """
    _metadata, stat = _run_rutracker_search(
        search_mod, monkeypatch, status=403, body=_CLOUDFLARE_403_BODY
    )

    assert stat.http_status == 403, (
        f"http_status={stat.http_status!r} — the caller cannot tell WHICH "
        f"upstream status refused the search."
    )


def test_rutracker_403_carries_a_typed_error_and_a_reason(search_mod, monkeypatch):
    """The error must be machine-routable AND human-readable (§11.4.6).

    `upstream_http_403` is the error_type the plugin-subprocess path already
    emits via `_classify_plugin_stderr`. Reusing that exact token keeps ONE
    vocabulary across both tracker paths (§11.4.28) instead of minting a
    second, divergent one the dashboard would have to learn.
    """
    _metadata, stat = _run_rutracker_search(
        search_mod, monkeypatch, status=403, body=_CLOUDFLARE_403_BODY
    )

    assert stat.error_type == "upstream_http_403", (
        f"error_type={stat.error_type!r} — expected the existing "
        f"`upstream_http_403` token already used by the plugin path."
    )
    assert stat.error, "a typed error with no human-readable reason is half a diagnostic"
    assert "403" in stat.error


def test_403_body_never_reaches_the_row_parser(search_mod, monkeypatch):
    """A refusal body must not be handed to the row parser AT ALL.

    This is the mechanism assertion, not a symptom assertion. Parsing a
    refusal body is precisely how the zero-row count got manufactured: the
    parser dutifully found no `trs-tr-` rows in a challenge page and returned
    [], which `_run_search` then rendered as "empty". Asserting only on the
    resulting count would pass in BOTH directions (a challenge page yields
    zero rows either way) and would therefore discriminate nothing —
    unvalidated instrumentation per §11.4.115(F). Asserting the parser is
    never INVOKED fails against the pre-fix code, which is what makes it a
    real guard.
    """
    calls: list[int] = []
    real_parser = search_mod.SearchOrchestrator._parse_rutracker_html

    def _spy(self, html_content, base_url):
        calls.append(len(html_content))
        return real_parser(self, html_content, base_url)

    with patch.object(search_mod.SearchOrchestrator, "_parse_rutracker_html", _spy):
        _metadata, stat = _run_rutracker_search(
            search_mod, monkeypatch, status=403, body=_CLOUDFLARE_403_BODY
        )

    assert calls == [], (
        f"the HTTP 403 challenge body was passed to _parse_rutracker_html "
        f"({calls} byte(s)). Parsing a refusal is what manufactured the "
        f"phantom zero that reads as 'empty'."
    )
    assert stat.results_count == 0
    assert stat.status == "error"


def test_healthy_200_body_DOES_reach_the_row_parser(search_mod, monkeypatch):
    """Negative control for the assertion above (§11.4.201(1)).

    A guard that stopped the parser running on healthy responses too would
    break every search while still passing the test above. This pins that the
    parser is skipped ONLY for refusals.
    """
    calls: list[int] = []
    real_parser = search_mod.SearchOrchestrator._parse_rutracker_html

    def _spy(self, html_content, base_url):
        calls.append(len(html_content))
        return real_parser(self, html_content, base_url)

    with patch.object(search_mod.SearchOrchestrator, "_parse_rutracker_html", _spy):
        _metadata, stat = _run_rutracker_search(
            search_mod, monkeypatch, status=200, body=_EMPTY_BUT_OK_BODY
        )

    assert len(calls) == 1, (
        f"a healthy HTTP 200 search body did not reach the row parser "
        f"(invocations={calls}) — the refusal guard is over-firing and no "
        f"search can return results at all."
    )
    assert stat.status == "empty"


def test_search_metadata_errors_names_the_refusing_tracker(search_mod, monkeypatch):
    """The merged response's error list must name rutracker.

    §11.4.262: the assertion is on what a caller of the merge API actually
    reads back, not on an internal-only field.
    """
    metadata, _stat = _run_rutracker_search(
        search_mod, monkeypatch, status=403, body=_CLOUDFLARE_403_BODY
    )
    payload = metadata.to_dict()
    joined = " | ".join(payload.get("errors") or [])
    assert "rutracker" in joined, (
        f"metadata.errors={payload.get('errors')!r} — a caller reading the "
        f"merged response has no signal that rutracker contributed nothing "
        f"because it was refused."
    )


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_other_refusing_statuses_also_surface_as_error(search_mod, monkeypatch, status):
    """403 is the measured case, not a special case.

    Hard-coding a 403-only check would leave the identical false-null open for
    every other non-2xx status — a fix narrower than the defect class.
    """
    _metadata, stat = _run_rutracker_search(
        search_mod, monkeypatch, status=status, body="<html>refused</html>"
    )
    assert stat.status == "error", f"HTTP {status} folded into status={stat.status!r}"
    assert stat.http_status == status


# ==========================================================================
# NEGATIVE CONTROL (§11.4.201(1)) — must be GREEN before AND after the fix.
# A false-positive refusal is a FAIL-bluff of equal severity to the
# false-null being fixed. These pin the other direction.
# ==========================================================================


def test_http_200_with_zero_rows_stays_empty_and_successful(search_mod, monkeypatch):
    """An obscure query that genuinely has no hits is EMPTY, not an error."""
    _metadata, stat = _run_rutracker_search(
        search_mod, monkeypatch, status=200, body=_EMPTY_BUT_OK_BODY
    )

    assert stat.status == "empty", (
        f"a legitimate zero-result HTTP 200 search was reported as "
        f"status={stat.status!r}. Conflating 'no hits' with 'refused' is the "
        f"§11.4.201(1) false-positive refusal — a worse defect than the one "
        f"under fix, because it teaches the operator to ignore tracker errors."
    )
    assert stat.results_count == 0


def test_http_200_with_zero_rows_carries_no_error(search_mod, monkeypatch):
    """A legitimately-empty tracker must carry no error and no error_type."""
    _metadata, stat = _run_rutracker_search(
        search_mod, monkeypatch, status=200, body=_EMPTY_BUT_OK_BODY
    )
    assert stat.error_type is None, f"error_type={stat.error_type!r} on a healthy empty search"
    assert stat.error is None, f"error={stat.error!r} on a healthy empty search"


def test_http_200_zero_rows_is_not_in_metadata_errors(search_mod, monkeypatch):
    """A healthy empty tracker must not pollute the merged error list."""
    metadata, _stat = _run_rutracker_search(
        search_mod, monkeypatch, status=200, body=_EMPTY_BUT_OK_BODY
    )
    joined = " | ".join(metadata.to_dict().get("errors") or [])
    assert "rutracker" not in joined, (
        f"a healthy zero-result search was reported as an error: {joined!r}"
    )
