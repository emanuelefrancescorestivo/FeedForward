"""Goals router — browse the clinical goal taxonomy."""
from __future__ import annotations

from fastapi import APIRouter

from ...engine import taxonomy
from ..models import GoalOut, SystemGoalsOut

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=list[GoalOut])
def list_goals():
    return [GoalOut(id=g.id, label=g.label, system=g.system,
                    description=g.description, icd10_refs=g.icd10_refs)
            for g in taxonomy.all_goals()]


@router.get("/by-system", response_model=list[SystemGoalsOut])
def goals_by_system():
    grouped = taxonomy.goals_by_system()
    out = []
    for system_id, label in taxonomy.SYSTEMS.items():
        goals = grouped.get(system_id, [])
        out.append(SystemGoalsOut(
            system=system_id, system_label=label,
            goals=[GoalOut(id=g.id, label=g.label, system=g.system,
                           description=g.description, icd10_refs=g.icd10_refs)
                   for g in goals]))
    return out


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: str):
    from fastapi import HTTPException
    g = taxonomy.get_goal(goal_id)
    if not g:
        raise HTTPException(404, f"Unknown goal: {goal_id}")
    return GoalOut(id=g.id, label=g.label, system=g.system,
                   description=g.description, icd10_refs=g.icd10_refs)
