"""
engine/schema.py
================
Core data containers for the FeedForward scientific engine.

These extend the original university dataclasses (Food, Nutrient, GoalEdge)
with the fields a *product* needs: evidence grading, nutrient form (which
governs bioavailability), and clinical goal metadata.

Design principle: these are plain declarative containers. All behaviour lives
in the engine modules (graph, bioavailability, evidence, recommender). Keeping
data and logic separate is what lets the same engine power a consumer app, a
clinical dashboard, and a public API without change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Evidence grading
# ---------------------------------------------------------------------------
class EvidenceGrade(str, Enum):
    """
    Strength of the scientific evidence behind a nutrient -> goal association.

    Adapted from the Oxford CEBM Levels of Evidence and the GRADE framework,
    collapsed into four product-facing grades. The ``rank`` (1 = strongest)
    is what the engine uses to modulate edge weights; the ``label`` and
    ``consumer_label`` are what the two UIs display.
    """

    A = "A"  # Meta-analyses / systematic reviews of RCTs / Cochrane reviews
    B = "B"  # Individual RCTs, or strong pooled cohort evidence
    C = "C"  # Observational studies, mechanistic/biochemical evidence
    D = "D"  # Expert opinion, traditional use, single small studies

    @property
    def rank(self) -> int:
        return {"A": 1, "B": 2, "C": 3, "D": 4}[self.value]

    @property
    def multiplier(self) -> float:
        """
        Evidence confidence as a multiplicative factor in [0, 1].
        Strong evidence keeps an association's strength; weak evidence
        discounts it. Used by the graph weighting (see bioavailability.py).
        """
        return {"A": 1.0, "B": 0.85, "C": 0.6, "D": 0.35}[self.value]

    @property
    def label(self) -> str:
        """Professional / clinical label."""
        return {
            "A": "Grade A — Strong (meta-analytic)",
            "B": "Grade B — Moderate (RCT)",
            "C": "Grade C — Limited (observational)",
            "D": "Grade D — Preliminary",
        }[self.value]

    @property
    def consumer_label(self) -> str:
        """Plain-language label for the consumer app."""
        return {
            "A": "Strongly supported by research",
            "B": "Well supported by research",
            "C": "Some supporting evidence",
            "D": "Emerging / traditional evidence",
        }[self.value]


class NutrientForm(str, Enum):
    """
    The chemical form a nutrient takes in a food. Form is the single biggest
    driver of *bioavailability* — how much of the nutrient the body can
    actually absorb — and is what distinguishes FeedForward from a calorie
    counter. Example: heme iron (from meat) is absorbed at 15-35%; non-heme
    iron (from plants) at 2-20% and is highly sensitive to other nutrients
    in the same meal.
    """

    HEME_IRON = "heme_iron"
    NON_HEME_IRON = "non_heme_iron"
    RETINOL = "retinol"                 # preformed vitamin A (animal)
    BETA_CAROTENE = "beta_carotene"     # provitamin A (plant)
    FOLATE = "folate"                   # natural folate
    FOLIC_ACID = "folic_acid"           # synthetic, higher bioavailability
    GENERIC = "generic"                 # form not differentiated


# ---------------------------------------------------------------------------
# Core nodes
# ---------------------------------------------------------------------------
@dataclass
class Food:
    """A food/product node. ``nutrients`` maps nutrient_id -> amount per 100 g."""

    id: str
    name: str
    category: str
    nutrients: dict[str, float]
    nutri_score: str = ""
    nova: int = 0
    # Optional richer fields used by the bioavailability layer
    is_animal_source: bool | None = None      # animal flesh (meat, fish, seafood): heme iron, meat factor
    is_animal_derived: bool | None = None     # flesh, dairy or egg: preformed vitamin A (retinol)
    contains_vitamin_c: bool = False          # computed at ingest for iron synergy
    contains_fat: bool = False                # for fat-soluble vitamin absorption
    anti_nutrients: set = field(default_factory=set)  # {phytate, oxalate, tannin}
    enhancer_props: set = field(default_factory=set)  # {caffeine, fructose, organic_acid}
    density_score: float | None = None        # NRF-style nutrient density (0-100)
    source: str = ""                          # curated | usda | openfoodfacts | ...
    familiarity: float = 1.0                  # engine/familiarity.py, orders results only
    source_id: str = ""                       # data/sources.json row

    @property
    def has_preformed_vitamin_a(self) -> bool:
        """Retinol, not carotenoids: animal-derived foods (flesh is always animal-derived)."""
        return bool(self.is_animal_derived or self.is_animal_source)

    def nutrient_vector(self) -> dict[str, float]:
        """Return the nutrient dict for cosine-similarity comparisons."""
        return self.nutrients


@dataclass
class Nutrient:
    """A nutrient node with the goals it plausibly supports."""

    id: str
    name: str
    unit: str = "mg"
    related_goals: list[str] = field(default_factory=list)
    form: NutrientForm = NutrientForm.GENERIC


@dataclass
class GoalEdge:
    """
    A weighted nutrient -> goal association.

    ``base_weight`` is the raw association strength in (0, 1] (higher = stronger
    physiological link). ``evidence`` grades how well that link is established.
    The engine combines the two — and, for absorption-sensitive nutrients, the
    bioavailability model — into the final graph edge cost.
    """

    nutrient_id: str
    goal: str
    base_weight: float
    evidence: EvidenceGrade = EvidenceGrade.C
    explanation: str = ""
    edge_type: str = "positive"       # "positive" | "negative"
    citations: list[str] = field(default_factory=list)  # PMIDs / DOIs


@dataclass
class Synergy:
    """
    A documented interaction between two nutrients, surfaced as an explanatory
    note and (when both are present in a meal) a bioavailability modifier.
    """

    a: str
    b: str
    effect: str
    direction: str = "enhances"       # "enhances" | "inhibits"
    magnitude: float = 1.0            # multiplicative effect on absorption
    citations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Clinical goal taxonomy
# ---------------------------------------------------------------------------
@dataclass
class ClinicalGoal:
    """
    A nutritional goal with clinical metadata. The consumer app shows ``label``
    and ``description``; the professional tier additionally surfaces ``system``
    and ``icd10_refs`` so a dietitian can tie a recommendation to a condition.
    """

    id: str
    label: str
    system: str                       # physiological system (see taxonomy.py)
    description: str
    icd10_refs: list[str] = field(default_factory=list)
    consumer_visible: bool = True
