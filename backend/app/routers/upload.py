"""
Upload Router — CSV/PDF bank statement import endpoints.
"""
import logging
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..services import parser_service, memory_engine
from ..services.wealth_graph import sync_graph

logger = logging.getLogger("finmate.upload")

router = APIRouter(prefix="/api/upload", tags=["Upload"])


@router.post("/csv")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    """Upload and parse a bank statement CSV file."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    try:
        parsed = parser_service.parse_csv(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Insert transactions into database
    inserted = _insert_transactions(db, user.id, parsed)

    # Re-sync wealth graph
    try:
        sync_graph(db, user.id)
    except Exception as e:
        logger.warning("Graph sync failed after upload: %s", e)

    return {
        "message": f"Successfully imported {inserted} transactions from '{file.filename}'",
        "total_parsed": len(parsed),
        "total_inserted": inserted,
        "transactions": parsed[:20],  # Preview first 20
    }


@router.post("/pdf")
async def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    """Upload and parse a bank statement PDF file."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a .pdf file")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:  # 20MB limit
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")

    try:
        parsed = parser_service.parse_pdf(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    inserted = _insert_transactions(db, user.id, parsed)

    try:
        sync_graph(db, user.id)
    except Exception as e:
        logger.warning("Graph sync failed after upload: %s", e)

    return {
        "message": f"Successfully imported {inserted} transactions from '{file.filename}'",
        "total_parsed": len(parsed),
        "total_inserted": inserted,
        "transactions": parsed[:20],
    }


@router.post("/manual")
def add_manual_transaction(txn: dict, db: Session = Depends(get_db),
                           user: models.User = Depends(get_current_user)):
    """Add a single manual transaction."""
    new_txn = models.Transaction(
        user_id=user.id,
        date=datetime.fromisoformat(txn.get("date", datetime.utcnow().isoformat())),
        amount=txn["amount"],
        category=txn.get("category", "Other"),
        type="income" if txn["amount"] > 0 else "expense",
        merchant=txn.get("merchant"),
        is_recurring=txn.get("is_recurring", False),
        note=txn.get("note"),
    )
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)
    
    # Create episodic memory
    label = "income" if new_txn.amount > 0 else "expense"
    memory_engine.add_memory(
        db, user.id, "episodic",
        f"Logged a ₹{abs(new_txn.amount):,.0f} {label} in '{new_txn.category}'"
        + (f" at {new_txn.merchant}" if new_txn.merchant else "") + ".",
        importance=0.4,
    )
    
    return {"message": "Transaction added", "transaction_id": new_txn.id}


def _insert_transactions(db: Session, user_id: int, transactions: list[dict]) -> int:
    """Bulk insert parsed transactions into database."""
    count = 0
    for txn in transactions:
        try:
            new_txn = models.Transaction(
                user_id=user_id,
                date=datetime.fromisoformat(txn["date"]) if isinstance(txn["date"], str) else txn["date"],
                amount=txn["amount"],
                category=txn.get("category", "Other"),
                type=txn.get("type", "expense"),
                merchant=txn.get("merchant"),
                is_recurring=txn.get("is_recurring", False),
                note=txn.get("note"),
            )
            db.add(new_txn)
            count += 1
        except Exception as e:
            logger.debug("Skipping transaction: %s", e)
            continue
    
    db.commit()
    
    # Create a single episodic memory for the upload
    if count > 0:
        total_income = sum(t["amount"] for t in transactions if t["amount"] > 0)
        total_expense = sum(-t["amount"] for t in transactions if t["amount"] < 0)
        memory_engine.add_memory(
            db, user_id, "episodic",
            f"Imported {count} transactions from bank statement. "
            f"Total income: ₹{total_income:,.0f}, total expenses: ₹{total_expense:,.0f}.",
            importance=0.6,
        )
        # Derive behavioral memories from the new data.
        try:
            memory_engine.detect_behavioral_patterns(db, user_id)
        except Exception as e:
            logger.warning("Behavioral pattern detection failed: %s", e)

    return count
