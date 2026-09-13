"""
Debt optimiser maths.

Amortisation is checked against closed-form EMI results - if this drifts, the
product tells people to make the wrong financial decision.
"""
import pytest

from app import models
from app.services import debt


class TestAmortize:
    def test_known_emi_matches_closed_form(self):
        """
        Rs 10,00,000 at 9% over 20 years has an EMI of about Rs 8,997.
        Amortising at that payment should take ~240 months.
        """
        result = debt.amortize(1_000_000, 9.0, 8997.26)
        assert result["amortizes"]
        assert 238 <= result["months"] <= 242

    def test_total_paid_equals_principal_plus_interest(self):
        result = debt.amortize(500_000, 12.0, 11_122.22)
        assert result["total_paid"] == pytest.approx(
            500_000 + result["total_interest"], rel=0.001
        )

    def test_extra_payment_shortens_the_loan(self):
        base = debt.amortize(1_000_000, 9.0, 8997.26)
        faster = debt.amortize(1_000_000, 9.0, 8997.26, extra_monthly=5000)
        assert faster["months"] < base["months"]
        assert faster["total_interest"] < base["total_interest"]

    def test_lump_sum_reduces_interest(self):
        base = debt.amortize(1_000_000, 9.0, 8997.26)
        prepaid = debt.amortize(1_000_000, 9.0, 8997.26, lump_sum=200_000)
        assert prepaid["total_interest"] < base["total_interest"]
        assert prepaid["months"] < base["months"]

    def test_payment_below_interest_is_reported_not_looped(self):
        """A payment that never amortises must be flagged, not spun on forever."""
        result = debt.amortize(1_000_000, 12.0, 500)
        assert result["amortizes"] is False
        assert result["months"] is None
        assert "does not cover" in result["reason"]

    def test_zero_principal_is_handled(self):
        result = debt.amortize(0, 10.0, 5000)
        assert result["months"] == 0
        assert result["total_interest"] == 0

    def test_zero_interest_loan(self):
        result = debt.amortize(120_000, 0.0, 10_000)
        assert result["months"] == 12
        assert result["total_interest"] == pytest.approx(0, abs=0.01)

    def test_lump_sum_larger_than_balance_clears_it(self):
        result = debt.amortize(100_000, 9.0, 5000, lump_sum=150_000)
        assert result["months"] == 0

    def test_schedule_balance_decreases_to_zero(self):
        result = debt.amortize(200_000, 10.0, 10_000)
        balances = [row["balance"] for row in result["schedule"]]
        assert balances == sorted(balances, reverse=True)
        assert balances[-1] == 0


class TestPayoffPlan:
    @pytest.fixture
    def debts(self, db, user):
        db.add_all([
            models.Liability(user_id=user.id, name="Credit Card", liability_type="credit_card",
                             amount=150_000, interest_rate=36.0, monthly_payment=8_000),
            models.Liability(user_id=user.id, name="Car Loan", liability_type="loan",
                             amount=400_000, interest_rate=11.0, monthly_payment=12_000),
            models.Liability(user_id=user.id, name="Personal Loan", liability_type="loan",
                             amount=80_000, interest_rate=15.0, monthly_payment=4_000),
        ])
        db.commit()
        return user

    def test_no_liabilities_returns_message(self, db, user):
        assert debt.payoff_plan(db, user.id)["debts"] == []

    def test_avalanche_targets_highest_rate_first(self, db, debts):
        plan = debt.payoff_plan(db, debts.id, strategy="avalanche")
        assert plan["debts"][0]["name"] == "Credit Card"  # 36%

    def test_snowball_targets_smallest_balance_first(self, db, debts):
        plan = debt.payoff_plan(db, debts.id, strategy="snowball")
        assert plan["debts"][0]["name"] == "Personal Loan"  # Rs 80k

    def test_surplus_saves_interest_and_time(self, db, debts):
        plan = debt.payoff_plan(db, debts.id, extra_monthly=10_000)
        assert plan["interest_saved_vs_baseline"] > 0
        assert plan["months_saved_vs_baseline"] > 0

    def test_avalanche_never_costs_more_than_snowball(self, db, debts):
        plan = debt.payoff_plan(db, debts.id, extra_monthly=10_000)
        assert plan["avalanche"]["total_interest"] <= plan["snowball"]["total_interest"]
        assert plan["avalanche_advantage"] >= 0

    def test_totals_are_reported(self, db, debts):
        plan = debt.payoff_plan(db, debts.id)
        assert plan["total_debt"] == 630_000
        assert plan["total_monthly_payment"] == 24_000


class TestPrepayVsInvest:
    @pytest.fixture
    def loan(self, db, user):
        db.add(models.Liability(
            user_id=user.id, name="Home Loan", liability_type="loan",
            amount=1_000_000, interest_rate=9.0, monthly_payment=8_997.26,
        ))
        db.commit()
        return user

    def test_high_rate_debt_favours_prepaying(self, db, user):
        db.add(models.Liability(
            user_id=user.id, name="Credit Card", liability_type="credit_card",
            amount=200_000, interest_rate=36.0, monthly_payment=10_000,
        ))
        db.commit()
        result = debt.prepay_vs_invest(db, user.id, 100_000, annual_return=0.10)
        assert result["verdict"] == "prepay"

    def test_low_rate_debt_favours_investing(self, db, user):
        db.add(models.Liability(
            user_id=user.id, name="Subsidised Loan", liability_type="loan",
            amount=500_000, interest_rate=4.0, monthly_payment=6_000,
        ))
        db.commit()
        result = debt.prepay_vs_invest(db, user.id, 100_000, annual_return=0.12)
        assert result["verdict"] == "invest"

    def test_reports_both_sides(self, db, loan):
        result = debt.prepay_vs_invest(db, loan.id, 200_000)
        assert result["prepay"]["interest_saved"] > 0
        assert result["prepay"]["months_saved"] > 0
        assert result["invest"]["post_tax_value"] > 200_000
        assert "not guaranteed" in result["summary"]

    def test_no_liability_returns_error(self, db, user):
        assert "error" in debt.prepay_vs_invest(db, user.id, 100_000)
