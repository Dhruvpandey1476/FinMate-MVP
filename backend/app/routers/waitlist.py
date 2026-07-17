"""Waitlist capture (public) + admin stats (key-protected)."""
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db

router = APIRouter(tags=["Growth"])

ADMIN_KEY = os.getenv("ADMIN_KEY", "")


@router.post("/api/waitlist")
def join_waitlist(payload: dict, db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email.")
    existing = db.query(models.Waitlist).filter(models.Waitlist.email == email).first()
    if existing:
        return {"ok": True, "message": "You're already on the list!"}
    db.add(models.Waitlist(email=email, note=(payload.get("note") or None)))
    db.commit()
    return {"ok": True, "message": "You're on the list — we'll be in touch."}


@router.get("/api/admin/stats")
def admin_stats(key: str = Query(""), db: Session = Depends(get_db)):
    if not ADMIN_KEY or key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key.")
    signups = db.query(models.User).count()
    waitlist = db.query(models.Waitlist).count()
    active = db.query(models.ChatMessage.user_id).distinct().count()
    return {
        "signups": signups,
        "waitlist": waitlist,
        "users_who_chatted": active,
    }
