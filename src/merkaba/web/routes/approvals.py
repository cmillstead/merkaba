from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["approvals"])


class DecisionBody(BaseModel):
    reason: str | None = None


class ApproveBody(BaseModel):
    totp_code: str | None = None


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
async def approve_action(action_id: int, body: ApproveBody, request: Request):
    """Approve a pending action (with rate limiting and optional TOTP 2FA)."""
    from merkaba.approval.secure import (
        RateLimitExceeded,
        SecureApprovalManager,
        TotpInvalid,
        TotpRequired,
    )

    queue = request.app.state.action_queue
    manager = SecureApprovalManager.from_config(queue)

    # If 2FA is configured, pass the totp_code through and let the manager
    # decide whether it's required for this specific action's autonomy level.
    # TotpRequired / TotpInvalid are surfaced as 403 to the caller.
    try:
        result = manager.approve(
            action_id,
            decided_by="web",
            totp_code=body.totp_code,
        )
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except TotpRequired:
        raise HTTPException(status_code=403, detail="TOTP code required")
    except TotpInvalid:
        raise HTTPException(status_code=403, detail="Invalid TOTP code")
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
