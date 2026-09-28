"""Nutrient ontology, source provenance, multilingual food names.

Revision ID: 002
Revises: 001
Create Date: 2026-09-26

Adds the tables importers resolve through (nutrient_aliases), the provenance
registry every food points at (sources), multilingual names (food_names) and
the cross-source food identity (food_concepts). Existing rows keep working:
every new column is nullable or has a server default. Column changes use
batch mode so the same revision runs on SQLite, which cannot ALTER a
constraint in place.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(64), nullable=False, server_default=""),
        sa.Column("licence", sa.String(200), nullable=False, server_default=""),
        sa.Column("url", sa.String(400), nullable=True),
        sa.Column("country", sa.String(8), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "food_concepts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label_en", sa.String(400), nullable=False, server_default=""),
        sa.Column("label_it", sa.String(400), nullable=False, server_default=""),
        sa.Column("category", sa.String(200), nullable=False, server_default=""),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="unreviewed"),
    )
    op.create_table(
        "nutrient_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nutrient_id", sa.String(64),
                  sa.ForeignKey("nutrients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(200), nullable=False),
        sa.Column("alias_norm", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("lang", sa.String(8), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint("kind", "source", "lang", "alias_norm", name="uq_nutrient_alias"),
    )
    op.create_index("ix_nutrient_aliases_nutrient_id", "nutrient_aliases", ["nutrient_id"])
    op.create_index("ix_nutrient_aliases_alias_norm", "nutrient_aliases", ["alias_norm"])
    op.create_table(
        "food_names",
        sa.Column("food_id", sa.String(64),
                  sa.ForeignKey("foods.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("lang", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(400), nullable=False),
    )

    with op.batch_alter_table("nutrients") as batch:
        batch.add_column(sa.Column("infoods_tag", sa.String(16), nullable=True))
        batch.add_column(sa.Column("nutrient_group", sa.String(16), nullable=False, server_default=""))

    with op.batch_alter_table("foods") as batch:
        batch.add_column(sa.Column("source_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("concept_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("name_lang", sa.String(8), nullable=False, server_default=""))
        batch.create_foreign_key("fk_foods_source_id", "sources", ["source_id"], ["id"])
        batch.create_foreign_key("fk_foods_concept_id", "food_concepts", ["concept_id"], ["id"],
                                 ondelete="SET NULL")
        batch.create_index("ix_foods_source_id", ["source_id"])
        batch.create_index("ix_foods_concept_id", ["concept_id"])

    with op.batch_alter_table("food_nutrients") as batch:
        batch.add_column(sa.Column("value_qualifier", sa.String(16), nullable=False,
                                   server_default="exact"))
        batch.add_column(sa.Column("original_amount", sa.Float(), nullable=True))
        batch.add_column(sa.Column("original_unit", sa.String(16), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("food_nutrients") as batch:
        batch.drop_column("original_unit")
        batch.drop_column("original_amount")
        batch.drop_column("value_qualifier")
    with op.batch_alter_table("foods") as batch:
        batch.drop_index("ix_foods_concept_id")
        batch.drop_index("ix_foods_source_id")
        batch.drop_constraint("fk_foods_concept_id", type_="foreignkey")
        batch.drop_constraint("fk_foods_source_id", type_="foreignkey")
        batch.drop_column("name_lang")
        batch.drop_column("concept_id")
        batch.drop_column("source_id")
    with op.batch_alter_table("nutrients") as batch:
        batch.drop_column("nutrient_group")
        batch.drop_column("infoods_tag")
    op.drop_table("food_names")
    op.drop_index("ix_nutrient_aliases_alias_norm", table_name="nutrient_aliases")
    op.drop_index("ix_nutrient_aliases_nutrient_id", table_name="nutrient_aliases")
    op.drop_table("nutrient_aliases")
    op.drop_table("food_concepts")
    op.drop_table("sources")
