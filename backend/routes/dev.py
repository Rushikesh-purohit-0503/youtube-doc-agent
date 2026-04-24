"""
Dev-only routes — only mounted when APP_ENV is 'dev' or 'development'.
Never included in production builds.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_current_user
from services.db import get_connection
from services.plan_service import PLAN_LIMITS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dev", tags=["dev"])

VALID_PLANS = list(PLAN_LIMITS.keys())


class SetPlanRequest(BaseModel):
    plan: str


@router.post("/set-plan")
async def set_plan(
    body: SetPlanRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """Instantly switch the authenticated user to any plan. Dev only."""
    if body.plan not in VALID_PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown plan '{body.plan}'. Valid: {VALID_PLANS}",
        )
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET plan = ? WHERE id = ?",
            (body.plan, user["id"]),
        )
    logger.info("[DEV] Set plan for user %s → %s", user["email"], body.plan)
    return {"success": True, "plan": body.plan, "user": user["email"]}


@router.post("/reset-usage")
async def reset_usage(user: dict = Depends(get_current_user)) -> dict:
    """Reset monthly PDF counter to 0. Dev only."""
    with get_connection() as conn:
        conn.execute("DELETE FROM usage WHERE user_id = ?", (user["id"],))
    logger.info("[DEV] Reset usage for user %s", user["email"])
    return {"success": True}
