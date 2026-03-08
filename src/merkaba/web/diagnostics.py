"""In-memory diagnostics store with ring buffer for request tracing."""

import enum
import logging
import threading
import time
import urllib.parse
import uuid
from collections import deque
from datetime import datetime, timezone

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


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
                "connected_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
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


_REDACTED_HEADERS = {"authorization", "x-api-key", "cookie", "set-cookie"}


class DiagnosticsMiddleware:
    """ASGI middleware that traces HTTP requests and WebSocket lifecycle events."""

    def __init__(self, app: ASGIApp, store: DiagnosticsStore) -> None:
        self.app = app
        self.store = store

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await self._trace_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._trace_websocket(scope, receive, send)
        else:
            await self.app(scope, receive, send)

    async def _trace_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        start = time.monotonic()
        status_code = 0
        response_size = 0

        async def send_wrapper(message):
            nonlocal status_code, response_size
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            elif message["type"] == "http.response.body":
                response_size += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = 500
            raise
        finally:
            duration = (time.monotonic() - start) * 1000
            try:
                entry = {
                    "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                    "scope_type": "http",
                    "method": scope.get("method", "?"),
                    "path": scope.get("path", "?"),
                    "status": status_code,
                    "duration_ms": round(duration, 2),
                    # Moderate fields
                    "route": self._get_route_name(scope),
                    "request_size": 0,
                    "response_size": response_size,
                    # Full fields
                    "query_string": self._redact_query_string(
                        scope.get("query_string", b"")
                    ).decode("utf-8", errors="replace"),
                    "headers": self._sanitize_headers(scope.get("headers", [])),
                }
                if status_code >= 400:
                    entry["error"] = f"HTTP {status_code}"
                self.store.record_request(entry)
            except Exception:
                logger.warning("Failed to record HTTP trace", exc_info=True)

    async def _trace_websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        conn_id = uuid.uuid4().hex[:12]
        path = scope.get("path", "?")
        start = time.monotonic()

        async def receive_wrapper():
            message = await receive()
            if message["type"] == "websocket.receive":
                try:
                    self.store.ws_frame_received(conn_id)
                except Exception as e:
                    logger.debug("Failed to record WS frame received: %s", e, exc_info=True)
            return message

        async def send_wrapper(message):
            if message["type"] == "websocket.send":
                try:
                    self.store.ws_frame_sent(conn_id)
                except Exception as e:
                    logger.debug("Failed to record WS frame sent: %s", e, exc_info=True)
            await send(message)

        try:
            self.store.ws_connect(conn_id, path)
            await self.app(scope, receive_wrapper, send_wrapper)
        except Exception:
            raise
        finally:
            duration = (time.monotonic() - start) * 1000
            try:
                conn_info = None
                for c in self.store.get_connections():
                    if c["path"] == path:
                        conn_info = c
                        break
                self.store.record_request({
                    "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                    "scope_type": "websocket",
                    "method": "WS",
                    "path": path,
                    "status": 0,
                    "duration_ms": round(duration, 2),
                    "event_type": "disconnect",
                    "frames_sent": conn_info["frames_sent"] if conn_info else 0,
                    "frames_received": conn_info["frames_received"] if conn_info else 0,
                })
            except Exception:
                logger.warning("Failed to record WebSocket trace", exc_info=True)
            self.store.ws_disconnect(conn_id)

    @staticmethod
    def _get_route_name(scope: Scope) -> str:
        route = scope.get("route")
        if route:
            return f"{type(route).__name__} {getattr(route, 'path', '')}"
        endpoint = scope.get("endpoint")
        if endpoint:
            name = getattr(endpoint, "__name__", None)
            if name:
                return name
            return type(endpoint).__name__
        return "unknown"

    _REDACTED_QUERY_PARAMS = frozenset({"token", "key", "secret", "api_key", "apikey"})

    @staticmethod
    def _redact_query_string(qs: bytes) -> bytes:
        """Replace values of sensitive query parameters with [REDACTED]."""
        if not qs:
            return qs
        text = qs.decode("utf-8", errors="replace")
        params = urllib.parse.parse_qsl(text, keep_blank_values=True)
        redacted = []
        for name, value in params:
            if name.lower() in DiagnosticsMiddleware._REDACTED_QUERY_PARAMS:
                redacted.append((name, "[REDACTED]"))
            else:
                redacted.append((name, value))
        return urllib.parse.urlencode(redacted).encode("utf-8")

    @staticmethod
    def _sanitize_headers(raw_headers: list) -> list[list[str]]:
        result = []
        for key_bytes, val_bytes in raw_headers:
            key = key_bytes.decode("latin-1") if isinstance(key_bytes, bytes) else key_bytes
            val = val_bytes.decode("latin-1") if isinstance(val_bytes, bytes) else val_bytes
            if key.lower() in _REDACTED_HEADERS:
                val = "[REDACTED]"
            result.append([key, val])
        return result
