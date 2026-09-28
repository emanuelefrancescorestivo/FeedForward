"""
The FeedForward dictionary: nutrients, foods and terms, each entry built from
a named source so the user can check it.

  nutrients  EU authorised claim wording (what it does), claims EFSA did not
             accept, daily need and upper limit for the profile, everyday
             food sources computed from the corpus, links to reference pages
  foods      our data (portion, source dataset and licence) plus a Wikipedia
             summary with attribution (dictionary/wikipedia.py)
  terms      how FeedForward uses a word (data/glossary.json), with the
             external definition's source where there is one
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"

# Consumer fact sheets of the US NIH Office of Dietary Supplements.
_NIH = {
    "iron": "Iron", "calcium": "Calcium", "magnesium": "Magnesium", "zinc": "Zinc",
    "copper": "Copper", "selenium": "Selenium", "manganese": "Manganese",
    "phosphorus": "Phosphorus", "potassium": "Potassium", "iodine": "Iodine",
    "vitamin-a": "VitaminA", "vitamin-c": "VitaminC", "vitamin-d": "VitaminD",
    "vitamin-e": "VitaminE", "vitamin-k": "VitaminK", "vitamin-b12": "VitaminB12",
    "vitamin-b6": "VitaminB6", "folate": "Folate", "thiamin": "Thiamin",
    "riboflavin": "Riboflavin", "niacin": "Niacin", "pantothenic-acid": "PantothenicAcid",
    "biotin": "Biotin", "choline": "Choline", "omega-3-fat": "Omega3FattyAcids",
    "epa-dha": "Omega3FattyAcids", "ala": "Omega3FattyAcids",
}
EU_REGISTER = "https://ec.europa.eu/food/food-feed-portal/screen/health-claims/eu-register"
EFSA_DRV = "https://multimedia.efsa.europa.eu/drvs/index.htm"


@lru_cache(maxsize=1)
def _eu() -> tuple[dict, dict]:
    claims = json.loads((_DATA / "eu_health_claims.json").read_text(encoding="utf-8"))
    edges = json.loads((_DATA / "goal_edges_eu.json").read_text(encoding="utf-8"))
    return claims, edges


@lru_cache(maxsize=1)
def glossary() -> list[dict]:
    return json.loads((_DATA / "glossary.json").read_text(encoding="utf-8"))["terms"]


@lru_cache(maxsize=1)
def _sources() -> dict[str, dict]:
    data = json.loads((_DATA / "sources.json").read_text(encoding="utf-8"))
    return {s["id"]: s for s in data["sources"]}


def nutrient_index() -> list[dict]:
    from ..ontology.nutrients import all_nutrients
    return [{"id": n.id, "name": n.name("en"), "group": n.group} for n in all_nutrients()
            if n.group in ("vitamin", "mineral") or n.id in ("proteins", "fiber", "omega-3-fat",
                                                             "epa-dha", "ala", "carbohydrates")]


def nutrient_entry(rec, nutrient_id: str, demo=None) -> dict | None:
    from ..engine.reference import DEFAULT_DEMOGRAPHIC, UL_APPLIES_TO_FOOD, reference_value
    from ..ontology.nutrients import get
    definition = get(nutrient_id)
    if definition is None:
        return None
    demo = demo or DEFAULT_DEMOGRAPHIC
    claims_file, edges_file = _eu()
    what_it_does = []
    seen = set()
    for c in claims_file["claims"]:
        if c["status"] == "authorised" and nutrient_id in c["nutrients"] and c["claim"] not in seen:
            seen.add(c["claim"])
            what_it_does.append({"text": c["claim"], "goals": c["goals"],
                                 "efsa": c.get("efsa_opinion", ""), "claim_id": c["claim_id"]})
    not_proven = [{"goal": r["goal"], "relationships": r["relationships"], "reason": r["reason"]}
                  for r in edges_file["rejected"] if r["nutrient"] == nutrient_id]
    ref = reference_value(nutrient_id, demo)
    return {
        "id": definition.id, "names": definition.names, "unit": definition.unit,
        "group": definition.group, "note": definition.note,
        "daily_need": ({"amount": ref.rda_ai, "kind": ref.kind, "demographic": demo.value}
                       if ref else None),
        "upper_limit": ({"amount": ref.ul, "applies_to_food": nutrient_id in UL_APPLIES_TO_FOOD}
                        if ref and ref.ul else None),
        "what_it_does": what_it_does,
        "not_proven": not_proven,
        "everyday_sources": everyday_sources(rec, nutrient_id, demo),
        "sources": [
            {"label": "EU Register of authorised health claims", "url": EU_REGISTER},
            {"label": "EFSA Dietary Reference Values", "url": EFSA_DRV},
            *([{"label": "NIH Office of Dietary Supplements fact sheet",
                "url": f"https://ods.od.nih.gov/factsheets/{_NIH[nutrient_id]}-Consumer/"}]
              if nutrient_id in _NIH else []),
        ],
    }


def everyday_sources(rec, nutrient_id: str, demo=None, k: int = 6) -> list[dict]:
    """Familiar foods giving the most of a nutrient per portion (one per food family)."""
    from ..engine.recommender import food_family, is_excluded_food
    scorer = rec.scorer_for(demo)
    rows = []
    for food in rec.foods:
        if food.familiarity < 0.85 or nutrient_id not in food.nutrients or is_excluded_food(food):
            continue
        d = scorer.delivery(food, nutrient_id)
        if d is None or d.exceeds_ul:
            continue
        rows.append((d.percent_of_need, food, d))
    rows.sort(key=lambda r: -r[0])
    out, families = [], set()
    for pct, food, d in rows:
        fam = food_family(food.name)
        if fam in families:
            continue
        families.add(fam)
        out.append({"food_id": food.id, "name": food.name, "category": food.category,
                    "portion_g": d.portion_g, "portion_group": d.portion_group,
                    "percent_of_need": pct})
        if len(out) >= k:
            break
    return out


def food_entry(rec, food_id: str, *, network: bool = True) -> dict | None:
    from ..engine.portions import portion_for
    from .wikipedia import lookup
    food = rec.food_by_id.get(food_id)
    if food is None:
        return None
    source = _sources().get(food.source_id or "", {})
    portion = portion_for(food)
    return {
        "food_id": food.id, "name": food.name, "category": food.category,
        "portion_g": portion.grams, "portion_group": portion.group,
        "data_source": {"name": source.get("name", food.source or "unknown"),
                        "licence": source.get("licence", ""), "url": source.get("url")},
        "everyday": food.familiarity >= 0.85,
        "wikipedia": lookup(food.name, network=network),
    }
