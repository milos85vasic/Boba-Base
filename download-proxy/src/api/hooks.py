"""
API endpoints for hook management.

Single source of truth for hook CRUD + event dispatch.
Uses JSON file persistence at /config/download-proxy/hooks.json.
"""

import asyncio
import collections
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# RW-02: env-gated shared-secret guard for the mutating routes. NO-OP when
# BOBA_API_TOKEN is unset (current operator contract preserved). Imported from
# routes.py (single source of truth — never redefined here).
from .routes import require_api_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["hooks"])

HOOKS_FILE = "/config/download-proxy/hooks.json"
LOGS_MAX = 200

VALID_EVENTS = [
    "search_start",
    "search_progress",
    "search_complete",
    "download_start",
    "download_progress",
    "download_complete",
    "merge_complete",
    "validation_complete",
]


class HookCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    event: str = Field(...)
    script_path: str = Field(...)
    enabled: bool = True
    timeout: int = Field(default=30, ge=1, le=300)
    environment: dict[str, Any] = Field(default_factory=dict)


class HookResponse(BaseModel):
    hook_id: str
    name: str
    event: str
    script_path: str
    enabled: bool
    timeout: int
    created_at: str


# Bounded hook-execution log.  Async handlers append to this from multiple
# coroutines, so we guard it with an asyncio.Lock and use a deque with a
# maxlen (env HOOK_LOG_MAXLEN, default 500) so it self-bounds.
_HOOK_LOG_MAXLEN: int = max(1, int(os.getenv("HOOK_LOG_MAXLEN", "500")))
_execution_logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=_HOOK_LOG_MAXLEN)
_execution_logs_lock: asyncio.Lock = asyncio.Lock()


async def append_hook_log(entry: dict[str, Any]) -> None:
    """Append a single hook-execution record under the module lock."""
    async with _execution_logs_lock:
        _execution_logs.append(entry)


async def extend_hook_logs(entries: list[dict[str, Any]]) -> None:
    """Bulk-append helper — serialises against concurrent single appends."""
    async with _execution_logs_lock:
        _execution_logs.extend(entries)


def _load_hooks() -> list[dict[str, Any]]:
    try:
        if os.path.isfile(HOOKS_FILE):
            with open(HOOKS_FILE) as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
    except Exception as e:
        logger.error(f"Failed to load hooks: {e}")
    return []


def _save_hooks(hooks: list[dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(HOOKS_FILE), exist_ok=True)
        with open(HOOKS_FILE, "w") as f:
            json.dump(hooks, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save hooks: {e}")


@router.get("")
async def list_hooks():  # type: ignore[no-untyped-def]
    hooks = _load_hooks()
    return {"hooks": hooks, "count": len(hooks)}


@router.post("", response_model=HookResponse)
async def create_hook(request: HookCreateRequest, _: None = Depends(require_api_token)):  # type: ignore[no-untyped-def]
    if request.event not in VALID_EVENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event type. Must be one of: {', '.join(VALID_EVENTS)}",
        )

    if ".." in request.script_path:
        raise HTTPException(
            status_code=400,
            detail="script_path cannot contain path traversal ('..')",
        )

    # RW-01 sandbox: the script must resolve inside the allowlisted hooks
    # directory (BOBA_HOOKS_DIR, default /config/download-proxy/hooks).
    # Registering a hook whose script_path is an arbitrary in-container
    # executable would let an event fire run it via merge_service.hooks.
    from merge_service.hooks import get_hooks_dir, is_script_path_allowed

    if not is_script_path_allowed(request.script_path):
        raise HTTPException(
            status_code=400,
            detail=(f"script_path must resolve to a file inside the allowlisted hooks dir ({get_hooks_dir()})"),
        )

    hook_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).isoformat()
    hook = {
        "hook_id": hook_id,
        "name": request.name,
        "event": request.event,
        "script_path": request.script_path,
        "enabled": request.enabled,
        "timeout": request.timeout,
        "environment": request.environment,
        "created_at": created_at,
    }

    hooks = _load_hooks()
    hooks.append(hook)
    _save_hooks(hooks)

    logger.info(f"Created hook: {request.name} ({hook_id})")

    return HookResponse(
        hook_id=hook_id,
        name=request.name,
        event=request.event,
        script_path=request.script_path,
        enabled=request.enabled,
        timeout=request.timeout,
        created_at=created_at,
    )


@router.delete("/{hook_id}")
async def delete_hook(hook_id: str, _: None = Depends(require_api_token)):  # type: ignore[no-untyped-def]
    hooks = _load_hooks()
    original_len = len(hooks)
    hooks = [h for h in hooks if h["hook_id"] != hook_id]
    if len(hooks) == original_len:
        raise HTTPException(status_code=404, detail="Hook not found")
    _save_hooks(hooks)
    logger.info(f"Deleted hook: {hook_id}")
    return {"message": "Hook deleted", "hook_id": hook_id}


@router.get("/logs")
async def get_execution_logs(limit: int = 50, hook_name: str | None = None):  # type: ignore[no-untyped-def]
    async with _execution_logs_lock:
        snapshot = list(_execution_logs)
    logs = snapshot[-limit:]
    if hook_name:
        logs = [line for line in logs if line.get("hook_name") == hook_name]
    return {"logs": logs, "count": len(logs)}


async def dispatch_event(event_type: str, event_data: dict[str, Any]):  # type: ignore[no-untyped-def]
    """Dispatch an event to all registered hooks."""
    from merge_service.hooks import HookEvent, HookEventType, get_dispatcher

    try:
        event_enum = HookEventType(event_type)
    except ValueError:
        logger.warning(f"Unknown event type: {event_type}")
        return

    dispatcher = get_dispatcher()

    hooks = _load_hooks()
    for h in hooks:
        if h.get("event") == event_type and h.get("enabled", True):
            from merge_service.hooks import HookConfig

            cfg = HookConfig(
                name=h["name"],
                event=event_enum,
                script_path=h["script_path"],
                enabled=True,
                timeout=h.get("timeout", 30),
                environment=h.get("environment", {}),
            )
            dispatcher.register_hook(cfg)

    hook_event = HookEvent(
        event_type=event_enum,
        search_id=event_data.get("search_id"),
        download_id=event_data.get("download_id"),
        data=event_data,
    )

    await dispatcher.dispatch(hook_event)

    new_logs = dispatcher.get_execution_log()
    # Deque's maxlen bounds size — the lock just serialises the extend.
    await extend_hook_logs(new_logs)


__all__ = ["append_hook_log", "dispatch_event", "extend_hook_logs", "router"]
