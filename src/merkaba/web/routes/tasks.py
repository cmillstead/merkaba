from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["tasks"])


class TaskCreate(BaseModel):
    name: str
    task_type: str
    schedule: str | None = None
    business_id: int | None = None
    payload: dict | None = None
    autonomy_level: int = 1


class TaskUpdate(BaseModel):
    name: str | None = None
    schedule: str | None = None
    status: str | None = None
    payload: dict | None = None


@router.get("")
async def list_tasks(
    request: Request,
    status: str | None = None,
    business_id: int | None = None,
):
    """List tasks with optional filters."""
    queue = request.app.state.task_queue
    return {"tasks": queue.list_tasks(status=status, business_id=business_id)}


@router.get("/runs/recent")
async def recent_runs(request: Request, limit: int = 10):
    """Recent task runs across all tasks."""
    queue = request.app.state.task_queue
    tasks = queue.list_tasks()
    all_runs = []
    for task in tasks:
        runs = queue.get_runs(task["id"])
        for run in runs:
            run["task_name"] = task["name"]
            run["task_type"] = task["task_type"]
        all_runs.extend(runs)
    # Sort by started_at descending, take limit
    all_runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return {"runs": all_runs[:limit]}


@router.get("/{task_id}")
async def get_task(task_id: int, request: Request):
    """Get task detail with recent runs."""
    queue = request.app.state.task_queue
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    runs = queue.get_runs(task_id)
    return {"task": task, "runs": runs}


@router.post("")
async def create_task(body: TaskCreate, request: Request):
    """Create a new task."""
    queue = request.app.state.task_queue
    task_id = queue.add_task(
        name=body.name,
        task_type=body.task_type,
        schedule=body.schedule,
        business_id=body.business_id,
        payload=body.payload,
        autonomy_level=body.autonomy_level,
    )
    return {"id": task_id, "status": "created"}


@router.patch("/{task_id}")
async def update_task(task_id: int, body: TaskUpdate, request: Request):
    """Update a task (pause/resume/edit)."""
    queue = request.app.state.task_queue
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.status == "paused":
        queue.pause_task(task_id)
    elif body.status == "pending":
        queue.resume_task(task_id)
    else:
        updates = body.model_dump(exclude_none=True)
        if updates:
            queue.update_task(task_id, **updates)

    return {"id": task_id, "status": "updated"}
