"""
engine/density.py
=================
Nutrient density scoring.

A transparent, explainable analogue of the Nutrient Rich Foods (NRF) index
(Drewnowski). The idea: a food's nutritional quality is the balance between the
beneficial nutrients it delivers (as a share of daily need) and the nutrients
we should limit (sodium, saturated fat, added sugars).

    NRF-style score = Σ min(%DV_beneficial, cap)  −  Σ %maxRV_limit

We compute per 100 kcal (energy-adjusted) so a calorie-dense food isn't rewarded
merely for being concentrated, then map to a 0-100 scale for display. Every term
is inspectable — no black box.

Reference: Drewnowski A. "Defining nutrient density: development and validation
of the nutrient rich foods index." J Am Coll Nutr. 2009. (NRF9.3 family.)
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import Food
from .reference import (percent_of_need, percent_of_limit, LIMIT_NUTRIENTS,
                        Demographic, DEFAULT_DEMOGRAPHIC)

# Beneficial "qualifying" nutrients counted toward density (NRF-style).
QUALIFYING = [
    "proteins", "fiber", "iron", "calcium", "magnesium", "zinc", "phosphorus",
    "manganese", "vitamin-a", "vitamin-c", "vitamin-e", "vitamin-k", "vitamin-d",
    "omega-3-fat",
]

# Per-nutrient cap on contribution (percent of DV) to avoid a single fortified
# nutrient dominating the score.
CAP = 100.0


@dataclass
class DensityBreakdown:
    score: float                       # 0-100 display score
    qualifying_sum: float              # Σ capped %DV of beneficial nutrients / 100 kcal
    limiting_sum: float                # Σ %maxRV of limit nutrients / 100 kcal
    top_contributors: list[tuple[str, float]]  # (nutrient, %DV contribution)


def _energy_factor(food: Food) -> float:
    """
    Scale to per-100-kcal; foods.json amounts are per 100 g.

    Very-low-calorie foods (coffee, broth, diet drinks) can score spuriously
    high under per-100-kcal normalisation because a trace of a micronutrient
    becomes a large %DV when divided by near-zero energy. We floor the energy
    used for normalisation to avoid this well-known NRF artifact.
    """
    kcal = food.nutrients.get("energy-kcal", 0)
    ENERGY_FLOOR = 20.0  # kcal/100g; below this, treat as 20 for scaling
    if kcal and kcal > 0:
        return 100.0 / max(kcal, ENERGY_FLOOR)
    return 1.0  # if energy unknown, score per 100 g


def density_breakdown(food: Food,
                      demo: Demographic = DEFAULT_DEMOGRAPHIC) -> DensityBreakdown:
    ef = _energy_factor(food)
    contributions: list[tuple[str, float]] = []
    qualifying = 0.0
    for n in QUALIFYING:
        amt = food.nutrients.get(n, 0)
        if amt <= 0:
            continue
        pct = percent_of_need(n, amt * ef, demo)
        if pct is None:
            continue
        capped = min(pct, CAP)
        qualifying += capped
        contributions.append((n, round(capped, 1)))

    limiting = 0.0
    for n in LIMIT_NUTRIENTS:
        amt = food.nutrients.get(n, 0)
        if amt <= 0:
            continue
        pct = percent_of_limit(n, amt * ef)
        if pct is not None:
            limiting += pct

    raw = qualifying - limiting
    # Map raw NRF-style score to a bounded 0-100 display scale. Empirically the
    # per-100-kcal qualifying sum spans roughly 0-400; we compress with a soft
    # curve and clamp.
    display = max(0.0, min(100.0, raw / 4.0))
    contributions.sort(key=lambda t: t[1], reverse=True)
    return DensityBreakdown(round(display, 1), round(qualifying, 1),
                            round(limiting, 1), contributions[:5])


def density_score(food: Food, demo: Demographic = DEFAULT_DEMOGRAPHIC) -> float:
    return density_breakdown(food, demo).score
