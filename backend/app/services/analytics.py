"""
Product analytics.

The MVP had no instrumentation at all, which means the onboarding funnel is
unmeasurable: you cannot tell whether the 30-second flow converts, whether
uploads fail, or whether anyone comes back on day 7.

Events are written locally first (so the funnel works with zero third-party
setup) and mirrored to PostHog when POSTHOG_API_KEY is present.
"""
import os
import json
import logging
import threading
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger("finmate.analytics")

POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY", "")
POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://app.posthog.com").rstrip("/")

# The funnel that actually matters for this product.
FUNNEL_STEPS = [
    "signup",
    "onboard_complete",
    "data_present",     # upload OR sample OR manual onboarding
    "first_chat",
    "return_d7",
]


def track(db: Session, user_id, name: str, props: dict = None) -> None:
    """Record an event. Never raises - telemetry must not break a request."""
    props = props or {}
    try:
        db.add(models.AnalyticsEvent(
            user_id=user_id, name=name, props=json.dumps(props, default=str)
        ))
        db.commit()
    except Exception as e:
        logger.warning("Analytics write failed (%s): %s", name, e)
        try:
            db.rollback()
        except Exception:
            pass

    if POSTHOG_API_KEY:
        _forward_async(user_id, name, props)


def _forward_async(user_id, name: str, props: dict) -> None:
    """Fire-and-forget to PostHog so the request never waits on it."""
    def _send():
        try:
            httpx.post(
                f"{POSTHOG_HOST}/capture/",
                json={
                    "api_key": POSTHOG_API_KEY,
                    "event": name,
                    "distinct_id": str(user_id or "anonymous"),
                    "properties": {**props, "$lib": "finmate-backend"},
                    "timestamp": datetime.utcnow().isoformat(),
                },
                timeout=5,
            )
        except Exception as e:
            logger.debug("PostHog forward failed: %s", e)

    threading.Thread(target=_send, daemon=True).start()


def track_once(db: Session, user_id, name: str, props: dict = None) -> bool:
    """
    Record an event only if this user has never fired it.

    Used for milestone events - "first_chat" should mark the first chat, not
    every chat. Returns True if the event was newly recorded.
    """
    try:
        seen = (
            db.query(models.AnalyticsEvent.id)
            .filter(
                models.AnalyticsEvent.user_id == user_id,
                models.AnalyticsEvent.name == name,
            )
            .first()
        )
        if seen:
            return False
    except Exception:
        return False

    track(db, user_id, name, props)
    return True


def funnel(db: Session, days: int = 30) -> dict:
    """Counts per funnel step, plus step-to-step conversion."""
    since = datetime.utcnow() - timedelta(days=days)
    counts = {}
    for step in FUNNEL_STEPS:
        counts[step] = int(
            db.query(func.count(func.distinct(models.AnalyticsEvent.user_id)))
            .filter(
                models.AnalyticsEvent.name == step,
                models.AnalyticsEvent.created_at >= since,
            )
            .scalar()
            or 0
        )

    steps = []
    previous = None
    for step in FUNNEL_STEPS:
        n = counts[step]
        steps.append({
            "step": step,
            "users": n,
            "conversion_from_previous": (
                None if previous in (None, 0) else round(n / previous * 100, 1)
            ),
        })
        previous = n

    return {"days": days, "steps": steps}


def event_totals(db: Session, days: int = 30) -> list:
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(models.AnalyticsEvent.name, func.count(models.AnalyticsEvent.id))
        .filter(models.AnalyticsEvent.created_at >= since)
        .group_by(models.AnalyticsEvent.name)
        .order_by(func.count(models.AnalyticsEvent.id).desc())
        .all()
    )
    return [{"name": r[0], "count": int(r[1])} for r in rows]
