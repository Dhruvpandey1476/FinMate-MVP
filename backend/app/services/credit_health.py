"""
Credit Health - computed from the user's own records.

What this is: utilisation, debt-to-income, obligation load and payment
consistency, derived from the liabilities and transactions the user entered.

What this is not: a credit score. A CIBIL or Experian score requires a signed
commercial data-sharing agreement with the bureau. There is no API key that
substitutes for one, and inventing a number that looks like a bureau score
would be the single most misleading thing this product could do. The bureau
field is therefore absent rather than mocked.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models
from . import financial_twin, debt as debt_service

logger = logging.getLogger("finmate.credit_health")

# Published so the score is arguable rather than opaque.
BANDS = [
    (80, "Excellent", "Low utilisation, comfortable obligations, steady income."),
    (65, "Good", "Healthy overall; one factor is holding you back."),
    (45, "Fair", "Serviceable, but a lender would look closely at this."),
    (0, "Needs work", "Obligations or utilisation are high relative to income."),
]

CARD_TYPES = ("credit_card", "card")


def assess(db: Session, user_id: int) -> dict:
    liabilities = db.query(models.Liability).filter(
        models.Liability.user_id == user_id
    ).all()
    run_rate = financial_twin.monthly_run_rate(db, user_id)
    income = run_rate["income"]

    factors = []
    score = 100.0

    # --- Credit utilisation -------------------------------------------------
    cards = [l for l in liabilities if (l.liability_type or "").lower() in CARD_TYPES]
    card_balance = sum(l.amount or 0 for l in cards)
    # Without a stated limit, a month of income is a defensible stand-in.
    assumed_limit = max(income * 1.0, 1.0)
    utilisation = (card_balance / assumed_limit * 100) if card_balance else 0

    if utilisation > 30:
        penalty = min((utilisation - 30) * 0.6, 30)
        score -= penalty
        detail = (f"Card balances are {utilisation:.0f}% of a month's income. "
                  f"Under 30% is where lenders stop worrying.")
    else:
        penalty = 0
        detail = ("Card balances are low relative to income."
                  if card_balance else "No credit-card balances recorded.")
    factors.append({"label": "Credit utilisation", "points": -round(penalty, 1),
                    "value": f"{utilisation:.0f}%", "detail": detail})

    # --- Debt-to-income -----------------------------------------------------
    obligations = sum(l.monthly_payment or 0 for l in liabilities)
    dti = (obligations / income * 100) if income > 0 else 0
    if dti > 36:
        penalty = min((dti - 36) * 0.8, 30)
        detail = f"EMIs take {dti:.0f}% of monthly income; 36% is the usual comfort ceiling."
    else:
        penalty = 0
        detail = (f"EMIs take {dti:.0f}% of monthly income, within the usual comfort range."
                  if obligations else "No monthly obligations recorded.")
    score -= penalty
    factors.append({"label": "Debt to income", "points": -round(penalty, 1),
                    "value": f"{dti:.0f}%", "detail": detail})

    # --- Obligation count ---------------------------------------------------
    count_penalty = max(0, (len(liabilities) - 3) * 4)
    score -= count_penalty
    factors.append({
        "label": "Number of obligations", "points": -round(count_penalty, 1),
        "value": str(len(liabilities)),
        "detail": (f"{len(liabilities)} active obligations. Several at once is "
                   f"harder to service if income dips."
                   if len(liabilities) > 3 else
                   f"{len(liabilities)} active obligation(s) - manageable."),
    })

    # --- Payment consistency ------------------------------------------------
    # A proxy: months in the last six where an EMI-like payment was recorded.
    since = datetime.utcnow() - timedelta(days=185)
    emi_months = {
        t.date.strftime("%Y-%m")
        for t in db.query(models.Transaction).filter(
            models.Transaction.user_id == user_id,
            models.Transaction.date >= since,
            models.Transaction.amount < 0,
        ).all()
        if (t.category or "").lower() in ("emi/loan", "emi", "loan")
    }
    if liabilities:
        consistency = min(len(emi_months) / 6 * 100, 100)
        penalty = (100 - consistency) * 0.15
        detail = (f"Repayments recorded in {len(emi_months)} of the last 6 months. "
                  f"This is inferred from your logged transactions, not a lender's record.")
    else:
        consistency, penalty = 100.0, 0
        detail = "No obligations to service."
    score -= penalty
    factors.append({"label": "Payment consistency", "points": -round(penalty, 1),
                    "value": f"{consistency:.0f}%", "detail": detail})

    score = int(max(0, min(100, round(score))))
    band, band_note = next((b, n) for threshold, b, n in BANDS if score >= threshold)

    payoff = debt_service.payoff_plan(db, user_id, extra_monthly=0)

    return {
        "score": score,
        "band": band,
        "band_note": band_note,
        "factors": factors,
        "utilisation_pct": round(utilisation, 1),
        "debt_to_income_pct": round(dti, 1),
        "monthly_obligations": round(obligations, 2),
        "monthly_income": round(income, 2),
        "income_basis": run_rate["basis"],
        "total_debt": round(sum(l.amount or 0 for l in liabilities), 2),
        "obligations": [
            {"name": l.name, "type": l.liability_type, "balance": l.amount,
             "rate": l.interest_rate, "monthly_payment": l.monthly_payment}
            for l in liabilities
        ],
        "payoff_months": payoff.get("baseline", {}).get("months"),
        "bureau_score": None,
        "bureau_note": (
            "Live bureau monitoring (CIBIL, Experian) needs a commercial "
            "data-sharing agreement and is not part of this build. This score is "
            "FinMate's own, computed from the records you entered - it is not a "
            "credit score and carries no weight with any lender."
        ),
        "improvements": _improvements(utilisation, dti, len(liabilities)),
    }


def _improvements(utilisation: float, dti: float, obligation_count: int) -> list:
    """Concrete, ordered by how much each would move the score."""
    out = []
    if utilisation > 30:
        out.append({
            "action": "Bring card balances under 30% of a month's income",
            "why": f"Utilisation is the heaviest single factor here, currently {utilisation:.0f}%.",
        })
    if dti > 36:
        out.append({
            "action": "Reduce monthly EMIs below 36% of income",
            "why": f"EMIs currently take {dti:.0f}%, above the usual comfort ceiling.",
        })
    if obligation_count > 3:
        out.append({
            "action": "Consolidate or clear the smallest obligations first",
            "why": f"{obligation_count} simultaneous obligations are harder to service.",
        })
    if not out:
        out.append({
            "action": "Keep it steady",
            "why": "Nothing here is dragging the score down.",
        })
    return out
