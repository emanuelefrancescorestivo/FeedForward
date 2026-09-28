"""Initial users and corpus schema.

Revision ID: 001
Revises:
Create Date: 2026-09-24

The models in feedforward.db.models are the source of this revision. Column
types are portable (no JSONB, no arrays) so the same migration runs on
PostgreSQL, which is the production dialect, and on SQLite, which is only
the test double.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("tier", sa.String(32), nullable=False, server_default="consumer"),
        sa.Column("demographic", sa.String(32), nullable=True),
        sa.Column("dietary_restrictions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "nutrients",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False, server_default=""),
    )
    op.create_table(
        "foods",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(400), nullable=False),
        sa.Column("category", sa.String(400), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=True),
        sa.Column("nutri_score", sa.String(8), nullable=False, server_default=""),
        sa.Column("nova", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_animal_source", sa.Boolean(), nullable=True),
        sa.Column("micronutrient_trusted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("barcode", sa.String(32), nullable=True),
    )
    op.create_index("ix_foods_name", "foods", ["name"])
    op.create_index("ix_foods_source", "foods", ["source"])

    op.create_table(
        "food_nutrients",
        sa.Column("food_id", sa.String(64), sa.ForeignKey("foods.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("nutrient_id", sa.String(64), sa.ForeignKey("nutrients.id"), primary_key=True),
        sa.Column("amount_per_100g", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False, server_default=""),
        sa.Column("trusted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reject_reason", sa.String(200), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default=""),
    )
    op.create_table(
        "goals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("system", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("icd10_refs", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "goal_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nutrient_id", sa.String(64), sa.ForeignKey("nutrients.id"), nullable=False),
        sa.Column("goal_id", sa.String(64), sa.ForeignKey("goals.id"), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("edge_type", sa.String(16), nullable=False, server_default="positive"),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_source", sa.String(32), nullable=False, server_default="default"),
        sa.Column("evidence_grade", sa.String(2), nullable=True),
        sa.Column("low_confidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("nutrient_id", "goal_id", name="uq_goal_edge"),
    )
    op.create_index("ix_goal_edges_nutrient", "goal_edges", ["nutrient_id"])
    op.create_index("ix_goal_edges_goal", "goal_edges", ["goal_id"])

    op.create_table(
        "interactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("modifier", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("factor", sa.Float(), nullable=False),
        sa.Column("mechanism", sa.Text(), nullable=False),
        sa.Column("evidence", sa.String(2), nullable=False, server_default="C"),
        sa.Column("dose_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("low_confidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("target", "modifier", name="uq_interaction"),
    )
    op.create_index("ix_interactions_target", "interactions", ["target"])

    op.create_table(
        "evidence_citations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pmid", sa.String(16), nullable=True),
        sa.Column("doi", sa.String(120), nullable=True),
        sa.Column("citation_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default="curated"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("goal_edge_id", sa.Integer(), sa.ForeignKey("goal_edges.id", ondelete="CASCADE"), nullable=True),
        sa.Column("interaction_id", sa.Integer(), sa.ForeignKey("interactions.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_citations_pmid", "evidence_citations", ["pmid"])


def downgrade() -> None:
    op.drop_table("evidence_citations")
    op.drop_table("interactions")
    op.drop_table("goal_edges")
    op.drop_table("goals")
    op.drop_table("food_nutrients")
    op.drop_table("foods")
    op.drop_table("nutrients")
    op.drop_table("users")
