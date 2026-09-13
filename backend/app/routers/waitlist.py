"""Waitlist capture (public) + admin stats (key-protected)."""
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import rate_limit_anon
from ..services import analytics, entitlements

router = APIRouter(tags=["Growth"])

ADMIN_KEY = os.getenv("ADMIN_KEY", "")


def _require_admin(key: str):
    if not ADMIN_KEY or not key or key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key.")


@router.post("/api/waitlist", dependencies=[Depends(rate_limit_anon("auth"))])
def join_waitlist(payload: dict, db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email.")

    existing = db.query(models.Waitlist).filter(models.Waitlist.email == email).first()
    if existing:
        return {"ok": True, "message": "You're already on the list!"}

    db.add(models.Waitlist(email=email, note=(payload.get("note") or None)))
    db.commit()
    analytics.track(db, None, "waitlist_join", {"email_domain": email.split("@")[-1]})
    return {"ok": True, "message": "You're on the list - we'll be in touch."}


@router.get("/api/admin/stats")
def admin_stats(key: str = Query(""), db: Session = Depends(get_db)):
    _require_admin(key)
    signups = db.query(func.count(models.User.id)).scalar() or 0
    waitlist = db.query(func.count(models.Waitlist.id)).scalar() or 0
    active = db.query(func.count(func.distinct(models.ChatMessage.user_id))).scalar() or 0
    with_data = db.query(func.count(func.distinct(models.Transaction.user_id))).scalar() or 0

    by_plan = dict(
        db.query(models.User.plan, func.count(models.User.id))
        .group_by(models.User.plan)
        .all()
    )

    return {
        "signups": int(signups),
        "waitlist": int(waitlist),
        "users_who_chatted": int(active),
        "users_with_data": int(with_data),
        "by_plan": {k or "free": int(v) for k, v in by_plan.items()},
    }


@router.get("/api/admin/funnel")
def admin_funnel(key: str = Query(""), days: int = 30, db: Session = Depends(get_db)):
    """
    Activation funnel: signup -> onboarded -> has data -> first chat -> D7 return.

    This is the number that tells you whether the 30-second onboarding works.
    """
    _require_admin(key)
    return {
        "funnel": analytics.funnel(db, days=days),
        "events": analytics.event_totals(db, days=days),
    }


@router.get("/api/admin/costs")
def admin_costs(key: str = Query(""), days: int = 30, user_id: int = None,
                db: Session = Depends(get_db)):
    """
    LLM spend by provider - gross margin per user, as a query rather than a guess.
    """
    _require_admin(key)
    report = entitlements.cost_report(db, user_id=user_id, days=days)

    active_users = (
        db.query(func.count(func.distinct(models.UsageEvent.user_id)))
        .filter(models.UsageEvent.created_at >= func.datetime("now", f"-{days} days"))
        .scalar()
        if db.bind.dialect.name == "sqlite" else None
    )
    if active_users:
        report["active_users"] = int(active_users)
        report["cost_per_active_user_usd"] = round(
            report["total_cost_usd"] / max(int(active_users), 1), 6
        )
    return report
