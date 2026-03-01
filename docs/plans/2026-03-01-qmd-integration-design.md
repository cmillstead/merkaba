# QMD Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate QMD (on-device markdown search engine) as a Merkaba adapter with agent tools, plus Claude Code MCP config and launchd daemon.

**Architecture:** Thin HTTP client adapter (`QMDAdapter`) calling a QMD HTTP daemon on localhost:8181. Two agent tools (`document_search`, `document_get`) registered in the tool registry. No new Python dependencies — uses stdlib `urllib` for HTTP.

**Tech Stack:** Python stdlib (`urllib.request`, `json`), QMD (`@tobilu/qmd` via npm), launchd, existing Merkaba IntegrationAdapter pattern.

---

### Task 1: QMD Adapter — Tests

**Files:**
- Create: `tests/test_qmd_adapter.py`

**Step 1: Write adapter test file with all test cases**

```python
# tests/test_qmd_adapter.py
"""Tests for QMD document search adapter."""

import json
from unittest.mock import MagicMock, patch

import pytest

from merkaba.integrations.base import ADAPTER_REGISTRY


def test_qmd_adapter_registered():
    from merkaba.integrations import qmd_adapter  # noqa: F401
    assert "qmd" in ADAPTER_REGISTRY


# --- Fixtures ---


@pytest.fixture
def adapter():
    from merkaba.integrations.qmd_adapter import QMDAdapter
    return QMDAdapter(name="qmd")


@pytest.fixture
def mock_urlopen():
    """Mock urllib.request.urlopen for HTTP calls."""
    with patch("merkaba.integrations.qmd_adapter.urlopen") as mock:
        yield mock


def _make_response(data: dict, status: int = 200) -> MagicMock:
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(data).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# --- connect ---


class TestConnect:
    def test_connect_success(self, adapter, mock_urlopen):
        mock_urlopen.return_value = _make_response({"status": "ok"})
        assert adapter.connect() is True
        assert adapter.is_connected is True

    def test_connect_failure(self, adapter, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        assert adapter.connect() is False
        assert adapter.is_connected is False


# --- health_check ---


class TestHealthCheck:
    def test_health_check_ok(self, adapter, mock_urlopen):
        mock_urlopen.return_value = _make_response({"status": "ok"})
        adapter._connected = True
        result = adapter.health_check()
        assert result["ok"] is True
        assert result["adapter"] == "qmd"

    def test_health_check_not_connected(self, adapter, mock_urlopen):
        result = adapter.health_check()
        assert result["ok"] is False


# --- execute: search ---


class TestSearch:
    def test_search_returns_results(self, adapter, mock_urlopen):
        adapter._connected = True
        search_response = {
            "result": [
                {"id": "abc123", "score": 0.85, "fields": {"path": "notes/test.md", "text": "Test content"}},
                {"id": "def456", "score": 0.72, "fields": {"path": "docs/readme.md", "text": "Readme content"}},
            ]
        }
        mock_urlopen.return_value = _make_response(search_response)
        result = adapter.execute("search", {"query": "test query", "limit": 5})
        assert result["ok"] is True
        assert len(result["results"]) == 2

    def test_search_missing_query(self, adapter, mock_urlopen):
        adapter._connected = True
        result = adapter.execute("search", {})
        assert result["ok"] is False
        assert "query" in result["error"].lower()

    def test_search_not_connected(self, adapter, mock_urlopen):
        result = adapter.execute("search", {"query": "test"})
        assert result["ok"] is False
        assert "not connected" in result["error"].lower()


# --- execute: get ---


class TestGet:
    def test_get_by_path(self, adapter, mock_urlopen):
        adapter._connected = True
        get_response = {
            "result": {"id": "abc123", "fields": {"path": "notes/test.md", "text": "Full document content here"}}
        }
        mock_urlopen.return_value = _make_response(get_response)
        result = adapter.execute("get", {"path": "notes/test.md"})
        assert result["ok"] is True
        assert "content" in result

    def test_get_missing_path(self, adapter, mock_urlopen):
        adapter._connected = True
        result = adapter.execute("get", {})
        assert result["ok"] is False
        assert "path" in result["error"].lower()


# --- execute: status ---


class TestStatus:
    def test_status_returns_info(self, adapter, mock_urlopen):
        adapter._connected = True
        status_response = {"status": "ok", "collections": 2, "documents": 150}
        mock_urlopen.return_value = _make_response(status_response)
        result = adapter.execute("status", {})
        assert result["ok"] is True

    def test_unknown_action(self, adapter, mock_urlopen):
        adapter._connected = True
        result = adapter.execute("unknown_action", {})
        assert result["ok"] is False
        assert "unknown" in result["error"].lower()


# --- HTTP error handling ---


class TestErrorHandling:
    def test_http_error(self, adapter, mock_urlopen):
        adapter._connected = True
        mock_urlopen.side_effect = Exception("HTTP 500")
        result = adapter.execute("status", {})
        assert result["ok"] is False

    def test_malformed_json(self, adapter, mock_urlopen):
        adapter._connected = True
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b"not json"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp
        result = adapter.execute("status", {})
        assert result["ok"] is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_qmd_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'merkaba.integrations.qmd_adapter'`

**Step 3: Commit failing tests**

```bash
git add tests/test_qmd_adapter.py
git commit -m "test: add QMD adapter tests (red)"
```

---

### Task 2: QMD Adapter — Implementation

**Files:**
- Create: `src/merkaba/integrations/qmd_adapter.py`
- Modify: `src/merkaba/integrations/__init__.py`

**Step 1: Write the adapter**

```python
# src/merkaba/integrations/qmd_adapter.py
"""QMD document search adapter — on-device hybrid search for markdown files."""

import json
import logging
from dataclasses import dataclass, field
from urllib.request import urlopen, Request
from urllib.error import URLError

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


register_adapter("qmd", QMDAdapter)
```

**Step 2: Register adapter in `__init__.py`**

Add to `src/merkaba/integrations/__init__.py` after the calendar adapter block:

```python
try:
    from merkaba.integrations import qmd_adapter  # noqa: F401
except ImportError:
    logger.debug("QMD not available -- QMD adapter unavailable")
```

**Step 3: Run tests to verify they pass**

Run: `pytest tests/test_qmd_adapter.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/merkaba/integrations/qmd_adapter.py src/merkaba/integrations/__init__.py
git commit -m "feat: add QMD document search adapter"
```

---

### Task 3: Agent Tools — Tests

**Files:**
- Create: `tests/test_qmd_tools.py`

**Step 1: Write tool tests**

```python
# tests/test_qmd_tools.py
"""Tests for QMD document search/get agent tools."""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_urlopen():
    with patch("merkaba.integrations.qmd_adapter.urlopen") as mock:
        yield mock


def _make_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = json.dumps(data).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestDocumentSearchTool:
    def test_tool_exists(self):
        from merkaba.tools.builtin.qmd import document_search
        assert document_search.name == "document_search"

    def test_tool_is_safe_tier(self):
        from merkaba.tools.builtin.qmd import document_search
        from merkaba.tools.base import PermissionTier
        assert document_search.permission_tier == PermissionTier.SAFE

    def test_search_executes(self, mock_urlopen):
        # Mock health check for connect
        health_resp = _make_response({"status": "ok"})
        search_resp = _make_response({"result": [{"id": "a", "score": 0.9, "fields": {"path": "test.md", "text": "content"}}]})
        mock_urlopen.side_effect = [health_resp, search_resp]

        from merkaba.tools.builtin.qmd import document_search
        result = document_search.execute(query="test")
        assert result.success is True

    def test_search_daemon_down(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        from merkaba.tools.builtin.qmd import document_search
        result = document_search.execute(query="test")
        # Should return graceful error, not crash
        assert result.success is True
        assert "unavailable" in result.output.lower() or "error" in result.output.lower()


class TestDocumentGetTool:
    def test_tool_exists(self):
        from merkaba.tools.builtin.qmd import document_get
        assert document_get.name == "document_get"

    def test_tool_is_safe_tier(self):
        from merkaba.tools.builtin.qmd import document_get
        from merkaba.tools.base import PermissionTier
        assert document_get.permission_tier == PermissionTier.SAFE

    def test_get_executes(self, mock_urlopen):
        health_resp = _make_response({"status": "ok"})
        get_resp = _make_response({"result": {"fields": {"path": "test.md", "text": "Full content"}}})
        mock_urlopen.side_effect = [health_resp, get_resp]

        from merkaba.tools.builtin.qmd import document_get
        result = document_get.execute(path="test.md")
        assert result.success is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_qmd_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'merkaba.tools.builtin.qmd'`

**Step 3: Commit failing tests**

```bash
git add tests/test_qmd_tools.py
git commit -m "test: add QMD agent tool tests (red)"
```

---

### Task 4: Agent Tools — Implementation

**Files:**
- Create: `src/merkaba/tools/builtin/qmd.py`
- Modify: `src/merkaba/tools/builtin/__init__.py`
- Modify: `src/merkaba/agent.py`

**Step 1: Write the tool module**

```python
# src/merkaba/tools/builtin/qmd.py
"""Agent tools for QMD document search and retrieval."""

import json
import logging

from merkaba.tools.base import Tool, PermissionTier

logger = logging.getLogger(__name__)


def _get_adapter():
    """Get a connected QMD adapter, or None if unavailable."""
    from merkaba.integrations.qmd_adapter import QMDAdapter
    adapter = QMDAdapter(name="qmd")
    if adapter.connect():
        return adapter
    return None


def _document_search(query: str, limit: int = 5, collection: str | None = None) -> str:
    """Search personal documents and notes via QMD."""
    adapter = _get_adapter()
    if not adapter:
        return "QMD document search unavailable — daemon not running on localhost:8181"

    params = {"query": query, "limit": limit}
    if collection:
        params["collection"] = collection
    result = adapter.execute("search", params)
    if not result["ok"]:
        return f"Search error: {result.get('error', 'unknown')}"
    return json.dumps(result["results"], indent=2)


def _document_get(path: str) -> str:
    """Retrieve a document by path or ID from QMD."""
    adapter = _get_adapter()
    if not adapter:
        return "QMD document search unavailable — daemon not running on localhost:8181"

    result = adapter.execute("get", {"path": path})
    if not result["ok"]:
        return f"Get error: {result.get('error', 'unknown')}"
    return result.get("content", "")


document_search = Tool(
    name="document_search",
    description="Search personal documents, notes, and project markdown files. Returns ranked results with relevance scores.",
    function=_document_search,
    permission_tier=PermissionTier.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query text"},
            "limit": {"type": "integer", "description": "Max results to return (default 5)"},
            "collection": {"type": "string", "description": "Optional collection name to search within (e.g. 'obsidian', 'src')"},
        },
        "required": ["query"],
    },
)

document_get = Tool(
    name="document_get",
    description="Retrieve a document's full content by file path or document ID.",
    function=_document_get,
    permission_tier=PermissionTier.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Document path or #docid from search results"},
        },
        "required": ["path"],
    },
)
```

**Step 2: Export from `__init__.py`**

Add to `src/merkaba/tools/builtin/__init__.py`:

```python
# After the existing imports, add:
try:
    from merkaba.tools.builtin.qmd import document_search, document_get
except ImportError:
    document_search = None
    document_get = None
```

And update `__all__` to include `"document_search"` and `"document_get"`.

**Step 3: Register tools in agent**

In `src/merkaba/agent.py`, in `_register_builtin_tools()` after `self.registry.register(bash)`, add:

```python
        # Document search tools (QMD)
        if document_search is not None:
            self.registry.register(document_search)
        if document_get is not None:
            self.registry.register(document_get)
```

And add to the import block at the top:

```python
from merkaba.tools.builtin import document_search, document_get
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_qmd_tools.py tests/test_qmd_adapter.py -v`
Expected: All PASS

**Step 5: Run full test suite to check for regressions**

Run: `pytest --timeout=30 -x -q`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add src/merkaba/tools/builtin/qmd.py src/merkaba/tools/builtin/__init__.py src/merkaba/agent.py
git commit -m "feat: add document_search and document_get agent tools (QMD)"
```

---

### Task 5: launchd Plist

**Files:**
- Create: `src/merkaba/resources/com.qmd.server.plist`

**Step 1: Write the launchd plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.qmd.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/qmd</string>
        <string>mcp</string>
        <string>--http</string>
        <string>--port</string>
        <string>8181</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/cevin/.cache/qmd/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/cevin/.cache/qmd/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

Note: The `qmd` binary path may vary. Check with `which qmd` after install. If installed via `npm install -g`, it's typically at the npm global bin path (check `npm bin -g`).

**Step 2: Commit**

```bash
git add src/merkaba/resources/com.qmd.server.plist
git commit -m "feat: add QMD launchd plist for HTTP daemon"
```

---

### Task 6: Documentation

**Files:**
- Create: `docs/integrations/qmd.md`
- Modify: `README.md`

**Step 1: Write the QMD integration guide**

Create `docs/integrations/qmd.md` with:
- Prerequisites (Node.js >= 22 or Bun)
- Installation (`npm install -g @tobilu/qmd`)
- Collection setup (obsidian, src)
- Context tags
- Embedding generation
- Claude Code MCP config (`~/.claude/settings.json`)
- launchd daemon install (`launchctl load`)
- Merkaba config (`~/.merkaba/config.json` qmd section)
- Verification steps (`qmd status`, `merkaba integrations test qmd`)
- Maintenance (`qmd update`, `qmd embed -f`)

**Step 2: Update README.md**

Add a "Third-Party Integrations" section before the "Security" section:

```markdown
## Third-Party Integrations

Merkaba integrates with open source tools to extend agent capabilities. These are optional — the framework works fully without them.

| Tool | Purpose | License |
|------|---------|---------|
| [QMD](https://github.com/tobi/qmd) | On-device document search (hybrid BM25 + vector + re-ranking) | MIT |

See [docs/integrations/](docs/integrations/) for setup guides.
```

**Step 3: Commit**

```bash
git add docs/integrations/qmd.md README.md
git commit -m "docs: add QMD integration guide and third-party integrations section"
```

---

### Task 7: Verify End-to-End

**Step 1: Run full test suite**

Run: `pytest --timeout=30 -x -q`
Expected: All tests pass, including new QMD tests

**Step 2: Verify adapter registration**

Run: `python -c "from merkaba.integrations import list_adapters; print(list_adapters())"`
Expected: Output includes `'qmd'`

**Step 3: Verify tool registration**

Run: `python -c "from merkaba.tools.builtin import document_search, document_get; print(document_search.name, document_get.name)"`
Expected: `document_search document_get`

**Step 4: Final commit if any fixups needed**

```bash
git add -u
git commit -m "fix: QMD integration fixups"
```
