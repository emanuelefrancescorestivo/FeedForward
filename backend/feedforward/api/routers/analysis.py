"""
Analysis router — the deep scientific endpoints.

These expose the layers that make FeedForward an analysis tool rather than a
lookup: full nutrient profiling (density + % of daily need), meal-level
bioavailability analysis (absorbable mineral delivery accounting for nutrient
interactions), and informational cautions.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from ...engine import load_engine
from ...engine.reference import Demographic
from ..auth import current_user_optional
from ..models import (FoodProfileResponse, DensityBreakdownOut, NutrientRowOut,
                      GoalSupportOut, CautionOut, MealAnalysisRequest,
                      MealAnalysisResponse, MineralDeliveryOut)

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _demo(name: str | None) -> Demographic:
    if not name:
        return Demographic.ADULT_FEMALE
    try:
        return Demographic(name)
    except ValueError:
        return Demographic.ADULT_FEMALE


def preview_allowed() -> bool:
    """The professional preview exists for local exploration, never in production."""
    return os.getenv("FEEDFORWARD_ENV", "development").lower() != "production"


@router.get("/profile/{food_id}", response_model=FoodProfileResponse)
def food_profile(food_id: str, demographic: str | None = None,
                 professional_preview: bool = False,
                 user=Depends(current_user_optional)):
    """Full scientific profile: density, % of daily need, anti-nutrients,
    goals supported, and informational cautions."""
    engine = load_engine()
    professional = bool(user and user.get("tier") == "professional") or \
        (professional_preview and preview_allowed())
    prof = engine.food_profile(food_id, demo=_demo(demographic))
    if prof is None:
        raise HTTPException(404, f"Unknown food: {food_id}")

    return FoodProfileResponse(
        food_id=prof["food_id"], food_name=prof["food_name"],
        category=prof["category"], nutri_score=prof["nutri_score"],
        portion_g=prof["portion_g"], portion_group=prof["portion_group"],
        nova=prof["nova"], density_score=prof["density_score"],
        density_breakdown=DensityBreakdownOut(**prof["density_breakdown"]),
        anti_nutrients=prof["anti_nutrients"],
        is_animal_source=prof["is_animal_source"],
        nutrients=[NutrientRowOut(**r) for r in prof["nutrients"]],
        goals_supported=[
            GoalSupportOut(goal=g["goal"], match=g["match"], nutrient=g["nutrient"],
                           evidence=g["evidence"] if professional else "",
                           citations=g.get("citations", []) if professional else [])
            for g in prof["goals_supported"]],
        # Cautions are informational and shown to everyone (safety first),
        # but citations are professional-only.
        cautions=[CautionOut(context=c["context"], severity=c["severity"],
                             message=c["message"], disposition=c["disposition"],
                             citations=c["citations"] if professional else [])
                  for c in prof["cautions"]],
    )


@router.post("/meal", response_model=MealAnalysisResponse)
def analyze_meal(req: MealAnalysisRequest):
    """Meal-level bioavailability: absorbable mineral delivery for a set of foods
    eaten together, accounting for enhancing/inhibiting nutrient interactions."""
    engine = load_engine()
    result = engine.analyze_meal(req.food_ids, demo=_demo(req.demographic))
    minerals = {
        k: MineralDeliveryOut(**v) for k, v in result.get("minerals", {}).items()
    }
    return MealAnalysisResponse(
        foods=result.get("foods", []), minerals=minerals,
        total_kcal=result.get("total_kcal", 0))


@router.get("/coverage")
def coverage():
    """
    Nutrient hubs and goals with thin positive-edge coverage.

    Computed on the nutrient→goal graph (tens of edges), not on the food
    graph, so it stays cheap after the USDA corpus is loaded.
    """
    from ...engine.analytics import coverage_report
    from ...engine.build import load_goal_edges
    return coverage_report(load_goal_edges())


@router.get("/nutrients")
def nutrients():
    """Display names (en/it/fr), units and groups from the nutrient ontology."""
    from ...ontology.nutrients import all_nutrients
    return [{"id": n.id, "name": n.name("en"), "names": n.names, "unit": n.unit,
             "group": n.group} for n in all_nutrients()]


@router.get("/cautions/contexts")
def caution_contexts():
    """The distinct medication/condition contexts the caution layer knows about
    — for a 'do any of these apply to you?' onboarding step."""
    from ...engine import cautions
    return {"contexts": cautions.all_contexts()}
