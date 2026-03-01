"""Memory search tool for the agent — lets it query Merkaba's structured memory."""

from merkaba.tools.base import Tool, PermissionTier

# This will be set by the Agent when it wires up memory.
# Using a mutable container so the tool closure captures the reference.
_retrieval_ref: dict = {"instance": None}
_business_ref: dict = {"id": None}


def set_active_business(business_id: int | None):
    """Set the active business ID for memory tool queries."""
    _business_ref["id"] = business_id


def _memory_search(query: str, limit: int = 5) -> str:
    """Search Merkaba's structured memory for facts, decisions, and learnings."""
    retrieval = _retrieval_ref.get("instance")
    if retrieval is None:
        return "Memory system not available."

    business_id = _business_ref.get("id")
    results = retrieval.recall(query, business_id=business_id, limit=limit)
    if not results:
        return f"No memories found for: {query}"

    lines = []
    for r in results:
        if r["type"] == "fact":
            lines.append(f"[Fact] {r.get('category', '')}: {r.get('key', '')} = {r.get('value', '')}")
        elif r["type"] == "decision":
            lines.append(f"[Decision] {r.get('decision', '')} — {r.get('reasoning', '')}")
        elif r["type"] == "learning":
            lines.append(f"[Learning] {r.get('insight', '')}")
    return "\n".join(lines)


def set_retrieval(retrieval_instance):
    """Wire the MemoryRetrieval instance into the tool."""
    _retrieval_ref["instance"] = retrieval_instance


memory_search = Tool(
    name="memory_search",
    description=(
        "Search Merkaba's long-term memory for facts, decisions, and learnings. "
        "Use this BEFORE doing web research to check if you already know the answer. "
        "Returns structured results from past research, stored facts, and decisions."
    ),
    function=_memory_search,
    permission_tier=PermissionTier.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in memory (semantic search)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5)",
            },
        },
        "required": ["query"],
    },
)
