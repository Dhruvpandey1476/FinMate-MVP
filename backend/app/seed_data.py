"""
Seed Data — Creates realistic demo user with 6 months of transaction history.
Also seeds Neo4j graph and Qdrant vectors on startup.
"""
import random
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from . import models
from .database import SessionLocal, engine, Base
from .services import memory_engine

random.seed(42)
logger = logging.getLogger("finmate.seed")

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


def seed():
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    if db.query(models.User).first():
        db.close()
        return  # already seeded

    user = models.User(name="Aarav Mehta", email="demo@finmate.ai", monthly_income=85000, risk_profile="moderate")
    db.add(user)
    db.commit()
    db.refresh(user)

    # --- Transactions: 6 months of history ---
    now = datetime.utcnow()
    for month_offset in range(5, -1, -1):
        year = now.year
        month = now.month - month_offset
        while month <= 0:
            month += 12
            year -= 1

        # Income
        salary_date = datetime(year, month, 1)
        db.add(models.Transaction(
            user_id=user.id, date=salary_date, amount=85000, category="Salary",
            type="income", merchant="Employer Inc.", is_recurring=True, note="Monthly salary",
        ))
        if month_offset == 0:
            db.add(models.Transaction(
                user_id=user.id, date=salary_date, amount=4500, category="Freelance",
                type="income", merchant="Side Project", is_recurring=False,
            ))

        # Expenses
        for category, (lo, hi, count) in EXPENSE_CATEGORIES.items():
            is_recurring = category in RECURRING_MERCHANTS
            occurrences = count if not is_recurring else len(RECURRING_MERCHANTS[category])
            for i in range(occurrences):
                day = min(28, random.randint(1, 28))
                amt = round(random.uniform(lo, hi), -1) if lo != hi else lo
                merchant = (
                    RECURRING_MERCHANTS[category][i % len(RECURRING_MERCHANTS[category])]
                    if is_recurring else None
                )
                db.add(models.Transaction(
                    user_id=user.id,
                    date=datetime(year, month, day),
                    amount=-amt,
                    category=category,
                    type="expense",
                    merchant=merchant,
                    is_recurring=is_recurring,
                ))

        # Spending leak in current month for Insights demo
        if month_offset == 0:
            for i in range(6):
                db.add(models.Transaction(
                    user_id=user.id,
                    date=datetime(year, month, min(28, 3 + i * 4)),
                    amount=-random.uniform(350, 700),
                    category="Food Delivery",
                    type="expense",
                    merchant="Swiggy/Zomato",
                    is_recurring=False,
                ))
            db.add(models.Transaction(
                user_id=user.id, date=datetime(year, month, 18), amount=-6200,
                category="Shopping", type="expense", merchant="Electronics Store",
            ))

    db.commit()

    # --- Goals ---
    db.add_all([
        models.Goal(user_id=user.id, name="Emergency Fund", goal_type="emergency_fund",
                    target_amount=300000, current_amount=120000, monthly_contribution=10000, priority=1),
        models.Goal(user_id=user.id, name="New Car", goal_type="vehicle",
                    target_amount=800000, current_amount=150000, monthly_contribution=8000, priority=2),
        models.Goal(user_id=user.id, name="Home Down Payment", goal_type="home",
                    target_amount=2000000, current_amount=300000, monthly_contribution=12000, priority=3),
    ])

    # --- Assets & Liabilities ---
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

    # --- Starter memories ---
    memory_engine.add_memory(db, user.id, "semantic", "User has a moderate risk profile and prefers a mix of mutual funds and fixed deposits.", 0.8)
    memory_engine.add_memory(db, user.id, "semantic", "User's top financial priority is building a 6-month emergency fund.", 0.9)
    memory_engine.add_memory(db, user.id, "behavioral", "User tends to overspend on food delivery in the second half of the month.", 0.85)
    memory_engine.add_memory(db, user.id, "behavioral", "User pays off credit card balance partially, carrying interest most months.", 0.7)
    memory_engine.add_memory(db, user.id, "episodic", "User mentioned wanting to buy a car within the next 12-18 months.", 0.6)
    memory_engine.add_memory(db, user.id, "episodic", "User started a freelance side project bringing in extra monthly income.", 0.5)
    memory_engine.add_memory(db, user.id, "semantic", "User lives in Koramangala, Bangalore with ₹18,000/month rent.", 0.7)
    memory_engine.add_memory(db, user.id, "behavioral", "User's entertainment spending spikes on weekends, especially on movie subscriptions.", 0.6)

    db.close()
    logger.info("Seed complete: demo user 'Aarav Mehta' created with 6 months of transactions.")


if __name__ == "__main__":
    seed()
