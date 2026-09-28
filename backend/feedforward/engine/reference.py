"""
engine/reference.py
===================
Dietary Reference Intake (DRI) layer.

Nutrient *content* only becomes actionable once you know how much a person
needs. This module holds Recommended Dietary Allowances (RDA) or Adequate
Intakes (AI) for the nutrients FeedForward tracks, by demographic group, so the
engine can express delivery as "% of daily need" rather than an abstract amount.

Values are the established U.S. Institute of Medicine (now NASEM) Dietary
Reference Intakes, cross-checked against EFSA Dietary Reference Values where
they differ materially. These are public reference data, not estimates.

Units follow FeedForward's nutrient ids:
  iron/calcium/magnesium/zinc/phosphorus/manganese/sodium  -> mg
  vitamin-c/vitamin-e                                       -> mg
  vitamin-a/vitamin-k/vitamin-d                             -> µg
  proteins/fat/carbohydrates/fiber/sugars/saturated-fat    -> g
  energy-kcal                                               -> kcal

IMPORTANT: DRIs are population reference values for healthy individuals. They
are not personalised medical targets. The caution layer (cautions.py) handles
situations where an individual's needs differ.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Demographic(str, Enum):
    """Coarse demographic groups. Enough to be useful without over-claiming."""
    ADULT_MALE = "adult_male"          # 19-50, male
    ADULT_FEMALE = "adult_female"      # 19-50, female
    OLDER_MALE = "older_male"          # 51+, male
    OLDER_FEMALE = "older_female"      # 51+, female
    PREGNANCY = "pregnancy"
    LACTATION = "lactation"
    TEEN = "teen"                      # 14-18, averaged


@dataclass(frozen=True)
class ReferenceValue:
    rda_ai: float          # RDA (preferred) or AI
    kind: str              # "RDA" | "AI"
    ul: float | None = None  # Tolerable Upper Intake Level, if defined


# ---------------------------------------------------------------------------
# DRI table: nutrient_id -> {demographic -> ReferenceValue}
# Values per day. Sources: IOM DRI reports (1997-2011); EFSA DRVs.
# ---------------------------------------------------------------------------
_DRI: dict[str, dict[Demographic, ReferenceValue]] = {
    "iron": {
        Demographic.ADULT_MALE: ReferenceValue(8, "RDA", 45),
        Demographic.ADULT_FEMALE: ReferenceValue(18, "RDA", 45),
        Demographic.OLDER_MALE: ReferenceValue(8, "RDA", 45),
        Demographic.OLDER_FEMALE: ReferenceValue(8, "RDA", 45),
        Demographic.PREGNANCY: ReferenceValue(27, "RDA", 45),
        Demographic.LACTATION: ReferenceValue(9, "RDA", 45),
        Demographic.TEEN: ReferenceValue(13, "RDA", 45),
    },
    "calcium": {
        Demographic.ADULT_MALE: ReferenceValue(1000, "RDA", 2500),
        Demographic.ADULT_FEMALE: ReferenceValue(1000, "RDA", 2500),
        Demographic.OLDER_MALE: ReferenceValue(1000, "RDA", 2000),
        Demographic.OLDER_FEMALE: ReferenceValue(1200, "RDA", 2000),
        Demographic.PREGNANCY: ReferenceValue(1000, "RDA", 2500),
        Demographic.LACTATION: ReferenceValue(1000, "RDA", 2500),
        Demographic.TEEN: ReferenceValue(1300, "RDA", 3000),
    },
    "magnesium": {
        Demographic.ADULT_MALE: ReferenceValue(400, "RDA"),
        Demographic.ADULT_FEMALE: ReferenceValue(310, "RDA"),
        Demographic.OLDER_MALE: ReferenceValue(420, "RDA"),
        Demographic.OLDER_FEMALE: ReferenceValue(320, "RDA"),
        Demographic.PREGNANCY: ReferenceValue(350, "RDA"),
        Demographic.LACTATION: ReferenceValue(310, "RDA"),
        Demographic.TEEN: ReferenceValue(410, "RDA"),
    },
    "zinc": {
        Demographic.ADULT_MALE: ReferenceValue(11, "RDA", 40),
        Demographic.ADULT_FEMALE: ReferenceValue(8, "RDA", 40),
        Demographic.OLDER_MALE: ReferenceValue(11, "RDA", 40),
        Demographic.OLDER_FEMALE: ReferenceValue(8, "RDA", 40),
        Demographic.PREGNANCY: ReferenceValue(11, "RDA", 40),
        Demographic.LACTATION: ReferenceValue(12, "RDA", 40),
        Demographic.TEEN: ReferenceValue(10, "RDA", 34),
    },
    "phosphorus": {
        Demographic.ADULT_MALE: ReferenceValue(700, "RDA", 4000),
        Demographic.ADULT_FEMALE: ReferenceValue(700, "RDA", 4000),
        Demographic.OLDER_MALE: ReferenceValue(700, "RDA", 4000),
        Demographic.OLDER_FEMALE: ReferenceValue(700, "RDA", 3000),
        Demographic.PREGNANCY: ReferenceValue(700, "RDA", 3500),
        Demographic.LACTATION: ReferenceValue(700, "RDA", 4000),
        Demographic.TEEN: ReferenceValue(1250, "RDA", 4000),
    },
    "manganese": {
        Demographic.ADULT_MALE: ReferenceValue(2.3, "AI", 11),
        Demographic.ADULT_FEMALE: ReferenceValue(1.8, "AI", 11),
        Demographic.OLDER_MALE: ReferenceValue(2.3, "AI", 11),
        Demographic.OLDER_FEMALE: ReferenceValue(1.8, "AI", 11),
        Demographic.PREGNANCY: ReferenceValue(2.0, "AI", 11),
        Demographic.LACTATION: ReferenceValue(2.6, "AI", 11),
        Demographic.TEEN: ReferenceValue(2.0, "AI", 9),
    },
    "copper": {  # µg -> stored as mg in foods; RDA 900 µg = 0.9 mg adults
        Demographic.ADULT_MALE: ReferenceValue(0.9, "RDA", 10),
        Demographic.ADULT_FEMALE: ReferenceValue(0.9, "RDA", 10),
        Demographic.OLDER_MALE: ReferenceValue(0.9, "RDA", 10),
        Demographic.OLDER_FEMALE: ReferenceValue(0.9, "RDA", 10),
        Demographic.PREGNANCY: ReferenceValue(1.0, "RDA", 10),
        Demographic.LACTATION: ReferenceValue(1.3, "RDA", 10),
        Demographic.TEEN: ReferenceValue(0.89, "RDA", 8),
    },
    "selenium": {  # µg
        Demographic.ADULT_MALE: ReferenceValue(55, "RDA", 400),
        Demographic.ADULT_FEMALE: ReferenceValue(55, "RDA", 400),
        Demographic.OLDER_MALE: ReferenceValue(55, "RDA", 400),
        Demographic.OLDER_FEMALE: ReferenceValue(55, "RDA", 400),
        Demographic.PREGNANCY: ReferenceValue(60, "RDA", 400),
        Demographic.LACTATION: ReferenceValue(70, "RDA", 400),
        Demographic.TEEN: ReferenceValue(55, "RDA", 400),
    },
    "potassium": {  # mg, AI
        Demographic.ADULT_MALE: ReferenceValue(3400, "AI"),
        Demographic.ADULT_FEMALE: ReferenceValue(2600, "AI"),
        Demographic.OLDER_MALE: ReferenceValue(3400, "AI"),
        Demographic.OLDER_FEMALE: ReferenceValue(2600, "AI"),
        Demographic.PREGNANCY: ReferenceValue(2900, "AI"),
        Demographic.LACTATION: ReferenceValue(2800, "AI"),
        Demographic.TEEN: ReferenceValue(2300, "AI"),
    },
    "folate": {  # µg DFE
        Demographic.ADULT_MALE: ReferenceValue(400, "RDA", 1000),
        Demographic.ADULT_FEMALE: ReferenceValue(400, "RDA", 1000),
        Demographic.OLDER_MALE: ReferenceValue(400, "RDA", 1000),
        Demographic.OLDER_FEMALE: ReferenceValue(400, "RDA", 1000),
        Demographic.PREGNANCY: ReferenceValue(600, "RDA", 1000),
        Demographic.LACTATION: ReferenceValue(500, "RDA", 1000),
        Demographic.TEEN: ReferenceValue(400, "RDA", 800),
    },
    "vitamin-b12": {  # µg
        Demographic.ADULT_MALE: ReferenceValue(2.4, "RDA"),
        Demographic.ADULT_FEMALE: ReferenceValue(2.4, "RDA"),
        Demographic.OLDER_MALE: ReferenceValue(2.4, "RDA"),
        Demographic.OLDER_FEMALE: ReferenceValue(2.4, "RDA"),
        Demographic.PREGNANCY: ReferenceValue(2.6, "RDA"),
        Demographic.LACTATION: ReferenceValue(2.8, "RDA"),
        Demographic.TEEN: ReferenceValue(2.4, "RDA"),
    },
    "vitamin-c": {
        Demographic.ADULT_MALE: ReferenceValue(90, "RDA", 2000),
        Demographic.ADULT_FEMALE: ReferenceValue(75, "RDA", 2000),
        Demographic.OLDER_MALE: ReferenceValue(90, "RDA", 2000),
        Demographic.OLDER_FEMALE: ReferenceValue(75, "RDA", 2000),
        Demographic.PREGNANCY: ReferenceValue(85, "RDA", 2000),
        Demographic.LACTATION: ReferenceValue(120, "RDA", 2000),
        Demographic.TEEN: ReferenceValue(70, "RDA", 1800),
    },
    "vitamin-a": {  # µg RAE
        Demographic.ADULT_MALE: ReferenceValue(900, "RDA", 3000),
        Demographic.ADULT_FEMALE: ReferenceValue(700, "RDA", 3000),
        Demographic.OLDER_MALE: ReferenceValue(900, "RDA", 3000),
        Demographic.OLDER_FEMALE: ReferenceValue(700, "RDA", 3000),
        Demographic.PREGNANCY: ReferenceValue(770, "RDA", 3000),
        Demographic.LACTATION: ReferenceValue(1300, "RDA", 3000),
        Demographic.TEEN: ReferenceValue(750, "RDA", 2800),
    },
    "vitamin-e": {  # mg α-tocopherol
        Demographic.ADULT_MALE: ReferenceValue(15, "RDA", 1000),
        Demographic.ADULT_FEMALE: ReferenceValue(15, "RDA", 1000),
        Demographic.OLDER_MALE: ReferenceValue(15, "RDA", 1000),
        Demographic.OLDER_FEMALE: ReferenceValue(15, "RDA", 1000),
        Demographic.PREGNANCY: ReferenceValue(15, "RDA", 1000),
        Demographic.LACTATION: ReferenceValue(19, "RDA", 1000),
        Demographic.TEEN: ReferenceValue(15, "RDA", 800),
    },
    "vitamin-k": {  # µg, AI
        Demographic.ADULT_MALE: ReferenceValue(120, "AI"),
        Demographic.ADULT_FEMALE: ReferenceValue(90, "AI"),
        Demographic.OLDER_MALE: ReferenceValue(120, "AI"),
        Demographic.OLDER_FEMALE: ReferenceValue(90, "AI"),
        Demographic.PREGNANCY: ReferenceValue(90, "AI"),
        Demographic.LACTATION: ReferenceValue(90, "AI"),
        Demographic.TEEN: ReferenceValue(75, "AI"),
    },
    "vitamin-d": {  # µg (1 µg = 40 IU), AI/RDA
        Demographic.ADULT_MALE: ReferenceValue(15, "RDA", 100),
        Demographic.ADULT_FEMALE: ReferenceValue(15, "RDA", 100),
        Demographic.OLDER_MALE: ReferenceValue(15, "RDA", 100),
        Demographic.OLDER_FEMALE: ReferenceValue(15, "RDA", 100),
        Demographic.PREGNANCY: ReferenceValue(15, "RDA", 100),
        Demographic.LACTATION: ReferenceValue(15, "RDA", 100),
        Demographic.TEEN: ReferenceValue(15, "RDA", 100),
    },
    "proteins": {  # g (RDA 0.8 g/kg; values assume reference body weights)
        Demographic.ADULT_MALE: ReferenceValue(56, "RDA"),
        Demographic.ADULT_FEMALE: ReferenceValue(46, "RDA"),
        Demographic.OLDER_MALE: ReferenceValue(56, "RDA"),
        Demographic.OLDER_FEMALE: ReferenceValue(46, "RDA"),
        Demographic.PREGNANCY: ReferenceValue(71, "RDA"),
        Demographic.LACTATION: ReferenceValue(71, "RDA"),
        Demographic.TEEN: ReferenceValue(52, "RDA"),
    },
    "fiber": {  # g, AI
        Demographic.ADULT_MALE: ReferenceValue(38, "AI"),
        Demographic.ADULT_FEMALE: ReferenceValue(25, "AI"),
        Demographic.OLDER_MALE: ReferenceValue(30, "AI"),
        Demographic.OLDER_FEMALE: ReferenceValue(21, "AI"),
        Demographic.PREGNANCY: ReferenceValue(28, "AI"),
        Demographic.LACTATION: ReferenceValue(29, "AI"),
        Demographic.TEEN: ReferenceValue(31, "AI"),
    },
    # IOM Adequate Intake for alpha-linolenic acid (ALA). Our omega-3 value is
    # ALA + EPA + DHA, so this is a conservative yardstick: EFSA's separate
    # 250 mg/day EPA+DHA reference is not represented.
    "omega-3-fat": {  # g
        Demographic.ADULT_MALE: ReferenceValue(1.6, "AI"),
        Demographic.ADULT_FEMALE: ReferenceValue(1.1, "AI"),
        Demographic.OLDER_MALE: ReferenceValue(1.6, "AI"),
        Demographic.OLDER_FEMALE: ReferenceValue(1.1, "AI"),
        Demographic.PREGNANCY: ReferenceValue(1.4, "AI"),
        Demographic.LACTATION: ReferenceValue(1.3, "AI"),
        Demographic.TEEN: ReferenceValue(1.35, "AI"),  # boys 1.6 / girls 1.1
    },
    # B vitamins, choline, iodine: IOM DRIs. TEEN averages the 14-18 y boys'
    # and girls' values, as elsewhere in this table.
    "thiamin": {  # mg
        Demographic.ADULT_MALE: ReferenceValue(1.2, "RDA"),
        Demographic.ADULT_FEMALE: ReferenceValue(1.1, "RDA"),
        Demographic.OLDER_MALE: ReferenceValue(1.2, "RDA"),
        Demographic.OLDER_FEMALE: ReferenceValue(1.1, "RDA"),
        Demographic.PREGNANCY: ReferenceValue(1.4, "RDA"),
        Demographic.LACTATION: ReferenceValue(1.4, "RDA"),
        Demographic.TEEN: ReferenceValue(1.1, "RDA"),
    },
    "riboflavin": {  # mg
        Demographic.ADULT_MALE: ReferenceValue(1.3, "RDA"),
        Demographic.ADULT_FEMALE: ReferenceValue(1.1, "RDA"),
        Demographic.OLDER_MALE: ReferenceValue(1.3, "RDA"),
        Demographic.OLDER_FEMALE: ReferenceValue(1.1, "RDA"),
        Demographic.PREGNANCY: ReferenceValue(1.4, "RDA"),
        Demographic.LACTATION: ReferenceValue(1.6, "RDA"),
        Demographic.TEEN: ReferenceValue(1.15, "RDA"),
    },
    # mg niacin equivalents. The UL (35 mg) is for supplements and fortificants.
    "niacin": {
        Demographic.ADULT_MALE: ReferenceValue(16, "RDA"),
        Demographic.ADULT_FEMALE: ReferenceValue(14, "RDA"),
        Demographic.OLDER_MALE: ReferenceValue(16, "RDA"),
        Demographic.OLDER_FEMALE: ReferenceValue(14, "RDA"),
        Demographic.PREGNANCY: ReferenceValue(18, "RDA"),
        Demographic.LACTATION: ReferenceValue(17, "RDA"),
        Demographic.TEEN: ReferenceValue(15, "RDA"),
    },
    "vitamin-b6": {  # mg
        Demographic.ADULT_MALE: ReferenceValue(1.3, "RDA", 100),
        Demographic.ADULT_FEMALE: ReferenceValue(1.3, "RDA", 100),
        Demographic.OLDER_MALE: ReferenceValue(1.7, "RDA", 100),
        Demographic.OLDER_FEMALE: ReferenceValue(1.5, "RDA", 100),
        Demographic.PREGNANCY: ReferenceValue(1.9, "RDA", 100),
        Demographic.LACTATION: ReferenceValue(2.0, "RDA", 100),
        Demographic.TEEN: ReferenceValue(1.25, "RDA", 80),
    },
    "pantothenic-acid": {  # mg, AI
        Demographic.ADULT_MALE: ReferenceValue(5, "AI"),
        Demographic.ADULT_FEMALE: ReferenceValue(5, "AI"),
        Demographic.OLDER_MALE: ReferenceValue(5, "AI"),
        Demographic.OLDER_FEMALE: ReferenceValue(5, "AI"),
        Demographic.PREGNANCY: ReferenceValue(6, "AI"),
        Demographic.LACTATION: ReferenceValue(7, "AI"),
        Demographic.TEEN: ReferenceValue(5, "AI"),
    },
    "biotin": {  # µg, AI
        Demographic.ADULT_MALE: ReferenceValue(30, "AI"),
        Demographic.ADULT_FEMALE: ReferenceValue(30, "AI"),
        Demographic.OLDER_MALE: ReferenceValue(30, "AI"),
        Demographic.OLDER_FEMALE: ReferenceValue(30, "AI"),
        Demographic.PREGNANCY: ReferenceValue(30, "AI"),
        Demographic.LACTATION: ReferenceValue(35, "AI"),
        Demographic.TEEN: ReferenceValue(25, "AI"),
    },
    "choline": {  # mg, AI
        Demographic.ADULT_MALE: ReferenceValue(550, "AI", 3500),
        Demographic.ADULT_FEMALE: ReferenceValue(425, "AI", 3500),
        Demographic.OLDER_MALE: ReferenceValue(550, "AI", 3500),
        Demographic.OLDER_FEMALE: ReferenceValue(425, "AI", 3500),
        Demographic.PREGNANCY: ReferenceValue(450, "AI", 3500),
        Demographic.LACTATION: ReferenceValue(550, "AI", 3500),
        Demographic.TEEN: ReferenceValue(475, "AI", 3000),
    },
    "iodine": {  # µg
        Demographic.ADULT_MALE: ReferenceValue(150, "RDA", 1100),
        Demographic.ADULT_FEMALE: ReferenceValue(150, "RDA", 1100),
        Demographic.OLDER_MALE: ReferenceValue(150, "RDA", 1100),
        Demographic.OLDER_FEMALE: ReferenceValue(150, "RDA", 1100),
        Demographic.PREGNANCY: ReferenceValue(220, "RDA", 1100),
        Demographic.LACTATION: ReferenceValue(290, "RDA", 1100),
        Demographic.TEEN: ReferenceValue(150, "RDA", 900),
    },
    # EFSA Adequate Intake for EPA + DHA (2010): 250 mg/day for adults, plus
    # 100-200 mg DHA in pregnancy and lactation (lower bound used). IOM sets
    # no EPA/DHA value; this is the EU reference the health claims assume.
    "epa-dha": {  # g
        Demographic.ADULT_MALE: ReferenceValue(0.25, "AI"),
        Demographic.ADULT_FEMALE: ReferenceValue(0.25, "AI"),
        Demographic.OLDER_MALE: ReferenceValue(0.25, "AI"),
        Demographic.OLDER_FEMALE: ReferenceValue(0.25, "AI"),
        Demographic.PREGNANCY: ReferenceValue(0.35, "AI"),
        Demographic.LACTATION: ReferenceValue(0.35, "AI"),
        Demographic.TEEN: ReferenceValue(0.25, "AI"),
    },
    "ala": {  # g, IOM AI (same values as omega-3-fat below)
        Demographic.ADULT_MALE: ReferenceValue(1.6, "AI"),
        Demographic.ADULT_FEMALE: ReferenceValue(1.1, "AI"),
        Demographic.OLDER_MALE: ReferenceValue(1.6, "AI"),
        Demographic.OLDER_FEMALE: ReferenceValue(1.1, "AI"),
        Demographic.PREGNANCY: ReferenceValue(1.4, "AI"),
        Demographic.LACTATION: ReferenceValue(1.3, "AI"),
        Demographic.TEEN: ReferenceValue(1.35, "AI"),
    },
    # IOM RDA for carbohydrate: the brain's glucose requirement, not a target
    # for total intake (the AMDR of 45-65% of energy is far higher).
    "carbohydrates": {  # g
        Demographic.ADULT_MALE: ReferenceValue(130, "RDA"),
        Demographic.ADULT_FEMALE: ReferenceValue(130, "RDA"),
        Demographic.OLDER_MALE: ReferenceValue(130, "RDA"),
        Demographic.OLDER_FEMALE: ReferenceValue(130, "RDA"),
        Demographic.PREGNANCY: ReferenceValue(175, "RDA"),
        Demographic.LACTATION: ReferenceValue(210, "RDA"),
        Demographic.TEEN: ReferenceValue(130, "RDA"),
    },
}

# Nutrients whose UL applies to intake from ordinary food, not only from
# supplements or fortificants. For magnesium, folate (folic acid) and vitamin E
# the IOM UL covers supplemental forms only, so a food cannot "exceed" it.
# Vitamin A's UL is for preformed retinol only: plant carotenoids do not count,
# which callers handle by checking the food's source.
UL_APPLIES_TO_FOOD = {
    "vitamin-a", "vitamin-d", "calcium", "iron", "zinc", "copper",
    "selenium", "phosphorus", "manganese", "iodine", "choline", "vitamin-b6",
}

# Nutrients where LESS is better — expressed as suggested upper limits rather
# than targets. Used to flag foods high in these, not to "recommend" them.
LIMIT_NUTRIENTS: dict[str, float] = {
    "sodium": 2300,        # mg/day upper guidance (chronic disease risk reduction ~1500)
    "saturated-fat": 22,   # g/day (~10% of a 2000 kcal diet)
    "sugars": 50,          # g/day added-sugar guidance (~10% of 2000 kcal)
}

DEFAULT_DEMOGRAPHIC = Demographic.ADULT_FEMALE  # conservative default (higher needs)


def reference_value(nutrient_id: str,
                    demo: Demographic = DEFAULT_DEMOGRAPHIC) -> ReferenceValue | None:
    table = _DRI.get(nutrient_id)
    if not table:
        return None
    return table.get(demo) or table.get(DEFAULT_DEMOGRAPHIC)


def percent_of_need(nutrient_id: str, amount: float,
                    demo: Demographic = DEFAULT_DEMOGRAPHIC) -> float | None:
    """
    What fraction of the daily reference intake does ``amount`` supply?
    Returns a percentage (e.g. 38.0), or None if no reference exists.
    """
    rv = reference_value(nutrient_id, demo)
    if not rv or rv.rda_ai <= 0:
        return None
    return round(100.0 * amount / rv.rda_ai, 1)


def is_limit_nutrient(nutrient_id: str) -> bool:
    return nutrient_id in LIMIT_NUTRIENTS


def percent_of_limit(nutrient_id: str, amount: float) -> float | None:
    """For limit nutrients, what fraction of the daily upper guidance is used."""
    lim = LIMIT_NUTRIENTS.get(nutrient_id)
    if not lim:
        return None
    return round(100.0 * amount / lim, 1)
