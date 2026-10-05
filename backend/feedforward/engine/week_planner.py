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
             energy between 90% and 115% of the need (hard: never cut food to save money)
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
  portions scale with it. A protein strategy raises the protein need to its g/kg.

The answers also filter the recipes, hard: foods not eaten (ingredient tags and
recipe tags such as "spicy"), the cooking time (batch recipes may take three
times as long when batch cooking is fine), recipes marked "not for me", and no
caffeine at a meal the person keeps caffeine-free. Ingredients at home bring no
filtered recipe back: they only make the recipes left cheaper.

Costs use the chosen chain's prices (data/ingredient_prices.json). Fridge
items (eggs, milk, meat, bread...) are bought as whole packs, so a pack of six
eggs is paid once and used across meals; pantry and freezer items (rice, oil,
frozen spinach...) are charged at the share the week uses; loose produce is
bought by weight.

Nutrition per recipe comes from CIQUAL (ANSES) values of its ingredients.
Recipes are drafts (data/recipes.json, status "draft").
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pulp

from .milp import solve
from .needs import Profile, daily_needs, energy_kcal, resting_kcal
from .profile import MEALS, Levers, resolve       # the three main meals are defined in profile.py
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
PACKED = {"fridge", "bakery"}   # bought in whole packs; pantry/freezer count the share used
PORTION_SCALE = (0.4, 2.5)
_EXCLUDED = {"vegetarian": {"meat", "fish"}, "vegan": {"meat", "fish", "dairy", "egg", "honey"}}
DIETS = (None, "vegetarian", "vegan")
APPLIANCES = ("hob", "microwave", "kettle", "blender")   # what recipes may need


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
    weekly: dict
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
    if levers.protein_g_per_kg:
        daily["proteins"] = round(max(daily["proteins"], levers.protein_g_per_kg * profile.weight_kg), 1)
    weekly = {n: v * days for n, v in daily.items()}
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
        levers=levers, goal_of=goal_of, resting_kcal=resting, evidence=evidence)


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
    ingredients, _raw, prices = _load()
    ctx = _context(rec, profile, goal=goal, chain=chain, diet=diet, equipment=equipment,
                   pantry=pantry, days=days, answers=answers, declined=declined, avoid_recipes=avoid_recipes)
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
    if not _ignore_energy:
        prob += intake("energy-kcal") >= ENERGY_BAND[0] * kcal_target, "energy_min"
        prob += intake("energy-kcal") <= ENERGY_BAND[1] * kcal_target, "energy_max"
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
    prob += (pulp.lpSum(ctx.weight[n] * y[n] for n in weekly) / total_w
             - (e_over + e_under) / kcal_target
             - 5 * pulp.lpSum(slack[n] / limits[n] for n in limits)
             - REPEAT_PENALTY * extra
             - 0.01 * cost / max(budget, 1)), "objective"
    ok, status = solve(prob, time_limit=SOLVE_SECONDS)
    if not ok:
        minimum, reason = _minimum_budget(rec, profile, goal, chain, diet, days, equipment, pantry=pantry,
                                          answers=answers, declined=declined, avoid_recipes=avoid_recipes)
        return {"feasible": False, "status": status, "reason": reason, "note": REASONS[reason],
                "chain": {"id": chain, "label": prices["chains"][chain]["label"]}, "budget": budget,
                "energy": {"target_per_day": round(kcal_target / days)}, "minimum_budget": minimum}

    counts = {k: int(round(v.value() or 0)) for k, v in x.items()}
    snack_counts = {k: int(round(v.value() or 0)) for k, v in s.items()}
    return _assemble(ctx, _schedule(counts, snack_counts, by_id, days), budget=budget)


def _variety_cap(r: Recipe) -> int:
    return 3 if r.batch else 2


def _assemble(ctx: _Week, week: list[dict], *, budget: float, edited: bool = False) -> dict:
    """
    A plan from a composed week ([{"meals": {meal: recipe id}, "snacks": [ids]}]):
    shopping list (whole packs for fridge and bakery items, ingredients at home
    free), cost, energy, coverage and limits. Deterministic, so a week the user
    edited is checked exactly like one the solver chose.
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
    targets = {"kcal": round(kcal_day),
               "protein": round(ctx.weekly.get("proteins", 0.0) / days, 1),
               "carbs": round(kcal_day * sum(CARBS_ENERGY) / 2 / 4, 1),
               "fat": round(kcal_day * sum(FAT_ENERGY) / 2 / 9, 1),
               "carbs_energy": list(CARBS_ENERGY), "fat_energy": list(FAT_ENERGY)}

    return {
        "feasible": True, "edited": edited,
        "chain": {"id": ctx.chain, "label": prices["chains"][ctx.chain]["label"]},
        "budget": budget, "total_cost": total_cost, "within_budget": total_cost <= budget + 1e-9,
        "energy": {"target_per_day": round(ctx.kcal_target / days), "planned_per_day": round(planned / days),
                   "in_band": ENERGY_BAND[0] * ctx.kcal_target - 1e-6 <= planned <= ENERGY_BAND[1] * ctx.kcal_target + 1e-6},
        "demographic": ctx.profile.demographic.value,
        "portion_scale": ctx.scale,
        "goal": ctx.goal, "goal_nutrients": [n for n in sorted(ctx.assoc, key=lambda n: -ctx.assoc[n]) if n in coverage],
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
    """Validate a week sent back by the app: 7 days, allowed recipes, in the right meals."""
    if len(week) != ctx.days:
        raise ValueError(f"a week has {ctx.days} days, got {len(week)}")
    out = []
    for i, d in enumerate(week):
        meals, snacks = dict(d.get("meals") or {}), list(d.get("snacks") or [])
        if set(meals) != set(MEALS):
            raise ValueError(f"day {i + 1} needs breakfast, lunch and dinner")
        for m, rid in meals.items():
            r = ctx.by_id.get(rid)
            if r is None or m not in r.meals:
                raise ValueError(f"day {i + 1}: '{rid}' is not a {m} for this diet and kitchen")
        for rid in snacks:
            if rid not in ctx.by_id or "snack" not in ctx.by_id[rid].meals:
                raise ValueError(f"day {i + 1}: '{rid}' is not a snack for this diet")
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
    return _assemble(ctx, _week_from(ctx, week), budget=budget, edited=True)


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

    fresh, repeated = [], []
    for r in ctx.meals:
        if meal not in r.meals or r.id == current or r.id in other:
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
    "recipes": "Too few recipes fit this diet and kitchen to fill a week.",
}


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
