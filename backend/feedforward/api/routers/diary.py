"""The day as the person eats it: totals of what they logged, and suggestions for one meal.

Same person, goal and answers as the week plan (/plan/week): see engine/diary.py.
Nothing is stored here; the app keeps the diary in the person's saved data (/me/state).
"""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...engine import diary, load_engine
from ...engine import week_planner as wp
from ...engine.portions import portion_for
from ...engine.presets import load_presets, preset_nutrients
from .plan import _profile

router = APIRouter(prefix="/diary", tags=["diary"])

Slot = Literal["breakfast", "lunch", "dinner", "snack"]


class EntryIn(BaseModel):
    kind: Literal["recipe", "food", "preset"]
    id: str = Field(min_length=1, max_length=80)
    meal: Slot
    servings: float = Field(1.0, gt=0, le=10)
    grams: float = Field(0.0, ge=0, le=3000)


class DayRequest(BaseModel):
    age: int = Field(ge=14, le=100)
    sex: str = Field(pattern="^(female|male)$")
    weight_kg: float = Field(ge=30, le=250)
    height_cm: float = Field(ge=120, le=230)
    activity: str = "light"
    pregnant: bool = False
    breastfeeding: bool = False
    goal: str | None = None
    chain: str = "lidl"
    diet: Literal["vegetarian", "vegan"] | None = None
    equipment: list[Literal["hob", "microwave", "kettle", "blender"]] | None = None
    answers: dict[str, str | list[str]] | None = None
    declined: list[str] | None = None
    avoid_recipes: list[str] | None = None
    entries: list[EntryIn] = Field(default_factory=list, max_length=60)


class SuggestRequest(DayRequest):
    meal: Slot
    k: int = Field(3, ge=1, le=6)
    exclude: list[str] | None = None        # recipe ids already shown


def _common(req: DayRequest) -> dict:
    return dict(goal=req.goal, diet=req.diet, equipment=req.equipment, answers=req.answers,
                declined=req.declined, chain=req.chain)


def _entries(req: DayRequest) -> list[diary.Entry]:
    return diary.entries_from([e.model_dump() for e in req.entries])


@router.post("/day")
def day(req: DayRequest):
    """Totals of the logged day against its targets, the goal's nutrients and the strategies per meal."""
    try:
        return diary.day_summary(load_engine(), _profile(req), _entries(req), **_common(req))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/suggest")
def suggest(req: SuggestRequest):
    """Up to k recipes for one meal today, with the reasons for each."""
    try:
        return diary.suggest_meal(load_engine(), _profile(req), _entries(req), req.meal, k=req.k,
                                  exclude=req.exclude, avoid_recipes=req.avoid_recipes, **_common(req))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/presets")
def presets():
    """Meals logged in one tap as an estimate (the CROUS lunch), with the energy of one portion."""
    engine = load_engine()
    return [{"kind": "preset", "id": p.id, "name": p.en, "fr": p.fr, "detail": p.detail_en,
             "kcal": round(preset_nutrients(engine, p).get("energy-kcal", 0.0)), "estimate": p.estimate,
             "price_eur": p.price_eur, "note": p.note_en} for p in load_presets().values()]


@router.get("/search")
def search(q: str = Query(..., min_length=2, max_length=60), scale: float = Query(1.0, ge=0.25, le=3.0),
           limit: int = Query(12, ge=1, le=30)):
    """What to log: recipes whose name matches, then foods (everyday foods first), each with its usual
    portion and energy, so one tap logs a sensible amount."""
    engine = load_engine()
    ql = q.lower().strip()
    word = re.compile(rf"\b{re.escape(ql)}")
    recipes = []
    for r in wp._recipes(engine, scale):
        if ql in r.en.lower() or ql in r.fr.lower():
            recipes.append({"kind": "recipe", "id": r.id, "name": r.en, "fr": r.fr, "meals": r.meals,
                            "kcal": round(r.nutrients.get("energy-kcal", 0.0)), "time_min": r.time_min})
    foods = sorted((f for f in engine.foods if ql in f.name.lower()),
                   key=lambda f: (0 if word.search(f.name.lower()) else 1, -f.familiarity, len(f.name)))
    out = []
    for f in foods[:limit]:
        portion = portion_for(f)
        out.append({"kind": "food", "id": f.id, "name": f.name, "category": f.category,
                    "portion_g": portion.grams, "group": portion.group,
                    "kcal_100g": round(f.nutrients.get("energy-kcal", 0.0))})
    return {"recipes": recipes[:6], "foods": out}
