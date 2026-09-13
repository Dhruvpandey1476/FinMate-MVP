from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..agents import opportunity_discovery

router = APIRouter(prefix="/api/insights", tags=["Opportunity Discovery"])


@router.get("/")
def get_insights(refresh: bool = False, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    """
    Ranked spending insights.

    Served from cache unless `refresh=true` - the dashboard calls this on every
    mount, and the LLM enrichment pass is identical for identical data.
    """
    return opportunity_discovery.discover(db, user.id, use_cache=not refresh, user=user)
