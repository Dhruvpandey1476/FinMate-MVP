"""Proactive nudges: in-app inbox plus the cron entry point for the digest."""
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..services import digest

router = APIRouter(tags=["Proactive Nudges"])

CRON_KEY = os.getenv("CRON_KEY", "")


@router.get("/api/notifications", response_model=List[schemas.NotificationOut])
def list_notifications(unread_only: bool = False, limit: int = 50,
                       db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)):
    return digest.list_for_user(db, user.id, limit=limit, unread_only=unread_only)


@router.post("/api/notifications/read")
def mark_read(notification_id: int = None, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    """Mark one notification read, or all of them when no id is given."""
    return {"updated": digest.mark_read(db, user.id, notification_id)}


@router.post("/api/notifications/refresh", response_model=List[schemas.NotificationOut])
def refresh(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Regenerate this user's nudges on demand (what the bell icon calls)."""
    digest.generate_for_user(db, user)
    return digest.list_for_user(db, user.id, limit=50)


@router.post("/api/digest/run")
def run_digest(key: str = Query(""), db: Session = Depends(get_db)):
    """
    Cron entry point - generate and deliver nudges for every eligible user.

    Protected by CRON_KEY rather than a user session so a scheduler can call it.
    Disabled entirely when CRON_KEY is unset, so an unconfigured deployment
    cannot be triggered by a stranger.
    """
    if not CRON_KEY or key != CRON_KEY:
        raise HTTPException(status_code=401, detail="Invalid cron key.")
    return digest.run_for_all(db)
