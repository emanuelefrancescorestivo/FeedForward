"""
engine/meal_optimizer.py
========================
Meal optimisation via Mixed-Integer Linear Programming (PuLP/CBC).

Picking the k individually best foods is not the best meal: three iron-rich
organ meats cover iron three times over and nothing else. The optimiser
chooses k portions that together cover the goal's nutrients, with
diminishing returns built into the model:

    maximise   sum_n  a_n * y_n            (a_n = association x evidence)
               + EPS * sum_i score_i x_i   (tie-break on the food's own score)
    subject to y_n <= 1                                   (need is capped)
               y_n <= sum_i x_i * c_{i,n}                 (c = share of daily
                                                           need per portion,
                                                           bioavailability-
                                                           adjusted)
               sum_i x_i = k
               sum_i x_i * kcal_i <= budget               (kcal per portion)
               sum_{i in group g} x_i <= 1                (one per food group)
               x_i binary, 0 <= y_n <= 1

Coverage is linear up to 100% of need and flat after it, so a second iron
source only helps if the first did not already cover the day. Candidates are
the top of the goal ranking (a window of _CANDIDATE_WINDOW eligible foods);
the MILP is optimal inside that window.

The greedy baseline takes foods in ranking order under the same constraints,
so the two objectives are directly comparable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pulp

from .milp import solve
from .portions import portion_for
from .recommender import Recommender, food_family
from .schema import Food

_CANDIDATE_WINDOW = 60
_EPS = 0.01


@dataclass
class MealItem:
    food_id: str
    food_name: str
    cost: float          # 1 - the food's goal score (lower = better), for the API
    kcal: float          # per portion
    portion_g: float = 0.0


@dataclass
class MealPlan:
    goal: str
    items: list[MealItem]
    total_cost: float    # 1 - coverage objective / max objective (lower = better)
    total_kcal: float
    feasible: bool
    note: str = ""
    coverage: dict[str, float] = field(default_factory=dict)  # nutrient -> % of need


def _candidates(rec: Recommender, goal: str, constraints: list[str], demo=None) -> list[Food]:
    out = []
    for food_id in rec.ranked(goal, demo):
        food = rec.food_by_id.get(food_id)
        if food is None or not rec._eligible(food, constraints):
            continue
        if food.nutrients.get("energy-kcal", 0) <= 0:
            continue
        out.append(food)
        if len(out) >= _CANDIDATE_WINDOW:
            break
    return out


def _kcal(food: Food) -> float:
    return food.nutrients.get("energy-kcal", 0.0) * portion_for(food).grams / 100.0


def _coverage_terms(rec: Recommender, goal: str, foods: list[Food], demo=None):
    """(nutrient, association) pairs and c[i][n]: bioavailable share of need."""
    scorer = rec.scorer_for(demo)
    nutrients = [(n, a) for n, a, _grade in scorer.positive.get(goal, [])]
    cover: list[dict[str, float]] = []
    for food in foods:
        row = {}
        for n, _a in nutrients:
            d = scorer.delivery(food, n)
            if d is not None and not d.exceeds_ul:
                row[n] = d.percent_of_need / 100.0 * d.relative_bioavailability
        cover.append(row)
    return nutrients, cover


def _evaluate(nutrients, rows: list[dict[str, float]]) -> tuple[float, dict[str, float]]:
    coverage = {}
    total = 0.0
    for n, a in nutrients:
        c = min(1.0, sum(r.get(n, 0.0) for r in rows))
        coverage[n] = round(100.0 * c, 1)
        total += a * c
    return total, coverage


def _plan(rec: Recommender, goal: str, chosen: list[Food], nutrients, rows, feasible=True,
          note: str = "", demo=None) -> MealPlan:
    objective, coverage = _evaluate(nutrients, rows)
    best = sum(a for _n, a in nutrients) or 1.0
    items = [MealItem(f.id, f.name, round(1.0 - rec.goal_score(f.id, goal, demo), 4),
                      round(_kcal(f), 1), portion_for(f).grams) for f in chosen]
    return MealPlan(goal, items, round(1.0 - objective / best, 4),
                    round(sum(i.kcal for i in items), 1), feasible, note,
                    {n: v for n, v in coverage.items() if v > 0})


def optimize_meal(rec: Recommender, goal: str, max_calories: float, k: int = 3,
                  constraints: list[str] | None = None, demo=None) -> MealPlan:
    """Choose ``k`` portions maximising capped, evidence-weighted coverage."""
    constraints = constraints or []
    foods = _candidates(rec, goal, constraints, demo)
    if len(foods) < k:
        return MealPlan(goal, [], 0.0, 0.0, False,
                        "Not enough candidate foods satisfy the constraints.")
    nutrients, cover = _coverage_terms(rec, goal, foods, demo)

    prob = pulp.LpProblem("Optimal_Meal", pulp.LpMaximize)
    x = prob.add_variable_dicts("food", range(len(foods)), cat="Binary")
    y = prob.add_variable_dicts("cover", range(len(nutrients)), lowBound=0, upBound=1)
    prob += (pulp.lpSum(a * y[j] for j, (_n, a) in enumerate(nutrients))
             + _EPS * pulp.lpSum(rec.goal_score(f.id, goal, demo) * x[i]
                                 for i, f in enumerate(foods))), "Coverage"
    for j, (n, _a) in enumerate(nutrients):
        prob += y[j] <= pulp.lpSum(cover[i].get(n, 0.0) * x[i]
                                   for i in range(len(foods))), f"Cover_{j}"
    prob += pulp.lpSum(x[i] for i in range(len(foods))) == k, "PickK"
    prob += pulp.lpSum(_kcal(f) * x[i] for i, f in enumerate(foods)) <= max_calories, "MaxKcal"
    groups: dict[str, list[int]] = {}
    for i, f in enumerate(foods):
        groups.setdefault(portion_for(f).group, []).append(i)
        groups.setdefault("family:" + food_family(f.name), []).append(i)
    for c, idx in enumerate(groups.values()):
        if len(idx) > 1:
            prob += pulp.lpSum(x[i] for i in idx) <= 1, f"OnePerGroup_{c}"
    ok, _status = solve(prob)

    if not ok:
        return MealPlan(goal, [], 0.0, 0.0, False,
                        "No feasible meal within the calorie budget.")
    picked = [i for i in range(len(foods)) if (x[i].value() or 0) > 0.5]
    return _plan(rec, goal, [foods[i] for i in picked], nutrients, [cover[i] for i in picked],
                 demo=demo)


def greedy_meal(rec: Recommender, goal: str, max_calories: float,
                k: int = 3, constraints: list[str] | None = None, demo=None) -> MealPlan:
    """Greedy baseline: ranking order, same calorie and one-per-group rules."""
    constraints = constraints or []
    foods = _candidates(rec, goal, constraints, demo)
    nutrients, cover = _coverage_terms(rec, goal, foods, demo)
    chosen: list[int] = []
    used: set[str] = set()
    kcal = 0.0
    for i, f in enumerate(foods):
        keys = {portion_for(f).group, "family:" + food_family(f.name)}
        if keys & used or kcal + _kcal(f) > max_calories:
            continue
        chosen.append(i)
        used |= keys
        kcal += _kcal(f)
        if len(chosen) == k:
            break
    return _plan(rec, goal, [foods[i] for i in chosen], nutrients,
                 [cover[i] for i in chosen], feasible=len(chosen) == k, demo=demo)
