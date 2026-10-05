"""Planner preferences: the strategies file, its validation, and the food tags it relies on."""
from __future__ import annotations

import copy

import pytest

from feedforward.engine import load_engine
from feedforward.engine import profile
from feedforward.engine import week_planner as wp


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
