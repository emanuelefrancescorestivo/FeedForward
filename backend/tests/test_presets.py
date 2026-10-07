"""Presets: meals logged in one tap as an estimate (the CROUS lunch), counted like any other entry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from feedforward.api.main import app
from feedforward.engine import diary, load_engine
from feedforward.engine.needs import Profile
from feedforward.engine.presets import load_presets, preset_nutrients

STUDENT = Profile(21, "male", 70, 178, "moderate")
INGREDIENTS = {i["id"]: i for i in json.loads(
    (Path(__file__).resolve().parents[1] / "feedforward" / "data" / "ingredients.json").read_text(encoding="utf-8"))["ingredients"]}


@pytest.fixture(scope="module")
def engine():
    return load_engine()


def test_crous_meal_is_a_plausible_estimate(engine):
    crous = load_presets()["crous-meal"]
    assert crous.estimate is True
    assert 500 <= preset_nutrients(engine, crous)["energy-kcal"] <= 850


def test_every_preset_ingredient_has_a_food(engine):
    for preset in load_presets().values():
        for ingredient, grams in preset.items:
            assert ingredient in INGREDIENTS, ingredient
            assert f"ciqual-{INGREDIENTS[ingredient]['ciqual']}" in engine.food_by_id, ingredient
            assert grams > 0


def test_a_preset_counts_in_the_day(engine):
    kcal = preset_nutrients(engine, load_presets()["crous-meal"])["energy-kcal"]
    entries = diary.entries_from([{"kind": "preset", "id": "crous-meal", "meal": "lunch", "servings": 1.5}])
    total = diary.day_summary(engine, STUDENT, entries, goal=None)["totals"]["kcal"]
    assert abs(total - 1.5 * kcal) <= 1


def test_unknown_kinds_are_refused():
    with pytest.raises(ValueError):
        diary.entries_from([{"kind": "presets", "id": "crous-meal", "meal": "lunch"}])


def test_presets_endpoint():
    with TestClient(app) as client:
        body = client.get("/diary/presets").json()
    crous = next(p for p in body if p["id"] == "crous-meal")
    assert crous["kind"] == "preset" and crous["estimate"] is True and crous["detail"] == "main + 2 sides"
    assert 500 <= crous["kcal"] <= 850 and crous["price_eur"] == 1.0
