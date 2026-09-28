"""
Reference portions.

Recommendations compare what one realistic portion of a food delivers with a
day's need. Per-100 g comparison rewards concentrates nobody eats 100 g of:
baking powder, dried herbs, freeze-dried vegetables, drink powders, fish oil.

Portions come from data/portions.json: ordered regex rules over the food's
name and category, first match wins. The rules are data so a dietitian can
review and change them without touching code.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .schema import Food

_PATH = Path(__file__).resolve().parent.parent / "data" / "portions.json"


@dataclass(frozen=True)
class Portion:
    grams: float
    group: str


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


@lru_cache(maxsize=1)
def _rules() -> tuple[float, tuple[tuple[str, float, re.Pattern, bool], ...]]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    rules = tuple(
        (r["group"], float(r["grams"]), re.compile(r["regex"]), r.get("on") == "name")
        for r in raw["rules"]
    )
    return float(raw.get("default_grams", 100)), rules


@lru_cache(maxsize=None)
def portion_for_text(name: str, category: str = "") -> Portion:
    default, rules = _rules()
    name_text = _fold(name)
    text = f"{name_text} | {_fold(category)}"
    for group, grams, pattern, name_only in rules:
        if pattern.search(name_text if name_only else text):
            return Portion(grams, group)
    return Portion(default, "default")


# OpenFoodFacts products are packaged foods as sold, so cereals, pasta and
# legumes are dry unless the name says cooked or canned. USDA and curated
# entries state their preparation in the name, so the rules already see it.
_AS_SOLD_DRY = {"grains_cooked": ("grains_dry", 70.0), "legumes": ("legumes_dry", 50.0)}
_PREPARED_WORDS = re.compile(
    r"cooked|boiled|canned|\bcuite?s?\b|precuite?s?|conserve|appertis|au naturel|en boite|bocal")


def portion_for(food: Food) -> Portion:
    portion = portion_for_text(food.name, food.category)
    if portion.group not in _AS_SOLD_DRY:
        return portion
    prepared = _PREPARED_WORDS.search(_fold(f"{food.name} {food.category}"))
    # Grains are dry unless the name says cooked, in any source ("Wheat, soft
    # white" is kernels). USDA legume names always state their form, so the
    # dry-by-default rule for legumes applies to packaged (OFF) products only.
    if not prepared and (portion.group == "grains_cooked" or food.source == "openfoodfacts"):
        group, grams = _AS_SOLD_DRY[portion.group]
        return Portion(grams, group)
    return portion
