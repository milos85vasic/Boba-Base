"""
FastAPI application and router setup for the merge service.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

_angular_dist_path = os.path.join(os.path.dirname(__file__), "..", "ui", "dist", "frontend", "browser")
_angular_dist_path = os.path.normpath(_angular_dist_path)
_angular_index_path = os.path.join(_angular_dist_path, "index.html")
_angular_available = os.path.isfile(_angular_index_path)

logger = logging.getLogger(__name__)

orchestrator_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    global orchestrator_instance

    logger.info("Starting Merge Service API...")

    from merge_service.enricher import MetadataEnricher
    from merge_service.scheduler import Scheduler
    from merge_service.search import SearchOrchestrator
    from merge_service.validator import TrackerValidator

    app.state.search_orchestrator = SearchOrchestrator()
    app.state.validator = TrackerValidator()
    app.state.enricher = MetadataEnricher()
    orchestrator_instance = app.state.search_orchestrator

    app.state.scheduler = Scheduler()
    await app.state.scheduler.load()
    app.state.scheduler.set_search_callback(lambda q, c: app.state.search_orchestrator.search(query=q, category=c))
    await app.state.scheduler.start()

    # Jackett auto-configuration — best-effort, never blocks boot.
    from merge_service.jackett_autoconfig import autoconfigure_jackett

    jackett_url = os.getenv("JACKETT_URL", "http://localhost:9117")
    jackett_key = os.getenv("JACKETT_API_KEY", "")
    if jackett_key and jackett_key != "YOUR_API_KEY_HERE":
        try:
            app.state.jackett_autoconfig_last = await autoconfigure_jackett(
                jackett_url=jackett_url,
                api_key=jackett_key,
                env=os.environ,
            )
            r = app.state.jackett_autoconfig_last
            logger.info(
                "Jackett autoconfig: discovered=%d configured_now=%d already=%d errors=%d",
                len(r.discovered_credentials),
                len(r.configured_now),
                len(r.already_present),
                len(r.errors),
            )
        except Exception:
            logger.exception("Jackett autoconfig failed unexpectedly")
            app.state.jackett_autoconfig_last = None
    else:
        logger.info("Jackett autoconfig: skipped (no API key)")
        app.state.jackett_autoconfig_last = None

    logger.info("Merge Service API started")

    yield

    await app.state.scheduler.stop()
    if hasattr(app.state, "validator") and app.state.validator:
        await app.state.validator.close()
    logger.info("Merge Service API stopped")


app = FastAPI(
    title="Боба Search Service",
    description="Search and merge results across multiple torrent trackers",
    version="1.0.0",
    lifespan=lifespan,
)


# Secure-by-default CORS allowlist. The dashboard SPA is served same-origin
# by this app, so it never needs CORS; the only legitimate cross-origin
# callers are the Angular dev server (ng serve :4200) and tooling hitting
# the merge service on :7187. Operators who genuinely need other origins set
# ALLOWED_ORIGINS (comma-separated); "*" is still accepted as an explicit
# opt-in but is no longer the default (CONTINUATION known-issue #5).
_MERGE_PORT = os.getenv("MERGE_SERVICE_PORT", "7187")
_DEFAULT_ORIGINS = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    f"http://localhost:{_MERGE_PORT}",
    f"http://127.0.0.1:{_MERGE_PORT}",
]


def _parse_allowed_origins(raw: str | None) -> list[str]:
    if raw is None:
        return list(_DEFAULT_ORIGINS)
    parts = [p.strip() for p in raw.split(",")]
    parts = [p for p in parts if p]
    return parts or list(_DEFAULT_ORIGINS)


_allowed_origins = _parse_allowed_origins(os.getenv("ALLOWED_ORIGINS"))

if "*" in _allowed_origins:
    logger.warning(
        "CORS wildcard origin ('*') is enabled — any website may call this API. "
        "Set ALLOWED_ORIGINS to an explicit comma-separated allowlist in production."
    )

# Browser extensions (e.g. the BobaLink WebExtension) call the merge service
# from a background fetch whose Origin is ``chrome-extension://<32-char-id>``
# (Chromium/Edge/Brave) or ``moz-extension://<uuid>`` (Firefox). A plain
# allowlist cannot cover these because the extension id is per-install — and a
# CORS wildcard ("*") would not even match, since the wildcard only applies to
# the scheme-less host form. Starlette's ``allow_origin_regex`` is the
# supported mechanism for matching a whole scheme://host pattern, so we admit
# the two extension schemes via an anchored regex while keeping the explicit
# host allowlist for everything else. The regex is anchored end-to-end so an
# http(s) site whose host merely *contains* "chrome-extension" is NOT matched.
_EXTENSION_ORIGIN_REGEX = r"^(chrome-extension|moz-extension)://[A-Za-z0-9._\-]+$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_EXTENSION_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):  # type: ignore[no-untyped-def]
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})


@app.get("/health")
async def health_check():  # type: ignore[no-untyped-def]
    return {"status": "healthy", "service": "merge-search", "version": "1.0.0"}


@app.get("/api/v1/bridge/health")
async def bridge_health():  # type: ignore[no-untyped-def]
    """Probe the host webui-bridge (default port 7188).

    The dashboard's "WebUI Bridge" link becomes disabled when this
    returns ``healthy: false`` so users don't land on a dead page.
    """
    import aiohttp

    bridge_port = int(os.getenv("BRIDGE_PORT", "7188"))

    # The webui-bridge runs as a HOST process (see webui-bridge.py). This
    # merge service runs inside the qbittorrent-proxy container, where
    # "localhost" resolves to the container's own loopback — NOT the host
    # where the bridge listens. So when BRIDGE_URL is not pinned, probe a
    # candidate-host chain: the container can reach the host bridge via
    # host.containers.internal (Podman) / host.docker.internal (Docker),
    # while a bare-host deployment reaches it via localhost. First host
    # that answers < 500 wins. An explicit BRIDGE_URL short-circuits the
    # chain (operator override).
    explicit = os.getenv("BRIDGE_URL")
    if explicit:
        candidates = [explicit]
    else:
        candidates = [
            f"http://localhost:{bridge_port}",
            f"http://host.containers.internal:{bridge_port}",
            f"http://host.docker.internal:{bridge_port}",
        ]

    last_error = None
    last_status: int | None = None
    try:
        async with aiohttp.ClientSession() as session:
            for bridge_url in candidates:
                try:
                    async with session.get(
                        bridge_url,
                        timeout=aiohttp.ClientTimeout(total=2),
                        allow_redirects=False,
                    ) as resp:
                        # Any 2xx / 3xx / 401 means the bridge is listening.
                        if resp.status < 500:
                            return {
                                "healthy": True,
                                "status_code": resp.status,
                                "bridge_url": bridge_url,
                                "port": bridge_port,
                            }
                        # Reached the bridge but it surfaced 5xx — record
                        # and keep trying other candidates (none should be
                        # a different bridge, but be defensive).
                        last_error = f"{bridge_url} returned {resp.status}"
                        last_status = resp.status
                except Exception as e:
                    last_error = f"{bridge_url}: {e}"
                    logger.debug(f"Bridge health probe failed for {bridge_url}: {e}")
    except Exception as e:
        last_error = str(e)
        logger.debug(f"Bridge health probe session error: {e}")

    return {
        "healthy": False,
        # Preserve the upstream 5xx code when a candidate WAS reached but
        # surfaced a server error, so a dashboard consumer reading
        # `status_code` on the unhealthy path still gets the real code
        # (None only when no candidate answered at all).
        "status_code": last_status,
        "error": last_error or "no bridge candidate reachable",
        "bridge_url": candidates[0],
        "port": bridge_port,
    }


@app.get("/api/v1/config")
async def get_config(request: Request):  # type: ignore[no-untyped-def]
    """Return the dashboard's user-facing service URLs.

    ``qbittorrent_url`` points to the authenticated download proxy
    (default port 7186) — the container-internal qBittorrent WebUI
    (port 7185) answers 401 Unauthorized without the proxy shim.
    ``qbittorrent_internal_url`` is still exposed for tooling that
    needs the direct container endpoint.

    The hostname is taken from the incoming request's ``Host`` header
    so the URLs match whatever address the browser used to reach us.
    """
    from config import get_config as load_config

    cfg = load_config()
    req_host = request.headers.get("host", "localhost")
    proxy_host = req_host.split(":")[0]
    proxy_port = int(os.getenv("PROXY_PORT", "7186"))
    qbittorrent_webui_url = f"http://{proxy_host}:{proxy_port}"
    return {
        "qbittorrent_url": qbittorrent_webui_url,
        "qbittorrent_internal_url": f"http://{cfg.qbittorrent_host}:{cfg.qbittorrent_port}",
        "qbittorrent_port": cfg.qbittorrent_port,
        "qbittorrent_host": cfg.qbittorrent_host,
        "proxy_port": proxy_port,
    }


@app.get("/api/v1/stats")
async def stats():  # type: ignore[no-untyped-def]
    orch = app.state.search_orchestrator if hasattr(app.state, "search_orchestrator") else None
    active = 0
    completed = 0
    aborted = 0
    trackers = []
    if orch is not None:
        for _sid, meta in orch._active_searches.items():
            if meta.status == "completed":
                completed += 1
            elif meta.status == "aborted":
                aborted += 1
            elif meta.status in ("pending", "running"):
                active += 1
        enabled_trackers = orch._get_enabled_trackers()
        trackers = [{"name": t.name, "url": t.url, "enabled": t.enabled} for t in enabled_trackers]
    return {
        "active_searches": active,
        "completed_searches": completed,
        "aborted_searches": aborted,
        "total_searches": active + completed + aborted,
        "trackers": trackers,
        "trackers_count": len(trackers),
    }


from .auth import router as auth_router  # noqa: E402
from .hooks import router as hooks_router  # noqa: E402

# NOTE(2026-04-27): the Python `/api/v1/jackett/autoconfig/last` endpoint
# (formerly download-proxy/src/api/jackett.py) was removed in favour of
# the canonical Go service at boba-jackett:7189
# (`/api/v1/jackett/autoconfig/runs` + `/runs/{id}`). See plan
# 2026-04-27-jackett-management-ui-and-system-db.md §38.
from .routes import router as api_router  # noqa: E402
from .scheduler import router as scheduler_router  # noqa: E402

app.include_router(api_router, prefix="/api/v1")
app.include_router(hooks_router, prefix="/api/v1/hooks")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(scheduler_router, prefix="/api/v1/schedules")


def _serve_index_html():  # type: ignore[no-untyped-def]
    if _angular_available:
        return FileResponse(
            _angular_index_path,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {
        "message": "Merge Search API",
        "version": "1.0.0",
        "dashboard": "not found",
    }


@app.get("/")
async def dashboard():  # type: ignore[no-untyped-def]
    return _serve_index_html()  # type: ignore[no-untyped-call]


@app.get("/dashboard")
async def dashboard_page():  # type: ignore[no-untyped-def]
    return _serve_index_html()  # type: ignore[no-untyped-call]


@app.get("/{path:path}")
async def spa_catch_all(path: str):  # type: ignore[no-untyped-def]
    if path.startswith("api/") or path == "health":
        raise HTTPException(status_code=404)
    file_path = os.path.join(_angular_dist_path, path)
    if os.path.isfile(file_path):  # noqa: ASYNC240
        return FileResponse(file_path)
    return _serve_index_html()  # type: ignore[no-untyped-call]
