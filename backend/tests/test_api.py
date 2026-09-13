"""
End-to-end API tests.

Runs against the real FastAPI app with a TestClient. No LLM keys are set, so
every agent takes its deterministic path - the suite is offline and free.
"""
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import models
from app.database import SessionLocal


@pytest.fixture(scope="module")
def client():
    # The lifespan runs migrations and seeds; tests use create_all from conftest,
    # so it is skipped here to keep the suite fast and hermetic.
    with TestClient(app) as c:
        yield c


@pytest.fixture
def account(client):
    """A registered user plus an auth header."""
    email = f"api-{uuid.uuid4().hex[:8]}@finmate.test"
    resp = client.post("/api/auth/signup", json={
        "name": "API Tester", "email": email, "password": "supersecret123",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {
        "email": email,
        "token": body["token"],
        "headers": {"Authorization": f"Bearer {body['token']}"},
        "id": body["user"]["id"],
    }


class TestHealth:
    def test_root(self, client):
        assert client.get("/").status_code == 200

    def test_health_reports_llm_state(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["llm"]["configured"] is False  # no keys in the test env

    def test_request_id_header_is_set(self, client):
        assert client.get("/").headers.get("X-Request-ID")


class TestAuth:
    def test_signup_returns_token(self, client):
        resp = client.post("/api/auth/signup", json={
            "name": "New", "email": f"new-{uuid.uuid4().hex[:6]}@t.test",
            "password": "longenoughpassword",
        })
        assert resp.status_code == 200
        assert resp.json()["token"]

    def test_short_password_rejected(self, client):
        resp = client.post("/api/auth/signup", json={
            "name": "X", "email": f"x-{uuid.uuid4().hex[:6]}@t.test", "password": "short",
        })
        assert resp.status_code == 400

    def test_duplicate_email_rejected(self, client, account):
        resp = client.post("/api/auth/signup", json={
            "name": "Dup", "email": account["email"], "password": "longenoughpassword",
        })
        assert resp.status_code == 400

    def test_login_works_and_wrong_password_does_not(self, client, account):
        ok = client.post("/api/auth/login", json={
            "email": account["email"], "password": "supersecret123",
        })
        assert ok.status_code == 200

        bad = client.post("/api/auth/login", json={
            "email": account["email"], "password": "wrongpassword",
        })
        assert bad.status_code == 401

    def test_protected_route_requires_a_token(self, client):
        assert client.get("/api/twin/snapshot").status_code == 401

    def test_garbage_token_rejected(self, client):
        resp = client.get("/api/twin/snapshot",
                          headers={"Authorization": "Bearer not-a-real-token"})
        assert resp.status_code == 401

    def test_logout_all_revokes_old_tokens(self, client, account):
        """A leaked token must stop working immediately, not in 30 days."""
        old_headers = account["headers"]
        assert client.get("/api/auth/me", headers=old_headers).status_code == 200

        resp = client.post("/api/auth/logout-all", headers=old_headers)
        assert resp.status_code == 200
        new_token = resp.json()["token"]

        assert client.get("/api/auth/me", headers=old_headers).status_code == 401
        assert client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {new_token}"}
        ).status_code == 200


class TestDataIsolation:
    def test_users_cannot_see_each_others_data(self, client):
        a = client.post("/api/auth/signup", json={
            "name": "A", "email": f"iso-a-{uuid.uuid4().hex[:6]}@t.test",
            "password": "longenoughpassword"}).json()
        b = client.post("/api/auth/signup", json={
            "name": "B", "email": f"iso-b-{uuid.uuid4().hex[:6]}@t.test",
            "password": "longenoughpassword"}).json()

        ha = {"Authorization": f"Bearer {a['token']}"}
        hb = {"Authorization": f"Bearer {b['token']}"}

        client.post("/api/profile/transactions", headers=ha, json={
            "amount": -1234, "category": "SecretCategory", "type": "expense"})

        b_txns = client.get("/api/profile/transactions", headers=hb).json()
        assert all(t["category"] != "SecretCategory" for t in b_txns)

    def test_cannot_delete_another_users_goal(self, client):
        a = client.post("/api/auth/signup", json={
            "name": "A", "email": f"g-a-{uuid.uuid4().hex[:6]}@t.test",
            "password": "longenoughpassword"}).json()
        b = client.post("/api/auth/signup", json={
            "name": "B", "email": f"g-b-{uuid.uuid4().hex[:6]}@t.test",
            "password": "longenoughpassword"}).json()

        ha = {"Authorization": f"Bearer {a['token']}"}
        hb = {"Authorization": f"Bearer {b['token']}"}

        goal = client.post("/api/goals/", headers=ha, json={
            "name": "Private Goal", "target_amount": 100000}).json()

        assert client.delete(f"/api/goals/{goal['id']}", headers=hb).status_code == 404


class TestTwin:
    def test_snapshot_includes_health_breakdown(self, client, account):
        body = client.get("/api/twin/snapshot", headers=account["headers"]).json()
        assert "financial_health_score" in body
        assert isinstance(body["health_breakdown"], list)
        assert len(body["health_breakdown"]) >= 3

    def test_cashflow_series_length(self, client, account):
        body = client.get("/api/twin/cashflow-series?months=6",
                          headers=account["headers"]).json()
        assert len(body) == 6


class TestTransactions:
    def test_add_and_list(self, client, account):
        resp = client.post("/api/profile/transactions", headers=account["headers"], json={
            "amount": -500, "category": "Food", "type": "expense", "merchant": "Swiggy"})
        assert resp.status_code == 200

        txns = client.get("/api/profile/transactions", headers=account["headers"]).json()
        assert any(t["merchant"] == "Swiggy" for t in txns)

    def test_duplicate_transaction_is_rejected(self, client, account):
        payload = {"amount": -777, "category": "Food", "type": "expense",
                   "merchant": "DupTest", "date": "2026-04-01T00:00:00"}
        assert client.post("/api/profile/transactions",
                           headers=account["headers"], json=payload).status_code == 200
        assert client.post("/api/profile/transactions",
                           headers=account["headers"], json=payload).status_code == 409

    def test_zero_amount_rejected(self, client, account):
        resp = client.post("/api/profile/transactions", headers=account["headers"], json={
            "amount": 0, "category": "Food", "type": "expense"})
        assert resp.status_code == 400

    def test_pagination(self, client, account):
        for i in range(5):
            client.post("/api/profile/transactions", headers=account["headers"], json={
                "amount": -(100 + i), "category": "Page", "type": "expense",
                "merchant": f"M{i}"})

        page = client.get("/api/profile/transactions?limit=2",
                          headers=account["headers"]).json()
        assert len(page) == 2


class TestUploadDedup:
    CSV = (
        "Date,Description,Amount\n"
        "2026-03-01,SWIGGY ORDER,-450\n"
        "2026-03-02,UBER RIDE,-220\n"
        "2026-03-03,SALARY CREDIT,85000\n"
    )

    def _upload(self, client, account):
        return client.post(
            "/api/upload/csv",
            headers=account["headers"],
            files={"file": ("statement.csv", io.BytesIO(self.CSV.encode()), "text/csv")},
        )

    def test_first_upload_imports(self, client, account):
        resp = self._upload(client, account)
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_inserted"] > 0

    def test_second_upload_of_same_file_imports_nothing(self, client, account):
        """The bug that silently doubled every user's spending."""
        first = self._upload(client, account).json()
        second = self._upload(client, account).json()

        assert second["total_inserted"] == 0
        assert second["duplicates_skipped"] == first["total_inserted"]
        assert "already imported" in second["message"]

    def test_rejects_wrong_extension(self, client, account):
        resp = client.post(
            "/api/upload/csv", headers=account["headers"],
            files={"file": ("x.txt", io.BytesIO(b"nope"), "text/plain")},
        )
        assert resp.status_code == 400


class TestQuotasAndLimits:
    def test_chat_quota_exhausts_and_returns_402(self, client, account):
        db = SessionLocal()
        try:
            from app.services import entitlements
            limit = entitlements.PLANS["free"]["chat_messages"]
            for _ in range(limit):
                entitlements.record_usage(db, account["id"], "chat", "rule_based")
        finally:
            db.close()

        resp = client.post("/api/chat/", headers=account["headers"],
                           json={"message": "Am I overspending on food?"})
        assert resp.status_code == 402
        assert "Upgrade" in resp.json()["detail"]

    def test_burst_limit_returns_429(self, client, account):
        from app.services import entitlements
        limit = entitlements.BURST_LIMITS["simulate"][0]

        codes = []
        for _ in range(limit + 3):
            r = client.post("/api/simulate/", headers=account["headers"], json={
                "scenario_type": "savings", "amount": 1000, "months_ahead": 12})
            codes.append(r.status_code)

        assert 429 in codes
        blocked = next(c for c in codes if c == 429)
        assert blocked == 429

    def test_empty_chat_message_rejected(self, client, account):
        resp = client.post("/api/chat/", headers=account["headers"], json={"message": "   "})
        assert resp.status_code in (400, 422)

    def test_overlong_chat_message_rejected(self, client, account):
        resp = client.post("/api/chat/", headers=account["headers"],
                           json={"message": "x" * 5000})
        assert resp.status_code in (400, 422)


class TestMemoryCRUD:
    def test_create_edit_pin_and_delete(self, client, account):
        h = account["headers"]

        created = client.post("/api/memory/", headers=h, json={
            "memory_type": "semantic",
            "content": "User supports their parents financially.",
            "importance": 0.9,
        })
        assert created.status_code == 200
        mem = created.json()
        assert mem["source"] == "user"

        edited = client.patch(f"/api/memory/{mem['id']}", headers=h, json={
            "content": "User supports both parents and a sibling.", "pinned": True})
        assert edited.status_code == 200
        assert edited.json()["pinned"] is True
        assert "sibling" in edited.json()["content"]

        assert client.delete(f"/api/memory/{mem['id']}", headers=h).status_code == 200
        assert client.delete(f"/api/memory/{mem['id']}", headers=h).status_code == 404

    def test_cannot_edit_another_users_memory(self, client, account):
        other = client.post("/api/auth/signup", json={
            "name": "O", "email": f"mem-{uuid.uuid4().hex[:6]}@t.test",
            "password": "longenoughpassword"}).json()

        mem = client.post("/api/memory/", headers=account["headers"], json={
            "memory_type": "semantic", "content": "Private fact about me."}).json()

        resp = client.patch(f"/api/memory/{mem['id']}",
                            headers={"Authorization": f"Bearer {other['token']}"},
                            json={"content": "hacked"})
        assert resp.status_code == 404

    def test_invalid_memory_type_rejected(self, client, account):
        resp = client.post("/api/memory/", headers=account["headers"], json={
            "memory_type": "telepathic", "content": "some content here"})
        assert resp.status_code == 400


class TestFeatureGating:
    def test_debt_optimizer_blocked_on_free_plan(self, client, account):
        resp = client.get("/api/debt/plan", headers=account["headers"])
        assert resp.status_code == 402

    def test_debt_optimizer_allowed_on_plus(self, client, account):
        db = SessionLocal()
        try:
            u = db.query(models.User).filter(models.User.id == account["id"]).first()
            u.plan = "plus"
            db.commit()
        finally:
            db.close()

        assert client.get("/api/debt/plan", headers=account["headers"]).status_code == 200

    def test_plan_endpoint_reports_quota(self, client, account):
        body = client.get("/api/auth/plan", headers=account["headers"]).json()
        assert "quotas" in body and "chat" in body["quotas"]

    def test_public_pricing_table(self, client):
        plans = client.get("/api/auth/plans").json()
        assert {p["id"] for p in plans} == {"free", "plus", "pro"}


class TestForecastEndpoints:
    def test_forecast_returns_series(self, client, account):
        body = client.get("/api/forecast/?days=30", headers=account["headers"]).json()
        assert body["horizon_days"] == 30
        assert len(body["series"]) == 31

    def test_recurring_endpoint(self, client, account):
        body = client.get("/api/forecast/recurring", headers=account["headers"]).json()
        assert "expenses" in body and "income" in body

    def test_budget_endpoint(self, client, account):
        assert client.get("/api/forecast/budget",
                          headers=account["headers"]).status_code == 200


class TestNotifications:
    def test_refresh_and_list(self, client, account):
        assert client.post("/api/notifications/refresh",
                           headers=account["headers"]).status_code == 200
        assert client.get("/api/notifications",
                          headers=account["headers"]).status_code == 200

    def test_cron_requires_key(self, client):
        assert client.post("/api/digest/run").status_code == 401
        assert client.post("/api/digest/run?key=wrong").status_code == 401
        assert client.post("/api/digest/run?key=test-cron-key").status_code == 200


class TestAdmin:
    def test_stats_require_key(self, client):
        assert client.get("/api/admin/stats").status_code == 401
        assert client.get("/api/admin/stats?key=test-admin-key").status_code == 200

    def test_funnel_reports_steps(self, client, account):
        body = client.get("/api/admin/funnel?key=test-admin-key").json()
        steps = [s["step"] for s in body["funnel"]["steps"]]
        assert "signup" in steps
        # Signing up in this module must be visible in the funnel.
        signup = next(s for s in body["funnel"]["steps"] if s["step"] == "signup")
        assert signup["users"] >= 1


class TestAccountDeletion:
    def test_delete_account_removes_everything(self, client):
        acct = client.post("/api/auth/signup", json={
            "name": "Deleting", "email": f"del-{uuid.uuid4().hex[:6]}@t.test",
            "password": "longenoughpassword"}).json()
        h = {"Authorization": f"Bearer {acct['token']}"}

        client.post("/api/profile/transactions", headers=h, json={
            "amount": -100, "category": "Food", "type": "expense"})

        assert client.delete("/api/profile/account", headers=h).status_code == 200
        # Token now refers to a user that no longer exists.
        assert client.get("/api/auth/me", headers=h).status_code == 401
