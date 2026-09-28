"""Dictionary endpoints: nutrients, foods and terms, each with its sources."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ... import dictionary
from ...engine import load_engine
from .analysis import _demo

router = APIRouter(prefix="/dictionary", tags=["dictionary"])


@router.get("/nutrients")
def nutrients():
    return dictionary.nutrient_index()


@router.get("/nutrients/{nutrient_id}")
def nutrient(nutrient_id: str, demographic: str | None = None):
    entry = dictionary.nutrient_entry(load_engine(), nutrient_id, _demo(demographic))
    if entry is None:
        raise HTTPException(404, f"Unknown nutrient: {nutrient_id}")
    return entry


@router.get("/foods/{food_id}")
def food(food_id: str):
    entry = dictionary.food_entry(load_engine(), food_id)
    if entry is None:
        raise HTTPException(404, f"Unknown food: {food_id}")
    return entry


@router.get("/terms")
def terms():
    return dictionary.glossary()
