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

propose() shows what a set of answers would turn on, so people can accept or decline
it; resolve() turns the answers (minus what they declined) into the Levers the week
planner applies. No answers at all resolve to Levers.none(goal): the planner as it
was before preferences existed.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .needs import Profile

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

# The energy goal scales the day's target (Mifflin-St Jeor x activity); the planner never goes below resting energy.
ENERGY_FACTORS = {"maintain": 1.0, "deficit": 0.85, "surplus": 1.10}
_UNDER_18 = "Deficit and surplus are for adults: under 18 the plan follows growth needs."
_PREGNANT = "In pregnancy and breastfeeding the plan follows the needs of those months."
_LOW_BMI = "With a BMI under 18.5 a deficit is not offered."


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


def energy_options(p: Profile) -> dict[str, str | None]:
    """Why each energy goal is or is not open to this person: None when allowed, else the reason to show.
    A deficit or surplus is for healthy adults: not under 18, not in pregnancy or breastfeeding,
    and no deficit when already underweight (BMI under 18.5)."""
    options: dict[str, str | None] = {goal: None for goal in ENERGY_FACTORS}
    if p.age < 18:
        options["deficit"] = options["surplus"] = _UNDER_18
    elif p.pregnant or p.breastfeeding:
        options["deficit"] = options["surplus"] = _PREGNANT
    elif p.weight_kg / (p.height_cm / 100) ** 2 < 18.5:
        options["deficit"] = _LOW_BMI
    return options


@dataclass(frozen=True)
class Levers:
    """Everything the week planner applies on top of the person's needs and goal.

    A None, empty or False field is a lever that is off; Levers.none(goal) has them all off.
    `applied` lists the strategies and preferences behind the levers, for the plan to report:
    id, kind, text, why, grade, goal, pmids, because, lever (None / [] where an entry has no such key).
    """
    goals: dict[str, float]                  # goal -> alpha; the person's own goal is 1.0
    energy_goal: str                         # key of ENERGY_FACTORS
    energy_factor: float
    protein_g_per_kg: float | None           # daily protein need, if raised by a strategy
    meal_carb_share: dict[str, float]        # meal -> least share of the day's carbohydrates
    breakfast_energy_min: float | None       # share of the day's energy
    breakfast_energy_max: float | None
    protein_per_meal_g_per_kg: float | None  # per main meal
    breakfast_protein_g_per_kg: float | None
    no_caffeine_at: frozenset[str]           # meals
    exclude: frozenset[str]                  # CATEGORIES the person does not eat
    avoid_recipes: frozenset[str]            # recipe ids marked "Not for me"; the planner checks they exist
    max_minutes: int | None
    batch_ok: bool
    applied: tuple[dict, ...]

    @classmethod
    def none(cls, goal: str | None) -> "Levers":
        """No answers: the planner as it is without preferences."""
        return cls(goals={goal: 1.0} if goal else {}, energy_goal="maintain", energy_factor=ENERGY_FACTORS["maintain"],
                   protein_g_per_kg=None, meal_carb_share={}, breakfast_energy_min=None, breakfast_energy_max=None,
                   protein_per_meal_g_per_kg=None, breakfast_protein_g_per_kg=None, no_caffeine_at=frozenset(),
                   exclude=frozenset(), avoid_recipes=frozenset(), max_minutes=None, batch_ok=False, applied=())


def propose(answers: dict, p: Profile, *, goal: str | None, known_goals: set[str]) -> dict:
    """What these answers would turn on, for people to accept or decline: the goals (with the alpha
    resolve would give them), the strategies and preferences that apply, each with `because` (the
    question and answer that triggered it), and the energy goals not open to this person, with the reason.
    Works with no answers: `unavailable` depends on the profile alone."""
    data, answers = _prepare(answers, p, known_goals)
    return {
        "goals": [{"id": g, "alpha": alpha, "because": because}
                  for g, (alpha, because) in _goals_turned_on(data, answers, goal).items()],
        "strategies": [{**copy.deepcopy(entry), "because": because} for entry, because in _triggered(data, answers)],
        "unavailable": {f"energy_goal={option}": reason for option, reason in energy_options(p).items() if reason},
    }


def resolve(answers: dict | None, declined: list[str] | None, p: Profile, *, goal: str | None,
            known_goals: set[str], avoid_recipes: list[str] | None = None) -> Levers:
    """Turn answers into the Levers the planner applies, leaving out the strategies in `declined`.

    Raises ValueError for an unknown question, an answer a question does not offer, an unknown declined id
    or an energy goal this profile may not choose (the message is the reason). A declined id the answers
    do not trigger is ignored. Recipe ids are not checked here (this module knows no recipes).
    Nothing answered or declined (None or empty) gives Levers.none(goal) without reading the strategies
    file: a request without answers does not depend on it.
    """
    if isinstance(avoid_recipes, str):
        raise ValueError("avoid_recipes must be a list of recipe ids")
    if _empty(answers, dict) and _empty(declined, (list, tuple, set, frozenset)):
        return dataclasses.replace(Levers.none(goal), avoid_recipes=frozenset(avoid_recipes or ()))
    data, answers = _prepare(answers, p, known_goals)
    declined = _check_declined(declined, data)

    goals = {goal: 1.0} if goal else {}
    for g, (alpha, _) in _goals_turned_on(data, answers, goal).items():
        goals[g] = alpha
    energy_goal = answers.get("energy_goal", "maintain")

    acc: dict = {"protein_g_per_kg": None, "meal_carb_share": {}, "breakfast_energy_min": None,
                 "breakfast_energy_max": None, "protein_per_meal_g_per_kg": None, "breakfast_protein_g_per_kg": None,
                 "no_caffeine_at": set(), "exclude": set(), "max_minutes": None, "batch_ok": False}
    applied = []
    for entry, because in _triggered(data, answers):
        if entry["id"] in declined:
            continue
        _fold(entry["lever"], answers, acc)
        lever = copy.deepcopy(entry["lever"])
        if "meal_from" in lever:                       # the meal the answer picked, for the plan to measure
            lever["meal"] = lever["map"][answers[lever["meal_from"]]]
        applied.append({"id": entry["id"], "kind": entry["kind"], "text": entry["text"], "why": entry.get("why"),
                        "grade": entry.get("grade"), "goal": entry.get("goal"), "pmids": list(entry.get("pmids", [])),
                        "because": because, "lever": lever})
    return Levers(goals=goals, energy_goal=energy_goal, energy_factor=ENERGY_FACTORS[energy_goal],
                  no_caffeine_at=frozenset(acc.pop("no_caffeine_at")), exclude=frozenset(acc.pop("exclude")),
                  avoid_recipes=frozenset(avoid_recipes or ()), applied=tuple(applied), **acc)


def _empty(value, kinds) -> bool:
    """None, or an empty value of the expected kind (an empty value of another kind is checked, and refused)."""
    return value is None or (isinstance(value, kinds) and not value)


def _prepare(answers: dict | None, p: Profile, known_goals: set[str]) -> tuple[dict, dict]:
    """The checked strategies file and the cleaned answers; refuses an energy goal this profile may not choose."""
    data = load_strategies()
    validate_strategies(data, known_goals)
    answers = _check_answers(answers, data)
    reason = energy_options(p)[answers.get("energy_goal", "maintain")]
    if reason:
        raise ValueError(reason)
    return data, answers


def _check_answers(answers: dict | None, data: dict) -> dict:
    """Only answered questions: None and {} mean nothing answered, an empty list is no answer to a
    multiple-choice question. Unknown questions and options outside a question's list are errors."""
    if answers is None:
        return {}
    if not isinstance(answers, dict):
        raise ValueError("answers must be a dict of question id to answer")
    questions_by_id = {q["id"]: q for q in data["questions"]}
    clean: dict = {}
    for qid, value in answers.items():
        q = questions_by_id.get(qid)
        if q is None:
            raise ValueError(f"unknown question {qid!r}")
        if q.get("multi"):
            if not isinstance(value, list):
                raise ValueError(f"{qid!r} takes a list of answers, not {value!r}")
            wrong = [v for v in value if v not in q["options"]]
            if wrong:
                raise ValueError(f"{wrong} is not an answer to {qid!r} (one of {q['options']})")
            if value:
                clean[qid] = list(dict.fromkeys(value))
        else:
            if isinstance(value, list) or value not in q["options"]:
                raise ValueError(f"{value!r} is not an answer to {qid!r} (one of {q['options']})")
            clean[qid] = value
    return clean


def _check_declined(declined: list[str] | None, data: dict) -> frozenset[str]:
    """Declined ids must be ids in the file, strategies and preferences alike."""
    if declined is None:
        return frozenset()
    if not isinstance(declined, (list, tuple, set, frozenset)):
        raise ValueError("declined must be a list of strategy ids")
    known = {s["id"] for s in data["strategies"]}
    unknown = [d for d in declined if not (isinstance(d, str) and d in known)]
    if unknown:
        raise ValueError(f"unknown strategy ids to decline: {unknown}")
    return frozenset(declined)


def _match(when: list[dict], answers: dict) -> dict | None:
    """The first condition the answers satisfy, as {"question", "answer"} for its first question; else None."""
    for condition in when:
        if all(_accepts(accepted, answers.get(qid)) for qid, accepted in condition.items()):
            first = next(iter(condition))
            return {"question": first, "answer": copy.deepcopy(answers[first])}
    return None


def _accepts(accepted, value) -> bool:
    if value is None:                                  # not answered
        return False
    if accepted == "*":
        return True
    return any(v in accepted for v in value) if isinstance(value, list) else value in accepted


def _goals_turned_on(data: dict, answers: dict, primary: str | None) -> dict[str, tuple[float, dict]]:
    """goal -> (alpha, because) for the goals the answers turn on. Several answers for one goal keep the
    highest alpha; the person's own goal keeps alpha 1 if an answer points at it too."""
    turned: dict[str, tuple[float, dict]] = {}
    for link in data["goals"]:
        because = _match(link["when"], answers)
        if because is None:
            continue
        alpha = 1.0 if link["goal"] == primary else float(link["alpha"])
        if link["goal"] not in turned or alpha > turned[link["goal"]][0]:
            turned[link["goal"]] = (alpha, because)
    return turned


def _triggered(data: dict, answers: dict) -> list[tuple[dict, dict]]:
    """(entry, because) for each strategy and preference the answers trigger, in file order. An entry
    whose lever reads a question that was not answered, or asks for no limit ("any" cooking time),
    has nothing to apply and is left out, so it is neither applied nor reported."""
    out = []
    for entry in data["strategies"]:
        because = _match(entry["when"], answers)
        lever = entry["lever"]
        if because is None or any(lever[k] not in answers for k in ("from", "meal_from") if k in lever):
            continue
        if lever["type"] == "max_minutes" and answers[lever["from"]] == "any":
            continue
        out.append((entry, because))
    return out


def _fold(lever: dict, answers: dict, acc: dict) -> None:
    """Add one lever to the accumulated levers. Floors keep the highest value, limits the lowest, so two
    strategies that touch the same lever never loosen each other."""
    kind = lever["type"]
    if kind == "meal_carb_share":
        meal = lever["map"][answers[lever["meal_from"]]] if "meal_from" in lever else lever["meal"]
        acc["meal_carb_share"][meal] = max(acc["meal_carb_share"].get(meal, 0.0), lever["min"])
    elif kind == "meal_energy_share":                  # breakfast only (checked with the file)
        if "min" in lever:
            acc["breakfast_energy_min"] = _most(acc["breakfast_energy_min"], lever["min"])
        if "max" in lever:
            acc["breakfast_energy_max"] = _least(acc["breakfast_energy_max"], lever["max"])
    elif kind == "protein_target":
        acc["protein_g_per_kg"] = _most(acc["protein_g_per_kg"], lever["g_per_kg"])
    elif kind == "protein_per_meal":
        acc["protein_per_meal_g_per_kg"] = _most(acc["protein_per_meal_g_per_kg"], lever["g_per_kg"])
    elif kind == "meal_protein":                       # breakfast only (checked with the file)
        acc["breakfast_protein_g_per_kg"] = _most(acc["breakfast_protein_g_per_kg"], lever["g_per_kg"])
    elif kind == "no_caffeine":
        acc["no_caffeine_at"].add(lever["meal"])
    elif kind == "exclude_tags":
        value = answers[lever["from"]]
        acc["exclude"].update(value if isinstance(value, list) else [value])
    elif kind == "max_minutes":
        value = answers[lever["from"]]
        acc["max_minutes"] = None if value == "any" else int(value)
    elif kind == "batch_ok":
        acc["batch_ok"] = True


def _most(current: float | None, value: float) -> float:
    return value if current is None else max(current, value)


def _least(current: float | None, value: float) -> float:
    return value if current is None else min(current, value)


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
    _check_lever_params(where, lever, options_of)


def _check_lever_params(where: str, lever: dict, options_of: dict[str, list[str]]) -> None:
    """The numbers and meals each lever type needs, so that resolve() can use a lever without guessing."""
    kind = lever["type"]

    def number(key: str, at_most: float | None = None) -> None:
        v = lever.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0 or (at_most and v > at_most):
            _fail(where, f"lever {kind!r} needs `{key}` as a positive number" + (f" up to {at_most}" if at_most else ""))

    def breakfast_only() -> None:
        if lever.get("meal") != "breakfast":
            _fail(where, f"lever {kind!r} is for breakfast only: `meal` must be \"breakfast\"")

    if kind == "meal_carb_share":
        number("min", 1)
        if "meal" not in lever and "meal_from" not in lever:
            _fail(where, "lever needs `meal` or `meal_from`")
    elif kind == "meal_energy_share":
        breakfast_only()
        if "min" not in lever and "max" not in lever:
            _fail(where, "lever needs `min` or `max`")
        for key in ("min", "max"):
            if key in lever:
                number(key, 1)
    elif kind in ("protein_target", "protein_per_meal", "meal_protein"):
        if kind == "meal_protein":
            breakfast_only()
        number("g_per_kg")
    elif kind == "no_caffeine":
        if lever.get("meal") not in MEALS:
            _fail(where, f"lever 'no_caffeine' needs `meal`, one of {MEALS}")
    elif kind in ("exclude_tags", "max_minutes"):
        source = lever.get("from")
        if source not in options_of:
            _fail(where, f"lever {kind!r} needs `from`, naming the question it reads")
        if kind == "max_minutes" and not all(o == "any" or o.isdigit() for o in options_of[source]):
            _fail(where, f"{source!r} must offer minutes as digits, or \"any\"")
