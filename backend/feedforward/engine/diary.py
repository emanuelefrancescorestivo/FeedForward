"""
A day as the person eats it: what they logged, and what to eat next.

The week planner (week_planner.py) decides a whole week at once. The diary is
the other way in: the day starts empty, the person logs what they ate (a
recipe, or a food in grams) and, for any meal, may ask for a few suggestions.
Both use the same person, needs, goal and answers as the planner (one
_context, days=1), so a suggestion follows the same strategies a planned week
would ("more of the day's carbohydrates at dinner", "no caffeine at dinner",
the foods they don't eat, their cooking time).

day_summary   totals for the logged day against the day's targets: energy and
              macros, coverage of each need, the goal's nutrients and the
              entry each mostly comes from, the limits, and per meal the
              strategies that apply to it.
suggest_meal  up to k recipes for one meal, ranked by what they add to the
              needs still open today (goal nutrients weighted up, as in the
              planner), how close they come to the energy left for that meal,
              and the strategies for that meal; each with its reasons.

Nothing here restricts: a day above its energy target is shown as it is, and
a suggestion never asks to eat less than the energy left for a meal suggests.
"""
from __future__ import annotations

from dataclasses import dataclass

from .needs import Profile
from .profile import MEALS
from . import week_planner as wp

SLOTS = MEALS + ("snack",)
# A day's energy, by meal, when no strategy says otherwise: typical shares in
# European dietary surveys (breakfast ~20-25 %, lunch and dinner ~30-35 %, snacks ~10-15 %).
MEAL_SHARE = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.30, "snack": 0.10}
ENERGY_WEIGHT = 0.6        # a suggestion that misses the meal's energy by all of it loses this much score
LEVER_WEIGHT = 0.25        # a strategy for this meal, met
LIMIT_WEIGHT = 0.5         # a suggestion that takes a limit (salt, saturated fat, free sugars) past the day's
REASON_MIN_SHARE = 15.0
CARB_RICH = 0.5            # a meal with half its energy or more from carbohydrates (the day's range is 45-60 %)    # a goal nutrient is a reason from 15 % of the daily need (the EU "source" threshold)


@dataclass(frozen=True)
class Entry:
    kind: str              # "recipe" | "food"
    id: str
    meal: str              # one of SLOTS
    servings: float = 1.0  # recipe
    grams: float = 0.0     # food


def entries_from(raw: list[dict]) -> list[Entry]:
    """Checked entries from the request: ValueError for an unknown kind, meal or amount."""
    out = []
    for e in raw or []:
        kind, meal = e.get("kind"), e.get("meal")
        if kind not in ("recipe", "food"):
            raise ValueError("entry kind must be 'recipe' or 'food'")
        if meal not in SLOTS:
            raise ValueError(f"entry meal must be one of {list(SLOTS)}")
        servings, grams = float(e.get("servings") or 1.0), float(e.get("grams") or 0.0)
        if kind == "recipe" and not 0 < servings <= 10:
            raise ValueError("servings must be above 0 and at most 10")
        if kind == "food" and not 0 < grams <= 3000:
            raise ValueError("grams must be above 0 and at most 3000")
        out.append(Entry(kind, str(e.get("id", "")), meal, servings, grams))
    return out


def _context(rec, profile: Profile, *, goal, chain, diet, equipment, answers, declined, avoid_recipes=None):
    return wp._context(rec, profile, goal=goal, chain=chain, diet=diet, equipment=equipment, pantry=None,
                       days=1, answers=answers, declined=declined, avoid_recipes=avoid_recipes)


def _all_recipes(rec, scale: float) -> dict[str, wp.Recipe]:
    """Every recipe at this person's portions: a logged meal counts whatever the filters (it was eaten)."""
    return {r.id: r for r in wp._recipes(rec, scale)}


def _entry_nutrients(rec, recipes: dict, e: Entry) -> tuple[dict[str, float], str]:
    if e.kind == "recipe":
        r = recipes.get(e.id)
        if r is None:
            raise ValueError(f"unknown recipe: {e.id}")
        return {n: v * e.servings for n, v in r.nutrients.items()}, r.en
    food = rec.food_by_id.get(e.id)
    if food is None:
        raise ValueError(f"unknown food: {e.id}")
    return {n: v * e.grams / 100.0 for n, v in food.nutrients.items()}, food.name


def _targets(ctx) -> dict:
    kcal = ctx.kcal_target
    return {"kcal": round(kcal), "protein": round(ctx.protein_target, 1),
            "carbs": round(kcal * sum(wp.CARBS_ENERGY) / 2 / 4, 1),
            "fat": round(kcal * sum(wp.FAT_ENERGY) / 2 / 9, 1)}


def _macros(n: dict) -> dict:
    return {"kcal": round(n.get("energy-kcal", 0.0)),
            **{k: round(n.get(v, 0.0), 1) for k, v in wp.MACROS.items()}}


def _meal_levers(ctx) -> dict[str, list[dict]]:
    """Per meal, the strategies and preferences that apply to it, as the app shows them."""
    out: dict[str, list[dict]] = {m: [] for m in SLOTS}
    for a in ctx.levers.applied:
        meal = (a.get("lever") or {}).get("meal")
        if meal in out:
            out[meal].append({"id": a["id"], "kind": a["kind"], "text": a["text"], "why": a.get("why"),
                              "grade": a.get("grade"), "pmids": a.get("pmids", [])})
    return out


def _goal_nutrients(ctx) -> list[str]:
    """The goal's nutrients with a need, strongest link first, evidence A to C only (as in "Why this meal?")."""
    return [n for n in sorted(ctx.assoc, key=lambda n: -ctx.assoc[n])
            if n in ctx.weekly and ctx.evidence.get(n, {}).get("grade", "D") != "D"]


def day_summary(rec, profile: Profile, entries: list[Entry], *, goal: str | None, diet: str | None = None,
                equipment: list[str] | None = None, answers: dict | None = None,
                declined: list[str] | None = None, chain: str = "lidl") -> dict:
    """The logged day against its targets. ValueError for an unknown recipe or food, or bad answers."""
    ctx = _context(rec, profile, goal=goal, chain=chain, diet=diet, equipment=equipment,
                   answers=answers, declined=declined)
    recipes = _all_recipes(rec, ctx.scale)
    total: dict[str, float] = {}
    per_meal: dict[str, dict[str, float]] = {m: {} for m in SLOTS}
    contributions = []                                # (entry index, name, nutrients)
    for i, e in enumerate(entries):
        nutrients, name = _entry_nutrients(rec, recipes, e)
        contributions.append((i, e, name, nutrients))
        for n, v in nutrients.items():
            total[n] = total.get(n, 0.0) + v
            per_meal[e.meal][n] = per_meal[e.meal].get(n, 0.0) + v

    goal_rows = []
    for n in _goal_nutrients(ctx):
        need = ctx.weekly[n]
        best = max(contributions, key=lambda c: c[3].get(n, 0.0), default=None)
        goal_rows.append({"nutrient": n, "goal": ctx.goal_of.get(n), "percent": round(100 * total.get(n, 0.0) / need, 1),
                          "eu_claim": ctx.evidence[n]["eu_claim"], "grade": ctx.evidence[n]["grade"],
                          "from": ({"entry": best[0], "meal": best[1].meal, "name": best[2]}
                                   if best and best[3].get(n, 0.0) > 0 else None)})
    return {
        "targets": _targets(ctx),
        "energy": {"goal": ctx.levers.energy_goal, "resting": round(ctx.resting_kcal)},
        "totals": _macros(total),
        "meals": {m: _macros(per_meal[m]) for m in SLOTS},
        "coverage": {n: round(100 * total.get(n, 0.0) / need, 1) for n, need in ctx.weekly.items()},
        "limits": {n: round(100 * total.get(n, 0.0) / lim, 1) for n, lim in ctx.limits.items()},
        "goal": goal, "goal_nutrients": goal_rows[:6],
        "meal_levers": _meal_levers(ctx),
        "meal_shares": {m: {"kcal": round(100 * per_meal[m].get("energy-kcal", 0.0) / total["energy-kcal"])
                            if total.get("energy-kcal") else 0,
                            "carbs": round(100 * per_meal[m].get("carbohydrates", 0.0) / total["carbohydrates"])
                            if total.get("carbohydrates") else 0} for m in SLOTS},
        "strategies": [{"id": a["id"], "kind": a["kind"], "text": a["text"], "grade": a.get("grade")}
                       for a in ctx.levers.applied],
        "demographic": profile.demographic.value, "portion_scale": ctx.scale,
    }


def _meal_energy(ctx, meal: str, eaten_by_meal: dict[str, float]) -> float:
    """The energy left for ``meal``: the day's target minus what is logged, shared among the meals not
    logged yet in their usual proportions; a breakfast strategy sets breakfast's share."""
    share = dict(MEAL_SHARE)
    lv = ctx.levers
    if lv.breakfast_energy_min is not None:
        share["breakfast"] = max(share["breakfast"], lv.breakfast_energy_min)
    if lv.breakfast_energy_max is not None:
        share["breakfast"] = min(share["breakfast"], lv.breakfast_energy_max)
    open_slots = [m for m in SLOTS if eaten_by_meal.get(m, 0.0) <= 0 or m == meal]
    left = max(0.0, ctx.kcal_target - sum(eaten_by_meal.values()))
    weight = sum(share[m] for m in open_slots) or 1.0
    # never below the meal's usual share of the day when the day is still open: a light lunch
    # earlier is not a reason to suggest a smaller dinner than usual
    return max(left * share[meal] / weight, 0.6 * share[meal] * ctx.kcal_target if left > 0 else 0.0)


def _lever_fit(ctx, r: wp.Recipe, meal: str, profile: Profile) -> tuple[float, list[dict]]:
    """How far ``r`` meets each strategy for ``meal`` (0 to 1 each, summed), and the ones it meets.
    A breakfast energy share is not here: it sets the energy the meal is measured against (_meal_energy).
    Day-level shares are reported by day_summary once the day's meals are logged (meal_shares)."""
    lv, score, met = ctx.levers, 0.0, []
    kcal = max(1.0, r.nutrients.get("energy-kcal", 0.0))
    carbs, protein = r.nutrients.get("carbohydrates", 0.0), r.nutrients.get("proteins", 0.0)
    for a in lv.applied:
        lever = a.get("lever") or {}
        kind, at = lever.get("type"), lever.get("meal")
        if kind == "meal_carb_share" and at == meal:
            # The share of the day's carbohydrates depends on meals not eaten yet, so one meal is
            # judged on its own: carbohydrate-rich (CARB_RICH of its energy or more).
            fit = 4 * carbs / kcal / CARB_RICH
        elif kind == "meal_protein" and at == meal:
            fit = protein / (lv.breakfast_protein_g_per_kg * profile.weight_kg)
        elif kind == "protein_per_meal" and meal in MEALS:
            fit = protein / (lv.protein_per_meal_g_per_kg * profile.weight_kg)
        else:
            continue
        score += min(1.0, fit)
        if fit >= 0.95:
            met.append(a)
    return score, met


def suggest_meal(rec, profile: Profile, entries: list[Entry], meal: str, *, goal: str | None,
                 diet: str | None = None, equipment: list[str] | None = None, answers: dict | None = None,
                 declined: list[str] | None = None, avoid_recipes: list[str] | None = None,
                 chain: str = "lidl", k: int = 3, exclude: list[str] | None = None) -> dict:
    """Up to ``k`` recipes for ``meal`` today, best first, each with its reasons. ``exclude``: recipe ids
    already shown ("show others"). Recipes logged today are not suggested again."""
    if meal not in SLOTS:
        raise ValueError(f"meal must be one of {list(SLOTS)}")
    ctx = _context(rec, profile, goal=goal, chain=chain, diet=diet, equipment=equipment,
                   answers=answers, declined=declined, avoid_recipes=avoid_recipes)
    recipes = _all_recipes(rec, ctx.scale)
    eaten: dict[str, float] = {}
    by_meal: dict[str, float] = {}
    for e in entries:
        nutrients, _name = _entry_nutrients(rec, recipes, e)
        for n, v in nutrients.items():
            eaten[n] = eaten.get(n, 0.0) + v
        by_meal[e.meal] = by_meal.get(e.meal, 0.0) + nutrients.get("energy-kcal", 0.0)
    logged = {e.id for e in entries if e.kind == "recipe"}
    skip = logged | set(exclude or ())
    pool = ctx.snacks if meal == "snack" else [r for r in ctx.meals if ctx.allowed(r, meal)]
    pool = [r for r in pool if r.id not in skip]
    target = _meal_energy(ctx, meal, by_meal)
    total_weight = sum(ctx.weight.values()) or 1.0
    goal_ids = set(_goal_nutrients(ctx))

    ranked = []
    for r in pool:
        gain = sum(ctx.weight[n] * (min(1.0, (eaten.get(n, 0.0) + r.nutrients.get(n, 0.0)) / need)
                                    - min(1.0, eaten.get(n, 0.0) / need))
                   for n, need in ctx.weekly.items()) / total_weight
        kcal = r.nutrients.get("energy-kcal", 0.0)
        energy_miss = abs(kcal - target) / target if target > 0 else 0.0
        lever_score, met = _lever_fit(ctx, r, meal, profile)
        over = sum(max(0.0, (eaten.get(n, 0.0) + r.nutrients.get(n, 0.0)) / lim - max(1.0, eaten.get(n, 0.0) / lim))
                   for n, lim in ctx.limits.items())
        score = gain * 10 - ENERGY_WEIGHT * min(1.0, energy_miss) + LEVER_WEIGHT * lever_score - LIMIT_WEIGHT * over
        ranked.append((score, r, met, kcal))
    ranked.sort(key=lambda t: (-t[0], t[1].time_min, t[1].id))

    out = []
    for score, r, met, kcal in ranked[:k]:
        reasons = []
        for n in sorted(goal_ids, key=lambda n: -ctx.assoc[n]):
            share = 100 * r.nutrients.get(n, 0.0) / ctx.weekly[n]
            if share >= REASON_MIN_SHARE:
                reasons.append({"kind": "nutrient", "nutrient": n, "percent": round(share),
                                "eu_claim": ctx.evidence[n]["eu_claim"], "goal": ctx.goal_of.get(n)})
        reasons = reasons[:2]
        reasons += [{"kind": "strategy", "id": a["id"], "text": a["text"], "grade": a.get("grade")} for a in met]
        out.append({"id": r.id, "en": r.en, "fr": r.fr, "meal": meal, **_macros(r.nutrients),
                    "time_min": r.time_min, "batch": r.batch, "cost": _cost(r, chain),
                    "reasons": reasons})
    return {"meal": meal, "energy_for_meal": round(target), "options": out,
            "more": max(0, len(ranked) - k), "levers": _meal_levers(ctx)[meal]}


def _cost(r: wp.Recipe, chain: str) -> float:
    """One portion at this shop, at the price per kg (a share of each pack, not whole packs)."""
    return round(sum(item["g"] * wp._price(item["id"], chain)[0] / 1000 for item in r.ingredients), 2)
