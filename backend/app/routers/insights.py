from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..agents import opportunity_discovery

router = APIRouter(prefix="/api/insights", tags=["Opportunity Discovery"])


@router.get("/")
def get_insights(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return opportunity_discovery.discover(db, user.id)
