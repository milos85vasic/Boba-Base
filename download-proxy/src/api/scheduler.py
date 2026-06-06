"""
API endpoints for scheduled search management.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scheduler"])


class ScheduleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    category: str = "all"
    interval_minutes: int = Field(default=60, ge=5, le=10080)


class ScheduleUpdateRequest(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    name: str | None = None


def _get_scheduler(request: Request):  # type: ignore[no-untyped-def]
    if not hasattr(request.app.state, "scheduler"):
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    return request.app.state.scheduler


@router.get("")
async def list_schedules(req: Request):  # type: ignore[no-untyped-def]
    scheduler = _get_scheduler(req)
    searches = scheduler.get_all_scheduled_searches()
    return {
        "schedules": [
            {
                "id": s.id,
                "name": s.name,
                "query": s.query,
                "category": s.category,
                "interval_minutes": s.interval_minutes,
                "enabled": s.enabled,
                "status": s.status.value,
                "last_run": s.last_run.isoformat() if s.last_run else None,
                "next_run": s.next_run.isoformat() if s.next_run else None,
                "results_count": s.results_count,
                "error_message": s.error_message,
            }
            for s in searches
        ],
        "count": len(searches),
    }


@router.post("")
async def create_schedule(request: ScheduleCreateRequest, req: Request):  # type: ignore[no-untyped-def]
    scheduler = _get_scheduler(req)
    search = scheduler.add_scheduled_search(
        name=request.name,
        query=request.query,
        category=request.category,
        interval_minutes=request.interval_minutes,
    )
    await scheduler.save()
    return {
        "id": search.id,
        "name": search.name,
        "query": search.query,
        "interval_minutes": search.interval_minutes,
        "enabled": search.enabled,
        "status": search.status.value,
        "next_run": search.next_run.isoformat() if search.next_run else None,
    }


@router.get("/{schedule_id}")
async def get_schedule(schedule_id: str, req: Request):  # type: ignore[no-untyped-def]
    scheduler = _get_scheduler(req)
    search = scheduler.get_scheduled_search(schedule_id)
    if not search:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {
        "id": search.id,
        "name": search.name,
        "query": search.query,
        "category": search.category,
        "interval_minutes": search.interval_minutes,
        "enabled": search.enabled,
        "status": search.status.value,
        "last_run": search.last_run.isoformat() if search.last_run else None,
        "next_run": search.next_run.isoformat() if search.next_run else None,
        "results_count": search.results_count,
        "error_message": search.error_message,
    }


@router.patch("/{schedule_id}")
async def update_schedule(schedule_id: str, request: ScheduleUpdateRequest, req: Request):  # type: ignore[no-untyped-def]
    scheduler = _get_scheduler(req)
    search = scheduler.get_scheduled_search(schedule_id)
    if not search:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if request.enabled is not None:
        search.enabled = request.enabled
    if request.interval_minutes is not None:
        search.interval_minutes = request.interval_minutes
    if request.name is not None:
        search.name = request.name

    await scheduler.save()
    return {"id": search.id, "name": search.name, "enabled": search.enabled}


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str, req: Request):  # type: ignore[no-untyped-def]
    scheduler = _get_scheduler(req)
    removed = scheduler.remove_scheduled_search(schedule_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await scheduler.save()
    return {"deleted": True, "schedule_id": schedule_id}


__all__ = ["router"]
