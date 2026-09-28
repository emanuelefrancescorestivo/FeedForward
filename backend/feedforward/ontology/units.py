"""
Unit normalisation for nutrient amounts.

Every importer converts into the canonical unit declared in nutrients.json
before a value reaches the database. Conversions live here, once, so a source
cannot quietly apply its own factor.

What converts, and what does not
--------------------------------
Mass (g, mg, µg) and energy (kcal, kJ) are exact. International Units are
converted only where the factor is fixed: vitamin D (40 IU = 1 µg). Vitamin A
IU is refused — the µg RAE equivalent depends on whether the IU came from
retinol (0.3 µg) or beta-carotene (0.05 µg RAE), which the label does not say.
Vitamin E IU is refused for the same reason (natural vs synthetic
alpha-tocopherol). A refusal raises UnitError; the importer records the value
as unconverted instead of guessing.
"""
from __future__ import annotations

import re
import unicodedata

_MASS_IN_G = {"g": 1.0, "mg": 1e-3, "µg": 1e-6}
_ENERGY_IN_KCAL = {"kcal": 1.0, "kj": 1 / 4.184}

# IU → µg, only where the factor does not depend on the chemical form.
_IU_TO_UG = {"vitamin-d": 1 / 40}

_ALIASES = {
    "g": "g", "gr": "g", "gram": "g", "grams": "g", "grammi": "g", "grammes": "g",
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "µg": "µg", "ug": "µg", "mcg": "µg", "microgram": "µg", "micrograms": "µg",
    "kcal": "kcal", "cal": "kcal", "kilocalorie": "kcal", "kilocalories": "kcal",
    "kj": "kj", "kilojoule": "kj", "kilojoules": "kj",
    "iu": "iu", "ui": "iu",
}


class UnitError(ValueError):
    """A conversion that cannot be done without guessing."""


def canonical_unit(unit: str) -> str:
    """
    Normalise a unit spelling: 'mcg', 'ug', 'μg' (Greek mu) and 'µg' (micro
    sign) are the same unit and are the most common source of silent 1000×
    errors between tables. Also drops a trailing '/100 g' or '/100g'.
    """
    text = unicodedata.normalize("NFKC", unit or "").strip().lower()
    # NFKC folds the micro sign (U+00B5) into Greek mu (U+03BC); fold back.
    text = text.replace("μ", "µ")
    text = re.sub(r"\s*/\s*100\s*(g|ml)\s*$", "", text)
    text = text.replace(" ", "")
    if text in _ALIASES:
        return _ALIASES[text]
    raise UnitError(f"unknown unit {unit!r}")


def convert(amount: float, from_unit: str, to_unit: str, *, nutrient: str | None = None) -> float:
    """Convert ``amount`` between units. Raises UnitError rather than guess."""
    src = canonical_unit(from_unit)
    dst = canonical_unit(to_unit)
    if src == dst:
        return float(amount)
    if src in _MASS_IN_G and dst in _MASS_IN_G:
        return float(amount) * _MASS_IN_G[src] / _MASS_IN_G[dst]
    if src in _ENERGY_IN_KCAL and dst in _ENERGY_IN_KCAL:
        return float(amount) * _ENERGY_IN_KCAL[src] / _ENERGY_IN_KCAL[dst]
    if src == "iu" and dst in _MASS_IN_G:
        factor = _IU_TO_UG.get(nutrient or "")
        if factor is None:
            raise UnitError(
                f"IU for {nutrient or 'this nutrient'} has no form-independent conversion")
        ug = float(amount) * factor
        return ug * _MASS_IN_G["µg"] / _MASS_IN_G[dst]
    raise UnitError(f"cannot convert {from_unit!r} to {to_unit!r}")


def grams_per_100g(amount: float, unit: str) -> float | None:
    """The amount as grams per 100 g, or None for non-mass units (energy, IU)."""
    try:
        src = canonical_unit(unit)
    except UnitError:
        return None
    if src not in _MASS_IN_G:
        return None
    return float(amount) * _MASS_IN_G[src]


def physically_possible(amount: float, unit: str) -> bool:
    """
    A single component cannot weigh more than the 100 g it is measured in.
    This catches data-entry errors (e.g. sodium '1440' typed into a gram
    field) that a statistical range check would also catch, but without
    needing a reference distribution. Energy is capped at 900 kcal/100 g,
    the value for pure fat.
    """
    if amount < 0:
        return False
    grams = grams_per_100g(amount, unit)
    if grams is not None:
        return grams <= 100.0
    try:
        src = canonical_unit(unit)
    except UnitError:
        return True
    if src in _ENERGY_IN_KCAL:
        return convert(amount, src, "kcal") <= 900.0
    return True
