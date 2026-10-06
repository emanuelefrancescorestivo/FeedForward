"""
Normalized corpus and account schema.

Why this shape
--------------
The engine thinks in three node types and two edge families (food→nutrient,
nutrient→goal) plus an interaction list. The tables mirror that, instead of
storing a JSON blob, so an ingest job can insert a food or an interaction
without editing a file. Citations are their own table because a PMID must be
attachable to either a goal edge or an interaction, and because "no citation"
has to be representable — we never invent one to fill the column.

Amounts are per 100 g, in the canonical unit of ontology/nutrients.json.
``trusted`` on ``food_nutrients`` is the gate that keeps an OpenFoodFacts
micronutrient out of the graph until it has passed the USDA range check (see
data/ingest/sanity.py).

Provenance (revision 002): every food points at a ``sources`` row (dataset,
version, licence). A value keeps the unit and number it was published in
(``original_*``) when a conversion was applied, and a ``value_qualifier``
for EU-table cells such as "< 0,5" or "traces". Nutrients carry their
INFOODS tagname and every alias/code importers resolve through. Foods from
different sources that are the same food share a ``food_concepts`` row.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    tier: Mapped[str] = mapped_column(String(32), default="consumer")
    # Demographic enum value from engine/reference.py. Null until onboarding.
    demographic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # JSON list of engine constraint ids (vegetarian, low_sodium, ...).
    # Stored as text so the column is identical on Postgres and SQLite.
    dietary_restrictions: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class UserStateRow(Base):
    """
    What a person keeps in the app: profile answers, preferences, food diary,
    shopping list. One JSON document per user, written whole by the app; the
    server checks its size and shape, not its meaning (the engine does that
    when the answers reach it). A table of its own, so the users table and its
    migrations stay as they are.
    """
    __tablename__ = "user_state"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class SourceRow(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # curated | usda | openfoodfacts | ciqual | fineli | crea | ...
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(64), default="")
    licence: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NutrientRow(Base):
    __tablename__ = "nutrients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(16), default="")
    # FAO/INFOODS tagname for exactly what is stored (TOCPHA, VITA_RAE, ...).
    infoods_tag: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # energy | macro | limit | mineral | vitamin
    nutrient_group: Mapped[str] = mapped_column(String(16), default="")

    aliases: Mapped[list[NutrientAliasRow]] = relationship(
        back_populates="nutrient", cascade="all, delete-orphan")


class NutrientAliasRow(Base):
    """
    A name, synonym or source code that resolves to a nutrient.

    kind='name' rows are display names per ``lang``; kind='alias' rows are
    synonyms in any language; kind='code' rows are source identifiers with
    ``source`` set (usda, off, infoods). ``alias_norm`` is the lowercase,
    accent- and punctuation-free form the resolver matches on.
    """
    __tablename__ = "nutrient_aliases"
    __table_args__ = (
        UniqueConstraint("kind", "source", "lang", "alias_norm", name="uq_nutrient_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nutrient_id: Mapped[str] = mapped_column(
        ForeignKey("nutrients.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(200))
    alias_norm: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    lang: Mapped[str] = mapped_column(String(8), default="")
    source: Mapped[str] = mapped_column(String(32), default="")

    nutrient: Mapped[NutrientRow] = relationship(back_populates="aliases")


class FoodConceptRow(Base):
    """
    One real-world food ("spinach, raw") that several source records describe.
    Linking is done by the matcher and stays 'unreviewed' until a person
    confirms it; the engine never merges values across an unreviewed link.
    """
    __tablename__ = "food_concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label_en: Mapped[str] = mapped_column(String(400), default="")
    label_it: Mapped[str] = mapped_column(String(400), default="")
    category: Mapped[str] = mapped_column(String(200), default="")
    # unreviewed | confirmed | rejected
    review_status: Mapped[str] = mapped_column(String(16), default="unreviewed")


class FoodRow(Base):
    __tablename__ = "foods"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(400), index=True)
    category: Mapped[str] = mapped_column(String(400), default="")
    # curated | usda | openfoodfacts
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nutri_score: Mapped[str] = mapped_column(String(8), default="")
    nova: Mapped[int] = mapped_column(Integer, default=0)
    is_animal_source: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # True only for USDA / hand-curated foods. OFF foods stay false even if
    # individual micronutrient rows later pass the range check — that flag
    # lives on food_nutrients.trusted, per value.
    micronutrient_trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    barcode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id"), nullable=True, index=True)
    concept_id: Mapped[int | None] = mapped_column(
        ForeignKey("food_concepts.id", ondelete="SET NULL"), nullable=True, index=True)
    # Language of ``name``; empty when the source does not say (most OFF products).
    name_lang: Mapped[str] = mapped_column(String(8), default="")

    nutrients: Mapped[list[FoodNutrientRow]] = relationship(
        back_populates="food", cascade="all, delete-orphan")
    names: Mapped[list[FoodNameRow]] = relationship(
        back_populates="food", cascade="all, delete-orphan")


class FoodNameRow(Base):
    """A food's name in one language (it, en, fr, ...)."""
    __tablename__ = "food_names"

    food_id: Mapped[str] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), primary_key=True)
    lang: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(400))

    food: Mapped[FoodRow] = relationship(back_populates="names")


class FoodNutrientRow(Base):
    __tablename__ = "food_nutrients"

    food_id: Mapped[str] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"), primary_key=True)
    nutrient_id: Mapped[str] = mapped_column(
        ForeignKey("nutrients.id"), primary_key=True)
    amount_per_100g: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16), default="")
    trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    # empty, or a short reason the sanity check rejected the value
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(32), default="")
    # exact | less_than | trace | missing (ontology/values.py). Only 'exact'
    # values reach the engine; the others are kept with their bound.
    value_qualifier: Mapped[str] = mapped_column(String(16), default="exact")
    # As published, when a unit conversion was applied; null otherwise.
    original_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_unit: Mapped[str] = mapped_column(String(16), default="")

    food: Mapped[FoodRow] = relationship(back_populates="nutrients")


class GoalRow(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    system: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    icd10_refs: Mapped[str] = mapped_column(Text, default="[]")


class GoalEdgeRow(Base):
    __tablename__ = "goal_edges"
    __table_args__ = (UniqueConstraint("nutrient_id", "goal_id", name="uq_goal_edge"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nutrient_id: Mapped[str] = mapped_column(ForeignKey("nutrients.id"), index=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id"), index=True)
    weight: Mapped[float] = mapped_column(Float)
    edge_type: Mapped[str] = mapped_column(String(16), default="positive")
    explanation: Mapped[str] = mapped_column(Text, default="")
    # curated | pubmed | default. The engine still grades via evidence.py;
    # this column records where the shipped grade came from.
    evidence_source: Mapped[str] = mapped_column(String(32), default="default")
    evidence_grade: Mapped[str | None] = mapped_column(String(2), nullable=True)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)

    citations: Mapped[list[EvidenceCitationRow]] = relationship(
        back_populates="goal_edge", cascade="all, delete-orphan")


class InteractionRow(Base):
    __tablename__ = "interactions"
    __table_args__ = (
        UniqueConstraint("target", "modifier", name="uq_interaction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target: Mapped[str] = mapped_column(String(64), index=True)
    modifier: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(16))
    factor: Mapped[float] = mapped_column(Float)
    mechanism: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(String(2), default="C")
    dose_note: Mapped[str] = mapped_column(Text, default="")
    # Explicit when we have a mechanism but no verified citation. Never filled
    # with a made-up PMID to clear this flag.
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)

    citations: Mapped[list[EvidenceCitationRow]] = relationship(
        back_populates="interaction", cascade="all, delete-orphan")


class EvidenceCitationRow(Base):
    __tablename__ = "evidence_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pmid: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    doi: Mapped[str | None] = mapped_column(String(120), nullable=True)
    citation_text: Mapped[str] = mapped_column(Text, default="")
    # curated | pubmed | interaction
    source: Mapped[str] = mapped_column(String(32), default="curated")
    # True only when the PMID was returned by NCBI or was already in the
    # hand-reviewed curated table. A well-formed string is not enough.
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    goal_edge_id: Mapped[int | None] = mapped_column(
        ForeignKey("goal_edges.id", ondelete="CASCADE"), nullable=True)
    interaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="CASCADE"), nullable=True)

    goal_edge: Mapped[GoalEdgeRow | None] = relationship(back_populates="citations")
    interaction: Mapped[InteractionRow | None] = relationship(back_populates="citations")
