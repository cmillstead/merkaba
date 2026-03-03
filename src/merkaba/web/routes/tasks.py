from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
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
    business_id: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List tasks with optional filters."""
    queue = request.app.state.task_queue
    tasks = queue.list_tasks(status=status, business_id=business_id)
    total = len(tasks)
    page = tasks[offset : offset + limit]
    return {"items": page, "total": total, "limit": limit, "offset": offset}


@router.get("/runs/recent")
async def recent_runs(request: Request, limit: int = Query(default=10, ge=1, le=1000)):
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
async def get_task(
    task_id: int = Path(gt=0),
    request: Request = None,
):
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


@router.delete("/{task_id}")
async def delete_task(
    request: Request,
    task_id: int = Path(gt=0),
):
    """Permanently delete a task and all its run history."""
    queue = request.app.state.task_queue
    deleted = queue.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return Response(status_code=204)


@router.patch("/{task_id}")
async def update_task(
    body: TaskUpdate,
    request: Request,
    task_id: int = Path(gt=0),
):
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
