"""
Paid outcomes - seven generated reports.

The business model these support is "free to understand your money, pay when
FinMate produces something valuable", so every generator below produces real
output from the user's actual data. Nothing here is a mock: the unlock flow is
mocked, the reports are not.

Each returns a structured dict the frontend renders and prints. There is no
server-side PDF renderer on purpose - the browser's own print-to-PDF produces
the same result from the styled view, with no extra dependency and no system
libraries in the image.

Naming is deliberate and legally load-bearing: "Net Worth Statement" not
certificate, "Loan Readiness Report" not assessment, and the tax export flags
items for review rather than claiming to calculate anything.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models
from . import financial_twin, forecast, debt as debt_service, tax_kb

logger = logging.getLogger("finmate.reports")

# Price in paise-free rupees. Mocked at checkout; see routers/reports.py.
CATALOGUE = [
    {"id": "money_wrapped", "title": "Money Wrapped",
     "blurb": "Your year in money - where it went, your best month, and your spending personality.",
     "price_inr": 49, "emoji": "🎁"},
    {"id": "financial_health", "title": "Detailed Financial Health Report",
     "blurb": "Full category breakdown, month-by-month trends and how your health score moved.",
     "price_inr": 99, "emoji": "📊"},
    {"id": "tax_ready", "title": "Tax-Ready Export",
     "blurb": "Your transactions organised by category, with items flagged for review at filing time.",
     "price_inr": 149, "emoji": "🧾"},
    {"id": "wedding_plan", "title": "Wedding Financial Plan",
     "blurb": "Contributor-by-contributor plan, milestone timeline and three ways to close the gap.",
     "price_inr": 199, "emoji": "💍"},
    {"id": "loan_readiness", "title": "Loan Readiness Report",
     "blurb": "Income stability, existing obligations and where you stand before you apply.",
     "price_inr": 149, "emoji": "🏦"},
    {"id": "net_worth", "title": "Net Worth Statement",
     "blurb": "A clean statement of what you own and owe, ready to share.",
     "price_inr": 49, "emoji": "📄"},
    {"id": "debt_payoff", "title": "Debt Payoff Plan",
     "blurb": "Avalanche versus snowball, with the interest each strategy costs you.",
     "price_inr": 99, "emoji": "✂️"},
]

CATALOGUE_BY_ID = {r["id"]: r for r in CATALOGUE}

SELF_REPORTED = (
    "Prepared by FinMate from information you provided. Figures are self-reported "
    "and have not been verified by any bank, employer or authority."
)


def _months_back(db: Session, user_id: int, months: int):
    since = financial_twin._add_months(
        financial_twin._month_start(datetime.utcnow()), -(months - 1)
    )
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == user_id, models.Transaction.date >= since)
        .all()
    ), since


def _by_category(txns, expenses_only=True):
    totals = defaultdict(float)
    for t in txns:
        if expenses_only and t.amount >= 0:
            continue
        totals[t.category or "Other"] += abs(t.amount)
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def _monthly(txns):
    buckets = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for t in txns:
        key = f"{t.date.year}-{t.date.month:02d}"
        if t.amount > 0:
            buckets[key]["income"] += t.amount
        else:
            buckets[key]["expense"] += -t.amount
    return [
        {"month": m, **v, "savings": round(v["income"] - v["expense"], 2)}
        for m, v in sorted(buckets.items())
    ]



def _merchant_leaderboard(txns, limit=10):
    """Who actually took the money, and how often."""
    agg = defaultdict(lambda: {"total": 0.0, "count": 0})
    for t in txns:
        if t.amount >= 0:
            continue
        key = (t.merchant or t.category or "Unknown").strip()
        agg[key]["total"] += abs(t.amount)
        agg[key]["count"] += 1
    rows = [
        {"merchant": k, "total": round(v["total"], 2), "count": v["count"],
         "average": round(v["total"] / v["count"], 2)}
        for k, v in agg.items()
    ]
    rows.sort(key=lambda r: -r["total"])
    return rows[:limit]


def _weekday_split(txns):
    """Weekday versus weekend spending - a habit most people cannot self-report."""
    weekday = weekend = 0.0
    wd_days: set = set()
    we_days: set = set()
    for t in txns:
        if t.amount >= 0:
            continue
        if t.date.weekday() >= 5:
            weekend += abs(t.amount)
            we_days.add(t.date.date())
        else:
            weekday += abs(t.amount)
            wd_days.add(t.date.date())
    return {
        "weekday_total": round(weekday, 2),
        "weekend_total": round(weekend, 2),
        "weekday_daily_average": round(weekday / max(len(wd_days), 1), 2),
        "weekend_daily_average": round(weekend / max(len(we_days), 1), 2),
    }


def _category_trend(txns, category_totals):
    """First half versus second half of the period, per category."""
    if not txns:
        return []
    dates = sorted(t.date for t in txns)
    midpoint = dates[len(dates) // 2]

    first, second = defaultdict(float), defaultdict(float)
    for t in txns:
        if t.amount >= 0:
            continue
        (first if t.date < midpoint else second)[t.category or "Other"] += abs(t.amount)

    out = []
    for category in category_totals:
        a, b = first.get(category, 0), second.get(category, 0)
        if a <= 0:
            continue
        change = (b - a) / a * 100
        out.append({
            "category": category,
            "earlier": round(a, 2),
            "later": round(b, 2),
            "change_pct": round(change, 1),
            "direction": "up" if change > 5 else "down" if change < -5 else "flat",
        })
    out.sort(key=lambda r: -abs(r["change_pct"]))
    return out


def _biggest_transactions(txns, limit=5):
    spends = [t for t in txns if t.amount < 0]
    spends.sort(key=lambda t: t.amount)
    return [
        {"date": t.date.date().isoformat(), "amount": round(abs(t.amount), 2),
         "merchant": t.merchant or "-", "category": t.category}
        for t in spends[:limit]
    ]


def _savings_streak(monthly):
    """Consecutive months ending in surplus, most recent backwards."""
    streak = 0
    for month in reversed(monthly):
        if month["savings"] > 0:
            streak += 1
        else:
            break
    positive = sum(1 for m in monthly if m["savings"] > 0)
    return {"current_streak": streak, "positive_months": positive,
            "total_months": len(monthly)}


# --- 1. Money Wrapped -------------------------------------------------------

def money_wrapped(db: Session, user_id: int) -> dict:
    """
    Year in review. Designed to be screenshot-shareable, so the headline facts
    lead and the detail follows.
    """
    txns, since = _months_back(db, user_id, 12)
    if not txns:
        return {"empty": True, "reason": "No transactions yet."}

    categories = _by_category(txns)
    monthly = _monthly(txns)
    total_spend = sum(categories.values())
    total_income = sum(t.amount for t in txns if t.amount > 0)

    best = max(monthly, key=lambda m: m["savings"]) if monthly else None
    top_category = next(iter(categories), None)

    # Personality from thresholds on the category mix - rules, not a model.
    share = {c: v / total_spend for c, v in categories.items()} if total_spend else {}
    food = share.get("Food Delivery", 0) + share.get("Groceries", 0)
    shopping = share.get("Shopping", 0)
    savings_rate = ((total_income - total_spend) / total_income * 100) if total_income else 0

    if savings_rate >= 30:
        personality, personality_note = "The Compounder", "You keep a third of what you earn. That is rare."
    elif shopping >= 0.25:
        personality, personality_note = "The Treat-Yourself", "Shopping is your biggest discretionary pull."
    elif food >= 0.3:
        personality, personality_note = "The Food Lover", "More of your money goes to eating than anything else."
    elif savings_rate >= 15:
        personality, personality_note = "The Steady Saver", "Consistent, unspectacular, and it works."
    else:
        personality, personality_note = "The Live-For-Now", "Most of what comes in goes back out."

    return {
        "period": f"{since.strftime('%b %Y')} - {datetime.utcnow().strftime('%b %Y')}",
        "months_covered": len(monthly),
        "total_spend": round(total_spend, 2),
        "total_income": round(total_income, 2),
        "savings_rate": round(savings_rate, 1),
        "top_category": top_category,
        "top_category_amount": round(categories.get(top_category, 0), 2) if top_category else 0,
        "best_saving_month": best["month"] if best else None,
        "best_saving_amount": round(best["savings"], 2) if best else 0,
        "transaction_count": len(txns),
        "personality": personality,
        "personality_note": personality_note,
        "categories": [{"category": c, "amount": round(v, 2),
                        "share": round(v / total_spend * 100, 1) if total_spend else 0}
                       for c, v in list(categories.items())[:8]],
        "monthly": monthly,
        "merchants": _merchant_leaderboard(txns),
        "weekday_split": _weekday_split(txns),
        "biggest_transactions": _biggest_transactions(txns),
        "trends": _category_trend(txns, categories),
        "streak": _savings_streak(monthly),
        "averages": {
            "per_month": round(total_spend / max(len(monthly), 1), 2),
            "per_transaction": round(
                total_spend / max(len([t for t in txns if t.amount < 0]), 1), 2),
            "per_day": round(total_spend / max(len(monthly) * 30, 1), 2),
        },
        "disclaimer": SELF_REPORTED,
    }


# --- 2. Detailed Financial Health Report ------------------------------------

def financial_health(db: Session, user_id: int) -> dict:
    snapshot = financial_twin.get_snapshot(db, user_id)
    txns, since = _months_back(db, user_id, 6)
    monthly = _monthly(txns)
    categories = _by_category(txns)
    total = sum(categories.values())
    run_rate = financial_twin.monthly_run_rate(db, user_id)

    return {
        "as_of": datetime.utcnow().date().isoformat(),
        "period": f"{since.strftime('%b %Y')} onwards",
        "score": snapshot["financial_health_score"],
        "score_breakdown": snapshot["health_breakdown"],
        "net_worth": snapshot["net_worth"],
        "total_assets": snapshot["total_assets"],
        "total_liabilities": snapshot["total_liabilities"],
        "run_rate": run_rate,
        "monthly": monthly,
        "categories": [{"category": c, "amount": round(v, 2),
                        "share": round(v / total * 100, 1) if total else 0,
                        "monthly_average": round(v / max(len(monthly), 1), 2)}
                       for c, v in categories.items()],
        "cashflow_series": financial_twin.monthly_cashflow_series(db, user_id, 6),
        "merchants": _merchant_leaderboard(txns),
        "trends": _category_trend(txns, categories),
        "streak": _savings_streak(monthly),
        "biggest_transactions": _biggest_transactions(txns),
        "weekday_split": _weekday_split(txns),
        "recurring_commitments": [
            {"label": r["label"], "amount": r["amount"], "cadence": r["cadence"],
             "monthly_equivalent": r["monthly_equivalent"], "next_due": r["next_due"]}
            for r in forecast.detect_recurring(db, user_id)[:10]
        ],
        "disclaimer": SELF_REPORTED,
    }


# --- 3. Tax-Ready Export ----------------------------------------------------

def tax_ready(db: Session, user_id: int) -> dict:
    """
    Transactions organised for filing, with potentially relevant items flagged.

    It flags; it does not decide. Eligibility depends on the instrument and the
    taxpayer, neither of which FinMate knows - so every flag names the section
    to look at and says what it depends on.
    """
    txns, since = _months_back(db, user_id, 12)
    grouped = defaultdict(list)
    for t in txns:
        grouped[t.category or "Other"].append(t)

    sections = []
    flagged_total = 0.0
    for category, items in sorted(grouped.items()):
        spend = sum(abs(t.amount) for t in items if t.amount < 0)
        flag = tax_kb.flags_for_category(category)
        if flag:
            flagged_total += spend
        sections.append({
            "category": category,
            "total": round(spend, 2),
            "count": len(items),
            "flagged": bool(flag),
            "sections": flag["sections"] if flag else [],
            "note": flag["note"] if flag else None,
            "transactions": [
                {"date": t.date.date().isoformat(), "amount": round(t.amount, 2),
                 "merchant": t.merchant, "note": t.note}
                for t in sorted(items, key=lambda x: x.date, reverse=True)[:50]
            ],
        })

    # Donations come from the donations ledger, where 80G eligibility is a flag
    # the user set. Inferring it from a category name would put an unverified
    # claim into a tax document.
    since_dt = financial_twin._add_months(
        financial_twin._month_start(datetime.utcnow()), -11)
    donation_rows = (
        db.query(models.Donation)
        .filter(models.Donation.user_id == user_id,
                models.Donation.donated_on >= since_dt)
        .order_by(models.Donation.donated_on.desc())
        .all()
    )
    donations = [
        {"date": d.donated_on.date().isoformat(), "amount": round(d.amount, 2),
         "recipient": d.recipient, "is_80g_eligible": d.is_80g_eligible,
         "receipt_ref": d.receipt_ref, "note": d.note}
        for d in donation_rows
    ]
    donations_eligible = round(
        sum(d.amount for d in donation_rows if d.is_80g_eligible), 2)

    income = sum(t.amount for t in txns if t.amount > 0)
    headroom = []
    for section, limit in tax_kb.LIMITS.items():
        used = sum(s["total"] for s in sections
                   if section in s["sections"])
        headroom.append({
            "section": section,
            "limit": limit,
            "identified_spend": round(min(used, limit), 2),
            "remaining": round(max(limit - used, 0), 2),
            "note": "Identified spend is what your records show in related "
                    "categories, not a confirmed eligible amount.",
        })

    return {
        "financial_year": tax_kb.FINANCIAL_YEAR,
        "rules_as_of": tax_kb.AS_OF,
        "period": f"{since.date().isoformat()} to {datetime.utcnow().date().isoformat()}",
        "total_income_recorded": round(income, 2),
        "flagged_total": round(flagged_total, 2),
        "sections": sections,
        "donations": donations,
        "donations_total": round(sum(d["amount"] for d in donations), 2),
        "donations_80g_marked": donations_eligible,
        "donations_note": (
            "80G eligibility is what you marked. Whether an institution is "
            "registered under 80G is a fact FinMate cannot verify - check your receipt."
        ),
        "headroom": headroom,
        "monthly_breakdown": _monthly(txns),
        "merchants": _merchant_leaderboard(txns, limit=15),
        "reference_facts": tax_kb.FACTS,
        "disclaimer": tax_kb.DISCLAIMER,
    }


# --- 4. Wedding Financial Plan ----------------------------------------------

def wedding_plan(db: Session, user_id: int) -> dict:
    goal = (
        db.query(models.Goal)
        .filter(models.Goal.user_id == user_id, models.Goal.goal_type == "wedding")
        .first()
    )
    if not goal:
        return {"empty": True,
                "reason": "Create a goal of type 'wedding' to generate this plan."}

    remaining = max(goal.target_amount - goal.current_amount, 0)
    monthly = goal.monthly_contribution or 0
    months_needed = (remaining / monthly) if monthly > 0 else None

    months_available = None
    if goal.target_date:
        months_available = max(
            (goal.target_date.year - datetime.utcnow().year) * 12
            + (goal.target_date.month - datetime.utcnow().month), 0
        )

    gap_per_month = None
    if months_available and months_available > 0:
        gap_per_month = max(remaining / months_available - monthly, 0)

    # Three ways to close the gap - the same planner arithmetic with different
    # inputs, not a second model of the problem.
    scenarios = []
    if gap_per_month and gap_per_month > 0:
        scenarios.append({
            "label": f"Save Rs {gap_per_month:,.0f} more each month",
            "detail": f"Reaches Rs {goal.target_amount:,.0f} by {goal.target_date.date()}.",
            "monthly_contribution": round(monthly + gap_per_month, 2),
        })
    if monthly > 0:
        extended = months_needed
        scenarios.append({
            "label": f"Keep Rs {monthly:,.0f}/month and extend the date",
            "detail": f"Fully funded in about {extended:.0f} months at the current pace.",
            "months": round(extended) if extended else None,
        })
    lump = min(remaining, 100_000)
    if lump > 0 and monthly > 0:
        scenarios.append({
            "label": f"Add a Rs {lump:,.0f} family contribution",
            "detail": f"Cuts about {lump / monthly:.0f} months off the timeline.",
            "months_saved": round(lump / monthly, 1),
        })

    milestones = []
    if monthly > 0 and months_needed:
        running = goal.current_amount
        step = max(1, int(months_needed // 4))
        for m in range(1, int(months_needed) + 1):
            running += monthly
            if m % step == 0 or m == int(months_needed):
                milestones.append({
                    "month": m,
                    "amount": round(min(running, goal.target_amount), 2),
                    "percent": round(min(running / goal.target_amount * 100, 100), 1),
                })

    return {
        "goal": {"name": goal.name, "target": goal.target_amount,
                 "saved": goal.current_amount, "remaining": round(remaining, 2),
                 "target_date": goal.target_date.date().isoformat() if goal.target_date else None},
        "monthly_contribution": monthly,
        "months_needed": round(months_needed, 1) if months_needed else None,
        "months_available": months_available,
        "monthly_gap": round(gap_per_month, 2) if gap_per_month else 0,
        "on_track": bool(gap_per_month is not None and gap_per_month <= 0),
        "scenarios": scenarios,
        "milestones": milestones,
        "disclaimer": SELF_REPORTED,
    }


# --- 5. Loan Readiness Report -----------------------------------------------

def loan_readiness(db: Session, user_id: int) -> dict:
    """
    A readiness indicator from the user's own records.

    Explicitly not an underwriting score: no bureau data, no verification, and
    the thresholds are published below so nobody mistakes it for one.
    """
    run_rate = financial_twin.monthly_run_rate(db, user_id)
    snapshot = financial_twin.get_snapshot(db, user_id)
    liabilities = db.query(models.Liability).filter(
        models.Liability.user_id == user_id
    ).all()

    income = run_rate["income"]
    obligations = sum(l.monthly_payment or 0 for l in liabilities)
    dti = (obligations / income * 100) if income > 0 else 0

    txns, _ = _months_back(db, user_id, 6)
    monthly = _monthly(txns)
    incomes = [m["income"] for m in monthly if m["income"] > 0]
    if len(incomes) >= 2:
        mean = sum(incomes) / len(incomes)
        variance = sum((i - mean) ** 2 for i in incomes) / len(incomes)
        stability = max(0.0, 100 - (variance ** 0.5 / mean * 100)) if mean else 0
    else:
        stability = 0

    if dti <= 30 and stability >= 80:
        indicator, summary = "Strong", "Low obligations against a steady income."
    elif dti <= 45 and stability >= 60:
        indicator, summary = "Moderate", "Serviceable, though lenders will look closely at the obligations."
    else:
        indicator, summary = "Needs work", "Obligations or income variability are likely to count against an application."

    return {
        "as_of": datetime.utcnow().date().isoformat(),
        "indicator": indicator,
        "summary": summary,
        "monthly_income": round(income, 2),
        "income_basis": run_rate["basis"],
        "income_stability_pct": round(stability, 1),
        "monthly_obligations": round(obligations, 2),
        "debt_to_income_pct": round(dti, 1),
        "total_debt": round(snapshot["total_liabilities"], 2),
        "net_worth": snapshot["net_worth"],
        "obligations": [
            {"name": l.name, "balance": l.amount, "rate": l.interest_rate,
             "monthly_payment": l.monthly_payment}
            for l in liabilities
        ],
        "thresholds": {
            "strong": "debt-to-income at or below 30% and income stability at or above 80%",
            "moderate": "debt-to-income at or below 45% and income stability at or above 60%",
        },
        "disclaimer": (
            "This is FinMate's own readiness indicator, computed from the records "
            "you provided. It is not a credit score, not an underwriting decision, "
            "and carries no weight with any lender. " + SELF_REPORTED
        ),
    }


# --- 6. Net Worth Statement -------------------------------------------------

def net_worth(db: Session, user_id: int) -> dict:
    assets = db.query(models.Asset).filter(models.Asset.user_id == user_id).all()
    liabilities = db.query(models.Liability).filter(
        models.Liability.user_id == user_id
    ).all()

    total_assets = sum(a.value or 0 for a in assets)
    total_liabilities = sum(l.amount or 0 for l in liabilities)

    grouped = defaultdict(float)
    for a in assets:
        grouped[a.asset_type or "other"] += a.value or 0

    return {
        "as_of": datetime.utcnow().date().isoformat(),
        "assets": [{"name": a.name, "type": a.asset_type, "value": a.value} for a in assets],
        "liabilities": [{"name": l.name, "type": l.liability_type, "amount": l.amount,
                         "rate": l.interest_rate} for l in liabilities],
        "assets_by_type": [{"type": k, "value": round(v, 2)} for k, v in grouped.items()],
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "net_worth": round(total_assets - total_liabilities, 2),
        "composition": [
            {"type": k, "value": round(v, 2),
             "share": round(v / total_assets * 100, 1) if total_assets else 0}
            for k, v in grouped.items()
        ],
        "leverage_ratio": round(total_liabilities / total_assets * 100, 1) if total_assets else 0,
        "liquid_assets": round(
            sum(a.value or 0 for a in assets
                if (a.asset_type or "").lower() in ("cash", "savings", "bank")), 2),
        "disclaimer": SELF_REPORTED,
    }


# --- 7. Debt Payoff Plan ----------------------------------------------------

def debt_payoff(db: Session, user_id: int, extra_monthly: float = 5000) -> dict:
    plan = debt_service.payoff_plan(db, user_id, extra_monthly=extra_monthly)
    if not plan.get("debts"):
        return {"empty": True, "reason": "No liabilities recorded."}

    plan["as_of"] = datetime.utcnow().date().isoformat()
    plan["disclaimer"] = SELF_REPORTED
    return plan


GENERATORS = {
    "money_wrapped": money_wrapped,
    "financial_health": financial_health,
    "tax_ready": tax_ready,
    "wedding_plan": wedding_plan,
    "loan_readiness": loan_readiness,
    "net_worth": net_worth,
    "debt_payoff": debt_payoff,
}


def generate(db: Session, user_id: int, report_id: str) -> dict:
    generator = GENERATORS.get(report_id)
    if not generator:
        raise KeyError(report_id)
    data = generator(db, user_id)
    meta = CATALOGUE_BY_ID[report_id]
    return {
        "id": report_id,
        "title": meta["title"],
        "emoji": meta["emoji"],
        "generated_at": datetime.utcnow().isoformat(),
        "data": data,
    }
