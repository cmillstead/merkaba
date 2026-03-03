# src/merkaba/observability/tracing.py
import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="no-trace")


def new_trace_id(prefix: str = "trace") -> str:
    """Generate a new trace ID, set it in the ContextVar, and return it."""
    tid = f"{prefix}-{uuid.uuid4().hex[:8]}"
    trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    """Return the current trace ID from the ContextVar."""
    return trace_id_var.get()


class TraceIdFilter(logging.Filter):
    """Logging filter that injects trace_id into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get()  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "trace_id": getattr(record, "trace_id", "no-trace"),
            "module": record.module,
            "msg": record.getMessage(),
        }
        return json.dumps(entry)


_setup_done = False


def setup_logging(
    log_dir: str | None = None,
    level: int = logging.INFO,
) -> None:
    """Configure the 'merkaba' logger with JSON file handler and trace filter.

    Idempotent — calling multiple times is safe.
    """
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    if log_dir is None:
        log_dir = os.path.expanduser("~/.merkaba/logs")
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("merkaba")
    logger.setLevel(level)

    log_path = os.path.join(log_dir, "merkaba.jsonl")
    handler = RotatingFileHandler(
        log_path,
        encoding="utf-8",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(TraceIdFilter())

    logger.addHandler(handler)
