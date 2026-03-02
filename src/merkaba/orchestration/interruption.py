# src/merkaba/orchestration/interruption.py
"""Thread-safe interruption management for the agent loop.

The async boundary (web/telegram) sets interruptions via interrupt().
The sync agent loop (in _execute_tools) checks them via check()/has_cancel().

Three modes:
- APPEND: queue behind current response (default, safe)
- STEER: inject at next tool boundary (for corrections)
- CANCEL: abort current response (for "stop, do this instead")
"""

import threading
from dataclasses import dataclass
from enum import Enum


class InterruptionMode(Enum):
    APPEND = "append"
    STEER = "steer"
    CANCEL = "cancel"


@dataclass
class InterruptionEvent:
    session_id: str
    message: str
    mode: InterruptionMode


class InterruptionManager:
    """Thread-safe interruption management.

    Async boundary (web/telegram) sets interruptions.
    Sync agent loop (in _execute_tools) checks them.
    """

    def __init__(self, default_mode: InterruptionMode = InterruptionMode.APPEND):
        self.default_mode = default_mode
        self._pending: dict[str, list[InterruptionEvent]] = {}
        self._lock = threading.Lock()

    def interrupt(self, session_id: str, message: str, mode: InterruptionMode | None = None):
        """Queue an interruption for the given session.

        Called from async boundary (web handler, telegram callback).
        """
        event = InterruptionEvent(
            session_id=session_id,
            message=message,
            mode=mode or self.default_mode,
        )
        with self._lock:
            self._pending.setdefault(session_id, []).append(event)

    def check(self, session_id: str) -> InterruptionEvent | None:
        """Pop the next pending interruption for the session.

        Called from the sync agent loop at tool boundaries.
        Returns None if no interruptions are pending.
        """
        with self._lock:
            events = self._pending.get(session_id, [])
            if events:
                return events.pop(0)
            return None

    def has_cancel(self, session_id: str) -> bool:
        """Check whether any pending event is a CANCEL (non-consuming peek).

        Used by the agent loop to decide whether to abort early
        without consuming other queued events.
        """
        with self._lock:
            return any(
                e.mode == InterruptionMode.CANCEL
                for e in self._pending.get(session_id, [])
            )

    def clear(self, session_id: str):
        """Remove all pending interruptions for the session.

        Called when a session ends or resets.
        """
        with self._lock:
            self._pending.pop(session_id, None)
