"""Planner preferences: the strategies file, its validation, and the food tags it relies on."""
from __future__ import annotations

import copy

import pytest

from feedforward.engine import load_engine
from feedforward.engine import profile
from feedforward.engine import week_planner as wp
from feedforward.engine.needs import Profile, energy_kcal, resting_kcal

STUDENT = Profile(24, "male", 72, 178, "light")
GOALS = set(load_engine().scorer.positive)


@pytest.fixture(scope="module")
def engine():
    return load_engine()


def _with(data: dict, i: int, **changes) -> dict:
    """A deep copy of the strategies data with strategy ``i`` changed."""
    out = copy.deepcopy(data)
    out["strategies"][i].update(changes)
    return out


# --------------------------------------------------------------- strategies file
def test_strategies_file_is_valid(engine):
    data = profile.load_strategies()
    profile.validate_strategies(data, set(engine.scorer.positive))     # no exception
    for s in data["strategies"]:
        if s["kind"] == "strategy":
            assert s["grade"] in "ABC" and s["pmids"] and s["goal"] in engine.scorer.positive


def test_strategy_wording_matches_its_sources():
    """What people read: each strategy's grade, sources and why, worded as its sources support (final review)."""
    by_id = {s["id"]: s for s in profile.load_strategies()["strategies"]}
    expected = {
        "no_evening_caffeine": ("B", ["36870101", "24235903"],
                                "A meta-analysis of 24 studies found caffeine shortened sleep by about 45 minutes; in one "
                                "trial, caffeine even six hours before bed cut sleep."),
        "evening_carbs": ("C", ["17284739", "27633109"],
                          "In small trials, a carbohydrate-rich evening meal with a high glycaemic index, eaten about "
                          "four hours before bed, shortened the time to fall asleep. The evidence is limited."),
        "protein_breakfast": ("C", ["23446906"],
                              "In a small trial, a higher-protein breakfast kept people fuller and reduced evening "
                              "snacking."),
        "protein_spread": ("C", ["23459753", "29497353"],
                           "In a training study, 20 g of protein every three hours built muscle protein better than "
                           "fewer large servings or many small ones."),
        "post_training_carbs": ("C", ["28919842"],
                                "Carbohydrate after exercise refills muscle glycogen; it matters most when the next "
                                "session is only a few hours away."),
    }
    for sid, (grade, pmids, why) in expected.items():
        assert (by_id[sid]["grade"], by_id[sid]["pmids"], by_id[sid]["why"]) == (grade, pmids, why), sid


def test_validation_rejects_bad_entries(engine):
    data = profile.load_strategies()
    goals = set(engine.scorer.positive)
    for broken in (_with(data, 0, grade="D"), _with(data, 0, pmids=[]), _with(data, 0, goal="telepathy"),
                   _with(data, 0, lever={"type": "levitate"}), _with(data, 0, when=[{"sleep_onset": ["never"]}])):
        with pytest.raises(ValueError):
            profile.validate_strategies(broken, goals)


def test_validation_rejects_bad_structure(engine):
    """The other rules: question ids, `when` keys, the training-time map, goal links, duplicate ids."""
    data = profile.load_strategies()
    goals = set(engine.scorer.positive)
    post_training = next(i for i, s in enumerate(data["strategies"]) if s["id"] == "post_training_carbs")

    duplicate_question = copy.deepcopy(data)
    duplicate_question["questions"].append(dict(duplicate_question["questions"][0]))
    unknown_question = _with(data, 0, when=[{"sleepiness": "*"}])
    map_misses_an_option = copy.deepcopy(data)
    del map_misses_an_option["strategies"][post_training]["lever"]["map"]["evening"]
    alpha_zero = copy.deepcopy(data)
    alpha_zero["goals"][0]["alpha"] = 0
    alpha_above_one = copy.deepcopy(data)
    alpha_above_one["goals"][0]["alpha"] = 1.5
    unknown_goal_link = copy.deepcopy(data)
    unknown_goal_link["goals"][0]["goal"] = "telepathy"
    duplicate_strategy = copy.deepcopy(data)
    duplicate_strategy["strategies"][1]["id"] = duplicate_strategy["strategies"][0]["id"]

    for broken in (duplicate_question, unknown_question, map_misses_an_option, alpha_zero, alpha_above_one,
                   unknown_goal_link, duplicate_strategy):
        with pytest.raises(ValueError):
            profile.validate_strategies(broken, goals)


def test_load_strategies_checks_structure_without_the_engine():
    """load_strategies() has no engine, so it checks everything except that goals exist."""
    data = profile.load_strategies()
    assert data is profile.load_strategies()                       # cached
    profile._check_structure(_with(data, 0, goal="telepathy"))      # goal existence is the engine's to check
    with pytest.raises(ValueError):
        profile._check_structure(_with(data, 0, grade="D"))


def test_strategies_come_before_preferences():
    kinds = [s["kind"] for s in profile.load_strategies()["strategies"]]
    assert kinds[0] == "strategy" and kinds == sorted(kinds, key=("strategy", "preference").index)


def test_questions_are_the_questionnaire():
    qs = profile.questions()
    assert [q["id"] for q in qs] == ["energy_goal", "sleep_onset", "training_days", "training_time", "morning_hunger",
                                     "energy_dips", "study_time", "dont_eat", "cook_time", "batch_ok"]
    assert [q["id"] for q in qs if q.get("multi")] == ["dont_eat"]
    assert next(q for q in qs if q["id"] == "dont_eat")["options"] == list(profile.CATEGORIES)
    assert all(q["text"] and q["options"] for q in qs)


# --------------------------------------------------------------- tags
def test_tags_cover_the_categories():
    ingredients, recipes, _ = wp._load()
    tagged = {t for i in ingredients.values() for t in i["tags"]} | {t for r in recipes for t in r.get("tags", [])}
    assert set(profile.CATEGORIES) | {"caffeine"} == tagged
    assert {r["id"] for r in recipes if "spicy" in r.get("tags", [])} == {"bean-chili-rice", "beef-bean-chili", "chickpea-spinach-curry"}


# --------------------------------------------------------------- energy
def test_resting_energy_is_mifflin_without_activity():
    assert resting_kcal(STUDENT) == pytest.approx(10 * 72 + 6.25 * 178 - 5 * 24 + 5)
    assert energy_kcal(STUDENT) == round(resting_kcal(STUDENT) * 1.375)


def test_energy_goal_limits():
    assert profile.energy_options(STUDENT) == {"maintain": None, "deficit": None, "surplus": None}
    assert profile.energy_options(Profile(16, "male", 60, 170))["deficit"]
    assert profile.energy_options(Profile(16, "male", 60, 170))["surplus"]
    assert profile.energy_options(Profile(30, "female", 60, 165, pregnant=True))["deficit"]
    thin = Profile(25, "female", 48, 170)            # BMI 16.6
    assert profile.energy_options(thin)["deficit"] and profile.energy_options(thin)["surplus"] is None
    with pytest.raises(ValueError):
        profile.resolve({"energy_goal": "deficit"}, None, thin, goal=None, known_goals=GOALS)


# --------------------------------------------------------------- answers -> levers
def test_answers_turn_on_goals_and_strategies():
    lv = profile.resolve({"sleep_onset": "often", "training_days": "3-4", "training_time": "evening"}, None,
                         STUDENT, goal="cognitive_function", known_goals=GOALS)
    assert lv.goals == {"cognitive_function": 1.0, "sleep_support": 0.5, "muscle_recovery": 0.5}
    assert lv.meal_carb_share == {"dinner": 0.40} and lv.no_caffeine_at == {"dinner"}
    assert lv.protein_g_per_kg == 1.6 and lv.protein_per_meal_g_per_kg == 0.3
    assert {a["id"] for a in lv.applied} >= {"evening_carbs", "no_evening_caffeine", "protein_target",
                                              "protein_spread", "post_training_carbs"}


def test_primary_goal_keeps_alpha_one():
    lv = profile.resolve({"study_time": "afternoons"}, None, STUDENT, goal="cognitive_function", known_goals=GOALS)
    assert lv.goals == {"cognitive_function": 1.0}


def test_preferences_and_energy():
    lv = profile.resolve({"energy_goal": "deficit", "dont_eat": ["fish_seafood", "spicy"], "cook_time": "20",
                          "batch_ok": "yes", "morning_hunger": "not_hungry"}, None, STUDENT, goal=None, known_goals=GOALS)
    assert lv.energy_factor == 0.85 and lv.exclude == {"fish_seafood", "spicy"}
    assert lv.max_minutes == 20 and lv.batch_ok and lv.breakfast_energy_max == 0.20


def test_partial_answers_and_declined():                                  # Review Focus 1 and 5
    lv = profile.resolve({"sleep_onset": "often"}, ["evening_carbs", "big_breakfast"], STUDENT, goal=None, known_goals=GOALS)
    assert lv.meal_carb_share == {} and lv.no_caffeine_at == {"dinner"}
    with pytest.raises(ValueError):
        profile.resolve({"sleep_onset": "often"}, ["levitation"], STUDENT, goal=None, known_goals=GOALS)


def test_unknown_answers_are_errors():
    for bad in ({"sleep_onset": "never"}, {"mood": "ok"}, {"dont_eat": ["kale"]}, {"dont_eat": "fish_seafood"}):
        with pytest.raises(ValueError):
            profile.resolve(bad, None, STUDENT, goal=None, known_goals=GOALS)


def test_no_answers_is_today():
    assert profile.resolve(None, None, STUDENT, goal="sleep_support", known_goals=GOALS) == profile.Levers.none("sleep_support")


# --------------------------------------------------------------- edges of resolve and propose
def test_energy_refusals_say_why():
    assert profile.energy_options(Profile(16, "male", 60, 170))["deficit"] == \
        "Deficit and surplus are for adults: under 18 the plan follows growth needs."
    assert profile.energy_options(Profile(30, "female", 60, 165, breastfeeding=True))["surplus"] == \
        "In pregnancy and breastfeeding the plan follows the needs of those months."
    assert profile.energy_options(Profile(25, "female", 48, 170))["deficit"] == \
        "With a BMI under 18.5 a deficit is not offered."
    with pytest.raises(ValueError, match="BMI under 18.5"):
        profile.resolve({"energy_goal": "deficit"}, None, Profile(25, "female", 48, 170), goal=None, known_goals=GOALS)
    # maintain is always open, and a surplus is open at a low BMI
    profile.resolve({"energy_goal": "maintain"}, None, Profile(16, "male", 60, 170), goal=None, known_goals=GOALS)
    assert profile.resolve({"energy_goal": "surplus"}, None, Profile(25, "female", 48, 170), goal=None,
                           known_goals=GOALS).energy_factor == 1.10


def test_nothing_answered_is_the_plain_planner():
    assert profile.Levers.none(None).goals == {} and profile.Levers.none("x").goals == {"x": 1.0}
    for nothing in (None, {}, {"dont_eat": []}):
        assert profile.resolve(nothing, None, STUDENT, goal=None, known_goals=GOALS) == profile.Levers.none(None)
    lv = profile.Levers.none("sleep_support")
    assert (lv.energy_goal, lv.energy_factor, lv.applied) == ("maintain", 1.0, ())
    assert not lv.batch_ok and lv.max_minutes is None and not lv.exclude and not lv.avoid_recipes


def test_propose_works_without_answers_and_says_because():
    empty = profile.propose({}, Profile(16, "male", 60, 170), goal=None, known_goals=GOALS)
    assert empty["goals"] == [] and empty["strategies"] == []
    assert set(empty["unavailable"]) == {"energy_goal=deficit", "energy_goal=surplus"}
    assert profile.propose({}, STUDENT, goal=None, known_goals=GOALS)["unavailable"] == {}

    out = profile.propose({"sleep_onset": "often", "energy_goal": "deficit", "training_days": "5+",
                           "training_time": "morning", "study_time": "mornings"},
                          STUDENT, goal="cognitive_function", known_goals=GOALS)
    assert {g["id"]: g["alpha"] for g in out["goals"]} == {"sleep_support": 0.5, "muscle_recovery": 0.5,
                                                          "cognitive_function": 1.0}
    assert next(g for g in out["goals"] if g["id"] == "sleep_support")["because"] == \
        {"question": "sleep_onset", "answer": "often"}
    by_id = {s["id"]: s for s in out["strategies"]}
    assert by_id["protein_target"]["because"] == {"question": "energy_goal", "answer": "deficit"}   # first match wins
    assert by_id["post_training_carbs"]["because"] == {"question": "training_days", "answer": "5+"}
    assert by_id["evening_carbs"]["grade"] == "C" and by_id["evening_carbs"]["pmids"]
    with pytest.raises(ValueError):
        profile.propose({"energy_goal": "deficit"}, Profile(16, "male", 60, 170), goal=None, known_goals=GOALS)


def test_more_bad_input_is_an_error():
    for answers in ({"sleep_onset": ["often"]}, {"cook_time": 20}, {"batch_ok": None}, ["sleep_onset"]):
        with pytest.raises(ValueError):
            profile.resolve(answers, None, STUDENT, goal=None, known_goals=GOALS)
    for declined in ("evening_carbs", [1], ["evening_carbs", "levitation"]):
        with pytest.raises(ValueError):
            profile.resolve({"sleep_onset": "often"}, declined, STUDENT, goal=None, known_goals=GOALS)
    with pytest.raises(ValueError):                              # goals not in the graph are the file's fault
        profile.resolve({}, None, STUDENT, goal=None, known_goals={"sleep_support"})


def test_declined_ids_cover_strategies_and_preferences():
    """batch_cooking is a known id the answers do not trigger: declining it is not an error."""
    lv = profile.resolve({"morning_hunger": "not_hungry", "energy_dips": "mid_morning", "cook_time": "10"},
                         ["light_breakfast", "protein_breakfast", "batch_cooking"],
                         STUDENT, goal=None, known_goals=GOALS)
    assert lv.breakfast_energy_max is None and lv.breakfast_protein_g_per_kg is None and lv.max_minutes == 10
    assert [a["id"] for a in lv.applied] == ["cook_time"]
    assert set(lv.goals) == {"energy_metabolism"}                 # a goal an answer turned on stays when a strategy is declined


def test_cook_time_any_is_no_limit_and_nothing_applied():
    any_time = profile.resolve({"cook_time": "any"}, None, STUDENT, goal=None, known_goals=GOALS)
    assert any_time.max_minutes is None and any_time.applied == ()
    assert profile.resolve({"cook_time": "30"}, None, STUDENT, goal=None, known_goals=GOALS).max_minutes == 30
    assert not profile.resolve({"batch_ok": "no"}, None, STUDENT, goal=None, known_goals=GOALS).batch_ok


def test_applied_entries_have_the_same_keys_for_strategies_and_preferences():
    lv = profile.resolve({"sleep_onset": "sometimes", "morning_hunger": "not_hungry", "dont_eat": ["pork"]},
                         None, STUDENT, goal=None, known_goals=GOALS, avoid_recipes=["a", "b"])
    keys = {"id", "kind", "text", "why", "grade", "goal", "pmids", "because", "lever"}
    assert all(set(a) == keys for a in lv.applied) and lv.avoid_recipes == frozenset({"a", "b"})
    strategy = next(a for a in lv.applied if a["id"] == "no_evening_caffeine")
    assert (strategy["kind"], strategy["grade"], strategy["goal"], strategy["pmids"]) == \
        ("strategy", "B", "sleep_support", ["36870101", "24235903"])
    assert strategy["because"] == {"question": "sleep_onset", "answer": "sometimes"}
    assert strategy["lever"] == {"type": "no_caffeine", "meal": "dinner"}
    light = next(a for a in lv.applied if a["id"] == "light_breakfast")
    assert (light["why"], light["grade"], light["goal"], light["pmids"]) == ("You said you're not hungry in the morning.", None, None, [])
    foods = next(a for a in lv.applied if a["id"] == "foods_not_eaten")
    assert foods["why"] is None and foods["because"] == {"question": "dont_eat", "answer": ["pork"]}
    order = [a["id"] for a in lv.applied]
    assert order.index("no_evening_caffeine") < order.index("light_breakfast")      # strategies first, as in the file


def test_levers_never_loosen_each_other():
    acc = {"meal_carb_share": {"dinner": 0.5}, "breakfast_energy_min": 0.3, "breakfast_energy_max": 0.2,
           "protein_g_per_kg": 1.8}
    profile._fold({"type": "meal_carb_share", "meal": "dinner", "min": 0.4}, {}, acc)
    profile._fold({"type": "meal_carb_share", "meal": "lunch", "min": 0.4}, {}, acc)
    profile._fold({"type": "meal_energy_share", "meal": "breakfast", "min": 0.25}, {}, acc)
    profile._fold({"type": "meal_energy_share", "meal": "breakfast", "max": 0.25}, {}, acc)
    profile._fold({"type": "protein_target", "g_per_kg": 1.6}, {}, acc)
    assert acc == {"meal_carb_share": {"dinner": 0.5, "lunch": 0.4}, "breakfast_energy_min": 0.3,
                   "breakfast_energy_max": 0.2, "protein_g_per_kg": 1.8}


def test_validation_rejects_levers_without_what_they_need(engine):
    data = profile.load_strategies()
    goals = set(engine.scorer.positive)
    ids = [s["id"] for s in data["strategies"]]
    for sid, lever in (("evening_carbs", {"type": "meal_carb_share", "meal": "dinner"}),
                       ("evening_carbs", {"type": "meal_carb_share", "min": 0.4}),
                       ("big_breakfast", {"type": "meal_energy_share", "meal": "lunch", "min": 0.3}),
                       ("big_breakfast", {"type": "meal_energy_share", "meal": "breakfast"}),
                       ("protein_target", {"type": "protein_target"}),
                       ("protein_breakfast", {"type": "meal_protein", "meal": "dinner", "g_per_kg": 0.25}),
                       ("no_evening_caffeine", {"type": "no_caffeine"}),
                       ("foods_not_eaten", {"type": "exclude_tags"}),
                       ("cook_time", {"type": "max_minutes", "from": "batch_ok"})):
        with pytest.raises(ValueError):
            profile.validate_strategies(_with(data, ids.index(sid), lever=lever), goals)
