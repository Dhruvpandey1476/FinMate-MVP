"""
Quick Add - log a transaction from one line of text.

The frontend presents this as a WhatsApp-style thread because that is the
interaction we intend to ship on real WhatsApp later. Nothing here talks to
Meta's API; it is the same parser a webhook would call, reached through the
app instead.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import get_current_user, rate_limit
from ..services import quickadd_parser, categorizer, dedupe, cache, analytics

logger = logging.getLogger("finmate.quickadd")

router = APIRouter(prefix="/api/quickadd", tags=["Quick Add"])


class QuickAddIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=280)


class CorrectionIn(BaseModel):
    transaction_id: int
    category: str


@router.post("/")
def quick_add(payload: QuickAddIn, db: Session = Depends(get_db),
              user: models.User = Depends(rate_limit("default"))):
    """
    Parse one line and log it.

    A message with no readable amount is refused rather than guessed at -
    logging a transaction the user did not mean is worse than asking again.
    """
    draft = quickadd_parser.parse(db, user.id, payload.text)
    if not draft:
        return {
            "ok": False,
            "reply": (
                "I couldn't find an amount in that. Try something like "
                "\"300 auto\" or \"spent 1200 on dinner\"."
            ),
        }

    when = datetime.utcnow()
    txn = models.Transaction(
        user_id=user.id,
        date=when,
        amount=draft["amount"],
        category=draft["category"],
        type="income" if draft["amount"] > 0 else "expense",
        merchant=draft["merchant"],
        note=payload.text[:200],
        dedupe_hash=dedupe.next_free_hash(
            db, user.id, when, draft["amount"], draft["merchant"], payload.text[:200]
        ),
    )
    db.add(txn)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That entry already exists.")
    db.refresh(txn)

    cache.invalidate(db, user.id)
    analytics.track(db, user.id, "quickadd_used", {
        "path": draft["path"], "category_source": draft["category_source"],
    })
    analytics.track_once(db, user.id, "data_present", {"via": "quickadd"})

    return {
        "ok": True,
        "reply": quickadd_parser.confirmation(draft["amount"], draft["category"]),
        "transaction": {
            "id": txn.id,
            "amount": txn.amount,
            "category": txn.category,
            "merchant": txn.merchant,
            "date": txn.date,
        },
        # Surfaced so the UI can offer a one-tap correction, and so rule
        # coverage can be measured rather than assumed.
        "parsed_by": draft["path"],
        "category_source": draft["category_source"],
    }


@router.post("/preview")
def preview(payload: QuickAddIn, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    """Parse without saving - lets the UI confirm before writing."""
    draft = quickadd_parser.parse(db, user.id, payload.text)
    if not draft:
        return {"ok": False}
    return {"ok": True, **draft}


@router.post("/correct")
def correct(payload: CorrectionIn, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    """
    Recategorise a transaction and remember it for that merchant.

    This is the correction loop: the same merchant will categorise correctly
    from now on, for this user only.
    """
    if payload.category not in categorizer.CATEGORIES:
        raise HTTPException(status_code=400, detail="Unknown category.")

    txn = (
        db.query(models.Transaction)
        .filter(models.Transaction.id == payload.transaction_id,
                models.Transaction.user_id == user.id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    txn.category = payload.category
    db.commit()

    categorizer.learn(db, user.id, txn.merchant or txn.note or "", payload.category)
    cache.invalidate(db, user.id)
    analytics.track(db, user.id, "category_corrected", {"category": payload.category})

    return {
        "ok": True,
        "reply": f"Got it - I'll file {txn.merchant or 'that'} under {payload.category} from now on.",
        "category": payload.category,
    }


@router.get("/rules")
def rules(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """What this user has taught the categoriser."""
    return [
        {"merchant": r.merchant_key, "category": r.category, "corrections": r.hit_count}
        for r in categorizer.rules_for(db, user.id)
    ]


@router.get("/categories")
def categories():
    return categorizer.CATEGORIES
