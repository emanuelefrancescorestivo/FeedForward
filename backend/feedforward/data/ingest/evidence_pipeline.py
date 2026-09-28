"""
Batch PubMed grading for goal edges that the curated table does not override.

Curated grades always win (see engine/evidence.py). This script fills the
remaining positive edges — the ones that would otherwise stay at the Grade C
default — with counts and PMIDs returned by NCBI. It does not grade pairs we
do not claim. A search for an unrelated nutrient×goal pair can return a
count; that count is not evidence for a recommendation we are not making.

PMIDs written here are the idlist from esearch. They are representative hits
for the query, not a hand-picked bibliography, and the file says so.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ...engine.evidence import CURATED, grade_from_pubmed

OUT = Path(__file__).resolve().parent.parent / "evidence_pubmed.json"
CURATED_EDGES = Path(__file__).resolve().parent.parent / "goal_edges_curated.json"


def pairs_to_grade() -> list[tuple[str, str]]:
    """
    Curated edges without a hand-reviewed grade.

    The scraped Wikipedia file is not graded here. A loose query such as
    "iron AND digestive health" can return a large count that does not
    support that edge, and promoting it above Grade C would lower the bar.
    Those edges stay at the default until a person reviews them.
    """
    edges = json.loads(CURATED_EDGES.read_text(encoding="utf-8"))["goal_edges"]
    pairs = []
    for edge in edges:
        if edge.get("type", "positive") != "positive":
            continue
        if edge.get("low_confidence"):
            continue
        key = (edge["nutrient"], edge["goal"])
        if key in CURATED or key in pairs:
            continue
        pairs.append(key)
    return pairs


def run(*, sleep: float = 0.4) -> dict:
    grades = {}
    if OUT.exists():
        try:
            grades = json.loads(OUT.read_text(encoding="utf-8")).get("grades", {})
        except json.JSONDecodeError:
            grades = {}
    for nutrient, goal in pairs_to_grade():
        key = f"{nutrient}|{goal}"
        if key in grades:
            continue
        assessment = grade_from_pubmed(nutrient, goal, sleep=sleep)
        # grade_from_pubmed falls back to curated/default and labels the source.
        # Only persist a grade that actually came back from NCBI.
        if assessment.source != "pubmed":
            continue
        grades[key] = {
            "grade": assessment.grade.value,
            "n_studies": assessment.n_studies,
            "n_rct_or_meta": assessment.n_rct_or_meta,
            "citations": assessment.citations,
            "query": assessment.query,
            "note": ("PMIDs are the first esearch hits for this query, not a "
                     "curated bibliography. The curated table overrides this file."),
        }
        OUT.write_text(json.dumps({
            "_comment": ("Automated PubMed grades for goal edges without a "
                         "curated override. Do not hand-edit PMIDs in this file."),
            "grades": grades,
        }, indent=2), encoding="utf-8")
        print(f"{key}: {assessment.grade.value} n={assessment.n_studies} "
              f"rct={assessment.n_rct_or_meta}")
    return grades


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Grade uncurated goal edges from PubMed.")
    parser.parse_args()
    grades = run()
    print(f"Wrote {len(grades)} grades to {OUT}")


if __name__ == "__main__":
    _cli()
