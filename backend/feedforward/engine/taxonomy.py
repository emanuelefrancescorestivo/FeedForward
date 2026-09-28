"""
engine/taxonomy.py
==================
The clinical goal taxonomy.

The university prototype had 7 ad-hoc goals (energy, recovery, iron_support,
...). A credible health product needs a structured taxonomy that (a) covers
the domains people actually care about and (b) maps to recognised clinical
categories so the professional tier can speak a dietitian's language.

This module defines 27 goals grouped into 9 physiological systems. Each goal
carries an ICD-10 reference where a corresponding condition exists — these are
*navigational references*, not diagnostic claims. FeedForward never diagnoses;
it explains nutrient relationships.
"""
from __future__ import annotations

from .schema import ClinicalGoal


# System groupings (used for UI navigation and filtering)
SYSTEMS: dict[str, str] = {
    "cardiovascular": "Cardiovascular",
    "metabolic": "Metabolic & Blood Sugar",
    "musculoskeletal": "Bone, Muscle & Joint",
    "hematological": "Blood & Iron",
    "immune": "Immune & Inflammation",
    "neurocognitive": "Brain, Mood & Sleep",
    "digestive": "Digestive & Gut",
    "energy": "Energy & Endurance",
    "integumentary": "Skin & Hair",
}


_GOALS: list[ClinicalGoal] = [
    # -- Cardiovascular --
    ClinicalGoal("heart_health", "Heart Health", "cardiovascular",
                 "Support cardiovascular function and healthy lipid balance.",
                 ["I25", "I10"]),
    ClinicalGoal("blood_pressure_support", "Blood Pressure Support", "cardiovascular",
                 "Nutrients associated with healthy blood pressure regulation.",
                 ["I10"]),
    ClinicalGoal("cholesterol_management", "Cholesterol Management", "cardiovascular",
                 "Support healthy LDL/HDL balance through diet.",
                 ["E78"]),

    # -- Metabolic --
    ClinicalGoal("blood_sugar_regulation", "Blood Sugar Regulation", "metabolic",
                 "Support stable glucose response and insulin sensitivity.",
                 ["E11", "R73"]),
    ClinicalGoal("metabolic_support", "Metabolic Support", "metabolic",
                 "Broad metabolic-syndrome-relevant nutrient support.",
                 ["E88"]),
    ClinicalGoal("weight_management", "Weight Management", "metabolic",
                 "Satiety- and metabolism-supportive nutrient profiles.",
                 ["E66"]),

    # -- Musculoskeletal --
    ClinicalGoal("bone_health", "Bone Health", "musculoskeletal",
                 "Support bone mineral density and skeletal strength.",
                 ["M81", "M80"]),
    ClinicalGoal("muscle_recovery", "Muscle Recovery", "musculoskeletal",
                 "Post-exercise tissue repair and protein synthesis support.",
                 []),
    ClinicalGoal("joint_health", "Joint Health", "musculoskeletal",
                 "Nutrients associated with connective-tissue and joint support.",
                 ["M15"]),

    # -- Hematological --
    ClinicalGoal("iron_support", "Iron Support", "hematological",
                 "Support healthy iron status and oxygen transport.",
                 ["D50"]),
    ClinicalGoal("healthy_blood", "Healthy Red Blood Cells", "hematological",
                 "Support erythropoiesis (B12, folate, iron).",
                 ["D51", "D52"]),

    # -- Immune / inflammation --
    ClinicalGoal("immune_support", "Immune Support", "immune",
                 "Support normal immune function.",
                 []),
    ClinicalGoal("anti_inflammatory", "Anti-Inflammatory", "immune",
                 "Nutrients with anti-inflammatory associations.",
                 []),
    ClinicalGoal("antioxidant_support", "Antioxidant Support", "immune",
                 "Support antioxidant defences against oxidative stress.",
                 []),

    # -- Neurocognitive --
    ClinicalGoal("cognitive_function", "Cognitive Function", "neurocognitive",
                 "Support focus, memory and long-term brain health.",
                 []),
    ClinicalGoal("mood_support", "Mood Support", "neurocognitive",
                 "Nutrients associated with mood and emotional regulation.",
                 ["F32"]),
    ClinicalGoal("sleep_support", "Sleep Support", "neurocognitive",
                 "Support healthy sleep onset and quality.",
                 ["G47"]),
    ClinicalGoal("stress_resilience", "Stress Resilience", "neurocognitive",
                 "Nutrients supporting the stress response and HPA axis.",
                 []),

    # -- Digestive --
    ClinicalGoal("digestive_health", "Digestive Health", "digestive",
                 "Support regularity and gastrointestinal comfort.",
                 ["K59"]),
    ClinicalGoal("gut_microbiome", "Gut Microbiome Support", "digestive",
                 "Fibre and prebiotic support for a healthy microbiome.",
                 []),

    # -- Energy --
    ClinicalGoal("energy_metabolism", "Energy Metabolism", "energy",
                 "Support cellular energy production (B-vitamins, iron).",
                 []),
    ClinicalGoal("endurance_support", "Endurance Support", "energy",
                 "Sustained-energy nutrient profiles for endurance activity.",
                 []),
    ClinicalGoal("recovery", "General Recovery", "energy",
                 "Broad post-exertion recovery support.",
                 []),

    # -- Integumentary --
    ClinicalGoal("skin_health", "Skin Health", "integumentary",
                 "Support skin structure, hydration and repair.",
                 ["L80", "L81"]),
    ClinicalGoal("hair_health", "Hair Health", "integumentary",
                 "Nutrients associated with hair strength and growth.",
                 []),
    ClinicalGoal("vision_support", "Vision Support", "integumentary",
                 "Support eye health and normal vision (vitamin A, lutein).",
                 ["H53"]),
    ClinicalGoal("thyroid_support", "Thyroid Support", "metabolic",
                 "Iodine, selenium and zinc support for thyroid function.",
                 ["E03"]),
]


# Fast lookup structures
GOALS: dict[str, ClinicalGoal] = {g.id: g for g in _GOALS}


def all_goals() -> list[ClinicalGoal]:
    return list(_GOALS)


def goals_by_system() -> dict[str, list[ClinicalGoal]]:
    out: dict[str, list[ClinicalGoal]] = {k: [] for k in SYSTEMS}
    for g in _GOALS:
        out.setdefault(g.system, []).append(g)
    return out


def get_goal(goal_id: str) -> ClinicalGoal | None:
    return GOALS.get(goal_id)


def consumer_goals() -> list[ClinicalGoal]:
    return [g for g in _GOALS if g.consumer_visible]
