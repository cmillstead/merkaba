import json
import logging
import os

import httpx
from fastapi import APIRouter, Query, Request
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
    days: int = Query(default=7, ge=1, le=365),
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


def _config_path(request: Request) -> str:
    """Resolve the config.json path from app state or default."""
    base_dir = getattr(request.app.state, "merkaba_base_dir", None)
    if base_dir is None:
        base_dir = os.path.expanduser("~/.merkaba")
    return os.path.join(base_dir, "config.json")


def _mask_api_key(config: dict) -> dict:
    """Return a copy of config with the api_key field masked."""
    result = dict(config)
    key = result.get("api_key")
    if key is not None:
        if len(key) > 8:
            result["api_key"] = key[:4] + "***" + key[-4:]
        else:
            result["api_key"] = "***"
    return result


@router.get("/config")
async def get_config(request: Request):
    """Read config from disk, masking sensitive fields."""
    path = _config_path(request)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return _mask_api_key(config)


@router.put("/config")
async def put_config(request: Request):
    """Update config on disk. Merges dict-valued keys; skips api_key."""
    body = await request.json()

    # Validate: if "models" is present, it must be a dict
    if "models" in body and not isinstance(body["models"], dict):
        return JSONResponse(
            status_code=422,
            content={"detail": "'models' must be a JSON object"},
        )

    path = _config_path(request)

    # Read existing config
    existing: dict = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Merge: dict-valued keys get update(), others get replaced; skip api_key
    for key, value in body.items():
        if key == "api_key":
            continue
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            existing[key].update(value)
        else:
            existing[key] = value

    # Write back
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)

    return _mask_api_key(existing)
