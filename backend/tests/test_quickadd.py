"""
Quick Add parsing and the categoriser correction loop.

The rule path must cover the common shapes without a model: an LLM round trip
for "300 auto" would be slow, costly, and unavailable offline. These tests pin
that coverage, and the correction loop that makes the categoriser improve.
"""
import pytest

from app import models
from app.services import quickadd_parser as qa, categorizer


class TestRuleParsing:
    @pytest.mark.parametrize("text,amount,category", [
        ("300 auto", -300, "Transport"),
        ("spent 1200 on dinner", -1200, "Food Delivery"),
        ("450 swiggy", -450, "Food Delivery"),
        ("paid 18000 rent", -18000, "Rent"),
        ("2500 bigbasket", -2500, "Groceries"),
        ("649 netflix", -649, "Subscriptions"),
        ("bought 3200 on myntra", -3200, "Shopping"),
        ("900 uber", -900, "Transport"),
    ])
    def test_common_shapes_need_no_model(self, db, user, text, amount, category):
        result = qa.parse(db, user.id, text)
        assert result is not None, f"rules failed to read {text!r}"
        assert result["path"] == "rules"
        assert result["amount"] == amount
        assert result["category"] == category

    @pytest.mark.parametrize("text,amount", [
        ("rs 500 coffee", -500),
        ("₹1,250 groceries", -1250),
        ("1.5k shopping", -1500),
        ("2k petrol", -2000),
    ])
    def test_amount_formats(self, db, user, text, amount):
        result = qa.parse(db, user.id, text)
        assert result is not None and result["amount"] == amount

    @pytest.mark.parametrize("text", [
        "received 85000 salary",
        "got 5000 refund",
        "credited 12000 freelance",
    ])
    def test_income_is_positive(self, db, user, text):
        result = qa.parse(db, user.id, text)
        assert result is not None and result["amount"] > 0

    @pytest.mark.parametrize("text", ["hello", "", "   ", "what did I spend"])
    def test_no_amount_is_refused_not_guessed(self, db, user, text):
        """Logging a transaction the user did not mean is worse than asking."""
        assert qa.parse(db, user.id, text) is None

    def test_description_excludes_filler_and_amount(self, db, user):
        result = qa.parse(db, user.id, "spent 1200 on dinner today")
        assert "1200" not in result["merchant"]
        assert "spent" not in result["merchant"].lower()
        assert "dinner" in result["merchant"].lower()


class TestCorrectionLoop:
    def test_keyword_match_is_the_starting_point(self, db, user):
        verdict = categorizer.categorize(db, user.id, "swiggy", -450)
        assert verdict["category"] == "Food Delivery"
        assert verdict["source"] == "keyword"

    def test_a_correction_sticks(self, db, user):
        categorizer.learn(db, user.id, "Chai Point", "Food Delivery")
        verdict = categorizer.categorize(db, user.id, "Chai Point", -60)
        assert verdict["category"] == "Food Delivery"
        assert verdict["source"] == "user_rule"

    def test_a_correction_overrides_the_keyword_guess(self, db, user):
        """The user is the authority on their own merchants."""
        assert categorizer.categorize(db, user.id, "amazon", -800)["category"] == "Shopping"

        categorizer.learn(db, user.id, "amazon", "Groceries")
        verdict = categorizer.categorize(db, user.id, "amazon", -800)
        assert verdict["category"] == "Groceries"
        assert verdict["source"] == "user_rule"

    def test_corrections_do_not_leak_between_users(self, db, user):
        other = models.User(name="Other", email="other-rules@finmate.test")
        db.add(other)
        db.commit()
        db.refresh(other)

        categorizer.learn(db, user.id, "amazon", "Groceries")
        assert categorizer.categorize(db, other.id, "amazon", -800)["category"] == "Shopping"

    def test_recorrecting_replaces_rather_than_duplicates(self, db, user):
        categorizer.learn(db, user.id, "blinkit", "Shopping")
        categorizer.learn(db, user.id, "blinkit", "Groceries")

        rules = [r for r in categorizer.rules_for(db, user.id) if "blinkit" in r.merchant_key]
        assert len(rules) == 1
        assert rules[0].category == "Groceries"
        assert rules[0].hit_count == 2

    def test_quick_add_uses_a_learned_rule(self, db, user):
        categorizer.learn(db, user.id, "Chai Point", "Food Delivery")
        result = qa.parse(db, user.id, "60 Chai Point")
        assert result["category"] == "Food Delivery"
        assert result["category_source"] == "user_rule"

    def test_unknown_category_is_ignored(self, db, user):
        categorizer.learn(db, user.id, "somewhere", "Not A Category")
        assert categorizer.categorize(db, user.id, "somewhere", -100)["source"] != "user_rule"


class TestConfirmation:
    def test_reads_like_a_reply(self):
        assert "Transport" in qa.confirmation(-300, "Transport")
        assert "300" in qa.confirmation(-300, "Transport")

    def test_income_is_worded_differently(self):
        assert qa.confirmation(85000, "Salary").startswith("Recorded")
        assert qa.confirmation(-300, "Transport").startswith("Added")
