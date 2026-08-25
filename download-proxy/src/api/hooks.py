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
import tempfile
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# RW-02: env-gated shared-secret guard for the mutating routes. NO-OP when
# BOBA_API_TOKEN is unset (current operator contract preserved). Imported from
# routes.py (single source of truth — never redefined here).
from merge_service.hooks import HookEventType

from .routes import require_api_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["hooks"])

HOOKS_FILE = "/config/download-proxy/hooks.json"
LOGS_MAX = 200

# DERIVED, not duplicated (§11.4.241 — land the invariant at the strongest rung
# the toolchain supports). This list and merge_service.hooks.HookEventType were two
# sources of truth for one closed set: a hook could register against an event the
# dispatcher would never emit, and nothing would fail — it would just silently
# never fire. Pinning the two with assertions DETECTS drift; deriving one from the
# other makes drift UNREPRESENTABLE, which is the stronger rung.
#
# The earlier decision to pin rather than derive rested on a rationale the
# independent review measured as FALSE on all three counts (BOB-174 review,
# IMPORTANT-1): merge_service/hooks.py is untouched (not live under a sibling
# stream), the change is one line in THIS file rather than that one, and
# merge_service.hooks imports only stdlib so there is no cycle. Re-measured here
# before taking it: the derived list is ORDER-IDENTICAL to the literal it replaces.
VALID_EVENTS = [event.value for event in HookEventType]


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


class HookPersistenceError(RuntimeError):
    """Raised when the hook store could not be written.

    BOB-173: ``_save_hooks`` used to swallow every exception and return ``None``,
    so its callers had no channel through which to learn the write had failed and
    reported success unconditionally — a create returned a ``hook_id`` for a hook
    that was never written, a delete reported removal of a hook still in the file.

    This path combines MUTATION of a shared resource with an EXTERNAL SIDE EFFECT
    (a hook is an outbound call the system will or will not make later), so it
    MUST fail closed (§11.4.252). An exception is the channel chosen over a
    returned status deliberately: a returned bool leaves "caller ignored the
    failure" representable and therefore reachable by accident, which is the exact
    state that produced this defect. Raising makes it unrepresentable at the call
    site (§11.4.241 — prefer the rung that removes the illegal state over the one
    that merely reports it).
    """


class HookStoreCorruptError(RuntimeError):
    """Raised when the hook store EXISTS but its contents could not be obtained.

    BOB-174 A1: ``_load_hooks`` used to wrap its read in ``except Exception:
    return []``, so a truncated or malformed hooks.json was reported to every
    caller as an empty, healthy list.

    THE ROOT is the conflation this class exists to end. A MISSING hooks file
    legitimately means "no hooks configured" — that is a real, healthy, extremely
    common state (a fresh install), and answering it with ``[]`` is correct. A
    file that exists but cannot be read or parsed means "the hooks the operator
    configured are UNKNOWN to me". Those two states have opposite consequences
    and the old code collapsed them into the same empty list, so the API answered
    "you have no hooks" when the truth was "I cannot tell you what hooks you
    have" (§11.4.201(6): a blind instrument and a clean artifact returned the
    identical quiet zero).

    Kept DISTINCT from ``HookPersistenceError`` deliberately: that one means a
    WRITE failed, this one means a READ did. They arrive at different points and
    an operator repairs them differently — one is a permissions/disk problem, the
    other is a file to inspect and fix. Collapsing them would re-create, one level
    up, the same "two different states, one indistinguishable signal" defect.

    The decision this class encodes, and why GET returns an error rather than a
    ``200`` carrying a degraded marker, is recorded in
    ``docs/qa/BOB-174/DESIGN_DECISION.md``.
    """


def _load_hooks() -> list[dict[str, Any]]:
    """Return the configured hooks, or raise ``HookStoreCorruptError``.

    ABSENT is not CORRUPT. A missing file is the fresh-install state and returns
    an empty list exactly as before — that path is unchanged, and a fix that
    failed closed on it would be a §11.4.201(1) false-positive refusal breaking
    every new deployment.

    ``exists`` rather than ``isfile`` on purpose: ``isfile`` is also False for a
    DIRECTORY (or fifo/socket/device) at the store path, so the old guard reported
    "exists but unusable" as "nothing configured" — the same conflation this
    function exists to end, in a rarer flavour. Letting those fall through to the
    ``open`` below turns them into the ``IsADirectoryError``/``OSError`` the
    handler already covers, which is why this costs one word rather than a branch.
    A broken symlink stays MISSING under both spellings (``exists`` follows links),
    which is correct — nothing readable is there.
    """
    if not os.path.exists(HOOKS_FILE):
        return []

    try:
        with open(HOOKS_FILE) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        # ValueError covers json.JSONDecodeError (truncated / malformed).
        # OSError covers a file that exists but cannot be read at all.
        logger.error(f"Hook store at {HOOKS_FILE} could not be read: {e}")
        raise HookStoreCorruptError(str(e)) from e

    # Shape is part of "could the contents be obtained". A dict, a string or a
    # list of non-objects parses cleanly yet satisfies none of this module's
    # accessors (``h["hook_id"]``, ``h.get("event")``), so treating it as a hook
    # list would only move the failure somewhere less legible.
    if not isinstance(data, list):
        logger.error(f"Hook store at {HOOKS_FILE} is a {type(data).__name__}, expected a list")
        raise HookStoreCorruptError(f"expected a JSON list, found {type(data).__name__}")
    if not all(isinstance(item, dict) for item in data):
        logger.error(f"Hook store at {HOOKS_FILE} contains entries that are not hook objects")
        raise HookStoreCorruptError("expected a JSON list of hook objects")

    return data


def _save_hooks(hooks: list[dict[str, Any]]) -> None:
    """Atomically persist the hook list, or raise ``HookPersistenceError``.

    BOB-174 A5: this used a plain ``open(HOOKS_FILE, "w")``, which TRUNCATES the
    destination the moment it opens. A crash, an ENOSPC, or a kill between that
    truncation and the completed ``json.dump`` therefore left a half-written
    fragment where the operator's hooks used to be — this function MANUFACTURED
    the corrupt file that ``_load_hooks`` then misread as "no hooks" and the next
    create overwrote. The write is the first link of the chain, so it is fixed at
    its own layer rather than merely guarded downstream.

    The tmp-file + fsync + ``os.replace`` sequence is NOT invented here: it is the
    pattern already established in this codebase by
    ``download-proxy/src/api/theme_state.py`` (``_write_atomic``), reused rather
    than re-derived (§11.4.28). It is not extracted into a shared helper only
    because that would edit a file outside this item's scope; doing so is the
    obvious follow-up.

    ``os.replace`` is atomic within a filesystem, which is why the temp file is
    created in the DESTINATION directory rather than /tmp. Across a filesystem
    boundary the rename does not silently degrade, it RAISES: measured 2026-08-23,
    ``os.replace`` from ``tempfile.gettempdir()`` onto another device gives
    ``OSError errno 18 (EXDEV) Invalid cross-device link``. In the container the
    store is the bind-mounted ``/config`` while ``/tmp`` is the overlay, so losing
    the ``dir=`` kwarg would fail EVERY hook write — and no test could see it,
    because pytest's ``tmp_path`` lives under ``gettempdir()`` so both are always
    the same device under test. Pinned device-independently on the CALL by
    ``TestAtomicWriteMechanicsArePinned``.

    PERMISSION CONSEQUENCE, measured rather than assumed: ``mkstemp`` creates its
    file 0600 and ``os.replace`` carries the TEMP file's mode onto the
    destination, so every write now resets ``hooks.json`` from 0644 (what the
    old in-place write left under umask 022) to 0600. The direction is strictly
    MORE restrictive, so nothing that could read the store loses access except
    other users — and ``hook.environment`` is a free-form dict that can hold
    tokens (§11.4.10), which makes owner-only the better default. Recorded in
    docs/qa/BOB-174/DESIGN_DECISION.md §5 with the measurement.

    The log line is kept for diagnostics — it was never the problem. The problem
    was that it was the ONLY consequence, so a failed write was indistinguishable
    from a successful one to every caller (§11.4.201(6) false-null).
    """
    try:
        store_dir = os.path.dirname(HOOKS_FILE)
        os.makedirs(store_dir, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=".hooks-", suffix=".json", dir=store_dir)
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(hooks, f, indent=2)
                f.flush()
                try:  # noqa: SIM105
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, HOOKS_FILE)
        except Exception:
            # Leave no debris: a stray .hooks-*.json is confusing at best and, if
            # a later reader ever globbed the directory, another corrupt input.
            try:  # noqa: SIM105
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
    except Exception as e:
        logger.error(f"Failed to save hooks: {e}")
        raise HookPersistenceError(str(e)) from e


def _corrupt_store_detail() -> str:
    """Build the operator-facing detail from the LIVE ``HOOKS_FILE``.

    A function, not a module constant: a constant would capture the path at import
    time and could then name a file that is not the one that failed. Naming the
    wrong file in an error about an unreadable file is a small version of the same
    dishonesty this item exists to remove.
    """
    return (
        f"The hook store at {HOOKS_FILE} exists but could not be read. It may be truncated or "
        "malformed. Hooks configured there are in an UNKNOWN state and may still be firing; "
        "inspect and repair the file. No hook was read, listed, added or removed."
    )


@router.get("")
async def list_hooks():  # type: ignore[no-untyped-def]
    try:
        hooks = _load_hooks()
    except HookStoreCorruptError as e:
        # Deliberately an error status, not a 200 carrying a degraded marker.
        # Reasoning recorded in docs/qa/BOB-174/DESIGN_DECISION.md: a marker only
        # helps consumers that opt in to reading it, and EVERY existing consumer
        # (including the dashboard, which does `h.hooks || []`) would keep
        # rendering "No hooks registered" — the exact false report being fixed.
        raise HTTPException(status_code=500, detail=_corrupt_store_detail()) from e
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

    # REFUSE, DO NOT CLOBBER (§11.4.252). This load is the whole defect: given a
    # corrupt file the old code received [], appended one hook, and wrote a
    # one-element list over the operator's entire configuration — turning a
    # hand-repairable truncated file into permanent, silent data loss. A mutation
    # of a shared resource combined with an external side effect (a hook is an
    # outbound call the system will later make) must fail closed when an input to
    # its correctness is unverifiable.
    try:
        hooks = _load_hooks()
    except HookStoreCorruptError as e:
        raise HTTPException(status_code=500, detail=_corrupt_store_detail()) from e

    hooks.append(hook)
    try:
        _save_hooks(hooks)
    except HookPersistenceError as e:
        # Never hand back a hook_id for a hook that does not exist — an id for a
        # thing that was never written is the same false report in a smaller box.
        raise HTTPException(
            status_code=500,
            detail="Hook was not created: persisting the hook definition failed",
        ) from e

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
    # The 404 below is a claim about the file's CONTENTS. Making that claim about
    # a file that could not be read is a false report, not a null result: pre-fix,
    # deleting a hook that WAS in a corrupt store answered "Hook not found".
    try:
        hooks = _load_hooks()
    except HookStoreCorruptError as e:
        raise HTTPException(status_code=500, detail=_corrupt_store_detail()) from e

    original_len = len(hooks)
    hooks = [h for h in hooks if h["hook_id"] != hook_id]
    if len(hooks) == original_len:
        raise HTTPException(status_code=404, detail="Hook not found")
    try:
        _save_hooks(hooks)
    except HookPersistenceError as e:
        # The hook is still in the file and will still fire — say so.
        raise HTTPException(
            status_code=500,
            detail="Hook was not deleted: persisting the hook list failed",
        ) from e
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

    # A corrupt store means the set of hooks to run is UNKNOWN, so none are run —
    # fail closed on the side effect (§11.4.252). It does NOT propagate: this
    # coroutine is awaited inline by the search and download handlers in
    # routes.py, so raising here would turn an unreadable hooks file into a 500 on
    # SEARCH and DOWNLOAD — a false-positive refusal of unrelated capabilities
    # (§11.4.201(1)) far worse than the gap it would close.
    #
    # HONEST BOUNDARY (§11.4.6): this arm is therefore log-only, which is the very
    # shape this item condemns elsewhere. It is accepted HERE and only here
    # because dispatch_event has no response channel of its own to be honest on —
    # it is fire-and-forget. GET /api/v1/hooks is the surface where the operator
    # learns the store is broken, and it now says so loudly. Recorded as a known
    # limitation in docs/qa/BOB-174/DESIGN_DECISION.md rather than left implicit.
    try:
        hooks = _load_hooks()
    except HookStoreCorruptError as e:
        logger.error(
            f"Hook store unreadable ({e}); dispatching NO hooks for event {event_type}. "
            f"Configured hooks are not running. Repair {HOOKS_FILE}."
        )
        return

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


__all__ = [
    "HookPersistenceError",
    "HookStoreCorruptError",
    "append_hook_log",
    "dispatch_event",
    "extend_hook_logs",
    "router",
]
