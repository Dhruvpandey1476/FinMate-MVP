"""
Financial Twin snapshot maths.

These numbers drive net worth, the health score and every downstream agent, so
a sign error here corrupts everything silently.
"""
from datetime import datetime, timedelta

import pytest

from app import models
from app.services import financial_twin


def _txn(user_id, amount, category="Other", days_ago=0, **kw):
    return models.Transaction(
        user_id=user_id,
        date=datetime.utcnow() - timedelta(days=days_ago),
        amount=amount,
        category=category,
        type="income" if amount > 0 else "expense",
        **kw,
    )


def test_snapshot_on_empty_account(db, user):
    snap = financial_twin.get_snapshot(db, user.id)
    assert snap["net_worth"] == 0
    assert snap["total_income_month"] == 0
    assert snap["savings_rate"] == 0  # must not divide by zero
    assert snap["top_expense_categories"] == []


def test_income_expense_and_savings_rate(db, user):
    db.add_all([
        _txn(user.id, 100000, "Salary"),
        _txn(user.id, -30000, "Rent", days_ago=1),
        _txn(user.id, -10000, "Food", days_ago=2),
    ])
    db.commit()

    snap = financial_twin.get_snapshot(db, user.id)
    assert snap["total_income_month"] == 100000
    assert snap["total_expense_month"] == 40000
    assert snap["cash_flow"] == 60000
    assert snap["savings_rate"] == 60.0


def test_only_current_month_counts(db, user):
    """A transaction from two months ago must not inflate this month's income."""
    old = datetime.utcnow().replace(day=1) - timedelta(days=45)
    db.add_all([
        _txn(user.id, 50000, "Salary"),
        models.Transaction(user_id=user.id, date=old, amount=999999,
                           category="Salary", type="income"),
    ])
    db.commit()

    snap = financial_twin.get_snapshot(db, user.id)
    assert snap["total_income_month"] == 50000


def test_net_worth_is_assets_minus_liabilities(db, user):
    db.add_all([
        models.Asset(user_id=user.id, name="Savings", asset_type="cash", value=500000),
        models.Asset(user_id=user.id, name="MF", asset_type="investment", value=200000),
        models.Liability(user_id=user.id, name="Car Loan", amount=300000),
    ])
    db.commit()

    snap = financial_twin.get_snapshot(db, user.id)
    assert snap["total_assets"] == 700000
    assert snap["total_liabilities"] == 300000
    assert snap["net_worth"] == 400000


def test_top_categories_ranked_and_capped(db, user):
    for i, (cat, amt) in enumerate(
        [("Rent", 30000), ("Food", 12000), ("Transport", 5000),
         ("Shopping", 8000), ("Health", 2000), ("Misc", 1000)]
    ):
        db.add(_txn(user.id, -amt, cat, days_ago=i))
    db.commit()

    cats = financial_twin.get_snapshot(db, user.id)["top_expense_categories"]
    assert len(cats) == 5  # capped
    assert cats[0]["category"] == "Rent"
    assert [c["amount"] for c in cats] == sorted(
        [c["amount"] for c in cats], reverse=True
    )


def test_user_data_is_isolated(db, user):
    """A second user's transactions must never leak into this snapshot."""
    other = models.User(name="Other", email="other-iso@finmate.test")
    db.add(other)
    db.commit()
    db.refresh(other)

    db.add_all([_txn(user.id, 10000, "Salary"), _txn(other.id, 999999, "Salary")])
    db.commit()

    assert financial_twin.get_snapshot(db, user.id)["total_income_month"] == 10000


class TestHealthScore:
    def test_score_is_bounded(self):
        awful = financial_twin.health_score_breakdown(-500, -1_000_000, 10_000_000, 1000)
        great = financial_twin.health_score_breakdown(500, 10_000_000, 0, 100000)
        assert 0 <= awful["score"] <= 100
        assert 0 <= great["score"] <= 100

    def test_higher_savings_rate_scores_higher(self):
        low = financial_twin.health_score_breakdown(5, 100000, 0, 100000)["score"]
        high = financial_twin.health_score_breakdown(30, 100000, 0, 100000)["score"]
        assert high > low

    def test_debt_reduces_score(self):
        no_debt = financial_twin.health_score_breakdown(20, 100000, 0, 100000)["score"]
        debt = financial_twin.health_score_breakdown(20, 100000, 5_000_000, 100000)["score"]
        assert debt < no_debt

    def test_breakdown_explains_the_score(self):
        """The hero number ships with its own audit trail."""
        result = financial_twin.health_score_breakdown(25, 500000, 100000, 100000)
        labels = {c["label"] for c in result["components"]}
        assert {"Baseline", "Savings rate", "Debt burden", "Positive net worth"} <= labels
        total = sum(c["points"] for c in result["components"])
        assert abs(total - result["score"]) < 1.0  # components sum to the score

    def test_zero_income_does_not_crash(self):
        result = financial_twin.health_score_breakdown(0, 0, 0, 0)
        assert 0 <= result["score"] <= 100


class TestCashflowSeries:
    def test_returns_exactly_n_buckets(self, db, user):
        series = financial_twin.monthly_cashflow_series(db, user.id, months=6)
        assert len(series) == 6

    def test_months_are_chronological_and_unique(self, db, user):
        series = financial_twin.monthly_cashflow_series(db, user.id, months=12)
        months = [b["month"] for b in series]
        assert months == sorted(months)
        assert len(set(months)) == 12  # the old version repeated buckets

    def test_last_bucket_is_current_month(self, db, user):
        series = financial_twin.monthly_cashflow_series(db, user.id, months=3)
        now = datetime.utcnow()
        assert series[-1]["month"] == f"{now.year}-{now.month:02d}"

    def test_amounts_land_in_the_right_bucket(self, db, user):
        db.add_all([_txn(user.id, 70000, "Salary"), _txn(user.id, -20000, "Rent")])
        db.commit()

        series = financial_twin.monthly_cashflow_series(db, user.id, months=3)
        current = series[-1]
        assert current["income"] == 70000
        assert current["expense"] == 20000
        assert current["savings"] == 50000

    def test_empty_months_are_zero_filled(self, db, user):
        series = financial_twin.monthly_cashflow_series(db, user.id, months=6)
        assert all(b["income"] == 0 and b["expense"] == 0 for b in series)


class TestFingerprint:
    def test_changes_when_a_transaction_is_added(self, db, user):
        before = financial_twin.transactions_fingerprint(db, user.id)
        db.add(_txn(user.id, -100, "Food"))
        db.commit()
        assert financial_twin.transactions_fingerprint(db, user.id) != before

    def test_stable_when_nothing_changes(self, db, user):
        a = financial_twin.transactions_fingerprint(db, user.id)
        b = financial_twin.transactions_fingerprint(db, user.id)
        assert a == b
