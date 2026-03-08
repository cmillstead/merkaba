import json
import logging
import os

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.routing import Mount

from merkaba.config.utils import atomic_write_json, deep_mask_secrets
from merkaba.paths import merkaba_home as _merkaba_home, db_path as _db_path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

# Keys that the web API is allowed to write.  Security-critical keys
# (security.*, auto_approve_level, cloud_providers, totp_*) are blocked
# and must be changed via the CLI or direct config editing.
WRITABLE_CONFIG_KEYS = frozenset(
    {
        "models",
        "schedules",
        "cors_origins",
        "default_business_id",
        "log_level",
        "debug",
        "max_retries",
        "temperature",
    }
)

BLOCKED_CONFIG_KEYS = frozenset(
    {
        "api_key",
        "security",
        "auto_approve_level",
        "cloud_providers",
        "totp_secret",
        "totp_threshold",
        "encryption_key",
        "permissions",
        "permission_tiers",
        "path_restrictions",
        "shell_allowlist",
    }
)


class ConfigUpdateBody(BaseModel):
    """Pydantic model for config update requests.

    Accepts arbitrary JSON but validation is done at the route level
    against the allowlist.
    """

    model_config = {"extra": "allow"}


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
        try:
            return os.path.getsize(path)
        except OSError:
            return None

    return {
        "ollama": ollama_ok,
        "databases": {
            "memory": _file_size(_db_path("memory")),
            "tasks": _file_size(_db_path("tasks")),
            "actions": _file_size(_db_path("actions")),
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
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"usage": [], "error": "Token usage tracking is not available"},
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
        base_dir = _merkaba_home()
    return os.path.join(base_dir, "config.json")


@router.get("/config")
async def get_config(request: Request):
    """Read config from disk, masking sensitive fields."""
    from merkaba.config.loader import load_config

    path = _config_path(request)
    config = load_config(path=path, use_cache=False)
    return deep_mask_secrets(config)


@router.put("/config")
async def put_config(request: Request, body: ConfigUpdateBody):
    """Update config on disk. Only allows WRITABLE_CONFIG_KEYS; blocks security keys."""
    updates = body.model_dump(exclude_unset=True)

    # Reject blocked keys with a clear error
    blocked = [k for k in updates if k in BLOCKED_CONFIG_KEYS]
    if blocked:
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Cannot modify security-sensitive keys via web API: {', '.join(sorted(blocked))}. "
                "Use the CLI or edit config.json directly."
            },
        )

    # Reject unknown keys not in the writable set
    unknown = [k for k in updates if k not in WRITABLE_CONFIG_KEYS]
    if unknown:
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Unknown config keys: {', '.join(sorted(unknown))}. "
                f"Allowed keys: {', '.join(sorted(WRITABLE_CONFIG_KEYS))}"
            },
        )

    # Validate: if "models" is present, it must be a dict
    if "models" in updates and not isinstance(updates["models"], dict):
        return JSONResponse(
            status_code=422,
            content={"detail": "'models' must be a JSON object"},
        )

    # Block safety-critical model sub-keys
    if isinstance(updates.get("models"), dict) and "classifier" in updates["models"]:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Cannot modify 'models.classifier' via web API — "
                "it controls safety classification. Use the CLI or edit config.json directly."
            },
        )

    path = _config_path(request)

    # Read existing config
    from merkaba.config.loader import load_config

    existing = load_config(path=path, use_cache=False)

    # Merge: dict-valued keys get update(), others get replaced
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            existing[key].update(value)
        else:
            existing[key] = value

    # Write atomically with secure permissions
    atomic_write_json(path, existing)
    try:
        from merkaba.security.file_permissions import ensure_secure_permissions

        ensure_secure_permissions(path)
    except ImportError:
        pass

    # Invalidate the config cache so subsequent reads pick up the new values
    from merkaba.config.loader import clear_cache

    clear_cache()

    return deep_mask_secrets(existing)
