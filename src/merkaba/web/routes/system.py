import os

import httpx
from fastapi import APIRouter, Request

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
            "memory": _file_size("~/.friday/memory.db"),
            "tasks": _file_size("~/.friday/tasks.db"),
            "actions": _file_size("~/.friday/actions.db"),
        },
        "counts": {
            "memory": memory_store.stats(),
            "tasks": task_queue.stats(),
            "actions": action_queue.stats(),
        },
    }


@router.get("/token-usage")
async def token_usage(
    group_by: str = "model",
    days: int = 7,
):
    """Token usage summary, grouped by model or worker_type."""
    try:
        from friday.observability.tokens import TokenUsageStore
    except ImportError as e:
        return {"usage": [], "error": f"TokenUsageStore not available: {e}"}
    store = None
    try:
        store = TokenUsageStore()
        usage = store.get_summary(group_by=group_by, days=days)
        return {"usage": usage}
    except Exception as e:
        return {"usage": [], "error": str(e)}
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
    except Exception as e:
        return {"models": [], "error": str(e)}
