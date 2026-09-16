from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..services import memory_engine, cache, dedupe, analytics, entitlements
from .. import seed_data

router = APIRouter(prefix="/api/profile", tags=["Profile"])


# --- Transactions ----------------------------------------------------------

@router.get("/transactions", response_model=List[schemas.TransactionOut])
def list_transactions(limit: int = 50, offset: int = 0, category: str = None,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    limit = max(1, min(int(limit or 50), 500))
    q = db.query(models.Transaction).filter(models.Transaction.user_id == user.id)
    if category:
        q = q.filter(models.Transaction.category == category)
    return (
        q.order_by(models.Transaction.date.desc())
        .offset(max(0, offset))
        .limit(limit)
        .all()
    )


@router.get("/transactions/count")
def count_transactions(db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)):
    total = db.query(func.count(models.Transaction.id)).filter(
        models.Transaction.user_id == user.id
    ).scalar()
    return {"total": int(total or 0)}


@router.post("/transactions", response_model=schemas.TransactionOut)
def add_transaction(txn: schemas.TransactionCreate, allow_duplicate: bool = False,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    """
    Log a transaction by hand.

    An identical entry is rejected by default, which catches the double-submit.
    Two identical coffees on the same day are a real thing though, so
    `allow_duplicate=true` claims the next occurrence slot instead.
    """
    if txn.amount == 0:
        raise HTTPException(status_code=400, detail="Amount cannot be zero.")

    data = txn.model_dump(exclude_none=True)
    when = data.get("date") or datetime.utcnow()
    data["date"] = when

    if allow_duplicate:
        dedupe_hash = dedupe.next_free_hash(db, user.id, when, txn.amount,
                                            txn.merchant, txn.note)
        if dedupe_hash is None:
            raise HTTPException(
                status_code=409,
                detail="Too many identical transactions on that date.",
            )
    else:
        dedupe_hash = dedupe.transaction_hash(when, txn.amount, txn.merchant, txn.note)

    new_txn = models.Transaction(user_id=user.id, dedupe_hash=dedupe_hash, **data)
    db.add(new_txn)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "An identical transaction on that date already exists. "
                "Send allow_duplicate=true if this is a genuine repeat."
            ),
        )
    db.refresh(new_txn)

    cache.invalidate(db, user.id)
    analytics.track_once(db, user.id, "data_present", {"via": "manual"})

    label = "income" if new_txn.amount > 0 else "expense"
    memory_engine.add_memory(
        db, user.id, "episodic",
        f"Logged a Rs {abs(new_txn.amount):,.0f} {label} in '{new_txn.category}'"
        + (f" at {new_txn.merchant}" if new_txn.merchant else "") + ".",
        importance=0.4, source="user",
    )
    return new_txn


@router.delete("/transactions/{txn_id}")
def delete_transaction(txn_id: int, db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)):
    txn = (
        db.query(models.Transaction)
        .filter(models.Transaction.id == txn_id, models.Transaction.user_id == user.id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(txn)
    db.commit()
    cache.invalidate(db, user.id)
    return {"ok": True}


# --- Assets ----------------------------------------------------------------

@router.get("/assets", response_model=List[schemas.AssetOut])
def list_assets(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Asset).filter(models.Asset.user_id == user.id).all()


@router.post("/assets", response_model=schemas.AssetOut)
def add_asset(payload: schemas.AssetCreate, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)):
    """Net worth is only real if users can record what they own."""
    asset = models.Asset(user_id=user.id, **payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    cache.invalidate(db, user.id)
    return asset


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    asset = (
        db.query(models.Asset)
        .filter(models.Asset.id == asset_id, models.Asset.user_id == user.id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    db.delete(asset)
    db.commit()
    cache.invalidate(db, user.id)
    return {"ok": True}


# --- Liabilities -----------------------------------------------------------

@router.get("/liabilities", response_model=List[schemas.LiabilityOut])
def list_liabilities(db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    return db.query(models.Liability).filter(models.Liability.user_id == user.id).all()


@router.post("/liabilities", response_model=schemas.LiabilityOut)
def add_liability(payload: schemas.LiabilityCreate, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    """Feeds the debt optimiser - interest rate and EMI are what make it work."""
    if payload.interest_rate < 0 or payload.amount < 0:
        raise HTTPException(status_code=400, detail="Amounts cannot be negative.")
    liability = models.Liability(user_id=user.id, **payload.model_dump())
    db.add(liability)
    db.commit()
    db.refresh(liability)
    cache.invalidate(db, user.id)
    return liability


@router.delete("/liabilities/{liability_id}")
def delete_liability(liability_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    liability = (
        db.query(models.Liability)
        .filter(models.Liability.id == liability_id, models.Liability.user_id == user.id)
        .first()
    )
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found")
    db.delete(liability)
    db.commit()
    cache.invalidate(db, user.id)
    return {"ok": True}


# --- User ------------------------------------------------------------------

@router.get("/user")
def get_user(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return {
        "name": user.name,
        "email": user.email,
        "monthly_income": user.monthly_income,
        "risk_profile": user.risk_profile,
        "plan": user.plan or "free",
        "entitlements": entitlements.quota_summary(db, user),
    }


@router.patch("/user")
def update_user(payload: dict, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    if "name" in payload and payload["name"]:
        user.name = str(payload["name"]).strip()[:120]
    if "monthly_income" in payload:
        try:
            user.monthly_income = max(0.0, float(payload["monthly_income"]))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="monthly_income must be a number.")
    if payload.get("risk_profile") in ("conservative", "moderate", "aggressive"):
        user.risk_profile = payload["risk_profile"]
    db.commit()
    db.refresh(user)
    return {"ok": True, "name": user.name, "monthly_income": user.monthly_income,
            "risk_profile": user.risk_profile}


@router.post("/onboard")
def onboard(payload: dict, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    """Lightweight, no-upload onboarding: capture income, top expenses, and a
    goal, then populate the Financial Twin + memory so the AI CFO is useful
    immediately for users who won't upload a bank statement."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _add_txn(**kwargs):
        kwargs["dedupe_hash"] = dedupe.transaction_hash(
            kwargs["date"], kwargs["amount"], kwargs.get("merchant"), kwargs.get("note")
        )
        db.add(models.Transaction(user_id=user.id, **kwargs))

    try:
        income = float(payload.get("monthly_income") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="monthly_income must be a number.")

    if income > 0:
        user.monthly_income = income
        _add_txn(date=month_start, amount=income, category="Salary", type="income",
                 merchant="Income", is_recurring=True, note="Monthly income")
        memory_engine.add_memory(db, user.id, "semantic",
                                 f"User earns about Rs {income:,.0f} per month.", 0.85,
                                 source="user")

    labeled = []
    for e in (payload.get("expenses") or []):
        cat = (e.get("category") or "Other").strip() or "Other"
        try:
            amt = float(e.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amt > 0:
            _add_txn(date=now, amount=-amt, category=cat, type="expense",
                     merchant=cat, is_recurring=True, note=f"Monthly {cat}")
            labeled.append(f"{cat} Rs {amt:,.0f}")
    if labeled:
        memory_engine.add_memory(db, user.id, "behavioral",
                                 "User's main monthly expenses: " + ", ".join(labeled) + ".",
                                 0.75, source="user")

    goal = payload.get("goal") or {}
    gname = (goal.get("name") or "").strip()
    try:
        gtarget = float(goal.get("target_amount") or 0)
    except (TypeError, ValueError):
        gtarget = 0
    if gname and gtarget > 0:
        db.add(models.Goal(
            user_id=user.id, name=gname, goal_type=goal.get("goal_type", "custom"),
            target_amount=gtarget, current_amount=float(goal.get("current_amount") or 0),
            monthly_contribution=float(goal.get("monthly_contribution") or 0), priority=1,
        ))
        memory_engine.add_memory(db, user.id, "episodic",
                                 f"User's goal: {gname} (target Rs {gtarget:,.0f}).", 0.8,
                                 source="user")

    note = (payload.get("note") or "").strip()
    if note:
        memory_engine.add_memory(db, user.id, "semantic", note[:2000], 0.7, source="user")

    db.commit()
    cache.invalidate(db, user.id)

    analytics.track(db, user.id, "onboard_complete", {
        "has_income": income > 0, "expense_count": len(labeled), "has_goal": bool(gname),
    })
    if income > 0 or labeled:
        analytics.track_once(db, user.id, "data_present", {"via": "onboarding"})

    return {"ok": True}


@router.post("/load-sample")
def load_sample(reset: bool = False, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """
    Populate the current account with sample data so new users can explore.

    Sample data is anchored to the month it is generated in, so an account
    seeded weeks ago has an empty current month - every month-based figure
    (cash flow, savings rate, Safe-to-Spend, the budget comparison) then reads
    zero. `reset=true` clears this account's generated rows and regenerates
    them against today, which is also what makes a demo repeatable.

    Destructive, and deliberately explicit: it only ever touches the
    authenticated user's own rows, and only when the flag is passed.
    """
    has_data = db.query(models.Transaction).filter(
        models.Transaction.user_id == user.id
    ).first()

    if has_data and not reset:
        return {
            "message": "Account already has data. Pass reset=true to replace it "
                       "with fresh sample data anchored to today.",
            "loaded": False,
        }

    cleared = 0
    if reset:
        for model in (models.Transaction, models.Goal, models.Asset,
                      models.Liability, models.Memory):
            cleared += db.query(model).filter(
                model.user_id == user.id
            ).delete(synchronize_session=False)
        for model in (models.InsightCache, models.Notification,
                      models.BalanceCheckpoint):
            db.query(model).filter(model.user_id == user.id).delete(
                synchronize_session=False
            )
        db.commit()

    seed_data.seed_for_user(db, user)
    db.commit()
    cache.invalidate(db, user.id)
    analytics.track_once(db, user.id, "data_present", {"via": "sample"})
    return {
        "message": (
            f"Replaced {cleared} rows with fresh sample data anchored to today."
            if reset else "Sample financial data loaded."
        ),
        "loaded": True,
        "reset": reset,
    }


@router.delete("/account")
def delete_account(db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    """
    Full account deletion.

    Required under India's DPDP Act, and a hard prerequisite for asking anyone
    to connect a bank account. Cascades cover the child rows; the tables added
    later are cleared explicitly.
    """
    from ..services.memory_engine import COLLECTION_NAME
    from ..database import get_qdrant

    qdrant = get_qdrant()
    if qdrant:
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            qdrant.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user.id))
                ]),
            )
        except Exception:
            pass

    for model in (models.Notification, models.InsightCache,
                  models.UsageEvent, models.AnalyticsEvent, models.ChatMessage):
        db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
    return {"ok": True, "message": "Account and all associated data deleted."}
