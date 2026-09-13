"""Cash-flow forecasting, recurring detection and budget tracking."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..services import forecast as forecast_service, cache, financial_twin, entitlements

router = APIRouter(prefix="/api/forecast", tags=["Cash-Flow Forecast"])

CACHE_KIND = "forecast"


@router.get("/")
def get_forecast(days: int = 90, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    """
    Day-by-day cash projection with the low-balance date.

    Cached against the transaction fingerprint - the projection is pure
    arithmetic but walks the full history, and the dashboard polls it.
    """
    if not entitlements.feature_enabled(user, "forecast"):
        raise HTTPException(status_code=402, detail="Forecasting is not available on your plan.")

    fingerprint = f"{financial_twin.transactions_fingerprint(db, user.id)}:{days}"
    cached = cache.get(db, user.id, CACHE_KIND, fingerprint)
    if cached is not None:
        return cached

    result = forecast_service.forecast(db, user.id, days=days)
    cache.put(db, user.id, CACHE_KIND, fingerprint, result)
    return result


@router.get("/recurring")
def recurring(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Detected subscriptions and committed bills, with next due dates."""
    return {
        "expenses": forecast_service.detect_recurring(db, user.id),
        "income": forecast_service.detect_recurring_income(db, user.id),
    }


@router.get("/budget")
def budget(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Month-to-date spend per category versus the trailing 3-month pace."""
    return forecast_service.budget_status(db, user.id)
