"""
Cash-flow forecasting and the scenario simulator.

The simulator previously assumed zero inflation, zero tax and a fixed 10%
return. These tests pin the corrected behaviour.
"""
from datetime import datetime, timedelta

import pytest

from app import models
from app.services import forecast
from app.agents import scenario_simulator


def _add_series(db, user_id, label, amount, count, period_days, category="Subscriptions"):
    """Insert a regular repeating charge going backwards from today."""
    for i in range(count):
        db.add(models.Transaction(
            user_id=user_id,
            date=datetime.utcnow() - timedelta(days=period_days * i),
            amount=amount,
            category=category,
            type="income" if amount > 0 else "expense",
            merchant=label,
        ))
    db.commit()


class TestRecurringDetection:
    def test_detects_a_monthly_subscription(self, db, user):
        _add_series(db, user.id, "Netflix", -649, count=6, period_days=30)
        found = forecast.detect_recurring(db, user.id)
        labels = {r["label"] for r in found}
        assert "Netflix" in labels
        netflix = next(r for r in found if r["label"] == "Netflix")
        assert netflix["cadence"] == "monthly"
        assert netflix["amount"] == pytest.approx(649, rel=0.01)

    def test_ignores_one_off_purchases(self, db, user):
        db.add(models.Transaction(
            user_id=user.id, date=datetime.utcnow(), amount=-45000,
            category="Shopping", type="expense", merchant="Laptop Store",
        ))
        db.commit()
        assert forecast.detect_recurring(db, user.id) == []

    def test_ignores_erratic_amounts(self, db, user):
        """Same merchant, wildly varying amounts - not a subscription."""
        for i, amt in enumerate([-100, -5000, -250, -9000, -75, -3000]):
            db.add(models.Transaction(
                user_id=user.id, date=datetime.utcnow() - timedelta(days=30 * i),
                amount=amt, category="Shopping", type="expense", merchant="Amazon",
            ))
        db.commit()
        assert all(r["label"] != "Amazon" for r in forecast.detect_recurring(db, user.id))

    def test_next_due_date_is_in_the_future(self, db, user):
        _add_series(db, user.id, "Spotify", -119, count=5, period_days=30)
        item = next(r for r in forecast.detect_recurring(db, user.id) if r["label"] == "Spotify")
        assert datetime.fromisoformat(item["next_due"]) > datetime.utcnow()

    def test_monthly_equivalent_normalises_cadence(self, db, user):
        _add_series(db, user.id, "Weekly Cleaner", -500, count=8, period_days=7)
        item = next(r for r in forecast.detect_recurring(db, user.id)
                    if r["label"] == "Weekly Cleaner")
        assert item["cadence"] == "weekly"
        assert item["monthly_equivalent"] == pytest.approx(500 * 30 / 7, rel=0.05)

    def test_detects_recurring_salary(self, db, user):
        _add_series(db, user.id, "Employer", 85000, count=6, period_days=30, category="Salary")
        income = forecast.detect_recurring_income(db, user.id)
        assert any(r["label"] == "Employer" for r in income)


class TestForecast:
    def test_shape_and_horizon(self, db, user):
        result = forecast.forecast(db, user.id, days=30)
        assert result["horizon_days"] == 30
        assert len(result["series"]) == 31  # today plus 30 days

    def test_horizon_is_clamped(self, db, user):
        assert forecast.forecast(db, user.id, days=99999)["horizon_days"] == 365

    def test_runway_detected_when_bills_exceed_cash(self, db, user):
        db.add(models.Asset(user_id=user.id, name="Bank", asset_type="cash", value=5000))
        db.commit()
        _add_series(db, user.id, "Rent", -20000, count=6, period_days=30)

        result = forecast.forecast(db, user.id, days=90)
        assert result["low_balance_date"] is not None
        assert result["runway_days"] is not None
        assert "run out of cash" in result["summary"]

    def test_healthy_account_has_no_runway_warning(self, db, user):
        db.add(models.Asset(user_id=user.id, name="Bank", asset_type="cash", value=1_000_000))
        db.commit()
        result = forecast.forecast(db, user.id, days=60)
        assert result["low_balance_date"] is None

    def test_only_liquid_assets_count_as_buffer(self, db, user):
        """A flat you cannot sell this month is not a cash buffer."""
        db.add(models.Asset(user_id=user.id, name="Apartment",
                            asset_type="property", value=10_000_000))
        db.commit()
        assert forecast.forecast(db, user.id, days=30)["opening_balance"] == 0


class TestBudgetStatus:
    def test_empty_history_yields_nothing(self, db, user):
        assert forecast.budget_status(db, user.id) == []

    def test_flags_overspending_against_history(self, db, user):
        now = datetime.utcnow()
        # Three prior months at Rs 5,000/month on Food.
        for m in range(1, 4):
            db.add(models.Transaction(
                user_id=user.id,
                date=(now.replace(day=1) - timedelta(days=30 * m)),
                amount=-5000, category="Food", type="expense",
            ))
        # This month, already far above the usual pace.
        db.add(models.Transaction(user_id=user.id, date=now, amount=-15000,
                                  category="Food", type="expense"))
        db.commit()

        status = forecast.budget_status(db, user.id)
        food = next(c for c in status if c["category"] == "Food")
        assert food["spent_mtd"] == 15000
        assert food["over_by"] > 0
        assert food["pct_of_average"] > 100


class TestSimulator:
    def test_unknown_scenario_is_rejected(self, db, user):
        assert "error" in scenario_simulator.simulate(db, user.id, "teleport", 100)

    def test_investment_reports_post_tax_and_real_values(self, db, user):
        result = scenario_simulator.simulate(
            db, user.id, "investment", amount=10000, months_ahead=120
        )
        assert result["nominal_value"] > result["total_contributed"]
        # LTCG must reduce the headline number.
        assert result["post_tax_value"] < result["nominal_value"]
        # Inflation must reduce it further in today's money.
        assert result["real_value_today"] < result["post_tax_value"]
        assert result["tax_paid"] > 0

    def test_inflation_erodes_a_below_inflation_raise(self, db, user):
        result = scenario_simulator.simulate(
            db, user.id, "salary_change", percent_change=3, months_ahead=12,
            inflation=0.06,
        )
        assert result["real_change_pct"] < 0, "a 3% raise under 6% inflation is a real cut"

    def test_purchase_reports_opportunity_cost(self, db, user):
        result = scenario_simulator.simulate(
            db, user.id, "purchase", amount=100000, months_ahead=60
        )
        assert result["opportunity_cost"] > 0
        assert result["true_cost"] > result["one_time_amount"]

    def test_monte_carlo_gated_behind_plan(self, db, user):
        free = scenario_simulator.simulate(
            db, user.id, "investment", amount=5000, months_ahead=60,
            monte_carlo=True, user=user,
        )
        assert "monte_carlo" not in free

        user.plan = "plus"
        db.commit()
        paid = scenario_simulator.simulate(
            db, user.id, "investment", amount=5000, months_ahead=60,
            monte_carlo=True, user=user,
        )
        assert "monte_carlo" in paid

    def test_monte_carlo_bands_are_ordered(self, db, user):
        user.plan = "pro"
        db.commit()
        result = scenario_simulator.simulate(
            db, user.id, "investment", amount=5000, months_ahead=60,
            monte_carlo=True, user=user,
        )
        mc = result["monte_carlo"]
        assert mc["final_p10"] <= mc["final_p50"] <= mc["final_p90"]
        for band in mc["bands"]:
            assert band["p10"] <= band["p50"] <= band["p90"]

    def test_monte_carlo_is_reproducible(self, db, user):
        user.plan = "pro"
        db.commit()
        kwargs = dict(amount=5000, months_ahead=36, monte_carlo=True, user=user)
        a = scenario_simulator.simulate(db, user.id, "investment", **kwargs)
        b = scenario_simulator.simulate(db, user.id, "investment", **kwargs)
        assert a["monte_carlo"]["final_p50"] == b["monte_carlo"]["final_p50"]

    def test_assumptions_are_disclosed(self, db, user):
        result = scenario_simulator.simulate(db, user.id, "savings", amount=5000)
        assert result["assumptions"]["inflation"] > 0
        assert "not guaranteed" in result["assumptions"]["note"]

    def test_prepay_debt_uses_real_amortisation(self, db, user):
        db.add(models.Liability(
            user_id=user.id, name="Car Loan", amount=400_000,
            interest_rate=11.0, monthly_payment=12_000,
        ))
        db.commit()
        result = scenario_simulator.simulate(
            db, user.id, "prepay_debt", amount=100_000, months_ahead=36
        )
        assert result["comparison"]["prepay"]["interest_saved"] > 0
        assert result["comparison"]["verdict"] in ("prepay", "invest")
