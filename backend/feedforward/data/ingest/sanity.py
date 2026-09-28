"""
OpenFoodFacts micronutrient gate.

OFF is kept for barcodes, NOVA, Nutri-Score and macros. Its micronutrient
fields are label declarations, not analytical data, and the original crawl
read them in the wrong unit (grams as mg/µg — fixed in openfoodfacts.py).
Even in the right unit a label can be mistyped, so a value may become a
graph edge only if it sits inside an order of magnitude of the USDA
distribution for that food's category. Failing values are stored with trusted=false so
the rejection is auditable, and they are omitted from the nutrients dict
the engine reads.

The check is a range gate, not a correction. We do not rescale a suspicious
value into a "fixed" one. Zero means "not reported" and is left alone.
"""
from __future__ import annotations

import statistics

# Nutrients the bioavailability and DRI layers treat as analytical.
# Sodium is included because the OFF crawl mixed grams and milligrams.
MICRONUTRIENTS = {
    "iron", "calcium", "magnesium", "zinc", "phosphorus", "manganese",
    "copper", "selenium", "potassium", "folate", "vitamin-b12",
    "vitamin-a", "vitamin-c", "vitamin-e", "vitamin-k", "vitamin-d",
    "omega-3-fat", "sodium",
}

# Coarse buckets. OFF categories are free text; USDA categories are a
# controlled list. Keyword overlap is the join. A bucket is used only when
# it has enough USDA foods to have a distribution — otherwise we fall back
# to the global range, which is wider and rejects less.
_BUCKETS: list[tuple[str, tuple[str, ...]]] = [
    ("leafy", ("leafy", "spinach", "kale", "lettuce", "cabbage")),
    ("vegetable", ("vegetable", "veg")),
    ("fruit", ("fruit", "berry", "citrus")),
    ("meat", ("beef", "pork", "poultry", "chicken", "lamb", "veal", "meat", "sausage")),
    ("fish", ("fish", "seafood", "shellfish", "finfish")),
    ("dairy", ("dairy", "milk", "cheese", "yogurt")),
    ("egg", ("egg",)),
    ("legume", ("legume", "bean", "lentil", "pea")),
    ("grain", ("grain", "cereal", "baked", "bread", "pasta")),
    ("nut", ("nut", "seed")),
]


def bucket_for(category: str, name: str = "") -> str:
    text = f"{category} {name}".lower()
    for bucket, keys in _BUCKETS:
        if any(k in text for k in keys):
            return bucket
    return "other"


def ranges_from_trusted(records: list[dict]) -> dict[str, dict[str, tuple[float, float]]]:
    """
    Per bucket, per nutrient: (p10, p90) of positive USDA/curated amounts.

    p10/p90 rather than min/max so one fortified outlier does not make the
    gate useless. A value is rejected only when it is more than 10× outside
    that central range.
    """
    grouped: dict[str, dict[str, list[float]]] = {}
    global_vals: dict[str, list[float]] = {}
    for rec in records:
        if not rec.get("_micronutrient_trusted", False):
            continue
        bucket = bucket_for(rec.get("category", ""), rec.get("name", ""))
        for nid, amount in rec.get("nutrients", {}).items():
            if nid not in MICRONUTRIENTS or not isinstance(amount, (int, float)):
                continue
            if amount <= 0:
                continue
            grouped.setdefault(bucket, {}).setdefault(nid, []).append(float(amount))
            global_vals.setdefault(nid, []).append(float(amount))

    def _band(values: list[float]) -> tuple[float, float] | None:
        if len(values) < 8:
            return None
        ordered = sorted(values)
        # Inclusive percentile, no interpolation library required.
        def at(q: float) -> float:
            idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
            return ordered[idx]
        low, high = at(0.10), at(0.90)
        if high <= 0:
            return None
        return low, high

    out: dict[str, dict[str, tuple[float, float]]] = {}
    for bucket, nutrients in grouped.items():
        for nid, values in nutrients.items():
            band = _band(values)
            if band:
                out.setdefault(bucket, {})[nid] = band
    for nid, values in global_vals.items():
        band = _band(values)
        if band:
            out.setdefault("*", {})[nid] = band
    return out


def check_micronutrient(nutrient: str, amount: float, *, category: str, name: str,
                        ranges: dict[str, dict[str, tuple[float, float]]]) -> str | None:
    """
    Return a reject reason, or None if the value may enter the graph.

    Macros are not passed here. A missing micronutrient (amount <= 0) is
    "not reported", not a failed check.
    """
    if nutrient not in MICRONUTRIENTS or amount <= 0:
        return None
    bucket = bucket_for(category, name)
    band = ranges.get(bucket, {}).get(nutrient) or ranges.get("*", {}).get(nutrient)
    if not band:
        # No USDA reference for this nutrient. Do not guess a range, and do
        # not let an unreferenced OFF value into the micronutrient graph.
        return "no USDA reference range"
    low, high = band
    if amount > high * 10:
        return f"above 10× USDA p90 ({high:.4g}) for {bucket}"
    if low > 0 and amount < low / 10:
        return f"below USDA p10/10 ({low:.4g}) for {bucket}"
    return None


def split_off_nutrients(record: dict, ranges: dict) -> dict:
    """
    Copy an OFF record, moving failed micronutrients out of ``nutrients``.

    The returned dict is what the engine loads. ``_rejected`` maps nutrient
    id → reason; ``_rejected_amounts`` keeps the raw number for the database.
    """
    kept = {}
    rejected: dict[str, str] = {}
    amounts: dict[str, float] = {}
    category = record.get("category", "")
    name = record.get("name", "")
    for nid, amount in record.get("nutrients", {}).items():
        if not isinstance(amount, (int, float)):
            continue
        if nid in MICRONUTRIENTS:
            reason = check_micronutrient(
                nid, float(amount), category=category, name=name, ranges=ranges)
            if reason:
                rejected[nid] = reason
                amounts[nid] = float(amount)
                continue
        kept[nid] = amount
    # Values the unit normaliser already found physically impossible.
    for nid, amount in record.get("_impossible", {}).items():
        rejected[nid] = "physically impossible (> 100 g per 100 g, or > 900 kcal)"
        amounts[nid] = float(amount)
    out = dict(record)
    out["nutrients"] = kept
    out["_rejected"] = rejected
    out["_rejected_amounts"] = amounts
    out["_micronutrient_trusted"] = False
    out["_source_kind"] = "openfoodfacts"
    return out
