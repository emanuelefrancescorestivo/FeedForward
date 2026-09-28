"""
Familiarity: how likely a European shopper is to know and buy a food.

Rankings put everyday foods first. The right signal is consumption data (the
EFSA Comprehensive European Food Consumption Database, planned with the EU
tables); until then this is a transparent heuristic from what the corpus
already tells us, in [0, 1]:

  source      curated staples 1.0 · CIQUAL (foods eaten in France) 0.9 ·
              USDA Foundation (common staples) 0.9 ·
              OpenFoodFacts (products sold in EU shops) 0.85 · USDA SR Legacy 0.7
  penalties   game and wild animals ×0.3 · restaurant and fast-food items ×0.4 ·
              offal ×0.5 · luxury or rarely bought items ×0.5 ·
              US brand names in capitals ×0.6 · US food-programme entries ×0.8

It changes the ORDER of recommendations (see Recommender.ranked), never a
food's goal score or what it delivers.
"""
from __future__ import annotations

import re
import unicodedata

from .schema import Food

_SOURCE_WEIGHT = {
    "ciqual-2020": 0.9, "ciqual": 0.9,          # French reference foods, rare items included
    "feedforward-curated": 1.0, "curated": 1.0,
    "usda-fdc-foundation": 0.9,
    "openfoodfacts": 0.85,
    "usda-fdc-sr-legacy": 0.7, "usda": 0.7,
}
_GAME = re.compile(
    r"\b(game meat|bear|beaver|muskrat|squirrel|opossum|raccoon|rabbit, wild|emu|ostrich|"
    r"grouse|pheasant|quail|dove|squab|goose, wild|canada goose|caribou|elk|moose|bison|"
    r"buffalo|antelope|deer|venison|boar|frog|turtle|snail|conch|whelk|abalone|"
    r"spleen|brain|lungs|pancreas|thymus|tripe|chitterlings)\b")
_RESTAURANT = ("fast foods", "restaurant foods")
# Offal and luxury or rarely bought items: real foods, not everyday ones.
_OFFAL = re.compile(r"\b(heart|kidneys?|liver|tongue|tripe|gizzards?|sweetbreads?|rognons?|coeur|foie)\b")
_RARE = re.compile(r"\b(caviar|roe|lobster|langoustine|scorpionfish|sea urchin|truffle|foie gras|"
                   r"abalone|oyster|snail|frog|kangaroo|horse|ostrich)\b")
_PROGRAMME = re.compile(r"food distribution program|school lunch|usda commodity")
_BRAND = re.compile(r"\b[A-Z][A-Z'&\-]{2,}\b")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def familiarity(food: Food, source_id: str = "") -> float:
    score = _SOURCE_WEIGHT.get(source_id or food.source, 0.7)
    name = _fold(food.name)
    if _GAME.search(name):
        score *= 0.3
    if any(c in _fold(food.category) for c in _RESTAURANT):
        score *= 0.4
    if _OFFAL.search(name):
        score *= 0.5
    if _RARE.search(name):
        score *= 0.5
    # USDA writes brands in capitals (RALSTON, MALT-O-MEAL); OFF names do not
    # follow that convention, so the check is USDA-only.
    if food.source == "usda" and len(_BRAND.findall(food.name)) >= 1:
        score *= 0.6
    if _PROGRAMME.search(name):
        score *= 0.8
    return round(score, 3)
