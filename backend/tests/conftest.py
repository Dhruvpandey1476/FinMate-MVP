"""
Shared test fixtures.

DATABASE_URL is set before any app module is imported, because app.database
builds its engine at import time. Each test module gets its own SQLite file so
tests never share state or touch the developer's real finmate.db.
"""
import os
import tempfile
import uuid

import pytest

_TEST_DIR = tempfile.mkdtemp(prefix="finmate-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test_{uuid.uuid4().hex}.db"
os.environ["JWT_SECRET"] = "test-secret-not-used-in-production"
os.environ["ENV"] = "test"
os.environ["ADMIN_KEY"] = "test-admin-key"
os.environ["CRON_KEY"] = "test-cron-key"
# No LLM keys: every test exercises the deterministic path, so the suite is
# offline, fast and free.
#
# These are set to "" rather than deleted on purpose. app.main calls
# load_dotenv(), which fills in any key that is *absent* from the environment -
# so deleting them would let the developer's real .env leak in and the test
# suite would start making billable API calls.
for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
            "POSTHOG_API_KEY", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID",
            "RESEND_API_KEY", "QDRANT_URL", "NEO4J_URI"):
    os.environ[key] = ""

from app.database import Base, engine, SessionLocal  # noqa: E402
from app import models  # noqa: E402,F401


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def user(db):
    """A fresh, isolated user for each test."""
    u = models.User(
        name="Test User",
        email=f"test-{uuid.uuid4().hex[:8]}@finmate.test",
        hashed_password="",
        monthly_income=100000,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """The burst limiter is process-global; clear it between tests."""
    from app.services import entitlements
    entitlements.reset_burst_state()
    yield
    entitlements.reset_burst_state()
