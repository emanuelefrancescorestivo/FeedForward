"""The diary as rows: what a person logged, and the days they showed up.

Revision ID: 004
Revises: 003
Create Date: 2026-10-07

Logged food moves out of the per-account document (user_state) into
diary_entries, one row per entry, so the server can read past days (weekly
progress, the recap) and two devices no longer overwrite each other
(DECISIONS.md, decision 24). activity_days records the days a person showed up.

Moving the diaries already saved is not done here: the API does it at start-up
(feedforward.db.diary_rows.migrate_state_diaries, idempotent), because tests
and local databases are created with create_all and never run Alembic.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diary_entries",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("meal", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("item_id", sa.String(80), nullable=False),
        sa.Column("servings", sa.Float(), nullable=False, server_default="1"),
        sa.Column("grams", sa.Float(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("kcal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("estimate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_diary_entries_user_day", "diary_entries", ["user_id", "day"])
    op.create_table(
        "activity_days",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("kind", sa.String(16), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("activity_days")
    op.drop_index("ix_diary_entries_user_day", table_name="diary_entries")
    op.drop_table("diary_entries")
