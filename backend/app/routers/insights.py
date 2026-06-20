from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..agents import opportunity_discovery

router = APIRouter(prefix="/api/insights", tags=["Opportunity Discovery"])

DEMO_USER_ID = 1


@router.get("/")
def get_insights(db: Session = Depends(get_db)):
    return opportunity_discovery.discover(db, DEMO_USER_ID)
