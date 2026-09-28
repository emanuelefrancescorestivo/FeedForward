"""
Sanity benchmark for goal rankings.

Scores a Recommender against data/benchmark_goals.json: for each goal, what
share of the top-k are textbook sources ("hit rate") and how many are foods
that should not be there ("implausible"). It is a regression guard for the
ranking, not a validation of the science — the keyword lists are written by
the developers and are meant to be replaced by dietitian-reviewed ones.

    python -m feedforward.engine.benchmark            # print the report
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "data" / "benchmark_goals.json"


# Phrases that contain an implausible keyword but say the opposite.
_NEGATED = ("without salt", "no salt added", "unsalted", "low salt", "reduced salt",
            "low sodium", "sans sel", "sans sucres ajoutés", "no sugar added")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return text


def _strip_negated(text: str) -> str:
    for phrase in _NEGATED:
        text = text.replace(phrase, " ")
    return text


@dataclass
class GoalResult:
    key: str
    hit_rate: float
    implausible: list[str] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)
    top: list[str] = field(default_factory=list)


def load_spec(path: Path = _PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(engine, spec: dict | None = None) -> dict[str, GoalResult]:
    spec = spec or load_spec()
    k = int(spec.get("k", 20))
    out: dict[str, GoalResult] = {}
    for key, case in spec["goals"].items():
        goal = case.get("goal", key)
        recs = engine.foods_for_goal(goal, constraints=case.get("constraints", []),
                                     k=k, explain=False)
        expected = [_norm(w) for w in case["expected"]]
        bad = [_norm(w) for w in case.get("implausible", [])]
        names = [r.food_name for r in recs]
        hits, implausible, misses = 0, [], []
        for name in names:
            low = _norm(name)
            if any(w in _strip_negated(low) for w in bad):
                implausible.append(name)
            elif any(w in low for w in expected):
                hits += 1
            else:
                misses.append(name)
        out[key] = GoalResult(key, hits / k if k else 0.0, implausible, misses, names)
    return out


def summary(results: dict[str, GoalResult]) -> dict[str, float]:
    n = len(results) or 1
    return {
        "mean_hit_rate": round(sum(r.hit_rate for r in results.values()) / n, 3),
        "implausible_total": sum(len(r.implausible) for r in results.values()),
    }


def _main() -> None:
    import sys
    from . import build_engine
    engine = build_engine()
    results = evaluate(engine)
    for r in results.values():
        print(f"{r.key:28s} hit@k={r.hit_rate:4.2f}  implausible={len(r.implausible)}")
        if "-v" in sys.argv:
            for name in r.top[:10]:
                mark = "!" if name in r.implausible else ("?" if name in r.misses else " ")
                print(f"    {mark} {name[:90]}")
    print(summary(results))


if __name__ == "__main__":
    _main()
