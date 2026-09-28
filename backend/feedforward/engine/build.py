"""
engine/build.py
===============
Builds the FeedForward graph from foods + goal edges, with scientifically
grounded edge weights.

WEIGHT SEMANTICS (why Dijkstra "minimising" = nutrition "maximising"):
Every edge has a strength in (0, 1] and a cost of -log(strength). A path's
strength is the product of its edges' strengths, so Dijkstra's shortest path
is exactly the strongest food -> nutrient -> goal chain, and Yen's k-shortest
paths are the next-strongest chains. The strengths are defined in
engine/scoring.py:

  Food -> Nutrient
    strength = saturating share of daily need delivered by ONE reference
    portion, adjusted for bioavailability (portions.py, reference.py,
    bioavailability.py). Not normalised to the dataset maximum, so adding a
    food never changes another food's edges.

  Nutrient -> Goal
    strength = base association weight x evidence multiplier
    (evidence.py: Grade A keeps full strength, Grade D is heavily discounted)

The ranking itself combines all paths (scoring.GoalScorer); the graph gives
the explanation route for each recommendation.

Negative associations (sodium -> blood pressure) and enhancer associations
(vitamin C -> iron support) are not routes. Negatives penalise the score and
are surfaced as warnings; enhancers act through the bioavailability model and
are suggested as pairings.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .schema import Food, EvidenceGrade
from .graph import FeedForwardGraph
from .evidence import grade_for
from ..ontology.nutrients import display_meta
from .recommender import _ANIMAL_NOT_VEGAN, _MEAT_FISH, _mentions, _norm

DATA = Path(__file__).resolve().parent.parent / "data"

# Nutrient display names / units. Defined once, in ontology/nutrients.json.
NUTRIENT_META: dict[str, tuple[str, str]] = display_meta()

# Dairy and egg words (the non-flesh animal foods), matched as whole words with
# the same lists as the diet filters, so "veggie" is not an egg and "coconut
# milk" is not dairy.
_DAIRY_EGG = tuple(k for k in _ANIMAL_NOT_VEGAN if k not in ("honey", "miel"))


def _detect_anti_nutrients(text: str) -> set:
    """Detect anti-nutrient properties from food name/category keywords."""
    from .bioavailability import food_property_keywords
    props = food_property_keywords()
    found = set()
    for prop in ("phytate", "oxalate", "tannin"):
        if any(k in text for k in props.get(prop, [])):
            found.add(prop)
    return found


def _detect_enhancer_props(text: str) -> set:
    """Detect absorption-enhancer properties (caffeine, fructose, organic acid)."""
    from .bioavailability import food_property_keywords
    props = food_property_keywords()
    found = set()
    for prop in ("caffeine", "fructose", "organic_acid", "alcohol"):
        if any(k in text for k in props.get(prop, [])):
            found.add(prop)
    return found


def _enrich_food(raw: dict) -> Food:
    """Turn a raw JSON record into a Food, computing bioavailability flags."""
    text = (raw.get("name", "") + " " + raw.get("category", "")).lower()
    # Two different questions. Flesh (heme iron, the meat factor): the source's
    # animal flag, where it has one (CIQUAL and USDA flag flesh groups; the
    # curated list also flags dairy and eggs), confirmed by a meat or fish word;
    # a flag of False (tofu in CIQUAL's "meat substitute") wins. Animal-derived
    # (preformed vitamin A): flesh, or a dairy or egg word.
    words = _norm(text)
    flag = raw.get("_is_animal")          # None: the source has no flag (Open Food Facts)
    is_flesh = (flag is None or bool(flag)) and _mentions(words, _MEAT_FISH)
    is_derived = is_flesh or _mentions(words, _DAIRY_EGG)
    nutrients = raw.get("nutrients", {})
    food = Food(
        id=str(raw["id"]),
        name=raw.get("name", str(raw["id"])),
        category=raw.get("category", ""),
        nutrients=nutrients,
        nutri_score=raw.get("nutri_score", ""),
        nova=raw.get("nova", 0),
        is_animal_source=is_flesh,
        is_animal_derived=is_derived,
        contains_vitamin_c=nutrients.get("vitamin-c", 0) > 5,
        contains_fat=nutrients.get("fat", 0) > 3,
        anti_nutrients=_detect_anti_nutrients(text),
        enhancer_props=_detect_enhancer_props(text),
        source=_source_kind(raw),
    )
    from .familiarity import familiarity
    food.source_id = _source_id(raw) or {"curated": "feedforward-curated",
                                         "openfoodfacts": "openfoodfacts"}.get(food.source, "")
    food.familiarity = familiarity(food, food.source_id)
    return food


def _source_id(raw: dict) -> str:
    """sources.json id: explicit on DB records, derived from the label on JSON ones."""
    if raw.get("_source_id"):
        return raw["_source_id"]
    label = raw.get("_source", "") or ""
    if "Foundation" in label:
        return "usda-fdc-foundation"
    if "SR Legacy" in label:
        return "usda-fdc-sr-legacy"
    return ""


_SOURCE_KINDS = {"curated", "usda", "openfoodfacts", "ciqual"}


def _source_kind(raw: dict) -> str:
    """JSON records carry ``_source_kind``; database records carry ``_source``."""
    kind = raw.get("_source_kind") or raw.get("_source") or ""
    return kind if kind in _SOURCE_KINDS else ""


def _should_read_db() -> bool:
    """Opt-in. The default JSON path keeps tests and offline builds deterministic."""
    import os
    return os.getenv("FEEDFORWARD_READ_DATABASE") == "1"


def _records_from_db() -> list[dict]:
    from ..db.repository import corpus_as_records, corpus_is_seeded
    from ..db.session import get_engine
    from ..db.models import Base
    get_engine()
    Base.metadata.create_all(get_engine())
    if not corpus_is_seeded():
        raise RuntimeError(
            "Database has no foods. Run: python -m feedforward.db.seed")
    foods, _edges = corpus_as_records()
    return foods


def load_food_records(*, include_whole_foods: bool = True,
                      whole_foods_only: bool = False,
                      include_usda: bool = True,
                      include_off: bool = True,
                      include_ciqual: bool = True) -> list[dict]:
    """
    JSON seed view of the corpus, before Food enrichment.

    Order is deliberate: hand-checked whole foods, then the USDA bulk corpus
    (skipping a description we already kept), then OpenFoodFacts with
    micronutrients that failed the USDA range check removed from ``nutrients``.
    Failed OFF values stay on ``_rejected`` so they are auditable and can be
    written to the database as trusted=false.
    """
    from ..data.ingest.sanity import ranges_from_trusted, split_off_nutrients

    foods: list[dict] = []
    wf_path = DATA / "whole_foods.json"
    if (include_whole_foods or whole_foods_only) and wf_path.exists():
        for item in json.loads(wf_path.read_text(encoding="utf-8")):
            rec = dict(item)
            rec["_source_kind"] = rec.get("_source_kind", "curated")
            rec["_micronutrient_trusted"] = True
            foods.append(rec)
    if whole_foods_only:
        return foods
    # CIQUAL (ANSES): foods as eaten in France, the primary corpus for the
    # French app. Kept alongside USDA; familiarity ranks it first.
    ciqual_path = DATA / "ciqual_corpus.json"
    if include_ciqual and ciqual_path.exists():
        for item in json.loads(ciqual_path.read_text(encoding="utf-8")):
            foods.append(dict(item))
    if include_usda:
        usda_path = DATA / "usda_corpus.json"
        if usda_path.exists():
            have = {item.get("name", "").strip().lower() for item in foods}
            for item in json.loads(usda_path.read_text(encoding="utf-8")):
                if item.get("name", "").strip().lower() in have:
                    continue
                rec = dict(item)
                rec["_source_kind"] = "usda"
                rec["_micronutrient_trusted"] = True
                foods.append(rec)
                have.add(rec.get("name", "").strip().lower())
    if include_off:
        path = DATA / "foods.json"
        if path.exists():
            ranges = ranges_from_trusted(foods)
            for item in json.loads(path.read_text(encoding="utf-8")):
                foods.append(split_off_nutrients(item, ranges))
    return foods


def load_foods(path: Path | None = None, *, include_whole_foods: bool = True,
               whole_foods_only: bool = False, source: str | None = None) -> list[Food]:
    """
    Load foods for the graph.

    ``source="db"`` reads the seeded database (same record shape). Otherwise
    the versioned JSON seed is used, including the USDA bulk file when present.
    ``whole_foods_only`` still means the hand-checked 88-item reference set —
    tests that assert on that corpus must not silently pick up SR Legacy.
    """
    if source == "db" or (source is None and _should_read_db() and not whole_foods_only):
        return [_enrich_food(item) for item in _records_from_db()]
    if path is not None:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return [_enrich_food(item) for item in raw]
    return [_enrich_food(item) for item in load_food_records(
        include_whole_foods=include_whole_foods, whole_foods_only=whole_foods_only)]


def load_goal_edges(*, source: str | None = None, eu: bool = True) -> list[dict]:
    """
    Merge the edge layers, weakest first:

      scraped   Wikipedia crawl from the university project (noisy weights)
      curated   hand-reviewed, with PMIDs; overrides a scraped pair
      EU        the EU register of health claims (data/goal_edges_eu.json,
                built by data/ingest/eu_claims.py)

    EU rules (``eu=True``):
      * an authorised claim sets grade A, source ``eu_authorised`` and the
        official wording as the explanation; it adds the pair if missing.
        A curated weight is kept (hand-tuned); a scraped weight is replaced.
      * a pair EFSA found not substantiated, with no authorised claim, keeps
        its row but becomes ``type: rejected`` — metadata, never a route.
      * a scraped vitamin/mineral edge with no authorised claim is graded D:
        EFSA reviewed the functions of vitamins and minerals systematically,
        so the absence of an authorised claim is informative.
      * a curated edge with no claim keeps its grade, marked ``eu_claim: false``
        so the app does not phrase it as a health claim.

    The scraped file still contains an orphan goal id (``energy``) from the
    university crawl; analytics flags it as outside the taxonomy.
    """
    if source == "db" or (source is None and _should_read_db()):
        from ..db.repository import corpus_as_records
        _foods, edges = corpus_as_records()
        if edges:
            return edges
    scraped = json.loads((DATA / "goal_edges_scraped.json").read_text(encoding="utf-8"))["goal_edges"]
    curated = json.loads((DATA / "goal_edges_curated.json").read_text(encoding="utf-8"))["goal_edges"]
    merged: dict[tuple[str, str], dict] = {}
    for e in scraped:
        merged[(e["nutrient"], e["goal"])] = {**e, "evidence_source": "scraped"}
    for e in curated:
        merged[(e["nutrient"], e["goal"])] = {**e, "evidence_source": "curated"}
    eu_path = DATA / "goal_edges_eu.json"
    if not eu or not eu_path.exists():
        return list(merged.values())
    return _apply_eu_layer(merged, json.loads(eu_path.read_text(encoding="utf-8")))


def _apply_eu_layer(merged: dict[tuple[str, str], dict], eu: dict) -> list[dict]:
    from ..ontology.nutrients import get as nutrient_def

    authorised = set()
    for claim_edge in eu.get("goal_edges", []):
        key = (claim_edge["nutrient"], claim_edge["goal"])
        authorised.add(key)
        base = merged.get(key)
        edge = {
            "nutrient": key[0], "goal": key[1],
            "weight": claim_edge["weight"],
            "type": claim_edge.get("type", "positive"),
            "explanation": claim_edge["explanation"],
            "evidence_grade": "A", "evidence_source": "eu_authorised",
            "eu_claim": True, "eu_claims": claim_edge["claims"],
            "citations": list(claim_edge.get("citations", [])),
        }
        if base is not None:
            if base.get("evidence_source") == "curated":
                edge["weight"] = base["weight"]
            if base.get("type") == "negative":
                edge["type"] = "negative"
            edge["citations"] = edge["citations"] + [
                c for c in base.get("citations", []) if c not in edge["citations"]]
        merged[key] = edge
    for rejected in eu.get("rejected", []):
        key = (rejected["nutrient"], rejected["goal"])
        base = merged.get(key)
        if base is None or key in authorised or base.get("type") == "negative":
            continue
        # A curated grade-A association (meta-analytic consensus) outweighs a
        # rejected claim, which is often narrower than the association
        # ("endurance in the NEXT exercise bout" vs carbohydrate for endurance).
        # It stays a route; the rejection is recorded next to it.
        if base.get("evidence_source") == "curated" and \
                grade_for(key[0], key[1]).grade == EvidenceGrade.A:
            base["eu_claim"] = False
            base["eu_rejected_claim"] = (f"EFSA assessed '{'; '.join(rejected['relationships'][:2])}': "
                                         f"{rejected['reason']}.")
            continue
        merged[key] = {
            **base, "type": "rejected", "evidence_grade": "D",
            "evidence_source": "eu_rejected", "eu_claim": False,
            "explanation": (f"EFSA assessed '{'; '.join(rejected['relationships'][:2])}': "
                            f"{rejected['reason']}."),
            "citations": list(rejected.get("citations", [])),
        }
    for key, edge in merged.items():
        if key in authorised or edge.get("type") in ("rejected", "negative"):
            continue
        edge["eu_claim"] = False
        definition = nutrient_def(key[0])
        is_micronutrient = definition is not None and definition.group in ("vitamin", "mineral")
        if edge.get("evidence_source") == "scraped" and is_micronutrient:
            edge["evidence_grade"] = "D"
            edge["evidence_source"] = "scraped_unsupported"
            edge["low_confidence"] = True
    return list(merged.values())


def build_graph(foods: list[Food], goal_edges: list[dict], *,
                use_pubmed: bool = False, scorer=None) -> tuple[FeedForwardGraph, dict]:
    """
    Build the weighted graph. Returns the graph plus a metadata dict with the
    per-edge evidence (``edges``) and the ``scorer`` that defines the weights,
    so the recommender ranks with exactly the strengths the graph encodes.
    """
    from .scoring import GoalScorer

    if scorer is None:
        scorer = GoalScorer(goal_edges, edge_grade=lambda e: edge_grade(e, use_pubmed))
    g = FeedForwardGraph()
    edge_meta: dict[tuple[str, str], dict] = {}
    linked = {e["nutrient"] for e in goal_edges if e.get("type", "positive") == "positive"}

    # --- Food -> Nutrient edges (portion delivery x bioavailability) ---
    for food in foods:
        g.add_node(food.id, node_type="food", name=food.name)
        for nutrient in food.nutrients:
            if nutrient not in linked:
                continue
            delivery = scorer.delivery(food, nutrient)
            if delivery is None or delivery.strength <= 0:
                continue
            g.add_node(nutrient, node_type="nutrient", name=nname_for(nutrient))
            g.add_edge(food.id, nutrient, -math.log(delivery.strength))

    # --- Nutrient -> Goal edges (association x evidence) ---
    for edge in goal_edges:
        nutrient = edge["nutrient"]
        goal = edge["goal"]
        base_weight = float(edge["weight"])
        edge_type = edge.get("type", "positive")
        g.add_node(goal, node_type="goal", name=goal.replace("_", " ").title())
        g.add_node(nutrient, node_type="nutrient", name=nname_for(nutrient))

        eu_fields = {
            "evidence_source": edge.get("evidence_source", ""),
            "eu_claim": bool(edge.get("eu_claim", False)),
            "eu_claims": list(edge.get("eu_claims", [])),
        }
        if edge_type == "negative":
            edge_meta[(nutrient, goal)] = {
                "evidence": edge.get("evidence_grade", "n/a"), "edge_type": "negative",
                "base_weight": base_weight,
                "explanation": edge.get("explanation",
                                        f"{nutrient} is negatively associated with {goal}."),
                "citations": list(edge.get("citations", [])),
                **eu_fields,
            }
            continue

        grade, citations, n_studies = _edge_grade(edge, use_pubmed)
        meta = {
            "evidence": grade.value,
            "evidence_label": grade.label,
            "consumer_label": grade.consumer_label,
            "edge_type": edge_type,
            "base_weight": base_weight,
            "citations": citations,
            "n_studies": n_studies,
            "low_confidence": bool(edge.get("low_confidence", False)) or (
                grade.value == "D" and not citations),
            "explanation": edge.get(
                "explanation",
                f"{nname_for(nutrient)} supports {goal.replace('_', ' ')}."),
            **eu_fields,
        }
        edge_meta[(nutrient, goal)] = meta
        if edge_type in ("enhancer", "rejected"):
            continue
        strength = base_weight * grade.multiplier
        if strength > 0:
            g.add_edge(nutrient, goal, -math.log(min(strength, 1.0)))

    return g, {"edges": {f"{n}->{gl}": m for (n, gl), m in edge_meta.items()},
               "scorer": scorer, "goal_edges": goal_edges}


def nname_for(nutrient: str) -> str:
    return NUTRIENT_META.get(nutrient, (nutrient, ""))[0]


def _edge_grade(edge: dict, use_pubmed: bool = False) -> tuple[EvidenceGrade, list[str], int | None]:
    """
    The edge's own grade when a layer fixed one (EU register: A; unsupported
    scraped micronutrient: D; rejected: D), else the curated/PubMed grade.
    Citations from the edge (EFSA opinions) come first.
    """
    assessment = grade_for(edge["nutrient"], edge["goal"], use_pubmed=use_pubmed)
    fixed = edge.get("evidence_grade")
    if fixed in ("A", "B", "C", "D"):
        grade = EvidenceGrade(fixed)
    else:
        grade = assessment.grade
    citations = list(edge.get("citations", []))
    if edge.get("evidence_source") not in ("eu_rejected", "scraped_unsupported"):
        citations += [c for c in assessment.citations if c not in citations]
    return grade, citations, assessment.n_studies


def edge_grade(edge: dict, use_pubmed: bool = False) -> EvidenceGrade:
    return _edge_grade(edge, use_pubmed)[0]
