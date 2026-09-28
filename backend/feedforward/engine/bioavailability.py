"""
engine/bioavailability.py
=========================
The bioavailability engine — FeedForward's core scientific differentiator.

Nutrient *content* is not nutrient *delivery*. How much of a nutrient the body
absorbs depends on its chemical FORM and on what else is in the meal. This
module turns "contains 3 mg iron" into "delivers X mg absorbable iron".

DATA-DRIVEN DESIGN
------------------
The interaction rules live in ``data/interactions.json``, not in code. Adding a
newly-established interaction is a data edit, and every absorption adjustment
carries the mechanism and citation from that file. This is deliberate: for a
health product, auditability is the feature. A dietitian can inspect exactly
why an absorption factor is what it is; a consumer can be told in plain words.

Complexity is bounded and small: per (nutrient, meal) we scan the interaction
list once — O(interactions) with interactions ~ 40 — and per-food absorption is
O(1). Nothing here is exponential.

Sources: see the citations in interactions.json and docs/SCIENTIFIC_BASIS.md.
Baseline absorption fractions come from IOM DRI reports and absorption reviews
(Hurrell & Egli 2010; Lönnerdal 2000; Heaney 2000).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .schema import Food, NutrientForm

_DATA = Path(__file__).resolve().parent.parent / "data" / "interactions.json"


# ---------------------------------------------------------------------------
# Baseline absorption fractions by nutrient form (fraction absorbed, 0-1).
# ---------------------------------------------------------------------------
BASELINE_ABSORPTION: dict[str, float] = {
    "heme_iron": 0.25,        # 15-35%
    "non_heme_iron": 0.10,    # 2-20%, highly modifiable
    "calcium": 0.30,          # ~30% baseline
    "zinc": 0.25,             # 15-40%, phytate-sensitive
    "magnesium": 0.35,        # 30-40%
    "vitamin-a": 0.80,        # preformed retinol, fat-dependent
    "beta_carotene": 0.15,    # provitamin A, low & matrix-dependent
    "vitamin-c": 0.85,        # high at normal intakes
    "vitamin-d": 0.70,        # fat-dependent
    "vitamin-e": 0.55,        # fat-soluble
    "vitamin-k": 0.60,        # fat-soluble
    "folate": 0.50,
    "folic_acid": 0.85,
    "proteins": 0.95,
    "generic": 0.90,
}

FAT_SOLUBLE = {"vitamin-a", "vitamin-d", "vitamin-e", "vitamin-k", "beta_carotene"}


# ---------------------------------------------------------------------------
# Load the interaction matrix (cached)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_matrix() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))


def interaction_count() -> int:
    return len(_load_matrix().get("interactions", []))


def food_property_keywords() -> dict[str, list[str]]:
    return _load_matrix().get("food_properties", {})


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class AbsorptionResult:
    factor: float                 # multiplicative absorption factor in (0, 1]
    reason: str                   # why the factor is what it is
    form: str                     # the nutrient form used


@dataclass
class MealModifier:
    target: str
    modifier: str
    multiplier: float
    direction: str                # "enhances" | "inhibits"
    mechanism: str
    evidence: str = "C"
    citations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-food absorption (form + intrinsic food properties)
# ---------------------------------------------------------------------------
def iron_form_for_food(food: Food) -> NutrientForm:
    """Heme iron only in animal flesh; everything else is non-heme."""
    return NutrientForm.HEME_IRON if food.is_animal_source else NutrientForm.NON_HEME_IRON


def _target_form(nutrient_id: str, food: Food) -> str:
    """Resolve the absorption 'target' key (form-aware for iron/vit A)."""
    if nutrient_id == "iron":
        return iron_form_for_food(food).value
    if nutrient_id == "vitamin-a" and not food.is_animal_source:
        return "beta_carotene"      # plant provitamin A
    return nutrient_id


def absorption_factor(nutrient_id: str, food: Food) -> AbsorptionResult:
    """How absorbable is ``nutrient_id`` from this single food (pre-meal)."""
    target = _target_form(nutrient_id, food)
    base = BASELINE_ABSORPTION.get(target, BASELINE_ABSORPTION["generic"])

    if target == "heme_iron":
        reason = ("Heme iron from an animal source — absorbed efficiently (~25%) "
                  "and largely unaffected by other meal components.")
    elif target == "non_heme_iron":
        reason = ("Non-heme iron from a plant source — baseline absorption is low "
                  "(~10%) but changes sharply with meal composition.")
    elif target == "beta_carotene":
        reason = ("Provitamin A (beta-carotene) from a plant source — absorption is "
                  "low and highly fat-dependent.")
    elif target in FAT_SOLUBLE:
        reason = f"{nutrient_id} is fat-soluble; absorption depends on dietary fat."
    else:
        reason = "Standard absorption for this nutrient."
    return AbsorptionResult(base, reason, target)


# ---------------------------------------------------------------------------
# Meal-level modifiers (data-driven from the interaction matrix)
# ---------------------------------------------------------------------------
def _meal_properties(meal: list[Food]) -> set[str]:
    """Which interaction 'modifier' properties are present in the meal."""
    props: set[str] = set()
    # nutrient-based modifiers (numeric thresholds, per 100 g)
    if any(f.nutrients.get("vitamin-c", 0) > 5 or f.contains_vitamin_c for f in meal):
        props.add("vitamin-c")
    if any(f.nutrients.get("calcium", 0) > 100 for f in meal):
        props.add("calcium")
    if any(f.nutrients.get("vitamin-d", 0) > 0 for f in meal):
        props.add("vitamin-d")
    if any(f.nutrients.get("fat", 0) > 3 or f.contains_fat for f in meal):
        props.add("fat")
    if any(f.nutrients.get("vitamin-a", 0) > 50 for f in meal):
        props.add("vitamin-a")
    if any(f.nutrients.get("magnesium", 0) > 50 for f in meal):
        props.add("magnesium")
    if any(f.nutrients.get("iron", 0) > 3 for f in meal):
        props.add("iron")
    if any(f.nutrients.get("zinc", 0) > 3 for f in meal):
        props.add("zinc")
    if any(f.nutrients.get("fiber", 0) > 5 for f in meal):
        props.add("fiber")
    if any(f.nutrients.get("sodium", 0) > 300 for f in meal):
        props.add("sodium")
    # property-based modifiers detected at ingest (phytate/oxalate/tannin/
    # caffeine/fructose/organic_acid) plus animal_protein
    for f in meal:
        props |= getattr(f, "anti_nutrients", set()) or set()
        props |= getattr(f, "enhancer_props", set()) or set()
        if f.is_animal_source:
            props.add("animal_protein")
    return props


def meal_modifiers(nutrient_id: str, food: Food,
                   meal: list[Food]) -> list[MealModifier]:
    """
    Return absorption modifiers that apply to ``nutrient_id`` from ``food`` given
    the meal, by matching the interaction matrix against meal properties.
    """
    target = _target_form(nutrient_id, food)
    present = _meal_properties(meal)
    mods: list[MealModifier] = []
    for inter in _load_matrix().get("interactions", []):
        if inter["target"] != target:
            continue
        modifier = inter["modifier"]
        if modifier not in present:
            continue
        # An interaction shouldn't count a food against itself as its own modifier
        # for animal_protein/fat when the food IS the only source — acceptable
        # simplification: meal-level presence is what matters.
        mods.append(MealModifier(
            target=target, modifier=modifier, multiplier=float(inter["factor"]),
            direction=inter["direction"], mechanism=inter["mechanism"],
            evidence=inter.get("evidence", "C"),
            citations=inter.get("citations", [])))
    return mods


def effective_absorption(nutrient_id: str, food: Food,
                         meal: list[Food] | None = None) -> AbsorptionResult:
    """Combine single-food absorption with meal-level interaction modifiers."""
    base = absorption_factor(nutrient_id, food)
    if not meal:
        return base
    factor = base.factor
    reasons = [base.reason]
    for mod in meal_modifiers(nutrient_id, food, meal):
        factor *= mod.multiplier
        verb = "increases" if mod.direction == "enhances" else "reduces"
        reasons.append(f"{mod.modifier.replace('_', ' ').title()} {verb} absorption: "
                       f"{mod.mechanism}")
    factor = min(factor, 1.0)
    return AbsorptionResult(factor, " ".join(reasons), base.form)
