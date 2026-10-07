"""Which photo shows which recipe or food, with its credit (data/photos.json, DECISIONS.md decision 30).

The files themselves are served by the app at /app/photos/, so showing a photo
sends nothing to Wikimedia Commons. Foods are matched through the planner's
ingredients (data/ingredients.json): a photo listing "oats" shows for the
engine food ciqual-32140.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(tags=["photos"])

DATA = Path(__file__).resolve().parents[2] / "data"


def _photo(p: dict) -> dict:
    return {"src": f"/app/photos/{p['id']}.webp", "thumb": f"/app/photos/{p['id']}-sq.webp",
            "author": p["author"], "licence": p["licence"], "licence_url": p.get("licence_url", ""), "page": p["page"],
            "changes": p["changes"]}


@lru_cache(maxsize=1)
def photo_index() -> dict:
    ledger = json.loads((DATA / "photos.json").read_text(encoding="utf-8"))
    ingredients = json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))["ingredients"]
    food_of = {i["id"]: f"ciqual-{i['ciqual']}" for i in ingredients}
    recipes, foods, by_ingredient = {}, {}, {}
    for p in ledger["photos"]:
        for ref in p["for"]:
            kind, item = ref.split(":", 1)
            if kind == "recipe":
                recipes[item] = _photo(p)
        for ing in p.get("ingredients", []):
            foods[food_of[ing]] = by_ingredient[ing] = _photo(p)
    credits = [{"shows": p["shows"], "author": p["author"], "licence": p["licence"], "licence_url": p.get("licence_url", ""),
                "page": p["page"], "changes": p["changes"]} for p in ledger["photos"]]
    return {"recipes": recipes, "foods": foods, "ingredients": by_ingredient, "credits": credits}


@router.get("/photos")
def photos():
    """Photo, thumbnail and credit for each recipe and everyday food that has one; foods keyed by engine
    food id and by the planner's ingredient id (shopping-list items carry the latter). 'credits' lists every
    photo once, with the changes made, for the app's Photo credits."""
    return photo_index()
