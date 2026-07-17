from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..services import financial_twin

router = APIRouter(prefix="/api/twin", tags=["Financial Twin"])


@router.get("/snapshot", response_model=schemas.FinancialTwinSnapshot)
def get_snapshot(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return financial_twin.get_snapshot(db, user.id)


@router.get("/cashflow-series")
def get_cashflow_series(months: int = 6, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return financial_twin.monthly_cashflow_series(db, user.id, months)
