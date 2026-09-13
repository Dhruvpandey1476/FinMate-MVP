"""
Cash-flow forecasting.

The twin already flagged `is_recurring` on transactions but never projected
forward from it. Answering "when do I run out of money?" is the highest
perceived-value question in personal finance, and it is pure arithmetic on data
already stored.

Two layers:
  * detect_recurring()  - find repeating charges from transaction history,
                          independent of the is_recurring flag the parser set
  * forecast()          - day-by-day balance projection with the low-balance
                          date, upcoming bills and per-category burn
"""
import logging
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models
from . import financial_twin

logger = logging.getLogger("finmate.forecast")

# A charge repeating on a stable cadence with a stable amount is a commitment.
_CADENCES = [
    ("weekly", 7, 2),
    ("fortnightly", 14, 3),
    ("monthly", 30, 5),
    ("quarterly", 91, 9),
    ("yearly", 365, 20),
]


def _classify_cadence(gaps):
    """Match the median gap between charges to a known billing cadence."""
    if not gaps:
        return None, None
    median_gap = statistics.median(gaps)
    for name, days, tolerance in _CADENCES:
        if abs(median_gap - days) <= tolerance:
            return name, days
    return None, None


def detect_recurring(db: Session, user_id: int, lookback_days: int = 400) -> list:
    """
    Find recurring charges by grouping on normalised merchant and looking for a
    consistent cadence and amount.

    Derived from history rather than trusting the parser's is_recurring flag,
    which is set by an LLM on a single row with no view of the series.
    """
    from .dedupe import normalize_description

    since = datetime.utcnow() - timedelta(days=lookback_days)
    txns = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= since,
            models.Transaction.amount < 0,
        )
        .order_by(models.Transaction.date)
        .all()
    )

    groups = defaultdict(list)
    for t in txns:
        key = normalize_description(t.merchant or t.category)
        if key:
            groups[key].append(t)

    recurring = []
    for key, items in groups.items():
        if len(items) < 3:
            continue

        dates = [t.date for t in items]
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        gaps = [g for g in gaps if g > 0]
        if not gaps:
            continue

        cadence, period_days = _classify_cadence(gaps)
        if not cadence:
            continue

        amounts = [abs(t.amount) for t in items]
        mean_amount = statistics.fmean(amounts)
        if mean_amount <= 0:
            continue

        # Reject noisy groups: a real subscription has a near-constant amount.
        spread = (statistics.pstdev(amounts) / mean_amount) if len(amounts) > 1 else 0
        if spread > 0.25:
            continue

        last_seen = dates[-1]
        next_due = last_seen + timedelta(days=period_days)
        # If the next date is already in the past, roll forward to the next one.
        while next_due < datetime.utcnow():
            next_due += timedelta(days=period_days)

        recurring.append({
            "label": items[-1].merchant or items[-1].category or key,
            "category": items[-1].category,
            "cadence": cadence,
            "period_days": period_days,
            "amount": round(mean_amount, 2),
            "occurrences": len(items),
            "last_seen": last_seen.date().isoformat(),
            "next_due": next_due.date().isoformat(),
            "monthly_equivalent": round(mean_amount * 30.0 / period_days, 2),
            "confidence": round(min(1.0, len(items) / 6) * (1 - spread), 2),
        })

    recurring.sort(key=lambda r: -r["monthly_equivalent"])
    return recurring


def detect_recurring_income(db: Session, user_id: int, lookback_days: int = 400) -> list:
    """Same cadence detection for inflows - usually salary."""
    from .dedupe import normalize_description

    since = datetime.utcnow() - timedelta(days=lookback_days)
    txns = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= since,
            models.Transaction.amount > 0,
        )
        .order_by(models.Transaction.date)
        .all()
    )

    groups = defaultdict(list)
    for t in txns:
        groups[normalize_description(t.merchant or t.category)].append(t)

    out = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        dates = [t.date for t in items]
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        gaps = [g for g in gaps if g > 0]
        cadence, period_days = _classify_cadence(gaps)
        if not cadence:
            continue
        amounts = [t.amount for t in items]
        mean_amount = statistics.fmean(amounts)
        next_due = dates[-1] + timedelta(days=period_days)
        while next_due < datetime.utcnow():
            next_due += timedelta(days=period_days)
        out.append({
            "label": items[-1].merchant or items[-1].category or key,
            "cadence": cadence,
            "period_days": period_days,
            "amount": round(mean_amount, 2),
            "next_due": next_due.date().isoformat(),
        })
    return out


def _liquid_balance(db: Session, user_id: int) -> float:
    """
    Spendable cash. Only cash-type assets count - a property valuation does not
    pay a bill, and treating it as a buffer would make the runway meaningless.
    """
    assets = db.query(models.Asset).filter(models.Asset.user_id == user_id).all()
    liquid = sum(a.value for a in assets if (a.asset_type or "").lower() in ("cash", "savings", "bank"))
    if liquid > 0:
        return float(liquid)
    # No cash asset recorded: fall back to accumulated net flow, floored at zero.
    total = sum(t.amount for t in
                db.query(models.Transaction).filter(models.Transaction.user_id == user_id).all())
    return float(max(total, 0.0))


def forecast(db: Session, user_id: int, days: int = 90) -> dict:
    """
    Day-by-day cash projection.

    Combines detected recurring commitments (dated precisely) with a smoothed
    daily rate for everything else, so a bill landing on the 3rd shows up on the
    3rd rather than being averaged away.
    """
    days = max(7, min(int(days or 90), 365))
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    recurring_out = detect_recurring(db, user_id)
    recurring_in = detect_recurring_income(db, user_id)

    # Discretionary burn = recent non-recurring spending, averaged per day.
    since = today - timedelta(days=90)
    recent = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= since,
            models.Transaction.amount < 0,
        )
        .all()
    )
    recurring_labels = {r["label"] for r in recurring_out}
    discretionary_total = sum(
        abs(t.amount) for t in recent
        if (t.merchant or t.category) not in recurring_labels
    )
    daily_discretionary = discretionary_total / 90.0 if recent else 0.0

    balance = _liquid_balance(db, user_id)
    opening_balance = balance

    # Pre-compute the dated events across the horizon.
    events_by_day = defaultdict(list)
    for item in recurring_out:
        due = datetime.fromisoformat(item["next_due"])
        while due <= today + timedelta(days=days):
            events_by_day[due.date()].append({
                "label": item["label"], "amount": -item["amount"], "kind": "bill",
            })
            due += timedelta(days=item["period_days"])

    for item in recurring_in:
        due = datetime.fromisoformat(item["next_due"])
        while due <= today + timedelta(days=days):
            events_by_day[due.date()].append({
                "label": item["label"], "amount": item["amount"], "kind": "income",
            })
            due += timedelta(days=item["period_days"])

    series = []
    low_balance_date = None
    lowest = balance
    lowest_date = today.date().isoformat()

    for i in range(days + 1):
        day = (today + timedelta(days=i)).date()
        day_events = events_by_day.get(day, [])
        day_delta = sum(e["amount"] for e in day_events) - daily_discretionary
        balance += day_delta

        if balance < lowest:
            lowest = balance
            lowest_date = day.isoformat()
        if low_balance_date is None and balance < 0:
            low_balance_date = day.isoformat()

        series.append({
            "date": day.isoformat(),
            "balance": round(balance, 2),
            "events": day_events,
        })

    upcoming = sorted(
        [
            {**e, "date": d.isoformat()}
            for d, evts in events_by_day.items() for e in evts
            if e["kind"] == "bill" and d <= (today + timedelta(days=30)).date()
        ],
        key=lambda e: e["date"],
    )

    monthly_committed = sum(r["monthly_equivalent"] for r in recurring_out)
    monthly_income = sum(r["amount"] * 30.0 / r["period_days"] for r in recurring_in)

    return {
        "opening_balance": round(opening_balance, 2),
        "horizon_days": days,
        "daily_discretionary_burn": round(daily_discretionary, 2),
        "monthly_committed": round(monthly_committed, 2),
        "monthly_recurring_income": round(monthly_income, 2),
        "projected_monthly_surplus": round(monthly_income - monthly_committed - daily_discretionary * 30, 2),
        "low_balance_date": low_balance_date,
        "lowest_balance": round(lowest, 2),
        "lowest_balance_date": lowest_date,
        "runway_days": (
            (datetime.fromisoformat(low_balance_date).date() - today.date()).days
            if low_balance_date else None
        ),
        "series": series,
        "recurring_expenses": recurring_out,
        "recurring_income": recurring_in,
        "upcoming_bills": upcoming,
        "summary": _summarize(low_balance_date, lowest, monthly_income, monthly_committed, today),
    }


def _summarize(low_balance_date, lowest, monthly_income, monthly_committed, today) -> str:
    if low_balance_date:
        days_out = (datetime.fromisoformat(low_balance_date).date() - today.date()).days
        return (
            f"At your current pace you run out of cash in {days_out} days "
            f"(around {low_balance_date}). Committed bills alone are "
            f"Rs {monthly_committed:,.0f}/month."
        )
    if monthly_income > 0 and monthly_committed / monthly_income > 0.7:
        return (
            f"You stay positive, but Rs {monthly_committed:,.0f}/month of committed bills "
            f"eats {monthly_committed / monthly_income * 100:.0f}% of recurring income - "
            f"little room for a surprise."
        )
    return (
        f"Cash flow looks stable. Lowest projected balance is Rs {lowest:,.0f} "
        f"over the forecast window."
    )


def budget_status(db: Session, user_id: int) -> list:
    """
    Month-to-date spend per category against the trailing 3-month average,
    pro-rated for how far through the month we are. This is what makes a nudge
    like "you're 40% over your usual food spend with 9 days left" possible.
    """
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_elapsed = max(1, (now - month_start).days + 1)
    days_in_month = (financial_twin._add_months(month_start, 1) - month_start).days
    progress = days_elapsed / days_in_month

    baseline_start = financial_twin._add_months(month_start, -3)
    baseline = defaultdict(float)
    for t in (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= baseline_start,
            models.Transaction.date < month_start,
            models.Transaction.amount < 0,
        )
        .all()
    ):
        baseline[t.category] += -t.amount

    current = defaultdict(float)
    for t in (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= month_start,
            models.Transaction.amount < 0,
        )
        .all()
    ):
        current[t.category] += -t.amount

    out = []
    for category, spent in current.items():
        monthly_avg = baseline.get(category, 0.0) / 3.0
        if monthly_avg <= 0:
            continue
        expected_by_now = monthly_avg * progress
        out.append({
            "category": category,
            "spent_mtd": round(spent, 2),
            "expected_by_now": round(expected_by_now, 2),
            "monthly_average": round(monthly_avg, 2),
            "projected_month_end": round(spent / progress, 2) if progress > 0 else spent,
            "over_by": round(spent - expected_by_now, 2),
            "pct_of_average": round(spent / monthly_avg * 100, 1) if monthly_avg else 0,
            "days_left": days_in_month - days_elapsed,
        })

    out.sort(key=lambda c: -c["over_by"])
    return out
