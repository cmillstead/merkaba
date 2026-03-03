"""Mission Control endpoints — state aggregation and WebSocket control channel."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.requests import HTTPConnection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["control"])

# Separate router for WebSocket (included without prefix in app.py)
ws_router = APIRouter(tags=["control-ws"])

HEARTBEAT_INTERVAL = 2  # seconds

WORKER_DESCRIPTIONS = {
    "health_check": "Analyzes business health metrics and generates reports",
    "research": "Performs research using web and document tools",
    "code": "Writes and reviews code using file and search tools",
    "review": "Reviews business decisions and suggests improvements",
    "memory_decay": "Reduces relevance scores on stale facts (daily 3am)",
    "memory_consolidate": "Summarizes and archives old memories (weekly Sun 4am)",
}

# Default cron schedules for workers that should run automatically.
# These are ensured to exist in the TaskQueue at web startup.
WORKER_SCHEDULES = {
    "health_check": "0 */6 * * *",       # every 6 hours
    "memory_decay": "0 3 * * *",          # daily 3am
    "memory_consolidate": "0 4 * * 0",    # weekly Sun 4am
}


def ensure_scheduled_workers(task_queue) -> None:
    """Ensure each scheduled worker has exactly one task with its default cron.

    On startup this:
    - Creates missing scheduled tasks
    - Fixes tasks that lost their schedule (e.g. from a manual trigger)
    - Removes duplicate tasks for the same worker type
    - Resets stuck 'running' tasks back to 'pending'
    """
    from croniter import croniter

    try:
        all_tasks = task_queue.list_tasks()
    except Exception:
        all_tasks = []

    # Group all tasks by type
    tasks_by_type: dict[str, list[dict]] = {}
    for t in all_tasks:
        tasks_by_type.setdefault(t["task_type"], []).append(t)

    for task_type, cron in WORKER_SCHEDULES.items():
        tasks = tasks_by_type.get(task_type, [])

        if not tasks:
            task_queue.add_task(name=task_type, task_type=task_type, schedule=cron)
            logger.info("Created scheduled task: %s (%s)", task_type, cron)
            continue

        # Keep the first task, delete duplicates
        keep = tasks[0]
        for dup in tasks[1:]:
            task_queue.delete_task(dup["id"])
            logger.info("Removed duplicate %s task (id=%d)", task_type, dup["id"])

        # Ensure the kept task has the correct schedule
        next_run = croniter(cron, datetime.now()).get_next(datetime).isoformat()
        updates: dict = {}
        if not keep.get("schedule"):
            updates["schedule"] = cron
            updates["next_run"] = next_run
        if keep["status"] == "running":
            updates["status"] = "pending"
        if updates:
            task_queue.update_task(keep["id"], **updates)
            logger.info("Fixed %s task (id=%d): %s", task_type, keep["id"], updates)


class ModelChangeRequest(BaseModel):
    agent: str
    model: str


# v1: Display-only model override, not persisted across restarts.
# Does not affect actual agent model routing — that requires config changes.
_model_overrides: dict[str, str] = {}


def _get_recent_activity(base_dir: str | None, limit: int = 5) -> list[dict]:
    """Read the latest conversation JSON files and return summaries."""
    if not base_dir:
        return []
    conv_dir = Path(base_dir) / "conversations"
    if not conv_dir.is_dir():
        return []

    try:
        files = sorted(
            (f for f in conv_dir.iterdir() if f.suffix == ".json"),
            key=lambda f: f.name,
            reverse=True,
        )[:limit]
    except OSError:
        return []

    results = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            messages = data.get("messages", [])
            # Find the first user message for preview
            preview = ""
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    preview = content[:80]
                    break
            results.append({
                "session_id": f.stem,
                "preview": preview,
                "timestamp": data.get("saved_at"),
            })
        except (OSError, json.JSONDecodeError, KeyError):
            continue
    return results


def _build_state(conn: HTTPConnection) -> dict:
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

    memory_store = conn.app.state.memory_store
    task_queue = conn.app.state.task_queue
    action_queue = conn.app.state.action_queue

    # System stats — memory facts count (across all businesses)
    try:
        cursor = memory_store._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM facts WHERE archived = 0")
        facts_count = cursor.fetchone()[0]
    except Exception:
        facts_count = 0

    try:
        cursor = memory_store._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM facts WHERE archived = 1")
        archived_count = cursor.fetchone()[0]
    except Exception:
        archived_count = 0

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

    # Workers from registry — enriched with TaskQueue data
    workers = []
    connections = []
    scheduled_workers = set(WORKER_SCHEDULES.keys())

    # Build lookup of tasks by task_type for schedule/run info
    try:
        all_tasks = task_queue.list_tasks()
    except Exception:
        all_tasks = []
    tasks_by_type: dict[str, dict] = {}
    for t in all_tasks:
        # Keep the first (oldest) task per type — matches the scheduled task
        if t["task_type"] not in tasks_by_type:
            tasks_by_type[t["task_type"]] = t

    for task_type, worker_cls in WORKER_REGISTRY.items():
        task_info = tasks_by_type.get(task_type)
        schedule = task_info["schedule"] if task_info else None
        next_run = task_info["next_run"] if task_info else None
        last_run = task_info["last_run"] if task_info else None

        # Fetch recent run history (last 5)
        run_history: list[dict] = []
        if task_info:
            try:
                runs = task_queue.get_runs(task_info["id"])[:5]
                run_history = [
                    {
                        "id": r["id"],
                        "started_at": r["started_at"],
                        "finished_at": r["finished_at"],
                        "status": r["status"],
                    }
                    for r in runs
                ]
            except Exception:
                pass

        workers.append({
            "id": task_type,
            "name": worker_cls.__name__.replace("Worker", ""),
            "description": WORKER_DESCRIPTIONS.get(task_type, ""),
            "status": "idle",
            "scheduled": task_type in scheduled_workers,
            "schedule": schedule,
            "next_run": next_run,
            "last_run": last_run,
            "run_history": run_history,
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
            "memory_archived": archived_count,
            "pending_approvals": pending_approvals,
            "active_tasks": active_tasks,
        },
        "agents": [{
            "id": "merkaba-prime",
            "name": "Merkaba",
            "role": "supervisor",
            "model": _model_overrides.get("merkaba-prime", "qwen3.5:122b"),
            "status": "active",
            "tools": tools,
            "workers": [w["id"] for w in workers],
            "active_skill": None,
            "current_task": None,
            "recent_activity": _get_recent_activity(
                getattr(conn.app.state, "merkaba_base_dir", None)
            ),
        }],
        "workers": workers,
        "connections": connections,
    }


def _build_kanban(conn: HTTPConnection) -> dict:
    """Build kanban board state — tasks, approvals, and recent runs grouped by column."""
    task_queue = conn.app.state.task_queue
    action_queue = conn.app.state.action_queue

    # Tasks grouped by status
    queued = []
    running = []
    try:
        all_tasks = task_queue.list_tasks()
        for t in all_tasks:
            entry = {
                "id": t["id"],
                "name": t["name"],
                "task_type": t["task_type"],
                "status": t["status"],
                "created_at": t["created_at"],
            }
            if t["status"] == "pending":
                queued.append(entry)
            elif t["status"] == "running":
                running.append(entry)
    except Exception:
        logger.exception("Error fetching tasks for kanban")

    # Pending approvals
    awaiting_approval = []
    try:
        pending_actions = action_queue.list_actions(status="pending")
        for a in pending_actions:
            awaiting_approval.append({
                "id": a["id"],
                "business_id": a["business_id"],
                "action_type": a["action_type"],
                "description": a["description"],
                "created_at": a["created_at"],
            })
    except Exception:
        logger.exception("Error fetching approvals for kanban")

    # Recent completed and failed runs from task_runs table (last 50 each)
    completed = []
    failed = []
    try:
        cursor = task_queue._conn.cursor()
        cursor.execute(
            """SELECT tr.id, tr.task_id, tr.started_at, tr.finished_at, tr.status,
                      t.name, t.task_type
               FROM task_runs tr
               LEFT JOIN tasks t ON tr.task_id = t.id
               WHERE tr.status = 'success'
               ORDER BY tr.finished_at DESC
               LIMIT 50"""
        )
        for row in cursor.fetchall():
            r = dict(row)
            completed.append({
                "id": r["id"],
                "task_id": r["task_id"],
                "name": r.get("name"),
                "task_type": r.get("task_type"),
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "status": r["status"],
            })

        cursor.execute(
            """SELECT tr.id, tr.task_id, tr.started_at, tr.finished_at, tr.status, tr.error,
                      t.name, t.task_type
               FROM task_runs tr
               LEFT JOIN tasks t ON tr.task_id = t.id
               WHERE tr.status = 'failed'
               ORDER BY tr.finished_at DESC
               LIMIT 50"""
        )
        for row in cursor.fetchall():
            r = dict(row)
            failed.append({
                "id": r["id"],
                "task_id": r["task_id"],
                "name": r.get("name"),
                "task_type": r.get("task_type"),
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "status": r["status"],
                "error": r.get("error"),
            })
    except Exception:
        logger.exception("Error fetching task runs for kanban")

    return {
        "queued": queued,
        "awaiting_approval": awaiting_approval,
        "running": running,
        "completed": completed,
        "failed": failed,
    }


@router.get("/state")
async def get_control_state(request: Request):
    """Full state snapshot for initial Mission Control load."""
    return _build_state(request)


@router.get("/kanban")
async def get_kanban_state(request: Request):
    """Kanban board state — tasks, approvals, and recent runs grouped by column."""
    return _build_kanban(request)


@router.post("/model")
async def change_model(body: ModelChangeRequest):
    """Change the model assigned to an agent."""
    if body.agent != "merkaba-prime":
        raise HTTPException(status_code=404, detail=f"Agent '{body.agent}' not found")
    _model_overrides[body.agent] = body.model
    return {"agent": body.agent, "model": body.model}


@router.post("/worker/{worker_id}/trigger")
async def trigger_worker(worker_id: str, request: Request):
    """Manually trigger a worker — executes it and records the run."""
    from starlette.background import BackgroundTask
    from starlette.responses import JSONResponse as StarletteJSONResponse

    from merkaba.orchestration.workers import WORKER_REGISTRY

    if worker_id not in WORKER_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Worker '{worker_id}' not found")

    task_queue = request.app.state.task_queue

    # Find existing task for this worker type (avoid creating duplicates)
    task_id = None
    try:
        for t in task_queue.list_tasks():
            if t["task_type"] == worker_id:
                task_id = t["id"]
                break
    except Exception:
        pass

    # Create one only if no existing task found
    if task_id is None:
        task_id = task_queue.add_task(
            name=f"Manual: {worker_id}",
            task_type=worker_id,
            payload={"triggered_by": "mission-control"},
        )

    task = task_queue.get_task(task_id)
    run_id = task_queue.start_run(task_id)

    db_path = task_queue.db_path

    def _execute_worker():
        from merkaba.orchestration.queue import TaskQueue
        tq = TaskQueue(db_path=db_path)
        worker_cls = WORKER_REGISTRY[worker_id]
        worker = worker_cls()
        try:
            result = worker.execute(task)
            tq.finish_run(
                run_id, "success", result=result.output if result else None,
            )
        except Exception as e:
            logger.error("Manual trigger of %s failed: %s", worker_id, e)
            tq.finish_run(run_id, "failed", error=str(e))
        finally:
            tq.update_task(task_id, last_run=datetime.now().isoformat())
            tq.close()

    return StarletteJSONResponse(
        content={"worker_id": worker_id, "task_id": task_id, "run_id": run_id, "status": "running"},
        background=BackgroundTask(_execute_worker),
    )


@ws_router.websocket("/ws/control")
async def websocket_control(websocket: WebSocket):
    """WebSocket endpoint for live Mission Control state updates.

    Supports client messages:
      {"type": "subscribe", "channel": "diagnostics"} — include diagnostic data
      {"type": "unsubscribe", "channel": "diagnostics"} — exclude diagnostic data
      {"type": "set_trace_depth", "level": "lightweight|moderate|full"} — change depth
    """
    await websocket.accept()

    subscriptions: set[str] = set()

    async def heartbeat_loop():
        """Send state snapshots every HEARTBEAT_INTERVAL seconds."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                state = _build_state(websocket)
                if "diagnostics" in subscriptions:
                    store = websocket.app.state.diagnostics_store
                    state["diagnostics"] = store.to_dict()
                if "kanban" in subscriptions:
                    state["kanban"] = _build_kanban(websocket)
                await websocket.send_json(state)
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Control heartbeat error")

    async def receive_loop():
        """Listen for client commands."""
        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")
                if msg_type == "subscribe":
                    channel = data.get("channel")
                    if channel:
                        subscriptions.add(channel)
                elif msg_type == "unsubscribe":
                    channel = data.get("channel")
                    if channel:
                        subscriptions.discard(channel)
                elif msg_type == "set_trace_depth":
                    level = data.get("level", "full")
                    try:
                        from merkaba.web.diagnostics import TraceDepth
                        store = websocket.app.state.diagnostics_store
                        store.set_trace_depth(TraceDepth(level))
                    except (ValueError, AttributeError):
                        pass
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Control receive error")

    try:
        # Send initial state immediately (no diagnostics yet — not subscribed)
        state = _build_state(websocket)
        await websocket.send_json(state)

        # Run heartbeat and receive concurrently
        heartbeat_task = asyncio.create_task(heartbeat_loop())
        receive_task = asyncio.create_task(receive_loop())
        done, pending = await asyncio.wait(
            [heartbeat_task, receive_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Control WebSocket error")
