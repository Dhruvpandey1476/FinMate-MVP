"""Paid report unlocks.

Revision ID: 0005_report_unlocks
Revises: 0004_merchant_rules
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_report_unlocks"
down_revision = "0004_merchant_rules"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    if not _has_table("report_unlocks"):
        op.create_table(
            "report_unlocks",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("report_id", sa.String(), nullable=True),
            sa.Column("price_inr", sa.Integer(), nullable=True),
            sa.Column("payment_ref", sa.String(), nullable=True),
            sa.Column("unlocked_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "report_id", name="uq_report_unlock"),
        )
    for name, cols in (
        ("ix_report_unlocks_id", ["id"]),
        ("ix_report_unlocks_user_id", ["user_id"]),
        ("ix_report_unlocks_report_id", ["report_id"]),
    ):
        if not _has_index("report_unlocks", name):
            op.create_index(name, "report_unlocks", cols)


def downgrade() -> None:
    op.drop_table("report_unlocks")
