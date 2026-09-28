"""
Read and write the corpus and the user store.

The engine never imports this module. ``engine/build.py`` calls
``corpus_as_records`` only when a database URL is configured and the foods
table has rows. The records it returns are the same dict shape the JSON
loader already produced, so ``_enrich_food`` and ``build_graph`` do not change.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import (
    EvidenceCitationRow, FoodNameRow, FoodNutrientRow, FoodRow, GoalEdgeRow, GoalRow,
    InteractionRow, NutrientAliasRow, NutrientRow, SourceRow, UserRow,
)
from .session import session_scope


@dataclass
class StoredUser:
    email: str
    password_hash: str
    tier: str = "consumer"
    id: int | None = None
    demographic: str | None = None
    dietary_restrictions: list[str] = field(default_factory=list)
    created_at: datetime | None = None


def _loads_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _user_from_row(row: UserRow) -> StoredUser:
    return StoredUser(
        email=row.email,
        password_hash=row.password_hash,
        tier=row.tier,
        id=row.id,
        demographic=row.demographic,
        dietary_restrictions=[str(x) for x in _loads_list(row.dietary_restrictions)],
        created_at=row.created_at,
    )


def corpus_is_seeded(session: Session | None = None) -> bool:
    def _count(s: Session) -> int:
        return s.scalar(select(func.count()).select_from(FoodRow)) or 0

    if session is not None:
        return _count(session) > 0
    with session_scope() as s:
        return _count(s) > 0


def corpus_as_records(session: Session | None = None) -> tuple[list[dict], list[dict]]:
    """
    Foods and goal edges in the JSON shapes ``load_foods`` / ``load_goal_edges``
    already return. Untrusted nutrient rows are omitted from ``nutrients`` —
    they stay in the table for audit, and ``_rejected_nutrients`` names them
    so a profile can say a value was withheld rather than silently missing.
    """
    def _load(s: Session) -> tuple[list[dict], list[dict]]:
        foods = s.scalars(select(FoodRow).options(selectinload(FoodRow.nutrients))).all()
        records = []
        for food in foods:
            nutrients = {}
            rejected = []
            below_detection = []
            for row in food.nutrients:
                if not row.trusted:
                    rejected.append(row.nutrient_id)
                elif (row.value_qualifier or "exact") != "exact":
                    # "< 0,5" or "traces": kept in the table, never an edge.
                    below_detection.append(row.nutrient_id)
                else:
                    nutrients[row.nutrient_id] = row.amount_per_100g
            records.append({
                "id": food.id,
                "name": food.name,
                "category": food.category,
                "nutrients": nutrients,
                "nutri_score": food.nutri_score or "",
                "nova": food.nova or 0,
                "_is_animal": food.is_animal_source,
                "_source": food.source,
                "_micronutrient_trusted": food.micronutrient_trusted,
                "_rejected_nutrients": rejected,
                "_below_detection": below_detection,
                "_barcode": food.barcode,
                "_source_id": food.source_id,
            })
        edges = []
        for edge in s.scalars(
                select(GoalEdgeRow).options(selectinload(GoalEdgeRow.citations))).all():
            item = {
                "nutrient": edge.nutrient_id,
                "goal": edge.goal_id,
                "weight": edge.weight,
                "type": edge.edge_type,
                "explanation": edge.explanation or "",
                "evidence_source": edge.evidence_source or "",
                "eu_claim": edge.evidence_source == "eu_authorised",
                "citations": [c.citation_text for c in edge.citations if c.citation_text],
            }
            if edge.evidence_grade:
                item["evidence_grade"] = edge.evidence_grade
            if edge.low_confidence:
                item["low_confidence"] = True
            edges.append(item)
        return records, edges

    if session is not None:
        return _load(session)
    with session_scope() as s:
        return _load(s)


def interactions_as_records(session: Session | None = None) -> list[dict]:
    def _load(s: Session) -> list[dict]:
        rows = s.scalars(
            select(InteractionRow).options(selectinload(InteractionRow.citations))
        ).all()
        out = []
        for row in rows:
            cites = []
            for c in row.citations:
                if c.pmid:
                    cites.append(f"PMID:{c.pmid}")
            item = {
                "target": row.target,
                "modifier": row.modifier,
                "direction": row.direction,
                "factor": row.factor,
                "mechanism": row.mechanism,
                "evidence": row.evidence,
                "citations": cites,
            }
            if row.dose_note:
                item["dose_note"] = row.dose_note
            if row.low_confidence:
                item["low_confidence"] = True
            out.append(item)
        return out

    if session is not None:
        return _load(session)
    with session_scope() as s:
        return _load(s)


def upsert_nutrient(session: Session, nutrient_id: str, name: str, unit: str) -> None:
    row = session.get(NutrientRow, nutrient_id)
    if row is None:
        session.add(NutrientRow(id=nutrient_id, name=name, unit=unit))
    else:
        row.name = name
        row.unit = unit


def replace_corpus(session: Session, *, foods: list[dict], edges: list[dict],
                   goals: list[dict], nutrients: dict[str, tuple[str, str]],
                   interactions: list[dict], sources: list[dict] | None = None,
                   ontology=None) -> dict[str, int]:
    """
    Replace the scientific tables from the versioned JSON seed. Users are
    left alone. This is the migration path from the flat files: the files
    remain the auditable source, the database is what the API reads.

    ``sources`` are provenance rows (data/sources.json); a food names its
    row with ``_source_id``. ``ontology`` is ontology.nutrients.all_nutrients();
    when given, nutrients get their INFOODS tag, group, names and aliases.

    food_concepts is not touched: concept links carry human review and are
    re-attached by the matcher, not by a reseed.

    Optional per-food provenance keys:
      ``_original_units``  {nutrient: [amount, unit]} as published, when converted
      ``_qualified``       {nutrient: [amount|None, qualifier]} for non-exact cells
      ``_name_lang``       language of ``name``; ``_names`` {lang: name}
    """
    session.query(EvidenceCitationRow).delete()
    session.query(FoodNameRow).delete()
    session.query(FoodNutrientRow).delete()
    session.query(GoalEdgeRow).delete()
    session.query(InteractionRow).delete()
    session.query(FoodRow).delete()
    session.query(GoalRow).delete()
    session.query(NutrientAliasRow).delete()
    session.query(NutrientRow).delete()
    session.query(SourceRow).delete()
    session.flush()

    for src in sources or []:
        session.add(SourceRow(
            id=src["id"], kind=src["kind"], name=src["name"],
            version=src.get("version") or "", licence=src.get("licence") or "",
            url=src.get("url"), country=src.get("country"),
        ))
    session.flush()

    defs = {n.id: n for n in (ontology or ())}
    for nid, (name, unit) in nutrients.items():
        definition = defs.get(nid)
        session.add(NutrientRow(
            id=nid, name=name, unit=unit,
            infoods_tag=definition.infoods if definition else None,
            nutrient_group=definition.group if definition else "",
        ))
    session.flush()
    if defs:
        session.bulk_insert_mappings(NutrientAliasRow, _alias_rows(defs.values(), set(nutrients)))
    # Nutrients that appear on foods but are not in the display table still
    # need a row, or the foreign key fails.
    seen = set(nutrients)
    for food in foods:
        for nid in food.get("nutrients", {}):
            if nid not in seen:
                session.add(NutrientRow(id=nid, name=nid, unit=""))
                seen.add(nid)
        for nid in food.get("_rejected", {}):
            if nid not in seen:
                session.add(NutrientRow(id=nid, name=nid, unit=""))
                seen.add(nid)
    for edge in edges:
        if edge["nutrient"] not in seen:
            session.add(NutrientRow(id=edge["nutrient"], name=edge["nutrient"], unit=""))
            seen.add(edge["nutrient"])
    session.flush()

    for goal in goals:
        session.add(GoalRow(
            id=goal["id"], label=goal["label"], system=goal["system"],
            description=goal.get("description", ""),
            icd10_refs=json.dumps(goal.get("icd10_refs", [])),
        ))
    session.flush()

    for food in foods:
        session.add(FoodRow(
            id=str(food["id"]),
            name=food.get("name", str(food["id"])),
            category=food.get("category", ""),
            source=food.get("_source_kind", "curated"),
            external_id=food.get("_external_id"),
            nutri_score=food.get("nutri_score", "") or "",
            nova=int(food.get("nova") or 0),
            is_animal_source=food.get("_is_animal"),
            micronutrient_trusted=bool(food.get("_micronutrient_trusted", False)),
            barcode=food.get("_barcode"),
            source_id=food.get("_source_id"),
            name_lang=food.get("_name_lang", "") or "",
        ))
    session.flush()

    name_rows = []
    for food in foods:
        names = dict(food.get("_names") or {})
        lang = food.get("_name_lang")
        if lang and lang not in names:
            names[lang] = food.get("name", "")
        for lang_code, text in names.items():
            if text:
                name_rows.append({"food_id": str(food["id"]), "lang": lang_code, "name": text})
    if name_rows:
        session.bulk_insert_mappings(FoodNameRow, name_rows)

    nutrient_rows = []
    for food in foods:
        fid = str(food["id"])
        source = food.get("_source_kind", "curated")
        originals = food.get("_original_units") or {}
        for nid, amount in food.get("nutrients", {}).items():
            original = originals.get(nid)
            nutrient_rows.append({
                "food_id": fid, "nutrient_id": nid,
                "amount_per_100g": float(amount),
                "unit": nutrients.get(nid, ("", ""))[1],
                "trusted": True, "reject_reason": "", "source": source,
                "value_qualifier": "exact",
                "original_amount": float(original[0]) if original else None,
                "original_unit": original[1] if original else "",
            })
        for nid, (bound, qualifier) in (food.get("_qualified") or {}).items():
            if nid in food.get("nutrients", {}):
                continue
            nutrient_rows.append({
                "food_id": fid, "nutrient_id": nid,
                "amount_per_100g": float(bound or 0.0),
                "unit": nutrients.get(nid, ("", ""))[1],
                "trusted": True, "reject_reason": "", "source": source,
                "value_qualifier": qualifier,
                "original_amount": None, "original_unit": "",
            })
        for nid, reason in food.get("_rejected", {}).items():
            original = originals.get(nid)
            nutrient_rows.append({
                "food_id": fid, "nutrient_id": nid,
                "amount_per_100g": float(food.get("_rejected_amounts", {}).get(nid, 0)),
                "unit": nutrients.get(nid, ("", ""))[1],
                "trusted": False, "reject_reason": reason, "source": source,
                "value_qualifier": "exact",
                "original_amount": float(original[0]) if original else None,
                "original_unit": original[1] if original else "",
            })
    if nutrient_rows:
        session.bulk_insert_mappings(FoodNutrientRow, nutrient_rows)

    for edge in edges:
        session.add(GoalEdgeRow(
            nutrient_id=edge["nutrient"],
            goal_id=edge["goal"],
            weight=float(edge["weight"]),
            edge_type=edge.get("type", "positive"),
            explanation=edge.get("explanation", ""),
            evidence_source=edge.get("evidence_source", "default"),
            evidence_grade=edge.get("evidence_grade"),
            low_confidence=bool(edge.get("low_confidence", False)),
        ))
    session.flush()

    edge_ids = {
        (e.nutrient_id, e.goal_id): e.id for e in session.scalars(select(GoalEdgeRow))
    }
    for edge in edges:
        for cite in edge.get("citations", []):
            # PMIDs, and EFSA opinions for edges from the EU register. Both
            # come from an authoritative source, never generated.
            pmid = _pmid(cite)
            is_efsa = cite.startswith("EFSA")
            if not pmid and not is_efsa:
                continue
            session.add(EvidenceCitationRow(
                pmid=pmid, source="efsa" if is_efsa else edge.get("evidence_source", "curated"),
                verified=True, citation_text=cite,
                goal_edge_id=edge_ids.get((edge["nutrient"], edge["goal"])),
            ))

    for inter in interactions:
        row = InteractionRow(
            target=inter["target"], modifier=inter["modifier"],
            direction=inter["direction"], factor=float(inter["factor"]),
            mechanism=inter.get("mechanism", ""),
            evidence=inter.get("evidence", "C"),
            dose_note=inter.get("dose_note", ""),
            low_confidence=bool(inter.get("low_confidence", not inter.get("citations"))),
        )
        session.add(row)
        session.flush()
        for cite in inter.get("citations", []):
            pmid = _pmid(cite)
            if not pmid:
                continue
            session.add(EvidenceCitationRow(
                pmid=pmid, source="interaction", verified=True,
                citation_text=cite, interaction_id=row.id,
            ))

    return {
        "foods": len(foods),
        "edges": len(edges),
        "interactions": len(interactions),
    }


def _alias_rows(definitions, known_ids: set[str]) -> list[dict]:
    """Names, aliases and codes for the nutrient_aliases table, de-duplicated."""
    from ..ontology.nutrients import normalize_label

    rows: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(nid: str, alias: str, kind: str, lang: str = "", source: str = "") -> None:
        norm = normalize_label(alias) if kind != "code" else str(alias).strip().lower()
        key = (kind, source, lang, norm)
        if not norm or key in seen:
            return
        seen.add(key)
        rows.append({"nutrient_id": nid, "alias": str(alias), "alias_norm": norm,
                     "kind": kind, "lang": lang, "source": source})

    for n in definitions:
        if n.id not in known_ids:
            continue
        for lang, name in n.names.items():
            add(n.id, name, "name", lang=lang)
        for alias in n.aliases:
            add(n.id, alias, "alias")
        if n.infoods:
            add(n.id, n.infoods, "code", source="infoods")
        for source, value in n.codes.items():
            for code in (value if isinstance(value, list) else [value]):
                add(n.id, code, "code", source=source)
    return rows


def _pmid(cite: str) -> str | None:
    text = cite.strip()
    if text.upper().startswith("PMID:"):
        text = text.split(":", 1)[1]
    return text if text.isdigit() else None


def create_stored_user(email: str, password_hash: str, tier: str = "consumer") -> StoredUser:
    """``password_hash`` is already hashed. Hashing stays in api/auth.py."""
    email = email.strip().lower()
    with session_scope() as s:
        existing = s.scalar(select(UserRow).where(UserRow.email == email))
        if existing:
            raise ValueError("exists")
        row = UserRow(
            email=email, password_hash=password_hash, tier=tier,
            dietary_restrictions="[]",
        )
        s.add(row)
        s.flush()
        return _user_from_row(row)


def user_password_hash(email: str) -> str | None:
    with session_scope() as s:
        row = s.scalar(select(UserRow).where(UserRow.email == email.strip().lower()))
        return row.password_hash if row else None


def get_user(email: str) -> StoredUser | None:
    with session_scope() as s:
        row = s.scalar(select(UserRow).where(UserRow.email == email.strip().lower()))
        return _user_from_row(row) if row else None


def update_profile(email: str, *, demographic: str | None = None,
                   dietary_restrictions: list[str] | None = None,
                   tier: str | None = None) -> StoredUser | None:
    with session_scope() as s:
        row = s.scalar(select(UserRow).where(UserRow.email == email.strip().lower()))
        if row is None:
            return None
        if demographic is not None:
            row.demographic = demographic
        if dietary_restrictions is not None:
            row.dietary_restrictions = json.dumps(list(dietary_restrictions))
        if tier is not None:
            row.tier = tier
        row.updated_at = datetime.now(timezone.utc)
        s.flush()
        return _user_from_row(row)


def delete_user(email: str) -> bool:
    with session_scope() as s:
        row = s.scalar(select(UserRow).where(UserRow.email == email.strip().lower()))
        if row is None:
            return False
        s.delete(row)
        return True


def export_user(email: str) -> dict | None:
    user = get_user(email)
    if user is None:
        return None
    return {
        "email": user.email,
        "tier": user.tier,
        "demographic": user.demographic,
        "dietary_restrictions": user.dietary_restrictions,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
