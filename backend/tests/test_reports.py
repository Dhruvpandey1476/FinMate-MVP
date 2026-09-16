"""
Paid outcomes.

The unlock is mocked; the reports are not. These assert the generators produce
real figures from real data, and that the legally load-bearing wording is
actually present - "Net Worth Statement" not certificate, a readiness report
that disclaims being a credit score, and a tax export that flags rather than
decides.
"""
from datetime import datetime, timedelta

import pytest

from app import models
from app.services import reports, tax_kb


def _txn(user_id, amount, category="Other", days_ago=0, merchant=None):
    return models.Transaction(
        user_id=user_id,
        date=datetime.utcnow() - timedelta(days=days_ago),
        amount=amount, category=category,
        type="income" if amount > 0 else "expense", merchant=merchant,
    )


@pytest.fixture
def populated(db, user):
    """Six months of income and spread-out spending."""
    for m in range(6):
        db.add(_txn(user.id, 90000, "Salary", days_ago=30 * m))
        db.add(_txn(user.id, -18000, "Rent", days_ago=30 * m + 1))
        db.add(_txn(user.id, -6000, "Food Delivery", days_ago=30 * m + 2))
        db.add(_txn(user.id, -4000, "Shopping", days_ago=30 * m + 3))
        db.add(_txn(user.id, -2500, "Insurance", days_ago=30 * m + 4))
    db.add_all([
        models.Asset(user_id=user.id, name="Savings", asset_type="cash", value=400000),
        models.Asset(user_id=user.id, name="MF", asset_type="investment", value=250000),
        models.Liability(user_id=user.id, name="Car Loan", amount=300000,
                         interest_rate=11.0, monthly_payment=9000),
    ])
    db.commit()
    return user


class TestCatalogue:
    def test_every_entry_has_a_generator(self):
        for report in reports.CATALOGUE:
            assert report["id"] in reports.GENERATORS

    def test_seven_outcomes_are_offered(self):
        assert len(reports.CATALOGUE) == 7

    def test_everything_is_priced(self):
        assert all(r["price_inr"] > 0 for r in reports.CATALOGUE)


class TestGeneratorsProduceRealOutput:
    @pytest.mark.parametrize("report_id", list(reports.GENERATORS))
    def test_generates_without_error(self, db, populated, report_id):
        result = reports.generate(db, populated.id, report_id)
        assert result["id"] == report_id
        assert result["title"]
        assert isinstance(result["data"], dict)

    @pytest.mark.parametrize("report_id", list(reports.GENERATORS))
    def test_empty_account_degrades_gracefully(self, db, user, report_id):
        """A report with nothing to say must explain itself, not crash."""
        result = reports.generate(db, user.id, report_id)
        assert isinstance(result["data"], dict)


class TestMoneyWrapped:
    def test_headline_numbers_are_real(self, db, populated):
        data = reports.money_wrapped(db, populated.id)
        assert data["total_income"] > 0
        assert data["total_spend"] > 0
        assert data["top_category"] == "Rent"
        assert data["transaction_count"] > 0

    def test_personality_is_assigned(self, db, populated):
        data = reports.money_wrapped(db, populated.id)
        assert data["personality"] and data["personality_note"]

    def test_category_shares_are_percentages(self, db, populated):
        shares = [c["share"] for c in reports.money_wrapped(db, populated.id)["categories"]]
        assert all(0 <= s <= 100 for s in shares)


class TestTaxReady:
    def test_flags_relevant_categories(self, db, populated):
        data = reports.tax_ready(db, populated.id)
        insurance = next(s for s in data["sections"] if s["category"] == "Insurance")
        assert insurance["flagged"] is True
        assert "80" in " ".join(insurance["sections"])

    def test_does_not_flag_ordinary_spending(self, db, populated):
        data = reports.tax_ready(db, populated.id)
        food = next(s for s in data["sections"] if s["category"] == "Food Delivery")
        assert food["flagged"] is False

    def test_never_claims_to_calculate_tax(self, db, populated):
        """The wording here is a legal constraint, not a style preference."""
        text = reports.tax_ready(db, populated.id)["disclaimer"].lower()
        assert "does not calculate your tax" in text
        assert "flags" in text

    def test_rules_are_dated(self, db, populated):
        data = reports.tax_ready(db, populated.id)
        assert data["rules_as_of"] == tax_kb.AS_OF
        assert all(f["as_of_date"] for f in data["reference_facts"])

    def test_headroom_is_framed_as_identified_not_eligible(self, db, populated):
        for row in reports.tax_ready(db, populated.id)["headroom"]:
            assert "not a confirmed eligible amount" in row["note"]


class TestLoanReadiness:
    def test_computes_debt_to_income(self, db, populated):
        data = reports.loan_readiness(db, populated.id)
        assert data["monthly_obligations"] == 9000
        assert data["debt_to_income_pct"] > 0
        assert data["indicator"] in ("Strong", "Moderate", "Needs work")

    def test_disclaims_being_a_credit_score(self, db, populated):
        text = reports.loan_readiness(db, populated.id)["disclaimer"].lower()
        assert "not a credit score" in text
        assert "no weight with any lender" in text

    def test_thresholds_are_published(self, db, populated):
        assert reports.loan_readiness(db, populated.id)["thresholds"]["strong"]


class TestNetWorthStatement:
    def test_arithmetic(self, db, populated):
        data = reports.net_worth(db, populated.id)
        assert data["total_assets"] == 650000
        assert data["total_liabilities"] == 300000
        assert data["net_worth"] == 350000

    def test_is_called_a_statement_not_a_certificate(self):
        title = reports.CATALOGUE_BY_ID["net_worth"]["title"]
        assert title == "Net Worth Statement"
        assert "certificate" not in title.lower()

    def test_says_it_is_self_reported(self, db, populated):
        assert "self-reported" in reports.net_worth(db, populated.id)["disclaimer"].lower()


class TestWeddingPlan:
    def test_explains_itself_without_a_wedding_goal(self, db, populated):
        data = reports.wedding_plan(db, populated.id)
        assert data["empty"] is True
        assert "wedding" in data["reason"].lower()

    def test_builds_scenarios_and_milestones(self, db, populated):
        db.add(models.Goal(
            user_id=populated.id, name="Our Wedding", goal_type="wedding",
            target_amount=1_500_000, current_amount=300_000,
            monthly_contribution=40_000,
            target_date=datetime.utcnow() + timedelta(days=540),
        ))
        db.commit()

        data = reports.wedding_plan(db, populated.id)
        assert data["goal"]["remaining"] == 1_200_000
        assert len(data["scenarios"]) >= 2
        assert data["milestones"]
        assert data["milestones"][-1]["percent"] <= 100


class TestNamingConstraints:
    def test_no_banned_terms_in_the_catalogue(self):
        """These were corrected for trust and legal risk; keep them corrected."""
        blob = " ".join(
            f"{r['title']} {r['blurb']}" for r in reports.CATALOGUE
        ).lower()
        for banned in ("net worth certificate", "loan readiness certificate",
                       "loan readiness assessment", "bank-approved",
                       "government-recognised", "officially verified"):
            assert banned not in blob
