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
