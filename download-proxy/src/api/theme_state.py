"""
Shared theme state for the cross-app theme system.

Phase A of docs/CROSS_APP_THEME_PLAN.md — a tiny JSON-backed store with
pub/sub fan-out so:

* The Angular dashboard at :7187 can PUT the active ``paletteId`` +
  ``mode`` on every user selection.
* The download-proxy injector at :7186 can read the current state on
  every page load (and subscribe to live updates via SSE).

The store is intentionally process-local and in-memory; the merge
service and the download-proxy both live inside the same
``qbittorrent-proxy`` container so a single subscriber fan-out is
enough.

IMPORTANT: keep :data:`ALLOWED_PALETTE_IDS` in sync with
``frontend/src/app/models/palette.model.ts``. The unit tests in
``tests/unit/merge_service/test_theme_endpoint.py`` will fail loudly
if the two lists drift.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_THEME: dict[str, str] = {"paletteId": "darcula", "mode": "dark"}

# NOTE: keep in sync with frontend/src/app/models/palette.model.ts.
# The catalog parser test (tests/unit/test_palette_catalog.py) plus
# test_put_theme_accepts_every_catalogued_palette keep drift caught.
ALLOWED_PALETTE_IDS: frozenset[str] = frozenset(
    {
        "darcula",
        "dracula",
        "solarized",
        "nord",
        "monokai",
        "gruvbox",
        "one-dark",
        "tokyo-night",
    }
)

ALLOWED_MODES: frozenset[str] = frozenset({"light", "dark"})


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ThemeState:
    paletteId: str
    mode: str
    updatedAt: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class ThemeStore:
    """JSON-backed theme store with async pub/sub.

    * ``get()`` returns the current state (seeded from disk or default).
    * ``put(paletteId, mode)`` validates, writes atomically, and
      fans out to every live subscriber queue.
    * ``subscribe()`` returns an :class:`asyncio.Queue` that receives
      each new :class:`ThemeState`. The caller *must* call
      :meth:`unsubscribe` when done (usually in a ``finally:``).
    """

    def __init__(self, path: Path):
        self._path = Path(path)
        self._state = self._load_or_seed()
        self._subscribers: list[asyncio.Queue[ThemeState]] = []

    # ----------------------------------------------------------------- io
    def _load_or_seed(self) -> ThemeState:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                pid = data.get("paletteId")
                mode = data.get("mode")
                if pid in ALLOWED_PALETTE_IDS and mode in ALLOWED_MODES:
                    return ThemeState(
                        paletteId=pid,
                        mode=mode,
                        updatedAt=str(data.get("updatedAt") or _utcnow_iso()),
                    )
                logger.warning(
                    "theme.json contains unknown paletteId/mode (%r/%r); reverting to default",
                    pid,
                    mode,
                )
            except Exception as exc:  # corrupted JSON, unreadable file…
                logger.warning("theme.json could not be parsed (%s); reverting to default", exc)
        return ThemeState(
            paletteId=DEFAULT_THEME["paletteId"],
            mode=DEFAULT_THEME["mode"],
            updatedAt=_utcnow_iso(),
        )

    def _write_atomic(self, state: ThemeState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic tmp-file + os.replace so partially-written files can't
        # poison the next boot.
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=".theme-", suffix=".json", dir=str(self._path.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fp:
                json.dump(state.to_dict(), fp, indent=2, sort_keys=True)
                fp.flush()
                try:  # noqa: SIM105
                    os.fsync(fp.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, self._path)
        except Exception:
            try:  # noqa: SIM105
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise

    # -------------------------------------------------------------- api
    def get(self) -> ThemeState:
        return self._state

    def put(self, paletteId: str, mode: str) -> ThemeState:
        if paletteId not in ALLOWED_PALETTE_IDS:
            raise ValueError(f"unknown paletteId {paletteId!r}; allowed: {sorted(ALLOWED_PALETTE_IDS)}")
        if mode not in ALLOWED_MODES:
            raise ValueError(f"invalid mode {mode!r}; allowed: {sorted(ALLOWED_MODES)}")
        state = ThemeState(paletteId=paletteId, mode=mode, updatedAt=_utcnow_iso())
        self._write_atomic(state)
        self._state = state
        self._notify(state)
        return state

    # --------------------------------------------------------- pub/sub
    def subscribe(self) -> asyncio.Queue[ThemeState]:
        queue: asyncio.Queue[ThemeState] = asyncio.Queue(maxsize=16)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[ThemeState]) -> None:
        try:  # noqa: SIM105
            self._subscribers.remove(queue)
        except ValueError:
            pass

    def _notify(self, state: ThemeState) -> None:
        # Drop dead queues and fan out. put_nowait never blocks; on a
        # full queue (slow subscriber) we drop the update rather than
        # stalling other writers.
        alive: list[asyncio.Queue[ThemeState]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(state)
                alive.append(q)
            except asyncio.QueueFull:
                logger.debug("theme subscriber queue full; dropping update")
                alive.append(q)
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug("dropping dead theme subscriber: %s", exc)
        self._subscribers = alive

    # ------------------------------------------------------------ debug
    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


_store: ThemeStore | None = None


def _resolve_path() -> Path:
    raw = os.environ.get("THEME_STATE_PATH", "/config/merge-service/theme.json")
    return Path(raw)


def get_store() -> ThemeStore:
    """Return the module-level singleton, creating it lazily.

    Tests reset the singleton by assigning ``_store = None`` after
    tweaking ``THEME_STATE_PATH``.
    """
    global _store
    if _store is None:
        _store = ThemeStore(_resolve_path())
    return _store


__all__ = [
    "ALLOWED_MODES",
    "ALLOWED_PALETTE_IDS",
    "DEFAULT_THEME",
    "ThemeState",
    "ThemeStore",
    "get_store",
]
