"""Balance checkpoints for Safe-to-Spend.

Revision ID: 0003_checkpoints
Revises: 0002_metering
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_checkpoints"
down_revision = "0002_metering"
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
    # Guarded like 0002: a database bootstrapped by create_all() before this
    # migration existed already has the table.
    if not _has_table("balance_checkpoints"):
        op.create_table(
            "balance_checkpoints",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("balance", sa.Float(), nullable=False),
            sa.Column("as_of", sa.DateTime(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("source", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    for name, cols in (
        ("ix_balance_checkpoints_id", ["id"]),
        ("ix_balance_checkpoints_user_id", ["user_id"]),
        ("ix_balance_checkpoints_as_of", ["as_of"]),
        ("ix_checkpoint_user_date", ["user_id", "as_of"]),
    ):
        if not _has_index("balance_checkpoints", name):
            op.create_index(name, "balance_checkpoints", cols)


def downgrade() -> None:
    op.drop_table("balance_checkpoints")
