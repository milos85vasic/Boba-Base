"""BOB-167 criterion (c) — the GENERAL guard that enumerates every
SSE-shaped route in the merge service and fails the build if any of them
carries no explicit rate-limit class.

This is the meta-test for
``scripts/pre_build/check_cm_sse_route_rate_limit_classed.sh`` /
``scripts/pre_build/sse_route_rate_limit_class_analyzer.py`` — the "GENERAL
form" the item's acceptance criterion (c) asks for, so a THIRD SSE route
landing later with the same silent omission is caught by the SAME
mechanism, not just the one route this item's decorator fix closes.

Lives under ``tests/unit/`` per the item's scope constraint (the gate
script itself is boba-specific, main-repo scope, not the constitution
submodule — see that script's own header).

Evidence classes covered here (§11.4.115(F) RED/GREEN polarity +
§11.4.201(1) both-directions):

  * PASS on the real, post-fix ``routes.py`` (both SSE routes classed).
  * FAIL (RED) reproduced against the real PRE-fix ``routes.py`` content
    via a controlled, in-memory mutation — never by depending on a live
    git-stash dance (that is done once, by hand, for the operator report;
    THIS suite is the machine-repeatable, permanent regression guard).
  * Golden-FALSE (§11.4.201(1)): a synthetic, correctly-classed SSE route
    is NOT flagged — proves the guard doesn't over-fire on routes doing
    the right thing, in BOTH established SSE-response idioms this
    codebase uses (inline ``StreamingResponse(media_type=...)`` and the
    shared ``create_streaming_response(...)`` helper) and BOTH established
    classing idioms (the ``@_rl(...)`` decorator and the
    ``Depends(rate_limit_dependency(...))`` dependency form).
  * A non-SSE ``StreamingResponse`` (a different ``media_type``, e.g. the
    real ``/search/sync`` heartbeat or a torrent download) is correctly
    excluded from the SSE-shaped set — never flagged, never "explains" an
    unrelated route.
  * The zero-SSE-shaped-routes refusal (§11.4.201(6) false-null): a file
    with no SSE routes at all is ERROR, never a silent PASS.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GATE = _REPO_ROOT / "scripts" / "pre_build" / "check_cm_sse_route_rate_limit_classed.sh"
_ANALYZER = _REPO_ROOT / "scripts" / "pre_build" / "sse_route_rate_limit_class_analyzer.py"
_REAL_ROUTES = _REPO_ROOT / "download-proxy" / "src" / "api" / "routes.py"


def _run_gate(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_GATE), str(target)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _run_analyzer_json(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ANALYZER), "--file", str(target), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture(autouse=True)
def _preconditions():
    assert _GATE.is_file(), f"gate wrapper missing: {_GATE}"
    assert _ANALYZER.is_file(), f"analyzer engine missing: {_ANALYZER}"
    assert _REAL_ROUTES.is_file(), f"real routes.py missing: {_REAL_ROUTES}"


class TestGatePassesOnRealPostFixTree:
    def test_gate_passes_on_the_real_routes_module(self):
        """The permanent-regression state: both real SSE routes classed."""
        result = _run_gate(_REAL_ROUTES)
        assert result.returncode == 0, (
            f"gate FAILed against the real (post-fix) routes.py — "
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "PASS(CM-SSE-ROUTE-RATE-LIMIT-CLASSED)" in result.stdout
        assert "'/theme/stream'" in result.stdout
        assert "'/search/stream/{search_id}'" in result.stdout


class TestGateReproducesTheOriginalGap:
    """§11.4.115(F): the RED half, reproduced by controlled in-memory
    mutation of the real file's content rather than a manual git dance —
    this makes the RED reproducible on every future run of this suite."""

    def test_gate_fails_when_theme_stream_decorator_is_reverted(self, tmp_path):
        real_src = _REAL_ROUTES.read_text(encoding="utf-8")
        assert '@router.get("/theme/stream")\n@_rl("sse_stream")\n' in real_src, (
            "the fix's exact decorator pair was not found verbatim in the "
            "real routes.py — has the route been refactored since this "
            "test was written?"
        )
        mutated = real_src.replace(
            '@router.get("/theme/stream")\n@_rl("sse_stream")\n',
            '@router.get("/theme/stream")\n',
            1,
        )
        assert mutated != real_src

        mutated_file = tmp_path / "routes.py"
        mutated_file.write_text(mutated, encoding="utf-8")

        result = _run_gate(mutated_file)
        assert result.returncode == 1, (
            f"gate did not FAIL against the reverted-decorator mutation — "
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "'/theme/stream'" in result.stderr
        assert "'/search/stream/{search_id}'" not in result.stderr, (
            "the still-correctly-classed sibling route must not be named "
            "as a finding"
        )


class TestGoldenFalseCorrectlyClassedRoutesAreNeverFlagged:
    """§11.4.201(1): the guard must not over-fire on routes doing the
    right thing, across every idiom combination this codebase actually
    uses."""

    def _fixture(self, body: str) -> str:
        header = textwrap.dedent(
            """\
            from typing import Callable, Any
            from fastapi import APIRouter, Request, Depends
            from fastapi.responses import StreamingResponse, JSONResponse

            router = APIRouter()

            def _rl(class_name):
                def deco(f):
                    return f
                return deco

            def rate_limit_dependency(class_name):
                def _charge(request: Request) -> None:
                    return None
                return _charge

            class SSEHandler:
                @staticmethod
                def create_streaming_response(gen, media_type="text/event-stream"):
                    return StreamingResponse(gen, media_type=media_type)

            """
        )
        return header + textwrap.dedent(body)

    def test_decorator_classed_inline_streaming_response_not_flagged(self, tmp_path):
        src = self._fixture(
            """
            @router.get("/a/stream")
            @_rl("sse_stream")
            async def a_stream(request: Request):
                async def gen():
                    yield b"data: x\\n\\n"
                return StreamingResponse(gen(), media_type="text/event-stream")
            """
        )
        f = tmp_path / "routes.py"
        f.write_text(src, encoding="utf-8")
        result = _run_gate(f)
        assert result.returncode == 0, f"golden-FALSE fixture flagged: {result.stderr}"
        assert "FINDING" not in result.stdout

    def test_decorator_classed_shared_helper_not_flagged(self, tmp_path):
        src = self._fixture(
            """
            @router.get("/b/stream/{sid}")
            @_rl("sse_stream")
            async def b_stream(sid: str, request: Request):
                async def gen():
                    yield b"data: x\\n\\n"
                return SSEHandler.create_streaming_response(gen())
            """
        )
        f = tmp_path / "routes.py"
        f.write_text(src, encoding="utf-8")
        result = _run_gate(f)
        assert result.returncode == 0, f"golden-FALSE fixture flagged: {result.stderr}"
        assert "FINDING" not in result.stdout

    def test_dependency_classed_route_not_flagged(self, tmp_path):
        """The 422-bypass idiom (``POST /search``'s real mechanism):
        classed via a ``Depends(rate_limit_dependency(...))`` dependency
        instead of the ``@_rl`` decorator — must ALSO count as classed."""
        src = self._fixture(
            """
            @router.get(
                "/c/stream",
                dependencies=[Depends(rate_limit_dependency("sse_stream"))],
            )
            async def c_stream(request: Request):
                async def gen():
                    yield b"data: x\\n\\n"
                return StreamingResponse(gen(), media_type="text/event-stream")
            """
        )
        f = tmp_path / "routes.py"
        f.write_text(src, encoding="utf-8")
        result = _run_gate(f)
        assert result.returncode == 0, f"golden-FALSE fixture flagged: {result.stderr}"
        assert "FINDING" not in result.stdout

    def test_non_sse_streaming_response_is_excluded_not_flagged(self, tmp_path):
        """A StreamingResponse whose media_type is NOT text/event-stream
        (e.g. the real /search/sync heartbeat, a torrent download) is a
        different resource shape and must be excluded entirely — never
        counted as SSE-shaped, classed or not."""
        src = self._fixture(
            """
            @router.get("/d/sync")
            async def d_sync(request: Request):
                async def gen():
                    yield b"{}"
                return StreamingResponse(gen(), media_type="application/json")

            @router.get("/e/stream")
            @_rl("sse_stream")
            async def e_stream(request: Request):
                async def gen():
                    yield b"data: x\\n\\n"
                return StreamingResponse(gen(), media_type="text/event-stream")
            """
        )
        f = tmp_path / "routes.py"
        f.write_text(src, encoding="utf-8")
        result = _run_analyzer_json(f)
        assert result.returncode == 0, f"expected PASS: {result.stdout}\n{result.stderr}"
        import json

        payload = json.loads(result.stdout)
        assert payload["sse_shaped_routes"] == 1, (
            f"the application/json heartbeat route was miscounted as "
            f"SSE-shaped: {payload}"
        )
        by_path = {r["path"]: r for r in payload["routes"]}
        assert by_path["/d/sync"]["sse_shaped"] is False
        assert by_path["/e/stream"]["sse_shaped"] is True
        assert by_path["/e/stream"]["classed"] is True


class TestGateFailsOnAGenuinelyUnclassedThirdSSERoute:
    """Proves the GENERAL form: a brand-new, never-seen-before SSE route
    with no class is caught, not merely the two routes this item names."""

    def test_new_unclassed_sse_route_is_flagged(self, tmp_path):
        src = (
            self._noop_header()
            + textwrap.dedent(
                """
                @router.get("/f/stream")
                async def f_stream(request: Request):
                    async def gen():
                        yield b"data: x\\n\\n"
                    return StreamingResponse(gen(), media_type="text/event-stream")
                """
            )
        )
        f = tmp_path / "routes.py"
        f.write_text(src, encoding="utf-8")
        result = _run_gate(f)
        assert result.returncode == 1
        assert "'/f/stream'" in result.stderr

    @staticmethod
    def _noop_header() -> str:
        return textwrap.dedent(
            """\
            from fastapi import APIRouter, Request
            from fastapi.responses import StreamingResponse

            router = APIRouter()

            def _rl(class_name):
                def deco(f):
                    return f
                return deco
            """
        )


class TestZeroSSERoutesIsRefusedNotSilentlyPassed:
    """§11.4.201(6): an extractor that resolves zero SSE routes is a BLIND
    instrument, indistinguishable from a genuinely SSE-route-free file — it
    must ERROR, never report an unverified PASS."""

    def test_file_with_no_sse_routes_errors(self, tmp_path):
        src = textwrap.dedent(
            """\
            from fastapi import APIRouter, Request
            from fastapi.responses import JSONResponse

            router = APIRouter()

            @router.get("/plain")
            def plain(request: Request):
                return JSONResponse({"ok": True})
            """
        )
        f = tmp_path / "routes.py"
        f.write_text(src, encoding="utf-8")
        result = _run_gate(f)
        assert result.returncode == 2, (
            f"expected ERROR(2) on a route-free file, got {result.returncode}: "
            f"{result.stdout}\n{result.stderr}"
        )
        assert "zero SSE-shaped routes" in result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
