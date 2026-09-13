"""
Early Warning Autopilot - rule-based triggers, no model.

This is an aggregation layer, not a new source of financial logic. The
underlying detectors already exist and are reused rather than reimplemented:

  * category pace vs. a trailing 3-month average -> services/forecast.budget_status()
  * bills landing inside the cash runway          -> services/safe_to_spend.compute()
  * a transaction far above its category norm     -> agents/opportunity_discovery

Warnings are returned newest-risk-first and carry a stable `key` so the UI can
remember what a user dismissed. Tone is deliberately a nudge, not an error: a
banner that shouts gets muted, and a muted channel warns nobody.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from .. import models
from ..services import forecast, safe_to_spend

logger = logging.getLogger("finmate.early_warning")

# A category must be this far over its own trailing average to be worth saying.
PACE_OVER_PCT = 20.0
MIN_PACE_OVERRUN = 400.0     # ignore rupee-trivial overruns
BILL_HORIZON_DAYS = 7
SPIKE_MULTIPLE = 2.5
MIN_SPIKE_AMOUNT = 1_000.0

SEVERITY_ORDER = {"critical": 0, "warn": 1, "info": 2}


def _period() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def check(db: Session, user_id: int) -> list:
    """Return every active warning for this user."""
    warnings = []
    warnings += _pace_warnings(db, user_id)
    warnings += _cash_crunch_warnings(db, user_id)
    warnings += _spike_warnings(db, user_id)

    warnings.sort(key=lambda w: (SEVERITY_ORDER.get(w["severity"], 3), -w.get("amount", 0)))
    return warnings


def _pace_warnings(db: Session, user_id: int) -> list:
    """Month-to-date spend running ahead of this category's own 3-month norm."""
    out = []
    try:
        for cat in forecast.budget_status(db, user_id):
            over_pct = cat["pct_of_average"] - 100.0
            if over_pct < PACE_OVER_PCT or cat["over_by"] < MIN_PACE_OVERRUN:
                continue
            out.append({
                "key": f"pace:{cat['category']}:{_period()}",
                "kind": "category_pace",
                "severity": "warn" if over_pct < 60 else "critical",
                "category": cat["category"],
                "amount": round(cat["over_by"], 2),
                "message": (
                    f"{cat['category']} is running Rs {cat['over_by']:,.0f} ahead of your "
                    f"usual pace with {cat['days_left']} days left. At this rate you'll "
                    f"finish the month at Rs {cat['projected_month_end']:,.0f} "
                    f"versus your Rs {cat['monthly_average']:,.0f} average."
                ),
                "detail": {
                    "spent_mtd": cat["spent_mtd"],
                    "expected_by_now": cat["expected_by_now"],
                    "monthly_average": cat["monthly_average"],
                    "projected_month_end": cat["projected_month_end"],
                    "days_left": cat["days_left"],
                },
            })
    except Exception as e:
        logger.warning("Pace warnings failed for user %s: %s", user_id, e)
    return out


def _cash_crunch_warnings(db: Session, user_id: int) -> list:
    """Bills due this week that exceed what is actually free to spend."""
    out = []
    try:
        sts = safe_to_spend.compute(db, user_id, horizon_days=BILL_HORIZON_DAYS)
        bills = sts["deductions"]["upcoming_bills"]
        due_soon = bills["total"]

        if due_soon > 0 and due_soon > max(sts["safe_to_spend"], 0):
            names = ", ".join(b["label"] for b in bills["items"][:3]) or "upcoming bills"
            out.append({
                "key": f"cash_crunch:{datetime.utcnow().strftime('%Y-W%V')}",
                "kind": "cash_crunch",
                "severity": "critical",
                "category": None,
                "amount": round(due_soon, 2),
                "message": (
                    f"Rs {due_soon:,.0f} of bills fall due in the next {BILL_HORIZON_DAYS} days - "
                    f"more than the Rs {max(sts['safe_to_spend'], 0):,.0f} you have free. "
                    f"Due soon: {names}."
                ),
                "detail": {"bills": bills["items"][:5],
                           "safe_to_spend": sts["safe_to_spend"]},
            })

        if sts["needs_checkpoint"]:
            out.append({
                "key": f"checkpoint:{datetime.utcnow().strftime('%Y-W%V')}",
                "kind": "stale_balance",
                "severity": "info",
                "category": None,
                "amount": 0,
                "message": (
                    "Confirm your current account balance to keep Safe-to-Spend accurate."
                    if sts["balance"]["basis"] == "checkpoint"
                    else "Add your current account balance so Safe-to-Spend reflects reality."
                ),
                "detail": {"basis": sts["balance"]["basis"],
                           "stale_days": sts["balance"]["stale_days"]},
            })
    except Exception as e:
        logger.warning("Cash-crunch warnings failed for user %s: %s", user_id, e)
    return out


def _spike_warnings(db: Session, user_id: int) -> list:
    """
    One transaction far above its category norm.

    Same threshold the Insights page already uses; computed here directly
    against the current month so the banner is about something that just
    happened rather than anything in the history.
    """
    from collections import defaultdict

    out = []
    try:
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        txns = (
            db.query(models.Transaction)
            .filter(models.Transaction.user_id == user_id, models.Transaction.amount < 0)
            .all()
        )
        if len(txns) < 5:
            return out

        by_category = defaultdict(list)
        for t in txns:
            by_category[t.category].append(t)

        for category, items in by_category.items():
            amounts = [abs(t.amount) for t in items]
            if len(amounts) < 3:
                continue
            avg = sum(amounts) / len(amounts)
            recent = [t for t in items if t.date >= month_start]
            for t in recent:
                amt = abs(t.amount)
                if amt > avg * SPIKE_MULTIPLE and amt > MIN_SPIKE_AMOUNT:
                    out.append({
                        "key": f"spike:{t.id}",
                        "kind": "unusual_transaction",
                        "severity": "warn",
                        "category": category,
                        "amount": round(amt, 2),
                        "message": (
                            f"A Rs {amt:,.0f} charge in {category} is more than "
                            f"{SPIKE_MULTIPLE:g}x your usual Rs {avg:,.0f} there."
                            + (f" Merchant: {t.merchant}." if t.merchant else "")
                        ),
                        "detail": {"transaction_id": t.id, "typical": round(avg, 2),
                                   "date": t.date.date().isoformat()},
                    })
                    break  # one spike per category is enough to make the point
    except Exception as e:
        logger.warning("Spike warnings failed for user %s: %s", user_id, e)
    return out
