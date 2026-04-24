import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from services.db import get_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

RC_WEBHOOK_SECRET = os.getenv("REVENUECAT_WEBHOOK_SECRET", "")

# Map RevenueCat product IDs → internal plan names
PRODUCT_TO_PLAN = {
    "yt_doc_basic_yearly":     "basic",
    "yt_doc_unlimited_yearly": "unlimited",
}


@router.post("/revenuecat")
async def revenuecat_webhook(request: Request) -> dict:
    # Verify shared secret
    if RC_WEBHOOK_SECRET:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {RC_WEBHOOK_SECRET}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    event = body.get("event", {})
    event_type = event.get("type", "")
    app_user_id = event.get("app_user_id", "")
    product_id = event.get("product_id", "")
    expiration_ms = event.get("expiration_at_ms")

    logger.info("RevenueCat %s user=%s product=%s", event_type, app_user_id, product_id)

    plan = PRODUCT_TO_PLAN.get(product_id)
    if not plan:
        return {"status": "ignored", "reason": "unknown product"}

    with get_connection() as conn:
        user = conn.execute(
            "SELECT id FROM users WHERE id = ?", (app_user_id,)
        ).fetchone()
        if not user:
            return {"status": "ignored", "reason": "unknown user"}

        now = datetime.now(timezone.utc).isoformat()
        original_tx = event.get("original_transaction_id", app_user_id)
        exp_iso = (
            datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc).isoformat()
            if expiration_ms else None
        )

        if event_type in ("INITIAL_PURCHASE", "RENEWAL", "PRODUCT_CHANGE", "UNCANCELLATION"):
            conn.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, app_user_id))
            conn.execute("""
                INSERT INTO subscriptions
                    (id, user_id, plan, rc_original_tx_id, rc_product_id, started_at, expires_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    plan = excluded.plan,
                    expires_at = excluded.expires_at,
                    is_active = 1
            """, (original_tx, app_user_id, plan, original_tx, product_id, now, exp_iso))

        elif event_type in ("CANCELLATION", "EXPIRATION"):
            conn.execute("UPDATE users SET plan = 'free' WHERE id = ?", (app_user_id,))
            conn.execute(
                "UPDATE subscriptions SET is_active = 0 WHERE user_id = ?",
                (app_user_id,),
            )

    return {"status": "ok", "event": event_type}
