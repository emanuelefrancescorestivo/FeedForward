"""
data/schema.py
--------------
Plain data containers, mirroring your proposal §5. Dataclasses are declarative
boilerplate, so starting from your own spec is fine. The interesting logic
lives elsewhere.
"""
from dataclasses import dataclass, field


@dataclass
class Food:
    id: str
    name: str
    category: str
    nutrients: dict           # nutrient_id -> amount per 100g
    nutri_score: str
    nova: int


@dataclass
class Nutrient:
    id: str
    name: str
    related_goals: list = field(default_factory=list)
    evidence_level: float = 0.0


@dataclass
class GoalEdge:
    nutrient_id: str
    goal: str
    weight: float
    explanation: str
    edge_type: str = "positive"