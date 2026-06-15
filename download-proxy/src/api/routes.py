"""
API routes for the merge service.
"""

import asyncio
import hmac
import ipaddress
import json
import logging
import os
import re
import socket
import urllib.parse
import uuid
from typing import Annotated, Any

import aiohttp
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from filelock import FileLock
from pydantic import BaseModel, Field

from merge_service.search import SearchResult

try:
    from . import theme_state
except ImportError:  # loaded via importlib.util.spec_from_file_location in tests
    import importlib

    theme_state = importlib.import_module("api.theme_state")

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


def _get_orchestrator(request: Request) -> Any:
    from api import orchestrator_instance

    if orchestrator_instance is not None:
        return orchestrator_instance
    from merge_service.search import SearchOrchestrator

    return SearchOrchestrator()


class ThemeUpdate(BaseModel):
    """Body for ``PUT /api/v1/theme``.

    ``paletteId`` must be one of
    :data:`api.theme_state.ALLOWED_PALETTE_IDS`; ``mode`` must be one
    of :data:`api.theme_state.ALLOWED_MODES`. Validation happens in
    :meth:`api.theme_state.ThemeStore.put` and is surfaced as ``422``
    by the route handler.
    """

    paletteId: str = Field(..., description="One of the catalogued palette ids")
    mode: str = Field(..., description="'light' or 'dark'")


@router.get("/theme")
def get_theme():  # type: ignore[no-untyped-def]
    """Return the current shared theme state (persisted)."""
    return theme_state.get_store().get().to_dict()


@router.put("/theme")
def put_theme(body: ThemeUpdate):  # type: ignore[no-untyped-def]
    """Persist the user's palette + mode choice and fan out to subscribers."""
    try:
        return theme_state.get_store().put(body.paletteId, body.mode).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/theme/stream")
async def stream_theme(request: Request):  # type: ignore[no-untyped-def]
    """SSE feed of theme updates.

    Emits the current state immediately (so late subscribers catch up),
    then one ``event: theme`` line per PUT. A ``: keepalive`` comment
    is sent every 15s when idle so proxies don't hang up the
    connection.
    """

    async def gen():  # type: ignore[no-untyped-def]
        store = theme_state.get_store()
        queue = store.subscribe()
        try:
            current = store.get()
            yield f"event: theme\ndata: {json.dumps(current.to_dict())}\n\n".encode()
            while True:
                if await request.is_disconnected():
                    break
                try:
                    state = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: theme\ndata: {json.dumps(state.to_dict())}\n\n".encode()
                except TimeoutError:
                    yield b": keepalive\n\n"
        finally:
            store.unsubscribe(queue)

    return StreamingResponse(
        gen(),  # type: ignore[no-untyped-call]
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query", min_length=1)
    category: str = Field(default="all", description="Category filter")
    limit: int = Field(default=50, description="Maximum results", ge=1, le=100)
    enable_metadata: bool = Field(default=True, description="Enable metadata enrichment")
    validate_trackers: bool = Field(default=True, description="Validate tracker health")
    sort_by: str = Field(default="seeds", description="Sort column")
    sort_order: str = Field(default="desc", description="Sort direction: asc or desc")
    trackers: list[str] | None = Field(
        default=None,
        description=(
            "Optional provider-selection filter (BUG-1): restrict the search to "
            "this subset of tracker names (case-insensitive). Omit / null / empty "
            "list searches every enabled tracker (back-compat)."
        ),
    )


class SearchResultResponse(BaseModel):
    # Some plugins emit size as an integer (byte count, including the
    # sentinel -1 when unknown) and others as a pre-formatted string
    # like "4.0 GB". Pydantic rejected the int variant and the whole
    # response collapsed with a 500. Allow both and coerce downstream.
    name: str
    size: str | int
    seeds: int
    leechers: int
    download_urls: list[str]
    quality: str | None = None
    content_type: str | None = None
    desc_link: str | None = None
    tracker: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    freeleech: bool = False


class SearchResponse(BaseModel):
    search_id: str
    query: str
    status: str
    results: list[SearchResultResponse] = Field(default_factory=list)
    total_results: int
    merged_results: int
    trackers_searched: list[str] = Field(default_factory=list)
    errors: list[str] = Field(
        default_factory=list,
        description="Per-tracker error strings (e.g. 'rutracker: HTTP 503')",
    )
    tracker_stats: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Per-tracker run-time diagnostics (status, result count, timings, error details, authentication flag)."
        ),
    )
    started_at: str
    completed_at: str | None = None
    stream_token: str | None = Field(
        default=None,
        description=(
            "Per-search SSE bearer token (CONTINUATION #6). Pass it to "
            "GET /search/stream/{search_id} as ?token=<t> or an "
            "Authorization: Bearer header. Required only when the server "
            "runs with SSE_REQUIRE_TOKEN enabled."
        ),
    )


class DownloadRequest(BaseModel):
    result_id: str = Field(..., description="Merged result ID")
    download_urls: list[str] = Field(..., description="URLs to download")


def _parse_size_to_bytes(size_str: str) -> float:
    if not size_str:
        return 0
    try:
        return float(size_str)
    except (ValueError, TypeError):
        pass
    match = re.search(r"([\d.]+)\s*(TB|GB|MB|KB|B)", str(size_str), re.I)
    if match:
        value = float(match.group(1))
        unit = match.group(2).upper()
        mult = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        return value * mult.get(unit, 1)
    return 0


def _detect_quality(name: str, size: str) -> str:
    from merge_service.enricher import MetadataEnricher

    enricher = MetadataEnricher()
    quality = enricher.detect_quality(name)
    if quality:
        mapping = {
            "4K": "uhd_4k",
            "1080p": "full_hd",
            "720p": "hd",
            "SD": "sd",
            "BluRay": "full_hd",
            "BDRip": "full_hd",
            "BDRemux": "uhd_4k",
            "WEB-DL": "hd",
            "WEBRip": "hd",
            "HDRip": "hd",
            "HDTV": "hd",
            "DVD": "sd",
            "DVDRip": "sd",
        }
        return mapping.get(quality, "unknown")
    sb = _parse_size_to_bytes(size)
    if sb >= 40 * 1024**3:
        return "uhd_4k"
    if sb >= 8 * 1024**3:
        return "full_hd"
    if sb >= 2 * 1024**3:
        return "hd"
    if sb >= 300 * 1024**2:
        return "sd"
    return "unknown"


def _to_response(r: SearchResult, content_type: str | None = None) -> SearchResultResponse:
    quality = getattr(r, "quality", None)
    if not quality:
        quality = _detect_quality(r.name, r.size)
    return SearchResultResponse(
        name=r.name,
        size=r.size,
        seeds=r.seeds,
        leechers=r.leechers,
        download_urls=[r.link],
        quality=quality,
        content_type=getattr(r, "content_type", None) or content_type,
        desc_link=r.desc_link,
        tracker=r.tracker,
        sources=[{"tracker": r.tracker, "seeds": r.seeds, "leechers": r.leechers}],
        freeleech=getattr(r, "freeleech", False),
    )


def _serialize_merged_rows(merged: list[Any]) -> list[SearchResultResponse]:
    """Serialize a list of ``MergedResult`` into response rows.

    Single source of truth for the merged→response-row mapping, called
    from BOTH ``get_search`` (the final GET payload) AND the SSE
    ``merged_update`` stream emission, so the live-streamed merged set is
    BYTE-IDENTICAL to what ``GET /search/{id}`` returns. This is the hard
    requirement behind progressive de-duplicated streaming — the last
    streamed merged set MUST equal the final get_search set so the grid
    never swaps a large raw list for a smaller merged one on completion.
    """
    rows: list[SearchResultResponse] = []
    for m in merged:
        best = m.original_results[0] if m.original_results else None
        if not best:
            continue
        ct = m.canonical_identity.content_type.value if m.canonical_identity else None
        resp = _to_response(best, ct)
        resp.sources = [
            {"tracker": orig.tracker, "seeds": orig.seeds, "leechers": orig.leechers} for orig in m.original_results
        ]
        resp.download_urls = list(dict.fromkeys(lnk for lnk in (orig.link for orig in m.original_results)))
        resp.seeds = m.total_seeds
        resp.leechers = m.total_leechers
        rows.append(resp)
    return rows


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, req: Request):  # type: ignore[no-untyped-def]
    """Kick off a search and return immediately.

    The endpoint returns ``status: "running"`` as soon as the search
    metadata is created — the actual tracker fan-out runs in a
    background ``asyncio.Task`` so the client can attach to
    ``/api/v1/search/stream/{search_id}`` and see results arrive
    live instead of waiting for the slowest tracker.

    When the orchestrator is already at ``MAX_CONCURRENT_SEARCHES``
    in-flight fan-outs, we return HTTP 429 so callers back off.
    Without this cap, stress tests revealed the event loop starves
    and even ``/health`` starts timing out.
    """
    import asyncio

    from .hooks import dispatch_event

    orch = _get_orchestrator(req)

    if orch.is_search_queue_full():
        raise HTTPException(
            status_code=429,
            detail=(
                f"merge service has reached MAX_CONCURRENT_SEARCHES ({orch._max_concurrent_searches}); retry shortly"
            ),
        )

    await dispatch_event("search_start", {"query": request.query})

    metadata = orch.start_search(
        query=request.query,
        category=request.category,
        enable_metadata=False,
        validate_trackers=request.validate_trackers,
        trackers=request.trackers,
    )

    # Fire-and-forget: the task populates _tracker_results incrementally
    # and flips metadata.status to 'completed' when done.
    async def _background() -> None:
        try:
            await orch._run_search(
                metadata.search_id,
                request.query,
                request.category,
            )
            await dispatch_event(
                "search_complete",
                {
                    "search_id": metadata.search_id,
                    "query": metadata.query,
                    "total_results": metadata.total_results,
                    "merged_results": metadata.merged_results,
                    "trackers_searched": metadata.trackers_searched,
                    # W1 (BUG-7 follow-up): the dashboard's PRIMARY path is this
                    # SSE event, so the distinct "all_trackers_errored" status and
                    # the per-tracker errors MUST ride along — otherwise a search
                    # where every tracker failed (bad creds/CAPTCHA) looks identical
                    # to a genuinely-empty one and the user sees a misleading
                    # "No results found." instead of an actionable banner.
                    "status": metadata.status,
                    "errors": metadata.errors,
                },
            )
        except Exception as e:
            logger.error(f"Background search {metadata.search_id} failed: {e}")

    task = asyncio.create_task(_background())
    orch._search_tasks[metadata.search_id] = task

    # Mint the per-search SSE bearer token so the client can authorise its
    # stream connection (CONTINUATION #6).
    stream_token = orch.issue_stream_token(metadata.search_id)

    # Return immediately — the caller should attach to SSE for real-time
    # results.  Any callers that want the old blocking behaviour can hit
    # GET /api/v1/search/{search_id} once status goes to 'completed'.
    return SearchResponse(
        search_id=metadata.search_id,
        query=metadata.query,
        status="running",
        results=[],
        total_results=0,
        merged_results=0,
        trackers_searched=metadata.trackers_searched,
        tracker_stats=metadata.to_dict()["tracker_stats"],
        started_at=metadata.started_at.isoformat(),
        completed_at=None,
        stream_token=stream_token,
    )


@router.post("/search/sync", response_model=SearchResponse)
async def search_sync(request: SearchRequest, req: Request):  # type: ignore[no-untyped-def]
    """Blocking search (legacy behaviour).

    Preserved for tests and schedulers that need the full merged result
    set in a single response.  Real-time clients should use
    ``POST /search`` + ``GET /search/stream/{search_id}``.
    """

    from .hooks import dispatch_event

    orch = _get_orchestrator(req)

    if orch.is_search_queue_full():
        raise HTTPException(
            status_code=429,
            detail=(
                f"merge service has reached MAX_CONCURRENT_SEARCHES ({orch._max_concurrent_searches}); retry shortly"
            ),
        )

    await dispatch_event("search_start", {"query": request.query})

    metadata = await orch.search(
        query=request.query,
        category=request.category,
        enable_metadata=False,
        validate_trackers=request.validate_trackers,
        trackers=request.trackers,
    )

    stored = orch._last_merged_results.get(metadata.search_id)
    merged = stored[0] if stored else []
    results = []
    for m in merged:
        best = m.original_results[0] if m.original_results else None
        if not best:
            continue
        content_type = (
            m.canonical_identity.content_type.value
            if m.canonical_identity and m.canonical_identity.content_type
            else None
        )
        resp = _to_response(best, content_type=content_type)
        resp.sources = [{"tracker": r.tracker, "seeds": r.seeds, "leechers": r.leechers} for r in m.original_results]
        resp.download_urls = list(dict.fromkeys(r.link for r in m.original_results))
        resp.seeds = m.total_seeds
        resp.leechers = m.total_leechers
        results.append(resp)

    # Apply sorting
    sort_by = request.sort_by
    sort_order = request.sort_order
    reverse = sort_order == "desc"
    sort_weights = {"unknown": 0, "sd": 1, "hd": 2, "full_hd": 3, "uhd_4k": 4, "uhd_8k": 5}

    def _sort_key(x):  # type: ignore[no-untyped-def]
        if sort_by == "name":
            return (x.name or "").lower()
        if sort_by == "type":
            return x.content_type or "unknown"
        if sort_by == "size":
            return _parse_size_to_bytes(x.size)
        if sort_by == "seeds":
            return x.seeds
        if sort_by == "leechers":
            return x.leechers
        if sort_by == "quality":
            return sort_weights.get(x.quality or "unknown", 0)
        if sort_by == "sources":
            return len(x.sources)
        return x.seeds

    results.sort(key=_sort_key, reverse=reverse)
    results = results[: request.limit]

    if request.enable_metadata and hasattr(req.app.state, "enricher"):
        from merge_service.enricher import MetadataEnricher

        enricher: MetadataEnricher = req.app.state.enricher
        for r in results[:10]:
            try:
                meta = await enricher.resolve(r.name)
                if meta:
                    r.metadata = {
                        "source": meta.source,
                        "title": meta.title,
                        "year": meta.year,
                        "content_type": meta.content_type,
                        "poster_url": meta.poster_url,
                        "overview": meta.overview,
                        "genres": meta.genres,
                    }
            except Exception as e:
                logger.debug(f"Metadata enrichment failed for {r.name}: {e}")

    captcha_errors = [e for e in metadata.errors if "captcha" in e.lower()]
    if captcha_errors and not results:
        return JSONResponse(
            status_code=403,
            content={
                "search_id": metadata.search_id,
                "query": metadata.query,
                "status": "captcha_required",
                "results": [],
                "total_results": 0,
                "merged_results": 0,
                "trackers_searched": metadata.trackers_searched,
                "errors": metadata.errors,
                "tracker_stats": metadata.to_dict()["tracker_stats"],
                "message": "RuTracker requires CAPTCHA. Use /api/v1/auth/rutracker/captcha to solve it.",
                "started_at": metadata.started_at.isoformat(),
                "completed_at": metadata.completed_at.isoformat() if metadata.completed_at else None,
            },
        )

    response = SearchResponse(
        search_id=metadata.search_id,
        query=metadata.query,
        status="completed" if metadata.total_results > 0 else "no_results",
        results=results,
        total_results=metadata.total_results,
        merged_results=len(merged),
        trackers_searched=metadata.trackers_searched,
        errors=metadata.errors,
        tracker_stats=metadata.to_dict()["tracker_stats"],
        started_at=metadata.started_at.isoformat(),
        completed_at=metadata.completed_at.isoformat() if metadata.completed_at else None,
    )

    await dispatch_event(
        "search_complete",
        {
            "search_id": metadata.search_id,
            "query": metadata.query,
            "total_results": metadata.total_results,
            "merged_results": len(merged),
            "trackers_searched": metadata.trackers_searched,
        },
    )

    return response


_sse_stream_count = 0
_SSE_STREAM_MAX = int(os.environ.get("MAX_CONCURRENT_SSE_STREAMS", "32"))


def _sse_require_token() -> bool:
    """Whether SSE streams must carry a valid per-search token.

    Read per-request (not cached at import) so operators can toggle it
    without restarting tests. Default off so the shipped dashboard keeps
    working over the UUID barrier alone; flip ``SSE_REQUIRE_TOKEN`` to a
    truthy value (1/true/yes/on) to harden (CONTINUATION #6).
    """
    return os.environ.get("SSE_REQUIRE_TOKEN", "").strip().lower() in ("1", "true", "yes", "on")


def _supplied_stream_token(req: Request, token: str | None) -> str | None:
    """Pull the stream token from the ``?token=`` query param (EventSource
    can't set headers) or an ``Authorization: Bearer`` header."""
    if token:
        return token
    auth = req.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


@router.get("/search/stream/{search_id}")
async def search_stream(search_id: str, req: Request, token: str | None = None):  # type: ignore[no-untyped-def]
    from fastapi.responses import StreamingResponse  # noqa: F401

    from .streaming import SSEHandler

    global _sse_stream_count
    orch = _get_orchestrator(req)
    # 404 up front for unknown search IDs so clients (and the
    # integration tests that probe this path) don't hang on an
    # open SSE socket waiting for events that will never come.
    if search_id not in orch._active_searches:
        raise HTTPException(status_code=404, detail="Search not found")
    # Per-search bearer-token gate (opt-in via SSE_REQUIRE_TOKEN). The 404
    # above intentionally precedes this so token probes can't enumerate
    # which search IDs exist.
    if _sse_require_token() and not orch.validate_stream_token(search_id, _supplied_stream_token(req, token)):
        raise HTTPException(status_code=403, detail="Invalid or missing stream token")
    # Cap concurrent open SSE streams. Each stream reserves an event
    # loop task and holds a tracker_results dict pointer; without a
    # cap a trivial client loop can exhaust sockets/fds.
    if _sse_stream_count >= _SSE_STREAM_MAX:
        raise HTTPException(
            status_code=429,
            detail=(f"merge service has {_SSE_STREAM_MAX} open SSE streams — retry shortly"),
        )

    async def _wrapped():  # type: ignore[no-untyped-def]
        global _sse_stream_count
        _sse_stream_count += 1
        try:
            async for frame in SSEHandler.search_results_stream(search_id, orch, request=req):
                yield frame
        finally:
            _sse_stream_count = max(0, _sse_stream_count - 1)

    return SSEHandler.create_streaming_response(_wrapped())  # type: ignore[no-untyped-call]


@router.get("/search/{search_id}", response_model=SearchResponse)
async def get_search(search_id: str, req: Request, limit: int = 0):  # type: ignore[no-untyped-def]
    orch = _get_orchestrator(req)
    metadata = orch.get_search_status(search_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Search not found")
    result_resp = []
    stored = orch._last_merged_results.get(search_id)
    if stored:
        merged, _all_results = stored
        # Return the FULL merged result set by default (limit<=0) so the grid the
        # user sees after `search_complete` matches the live-streamed list. A
        # hardcoded ``merged[:50]`` collapsed e.g. 2153 streamed results to 50 —
        # the "just a fraction of results" defect. The grid uses cdk
        # virtual-scroll, so rendering the full set is cheap. Optional ``?limit=N``
        # truncates for callers that explicitly want a smaller page.
        display = merged if limit <= 0 else merged[: max(0, limit)]
        result_resp = _serialize_merged_rows(display)
    return SearchResponse(
        search_id=metadata.search_id,
        query=metadata.query,
        status=metadata.status,
        results=result_resp,
        total_results=metadata.total_results,
        merged_results=metadata.merged_results,
        trackers_searched=metadata.trackers_searched,
        errors=metadata.errors,
        tracker_stats=metadata.to_dict()["tracker_stats"],
        started_at=metadata.started_at.isoformat(),
        completed_at=metadata.completed_at.isoformat() if metadata.completed_at else None,
    )


@router.post("/search/{search_id}/abort")
async def abort_search(search_id: str, req: Request):  # type: ignore[no-untyped-def]
    """Cancel a running search and its background tracker tasks."""
    orch = _get_orchestrator(req)
    if search_id in orch._active_searches:
        orch.cancel_search(search_id)
        return {"search_id": search_id, "status": "aborted"}
    return {"search_id": search_id, "status": "not_found"}


@router.get("/downloads/active")
async def get_active_downloads():  # type: ignore[no-untyped-def]

    qbit_url = os.getenv("QBITTORRENT_URL", "http://localhost:7185")
    qbit_user = _get_qbit_username()  # type: ignore[no-untyped-call]
    qbit_pass = _get_qbit_password()  # type: ignore[no-untyped-call]

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                f"{qbit_url}/api/v2/auth/login",
                data={"username": qbit_user, "password": qbit_pass},
            ) as resp:
                login_text = await resp.text()
                cookies = resp.cookies
                if not _qbit_login_succeeded(resp.status, login_text, cookies):
                    return {"downloads": [], "count": 0, "error": "auth failed"}

            async with session.get(f"{qbit_url}/api/v2/torrents/info", cookies=cookies) as resp:
                if resp.status == 200:
                    torrents = await resp.json()
                    downloads = []
                    for t in torrents:
                        downloads.append(
                            {
                                "name": t.get("name", ""),
                                "size": t.get("size", 0),
                                "progress": round(t.get("progress", 0) * 100, 1),
                                "dlspeed": t.get("dlspeed", 0),
                                "upspeed": t.get("upspeed", 0),
                                "state": t.get("state", ""),
                                "hash": t.get("hash", ""),
                                "eta": t.get("eta", 8640000),
                            }
                        )
                    return {"downloads": downloads, "count": len(downloads)}
    except Exception as e:
        logger.error(f"Failed to get active downloads: {e}")

    return {"downloads": [], "count": 0, "error": "unavailable"}


@router.post("/auth/qbittorrent")
async def auth_qbittorrent(request: Request):  # type: ignore[no-untyped-def]
    from pydantic import BaseModel

    class QBitLoginRequest(BaseModel):
        username: str = "admin"
        password: str = "admin"  # noqa: S105
        save: bool = False

    try:
        data = await request.json()
        req = QBitLoginRequest(**data)
    except Exception:
        req = QBitLoginRequest()

    qbit_url = os.getenv("QBITTORRENT_URL", "http://localhost:7185")

    try:
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session,
            session.post(
                f"{qbit_url}/api/v2/auth/login",
                data={"username": req.username, "password": req.password},
            ) as resp,
        ):
            login_text = await resp.text()
            cookies = resp.cookies
            if _qbit_login_succeeded(resp.status, login_text, cookies):
                async with session.get(f"{qbit_url}/api/v2/app/version", cookies=cookies) as vresp:
                    version = await vresp.text() if vresp.status == 200 else "unknown"

                if req.save:
                    creds_dir = "/config/download-proxy"
                    _save_qbit_credentials(
                        f"{creds_dir}/qbittorrent_creds.json",
                        {"username": req.username, "password": req.password},
                    )

                return {
                    "status": "authenticated",
                    "version": version,
                    "message": "Login successful",
                }
            else:
                return {
                    "status": "failed",
                    "error": "Invalid credentials",
                }
    except Exception as e:
        logger.error(f"qBittorrent auth error: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


def _save_qbit_credentials(path: str, data: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lock = FileLock(path + ".lock")
        with lock, open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save qBittorrent credentials: {e}")


def _load_saved_qbit_credentials():  # type: ignore[no-untyped-def]
    import json
    import os

    creds_file = "/config/download-proxy/qbittorrent_creds.json"
    if os.path.isfile(creds_file):
        try:
            with open(creds_file) as f:
                return json.load(f)
        except Exception:  # noqa: S110
            pass
    return None


def _get_qbit_password():  # type: ignore[no-untyped-def]
    saved = _load_saved_qbit_credentials()  # type: ignore[no-untyped-call]
    if saved:
        return saved.get("password", os.getenv("QBITTORRENT_PASS", "admin"))
    return os.getenv("QBITTORRENT_PASS", "admin")


def _get_qbit_username():  # type: ignore[no-untyped-def]
    saved = _load_saved_qbit_credentials()  # type: ignore[no-untyped-call]
    if saved:
        return saved.get("username", os.getenv("QBITTORRENT_USER", "admin"))
    return os.getenv("QBITTORRENT_USER", "admin")


def _qbit_login_succeeded(status, body, cookies):  # type: ignore[no-untyped-def]
    """Detect a successful qBittorrent ``/api/v2/auth/login`` across versions.

    Legacy qBittorrent (<4.6) replies ``200`` with body ``Ok.``; modern
    qBittorrent (4.6+/5.x, as shipped by ``linuxserver/qbittorrent:latest``)
    replies ``204 No Content`` with an EMPTY body. Both issue the ``QBT_SID``
    session cookie on success; a rejected login replies ``200 Fails.`` with no
    cookie. The authoritative, version-independent success signal is therefore
    "the server issued a session cookie", with the legacy ``Ok.`` body kept as
    a fallback. Requiring ``status == 200 and body == 'Ok.'`` (the old check)
    mis-classifies the modern 204 as ``auth_failed`` even though login worked —
    the real defect surfaced by the live :7187 round-trip.
    """
    if status not in (200, 204):
        return False
    # qBittorrent's session cookie is ``QBT_SID`` (or ``QBT_SID_<port>``). Match
    # it exactly/by prefix — a loose ``"SID" in key`` substring test would treat
    # a foreign ``*SID*`` cookie (PHPSESSID, BSSID, …) as a successful login.
    has_session_cookie = any(c.key == "QBT_SID" or c.key.startswith("QBT_SID_") for c in cookies.values())
    return has_session_cookie or body.strip() == "Ok."


def _qbit_add_succeeded(status, body):  # type: ignore[no-untyped-def]
    """Detect a successful qBittorrent ``/api/v2/torrents/add`` across versions.

    Legacy qBittorrent (<5.x) replies ``200`` with body ``Ok.`` (``Fails.`` on
    rejection). Modern qBittorrent (5.x, as shipped by
    ``linuxserver/qbittorrent:latest``) replies ``200`` with a JSON summary::

        {"added_torrent_ids":["<hash>"],"failure_count":0,
         "pending_count":0,"success_count":1}

    The torrent landed when ``success_count`` or ``pending_count`` is >= 1, or
    ``added_torrent_ids`` is non-empty (``pending_count`` covers a magnet whose
    metadata is still resolving — it IS accepted into the session). Requiring
    ``body.lower().startswith('ok')`` mis-classifies the modern JSON success as
    ``failed`` even though the torrent was added — the real defect surfaced by
    the live :7187 round-trip.

    A ``409 Conflict`` is also a SUCCESS: qBittorrent returns it when the
    torrent is already in the session (a duplicate add). Adding is idempotent
    from the user's view — the torrent IS present — and a client retry of this
    non-idempotent POST (e.g. BobaClient retrying after attempt 1 timed out
    client-side but already landed server-side) produces exactly this. Treating
    the duplicate as success makes the add retry-safe.
    """
    if status == 409:
        return True
    if status not in (200, 201):
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
    # Coerce defensively — a malformed body like ``{"success_count":"N/A"}`` must
    # classify as failure, never raise (``int("N/A")`` would crash the add path).
    try:
        success = int(payload.get("success_count") or 0)
        pending = int(payload.get("pending_count") or 0)
    except (ValueError, TypeError):
        return False
    return success >= 1 or pending >= 1


TRACKER_DOMAINS = (
    "rutracker.org",
    "rutracker.nl",
    "kinozal.tv",
    "kinozal.guru",
    "nnmclub.to",
    "nnmclub.ro",
    "nnm-club.me",
    "iptorrents.com",
    "iptorrents.me",
)


def _is_tracker_url(url: str) -> str | None:
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
        for domain in TRACKER_DOMAINS:
            if host == domain or host.endswith("." + domain):
                if "rutracker" in domain:
                    return "rutracker"
                if "kinozal" in domain:
                    return "kinozal"
                if "nnmclub" in domain or "nnm-club" in domain:
                    return "nnmclub"
                if "iptorrents" in domain:
                    return "iptorrents"
    except Exception as e:
        logger.debug(f"Could not identify tracker from URL: {e}")
    return None


def require_api_token(request: Request) -> None:
    """Optional, env-gated shared-secret gate for the download-WRITE endpoints.

    Read the token from the environment AT REQUEST TIME (not import time) so
    operators can toggle it without restarting and so tests can monkeypatch
    ``BOBA_API_TOKEN``.

    * ``BOBA_API_TOKEN`` unset/empty -> return (OPEN). This is the DEFAULT and
      preserves the current no-auth contract + dev workflow (§11.4.122).
    * ``BOBA_API_TOKEN`` set -> the request MUST present a MATCHING token in
      either ``Authorization: Bearer <token>`` OR ``X-Boba-Token: <token>``.
      Comparison is constant-time (``hmac.compare_digest``). Missing/mismatch
      -> ``401``.

    §11.4.10: the token value and the supplied header value are NEVER logged.
    """
    token = os.getenv("BOBA_API_TOKEN", "").strip()
    if not token:
        return  # OPEN — default, no-auth contract preserved.

    supplied = ""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    if not supplied:
        supplied = request.headers.get("x-boba-token", "").strip()

    if not supplied or not hmac.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Unauthorized: valid API token required")


def _is_safe_fetch_url(url: str) -> bool:
    """SSRF guard for server-side fetches of user-supplied URLs (RW-03).

    Returns ``True`` ONLY for an ``http(s)`` URL whose host resolves entirely
    to public IP addresses. Rejects (returns ``False``) when the scheme is not
    http/https, the host is missing, DNS resolution fails, or ANY resolved
    address is loopback / private (RFC-1918) / link-local (incl. the
    ``169.254.169.254`` cloud-metadata endpoint) / multicast / reserved /
    unspecified.

    A caller could otherwise make the proxy GET ``http://169.254.169.254/``,
    ``http://127.0.0.1:7185/``, or LAN/RFC-1918 hosts and receive the body.
    Legit public tracker URLs and magnets (which do no fetch) are unaffected.

    The DNS lookup is bounded by a short ``socket.setdefaulttimeout`` window so
    the SSRF check never blocks the request indefinitely on a hostile/slow
    resolver. ``getaddrinfo`` covers every A/AAAA record so a multi-record host
    cannot smuggle one private address past the check.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except (ValueError, TypeError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False

    prev_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(5)
        infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, OSError, UnicodeError, ValueError):
        return False
    finally:
        socket.setdefaulttimeout(prev_timeout)

    addresses = {info[4][0] for info in infos}
    if not addresses:
        return False
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr.split("%", 1)[0])  # strip IPv6 zone id
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


@router.post("/download")
async def initiate_download(
    request: DownloadRequest, req: Request, _: None = Depends(require_api_token)
):  # type: ignore[no-untyped-def]
    import tempfile

    from .hooks import dispatch_event

    download_id = str(uuid.uuid4())

    await dispatch_event(
        "download_start",
        {
            "download_id": download_id,
            "result_id": request.result_id,
            "url_count": len(request.download_urls),
        },
    )
    qbit_url = os.getenv("QBITTORRENT_URL", "http://localhost:7185")
    qbit_user = _get_qbit_username()  # type: ignore[no-untyped-call]
    qbit_pass = _get_qbit_password()  # type: ignore[no-untyped-call]

    results = []

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(
                f"{qbit_url}/api/v2/auth/login",
                data={"username": qbit_user, "password": qbit_pass},
            ) as resp:
                login_text = await resp.text()
                qbit_cookies = resp.cookies
                if not _qbit_login_succeeded(resp.status, login_text, qbit_cookies):
                    return {
                        "download_id": download_id,
                        "status": "auth_failed",
                        "results": [],
                    }

            for url in request.download_urls[:5]:
                try:
                    tracker = _is_tracker_url(url)
                    if tracker:
                        orch = _get_orchestrator(req)
                        torrent_data = await orch.fetch_torrent(tracker, url)
                        if torrent_data is None:
                            results.append(
                                {
                                    "url": url,
                                    "status": "failed",
                                    "detail": "could not fetch torrent file from tracker",
                                }
                            )
                            continue
                        with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as tmp:
                            tmp.write(torrent_data)
                            tmp_path = tmp.name
                        try:
                            with open(tmp_path, "rb") as f:  # noqa: ASYNC230
                                form = aiohttp.FormData()
                                form.add_field(
                                    "torrents",
                                    f,
                                    filename=f"{tracker}_{download_id[:8]}.torrent",
                                    content_type="application/x-bittorrent",
                                )
                                async with session.post(
                                    f"{qbit_url}/api/v2/torrents/add",
                                    data=form,
                                    cookies=qbit_cookies,
                                ) as add_resp:
                                    # qBittorrent returns 200 with body
                                    # ``Ok.`` on success and ``Fails.`` on
                                    # rejection — so status alone lies.
                                    body = (await add_resp.text()).strip()
                                    if _qbit_add_succeeded(add_resp.status, body):
                                        results.append(
                                            {
                                                "url": url,
                                                "status": "added",
                                                "method": "proxy",
                                            }
                                        )
                                    else:
                                        results.append(
                                            {
                                                "url": url,
                                                "status": "failed",
                                                "detail": body[:200] or f"HTTP {add_resp.status}",
                                            }
                                        )
                        finally:
                            os.unlink(tmp_path)
                    else:
                        async with session.post(
                            f"{qbit_url}/api/v2/torrents/add",
                            data={"urls": url},
                            cookies=qbit_cookies,
                        ) as resp:
                            body = (await resp.text()).strip()
                            if _qbit_add_succeeded(resp.status, body):
                                results.append({"url": url, "status": "added"})
                            else:
                                results.append(
                                    {
                                        "url": url,
                                        "status": "failed",
                                        "detail": body[:200] or f"HTTP {resp.status}",
                                    }
                                )
                except Exception as e:
                    results.append({"url": url, "status": "error", "message": str(e)})
                # A merged content row's download_urls are many DISTINCT
                # tracker-copies of ONE item. Add the best (first) source and
                # stop — never fan one content item out into N torrents in the
                # client. Fall through to the next source ONLY if this one
                # failed (primary-with-fallback). Single-source rows are
                # unaffected (their list has one URL).
                if results and results[-1].get("status") == "added":
                    break
    except Exception as e:
        return {
            "download_id": download_id,
            "status": "connection_failed",
            "error": str(e),
        }

    added_count = sum(1 for r in results if r.get("status") == "added")

    await dispatch_event(
        "download_complete",
        {
            "download_id": download_id,
            "result_id": request.result_id,
            "added_count": added_count,
            "total_urls": len(request.download_urls),
        },
    )

    return {
        "download_id": download_id,
        "status": "initiated" if added_count > 0 else "failed",
        "urls_count": len(request.download_urls),
        "added_count": added_count,
        "results": results,
    }


# Raw .torrent uploads (browser-extension picks a local file): the extension
# POSTs the file bytes as multipart, and we forward them to qBittorrent exactly
# like the tracker-fetched path above (routes.py:810-822). 10 MiB is generous —
# real .torrent metainfo files are KiB-to-low-MiB even for huge payloads.
_MAX_TORRENT_UPLOAD_BYTES = 10 * 1024 * 1024


def _looks_like_torrent(data: bytes) -> bool:
    """Cheap content sniff: a .torrent is a bencoded dict (starts with ``d``)
    and every real metainfo carries an ``info`` dict. We do not fully parse —
    just reject obvious non-torrents (HTML, JSON, binary garbage) before
    forwarding bytes to qBittorrent."""
    if not data.startswith(b"d"):
        return False
    return b"4:infod" in data[:4096] or b"infod" in data[:4096]


@router.post("/download/upload")
async def upload_torrent(
    file: Annotated[UploadFile, File()], _: None = Depends(require_api_token)
):  # type: ignore[no-untyped-def]
    """Accept a raw ``.torrent`` file (multipart ``file`` field) and add it to
    qBittorrent.

    Mirrors the auth + multipart-forward pattern of ``/api/v1/download``
    (routes.py:776-789 login, routes.py:810-822 ``torrents`` form upload) but
    takes the bytes directly from the upload instead of fetching a URL. Returns
    a user-observable body ``{download_id, status, filename, detail}``.
    """
    from .hooks import dispatch_event

    download_id = str(uuid.uuid4())
    filename = os.path.basename(file.filename or "uploaded.torrent")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded .torrent file is empty")
    if len(data) > _MAX_TORRENT_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded .torrent file exceeds the 10 MiB limit ({len(data)} bytes)",
        )
    if not _looks_like_torrent(data):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid .torrent (bencode sniff failed)")

    await dispatch_event(
        "download_start",
        {"download_id": download_id, "result_id": filename, "url_count": 1},
    )

    qbit_url = os.getenv("QBITTORRENT_URL", "http://localhost:7185")
    qbit_user = _get_qbit_username()  # type: ignore[no-untyped-call]
    qbit_pass = _get_qbit_password()  # type: ignore[no-untyped-call]

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(
                f"{qbit_url}/api/v2/auth/login",
                data={"username": qbit_user, "password": qbit_pass},
            ) as resp:
                login_text = await resp.text()
                qbit_cookies = resp.cookies
                if not _qbit_login_succeeded(resp.status, login_text, qbit_cookies):
                    return {
                        "download_id": download_id,
                        "status": "auth_failed",
                        "filename": filename,
                    }

            form = aiohttp.FormData()
            form.add_field(
                "torrents",
                data,
                filename=filename,
                content_type="application/x-bittorrent",
            )
            async with session.post(
                f"{qbit_url}/api/v2/torrents/add",
                data=form,
                cookies=qbit_cookies,
            ) as add_resp:
                body = (await add_resp.text()).strip()
                added = _qbit_add_succeeded(add_resp.status, body)
    except Exception as e:
        return {
            "download_id": download_id,
            "status": "connection_failed",
            "filename": filename,
            "error": str(e),
        }

    await dispatch_event(
        "download_complete",
        {"download_id": download_id, "result_id": filename, "added_count": 1 if added else 0, "total_urls": 1},
    )

    if added:
        return {"download_id": download_id, "status": "added", "filename": filename, "method": "upload"}
    return {
        "download_id": download_id,
        "status": "failed",
        "filename": filename,
        "detail": body[:200] or f"HTTP {add_resp.status}",
    }


@router.post("/download/file")
async def download_torrent_file(
    request: DownloadRequest, req: Request, _: None = Depends(require_api_token)
):  # type: ignore[no-untyped-def]
    """Download the first available .torrent file from the result's URLs."""

    orch = _get_orchestrator(req)

    for url in request.download_urls[:5]:
        try:
            tracker = _is_tracker_url(url)
            if tracker:
                torrent_data = await orch.fetch_torrent(tracker, url)
                if torrent_data:
                    from io import BytesIO

                    from fastapi.responses import StreamingResponse

                    return StreamingResponse(
                        BytesIO(torrent_data),
                        media_type="application/x-bittorrent",
                        headers={
                            "Content-Disposition": f'attachment; filename="{tracker}_{request.result_id}.torrent"'
                        },
                    )
            elif url.startswith("magnet:"):
                # For magnet links, return as a .magnet text file
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse(
                    url,
                    headers={
                        "Content-Disposition": f'attachment; filename="{request.result_id}.magnet"',
                        "Content-Type": "text/plain; charset=utf-8",
                    },
                )
            else:
                # Try to fetch direct URL — but only after the SSRF guard
                # (RW-03) confirms the host resolves to a public address.
                # Reject (skip to the next URL) otherwise so a caller cannot
                # make the proxy fetch loopback / RFC-1918 / cloud-metadata
                # targets and receive the body.
                if not _is_safe_fetch_url(url):
                    logger.warning("Refusing SSRF-unsafe download URL (non-public target); skipping")
                    continue
                async with (
                    aiohttp.ClientSession() as session,
                    session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp,
                ):
                    if resp.status == 200:
                        data = await resp.read()
                        from io import BytesIO

                        from fastapi.responses import StreamingResponse

                        filename = url.split("/")[-1] or f"{request.result_id}.torrent"
                        return StreamingResponse(
                            BytesIO(data),
                            media_type="application/x-bittorrent",
                            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                        )
        except Exception:  # noqa: S112
            continue

    raise HTTPException(status_code=404, detail="No downloadable torrent file found")


@router.post("/magnet")
async def generate_magnet(
    request: Request, _: None = Depends(require_api_token)
):  # type: ignore[no-untyped-def]
    from pydantic import BaseModel

    class MagnetRequest(BaseModel):
        result_id: str
        download_urls: list[str]

    try:
        data = await request.json()
        req = MagnetRequest(**data)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid request"})

    urls = req.download_urls
    hashes = []
    trackers = set()
    for url in urls:
        m = re.search(r"btih:([a-f0-9]{40}|[a-f0-9]{32})", url, re.I)
        if m:
            hashes.append(m.group(1))
        # Extract trackers from magnet links
        if url.startswith("magnet:"):
            for tr in re.findall(r"tr=([^&]+)", url):
                trackers.add(urllib.parse.unquote(tr))

    name = req.result_id or "download"
    dn = urllib.parse.quote(name)
    # A magnet identifies ONE torrent, so it carries exactly ONE xt. A merged
    # content row aggregates many DISTINCT tracker-copies (each a different
    # infohash) of the same item — joining every infohash produced a malformed
    # multi-xt magnet that qBittorrent rejects (live defect, 2026-06-14: an
    # Ubuntu merged row yielded a 21-xt magnet). Use the PRIMARY (first =
    # best/highest-seeded) source only; trackers from ALL sources are still
    # aggregated above to enrich that single torrent's swarm.
    xt = f"xt=urn:btih:{hashes[0]}" if hashes else ""
    # Include source trackers + fallback public trackers
    default_trackers = [
        "udp://tracker.opentrackr.org:1337",
        "udp://tracker.leechers.org:6969",
    ]
    for dt in default_trackers:
        trackers.add(dt)
    tr_params = "&".join(f"tr={urllib.parse.quote(t)}" for t in sorted(trackers))
    magnet = f"magnet:?dn={dn}" + (f"&{xt}" if xt else "")
    if tr_params:
        magnet += "&" + tr_params

    return {"magnet": magnet, "hashes": hashes}


__all__ = ["router"]
