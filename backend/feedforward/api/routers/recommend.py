"""Recommendation, explanation, meal-plan and food-detail endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...engine import load_engine
from ...engine.meal_optimizer import optimize_meal, greedy_meal
from ...engine.reference import Demographic
from .analysis import _demo, preview_allowed
from ..auth import current_user_optional
from ..models import (RecommendRequest, RecommendResponse, RecommendationOut,
                      ExplanationOut, PathStepOut, MealPlanRequest,
                      MealPlanResponse, MealItemOut, FoodDetailResponse,
                      GoalSupportOut, ContributionOut, PenaltyOut)

router = APIRouter(tags=["recommend"])


def _explanation_out(exp, professional: bool) -> ExplanationOut | None:
    if exp is None:
        return None
    return ExplanationOut(
        food_id=exp.food_id, food_name=exp.food_name, goal=exp.goal,
        total_cost=exp.total_cost,
        steps=[PathStepOut(node_id=s.node_id, name=s.name, node_type=s.node_type)
               for s in exp.steps],
        nutrient=exp.nutrient,
        # Consumers see the plain label; professionals additionally see the
        # graded label + citations.
        evidence=exp.evidence if professional else "",
        evidence_label=exp.evidence_label if professional else "",
        consumer_label=exp.consumer_label,
        citations=exp.citations if professional else [],
        note=exp.note,
        portion_g=exp.portion_g,
        portion_group=exp.portion_group,
        contributions=[ContributionOut(**{**c, "evidence": c["evidence"] if professional else ""})
                       for c in exp.contributions],
        penalties=[PenaltyOut(**p) for p in exp.penalties],
        pairing=exp.pairing,
        eu_claim=exp.eu_claim,
        evidence_source=exp.evidence_source,
    )


def _rec_out(r, professional: bool) -> RecommendationOut:
    return RecommendationOut(
        food_id=r.food_id, food_name=r.food_name, category=r.category,
        match=r.match, score=r.score,
        explanation=_explanation_out(r.explanation, professional))


@router.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest, user=Depends(current_user_optional)):
    engine = load_engine()
    professional = bool(user and user.get("tier") == "professional") or \
        (req.professional_preview and preview_allowed())
    recs = engine.foods_for_goal(req.goal, req.constraints, req.k, req.explain,
                                 demo=_demo(req.demographic))
    return RecommendResponse(
        goal=req.goal, count=len(recs),
        recommendations=[_rec_out(r, professional) for r in recs])


@router.get("/explain", response_model=ExplanationOut)
def explain(food_id: str = Query(...), goal: str = Query(...),
            user=Depends(current_user_optional)):
    engine = load_engine()
    professional = bool(user and user.get("tier") == "professional")
    exp = engine.explain(food_id, goal)
    if exp is None:
        raise HTTPException(404, "No explanatory path from this food to this goal.")
    return _explanation_out(exp, professional)


@router.post("/meal-plan", response_model=MealPlanResponse)
def meal_plan(req: MealPlanRequest):
    engine = load_engine()
    demo = _demo(req.demographic)
    plan = optimize_meal(engine, req.goal, req.max_calories, req.k, req.constraints, demo)
    greedy = greedy_meal(engine, req.goal, req.max_calories, req.k, req.constraints, demo)
    return MealPlanResponse(
        goal=plan.goal, feasible=plan.feasible,
        total_cost=plan.total_cost, total_kcal=plan.total_kcal,
        items=[MealItemOut(food_id=i.food_id, food_name=i.food_name,
                           cost=i.cost, kcal=i.kcal, portion_g=i.portion_g)
               for i in plan.items],
        note=plan.note,
        greedy_total_cost=greedy.total_cost if greedy.feasible else None,
        coverage=plan.coverage)


@router.get("/foods/{food_id}", response_model=FoodDetailResponse)
def food_detail(food_id: str, user=Depends(current_user_optional)):
    engine = load_engine()
    professional = bool(user and user.get("tier") == "professional")
    food = engine.food_by_id.get(food_id)
    if not food:
        raise HTTPException(404, f"Unknown food: {food_id}")
    goals = engine.goals_for_food(food_id)
    similar = engine.similar_foods(food_id, k=5)
    return FoodDetailResponse(
        food_id=food.id, food_name=food.name, category=food.category,
        nutri_score=food.nutri_score, nova=food.nova, nutrients=food.nutrients,
        goals_supported=[GoalSupportOut(goal=g["goal"], match=g["match"],
                                        nutrient=g["nutrient"],
                                        evidence=g["evidence"] if professional else "",
                                        citations=g.get("citations", []) if professional else [])
                         for g in goals],
        similar=[_rec_out(r, professional) for r in similar])


@router.get("/foods/{food_id}/similar", response_model=list[RecommendationOut])
def similar(food_id: str, k: int = Query(5, ge=1, le=50),
            constraints: list[str] = Query(default_factory=list)):
    """
    Nutritionally similar foods. With constraints (e.g. ?constraints=vegetarian)
    these are substitutes: the closest profiles that satisfy the diet.
    """
    engine = load_engine()
    if food_id not in engine.food_by_id:
        raise HTTPException(404, f"Unknown food: {food_id}")
    return [RecommendationOut(food_id=r.food_id, food_name=r.food_name,
                              category=r.category, match=r.match, score=r.score)
            for r in engine.similar_foods(food_id, k=k, constraints=constraints)]


@router.get("/search", response_model=list[RecommendationOut])
def search_foods(q: str = Query(..., min_length=2), limit: int = 20):
    """Simple substring search over food names for the app's search bar."""
    import re
    engine = load_engine()
    ql = q.lower().strip()
    word = re.compile(rf"\b{re.escape(ql)}\b")
    prefix = re.compile(rf"\b{re.escape(ql)}")

    def rank(f):
        name = f.name.lower()
        kind = 0 if word.search(name) else 1 if prefix.search(name) else 2
        return (kind, -f.familiarity, len(name))
    hits = sorted((f for f in engine.foods if ql in f.name.lower()), key=rank)[:limit]
    return [RecommendationOut(food_id=f.id, food_name=f.name, category=f.category,
                              match=0.0, score=0.0) for f in hits]
