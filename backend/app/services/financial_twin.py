"""
Financial Digital Twin - real-time snapshot computation.

Everything here aggregates in SQL. The previous version pulled a user's entire
transaction history into Python on every call (and the dashboard, twin page and
every CFO chat node all call it), which is O(all rows) per request. At a few
years of data that is tens of thousands of rows deserialized per page load.
"""
from datetime import datetime, timedelta
from sqlalchemy import func, case, and_
from sqlalchemy.orm import Session
from .. import models


def _current_month_range():
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(dt: datetime, months: int) -> datetime:
    """Shift by whole months without pulling in dateutil."""
    m = dt.month - 1 + months
    y = dt.year + m // 12
    m = m % 12 + 1
    return dt.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)


def get_snapshot(db: Session, user_id: int) -> dict:
    """Computes the user's real-time Financial Digital Twin state."""
    start, end = _current_month_range()

    # One row: income and expense totals for the current month.
    income_expr = func.coalesce(
        func.sum(case((models.Transaction.amount > 0, models.Transaction.amount), else_=0.0)), 0.0
    )
    expense_expr = func.coalesce(
        func.sum(case((models.Transaction.amount < 0, -models.Transaction.amount), else_=0.0)), 0.0
    )
    total_income_month, total_expense_month = (
        db.query(income_expr, expense_expr)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= start,
        )
        .one()
    )

    total_assets = db.query(
        func.coalesce(func.sum(models.Asset.value), 0.0)
    ).filter(models.Asset.user_id == user_id).scalar() or 0.0

    total_liabilities = db.query(
        func.coalesce(func.sum(models.Liability.amount), 0.0)
    ).filter(models.Liability.user_id == user_id).scalar() or 0.0

    net_worth = total_assets - total_liabilities
    cash_flow = total_income_month - total_expense_month
    savings_rate = (cash_flow / total_income_month * 100) if total_income_month > 0 else 0.0

    # Top expense categories this month - grouped and limited in SQL.
    cat_rows = (
        db.query(
            models.Transaction.category,
            func.sum(-models.Transaction.amount).label("total"),
        )
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= start,
            models.Transaction.amount < 0,
        )
        .group_by(models.Transaction.category)
        .order_by(func.sum(-models.Transaction.amount).desc())
        .limit(5)
        .all()
    )
    top_categories = [
        {"category": c or "Other", "amount": round(float(t or 0), 2)} for c, t in cat_rows
    ]

    health = health_score_breakdown(
        savings_rate=savings_rate,
        net_worth=net_worth,
        total_liabilities=total_liabilities,
        total_income_month=total_income_month,
    )

    return {
        "net_worth": round(net_worth, 2),
        "total_income_month": round(float(total_income_month), 2),
        "total_expense_month": round(float(total_expense_month), 2),
        "savings_rate": round(savings_rate, 2),
        "cash_flow": round(cash_flow, 2),
        "total_assets": round(float(total_assets), 2),
        "total_liabilities": round(float(total_liabilities), 2),
        "financial_health_score": health["score"],
        "health_breakdown": health["components"],
        "top_expense_categories": top_categories,
    }


def health_score_breakdown(savings_rate, net_worth, total_liabilities, total_income_month) -> dict:
    """
    A 0-100 composite score plus the per-factor contributions that produced it.

    The score is the product's hero number, so it ships with its own audit trail:
    each component reports what it contributed and what would move it. Users see
    this on the twin page instead of an unexplained integer.
    """
    components = []
    score = 50.0
    components.append({
        "label": "Baseline",
        "points": 50.0,
        "detail": "Every twin starts at 50.",
    })

    # Savings rate: the dominant factor, capped so one great month cannot mask debt.
    savings_points = max(min(savings_rate, 30.0), -30.0)
    score += savings_points
    components.append({
        "label": "Savings rate",
        "points": round(savings_points, 1),
        "detail": (
            f"Saving {savings_rate:.1f}% of income. "
            f"{'Above the 20% healthy mark.' if savings_rate >= 20 else 'Target 20-30% for full credit.'}"
        ),
    })

    # Debt burden relative to annualised income.
    debt_points = 0.0
    if total_income_month > 0:
        debt_to_income = total_liabilities / (total_income_month * 12 + 1)
        debt_points = -min(debt_to_income * 40, 25)
        detail = (
            f"Liabilities are {debt_to_income * 100:.0f}% of annual income."
            if total_liabilities > 0 else "No liabilities on record."
        )
    else:
        detail = "No income recorded this month - debt burden not scored."
    score += debt_points
    components.append({
        "label": "Debt burden",
        "points": round(debt_points, 1),
        "detail": detail,
    })

    nw_points = 5.0 if net_worth > 0 else 0.0
    score += nw_points
    components.append({
        "label": "Positive net worth",
        "points": nw_points,
        "detail": "Assets exceed liabilities." if net_worth > 0 else "Net worth is not yet positive.",
    })

    return {
        "score": int(max(0, min(100, round(score)))),
        "components": components,
    }


def _financial_health_score(savings_rate, net_worth, total_liabilities, total_income_month) -> int:
    """Backwards-compatible scalar wrapper around health_score_breakdown."""
    return health_score_breakdown(
        savings_rate, net_worth, total_liabilities, total_income_month
    )["score"]


def monthly_cashflow_series(db: Session, user_id: int, months: int = 6) -> list:
    """
    Trailing N-month income/expense series for charting.

    Aggregated in one grouped query rather than N passes over every transaction.
    """
    months = max(1, min(int(months or 6), 60))
    now = datetime.utcnow()
    first_bucket = _add_months(_month_start(now), -(months - 1))

    rows = (
        db.query(
            func.strftime("%Y-%m", models.Transaction.date).label("ym")
            if db.bind.dialect.name == "sqlite"
            else func.to_char(models.Transaction.date, "YYYY-MM").label("ym"),
            func.coalesce(
                func.sum(case((models.Transaction.amount > 0, models.Transaction.amount), else_=0.0)), 0.0
            ).label("income"),
            func.coalesce(
                func.sum(case((models.Transaction.amount < 0, -models.Transaction.amount), else_=0.0)), 0.0
            ).label("expense"),
        )
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= first_bucket,
        )
        .group_by("ym")
        .all()
    )
    by_month = {r[0]: (float(r[1] or 0), float(r[2] or 0)) for r in rows}

    # Emit every bucket, including months with no activity, so the chart has no gaps.
    buckets = []
    for i in range(months):
        bucket = _add_months(first_bucket, i)
        key = f"{bucket.year}-{bucket.month:02d}"
        income, expense = by_month.get(key, (0.0, 0.0))
        buckets.append({
            "month": key,
            "income": round(income, 2),
            "expense": round(expense, 2),
            "savings": round(income - expense, 2),
        })
    return buckets


def transactions_fingerprint(db: Session, user_id: int) -> str:
    """
    Cheap change-detector for caches keyed on transaction state: row count plus
    the newest id and the summed amount. Any insert, delete or edit moves it.
    """
    count, max_id, total = (
        db.query(
            func.count(models.Transaction.id),
            func.coalesce(func.max(models.Transaction.id), 0),
            func.coalesce(func.sum(models.Transaction.amount), 0.0),
        )
        .filter(models.Transaction.user_id == user_id)
        .one()
    )
    return f"{count}:{max_id}:{round(float(total or 0), 2)}"


def monthly_run_rate(db: Session, user_id: int, months: int = 3) -> dict:
    """
    Normalised monthly income and expense from recent *complete* months.

    Projections must not be built from the current month. On the 13th it holds
    13 days of data, so a 12-month forecast drawn from it understates income by
    more than half - and on the 1st it is empty, which projects a flat line.

    Falls back to the current month only when there is no completed history.
    """
    now = datetime.utcnow()
    this_month_start = _month_start(now)
    window_start = _add_months(this_month_start, -months)

    income_expr = func.coalesce(
        func.sum(case((models.Transaction.amount > 0, models.Transaction.amount), else_=0.0)), 0.0
    )
    expense_expr = func.coalesce(
        func.sum(case((models.Transaction.amount < 0, -models.Transaction.amount), else_=0.0)), 0.0
    )

    income, expense = (
        db.query(income_expr, expense_expr)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= window_start,
            models.Transaction.date < this_month_start,
        )
        .one()
    )

    # How many of those months actually contain data, so a user with two months
    # of history is not averaged across three.
    distinct_months = (
        db.query(func.count(func.distinct(
            func.strftime("%Y-%m", models.Transaction.date)
            if db.bind.dialect.name == "sqlite"
            else func.to_char(models.Transaction.date, "YYYY-MM")
        )))
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= window_start,
            models.Transaction.date < this_month_start,
        )
        .scalar()
        or 0
    )

    if distinct_months > 0:
        return {
            "income": round(float(income) / distinct_months, 2),
            "expense": round(float(expense) / distinct_months, 2),
            "basis": f"average of the last {distinct_months} month(s)",
            "months_used": int(distinct_months),
        }

    snapshot = get_snapshot(db, user_id)
    return {
        "income": snapshot["total_income_month"],
        "expense": snapshot["total_expense_month"],
        "basis": "current month so far (no completed months yet)",
        "months_used": 0,
    }
