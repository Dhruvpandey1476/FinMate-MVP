"""
Migrations must survive a half-applied schema.

A deploy shipped before the migration files were in the image. Startup fell
back to create_all(), which created the NEW tables but could not add columns
to existing ones. The next deploy then ran 0002 against a database where
`usage_events` already existed and died on "relation already exists".

These tests run the real migration against each shape of database a live
deployment can actually be in.
"""
import os
import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / f'mig_{uuid.uuid4().hex[:8]}.db'}"


def _run_migrations(db_url: str, target: str = "head"):
    """Run Alembic against an arbitrary database, isolated from app state."""
    from app.database_migrations import _alembic_config

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    try:
        cfg = _alembic_config()
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, target)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


class TestFullMigration:
    def test_builds_the_whole_schema_from_empty(self, db_url):
        _run_migrations(db_url)
        engine = create_engine(db_url)
        tables = set(inspect(engine).get_table_names())

        assert {"users", "transactions", "memories"} <= tables
        assert {"usage_events", "insight_cache", "notifications", "analytics_events"} <= tables
        assert "plan" in _columns(engine, "users")
        assert "dedupe_hash" in _columns(engine, "transactions")


class TestHalfAppliedSchema:
    """The exact state the failed deploy left the production database in."""

    def test_survives_new_tables_already_existing(self, db_url):
        # Baseline schema...
        _run_migrations(db_url, "0001_baseline")

        engine = create_engine(db_url)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (name, email, hashed_password) "
                "VALUES ('Real User', 'demo@finmate.ai', 'x')"
            ))
            # ...plus the tables create_all() managed to add, but none of the
            # columns it could not add to existing tables.
            conn.execute(text(
                "CREATE TABLE usage_events (id INTEGER PRIMARY KEY, user_id INTEGER, "
                "kind VARCHAR, provider VARCHAR, model VARCHAR, prompt_tokens INTEGER, "
                "completion_tokens INTEGER, cost_usd FLOAT, latency_ms INTEGER, "
                "ok BOOLEAN, created_at DATETIME)"
            ))
            conn.execute(text(
                "CREATE TABLE notifications (id INTEGER PRIMARY KEY, user_id INTEGER, "
                "kind VARCHAR, title VARCHAR, body TEXT, severity VARCHAR, "
                "dedupe_key VARCHAR, read BOOLEAN, created_at DATETIME)"
            ))
            conn.execute(text("DROP TABLE alembic_version"))

        from app.database_migrations import _alembic_config
        cfg = _alembic_config()
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.stamp(cfg, "0001_baseline")

        # This is what crashed the deploy.
        _run_migrations(db_url)

        engine = create_engine(db_url)
        assert "plan" in _columns(engine, "users")
        assert "token_version" in _columns(engine, "users")
        assert "source" in _columns(engine, "memories")
        assert "dedupe_hash" in _columns(engine, "transactions")

        with engine.connect() as conn:
            rows = conn.execute(text("SELECT name, email FROM users")).fetchall()
        assert rows == [("Real User", "demo@finmate.ai")], "existing rows must survive"

    def test_survives_columns_already_existing(self, db_url):
        """Partial column application must not abort the rest of the migration."""
        _run_migrations(db_url, "0001_baseline")

        engine = create_engine(db_url)
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN plan VARCHAR DEFAULT 'free'"))
            conn.execute(text("DROP TABLE alembic_version"))

        from app.database_migrations import _alembic_config
        cfg = _alembic_config()
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.stamp(cfg, "0001_baseline")

        _run_migrations(db_url)

        engine = create_engine(db_url)
        cols = _columns(engine, "users")
        assert {"plan", "plan_renews_at", "token_version"} <= cols


class TestEnsureSchemaPaths:
    """ensure_schema() must pick the right revision to stamp."""

    def _ensure(self, db_url, monkeypatch):
        """
        Point ensure_schema at a throwaway database.

        The engine and URL are patched rather than reloading app.database:
        a reload would rebind Base while app.models still referenced the old
        one, leaving the metadata comparison with nothing to compare.
        """
        from app import database_migrations

        engine = create_engine(db_url)
        monkeypatch.setattr(database_migrations, "engine", engine)
        monkeypatch.setattr(database_migrations, "DATABASE_URL", db_url)
        return database_migrations.ensure_schema()

    def test_empty_database_migrates_from_scratch(self, db_url, monkeypatch):
        assert self._ensure(db_url, monkeypatch) == "0002_metering"
        assert "plan" in _columns(create_engine(db_url), "users")

    def test_legacy_database_is_upgraded_not_skipped(self, db_url, monkeypatch):
        """The production case: old schema, real rows, no alembic_version."""
        _run_migrations(db_url, "0001_baseline")
        engine = create_engine(db_url)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (name, email, hashed_password) "
                "VALUES ('Legacy', 'legacy@finmate.test', 'x')"
            ))
            conn.execute(text("DROP TABLE alembic_version"))
        engine.dispose()

        assert self._ensure(db_url, monkeypatch) == "0002_metering"

        engine = create_engine(db_url)
        assert "plan" in _columns(engine, "users"), "legacy schema was skipped, not migrated"
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 1

    def test_current_schema_is_stamped_not_re_migrated(self, db_url, monkeypatch):
        """A create_all() database already has every column; stamp it at head."""
        from app.database import Base
        from app import models  # noqa: F401

        engine = create_engine(db_url)
        Base.metadata.create_all(bind=engine)
        engine.dispose()

        assert self._ensure(db_url, monkeypatch) == "0002_metering"
        assert "plan" in _columns(create_engine(db_url), "users")
