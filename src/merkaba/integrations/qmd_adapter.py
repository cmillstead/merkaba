# src/merkaba/integrations/qmd_adapter.py
"""QMD document search adapter — on-device hybrid search for markdown files."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from urllib.request import urlopen, Request

from merkaba.integrations.base import IntegrationAdapter, register_adapter

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8181


@dataclass
class QMDAdapter(IntegrationAdapter):
    """Adapter for QMD (https://github.com/tobi/qmd) on-device document search."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    _base_url: str = field(default="", init=False, repr=False)

    def __post_init__(self):
        self._base_url = f"http://{self.host}:{self.port}"

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        """Make an HTTP request to the QMD daemon."""
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body else None
        req = Request(url, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def connect(self) -> bool:
        try:
            self._request("GET", "/health")
            self._connected = True
            return True
        except Exception as e:
            logger.warning("QMD connect failed: %s", e)
            self._connected = False
            return False

    def execute(self, action: str, params: dict | None = None) -> dict:
        params = params or {}
        if not self._connected:
            return {"ok": False, "error": "Not connected — call connect() first"}
        if action == "search":
            return self._search(params)
        elif action == "get":
            return self._get(params)
        elif action == "status":
            return self._status(params)
        else:
            return {"ok": False, "error": f"Unknown action: {action}"}

    def health_check(self) -> dict:
        if not self._connected:
            return {"ok": False, "adapter": "qmd"}
        try:
            data = self._request("GET", "/health")
            return {"ok": True, "adapter": "qmd", "status": data}
        except Exception as e:
            logger.error("QMD health check failed: %s", e)
            return {"ok": False, "adapter": "qmd", "error": str(e)}

    def _search(self, params: dict) -> dict:
        query = params.get("query")
        if not query:
            return {"ok": False, "error": "Missing required param: query"}
        limit = params.get("limit", 5)
        collection = params.get("collection")
        try:
            mcp_body = {
                "method": "tools/call",
                "params": {
                    "name": "qmd_deep_search",
                    "arguments": {"query": query, "n": limit},
                },
            }
            if collection:
                mcp_body["params"]["arguments"]["collection"] = collection
            data = self._request("POST", "/mcp", mcp_body)
            results = data.get("result", [])
            return {"ok": True, "results": results, "count": len(results)}
        except Exception as e:
            logger.error("QMD search failed: %s", e)
            return {"ok": False, "error": str(e), "results": []}

    def _get(self, params: dict) -> dict:
        path = params.get("path")
        if not path:
            return {"ok": False, "error": "Missing required param: path"}
        try:
            mcp_body = {
                "method": "tools/call",
                "params": {
                    "name": "qmd_get",
                    "arguments": {"path": path},
                },
            }
            data = self._request("POST", "/mcp", mcp_body)
            result = data.get("result", {})
            content = result.get("fields", {}).get("text", "") if isinstance(result, dict) else str(result)
            return {"ok": True, "content": content, "path": path}
        except Exception as e:
            logger.error("QMD get failed: %s", e)
            return {"ok": False, "error": str(e)}

    def disconnect(self) -> None:
        self._connected = False

    def _status(self, params: dict) -> dict:
        try:
            mcp_body = {
                "method": "tools/call",
                "params": {"name": "qmd_status", "arguments": {}},
            }
            data = self._request("POST", "/mcp", mcp_body)
            return {"ok": True, "status": data.get("result", data)}
        except Exception as e:
            logger.error("QMD status failed: %s", e)
            return {"ok": False, "error": str(e)}

    # --- Async wrappers (delegate to sync via asyncio.to_thread) ---

    async def _request_async(self, method: str, path: str, body: dict | None = None) -> dict:
        """Async wrapper around _request — runs the blocking HTTP call in a thread."""
        return await asyncio.to_thread(self._request, method, path, body)

    async def _search_async(self, params: dict) -> dict:
        """Async wrapper around _search."""
        return await asyncio.to_thread(self._search, params)

    async def _get_async(self, params: dict) -> dict:
        """Async wrapper around _get."""
        return await asyncio.to_thread(self._get, params)

    async def _status_async(self, params: dict) -> dict:
        """Async wrapper around _status."""
        return await asyncio.to_thread(self._status, params)

    async def execute_async(self, action: str, params: dict | None = None) -> dict:
        """Async wrapper around execute — for use in async contexts (e.g. FastAPI)."""
        return await asyncio.to_thread(self.execute, action, params)


register_adapter("qmd", QMDAdapter)
