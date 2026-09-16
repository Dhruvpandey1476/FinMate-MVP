"""
Tier 1 Core Loop: Safe-to-Spend, Early Warning, Time Machine, Next Best Action.

The load-bearing guarantee here is that every *decision* is deterministic. The
tests assert that directly - same inputs, same ranking, no model involved - so
the claim can be demonstrated rather than asserted.
"""
from datetime import datetime, timedelta

import pytest

from app import models
from app.services import safe_to_spend
from app.agents import early_warning, next_best_action


def _txn(user_id, amount, category="Other", days_ago=0, merchant=None, recurring=False):
    return models.Transaction(
        user_id=user_id,
        date=datetime.utcnow() - timedelta(days=days_ago),
        amount=amount,
        category=category,
        type="income" if amount > 0 else "expense",
        merchant=merchant,
        is_recurring=recurring,
    )


def _series(db, user_id, label, amount, count=6, period=30, category="Subscriptions"):
    """A charge repeating on a stable cadence, which is what the detector needs."""
    for i in range(count):
        db.add(_txn(user_id, amount, category, days_ago=period * i, merchant=label))
    db.commit()


class TestRunningBalance:
    def test_falls_back_to_ledger_without_a_checkpoint(self, db, user):
        db.add_all([_txn(user.id, 50000, "Salary"), _txn(user.id, -12000, "Rent")])
        db.commit()

        info = safe_to_spend.running_balance(db, user.id)
        assert info["basis"] == "ledger"
        assert info["balance"] == 38000

    def test_checkpoint_plus_net_since(self, db, user):
        safe_to_spend.add_checkpoint(
            db, user.id, 100000, as_of=datetime.utcnow() - timedelta(days=5)
        )
        db.add_all([
            _txn(user.id, -3000, "Food", days_ago=2),
            _txn(user.id, -2000, "Transport", days_ago=1),
        ])
        db.commit()

        info = safe_to_spend.running_balance(db, user.id)
        assert info["basis"] == "checkpoint"
        assert info["balance"] == 95000
        assert info["confirmed_balance"] == 100000

    def test_transactions_before_the_checkpoint_are_not_double_counted(self, db, user):
        """They are already reflected in the balance the user confirmed."""
        db.add(_txn(user.id, -9999, "Food", days_ago=30))
        db.commit()
        safe_to_spend.add_checkpoint(db, user.id, 50000)

        assert safe_to_spend.running_balance(db, user.id)["balance"] == 50000

    def test_latest_checkpoint_wins(self, db, user):
        safe_to_spend.add_checkpoint(db, user.id, 10000,
                                     as_of=datetime.utcnow() - timedelta(days=10))
        safe_to_spend.add_checkpoint(db, user.id, 70000)
        assert safe_to_spend.running_balance(db, user.id)["confirmed_balance"] == 70000


class TestSafeToSpend:
    def test_empty_account_is_not_negative_nonsense(self, db, user):
        result = safe_to_spend.compute(db, user.id)
        assert "safe_to_spend" in result
        assert result["balance"]["basis"] == "ledger"

    def test_subtracts_bills_goals_and_buffer(self, db, user):
        safe_to_spend.add_checkpoint(db, user.id, 100000)
        _series(db, user.id, "Netflix", -649, category="Subscriptions")
        db.add(models.Goal(user_id=user.id, name="Emergency Fund", target_amount=300000,
                           current_amount=0, monthly_contribution=10000))
        db.commit()

        result = safe_to_spend.compute(db, user.id)
        d = result["deductions"]
        assert d["goal_contributions"]["total"] == 10000
        assert d["safety_buffer"]["total"] > 0
        expected = (result["balance"]["amount"]
                    - d["upcoming_bills"]["total"]
                    - d["goal_contributions"]["total"]
                    - d["safety_buffer"]["total"])
        assert result["safe_to_spend"] == pytest.approx(expected, abs=0.01)

    def test_goal_paid_as_a_recurring_transfer_is_not_counted_twice(self, db, user):
        """
        The bug this guards: a goal funded by a recurring transfer would be
        subtracted once as a bill and again as a goal contribution.
        """
        safe_to_spend.add_checkpoint(db, user.id, 100000)
        _series(db, user.id, "Emergency Fund", -10000, category="Savings")
        db.add(models.Goal(user_id=user.id, name="Emergency Fund", target_amount=300000,
                           current_amount=0, monthly_contribution=10000))
        db.commit()

        goals = safe_to_spend.compute(db, user.id)["deductions"]["goal_contributions"]
        assert goals["total"] == 0
        assert any("already counted" in (i.get("note") or "") for i in goals["items"])

    def test_contribution_already_set_aside_reduces_the_deduction(self, db, user):
        safe_to_spend.add_checkpoint(db, user.id, 100000)
        db.add(models.Goal(user_id=user.id, name="New Car", target_amount=500000,
                           current_amount=0, monthly_contribution=8000))
        db.add(_txn(user.id, -5000, "New Car"))
        db.commit()

        goals = safe_to_spend.compute(db, user.id)["deductions"]["goal_contributions"]
        assert goals["total"] == 3000

    def test_buffer_is_bounded(self, db, user):
        result = safe_to_spend.compute(db, user.id)
        buffer = result["deductions"]["safety_buffer"]["total"]
        assert safe_to_spend.MIN_BUFFER <= buffer <= safe_to_spend.MAX_BUFFER

    def test_buffer_explains_itself(self, db, user):
        """A number in the breakdown the user cannot interrogate is a bad number."""
        basis = safe_to_spend.compute(db, user.id)["deductions"]["safety_buffer"]["basis"]
        assert "days" in basis

    def test_balance_label_never_implies_a_live_feed(self, db, user):
        label = safe_to_spend.compute(db, user.id)["balance"]["label"]
        assert "last update" in label or "logged transactions" in label

    def test_checkpoint_nudge_after_a_week(self, db, user):
        safe_to_spend.add_checkpoint(db, user.id, 50000,
                                     as_of=datetime.utcnow() - timedelta(days=9))
        assert safe_to_spend.compute(db, user.id)["needs_checkpoint"] is True

    def test_fresh_checkpoint_does_not_nag(self, db, user):
        safe_to_spend.add_checkpoint(db, user.id, 50000)
        assert safe_to_spend.compute(db, user.id)["needs_checkpoint"] is False


class TestEarlyWarning:
    def test_quiet_on_an_empty_account(self, db, user):
        kinds = {w["kind"] for w in early_warning.check(db, user.id)}
        # Only the "tell us your balance" nudge is reasonable with no data.
        assert kinds <= {"stale_balance"}

    def test_flags_a_category_running_hot(self, db, user):
        now = datetime.utcnow()
        month_start = now.replace(day=1)
        for m in range(1, 4):
            db.add(models.Transaction(
                user_id=user.id, date=month_start - timedelta(days=30 * m),
                amount=-5000, category="Food", type="expense"))
        db.add(_txn(user.id, -20000, "Food"))
        db.commit()

        warnings = early_warning.check(db, user.id)
        assert any(w["kind"] == "category_pace" and w["category"] == "Food" for w in warnings)

    def test_flags_a_spike(self, db, user):
        for i in range(5):
            db.add(_txn(user.id, -500, "Shopping", days_ago=i + 1))
        db.add(_txn(user.id, -9000, "Shopping"))
        db.commit()

        assert any(w["kind"] == "unusual_transaction" for w in early_warning.check(db, user.id))

    def test_warnings_carry_a_stable_key_for_dismissal(self, db, user):
        db.add(_txn(user.id, -100, "Food"))
        db.commit()
        first = {w["key"] for w in early_warning.check(db, user.id)}
        second = {w["key"] for w in early_warning.check(db, user.id)}
        assert first == second

    def test_sorted_most_severe_first(self, db, user):
        order = [early_warning.SEVERITY_ORDER[w["severity"]]
                 for w in early_warning.check(db, user.id)]
        assert order == sorted(order)


class TestNextBestAction:
    @pytest.fixture
    def funded(self, db, user):
        safe_to_spend.add_checkpoint(db, user.id, 60000)
        db.add_all([
            _txn(user.id, 90000, "Salary"),
            _txn(user.id, -20000, "Rent", days_ago=1),
            models.Goal(user_id=user.id, name="Emergency Fund", target_amount=300000,
                        current_amount=50000, monthly_contribution=10000, priority=1),
        ])
        for i in range(4):
            db.add(_txn(user.id, -649, "Subscriptions", days_ago=30 * i, merchant="Netflix"))
        db.commit()
        return user

    def test_returns_exactly_one_action(self, db, funded):
        result = next_best_action.run(db, funded.id, user=funded)
        assert isinstance(result["action_text"], str) and result["action_text"]
        assert result["source_module"] is not None

    def test_the_decision_is_deterministic_not_a_model(self, db, funded):
        """Re-ranking the same data must produce the same winner, every time."""
        a = next_best_action.collect_candidates(db, funded.id, funded)
        b = next_best_action.collect_candidates(db, funded.id, funded)
        assert [c["action_text"] for c in a] == [c["action_text"] for c in b]
        assert [c["score"] for c in a] == [c["score"] for c in b]

    def test_candidates_are_sorted_by_score(self, db, funded):
        scores = [c["score"] for c in next_best_action.collect_candidates(db, funded.id, funded)]
        assert scores == sorted(scores, reverse=True)

    def test_result_declares_how_it_decided(self, db, funded):
        assert next_best_action.run(db, funded.id, user=funded)["decided_by"] == "deterministic_scoring"

    def test_urgent_cash_flow_outranks_a_slow_saving(self, db, user):
        """Urgency has to beat raw rupee impact, or the ranking is just a sort by size."""
        urgent = {"kind": "cash_flow", "estimated_impact_rupees": 3000}
        slow = {"kind": "spending_leak", "estimated_impact_rupees": 3000}
        assert next_best_action._score(urgent) > next_best_action._score(slow)

    def test_lower_effort_wins_at_equal_impact(self, db, user):
        easy = {"kind": "subscription", "estimated_impact_rupees": 2000}
        hard = {"kind": "spending_leak", "estimated_impact_rupees": 2000}
        assert next_best_action._score(easy) > next_best_action._score(hard)

    def test_empty_account_degrades_gracefully(self, db, user):
        result = next_best_action.run(db, user.id, user=user)
        assert result["action_text"]
        assert result["considered"] == 0


class TestEssentialsAreNeverCancelCandidates:
    """
    Recurring-charge detection finds rent and EMIs as reliably as Netflix.
    Without a guard the top recommendation becomes "eliminate your rent",
    which is useless advice and destroys trust in everything else on the page.
    """

    @pytest.mark.parametrize("title", [
        "Recurring charge: Landlord - Koramangala Flat",
        "Spending leak: Rent",
        "Recurring charge: BESCOM Electricity",
        "Home Loan EMI",
        "Recurring charge: LIC Insurance Premium",
        "Spending leak: Utilities",
    ])
    def test_commitments_are_blocked(self, title):
        assert next_best_action._is_essential(title) is True

    @pytest.mark.parametrize("title", [
        "Recurring charge: Netflix",
        "Spending leak: Food Delivery",
        "Spending leak: Shopping",
        "Recurring charge: Spotify",
    ])
    def test_discretionary_spend_is_allowed(self, title):
        assert next_best_action._is_essential(title) is False

    def test_rent_never_reaches_the_candidate_list(self, db, user):
        for i in range(6):
            db.add(_txn(user.id, -18000, "Rent", days_ago=30 * i,
                        merchant="Landlord - Koramangala Flat"))
            db.add(_txn(user.id, -800, "Food Delivery", days_ago=30 * i + 3,
                        merchant="Swiggy"))
        db.commit()

        texts = " ".join(
            c["action_text"].lower()
            for c in next_best_action.collect_candidates(db, user.id, user)
        )
        assert "rent" not in texts
        assert "landlord" not in texts


class TestProjectionsUseARunRate:
    def test_partial_current_month_does_not_flatten_the_projection(self, db, user):
        """
        Projecting from the current month means a 12-month forecast built on
        however many days have elapsed - and a flat line on the 1st.
        """
        from app.services import financial_twin

        now = datetime.utcnow()
        month_start = now.replace(day=1)
        for m in range(1, 4):
            base = month_start - timedelta(days=30 * m)
            db.add(models.Transaction(user_id=user.id, date=base, amount=80000,
                                      category="Salary", type="income"))
            db.add(models.Transaction(user_id=user.id, date=base + timedelta(days=2),
                                      amount=-50000, category="Rent", type="expense"))
        db.commit()

        rate = financial_twin.monthly_run_rate(db, user.id)
        assert rate["income"] == pytest.approx(80000, rel=0.01)
        assert rate["expense"] == pytest.approx(50000, rel=0.01)
        assert rate["months_used"] == 3

    def test_falls_back_when_there_is_no_completed_history(self, db, user):
        from app.services import financial_twin

        db.add(_txn(user.id, 40000, "Salary"))
        db.commit()
        rate = financial_twin.monthly_run_rate(db, user.id)
        assert rate["months_used"] == 0
        assert "current month" in rate["basis"]


class TestDemoSeedFreshness:
    """
    A demo account whose current month is empty makes every month-scoped figure
    read zero - cash flow, savings rate, Safe-to-Spend, the budget comparison.
    """

    def test_stale_means_the_current_month_is_empty(self, db, user):
        from app import seed_data

        # Seeded late last month: recent by a rolling-window rule, but the
        # current month has nothing in it.
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0,
                                                second=0, microsecond=0)
        db.add(models.Transaction(
            user_id=user.id, date=month_start - timedelta(days=3),
            amount=-2500, category="Food", type="expense"))
        db.commit()

        assert seed_data._demo_is_stale(db, user) is True

    def test_data_in_the_current_month_is_fresh(self, db, user):
        from app import seed_data

        db.add(_txn(user.id, -500, "Food"))
        db.commit()
        assert seed_data._demo_is_stale(db, user) is False

    def test_empty_account_is_stale(self, db, user):
        from app import seed_data
        assert seed_data._demo_is_stale(db, user) is True

    def test_seeded_data_never_lands_in_the_future(self, db, user):
        """Future-dated spending inflates this month's totals."""
        from app import seed_data

        seed_data.seed_for_user(db, user)
        db.commit()

        newest = (
            db.query(models.Transaction.date)
            .filter(models.Transaction.user_id == user.id)
            .order_by(models.Transaction.date.desc())
            .first()[0]
        )
        assert newest.date() <= datetime.utcnow().date(), (
            f"seed produced a future-dated transaction: {newest}"
        )

    def test_seeded_data_covers_the_current_month(self, db, user):
        from app import seed_data

        seed_data.seed_for_user(db, user)
        db.commit()

        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0,
                                                second=0, microsecond=0)
        current = (
            db.query(models.Transaction)
            .filter(models.Transaction.user_id == user.id,
                    models.Transaction.date >= month_start)
            .count()
        )
        assert current > 0, "seed left the current month empty"
        assert seed_data._demo_is_stale(db, user) is False
