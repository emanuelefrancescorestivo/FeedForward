"""EU register of health claims: parsing, mapping, merge policy, engine effects."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from feedforward.data.ingest.eu_claims import (
    build_edges, load_rules, map_claim, parse_register,
)
from feedforward.engine import build_engine
from feedforward.engine.build import load_goal_edges

DATA = Path(__file__).resolve().parent.parent / "feedforward" / "data"


def _item(code, substance, status, claim, relationship="", reason="", ctype="HCLBT_13_1",
          opinion="2009;7(9):1215"):
    """One register entry in the portal's entity-attribute-value shape."""
    def v(ident, value, children=()):
        return {"valueIdentifier": ident, "value": value, "childrenValues": list(children)}
    return v("policyItemObject", None, [
        v("policyItemCode", code),
        v("hcCharacteristicWrapper", None, [
            v("hcNutSubFoodCat", substance), v("hcClaimStatus", status),
            v("hcClaimType", ctype)]),
        v("hcClaimWrapper", None, [
            v("hcClaim", claim), v("hcHealthRelationship", relationship),
            v("hcReasonsForNonAuth", reason)]),
        v("hcEfsaOpinionReferenceWrapper", None, [
            v("hcEfsaOpinionReferenceMap", None, [v("hcEfsaQuestionNbr", opinion)])]),
    ])


@pytest.fixture(scope="module")
def mini_register():
    return [
        _item("POL-1", "Iron", "HCCS_AUTHORISED", "Iron contributes to normal cognitive function"),
        _item("POL-2", "Vitamin C", "HCCS_AUTHORISED", "Vitamin C increases iron absorption"),
        _item("POL-3", "Vitamin E", "HCCS_NON_AUTHORISED", "",
              "maintenance of normal cardiac function", "HC_RR_132"),
        _item("POL-4", "Magnesium", "HCCS_NON_AUTHORISED", "",
              "Resistance to mental stress", "HC_RR_132"),
        _item("POL-5", "Zinc", "HCCS_NON_AUTHORISED", "", "energy", "HC_RR_134"),
        _item("POL-6", "Calcium", "HCCS_AUTHORISED", "Calcium is needed for the maintenance of normal teeth"),
        _item("POL-7", "Guar Gum", "HCCS_AUTHORISED",
              "Guar gum contributes to the maintenance of normal blood cholesterol levels"),
        _item("POL-8", "Foods with a low or reduced content of sodium", "HCCS_AUTHORISED",
              "Reducing consumption of sodium contributes to the maintenance of normal blood pressure"),
        _item("POL-9", "Iron", "HCCS_NON_AUTHORISED", "", "maintenance of normal cognitive function",
              "HC_RR_132"),
    ]


def test_parse_flattens_the_register(mini_register):
    claims = parse_register(mini_register)
    assert [c.claim_id for c in claims][:2] == ["POL-1", "POL-2"]
    assert claims[0].status == "authorised" and claims[0].claim_type == "art_13_1"
    assert claims[2].rejection_reason == "HC_RR_132"
    assert claims[0].efsa_opinion == "2009;7(9):1215"


def test_mapping_and_edges(mini_register):
    rules = load_rules()
    claims = [map_claim(c, rules) for c in parse_register(mini_register)]
    by_id = {c.claim_id: c for c in claims}
    assert by_id["POL-1"].goals == ["cognitive_function"]
    assert by_id["POL-2"].edge_type == "enhancer"
    assert by_id["POL-6"].mapping == "no_goal"                  # teeth
    assert by_id["POL-7"].mapping == "unmapped_substance"       # guar gum
    assert by_id["POL-8"].nutrients == ["sodium"] and by_id["POL-8"].edge_type == "negative"

    result = build_edges(claims, rules)
    edges = {(e["nutrient"], e["goal"]): e for e in result["goal_edges"]}
    assert edges[("iron", "cognitive_function")]["evidence_grade"] == "A"
    assert edges[("iron", "cognitive_function")]["citations"] == ["EFSA Journal 2009;7(9):1215"]
    assert edges[("vitamin-c", "iron_support")]["type"] == "enhancer"
    rejected = {(r["nutrient"], r["goal"]) for r in result["rejected"]}
    assert ("vitamin-e", "heart_health") in rejected
    assert ("magnesium", "stress_resilience") in rejected
    # An authorised claim for the same pair wins over a rejected one.
    assert ("iron", "cognitive_function") not in rejected
    # HC_RR_134 ("not sufficiently defined") does not demote.
    assert not any(r["nutrient"] == "zinc" for r in result["rejected"])
    assert "Guar Gum" in result["report"]["unmapped_substances"]


def test_every_shipped_authorised_claim_is_accounted_for():
    """No authorised claim for a tracked nutrient may fall through the rules unseen."""
    data = json.loads((DATA / "eu_health_claims.json").read_text(encoding="utf-8"))
    assert data["provenance"]["retrieved_at"]
    authorised = [c for c in data["claims"] if c["status"] == "authorised"]
    assert len(authorised) >= 250
    assert not [c for c in authorised if c["mapping"] == "unmatched_wording"]
    mapped = [c for c in authorised if c["mapping"] == "mapped"]
    assert len(mapped) >= 130


@pytest.fixture(scope="module")
def edges():
    return {(e["nutrient"], e["goal"]): e for e in load_goal_edges()}


def test_merge_policy_on_shipped_data(edges):
    # Rejected by EFSA, no authorised claim: kept for the record, never a route.
    assert edges[("vitamin-e", "heart_health")]["type"] == "rejected"
    assert edges[("magnesium", "blood_pressure_support")]["evidence_source"] == "eu_rejected"
    # Authorised: grade A, EU wording, EFSA citation.
    k = edges[("potassium", "blood_pressure_support")]
    assert k["evidence_grade"] == "A" and k["eu_claim"]
    assert "Potassium contributes to the maintenance of normal blood pressure" in k["explanation"]
    assert any(c.startswith("EFSA Journal") for c in k["citations"])
    # The vitamin C -> iron enhancer is now an authorised claim.
    vc = edges[("vitamin-c", "iron_support")]
    assert vc["type"] == "enhancer" and vc["evidence_grade"] == "A"
    # Scraped micronutrient edge with no EU claim: downgraded, kept.
    assert edges[("vitamin-a", "digestive_health")]["evidence_grade"] == "D"
    # Curated edge with no claim either way keeps its grade, not phrased as a claim.
    sleep = edges[("magnesium", "sleep_support")]
    assert sleep["eu_claim"] is False and "evidence_grade" not in sleep
    # Curated grade-A association survives a narrower rejected claim, with the note.
    carbs = edges[("carbohydrates", "endurance_support")]
    assert carbs.get("type", "positive") == "positive" and "eu_rejected_claim" in carbs
    # Negative edges gain the EU wording but stay negative.
    sodium = edges[("sodium", "blood_pressure_support")]
    assert sodium["type"] == "negative" and sodium["evidence_source"] == "eu_authorised"


def test_b_vitamins_now_route_to_energy(edges):
    for nutrient in ("thiamin", "riboflavin", "niacin", "vitamin-b6", "vitamin-b12",
                     "pantothenic-acid", "folate"):
        assert edges[(nutrient, "energy_metabolism")]["evidence_source"] == "eu_authorised"


@pytest.fixture(scope="module")
def engine():
    return build_engine()


def test_rejected_pairs_are_not_scored(engine):
    heart = {n for n, _a, _g in engine.scorer.positive["heart_health"]}
    assert "vitamin-e" not in heart
    assert "epa-dha" in heart


def test_explanations_flag_authorised_wording(engine):
    rec = engine.foods_for_goal("healthy_blood", k=1)[0]
    exp = rec.explanation
    assert exp.eu_claim and exp.evidence_source == "eu_authorised"
    assert "contributes to" in exp.note
    assert any(c["eu_claim"] for c in exp.contributions)


def test_thyroid_is_led_by_iodine_sources(engine):
    top = engine.foods_for_goal("thyroid_support", k=5)
    assert all(r.explanation.contributions[0]["nutrient"] in ("iodine", "selenium") for r in top)
    assert any(r.explanation.contributions[0]["nutrient"] == "iodine" for r in top)


def test_formulated_drinks_are_not_recommended_for_energy(engine):
    names = [r.food_name.lower() for r in engine.foods_for_goal("energy_metabolism", k=30)]
    assert not any("vitamin water" in n or "drink, powder" in n or "energy drink" in n for n in names)


def test_database_keeps_eu_grades_and_efsa_citations(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'eu.db'}"
    monkeypatch.setenv("FEEDFORWARD_DATABASE_URL", url)
    from feedforward.db.models import Base
    from feedforward.db.repository import corpus_as_records, replace_corpus
    from feedforward.db.session import get_engine, reset_engine, session_scope
    reset_engine()
    get_engine(url, force=True)
    Base.metadata.create_all(get_engine())
    edge = dict(next(e for e in load_goal_edges()
                     if e["nutrient"] == "iron" and e["goal"] == "healthy_blood"))
    with session_scope() as s:
        replace_corpus(s, foods=[], edges=[edge],
                       goals=[{"id": "healthy_blood", "label": "Blood", "system": "x",
                               "description": "", "icd10_refs": []}],
                       nutrients={"iron": ("Iron", "mg")}, interactions=[])
    _foods, stored = corpus_as_records()
    assert stored[0]["evidence_grade"] == "A" and stored[0]["eu_claim"]
    assert any(c.startswith("EFSA Journal") for c in stored[0]["citations"])
    reset_engine()
