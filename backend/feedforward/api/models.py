"""
api/models.py
=============
Pydantic models defining the API request/response contracts. These are the
shapes the mobile app and any third-party integrator code against.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# -- shared --
class PathStepOut(BaseModel):
    node_id: str
    name: str
    node_type: str


class ContributionOut(BaseModel):
    """One food -> nutrient -> goal route: what one portion delivers along it."""
    nutrient: str
    name: str
    amount: float                      # per portion, in the nutrient's unit
    percent_of_need: float             # of the daily reference intake
    relative_bioavailability: float
    exceeds_upper_limit: bool = False
    evidence: str = ""                 # blanked for consumers
    eu_claim: bool = False             # route backed by an authorised EU claim
    delivery_strength: float = 0.0     # food -> nutrient edge, 0-1
    association: float = 0.0           # nutrient -> goal edge, 0-1
    strength: float                    # 0-1


class PenaltyOut(BaseModel):
    nutrient: str
    share_of_daily_limit: float
    factor: float
    goal_specific: bool
    kind: str = "limit"                # limit | upper_limit


class ExplanationOut(BaseModel):
    food_id: str
    food_name: str
    goal: str
    total_cost: float                  # -log(strength) of the strongest route
    steps: list[PathStepOut]
    nutrient: str = ""
    evidence: str = ""
    evidence_label: str = ""
    consumer_label: str = ""
    citations: list[str] = Field(default_factory=list)
    note: str = ""
    portion_g: float = 0.0
    portion_group: str = ""
    contributions: list[ContributionOut] = Field(default_factory=list)
    penalties: list[PenaltyOut] = Field(default_factory=list)
    pairing: str = ""
    eu_claim: bool = False             # ``note`` is authorised EU claim wording
    evidence_source: str = ""          # eu_authorised | curated | scraped | ...


class RecommendationOut(BaseModel):
    food_id: str
    food_name: str
    category: str
    match: float                       # 0-100
    score: float                       # 0-1 goal score (similarity for /similar)
    explanation: ExplanationOut | None = None


# -- goals --
class GoalOut(BaseModel):
    id: str
    label: str
    system: str
    description: str
    icd10_refs: list[str] = Field(default_factory=list)


class SystemGoalsOut(BaseModel):
    system: str
    system_label: str
    goals: list[GoalOut]


# -- recommend --
class RecommendRequest(BaseModel):
    goal: str
    constraints: list[str] = Field(default_factory=list)
    k: int = 10
    explain: bool = True
    demographic: str | None = None     # engine/reference.py Demographic value
    # Development only: show the professional view without a professional
    # account, for the local exploration UI. Ignored in production.
    professional_preview: bool = False


class RecommendResponse(BaseModel):
    goal: str
    count: int
    recommendations: list[RecommendationOut]


# -- meal plan --
class MealPlanRequest(BaseModel):
    goal: str
    max_calories: float = 600
    k: int = 3
    constraints: list[str] = Field(default_factory=list)
    demographic: str | None = None


class MealItemOut(BaseModel):
    food_id: str
    food_name: str
    cost: float                        # 1 - goal score
    kcal: float                        # per portion
    portion_g: float = 0.0


class MealPlanResponse(BaseModel):
    goal: str
    feasible: bool
    total_cost: float                  # 1 - share of the achievable coverage
    total_kcal: float
    items: list[MealItemOut]
    note: str = ""
    greedy_total_cost: float | None = None
    coverage: dict[str, float] = Field(default_factory=dict)  # nutrient -> % of need


# -- food detail --
class GoalSupportOut(BaseModel):
    goal: str
    match: float
    nutrient: str
    evidence: str
    citations: list[str] = Field(default_factory=list)


class FoodDetailResponse(BaseModel):
    food_id: str
    food_name: str
    category: str
    nutri_score: str
    nova: int
    nutrients: dict[str, float]
    goals_supported: list[GoalSupportOut]
    similar: list[RecommendationOut]


# -- auth --
class UserCreate(BaseModel):
    email: str
    password: str
    tier: str = "consumer"       # "consumer" | "professional"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tier: str


class ProfileUpdate(BaseModel):
    demographic: str | None = None
    dietary_restrictions: list[str] | None = None
    # Self-declared tier. Billing is not implemented; this flag is what the
    # API gates citations on. See docs/APP_STORE.md.
    tier: str | None = None


class UserOut(BaseModel):
    email: str
    tier: str
    demographic: str | None = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    created_at: str | None = None


# -- scientific analysis (density, DRI %, interactions, cautions) --
class NutrientRowOut(BaseModel):
    nutrient: str
    amount: float
    kind: str                              # "beneficial" | "limit"
    percent_of_need: float | None = None
    percent_of_limit: float | None = None


class DensityBreakdownOut(BaseModel):
    qualifying_sum: float
    limiting_sum: float
    top_contributors: list[tuple[str, float]]


class CautionOut(BaseModel):
    context: str
    severity: str
    message: str
    disposition: str
    citations: list[str] = Field(default_factory=list)


class FoodProfileResponse(BaseModel):
    food_id: str
    food_name: str
    category: str
    portion_g: float = 100.0           # reference portion used for scoring
    portion_group: str = ""
    nutri_score: str
    nova: int
    density_score: float
    density_breakdown: DensityBreakdownOut
    anti_nutrients: list[str]
    is_animal_source: bool | None
    nutrients: list[NutrientRowOut]
    goals_supported: list[GoalSupportOut]
    cautions: list[CautionOut]


class MealAnalysisRequest(BaseModel):
    food_ids: list[str]
    demographic: str | None = None         # e.g. "adult_female"


class MineralDeliveryOut(BaseModel):
    raw_amount: float
    absorbable_amount: float
    absorption_pct: float
    percent_of_need_absorbable: float | None = None


class MealAnalysisResponse(BaseModel):
    foods: list[str]
    minerals: dict[str, MineralDeliveryOut]
    total_kcal: float
