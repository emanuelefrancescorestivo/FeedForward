"""
engine/evidence.py
==================
Evidence grading for nutrient -> goal associations.

Every edge in the FeedForward graph carries an EvidenceGrade (A-D). This module
is responsible for *assigning* those grades. It has two modes:

  1. CURATED (default, offline): a hand-maintained table of grades with
     representative citations. Deterministic, fast, works with no network —
     this is what ships in tests and what the app falls back to.

  2. PUBMED (opt-in, online): queries the NCBI E-utilities API to count and
     classify the literature for a (nutrient, goal) pair, then derives a grade
     from the volume and study types found. Results are cached to disk so we
     never hammer the API and so builds stay reproducible.

The two modes share one output contract: ``grade_for(nutrient, goal) ->
EvidenceAssessment``. The rest of the engine never needs to know which mode
produced the grade.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .schema import EvidenceGrade


NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "pubmed_cache.json"


@dataclass
class EvidenceAssessment:
    grade: EvidenceGrade
    n_studies: int
    n_rct_or_meta: int
    citations: list[str]
    source: str            # "curated" | "pubmed" | "pubmed+curated"
    query: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["grade"] = self.grade.value
        return d


# ---------------------------------------------------------------------------
# Curated evidence table
# ---------------------------------------------------------------------------
# Grades reflect the strength of the mechanistic + trial literature for each
# association as of the project's knowledge cutoff. Citations are representative
# anchors (PMIDs), not the full evidence base.
CURATED: dict[tuple[str, str], EvidenceAssessment] = {
    ("iron", "iron_support"): EvidenceAssessment(
        EvidenceGrade.A, 500, 120, ["PMID:19260872", "PMID:33096647"], "curated"),
    ("vitamin-c", "iron_support"): EvidenceAssessment(
        EvidenceGrade.A, 200, 40, ["PMID:2507711", "PMID:20200263"], "curated"),
    ("vitamin-c", "immune_support"): EvidenceAssessment(
        EvidenceGrade.B, 150, 30, ["PMID:29099763"], "curated"),
    ("calcium", "bone_health"): EvidenceAssessment(
        EvidenceGrade.A, 400, 90, ["PMID:25278298"], "curated"),
    ("vitamin-d", "bone_health"): EvidenceAssessment(
        EvidenceGrade.A, 450, 110, ["PMID:24239701"], "curated"),
    ("proteins", "muscle_recovery"): EvidenceAssessment(
        EvidenceGrade.A, 300, 80, ["PMID:28642676"], "curated"),
    ("proteins", "recovery"): EvidenceAssessment(
        EvidenceGrade.B, 200, 45, ["PMID:28642676"], "curated"),
    ("omega-3-fat", "heart_health"): EvidenceAssessment(
        EvidenceGrade.B, 350, 70, ["PMID:30103071"], "curated"),
    ("omega-3-fat", "anti_inflammatory"): EvidenceAssessment(
        EvidenceGrade.B, 180, 35, ["PMID:26545825"], "curated"),
    ("fiber", "digestive_health"): EvidenceAssessment(
        EvidenceGrade.A, 300, 60, ["PMID:23609775"], "curated"),
    ("fiber", "gut_microbiome"): EvidenceAssessment(
        EvidenceGrade.B, 150, 25, ["PMID:29902436"], "curated"),
    ("fiber", "blood_sugar_regulation"): EvidenceAssessment(
        EvidenceGrade.B, 200, 40, ["PMID:23786819"], "curated"),
    ("magnesium", "sleep_support"): EvidenceAssessment(
        EvidenceGrade.C, 60, 8, ["PMID:23853635"], "curated"),
    ("magnesium", "stress_resilience"): EvidenceAssessment(
        EvidenceGrade.C, 70, 10, ["PMID:28241991"], "curated"),
    ("zinc", "immune_support"): EvidenceAssessment(
        EvidenceGrade.B, 160, 35, ["PMID:28515951"], "curated"),
    ("vitamin-a", "vision_support"): EvidenceAssessment(
        EvidenceGrade.A, 220, 50, ["PMID:22133051"], "curated"),
    ("vitamin-e", "antioxidant_support"): EvidenceAssessment(
        EvidenceGrade.C, 120, 20, ["PMID:17999776"], "curated"),
    ("vitamin-k", "bone_health"): EvidenceAssessment(
        EvidenceGrade.C, 90, 15, ["PMID:23018678"], "curated"),
    ("carbohydrates", "energy_metabolism"): EvidenceAssessment(
        EvidenceGrade.B, 100, 20, [], "curated"),
    ("carbohydrates", "endurance_support"): EvidenceAssessment(
        EvidenceGrade.A, 250, 70, ["PMID:24791914"], "curated"),
    # Added when the last unwired goals were connected. PMIDs were taken from
    # NCBI esearch/esummary titles that match the claim (see CHANGELOG). Grades
    # are deliberately not upgraded to A where the trials are in a disease
    # population or the effect size is small — the edge weight carries that.
    ("potassium", "blood_pressure_support"): EvidenceAssessment(
        EvidenceGrade.A, 197, 40, ["PMID:32500831"], "curated"),
    ("magnesium", "blood_pressure_support"): EvidenceAssessment(
        EvidenceGrade.B, 21, 12, ["PMID:27402922", "PMID:39280209"], "curated"),
    ("calcium", "blood_pressure_support"): EvidenceAssessment(
        EvidenceGrade.B, 44, 15, ["PMID:16673011"], "curated"),
    ("omega-3-fat", "joint_health"): EvidenceAssessment(
        EvidenceGrade.B, 28, 10, ["PMID:22835600", "PMID:38922552"], "curated"),
    ("vitamin-c", "joint_health"): EvidenceAssessment(
        EvidenceGrade.C, 1, 1, ["PMID:27852613"], "curated"),
    ("manganese", "joint_health"): EvidenceAssessment(
        EvidenceGrade.D, 0, 0, [], "curated",
        query="mechanistic cofactor; no verified citation attached"),
    ("magnesium", "metabolic_support"): EvidenceAssessment(
        EvidenceGrade.B, 35, 12, ["PMID:27329332", "PMID:34836329"], "curated"),
    ("fiber", "metabolic_support"): EvidenceAssessment(
        EvidenceGrade.B, 28, 8, ["PMID:29278406", "PMID:29137803"], "curated"),
    ("omega-3-fat", "metabolic_support"): EvidenceAssessment(
        EvidenceGrade.B, 35, 10, ["PMID:31010701", "PMID:28684692"], "curated"),
    ("selenium", "thyroid_support"): EvidenceAssessment(
        EvidenceGrade.C, 22, 8, ["PMID:38243784"], "curated",
        query="trial evidence is in autoimmune thyroiditis, not a general treatment claim"),
}


def _default_grade(nutrient: str, goal: str) -> EvidenceAssessment:
    """When we have no specific record, assume limited (Grade C) evidence."""
    return EvidenceAssessment(
        EvidenceGrade.C, 0, 0, [], "curated",
        query=f"{nutrient} + {goal} (no specific record)")


# ---------------------------------------------------------------------------
# PubMed grading (opt-in)
# ---------------------------------------------------------------------------
def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, indent=2))


def _grade_from_counts(total: int, rct_meta: int) -> EvidenceGrade:
    """
    Derive a grade from literature volume and the amount of high-tier evidence.
    Thresholds are intentionally conservative and documented so they can be
    tuned against expert review.
    """
    if rct_meta >= 40 and total >= 150:
        return EvidenceGrade.A
    if rct_meta >= 10 and total >= 40:
        return EvidenceGrade.B
    if total >= 10:
        return EvidenceGrade.C
    return EvidenceGrade.D


def grade_from_pubmed(nutrient: str, goal: str, *, api_key: str | None = None,
                      sleep: float = 0.4) -> EvidenceAssessment:
    """
    Query PubMed for the (nutrient, goal) pair and derive an evidence grade.

    Requires the ``requests`` package and network access to eutils.ncbi.nlm.nih.gov.
    Results are cached to disk keyed by the query. On any failure we fall back
    to the curated grade so the engine degrades gracefully.
    """
    goal_terms = goal.replace("_", " ")
    base_term = f'{nutrient.replace("-", " ")} AND {goal_terms}'
    cache = _load_cache()
    if base_term in cache:
        d = cache[base_term]
        return EvidenceAssessment(EvidenceGrade(d["grade"]), d["n_studies"],
                                  d["n_rct_or_meta"], d["citations"],
                                  "pubmed", base_term)

    try:
        import requests  # local import: only needed in online mode
    except ImportError:
        return grade_for(nutrient, goal, use_pubmed=False)

    def _count(term: str) -> tuple[int, list[str]]:
        params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": 5}
        if api_key:
            params["api_key"] = api_key
        r = requests.get(NCBI_ESEARCH, params=params, timeout=15)
        r.raise_for_status()
        js = r.json().get("esearchresult", {})
        return int(js.get("count", 0)), js.get("idlist", [])

    try:
        total, ids = _count(base_term)
        time.sleep(sleep)
        filt = ('(systematic review[pt] OR meta-analysis[pt] OR '
                'randomized controlled trial[pt])')
        rct_meta, _ = _count(f"({base_term}) AND {filt}")
        grade = _grade_from_counts(total, rct_meta)
        citations = [f"PMID:{i}" for i in ids]
        assessment = EvidenceAssessment(grade, total, rct_meta, citations,
                                        "pubmed", base_term)
        cache[base_term] = assessment.to_dict()
        _save_cache(cache)
        return assessment
    except Exception:
        # Network/parse failure -> curated fallback, clearly labelled
        fallback = grade_for(nutrient, goal, use_pubmed=False)
        fallback.source = "pubmed+curated"
        return fallback


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------
_PUBMED_TABLE = Path(__file__).resolve().parent.parent / "data" / "evidence_pubmed.json"


def _pubmed_table() -> dict[tuple[str, str], EvidenceAssessment]:
    """
    Committed PubMed grades. Curated entries override these — the file is the
    automated layer, not a replacement for the hand-reviewed table.

    Only pairs we actually claim (goal edges) are graded. A cartesian product
    of unrelated nutrient×goal queries would attach a grade to a search that
    is not a claim, which is a lower bar, not a higher one.
    """
    if not _PUBMED_TABLE.exists():
        return {}
    try:
        raw = json.loads(_PUBMED_TABLE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    # A broad query ("protein AND energy metabolism") can return hundreds of
    # thousands of hits and a Grade A under the volume thresholds. That is not
    # a grade of the association. Rows affect the graph only after a person
    # sets accepted=true on the file. Until then they are a research log.
    if raw.get("accepted") is not True:
        return {}
    out = {}
    for key, d in raw.get("grades", {}).items():
        if "|" not in key:
            continue
        nutrient, goal = key.split("|", 1)
        out[(nutrient, goal)] = EvidenceAssessment(
            EvidenceGrade(d["grade"]), d.get("n_studies", 0),
            d.get("n_rct_or_meta", 0), d.get("citations", []),
            "pubmed", d.get("query", key))
    return out


def grade_for(nutrient: str, goal: str, *, use_pubmed: bool = False,
              api_key: str | None = None) -> EvidenceAssessment:
    """
    Return the evidence assessment for a (nutrient, goal) pair.

    Lookup order, whether or not a live query is requested:
      1. Curated table — hand-reviewed override, always wins.
      2. Committed PubMed grades (``evidence_pubmed.json``), or a live query
         when ``use_pubmed=True`` and the pair is not curated.
      3. Grade C default, labelled as having no specific record.

    ``use_pubmed=False`` (default): deterministic curated grade, then the
    committed PubMed file, then Grade C.
    ``use_pubmed=True``: live PubMed grading with curated fallback.
    """
    curated = CURATED.get((nutrient, goal))
    if curated:
        return curated
    if use_pubmed:
        return grade_from_pubmed(nutrient, goal, api_key=api_key)
    cached = _pubmed_table().get((nutrient, goal))
    if cached:
        return cached
    return _default_grade(nutrient, goal)
