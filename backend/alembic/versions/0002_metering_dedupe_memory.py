"""Usage metering, transaction de-duplication, editable memory, notifications.

Revision ID: 0002_metering
Revises: 0001_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_metering"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


# --- Idempotency helpers ---------------------------------------------------
# A deploy that ran before migrations shipped bootstrapped the database with
# create_all(), which created the NEW tables but could not add columns to the
# existing ones. This migration therefore has to run against a half-applied
# schema and create only what is genuinely missing.

def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def _has_unique_constraint(table: str, name: str) -> bool:
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    names = {c["name"] for c in insp.get_unique_constraints(table)}
    names |= {i["name"] for i in insp.get_indexes(table) if i.get("unique")}
    return name in names


def _add_columns(table: str, columns) -> None:
    """Add only the columns that are not already present."""
    missing = [c for c in columns if not _has_column(table, c.name)]
    if not missing:
        return
    with op.batch_alter_table(table) as batch:
        for column in missing:
            batch.add_column(column)


def _create_index(name: str, table: str, columns) -> None:
    if not _has_index(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    # --- users: plan + session revocation ---------------------------------
    _add_columns("users", [
        sa.Column("plan", sa.String(), nullable=False, server_default="free"),
        sa.Column("plan_renews_at", sa.DateTime(), nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    ])

    # --- transactions: dedupe identity ------------------------------------
    # Added nullable and backfilled at startup: existing rows have no hash yet,
    # and a NOT NULL column would fail on any populated database.
    _add_columns("transactions", [sa.Column("dedupe_hash", sa.String(), nullable=True)])
    _create_index("ix_transactions_dedupe_hash", "transactions", ["dedupe_hash"])
    _create_index("ix_txn_user_date", "transactions", ["user_id", "date"])
    if not _has_unique_constraint("transactions", "uq_txn_user_dedupe"):
        # SQLite needs the constraint created inside a batch (table rewrite).
        with op.batch_alter_table("transactions") as batch:
            batch.create_unique_constraint("uq_txn_user_dedupe", ["user_id", "dedupe_hash"])

    # --- memories: transparency + user control ----------------------------
    _add_columns("memories", [
        sa.Column("source", sa.String(), nullable=False, server_default="system"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ])

    # --- usage metering ----------------------------------------------------
    if not _has_table("usage_events"):
        op.create_table(
            "usage_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("kind", sa.String(), nullable=True),
            sa.Column("provider", sa.String(), nullable=True),
            sa.Column("model", sa.String(), nullable=True),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("cost_usd", sa.Float(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("ok", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("ix_usage_events_id", "usage_events", ["id"])
    _create_index("ix_usage_events_kind", "usage_events", ["kind"])
    _create_index("ix_usage_events_created_at", "usage_events", ["created_at"])
    _create_index("ix_usage_user_created", "usage_events", ["user_id", "created_at"])

    # --- derived-output cache ---------------------------------------------
    if not _has_table("insight_cache"):
        op.create_table(
            "insight_cache",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("kind", sa.String(), nullable=True),
            sa.Column("fingerprint", sa.String(), nullable=True),
            sa.Column("payload", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "kind", name="uq_insight_user_kind"),
        )
    _create_index("ix_insight_cache_id", "insight_cache", ["id"])
    _create_index("ix_insight_cache_user_id", "insight_cache", ["user_id"])
    _create_index("ix_insight_cache_fingerprint", "insight_cache", ["fingerprint"])

    # --- proactive nudges --------------------------------------------------
    if not _has_table("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("kind", sa.String(), nullable=True),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("severity", sa.String(), nullable=True),
            sa.Column("dedupe_key", sa.String(), nullable=True),
            sa.Column("read", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("ix_notifications_id", "notifications", ["id"])
    _create_index("ix_notifications_user_id", "notifications", ["user_id"])
    _create_index("ix_notifications_kind", "notifications", ["kind"])
    _create_index("ix_notifications_dedupe_key", "notifications", ["dedupe_key"])
    _create_index("ix_notif_user_created", "notifications", ["user_id", "created_at"])

    # --- product analytics -------------------------------------------------
    if not _has_table("analytics_events"):
        op.create_table(
            "analytics_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("props", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("ix_analytics_events_id", "analytics_events", ["id"])
    _create_index("ix_analytics_events_user_id", "analytics_events", ["user_id"])
    _create_index("ix_analytics_events_name", "analytics_events", ["name"])
    _create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])
    _create_index("ix_analytics_name_created", "analytics_events", ["name", "created_at"])


def downgrade() -> None:
    op.drop_table("analytics_events")
    op.drop_table("notifications")
    op.drop_table("insight_cache")
    op.drop_table("usage_events")

    with op.batch_alter_table("memories") as batch:
        for col in ("updated_at", "muted", "pinned", "source"):
            batch.drop_column(col)

    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("uq_txn_user_dedupe", type_="unique")
    op.drop_index("ix_txn_user_date", table_name="transactions")
    op.drop_index("ix_transactions_dedupe_hash", table_name="transactions")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("dedupe_hash")

    with op.batch_alter_table("users") as batch:
        for col in ("token_version", "plan_renews_at", "plan"):
            batch.drop_column(col)
