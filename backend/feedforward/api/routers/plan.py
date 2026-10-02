"""Weekly plan endpoints: options, the plan itself, and recipe details."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...engine import load_engine
from ...engine.needs import ACTIVITY, Profile, energy_kcal
from ...engine import week_planner as wp

router = APIRouter(prefix="/plan", tags=["plan"])


class WeekRequest(BaseModel):
    age: int = Field(ge=14, le=100)
    sex: str = Field(pattern="^(female|male)$")
    weight_kg: float = Field(ge=30, le=250)
    height_cm: float = Field(ge=120, le=230)
    activity: str = "light"
    pregnant: bool = False
    breastfeeding: bool = False
    goal: str | None = "cognitive_function"
    budget: float = Field(50, ge=10, le=500)
    chain: str = "lidl"
    diet: Literal["vegetarian", "vegan"] | None = None
    equipment: list[Literal["hob", "microwave", "kettle", "blender"]] | None = None   # None = full kitchen


@router.get("/options")
def options():
    return {"chains": wp.chains(), "activities": list(ACTIVITY),
            "diets": [None, "vegetarian", "vegan"]}


@router.post("/week")
def week(req: WeekRequest):
    profile = Profile(req.age, req.sex, req.weight_kg, req.height_cm, req.activity,
                      req.pregnant, req.breastfeeding)
    try:
        profile.validate()
        return wp.plan_week(load_engine(), profile, goal=req.goal, budget=req.budget,
                            chain=req.chain, diet=req.diet, equipment=req.equipment)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


SCALE = Query(1.0, ge=0.25, le=3.0, description="the plan's portion_scale")


@router.get("/recipes/{recipe_id}")
def recipe(recipe_id: str, chain: str = "lidl", scale: float = SCALE):
    ingredients, raw, prices = wp._load()
    r = next((x for x in raw if x["id"] == recipe_id), None)
    if r is None:
        raise HTTPException(404, f"Unknown recipe: {recipe_id}")
    if chain not in prices["chains"]:
        raise HTTPException(400, f"unknown chain: {chain}")
    k = wp.serving_scale(r, scale)
    items, cost = [], 0.0
    for it in r["ingredients"]:
        eur_kg, _pack, estimated = wp._price(it["id"], chain)
        g = round(it["g"] * k)
        items.append({"id": it["id"], "en": ingredients[it["id"]]["en"], "fr": ingredients[it["id"]]["fr"],
                      "g": g, "cost": round(g * eur_kg / 1000, 2), "estimated": estimated,
                      "liquid": bool(ingredients[it["id"]].get("liquid"))})
        cost += g * eur_kg / 1000
    return {"id": r["id"], "en": r["en"], "fr": r["fr"], "meals": r["meals"],
            "time_min": r.get("time_min", 0), "equipment": r.get("equipment", []),
            "batch": bool(r.get("batch")), "steps": r.get("steps", []),
            "ingredients": items, "cost_per_serving": round(cost, 2), "status": "draft"}


@router.get("/recipes/{recipe_id}/why")
def recipe_why(recipe_id: str, goal: str = "cognitive_function", scale: float = SCALE,
               demographic: str | None = None):
    """Why this recipe is in the plan: goal nutrients per portion, with their evidence."""
    try:
        return wp.recipe_why(load_engine(), recipe_id, goal=goal, scale=scale, demographic=demographic)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except ValueError as exc:                      # unknown demographic
        raise HTTPException(400, str(exc)) from exc
