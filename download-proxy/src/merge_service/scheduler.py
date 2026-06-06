"""
Automated scheduling for recurring searches.

Provides:
- Cron-like scheduled search execution
- Persistent storage of scheduled searches
- Automatic search execution at configured intervals
"""

import asyncio
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from datetime import UTC, datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ScheduleStatus(Enum):
    """Status of a scheduled search."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScheduledSearch:
    """Configuration for a scheduled search."""

    id: str
    name: str
    query: str
    category: str = "all"
    interval_minutes: int = 60
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    results_count: int = 0
    error_message: str | None = None


class Scheduler:
    """Manages scheduled searches with persistence."""

    def __init__(self, config_path: str = "/config/merge-service/scheduling.json"):
        self._config_path = config_path
        self._scheduled_searches: dict[str, ScheduledSearch] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._search_callback: Callable[..., Any] | None = None

    def set_search_callback(self, callback: Callable[..., Any]) -> None:
        """Set the callback function for executing searches."""
        self._search_callback = callback

    async def load(self) -> None:
        """Load scheduled searches from persistent storage."""
        json_path = self._config_path

        if os.path.exists(json_path):  # noqa: ASYNC240
            try:
                with open(json_path) as f:  # noqa: ASYNC230
                    data = json.load(f)
                    for item in data.get("scheduled_searches", []):
                        search = ScheduledSearch(
                            id=item["id"],
                            name=item["name"],
                            query=item["query"],
                            category=item.get("category", "all"),
                            interval_minutes=item.get("interval_minutes", 60),
                            enabled=item.get("enabled", True),
                            last_run=datetime.fromisoformat(item["last_run"]) if item.get("last_run") else None,
                            next_run=datetime.fromisoformat(item["next_run"]) if item.get("next_run") else None,
                            status=ScheduleStatus(item.get("status", "active")),
                            results_count=item.get("results_count", 0),
                            error_message=item.get("error_message"),
                        )
                        self._scheduled_searches[search.id] = search

                logger.info(f"Loaded {len(self._scheduled_searches)} scheduled searches")
            except Exception as e:
                logger.error(f"Failed to load scheduled searches: {e}")

    async def save(self) -> None:
        """Save scheduled searches to persistent storage."""
        json_path = self._config_path

        try:
            data = {
                "scheduled_searches": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "query": s.query,
                        "category": s.category,
                        "interval_minutes": s.interval_minutes,
                        "enabled": s.enabled,
                        "last_run": s.last_run.isoformat() if s.last_run else None,
                        "next_run": s.next_run.isoformat() if s.next_run else None,
                        "status": s.status.value,
                        "results_count": s.results_count,
                        "error_message": s.error_message,
                    }
                    for s in self._scheduled_searches.values()
                ]
            }

            # Ensure directory exists
            os.makedirs(os.path.dirname(json_path), exist_ok=True)

            with open(json_path, "w") as f:  # noqa: ASYNC230
                json.dump(data, f, indent=2)

            logger.info(f"Saved {len(self._scheduled_searches)} scheduled searches")
        except Exception as e:
            logger.error(f"Failed to save scheduled searches: {e}")

    def add_scheduled_search(
        self,
        name: str,
        query: str,
        category: str = "all",
        interval_minutes: int = 60,
    ) -> ScheduledSearch:
        """Add a new scheduled search."""
        import uuid

        search = ScheduledSearch(
            id=str(uuid.uuid4()),
            name=name,
            query=query,
            category=category,
            interval_minutes=interval_minutes,
            next_run=datetime.now(UTC),
        )

        self._scheduled_searches[search.id] = search
        logger.info(f"Added scheduled search: {search.name} ({search.id})")

        return search

    def remove_scheduled_search(self, search_id: str) -> bool:
        """Remove a scheduled search."""
        if search_id in self._scheduled_searches:
            del self._scheduled_searches[search_id]
            logger.info(f"Removed scheduled search: {search_id}")
            return True
        return False

    def get_scheduled_search(self, search_id: str) -> ScheduledSearch | None:
        """Get a scheduled search by ID."""
        return self._scheduled_searches.get(search_id)

    def get_all_scheduled_searches(self) -> list[ScheduledSearch]:
        """Get all scheduled searches."""
        return list(self._scheduled_searches.values())

    def get_active_scheduled_searches(self) -> list[ScheduledSearch]:
        """Get all active scheduled searches."""
        return [s for s in self._scheduled_searches.values() if s.enabled and s.status == ScheduleStatus.ACTIVE]

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:  # noqa: SIM105
                await self._task
            except asyncio.CancelledError:
                pass

        await self.save()
        logger.info("Scheduler stopped")

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                now = datetime.now(UTC)

                # Check each active scheduled search
                for search in self.get_active_scheduled_searches():
                    if search.next_run and now >= search.next_run:
                        await self._execute_search(search)

                        # Schedule next run
                        search.last_run = now
                        search.next_run = now + timedelta(minutes=search.interval_minutes)

                # Save periodically
                await self.save()

            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")

            # Check every minute
            await asyncio.sleep(60)

    async def _execute_search(self, search: ScheduledSearch) -> None:
        """Execute a scheduled search."""
        logger.info(f"Executing scheduled search: {search.name}")

        if not self._search_callback:
            logger.error("No search callback configured")
            return

        try:
            # Execute the search
            result = await self._search_callback(search.query, search.category)

            search.results_count = result.get("merged_results", 0) if result else 0
            search.status = ScheduleStatus.COMPLETED
            search.error_message = None

            logger.info(f"Scheduled search {search.name} completed: {search.results_count} results")

        except Exception as e:
            search.status = ScheduleStatus.FAILED
            search.error_message = str(e)
            logger.error(f"Scheduled search {search.name} failed: {e}")


# Global scheduler instance
_scheduler: Scheduler | None = None


def get_scheduler(
    config_path: str = "/config/merge-service/scheduling.yaml",
) -> Scheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler(config_path)
    return _scheduler
