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
