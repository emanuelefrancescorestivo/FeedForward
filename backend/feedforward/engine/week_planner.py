"""
engine/week_planner.py
======================
A week of breakfasts, lunches and dinners, within a budget, at one shop.

Decision: how many times each recipe is eaten at each meal of the week, and
how many snacks. Solved as a mixed-integer programme (PuLP/CBC):

  maximise   sum_n w_n * y_n / sum_n w_n           nutrient coverage, capped at 100%
             - (e_over + e_under) / E              energy close to the need
             - 5 * sum_l slack_l / L_l             stay under salt / sat. fat / sugar limits
             - 0.03 * repeats                      variety (see below)
             - 0.01 * cost / budget                cheaper when otherwise equal
  subject to exactly 7 breakfasts, 7 lunches, 7 dinners
             energy between 90% and 115% of the need (hard: never cut food to save money);
               from 97% in a deficit, and never below resting energy x days (_energy_band)
             a recipe twice a week (three times if it keeps: batch cooking)
               + repeats, so narrow settings still get a plan, with repeats
             y_n * weekly_need_n <= weekly intake_n,   0 <= y_n <= 1
             cost <= budget

  w_n = 1 + GOAL_BONUS * a(n): every nutrient counts, the goals' nutrients
  (from the EU-claim graph) count more. a(n) = max_g alpha_g * association(n, g)
  over the person's goal (alpha 1) and the goals their answers turn on (alpha
  0.5, engine/profile.py): the maximum keeps a(n) in [0, 1], never counts a
  nutrient twice, and names the goal that set its weight. With no answers,
  a(n) is the one goal's association, as before.

  E = Mifflin-St Jeor x activity (engine/needs.py) x the energy goal's factor
  (maintain 1.0, deficit 0.85, surplus 1.10), never below resting energy; meal
  portions scale with it. The week's energy is never planned below resting
  energy, and a deficit week at 97 % of E or more: at most 1 - 0.97 x 0.85, about
  17.5 %, below maintenance (with no answers the bound is today's 90 %, already
  above resting energy). A protein strategy sets a protein target, its g/kg,
  not a need: the needs and the coverage stay the reference intakes.

Soft levers (strategies and preferences from the answers), with S_m(n) the
week's n from meal m, each slack >= 0 and divided by its normaliser, so that a
lever missed by its whole threshold costs about its weight:

  meal m >= p of the day's carbs   S_m(carbs) + sl >= p * intake(carbs)   p * 0.525 * E / 4
  breakfast >= p of the energy     S_b(kcal) + sl >= p * max(intake(kcal), E)   p * E
  breakfast <= p of the energy     S_b(kcal) - sl <= p * E                      p * E
  protein >= t per main meal       sum_r,m max(0, t - protein_r) / t * x_rm   3 * days
  protein >= t at breakfast        the same, breakfast only                   days
      all of these weigh PREFERENCE_WEIGHT = 1
  protein target (g/kg)            intake(protein) + sl >= the target          the target
      weighs PROTEIN_NEED_WEIGHT = 20, before the other levers

  Needs first, lexicographically: with levers the week is solved twice. The
  first solve is the model above without any lever (with no answers it is the
  only one, so a plan without answers is exactly today's). The second adds
  them, and from the first week no nutrient may fall more than NEEDS_TOLERANCE
  (3 points), nor below 97 % of the need (nor below the first week where that
  was lower); energy may move at most 3 % of E further from the target; and the
  week may cost at most LEVER_COST (5 %) more. The levers only trade, then,
  against coverage above the floors, energy within 3 points, variety and cost
  within 5 %: so they weigh 1, not the 0.3 first planned. Measured on the
  README profile: weights alone could not keep needs first (at 0.3, 0.1 and
  0.03 a lever still took riboflavin or iodine below 97 %); with the floors and
  the cost cap, 0.3 left evening carbs on 3-4 days and 1 meets them. The protein
  target weighs 20 (chosen when it was still a need of the first solve: 3 or 5
  left it at 95 %, 10 at 96.8 % with PuLP 4's CBC). In a deficit at EUR 60 the
  recipes give about 1.3 g/kg within the bounds whatever the weight (20 or 100)
  or the cost cap (5 % or 50 %): there the energy bound, not the weight, limits
  it. A 10 % cap let training weeks reach 1.15 x the plain week's cost (their
  first week was then 5 % dearer); 4 % and 3 % lost evening carbs or hit the
  time limit. The second solve is the slow one: up to the 10 s safety net for
  six answers at once (the best week found by then is planned).

  Shares are written on the week; the plan reports them day by day, so after
  the days are laid out, meals and snacks are swapped between days while that
  meets the levers on more days (same food, cost and coverage). A swap never
  takes a day's energy more than 10 % from the daily target (or further, for a
  day already off), nor below resting energy, and a breakfast energy share
  counts only on a day in the energy band, taken of the day or its target
  (whichever is less favourable): a breakfast lever is never met by eating less.

  In a deficit week the days are balanced before that (_balance): a day below
  resting energy swaps meals or snacks with a day that stays at resting energy
  or above, where the recipes allow; the plan counts the days left below
  (energy.days_below_resting).

The answers also filter the recipes, hard: foods not eaten (ingredient tags and
recipe tags such as "spicy"), the cooking time (batch recipes may take three
times as long when batch cooking is fine), recipes marked "not for me", and no
caffeine at a meal the person keeps caffeine-free. Ingredients at home bring no
filtered recipe back: they only make the recipes left cheaper.

When these filters leave a main meal fewer than MIN_OPTIONS (3) recipes, the plan
lists in `relax` what to loosen: one change at a time (a longer cooking time, a
food allowed again, batch cooking, the recipes "not for me" at that meal, a looser
diet), counted with the same filters as the plan, each only if it adds recipes to
that meal. A meal with none at all has no plan to make: the reason is "recipes",
found before any solve. `relax` is always on the plan, empty when no meal is short.

Costs use the chosen chain's prices (data/ingredient_prices.json). Fridge
items (eggs, milk, meat, bread...) are bought as whole packs, so a pack of six
eggs is paid once and used across meals; pantry and freezer items (rice, oil,
frozen spinach...) are charged at the share the week uses; loose produce is
bought by weight.

Nutrition per recipe comes from CIQUAL (ANSES) values of its ingredients.
Recipes are drafts (data/recipes.json, status "draft").
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pulp

from .milp import replace_objective, solve
from .needs import Profile, daily_needs, energy_kcal, resting_kcal
from .profile import MEALS, Levers, questions, resolve       # the three main meals are defined in profile.py
from .taxonomy import get_goal
from .reference import LIMIT_NUTRIENTS

DATA = Path(__file__).resolve().parent.parent / "data"
GOAL_BONUS = 3.0
# Snacks per day grow with the energy need (an athlete eats more often, not
# only bigger plates); with 3 or more a day a snack may come back daily.
SNACKS_PER_DAY = ((2800, 2), (3800, 3), (float("inf"), 4))   # (up to kcal/day, snacks)
SNACK_REPEAT = 4        # the same snack at most 4 times a week (7 when 3+ a day)
# Energy is a hard band, never traded for budget: a plan that saves money by
# feeding less is unsafe (and would train restriction). Too little budget for
# enough food returns the minimum budget instead.
ENERGY_BAND = (0.9, 1.15)
# A deficit week's band starts at 97 % of its target (0.85 x maintenance), so the
# planned deficit is at most 1 - 0.97 x 0.85, about 17.5 % of maintenance; and no week
# is planned below resting energy x days, whatever the goal (_energy_band).
DEFICIT_BAND_MIN = 0.97
# Recipes are written for ~2,100 kcal a day; meal portions scale with the
# person's energy need (snacks do not), within these bounds. Measured over the
# input space (age 14-100, 30-250 kg, 120-230 cm, every activity level): plans
# exist from ~470 to ~6,200 kcal a day; only extreme combinations above that
# get "energy" as the reason.
REFERENCE_KCAL = 2100
# The WHO 50 g/day sugar limit is for FREE sugars (added sugars, honey), not
# the sugars naturally in fruit and milk. Only these ingredients count.
FREE_SUGAR_INGREDIENTS = {"honey", "dark-chocolate"}
VEGAN_B12_NOTE = ("Vitamin B12 is found almost only in animal foods: on a vegan diet, take a B12 "
                  "supplement or B12-fortified foods (a pharmacist can advise).")
REPEAT_PENALTY = 0.03   # objective cost of one repeat beyond the variety cap
REPEAT_EUR = 1.0        # the same, in euros, for the cheapest-week solve
SOLVE_SECONDS = 10      # safety net; with the 1% gap (engine/milp.py) plans take well under 1 s
# Macro targets for the day view: EFSA reference intake ranges as shares of
# energy (carbohydrates 45-60 %, fat 20-35 %), shown at their midpoints; protein
# is the person's need (engine/needs.py). Targets to aim for, not limits.
CARBS_ENERGY = (0.45, 0.60)
FAT_ENERGY = (0.20, 0.35)
MACROS = {"protein": "proteins", "carbs": "carbohydrates", "fat": "fat"}
# Soft levers from the answers (engine/profile.py), behind the needs (see the
# docstring): a lever missed by its whole threshold costs PREFERENCE_WEIGHT.
PREFERENCE_WEIGHT = 1.0
NEEDS_TOLERANCE = 0.03      # what a lever may take from a nutrient's coverage, at most
LEVER_COST = 1.05           # the levers may make the week at most 5 % dearer (within the budget)
PROTEIN_NEED_WEIGHT = 20.0  # a protein strategy raises a need: it comes before the levers
# The plan reports each lever day by day: a share counts within half a point of its
# threshold, a protein amount from 98 % of it.
SHARE_TOLERANCE = 0.005
DAY_ENERGY_TOLERANCE = 0.10  # _arrange keeps a day within 10 % of the daily target (or no further off)
PROTEIN_TOLERANCE = 0.98
SOFT_LEVERS = ("meal_carb_share", "meal_energy_share", "protein_target", "protein_per_meal", "meal_protein")
PACKED = {"fridge", "bakery"}   # bought in whole packs; pantry/freezer count the share used
PORTION_SCALE = (0.4, 2.5)
_EXCLUDED = {"vegetarian": {"meat", "fish"}, "vegan": {"meat", "fish", "dairy", "egg", "honey"}}
DIETS = (None, "vegetarian", "vegan")
APPLIANCES = ("hob", "microwave", "kettle", "blender")   # what recipes may need
MIN_OPTIONS = 3         # a main meal with fewer recipes than this is short: the plan says what to relax


@lru_cache(maxsize=1)
def _load() -> tuple[dict, list[dict], dict]:
    ingredients = {i["id"]: i for i in json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))["ingredients"]}
    recipes = json.loads((DATA / "recipes.json").read_text(encoding="utf-8"))["recipes"]
    prices = json.loads((DATA / "ingredient_prices.json").read_text(encoding="utf-8"))
    return ingredients, recipes, prices


def chains() -> list[dict]:
    _i, _r, prices = _load()
    return [{"id": cid, "label": c["label"], "tier": c["tier"], "price_index": c["index"]}
            for cid, c in prices["chains"].items()]


@dataclass
class Recipe:
    id: str
    en: str
    fr: str
    meals: list[str]
    batch: bool
    time_min: int
    equipment: list[str]
    ingredients: list[dict]
    steps: list[str]
    nutrients: dict[str, float] = field(default_factory=dict)
    animal: set = field(default_factory=set)
    tags: frozenset[str] = frozenset()      # its ingredients' tags and its own ("spicy")


def portion_scale(profile: Profile, kcal: float | None = None) -> float:
    """Meal portions for a daily energy target: ``kcal``, or the person's need when not given."""
    lo, hi = PORTION_SCALE
    kcal = energy_kcal(profile) if kcal is None else kcal
    return round(min(hi, max(lo, kcal / REFERENCE_KCAL)), 2)


def _recipes(rec, scale: float = 1.0) -> list[Recipe]:
    ingredients, raw, _p = _load()
    out = []
    for r in raw:
        totals: dict[str, float] = {}
        animal = set()
        tags = set(r.get("tags", []))
        k = 1.0 if "snack" in r["meals"] else scale
        items = [{"id": i["id"], "g": round(i["g"] * k)} for i in r["ingredients"]]
        for item in items:
            ing = ingredients[item["id"]]
            tags.update(ing["tags"])
            if ing.get("animal"):
                animal.add(ing["animal"])
            food = rec.food_by_id.get(f"ciqual-{ing['ciqual']}")
            if food is None:
                continue
            for n, per100 in food.nutrients.items():
                totals[n] = totals.get(n, 0.0) + per100 * item["g"] / 100.0
            if item["id"] in FREE_SUGAR_INGREDIENTS:
                totals["free-sugars"] = totals.get("free-sugars", 0.0) +                     food.nutrients.get("sugars", 0.0) * item["g"] / 100.0
        out.append(Recipe(r["id"], r["en"], r["fr"], r["meals"], bool(r.get("batch")), r.get("time_min", 0),
                          r.get("equipment", []), items, r.get("steps", []), totals, animal, frozenset(tags)))
    return out


def _price(ingredient_id: str, chain: str) -> tuple[float, float | None, bool]:
    """(EUR per kg, pack grams, estimated?) at a chain."""
    ingredients, _r, prices = _load()
    entry = prices["prices"][ingredient_id]
    at = entry["by_chain"].get(chain) or {}
    eur_kg = at.get("eur_kg") or entry["national_eur_kg"]
    # a standard pack size, where shops sell one (eggs: a box of 6), beats the
    # median of the few barcodes a chain has receipts for
    pack = ingredients[ingredient_id].get("pack_g") or at.get("pack_g") or entry.get("pack_g")
    return eur_kg, pack, bool(at.get("estimated", True))


@dataclass
class _Week:
    """Everything a week is planned or checked against, for one person and shop."""
    profile: Profile
    goal: str | None
    chain: str
    diet: str | None
    days: int
    scale: float
    by_id: dict
    meals: list
    snacks: list
    weekly: dict                                    # the needs (reference intakes) x days: what coverage is against
    kcal_target: float
    assoc: dict
    weight: dict
    limits: dict
    snacks_per_day: int
    snack_repeat: int
    pantry: frozenset
    levers: Levers                                  # what the answers turn on (engine/profile.py)
    goal_of: dict                                   # goal nutrient -> the goal that set its weight
    resting_kcal: float                             # per day: the floor under the energy target
    protein_target: float                           # g a week: the need, or a protein strategy's g/kg when higher
    evidence: dict = field(default_factory=dict)   # goal nutrient -> {"grade", "eu_claim"}

    def allowed(self, r: Recipe, meal: str) -> bool:
        """Whether ``r`` may be served at ``meal``: one of its meals, and no caffeine where the person asked for none."""
        return meal in r.meals and not ("caffeine" in r.tags and meal in self.levers.no_caffeine_at)


def _within_time(r: Recipe, levers: Levers) -> bool:
    """Within the cooking time asked; a batch recipe (cooked once for three days) may take three times as long."""
    limit = levers.max_minutes
    return limit is None or r.time_min <= (3 * limit if r.batch and levers.batch_ok else limit)


def _context(rec, profile: Profile, *, goal, chain, diet, equipment, pantry, days,
             answers=None, declined=None, avoid_recipes=None) -> _Week:
    ingredients, raw, prices = _load()
    if chain not in prices["chains"]:
        raise ValueError(f"unknown chain: {chain}")
    # Unknown values are errors, never silently ignored: a misspelt "vegan"
    # must not produce a week with meat in it.
    if diet not in DIETS:
        raise ValueError(f"diet must be one of {[d for d in DIETS if d]} or none")
    if equipment is not None and not set(equipment) <= set(APPLIANCES):
        raise ValueError(f"equipment must be among {list(APPLIANCES)}")
    if goal is not None and goal not in rec.scorer.positive and get_goal(goal) is None:
        raise ValueError(f"unknown goal: {goal}")
    unknown = set(pantry or ()) - set(ingredients)
    if unknown:
        raise ValueError(f"unknown pantry ingredients: {sorted(unknown)}")
    profile.validate()
    # The answers as levers; no answers at all give Levers.none(goal), the planner as before.
    levers = resolve(answers, declined, profile, goal=goal, known_goals=set(rec.scorer.positive),
                     avoid_recipes=avoid_recipes)
    unknown = levers.avoid_recipes - {r["id"] for r in raw}
    if unknown:
        raise ValueError(f"unknown recipes in avoid_recipes: {sorted(unknown, key=str)}")
    resting = resting_kcal(profile)
    kcal_day = max(resting, energy_kcal(profile) * levers.energy_factor)
    scale = portion_scale(profile, kcal_day)
    recipes = [r for r in _recipes(rec, scale) if not (r.animal & _EXCLUDED.get(diet or "", set()))]
    if equipment is not None:
        allowed = set(equipment) | {"kettle"}
        recipes = [r for r in recipes if set(r.equipment) <= allowed]
    # Hard filters from the answers. The pantry only prices what is left: an
    # excluded recipe stays out whatever is at home.
    recipes = [r for r in recipes if not (r.tags & levers.exclude) and r.id not in levers.avoid_recipes
               and _within_time(r, levers)]
    nutrient_ids = sorted({n for r in recipes for n in r.nutrients})
    daily = daily_needs(profile, nutrient_ids)
    weekly = {n: v * days for n, v in daily.items()}
    # A protein strategy raises the protein target, not the need: the first solve plans
    # the reference needs, and the g/kg is a lever of the second (_after_needs).
    protein_day = daily["proteins"]
    if levers.protein_g_per_kg:
        protein_day = round(max(protein_day, levers.protein_g_per_kg * profile.weight_kg), 1)
    # a(n) = max_g alpha_g * a_g(n). The person's goal comes first in levers.goals and
    # keeps the nutrients it ties on; alone (alpha 1) it gives today's associations.
    assoc, goal_of, grade_of = {}, {}, {}
    for g, alpha in levers.goals.items():
        for n, (a, grade) in {n: (a, grade) for n, a, grade in rec.scorer.positive.get(g, [])}.items():
            if n not in assoc or alpha * a > assoc[n]:
                assoc[n], goal_of[n], grade_of[n] = alpha * a, g, grade
    evidence = {}
    for n, g in goal_of.items():
        meta = rec.edge_meta.get(f"{n}->{g}", {})
        evidence[n] = {"grade": meta.get("evidence", grade_of[n]), "eu_claim": bool(meta.get("eu_claim"))}
    per_day = next(n for kcal, n in SNACKS_PER_DAY if kcal_day <= kcal)
    return _Week(
        profile=profile, goal=goal, chain=chain, diet=diet, days=days, scale=scale,
        by_id={r.id: r for r in recipes},
        meals=[r for r in recipes if any(m in MEALS for m in r.meals)],
        snacks=[r for r in recipes if "snack" in r.meals],
        weekly=weekly, kcal_target=kcal_day * days, assoc=assoc,
        weight={n: 1.0 + GOAL_BONUS * assoc.get(n, 0.0) for n in weekly},
        limits={("free-sugars" if n == "sugars" else n): lim * days for n, lim in LIMIT_NUTRIENTS.items()},
        snacks_per_day=per_day, snack_repeat=SNACK_REPEAT if per_day <= 2 else days,
        pantry=frozenset(pantry or ()),
        levers=levers, goal_of=goal_of, resting_kcal=resting, protein_target=protein_day * days, evidence=evidence)


def _energy_band(ctx: _Week) -> tuple[float, float]:
    """
    The week's hard energy band, in kcal: ENERGY_BAND of the target, from DEFICIT_BAND_MIN of it
    in a deficit, and never below resting energy x days. Without answers the lower edge is
    today's 90 % (with a PAL of at least 1.2, 0.9 x the target is above resting energy).
    """
    low = DEFICIT_BAND_MIN if ctx.levers.energy_goal == "deficit" else ENERGY_BAND[0]
    return max(low * ctx.kcal_target, ctx.resting_kcal * ctx.days), ENERGY_BAND[1] * ctx.kcal_target


def _option_counts(ctx: _Week) -> dict[str, int]:
    """How many recipes the plan may choose from at each main meal: ``ctx.allowed``, the plan's own filter."""
    return {m: sum(ctx.allowed(r, m) for r in ctx.meals) for m in MEALS}


def _looser(answers: dict, diet: str | None, avoid_recipes: list[str], meal: str):
    """
    The settings one step looser, one change at a time, in the order they are offered:
    (filter, now, try, what to change in the context). ``try`` is None where the filter is lifted;
    the recipes "not for me" come back for ``meal`` only.
    """
    levels = next(q["options"] for q in questions() if q["id"] == "cook_time")      # 10, 20, 30, any
    if answers.get("cook_time") in levels[:-1]:
        longer = levels[levels.index(answers["cook_time"]) + 1]
        yield "cook_time", answers["cook_time"], longer, {"answers": {**answers, "cook_time": longer}}
    for category in answers.get("dont_eat", []):
        rest = [c for c in answers["dont_eat"] if c != category]
        yield "dont_eat", category, None, {"answers": {**answers, "dont_eat": rest}}
    if answers.get("batch_ok") != "yes":
        yield "batch_ok", answers.get("batch_ok", "no"), "yes", {"answers": {**answers, "batch_ok": "yes"}}
    meals_of = {r["id"]: r["meals"] for r in _load()[1]}
    avoided = sorted(i for i in set(avoid_recipes) if meal in meals_of[i])
    if avoided:
        yield "avoid_recipes", avoided, [], {"avoid_recipes": [i for i in avoid_recipes if i not in avoided]}
    if diet:
        looser = DIETS[DIETS.index(diet) - 1]
        yield "diet", diet, looser, {"diet": looser}


def _relax(rec, profile: Profile, *, goal, chain, diet, equipment, pantry, days, answers, declined, avoid_recipes,
           base: _Week | None = None) -> list[dict]:
    """
    What to loosen, for each main meal with fewer than MIN_OPTIONS recipes (``base``: the context of these
    settings, built here when not given). Each setting is loosened on its own and the recipes at the meal counted
    again (no solve): a longer cooking time, a food allowed again, batch cooking, the recipes "not for me" at
    that meal, the diet one step looser. Only a change that adds recipes is kept: the best three per meal,
    {"filter", "now", "try", "meal", "options_now", "options"}, most recipes first. [] when no meal is short.
    """
    kw = dict(goal=goal, chain=chain, diet=diet, equipment=equipment, pantry=pantry, days=days,
              answers=answers, declined=declined, avoid_recipes=avoid_recipes)
    base = _context(rec, profile, **kw) if base is None else base
    now = _option_counts(base)
    counted: dict = {}      # the same change asked of several meals is counted once
    found = []
    for m in (m for m in MEALS if now[m] < MIN_OPTIONS):
        entries = []
        for name, was, then, change in _looser(dict(answers or {}), diet, list(avoid_recipes or ()), m):
            key = (name, repr(was), repr(then))
            if key not in counted:
                counted[key] = _option_counts(_context(rec, profile, **{**kw, **change}))
            if counted[key][m] > now[m]:
                entries.append({"filter": name, "now": was, "try": then, "meal": m,
                                "options_now": now[m], "options": counted[key][m]})
        found += sorted(entries, key=lambda e: -e["options"])[:3]
    return sorted(found, key=lambda e: -e["options"])


def plan_week(rec, profile: Profile, *, goal: str | None, budget: float, chain: str,
              diet: str | None = None, days: int = 7, equipment: list[str] | None = None,
              pantry: list[str] | None = None, answers: dict | None = None, declined: list[str] | None = None,
              avoid_recipes: list[str] | None = None, _cheapest: bool = False, _ignore_energy: bool = False) -> dict:
    """
    The best week within the budget. ``pantry``: ingredients already at home,
    which cost nothing (the planner then tends to use them). ``answers``: the
    person's answers to the questions (engine/profile.py), ``declined``: the
    strategy ids they turned down, ``avoid_recipes``: recipes marked "not for me".
    """
    ingredients = _load()[0]
    ctx = _context(rec, profile, goal=goal, chain=chain, diet=diet, equipment=equipment,
                   pantry=pantry, days=days, answers=answers, declined=declined, avoid_recipes=avoid_recipes)
    relax = [] if _cheapest else _relax(rec, profile, goal=goal, chain=chain, diet=diet, equipment=equipment,
                                        pantry=pantry, days=days, answers=answers, declined=declined,
                                        avoid_recipes=avoid_recipes, base=ctx)
    if 0 in _option_counts(ctx).values():       # a meal no recipe fits: nothing to solve, but what to relax
        return _no_plan(ctx, budget, status="no recipes", reason="recipes", minimum=None, relax=relax)
    by_id, weekly, limits, kcal_target = ctx.by_id, ctx.weekly, ctx.limits, ctx.kcal_target

    prob = pulp.LpProblem("week", pulp.LpMaximize)
    x = {}
    for r in ctx.meals:
        for m in MEALS:
            if ctx.allowed(r, m):
                x[r.id, m] = prob.add_variable(f"x_{r.id}_{m}", 0, days, cat="Integer")
    s = {r.id: prob.add_variable(f"s_{r.id}", 0, ctx.snack_repeat, cat="Integer") for r in ctx.snacks}
    servings = list(x.items()) + [((rid, "snack"), v) for rid, v in s.items()]

    def intake(n):
        return pulp.lpSum(by_id[rid].nutrients.get(n, 0.0) * v for (rid, _m), v in servings)

    for m in MEALS:
        prob += pulp.lpSum(v for (rid, mm), v in x.items() if mm == m) == days, f"count_{m}"
    # Variety: a recipe 2 times a week (3 for batch cooking). Soft, so that a
    # narrow combination (vegan + microwave only) still gets a plan, with repeats.
    # The first extra time of a recipe costs 1, each further one 3: repeats
    # spread over several recipes instead of one dish every night.
    repeats = {}
    for r in ctx.meals:
        vs = [v for (rid, _m), v in x.items() if rid == r.id]
        once = prob.add_variable(f"rep1_{r.id}", 0, 1, cat="Integer")
        more = prob.add_variable(f"rep2_{r.id}", 0, cat="Integer")
        repeats[r.id] = (once, more)
        prob += pulp.lpSum(vs) <= _variety_cap(r) + once + more, f"variety_{r.id}"
    extra = pulp.lpSum(once + 3 * more for once, more in repeats.values())
    y = {n: prob.add_variable(f"y_{n}", 0, 1) for n in weekly}
    for n in weekly:
        prob += y[n] * weekly[n] <= intake(n), f"cover_{n}"
    prob += pulp.lpSum(s.values()) <= ctx.snacks_per_day * days, "snacks_per_day"
    e_over, e_under = prob.add_variable("e_over", 0), prob.add_variable("e_under", 0)
    prob += intake("energy-kcal") - kcal_target == e_over - e_under, "energy"
    if not _ignore_energy:                      # in every solve: the plan, its levers, the cheapest week
        low, high = _energy_band(ctx)
        prob += intake("energy-kcal") >= low, "energy_min"
        prob += intake("energy-kcal") <= high, "energy_max"
    slack = {n: prob.add_variable(f"slack_{n}", 0) for n in limits}
    for n, lim in limits.items():
        prob += intake(n) <= lim + slack[n], f"limit_{n}"

    # cost: what has to be bought (ingredients at home are free)
    usage = {}
    for (rid, _m), v in servings:
        for item in by_id[rid].ingredients:
            usage.setdefault(item["id"], []).append((item["g"], v))
    cost_terms = []
    for iid, uses in usage.items():
        if iid in ctx.pantry:
            continue
        eur_kg, pack_g, _est = _price(iid, chain)
        grams = pulp.lpSum(g * v for g, v in uses)
        if ingredients[iid]["storage"] in PACKED and pack_g:
            n_packs = prob.add_variable(f"p_{iid}", 0, cat="Integer")
            prob += n_packs * pack_g >= grams, f"pack_{iid}"
            cost_terms.append(n_packs * pack_g * eur_kg / 1000)
        else:
            cost_terms.append(grams * eur_kg / 1000)
    cost = pulp.lpSum(cost_terms)
    if _cheapest:
        # Cheapest week that still feeds enough and stays under the limits.
        prob += -cost - 5 * pulp.lpSum(slack[n] / limits[n] for n in limits) - REPEAT_EUR * extra, "objective"
        ok, _status = solve(prob, time_limit=SOLVE_SECONDS)
        return {"feasible": ok, "total_cost": round(pulp.value(cost), 2) if ok else None}
    prob += cost <= budget, "budget"

    total_w = sum(ctx.weight.values()) or 1.0
    objective = (pulp.lpSum(ctx.weight[n] * y[n] for n in weekly) / total_w
                 - (e_over + e_under) / kcal_target
                 - 5 * pulp.lpSum(slack[n] / limits[n] for n in limits)
                 - REPEAT_PENALTY * extra
                 - 0.01 * cost / max(budget, 1))
    prob += objective, "objective"
    ok, status = solve(prob, time_limit=SOLVE_SECONDS)
    if not ok:
        minimum, reason = _minimum_budget(rec, profile, goal, chain, diet, days, equipment, pantry=pantry,
                                          answers=answers, declined=declined, avoid_recipes=avoid_recipes)
        return _no_plan(ctx, budget, status=status, reason=reason, minimum=minimum, relax=relax)

    def chosen() -> tuple[dict, dict]:
        return ({k: int(round(v.value() or 0)) for k, v in x.items()},
                {k: int(round(v.value() or 0)) for k, v in s.items()})

    counts, snack_counts = chosen()
    soft = any(a["lever"]["type"] in SOFT_LEVERS for a in ctx.levers.applied)   # none without answers
    if soft and _after_needs(prob, ctx, objective, x, y, intake, cost, e_over + e_under):
        counts, snack_counts = chosen()
    week = _balance(ctx, _schedule(counts, snack_counts, by_id, days))
    return _assemble(ctx, _arrange(ctx, week), budget=budget, relax=relax)


def _variety_cap(r: Recipe) -> int:
    return 3 if r.batch else 2


def _after_needs(prob: pulp.LpProblem, ctx: _Week, objective, x: dict, y: dict, intake, cost, off) -> bool:
    """
    Needs first: the levers' solve, from the week just solved without them, which
    covers the needs as well as they can be. From here no nutrient may fall more
    than NEEDS_TOLERANCE below that week's coverage (nor below 97 % of its need,
    nor below the week where it was lower), the energy may move at most
    NEEDS_TOLERANCE further from the target, and the week may cost at most
    LEVER_COST times as much (the cost term alone is below the solver's gap).
    Within that, a raised protein need weighs PROTEIN_NEED_WEIGHT, the levers
    PREFERENCE_WEIGHT. True when the model holds a new week to read; else the
    first week stands (it meets every bound, so this rarely happens).
    """
    for n in ctx.weekly:
        prob += y[n] >= min(1.0 - NEEDS_TOLERANCE, y[n].value() or 0.0) - 1e-6, f"needs_{n}"
    prob += off <= (pulp.value(off) or 0.0) + NEEDS_TOLERANCE * ctx.kcal_target + 1e-6, "needs_energy"
    prob += cost <= LEVER_COST * (pulp.value(cost) or 0.0) + 1e-6, "lever_cost"
    terms = _lever_terms(prob, ctx, x, intake)
    if ctx.levers.protein_g_per_kg:       # the strategy's target, above the need the first solve planned
        sl = prob.add_variable("lever_protein", 0)
        prob += intake("proteins") + sl >= ctx.protein_target, "lever_protein"
        terms.append(PROTEIN_NEED_WEIGHT * sl / ctx.protein_target)
    replace_objective(prob, objective - pulp.lpSum(terms))
    return solve(prob, time_limit=SOLVE_SECONDS)[0]


def _lever_terms(prob: pulp.LpProblem, ctx: _Week, x: dict, intake) -> list:
    """
    The soft levers as penalties for the objective, each PREFERENCE_WEIGHT when the
    lever is missed by its whole threshold (added for the second solve only).
    Shares are written on the week's totals (S_m(n): the week's n from meal m) and
    reported day by day (_strategy_report). Protein per meal is a constant per
    recipe: how far one serving falls short of the threshold.
    """
    lv, days, kcal = ctx.levers, ctx.days, ctx.kcal_target
    kg = ctx.profile.weight_kg

    def at(meal: str, n: str):
        return pulp.lpSum(ctx.by_id[rid].nutrients.get(n, 0.0) * v for (rid, m), v in x.items() if m == meal)

    def short_of(t: float, meals) -> pulp.LpAffineExpression:
        return pulp.lpSum(max(0.0, t - ctx.by_id[rid].nutrients.get("proteins", 0.0)) / t * v
                          for (rid, m), v in x.items() if m in meals)

    terms = []
    for meal, p in lv.meal_carb_share.items():      # the week's carbs at the reference midpoint
        sl = prob.add_variable(f"lever_carbs_{meal}", 0)
        prob += at(meal, "carbohydrates") + sl >= p * intake("carbohydrates"), f"lever_carbs_{meal}"
        terms.append(PREFERENCE_WEIGHT * sl / (p * sum(CARBS_ENERGY) / 2 * kcal / 4))
    # A breakfast floor holds against the week's energy and against its target, so
    # eating less never meets it; a ceiling is taken of the target, so eating more
    # never does (a ceiling of min(intake, target) made the solve take over 10 s).
    if lv.breakfast_energy_min:
        p = lv.breakfast_energy_min
        sl = prob.add_variable("lever_breakfast_min", 0)
        prob += at("breakfast", "energy-kcal") + sl >= p * intake("energy-kcal"), "lever_breakfast_min"
        prob += at("breakfast", "energy-kcal") + sl >= p * kcal, "lever_breakfast_min_target"
        terms.append(PREFERENCE_WEIGHT * sl / (p * kcal))
    if lv.breakfast_energy_max:
        p = lv.breakfast_energy_max
        sl = prob.add_variable("lever_breakfast_max", 0)
        prob += at("breakfast", "energy-kcal") - sl <= p * kcal, "lever_breakfast_max"
        terms.append(PREFERENCE_WEIGHT * sl / (p * kcal))
    if lv.protein_per_meal_g_per_kg:
        terms.append(PREFERENCE_WEIGHT * short_of(lv.protein_per_meal_g_per_kg * kg, MEALS) / (len(MEALS) * days))
    if lv.breakfast_protein_g_per_kg:
        terms.append(PREFERENCE_WEIGHT * short_of(lv.breakfast_protein_g_per_kg * kg, ("breakfast",)) / days)
    return terms


def _assemble(ctx: _Week, week: list[dict], *, budget: float, edited: bool = False,
              relax: list[dict] | None = None) -> dict:
    """
    A plan from a composed week ([{"meals": {meal: recipe id}, "snacks": [ids]}]):
    shopping list (whole packs for fridge and bakery items, ingredients at home
    free), cost, energy, coverage and limits. Deterministic, so a week the user
    edited is checked exactly like one the solver chose. ``relax``: what to loosen
    for a meal with few recipes (_relax), none when not given.
    """
    ingredients, _raw, prices = _load()
    by_id, days = ctx.by_id, ctx.days
    eaten = [by_id[rid] for d in week for rid in list(d["meals"].values()) + list(d["snacks"])]
    intake: dict[str, float] = {}
    grams: dict[str, float] = {}
    for r in eaten:
        for n, v in r.nutrients.items():
            intake[n] = intake.get(n, 0.0) + v
        for item in r.ingredients:
            grams[item["id"]] = grams.get(item["id"], 0.0) + item["g"]
    basket = _basket(grams, ctx.chain, ingredients, ctx.pantry)
    total_cost = round(sum(b["cost"] for b in basket), 2)
    coverage = {n: round(100 * intake.get(n, 0.0) / ctx.weekly[n], 1) for n in ctx.weekly}
    served = {}
    for d in week:
        for rid in d["meals"].values():
            served[rid] = served.get(rid, 0) + 1
    extra = sum(max(0, c - _variety_cap(by_id[rid])) for rid, c in served.items())
    planned = intake.get("energy-kcal", 0.0)

    def amounts(r) -> dict:
        n = r.nutrients
        return {"kcal": round(n.get("energy-kcal", 0.0)), **{k: round(n.get(v, 0.0), 1) for k, v in MACROS.items()}}

    def show(rid, meal=True):
        r = by_id[rid]
        out = {"id": r.id, "en": r.en, "fr": r.fr, **amounts(r)}
        return {**out, "time_min": r.time_min, "batch": r.batch} if meal else out

    goal_ids = [n for n in sorted(ctx.assoc, key=lambda n: -ctx.assoc[n]) if n in ctx.weekly]

    def day_view(i: int, d: dict) -> dict:
        eaten_today = [by_id[rid] for rid in list(d["meals"].values()) + list(d["snacks"])]
        total = {"kcal": round(sum(r.nutrients.get("energy-kcal", 0.0) for r in eaten_today)),
                 **{k: round(sum(r.nutrients.get(v, 0.0) for r in eaten_today), 1) for k, v in MACROS.items()}}
        goal_today = {n: round(100 * sum(r.nutrients.get(n, 0.0) for r in eaten_today) / (ctx.weekly[n] / days), 1)
                      for n in goal_ids}
        # which meal of the day gives most of each goal nutrient: the food -> nutrient
        # edge of the graph, at a glance
        slots = [(m, by_id[rid]) for m, rid in d["meals"].items()] + [("snack", by_id[rid]) for rid in d["snacks"]]
        goal_from = {}
        for n in goal_ids:
            meal, r = max(slots, key=lambda mr: mr[1].nutrients.get(n, 0.0))
            if r.nutrients.get(n, 0.0) > 0:
                goal_from[n] = {"meal": meal, "id": r.id, "en": r.en}
        return {"day": i + 1, "meals": {m: show(d["meals"][m]) for m in MEALS if m in d["meals"]},
                "snacks": [show(rid, meal=False) for rid in d["snacks"]], "totals": total,
                "goal_today": goal_today, "goal_from": goal_from}

    kcal_day = ctx.kcal_target / days
    low, high = _energy_band(ctx)
    targets = {"kcal": round(kcal_day),
               "protein": round(ctx.protein_target / days, 1),
               "carbs": round(kcal_day * sum(CARBS_ENERGY) / 2 / 4, 1),
               "fat": round(kcal_day * sum(FAT_ENERGY) / 2 / 9, 1),
               "carbs_energy": list(CARBS_ENERGY), "fat_energy": list(FAT_ENERGY)}

    return {
        "feasible": True, "edited": edited,
        "chain": {"id": ctx.chain, "label": prices["chains"][ctx.chain]["label"]},
        "budget": budget, "total_cost": total_cost, "within_budget": total_cost <= budget + 1e-9,
        "energy": {"target_per_day": round(ctx.kcal_target / days), "planned_per_day": round(planned / days),
                   "in_band": low - 1e-6 <= planned <= high + 1e-6,
                   "goal": ctx.levers.energy_goal, "resting": round(ctx.resting_kcal),
                   "days_below_resting": sum(_day_total(ctx, d, "energy-kcal") < ctx.resting_kcal - 1e-6 for d in week)},
        "protein_target_g": targets["protein"],
        "demographic": ctx.profile.demographic.value,
        "portion_scale": ctx.scale,
        "goal": ctx.goal, "goals": [{"id": g, "alpha": alpha} for g, alpha in ctx.levers.goals.items()],
        "strategies": _strategy_report(ctx, week), "relax": relax or [],
        "goal_nutrients": [n for n in sorted(ctx.assoc, key=lambda n: -ctx.assoc[n]) if n in coverage],
        "goal_evidence": {n: ctx.evidence[n] for n in ctx.assoc if n in ctx.evidence},
        "coverage": coverage,
        "limits": {n: round(100 * intake.get(n, 0.0) / lim, 1) for n, lim in ctx.limits.items()},
        "days": [day_view(i, d) for i, d in enumerate(week)],
        "targets": targets,
        "basket": basket, "pantry": sorted(ctx.pantry),
        "diet_note": VEGAN_B12_NOTE if ctx.diet == "vegan" else None,
        "repeats": extra,
        "notes": ["Pantry and freezer items (rice, oil, frozen vegetables…) are counted at the share this week uses.",
                  "Prices: Open Prices medians for this chain; items marked 'estimated' use the national median x the chain's price index.",
                  "Ingredients you have at home cost nothing in this plan.",
                  "Recipes are drafts awaiting review by a dietitian."],
    }


def _amount(ctx: _Week, rid: str, n: str) -> float:
    return ctx.by_id[rid].nutrients.get(n, 0.0)


def _day_total(ctx: _Week, d: dict, n: str) -> float:
    return sum(_amount(ctx, rid, n) for rid in list(d["meals"].values()) + list(d["snacks"]))


def _share(ctx: _Week, d: dict, lever: dict) -> float:
    """A share lever's meal's share of the day's carbohydrates or energy."""
    n = "carbohydrates" if lever["type"] == "meal_carb_share" else "energy-kcal"
    total = _day_total(ctx, d, n)
    return _amount(ctx, d["meals"][lever["meal"]], n) / total if total else 0.0


def _off_band(ctx: _Week, d: dict) -> float:
    """How far the day's energy is outside ENERGY_BAND of the daily target, as a fraction of it (0 inside)."""
    e = _day_total(ctx, d, "energy-kcal") / (ctx.kcal_target / ctx.days)
    return max(0.0, ENERGY_BAND[0] - e, e - ENERGY_BAND[1])


def _shortfall(ctx: _Week, lever: dict, d: dict) -> float:
    """
    How far one day falls short of a soft lever: 0 when the day meets it, else in
    share points or as a fraction of the protein threshold. A share counts within
    SHARE_TOLERANCE of its threshold, a protein amount from PROTEIN_TOLERANCE of it.
    A breakfast energy share counts only on a day inside the energy band, and is
    taken of the day's energy or of its target, whichever is less favourable: a
    day eaten smaller (or bigger) never makes the breakfast count.
    ``lever["meal"]`` is always set: profile.resolve names the meal a "meal_from" lever picked.
    """
    kind, kg = lever["type"], ctx.profile.weight_kg
    if kind == "meal_carb_share":
        s = _share(ctx, d, lever)
        return max(0.0, lever.get("min", 0.0) - SHARE_TOLERANCE - s, s - lever.get("max", 1.0) - SHARE_TOLERANCE)
    if kind == "meal_energy_share":
        meal = _amount(ctx, d["meals"][lever["meal"]], "energy-kcal")
        day, target = _day_total(ctx, d, "energy-kcal"), ctx.kcal_target / ctx.days
        gap = 0.0
        if "min" in lever:          # against the day or its target, the larger: a smaller day never helps
            gap += max(0.0, lever["min"] - SHARE_TOLERANCE - meal / max(day, target))
        if "max" in lever:          # and the smaller for a ceiling: a bigger day never helps
            gap += max(0.0, meal / min(day, target) - lever["max"] - SHARE_TOLERANCE)
        return gap + _off_band(ctx, d)
    t = lever["g_per_kg"] * kg
    if kind == "protein_target":
        return max(0.0, PROTEIN_TOLERANCE * t - _day_total(ctx, d, "proteins")) / t
    meals = MEALS if kind == "protein_per_meal" else ("breakfast",)
    return sum(max(0.0, PROTEIN_TOLERANCE * t - _amount(ctx, d["meals"][m], "proteins")) for m in meals) / t


def _strategy_report(ctx: _Week, week: list[dict]) -> list[dict]:
    """
    Each strategy and preference the answers turned on, with its evidence, the
    number of days of the composed week that meet it (``met_days``) and the week's
    mean as text (``value``). Measured on the days, so an edited week is reported
    like a solved one. The hard filters (no caffeine at a meal, foods not eaten,
    cooking time, batch cooking) hold on every day: no recipe outside them can be
    planned.
    """
    days, kg = ctx.days, ctx.profile.weight_kg
    out = []
    for entry in ctx.levers.applied:
        lever, kind = entry["lever"], entry["lever"]["type"]
        met = sum(_shortfall(ctx, lever, d) == 0 for d in week) if kind in SOFT_LEVERS else days
        if kind in ("meal_carb_share", "meal_energy_share"):
            mean = round(100 * sum(_share(ctx, d, lever) for d in week) / days)
            value = (f"{lever['meal']} carbs {mean} %" if kind == "meal_carb_share"
                     else f"{lever['meal']} {mean} % of energy")
        elif kind == "protein_target":
            value = f"protein {sum(_day_total(ctx, d, 'proteins') for d in week) / days / kg:.1f} g/kg"
        elif kind in ("protein_per_meal", "meal_protein"):
            label = "main meals" if kind == "protein_per_meal" else "breakfast"
            value = f"{label} ≥ {round(lever['g_per_kg'] * kg)} g protein on {met} of {days} days"
        else:
            value = _filter_value(ctx, lever, week)
        out.append({**{k: copy.deepcopy(v) for k, v in entry.items() if k != "lever"}, "met_days": met, "value": value})
    return out


def _filter_value(ctx: _Week, lever: dict, week: list[dict]) -> str:
    """What a hard filter did to the week, as text."""
    lv, kind = ctx.levers, lever["type"]
    if kind == "no_caffeine":
        return f"no caffeine at {lever['meal']}"
    if kind == "exclude_tags":
        return "none in the plan: " + ", ".join(c.replace("_", " or ") for c in sorted(lv.exclude))
    if kind == "max_minutes":
        batch = f", batch recipes within {3 * lv.max_minutes} min" if lv.batch_ok else ""
        return f"every meal within {lv.max_minutes} min{batch}"
    batch_meals = sum(ctx.by_id[rid].batch for d in week for rid in d["meals"].values())
    return f"{batch_meals} batch-cooked meals"          # batch_ok


def _arrange(ctx: _Week, week: list[dict]) -> list[dict]:
    """
    The solver chooses the week's meals; the soft levers are read day by day. Swap
    the breakfasts, lunches, dinners or snacks of two days while that meets the
    levers on more days, or brings the days that miss closer: the same food, the
    same cost and coverage, better days. A swap never takes either day's energy
    more than DAY_ENERGY_TOLERANCE from the daily target (nor further, for a day
    already off), nor below resting energy (nor lower, for a day already below:
    see _balance), and breakfast energy shares are measured so that a smaller day
    never meets them (_shortfall). Batch recipes keep their consecutive days, a
    recipe is never lunch and dinner on one day, and a snack never twice in one day.
    """
    levers = [e["lever"] for e in ctx.levers.applied if e["lever"]["type"] in SOFT_LEVERS]
    if not levers:
        return week
    week = [{"meals": dict(d["meals"]), "snacks": list(d["snacks"])} for d in week]

    def score(d: dict) -> tuple[int, float]:
        gaps = [_shortfall(ctx, lever, d) for lever in levers]
        return sum(g == 0 for g in gaps), -sum(gaps)

    per_day = ctx.kcal_target / ctx.days

    def off(d: dict) -> float:                      # the day's energy, as a distance from the daily target
        return abs(_day_total(ctx, d, "energy-kcal") - per_day)

    def ok(d: dict, was: float, was_kcal: float) -> bool:
        return (d["meals"].get("lunch") != d["meals"].get("dinner") and len(set(d["snacks"])) == len(d["snacks"])
                and off(d) <= max(was, DAY_ENERGY_TOLERANCE * per_day) + 1e-6
                and _day_total(ctx, d, "energy-kcal") >= min(was_kcal, ctx.resting_kcal) - 1e-6)

    def swaps(i: int, j: int):
        for m in MEALS:
            a, b = week[i]["meals"].get(m), week[j]["meals"].get(m)
            if a and b and a != b and not (ctx.by_id[a].batch or ctx.by_id[b].batch):
                yield "meals", m, m
        for p in range(len(week[i]["snacks"])):
            for q in range(len(week[j]["snacks"])):
                if week[i]["snacks"][p] != week[j]["snacks"][q]:
                    yield "snacks", p, q

    scores = [score(d) for d in week]
    improved = True
    while improved:
        improved = False
        for i in range(len(week)):
            for j in range(i + 1, len(week)):
                for part, p, q in list(swaps(i, j)):
                    di, dj = week[i][part], week[j][part]
                    was_i, was_j = off(week[i]), off(week[j])
                    kcal_i, kcal_j = _day_total(ctx, week[i], "energy-kcal"), _day_total(ctx, week[j], "energy-kcal")
                    di[p], dj[q] = dj[q], di[p]
                    new_i, new_j = score(week[i]), score(week[j])
                    before = (scores[i][0] + scores[j][0], scores[i][1] + scores[j][1])
                    after = (new_i[0] + new_j[0], new_i[1] + new_j[1])
                    if (ok(week[i], was_i, kcal_i) and ok(week[j], was_j, kcal_j)
                            and after > (before[0], before[1] + 1e-9)):
                        scores[i], scores[j], improved = new_i, new_j, True
                    else:
                        di[p], dj[q] = dj[q], di[p]
    return week


def _balance(ctx: _Week, week: list[dict]) -> list[dict]:
    """
    A deficit week's days, lifted to resting energy where the recipes allow. The solve
    holds the week at resting energy x days or above, but _schedule can still put the
    small meals on the same days. While a day is below resting energy, swap one of its
    main meals (with the same meal of another day) or snacks with another day, so long
    as that day stays at resting energy or above: each time the swap that lifts a low
    day most, and of those the one that moves the least energy. The same food, cost and
    coverage; batch recipes keep their days, a recipe is never lunch and dinner on one
    day and a snack never twice in one day (as in _arrange). Best effort: a day the
    recipes cannot lift stays below, and the plan counts it
    (``energy.days_below_resting``). Other weeks are returned as they are.
    """
    if ctx.levers.energy_goal != "deficit":
        return week
    week = [{"meals": dict(d["meals"]), "snacks": list(d["snacks"])} for d in week]
    rest = ctx.resting_kcal

    def kcal(d: dict) -> float:
        return _day_total(ctx, d, "energy-kcal")

    def swaps(low: dict, high: dict):
        for m in MEALS:
            a, b = low["meals"].get(m), high["meals"].get(m)
            if a and b and a != b and not (ctx.by_id[a].batch or ctx.by_id[b].batch):
                yield "meals", m, m, a, b
        for p, a in enumerate(low["snacks"]):
            for q, b in enumerate(high["snacks"]):
                if a != b:
                    yield "snacks", p, q, a, b

    def valid(d: dict) -> bool:
        return d["meals"].get("lunch") != d["meals"].get("dinner") and len(set(d["snacks"])) == len(d["snacks"])

    while True:                                     # each swap lowers the week's total shortfall: it ends
        best, best_key = None, (1e-6, 0.0)          # (lift, -kcal moved): the most lift, then the least moved
        for i, low in enumerate(week):
            short = rest - kcal(low)
            if short <= 1e-6:
                continue
            for j, high in enumerate(week):
                if j == i:
                    continue
                for part, p, q, a, b in list(swaps(low, high)):
                    moved = _amount(ctx, b, "energy-kcal") - _amount(ctx, a, "energy-kcal")
                    key = (min(moved, short), -moved)
                    if moved <= 0 or kcal(high) - moved < rest or key <= best_key:
                        continue
                    low[part][p], high[part][q] = b, a
                    if valid(low) and valid(high):
                        best, best_key = (i, j, part, p, q), key
                    low[part][p], high[part][q] = a, b
        if best is None:
            return week
        i, j, part, p, q = best
        week[i][part][p], week[j][part][q] = week[j][part][q], week[i][part][p]


def _schedule(counts: dict, snack_counts: dict, by_id: dict, days: int) -> list[dict]:
    """Spread recipe counts over the days; batch recipes on consecutive days. Returns recipe ids."""
    lines = {}
    for m in MEALS:
        seq = []
        for (rid, mm), c in sorted(counts.items(), key=lambda kv: (not by_id[kv[0][0]].batch, kv[0][0])):
            if mm == m:
                seq += [rid] * c
        lines[m] = seq[:days]
    # avoid the same recipe at lunch and dinner on the same day
    lunch, dinner = lines["lunch"], lines["dinner"]
    for d in range(days):
        if d < len(dinner) and d < len(lunch) and dinner[d] == lunch[d]:
            for e in range(days):
                if e != d and dinner[e] != lunch[d] and dinner[d] != lunch[e]:
                    dinner[d], dinner[e] = dinner[e], dinner[d]
                    break
    snack_seq = [rid for rid, c in sorted(snack_counts.items()) for _ in range(c)]
    return [{"meals": {m: lines[m][d] for m in MEALS if d < len(lines[m])},
             "snacks": [rid for i, rid in enumerate(snack_seq) if i % days == d]} for d in range(days)]


def _basket(grams_by_ingredient: dict, chain: str, ingredients: dict, pantry: frozenset = frozenset()) -> list[dict]:
    """
    The shopping list. ``cost`` is what this plan pays (0 for what is at home);
    ``price`` is what the line would cost bought, so the app can move items in
    and out of "at home" without asking the server.
    """
    order = {"fresh": 0, "bakery": 1, "fridge": 2, "freezer": 3, "pantry": 4}
    out = []
    for iid, grams in grams_by_ingredient.items():
        if grams <= 0:
            continue
        eur_kg, pack_g, estimated = _price(iid, chain)
        ing = ingredients[iid]
        if ing["storage"] in PACKED and pack_g:
            n = math.ceil(grams / pack_g - 1e-9)     # whole packs: the fewest that cover the week
            price = n * pack_g * eur_kg / 1000
            buy = {"packs": n, "pack_g": pack_g}
            if ing.get("unit_g"):                       # eggs: a box of 6, not 374 g
                buy["units_per_pack"] = max(1, round(pack_g / ing["unit_g"]))
        else:
            price = grams * eur_kg / 1000
            buy = {"grams": round(grams)}
            if ing.get("unit_g") and grams >= 0.75 * ing["unit_g"]:   # loose produce: "about 8 apples"
                buy["about_units"] = max(1, round(grams / ing["unit_g"]))
        at_home = iid in pantry
        out.append({"id": iid, "food_id": f"ciqual-{ing['ciqual']}", "en": ing["en"], "fr": ing["fr"],
                    "storage": ing["storage"], "liquid": bool(ing.get("liquid")),
                    "grams_used": round(grams), **buy, "eur_kg": eur_kg,
                    "cost": 0.0 if at_home else price, "price": round(price, 2),
                    "at_home": at_home, "estimated": estimated})
    _round_to_cents(out)
    out.sort(key=lambda b: (order.get(b["storage"], 9), -b["price"]))
    return out


# ---------------------------------------------------------------- edits
def _week_from(ctx: _Week, week: list[dict]) -> list[dict]:
    """
    Validate a week sent back by the app: 7 days, and every recipe one the settings
    allow at its meal. A recipe the preferences or the avoided list took out of the
    context is refused like one that is not a dinner.
    """
    if len(week) != ctx.days:
        raise ValueError(f"a week has {ctx.days} days, got {len(week)}")
    out = []
    for i, d in enumerate(week):
        meals, snacks = dict(d.get("meals") or {}), list(d.get("snacks") or [])
        if set(meals) != set(MEALS):
            raise ValueError(f"day {i + 1} needs breakfast, lunch and dinner")
        for m, rid in meals.items():
            r = ctx.by_id.get(rid)
            if r is None or not ctx.allowed(r, m):
                raise ValueError(f"day {i + 1}: '{rid}' is not a {m} for these settings")
        for rid in snacks:
            if rid not in ctx.by_id or not ctx.allowed(ctx.by_id[rid], "snack"):
                raise ValueError(f"day {i + 1}: '{rid}' is not a snack for these settings")
        if len(snacks) > ctx.snacks_per_day:
            raise ValueError(f"day {i + 1}: at most {ctx.snacks_per_day} snacks")
        out.append({"meals": meals, "snacks": snacks})
    return out


def evaluate_week(rec, profile: Profile, week: list[dict], *, goal: str | None, budget: float, chain: str,
                  diet: str | None = None, equipment: list[str] | None = None,
                  pantry: list[str] | None = None, days: int = 7, answers: dict | None = None,
                  declined: list[str] | None = None, avoid_recipes: list[str] | None = None) -> dict:
    """The plan for a week the user edited (swapped meals), checked like a solved one."""
    ctx = _context(rec, profile, goal=goal, chain=chain, diet=diet, equipment=equipment, pantry=pantry, days=days,
                   answers=answers, declined=declined, avoid_recipes=avoid_recipes)
    relax = _relax(rec, profile, goal=goal, chain=chain, diet=diet, equipment=equipment, pantry=pantry, days=days,
                   answers=answers, declined=declined, avoid_recipes=avoid_recipes, base=ctx)
    return _assemble(ctx, _week_from(ctx, week), budget=budget, edited=True, relax=relax)


def _goal_score(ctx: _Week, coverage: dict) -> float:
    """The solver's objective on coverage: capped, goal nutrients weighted up."""
    total = sum(ctx.weight.values()) or 1.0
    return sum(ctx.weight[n] * min(coverage[n], 100.0) / 100.0 for n in ctx.weekly) / total


def swap_options(rec, profile: Profile, week: list[dict], day: int, meal: str, *, goal: str | None,
                 budget: float, chain: str, diet: str | None = None, equipment: list[str] | None = None,
                 pantry: list[str] | None = None, k: int = 3, days: int = 7, answers: dict | None = None,
                 declined: list[str] | None = None, avoid_recipes: list[str] | None = None) -> dict:
    """
    Up to ``k`` recipes to put in place of one meal. Each keeps the week's
    rules: within budget, energy in the band, no salt / saturated fat / free
    sugar limit worse than now, not the other main meal of that day, and no
    extra repeat while non-repeating options exist. Best for the goal first.
    ``breaks`` names the strategies that the swap would meet on fewer days.
    """
    if meal not in MEALS:
        raise ValueError(f"meal must be one of {list(MEALS)}")
    if not 0 <= day < days:
        raise ValueError(f"day must be 0 to {days - 1}")
    ctx = _context(rec, profile, goal=goal, chain=chain, diet=diet, equipment=equipment, pantry=pantry, days=days,
                   answers=answers, declined=declined, avoid_recipes=avoid_recipes)
    week = _week_from(ctx, week)
    base = _assemble(ctx, week, budget=budget)
    current = week[day]["meals"][meal]
    other = {week[day]["meals"][m] for m in ("lunch", "dinner") if m != meal} if meal != "breakfast" else set()
    served = {}
    for d in week:
        served[d["meals"][meal]] = served.get(d["meals"][meal], 0) + 1
    base_score = _goal_score(ctx, base["coverage"])
    base_met = {s["id"]: s["met_days"] for s in base["strategies"]}

    fresh, repeated = [], []
    for r in ctx.meals:
        if not ctx.allowed(r, meal) or r.id == current or r.id in other:
            continue
        trial = [{"meals": dict(d["meals"]), "snacks": list(d["snacks"])} for d in week]
        trial[day]["meals"][meal] = r.id
        plan = _assemble(ctx, trial, budget=budget)
        if not (plan["within_budget"] and plan["energy"]["in_band"]):
            continue
        if any(plan["limits"][n] > max(100.0, base["limits"][n]) + 0.05 for n in ctx.limits):
            continue
        score = _goal_score(ctx, plan["coverage"])
        delta = score - base_score
        option = {"id": r.id, "en": r.en, "fr": r.fr, "time_min": r.time_min, "batch": r.batch,
                  "total_cost": plan["total_cost"], "cost_delta": round(plan["total_cost"] - base["total_cost"], 2),
                  "effect": "better" if delta > 0.005 else "less" if delta < -0.005 else "same",
                  "breaks": [s["id"] for s in plan["strategies"] if s["met_days"] < base_met[s["id"]]],
                  "_score": score}
        (repeated if served.get(r.id, 0) + 1 > _variety_cap(r) else fresh).append(option)
    ranked = sorted(fresh, key=lambda o: (-o["_score"], o["total_cost"]))
    if len(ranked) < k:
        ranked += sorted(repeated, key=lambda o: (-o["_score"], o["total_cost"]))
    for o in ranked:
        o.pop("_score")
    return {"day": day, "meal": meal, "current": base["days"][day]["meals"][meal], "options": ranked[:k],
            "total_cost": base["total_cost"]}


def _round_to_cents(rows: list[dict]) -> None:
    """
    Round line costs to cents so that they add up exactly to the rounded
    total (largest-remainder method). Rounding each line on its own can push
    the shown total a cent over a budget the exact cost respects.
    """
    cents = [r["cost"] * 100 for r in rows]
    floors = [math.floor(c + 1e-9) for c in cents]
    missing = round(sum(cents)) - sum(floors)
    for i in sorted(range(len(rows)), key=lambda i: floors[i] - cents[i])[:max(0, missing)]:
        floors[i] += 1
    for r, c in zip(rows, floors):
        r["cost"] = c / 100


# Why there is no plan. The app shows the note; "budget" comes with the minimum.
REASONS = {
    "budget": "Enough food for the week does not fit this budget at this shop.",
    "energy": ("Your estimated energy need is outside what these recipes can be portioned for "
               "(tested from about 500 to 6,000 kcal a day). For needs like this, plan with a dietitian."),
    "recipes": "Too few recipes fit these settings to fill a week.",
}


def _no_plan(ctx: _Week, budget: float, *, status: str, reason: str, minimum: float | None, relax: list[dict]) -> dict:
    """No week: why (a key of REASONS), the minimum budget where that is the reason, and what to relax."""
    _i, _r, prices = _load()
    return {"feasible": False, "status": status, "reason": reason, "note": REASONS[reason],
            "chain": {"id": ctx.chain, "label": prices["chains"][ctx.chain]["label"]}, "budget": budget,
            "energy": {"target_per_day": round(ctx.kcal_target / ctx.days)}, "minimum_budget": minimum, "relax": relax}


def _minimum_budget(rec, profile, goal, chain, diet, days, equipment, *, pantry=None, answers=None,
                    declined=None, avoid_recipes=None) -> tuple[float | None, str]:
    """
    (minimum budget, reason) when a week does not fit. The cheapest adequate
    week gives the minimum; if even that is impossible, a second solve without
    the energy band tells an energy need out of reach from too few recipes.
    Both solves keep the person's answers, so the minimum is for their settings.
    """
    kw = dict(goal=goal, budget=0, chain=chain, diet=diet, days=days, equipment=equipment, pantry=pantry,
              answers=answers, declined=declined, avoid_recipes=avoid_recipes, _cheapest=True)
    cheapest = plan_week(rec, profile, **kw)
    if cheapest.get("feasible"):
        return math.ceil(cheapest["total_cost"]), "budget"
    any_energy = plan_week(rec, profile, **kw, _ignore_energy=True)
    return None, ("energy" if any_energy.get("feasible") else "recipes")


# ---------------------------------------------------------------- why this meal
# A nutrient is explained only when one portion gives at least 15 % of the
# daily need: the EU threshold for a food to be a "source" of a vitamin or
# mineral (Reg. 1924/2006), below which citing a health claim would mislead.
WHY_MIN_SHARE = 15.0
WHY_LIMIT_SHARE = 30.0      # mention salt / saturated fat / free sugars from here


def serving_scale(recipe: dict, scale: float) -> float:
    """Meals follow the person's portion scale; snacks are fixed."""
    lo, hi = PORTION_SCALE
    return 1.0 if "snack" in recipe["meals"] else max(lo, min(hi, scale))


def recipe_why(rec, recipe_id: str, *, goal: str, scale: float = 1.0,
               demographic: str | None = None) -> dict:
    """
    Why a recipe is in the plan for this goal: per nutrient linked to the goal,
    the share of the daily need one portion gives, the ingredient it mostly
    comes from, and the evidence for the nutrient -> goal link (the official
    EU claim wording where one is authorised). Raises KeyError for an unknown
    recipe or goal.
    """
    from .reference import DEFAULT_DEMOGRAPHIC, Demographic, reference_value
    from .scoring import saturate

    ingredients, raw, _prices = _load()
    recipe = next((r for r in raw if r["id"] == recipe_id), None)
    if recipe is None:
        raise KeyError(f"unknown recipe: {recipe_id}")
    linked = rec.scorer.positive.get(goal)
    if linked is None:
        raise KeyError(f"unknown goal: {goal}")
    demo = Demographic(demographic) if demographic else DEFAULT_DEMOGRAPHIC
    k = serving_scale(recipe, scale)

    totals: dict[str, float] = {}
    by_ingredient: dict[str, list[tuple[str, float]]] = {}
    for item in recipe["ingredients"]:
        ing = ingredients[item["id"]]
        food = rec.food_by_id.get(f"ciqual-{ing['ciqual']}")
        if food is None:
            continue
        grams = item["g"] * k
        for n, per_100g in food.nutrients.items():
            amount = per_100g * grams / 100.0
            totals[n] = totals.get(n, 0.0) + amount
            by_ingredient.setdefault(n, []).append((item["id"], amount))
        if item["id"] in FREE_SUGAR_INGREDIENTS:
            free = food.nutrients.get("sugars", 0.0) * grams / 100.0
            totals["free-sugars"] = totals.get("free-sugars", 0.0) + free
            by_ingredient.setdefault("free-sugars", []).append((item["id"], free))

    def main_source(n: str) -> dict:
        iid, amount = max(by_ingredient[n], key=lambda t: t[1])
        return {"id": iid, "en": ingredients[iid]["en"], "fr": ingredients[iid]["fr"],
                "share": round(100 * amount / totals[n])}

    nutrients = []
    for n, association, grade in linked:
        ref = reference_value(n, demo)
        if ref is None or ref.rda_ai <= 0 or totals.get(n, 0.0) <= 0:
            continue
        share = 100.0 * totals[n] / ref.rda_ai
        if share < WHY_MIN_SHARE:
            continue
        meta = rec.edge_meta.get(f"{n}->{goal}", {})
        if meta.get("evidence", grade) == "D":
            continue        # literature-only links without a confirming claim are not a reason
        nutrients.append({
            "nutrient": n, "amount": round(totals[n], 3), "percent_of_need": round(share, 1),
            "delivery_strength": round(saturate(share / 100.0), 4), "association": association,
            "evidence": meta.get("evidence", grade), "evidence_source": meta.get("evidence_source", ""),
            "consumer_label": meta.get("consumer_label", ""),
            "eu_claim": bool(meta.get("eu_claim")), "eu_claims": list(meta.get("eu_claims", [])),
            "citations": list(meta.get("citations", [])), "main_source": main_source(n),
        })
    # strongest routes first, the same order the ranking would use
    nutrients.sort(key=lambda r: -r["delivery_strength"] * r["association"])

    limits = []
    for n, daily in LIMIT_NUTRIENTS.items():
        key = "free-sugars" if n == "sugars" else n
        share = 100.0 * totals.get(key, 0.0) / daily
        if share >= WHY_LIMIT_SHARE:
            limits.append({"nutrient": key, "percent_of_limit": round(share), "main_source": main_source(key)
                           if key in by_ingredient else None})
    return {"id": recipe["id"], "en": recipe["en"], "fr": recipe["fr"], "goal": goal,
            "demographic": demo.value, "portion_scale": k, "nutrients": nutrients, "limits": limits,
            "rule": (f"Nutrients listed when one portion gives at least {WHY_MIN_SHARE:.0f}% of the daily "
                     "need and the link to the goal has evidence graded A to C.")}
