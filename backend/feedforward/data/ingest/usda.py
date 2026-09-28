"""
data/ingest/usda.py
===================
USDA FoodData Central connector — the path to scale FeedForward's food corpus
from dozens of curated staples to thousands of research-grade entries.

WHY USDA
--------
OpenFoodFacts is strong on branded products but unreliable on micronutrients.
USDA FoodData Central (Foundation Foods + SR Legacy) is the standardised source
used throughout the nutrition literature, with consistent units and trace
minerals (copper, selenium, etc.) and B-vitamins that FeedForward's interaction
matrix can act on.

USAGE
-----
1. Get a free API key: https://fdc.nal.usda.gov/api-key-signup.html
2. export FDC_API_KEY=your_key
3. Fetch and merge into the whole-foods corpus:
       python -m feedforward.data.ingest.usda --merge \
           "spinach" "lentils" "beef" "salmon" "almonds"

This connector is not run at import time and not part of the default build; the
default engine uses the cached corpus so it works offline and reproducibly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

FDC_SEARCH = "https://api.nal.usda.gov/fdc/v1/foods/search"
_DATA = Path(__file__).resolve().parent.parent

# FDC nutrient number -> FeedForward nutrient id
FDC_NUTRIENT_MAP: dict[str, str] = {
    "203": "proteins", "204": "fat", "205": "carbohydrates", "291": "fiber",
    "269": "sugars", "208": "energy-kcal", "606": "saturated-fat", "307": "sodium",
    "301": "calcium", "303": "iron", "304": "magnesium", "305": "phosphorus",
    "306": "potassium", "309": "zinc", "312": "copper", "315": "manganese",
    "317": "selenium", "401": "vitamin-c", "320": "vitamin-a", "323": "vitamin-e",
    "430": "vitamin-k", "328": "vitamin-d", "417": "folate", "418": "vitamin-b12",
    "621": "omega-3-fat",
}

# Heuristic: FDC food categories / description keywords that imply animal source
_ANIMAL_HINTS = ["beef", "pork", "chicken", "turkey", "lamb", "veal", "fish",
                 "salmon", "tuna", "cod", "shrimp", "oyster", "mussel", "egg",
                 "milk", "cheese", "yogurt", "liver", "meat", "poultry", "seafood"]


def _require_requests():
    try:
        import requests
        return requests
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("The 'requests' package is required for USDA ingest.") from e


def search_foods(query: str, page_size: int = 5, *, api_key: str | None = None,
                 data_types: tuple[str, ...] = ("Foundation", "SR Legacy")):
    """Search FDC and return the raw hit list."""
    requests = _require_requests()
    key = api_key or os.getenv("FDC_API_KEY")
    if not key:
        raise RuntimeError("Set FDC_API_KEY (get one free at "
                           "https://fdc.nal.usda.gov/api-key-signup.html).")
    params = {"query": query, "pageSize": page_size, "api_key": key,
              "dataType": list(data_types)}
    r = requests.get(FDC_SEARCH, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("foods", [])


def _looks_animal(food: dict) -> bool:
    text = (food.get("description", "") + " " +
            str(food.get("foodCategory", ""))).lower()
    return any(h in text for h in _ANIMAL_HINTS)


def to_feedforward_record(fdc_food: dict) -> dict:
    """Convert one FDC food into a FeedForward foods.json record."""
    nutrients: dict[str, float] = {}
    for n in fdc_food.get("foodNutrients", []):
        num = str(n.get("nutrientNumber", ""))
        ff_id = FDC_NUTRIENT_MAP.get(num)
        val = n.get("value")
        if ff_id and isinstance(val, (int, float)) and val > 0:
            # USDA copper is mg; keep mg. Everything else already matches our units.
            nutrients[ff_id] = round(float(val), 3)
    return {
        "id": f"fdc-{fdc_food.get('fdcId')}",
        "name": fdc_food.get("description", "").title(),
        "category": str(fdc_food.get("foodCategory", "USDA")),
        "nutrients": nutrients,
        "nutri_score": "",
        "nova": 1,
        "_source": "USDA FoodData Central",
        "_is_animal": _looks_animal(fdc_food),
    }


def ingest(queries: list[str], *, api_key: str | None = None,
           per_query: int = 3, sleep: float = 0.3) -> list[dict]:
    """Fetch and convert a batch of queries into FeedForward records."""
    out: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        try:
            hits = search_foods(q, page_size=per_query, api_key=api_key)
        except Exception as e:  # pragma: no cover
            print(f"  ! {q}: {e}", file=sys.stderr)
            continue
        for food in hits:
            rec = to_feedforward_record(food)
            if rec["id"] not in seen and len(rec["nutrients"]) >= 3:
                out.append(rec)
                seen.add(rec["id"])
        time.sleep(sleep)
    return out


def merge_into_whole_foods(records: list[dict],
                           path: Path | None = None) -> Path:
    """Append new USDA records to whole_foods.json, de-duplicating by id."""
    path = path or (_DATA / "whole_foods.json")
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    have = {r["id"] for r in existing}
    added = [r for r in records if r["id"] not in have]
    existing.extend(added)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"Merged {len(added)} new USDA foods (total {len(existing)}).")
    return path


def _cli():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Ingest foods from USDA FoodData Central.")
    ap.add_argument("queries", nargs="*", help="Food search terms (API mode)")
    ap.add_argument("--merge", action="store_true",
                    help="Merge API results into whole_foods.json")
    ap.add_argument("--per-query", type=int, default=3)
    ap.add_argument("--bulk", action="store_true",
                    help="Parse downloaded Foundation + SR Legacy CSV dirs into usda_corpus.json")
    ap.add_argument("--foundation", type=Path, default=None)
    ap.add_argument("--sr", type=Path, default=None)
    args = ap.parse_args()
    if args.bulk:
        from .usda_bulk import build_corpus, write_corpus, _norm_name
        cache = _DATA / "ingest" / "cache"
        foundation = args.foundation or (cache / "foundation")
        sr = args.sr or (cache / "sr")
        curated = json.loads((_DATA / "whole_foods.json").read_text(encoding="utf-8"))
        names = {_norm_name(r["name"]) for r in curated}
        records = build_corpus(foundation, sr, curated_names=names)
        out = write_corpus(records, _DATA / "usda_corpus.json")
        print(f"Wrote {len(records)} USDA foods to {out}")
        return
    if not args.queries:
        ap.error("queries are required unless --bulk is set")
    records = ingest(args.queries, per_query=args.per_query)
    print(f"Fetched {len(records)} records.")
    if args.merge:
        merge_into_whole_foods(records)
    else:
        for r in records[:10]:
            print(f"  {r['name']}: {len(r['nutrients'])} nutrients")


if __name__ == "__main__":  # pragma: no cover
    _cli()
