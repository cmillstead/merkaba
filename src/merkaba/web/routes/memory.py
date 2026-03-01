from fastapi import APIRouter, Query, Request

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
    business_id: int | None = None,
    category: str | None = None,
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
    return {"facts": facts}


@router.get("/decisions")
async def list_decisions(
    request: Request,
    business_id: int | None = None,
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
    return {"decisions": decisions}


@router.get("/learnings")
async def list_learnings(request: Request):
    """List shared learnings."""
    store = request.app.state.memory_store
    return {"learnings": store.get_learnings()}
