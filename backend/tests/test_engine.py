"""
Test suite for the FeedForward scientific engine.

Covers the algorithmic core (the parts the university review flagged as
untested), the new bioavailability and evidence layers, and the recommender's
end-to-end behaviour. Run with:  pytest -q
"""
from __future__ import annotations

import math

import pytest

from feedforward.engine.graph import FeedForwardGraph
from feedforward.engine.algorithms import (dijkstra, reconstruct_path,
                                           cosine_similarity, k_shortest_paths,
                                           dijkstra_reverse)
from feedforward.engine.schema import Food, EvidenceGrade
from feedforward.engine.bioavailability import (absorption_factor,
                                                effective_absorption)
from feedforward.engine import evidence, build_engine, taxonomy


# ---------------------------------------------------------------------------
# Graph + Dijkstra (the 5-node toy graph the report references)
# ---------------------------------------------------------------------------
def _toy_graph() -> FeedForwardGraph:
    g = FeedForwardGraph()
    for n in ["A", "B", "C", "D", "E"]:
        g.add_node(n)
    g.add_edge("A", "B", 1.0)
    g.add_edge("B", "C", 2.0)
    g.add_edge("A", "C", 5.0)
    g.add_edge("C", "D", 1.0)
    g.add_edge("D", "E", 1.0)
    return g


def test_dijkstra_shortest_path():
    g = _toy_graph()
    dist, pred = dijkstra(g, "A")
    assert dist["C"] == 3.0                  # A->B->C beats A->C (5)
    assert reconstruct_path(pred, "A", "C") == ["A", "B", "C"]
    assert dist["E"] == 5.0                  # A->B->C->D->E


def test_dijkstra_unreachable():
    g = FeedForwardGraph()
    g.add_node("X"); g.add_node("Y")
    dist, _ = dijkstra(g, "X")
    assert dist["Y"] == math.inf


def test_reverse_dijkstra_matches_forward():
    """Reverse Dijkstra from a target must equal forward distance to it."""
    g = _toy_graph()
    fwd, _ = dijkstra(g, "A")
    rev, _ = dijkstra_reverse(g, "E")
    assert rev["A"] == fwd["E"] == 5.0


def test_cosine_similarity():
    a = {"iron": 3.0, "vitamin-c": 10.0}
    assert cosine_similarity(a, a) == pytest.approx(1.0)
    assert cosine_similarity(a, {"zinc": 5.0}) == 0.0
    assert cosine_similarity({}, a) == 0.0


def test_k_shortest_paths_returns_distinct():
    g = _toy_graph()
    paths = k_shortest_paths(g, "A", "C", 2)
    assert len(paths) >= 1
    assert paths[0][1] == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Bioavailability
# ---------------------------------------------------------------------------
def test_heme_vs_non_heme_iron():
    beef = Food("1", "Beef steak", "meat", {"iron": 3.0}, is_animal_source=True)
    lentils = Food("2", "Lentils", "legume", {"iron": 3.0}, is_animal_source=False)
    heme = absorption_factor("iron", beef).factor
    non_heme = absorption_factor("iron", lentils).factor
    assert heme > non_heme                    # heme iron absorbed better
    assert non_heme == pytest.approx(0.10)


def test_vitamin_c_boosts_non_heme_iron():
    lentils = Food("2", "Lentils", "legume", {"iron": 3.0}, is_animal_source=False)
    pepper = Food("3", "Red pepper", "veg", {"vitamin-c": 120.0},
                  contains_vitamin_c=True)
    alone = effective_absorption("iron", lentils).factor
    with_c = effective_absorption("iron", lentils, meal=[lentils, pepper]).factor
    assert with_c > alone                     # vitamin C enhances absorption


def test_fat_soluble_vitamin_needs_fat():
    """Fat's effect on fat-soluble vitamin absorption is a meal-level modifier."""
    # A retinol (animal) source so the target is vitamin-a, not beta_carotene.
    liver = Food("4", "Liver", "meat", {"vitamin-a": 100.0}, is_animal_source=True)
    oil = Food("5", "Olive oil", "fat", {"fat": 90.0}, contains_fat=True)
    dry = Food("6", "Rice cake", "grain", {"carbohydrates": 80.0})
    without_fat = effective_absorption("vitamin-a", liver, meal=[liver, dry]).factor
    with_fat = effective_absorption("vitamin-a", liver, meal=[liver, oil]).factor
    assert with_fat > without_fat


# ---------------------------------------------------------------------------
# Evidence grading
# ---------------------------------------------------------------------------
def test_curated_evidence_grades():
    a = evidence.grade_for("iron", "iron_support")
    assert a.grade == EvidenceGrade.A
    assert a.source == "curated"
    unknown = evidence.grade_for("iron", "nonexistent_goal")
    assert unknown.grade == EvidenceGrade.C   # conservative default


def test_evidence_multiplier_ordering():
    assert EvidenceGrade.A.multiplier > EvidenceGrade.B.multiplier
    assert EvidenceGrade.B.multiplier > EvidenceGrade.C.multiplier
    assert EvidenceGrade.C.multiplier > EvidenceGrade.D.multiplier


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------
def test_taxonomy_size_and_lookup():
    assert len(taxonomy.all_goals()) >= 25
    assert taxonomy.get_goal("sleep_support") is not None
    assert taxonomy.get_goal("does_not_exist") is None


# ---------------------------------------------------------------------------
# End-to-end recommender
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def engine():
    return build_engine(use_pubmed=False)


def test_recommend_returns_explained_results(engine):
    recs = engine.foods_for_goal("iron_support", k=5)
    assert len(recs) > 0
    top = recs[0]
    assert top.explanation is not None
    assert top.explanation.steps[-1].node_id == "iron_support"
    # score should be a valid 0-100 match
    assert 0 <= top.match <= 100


def test_constraints_filter(engine):
    veg = engine.foods_for_goal("iron_support", constraints=["vegetarian"], k=10)
    # No obviously-meat foods in a vegetarian result
    for r in veg:
        assert "beef" not in r.food_name.lower()


def test_explain_and_similar(engine):
    recs = engine.foods_for_goal("bone_health", k=1)
    fid = recs[0].food_id
    exp = engine.explain(fid, "bone_health")
    assert exp is not None and exp.goal == "bone_health"
    sims = engine.similar_foods(fid, k=3)
    assert len(sims) <= 3


# ---------------------------------------------------------------------------
# NEW SCIENTIFIC LAYERS: reference intakes, interactions, density, cautions
# ---------------------------------------------------------------------------
from feedforward.engine.reference import (percent_of_need, Demographic,
                                          is_limit_nutrient, percent_of_limit)
from feedforward.engine.bioavailability import (interaction_count,
                                                effective_absorption)
from feedforward.engine.density import density_breakdown, density_score
from feedforward.engine import cautions


def test_reference_intake_demographic_aware():
    # Same iron amount, different % of need by demographic
    male = percent_of_need("iron", 8.0, Demographic.ADULT_MALE)
    female = percent_of_need("iron", 8.0, Demographic.ADULT_FEMALE)
    assert male > female                       # men need less iron -> higher %
    assert percent_of_need("iron", 8.0, Demographic.ADULT_MALE) == 100.0


def test_limit_nutrients():
    assert is_limit_nutrient("sodium")
    assert not is_limit_nutrient("iron")
    assert percent_of_limit("sodium", 2300) == 100.0


def test_interaction_matrix_loaded():
    assert interaction_count() >= 15


def test_interaction_competing_effects():
    """Phytate inhibits and vitamin C enhances iron simultaneously."""
    lentils = Food("l", "Lentils", "legume", {"iron": 3.3}, is_animal_source=False)
    lentils.anti_nutrients = {"phytate"}
    pepper = Food("p", "Pepper", "veg", {"vitamin-c": 128}, contains_vitamin_c=True)
    # phytate alone -> below baseline
    inhibited = effective_absorption("iron", lentils, meal=[lentils]).factor
    assert inhibited < 0.10
    # adding vitamin C -> partially recovers
    recovered = effective_absorption("iron", lentils, meal=[lentils, pepper]).factor
    assert recovered > inhibited


def test_density_score_bounded_and_ordered():
    junk = Food("j", "Sugary drink", "drink",
                {"energy-kcal": 200, "sugars": 40})
    nutritious = Food("n", "Spinach", "veg",
                      {"energy-kcal": 23, "iron": 2.7, "vitamin-c": 28,
                       "vitamin-k": 483, "calcium": 99, "fiber": 2.2})
    assert 0 <= density_score(junk) <= 100
    assert 0 <= density_score(nutritious) <= 100
    assert density_score(nutritious) > density_score(junk)


def test_density_low_calorie_guard():
    """Near-zero-calorie foods shouldn't score absurdly high."""
    coffee = Food("c", "Black coffee", "drink",
                  {"energy-kcal": 2, "magnesium": 3})
    # Should not blow up to 100 due to division by tiny energy
    assert density_score(coffee) < 50


def test_cautions_framing_and_lookup():
    vit_k = cautions.cautions_for_nutrient("vitamin-k")
    assert len(vit_k) >= 1
    # Every caution must defer to a professional (never gives medical advice)
    for c in vit_k:
        assert "healthcare provider" in c.disposition.lower()
    kale = Food("k", "Kale", "veg", {"vitamin-k": 705})
    assert any(c.nutrient == "vitamin-k" for c in cautions.cautions_for_food(kale))


def test_whole_foods_have_real_micronutrients():
    """Regression guard: the curated corpus must have realistic values."""
    eng = build_engine(whole_foods_only=True)
    irons = [f.nutrients.get("iron", 0) for f in eng.foods]
    vitc = [f.nutrients.get("vitamin-c", 0) for f in eng.foods]
    assert max(irons) > 5      # e.g. pumpkin seeds ~8.8 mg
    assert max(vitc) > 50      # e.g. red pepper ~128 mg


def test_meal_analysis_absorbable_delivery():
    eng = build_engine(whole_foods_only=True)
    lentils = next(f for f in eng.foods if "Lentils" in f.name)
    pepper = next(f for f in eng.foods if "bell pepper" in f.name)
    solo = eng.analyze_meal([lentils.id])["minerals"]["iron"]
    combo = eng.analyze_meal([lentils.id, pepper.id])["minerals"]["iron"]
    # Vitamin C raises absorbable iron delivery
    assert combo["absorption_pct"] > solo["absorption_pct"]


# ---------------------------------------------------------------------------
# EXPANDED INTERACTION MATRIX (v1.2): new targets and modifiers
# ---------------------------------------------------------------------------
def test_expanded_interaction_matrix_size():
    assert interaction_count() >= 30


def test_copper_zinc_competition():
    """High zinc blocks copper absorption (metallothionein mechanism)."""
    # A copper source low in zinc, so zinc presence comes only from the added food.
    liver = Food("cu", "Copper source", "food", {"copper": 1.0, "zinc": 0.5})
    oysters = Food("zn", "Oysters", "seafood", {"zinc": 78}, is_animal_source=True)
    alone = effective_absorption("copper", liver, meal=[liver]).factor
    with_zinc = effective_absorption("copper", liver, meal=[liver, oysters]).factor
    assert with_zinc < alone


def test_vitamin_a_enhances_non_heme_iron():
    lentils = Food("fe", "Lentils", "legume", {"iron": 3.3}, is_animal_source=False)
    lentils.anti_nutrients = {"phytate"}
    carrot = Food("va", "Carrot", "veg", {"vitamin-a": 835})
    alone = effective_absorption("iron", lentils, meal=[lentils]).factor
    with_a = effective_absorption("iron", lentils, meal=[lentils, carrot]).factor
    assert with_a > alone


def test_expanded_reference_values():
    """New nutrients have reference values."""
    assert percent_of_need("copper", 0.9, Demographic.ADULT_MALE) == 100.0
    assert percent_of_need("selenium", 55, Demographic.ADULT_MALE) == 100.0
    assert percent_of_need("potassium", 3400, Demographic.ADULT_MALE) == 100.0
    assert percent_of_need("folate", 400, Demographic.ADULT_MALE) == 100.0


def test_expanded_whole_foods_corpus():
    eng = build_engine(whole_foods_only=True)
    assert len(eng.foods) >= 80
    # trace minerals now represented
    coppers = [f.nutrients.get("copper", 0) for f in eng.foods]
    seleniums = [f.nutrients.get("selenium", 0) for f in eng.foods]
    assert max(coppers) > 1        # e.g. cashews ~2.2 mg
    assert max(seleniums) > 100    # e.g. brazil nuts ~1917 µg


def test_no_malformed_citations():
    """Regression guard: every interaction citation is a well-formed PMID."""
    import json
    from pathlib import Path
    p = (Path(__file__).resolve().parent.parent / "feedforward" / "data"
         / "interactions.json")
    data = json.loads(p.read_text())
    for inter in data["interactions"]:
        for c in inter.get("citations", []):
            assert c.startswith("PMID:") and c[5:].isdigit(), f"bad citation {c}"
