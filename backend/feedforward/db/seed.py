"""
Load the versioned JSON corpus into the database, and export it back out.

The JSON files stay the auditable seed. The database is what the API reads
after ``python -m feedforward.db.seed``. Export writes ``data/seed/`` so a
reviewer can diff the database without querying it.

Users are not touched. Re-running the seed replaces the scientific tables.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..data.ingest.openfoodfacts import off_unit
from ..engine.build import DATA, NUTRIENT_META, load_food_records, load_goal_edges
from ..engine import taxonomy
from ..ontology import nutrients as ontology
from ..ontology.units import UnitError, canonical_unit, convert
from .models import Base
from .repository import replace_corpus
from .session import get_engine, session_scope

SEED_DIR = DATA / "seed"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_sources() -> list[dict]:
    return _load_json(DATA / "sources.json")["sources"]


def source_id_for(record: dict) -> str:
    """Which sources.json row a merged record came from."""
    kind = record.get("_source_kind", "curated")
    if kind == "usda":
        label = record.get("_source", "")
        return "usda-fdc-foundation" if "Foundation" in label else "usda-fdc-sr-legacy"
    if kind == "openfoodfacts":
        return "openfoodfacts"
    if kind == "ciqual":
        return "ciqual-2020"
    return "feedforward-curated"


def _off_provenance(record: dict) -> tuple[dict[str, list], dict[str, float]]:
    """
    (original units, rejected amounts in canonical units).

    Kept and range-rejected amounts are already canonical; the published
    OpenFoodFacts value (grams, or kcal for energy) is recomputed from them.
    Physically impossible values were never converted, so for those the raw
    number is the original and the canonical amount is derived from it.
    Originals are stored only where the unit differs.
    """
    originals: dict[str, list] = {}
    rejected = dict(record.get("_rejected_amounts") or {})
    canonical = {**record.get("nutrients", {}), **rejected}
    for nid, amount in canonical.items():
        definition = ontology.get(nid)
        if definition is None or nid in record.get("_impossible", {}):
            continue
        src = off_unit(nid)
        try:
            if canonical_unit(src) != definition.unit:
                originals[nid] = [round(convert(amount, definition.unit, src, nutrient=nid), 9), src]
        except UnitError:
            continue
    for nid, raw in (record.get("_impossible") or {}).items():
        definition = ontology.get(nid)
        src = off_unit(nid)
        originals[nid] = [float(raw), src]
        if definition is not None:
            try:
                rejected[nid] = convert(raw, src, definition.unit, nutrient=nid)
            except UnitError:
                pass
    return originals, rejected


def with_provenance(record: dict) -> dict:
    rec = dict(record)
    rec["_source_id"] = source_id_for(rec)
    kind = rec.get("_source_kind")
    if kind == "openfoodfacts":
        rec["_barcode"] = str(rec.get("id", ""))
        rec["_original_units"], rec["_rejected_amounts"] = _off_provenance(rec)
        # OFF product names are in whatever language the contributor used.
        rec.setdefault("_name_lang", "")
    else:
        # USDA descriptions, the curated set and CIQUAL's name column are English;
        # CIQUAL also carries the French name in _names.
        rec.setdefault("_name_lang", "en")
    return rec


def _food_records() -> list[dict]:
    """The merge the engine uses (build.load_food_records), plus provenance."""
    return [with_provenance(r) for r in load_food_records()]


def _edges() -> list[dict]:
    return load_goal_edges()


def _interactions() -> list[dict]:
    raw = _load_json(DATA / "interactions.json")
    return raw["interactions"]


def _goals() -> list[dict]:
    return [
        {"id": g.id, "label": g.label, "system": g.system,
         "description": g.description, "icd10_refs": g.icd10_refs}
        for g in taxonomy.all_goals()
    ]


def seed() -> dict[str, int]:
    get_engine()
    Base.metadata.create_all(get_engine())
    foods = _food_records()
    with session_scope() as session:
        return replace_corpus(
            session,
            foods=foods,
            edges=_edges(),
            goals=_goals(),
            nutrients=NUTRIENT_META,
            interactions=_interactions(),
            sources=load_sources(),
            ontology=ontology.all_nutrients(),
        )


def export_seed(dest: Path | None = None) -> Path:
    """Write the JSON the database was seeded from, plus a manifest."""
    dest = dest or SEED_DIR
    dest.mkdir(parents=True, exist_ok=True)
    foods = _food_records()
    # The export is the engine-facing view: trusted amounts only, with the
    # rejection reasons kept so a reviewer can see what was withheld.
    payload = {
        "foods": foods,
        "goal_edges": _edges(),
        "interactions": _interactions(),
        "goals": _goals(),
    }
    (dest / "corpus.json").write_text(
        json.dumps({
            "food_count": len(foods),
            "goal_edge_count": len(payload["goal_edges"]),
            "interaction_count": len(payload["interactions"]),
            "note": ("Export of the seed view. Raw OFF values that failed the "
                     "USDA range check are under each food's _rejected map, "
                     "not in nutrients."),
        }, indent=2),
        encoding="utf-8",
    )
    # Full foods file can be large once USDA is included. Write it anyway:
    # auditability was the requirement. It is generated, not hand-edited.
    (dest / "foods.json").write_text(json.dumps(foods, ensure_ascii=False), encoding="utf-8")
    (dest / "goal_edges.json").write_text(
        json.dumps(payload["goal_edges"], indent=2, ensure_ascii=False), encoding="utf-8")
    (dest / "interactions.json").write_text(
        json.dumps(payload["interactions"], indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Seed or export the FeedForward corpus.")
    parser.add_argument("--export", action="store_true", help="Also write data/seed/")
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    if not args.export_only:
        counts = seed()
        print(f"Seeded {counts['foods']} foods, {counts['edges']} edges, "
              f"{counts['interactions']} interactions.")
    if args.export or args.export_only:
        path = export_seed()
        print(f"Exported seed to {path}")


if __name__ == "__main__":
    _cli()
