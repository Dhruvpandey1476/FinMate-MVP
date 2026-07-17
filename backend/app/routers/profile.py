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


@router.post("/load-sample")
def load_sample(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Populate the current account with sample data so new users can explore the product."""
    has_data = db.query(models.Transaction).filter(models.Transaction.user_id == user.id).first()
    if has_data:
        return {"message": "Account already has data.", "loaded": False}
    seed_data.seed_for_user(db, user)
    return {"message": "Sample financial data loaded.", "loaded": True}
