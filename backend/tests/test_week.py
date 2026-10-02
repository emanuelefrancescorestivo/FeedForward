"""Week planner path: CIQUAL corpus, ingredient prices, personal needs, the plan, the API."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from feedforward.data.ingest.ciqual import column_map
from feedforward.data.ingest.prices import chain_of, pack_grams
from feedforward.engine import load_engine
from feedforward.engine import week_planner as wp
from feedforward.engine.needs import Profile, daily_needs, energy_kcal

DATA = Path(__file__).resolve().parent.parent / "feedforward" / "data"
STUDENT = Profile(24, "male", 72, 178, "light")


@pytest.fixture(scope="module")
def engine():
    return load_engine()


# --------------------------------------------------------------- CIQUAL
def test_ciqual_corpus_is_complete_and_sourced():
    foods = json.loads((DATA / "ciqual_corpus.json").read_text(encoding="utf-8"))
    assert len(foods) > 3000
    by_id = {f["id"]: f for f in foods}
    assert len(by_id) == len(foods)
    for f in foods:
        assert f["_source_id"] == "ciqual-2020" and f["_names"]["fr"]
    # vitamin A as RAE, omega-3 as a sum of its parts
    for f in foods:
        n = f["nutrients"]
        if "omega-3-fat" in n:
            assert n["omega-3-fat"] >= n.get("epa-dha", 0) + n.get("ala", 0) - 1e-3
    ingredients = {i["id"]: i for i in json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))["ingredients"]}
    lentils = by_id[f"ciqual-{ingredients['green-lentils']['ciqual']}"]
    assert lentils["nutrients"]["iron"] > 4          # dry green lentils, mg/100 g


def test_ciqual_flesh_groups_never_pass_as_vegetarian(engine):
    """CIQUAL's meat / fish / seafood / delicatessen sub-groups are ground truth."""
    from feedforward.engine.recommender import satisfies

    flesh = [f for f in engine.food_by_id.values() if f.id.startswith("ciqual-") and f.is_animal_source]
    assert len(flesh) > 700
    leaks = [f.name for f in flesh if satisfies(f, "vegetarian") or satisfies(f, "vegan")]
    assert not leaks, leaks[:10]


def test_ciqual_meat_substitutes_are_plant_foods(engine):
    """Tofu and seitan sit in CIQUAL's "meat substitute" group: not flesh, non-heme iron."""
    from feedforward.engine.bioavailability import iron_form_for_food as iron_form
    from feedforward.engine.recommender import satisfies
    from feedforward.engine.schema import NutrientForm

    subs = [f for f in engine.food_by_id.values() if f.id.startswith("ciqual-") and f.category == "meat substitute"]
    assert subs
    for f in subs:
        assert not f.is_animal_source, f.name
        assert iron_form(f) == NutrientForm.NON_HEME_IRON, f.name
    tofu = next(f for f in subs if f.name == "Tofu, plain")
    assert satisfies(tofu, "vegetarian") and satisfies(tofu, "vegan")


def test_ciqual_column_map_refuses_unknown_columns():
    with pytest.raises(ValueError):
        column_map(["alim_code", "Mystery nutrient (g/100 g)"])


# --------------------------------------------------------------- prices
def test_chain_names_from_osm():
    assert chain_of("Lidl, 12, Rue de Rivoli, Paris") == "lidl"
    assert chain_of("Carrefour City, Paris") == "carrefour"
    assert chain_of("Monop', Paris") == "monoprix"
    assert chain_of("Bio c' Bon, Paris") == "bio-c-bon"
    assert chain_of("Boulangerie du coin") is None


def test_pack_grams_units():
    assert pack_grams({"product_quantity": "500", "product_quantity_unit": "g"}) == 500
    assert pack_grams({"product_quantity": 1, "product_quantity_unit": "kg"}) == 1000
    assert pack_grams({"product_quantity": "6", "product_quantity_unit": ""}, unit_g=60) == 360
    assert pack_grams({"product_quantity": None}) is None


def test_every_ingredient_has_a_price_everywhere():
    ingredients = json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))["ingredients"]
    prices = json.loads((DATA / "ingredient_prices.json").read_text(encoding="utf-8"))
    for ing in ingredients:
        entry = prices["prices"][ing["id"]]
        assert entry["national_eur_kg"], ing["id"]
        for cid in prices["chains"]:
            v = entry["by_chain"][cid]["eur_kg"]
            # outliers beyond 3x the national median are dropped, and shrinkage pulls towards it
            assert entry["national_eur_kg"] / 3.5 <= v <= entry["national_eur_kg"] * 3.5, (ing["id"], cid, v)


def test_discounters_cheaper_than_organic_shops():
    idx = {c["id"]: c["price_index"] for c in wp.chains()}
    assert idx["lidl"] < idx["carrefour"] < idx["naturalia"]
    assert idx["aldi"] < idx["monoprix"] < idx["biocoop"]


# --------------------------------------------------------------- needs
def test_energy_follows_mifflin_st_jeor():
    # 10*72 + 6.25*178 - 5*24 + 5 = 1717.5; x 1.375
    assert energy_kcal(STUDENT) == round(1717.5 * 1.375)
    pregnant = Profile(30, "female", 60, 165, "light", pregnant=True)
    assert energy_kcal(pregnant) == energy_kcal(Profile(30, "female", 60, 165, "light")) + 340


def test_weight_changes_protein_not_vitamins():
    light = daily_needs(Profile(30, "female", 55, 165), ["proteins", "iron", "vitamin-c"])
    heavy = daily_needs(Profile(30, "female", 95, 165), ["proteins", "iron", "vitamin-c"])
    assert heavy["proteins"] > light["proteins"]
    assert heavy["iron"] == light["iron"] and heavy["vitamin-c"] == light["vitamin-c"]


def test_profile_validation():
    with pytest.raises(ValueError):
        Profile(10, "male", 40, 140).validate()
    with pytest.raises(ValueError):
        Profile(30, "male", 70, 175, "couch").validate()


# --------------------------------------------------------------- planner
def test_milp_adapter_reports_optimal_and_infeasible():
    """engine/milp.py hides the PuLP 3 / PuLP 4 differences."""
    import pulp
    from feedforward.engine.milp import solve

    prob = pulp.LpProblem("ok", pulp.LpMaximize)
    x = prob.add_variable("x", 0, 3, cat="Integer")
    prob += x
    prob += x <= 2.5
    ok, status = solve(prob, time_limit=10)
    assert ok and x.value() == 2, status

    prob = pulp.LpProblem("impossible", pulp.LpMaximize)
    y = prob.add_variable("y", 0, 3)
    prob += y
    prob += y >= 5
    ok, _status = solve(prob)
    assert not ok


def test_recipes_reference_known_ingredients_and_foods(engine):
    ingredients, recipes, _p = wp._load()
    for r in recipes:
        for it in r["ingredients"]:
            assert it["id"] in ingredients, (r["id"], it["id"])
    for ing in ingredients.values():
        assert f"ciqual-{ing['ciqual']}" in engine.food_by_id, ing["id"]


def test_student_week_at_lidl_fits_budget_and_energy(engine):
    plan = wp.plan_week(engine, STUDENT, goal="cognitive_function", budget=50, chain="lidl")
    assert plan["feasible"]
    assert plan["total_cost"] <= 50
    target = plan["energy"]["target_per_day"]
    assert 0.9 * target <= plan["energy"]["planned_per_day"] <= 1.15 * target
    assert len(plan["days"]) == 7
    assert all(set(d["meals"]) == {"breakfast", "lunch", "dinner"} for d in plan["days"])
    assert all(v <= 100.5 for v in plan["limits"].values()), plan["limits"]
    # the basket pays for what the recipes use
    assert abs(sum(b["cost"] for b in plan["basket"]) - plan["total_cost"]) < 0.05
    for b in plan["basket"]:
        if "packs" in b:
            assert b["packs"] * b["pack_g"] >= b["grams_used"] - 1


def test_never_less_food_to_fit_a_small_budget(engine):
    plan = wp.plan_week(engine, STUDENT, goal="cognitive_function", budget=20, chain="naturalia")
    assert not plan["feasible"]
    assert plan["minimum_budget"] and plan["minimum_budget"] > 20
    again = wp.plan_week(engine, STUDENT, goal="cognitive_function", budget=plan["minimum_budget"] + 2,
                         chain="naturalia")
    assert again["feasible"]


def test_vegetarian_and_vegan_weeks_have_no_excluded_foods(engine):
    ingredients, recipes, _p = wp._load()
    by_id = {r["id"]: r for r in recipes}
    for diet, banned in (("vegetarian", {"meat", "fish"}), ("vegan", {"meat", "fish", "dairy", "egg", "honey"})):
        plan = wp.plan_week(engine, STUDENT, goal="energy_metabolism", budget=80, chain="carrefour", diet=diet)
        assert plan["feasible"], diet
        used = {m["id"] for d in plan["days"] for m in d["meals"].values()} | \
               {s["id"] for d in plan["days"] for s in d["snacks"]}
        for rid in used:
            animals = {ingredients[i["id"]].get("animal") for i in by_id[rid]["ingredients"]}
            assert not (animals & banned), (diet, rid, animals)


def test_microwave_only_week(engine):
    plan = wp.plan_week(engine, STUDENT, goal=None, budget=60, chain="lidl", equipment=["microwave"])
    _i, recipes, _p = wp._load()
    by_id = {r["id"]: r for r in recipes}
    assert plan["feasible"]
    for d in plan["days"]:
        for m in d["meals"].values():
            assert set(by_id[m["id"]].get("equipment", [])) <= {"microwave", "kettle"}


def test_narrow_settings_repeat_meals_instead_of_failing(engine):
    """Vegan + microwave has few recipes: the plan repeats some, spread out."""
    plan = wp.plan_week(engine, STUDENT, goal=None, budget=60, chain="lidl", diet="vegan", equipment=["microwave"])
    assert plan["feasible"] and plan["repeats"] > 0
    counts = {}
    for d in plan["days"]:
        for m in d["meals"].values():
            counts[m["id"]] = counts.get(m["id"], 0) + 1
    assert max(counts.values()) <= 5, counts
    assert plan["diet_note"] and "B12" in plan["diet_note"]


def test_why_this_meal_lists_only_meaningful_supported_nutrients(engine):
    why = wp.recipe_why(engine, "sardine-tartines", goal="cognitive_function", demographic="adult_male")
    assert why["nutrients"], why
    top = why["nutrients"][0]
    assert top["nutrient"] == "epa-dha" and top["eu_claim"] and top["eu_claims"]
    assert top["main_source"]["id"] == "sardines"
    for n in why["nutrients"]:
        assert n["percent_of_need"] >= wp.WHY_MIN_SHARE           # the EU "source" threshold
        assert n["evidence"] in ("A", "B", "C")                   # no literature-only (D) reasons
    strengths = [n["delivery_strength"] * n["association"] for n in why["nutrients"]]
    assert strengths == sorted(strengths, reverse=True)
    # a banana is not a reason to sleep better, and the app should say so
    assert wp.recipe_why(engine, "snack-banana", goal="sleep_support")["nutrients"] == []
    with pytest.raises(KeyError):
        wp.recipe_why(engine, "no-such-recipe", goal="cognitive_function")
    with pytest.raises(KeyError):
        wp.recipe_why(engine, "sardine-tartines", goal="no_such_goal")


def _violations(plan, profile, budget, diet, kitchen):
    """Invariants every answer must keep, whatever the input."""
    _i, recipes, _p = wp._load()
    ingredients = _i
    by_id = {r["id"]: r for r in recipes}
    banned = {"vegetarian": {"meat", "fish"}, "vegan": {"meat", "fish", "dairy", "egg", "honey"}}.get(diet, set())
    bad = []
    if plan["feasible"]:
        if plan["total_cost"] > budget:
            bad.append(f"cost {plan['total_cost']} over budget {budget}")
        target, got = plan["energy"]["target_per_day"], plan["energy"]["planned_per_day"]
        if not 0.895 * target <= got <= 1.155 * target:
            bad.append(f"energy {got} for a need of {target}")
        for d in plan["days"]:
            if set(d["meals"]) != {"breakfast", "lunch", "dinner"}:
                bad.append(f"day {d['day']} incomplete")
            for m in list(d["meals"].values()) + d["snacks"]:
                r = by_id[m["id"]]
                if {ingredients[i["id"]].get("animal") for i in r["ingredients"]} & banned:
                    bad.append(f"{m['id']} breaks {diet}")
                if kitchen and not set(r.get("equipment", [])) <= set(kitchen) | {"kettle"}:
                    bad.append(f"{m['id']} needs more than {kitchen}")
    elif plan["reason"] == "budget":
        if not plan["minimum_budget"] or plan["minimum_budget"] <= budget:
            bad.append(f"minimum budget {plan['minimum_budget']} for budget {budget}")
    elif plan["reason"] == "energy":
        if 500 <= energy_kcal(profile) <= 6000:
            bad.append(f"no plan for {round(energy_kcal(profile))} kcal, inside the promised range")
    else:
        bad.append(f"no plan: {plan['reason']}")
    return bad


def test_planner_handles_the_input_space(engine):
    """Not just the demo: small and athlete-sized needs, every diet and kitchen, cheap and dear shops."""
    import random
    small = Profile(75, "female", 45, 150, "sedentary")        # ~1,000 kcal a day
    typical = Profile(22, "female", 60, 165, "moderate")
    athlete = Profile(20, "male", 90, 190, "very_active")      # ~4,000 kcal a day
    failures = []

    def run(profile, budget, chain, diet=None, kitchen=None):
        plan = wp.plan_week(engine, profile, goal="energy_metabolism", budget=budget, chain=chain,
                            diet=diet, equipment=kitchen)
        failures.extend(f"{profile} {chain} {diet} {kitchen} €{budget}: {b}"
                        for b in _violations(plan, profile, budget, diet, kitchen))
        return plan

    for profile in (small, typical, athlete):
        for chain in ("lidl", "biocoop"):
            for diet in (None, "vegetarian", "vegan"):
                for kitchen in (None, ["microwave"]):
                    assert run(profile, 500, chain, diet, kitchen)["feasible"], (profile, chain, diet, kitchen)
    for chain in ("netto", "monoprix", "naturalia"):
        for diet in (None, "vegan"):
            low = run(typical, 10, chain, diet)
            assert not low["feasible"] and low["reason"] == "budget"
            assert run(typical, low["minimum_budget"], chain, diet)["feasible"], (chain, diet)
    rng = random.Random(42)
    for _ in range(15):
        p = Profile(rng.randint(14, 90), rng.choice(["female", "male"]), round(rng.uniform(40, 140), 1),
                    round(rng.uniform(145, 205), 1), rng.choice(["sedentary", "light", "moderate", "active", "very_active"]))
        run(p, 500, rng.choice(["lidl", "carrefour", "naturalia"]), rng.choice([None, "vegetarian", "vegan"]))
    assert not failures, failures[:10]


def test_needs_out_of_reach_say_so(engine):
    """A need no recipe can be portioned for gets a reason, not a fake budget."""
    giant = Profile(14, "male", 250, 230, "very_active")       # ~7,400 kcal a day
    plan = wp.plan_week(engine, giant, goal=None, budget=500, chain="naturalia")
    assert not plan["feasible"] and plan["reason"] == "energy" and plan["minimum_budget"] is None


def test_unknown_inputs_are_errors_not_ignored(engine):
    """A misspelt diet must never silently become 'no restriction'."""
    for bad in (dict(diet="vegna"), dict(equipment=["oven"]), dict(goal="telepathy")):
        with pytest.raises(ValueError):
            wp.plan_week(engine, STUDENT, **{"goal": None, "budget": 50, "chain": "lidl", **bad})
    for profile in (Profile(30, "male", 70, 175, pregnant=True),
                    Profile(30, "female", 60, 165, pregnant=True, breastfeeding=True)):
        with pytest.raises(ValueError):
            profile.validate()


def test_shown_total_never_exceeds_the_budget(engine):
    """Lines are rounded to cents so they add up to a total the budget covers."""
    for chain, budget in (("lidl", 43), ("aldi", 24), ("carrefour", 35)):
        plan = wp.plan_week(engine, Profile(22, "female", 60, 165, "moderate"), goal=None, budget=budget, chain=chain)
        if plan["feasible"]:
            assert plan["total_cost"] <= budget
            assert round(sum(b["cost"] for b in plan["basket"]), 2) == plan["total_cost"]


def test_unknown_chain_is_an_error(engine):
    with pytest.raises(ValueError):
        wp.plan_week(engine, STUDENT, goal=None, budget=50, chain="harrods")


# --------------------------------------------------------------- API
def test_plan_api_round_trip():
    from fastapi.testclient import TestClient
    from feedforward.api.main import app

    with TestClient(app) as client:
        opts = client.get("/plan/options").json()
        assert {"lidl", "naturalia"} <= {c["id"] for c in opts["chains"]}
        body = {"age": 24, "sex": "male", "weight_kg": 72, "height_cm": 178, "activity": "light",
                "goal": "cognitive_function", "budget": 50, "chain": "lidl"}
        plan = client.post("/plan/week", json=body).json()
        assert plan["feasible"] and plan["chain"]["label"] == "Lidl"
        first = plan["days"][0]["meals"]["breakfast"]["id"]
        rec = client.get(f"/plan/recipes/{first}", params={"chain": "lidl", "scale": plan["portion_scale"]}).json()
        assert rec["ingredients"] and rec["cost_per_serving"] > 0
        assert client.post("/plan/week", json={**body, "age": 9}).status_code == 422
        assert client.post("/plan/week", json={**body, "activity": "couch"}).status_code == 400
        assert client.get("/plan/recipes/nope").status_code == 404
        why = client.get(f"/plan/recipes/{first}/why",
                         params={"goal": "cognitive_function", "scale": plan["portion_scale"]}).json()
        assert why["goal"] == "cognitive_function" and "rule" in why
        assert client.get("/plan/recipes/nope/why").status_code == 404
        assert client.get(f"/plan/recipes/{first}/why", params={"demographic": "martian"}).status_code == 400
        for bad in ({"diet": "keto"}, {"equipment": ["oven"]}, {"goal": "telepathy"}, {"pregnant": True}):
            assert client.post("/plan/week", json={**body, **bad}).status_code in (400, 422), bad
        assert client.get(f"/plan/recipes/{first}", params={"chain": "harrods"}).status_code == 400
        assert client.get(f"/plan/recipes/{first}", params={"scale": -3}).status_code == 422
