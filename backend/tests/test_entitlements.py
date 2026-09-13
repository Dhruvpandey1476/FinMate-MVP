"""
Quotas, burst limiting and cost metering.

This is the layer that stops one scripted user draining a month of LLM budget
in an hour, and the layer that makes gross margin a query instead of a guess.
"""
from datetime import datetime, timedelta

import pytest

from app import models
from app.services import entitlements


class TestPlans:
    def test_default_plan_is_free(self, user):
        assert entitlements.plan_for(user)["label"] == "Free"

    def test_unknown_plan_falls_back_to_free(self, db, user):
        user.plan = "enterprise-unicorn"
        db.commit()
        assert entitlements.plan_for(user)["label"] == "Free"

    def test_paid_plans_unlock_features(self, db, user):
        assert entitlements.feature_enabled(user, "monte_carlo") is False
        user.plan = "plus"
        db.commit()
        assert entitlements.feature_enabled(user, "monte_carlo") is True
        assert entitlements.feature_enabled(user, "debt_optimizer") is True

    def test_pro_has_unlimited_chat(self, db, user):
        user.plan = "pro"
        db.commit()
        assert entitlements.check_quota(db, user, "chat")["limit"] == -1


class TestQuota:
    def test_fresh_user_is_allowed(self, db, user):
        q = entitlements.check_quota(db, user, "chat")
        assert q["allowed"] is True
        assert q["used"] == 0

    def test_quota_blocks_once_exhausted(self, db, user):
        limit = entitlements.PLANS["free"]["chat_messages"]
        for _ in range(limit):
            entitlements.record_usage(db, user.id, "chat", "groq", "llama", 100, 50)

        q = entitlements.check_quota(db, user, "chat")
        assert q["used"] == limit
        assert q["remaining"] == 0
        assert q["allowed"] is False

    def test_unmetered_action_is_always_allowed(self, db, user):
        assert entitlements.check_quota(db, user, "insights")["allowed"] is True

    def test_usage_from_last_month_does_not_count(self, db, user):
        old = datetime.utcnow().replace(day=1) - timedelta(days=5)
        for _ in range(50):
            db.add(models.UsageEvent(user_id=user.id, kind="chat", created_at=old))
        db.commit()

        assert entitlements.check_quota(db, user, "chat")["allowed"] is True

    def test_quotas_are_per_user(self, db, user):
        other = models.User(name="Other", email="other-quota@finmate.test")
        db.add(other)
        db.commit()
        db.refresh(other)

        for _ in range(entitlements.PLANS["free"]["chat_messages"]):
            entitlements.record_usage(db, user.id, "chat", "groq")

        assert entitlements.check_quota(db, user, "chat")["allowed"] is False
        assert entitlements.check_quota(db, other, "chat")["allowed"] is True

    def test_summary_shape_for_the_ui(self, db, user):
        summary = entitlements.quota_summary(db, user)
        assert summary["plan"] == "free"
        assert set(summary["quotas"]) == {"chat", "simulate", "upload"}
        assert "monte_carlo" in summary["features"]


class TestCost:
    def test_cost_scales_with_tokens(self):
        small = entitlements.estimate_cost_usd("groq", 1000, 500)
        large = entitlements.estimate_cost_usd("groq", 100_000, 50_000)
        assert large > small > 0

    def test_rule_based_is_free(self):
        assert entitlements.estimate_cost_usd("rule_based", 1000, 1000) == 0.0

    def test_unknown_provider_costs_nothing(self):
        assert entitlements.estimate_cost_usd("mystery", 1000, 1000) == 0.0

    def test_report_aggregates_by_provider(self, db, user):
        entitlements.record_usage(db, user.id, "chat", "groq", "llama", 1000, 500)
        entitlements.record_usage(db, user.id, "chat", "groq", "llama", 2000, 800)
        entitlements.record_usage(db, user.id, "insights", "gemini", "flash", 500, 200)

        report = entitlements.cost_report(db, user_id=user.id)
        providers = {r["provider"]: r for r in report["by_provider"]}
        assert providers["groq"]["calls"] == 2
        assert providers["groq"]["prompt_tokens"] == 3000
        assert report["total_cost_usd"] > 0

    def test_metering_never_raises(self, db):
        """Telemetry must not be able to break a user request."""
        entitlements.record_usage(db, None, "chat", "groq", "x", None, None)


class TestBurstLimiter:
    def test_allows_under_the_limit(self):
        limit = entitlements.BURST_LIMITS["chat"][0]
        for i in range(limit):
            assert entitlements.check_burst("u1", "chat")["allowed"], f"blocked at {i}"

    def test_blocks_over_the_limit(self):
        limit = entitlements.BURST_LIMITS["chat"][0]
        for _ in range(limit):
            entitlements.check_burst("u2", "chat")

        verdict = entitlements.check_burst("u2", "chat")
        assert verdict["allowed"] is False
        assert verdict["retry_after"] >= 1

    def test_keys_are_independent(self):
        limit = entitlements.BURST_LIMITS["chat"][0]
        for _ in range(limit):
            entitlements.check_burst("u3", "chat")

        assert entitlements.check_burst("u3", "chat")["allowed"] is False
        assert entitlements.check_burst("u4", "chat")["allowed"] is True

    def test_kinds_are_independent(self):
        limit = entitlements.BURST_LIMITS["chat"][0]
        for _ in range(limit):
            entitlements.check_burst("u5", "chat")

        assert entitlements.check_burst("u5", "chat")["allowed"] is False
        assert entitlements.check_burst("u5", "simulate")["allowed"] is True
