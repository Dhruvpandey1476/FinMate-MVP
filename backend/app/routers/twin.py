from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import schemas
from ..database import get_db
from ..services import financial_twin

router = APIRouter(prefix="/api/twin", tags=["Financial Twin"])

DEMO_USER_ID = 1


@router.get("/snapshot", response_model=schemas.FinancialTwinSnapshot)
def get_snapshot(db: Session = Depends(get_db)):
    return financial_twin.get_snapshot(db, DEMO_USER_ID)


@router.get("/cashflow-series")
def get_cashflow_series(months: int = 6, db: Session = Depends(get_db)):
    return financial_twin.monthly_cashflow_series(db, DEMO_USER_ID, months)
