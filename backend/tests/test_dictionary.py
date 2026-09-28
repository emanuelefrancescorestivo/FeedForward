"""Dictionary: every entry is built from a named source."""
from __future__ import annotations

import pytest

from feedforward import dictionary
from feedforward.dictionary.wikipedia import search_terms
from feedforward.engine import build_engine
from feedforward.engine.reference import Demographic


@pytest.fixture(scope="module")
def engine():
    return build_engine()


def test_nutrient_entry_is_sourced(engine):
    iron = dictionary.nutrient_entry(engine, "iron", Demographic.ADULT_FEMALE)
    assert iron["daily_need"]["amount"] == 18
    assert iron["upper_limit"] == {"amount": 45, "applies_to_food": True}
    texts = [c["text"] for c in iron["what_it_does"]]
    assert "Iron contributes to normal cognitive function" in texts      # EU wording, verbatim
    assert all(c["efsa"] for c in iron["what_it_does"])
    assert any(s["url"].startswith("https://ec.europa.eu") for s in iron["sources"])
    # Everyday sources are familiar foods only, one per family.
    assert iron["everyday_sources"]
    assert all(engine.food_by_id[s["food_id"]].familiarity >= 0.85 for s in iron["everyday_sources"])
    male = dictionary.nutrient_entry(engine, "iron", Demographic.ADULT_MALE)
    assert male["daily_need"]["amount"] == 8


def test_not_proven_lists_efsa_rejections(engine):
    vit_e = dictionary.nutrient_entry(engine, "vitamin-e")
    goals = {r["goal"] for r in vit_e["not_proven"]}
    assert {"heart_health", "immune_support"} <= goals
    assert [c["text"] for c in vit_e["what_it_does"]] == [
        "Vitamin E contributes to the protection of cells from oxidative stress"]


def test_glossary_terms_have_short_and_long_text():
    terms = dictionary.glossary()
    ids = {t["id"] for t in terms}
    assert {"daily-need", "portion", "eu-claim", "bioavailability"} <= ids
    for t in terms:
        assert t["short"] and t["long"] and t["kind"] in ("external", "methodology")
        if t["kind"] == "external":
            assert t["source"] and t["source"]["url"].startswith("https://")


@pytest.mark.parametrize("name,first", [
    ("Balsam-pear (bitter gourd), leafy tips, raw", "bitter gourd"),
    ("Emu, fan fillet, raw", "Emu"),
    ("Fish, tuna, yellowfin, fresh, cooked", "tuna"),
    ("Caribou, liver, raw (Alaska Native)", "Caribou"),
])
def test_wikipedia_search_terms(name, first):
    assert search_terms(name)[0] == first


def test_food_entry_offline_names_its_data_source(engine):
    food = next(f for f in engine.foods if f.name.startswith("Emu, fan fillet"))
    entry = dictionary.food_entry(engine, food.id, network=False)
    assert entry["data_source"]["name"].startswith("USDA FoodData Central")
    assert "Public domain" in entry["data_source"]["licence"]
    assert entry["everyday"] is False


def test_contributions_carry_both_edge_strengths(engine):
    exp = engine.foods_for_goal("energy_metabolism", k=1)[0].explanation
    c = exp.contributions[0]
    assert 0 < c["delivery_strength"] <= 1 and 0 < c["association"] <= 1
    assert c["strength"] == pytest.approx(c["delivery_strength"] * c["association"], abs=1e-3)
