"""Cross-business analytics API routes."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["analytics"])


@router.get("/overview")
async def analytics_overview(request: Request, days: int = 30):
    """Aggregate analytics across all businesses."""
    store = request.app.state.memory_store
    task_queue = request.app.state.task_queue
    action_queue = request.app.state.action_queue

    businesses = store.list_businesses()

    # Tasks per business
    tasks_by_business = {}
    for biz in businesses:
        biz_id = biz["id"]
        tasks = task_queue.list_tasks(business_id=biz_id)
        completed = sum(1 for t in tasks if t.get("status") == "completed")
        pending = sum(1 for t in tasks if t.get("status") == "pending")
        running = sum(1 for t in tasks if t.get("status") == "running")
        tasks_by_business[str(biz_id)] = {
            "name": biz.get("name", f"Business {biz_id}"),
            "total": len(tasks),
            "completed": completed,
            "pending": pending,
            "running": running,
        }

    # Approvals summary
    approvals_summary = action_queue.stats()

    # Memory per business
    memory_by_business = {}
    for biz in businesses:
        biz_id = biz["id"]
        facts = store.get_facts(biz_id)
        decisions = store.get_decisions(biz_id)
        memory_by_business[str(biz_id)] = {
            "name": biz.get("name", f"Business {biz_id}"),
            "facts": len(facts),
            "decisions": len(decisions),
        }

    return {
        "businesses": len(businesses),
        "tasks_by_business": tasks_by_business,
        "approvals_summary": approvals_summary,
        "memory_by_business": memory_by_business,
    }
