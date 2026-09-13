"""
Proactive digest engine.

Nobody opens a personal finance app. The product only compounds if it reaches
out: "you're Rs 4,200 over your usual food spend with 9 days left", "your
Rs 1,499 renewal hits on Thursday and your balance dips below it".

This module generates those nudges from the twin, stores them (so nothing is
sent twice), and hands them to a channel. In-app is wired now; WhatsApp/push
plug into `deliver()` without touching the generation logic.

Runs from POST /api/digest/run (cron-friendly) or per-user on demand.
"""
import logging
import os
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from .. import models
from . import forecast, financial_twin, entitlements

logger = logging.getLogger("finmate.digest")

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")

# Thresholds tuned to be worth a notification - a nudge that fires every day
# gets muted, and a muted channel is a dead channel.
LOW_RUNWAY_DAYS = 21
BUDGET_OVERRUN_PCT = 125
MIN_OVERRUN_AMOUNT = 500
BIG_BILL_THRESHOLD = 2000


def _period_key(granularity: str = "week") -> str:
    now = datetime.utcnow()
    if granularity == "day":
        return now.strftime("%Y-%m-%d")
    if granularity == "month":
        return now.strftime("%Y-%m")
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _already_sent(db: Session, user_id: int, dedupe_key: str) -> bool:
    return (
        db.query(models.Notification.id)
        .filter(
            models.Notification.user_id == user_id,
            models.Notification.dedupe_key == dedupe_key,
        )
        .first()
        is not None
    )


def generate_for_user(db: Session, user: models.User, persist: bool = True) -> list:
    """
    Build this user's nudges. Returns the ones that are new.

    Each nudge carries a dedupe_key scoped to a period, so "you're over budget
    on Food" fires once a week, not on every run.
    """
    candidates = []

    # --- 1. Runway warning -------------------------------------------------
    try:
        fc = forecast.forecast(db, user.id, days=90)
        runway = fc.get("runway_days")
        if runway is not None and runway <= LOW_RUNWAY_DAYS:
            candidates.append({
                "kind": "low_balance",
                "severity": "critical" if runway <= 7 else "warn",
                "title": f"Cash runs low in {runway} days",
                "body": (
                    f"Your projected balance goes negative around "
                    f"{fc['low_balance_date']}. Committed bills are "
                    f"Rs {fc['monthly_committed']:,.0f}/month against "
                    f"Rs {fc['monthly_recurring_income']:,.0f} of recurring income."
                ),
                "dedupe_key": f"low_balance:{user.id}:{_period_key('week')}",
            })

        # --- 2. Large bill landing soon ------------------------------------
        soon = datetime.utcnow().date() + timedelta(days=5)
        for bill in fc.get("upcoming_bills", [])[:5]:
            if abs(bill["amount"]) >= BIG_BILL_THRESHOLD and \
                    datetime.fromisoformat(bill["date"]).date() <= soon:
                candidates.append({
                    "kind": "subscription",
                    "severity": "info",
                    "title": f"Rs {abs(bill['amount']):,.0f} due on {bill['date']}",
                    "body": f"'{bill['label']}' is scheduled to hit your account on {bill['date']}.",
                    "dedupe_key": f"bill:{user.id}:{bill['label']}:{bill['date']}",
                })
    except Exception as e:
        logger.warning("Forecast nudges failed for user %s: %s", user.id, e)

    # --- 3. Budget overrun -------------------------------------------------
    try:
        for cat in forecast.budget_status(db, user.id)[:3]:
            if cat["pct_of_average"] >= BUDGET_OVERRUN_PCT and cat["over_by"] >= MIN_OVERRUN_AMOUNT:
                candidates.append({
                    "kind": "budget_overrun",
                    "severity": "warn",
                    "title": f"{cat['category']} is running hot",
                    "body": (
                        f"You've spent Rs {cat['spent_mtd']:,.0f} on {cat['category']} "
                        f"this month - Rs {cat['over_by']:,.0f} more than usual by this point, "
                        f"with {cat['days_left']} days left. On this pace you'll finish at "
                        f"Rs {cat['projected_month_end']:,.0f} versus your Rs {cat['monthly_average']:,.0f} average."
                    ),
                    "dedupe_key": f"budget:{user.id}:{cat['category']}:{_period_key('week')}",
                })
    except Exception as e:
        logger.warning("Budget nudges failed for user %s: %s", user.id, e)

    # --- 4. Goal at risk ---------------------------------------------------
    try:
        snapshot = financial_twin.get_snapshot(db, user.id)
        goals = (
            db.query(models.Goal)
            .filter(models.Goal.user_id == user.id)
            .order_by(models.Goal.priority)
            .all()
        )
        for g in goals[:2]:
            if g.monthly_contribution > 0 and snapshot["cash_flow"] < g.monthly_contribution:
                shortfall = g.monthly_contribution - snapshot["cash_flow"]
                candidates.append({
                    "kind": "goal_risk",
                    "severity": "warn",
                    "title": f"'{g.name}' contribution is at risk",
                    "body": (
                        f"This month's cash flow is Rs {snapshot['cash_flow']:,.0f}, "
                        f"Rs {shortfall:,.0f} short of the Rs {g.monthly_contribution:,.0f} "
                        f"you planned to put toward '{g.name}'."
                    ),
                    "dedupe_key": f"goal_risk:{user.id}:{g.id}:{_period_key('month')}",
                })

        # --- 5. A win worth celebrating ------------------------------------
        if snapshot["savings_rate"] >= 25 and snapshot["total_income_month"] > 0:
            candidates.append({
                "kind": "win",
                "severity": "info",
                "title": f"{snapshot['savings_rate']:.0f}% savings rate this month",
                "body": (
                    f"You're saving Rs {snapshot['cash_flow']:,.0f} of "
                    f"Rs {snapshot['total_income_month']:,.0f} income - above the 20% "
                    f"healthy mark. Health score: {snapshot['financial_health_score']}/100."
                ),
                "dedupe_key": f"win:{user.id}:{_period_key('month')}",
            })
    except Exception as e:
        logger.warning("Goal nudges failed for user %s: %s", user.id, e)

    # --- Persist, skipping anything already sent ---------------------------
    fresh = []
    for c in candidates:
        if _already_sent(db, user.id, c["dedupe_key"]):
            continue
        note = models.Notification(
            user_id=user.id, kind=c["kind"], title=c["title"], body=c["body"],
            severity=c["severity"], dedupe_key=c["dedupe_key"],
        )
        if persist:
            db.add(note)
        fresh.append(note)

    if persist and fresh:
        db.commit()

    return fresh


def run_for_all(db: Session, limit: int = 500) -> dict:
    """
    Cron entry point. Only users whose plan includes proactive nudges are
    processed - the digest is a paid retention feature.
    """
    users = db.query(models.User).limit(limit).all()
    total, processed = 0, 0

    for user in users:
        if not entitlements.feature_enabled(user, "proactive_digest"):
            continue
        try:
            fresh = generate_for_user(db, user)
            processed += 1
            total += len(fresh)
            for note in fresh:
                deliver(user, note)
        except Exception as e:
            logger.error("Digest failed for user %s: %s", user.id, e)

    return {"users_processed": processed, "notifications_created": total}


def deliver(user: models.User, note: models.Notification) -> bool:
    """
    Send a nudge on the user's best channel.

    In-app is implicit (the row exists). WhatsApp is the channel that matters
    for the Indian market and activates as soon as credentials are configured.
    """
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID):
        return False

    phone = getattr(user, "phone", None)
    if not phone:
        return False

    try:
        resp = httpx.post(
            f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "text",
                "text": {"body": f"*{note.title}*\n\n{note.body}"},
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("WhatsApp delivery failed for user %s: %s", user.id, e)
        return False


def list_for_user(db: Session, user_id: int, limit: int = 50, unread_only: bool = False) -> list:
    q = db.query(models.Notification).filter(models.Notification.user_id == user_id)
    if unread_only:
        q = q.filter(models.Notification.read.is_(False))
    return q.order_by(models.Notification.created_at.desc()).limit(max(1, min(limit, 200))).all()


def mark_read(db: Session, user_id: int, notification_id=None) -> int:
    q = db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.read.is_(False),
    )
    if notification_id:
        q = q.filter(models.Notification.id == notification_id)
    updated = q.update({models.Notification.read: True}, synchronize_session=False)
    db.commit()
    return updated
