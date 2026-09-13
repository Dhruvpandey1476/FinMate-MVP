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


def upgrade() -> None:
    # --- users: plan + session revocation ---------------------------------
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("plan", sa.String(), nullable=False, server_default="free"))
        batch.add_column(sa.Column("plan_renews_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))

    # --- transactions: dedupe identity ------------------------------------
    # Added nullable and backfilled at startup: existing rows have no hash yet,
    # and a NOT NULL column would fail on any populated database.
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("dedupe_hash", sa.String(), nullable=True))
    op.create_index("ix_transactions_dedupe_hash", "transactions", ["dedupe_hash"])
    op.create_index("ix_txn_user_date", "transactions", ["user_id", "date"])
    # SQLite needs the constraint created inside a batch (table rewrite).
    with op.batch_alter_table("transactions") as batch:
        batch.create_unique_constraint("uq_txn_user_dedupe", ["user_id", "dedupe_hash"])

    # --- memories: transparency + user control ----------------------------
    with op.batch_alter_table("memories") as batch:
        batch.add_column(sa.Column("source", sa.String(), nullable=False, server_default="system"))
        batch.add_column(sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    # --- usage metering ----------------------------------------------------
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
    op.create_index("ix_usage_events_id", "usage_events", ["id"])
    op.create_index("ix_usage_events_kind", "usage_events", ["kind"])
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])
    op.create_index("ix_usage_user_created", "usage_events", ["user_id", "created_at"])

    # --- derived-output cache ---------------------------------------------
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
    op.create_index("ix_insight_cache_id", "insight_cache", ["id"])
    op.create_index("ix_insight_cache_user_id", "insight_cache", ["user_id"])
    op.create_index("ix_insight_cache_fingerprint", "insight_cache", ["fingerprint"])

    # --- proactive nudges --------------------------------------------------
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
    op.create_index("ix_notifications_id", "notifications", ["id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_kind", "notifications", ["kind"])
    op.create_index("ix_notifications_dedupe_key", "notifications", ["dedupe_key"])
    op.create_index("ix_notif_user_created", "notifications", ["user_id", "created_at"])

    # --- product analytics -------------------------------------------------
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
    op.create_index("ix_analytics_events_id", "analytics_events", ["id"])
    op.create_index("ix_analytics_events_user_id", "analytics_events", ["user_id"])
    op.create_index("ix_analytics_events_name", "analytics_events", ["name"])
    op.create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])
    op.create_index("ix_analytics_name_created", "analytics_events", ["name", "created_at"])


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
