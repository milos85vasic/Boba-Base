"""
SSE (Server-Sent Events) streaming for real-time search results.

Provides:
- SSE event generation for search progress
- Streaming response support for /search/stream/{searchId}
- Download progress streaming
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


class SSEHandler:
    """Handles Server-Sent Events streaming."""

    # SSE format constants
    EVENT_FIELD = "event"
    DATA_FIELD = "data"
    ID_FIELD = "id"
    RETRY_FIELD = "retry"

    @staticmethod
    def format_event(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
        """Format a single SSE event."""
        lines = []

        if event:
            lines.append(f"{SSEHandler.EVENT_FIELD}: {event}")

        # Format data as JSON
        json_data = json.dumps(data, default=str)
        for line in json_data.split("\n"):
            lines.append(f"{SSEHandler.DATA_FIELD}: {line}")

        if event_id:
            lines.append(f"{SSEHandler.ID_FIELD}: {event_id}")

        lines.append("")  # Empty line terminates event
        lines.append("")  # Second newline required by SSE spec
        return "\n".join(lines)

    @staticmethod
    async def search_results_stream(
        search_id: str,
        orchestrator: Any,
        poll_interval: float = 0.5,
        request: Request | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream search results as they come in.

        Args:
            search_id: The search ID to stream
            orchestrator: SearchOrchestrator instance
            poll_interval: How often to check for updates (seconds)
            request: Optional FastAPI Request.  When provided, the loop
                polls ``request.is_disconnected()`` every iteration and
                exits cleanly (emitting an ``event: close`` sentinel) if
                the client has gone away.

        Yields:
            SSE-formatted event strings
        """
        yield SSEHandler.format_event(
            event="search_start",
            data={"search_id": search_id, "status": "started"},
            event_id=search_id,
        )

        last_count = 0
        seen_hashes = set()
        # Per-tracker status diff — lets us emit ``tracker_started`` /
        # ``tracker_completed`` events whenever a stat flips between
        # poll iterations.  Keyed by tracker name; value is the last
        # observed status string.
        last_tracker_status: dict[str, str] = {}
        _TERMINAL_STATUSES = {"success", "empty", "error", "timeout", "cancelled"}

        async def _client_gone() -> bool:
            if request is None:
                return False
            try:
                return await request.is_disconnected()
            except Exception:
                return False

        while True:
            if await _client_gone():
                yield SSEHandler.format_event(
                    event="close",
                    data={"search_id": search_id, "reason": "client_disconnected"},
                    event_id=search_id,
                )
                return

            # Get current search status
            metadata = orchestrator.get_search_status(search_id)

            if metadata is None:
                yield SSEHandler.format_event(
                    event="error",
                    data={"error": "Search not found", "search_id": search_id},
                    event_id=search_id,
                )
                break

            # Emit per-tracker stat transition events.  We diff against
            # the last observed status per tracker so each flip fires
            # exactly once.  tracker_started covers pending → running;
            # tracker_completed covers any flip to a terminal status.
            try:
                tracker_stats = getattr(metadata, "tracker_stats", {}) or {}
                for tname, stat in tracker_stats.items():
                    prev = last_tracker_status.get(tname)
                    cur = getattr(stat, "status", None)
                    if cur is None or cur == prev:
                        continue
                    to_dict = getattr(stat, "to_dict", None)
                    payload = to_dict() if callable(to_dict) else {"name": tname, "status": cur}
                    if cur == "running":
                        yield SSEHandler.format_event(
                            event="tracker_started",
                            data=payload,
                            event_id=search_id,
                        )
                    elif cur in _TERMINAL_STATUSES:
                        yield SSEHandler.format_event(
                            event="tracker_completed",
                            data=payload,
                            event_id=search_id,
                        )
                    last_tracker_status[tname] = cur
            except Exception as _e:  # noqa: S110
                # Never let a diagnostics-emit failure kill the stream.
                pass

            # Check if search completed
            if metadata.status in ("completed", "failed"):
                # IMPORTANT: If search completed, emit any pending results first
                try:
                    live_results = orchestrator.get_live_results(search_id)
                    seen_hashes_local = set()
                    for result in live_results:
                        result_hash = getattr(result, "hash", None) or str(id(result))
                        if result_hash not in seen_hashes_local:
                            seen_hashes_local.add(result_hash)
                            yield SSEHandler.format_event(
                                event="result_found",
                                data={
                                    "search_id": search_id,
                                    "name": getattr(result, "name", ""),
                                    "seeds": getattr(result, "seeds", 0),
                                    "leechers": getattr(result, "leechers", 0),
                                    "tracker": getattr(result, "tracker", ""),
                                    "size": getattr(result, "size", 0),
                                    "link": getattr(result, "link", ""),
                                    "content_type": getattr(result, "content_type", None),
                                    "quality": getattr(result, "quality", None),
                                },
                                event_id=search_id,
                            )
                except Exception:  # noqa: S110
                    pass

                yield SSEHandler.format_event(event="search_complete", data=metadata.to_dict(), event_id=search_id)
                break

            # Stream individual results as they arrive
            try:
                live_results = orchestrator.get_live_results(search_id)
                for result in live_results:
                    result_hash = getattr(result, "hash", None) or str(id(result))
                    if result_hash not in seen_hashes:
                        seen_hashes.add(result_hash)
                        yield SSEHandler.format_event(
                            event="result_found",
                            data={
                                "search_id": search_id,
                                "name": getattr(result, "name", ""),
                                "seeds": getattr(result, "seeds", 0),
                                "leechers": getattr(result, "leechers", 0),
                                "tracker": getattr(result, "tracker", ""),
                                "size": getattr(result, "size", 0),
                                "link": getattr(result, "link", ""),
                                "content_type": getattr(result, "content_type", None),
                                "quality": getattr(result, "quality", None),
                            },
                            event_id=search_id,
                        )
            except Exception:  # noqa: S110
                pass

            # Stream intermediate results if count changed
            if metadata.total_results != last_count:
                yield SSEHandler.format_event(
                    event="results_update",
                    data={
                        "search_id": search_id,
                        "total_results": metadata.total_results,
                        "merged_results": metadata.merged_results,
                        "trackers_searched": metadata.trackers_searched,
                    },
                    event_id=search_id,
                )
                last_count = metadata.total_results

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    @staticmethod
    async def download_progress_stream(
        download_id: str,
        get_progress: Callable[[str], Any],
        poll_interval: float = 0.5,
        request: Request | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream download progress updates.

        Args:
            download_id: The download ID to track
            get_progress: Function to get current progress
            poll_interval: How often to check for updates
            request: Optional FastAPI Request.  When provided, the loop
                polls ``request.is_disconnected()`` every iteration and
                exits cleanly (emitting an ``event: close`` sentinel) if
                the client has gone away.

        Yields:
            SSE-formatted event strings
        """
        yield SSEHandler.format_event(
            event="download_start",
            data={"download_id": download_id, "status": "started"},
            event_id=download_id,
        )

        async def _client_gone() -> bool:
            if request is None:
                return False
            try:
                return await request.is_disconnected()
            except Exception:
                return False

        while True:
            if await _client_gone():
                yield SSEHandler.format_event(
                    event="close",
                    data={"download_id": download_id, "reason": "client_disconnected"},
                    event_id=download_id,
                )
                return

            progress = get_progress(download_id)

            if progress is None:
                yield SSEHandler.format_event(
                    event="download_complete",
                    data={"download_id": download_id},
                    event_id=download_id,
                )
                break

            yield SSEHandler.format_event(event="download_progress", data=progress, event_id=download_id)

            if progress.get("complete", False):
                break

            await asyncio.sleep(poll_interval)

    @staticmethod
    def create_streaming_response(
        generator: AsyncGenerator[str, None],
        media_type: str = "text/event-stream",
    ) -> StreamingResponse:
        """
        Create a FastAPI StreamingResponse for SSE.

        Args:
            generator: Async generator of SSE events
            media_type: Content type (default: text/event-stream)

        Returns:
            FastAPI StreamingResponse
        """
        return StreamingResponse(
            generator,
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )
