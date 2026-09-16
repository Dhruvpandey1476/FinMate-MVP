"""Per-user merchant categorisation rules (the correction loop).

Revision ID: 0004_merchant_rules
Revises: 0003_checkpoints
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_merchant_rules"
down_revision = "0003_checkpoints"
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
    if not _has_table("merchant_rules"):
        op.create_table(
            "merchant_rules",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("merchant_key", sa.String(), nullable=True),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("hit_count", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "merchant_key", name="uq_merchant_rule"),
        )
    for name, cols in (
        ("ix_merchant_rules_id", ["id"]),
        ("ix_merchant_rules_user_id", ["user_id"]),
        ("ix_merchant_rules_merchant_key", ["merchant_key"]),
    ):
        if not _has_index("merchant_rules", name):
            op.create_index(name, "merchant_rules", cols)


def downgrade() -> None:
    op.drop_table("merchant_rules")
