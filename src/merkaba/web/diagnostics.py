"""In-memory diagnostics store with ring buffer for request tracing."""

import enum
import threading
from collections import deque
from datetime import datetime, timezone


class TraceDepth(enum.Enum):
    LIGHTWEIGHT = "lightweight"
    MODERATE = "moderate"
    FULL = "full"


# Fields included at each trace depth
_LIGHTWEIGHT_FIELDS = {"timestamp", "method", "path", "status", "duration_ms", "scope_type"}
_MODERATE_FIELDS = _LIGHTWEIGHT_FIELDS | {"route", "request_size", "response_size", "error", "close_code", "event_type"}
# FULL includes everything


class DiagnosticsStore:
    """Thread-safe ring buffer for request traces and WebSocket connection tracking."""

    def __init__(self, buffer_size: int = 500):
        self._buffer_size = buffer_size
        self._buffer: deque[dict] = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
        self._connections: dict[str, dict] = {}
        self._trace_depth = TraceDepth.FULL
        self._total_requests = 0
        self._total_errors = 0
        self._total_duration = 0.0

    @property
    def trace_depth(self) -> TraceDepth:
        return self._trace_depth

    def set_trace_depth(self, depth: TraceDepth) -> None:
        self._trace_depth = depth

    def _filter_fields(self, entry: dict) -> dict:
        """Strip fields not included at the current trace depth."""
        if self._trace_depth == TraceDepth.FULL:
            return entry
        allowed = _MODERATE_FIELDS if self._trace_depth == TraceDepth.MODERATE else _LIGHTWEIGHT_FIELDS
        return {k: v for k, v in entry.items() if k in allowed}

    def record_request(self, entry: dict) -> None:
        filtered = self._filter_fields(entry)
        with self._lock:
            self._buffer.append(filtered)
            self._total_requests += 1
            self._total_duration += entry.get("duration_ms", 0.0)
            status = entry.get("status", 0)
            if status >= 400 or entry.get("error"):
                self._total_errors += 1

    def get_recent(self, n: int) -> list[dict]:
        with self._lock:
            items = list(self._buffer)
        # Newest first
        items.reverse()
        return items[:n]

    def get_errors(self, n: int) -> list[dict]:
        with self._lock:
            items = list(self._buffer)
        items.reverse()
        errors = [e for e in items if e.get("status", 0) >= 400 or e.get("error")]
        return errors[:n]

    def get_summary(self) -> dict:
        with self._lock:
            total = self._total_requests
            errors = self._total_errors
            duration = self._total_duration
            used = len(self._buffer)
        return {
            "total_requests": total,
            "total_errors": errors,
            "avg_duration_ms": round(duration / total, 1) if total else 0.0,
            "buffer_size": self._buffer_size,
            "buffer_used": used,
        }

    # --- WebSocket connection tracking ---

    def ws_connect(self, conn_id: str, path: str) -> None:
        with self._lock:
            self._connections[conn_id] = {
                "path": path,
                "connected_at": datetime.now(timezone.utc).isoformat(),
                "frames_sent": 0,
                "frames_received": 0,
            }

    def ws_disconnect(self, conn_id: str) -> None:
        with self._lock:
            self._connections.pop(conn_id, None)

    def ws_frame_sent(self, conn_id: str) -> None:
        with self._lock:
            conn = self._connections.get(conn_id)
            if conn:
                conn["frames_sent"] += 1

    def ws_frame_received(self, conn_id: str) -> None:
        with self._lock:
            conn = self._connections.get(conn_id)
            if conn:
                conn["frames_received"] += 1

    def get_connections(self) -> list[dict]:
        with self._lock:
            return list(self._connections.values())

    def to_dict(self) -> dict:
        """Full diagnostics snapshot for WebSocket heartbeat."""
        return {
            "trace_depth": self._trace_depth.value,
            **self.get_summary(),
            "active_websockets": self.get_connections(),
            "recent_requests": self.get_recent(50),
            "recent_errors": self.get_errors(10),
        }
