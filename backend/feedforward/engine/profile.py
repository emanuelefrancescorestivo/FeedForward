"""
engine/profile.py
=================
What people tell the week planner about themselves, and what it may do with it.

The questions, the goals each answer turns on in the knowledge graph, and the
strategies and preferences each answer triggers live in one data file
(data/strategies.json), not in code, so that every strategy carries its evidence
grade and PubMed IDs where a reader can check them:

  answer --triggers--> strategy --supports (grade A-C, PMIDs)--> goal

  kind "strategy"    a lever backed by evidence; proposed with its grade and sources
  kind "preference"  comfort, taste or kitchen limits; applied as asked, no evidence needed

This module reads that file and checks it. An unknown question, answer, lever or
goal is an error, never silently ignored: a typo in the file must not turn into a
strategy that quietly does nothing.

`when` is a list of conditions: OR between conditions, AND inside one. A value is
the list of answers that match, or "*" for any answer.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# What "foods I don't eat" can name. The first eight are ingredient tags in
# data/ingredients.json; "spicy" is a recipe tag in data/recipes.json (the spice is
# not an ingredient there). "caffeine" is a tag too but is not a category: it is
# what the no-evening-caffeine strategy looks for.
CATEGORIES = ("fish_seafood", "meat", "pork", "mushrooms", "legumes", "dairy", "eggs", "nuts", "spicy")
# The three main meals, as in week_planner.MEALS (kept here so this module never imports the MILP code).
MEALS = ("breakfast", "lunch", "dinner")
LEVER_TYPES = ("meal_carb_share", "meal_energy_share", "protein_target", "protein_per_meal",
               "meal_protein", "no_caffeine", "exclude_tags", "max_minutes", "batch_ok")
GRADES = ("A", "B", "C")        # D and below are never proposed
KINDS = ("strategy", "preference")


@lru_cache(maxsize=1)
def load_strategies() -> dict:
    """The validated data file. It has no engine to ask, so goal names are checked
    where the engine is at hand (validate_strategies); everything else is checked here."""
    data = json.loads((DATA / "strategies.json").read_text(encoding="utf-8"))
    _check_structure(data)
    return data


def questions() -> list[dict]:
    """The questionnaire: id, text, options, and `multi` where several may be chosen. Read-only."""
    return load_strategies()["questions"]


def validate_strategies(data: dict, known_goals: set[str]) -> None:
    """Raise ValueError unless `data` is a sound strategies file and every goal it names is in the graph."""
    _check_structure(data)
    for link in data["goals"]:
        if link["goal"] not in known_goals:
            _fail(f"goal link to {link['goal']!r}", "not a goal in the knowledge graph")
    for s in data["strategies"]:
        if s["kind"] == "strategy" and s["goal"] not in known_goals:
            _fail(f"strategy {s['id']!r}", f"goal {s['goal']!r} is not in the knowledge graph")


def _fail(where: str, message: str) -> None:
    raise ValueError(f"strategies.json, {where}: {message}")


def _check_structure(data: dict) -> None:
    """Everything that can be checked without the graph: ids, answers, levers, grades, sources."""
    for key in ("questions", "goals", "strategies"):
        if not isinstance(data.get(key), list):
            _fail("top level", f"`{key}` must be a list")
    options_of: dict[str, list[str]] = {}
    for q in data["questions"]:
        qid = q.get("id")
        if not qid or qid in options_of:
            _fail("questions", f"missing or duplicate question id {qid!r}")
        if not q.get("text") or not q.get("options") or len(set(q["options"])) != len(q["options"]):
            _fail(f"question {qid!r}", "needs text and a list of distinct options")
        options_of[qid] = list(q["options"])

    for link in data["goals"]:
        where = f"goal link to {link.get('goal')!r}"
        _check_when(where, link.get("when"), options_of)
        alpha = link.get("alpha")
        if not isinstance(alpha, (int, float)) or not 0 < alpha <= 1:
            _fail(where, f"alpha must be in (0, 1], not {alpha!r}")

    seen: set[str] = set()
    for s in data["strategies"]:
        sid = s.get("id")
        where = f"strategy {sid!r}"
        if not sid or sid in seen:
            _fail("strategies", f"missing or duplicate id {sid!r}")
        seen.add(sid)
        if s.get("kind") not in KINDS:
            _fail(where, f"kind must be one of {KINDS}, not {s.get('kind')!r}")
        if not s.get("text") or (s["kind"] == "strategy" and not s.get("why")):
            _fail(where, "needs text (and, for a strategy, why)")
        _check_when(where, s.get("when"), options_of)
        _check_lever(where, s.get("lever"), options_of)
        if s["kind"] == "strategy":
            if s.get("grade") not in GRADES:
                _fail(where, f"grade must be one of {GRADES}, not {s.get('grade')!r}")
            pmids = s.get("pmids")
            if not pmids or not all(isinstance(p, str) and p.isdigit() for p in pmids):
                _fail(where, "needs at least one PubMed ID, as digits")
            if not s.get("goal"):
                _fail(where, "needs a goal")


def _check_when(where: str, when, options_of: dict[str, list[str]]) -> None:
    if not isinstance(when, list) or not when:
        _fail(where, "`when` must be a non-empty list of conditions")
    for condition in when:
        if not isinstance(condition, dict) or not condition:
            _fail(where, "each condition must name at least one question")
        for qid, accepted in condition.items():
            if qid not in options_of:
                _fail(where, f"`when` names an unknown question {qid!r}")
            if accepted == "*":
                continue
            if not isinstance(accepted, list) or not accepted:
                _fail(where, f"{qid!r}: expected a list of answers or \"*\", not {accepted!r}")
            for answer in accepted:
                if answer not in options_of[qid]:
                    _fail(where, f"{answer!r} is not an answer to {qid!r} (one of {options_of[qid]})")


def _check_lever(where: str, lever, options_of: dict[str, list[str]]) -> None:
    kind = lever.get("type") if isinstance(lever, dict) else None
    if kind not in LEVER_TYPES:
        _fail(where, f"unknown lever type {kind!r} (one of {LEVER_TYPES})")
    if "meal" in lever and lever["meal"] not in MEALS:
        _fail(where, f"unknown meal {lever['meal']!r}")
    # A lever may read its value from an answer ("from") or pick its meal from one ("meal_from" + "map").
    for key in ("from", "meal_from"):
        if key in lever and lever[key] not in options_of:
            _fail(where, f"`{key}` names an unknown question {lever[key]!r}")
    if "meal_from" in lever:
        mapping = lever.get("map") or {}
        missing = [o for o in options_of[lever["meal_from"]] if o not in mapping]
        if missing:
            _fail(where, f"`map` has no meal for {lever['meal_from']}: {missing}")
        if any(m not in MEALS for m in mapping.values()):
            _fail(where, f"`map` names an unknown meal in {mapping}")
