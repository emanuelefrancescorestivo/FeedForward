"""
Bulk USDA FoodData Central ingest.

The search API needs a key and is rate-limited. Foundation Foods and SR Legacy
are published as CSV archives that do not. This parser reads those archives
and emits the same record shape as ``usda.to_feedforward_record``.

What is mapped, and what is not
--------------------------------
Nutrient ids below are the internal FDC ids in ``nutrient.csv`` (not the
three-digit nutrient numbers the API uses). Energy is kcal id 1008 only —
Atwater general/specific factors are a second energy estimate and would
double-count if added. Vitamin A is RAE (1106), not IU. Vitamin D is µg
D2+D3 (1114), not IU. Vitamin K is phylloquinone (1185), the form the DRI
refers to in food. Folate prefers DFE (1190) and falls back to total folate
(1177). Omega-3 is the sum of ALA + EPA + DHA (1404, 1278, 1272), in grams.
That sum is a derived field; it is not a single USDA column, and it is
labelled as such on the record.

Heme iron exists in flesh (meat, poultry, fish), not in dairy or eggs. The
``_is_animal`` flag follows that, so milk is not treated as a heme source.
The older keyword list in ``build.py`` is broader; bulk records set the flag
explicitly so the keyword fallback does not override it.

Foundation foods are preferred over SR Legacy when the normalised description
matches: Foundation is the current analytical set, SR Legacy is the 2018
close-out of Standard Reference.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from ...ontology.nutrients import usda_direct_map, usda_preferred, usda_sums

# Internal nutrient id → FeedForward id, from ontology/nutrients.json. The ids
# were confirmed against nutrient.csv names in the April 2018 SR Legacy and
# April 2026 Foundation downloads.
_ID_MAP: dict[str, str] = usda_direct_map()

_FOLATE_DFE = "1190"
# Nutrients published under several ids: first present wins (ontology order).
_PREFERRED: dict[str, tuple[str, ...]] = usda_preferred()
_PREFERRED_BY_ID = {i: nid for nid, ids in _PREFERRED.items() for i in ids}
# Derived nutrients summed from components (omega-3 = ALA+EPA+DHA, EPA+DHA),
# from ``usda_sum`` in ontology/nutrients.json. A component can also be a
# nutrient in its own right (ALA), so sums are accumulated independently.
_SUMS: dict[str, tuple[str, ...]] = usda_sums()

# Flesh categories only. Dairy and eggs are animal foods but not heme iron.
_FLESH_CATEGORIES = {
    "beef products", "pork products", "poultry products",
    "finfish and shellfish products", "lamb, veal, and game products",
    "sausages and luncheon meats",
}
_FLESH_WORDS = (
    "beef", "pork", "chicken", "turkey", "lamb", "veal", "fish", "salmon",
    "tuna", "cod", "shrimp", "oyster", "mussel", "liver", "meat", "poultry",
    "seafood", "sardine", "mackerel", "trout", "herring",
)


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _find_table(root: Path, name: str) -> Path:
    matches = list(root.rglob(name))
    if not matches:
        raise FileNotFoundError(f"{name} not under {root}")
    return matches[0]


def _categories(root: Path) -> dict[str, str]:
    path = _find_table(root, "food_category.csv")
    out = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            out[row["id"]] = row["description"]
    return out


def _foods(root: Path, data_type: str, categories: dict[str, str]) -> dict[str, dict]:
    path = _find_table(root, "food.csv")
    out = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("data_type") != data_type:
                continue
            out[row["fdc_id"]] = {
                "fdc_id": row["fdc_id"],
                "name": row.get("description", "").strip(),
                "category": categories.get(row.get("food_category_id", ""), "USDA"),
            }
    return out


def _attach_nutrients(root: Path, foods: dict[str, dict]) -> None:
    path = _find_table(root, "food_nutrient.csv")
    # Hold preferred-id and summed components aside: pick the first, add the sums.
    preferred: dict[tuple[str, str], dict[str, float]] = {}
    sums: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            fdc = row["fdc_id"]
            if fdc not in foods:
                continue
            nid = row["nutrient_id"]
            raw = row.get("amount") or ""
            try:
                amount = float(raw)
            except ValueError:
                continue
            if amount <= 0:
                continue
            mapped = _ID_MAP.get(nid)
            if mapped:
                foods[fdc].setdefault("nutrients", {})[mapped] = round(amount, 3)
            elif nid in _PREFERRED_BY_ID:
                preferred.setdefault((fdc, _PREFERRED_BY_ID[nid]), {})[nid] = amount
            for derived, components in _SUMS.items():
                if nid in components:
                    per_food = sums.setdefault(derived, {})
                    per_food[fdc] = per_food.get(fdc, 0.0) + amount
    for (fdc, nutrient), parts in preferred.items():
        chosen = next((i for i in _PREFERRED[nutrient] if i in parts), None)
        if chosen is None:
            continue
        foods[fdc].setdefault("nutrients", {})[nutrient] = round(parts[chosen], 3)
        if nutrient == "folate":
            foods[fdc]["folate_is_dfe"] = chosen == _FOLATE_DFE
    for derived, per_food in sums.items():
        for fdc, total in per_food.items():
            if total > 0:
                foods[fdc].setdefault("nutrients", {})[derived] = round(total, 3)
                if derived == "omega-3-fat":
                    foods[fdc]["omega3_derived"] = True


def _is_flesh(food: dict) -> bool:
    category = food.get("category", "").lower()
    if category in _FLESH_CATEGORIES:
        return True
    text = f"{food.get('name', '')} {category}".lower()
    return any(w in text for w in _FLESH_WORDS)


def records_from_csv_dir(root: Path, *, data_type: str, source_label: str) -> list[dict]:
    categories = _categories(root)
    foods = _foods(root, data_type, categories)
    _attach_nutrients(root, foods)
    out = []
    for food in foods.values():
        nutrients = food.get("nutrients") or {}
        if len(nutrients) < 4:
            continue
        rec = {
            "id": f"fdc-{food['fdc_id']}",
            "name": food["name"].title() if food["name"].islower() else food["name"],
            "category": food["category"],
            "nutrients": nutrients,
            "nutri_score": "",
            "nova": 1,
            "_source": source_label,
            "_source_kind": "usda",
            "_external_id": food["fdc_id"],
            "_is_animal": _is_flesh(food),
            "_micronutrient_trusted": True,
        }
        if food.get("omega3_derived"):
            rec["_omega3_method"] = "sum of ALA+EPA+DHA (FDC ids 1404, 1278, 1272)"
        if "folate" in nutrients:
            rec["_folate_is_dfe"] = bool(food.get("folate_is_dfe"))
        out.append(rec)
    return out


def build_corpus(foundation_dir: Path, sr_dir: Path,
                 curated_names: set[str] | None = None) -> list[dict]:
    """
    Foundation first, then SR Legacy, skipping a description already kept.

    Curated whole-food names are also skipped: those 88 records were
    hand-checked and should not be duplicated by the bulk file.
    """
    curated_names = curated_names or set()
    kept: list[dict] = []
    seen = set(curated_names)
    batches = (
        (foundation_dir, "foundation_food", "USDA FoodData Central Foundation Foods"),
        (sr_dir, "sr_legacy_food", "USDA FoodData Central SR Legacy"),
    )
    for directory, data_type, label in batches:
        if not directory.exists():
            continue
        for rec in records_from_csv_dir(directory, data_type=data_type, source_label=label):
            key = _norm_name(rec["name"])
            if not key or key in seen:
                continue
            seen.add(key)
            kept.append(rec)
    return kept


def write_corpus(records: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return path
