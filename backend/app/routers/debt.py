"""Debt payoff planning and prepay-vs-invest analysis."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..services import debt as debt_service, entitlements

router = APIRouter(prefix="/api/debt", tags=["Debt Optimizer"])


def _require_feature(user: models.User):
    if not entitlements.feature_enabled(user, "debt_optimizer"):
        raise HTTPException(
            status_code=402,
            detail="The debt optimiser is available on Plus and Pro plans.",
        )


@router.get("/plan")
def plan(extra_monthly: float = 0.0, strategy: str = "avalanche",
         db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """
    Payoff ordering with a surplus rolled forward as each debt clears.

    Both avalanche and snowball are returned so the interest cost of the
    behavioural choice is explicit.
    """
    _require_feature(user)
    if strategy not in ("avalanche", "snowball"):
        raise HTTPException(status_code=400, detail="strategy must be 'avalanche' or 'snowball'.")
    if extra_monthly < 0:
        raise HTTPException(status_code=400, detail="extra_monthly cannot be negative.")

    return debt_service.payoff_plan(db, user.id, extra_monthly=extra_monthly, strategy=strategy)


@router.get("/prepay-vs-invest")
def prepay_vs_invest(amount: float, annual_return: float = 0.10, liability_id: int = None,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    """Guaranteed interest saved versus expected post-tax investment return."""
    _require_feature(user)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive.")

    result = debt_service.prepay_vs_invest(
        db, user.id, amount, annual_return=annual_return, liability_id=liability_id
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/amortize/{liability_id}")
def amortize(liability_id: int, extra_monthly: float = 0.0,
             db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Full amortisation schedule for one loan."""
    _require_feature(user)
    liability = (
        db.query(models.Liability)
        .filter(models.Liability.id == liability_id, models.Liability.user_id == user.id)
        .first()
    )
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found.")

    base = debt_service.amortize(liability.amount, liability.interest_rate,
                                 liability.monthly_payment)
    accelerated = debt_service.amortize(liability.amount, liability.interest_rate,
                                        liability.monthly_payment,
                                        extra_monthly=extra_monthly)
    return {
        "liability": {
            "id": liability.id, "name": liability.name,
            "balance": liability.amount, "interest_rate": liability.interest_rate,
            "monthly_payment": liability.monthly_payment,
        },
        "baseline": base,
        "accelerated": accelerated if extra_monthly else None,
    }
