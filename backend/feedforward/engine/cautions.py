"""
engine/cautions.py
==================
The caution / contraindication layer.

Real nutritional analysis must be able to say "be careful" — some nutrients
interact with medications or conditions in well-documented ways. This layer
surfaces those as INFORMATIONAL flags.

CRITICAL FRAMING
----------------
These flags are educational, not medical advice, diagnosis, or treatment. They
are phrased to prompt a conversation with a qualified professional, never to
instruct. FeedForward does not know the user's medications or conditions unless
they tell it, and even then defers to their clinician. Every flag includes a
"talk to your healthcare provider" disposition.

Each caution ties a nutrient (or food property) to a context and explains the
interaction. Sources are well-established clinical pharmacology / nutrition
references; specific citations should be verified before any clinical use.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .schema import Food


@dataclass
class Caution:
    nutrient: str
    context: str                       # medication class or condition (plain label)
    severity: str                      # "info" | "moderate" | "important"
    message: str                       # what to be aware of
    disposition: str = ("This is general information, not medical advice — "
                        "discuss with your healthcare provider.")
    citations: list[str] = field(default_factory=list)


# nutrient_id -> list of cautions
_CAUTIONS: dict[str, list[Caution]] = {
    "vitamin-k": [
        Caution("vitamin-k", "blood thinners (warfarin)", "important",
                "Vitamin K can reduce the effect of warfarin-type anticoagulants. "
                "Consistency of intake matters more than avoidance.",
                citations=["PMID:15571428"]),
    ],
    "calcium": [
        Caution("calcium", "certain antibiotics & thyroid medication", "moderate",
                "Calcium can bind some medicines (tetracyclines, levothyroxine) "
                "and reduce their absorption if taken at the same time. Separate "
                "calcium supplements or calcium-rich meals from the medicine by "
                "several hours — this is a timing issue, not a reason to avoid "
                "dietary calcium.",
                citations=["PMID:10838651", "PMID:28153426", "PMID:106309"]),
        Caution("calcium", "history of calcium-oxalate kidney stones", "moderate",
                "Very high supplemental calcium may affect stone risk in susceptible "
                "individuals; dietary calcium is generally handled differently."),
    ],
    "vitamin-c": [
        Caution("vitamin-c", "hemochromatosis / iron overload", "moderate",
                "Vitamin C increases iron absorption, which may be undesirable for "
                "people with iron-overload conditions."),
    ],
    "iron": [
        Caution("iron", "hemochromatosis / iron overload", "important",
                "People with iron-overload conditions typically need to limit iron "
                "intake."),
        Caution("iron", "thyroid medication (levothyroxine)", "moderate",
                "Iron supplements can reduce levothyroxine absorption if taken "
                "together. Separate them by several hours. This is timing "
                "information, not a reason to avoid iron-containing foods.",
                citations=["PMID:19942153"]),
    ],
    "vitamin-a": [
        Caution("vitamin-a", "pregnancy", "important",
                "Very high preformed vitamin A (retinol) intake is not advised in "
                "pregnancy; provitamin A (beta-carotene) does not carry the same "
                "concern.",
                citations=["PMID:7477165"]),
    ],
    "sodium": [
        Caution("sodium", "high blood pressure", "moderate",
                "High sodium intake works against blood-pressure management for many "
                "people."),
    ],
    "vitamin-e": [
        Caution("vitamin-e", "blood thinners", "moderate",
                "High-dose vitamin E may add to the effect of anticoagulant/"
                "antiplatelet medicines."),
    ],
    "magnesium": [
        Caution("magnesium", "reduced kidney function", "moderate",
                "Impaired kidneys clear magnesium less efficiently; supplemental "
                "magnesium may accumulate."),
    ],
}

# Thresholds (per 100 g) above which a food is considered "high" in a nutrient
# for the purpose of raising a caution. Conservative.
_HIGH_THRESHOLD: dict[str, float] = {
    "vitamin-k": 50, "calcium": 150, "vitamin-c": 40, "iron": 4,
    "vitamin-a": 300, "sodium": 400, "vitamin-e": 8, "magnesium": 100,
}


def cautions_for_nutrient(nutrient_id: str) -> list[Caution]:
    return _CAUTIONS.get(nutrient_id, [])


def cautions_for_food(food: Food) -> list[Caution]:
    """
    Which cautions are relevant to this food, based on the nutrients it is
    notably high in. Returns an empty list for foods with no flagged nutrients.
    """
    out: list[Caution] = []
    for nutrient, threshold in _HIGH_THRESHOLD.items():
        if food.nutrients.get(nutrient, 0) >= threshold:
            out.extend(_CAUTIONS.get(nutrient, []))
    return out


def all_contexts() -> list[str]:
    """Distinct contexts, for building a 'do any of these apply to you?' UI."""
    seen: list[str] = []
    for lst in _CAUTIONS.values():
        for c in lst:
            if c.context not in seen:
                seen.append(c.context)
    return seen
