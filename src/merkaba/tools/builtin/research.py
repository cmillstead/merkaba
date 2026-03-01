# src/merkaba/tools/builtin/research.py
"""Etsy research tools for Merkaba."""

import json
import os
from datetime import datetime
from typing import Any

from merkaba.research import ApifyClient, ResearchDatabase, analyze_listings
from merkaba.tools.base import PermissionTier, Tool


def _etsy_search(query: str, max_results: int = 50) -> dict[str, Any]:
    """Search Etsy for listings via Apify.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return (default: 50).

    Returns:
        Dict with query, listings, and total_results.
    """
    client = ApifyClient()
    listings = client.search_etsy(query, max_results)

    return {
        "query": query,
        "listings": listings,
        "total_results": len(listings),
    }


def _analyze_results(listings: list[dict[str, Any]], total_results: int) -> dict[str, Any]:
    """Analyze listings and compute market metrics.

    Args:
        listings: List of normalized listing dicts.
        total_results: Total number of search results.

    Returns:
        Dict with demand_score, competition_score, price metrics,
        opportunity_score, and recommendation.
    """
    return analyze_listings(listings, total_results)


def _save_research(
    research_data: dict[str, Any],
    db_path: str | None = None,
    export_dir: str | None = None,
) -> dict[str, Any]:
    """Save research to database and export JSON.

    Args:
        research_data: Dict with query, listings, and metrics.
        db_path: Custom database path (default: ~/.merkaba/research.db).
        export_dir: Directory to export JSON (default: ~/.merkaba/research/).

    Returns:
        Dict with run_id, db_path, and export_path.
    """
    if export_dir is None:
        export_dir = os.path.expanduser("~/.merkaba/research/")

    # Ensure export directory exists
    os.makedirs(export_dir, exist_ok=True)

    # Extract data
    query = research_data["query"]
    listings = research_data["listings"]
    metrics = research_data["metrics"]

    # Save to database
    db = ResearchDatabase(db_path)
    try:
        run_id = db.save_run(
            query=query,
            listing_count=len(listings),
            opportunity_score=metrics["opportunity_score"],
        )
        db.save_listings(run_id, listings)
        db.save_metrics(run_id, metrics)
    finally:
        db.close()

    # Export JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"research_{run_id}_{timestamp}.json"
    export_path = os.path.join(export_dir, filename)

    export_data = {
        "run_id": run_id,
        "query": query,
        "listings": listings,
        "metrics": metrics,
        "exported_at": datetime.now().isoformat(),
    }

    with open(export_path, "w") as f:
        json.dump(export_data, f, indent=2)

    return {
        "run_id": run_id,
        "db_path": db.db_path,
        "export_path": export_path,
    }


etsy_search = Tool(
    name="etsy_search",
    description="Search Etsy for listings matching a query via Apify API",
    function=_etsy_search,
    permission_tier=PermissionTier.MODERATE,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query to use on Etsy",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 50)",
            },
        },
        "required": ["query"],
    },
)

analyze_results = Tool(
    name="analyze_results",
    description="Analyze Etsy listings and compute market opportunity metrics",
    function=_analyze_results,
    permission_tier=PermissionTier.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "listings": {
                "type": "array",
                "description": "List of normalized listing dictionaries",
                "items": {"type": "object"},
            },
            "total_results": {
                "type": "integer",
                "description": "Total number of search results",
            },
        },
        "required": ["listings", "total_results"],
    },
)

save_research = Tool(
    name="save_research",
    description="Save research results to database and export as JSON",
    function=_save_research,
    permission_tier=PermissionTier.MODERATE,
    parameters={
        "type": "object",
        "properties": {
            "research_data": {
                "type": "object",
                "description": "Research data containing query, listings, and metrics",
            },
            "db_path": {
                "type": "string",
                "description": "Custom database path (default: ~/.merkaba/research.db)",
            },
            "export_dir": {
                "type": "string",
                "description": "Directory to export JSON (default: ~/.merkaba/research/)",
            },
        },
        "required": ["research_data"],
    },
)
