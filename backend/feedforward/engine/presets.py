"""Presets: a meal logged in one tap as an estimate, such as the CROUS lunch (data/presets.json).

A preset is a list of the planner's ingredients with grams; its nutrients are
each ingredient's CIQUAL food, like a recipe's. It is always shown as an
estimate (≈), because the real plate changes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Preset:
    id: str
    en: str
    fr: str
    detail_en: str
    detail_fr: str
    price_eur: float
    estimate: bool
    note_en: str
    items: tuple[tuple[str, float], ...]       # (ingredient id, grams)


@lru_cache(maxsize=1)
def load_presets() -> dict[str, Preset]:
    raw = json.loads((DATA / "presets.json").read_text(encoding="utf-8"))["presets"]
    return {p["id"]: Preset(p["id"], p["en"], p["fr"], p["detail_en"], p["detail_fr"], float(p["price_eur"]),
                            bool(p["estimate"]), p["note_en"], tuple((i["ingredient"], float(i["g"])) for i in p["items"]))
            for p in raw}


@lru_cache(maxsize=1)
def _ingredient_foods() -> dict[str, str]:
    ingredients = json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))["ingredients"]
    return {i["id"]: f"ciqual-{i['ciqual']}" for i in ingredients}


def preset_nutrients(rec, preset: Preset) -> dict[str, float]:
    """Nutrients of one portion: each ingredient's CIQUAL food x grams / 100. KeyError for an unknown
    ingredient or a food missing from the engine."""
    totals: dict[str, float] = {}
    for ingredient, grams in preset.items:
        food = rec.food_by_id.get(_ingredient_foods()[ingredient])
        if food is None:
            raise KeyError(f"no food for ingredient {ingredient}")
        for n, per100 in food.nutrients.items():
            totals[n] = totals.get(n, 0.0) + per100 * grams / 100.0
    return totals
