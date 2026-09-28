"""Goal scoring: portions, delivery, bioavailability, penalties, ranking, meals."""
from __future__ import annotations

import math

import pytest

from feedforward.engine import build_engine
from feedforward.engine.benchmark import evaluate, summary
from feedforward.engine.meal_optimizer import greedy_meal, optimize_meal
from feedforward.engine.portions import portion_for, portion_for_text
from feedforward.engine.recommender import (food_family, is_excluded_food,
                                            satisfies)
from feedforward.engine.schema import Food
from feedforward.engine.scoring import GoalScorer, saturate


@pytest.fixture(scope="module")
def engine():
    return build_engine()


def _scorer(edges=None):
    return GoalScorer(edges or [
        {"nutrient": "iron", "goal": "iron_support", "weight": 0.95},
        {"nutrient": "vitamin-c", "goal": "iron_support", "weight": 0.8, "type": "enhancer"},
        {"nutrient": "calcium", "goal": "bone_health", "weight": 0.95},
        {"nutrient": "vitamin-a", "goal": "vision_support", "weight": 0.9},
        {"nutrient": "potassium", "goal": "blood_pressure_support", "weight": 0.8},
        {"nutrient": "sodium", "goal": "blood_pressure_support", "weight": 0.85,
         "type": "negative"},
    ])


# --- saturation and combination ------------------------------------------

def test_saturation_is_anchored_to_eu_claim_thresholds():
    # "source of" = 15% of NRV, "high in" = 30% (Reg. 1924/2006).
    assert saturate(0.30) == pytest.approx(0.70, abs=0.01)
    assert saturate(0.15) == pytest.approx(0.45, abs=0.01)
    assert saturate(0) == 0
    assert saturate(10) <= 1.0
    assert saturate(1.0) - saturate(0.5) < saturate(0.5) - saturate(0.0)


def test_strongest_path_dominates_combination():
    one_strong = GoalScorer.combine([0.8])
    many_weak = GoalScorer.combine([0.3, 0.3, 0.3, 0.3])
    assert one_strong > many_weak
    assert GoalScorer.combine([0.8, 0.5]) > one_strong
    assert GoalScorer.combine([]) == 0.0


# --- portions -----------------------------------------------------------

@pytest.mark.parametrize("name,category,grams", [
    ("Leavening agents, baking powder, double-acting", "Baked Products", 2),
    ("Spices, sage, ground", "Spices and Herbs", 2),
    ("Peppers, sweet, red, freeze-dried", "Vegetables and Vegetable Products", 5),
    ("Peppers, pasilla, dried", "Vegetables and Vegetable Products", 10),
    ("Lentils, mature seeds, cooked, boiled, without salt", "Legumes and Legume Products", 150),
    ("Lentils, raw", "Legumes and Legume Products", 50),
    ("Beans, kidney, dried", "Legumes", 50),
    ("Flour, soy, defatted", "Legumes and Legume Products", 50),
    ("Oranges, raw", "Fruits and Fruit Juices", 120),
    ("Orange juice, raw", "Fruits and Fruit Juices", 250),
    ("EXTRA VIRGIN OLIVE OIL", "Olive oils", 10),
    ("Beef, boiled", "Beef Products", 100),
    ("Water convolvulus, raw", "Vegetables and Vegetable Products", 80),
    ("Snacks, rice cakes, brown rice", "Snacks", 20),
    ("Parsley, fresh", "Vegetables and Vegetable Products", 5),
    ("Sauce, chili, peppers, hot", "Soups, Sauces, and Gravies", 20),
    ("Cheese, parmesan", "Dairy and Egg Products", 30),
])
def test_reference_portions(name, category, grams):
    assert portion_for_text(name, category).grams == grams


def test_packaged_products_are_weighed_dry():
    pasta = Food("p", "Spaghetti complets", "Pâtes", {}, source="openfoodfacts")
    canned = Food("c", "Lentilles cuites en conserve", "Légumineuses", {}, source="openfoodfacts")
    usda = Food("u", "Spaghetti, cooked", "Cereal Grains and Pasta", {}, source="usda")
    assert portion_for(pasta).grams == 70
    assert portion_for(canned).grams == 150
    assert portion_for(usda).grams == 180


# --- delivery and bioavailability ---------------------------------------

def test_heme_iron_beats_non_heme_at_equal_content():
    s = _scorer()
    beef = Food("b", "Beef, raw", "Beef Products", {"iron": 2.5}, is_animal_source=True)
    beans = Food("l", "Beans, kidney, cooked", "Legumes", {"iron": 2.5 * 100 / 150})
    # Same mg per portion (2.5 mg): 100 g beef vs 150 g beans.
    assert s.delivery(beef, "iron").amount == pytest.approx(s.delivery(beans, "iron").amount)
    assert s.delivery(beef, "iron").relative_bioavailability > 1.0
    assert s.delivery(beans, "iron").relative_bioavailability < 1.0
    assert s.delivery(beef, "iron").strength > s.delivery(beans, "iron").strength


def test_own_vitamin_c_does_not_inflate_own_iron():
    """Meal factors come from added vitamin C; a food's own is already in its absorption."""
    s = _scorer()
    plain = Food("a", "Chard, raw", "Vegetables", {"iron": 1.8})
    with_c = Food("b", "Chard, raw", "Vegetables", {"iron": 1.8, "vitamin-c": 30},
                  contains_vitamin_c=True)
    assert s.relative_bioavailability("iron", plain) == s.relative_bioavailability("iron", with_c)


def test_oxalate_limits_calcium_from_spinach():
    s = _scorer()
    spinach = Food("s", "Spinach, raw", "Vegetables", {"calcium": 99})
    spinach.anti_nutrients = {"oxalate"}
    kale = Food("k", "Kale, raw", "Vegetables", {"calcium": 99})
    assert s.relative_bioavailability("calcium", spinach) == pytest.approx(0.25)
    assert s.relative_bioavailability("calcium", kale) == 1.0


def test_enhancer_is_not_a_route():
    s = _scorer()
    acerola = Food("a", "Acerola, raw", "Fruits", {"vitamin-c": 1677})
    assert s.score(acerola, "iron_support").score == 0.0
    lentils = Food("l", "Lentils, boiled", "Legumes", {"iron": 3.3})
    assert s.score(lentils, "iron_support").pairings == ["vitamin-c"]


def test_upper_limit_discounts_liver_but_not_carrots():
    s = _scorer()
    liver = Food("lv", "Beef, liver, raw", "Beef Products",
                 {"vitamin-a": 4968, "iron": 4.9}, is_animal_source=True)
    carrot = Food("c", "Carrots, raw", "Vegetables", {"vitamin-a": 4000})
    assert s.delivery(liver, "vitamin-a").exceeds_ul
    assert not s.delivery(carrot, "vitamin-a").exceeds_ul   # carotenoids have no UL
    # The UL counts against liver for every goal, iron included.
    kinds = {p.kind for p in s.penalties(liver, "iron_support")}
    assert "upper_limit" in kinds


def test_sodium_penalty_is_stronger_for_blood_pressure():
    s = _scorer()
    salty = Food("x", "Beans, canned, salted", "Legumes",
                 {"potassium": 400, "sodium": 600})
    fresh = Food("y", "Beans, boiled, without salt", "Legumes",
                 {"potassium": 400, "sodium": 5})
    assert s.score(salty, "blood_pressure_support").score < s.score(fresh, "blood_pressure_support").score
    specific = [p for p in s.penalties(salty, "blood_pressure_support") if p.nutrient == "sodium"]
    assert specific and specific[0].goal_specific


# --- filters and exclusions ---------------------------------------------

@pytest.mark.parametrize("name,category,vegetarian,vegan", [
    ("Champignons de Paris", "Mushrooms", True, True),
    ("Pâtes complètes", "Pasta", True, True),
    ("Pâté de campagne", "Pâtés", False, False),
    ("Fromage moulé à la louche", "Cheeses", True, False),
    ("Moules marinières", "Plats", False, False),
    ("Lamb's lettuce, raw", "Vegetables", True, True),
    ("Beans, kidney, red, raw", "Legumes", True, True),
    ("Caribou, liver, raw (Alaska Native)", "American Indian/Alaska Native Foods", False, False),
    ("Cockles, raw (Alaska Native)", "American Indian/Alaska Native Foods", False, False),
    ("Chili with beans, canned", "Meals, Entrees, and Side Dishes", False, False),
    ("WENDY'S, CLASSIC DOUBLE, with cheese", "Fast Foods", False, False),
    ("Pizza, cheese, meatless", "Fast Foods", True, False),
    ("Burger végétarien", "Plats préparés", True, False),
    ("Coconut milk", "Nut and Seed Products", True, True),
    ("Cheese, goat, hard type", "Dairy and Egg Products", True, False),
])
def test_dietary_filters(name, category, vegetarian, vegan):
    food = Food("x", name, category, {})
    assert satisfies(food, "vegetarian") is vegetarian
    assert satisfies(food, "vegan") is vegan


@pytest.mark.parametrize("name,excluded", [
    ("Oil, bearded seal (Oogruk) (Alaska Native)", True),
    ("Sea lion, Steller, meat (Alaska Native)", True),
    ("Fish oil, cod liver", True),
    ("Pokeberry shoots, (poke), raw", True),
    ("Taro leaves, raw", True),
    ("Taro leaves, cooked, steamed", False),
    ("Babyfood, cereal, rice", True),
    ("Sealed jar of almonds", False),
])
def test_default_exclusions(name, excluded):
    assert is_excluded_food(Food("x", name, "", {})) is excluded


@pytest.mark.parametrize("name,category,excluded", [
    ("Seeds, cottonseed flour, low fat (glandless)", "Nut and Seed Products", True),
    ("Soy meal, defatted, raw", "Legumes and Legume Products", True),
    ("Flour, soy, defatted", "Legumes and Legume Products", True),
    ("Seeds, safflower seed meal, partially defatted", "Nut and Seed Products", True),
    ("Oil, industrial, soy, fully hydrogenated", "Fats and Oils", True),
    ("Flour, soy, full-fat, raw", "Legumes and Legume Products", False),
    ("Oatmeal, cooked", "Breakfast Cereals", False),
    ("Seeds, sesame seeds, whole, dried", "Nut and Seed Products", False),
    ("Caribou, eye, raw (Alaska Native)", "American Indian/Alaska Native Foods", True),
    ("Rose Hips, wild (Northern Plains Indians)", "American Indian/Alaska Native Foods", True),
])
def test_industrial_and_search_only_exclusions(name, category, excluded):
    assert is_excluded_food(Food("x", name, category, {})) is excluded


def test_food_family_ignores_preparation():
    assert food_family("Lentils, mature seeds, cooked, boiled, without salt") == \
        food_family("Lentils, mature seeds, raw")
    assert food_family("Beef, spleen, raw") != food_family("Lamb, spleen, raw")


# --- end to end ---------------------------------------------------------

def test_recommendations_are_diverse_and_explained(engine):
    recs = engine.foods_for_goal("iron_support", k=20)
    assert len(recs) == 20
    families = [food_family(r.food_name) for r in recs]
    assert len(set(families)) == len(families)
    # Ordered by score weighted towards everyday foods (Recommender._order).
    floor = engine.FAMILIARITY_FLOOR
    keys = [r.score * (floor + (1 - floor) * engine.food_by_id[r.food_id].familiarity) for r in recs]
    assert keys == sorted(keys, reverse=True) or all(
        abs(a - b) < 1e-3 or a >= b for a, b in zip(keys, keys[1:]))
    top = recs[0].explanation
    assert top.contributions and top.contributions[0]["nutrient"] == top.nutrient
    assert top.portion_g > 0
    assert 0 < recs[0].match <= 100
    # The explanation route is the strongest contribution: -log(strength).
    assert top.total_cost == pytest.approx(-math.log(top.contributions[0]["strength"]), abs=1e-3)


def test_vitamin_c_foods_do_not_rank_for_iron(engine):
    names = [r.food_name.lower() for r in engine.foods_for_goal("iron_support", k=30)]
    assert not any("acerola" in n or "orange-flavor" in n for n in names)


def test_excluded_foods_never_recommended(engine):
    for goal in ("cognitive_function", "vision_support", "iron_support"):
        for r in engine.foods_for_goal(goal, k=30, explain=False):
            assert not is_excluded_food(engine.food_by_id[r.food_id]), r.food_name


def test_vegan_substitutes_for_milk(engine):
    milk = next(f for f in engine.foods if f.name.startswith("Milk, whole, 3.25%"))
    subs = engine.similar_foods(milk.id, k=5, constraints=["vegan"])
    assert any("soymilk" in s.food_name.lower() or "oat milk" in s.food_name.lower()
               for s in subs)
    assert all(satisfies(engine.food_by_id[s.food_id], "vegan") for s in subs)


def test_similar_foods_skip_same_food_variants(engine):
    lentils = next(f for f in engine.foods
                   if f.name.startswith("Lentils, mature seeds, cooked, boiled, without"))
    sims = engine.similar_foods(lentils.id, k=5)
    assert all(food_family(s.food_name) != food_family(lentils.name) for s in sims)


def test_meal_optimizer_beats_greedy_and_respects_constraints(engine):
    plan = optimize_meal(engine, "iron_support", 600, k=3, constraints=["vegetarian"])
    greedy = greedy_meal(engine, "iron_support", 600, k=3, constraints=["vegetarian"])
    assert plan.feasible and len(plan.items) == 3
    assert plan.total_kcal <= 600
    assert plan.total_cost <= greedy.total_cost + 1e-9
    assert all(satisfies(engine.food_by_id[i.food_id], "vegetarian") for i in plan.items)
    groups = [portion_for(engine.food_by_id[i.food_id]).group for i in plan.items]
    assert len(set(groups)) == len(groups)
    assert plan.coverage.get("iron", 0) > 50


def test_benchmark_regression(engine):
    """
    Guards the ranking against the sanity benchmark. v1.2 scored 0.31 with 34
    implausible foods; v1.3 must stay well above that. Thresholds, not exact
    numbers, so data growth does not break the build.
    """
    s = summary(evaluate(engine))
    assert s["mean_hit_rate"] >= 0.55
    assert s["implausible_total"] <= 8


# --- API ----------------------------------------------------------------

def test_api_exposes_contributions_similar_and_coverage():
    from fastapi.testclient import TestClient
    from feedforward.api.main import app
    with TestClient(app) as client:
        rec = client.post("/recommend", json={"goal": "bone_health", "k": 3})
        assert rec.status_code == 200, rec.text
        exp = rec.json()["recommendations"][0]["explanation"]
        assert exp["contributions"] and exp["portion_g"] > 0
        assert exp["contributions"][0]["evidence"] == ""   # consumer tier
        fid = rec.json()["recommendations"][0]["food_id"]
        sim = client.get(f"/foods/{fid}/similar", params={"k": 3, "constraints": ["vegan"]})
        assert sim.status_code == 200 and len(sim.json()) <= 3
        plan = client.post("/meal-plan", json={"goal": "iron_support", "max_calories": 600})
        assert plan.status_code == 200 and plan.json()["coverage"]


# --- familiarity ----------------------------------------------------------

def test_familiarity_orders_but_does_not_rescore(engine):
    from feedforward.engine.familiarity import familiarity
    emu = Food("e", "Emu, fan fillet, cooked, broiled", "Poultry Products", {}, source="usda")
    lentils = Food("l", "Lentils, mature seeds, cooked", "Legumes", {}, source="curated")
    assert familiarity(emu, "usda-fdc-sr-legacy") < 0.3 < familiarity(lentils, "feedforward-curated")
    top = engine.foods_for_goal("energy_metabolism", k=10, explain=False)
    names = " ".join(r.food_name.lower() for r in top)
    assert "emu" not in names and "grouse" not in names and "game meat" not in names
    # Displayed score is still the goal score, not the familiarity-weighted key.
    assert all(r.score == round(engine.goal_score(r.food_id, "energy_metabolism"), 4) for r in top)
