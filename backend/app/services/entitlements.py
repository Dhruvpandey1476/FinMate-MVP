"""
Plan entitlements and usage metering.

Two problems this solves:

  1. Cost. Every /api/chat call hits a paid LLM with no ceiling. One scripted
     user could drain a month of free tier in an hour. Quotas are enforced per
     user per calendar month, plus a short-window burst limit per IP+user.

  2. Pricing. You cannot price what you cannot measure. Every LLM call writes a
     UsageEvent with tokens and estimated cost, so gross margin per user is a
     query rather than a guess.
"""
import os
import time
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger("finmate.entitlements")


# --- Plans -----------------------------------------------------------------
# Limits are per calendar month. `-1` means unlimited.
PLANS = {
    "free": {
        "label": "Free",
        "price_inr_month": 0,
        "chat_messages": 25,
        "simulations": 10,
        "uploads": 3,
        "ai_insights": True,
        "forecast": True,
        "monte_carlo": False,
        "debt_optimizer": False,
        "proactive_digest": False,
    },
    "plus": {
        "label": "Plus",
        "price_inr_month": 199,
        "chat_messages": 300,
        "simulations": -1,
        "uploads": 25,
        "ai_insights": True,
        "forecast": True,
        "monte_carlo": True,
        "debt_optimizer": True,
        "proactive_digest": True,
    },
    "pro": {
        "label": "Pro",
        "price_inr_month": 499,
        "chat_messages": -1,
        "simulations": -1,
        "uploads": -1,
        "ai_insights": True,
        "forecast": True,
        "monte_carlo": True,
        "debt_optimizer": True,
        "proactive_digest": True,
    },
}

# Metered actions map to a plan key holding their monthly allowance.
METERED = {
    "chat": "chat_messages",
    "simulate": "simulations",
    "upload": "uploads",
}


def plan_for(user) -> dict:
    return PLANS.get(getattr(user, "plan", "free") or "free", PLANS["free"])


def feature_enabled(user, feature: str) -> bool:
    return bool(plan_for(user).get(feature, False))


def _month_start() -> datetime:
    now = datetime.utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_this_month(db: Session, user_id: int, kind: str) -> int:
    return int(
        db.query(func.count(models.UsageEvent.id))
        .filter(
            models.UsageEvent.user_id == user_id,
            models.UsageEvent.kind == kind,
            models.UsageEvent.created_at >= _month_start(),
        )
        .scalar()
        or 0
    )


def check_quota(db: Session, user, kind: str) -> dict:
    """
    Returns {allowed, used, limit, remaining}. Does not consume anything -
    callers record a UsageEvent when the action actually succeeds.
    """
    plan_key = METERED.get(kind)
    if not plan_key:
        return {"allowed": True, "used": 0, "limit": -1, "remaining": -1}

    limit = plan_for(user).get(plan_key, -1)
    if limit < 0:
        return {"allowed": True, "used": 0, "limit": -1, "remaining": -1}

    used = usage_this_month(db, user.id, kind)
    return {
        "allowed": used < limit,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
    }


def quota_summary(db: Session, user) -> dict:
    """Everything the UI needs to render a usage meter."""
    plan = plan_for(user)
    out = {
        "plan": getattr(user, "plan", "free") or "free",
        "label": plan["label"],
        "price_inr_month": plan["price_inr_month"],
        "features": {k: v for k, v in plan.items() if isinstance(v, bool)},
        "quotas": {},
    }
    for kind, plan_key in METERED.items():
        limit = plan.get(plan_key, -1)
        used = usage_this_month(db, user.id, kind) if limit >= 0 else 0
        out["quotas"][kind] = {
            "used": used,
            "limit": limit,
            "remaining": -1 if limit < 0 else max(0, limit - used),
        }
    return out


# --- Cost model ------------------------------------------------------------
# USD per 1M tokens (input, output). Rough public list prices; the point is a
# directionally correct unit-economics number, not billing-grade accounting.
_PRICING = {
    "groq": (0.59, 0.79),
    "gemini": (0.075, 0.30),
    "openai": (0.15, 0.60),
    "rule_based": (0.0, 0.0),
    "none": (0.0, 0.0),
}


def estimate_cost_usd(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = _PRICING.get(provider, (0.0, 0.0))
    return round(
        (prompt_tokens / 1_000_000) * pin + (completion_tokens / 1_000_000) * pout, 8
    )


def record_usage(
    db: Session,
    user_id,
    kind: str,
    provider: str = "",
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    ok: bool = True,
) -> None:
    """Best-effort meter write - never break a user request over telemetry."""
    try:
        db.add(
            models.UsageEvent(
                user_id=user_id,
                kind=kind,
                provider=provider or "",
                model=model or "",
                prompt_tokens=int(prompt_tokens or 0),
                completion_tokens=int(completion_tokens or 0),
                cost_usd=estimate_cost_usd(provider, prompt_tokens or 0, completion_tokens or 0),
                latency_ms=int(latency_ms or 0),
                ok=bool(ok),
            )
        )
        db.commit()
    except Exception as e:  # pragma: no cover - telemetry must never raise
        logger.warning("Failed to record usage: %s", e)
        try:
            db.rollback()
        except Exception:
            pass


def cost_report(db: Session, user_id=None, days: int = 30) -> dict:
    """Aggregate spend. Powers the admin view and the margin question."""
    since_dt = datetime.utcnow() - timedelta(days=days)
    q = db.query(
        models.UsageEvent.provider,
        func.count(models.UsageEvent.id),
        func.coalesce(func.sum(models.UsageEvent.prompt_tokens), 0),
        func.coalesce(func.sum(models.UsageEvent.completion_tokens), 0),
        func.coalesce(func.sum(models.UsageEvent.cost_usd), 0.0),
    ).filter(models.UsageEvent.created_at >= since_dt)
    if user_id is not None:
        q = q.filter(models.UsageEvent.user_id == user_id)
    rows = q.group_by(models.UsageEvent.provider).all()
    return {
        "days": days,
        "by_provider": [
            {
                "provider": r[0] or "unknown",
                "calls": int(r[1]),
                "prompt_tokens": int(r[2]),
                "completion_tokens": int(r[3]),
                "cost_usd": round(float(r[4]), 6),
            }
            for r in rows
        ],
        "total_cost_usd": round(sum(float(r[4]) for r in rows), 6),
    }


# --- Burst limiter ---------------------------------------------------------
# In-process sliding window. Deliberately simple: it stops runaway loops and
# scripted abuse on a single instance. Multi-instance deployments should point
# this at Redis - see REDIS_URL handling below.
_WINDOWS = defaultdict(deque)
_WINDOW_LOCK = Lock()

BURST_LIMITS = {
    "chat": (int(os.getenv("BURST_CHAT_N", "8")), 60),        # 8 per minute
    "simulate": (int(os.getenv("BURST_SIM_N", "20")), 60),
    "upload": (int(os.getenv("BURST_UPLOAD_N", "5")), 300),   # 5 per 5 minutes
    "auth": (int(os.getenv("BURST_AUTH_N", "10")), 300),
    "default": (int(os.getenv("BURST_DEFAULT_N", "60")), 60),
}


def check_burst(key: str, kind: str = "default") -> dict:
    """
    Sliding-window burst check. Returns {allowed, retry_after}.
    `key` should identify the caller (user id, or IP for anonymous routes).
    """
    limit, window = BURST_LIMITS.get(kind, BURST_LIMITS["default"])
    now = time.monotonic()
    bucket_key = f"{kind}:{key}"

    with _WINDOW_LOCK:
        bucket = _WINDOWS[bucket_key]
        cutoff = now - window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(window - (now - bucket[0])) + 1
            return {"allowed": False, "retry_after": max(1, retry_after), "limit": limit}
        bucket.append(now)

        # Opportunistic cleanup so idle keys do not accumulate forever.
        if len(_WINDOWS) > 10_000:
            for k in [k for k, v in list(_WINDOWS.items()) if not v]:
                _WINDOWS.pop(k, None)

    return {"allowed": True, "retry_after": 0, "limit": limit}


def reset_burst_state() -> None:
    """Test helper - clears the sliding windows."""
    with _WINDOW_LOCK:
        _WINDOWS.clear()
