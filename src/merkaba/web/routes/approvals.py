from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["approvals"])


class DecisionBody(BaseModel):
    reason: str | None = None


@router.get("")
async def list_approvals(
    request: Request,
    status: str | None = "pending",
    business_id: int | None = None,
):
    """List approvals (defaults to pending)."""
    queue = request.app.state.action_queue
    return {"approvals": queue.list_actions(status=status, business_id=business_id)}


@router.post("/{action_id}/approve")
async def approve_action(action_id: int, request: Request):
    """Approve a pending action (with rate limiting, 2FA skipped for web)."""
    from merkaba.approval.secure import RateLimitExceeded, SecureApprovalManager

    queue = request.app.state.action_queue
    manager = SecureApprovalManager.from_config(queue)
    try:
        result = manager.approve(action_id, decided_by="web")
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    if not result:
        raise HTTPException(status_code=404, detail="Action not found")
    return {"id": action_id, "status": "approved"}


@router.post("/{action_id}/deny")
async def deny_action(action_id: int, body: DecisionBody, request: Request):
    """Deny a pending action with optional reason."""
    queue = request.app.state.action_queue
    result = queue.decide(action_id, approved=False, decided_by="web")
    if not result:
        raise HTTPException(status_code=404, detail="Action not found")
    return {"id": action_id, "status": "denied", "reason": body.reason}


@router.get("/stats")
async def approval_stats(request: Request):
    """Overall approval statistics."""
    queue = request.app.state.action_queue
    return {"stats": queue.stats()}
