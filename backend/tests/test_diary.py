"""The diary: a logged day against its targets, and suggestions for one meal (engine/diary.py, /diary)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from feedforward.api.main import app
from feedforward.engine import diary, load_engine, profile
from feedforward.engine import week_planner as wp
from feedforward.engine.needs import Profile, energy_kcal

STUDENT = Profile(24, "male", 72, 178, "light")
PERSON = dict(age=24, sex="male", weight_kg=72, height_cm=178, activity="light")


@pytest.fixture(scope="module")
def engine():
    return load_engine()


def _all_suggestions(engine, meal, **kw):
    """Every recipe the diary would ever suggest for this meal: ask again, excluding what was shown, until none."""
    shown = []
    while True:
        r = diary.suggest_meal(engine, STUDENT, [], meal, k=6, exclude=shown, **kw)
        if not r["options"]:
            return shown
        shown += [o["id"] for o in r["options"]]


def test_vegetarian_ideas_have_no_animal_flesh(engine):
    """The first idea a vegetarian sees (day one, inline) comes from these: none may contain meat or fish."""
    import json
    from pathlib import Path
    flesh = {"chicken", "ham", "minced-beef", "mackerel", "salmon", "sardines", "tuna"}
    recipes = {r["id"]: r for r in json.loads(
        (Path(__file__).resolve().parents[1] / "feedforward" / "data" / "recipes.json").read_text(encoding="utf-8"))["recipes"]}
    for meal in ("breakfast", "lunch", "dinner", "snack"):
        ids = _all_suggestions(engine, meal, goal=None, diet="vegetarian")
        assert ids, meal
        for rid in ids:
            assert not flesh & {i["id"] for i in recipes[rid]["ingredients"]}, (meal, rid)


def test_an_empty_day_has_targets_and_nothing_eaten(engine):
    s = diary.day_summary(engine, STUDENT, [], goal="sleep_support")
    assert s["totals"] == {"kcal": 0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    assert s["targets"]["kcal"] == round(energy_kcal(STUDENT))
    assert all(v == 0 for v in s["coverage"].values())
    assert all(g["from"] is None for g in s["goal_nutrients"])


def test_logged_totals_add_up(engine):
    recipes = {r.id: r for r in wp._recipes(engine, wp.portion_scale(STUDENT))}
    food = engine.food_by_id["wf-042"]                                   # banana
    entries = diary.entries_from([
        {"kind": "recipe", "id": "porridge-banana-walnut", "meal": "breakfast", "servings": 1.5},
        {"kind": "food", "id": "wf-042", "meal": "snack", "grams": 120}])
    s = diary.day_summary(engine, STUDENT, entries, goal=None)
    kcal = 1.5 * recipes["porridge-banana-walnut"].nutrients["energy-kcal"] + 1.2 * food.nutrients["energy-kcal"]
    assert s["totals"]["kcal"] == round(kcal)
    assert s["meals"]["breakfast"]["kcal"] + s["meals"]["snack"]["kcal"] == pytest.approx(s["totals"]["kcal"], abs=1)
    assert s["meal_shares"]["breakfast"]["kcal"] + s["meal_shares"]["snack"]["kcal"] in (99, 100, 101)


def test_a_deficit_lowers_the_target_but_never_below_resting(engine):
    keep = diary.day_summary(engine, STUDENT, [], goal=None)
    cut = diary.day_summary(engine, STUDENT, [], goal=None, answers={"energy_goal": "deficit"})
    assert cut["targets"]["kcal"] < keep["targets"]["kcal"]
    assert cut["targets"]["kcal"] >= cut["energy"]["resting"]


def test_bad_entries_are_refused(engine):
    for bad in ({"kind": "drink", "id": "x", "meal": "lunch"}, {"kind": "food", "id": "wf-042", "meal": "brunch", "grams": 10},
                {"kind": "food", "id": "wf-042", "meal": "lunch", "grams": 0}):
        with pytest.raises(ValueError):
            diary.entries_from([bad])
    with pytest.raises(ValueError):
        diary.day_summary(engine, STUDENT, diary.entries_from([{"kind": "recipe", "id": "nope", "meal": "lunch"}]), goal=None)


def test_suggestions_follow_every_hard_preference(engine):
    """Diet, foods not eaten, cooking time, kitchen and "not for me": no suggestion ever breaks one."""
    by_id = {r.id: r for r in wp._recipes(engine)}
    avoid = ["omelette-spinach-toast"]
    not_eaten = profile.resolve({"dont_eat": ["eggs", "nuts"]}, None, STUDENT, goal=None,
                                known_goals=set(engine.scorer.positive)).exclude
    assert not_eaten
    for meal in ("breakfast", "lunch", "dinner", "snack"):
        ids = _all_suggestions(engine, meal, goal="energy_metabolism", diet="vegetarian", equipment=["microwave"],
                               answers={"dont_eat": ["eggs", "nuts"], "cook_time": "20"}, avoid_recipes=avoid)
        assert len(ids) == len(set(ids))
        for rid in ids:
            r = by_id[rid]
            assert not r.animal & {"meat", "fish"}, rid
            assert not r.tags & not_eaten, rid
            assert set(r.equipment) <= {"microwave", "kettle"}, rid
            assert meal in r.meals and rid not in avoid
            if meal != "snack":
                assert r.time_min <= (60 if r.batch else 20), rid


def test_logged_recipes_are_not_suggested_again(engine):
    first = diary.suggest_meal(engine, STUDENT, [], "lunch", goal="iron_support")["options"][0]["id"]
    entries = diary.entries_from([{"kind": "recipe", "id": first, "meal": "dinner"}])
    again = diary.suggest_meal(engine, STUDENT, entries, "lunch", goal="iron_support")
    assert first not in [o["id"] for o in again["options"]]


def test_suggestions_explain_themselves(engine):
    r = diary.suggest_meal(engine, STUDENT, [], "dinner", goal="sleep_support", answers={"sleep_onset": "often"})
    assert len(r["options"]) == 3 and r["energy_for_meal"] > 0
    assert {l["id"] for l in r["levers"]} >= {"evening_carbs", "no_evening_caffeine"}
    for o in r["options"]:
        for rz in o["reasons"]:
            assert rz["kind"] in ("nutrient", "strategy")
            if rz["kind"] == "nutrient":
                assert rz["percent"] >= diary.REASON_MIN_SHARE
    carb_rich = [o for o in r["options"] if any(rz.get("id") == "evening_carbs" for rz in o["reasons"])]
    for o in carb_rich:
        assert 4 * o["carbs"] / o["kcal"] >= diary.CARB_RICH - 0.03


def test_a_declined_strategy_does_not_steer_suggestions(engine):
    r = diary.suggest_meal(engine, STUDENT, [], "dinner", goal=None, answers={"sleep_onset": "often"},
                           declined=["evening_carbs"])
    assert "evening_carbs" not in {l["id"] for l in r["levers"]}
    assert all(rz.get("id") != "evening_carbs" for o in r["options"] for rz in o["reasons"])


def test_the_energy_left_for_a_meal_follows_the_day(engine):
    empty = diary.suggest_meal(engine, STUDENT, [], "dinner", goal=None)["energy_for_meal"]
    big_lunch = diary.entries_from([{"kind": "recipe", "id": "lentil-bolognese", "meal": "lunch", "servings": 2}])
    after = diary.suggest_meal(engine, STUDENT, big_lunch, "dinner", goal=None)["energy_for_meal"]
    assert 0 < after < empty
    light = diary.suggest_meal(engine, STUDENT, [], "breakfast", goal=None, answers={"morning_hunger": "not_hungry"})
    usual = diary.suggest_meal(engine, STUDENT, [], "breakfast", goal=None)
    assert light["energy_for_meal"] < usual["energy_for_meal"]


def test_diary_api():
    with TestClient(app) as client:
        day = client.post("/diary/day", json={**PERSON, "goal": "iron_support",
                                               "entries": [{"kind": "food", "id": "wf-042", "meal": "snack", "grams": 120}]})
        assert day.status_code == 200 and day.json()["totals"]["kcal"] > 0
        sug = client.post("/diary/suggest", json={**PERSON, "meal": "lunch", "k": 2})
        assert sug.status_code == 200 and len(sug.json()["options"]) == 2
        assert client.post("/diary/suggest", json={**PERSON, "meal": "brunch"}).status_code == 422
        bad = client.post("/diary/day", json={**PERSON, "entries": [{"kind": "recipe", "id": "nope", "meal": "lunch"}]})
        assert bad.status_code == 400
        found = client.get("/diary/search", params={"q": "porridge"}).json()
        assert found["recipes"] and all(f["portion_g"] > 0 for f in found["foods"])
