"""
Pipeline event hooks system.

Provides:
- Hook event definitions
- Hook configuration management
- Script execution with timeout
- Event dispatching to registered hooks
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HookEventType(Enum):
    """Types of events that can trigger hooks."""

    SEARCH_START = "search_start"
    SEARCH_PROGRESS = "search_progress"
    SEARCH_COMPLETE = "search_complete"
    DOWNLOAD_START = "download_start"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_COMPLETE = "download_complete"
    MERGE_COMPLETE = "merge_complete"
    VALIDATION_COMPLETE = "validation_complete"


@dataclass
class HookEvent:
    """Event payload for hook execution."""

    event_type: HookEventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    search_id: str | None = None
    download_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "search_id": self.search_id,
            "download_id": self.download_id,
            "data": self.data,
        }


@dataclass
class HookConfig:
    """Configuration for a hook."""

    name: str
    event: HookEventType
    script_path: str
    enabled: bool = True
    timeout: int = 30  # seconds
    environment: dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        """Validate hook configuration."""
        if not self.name:
            return False
        if not self.script_path:
            return False
        if not os.path.exists(self.script_path):
            logger.warning(f"Hook script not found: {self.script_path}")
            return False
        return True


class HookDispatcher:
    """Dispatches events to registered hooks."""

    def __init__(self, timeout: int = 30):
        self._hooks: dict[HookEventType, list[HookConfig]] = {}
        self._timeout = timeout
        self._execution_log: list[dict[str, Any]] = []

    def register_hook(self, hook: HookConfig) -> None:
        """Register a hook for an event type."""
        if hook.event not in self._hooks:
            self._hooks[hook.event] = []

        # Avoid duplicates
        existing = [h for h in self._hooks[hook.event] if h.name == hook.name]
        if not existing:
            self._hooks[hook.event].append(hook)
            logger.info(f"Registered hook: {hook.name} for {hook.event.value}")

    def unregister_hook(self, name: str, event: HookEventType) -> None:
        """Unregister a hook by name and event type."""
        if event in self._hooks:
            self._hooks[event] = [h for h in self._hooks[event] if h.name != name]

    def get_hooks(self, event: HookEventType) -> list[HookConfig]:
        """Get all hooks registered for an event type."""
        return self._hooks.get(event, [])

    async def dispatch(self, event: HookEvent) -> None:
        """Dispatch an event to all registered hooks."""
        hooks = self.get_hooks(event.event_type)

        for hook in hooks:
            if not hook.enabled:
                continue

            if not hook.validate():
                logger.warning(f"Hook validation failed: {hook.name}")
                continue

            try:
                await self._execute_hook(hook, event)
            except Exception as e:
                logger.error(f"Hook execution failed: {hook.name} - {e}")

    async def _execute_hook(self, hook: HookConfig, event: HookEvent) -> None:
        """Execute a single hook script."""
        # Prepare environment
        env = os.environ.copy()
        env.update(hook.environment)
        env["HOOK_EVENT"] = event.event_type.value
        env["HOOK_DATA"] = json.dumps(event.to_dict())

        if event.search_id:
            env["SEARCH_ID"] = event.search_id
        if event.download_id:
            env["DOWNLOAD_ID"] = event.download_id

        # Execute script
        start_time = datetime.now(UTC)

        try:
            result = subprocess.run(  # noqa: ASYNC221
                [hook.script_path],
                capture_output=True,
                text=True,
                timeout=hook.timeout,
                env=env,
            )

            duration = (datetime.now(UTC) - start_time).total_seconds()

            log_entry = {
                "hook_name": hook.name,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "duration_seconds": duration,
                "return_code": result.returncode,
                "success": result.returncode == 0,
                "stdout": result.stdout[:500] if result.stdout else "",
                "stderr": result.stderr[:500] if result.stderr else "",
            }

            self._execution_log.append(log_entry)

            if result.returncode == 0:
                logger.info(f"Hook {hook.name} executed successfully")
            else:
                logger.warning(f"Hook {hook.name} returned code {result.returncode}")

        except subprocess.TimeoutExpired:
            logger.error(f"Hook {hook.name} timed out after {hook.timeout}s")
            self._execution_log.append(
                {
                    "hook_name": hook.name,
                    "event_type": event.event_type.value,
                    "timestamp": event.timestamp.isoformat(),
                    "success": False,
                    "error": "timeout",
                }
            )
        except Exception as e:
            logger.error(f"Hook {hook.name} failed: {e}")
            self._execution_log.append(
                {
                    "hook_name": hook.name,
                    "event_type": event.event_type.value,
                    "timestamp": event.timestamp.isoformat(),
                    "success": False,
                    "error": str(e),
                }
            )

    def get_execution_log(self) -> list[dict[str, Any]]:
        """Get the execution log."""
        return self._execution_log


# Global dispatcher instance
_dispatcher: HookDispatcher | None = None


def get_dispatcher() -> HookDispatcher:
    """Get the global hook dispatcher."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = HookDispatcher()
    return _dispatcher


def create_default_hook(name: str, event: HookEventType, script_path: str) -> HookConfig:
    """Create a hook configuration with defaults."""
    return HookConfig(
        name=name,
        event=event,
        script_path=script_path,
        enabled=True,
        timeout=30,
    )
