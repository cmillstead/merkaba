import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.routing import Mount

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get("/status")
async def system_status(request: Request):
    """Health check: Ollama reachable, DB sizes, scheduler status."""
    memory_store = request.app.state.memory_store
    task_queue = request.app.state.task_queue
    action_queue = request.app.state.action_queue

    # Check Ollama
    ollama_ok = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:11434/api/tags", timeout=3.0)
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    # DB sizes
    def _file_size(path: str) -> int | None:
        expanded = os.path.expanduser(path)
        try:
            return os.path.getsize(expanded)
        except OSError:
            return None

    return {
        "ollama": ollama_ok,
        "databases": {
            "memory": _file_size("~/.merkaba/memory.db"),
            "tasks": _file_size("~/.merkaba/tasks.db"),
            "actions": _file_size("~/.merkaba/actions.db"),
        },
        "counts": {
            "memory": memory_store.stats(),
            "tasks": task_queue.stats(),
            "actions": action_queue.stats(),
        },
    }


@router.get("/routes")
async def route_diagnostics(request: Request):
    """Route table diagnostic — shows order, type, and path for every registered route."""
    routes = []
    for i, route in enumerate(request.app.routes):
        entry = {
            "index": i,
            "type": type(route).__name__,
            "path": getattr(route, "path", None),
            "methods": sorted(route.methods) if getattr(route, "methods", None) else None,
        }
        if isinstance(route, Mount):
            entry["mounted_app"] = type(route.app).__name__
        routes.append(entry)
    return {"route_count": len(routes), "routes": routes}


@router.get("/diagnostics")
async def diagnostics_state(request: Request):
    """Current diagnostics snapshot — ring buffer contents, active connections, summary."""
    store = getattr(request.app.state, "diagnostics_store", None)
    if store is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Diagnostics store not initialized"},
        )
    return store.to_dict()


@router.get("/token-usage")
async def token_usage(
    group_by: str = "model",
    days: int = 7,
):
    """Token usage summary, grouped by model or worker_type."""
    try:
        from merkaba.observability.tokens import TokenUsageStore
    except ImportError as e:
        return JSONResponse(
            status_code=503,
            content={"usage": [], "error": f"TokenUsageStore not available: {e}"},
        )
    store = None
    try:
        store = TokenUsageStore()
        usage = store.get_summary(group_by=group_by, days=days)
        return {"usage": usage}
    except Exception:
        logger.exception("Failed to retrieve token usage data")
        return JSONResponse(
            status_code=500,
            content={"usage": [], "error": "Failed to retrieve token usage data"},
        )
    finally:
        if store is not None:
            store.close()


@router.get("/models")
async def list_models():
    """List available Ollama models."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:11434/api/tags", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            return {"models": data.get("models", [])}
    except Exception:
        logger.exception("Unable to connect to model provider")
        return JSONResponse(
            status_code=503,
            content={"models": [], "error": "Unable to connect to model provider"},
        )
