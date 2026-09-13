"""
Transaction de-duplication.

Users re-upload statements: overlapping date ranges, a corrected export, or
simply forgetting they already imported March. Without a stable identity per
row, every re-upload silently doubles their spending and corrupts the twin.

The hash covers the fields a bank would never change between exports of the
same transaction: value date, exact amount, and a normalised description. It
deliberately excludes category and is_recurring, which our own classifier may
assign differently on a later run.
"""
import re
import hashlib
from datetime import datetime, date

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models

# Reference numbers, UPI ids and dates inside descriptions vary between exports
# of the same row, so they are stripped before hashing.
_NOISE_PATTERNS = [
    r"\b\d{2}[/-]\d{2}[/-]\d{2,4}\b",   # embedded dates
    r"\b[a-z0-9._-]+@[a-z]{2,}\b",       # UPI VPAs
    r"\bref\s*[:.# ]?\s*\w+\b",
    r"\btxn\s*[:.# ]?\s*\w+\b",
    r"\butr\s*[:.# ]?\s*\w+\b",
    r"\b\d{9,}\b",                        # long reference numbers
]
_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)


def normalize_description(*parts) -> str:
    """Collapse merchant/note into a stable, comparable key."""
    text = " ".join(str(p) for p in parts if p)
    text = text.lower()
    text = _NOISE_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:120]


def _coerce_date(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except ValueError:
            return value[:10]
    return ""


def transaction_hash(txn_date, amount, merchant=None, note=None, occurrence: int = 0) -> str:
    """
    Stable identity for one transaction, independent of our own labelling.

    `occurrence` distinguishes genuinely repeated rows: two identical Rs 200
    coffees on the same day at the same shop are two real transactions, not a
    duplicate. The index is assigned by position within the statement, so
    re-importing the same file regenerates exactly the same set of hashes and
    still dedupes correctly.
    """
    key = "|".join([
        _coerce_date(txn_date),
        f"{round(float(amount or 0), 2):.2f}",
        normalize_description(merchant, note),
        str(int(occurrence or 0)),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def hash_for_model(txn: "models.Transaction", occurrence: int = 0) -> str:
    return transaction_hash(txn.date, txn.amount, txn.merchant, txn.note, occurrence)


def existing_hashes(db: Session, user_id: int) -> set:
    rows = (
        db.query(models.Transaction.dedupe_hash)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.dedupe_hash.isnot(None),
        )
        .all()
    )
    return {r[0] for r in rows if r[0]}


def partition_new(db: Session, user_id: int, parsed: list) -> tuple:
    """
    Split parsed rows into (new, duplicates).

    Each row gets an occurrence index counted within this batch, so N identical
    rows in one statement produce N distinct hashes. A row is a duplicate only
    if that exact (content, occurrence) pair is already stored - which is what
    makes re-importing an overlapping statement a no-op while still allowing a
    genuinely repeated charge through.
    """
    existing = existing_hashes(db, user_id)
    batch_counts = {}
    new_rows, duplicates = [], []

    for txn in parsed:
        base = (
            _coerce_date(txn.get("date")),
            round(float(txn.get("amount") or 0), 2),
            normalize_description(txn.get("merchant"), txn.get("note")),
        )
        occurrence = batch_counts.get(base, 0)
        batch_counts[base] = occurrence + 1

        h = transaction_hash(
            txn.get("date"), txn.get("amount"), txn.get("merchant"),
            txn.get("note"), occurrence,
        )
        if h in existing:
            duplicates.append(txn)
            continue

        txn = dict(txn)
        txn["dedupe_hash"] = h
        new_rows.append(txn)

    return new_rows, duplicates


def next_free_hash(db: Session, user_id: int, txn_date, amount,
                   merchant=None, note=None, max_occurrences: int = 100):
    """
    Find the first unused occurrence slot for a single transaction.

    Used when a user deliberately logs a repeat of something they already have
    (two identical coffees). Returns None once the slot limit is hit, which the
    caller surfaces as a conflict rather than looping.
    """
    existing = existing_hashes(db, user_id)
    for occurrence in range(max_occurrences):
        h = transaction_hash(txn_date, amount, merchant, note, occurrence)
        if h not in existing:
            return h
    return None


def backfill_hashes(db: Session, batch_size: int = 500) -> int:
    """
    Populate dedupe_hash for rows imported before dedup existed.

    Runs at startup. Rows that would collide with an already-hashed row are left
    null rather than deleted - silently removing a user's data to satisfy a new
    constraint would be worse than the duplicate.
    """
    pending = (
        db.query(models.Transaction)
        .filter(models.Transaction.dedupe_hash.is_(None))
        .limit(batch_size)
        .all()
    )
    if not pending:
        return 0

    # Seed per-user seen-sets from what is already hashed.
    seen_by_user = {}
    updated = 0
    for txn in pending:
        seen = seen_by_user.get(txn.user_id)
        if seen is None:
            seen = existing_hashes(db, txn.user_id)
            seen_by_user[txn.user_id] = seen

        # Walk occurrence slots so legitimately repeated historical rows each
        # get their own identity instead of one of them staying unhashed.
        assigned = None
        for occurrence in range(100):
            h = hash_for_model(txn, occurrence)
            if h not in seen:
                assigned = h
                break
        if assigned is None:
            continue  # leave null; a later manual merge can resolve it

        txn.dedupe_hash = assigned
        seen.add(assigned)
        updated += 1

    db.commit()
    return updated


def duplicate_report(db: Session, user_id: int) -> dict:
    """Surface pre-existing duplicates so a user can clean up historical imports."""
    rows = (
        db.query(
            models.Transaction.dedupe_hash,
            func.count(models.Transaction.id).label("n"),
        )
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.dedupe_hash.isnot(None),
        )
        .group_by(models.Transaction.dedupe_hash)
        .having(func.count(models.Transaction.id) > 1)
        .all()
    )
    return {"duplicate_groups": len(rows), "extra_rows": sum(int(r[1]) - 1 for r in rows)}
