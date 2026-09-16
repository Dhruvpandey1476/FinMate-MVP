"""
Paid outcomes - the reports catalogue, unlock flow and generation.

Framed as "financial outcomes you can generate" rather than a pricing page,
because that is the business model: free to understand your money, pay when
FinMate produces something worth paying for.

The unlock is mocked. The reports are not - every one is generated from the
user's real data, so what a buyer would receive is exactly what is shown here.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..services import reports as reports_service, analytics

logger = logging.getLogger("finmate.reports")

router = APIRouter(prefix="/api/reports", tags=["Paid Outcomes"])


def _unlocked_ids(db: Session, user_id: int) -> set:
    return {
        r.report_id
        for r in db.query(models.ReportUnlock).filter(
            models.ReportUnlock.user_id == user_id
        )
    }


@router.get("/")
def catalogue(db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    """Everything on offer, with what this account has already unlocked."""
    unlocked = _unlocked_ids(db, user.id)
    return [
        {**report, "unlocked": report["id"] in unlocked}
        for report in reports_service.CATALOGUE
    ]


@router.post("/{report_id}/unlock")
def unlock(report_id: str, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)):
    """
    Unlock a report.

    DEMO MODE: this grants access immediately. Real payment integration is
    Razorpay (or Stripe for cards), post-funding - it would sit in front of
    this call and pass its reference through as payment_ref. Nothing else about
    the flow changes, which is the point of mocking it here rather than
    stubbing the reports.
    """
    if report_id not in reports_service.CATALOGUE_BY_ID:
        raise HTTPException(status_code=404, detail="No such report.")

    meta = reports_service.CATALOGUE_BY_ID[report_id]
    record = models.ReportUnlock(
        user_id=user.id,
        report_id=report_id,
        price_inr=meta["price_inr"],
        payment_ref=f"demo_{uuid.uuid4().hex[:12]}",
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # already unlocked; idempotent by design

    analytics.track(db, user.id, "report_unlocked",
                    {"report": report_id, "price_inr": meta["price_inr"]})

    return {"ok": True, "report_id": report_id, "unlocked": True,
            "demo_mode": True,
            "message": f"{meta['title']} unlocked."}


@router.get("/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    """Generate a report the account has unlocked."""
    if report_id not in reports_service.CATALOGUE_BY_ID:
        raise HTTPException(status_code=404, detail="No such report.")

    if report_id not in _unlocked_ids(db, user.id):
        raise HTTPException(
            status_code=402,
            detail=f"{reports_service.CATALOGUE_BY_ID[report_id]['title']} is locked.",
        )

    try:
        result = reports_service.generate(db, user.id, report_id)
    except Exception as e:
        logger.error("Report %s failed for user %s: %s", report_id, user.id, e,
                     exc_info=True)
        raise HTTPException(status_code=500, detail="Could not generate that report.")

    analytics.track(db, user.id, "report_viewed", {"report": report_id})
    return result


@router.get("/{report_id}/preview")
def preview(report_id: str, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    """
    Enough of a report to show it is real before paying.

    A locked product nobody can see the shape of does not sell, and a preview
    built from the user's own numbers is more convincing than a sample.
    """
    if report_id not in reports_service.CATALOGUE_BY_ID:
        raise HTTPException(status_code=404, detail="No such report.")

    try:
        full = reports_service.generate(db, user.id, report_id)
    except Exception:
        return {"id": report_id, "available": False}

    data = full["data"]
    if data.get("empty"):
        return {"id": report_id, "available": False, "reason": data.get("reason")}

    # A few headline numbers only - never the body of the report.
    highlights = {
        k: v for k, v in data.items()
        if isinstance(v, (int, float, str)) and k not in ("disclaimer", "reason")
    }
    return {
        "id": report_id,
        "available": True,
        "highlights": dict(list(highlights.items())[:5]),
    }
