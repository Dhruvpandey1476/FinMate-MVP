"""
Safe-to-Spend - deterministic arithmetic, no model of any kind.

    safe_to_spend = running_balance
                  - upcoming known bills (next N days)
                  - remaining goal contributions this month
                  - safety buffer

Every term is returned alongside the number so the UI can show *why*, not just
the figure. A number a user cannot interrogate is a number they will not trust
with a spending decision.

Two things this deliberately does NOT do:

  * It does not pretend to know a live bank balance. There is no Account
    Aggregator feed, so the balance is the user's last confirmed checkpoint
    plus everything logged since, and the API says exactly that via
    `balance_as_of`.

  * It does not use the per-row `is_recurring` flag to find bills. That flag is
    set by an LLM looking at a single transaction with no view of the series.
    services/forecast.detect_recurring() infers cadence from history instead
    (median gap, amount stability, a confidence score), which is both more
    accurate and defensible.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from . import forecast

logger = logging.getLogger("finmate.safe_to_spend")

# How far ahead a bill counts against today's spending power.
DEFAULT_HORIZON_DAYS = 14

# The buffer is expressed in days of the user's own discretionary burn rather
# than a flat rupee amount, so it scales with how they actually live. A magic
# constant here would be the one number in the breakdown nobody could justify.
BUFFER_DAYS = 3
MIN_BUFFER = 500.0
MAX_BUFFER = 10_000.0

# A recurring charge below this confidence is not counted as a committed bill.
BILL_CONFIDENCE_FLOOR = 0.4


def latest_checkpoint(db: Session, user_id: int):
    return (
        db.query(models.BalanceCheckpoint)
        .filter(models.BalanceCheckpoint.user_id == user_id)
        .order_by(models.BalanceCheckpoint.as_of.desc())
        .first()
    )


def running_balance(db: Session, user_id: int) -> dict:
    """
    Last confirmed balance plus the net of everything logged since.

    Falls back to accumulated net flow when the user has never confirmed a
    balance, and reports which basis was used so the UI can be honest about it.
    """
    checkpoint = latest_checkpoint(db, user_id)

    if checkpoint:
        net_since = (
            db.query(func.coalesce(func.sum(models.Transaction.amount), 0.0))
            .filter(
                models.Transaction.user_id == user_id,
                models.Transaction.date > checkpoint.as_of,
            )
            .scalar()
            or 0.0
        )
        return {
            "balance": round(float(checkpoint.balance) + float(net_since), 2),
            "basis": "checkpoint",
            "as_of": checkpoint.as_of,
            "confirmed_balance": round(float(checkpoint.balance), 2),
            "net_since_checkpoint": round(float(net_since), 2),
            "stale_days": (datetime.utcnow() - checkpoint.as_of).days,
        }

    total = (
        db.query(func.coalesce(func.sum(models.Transaction.amount), 0.0))
        .filter(models.Transaction.user_id == user_id)
        .scalar()
        or 0.0
    )
    return {
        "balance": round(max(float(total), 0.0), 2),
        "basis": "ledger",
        "as_of": None,
        "confirmed_balance": None,
        "net_since_checkpoint": None,
        "stale_days": None,
    }


def _upcoming_bills(db: Session, user_id: int, horizon_days: int) -> list:
    """Committed bills falling due inside the horizon, from detected cadence."""
    cutoff = (datetime.utcnow() + timedelta(days=horizon_days)).date()
    today = datetime.utcnow().date()

    bills = []
    for item in forecast.detect_recurring(db, user_id):
        if item["confidence"] < BILL_CONFIDENCE_FLOOR:
            continue
        due = datetime.fromisoformat(item["next_due"]).date()
        # A cadence shorter than the horizon can fall due more than once.
        while due <= cutoff:
            if due >= today:
                bills.append({
                    "label": item["label"],
                    "category": item["category"],
                    "amount": round(item["amount"], 2),
                    "due_date": due.isoformat(),
                    "confidence": item["confidence"],
                })
            due += timedelta(days=item["period_days"])

    bills.sort(key=lambda b: b["due_date"])
    return bills


def _remaining_goal_contributions(db: Session, user_id: int, recurring_labels: set) -> dict:
    """
    Goal money not yet set aside this month.

    Contributions already paid as a detected recurring transfer are excluded -
    otherwise the same rupee is subtracted twice, once as a bill and once as a
    goal, and Safe-to-Spend reads far lower than the truth.

    The match is against *every* detected recurring charge, not only the ones
    falling inside the horizon. A monthly SIP due on the 28th is just as
    committed on the 1st as on the 25th, and making the dedup depend on the
    window would make the same goal double-count or not depending on the date.
    """
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    goals = (
        db.query(models.Goal)
        .filter(models.Goal.user_id == user_id, models.Goal.monthly_contribution > 0)
        .all()
    )

    items, total = [], 0.0
    for goal in goals:
        # A recurring bill whose label matches the goal is that contribution.
        if goal.name.strip().lower() in recurring_labels:
            items.append({
                "goal": goal.name,
                "amount": 0.0,
                "note": "already counted as a recurring transfer",
            })
            continue

        paid = (
            db.query(func.coalesce(func.sum(-models.Transaction.amount), 0.0))
            .filter(
                models.Transaction.user_id == user_id,
                models.Transaction.date >= month_start,
                models.Transaction.amount < 0,
                models.Transaction.category == goal.name,
            )
            .scalar()
            or 0.0
        )
        remaining = max(float(goal.monthly_contribution) - float(paid), 0.0)
        total += remaining
        items.append({
            "goal": goal.name,
            "amount": round(remaining, 2),
            "monthly_target": round(float(goal.monthly_contribution), 2),
            "already_set_aside": round(float(paid), 2),
        })

    return {"total": round(total, 2), "items": items}


def compute(db: Session, user_id: int, horizon_days: int = DEFAULT_HORIZON_DAYS) -> dict:
    """Safe-to-Spend plus the full breakdown behind it."""
    horizon_days = max(1, min(int(horizon_days or DEFAULT_HORIZON_DAYS), 60))

    balance_info = running_balance(db, user_id)
    balance = balance_info["balance"]

    bills = _upcoming_bills(db, user_id, horizon_days)
    bills_total = round(sum(b["amount"] for b in bills), 2)

    # Every detected recurring charge, regardless of horizon - see the note in
    # _remaining_goal_contributions for why the window must not affect dedup.
    recurring_labels = {
        r["label"].strip().lower()
        for r in forecast.detect_recurring(db, user_id)
        if r["confidence"] >= BILL_CONFIDENCE_FLOOR
    }
    goals = _remaining_goal_contributions(db, user_id, recurring_labels)

    # Buffer scales with the user's own discretionary spending.
    daily_burn = _daily_discretionary_burn(db, user_id)
    buffer = round(min(max(daily_burn * BUFFER_DAYS, MIN_BUFFER), MAX_BUFFER), 2)

    amount = round(balance - bills_total - goals["total"] - buffer, 2)

    return {
        "safe_to_spend": amount,
        "is_negative": amount < 0,
        "horizon_days": horizon_days,
        "balance": {
            "amount": balance,
            "basis": balance_info["basis"],
            "as_of": balance_info["as_of"],
            "stale_days": balance_info["stale_days"],
            "confirmed_balance": balance_info["confirmed_balance"],
            "net_since_checkpoint": balance_info["net_since_checkpoint"],
            # The UI shows this instead of implying a live bank figure.
            "label": (
                "as of your last update" if balance_info["basis"] == "checkpoint"
                else "estimated from your logged transactions"
            ),
        },
        "deductions": {
            "upcoming_bills": {"total": bills_total, "items": bills},
            "goal_contributions": goals,
            "safety_buffer": {
                "total": buffer,
                "basis": f"{BUFFER_DAYS} days of your typical discretionary spend "
                         f"(about Rs {daily_burn:,.0f}/day)",
            },
        },
        "needs_checkpoint": _needs_checkpoint(balance_info),
        "summary": _summarize(amount, bills_total, goals["total"], balance_info),
    }


def _daily_discretionary_burn(db: Session, user_id: int) -> float:
    """Recent non-recurring spend per day, reusing the forecast engine's view."""
    try:
        return float(forecast.forecast(db, user_id, days=30).get("daily_discretionary_burn", 0.0))
    except Exception as e:
        logger.warning("Falling back to flat buffer for user %s: %s", user_id, e)
        return 0.0


def _needs_checkpoint(balance_info: dict) -> bool:
    """Nudge a weekly confirmation; never block on it."""
    if balance_info["basis"] != "checkpoint":
        return True
    return (balance_info["stale_days"] or 0) >= 7


def _summarize(amount, bills_total, goals_total, balance_info) -> str:
    if amount < 0:
        return (
            f"Your committed spending over the next two weeks exceeds what's in the account "
            f"by Rs {abs(amount):,.0f}. Bills account for Rs {bills_total:,.0f} of that."
        )
    if balance_info["basis"] != "checkpoint":
        return (
            f"About Rs {amount:,.0f} is free to spend, estimated from your logged "
            f"transactions. Confirm your actual balance to make this exact."
        )
    return (
        f"Rs {amount:,.0f} is free to spend after Rs {bills_total:,.0f} of upcoming bills "
        f"and Rs {goals_total:,.0f} still to set aside for your goals."
    )


def add_checkpoint(db: Session, user_id: int, balance: float,
                   as_of=None, note=None, source: str = "user"):
    checkpoint = models.BalanceCheckpoint(
        user_id=user_id,
        balance=float(balance),
        as_of=as_of or datetime.utcnow(),
        note=note,
        source=source,
    )
    db.add(checkpoint)
    db.commit()
    db.refresh(checkpoint)
    return checkpoint
