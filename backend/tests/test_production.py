"""Production-path tests: database, citation integrity, ingest gates, coverage."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from feedforward.engine import taxonomy
from feedforward.engine.analytics import coverage_report
from feedforward.engine.bioavailability import effective_absorption, interaction_count
from feedforward.engine.build import load_food_records, load_goal_edges, _enrich_food
from feedforward.engine.evidence import CURATED, grade_for
from feedforward.engine.schema import EvidenceGrade, Food
from feedforward.data.ingest.openfoodfacts import nova_group, passes_nova_filter
from feedforward.data.ingest.sanity import check_micronutrient, ranges_from_trusted, split_off_nutrients

DATA = Path(__file__).resolve().parent.parent / "feedforward" / "data"
PMID = re.compile(r"PMID:(\d+)")


def test_interaction_matrix_grew_and_flags_unsourced():
    assert interaction_count() >= 36
    data = json.loads((DATA / "interactions.json").read_text(encoding="utf-8"))
    for inter in data["interactions"]:
        cites = inter.get("citations") or []
        for cite in cites:
            assert cite.startswith("PMID:") and cite[5:].isdigit(), cite
        if not cites:
            assert inter.get("low_confidence") is True


def test_citation_integrity_across_sources():
    """Every PMID we ship is well-formed. This does not prove the paper matches the claim."""
    blobs = [
        (DATA / "interactions.json").read_text(encoding="utf-8"),
        (DATA / "goal_edges_curated.json").read_text(encoding="utf-8"),
        (Path(__file__).resolve().parent.parent / "feedforward" / "engine" / "cautions.py").read_text(encoding="utf-8"),
        (Path(__file__).resolve().parent.parent / "feedforward" / "engine" / "evidence.py").read_text(encoding="utf-8"),
    ]
    pubmed = DATA / "evidence_pubmed.json"
    if pubmed.exists():
        blobs.append(pubmed.read_text(encoding="utf-8"))
    found = 0
    for blob in blobs:
        for match in PMID.finditer(blob):
            found += 1
            assert match.group(1).isdigit()
    assert found >= 40
    # The calcium/thyroid caution used to cite an iron paper. That PMID must not return.
    cautions = blobs[2]
    assert "PMID:2507711" not in cautions


def test_every_taxonomy_goal_has_a_positive_edge_or_a_declared_gap():
    """
    Since the EU layer, stress_resilience has no supported nutrient: EFSA
    rejected magnesium for 'resistance to mental stress' and no nutrient has
    an authorised stress claim. The gap is declared, not papered over.
    """
    edges = load_goal_edges()
    positive = {e["goal"] for e in edges if e.get("type", "positive") == "positive"}
    missing = [g.id for g in taxonomy.all_goals() if g.id not in positive]
    assert missing == ["stress_resilience"]
    # Without the EU layer every goal still had a route.
    legacy = {e["goal"] for e in load_goal_edges(eu=False)
              if e.get("type", "positive") == "positive"}
    assert all(g.id in legacy for g in taxonomy.all_goals())


def test_coverage_flags_orphan_and_hubs():
    report = coverage_report(load_goal_edges())
    assert report["goals_with_positive_edges"] == 26
    assert report["evidence_gaps"] == ["stress_resilience"]
    assert "sleep_support" in report["goals_without_eu_claim"]
    assert "immune_support" not in report["goals_without_eu_claim"]
    assert "energy" in report["orphan_goals"]
    assert report["nutrient_hubs"]
    assert "joint_health" not in {g["goal"] for g in report["thin_goals"]}
    assert "metabolic_support" not in {g["goal"] for g in report["thin_goals"]}


def test_curated_override_beats_pubmed_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "feedforward.engine.evidence._PUBMED_TABLE",
        tmp_path / "evidence_pubmed.json",
    )
    (tmp_path / "evidence_pubmed.json").write_text(json.dumps({
        "grades": {"iron|iron_support": {
            "grade": "D", "n_studies": 1, "n_rct_or_meta": 0,
            "citations": ["PMID:1"], "query": "should not win",
        }}
    }), encoding="utf-8")
    # lru not used; _pubmed_table reads the path each call.
    assessment = grade_for("iron", "iron_support")
    assert assessment.grade == EvidenceGrade.A
    assert assessment.source == "curated"
    assert ("iron", "iron_support") in CURATED


def test_heme_iron_calcium_competition():
    beef = Food("b", "Beef", "meat", {"iron": 3.0}, is_animal_source=True)
    yogurt = Food("y", "Yogurt", "dairy", {"calcium": 200})
    alone = effective_absorption("iron", beef, meal=[beef]).factor
    with_calcium = effective_absorption("iron", beef, meal=[beef, yogurt]).factor
    assert with_calcium < alone


def test_alcohol_reduces_folate_and_does_not_match_swine():
    greens = Food("g", "Spinach", "veg", {"folate": 194})
    beer = Food("beer", "Lager beer", "drink", {"carbohydrates": 3})
    beer.enhancer_props = {"alcohol"}
    alone = effective_absorption("folate", greens, meal=[greens]).factor
    with_beer = effective_absorption("folate", greens, meal=[greens, beer]).factor
    assert with_beer < alone
    swine = _enrich_food({"id": "s", "name": "Swine, pork, raw", "category": "meat",
                          "nutrients": {"proteins": 20}})
    lager = _enrich_food({"id": "l", "name": "Lager beer", "category": "drink",
                          "nutrients": {"carbohydrates": 3}})
    assert "alcohol" not in swine.enhancer_props
    assert "alcohol" in lager.enhancer_props


def test_off_micronutrient_gate_rejects_thousandfold_error():
    trusted = [{
        "name": "Spinach, raw", "category": "Vegetables",
        "_micronutrient_trusted": True,
        "nutrients": {"vitamin-c": 28, "iron": 2.7},
    }] * 8
    ranges = ranges_from_trusted(trusted)
    reason = check_micronutrient(
        "vitamin-c", 0.028, category="Vegetables", name="Spinach drink", ranges=ranges)
    assert reason
    ok = check_micronutrient(
        "vitamin-c", 20, category="Vegetables", name="Spinach drink", ranges=ranges)
    assert ok is None
    gated = split_off_nutrients({
        "id": "1", "name": "Spinach drink", "category": "Vegetables",
        "nutrients": {"proteins": 2, "vitamin-c": 0.028, "energy-kcal": 20},
    }, ranges)
    assert "vitamin-c" not in gated["nutrients"]
    assert "proteins" in gated["nutrients"]
    assert "vitamin-c" in gated["_rejected"]


def test_nova_filter_requires_an_integer_group():
    assert nova_group({"nova_group": "3"}) == 3
    assert nova_group({}) is None
    assert passes_nova_filter({}, {1}) is False
    assert passes_nova_filter({"nova_group": 1}, {1}) is True
    assert passes_nova_filter({}, None) is True


def test_usda_corpus_scale_and_trace_minerals():
    path = DATA / "usda_corpus.json"
    assert path.exists(), "USDA bulk corpus was not generated"
    records = json.loads(path.read_text(encoding="utf-8"))
    assert len(records) >= 5000
    with_copper = sum(1 for r in records if r["nutrients"].get("copper", 0) > 0)
    with_selenium = sum(1 for r in records if r["nutrients"].get("selenium", 0) > 0)
    assert with_copper >= 1000
    assert with_selenium >= 1000
    assert all(r.get("_micronutrient_trusted") is True for r in records[:20])


def test_database_roundtrip_and_auth(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ff.db'}"
    monkeypatch.setenv("FEEDFORWARD_DATABASE_URL", url)
    from feedforward.db.session import get_engine, reset_engine
    from feedforward.db.models import Base
    from feedforward.db.repository import (
        corpus_as_records, create_stored_user, delete_user, export_user,
        replace_corpus, update_profile, user_password_hash,
    )
    from feedforward.api.auth import hash_password, verify_password
    from feedforward.engine import build_engine

    reset_engine()
    get_engine(url, force=True)
    Base.metadata.create_all(get_engine())
    foods = [{
        "id": "t-1", "name": "Test lentils", "category": "Legumes",
        "nutrients": {"iron": 3.3, "proteins": 9, "energy-kcal": 116},
        "_is_animal": False, "_source_kind": "curated",
        "_micronutrient_trusted": True,
    }]
    edges = [{
        "nutrient": "iron", "goal": "iron_support", "weight": 0.9,
        "type": "positive", "explanation": "test",
        "citations": ["PMID:19260872"],
    }]
    from feedforward.db.session import session_scope
    with session_scope() as session:
        counts = replace_corpus(
            session, foods=foods, edges=edges,
            goals=[{"id": "iron_support", "label": "Iron", "system": "hematological",
                    "description": "", "icd10_refs": []}],
            nutrients={"iron": ("Iron", "mg"), "proteins": ("Protein", "g"),
                       "energy-kcal": ("Energy", "kcal")},
            interactions=[{
                "target": "non_heme_iron", "modifier": "phytate",
                "direction": "inhibits", "factor": 0.45,
                "mechanism": "binds iron", "evidence": "A",
                "citations": ["PMID:2670022"],
            }],
        )
    assert counts["foods"] == 1
    loaded, loaded_edges = corpus_as_records()
    assert loaded[0]["nutrients"]["iron"] == 3.3
    assert loaded_edges[0]["goal"] == "iron_support"
    engine = build_engine(source="db", whole_foods_only=False)
    # source=db ignores the json corpus even if whole_foods_only is false
    assert len(engine.foods) == 1
    recs = engine.foods_for_goal("iron_support", k=1)
    assert recs and recs[0].food_id == "t-1"

    user = create_stored_user("a@b.co", hash_password("secret"), "consumer")
    assert verify_password("secret", user_password_hash("a@b.co"))
    updated = update_profile("a@b.co", demographic="adult_male",
                             dietary_restrictions=["vegetarian"], tier="professional")
    assert updated.tier == "professional"
    assert updated.demographic == "adult_male"
    exported = export_user("A@B.co")
    assert exported["dietary_restrictions"] == ["vegetarian"]
    assert "password" not in json.dumps(exported)
    assert delete_user("a@b.co")
    assert export_user("a@b.co") is None
    reset_engine()


def test_auth_api_register_profile_delete():
    from fastapi.testclient import TestClient
    from feedforward.api.main import app
    from feedforward.db.models import Base
    from feedforward.db.session import get_engine, reset_engine

    reset_engine()
    Base.metadata.create_all(get_engine(force=True))
    with TestClient(app) as client:
        reg = client.post("/auth/register", json={
            "email": "person@example.com", "password": "longenough", "tier": "consumer",
        })
        assert reg.status_code == 200, reg.text
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/auth/me", headers=headers)
        assert me.status_code == 200
        patched = client.patch("/auth/profile", headers=headers, json={
            "demographic": "adult_female",
            "dietary_restrictions": ["vegan"],
            "tier": "professional",
        })
        assert patched.status_code == 200
        assert patched.json()["tier"] == "professional"
        pro = patched.json()["access_token"]
        exported = client.get("/auth/export", headers={"Authorization": f"Bearer {pro}"})
        assert exported.json()["user"]["dietary_restrictions"] == ["vegan"]
        gone = client.delete("/auth/me", headers={"Authorization": f"Bearer {pro}"})
        assert gone.status_code == 200
        again = client.get("/auth/me", headers={"Authorization": f"Bearer {pro}"})
        assert again.status_code == 401
    reset_engine()


def test_production_refuses_the_development_jwt_secret(monkeypatch):
    from feedforward.api.auth import assert_production_secret

    monkeypatch.setenv("FEEDFORWARD_ENV", "production")
    for bad in ("", "dev-secret-change-in-production", "replace-with-a-long-random-string", "short"):
        monkeypatch.setenv("FEEDFORWARD_SECRET", bad)
        with pytest.raises(RuntimeError):
            assert_production_secret()
    monkeypatch.setenv("FEEDFORWARD_SECRET", "x" * 48)
    assert_production_secret()
    monkeypatch.setenv("FEEDFORWARD_ENV", "test")
    monkeypatch.delenv("FEEDFORWARD_SECRET")
    assert_production_secret()          # development and tests keep the default
