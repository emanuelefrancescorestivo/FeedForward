"""
CIQUAL 2020 (ANSES) -> FeedForward food records.

The French reference food composition table: 3,186 foods consumed in France,
published as open data under the Licence Ouverte / Etalab 2.0. Downloaded
from ciqual.anses.fr (linked from data.gouv.fr) into data/ingest/cache/ciqual/.

Column mapping goes through the nutrient ontology (column headers such as
"Iron (mg/100g)" resolve by alias, with their unit); the few columns the
resolver must not guess are mapped explicitly below, and every other column
is listed as deliberately ignored, so a new CIQUAL release with an unknown
column fails loudly instead of being dropped silently.

Derived values, documented on each record:
  vitamin-a    RAE = retinol + beta-carotene / 12 (IOM, dietary beta-carotene)
  epa-dha      EPA + DHA
  omega-3-fat  ALA + EPA + DHA
  folate       CIQUAL reports total folate, not DFE (flagged _folate_is_dfe=False)
  energy       when CIQUAL publishes none (871 foods), 4P + 4C + 9F + 2 fibre
               (+ alcohol, organic acids, polyols), EU 1169/2011 Annex XIV

Cells such as "traces", "< 0,5" or "-" become qualified values
(ontology/values.py): never an edge in the graph, kept with their bound.

    python -m feedforward.data.ingest.ciqual   # writes data/ciqual_corpus.json
"""
from __future__ import annotations

import json
from pathlib import Path

from ...ontology.nutrients import get as nutrient_def, resolve
from ...ontology.units import convert
from ...ontology.values import EXACT, parse_value

DATA = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / "cache" / "ciqual"
OUT = DATA / "ciqual_corpus.json"

_EXPLICIT = {
    "Energy, Regulation EU No 1169/2011 (kcal/100g)": ("energy-kcal", "kcal"),
    "Protein (g/100g)": ("proteins", "g"),
    "FA saturated (g/100g)": ("saturated-fat", "g"),
    "FA 18:3 c9,c12,c15 (n-3) (g/100g)": ("_ala", "g"),
    "FA 20:5 5c,8c,11c,14c,17c (n-3) EPA (g/100g)": ("_epa", "g"),
    "FA 22:6 4c,7c,10c,13c,16c,19c (n-3) DHA (g/100g)": ("_dha", "g"),
    "Retinol (µg/100g)": ("_retinol", "µg"),
    "Beta-carotene (µg/100g)": ("_beta_carotene", "µg"),
    "Vitamin K1 (µg/100g)": ("vitamin-k", "µg"),
    # Components used only to compute energy when CIQUAL does not publish it.
    "Alcohol (g/100g)": ("_alcohol", "g"),
    "Organic acids (g/100g)": ("_organic_acids", "g"),
    "Polyols (g/100g)": ("_polyols", "g"),
}
# EU Regulation 1169/2011, Annex XIV conversion factors (kcal per g).
_KCAL_PER_G = {"proteins": 4, "carbohydrates": 4, "fat": 9, "fiber": 2,
               "_alcohol": 7, "_organic_acids": 3, "_polyols": 2.4}
_IGNORED = {
    "Energy, Regulation EU No 1169/2011 (kJ/100g)",       # same energy in kJ
    "Energy, N x Jones' factor, with fibres (kJ/100g)",   # alternative energy method
    "Energy, N x Jones' factor, with fibres (kcal/100g)",
    "Protein, crude, N x 6.25 (g/100g)",                   # alternative protein method
    "Water (g/100g)", "fructose (g/100g)", "galactose (g/100g)", "glucose (g/100g)",
    "lactose (g/100g)", "maltose (g/100g)", "sucrose (g/100g)", "Starch (g/100g)",
    "Ash (g/100g)",
    "FA mono (g/100g)", "FA poly (g/100g)", "FA 4:0 (g/100g)", "FA 6:0 (g/100g)",
    "FA 8:0 (g/100g)", "FA 10:0 (g/100g)", "FA 12:0 (g/100g)", "FA 14:0 (g/100g)",
    "FA 16:0 (g/100g)", "FA 18:0 (g/100g)", "FA 18:1 n-9 cis (g/100g)",
    "FA 18:2 9c,12c (n-6) (g/100g)", "FA 20:4 5c,8c,11c,14c (n-6) (g/100g)",
    "Cholesterol (mg/100g)", "Chloride (mg/100g)", "Vitamin K2 (µg/100g)",
}
_META = {"alim_grp_code", "alim_ssgrp_code", "alim_ssssgrp_code", "alim_grp_nom_eng",
         "alim_ssgrp_nom_eng", "alim_ssssgrp_nom_eng", "alim_code", "alim_nom_eng", "alim_nom_sci"}
# CIQUAL sub-groups whose foods contain heme iron (animal flesh).
_FLESH_WORDS = ("meat", "poultry", "fish", "offal", "charcuterie", "seafood", "game",
                "crustacean", "mollusc", "cooked meats", "sausage")


def column_map(columns) -> dict[str, tuple[str, str]]:
    """Header -> (nutrient id or _component, unit). Raises on an unaccounted column."""
    mapping, unknown = {}, []
    for col in columns:
        if col in _META or col in _IGNORED:
            continue
        if col in _EXPLICIT:
            mapping[col] = _EXPLICIT[col]
            continue
        found = resolve(col)
        if found is None or found.unit is None:
            unknown.append(col)
            continue
        mapping[col] = (found.nutrient_id, found.unit)
    if unknown:
        raise ValueError(f"CIQUAL columns not accounted for: {unknown}")
    return mapping


def records(eng_path: Path | None = None, fr_path: Path | None = None) -> list[dict]:
    import pandas as pd
    eng = pd.read_excel(eng_path or CACHE / "ciqual_2020_eng.xls")
    fr = pd.read_excel(fr_path or CACHE / "ciqual_2020_fr.xls")
    fr_names = dict(zip(fr["alim_code"], fr["alim_nom_fr"]))
    fr_groups = dict(zip(fr["alim_code"], fr["alim_ssgrp_nom_fr"]))
    mapping = column_map(eng.columns)
    out = []
    seen: dict[int, int] = {}
    for _, row in eng.iterrows():
        code = int(row["alim_code"])
        values: dict[str, float] = {}
        qualified: dict[str, list] = {}
        for col, (nid, unit) in mapping.items():
            parsed = parse_value(row[col])
            if parsed.qualifier == "missing":
                continue
            if nid.startswith("_"):
                values[nid] = parsed.engine_amount
                continue
            target = nutrient_def(nid)
            if parsed.qualifier != EXACT:
                bound = None if parsed.amount is None else convert(parsed.amount, unit, target.unit, nutrient=nid)
                qualified[nid] = [bound, parsed.qualifier]
                continue
            values[nid] = round(convert(parsed.amount, unit, target.unit, nutrient=nid), 4)
        nutrients = {k: v for k, v in values.items() if not k.startswith("_") and v > 0}
        energy_method = "published"
        if "energy-kcal" not in nutrients and all(k in values for k in ("proteins", "carbohydrates", "fat")):
            kcal = sum(values.get(k, 0.0) * f for k, f in _KCAL_PER_G.items())
            if kcal > 0:
                nutrients["energy-kcal"] = round(kcal, 1)
                energy_method = "computed with EU 1169/2011 Annex XIV factors"
        retinol, carotene = values.get("_retinol"), values.get("_beta_carotene")
        if retinol is not None or carotene is not None:
            rae = (retinol or 0) + (carotene or 0) / 12
            if rae > 0:
                nutrients["vitamin-a"] = round(rae, 3)
        epa, dha, ala = values.get("_epa", 0), values.get("_dha", 0), values.get("_ala", 0)
        if epa + dha > 0:
            nutrients["epa-dha"] = round(epa + dha, 4)
        if ala > 0:
            nutrients["ala"] = round(ala, 4)
        if ala + epa + dha > 0:
            nutrients["omega-3-fat"] = round(ala + epa + dha, 4)
        group = f"{row['alim_grp_nom_eng']} | {row['alim_ssgrp_nom_eng']}"
        is_flesh = any(w in str(row["alim_ssgrp_nom_eng"]).lower() for w in _FLESH_WORDS)
        if code in seen:
            # CIQUAL 2020 lists a few codes twice (e.g. 9621 wheat bran, once
            # with no values); keep the row with more nutrients
            if len(nutrients) <= len(out[seen[code]]["nutrients"]):
                continue
            out.pop(seen[code])
            seen = {int(r["_ciqual_code"]): i for i, r in enumerate(out)}
        seen[code] = len(out)
        out.append({
            "id": f"ciqual-{code}",
            "name": str(row["alim_nom_eng"]).strip(),
            "category": str(row["alim_ssgrp_nom_eng"]),
            "nutrients": nutrients,
            "nutri_score": "", "nova": 0,
            "_names": {"en": str(row["alim_nom_eng"]).strip(), "fr": str(fr_names.get(code, "")).strip()},
            "_category_fr": str(fr_groups.get(code, "")),
            "_group": group,
            "_qualified": {k: v for k, v in qualified.items() if k not in nutrients},
            "_ciqual_code": code,
            "_is_animal": is_flesh,
            "_source": "ANSES-CIQUAL 2020",
            "_source_kind": "ciqual",
            "_source_id": "ciqual-2020",
            "_micronutrient_trusted": True,
            "_folate_is_dfe": False,
            "_vitamin_a_method": "RAE = retinol + beta-carotene/12",
            "_energy_method": energy_method,
        })
    return out


def _cli() -> None:  # pragma: no cover
    recs = records()
    OUT.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(recs)} CIQUAL foods to {OUT}")


if __name__ == "__main__":
    _cli()
