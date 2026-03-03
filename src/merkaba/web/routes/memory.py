from fastapi import APIRouter, HTTPException, Path, Query, Request, Response

router = APIRouter(tags=["memory"])


@router.get("/search")
async def search_memory(request: Request, q: str = Query(..., min_length=1)):
    """Semantic search across memory."""
    retrieval = request.app.state.memory_retrieval
    results = retrieval.recall(q, limit=10)
    return {"query": q, "results": results}


@router.get("/facts")
async def list_facts(
    request: Request,
    business_id: int | None = Query(None, ge=1),
    category: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List facts with optional filters."""
    store = request.app.state.memory_store
    if business_id is not None:
        facts = store.get_facts(business_id, category=category)
    else:
        # Get facts across all businesses
        businesses = store.list_businesses()
        facts = []
        for biz in businesses:
            facts.extend(store.get_facts(biz["id"], category=category))
    total = len(facts)
    page = facts[offset : offset + limit]
    return {"items": page, "total": total, "limit": limit, "offset": offset}


@router.get("/decisions")
async def list_decisions(
    request: Request,
    business_id: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List decisions."""
    store = request.app.state.memory_store
    if business_id is not None:
        decisions = store.get_decisions(business_id)
    else:
        businesses = store.list_businesses()
        decisions = []
        for biz in businesses:
            decisions.extend(store.get_decisions(biz["id"]))
    total = len(decisions)
    page = decisions[offset : offset + limit]
    return {"items": page, "total": total, "limit": limit, "offset": offset}


@router.delete("/facts/{fact_id}")
async def delete_fact(
    request: Request,
    fact_id: int = Path(gt=0),
):
    """Permanently delete a memory fact by ID."""
    store = request.app.state.memory_store
    deleted = store.hard_delete("facts", fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found")
    return Response(status_code=204)


@router.get("/learnings")
async def list_learnings(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List shared learnings."""
    store = request.app.state.memory_store
    learnings = store.get_learnings()
    total = len(learnings)
    page = learnings[offset : offset + limit]
    return {"items": page, "total": total, "limit": limit, "offset": offset}
