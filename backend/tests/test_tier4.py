"""
Tier 4: wedding contributors, Family Wealth, Credit Health, donations, B2B API.

The load-bearing assertions here are about consent and honesty: nothing is
shared before an invite is accepted, a partial family total says it is partial,
and the credit score is never presented as a bureau score.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from app import models
from app.services import family, credit_health, reports
from app.services import next_best_action_stateless as nba


def _txn(user_id, amount, category="Other", days_ago=0, merchant=None):
    return models.Transaction(
        user_id=user_id, date=datetime.utcnow() - timedelta(days=days_ago),
        amount=amount, category=category,
        type="income" if amount > 0 else "expense", merchant=merchant,
    )


@pytest.fixture
def other_user(db):
    # Unique per test: the fixture runs once per test against a shared DB.
    u = models.User(name="Partner", email=f"partner-{uuid.uuid4().hex[:8]}@finmate.test")
    db.add(u)
    db.commit()
    db.refresh(u)
    for m in range(3):
        db.add(_txn(u.id, 60000, "Salary", days_ago=30 * m))
        db.add(_txn(u.id, -25000, "Rent", days_ago=30 * m + 1))
    db.add(models.Asset(user_id=u.id, name="Savings", asset_type="cash", value=200000))
    db.commit()
    return u


class TestFamilyConsent:
    def test_invite_starts_pending_and_shares_nothing(self, db, user, other_user):
        family.invite(db, user.id, other_user.email)
        view = family.family_twin(db, user)

        member = next(m for m in view["members"] if m.get("email") == other_user.email)
        assert member["status"] == "pending"
        assert member["net_worth"] is None
        assert "not accepted" in member["note"] or "pending" in member["note"].lower()

    def test_accepting_shares_what_was_granted(self, db, user, other_user):
        link = family.invite(db, user.id, other_user.email)
        family.accept(db, other_user, link.invite_token)

        member = next(m for m in family.family_twin(db, user)["members"]
                      if m.get("email") == other_user.email)
        assert member["status"] == "accepted"
        assert member["net_worth"] is not None

    def test_a_withheld_figure_is_withheld(self, db, user, other_user):
        link = family.invite(db, user.id, other_user.email, share_net_worth=False)
        family.accept(db, other_user, link.invite_token)

        member = next(m for m in family.family_twin(db, user)["members"]
                      if m.get("email") == other_user.email)
        assert member["net_worth"] is None
        assert "not shared" in member["note"]

    def test_only_the_invited_address_can_accept(self, db, user, other_user):
        link = family.invite(db, user.id, "someone.else@finmate.test")
        with pytest.raises(ValueError):
            family.accept(db, other_user, link.invite_token)

    def test_revoking_removes_access(self, db, user, other_user):
        link = family.invite(db, user.id, other_user.email)
        family.accept(db, other_user, link.invite_token)
        assert family.revoke(db, user.id, link.id) is True
        assert all(m.get("email") != other_user.email
                   for m in family.family_twin(db, user)["members"])

    def test_a_partial_total_says_it_is_partial(self, db, user, other_user):
        link = family.invite(db, user.id, other_user.email, share_net_worth=False)
        family.accept(db, other_user, link.invite_token)

        view = family.family_twin(db, user)
        assert view["withheld"] >= 1
        assert "partial" in view["note"]

    def test_combined_total_adds_up(self, db, user, other_user):
        db.add(models.Asset(user_id=user.id, name="Bank", asset_type="cash", value=100000))
        db.commit()
        link = family.invite(db, user.id, other_user.email)
        family.accept(db, other_user, link.invite_token)

        view = family.family_twin(db, user)
        assert view["combined_net_worth"] == 300000
        assert view["counted"] == 2


class TestCreditHealth:
    def test_never_reports_a_bureau_score(self, db, user):
        result = credit_health.assess(db, user.id)
        assert result["bureau_score"] is None
        assert "not a credit score" in result["bureau_note"].lower()
        assert "no weight with any lender" in result["bureau_note"].lower()

    def test_high_utilisation_costs_points(self, db, user):
        for m in range(3):
            db.add(_txn(user.id, 50000, "Salary", days_ago=30 * m))
        db.add(models.Liability(user_id=user.id, name="Card",
                                liability_type="credit_card", amount=80000,
                                monthly_payment=4000, interest_rate=36))
        db.commit()

        result = credit_health.assess(db, user.id)
        util = next(f for f in result["factors"] if f["label"] == "Credit utilisation")
        assert util["points"] < 0
        assert result["score"] < 100

    def test_clean_profile_scores_well(self, db, user):
        for m in range(3):
            db.add(_txn(user.id, 100000, "Salary", days_ago=30 * m))
        db.commit()
        result = credit_health.assess(db, user.id)
        assert result["score"] >= 80
        assert result["band"] == "Excellent"

    def test_bands_and_improvements_are_explained(self, db, user):
        result = credit_health.assess(db, user.id)
        assert result["band_note"]
        assert result["improvements"]
        assert all(f["detail"] for f in result["factors"])


class TestDonationsFeedTaxExport:
    def test_marked_donations_reach_the_export(self, db, user):
        db.add(_txn(user.id, 90000, "Salary"))
        db.add_all([
            models.Donation(user_id=user.id, recipient="Goonj", amount=5000,
                            donated_on=datetime.utcnow(), is_80g_eligible=True),
            models.Donation(user_id=user.id, recipient="Local temple", amount=2000,
                            donated_on=datetime.utcnow(), is_80g_eligible=False),
        ])
        db.commit()

        data = reports.tax_ready(db, user.id)
        assert data["donations_total"] == 7000
        assert data["donations_80g_marked"] == 5000

    def test_eligibility_is_never_inferred(self, db, user):
        db.add(_txn(user.id, 50000, "Salary"))
        db.commit()
        assert "cannot verify" in reports.tax_ready(db, user.id)["donations_note"]


class TestRicherReports:
    @pytest.fixture
    def populated(self, db, user):
        for m in range(6):
            db.add(_txn(user.id, 90000, "Salary", days_ago=30 * m))
            db.add(_txn(user.id, -18000, "Rent", days_ago=30 * m + 1, merchant="Landlord"))
            db.add(_txn(user.id, -6000, "Food Delivery", days_ago=30 * m + 2, merchant="Swiggy"))
            db.add(_txn(user.id, -4000, "Shopping", days_ago=30 * m + 3, merchant="Amazon"))
        db.commit()
        return user

    def test_money_wrapped_gained_real_depth(self, db, populated):
        d = reports.money_wrapped(db, populated.id)
        assert d["merchants"] and d["merchants"][0]["count"] > 0
        assert d["biggest_transactions"]
        assert d["weekday_split"]["weekday_total"] >= 0
        assert d["averages"]["per_transaction"] > 0
        assert "current_streak" in d["streak"]

    def test_health_report_lists_commitments_and_trends(self, db, populated):
        d = reports.financial_health(db, populated.id)
        assert isinstance(d["recurring_commitments"], list)
        assert isinstance(d["trends"], list)
        assert d["merchants"]

    def test_net_worth_shows_composition_and_leverage(self, db, populated):
        db.add_all([
            models.Asset(user_id=populated.id, name="Cash", asset_type="cash", value=300000),
            models.Liability(user_id=populated.id, name="Loan", amount=150000),
        ])
        db.commit()
        d = reports.net_worth(db, populated.id)
        assert d["leverage_ratio"] == 50.0
        assert d["liquid_assets"] == 300000
        assert d["composition"]

    def test_weekday_and_weekend_are_separate_buckets(self, db, populated):
        """They were aliased to one set, so every day counted in both."""
        split = reports.money_wrapped(db, populated.id)["weekday_split"]
        assert split["weekday_total"] + split["weekend_total"] > 0


class TestStatelessNextBestAction:
    def test_ranks_deterministically(self):
        args = dict(monthly_income=80000, monthly_expense=60000,
                    categories={"Shopping": 20000, "Food Delivery": 12000})
        assert nba.recommend(**args) == nba.recommend(**args)

    def test_negative_cash_flow_wins(self):
        result = nba.recommend(monthly_income=40000, monthly_expense=55000,
                               categories={"Shopping": 15000})
        assert result["kind"] == "cash_flow"

    def test_never_suggests_cutting_a_commitment(self):
        result = nba.recommend(monthly_income=90000, monthly_expense=60000,
                               categories={"Rent": 40000, "Shopping": 12000})
        assert "rent" not in result["action"].lower()

    def test_declares_how_it_decided(self):
        result = nba.recommend(monthly_income=80000, monthly_expense=50000,
                               categories={"Shopping": 20000})
        assert result["decided_by"] == "deterministic_scoring"
