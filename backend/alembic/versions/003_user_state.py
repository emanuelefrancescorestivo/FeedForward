"""What a person keeps in the app: one JSON document per user.

Revision ID: 003
Revises: 002
Create Date: 2026-10-06

The app (profile answers, preferences, food diary, shopping list) saves one
document per account, so the same person finds it on any device. A table of
its own: the users table is unchanged.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_state",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_state")
