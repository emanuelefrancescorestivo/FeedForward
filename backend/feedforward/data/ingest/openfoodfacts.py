"""
OpenFoodFacts crawler, re-scoped.

OFF is used for what it is good at: branded products, barcodes, NOVA and
Nutri-Score, and macros. Micronutrients are stored only after the USDA range
gate in ``sanity.py``. A value that fails is kept with trusted=false so the
rejection can be inspected. Nothing here rescales a suspicious number.

The original crawl had two defects this module is written not to repeat:

  1. NOVA. Missing ``nova_group`` was treated as a pass, and the filter compared
     the tag string rather than the integer group. We require an integer 1–4
     when a NOVA filter is requested, and we store the value we actually saw.
  2. Units. Every OFF ``<nutrient>_100g`` field is normalised by OFF to
     grams (energy-kcal to kcal), whatever unit the label used; the raw crawl
     files state this per value (``iron_unit: "g"``). The original crawl
     stored those gram values as if they were the engine's mg/µg, which is
     why iron and vitamin C looked ~1000× too low. We now convert from the
     declared unit with ontology/units.py. That is a unit conversion, not a
     rescale of a suspicious number: values still pass the physical and
     USDA range gates in ``sanity.py`` afterwards.

The crawler is not imported by the engine. Run it explicitly.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ...ontology import nutrients as ontology
from ...ontology.units import convert, physically_possible

SEARCH = "https://world.openfoodfacts.org/api/v2/search"

# OFF nutrient keys → FeedForward ids, from ontology/nutrients.json.
# Micronutrient values are parsed and then gated; they are not trusted by default.
_OFF_KEYS = {f"{key}_100g": nid for key, nid in ontology.off_keys().items()}

# The unit OFF uses for every ``_100g`` field.
_OFF_UNIT = {"energy-kcal": "kcal"}
UNITS_MARKER = "canonical"


def off_unit(nutrient_id: str) -> str:
    return _OFF_UNIT.get(nutrient_id, "g")


def to_canonical(nutrient_id: str, amount: float) -> float | None:
    """
    OFF ``_100g`` amount → engine unit. None if the value is physically
    impossible (more than 100 g of one component in 100 g of food) — those
    are data-entry errors on the product page, not a unit question.
    """
    unit = off_unit(nutrient_id)
    if not physically_possible(amount, unit):
        return None
    definition = ontology.get(nutrient_id)
    if definition is None:
        return None
    return convert(amount, unit, definition.unit, nutrient=nutrient_id)


def normalize_record_units(record: dict) -> dict:
    """
    Convert a record written by the original crawler (gram values stored
    under engine ids) to canonical units. Idempotent: a record already
    carrying ``_units == "canonical"`` is returned unchanged. Values that are
    physically impossible move to ``_impossible`` with the raw number.
    """
    if record.get("_units") == UNITS_MARKER:
        return record
    out = dict(record)
    nutrients: dict[str, float] = {}
    impossible: dict[str, float] = {}
    for nid, amount in record.get("nutrients", {}).items():
        if not isinstance(amount, (int, float)):
            continue
        value = to_canonical(nid, float(amount))
        if value is None:
            impossible[nid] = amount
            continue
        nutrients[nid] = round(value, 4)
    out["nutrients"] = nutrients
    if impossible:
        out["_impossible"] = impossible
    out["_units"] = UNITS_MARKER
    return out


def nova_group(product: dict) -> int | None:
    """Integer NOVA group, or None if the product does not state one."""
    raw = product.get("nova_group")
    if raw is None:
        nutriments = product.get("nutriments") or {}
        raw = nutriments.get("nova-group")
    try:
        group = int(raw)
    except (TypeError, ValueError):
        return None
    return group if group in (1, 2, 3, 4) else None


def passes_nova_filter(product: dict, allowed: set[int] | None) -> bool:
    """
    A missing NOVA group does not pass a filter.

    That was the old bug: foods with no NOVA tag were kept when the intent
    was to keep only a stated group. Unfiltered crawls (allowed is None)
    still keep the product and store nova=0.
    """
    group = nova_group(product)
    if allowed is None:
        return True
    return group in allowed


def product_to_record(product: dict) -> dict | None:
    code = str(product.get("code") or "").strip()
    name = (product.get("product_name") or "").strip()
    if not code or not name:
        return None
    nutriments = product.get("nutriments") or {}
    nutrients = {}
    impossible = {}
    for src, dest in _OFF_KEYS.items():
        value = nutriments.get(src)
        if isinstance(value, (int, float)) and value > 0:
            converted = to_canonical(dest, float(value))
            if converted is None:
                impossible[dest] = value
            else:
                nutrients[dest] = round(converted, 4)
    if "energy-kcal" not in nutrients and len(nutrients) < 2:
        return None
    group = nova_group(product)
    record = {
        "id": code,
        "name": name,
        "category": product.get("categories") or "",
        "nutrients": nutrients,
        "nutri_score": (product.get("nutriscore_grade") or "").lower(),
        "nova": group or 0,
        "_source": "OpenFoodFacts",
        "_source_kind": "openfoodfacts",
        "_barcode": code,
        "_micronutrient_trusted": False,
        "_units": UNITS_MARKER,
    }
    if impossible:
        record["_impossible"] = impossible
    return record


def search_products(query: str, *, page_size: int = 20, page: int = 1,
                    nova: set[int] | None = None) -> list[dict]:
    import requests
    params = {
        "search_terms": query,
        "page_size": page_size,
        "page": page,
        "fields": "code,product_name,categories,nutriments,nutriscore_grade,nova_group",
        "json": 1,
    }
    response = requests.get(SEARCH, params=params, timeout=30, headers={
        "User-Agent": "FeedForward/1.0 (nutrition research; local ingest)",
    })
    response.raise_for_status()
    products = response.json().get("products") or []
    records = []
    for product in products:
        if not passes_nova_filter(product, nova):
            continue
        rec = product_to_record(product)
        if rec:
            records.append(rec)
    return records


def ingest(queries: list[str], *, page_size: int = 20,
           nova: set[int] | None = None, sleep: float = 0.5) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for query in queries:
        try:
            batch = search_products(query, page_size=page_size, nova=nova)
        except Exception as exc:
            print(f"  ! {query}: {exc}")
            continue
        for rec in batch:
            if rec["id"] not in seen:
                out.append(rec)
                seen.add(rec["id"])
        time.sleep(sleep)
    return out


def write_records(records: list[dict], path: Path) -> Path:
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def normalize_file(path: Path) -> dict[str, int]:
    """Rewrite a crawl file in canonical units. Safe to run twice."""
    records = json.loads(path.read_text(encoding="utf-8"))
    already = sum(1 for r in records if r.get("_units") == UNITS_MARKER)
    out = [normalize_record_units(r) for r in records]
    impossible = sum(len(r.get("_impossible", {})) for r in out)
    write_records(out, path)
    return {"records": len(out), "already_canonical": already,
            "impossible_values": impossible}


def _cli() -> None:
    parser = argparse.ArgumentParser(description="OpenFoodFacts maintenance.")
    parser.add_argument("--normalize-units", type=Path, metavar="FILE",
                        help="convert a crawl file from OFF grams to canonical units")
    args = parser.parse_args()
    if args.normalize_units:
        print(normalize_file(args.normalize_units))
    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
