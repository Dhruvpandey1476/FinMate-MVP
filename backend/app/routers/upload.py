"""
Upload Router - CSV/PDF bank statement import.

Imports are de-duplicated (services/dedupe.py). Re-uploading an overlapping
statement is normal user behaviour, and without this it silently doubles their
spending and corrupts every downstream number.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import get_current_user, require_quota
from ..services import parser_service, memory_engine, dedupe, cache, analytics, entitlements
from ..services.wealth_graph import sync_graph

logger = logging.getLogger("finmate.upload")

router = APIRouter(prefix="/api/upload", tags=["Upload"])

MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024


def _finish_import(db: Session, user, parsed: list, filename: str, source: str) -> dict:
    """Shared post-parse path: dedupe, insert, invalidate caches, report."""
    new_rows, duplicates = dedupe.partition_new(db, user.id, parsed)
    inserted = _insert_transactions(db, user.id, new_rows)

    # Derived output is now stale.
    cache.invalidate(db, user.id)

    try:
        sync_graph(db, user.id)
    except Exception as e:
        logger.warning("Graph sync failed after upload: %s", e)

    entitlements.record_usage(db, user.id, "upload", source, "", 0, 0, 0, True)
    analytics.track(db, user.id, "upload_success", {
        "source": source, "parsed": len(parsed), "inserted": inserted, "duplicates": len(duplicates),
    })
    if inserted:
        analytics.track_once(db, user.id, "data_present", {"via": source})

    if inserted == 0 and duplicates:
        message = (
            f"No new transactions - all {len(duplicates)} rows in '{filename}' "
            f"were already imported."
        )
    else:
        message = f"Imported {inserted} transactions from '{filename}'"
        if duplicates:
            message += f" ({len(duplicates)} duplicates skipped)"

    return {
        "message": message,
        "total_parsed": len(parsed),
        "total_inserted": inserted,
        "duplicates_skipped": len(duplicates),
        "transactions": new_rows[:20],
    }


@router.post("/csv")
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_quota("upload")),
):
    """Upload and parse a bank statement CSV file."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = await file.read()
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    try:
        parsed = parser_service.parse_csv(content, file.filename)
    except ValueError as e:
        analytics.track(db, user.id, "upload_failed", {"source": "csv", "reason": str(e)[:120]})
        raise HTTPException(status_code=400, detail=str(e))

    return _finish_import(db, user, parsed, file.filename, "csv")


@router.post("/pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_quota("upload")),
):
    """Upload and parse a bank statement PDF file."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a .pdf file")

    content = await file.read()
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")

    try:
        parsed = parser_service.parse_pdf(content, file.filename)
    except ValueError as e:
        analytics.track(db, user.id, "upload_failed", {"source": "pdf", "reason": str(e)[:120]})
        raise HTTPException(status_code=400, detail=str(e))

    return _finish_import(db, user, parsed, file.filename, "pdf")


@router.post("/manual")
def add_manual_transaction(
    txn: dict,
    allow_duplicate: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Add a single manual transaction. See /api/profile/transactions for the
    typed equivalent; this endpoint accepts the looser legacy payload."""
    try:
        amount = float(txn["amount"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="A numeric 'amount' is required.")
    if amount == 0:
        raise HTTPException(status_code=400, detail="Amount cannot be zero.")

    raw_date = txn.get("date")
    try:
        when = datetime.fromisoformat(raw_date) if raw_date else datetime.utcnow()
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Date must be ISO format (YYYY-MM-DD).")

    merchant = txn.get("merchant")
    note = txn.get("note")

    if allow_duplicate:
        dedupe_hash = dedupe.next_free_hash(db, user.id, when, amount, merchant, note)
        if dedupe_hash is None:
            raise HTTPException(
                status_code=409, detail="Too many identical transactions on that date."
            )
    else:
        dedupe_hash = dedupe.transaction_hash(when, amount, merchant, note)

    new_txn = models.Transaction(
        user_id=user.id,
        date=when,
        amount=amount,
        category=txn.get("category", "Other"),
        type="income" if amount > 0 else "expense",
        merchant=merchant,
        is_recurring=bool(txn.get("is_recurring", False)),
        note=note,
        dedupe_hash=dedupe_hash,
    )
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

    return {"message": "Transaction added", "transaction_id": new_txn.id}


@router.get("/duplicates")
def duplicates(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Report duplicate rows left over from imports made before dedup existed."""
    return dedupe.duplicate_report(db, user.id)


def _insert_transactions(db: Session, user_id: int, transactions: list) -> int:
    """
    Bulk insert parsed transactions.

    Rows are pre-deduped, but the unique constraint is still the authority - a
    concurrent import of the same file must not slip through, so an
    IntegrityError falls back to per-row inserts and skips the collisions.
    """
    if not transactions:
        return 0

    objects = []
    for txn in transactions:
        try:
            when = txn["date"]
            if isinstance(when, str):
                when = datetime.fromisoformat(when)
            objects.append(models.Transaction(
                user_id=user_id,
                date=when,
                amount=float(txn["amount"]),
                category=txn.get("category", "Other"),
                type=txn.get("type", "expense"),
                merchant=txn.get("merchant"),
                is_recurring=bool(txn.get("is_recurring", False)),
                note=txn.get("note"),
                dedupe_hash=txn.get("dedupe_hash") or dedupe.transaction_hash(
                    txn.get("date"), txn.get("amount"), txn.get("merchant"), txn.get("note")
                ),
            ))
        except Exception as e:
            logger.debug("Skipping unparseable transaction: %s", e)
            continue

    if not objects:
        return 0

    try:
        db.add_all(objects)
        db.commit()
        count = len(objects)
    except IntegrityError:
        db.rollback()
        count = 0
        for obj in objects:
            try:
                db.add(obj)
                db.commit()
                count += 1
            except IntegrityError:
                db.rollback()
                continue

    if count > 0:
        total_income = sum(t["amount"] for t in transactions if t.get("amount", 0) > 0)
        total_expense = sum(-t["amount"] for t in transactions if t.get("amount", 0) < 0)
        memory_engine.add_memory(
            db, user_id, "episodic",
            f"Imported {count} transactions from a bank statement. "
            f"Total income: Rs {total_income:,.0f}, total expenses: Rs {total_expense:,.0f}.",
            importance=0.6, source="import",
        )
        try:
            memory_engine.detect_behavioral_patterns(db, user_id)
        except Exception as e:
            logger.warning("Behavioral pattern detection failed: %s", e)

    return count
