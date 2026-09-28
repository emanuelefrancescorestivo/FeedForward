"""
Canonical nutrient vocabulary and label resolution.

nutrients.json is the one place a nutrient is defined. Importers call
``resolve`` with whatever the source uses — a USDA nutrient id, an
OpenFoodFacts key, an INFOODS tagname, or a column header such as
"Fer (mg/100 g)" — and get back the engine id plus the unit the header
declared. A label that does not resolve returns None; the importer must then
skip the column and report it, never map it by guesswork.

Matching is by normalised alias, not fuzzy similarity. "Rétinol" does not
resolve to vitamin-a on purpose: retinol is one input to RAE, not RAE.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .units import UnitError, canonical_unit

_PATH = Path(__file__).resolve().parent / "nutrients.json"


@dataclass(frozen=True)
class NutrientDef:
    id: str
    unit: str
    group: str
    infoods: str | None
    names: dict[str, str]
    aliases: tuple[str, ...]
    codes: dict[str, object] = field(default_factory=dict)
    note: str = ""
    usda_sum: tuple[str, ...] = ()

    def name(self, lang: str = "en") -> str:
        return self.names.get(lang) or self.names.get("en") or self.id


@dataclass(frozen=True)
class Resolved:
    nutrient_id: str
    unit: str | None  # the unit the label declared, canonicalised; None if none


def normalize_label(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


@lru_cache(maxsize=1)
def _load() -> tuple[NutrientDef, ...]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    out = []
    for item in raw["nutrients"]:
        out.append(NutrientDef(
            id=item["id"],
            unit=canonical_unit(item["unit"]),
            group=item["group"],
            infoods=item.get("infoods"),
            names=dict(item["names"]),
            aliases=tuple(dict.fromkeys(item.get("aliases", []))),
            codes=dict(item.get("codes", {})),
            note=item.get("note", ""),
            usda_sum=tuple(item.get("usda_sum", ())),
        ))
    return tuple(out)


@lru_cache(maxsize=1)
def _indexes() -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """
    (alias index, code index). Built once; raises on an alias or code that
    points at two nutrients, because a silent last-wins would mis-map data.
    """
    aliases: dict[str, str] = {}
    codes: dict[tuple[str, str], str] = {}

    def put_alias(key: str, nid: str) -> None:
        key = normalize_label(key)
        if not key:
            return
        if aliases.get(key, nid) != nid:
            raise ValueError(f"alias {key!r} maps to {aliases[key]} and {nid}")
        aliases[key] = nid

    def put_code(source: str, code: str, nid: str) -> None:
        k = (source, str(code).strip().lower())
        if codes.get(k, nid) != nid:
            raise ValueError(f"code {k} maps to {codes[k]} and {nid}")
        codes[k] = nid

    for n in _load():
        put_alias(n.id, n.id)
        for name in n.names.values():
            put_alias(name, n.id)
        for alias in n.aliases:
            put_alias(alias, n.id)
        if n.infoods:
            put_code("infoods", n.infoods, n.id)
        for source, value in n.codes.items():
            for code in (value if isinstance(value, list) else [value]):
                put_code(source, code, n.id)
    return aliases, codes


def all_nutrients() -> tuple[NutrientDef, ...]:
    return _load()


def get(nutrient_id: str) -> NutrientDef | None:
    for n in _load():
        if n.id == nutrient_id:
            return n
    return None


def display_meta() -> dict[str, tuple[str, str]]:
    """id → (English name, canonical unit). The shape build.NUTRIENT_META had."""
    return {n.id: (n.name("en"), n.unit) for n in _load()}


def usda_direct_map() -> dict[str, str]:
    """
    FDC internal nutrient id → engine id, for nutrients stored from a single
    USDA column. Folate (DFE-or-total) and omega-3 (a sum) list several ids
    and are combined by the USDA importer, so they are excluded here.
    """
    out = {}
    for n in _load():
        ids = n.codes.get("usda") or []
        if len(ids) == 1:
            out[str(ids[0])] = n.id
    return out


def usda_preferred() -> dict[str, tuple[str, ...]]:
    """
    Nutrient id -> FDC ids in order of preference, for nutrients USDA
    publishes under more than one id (folate DFE/total, energy, sugars).
    The importer keeps the first id present; values are never added up.
    """
    out = {}
    for n in _load():
        ids = n.codes.get("usda") or []
        if len(ids) > 1:
            out[n.id] = tuple(str(i) for i in ids)
    return out


def usda_sums() -> dict[str, tuple[str, ...]]:
    """Derived nutrient id -> FDC component ids that are summed into it."""
    return {n.id: tuple(n.usda_sum) for n in _load() if n.usda_sum}


def off_keys() -> dict[str, str]:
    """OpenFoodFacts nutriment key → engine id."""
    return {str(n.codes["off"]): n.id for n in _load() if n.codes.get("off")}


_PAREN = re.compile(r"\(([^()]*)\)")
_ALTERNATIVES = re.compile(r"\s+(?:ou|or|o|oppure)\s+", re.IGNORECASE)


def split_label(label: str) -> tuple[str, str | None]:
    """
    Separate a declared unit from a column header.

    "Fer (mg/100 g)" → ("Fer", "mg"); "Energy, kcal" → ("Energy", "kcal");
    "Total lipid (fat)" → ("Total lipid (fat)", None) because "fat" is not a unit.
    """
    text = (label or "").strip()
    unit = None
    for match in _PAREN.finditer(text):
        try:
            unit = canonical_unit(match.group(1))
        except UnitError:
            continue
        text = (text[:match.start()] + text[match.end():]).strip()
        break
    if unit is None and "," in text:
        head, tail = text.rsplit(",", 1)
        try:
            unit = canonical_unit(tail)
            text = head.strip()
        except UnitError:
            pass
    return text, unit


def resolve(label: str | None = None, *, code: str | None = None,
            source: str | None = None) -> Resolved | None:
    """
    Resolve a code (with its ``source``: 'usda', 'off', 'infoods', ...) or a
    free-text label to an engine nutrient id. Returns None when nothing
    matches exactly after normalisation.
    """
    aliases, codes = _indexes()
    if code is not None:
        if source is None:
            raise ValueError("a code needs its source")
        nid = codes.get((source, str(code).strip().lower()))
        return Resolved(nid, None) if nid else None
    if not label:
        return None
    name, unit = split_label(label)
    candidates = [name]
    # "Total lipid (fat)" — a qualifier in parentheses that is not a unit.
    bare = _PAREN.sub(" ", name).strip()
    if bare != name:
        candidates.append(bare)
    # "Vitamine B9 ou Folates totaux" — either side may be the alias.
    candidates.extend(_ALTERNATIVES.split(bare))
    # "Vitamin C, total ascorbic acid" — the head is often enough.
    candidates.extend(part for part in (name.split(",")[0],) if part != name)
    for candidate in candidates:
        nid = aliases.get(normalize_label(candidate))
        if nid:
            return Resolved(nid, unit)
    return None
