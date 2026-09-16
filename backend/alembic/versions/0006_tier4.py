"""Goal contributors, family links and donations.

Revision ID: 0006_tier4
Revises: 0005_report_unlocks
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_tier4"
down_revision = "0005_report_unlocks"
branch_labels = None
depends_on = None


def _has_table(name):
    return name in sa.inspect(op.get_bind()).get_table_names()


def _idx(table, name, cols):
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return
    if name not in {i["name"] for i in insp.get_indexes(table)}:
        op.create_index(name, table, cols)


def upgrade() -> None:
    if not _has_table("goal_contributors"):
        op.create_table(
            "goal_contributors",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("goal_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("relationship_label", sa.String(), nullable=True),
            sa.Column("monthly_amount", sa.Float(), nullable=True),
            sa.Column("committed_lump_sum", sa.Float(), nullable=True),
            sa.Column("contributed_so_far", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["goal_id"], ["goals.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _idx("goal_contributors", "ix_goal_contributors_id", ["id"])
    _idx("goal_contributors", "ix_goal_contributors_goal_id", ["goal_id"])
    _idx("goal_contributors", "ix_contrib_goal", ["goal_id"])

    if not _has_table("family_members"):
        op.create_table(
            "family_members",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.Integer(), nullable=True),
            sa.Column("member_user_id", sa.Integer(), nullable=True),
            sa.Column("invited_email", sa.String(), nullable=True),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("role", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("share_net_worth", sa.Boolean(), nullable=True),
            sa.Column("share_goals", sa.Boolean(), nullable=True),
            sa.Column("share_transactions", sa.Boolean(), nullable=True),
            sa.Column("invite_token", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("accepted_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["member_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("owner_id", "invited_email", name="uq_family_invite"),
        )
    for name, cols in (
        ("ix_family_members_id", ["id"]),
        ("ix_family_members_owner_id", ["owner_id"]),
        ("ix_family_members_member_user_id", ["member_user_id"]),
        ("ix_family_members_invited_email", ["invited_email"]),
        ("ix_family_members_invite_token", ["invite_token"]),
        ("ix_family_owner", ["owner_id", "status"]),
    ):
        _idx("family_members", name, cols)

    if not _has_table("donations"):
        op.create_table(
            "donations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("recipient", sa.String(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("donated_on", sa.DateTime(), nullable=True),
            sa.Column("is_80g_eligible", sa.Boolean(), nullable=True),
            sa.Column("receipt_ref", sa.String(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, cols in (
        ("ix_donations_id", ["id"]),
        ("ix_donations_user_id", ["user_id"]),
        ("ix_donation_user_date", ["user_id", "donated_on"]),
    ):
        _idx("donations", name, cols)


def downgrade() -> None:
    for table in ("donations", "family_members", "goal_contributors"):
        op.drop_table(table)
