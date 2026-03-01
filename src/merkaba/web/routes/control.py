"""Mission Control endpoints — state aggregation and WebSocket control channel."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["control"])


def _build_state(request: Request) -> dict:
    """Aggregate system state from existing stores and registries."""
    from merkaba.orchestration.workers import WORKER_REGISTRY
    from merkaba.tools.builtin import (
        file_read, file_write, file_list,
        grep, glob,
        web_fetch,
        bash,
        memory_search,
        document_search, document_get,
    )

    memory_store = request.app.state.memory_store
    task_queue = request.app.state.task_queue
    action_queue = request.app.state.action_queue

    # System stats — memory facts count (across all businesses)
    try:
        cursor = memory_store._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM facts WHERE archived = 0")
        facts_count = cursor.fetchone()[0]
    except Exception:
        facts_count = 0

    try:
        pending_approvals = action_queue.get_pending_count()
    except Exception:
        pending_approvals = 0

    try:
        active_tasks = len(task_queue.list_tasks(status="running"))
    except Exception:
        active_tasks = 0

    # Build tool list from built-in tools
    tools = []
    builtin_tools = [
        file_read, file_write, file_list,
        grep, glob,
        web_fetch,
        bash,
        memory_search,
    ]
    # Add optional QMD tools if available
    if document_search is not None:
        builtin_tools.append(document_search)
    if document_get is not None:
        builtin_tools.append(document_get)

    for tool in builtin_tools:
        tools.append({
            "name": tool.name,
            "tier": tool.permission_tier.name,
            "active": True,
        })

    # Workers from registry
    workers = []
    connections = []
    scheduled_workers = {"health_check", "memory_decay", "memory_consolidation"}
    for task_type, worker_cls in WORKER_REGISTRY.items():
        workers.append({
            "id": task_type,
            "name": worker_cls.__name__.replace("Worker", ""),
            "status": "idle",
            "scheduled": task_type in scheduled_workers,
            "last_run": None,
            "parent": "merkaba-prime",
        })
        connections.append({
            "from": "merkaba-prime",
            "to": task_type,
            "type": "supervises",
        })

    return {
        "type": "state_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "status": "online",
            "memory_facts": facts_count,
            "pending_approvals": pending_approvals,
            "active_tasks": active_tasks,
        },
        "agents": [{
            "id": "merkaba-prime",
            "name": "Merkaba",
            "role": "supervisor",
            "model": "qwen3.5:122b",
            "status": "active",
            "tools": tools,
            "workers": [w["id"] for w in workers],
            "active_skill": None,
            "current_task": None,
        }],
        "workers": workers,
        "connections": connections,
    }


@router.get("/state")
async def get_control_state(request: Request):
    """Full state snapshot for initial Mission Control load."""
    return _build_state(request)
