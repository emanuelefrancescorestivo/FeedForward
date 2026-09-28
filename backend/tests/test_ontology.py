"""Nutrient ontology, unit normalisation, value qualifiers and provenance storage."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from feedforward.ontology import nutrients as N
from feedforward.ontology.units import (
    UnitError, canonical_unit, convert, physically_possible,
)
from feedforward.ontology.values import EXACT, LESS_THAN, MISSING, TRACE, parse_value

DATA = Path(__file__).resolve().parent.parent / "feedforward" / "data"
BACKEND = Path(__file__).resolve().parent.parent


# --- ontology ---------------------------------------------------------------

def test_ontology_loads_without_ambiguous_aliases():
    aliases, codes = N._indexes()  # raises on an alias shared by two nutrients
    assert len(N.all_nutrients()) == 36
    assert aliases["ferro"] == "iron"
    assert aliases["tiamina"] == "thiamin"
    assert codes[("infoods", "tocpha")] == "vitamin-e"


def test_usda_ids_match_the_verified_mapping():
    # Frozen copy of the ids confirmed against nutrient.csv in usda_bulk.py.
    # Editing nutrients.json must not silently move a USDA column.
    direct = N.usda_direct_map()
    verified = {
        "1003": "proteins", "1004": "fat", "1005": "carbohydrates",
        "1079": "fiber", "1258": "saturated-fat", "1093": "sodium",
        "1087": "calcium", "1089": "iron", "1090": "magnesium",
        "1091": "phosphorus", "1092": "potassium", "1095": "zinc",
        "1098": "copper", "1101": "manganese", "1103": "selenium",
        "1162": "vitamin-c", "1106": "vitamin-a", "1109": "vitamin-e",
        "1185": "vitamin-k", "1114": "vitamin-d", "1178": "vitamin-b12",
        "1165": "thiamin", "1166": "riboflavin", "1167": "niacin",
        "1175": "vitamin-b6", "1170": "pantothenic-acid", "1180": "choline",
        "1100": "iodine", "1404": "ala",
    }
    assert {k: direct[k] for k in verified} == verified
    # Published under several ids: first present wins, never summed.
    preferred = N.usda_preferred()
    assert preferred["energy-kcal"] == ("1008", "2048", "2047")
    assert preferred["sugars"] == ("2000", "1063")
    assert preferred["folate"] == ("1190", "1177")
    assert N.usda_sums()["epa-dha"] == ("1278", "1272")
    # A sum's components are not codes: 1404 identifies ALA, not omega-3.
    assert N.resolve(code="1404", source="usda").nutrient_id == "ala"


def test_engine_meta_comes_from_ontology():
    from feedforward.engine.build import NUTRIENT_META
    assert NUTRIENT_META == N.display_meta()
    assert NUTRIENT_META["iron"] == ("Iron", "mg")
    assert NUTRIENT_META["selenium"][1] == "µg"


@pytest.mark.parametrize("label,expected,unit", [
    ("Fer (mg/100 g)", "iron", "mg"),
    ("Vitamine C (mg/100 g)", "vitamin-c", "mg"),
    ("Vitamine B9 ou Folates totaux (µg/100 g)", "folate", "µg"),
    ("Energie, Règlement UE N° 1169/2011 (kJ/100 g)", "energy-kcal", "kj"),
    ("AG saturés (g/100 g)", "saturated-fat", "g"),
    ("Vitamina D (μg)", "vitamin-d", "µg"),  # Greek mu
    ("Magnesio (mg)", "magnesium", "mg"),
    ("Fibra alimentare totale", None, None),
    ("Vitamin C, total ascorbic acid", "vitamin-c", None),
    ("Total lipid (fat)", "fat", None),
    ("Energy, kcal", "energy-kcal", "kcal"),
])
def test_resolve_labels(label, expected, unit):
    got = N.resolve(label)
    if expected is None:
        assert got is None
    else:
        assert got == N.Resolved(expected, unit)


def test_retinol_is_not_vitamin_a():
    # Retinol is one input to RAE; mapping it to vitamin-a would drop carotenoids.
    assert N.resolve("Rétinol (µg/100 g)") is None
    assert N.resolve("Beta-Carotène (µg/100 g)") is None


def test_resolve_codes():
    assert N.resolve(code="FE", source="infoods").nutrient_id == "iron"
    assert N.resolve(code="1089", source="usda").nutrient_id == "iron"
    assert N.resolve(code="vitamin-b9", source="off").nutrient_id == "folate"
    assert N.resolve(code="9999", source="usda") is None
    with pytest.raises(ValueError):
        N.resolve(code="FE")


# --- units ------------------------------------------------------------------

def test_micro_spellings_are_one_unit():
    assert canonical_unit("µg") == canonical_unit("μg") == canonical_unit("mcg") \
        == canonical_unit("ug") == canonical_unit("µg/100 g") == "µg"


def test_mass_and_energy_conversions():
    assert convert(0.0027, "g", "mg") == pytest.approx(2.7)
    assert convert(2.7, "mg", "µg") == pytest.approx(2700)
    assert convert(418.4, "kJ", "kcal") == pytest.approx(100)
    assert convert(400, "IU", "µg", nutrient="vitamin-d") == pytest.approx(10)


def test_form_dependent_iu_is_refused():
    with pytest.raises(UnitError):
        convert(1000, "IU", "µg", nutrient="vitamin-a")
    with pytest.raises(UnitError):
        convert(10, "IU", "mg", nutrient="vitamin-e")
    with pytest.raises(UnitError):
        convert(1, "g", "kcal")
    with pytest.raises(UnitError):
        canonical_unit("cups")


def test_physical_plausibility():
    assert physically_possible(99, "g")
    assert not physically_possible(1440, "g")
    assert physically_possible(40000, "mg")
    assert not physically_possible(1587, "kcal")
    assert physically_possible(3000, "kJ")
    assert not physically_possible(-1, "mg")


# --- reported values --------------------------------------------------------

@pytest.mark.parametrize("raw,amount,qualifier", [
    ("12,5", 12.5, EXACT),
    ("0.3", 0.3, EXACT),
    (4, 4.0, EXACT),
    ("< 0,5", 0.5, LESS_THAN),
    ("<0.05", 0.05, LESS_THAN),
    ("traces", None, TRACE),
    ("Tr", None, TRACE),
    ("tracce", None, TRACE),
    ("-", None, MISSING),
    ("", None, MISSING),
    (None, None, MISSING),
    (float("nan"), None, MISSING),
])
def test_parse_value(raw, amount, qualifier):
    value = parse_value(raw)
    assert value.qualifier == qualifier
    if amount is None:
        assert value.amount is None
    else:
        assert math.isclose(value.amount, amount)


def test_non_exact_values_never_feed_the_engine():
    assert parse_value("< 0,5").engine_amount == 0.0
    assert parse_value("traces").engine_amount == 0.0
    assert parse_value("2,7").engine_amount == 2.7
    with pytest.raises(ValueError):
        parse_value("about 3")


# --- OpenFoodFacts units ----------------------------------------------------

def test_off_product_is_converted_from_grams():
    from feedforward.data.ingest.openfoodfacts import product_to_record
    rec = product_to_record({
        "code": "123", "product_name": "Amandes",
        "nutriments": {"energy-kcal_100g": 620, "proteins_100g": 24.5,
                       "iron_100g": 0.00333, "vitamin-a_100g": 0.00012,
                       "sodium_100g": 1440},
    })
    assert rec["nutrients"]["iron"] == pytest.approx(3.33)
    assert rec["nutrients"]["vitamin-a"] == pytest.approx(120)
    assert rec["nutrients"]["proteins"] == 24.5
    assert "sodium" not in rec["nutrients"]
    assert rec["_impossible"] == {"sodium": 1440}
    assert rec["_units"] == "canonical"


def test_off_normalisation_is_idempotent():
    from feedforward.data.ingest.openfoodfacts import normalize_record_units
    legacy = {"id": "1", "name": "x", "nutrients": {"iron": 0.0036, "energy-kcal": 50}}
    once = normalize_record_units(legacy)
    twice = normalize_record_units(once)
    assert once["nutrients"]["iron"] == pytest.approx(3.6)
    assert twice == once


def test_shipped_off_file_is_canonical_and_salt_matches_sodium():
    """
    Independent check of the gram→mg fix: EU labelling defines salt as
    sodium × 2.5, and OFF stores both. If sodium were still in grams the
    ratio would be ~2500, not 2.5.
    """
    records = json.loads((DATA / "foods.json").read_text(encoding="utf-8"))
    assert all(r.get("_units") == "canonical" for r in records)
    ratios = [r["nutrients"]["salt"] / (r["nutrients"]["sodium"] / 1000)
              for r in records
              if r["nutrients"].get("salt") and r["nutrients"].get("sodium")]
    assert len(ratios) > 1000
    close = sum(1 for x in ratios if 2.4 <= x <= 2.6)
    assert close / len(ratios) > 0.9


def test_off_micronutrients_now_pass_the_usda_gate():
    from feedforward.engine.build import load_food_records
    off = [r for r in load_food_records() if r.get("_source_kind") == "openfoodfacts"]
    kept_iron = sum(1 for r in off if "iron" in r["nutrients"])
    rejected_iron = sum(1 for r in off if "iron" in r.get("_rejected", {}))
    assert kept_iron > 100
    assert rejected_iron < kept_iron / 5


# --- database provenance ----------------------------------------------------

def test_seed_stores_provenance_aliases_and_qualifiers(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ff.db'}"
    monkeypatch.setenv("FEEDFORWARD_DATABASE_URL", url)
    from sqlalchemy import select
    from feedforward.db.models import Base, FoodNutrientRow, FoodRow, NutrientAliasRow, NutrientRow
    from feedforward.db.repository import corpus_as_records, replace_corpus
    from feedforward.db.session import get_engine, reset_engine, session_scope

    reset_engine()
    get_engine(url, force=True)
    Base.metadata.create_all(get_engine())
    foods = [{
        "id": "c-1", "name": "Lentilles, crues", "category": "Légumineuses",
        "nutrients": {"iron": 6.5, "proteins": 24},
        "_qualified": {"vitamin-c": [0.5, "less_than"], "vitamin-d": [None, "trace"]},
        "_original_units": {"iron": [0.0065, "g"]},
        "_names": {"fr": "Lentilles, crues", "it": "Lenticchie, crude"},
        "_name_lang": "fr", "_source_kind": "ciqual", "_source_id": "ciqual-2020",
        "_micronutrient_trusted": True, "_is_animal": False,
    }]
    with session_scope() as s:
        replace_corpus(
            s, foods=foods, edges=[], goals=[], interactions=[],
            nutrients={k: N.display_meta()[k] for k in
                       ("iron", "proteins", "vitamin-c", "vitamin-d")},
            sources=[{"id": "ciqual-2020", "kind": "ciqual", "name": "CIQUAL",
                      "version": "2020", "licence": "Licence Ouverte 2.0",
                      "url": None, "country": "FR"}],
            ontology=N.all_nutrients(),
        )
    with session_scope() as s:
        food = s.get(FoodRow, "c-1")
        assert food.source_id == "ciqual-2020"
        assert {n.lang: n.name for n in food.names}["it"] == "Lenticchie, crude"
        iron = s.get(FoodNutrientRow, ("c-1", "iron"))
        assert (iron.original_amount, iron.original_unit) == (0.0065, "g")
        vit_c = s.get(FoodNutrientRow, ("c-1", "vitamin-c"))
        assert (vit_c.value_qualifier, vit_c.amount_per_100g) == ("less_than", 0.5)
        assert s.get(NutrientRow, "iron").infoods_tag == "FE"
        ferro = s.scalar(select(NutrientAliasRow).where(NutrientAliasRow.alias_norm == "ferro"))
        assert ferro.nutrient_id == "iron"
        # Only nutrients present in the table get aliases (FK integrity).
        assert s.scalar(select(NutrientAliasRow).where(
            NutrientAliasRow.nutrient_id == "zinc")) is None

    records, _ = corpus_as_records()
    assert records[0]["nutrients"] == {"iron": 6.5, "proteins": 24}
    assert sorted(records[0]["_below_detection"]) == ["vitamin-c", "vitamin-d"]
    reset_engine()


def test_alembic_upgrade_downgrade_roundtrip(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    url = f"sqlite:///{tmp_path / 'mig.db'}"
    monkeypatch.setenv("FEEDFORWARD_DATABASE_URL", url)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"sources", "nutrient_aliases", "food_names", "food_concepts"} <= tables
    command.downgrade(cfg, "001")
    assert "sources" not in set(inspect(create_engine(url)).get_table_names())
    command.upgrade(cfg, "head")
