from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from .. import schemas, models
from ..database import get_db
from ..services import memory_engine

router = APIRouter(prefix="/api/profile", tags=["Profile"])

DEMO_USER_ID = 1


@router.get("/transactions", response_model=List[schemas.TransactionOut])
def list_transactions(limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == DEMO_USER_ID)
        .order_by(models.Transaction.date.desc())
        .limit(limit)
        .all()
    )


@router.post("/transactions", response_model=schemas.TransactionOut)
def add_transaction(txn: schemas.TransactionCreate, db: Session = Depends(get_db)):
    new_txn = models.Transaction(user_id=DEMO_USER_ID, **txn.model_dump(exclude_none=True))
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)

    # New transactions become episodic memories — this is the Financial Twin
    # "remembering" events as they happen.
    label = "income" if new_txn.amount > 0 else "expense"
    memory_engine.add_memory(
        db, DEMO_USER_ID, "episodic",
        f"Logged a ₹{abs(new_txn.amount):,.0f} {label} in '{new_txn.category}'"
        + (f" at {new_txn.merchant}" if new_txn.merchant else "") + ".",
        importance=0.4,
    )
    return new_txn


@router.get("/assets", response_model=List[schemas.AssetOut])
def list_assets(db: Session = Depends(get_db)):
    return db.query(models.Asset).filter(models.Asset.user_id == DEMO_USER_ID).all()


@router.get("/liabilities", response_model=List[schemas.LiabilityOut])
def list_liabilities(db: Session = Depends(get_db)):
    return db.query(models.Liability).filter(models.Liability.user_id == DEMO_USER_ID).all()


@router.get("/user")
def get_user(db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == DEMO_USER_ID).first()
    if not user:
        return {}
    return {
        "name": user.name,
        "email": user.email,
        "monthly_income": user.monthly_income,
        "risk_profile": user.risk_profile,
    }
