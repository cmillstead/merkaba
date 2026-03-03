import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from merkaba.config.prompts import PromptLoader
from merkaba.security.sanitizer import sanitize_skill_content

router = APIRouter(tags=["businesses"])


@router.get("")
async def list_businesses(request: Request):
    """List all businesses."""
    store = request.app.state.memory_store
    return {"businesses": store.list_businesses()}


@router.get("/{business_id}")
async def get_business(business_id: int, request: Request):
    """Get business detail with recent facts and decisions."""
    store = request.app.state.memory_store
    business = store.get_business(business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    facts = store.get_facts(business_id)
    decisions = store.get_decisions(business_id)
    return {
        "business": business,
        "facts": facts[-20:],
        "decisions": decisions[-20:],
    }


class BusinessConfigUpdate(BaseModel):
    soul: str | None = None
    user: str | None = None


@router.get("/{business_id}/config")
async def get_business_config(business_id: int, request: Request):
    """Get per-business SOUL.md and USER.md content with fallback info."""
    base_dir = getattr(request.app.state, "merkaba_base_dir", None)
    loader = PromptLoader(base_dir=base_dir)
    soul, user = loader.load(business_id=business_id)
    info = loader.resolve(business_id=business_id)
    return {
        "soul": soul,
        "user": user,
        "soul_source": info["soul_source"],
        "user_source": info["user_source"],
    }


@router.put("/{business_id}/config")
async def update_business_config(
    business_id: int, body: BusinessConfigUpdate, request: Request
):
    """Update per-business SOUL.md and/or USER.md files."""
    base_dir = getattr(request.app.state, "merkaba_base_dir", None)
    loader = PromptLoader(base_dir=base_dir)
    biz_dir = loader.base_dir / "businesses" / str(business_id)
    biz_dir.mkdir(parents=True, exist_ok=True)

    if body.soul is not None:
        (biz_dir / "SOUL.md").write_text(sanitize_skill_content(body.soul), encoding="utf-8")
    if body.user is not None:
        (biz_dir / "USER.md").write_text(sanitize_skill_content(body.user), encoding="utf-8")

    # Return updated state
    soul, user = loader.load(business_id=business_id)
    info = loader.resolve(business_id=business_id)
    return {
        "soul": soul,
        "user": user,
        "soul_source": info["soul_source"],
        "user_source": info["user_source"],
    }
