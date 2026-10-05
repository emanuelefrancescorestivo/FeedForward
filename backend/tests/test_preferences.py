"""Planner preferences in the week planner: energy goal, protein, graph goal weights, hard filters."""
from __future__ import annotations

import dataclasses

import pytest

from feedforward.engine import load_engine
from feedforward.engine import profile
from feedforward.engine import week_planner as wp
from feedforward.engine.needs import Profile, resting_kcal

STUDENT = Profile(24, "male", 72, 178, "light")


@pytest.fixture(scope="module")
def engine():
    return load_engine()


def _composition(plan):
    return [{"meals": {m: d["meals"][m]["id"] for m in d["meals"]}, "snacks": [s["id"] for s in d["snacks"]]}
            for d in plan["days"]]


def _ids(plan):
    return {x["id"] for d in plan["days"] for x in list(d["meals"].values()) + d["snacks"]}


def _tags_of(ids):
    tags = {r.id: r.tags for r in wp._recipes(load_engine())}
    return set().union(*(tags[i] for i in ids))


def _tags_in(plan):
    return _tags_of(_ids(plan))


def _ctx(engine, **kw):
    return wp._context(engine, STUDENT, **{"goal": "cognitive_function", "chain": "lidl", "diet": None,
                                           "equipment": None, "pantry": None, "days": 7, **kw})


# --------------------------------------------------------------- the brief's tests
def test_no_answers_gives_todays_plan(engine):
    plain = wp.plan_week(engine, STUDENT, goal="cognitive_function", budget=50, chain="lidl")
    same = wp.plan_week(engine, STUDENT, goal="cognitive_function", budget=50, chain="lidl", answers=None, declined=None)
    assert _composition(plain) == _composition(same) and plain["total_cost"] == same["total_cost"]


def test_energy_goal_moves_the_target(engine):
    base = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl")["energy"]["target_per_day"]
    for goal, factor in (("deficit", 0.85), ("surplus", 1.10)):
        plan = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", answers={"energy_goal": goal})
        assert plan["energy"]["target_per_day"] == pytest.approx(base * factor, abs=2)
        assert plan["energy"]["in_band"]


def test_excluded_foods_never_appear(engine):                     # with Review Focus 3
    plan = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", pantry=["sardines"],
                        answers={"dont_eat": ["fish_seafood", "legumes", "spicy"]})
    assert plan["feasible"] and not _tags_in(plan) & {"fish_seafood", "legumes", "spicy"}


def test_cooking_time_and_not_for_me(engine):
    plan = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", answers={"cook_time": "20"},
                        avoid_recipes=["sardine-tartines"])
    times = [m["time_min"] for d in plan["days"] for m in d["meals"].values()]
    assert max(times) <= 20 and "sardine-tartines" not in _ids(plan)
    with pytest.raises(ValueError):
        wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", avoid_recipes=["nope"])


def test_answers_weight_the_graph_goals(engine):
    ctx = wp._context(engine, STUDENT, goal="cognitive_function", chain="lidl", diet=None, equipment=None,
                      pantry=None, days=7, answers={"sleep_onset": "often"})
    assert ctx.goal_of["magnesium"] in {"sleep_support", "cognitive_function"}
    assert ctx.assoc["magnesium"] >= 0.5 * dict((n, a) for n, a, _ in engine.scorer.positive["sleep_support"])["magnesium"]
    assert ctx.goal_of["epa-dha"] == "cognitive_function"


# --------------------------------------------------------------- the context, lever by lever
def test_no_answers_keep_todays_weights_and_evidence(engine):
    """A lone primary goal: alpha 1 x a = a, every weight set by that goal, the same evidence."""
    for answers in (None, {}):
        ctx = _ctx(engine, answers=answers)
        positive = engine.scorer.positive["cognitive_function"]
        assert ctx.assoc == {n: a for n, a, _g in positive}
        assert list(ctx.assoc) == [n for n, _a, _g in positive]          # same order: same tie-breaks
        assert set(ctx.goal_of.values()) == {"cognitive_function"} and set(ctx.goal_of) == set(ctx.assoc)
        assert ctx.levers == profile.Levers.none("cognitive_function")
        assert ctx.kcal_target == 7 * wp.energy_kcal(STUDENT) and ctx.scale == wp.portion_scale(STUDENT)
    assert _ctx(engine, goal=None).assoc == {} and _ctx(engine, goal=None).goal_of == {}


def test_an_answer_goal_adds_nutrients_at_half_weight(engine):
    ctx = _ctx(engine, answers={"training_days": "5+"})
    muscle = {n: a for n, a, _g in engine.scorer.positive["muscle_recovery"]}
    cognitive = {n: a for n, a, _g in engine.scorer.positive["cognitive_function"]}
    assert ctx.assoc["vitamin-d"] == pytest.approx(0.5 * muscle["vitamin-d"]) and ctx.goal_of["vitamin-d"] == "muscle_recovery"
    for n in set(muscle) | set(cognitive):
        assert ctx.assoc[n] == pytest.approx(max(cognitive.get(n, 0.0), 0.5 * muscle.get(n, 0.0)))
    # carbohydrates: 0.3 for the person's goal, 0.5 x 0.7 for training. The higher one sets the
    # weight, and the evidence shown is that of its edge.
    assert ctx.goal_of["carbohydrates"] == "muscle_recovery"
    for n in ("vitamin-d", "carbohydrates"):
        meta = engine.edge_meta[f"{n}->muscle_recovery"]
        assert ctx.evidence[n] == {"grade": meta["evidence"], "eu_claim": bool(meta.get("eu_claim"))}


def test_protein_target_raises_the_weekly_need(engine):
    plain = _ctx(engine)
    trained = _ctx(engine, answers={"training_days": "5+"})
    assert trained.weekly["proteins"] == pytest.approx(1.6 * 72 * 7, abs=0.5)
    assert plain.weekly["proteins"] < trained.weekly["proteins"]
    assert {n: v for n, v in trained.weekly.items() if n != "proteins"} == \
           {n: v for n, v in plain.weekly.items() if n != "proteins"}


def test_energy_never_below_resting(engine, monkeypatch):
    """No energy goal open today goes below resting energy (PAL >= 1.2), so force one that would."""
    monkeypatch.setitem(profile.ENERGY_FACTORS, "deficit", 0.5)
    ctx = _ctx(engine, answers={"energy_goal": "deficit"})
    assert ctx.kcal_target == pytest.approx(7 * resting_kcal(STUDENT)) and ctx.resting_kcal == resting_kcal(STUDENT)
    assert ctx.scale == wp.portion_scale(STUDENT, resting_kcal(STUDENT))


def test_batch_recipes_get_three_times_the_cooking_time(engine):
    quick = _ctx(engine, answers={"cook_time": "10"})
    batch = _ctx(engine, answers={"cook_time": "10", "batch_ok": "yes"})
    assert all(r.time_min <= 10 for r in quick.by_id.values())
    assert "lentil-bolognese" in batch.by_id                      # batch, 30 min: 3 x 10
    assert "lentil-vegetable-soup" not in batch.by_id             # batch, 35 min
    assert "egg-fried-rice" not in batch.by_id                    # 15 min, not a batch recipe


def test_no_caffeine_at_dinner(engine):
    sleepy = _ctx(engine, answers={"sleep_onset": "often"})
    awake = _ctx(engine, answers={"sleep_onset": "often"}, declined=["no_evening_caffeine"])
    chocolate = sleepy.by_id["snack-bread-chocolate"]
    assert "caffeine" in chocolate.tags
    as_dinner = dataclasses.replace(chocolate, meals=["dinner", "lunch"])
    assert not sleepy.allowed(as_dinner, "dinner") and sleepy.allowed(as_dinner, "lunch")
    assert awake.allowed(as_dinner, "dinner")
    assert not sleepy.allowed(sleepy.by_id["porridge-banana-walnut"], "dinner")     # not a dinner at all


def test_unknown_recipe_ids_are_named(engine):
    with pytest.raises(ValueError, match="nope"):
        _ctx(engine, avoid_recipes=["sardine-tartines", "nope"])
    with pytest.raises(ValueError):
        _ctx(engine, answers={"dont_eat": ["gluten"]})


def test_edits_swaps_and_minimum_budget_use_the_same_settings(engine):
    answers = {"dont_eat": ["fish_seafood"]}
    kw = dict(goal="cognitive_function", budget=50, chain="lidl")
    plan = wp.plan_week(engine, STUDENT, **kw, answers=answers)
    week = _composition(plan)
    assert wp.evaluate_week(engine, STUDENT, week, **kw, answers=answers)["total_cost"] == plan["total_cost"]
    rid = week[0]["meals"]["dinner"]
    with pytest.raises(ValueError, match=rid):
        wp.evaluate_week(engine, STUDENT, week, **kw, answers=answers, avoid_recipes=[rid])
    opts = wp.swap_options(engine, STUDENT, week, 2, "dinner", **kw, answers=answers)
    assert opts["options"] and not _tags_of({o["id"] for o in opts["options"]}) & {"fish_seafood"}
    poor = wp.plan_week(engine, STUDENT, goal=None, budget=15, chain="lidl", answers=answers)
    assert not poor["feasible"] and poor["reason"] == "budget"
    assert wp.plan_week(engine, STUDENT, goal=None, budget=poor["minimum_budget"], chain="lidl",
                        answers=answers)["feasible"]
