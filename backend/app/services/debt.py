"""
Debt optimiser.

The Liability model already stores interest_rate and monthly_payment, and
nothing in the product used them: loans were a flat number subtracted from net
worth. Real amortisation answers questions users genuinely lose sleep over -
should I prepay or invest, which loan do I kill first, what does one extra EMI
a year actually save.

All arithmetic, no LLM.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger("finmate.debt")

MAX_MONTHS = 600  # 50 years - guards against a payment that never amortises


def amortize(principal: float, annual_rate: float, monthly_payment: float,
             extra_monthly: float = 0.0, lump_sum: float = 0.0) -> dict:
    """
    Amortise a loan month by month.

    Returns total interest, payoff month, and the schedule. If the payment does
    not cover the monthly interest the loan never amortises - that is reported
    rather than silently looping.
    """
    principal = max(float(principal or 0), 0.0)
    if principal <= 0:
        return {"months": 0, "total_interest": 0.0, "total_paid": 0.0,
                "schedule": [], "amortizes": True}

    monthly_rate = float(annual_rate or 0) / 100.0 / 12.0
    payment = float(monthly_payment or 0) + float(extra_monthly or 0)
    balance = principal - float(lump_sum or 0)
    if balance <= 0:
        return {"months": 0, "total_interest": 0.0, "total_paid": float(lump_sum),
                "schedule": [], "amortizes": True}

    first_month_interest = balance * monthly_rate
    if payment <= first_month_interest:
        return {
            "months": None,
            "total_interest": None,
            "total_paid": None,
            "schedule": [],
            "amortizes": False,
            "reason": (
                f"A payment of Rs {payment:,.0f}/month does not cover the "
                f"Rs {first_month_interest:,.0f} monthly interest - the balance grows."
            ),
        }

    schedule = []
    total_interest = 0.0
    month = 0

    while balance > 0 and month < MAX_MONTHS:
        month += 1
        interest = balance * monthly_rate
        principal_paid = min(payment - interest, balance)
        balance -= principal_paid
        total_interest += interest
        schedule.append({
            "month": month,
            "interest": round(interest, 2),
            "principal": round(principal_paid, 2),
            "balance": round(max(balance, 0), 2),
        })

    return {
        "months": month,
        "years": round(month / 12, 1),
        "total_interest": round(total_interest, 2),
        "total_paid": round(principal + total_interest, 2),
        "schedule": schedule,
        "amortizes": True,
    }


def payoff_plan(db: Session, user_id: int, extra_monthly: float = 0.0,
                strategy: str = "avalanche") -> dict:
    """
    Order debts and apply any surplus to one of them.

    avalanche = highest interest first (mathematically optimal)
    snowball  = smallest balance first (pays off faster psychologically)

    Both are reported so the user can see exactly what the behavioural choice
    costs them in rupees.
    """
    liabilities = (
        db.query(models.Liability)
        .filter(models.Liability.user_id == user_id, models.Liability.amount > 0)
        .all()
    )
    if not liabilities:
        return {"debts": [], "message": "No liabilities on record."}

    def _simulate(order, surplus):
        """Roll the surplus (and each freed EMI) into the next debt in order."""
        remaining = [
            {
                "id": l.id, "name": l.name,
                "balance": float(l.amount or 0),
                "rate": float(l.interest_rate or 0),
                "payment": float(l.monthly_payment or 0),
            }
            for l in order
        ]
        rolling = float(surplus or 0)
        total_interest = 0.0
        month = 0
        payoff_months = {}

        while any(d["balance"] > 0 for d in remaining) and month < MAX_MONTHS:
            month += 1
            focus_found = False
            for debt in remaining:
                if debt["balance"] <= 0:
                    continue
                interest = debt["balance"] * debt["rate"] / 100.0 / 12.0
                total_interest += interest

                payment = debt["payment"]
                if not focus_found:
                    payment += rolling  # surplus goes to the first live debt
                    focus_found = True

                principal_paid = min(max(payment - interest, 0), debt["balance"])
                if principal_paid <= 0 and debt["balance"] > 0:
                    # Payment does not cover interest; this plan cannot complete.
                    return {"months": None, "total_interest": None, "payoff_months": {},
                            "amortizes": False}

                debt["balance"] -= principal_paid
                if debt["balance"] <= 0.01:
                    debt["balance"] = 0.0
                    payoff_months[debt["id"]] = month
                    # The freed EMI now accelerates the remaining debts.
                    rolling += debt["payment"]

        return {
            "months": month,
            "total_interest": round(total_interest, 2),
            "payoff_months": payoff_months,
            "amortizes": True,
        }

    avalanche_order = sorted(liabilities, key=lambda l: -(l.interest_rate or 0))
    snowball_order = sorted(liabilities, key=lambda l: (l.amount or 0))

    baseline = _simulate(avalanche_order, 0.0)
    avalanche = _simulate(avalanche_order, extra_monthly)
    snowball = _simulate(snowball_order, extra_monthly)

    chosen = avalanche if strategy == "avalanche" else snowball
    order = avalanche_order if strategy == "avalanche" else snowball_order

    debts = []
    for idx, l in enumerate(order):
        solo = amortize(l.amount, l.interest_rate, l.monthly_payment)
        debts.append({
            "id": l.id,
            "name": l.name,
            "type": l.liability_type,
            "balance": round(float(l.amount or 0), 2),
            "interest_rate": float(l.interest_rate or 0),
            "monthly_payment": round(float(l.monthly_payment or 0), 2),
            "priority": idx + 1,
            "months_if_alone": solo.get("months"),
            "interest_if_alone": solo.get("total_interest"),
            "payoff_month_in_plan": chosen.get("payoff_months", {}).get(l.id),
        })

    interest_saved = None
    months_saved = None
    if baseline.get("amortizes") and chosen.get("amortizes"):
        interest_saved = round((baseline["total_interest"] or 0) - (chosen["total_interest"] or 0), 2)
        months_saved = (baseline["months"] or 0) - (chosen["months"] or 0)

    strategy_delta = None
    if avalanche.get("amortizes") and snowball.get("amortizes"):
        strategy_delta = round(
            (snowball["total_interest"] or 0) - (avalanche["total_interest"] or 0), 2
        )

    return {
        "strategy": strategy,
        "debts": debts,
        "total_debt": round(sum(float(l.amount or 0) for l in liabilities), 2),
        "total_monthly_payment": round(sum(float(l.monthly_payment or 0) for l in liabilities), 2),
        "extra_monthly": round(float(extra_monthly or 0), 2),
        "baseline": baseline,
        "avalanche": avalanche,
        "snowball": snowball,
        "interest_saved_vs_baseline": interest_saved,
        "months_saved_vs_baseline": months_saved,
        "avalanche_advantage": strategy_delta,
        "summary": _payoff_summary(extra_monthly, interest_saved, months_saved, strategy_delta),
    }


def _payoff_summary(extra, interest_saved, months_saved, strategy_delta) -> str:
    parts = []
    if extra and interest_saved:
        parts.append(
            f"Putting an extra Rs {extra:,.0f}/month toward your debts saves "
            f"Rs {interest_saved:,.0f} in interest and clears them "
            f"{months_saved} months sooner."
        )
    elif not extra:
        parts.append("Add a surplus amount to see how much faster your debts clear.")

    if strategy_delta and strategy_delta > 0:
        parts.append(
            f"Avalanche (highest rate first) beats snowball by "
            f"Rs {strategy_delta:,.0f} in total interest."
        )
    return " ".join(parts) or "Debt plan computed."


def prepay_vs_invest(db: Session, user_id: int, amount: float,
                     annual_return: float = 0.10, tax_rate: float = 0.125,
                     liability_id: int = None) -> dict:
    """
    Should a surplus go to the loan or the market?

    Compares guaranteed interest saved against expected post-tax investment
    return. The comparison is deliberately conservative: loan prepayment is
    risk-free, investing is not, so a small expected edge does not justify it.
    """
    q = db.query(models.Liability).filter(
        models.Liability.user_id == user_id, models.Liability.amount > 0
    )
    if liability_id:
        q = q.filter(models.Liability.id == liability_id)
    target = q.order_by(models.Liability.interest_rate.desc()).first()

    if not target:
        return {"error": "No liabilities on record to compare against."}

    amount = max(float(amount or 0), 0.0)
    base = amortize(target.amount, target.interest_rate, target.monthly_payment)
    with_prepay = amortize(target.amount, target.interest_rate, target.monthly_payment,
                           lump_sum=amount)

    if not base.get("amortizes") or not with_prepay.get("amortizes"):
        return {
            "error": (
                f"'{target.name}' does not amortise at its current EMI - "
                f"increase the monthly payment before considering prepayment."
            )
        }

    interest_saved = round(base["total_interest"] - with_prepay["total_interest"], 2)
    months_saved = base["months"] - with_prepay["months"]

    # Invest the same lump sum over the loan's original remaining life.
    years = base["months"] / 12.0
    gross = amount * ((1 + annual_return) ** years)
    gain = gross - amount
    post_tax_gain = gain * (1 - tax_rate)
    investment_value = amount + post_tax_gain

    verdict = "prepay" if interest_saved > post_tax_gain else "invest"
    margin = abs(interest_saved - post_tax_gain)

    return {
        "liability": {
            "id": target.id, "name": target.name,
            "balance": round(float(target.amount or 0), 2),
            "interest_rate": float(target.interest_rate or 0),
        },
        "amount": round(amount, 2),
        "horizon_years": round(years, 1),
        "prepay": {
            "interest_saved": interest_saved,
            "months_saved": months_saved,
            "new_payoff_months": with_prepay["months"],
        },
        "invest": {
            "assumed_annual_return": annual_return,
            "assumed_tax_rate": tax_rate,
            "gross_value": round(gross, 2),
            "post_tax_gain": round(post_tax_gain, 2),
            "post_tax_value": round(investment_value, 2),
        },
        "verdict": verdict,
        "summary": (
            f"Prepaying Rs {amount:,.0f} on '{target.name}' saves Rs {interest_saved:,.0f} "
            f"in guaranteed interest and clears it {months_saved} months early. "
            f"Investing the same amount at {annual_return * 100:.0f}% would return about "
            f"Rs {post_tax_gain:,.0f} after tax - but that return is not guaranteed. "
            f"{'Prepaying wins' if verdict == 'prepay' else 'Investing wins'} "
            f"by roughly Rs {margin:,.0f}."
        ),
    }
