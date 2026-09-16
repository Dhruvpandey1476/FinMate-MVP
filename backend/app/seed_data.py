"""
Seed Data — sample financial data for demos and new-user onboarding.

- `seed()` creates a ready-to-use demo account (demo@finmate.ai / demo1234)
  so anyone (judges, first users) can log in and see a full product instantly.
- `seed_for_user(db, user)` populates any account with the same sample data,
  used by the "Load sample data" button in the app.
"""
import os
import random
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from . import models
from .database import SessionLocal, engine, Base
from .services import memory_engine, dedupe
from . import auth

random.seed(42)
logger = logging.getLogger("finmate.seed")

DEMO_EMAIL = "demo@finmate.ai"
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")

EXPENSE_CATEGORIES = {
    "Food Delivery": (250, 900, 14),
    "Groceries": (800, 2500, 4),
    "Rent": (18000, 18000, 1),
    "Transport": (100, 600, 10),
    "Entertainment": (300, 1500, 5),
    "Shopping": (500, 4000, 4),
    "Utilities": (1200, 2200, 1),
    "Subscriptions": (149, 649, 3),
    "Health": (300, 2000, 2),
}

RECURRING_MERCHANTS = {
    "Subscriptions": ["Netflix", "Spotify", "Amazon Prime"],
    "Rent": ["Landlord - Koramangala Flat"],
    "Utilities": ["BESCOM Electricity"],
}


def _add_txn(db: Session, user_id: int, _seen=None, **kwargs):
    """
    Insert a seeded transaction with a dedupe hash, matching real imports.

    Sample data can randomly produce two identical rows in the same month, so
    occurrence slots are walked exactly as an import would - otherwise seeding
    trips the (user_id, dedupe_hash) unique constraint.
    """
    kwargs.setdefault("note", None)
    kwargs.setdefault("merchant", None)

    seen = _seen if _seen is not None else set()
    for occurrence in range(100):
        h = dedupe.transaction_hash(
            kwargs["date"], kwargs["amount"], kwargs.get("merchant"),
            kwargs.get("note"), occurrence,
        )
        if h not in seen:
            seen.add(h)
            kwargs["dedupe_hash"] = h
            break
    else:
        return

    db.add(models.Transaction(user_id=user_id, **kwargs))


def seed_for_user(db: Session, user: models.User):
    """Populate one user's account with 6 months of sample data."""
    user.monthly_income = 85000
    user.risk_profile = "moderate"
    seen_hashes = set()

    now = datetime.utcnow()
    for month_offset in range(5, -1, -1):
        year = now.year
        month = now.month - month_offset
        while month <= 0:
            month += 12
            year -= 1

        _add_txn(
            db, user.id, seen_hashes, date=datetime(year, month, 1), amount=85000, category="Salary",
            type="income", merchant="Employer Inc.", is_recurring=True, note="Monthly salary",
        )
        if month_offset == 0:
            _add_txn(
                db, user.id, seen_hashes, date=datetime(year, month, 1), amount=4500, category="Freelance",
                type="income", merchant="Side Project", is_recurring=False,
            )

        # The current month is only partly elapsed, so cap generated days at
        # today. Seeding to the 28th regardless produces future-dated spending,
        # which inflates this month's totals and reads as wrong in a demo.
        last_day = min(28, now.day) if month_offset == 0 else 28

        for category, (lo, hi, count) in EXPENSE_CATEGORIES.items():
            is_recurring = category in RECURRING_MERCHANTS
            occurrences = count if not is_recurring else len(RECURRING_MERCHANTS[category])
            for i in range(occurrences):
                day = random.randint(1, last_day)
                amt = round(random.uniform(lo, hi), -1) if lo != hi else lo
                merchant = (
                    RECURRING_MERCHANTS[category][i % len(RECURRING_MERCHANTS[category])]
                    if is_recurring else None
                )
                _add_txn(
                    db, user.id, seen_hashes, date=datetime(year, month, day), amount=-amt,
                    category=category, type="expense", merchant=merchant, is_recurring=is_recurring,
                )

        if month_offset == 0:
            for i in range(6):
                _add_txn(
                    db, user.id, seen_hashes, date=datetime(year, month, min(last_day, 3 + i * 4)),
                    amount=-random.uniform(350, 700), category="Food Delivery",
                    type="expense", merchant="Swiggy/Zomato", is_recurring=False,
                )
            _add_txn(
                db, user.id, seen_hashes, date=datetime(year, month, min(last_day, 18)), amount=-6200,
                category="Shopping", type="expense", merchant="Electronics Store",
            )

    db.add_all([
        models.Goal(user_id=user.id, name="Emergency Fund", goal_type="emergency_fund",
                    target_amount=300000, current_amount=120000, monthly_contribution=10000, priority=1),
        models.Goal(user_id=user.id, name="New Car", goal_type="vehicle",
                    target_amount=800000, current_amount=150000, monthly_contribution=8000, priority=2),
        models.Goal(user_id=user.id, name="Home Down Payment", goal_type="home",
                    target_amount=2000000, current_amount=300000, monthly_contribution=12000, priority=3),
    ])
    db.add_all([
        models.Asset(user_id=user.id, name="Savings Account", asset_type="cash", value=185000),
        models.Asset(user_id=user.id, name="Mutual Funds", asset_type="investment", value=240000),
        models.Asset(user_id=user.id, name="Fixed Deposit", asset_type="cash", value=100000),
    ])
    db.add_all([
        models.Liability(user_id=user.id, name="Personal Loan", liability_type="loan",
                         amount=120000, interest_rate=11.5, monthly_payment=6500),
        models.Liability(user_id=user.id, name="Credit Card", liability_type="credit_card",
                         amount=18000, interest_rate=36.0, monthly_payment=5000),
    ])
    db.commit()

    memory_engine.add_memory(db, user.id, "semantic", "User has a moderate risk profile and prefers a mix of mutual funds and fixed deposits.", 0.8)
    memory_engine.add_memory(db, user.id, "semantic", "User's top financial priority is building a 6-month emergency fund.", 0.9)
    memory_engine.add_memory(db, user.id, "behavioral", "User tends to overspend on food delivery in the second half of the month.", 0.85)
    memory_engine.add_memory(db, user.id, "behavioral", "User pays off credit card balance partially, carrying interest most months.", 0.7)
    memory_engine.add_memory(db, user.id, "episodic", "User mentioned wanting to buy a car within the next 12-18 months.", 0.6)
    memory_engine.add_memory(db, user.id, "semantic", "User lives in Koramangala, Bangalore with ₹18,000/month rent.", 0.7)
    logger.info("Seeded sample data for user %d", user.id)


def _demo_is_stale(db: Session, user: models.User) -> bool:
    """
    Stale means the current month has no data - not that the newest row is some
    number of days old.

    A rolling window gets this wrong at exactly the point it matters: an account
    seeded on 28 August has zero September rows, but on 16 September its newest
    transaction is only 19 days old. Under a 35-day rule it is "fresh" while
    cash flow, savings rate, Safe-to-Spend and the budget comparison all read
    zero, because every one of them is scoped to the current month.
    """
    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    has_current_month = (
        db.query(models.Transaction.id)
        .filter(
            models.Transaction.user_id == user.id,
            models.Transaction.date >= month_start,
        )
        .first()
    )
    return has_current_month is None


def _reset_demo(db: Session, user: models.User) -> None:
    """Clear generated demo rows so seed_for_user can re-anchor them to today."""
    for model in (models.Transaction, models.Goal, models.Asset,
                  models.Liability, models.Memory):
        db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)
    for model in (models.InsightCache, models.Notification, models.BalanceCheckpoint):
        db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)
    db.commit()


def seed():
    """Ensure the demo account exists and is populated (runs on startup)."""
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.email == DEMO_EMAIL).first()
        if existing:
            # Re-anchor rather than skip: a demo seeded two months ago shows an
            # empty dashboard, which is the worst possible first impression.
            if _demo_is_stale(db, existing):
                logger.info("Demo data is stale - regenerating against today's date.")
                _reset_demo(db, existing)
                seed_for_user(db, existing)
                db.commit()
            return

        demo = models.User(
            name="Aarav Mehta", email=DEMO_EMAIL,
            hashed_password=auth.hash_password(DEMO_PASSWORD),
            monthly_income=85000, risk_profile="moderate",
        )
        db.add(demo)
        db.commit()
        db.refresh(demo)
        seed_for_user(db, demo)
        logger.info("Demo account ready: %s / %s", DEMO_EMAIL, DEMO_PASSWORD)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
