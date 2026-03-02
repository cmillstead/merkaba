# src/merkaba/orchestration/lane_queue.py
import asyncio
import threading
from collections import defaultdict
from typing import Any, Callable


class LaneQueue:
    """Per-session serial execution with cross-session concurrency.

    Each session_id gets its own lock. Messages within a session
    execute serially. Different sessions execute concurrently.

    Sync core with async boundary wrapper via asyncio.to_thread().
    """

    def __init__(self):
        # Note: defaultdict.__missing__ is atomic under CPython GIL.
        # If targeting free-threaded Python, wrap access in _active_lock.
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._active_sessions: set[str] = set()
        self._active_lock = threading.Lock()

    def submit_sync(
        self,
        session_id: str,
        handler: Callable[[Any], Any],
        payload: Any,
    ) -> Any:
        """Submit work for a session. Blocks if session is busy."""
        with self._locks[session_id]:
            with self._active_lock:
                self._active_sessions.add(session_id)
            try:
                return handler(payload)
            finally:
                with self._active_lock:
                    self._active_sessions.discard(session_id)

    async def submit(
        self,
        session_id: str,
        handler: Callable[[Any], Any],
        payload: Any,
    ) -> Any:
        """Async wrapper -- runs submit_sync in a thread."""
        return await asyncio.to_thread(self.submit_sync, session_id, handler, payload)

    def remove_session(self, session_id: str) -> None:
        """Remove a session's lock. Call during session eviction."""
        self._locks.pop(session_id, None)

    def is_busy(self, session_id: str) -> bool:
        with self._active_lock:
            return session_id in self._active_sessions

    def active_session_count(self) -> int:
        with self._active_lock:
            return len(self._active_sessions)
