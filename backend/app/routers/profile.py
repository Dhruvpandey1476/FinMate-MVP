from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..services import memory_engine
from .. import seed_data

router = APIRouter(prefix="/api/profile", tags=["Profile"])


@router.get("/transactions", response_model=List[schemas.TransactionOut])
def list_transactions(limit: int = 50, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)):
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == user.id)
        .order_by(models.Transaction.date.desc())
        .limit(limit)
        .all()
    )


@router.post("/transactions", response_model=schemas.TransactionOut)
def add_transaction(txn: schemas.TransactionCreate, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    new_txn = models.Transaction(user_id=user.id, **txn.model_dump(exclude_none=True))
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)

    label = "income" if new_txn.amount > 0 else "expense"
    memory_engine.add_memory(
        db, user.id, "episodic",
        f"Logged a ₹{abs(new_txn.amount):,.0f} {label} in '{new_txn.category}'"
        + (f" at {new_txn.merchant}" if new_txn.merchant else "") + ".",
        importance=0.4,
    )
    return new_txn


@router.get("/assets", response_model=List[schemas.AssetOut])
def list_assets(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Asset).filter(models.Asset.user_id == user.id).all()


@router.get("/liabilities", response_model=List[schemas.LiabilityOut])
def list_liabilities(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Liability).filter(models.Liability.user_id == user.id).all()


@router.get("/user")
def get_user(user: models.User = Depends(get_current_user)):
    return {
        "name": user.name,
        "email": user.email,
        "monthly_income": user.monthly_income,
        "risk_profile": user.risk_profile,
    }


@router.post("/onboard")
def onboard(payload: dict, db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)):
    """Lightweight, no-upload onboarding: capture income, top expenses, and a
    goal, then populate the Financial Twin + memory so the AI CFO is useful
    immediately for users who won't upload a bank statement."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    income = float(payload.get("monthly_income") or 0)
    if income > 0:
        user.monthly_income = income
        db.add(models.Transaction(
            user_id=user.id, date=month_start, amount=income, category="Salary",
            type="income", merchant="Income", is_recurring=True, note="Monthly income",
        ))
        memory_engine.add_memory(db, user.id, "semantic",
                                 f"User earns about ₹{income:,.0f} per month.", 0.85)

    expenses = payload.get("expenses") or []
    labeled = []
    for e in expenses:
        cat = (e.get("category") or "Other").strip() or "Other"
        amt = float(e.get("amount") or 0)
        if amt > 0:
            db.add(models.Transaction(
                user_id=user.id, date=now, amount=-amt, category=cat,
                type="expense", merchant=cat, is_recurring=True, note=f"Monthly {cat}",
            ))
            labeled.append(f"{cat} ₹{amt:,.0f}")
    if labeled:
        memory_engine.add_memory(db, user.id, "behavioral",
                                 "User's main monthly expenses: " + ", ".join(labeled) + ".", 0.75)

    goal = payload.get("goal") or {}
    gname = (goal.get("name") or "").strip()
    gtarget = float(goal.get("target_amount") or 0)
    if gname and gtarget > 0:
        db.add(models.Goal(
            user_id=user.id, name=gname, goal_type=goal.get("goal_type", "custom"),
            target_amount=gtarget, current_amount=float(goal.get("current_amount") or 0),
            monthly_contribution=float(goal.get("monthly_contribution") or 0), priority=1,
        ))
        memory_engine.add_memory(db, user.id, "episodic",
                                 f"User's goal: {gname} (target ₹{gtarget:,.0f}).", 0.8)

    note = (payload.get("note") or "").strip()
    if note:
        memory_engine.add_memory(db, user.id, "semantic", note, 0.7)

    db.commit()
    return {"ok": True}


@router.post("/load-sample")
def load_sample(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Populate the current account with sample data so new users can explore the product."""
    has_data = db.query(models.Transaction).filter(models.Transaction.user_id == user.id).first()
    if has_data:
        return {"message": "Account already has data.", "loaded": False}
    seed_data.seed_for_user(db, user)
    return {"message": "Sample financial data loaded.", "loaded": True}
