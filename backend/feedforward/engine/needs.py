"""
Personal daily needs from a few everyday facts.

What the inputs change, and what they do not:
  energy    Mifflin-St Jeor resting energy x physical activity level
            (+ ~340 kcal in pregnancy, +500 kcal when breastfeeding)
  protein   the higher of the reference intake and 0.83 g per kg of body
            weight (EFSA Population Reference Intake for adults)
  others    vitamins and minerals depend on age, sex, pregnancy and
            breastfeeding (engine/reference.py), NOT on weight or height

This is general-population guidance for healthy adults. It takes no medical
conditions as input, on purpose: advice for a condition is a medical
decision (and would make the app a medical device under the EU MDR).
"""
from __future__ import annotations

from dataclasses import dataclass

from .reference import Demographic, LIMIT_NUTRIENTS, reference_value

ACTIVITY = {  # physical activity level (PAL) multipliers
    "sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9,
}
PROTEIN_G_PER_KG = 0.83


@dataclass
class Profile:
    age: int
    sex: str                      # "female" | "male"
    weight_kg: float
    height_cm: float
    activity: str = "light"
    pregnant: bool = False
    breastfeeding: bool = False

    def validate(self) -> "Profile":
        if not 14 <= self.age <= 100:
            raise ValueError("age must be between 14 and 100")
        if self.sex not in ("female", "male"):
            raise ValueError("sex must be 'female' or 'male'")
        if not 30 <= self.weight_kg <= 250 or not 120 <= self.height_cm <= 230:
            raise ValueError("weight or height out of range")
        if self.activity not in ACTIVITY:
            raise ValueError(f"activity must be one of {sorted(ACTIVITY)}")
        return self

    @property
    def demographic(self) -> Demographic:
        if self.pregnant:
            return Demographic.PREGNANCY
        if self.breastfeeding:
            return Demographic.LACTATION
        if self.age < 19:
            return Demographic.TEEN
        if self.age >= 51:
            return Demographic.OLDER_MALE if self.sex == "male" else Demographic.OLDER_FEMALE
        return Demographic.ADULT_MALE if self.sex == "male" else Demographic.ADULT_FEMALE


def energy_kcal(p: Profile) -> float:
    bmr = 10 * p.weight_kg + 6.25 * p.height_cm - 5 * p.age + (5 if p.sex == "male" else -161)
    kcal = bmr * ACTIVITY[p.activity]
    if p.pregnant:
        kcal += 340
    elif p.breastfeeding:
        kcal += 500
    return round(kcal)


def daily_needs(p: Profile, nutrients: list[str]) -> dict[str, float]:
    """Daily amount per nutrient for this person (only nutrients with a reference)."""
    p.validate()
    demo = p.demographic
    out = {}
    for n in nutrients:
        if n in LIMIT_NUTRIENTS or n == "energy-kcal":
            continue
        ref = reference_value(n, demo)
        if ref and ref.rda_ai > 0:
            out[n] = ref.rda_ai
    out["proteins"] = round(max(out.get("proteins", 0), PROTEIN_G_PER_KG * p.weight_kg), 1)
    return out
