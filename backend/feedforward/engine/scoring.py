"""
engine/scoring.py
=================
How much does one portion of a food support a goal?

The graph is Food -> Nutrient -> Goal. This module gives every edge a
strength in [0, 1] with a physiological meaning, and combines the paths.

Food -> Nutrient: delivery strength
    x        = amount in one reference portion / daily reference intake
               (portion from engine/portions.py, DRI from engine/reference.py)
    rel      = relative bioavailability of that nutrient from that food on
               its own: chemical form (heme vs non-heme iron, against the
               18% the IOM RDA assumes) and strong intrinsic inhibitors
               (oxalate on calcium). Meal effects are not applied here.
    strength = 1 - exp(-K * x * rel)

    Saturating, so the tenth day's worth of a nutrient in one bite adds
    almost nothing. A portion that exceeds a Tolerable Upper Intake Level
    (where the UL applies to food, not only to supplements) is discounted:
    liver is not the best food for bone health because of its vitamin A.

Nutrient -> Goal: association strength
    base weight x evidence multiplier (A 1.0, B 0.85, C 0.6, D 0.35)

Path strength = delivery x association. Because costs on the graph are
-log(strength), Dijkstra's shortest path is exactly the strongest path, and
Yen's k-shortest paths are the next-strongest routes.

Food -> Goal: combining paths
    support = 1 - (1 - p1) * prod_{i=2..4} (1 - BETA * p_i)

    p1 is the strongest path. The next three add with weight BETA, so a
    food rich in the goal's main nutrient beats one that touches many weakly
    linked nutrients. Enhancer edges (vitamin C for iron) are not paths: a
    food's own vitamin C already raises its iron's bioavailability, and the
    enhancer is suggested as a pairing instead.

Penalties (multiplicative):
    goal-specific: a negative edge (sodium -> blood pressure) scales the
        score by 1 - weight * share of the daily limit one portion uses;
    general: every limit nutrient (sodium, saturated fat, sugars) scales it
        by 1 - LIMIT_PENALTY * share of the daily limit, so a salty or sugary
        food is not recommended for its micronutrients;
    safety: every nutrient of which one portion exceeds the UL scales it by
        UL_FOOD_PENALTY, whatever the goal (liver's vitamin A also counts
        against liver as an iron source).

Every constant below is a modelling choice, documented and tested, and is
meant to be reviewed with dietitians.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

from .bioavailability import absorption_factor
from .portions import portion_for
from .reference import (DEFAULT_DEMOGRAPHIC, LIMIT_NUTRIENTS, UL_APPLIES_TO_FOOD,
                        Demographic, reference_value)
from .schema import EvidenceGrade, Food

# Saturation is anchored to the EU claim thresholds (Reg. 1924/2006): a food
# is a "source" of a vitamin or mineral at 15% of the NRV and "high" in it at
# 30%. With K = 4: 15% -> 0.45, 30% -> 0.70, 50% -> 0.86, 100% -> 0.98.
SATURATION_K = 4.0
# Every path after the strongest counts at SECONDARY_WEIGHT, and only the
# SECONDARY_PATHS strongest of them. The EU register links up to ~17
# nutrients to one goal ("contributes to normal cognitive function"); without
# the cap every nutrient-dense food would saturate near 100 and the ranking
# would stop being about the goal.
SECONDARY_WEIGHT = 0.3
SECONDARY_PATHS = 3
LIMIT_PENALTY = 0.5         # general penalty per unit share of a daily limit
UL_PENALTY = 0.25           # delivery multiplier when a portion exceeds the UL
UL_FOOD_PENALTY = 0.6       # whole-food multiplier per nutrient over its UL
REL_BIO_RANGE = (0.1, 2.0)
IRON_RDA_ABSORPTION = 0.18  # IOM: iron RDA assumes 18% bioavailability
SODIUM_PER_G_SALT = 400.0   # mg sodium per g salt (EU: salt = sodium x 2.5)
# Portion groups where missing sugars are estimated as carbohydrate - fibre.
_SUGARY_GROUPS = {"beverages", "beverage_concentrate", "powders", "sweets_snacks",
                  "spreads_sweeteners"}


# (target, modifier) pairs applied to a food on its own. The factor is read
# from data/interactions.json so it stays auditable in one place.
INTRINSIC_INHIBITORS = {("calcium", "oxalate")}


@lru_cache(maxsize=1)
def _intrinsic_inhibitors() -> dict[str, list[tuple[str, float]]]:
    from .bioavailability import _load_matrix
    out: dict[str, list[tuple[str, float]]] = {}
    for inter in _load_matrix().get("interactions", []):
        key = (inter["target"], inter["modifier"])
        if key in INTRINSIC_INHIBITORS and inter["direction"] == "inhibits":
            out.setdefault(inter["target"], []).append((inter["modifier"], float(inter["factor"])))
    return out


def saturate(x: float) -> float:
    return 1.0 - math.exp(-SATURATION_K * x) if x > 0 else 0.0


@dataclass(frozen=True)
class Delivery:
    nutrient: str
    portion_g: float
    portion_group: str
    amount: float                 # per portion, canonical unit
    percent_of_need: float        # of the DRI, before bioavailability
    relative_bioavailability: float
    strength: float               # in [0, 1]
    exceeds_ul: bool = False


@dataclass(frozen=True)
class PathContribution:
    nutrient: str
    delivery: Delivery
    association: float            # base weight x evidence multiplier
    evidence: str
    strength: float               # delivery x association


@dataclass(frozen=True)
class Penalty:
    nutrient: str
    share_of_limit: float         # one portion as a fraction of the daily limit
    factor: float
    goal_specific: bool
    kind: str = "limit"           # limit | upper_limit


@dataclass
class GoalScore:
    food_id: str
    goal: str
    score: float                  # final, in [0, 1]
    support: float                # before penalties
    contributions: list[PathContribution] = field(default_factory=list)
    penalties: list[Penalty] = field(default_factory=list)
    pairings: list[str] = field(default_factory=list)   # enhancer nutrients


class GoalScorer:
    """
    Scores foods against goals. Built once per engine; per-food deliveries
    are cached, so scoring every food for every goal is linear in the number
    of (food, nutrient, goal) triples.
    """

    def __init__(self, goal_edges: list[dict], *,
                 demo: Demographic = DEFAULT_DEMOGRAPHIC,
                 edge_grade=None) -> None:
        if edge_grade is None:
            from .build import edge_grade
        self.demo = demo
        self.positive: dict[str, list[tuple[str, float, str]]] = {}
        self.negative: dict[str, list[tuple[str, float]]] = {}
        self.enhancers: dict[str, list[str]] = {}
        for edge in goal_edges:
            nutrient, goal = edge["nutrient"], edge["goal"]
            kind = edge.get("type", "positive")
            weight = float(edge["weight"])
            if kind == "negative":
                self.negative.setdefault(goal, []).append((nutrient, weight))
            elif kind == "enhancer":
                self.enhancers.setdefault(goal, []).append(nutrient)
            elif kind == "positive":
                grade: EvidenceGrade = edge_grade(edge)
                self.positive.setdefault(goal, []).append(
                    (nutrient, weight * grade.multiplier, grade.value))
        self._delivery: dict[tuple[str, str], Delivery | None] = {}
        self._shares: dict[str, dict[str, float]] = {}
        self._over_ul: dict[str, list[str]] = {}

    # -- goals ------------------------------------------------------------
    def goals(self) -> list[str]:
        return sorted(self.positive)

    def association(self, nutrient: str, goal: str) -> float | None:
        for n, strength, _grade in self.positive.get(goal, []):
            if n == nutrient:
                return strength
        return None

    # -- food -> nutrient -------------------------------------------------
    @staticmethod
    def relative_bioavailability(nutrient: str, food: Food) -> float:
        """
        Absorption of ``nutrient`` from ``food`` eaten on its own, relative to
        what the DRI already assumes.

        Only two things count here:
          * chemical form — iron: heme (~25%) or non-heme (~10%) against the
            18% the IOM iron RDA assumes for a mixed diet;
          * INTRINSIC_INHIBITORS — strong, food-intrinsic effects that a DRI
            for a mixed diet does not already average in (oxalate on calcium).

        Everything else in the interaction matrix is a meal effect and is
        applied where there is a meal (analyze_meal, the meal optimiser,
        pairing notes). Applying the ×2.5 vitamin C factor to spinach's own
        vitamin C, or multiplying phytate × calcium × fibre for a legume,
        double-counts: those factors come from meals with the modifier added,
        and DRIs are derived for diets that already contain phytate. Vitamin A
        values are RAE, which already include carotenoid conversion.
        """
        rel = 1.0
        if nutrient == "iron":
            rel = absorption_factor(nutrient, food).factor / IRON_RDA_ABSORPTION
        target = "non_heme_iron" if nutrient == "iron" and not food.is_animal_source else nutrient
        for modifier, factor in _intrinsic_inhibitors().get(target, []):
            if modifier in (food.anti_nutrients or set()):
                rel *= factor
        low, high = REL_BIO_RANGE
        return min(high, max(low, rel))

    def delivery(self, food: Food, nutrient: str) -> Delivery | None:
        key = (food.id, nutrient)
        if key in self._delivery:
            return self._delivery[key]
        result = self._compute_delivery(food, nutrient)
        self._delivery[key] = result
        return result

    def _compute_delivery(self, food: Food, nutrient: str) -> Delivery | None:
        per_100g = food.nutrients.get(nutrient, 0.0)
        if per_100g <= 0:
            return None
        ref = reference_value(nutrient, self.demo)
        if ref is None or ref.rda_ai <= 0:
            return None
        portion = portion_for(food)
        amount = per_100g * portion.grams / 100.0
        x = amount / ref.rda_ai
        rel = self.relative_bioavailability(nutrient, food)
        strength = saturate(x * rel)
        exceeds = False
        if ref.ul and nutrient in UL_APPLIES_TO_FOOD and amount > ref.ul:
            # Vitamin A's UL is for preformed retinol; plant RAE does not count.
            if nutrient != "vitamin-a" or food.has_preformed_vitamin_a:
                exceeds = True
                strength *= UL_PENALTY
        return Delivery(nutrient, portion.grams, portion.group, round(amount, 4),
                        round(100.0 * x, 1), round(rel, 3), strength, exceeds)

    # -- limits -----------------------------------------------------------
    @staticmethod
    def _limit_amount(food: Food, nutrient: str) -> float:
        """
        Amount per 100 g for a limit nutrient. Two documented fallbacks, used
        only for penalties, never shown as data: sodium from salt (EU: salt =
        sodium x 2.5), and, for drinks and sweets that do not report sugars
        (about 140 USDA beverages), carbohydrate minus fibre — in those foods
        the available carbohydrate is essentially sugar.
        """
        amount = food.nutrients.get(nutrient, 0.0)
        if nutrient == "sodium" and amount <= 0:
            amount = food.nutrients.get("salt", 0.0) * SODIUM_PER_G_SALT
        if nutrient == "sugars" and amount <= 0 and portion_for(food).group in _SUGARY_GROUPS:
            amount = max(0.0, food.nutrients.get("carbohydrates", 0.0)
                         - food.nutrients.get("fiber", 0.0))
        return amount

    def share_of_limit(self, food: Food, nutrient: str) -> float:
        shares = self._shares.get(food.id)
        if shares is None:
            grams = portion_for(food).grams
            shares = {n: self._limit_amount(food, n) * grams / 100.0 / limit
                      for n, limit in LIMIT_NUTRIENTS.items()}
            self._shares[food.id] = shares
        return shares.get(nutrient, 0.0)

    def over_upper_limit(self, food: Food) -> list[str]:
        """Nutrients of which one portion exceeds a UL that applies to food."""
        if food.id not in self._over_ul:
            over = []
            for nutrient in sorted(UL_APPLIES_TO_FOOD):
                d = self.delivery(food, nutrient)
                if d is not None and d.exceeds_ul:
                    over.append(nutrient)
            self._over_ul[food.id] = over
        return self._over_ul[food.id]

    def penalties(self, food: Food, goal: str) -> list[Penalty]:
        out: list[Penalty] = []
        specific = {n: w for n, w in self.negative.get(goal, [])}
        for nutrient in self.over_upper_limit(food):
            out.append(Penalty(nutrient, 0.0, UL_FOOD_PENALTY, False, "upper_limit"))
        for nutrient in LIMIT_NUTRIENTS:
            share = self.share_of_limit(food, nutrient)
            if share <= 0:
                continue
            capped = min(1.0, share)
            if nutrient in specific:
                factor = 1.0 - specific[nutrient] * capped
                out.append(Penalty(nutrient, round(share, 3), round(factor, 4), True))
            else:
                factor = 1.0 - LIMIT_PENALTY * capped
                out.append(Penalty(nutrient, round(share, 3), round(factor, 4), False))
        return out

    # -- food -> goal -----------------------------------------------------
    def contributions(self, food: Food, goal: str) -> list[PathContribution]:
        out = []
        for nutrient, association, grade in self.positive.get(goal, []):
            d = self.delivery(food, nutrient)
            if d is None or d.strength <= 0:
                continue
            out.append(PathContribution(nutrient, d, association, grade,
                                        d.strength * association))
        out.sort(key=lambda c: c.strength, reverse=True)
        return out

    @staticmethod
    def combine(strengths: list[float]) -> float:
        """Strongest path in full, every other path at SECONDARY_WEIGHT (noisy-OR)."""
        if not strengths:
            return 0.0
        ordered = sorted(strengths, reverse=True)
        miss = 1.0 - ordered[0]
        for p in ordered[1:1 + SECONDARY_PATHS]:
            miss *= 1.0 - SECONDARY_WEIGHT * p
        return 1.0 - miss

    def score(self, food: Food, goal: str) -> GoalScore:
        contribs = self.contributions(food, goal)
        support = self.combine([c.strength for c in contribs])
        pens = self.penalties(food, goal) if support > 0 else []
        final = support
        for p in pens:
            final *= p.factor
        return GoalScore(food.id, goal, max(0.0, final), support, contribs, pens,
                         list(self.enhancers.get(goal, [])))

    def score_value(self, food: Food, goal: str) -> float:
        return self.score(food, goal).score
