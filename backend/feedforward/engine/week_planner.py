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

  w_n = 1 + GOAL_BONUS * association(n, goal): every nutrient counts, the
  goal's nutrients (from the EU-claim graph) count more.

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
from .needs import Profile, daily_needs, energy_kcal
from .reference import LIMIT_NUTRIENTS

DATA = Path(__file__).resolve().parent.parent / "data"
MEALS = ("breakfast", "lunch", "dinner")
GOAL_BONUS = 3.0
MAX_SNACKS = 7          # snacks in total per week at most 2 a day (see below)
SNACK_REPEAT = 4        # the same snack at most 4 times a week
# Energy is a hard band, never traded for budget: a plan that saves money by
# feeding less is unsafe (and would train restriction). Too little budget for
# enough food returns the minimum budget instead.
ENERGY_BAND = (0.9, 1.15)
# Recipes are written for ~2,100 kcal a day; meal portions scale with the
# person's energy need (snacks do not), within these bounds.
REFERENCE_KCAL = 2100
# The WHO 50 g/day sugar limit is for FREE sugars (added sugars, honey), not
# the sugars naturally in fruit and milk. Only these ingredients count.
FREE_SUGAR_INGREDIENTS = {"honey", "dark-chocolate"}
VEGAN_B12_NOTE = ("Vitamin B12 is found almost only in animal foods: on a vegan diet, take a B12 "
                  "supplement or B12-fortified foods (a pharmacist can advise).")
REPEAT_PENALTY = 0.03   # objective cost of one repeat beyond the variety cap
REPEAT_EUR = 1.0        # the same, in euros, for the cheapest-week solve
PACKED = {"fridge", "bakery"}   # bought in whole packs; pantry/freezer count the share used
PORTION_SCALE = (0.8, 1.4)
_EXCLUDED = {"vegetarian": {"meat", "fish"}, "vegan": {"meat", "fish", "dairy", "egg", "honey"}}


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


def portion_scale(profile: Profile) -> float:
    lo, hi = PORTION_SCALE
    return round(min(hi, max(lo, energy_kcal(profile) / REFERENCE_KCAL)), 2)


def _recipes(rec, scale: float = 1.0) -> list[Recipe]:
    ingredients, raw, _p = _load()
    out = []
    for r in raw:
        totals: dict[str, float] = {}
        animal = set()
        k = 1.0 if "snack" in r["meals"] else scale
        items = [{"id": i["id"], "g": round(i["g"] * k)} for i in r["ingredients"]]
        for item in items:
            ing = ingredients[item["id"]]
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
                          r.get("equipment", []), items, r.get("steps", []), totals, animal))
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


def plan_week(rec, profile: Profile, *, goal: str | None, budget: float, chain: str,
              diet: str | None = None, days: int = 7, equipment: list[str] | None = None,
              _cheapest: bool = False) -> dict:
    ingredients, _raw, prices = _load()
    if chain not in prices["chains"]:
        raise ValueError(f"unknown chain: {chain}")
    scale = portion_scale(profile)
    recipes = [r for r in _recipes(rec, scale) if not (r.animal & _EXCLUDED.get(diet or "", set()))]
    if equipment is not None:
        allowed = set(equipment) | {"kettle"}
        recipes = [r for r in recipes if set(r.equipment) <= allowed]
    meals = [r for r in recipes if any(m in MEALS for m in r.meals)]
    snacks = [r for r in recipes if "snack" in r.meals]

    nutrient_ids = sorted({n for r in recipes for n in r.nutrients})
    need = daily_needs(profile, nutrient_ids)
    weekly = {n: v * days for n, v in need.items()}
    kcal_target = energy_kcal(profile) * days
    assoc = {n: a for n, a, _g in rec.scorer.positive.get(goal or "", [])}
    weight = {n: 1.0 + GOAL_BONUS * assoc.get(n, 0.0) for n in weekly}
    limits = {("free-sugars" if n == "sugars" else n): lim * days for n, lim in LIMIT_NUTRIENTS.items()}

    prob = pulp.LpProblem("week", pulp.LpMaximize)
    x = {}
    for r in meals:
        for m in MEALS:
            if m in r.meals:
                x[r.id, m] = prob.add_variable(f"x_{r.id}_{m}", 0, days, cat="Integer")
    s = {r.id: prob.add_variable(f"s_{r.id}", 0, SNACK_REPEAT, cat="Integer") for r in snacks}
    by_id = {r.id: r for r in recipes}
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
    for r in meals:
        vs = [v for (rid, _m), v in x.items() if rid == r.id]
        once = prob.add_variable(f"rep1_{r.id}", 0, 1, cat="Integer")
        more = prob.add_variable(f"rep2_{r.id}", 0, cat="Integer")
        repeats[r.id] = (once, more)
        prob += pulp.lpSum(vs) <= (3 if r.batch else 2) + once + more, f"variety_{r.id}"
    extra = pulp.lpSum(once + 3 * more for once, more in repeats.values())
    y = {n: prob.add_variable(f"y_{n}", 0, 1) for n in weekly}
    for n in weekly:
        prob += y[n] * weekly[n] <= intake(n), f"cover_{n}"
    prob += pulp.lpSum(s.values()) <= 2 * days, "snacks_per_day"
    e_over, e_under = prob.add_variable("e_over", 0), prob.add_variable("e_under", 0)
    prob += intake("energy-kcal") - kcal_target == e_over - e_under, "energy"
    prob += intake("energy-kcal") >= ENERGY_BAND[0] * kcal_target, "energy_min"
    prob += intake("energy-kcal") <= ENERGY_BAND[1] * kcal_target, "energy_max"
    slack = {n: prob.add_variable(f"slack_{n}", 0) for n in limits}
    for n, lim in limits.items():
        prob += intake(n) <= lim + slack[n], f"limit_{n}"

    # cost
    usage = {}
    for (rid, _m), v in servings:
        for item in by_id[rid].ingredients:
            usage.setdefault(item["id"], []).append((item["g"], v))
    cost_terms, packs = [], {}
    for iid, uses in usage.items():
        eur_kg, pack_g, _est = _price(iid, chain)
        grams = pulp.lpSum(g * v for g, v in uses)
        if ingredients[iid]["storage"] in PACKED and pack_g:
            packs[iid] = prob.add_variable(f"p_{iid}", 0, cat="Integer")
            prob += packs[iid] * pack_g >= grams, f"pack_{iid}"
            cost_terms.append(packs[iid] * pack_g * eur_kg / 1000)
        else:
            cost_terms.append(grams * eur_kg / 1000)
    cost = pulp.lpSum(cost_terms)
    if _cheapest:
        # Cheapest week that still feeds enough and stays under the limits.
        prob += -cost - 5 * pulp.lpSum(slack[n] / limits[n] for n in limits) - REPEAT_EUR * extra, "objective"
        ok, _status = solve(prob, time_limit=20)
        return {"feasible": ok, "total_cost": round(pulp.value(cost), 2) if ok else None}
    prob += cost <= budget, "budget"

    total_w = sum(weight.values()) or 1.0
    prob += (pulp.lpSum(weight[n] * y[n] for n in weekly) / total_w
             - (e_over + e_under) / kcal_target
             - 5 * pulp.lpSum(slack[n] / limits[n] for n in limits)
             - REPEAT_PENALTY * extra
             - 0.01 * cost / max(budget, 1)), "objective"
    ok, status = solve(prob, time_limit=20)
    if not ok:
        return {"feasible": False, "status": status,
                "chain": {"id": chain, "label": prices["chains"][chain]["label"]}, "budget": budget,
                "note": "Enough food for the week does not fit this budget at this shop.",
                "minimum_budget": _minimum_budget(rec, profile, goal, chain, diet, days, equipment)}

    counts = {k: int(round(v.value() or 0)) for k, v in x.items()}
    n_extra = int(round(sum((a.value() or 0) + (b.value() or 0) for a, b in repeats.values())))
    snack_counts = {k: int(round(v.value() or 0)) for k, v in s.items()}
    week = _schedule(counts, snack_counts, by_id, days)
    basket = _basket(usage, packs, chain, ingredients)
    total_cost = round(sum(b["cost"] for b in basket), 2)
    intake_val = {n: sum(by_id[rid].nutrients.get(n, 0) * (counts.get((rid, m)) if m != "snack" else snack_counts[rid])
                         for (rid, m), _v in servings) for n in set(weekly) | set(limits) | {"energy-kcal"}}
    coverage = {n: round(100 * intake_val[n] / weekly[n], 1) for n in weekly}
    goal_nutrients = sorted(assoc, key=lambda n: -assoc[n])
    return {
        "feasible": True,
        "chain": {"id": chain, "label": prices["chains"][chain]["label"]},
        "budget": budget, "total_cost": total_cost,
        "energy": {"target_per_day": round(kcal_target / days), "planned_per_day": round(intake_val["energy-kcal"] / days)},
        "demographic": profile.demographic.value,
        "portion_scale": scale,
        "goal": goal, "goal_nutrients": [n for n in goal_nutrients if n in coverage],
        "coverage": coverage,
        "limits": {n: round(100 * intake_val[n] / limits[n], 1) for n in limits},
        "days": week, "basket": basket,
        "diet_note": VEGAN_B12_NOTE if diet == "vegan" else None,
        "repeats": n_extra,
        "notes": ["Pantry and freezer items (rice, oil, frozen vegetables…) are counted at the share this week uses.",
                  "Prices: Open Prices medians for this chain; items marked 'estimated' use the national median x the chain's price index.",
                  "Recipes are drafts awaiting review by a dietitian."],
    }


def _schedule(counts: dict, snack_counts: dict, by_id: dict, days: int) -> list[dict]:
    """Spread recipe counts over the days; batch recipes on consecutive days."""
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
    out = []
    for d in range(days):
        day = {"day": d + 1, "meals": {}, "snacks": []}
        for m in MEALS:
            rid = lines[m][d] if d < len(lines[m]) else None
            if rid:
                r = by_id[rid]
                day["meals"][m] = {"id": r.id, "en": r.en, "fr": r.fr, "time_min": r.time_min, "batch": r.batch}
        for i, rid in enumerate(snack_seq):
            if i % days == d:
                day["snacks"].append({"id": rid, "en": by_id[rid].en, "fr": by_id[rid].fr})
        out.append(day)
    return out


def _basket(usage: dict, packs: dict, chain: str, ingredients: dict) -> list[dict]:
    order = {"fresh": 0, "bakery": 1, "fridge": 2, "freezer": 3, "pantry": 4}
    out = []
    for iid, uses in usage.items():
        grams = sum(g * (v.value() or 0) for g, v in uses)
        if grams <= 0:
            continue
        eur_kg, pack_g, estimated = _price(iid, chain)
        ing = ingredients[iid]
        if iid in packs:
            n = int(round(packs[iid].value() or 0))
            cost = n * pack_g * eur_kg / 1000
            buy = {"packs": n, "pack_g": pack_g}
            if ing.get("unit_g"):                       # eggs: a box of 6, not 374 g
                buy["units_per_pack"] = max(1, round(pack_g / ing["unit_g"]))
        else:
            cost = grams * eur_kg / 1000
            buy = {"grams": round(grams)}
            if ing.get("unit_g") and grams >= 0.75 * ing["unit_g"]:   # loose produce: "about 8 apples"
                buy["about_units"] = max(1, round(grams / ing["unit_g"]))
        out.append({"id": iid, "food_id": f"ciqual-{ing['ciqual']}", "en": ing["en"], "fr": ing["fr"],
                    "storage": ing["storage"], "liquid": bool(ing.get("liquid")),
                    "grams_used": round(grams), **buy, "eur_kg": eur_kg,
                    "cost": round(cost, 2), "estimated": estimated})
    out.sort(key=lambda b: (order.get(b["storage"], 9), -b["cost"]))
    return out


def _minimum_budget(rec, profile, goal, chain, diet, days, equipment) -> float | None:
    """Cost of the cheapest adequate week at this chain (for 'budget too low')."""
    r = plan_week(rec, profile, goal=goal, budget=0, chain=chain, diet=diet, days=days,
                  equipment=equipment, _cheapest=True)
    return math.ceil(r["total_cost"]) if r.get("feasible") else None
