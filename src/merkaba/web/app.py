import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, WebSocketException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import HTTPConnection
from starlette.types import Receive, Scope, Send

from merkaba.memory.store import MemoryStore
from merkaba.memory.retrieval import MemoryRetrieval
from merkaba.orchestration.queue import TaskQueue
from merkaba.approval.queue import ActionQueue

logger = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """StaticFiles subclass that rejects non-HTTP scopes instead of crashing.

    Starlette's Mount("/") matches ALL scopes (HTTP and WebSocket) with
    Match.FULL.  If a WebSocket connection reaches this mount — due to a
    routing edge-case, race condition, or an unrecognised WS path — the
    base StaticFiles raises ``assert scope["type"] == "http"``, killing
    the ASGI handler.  This subclass returns a clean close instead.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            logger.warning(
                "SPAStaticFiles received non-HTTP scope type=%s path=%s — rejecting",
                scope["type"],
                scope.get("path", "?"),
            )
            if scope["type"] == "websocket":
                # Accept then immediately close so the client gets a clean signal
                await send({"type": "websocket.close", "code": 4004})
            return
        await super().__call__(scope, receive, send)


def _load_api_key() -> str | None:
    config_path = os.path.expanduser("~/.merkaba/config.json")
    try:
        with open(config_path) as f:
            return json.load(f).get("api_key")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def verify_api_key(conn: HTTPConnection):
    """Dependency that checks X-API-Key header if one is configured.

    Uses HTTPConnection (parent of both Request and WebSocket) so this
    dependency works on HTTP *and* WebSocket endpoints.

    For WebSocket connections, if no Authorization or X-API-Key header is
    present, the ``token`` query parameter is also accepted.  This allows
    browser-native WebSocket clients (which cannot set custom headers) to
    authenticate via ``ws://host/ws/chat?token=<api_key>``.
    """
    expected = conn.app.state.api_key
    if expected is None:
        return
    import hmac

    is_websocket = conn.scope["type"] == "websocket"

    # Prefer the Authorization Bearer token, then fall back to X-API-Key header.
    # For WebSocket connections, also accept the ?token= query parameter as a
    # last resort (browsers cannot set custom headers on WebSocket handshakes).
    provided = (
        conn.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        or conn.headers.get("X-API-Key")
        or (conn.query_params.get("token") if is_websocket else None)
        or ""
    )

    if not hmac.compare_digest(provided, expected):
        if is_websocket:
            raise WebSocketException(code=4001, reason="Invalid API key")
        raise HTTPException(status_code=401, detail="Invalid API key")


def _make_lifespan(db_overrides: dict | None = None):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup — use overrides if provided (for testing)
        if db_overrides:
            app.state.api_key = None
            if app.state.api_key is None:
                logger.warning(
                    "Web server running without authentication. "
                    "Set 'api_key' in ~/.merkaba/config.json to require API key authentication. "
                    "All endpoints are currently accessible without credentials."
                )
            app.state.memory_store = db_overrides["memory_store"]
            app.state.memory_retrieval = MemoryRetrieval(store=app.state.memory_store)
            app.state.task_queue = db_overrides["task_queue"]
            app.state.action_queue = db_overrides["action_queue"]
            app.state.merkaba_base_dir = db_overrides.get("merkaba_base_dir")
            app.state.session_pool = None  # Tests can set this if needed

        else:
            try:
                from merkaba.observability.tracing import setup_logging
                setup_logging()
            except Exception:
                pass
            app.state.api_key = _load_api_key()
            if app.state.api_key is None:
                logger.warning(
                    "Web server running without authentication. "
                    "Set 'api_key' in ~/.merkaba/config.json to require API key authentication. "
                    "All endpoints are currently accessible without credentials."
                )
            app.state.merkaba_base_dir = None  # use ~/.merkaba default
            app.state.memory_store = MemoryStore()
            app.state.memory_retrieval = MemoryRetrieval(store=app.state.memory_store)
            app.state.task_queue = TaskQueue()
            app.state.action_queue = ActionQueue()

            from merkaba.orchestration.session_pool import SessionPool
            app.state.session_pool = SessionPool()

            # Ensure default scheduled worker tasks exist
            from merkaba.web.routes.control import ensure_scheduled_workers
            ensure_scheduled_workers(app.state.task_queue)

            # Validate configuration
            try:
                from merkaba.config.validation import validate_config, Severity
                config_path = os.path.expanduser("~/.merkaba/config.json")
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
                    config = {}
                issues = validate_config(config, Path(os.path.expanduser("~/.merkaba")))
                for issue in issues:
                    if issue.severity == Severity.ERROR:
                        logger.error("Config: [%s] %s", issue.component, issue.message)
                    elif issue.severity == Severity.WARNING:
                        logger.warning("Config: [%s] %s", issue.component, issue.message)
                    else:
                        logger.info("Config: [%s] %s", issue.component, issue.message)
            except Exception as e:
                logger.warning("Config validation failed: %s", e)
        yield
        # Shutdown
        app.state.memory_store.close()
        app.state.task_queue.close()
        app.state.action_queue.close()
    return lifespan


def create_app(db_overrides: dict | None = None) -> FastAPI:
    app = FastAPI(
        title="Merkaba Mission Control",
        version="0.1.0",
        lifespan=_make_lifespan(db_overrides),
    )

    # Build CORS origins: start with the hard-coded dev origins, then merge
    # any user-configured origins from ~/.merkaba/config.json.  This is done
    # eagerly (before lifespan) because CORSMiddleware is not hot-reloadable.
    cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    try:
        with open(os.path.expanduser("~/.merkaba/config.json")) as _f:
            _user_cfg = json.load(_f)
        cors_origins.extend(_user_cfg.get("cors_origins", []))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from merkaba.web.middleware import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)

    # Register routes
    from merkaba.web.routes.system import router as system_router
    from merkaba.web.routes.businesses import router as businesses_router
    from merkaba.web.routes.memory import router as memory_router
    from merkaba.web.routes.tasks import router as tasks_router
    from merkaba.web.routes.approvals import router as approvals_router
    from merkaba.web.routes.chat import router as chat_router
    from merkaba.web.routes.analytics import router as analytics_router
    from merkaba.web.routes.control import router as control_router
    from merkaba.web.routes.control import ws_router as control_ws_router

    app.include_router(system_router, prefix="/api/system", dependencies=[Depends(verify_api_key)])
    app.include_router(businesses_router, prefix="/api/businesses", dependencies=[Depends(verify_api_key)])
    app.include_router(memory_router, prefix="/api/memory", dependencies=[Depends(verify_api_key)])
    app.include_router(tasks_router, prefix="/api/tasks", dependencies=[Depends(verify_api_key)])
    app.include_router(approvals_router, prefix="/api/approvals", dependencies=[Depends(verify_api_key)])
    app.include_router(chat_router, dependencies=[Depends(verify_api_key)])
    app.include_router(analytics_router, prefix="/api/analytics", dependencies=[Depends(verify_api_key)])
    app.include_router(control_router, prefix="/api/control", dependencies=[Depends(verify_api_key)])
    app.include_router(control_ws_router, dependencies=[Depends(verify_api_key)])

    # Diagnostics middleware — wraps all requests for tracing
    from merkaba.web.diagnostics import DiagnosticsStore, DiagnosticsMiddleware
    if not hasattr(app.state, "diagnostics_store"):
        app.state.diagnostics_store = DiagnosticsStore()
    app.add_middleware(DiagnosticsMiddleware, store=app.state.diagnostics_store)

    # Serve React static files if built
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="static")

    return app
