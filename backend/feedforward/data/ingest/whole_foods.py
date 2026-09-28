"""
data/ingest/whole_foods.py
==========================
Curated whole-foods reference dataset.

WHY THIS EXISTS
---------------
The OpenFoodFacts demonstration corpus is rich in branded/processed products
but its micronutrient fields are unreliable — many are off by orders of
magnitude or simply absent (max iron ~1.3 mg, max vitamin C ~0.1 mg across
1,800 items, which is physically impossible for real foods). That makes genuine
micronutrient reasoning impossible.

This module provides a small, high-accuracy corpus of staple whole foods with
per-100 g values taken from USDA FoodData Central (SR Legacy / Foundation
Foods). These are stable public reference values. The set is deliberately
curated for nutritional breadth — heme and non-heme iron sources, vitamin C
sources, calcium sources, fat for fat-soluble vitamin absorption, high-phytate
and high-oxalate foods — so the bioavailability, reference-intake and density
layers all have valid data to reason over.

Values are per 100 g edible portion. Units match FeedForward nutrient ids:
minerals & vitamin C/E in mg, vitamin A/K/D in µg, macros/omega-3 in g,
energy in kcal. Vitamin A is µg RAE; vitamin D in µg (1 µg = 40 IU).

This is a reference dataset, not a substitute for a full USDA ingest; the USDA
API connector in usda.py remains the path to scale. Provenance: USDA FDC.
"""
from __future__ import annotations

import json
from pathlib import Path

# name, category, is_animal, {nutrients per 100g}
# nutrients: kcal, protein, fat, carbs, fiber, sugars, satfat, sodium (g/mg),
#            iron, calcium, magnesium, zinc, phosphorus (mg),
#            vitamin-c, vitamin-e (mg), vitamin-a, vitamin-k, vitamin-d (µg),
#            omega-3-fat (g)
_WHOLE_FOODS: list[tuple[str, str, bool, dict]] = [
    # -------- Leafy greens & vegetables --------
    ("Spinach, raw", "Vegetables, leafy greens", False, {
        "energy-kcal": 23, "proteins": 2.9, "fat": 0.4, "carbohydrates": 3.6,
        "fiber": 2.2, "sugars": 0.4, "iron": 2.7, "calcium": 99, "magnesium": 79,
        "zinc": 0.53, "phosphorus": 49, "vitamin-c": 28, "vitamin-e": 2.0,
        "vitamin-a": 469, "vitamin-k": 483, "sodium": 79}),
    ("Kale, raw", "Vegetables, leafy greens", False, {
        "energy-kcal": 49, "proteins": 4.3, "fat": 0.9, "carbohydrates": 8.8,
        "fiber": 3.6, "sugars": 2.3, "iron": 1.5, "calcium": 150, "magnesium": 47,
        "zinc": 0.56, "phosphorus": 92, "vitamin-c": 120, "vitamin-a": 500,
        "vitamin-k": 705, "sodium": 38}),
    ("Broccoli, raw", "Vegetables", False, {
        "energy-kcal": 34, "proteins": 2.8, "fat": 0.4, "carbohydrates": 6.6,
        "fiber": 2.6, "sugars": 1.7, "iron": 0.73, "calcium": 47, "magnesium": 21,
        "zinc": 0.41, "phosphorus": 66, "vitamin-c": 89, "vitamin-a": 31,
        "vitamin-k": 102, "sodium": 33}),
    ("Swiss chard, raw", "Vegetables, leafy greens", False, {
        "energy-kcal": 19, "proteins": 1.8, "fat": 0.2, "carbohydrates": 3.7,
        "fiber": 1.6, "sugars": 1.1, "iron": 1.8, "calcium": 51, "magnesium": 81,
        "zinc": 0.36, "phosphorus": 46, "vitamin-c": 30, "vitamin-a": 306,
        "vitamin-k": 830, "sodium": 213}),
    ("Red bell pepper, raw", "Vegetables", False, {
        "energy-kcal": 31, "proteins": 1.0, "fat": 0.3, "carbohydrates": 6.0,
        "fiber": 2.1, "sugars": 4.2, "iron": 0.43, "calcium": 7, "magnesium": 12,
        "zinc": 0.25, "phosphorus": 26, "vitamin-c": 128, "vitamin-a": 157,
        "vitamin-k": 5, "sodium": 4}),
    ("Sweet potato, cooked", "Vegetables, starchy", False, {
        "energy-kcal": 90, "proteins": 2.0, "fat": 0.2, "carbohydrates": 21,
        "fiber": 3.3, "sugars": 6.5, "iron": 0.69, "calcium": 38, "magnesium": 27,
        "zinc": 0.32, "phosphorus": 54, "vitamin-c": 20, "vitamin-a": 961,
        "vitamin-k": 2.3, "sodium": 36}),
    ("Carrot, raw", "Vegetables", False, {
        "energy-kcal": 41, "proteins": 0.9, "fat": 0.2, "carbohydrates": 10,
        "fiber": 2.8, "sugars": 4.7, "iron": 0.3, "calcium": 33, "magnesium": 12,
        "zinc": 0.24, "phosphorus": 35, "vitamin-c": 5.9, "vitamin-a": 835,
        "vitamin-k": 13, "sodium": 69}),
    ("Tomato, raw", "Vegetables", False, {
        "energy-kcal": 18, "proteins": 0.9, "fat": 0.2, "carbohydrates": 3.9,
        "fiber": 1.2, "sugars": 2.6, "iron": 0.27, "calcium": 10, "magnesium": 11,
        "zinc": 0.17, "phosphorus": 24, "vitamin-c": 14, "vitamin-a": 42,
        "vitamin-k": 7.9, "sodium": 5}),
    ("Rhubarb, raw", "Vegetables", False, {
        "energy-kcal": 21, "proteins": 0.9, "fat": 0.2, "carbohydrates": 4.5,
        "fiber": 1.8, "sugars": 1.1, "iron": 0.22, "calcium": 86, "magnesium": 12,
        "zinc": 0.1, "phosphorus": 14, "vitamin-c": 8, "vitamin-k": 29, "sodium": 4}),

    # -------- Legumes (non-heme iron, high phytate) --------
    ("Lentils, cooked", "Legumes", False, {
        "energy-kcal": 116, "proteins": 9.0, "fat": 0.4, "carbohydrates": 20,
        "fiber": 7.9, "sugars": 1.8, "iron": 3.3, "calcium": 19, "magnesium": 36,
        "zinc": 1.3, "phosphorus": 180, "vitamin-c": 1.5, "vitamin-k": 1.7,
        "sodium": 2}),
    ("Chickpeas, cooked", "Legumes", False, {
        "energy-kcal": 164, "proteins": 8.9, "fat": 2.6, "carbohydrates": 27,
        "fiber": 7.6, "sugars": 4.8, "iron": 2.9, "calcium": 49, "magnesium": 48,
        "zinc": 1.5, "phosphorus": 168, "vitamin-c": 1.3, "vitamin-k": 4,
        "sodium": 7}),
    ("Black beans, cooked", "Legumes", False, {
        "energy-kcal": 132, "proteins": 8.9, "fat": 0.5, "carbohydrates": 24,
        "fiber": 8.7, "sugars": 0.3, "iron": 2.1, "calcium": 27, "magnesium": 70,
        "zinc": 1.1, "phosphorus": 140, "vitamin-c": 0, "vitamin-k": 3.3,
        "sodium": 1}),
    ("Kidney beans, cooked", "Legumes", False, {
        "energy-kcal": 127, "proteins": 8.7, "fat": 0.5, "carbohydrates": 23,
        "fiber": 6.4, "sugars": 0.3, "iron": 2.9, "calcium": 35, "magnesium": 42,
        "zinc": 1.0, "phosphorus": 138, "vitamin-c": 1.2, "vitamin-k": 8.4,
        "sodium": 1}),
    ("Tofu, firm", "Legumes, soy", False, {
        "energy-kcal": 144, "proteins": 17, "fat": 8.7, "carbohydrates": 2.8,
        "fiber": 2.3, "sugars": 0.6, "iron": 2.7, "calcium": 372, "magnesium": 58,
        "zinc": 1.6, "phosphorus": 190, "vitamin-c": 0.1, "vitamin-k": 2.4,
        "sodium": 14, "omega-3-fat": 0.6}),
    ("Edamame, cooked", "Legumes, soy", False, {
        "energy-kcal": 121, "proteins": 12, "fat": 5.2, "carbohydrates": 8.9,
        "fiber": 5.2, "sugars": 2.2, "iron": 2.3, "calcium": 63, "magnesium": 64,
        "zinc": 1.3, "phosphorus": 169, "vitamin-c": 6.1, "vitamin-k": 27,
        "sodium": 6, "omega-3-fat": 0.36}),

    # -------- Nuts & seeds (high phytate) --------
    ("Almonds", "Nuts and seeds", False, {
        "energy-kcal": 579, "proteins": 21, "fat": 50, "carbohydrates": 22,
        "fiber": 12.5, "sugars": 4.4, "saturated-fat": 3.8, "iron": 3.7,
        "calcium": 269, "magnesium": 270, "zinc": 3.1, "phosphorus": 481,
        "vitamin-e": 25.6, "vitamin-c": 0, "sodium": 1}),
    ("Walnuts", "Nuts and seeds", False, {
        "energy-kcal": 654, "proteins": 15, "fat": 65, "carbohydrates": 14,
        "fiber": 6.7, "sugars": 2.6, "saturated-fat": 6.1, "iron": 2.9,
        "calcium": 98, "magnesium": 158, "zinc": 3.1, "phosphorus": 346,
        "vitamin-e": 0.7, "sodium": 2, "omega-3-fat": 9.1}),
    ("Pumpkin seeds", "Nuts and seeds", False, {
        "energy-kcal": 559, "proteins": 30, "fat": 49, "carbohydrates": 11,
        "fiber": 6.0, "sugars": 1.4, "saturated-fat": 8.7, "iron": 8.8,
        "calcium": 46, "magnesium": 592, "zinc": 7.8, "phosphorus": 1233,
        "vitamin-c": 1.9, "sodium": 7}),
    ("Chia seeds", "Nuts and seeds", False, {
        "energy-kcal": 486, "proteins": 17, "fat": 31, "carbohydrates": 42,
        "fiber": 34, "sugars": 0, "saturated-fat": 3.3, "iron": 7.7,
        "calcium": 631, "magnesium": 335, "zinc": 4.6, "phosphorus": 860,
        "vitamin-c": 1.6, "sodium": 16, "omega-3-fat": 17.8}),
    ("Sunflower seeds", "Nuts and seeds", False, {
        "energy-kcal": 584, "proteins": 21, "fat": 51, "carbohydrates": 20,
        "fiber": 8.6, "sugars": 2.6, "saturated-fat": 4.5, "iron": 5.2,
        "calcium": 78, "magnesium": 325, "zinc": 5.0, "phosphorus": 660,
        "vitamin-e": 35, "vitamin-c": 1.4, "sodium": 9}),
    ("Flaxseed", "Nuts and seeds", False, {
        "energy-kcal": 534, "proteins": 18, "fat": 42, "carbohydrates": 29,
        "fiber": 27, "sugars": 1.5, "saturated-fat": 3.7, "iron": 5.7,
        "calcium": 255, "magnesium": 392, "zinc": 4.3, "phosphorus": 642,
        "vitamin-c": 0.6, "sodium": 30, "omega-3-fat": 22.8}),

    # -------- Whole grains (phytate) --------
    ("Oats, rolled (dry)", "Grains", False, {
        "energy-kcal": 389, "proteins": 17, "fat": 6.9, "carbohydrates": 66,
        "fiber": 11, "sugars": 0, "saturated-fat": 1.2, "iron": 4.7,
        "calcium": 54, "magnesium": 177, "zinc": 4.0, "phosphorus": 523,
        "vitamin-c": 0, "sodium": 2}),
    ("Quinoa, cooked", "Grains", False, {
        "energy-kcal": 120, "proteins": 4.4, "fat": 1.9, "carbohydrates": 21,
        "fiber": 2.8, "sugars": 0.9, "iron": 1.5, "calcium": 17, "magnesium": 64,
        "zinc": 1.1, "phosphorus": 152, "vitamin-c": 0, "sodium": 7}),
    ("Brown rice, cooked", "Grains", False, {
        "energy-kcal": 123, "proteins": 2.7, "fat": 1.0, "carbohydrates": 26,
        "fiber": 1.6, "sugars": 0.4, "iron": 0.56, "calcium": 3, "magnesium": 39,
        "zinc": 0.71, "phosphorus": 103, "vitamin-c": 0, "sodium": 4}),

    # -------- Meat & poultry (heme iron) --------
    ("Beef, ground, cooked", "Meats", True, {
        "energy-kcal": 250, "proteins": 26, "fat": 15, "carbohydrates": 0,
        "saturated-fat": 5.9, "iron": 2.7, "calcium": 18, "magnesium": 21,
        "zinc": 6.3, "phosphorus": 198, "vitamin-d": 0.1, "sodium": 72}),
    ("Beef liver, cooked", "Meats, organ", True, {
        "energy-kcal": 175, "proteins": 27, "fat": 4.9, "carbohydrates": 5.1,
        "saturated-fat": 1.6, "iron": 6.2, "calcium": 6, "magnesium": 21,
        "zinc": 4.0, "phosphorus": 497, "vitamin-c": 1.9, "vitamin-a": 9440,
        "vitamin-d": 1.2, "sodium": 76}),
    ("Chicken breast, cooked", "Meats, poultry", True, {
        "energy-kcal": 165, "proteins": 31, "fat": 3.6, "carbohydrates": 0,
        "saturated-fat": 1.0, "iron": 1.0, "calcium": 15, "magnesium": 29,
        "zinc": 1.0, "phosphorus": 228, "vitamin-d": 0.1, "sodium": 74}),
    ("Pork loin, cooked", "Meats", True, {
        "energy-kcal": 242, "proteins": 27, "fat": 14, "carbohydrates": 0,
        "saturated-fat": 4.9, "iron": 0.9, "calcium": 19, "magnesium": 28,
        "zinc": 2.4, "phosphorus": 246, "vitamin-d": 0.7, "sodium": 62}),

    # -------- Fish & seafood (omega-3, vitamin D, heme iron) --------
    ("Salmon, Atlantic, cooked", "Fish and seafood", True, {
        "energy-kcal": 206, "proteins": 22, "fat": 12, "carbohydrates": 0,
        "saturated-fat": 2.5, "iron": 0.34, "calcium": 15, "magnesium": 30,
        "zinc": 0.43, "phosphorus": 252, "vitamin-e": 3.5, "vitamin-d": 13.1,
        "sodium": 61, "omega-3-fat": 2.3}),
    ("Sardines, canned", "Fish and seafood", True, {
        "energy-kcal": 208, "proteins": 25, "fat": 11, "carbohydrates": 0,
        "saturated-fat": 1.5, "iron": 2.9, "calcium": 382, "magnesium": 39,
        "zinc": 1.3, "phosphorus": 490, "vitamin-d": 4.8, "sodium": 307,
        "omega-3-fat": 1.5}),
    ("Mackerel, cooked", "Fish and seafood", True, {
        "energy-kcal": 262, "proteins": 24, "fat": 18, "carbohydrates": 0,
        "saturated-fat": 4.2, "iron": 1.6, "calcium": 15, "magnesium": 97,
        "zinc": 0.9, "phosphorus": 236, "vitamin-d": 13.8, "sodium": 83,
        "omega-3-fat": 2.6}),
    ("Tuna, canned in water", "Fish and seafood", True, {
        "energy-kcal": 116, "proteins": 26, "fat": 0.8, "carbohydrates": 0,
        "saturated-fat": 0.2, "iron": 1.3, "calcium": 11, "magnesium": 33,
        "zinc": 0.66, "phosphorus": 184, "vitamin-d": 1.7, "sodium": 247,
        "omega-3-fat": 0.27}),
    ("Oysters, cooked", "Fish and seafood", True, {
        "energy-kcal": 79, "proteins": 9.0, "fat": 2.1, "carbohydrates": 4.9,
        "iron": 6.7, "calcium": 45, "magnesium": 47, "zinc": 78, "phosphorus": 156,
        "vitamin-d": 8, "sodium": 106, "omega-3-fat": 0.7}),

    # -------- Eggs & dairy (calcium, vitamin D) --------
    ("Egg, whole, cooked", "Eggs", True, {
        "energy-kcal": 155, "proteins": 13, "fat": 11, "carbohydrates": 1.1,
        "saturated-fat": 3.3, "iron": 1.2, "calcium": 50, "magnesium": 10,
        "zinc": 1.1, "phosphorus": 172, "vitamin-a": 149, "vitamin-d": 2.2,
        "vitamin-e": 1.0, "sodium": 124}),
    ("Milk, whole", "Dairy", True, {
        "energy-kcal": 61, "proteins": 3.2, "fat": 3.3, "carbohydrates": 4.8,
        "sugars": 5.1, "saturated-fat": 1.9, "iron": 0.03, "calcium": 113,
        "magnesium": 10, "zinc": 0.37, "phosphorus": 84, "vitamin-a": 46,
        "vitamin-d": 1.3, "sodium": 43}),
    ("Greek yogurt, plain", "Dairy", True, {
        "energy-kcal": 59, "proteins": 10, "fat": 0.4, "carbohydrates": 3.6,
        "sugars": 3.2, "iron": 0.07, "calcium": 110, "magnesium": 11,
        "zinc": 0.52, "phosphorus": 135, "vitamin-a": 1, "sodium": 36}),
    ("Cheddar cheese", "Dairy", True, {
        "energy-kcal": 404, "proteins": 23, "fat": 33, "carbohydrates": 3.1,
        "sugars": 0.5, "saturated-fat": 19, "iron": 0.68, "calcium": 721,
        "magnesium": 28, "zinc": 3.1, "phosphorus": 512, "vitamin-a": 265,
        "vitamin-d": 0.6, "sodium": 653}),

    # -------- Fruits (vitamin C) --------
    ("Orange, raw", "Fruits", False, {
        "energy-kcal": 47, "proteins": 0.9, "fat": 0.1, "carbohydrates": 12,
        "fiber": 2.4, "sugars": 9.4, "iron": 0.1, "calcium": 40, "magnesium": 10,
        "zinc": 0.07, "phosphorus": 14, "vitamin-c": 53, "vitamin-a": 11,
        "sodium": 0}),
    ("Strawberries, raw", "Fruits", False, {
        "energy-kcal": 32, "proteins": 0.7, "fat": 0.3, "carbohydrates": 7.7,
        "fiber": 2.0, "sugars": 4.9, "iron": 0.41, "calcium": 16, "magnesium": 13,
        "zinc": 0.14, "phosphorus": 24, "vitamin-c": 59, "vitamin-k": 2.2,
        "sodium": 1}),
    ("Kiwi, raw", "Fruits", False, {
        "energy-kcal": 61, "proteins": 1.1, "fat": 0.5, "carbohydrates": 15,
        "fiber": 3.0, "sugars": 9.0, "iron": 0.31, "calcium": 34, "magnesium": 17,
        "zinc": 0.14, "phosphorus": 34, "vitamin-c": 93, "vitamin-k": 40,
        "vitamin-e": 1.5, "sodium": 3}),
    ("Blueberries, raw", "Fruits", False, {
        "energy-kcal": 57, "proteins": 0.7, "fat": 0.3, "carbohydrates": 14,
        "fiber": 2.4, "sugars": 10, "iron": 0.28, "calcium": 6, "magnesium": 6,
        "zinc": 0.16, "phosphorus": 12, "vitamin-c": 9.7, "vitamin-k": 19,
        "vitamin-e": 0.6, "sodium": 1}),
    ("Banana, raw", "Fruits", False, {
        "energy-kcal": 89, "proteins": 1.1, "fat": 0.3, "carbohydrates": 23,
        "fiber": 2.6, "sugars": 12, "iron": 0.26, "calcium": 5, "magnesium": 27,
        "zinc": 0.15, "phosphorus": 22, "vitamin-c": 8.7, "sodium": 1}),
    ("Avocado, raw", "Fruits", False, {
        "energy-kcal": 160, "proteins": 2.0, "fat": 15, "carbohydrates": 9,
        "fiber": 6.7, "sugars": 0.7, "saturated-fat": 2.1, "iron": 0.55,
        "calcium": 12, "magnesium": 29, "zinc": 0.64, "phosphorus": 52,
        "vitamin-c": 10, "vitamin-e": 2.1, "vitamin-k": 21, "sodium": 7,
        "omega-3-fat": 0.11}),

    # -------- Other --------
    ("Dark chocolate, 70-85%", "Other", False, {
        "energy-kcal": 598, "proteins": 7.8, "fat": 43, "carbohydrates": 46,
        "fiber": 11, "sugars": 24, "saturated-fat": 24, "iron": 12,
        "calcium": 73, "magnesium": 228, "zinc": 3.3, "phosphorus": 308,
        "sodium": 20}),
    ("Fortified breakfast cereal", "Grains, fortified", False, {
        "energy-kcal": 375, "proteins": 8, "fat": 3.5, "carbohydrates": 84,
        "fiber": 7, "sugars": 25, "iron": 28, "calcium": 500, "magnesium": 90,
        "zinc": 15, "phosphorus": 200, "vitamin-c": 60, "vitamin-a": 450,
        "vitamin-d": 4.2, "sodium": 400, "folate": 680, "vitamin-b12": 6}),

    # ======== BATCH 2: broader coverage + trace minerals/B-vitamins ========
    # -------- More vegetables --------
    ("Broccoli, cooked", "Vegetables", False, {
        "energy-kcal": 35, "proteins": 2.4, "fat": 0.4, "carbohydrates": 7.2,
        "fiber": 3.3, "sugars": 1.4, "iron": 0.67, "calcium": 40, "magnesium": 21,
        "zinc": 0.45, "phosphorus": 67, "potassium": 293, "vitamin-c": 65,
        "vitamin-a": 77, "vitamin-k": 141, "folate": 108, "copper": 0.05,
        "sodium": 41}),
    ("Brussels sprouts, cooked", "Vegetables", False, {
        "energy-kcal": 36, "proteins": 2.6, "fat": 0.5, "carbohydrates": 7.1,
        "fiber": 2.6, "sugars": 1.7, "iron": 1.2, "calcium": 36, "magnesium": 20,
        "zinc": 0.33, "phosphorus": 56, "potassium": 317, "vitamin-c": 62,
        "vitamin-k": 140, "folate": 60, "sodium": 21}),
    ("Cauliflower, raw", "Vegetables", False, {
        "energy-kcal": 25, "proteins": 1.9, "fat": 0.3, "carbohydrates": 5.0,
        "fiber": 2.0, "sugars": 1.9, "iron": 0.44, "calcium": 22, "magnesium": 15,
        "zinc": 0.27, "phosphorus": 44, "potassium": 299, "vitamin-c": 48,
        "vitamin-k": 15, "folate": 57, "sodium": 30}),
    ("Asparagus, cooked", "Vegetables", False, {
        "energy-kcal": 22, "proteins": 2.4, "fat": 0.2, "carbohydrates": 4.1,
        "fiber": 2.0, "sugars": 1.3, "iron": 0.91, "calcium": 23, "magnesium": 14,
        "zinc": 0.6, "phosphorus": 54, "potassium": 224, "vitamin-c": 7.7,
        "vitamin-a": 50, "vitamin-k": 51, "folate": 149, "sodium": 14}),
    ("Green peas, cooked", "Vegetables", False, {
        "energy-kcal": 84, "proteins": 5.4, "fat": 0.2, "carbohydrates": 16,
        "fiber": 5.5, "sugars": 5.9, "iron": 1.5, "calcium": 27, "magnesium": 39,
        "zinc": 1.2, "phosphorus": 117, "potassium": 271, "vitamin-c": 14,
        "vitamin-a": 40, "vitamin-k": 24, "folate": 65, "sodium": 3}),
    ("Beetroot, cooked", "Vegetables", False, {
        "energy-kcal": 44, "proteins": 1.7, "fat": 0.2, "carbohydrates": 10,
        "fiber": 2.0, "sugars": 8, "iron": 0.79, "calcium": 16, "magnesium": 23,
        "zinc": 0.35, "phosphorus": 38, "potassium": 305, "vitamin-c": 3.6,
        "folate": 80, "sodium": 77}),
    ("Mushrooms, white, raw", "Vegetables", False, {
        "energy-kcal": 22, "proteins": 3.1, "fat": 0.3, "carbohydrates": 3.3,
        "fiber": 1.0, "sugars": 2.0, "iron": 0.5, "calcium": 3, "magnesium": 9,
        "zinc": 0.52, "phosphorus": 86, "potassium": 318, "vitamin-c": 2.1,
        "vitamin-d": 0.2, "selenium": 9.3, "copper": 0.32, "folate": 17,
        "sodium": 5}),
    ("Potato, baked with skin", "Vegetables, starchy", False, {
        "energy-kcal": 93, "proteins": 2.5, "fat": 0.1, "carbohydrates": 21,
        "fiber": 2.2, "sugars": 1.2, "iron": 1.1, "calcium": 15, "magnesium": 28,
        "zinc": 0.36, "phosphorus": 70, "potassium": 535, "vitamin-c": 9.6,
        "folate": 28, "sodium": 10}),
    ("Onion, raw", "Vegetables", False, {
        "energy-kcal": 40, "proteins": 1.1, "fat": 0.1, "carbohydrates": 9.3,
        "fiber": 1.7, "sugars": 4.2, "iron": 0.21, "calcium": 23, "magnesium": 10,
        "zinc": 0.17, "phosphorus": 29, "potassium": 146, "vitamin-c": 7.4,
        "folate": 19, "sodium": 4}),
    ("Garlic, raw", "Vegetables", False, {
        "energy-kcal": 149, "proteins": 6.4, "fat": 0.5, "carbohydrates": 33,
        "fiber": 2.1, "sugars": 1.0, "iron": 1.7, "calcium": 181, "magnesium": 25,
        "zinc": 1.2, "phosphorus": 153, "potassium": 401, "vitamin-c": 31,
        "selenium": 14.2, "manganese": 1.7, "sodium": 17}),

    # -------- More fruits --------
    ("Apple, raw with skin", "Fruits", False, {
        "energy-kcal": 52, "proteins": 0.3, "fat": 0.2, "carbohydrates": 14,
        "fiber": 2.4, "sugars": 10, "iron": 0.12, "calcium": 6, "magnesium": 5,
        "potassium": 107, "vitamin-c": 4.6, "vitamin-k": 2.2, "sodium": 1}),
    ("Mango, raw", "Fruits", False, {
        "energy-kcal": 60, "proteins": 0.8, "fat": 0.4, "carbohydrates": 15,
        "fiber": 1.6, "sugars": 14, "iron": 0.16, "calcium": 11, "magnesium": 10,
        "potassium": 168, "vitamin-c": 36, "vitamin-a": 54, "folate": 43,
        "sodium": 1}),
    ("Papaya, raw", "Fruits", False, {
        "energy-kcal": 43, "proteins": 0.5, "fat": 0.3, "carbohydrates": 11,
        "fiber": 1.7, "sugars": 7.8, "iron": 0.25, "calcium": 20, "magnesium": 21,
        "potassium": 182, "vitamin-c": 61, "vitamin-a": 47, "folate": 37,
        "sodium": 8}),
    ("Guava, raw", "Fruits", False, {
        "energy-kcal": 68, "proteins": 2.6, "fat": 1.0, "carbohydrates": 14,
        "fiber": 5.4, "sugars": 8.9, "iron": 0.26, "calcium": 18, "magnesium": 22,
        "potassium": 417, "vitamin-c": 228, "vitamin-a": 31, "folate": 49,
        "sodium": 2}),
    ("Pineapple, raw", "Fruits", False, {
        "energy-kcal": 50, "proteins": 0.5, "fat": 0.1, "carbohydrates": 13,
        "fiber": 1.4, "sugars": 9.9, "iron": 0.29, "calcium": 13, "magnesium": 12,
        "potassium": 109, "vitamin-c": 48, "manganese": 0.93, "folate": 18,
        "sodium": 1}),
    ("Grapes, raw", "Fruits", False, {
        "energy-kcal": 69, "proteins": 0.7, "fat": 0.2, "carbohydrates": 18,
        "fiber": 0.9, "sugars": 16, "iron": 0.36, "calcium": 10, "magnesium": 7,
        "potassium": 191, "vitamin-c": 3.2, "vitamin-k": 15, "sodium": 2}),
    ("Pomegranate, raw", "Fruits", False, {
        "energy-kcal": 83, "proteins": 1.7, "fat": 1.2, "carbohydrates": 19,
        "fiber": 4.0, "sugars": 14, "iron": 0.3, "calcium": 10, "magnesium": 12,
        "potassium": 236, "vitamin-c": 10, "vitamin-k": 16, "folate": 38,
        "sodium": 3}),

    # -------- More legumes --------
    ("White beans, cooked", "Legumes", False, {
        "energy-kcal": 139, "proteins": 9.7, "fat": 0.4, "carbohydrates": 25,
        "fiber": 6.3, "sugars": 0.3, "iron": 3.7, "calcium": 90, "magnesium": 63,
        "zinc": 1.4, "phosphorus": 113, "potassium": 561, "copper": 0.26,
        "folate": 81, "sodium": 6}),
    ("Pinto beans, cooked", "Legumes", False, {
        "energy-kcal": 143, "proteins": 9.0, "fat": 0.7, "carbohydrates": 26,
        "fiber": 9.0, "sugars": 0.3, "iron": 2.1, "calcium": 46, "magnesium": 50,
        "zinc": 0.98, "phosphorus": 147, "potassium": 436, "copper": 0.22,
        "folate": 172, "sodium": 1}),
    ("Soybeans, cooked", "Legumes, soy", False, {
        "energy-kcal": 173, "proteins": 17, "fat": 9, "carbohydrates": 10,
        "fiber": 6.0, "sugars": 3, "iron": 5.1, "calcium": 102, "magnesium": 86,
        "zinc": 1.2, "phosphorus": 245, "potassium": 515, "copper": 0.41,
        "folate": 54, "sodium": 1, "omega-3-fat": 0.6}),
    ("Split peas, cooked", "Legumes", False, {
        "energy-kcal": 118, "proteins": 8.3, "fat": 0.4, "carbohydrates": 21,
        "fiber": 8.3, "sugars": 2.9, "iron": 1.3, "calcium": 14, "magnesium": 36,
        "zinc": 1.0, "phosphorus": 99, "potassium": 362, "folate": 65,
        "sodium": 2}),
    ("Tempeh", "Legumes, soy", False, {
        "energy-kcal": 192, "proteins": 20, "fat": 11, "carbohydrates": 8,
        "fiber": 0, "iron": 2.7, "calcium": 111, "magnesium": 81, "zinc": 1.1,
        "phosphorus": 266, "potassium": 412, "copper": 0.56, "vitamin-b12": 0.1,
        "sodium": 9, "omega-3-fat": 0.3}),

    # -------- More nuts & seeds --------
    ("Cashews", "Nuts and seeds", False, {
        "energy-kcal": 553, "proteins": 18, "fat": 44, "carbohydrates": 30,
        "fiber": 3.3, "sugars": 5.9, "saturated-fat": 7.8, "iron": 6.7,
        "calcium": 37, "magnesium": 292, "zinc": 5.8, "phosphorus": 593,
        "potassium": 660, "copper": 2.2, "selenium": 19.9, "sodium": 12}),
    ("Pistachios", "Nuts and seeds", False, {
        "energy-kcal": 560, "proteins": 20, "fat": 45, "carbohydrates": 28,
        "fiber": 10, "sugars": 7.7, "saturated-fat": 5.9, "iron": 3.9,
        "calcium": 105, "magnesium": 121, "zinc": 2.2, "phosphorus": 490,
        "potassium": 1025, "copper": 1.3, "folate": 51,
        "sodium": 1}),
    ("Peanuts", "Nuts and seeds", False, {
        "energy-kcal": 567, "proteins": 26, "fat": 49, "carbohydrates": 16,
        "fiber": 8.5, "sugars": 4.7, "saturated-fat": 6.8, "iron": 4.6,
        "calcium": 92, "magnesium": 168, "zinc": 3.3, "phosphorus": 376,
        "potassium": 705, "copper": 1.1, "folate": 240, "vitamin-e": 8.3,
        "sodium": 18}),
    ("Hazelnuts", "Nuts and seeds", False, {
        "energy-kcal": 628, "proteins": 15, "fat": 61, "carbohydrates": 17,
        "fiber": 9.7, "sugars": 4.3, "saturated-fat": 4.5, "iron": 4.7,
        "calcium": 114, "magnesium": 163, "zinc": 2.5, "phosphorus": 290,
        "potassium": 680, "copper": 1.7, "vitamin-e": 15, "folate": 113,
        "sodium": 0}),
    ("Brazil nuts", "Nuts and seeds", False, {
        "energy-kcal": 659, "proteins": 14, "fat": 67, "carbohydrates": 12,
        "fiber": 7.5, "sugars": 2.3, "saturated-fat": 16, "iron": 2.4,
        "calcium": 160, "magnesium": 376, "zinc": 4.1, "phosphorus": 725,
        "potassium": 659, "copper": 1.7, "selenium": 1917, "sodium": 3}),
    ("Sesame seeds", "Nuts and seeds", False, {
        "energy-kcal": 573, "proteins": 18, "fat": 50, "carbohydrates": 23,
        "fiber": 12, "sugars": 0.3, "saturated-fat": 7, "iron": 14.6,
        "calcium": 975, "magnesium": 351, "zinc": 7.8, "phosphorus": 629,
        "potassium": 468, "copper": 4.1, "sodium": 11}),

    # -------- More fish & seafood --------
    ("Shrimp, cooked", "Fish and seafood", True, {
        "energy-kcal": 99, "proteins": 24, "fat": 0.3, "carbohydrates": 0.2,
        "iron": 0.51, "calcium": 70, "magnesium": 39, "zinc": 1.6,
        "phosphorus": 237, "potassium": 259, "selenium": 38, "copper": 0.2,
        "vitamin-b12": 1.5, "vitamin-d": 0.1, "sodium": 111, "omega-3-fat": 0.3}),
    ("Cod, cooked", "Fish and seafood", True, {
        "energy-kcal": 105, "proteins": 23, "fat": 0.9, "carbohydrates": 0,
        "iron": 0.49, "calcium": 14, "magnesium": 38, "zinc": 0.58,
        "phosphorus": 248, "potassium": 244, "selenium": 37, "vitamin-b12": 1.0,
        "vitamin-d": 1.2, "sodium": 78, "omega-3-fat": 0.2}),
    ("Trout, cooked", "Fish and seafood", True, {
        "energy-kcal": 190, "proteins": 27, "fat": 8.5, "carbohydrates": 0,
        "saturated-fat": 1.9, "iron": 0.36, "calcium": 86, "magnesium": 33,
        "zinc": 0.83, "phosphorus": 293, "potassium": 448, "selenium": 15,
        "vitamin-b12": 7.5, "vitamin-d": 16, "sodium": 61, "omega-3-fat": 1.0}),
    ("Mussels, cooked", "Fish and seafood", True, {
        "energy-kcal": 172, "proteins": 24, "fat": 4.5, "carbohydrates": 7.4,
        "iron": 6.7, "calcium": 33, "magnesium": 37, "zinc": 2.7,
        "phosphorus": 285, "potassium": 268, "selenium": 89, "vitamin-b12": 24,
        "vitamin-d": 0.1, "sodium": 369, "omega-3-fat": 0.7}),

    # -------- More meat & poultry --------
    ("Turkey breast, cooked", "Meats, poultry", True, {
        "energy-kcal": 147, "proteins": 30, "fat": 2.1, "carbohydrates": 0,
        "saturated-fat": 0.7, "iron": 1.2, "calcium": 12, "magnesium": 28,
        "zinc": 1.7, "phosphorus": 210, "potassium": 249, "selenium": 31,
        "vitamin-b12": 1.1, "sodium": 63}),
    ("Lamb, cooked", "Meats", True, {
        "energy-kcal": 258, "proteins": 25, "fat": 17, "carbohydrates": 0,
        "saturated-fat": 7, "iron": 1.9, "calcium": 9, "magnesium": 23,
        "zinc": 4.5, "phosphorus": 188, "potassium": 310, "selenium": 27,
        "vitamin-b12": 2.7, "sodium": 72}),
    ("Chicken thigh, cooked", "Meats, poultry", True, {
        "energy-kcal": 209, "proteins": 26, "fat": 11, "carbohydrates": 0,
        "saturated-fat": 3, "iron": 1.3, "calcium": 12, "magnesium": 23,
        "zinc": 2.4, "phosphorus": 193, "potassium": 240, "selenium": 26,
        "vitamin-b12": 0.6, "sodium": 88}),

    # -------- Dairy & eggs --------
    ("Cottage cheese, low-fat", "Dairy", True, {
        "energy-kcal": 72, "proteins": 12, "fat": 1.0, "carbohydrates": 4.3,
        "sugars": 4.3, "iron": 0.07, "calcium": 61, "magnesium": 5, "zinc": 0.4,
        "phosphorus": 134, "potassium": 84, "selenium": 9.7, "vitamin-b12": 0.6,
        "sodium": 330}),
    ("Egg yolk", "Eggs", True, {
        "energy-kcal": 322, "proteins": 16, "fat": 27, "carbohydrates": 3.6,
        "saturated-fat": 10, "iron": 2.7, "calcium": 129, "magnesium": 5,
        "zinc": 2.3, "phosphorus": 390, "selenium": 56, "vitamin-a": 381,
        "vitamin-d": 5.4, "folate": 146, "vitamin-b12": 2.0, "sodium": 48}),

    # -------- Grains --------
    ("Whole wheat bread", "Grains", False, {
        "energy-kcal": 247, "proteins": 13, "fat": 3.4, "carbohydrates": 41,
        "fiber": 7, "sugars": 6, "iron": 2.5, "calcium": 107, "magnesium": 82,
        "zinc": 1.8, "phosphorus": 212, "potassium": 250, "selenium": 28,
        "folate": 42, "sodium": 450}),
    ("Buckwheat, cooked", "Grains", False, {
        "energy-kcal": 92, "proteins": 3.4, "fat": 0.6, "carbohydrates": 20,
        "fiber": 2.7, "sugars": 0.9, "iron": 0.8, "calcium": 7, "magnesium": 51,
        "zinc": 0.61, "phosphorus": 70, "potassium": 88, "copper": 0.15,
        "sodium": 4}),
    ("Barley, cooked", "Grains", False, {
        "energy-kcal": 123, "proteins": 2.3, "fat": 0.4, "carbohydrates": 28,
        "fiber": 3.8, "sugars": 0.3, "iron": 1.3, "calcium": 11, "magnesium": 22,
        "zinc": 0.82, "phosphorus": 54, "potassium": 93, "selenium": 8.6,
        "sodium": 3}),

    # -------- Other nutrient-dense staples --------
    ("Nutritional yeast", "Other, fortified", False, {
        "energy-kcal": 325, "proteins": 45, "fat": 5, "carbohydrates": 36,
        "fiber": 20, "iron": 9.7, "magnesium": 120, "zinc": 17, "phosphorus": 1290,
        "potassium": 1700, "folate": 590, "vitamin-b12": 44, "sodium": 51}),
    ("Seaweed, dried (nori)", "Vegetables, sea", False, {
        "energy-kcal": 35, "proteins": 6, "fat": 0.3, "carbohydrates": 5,
        "fiber": 0.3, "iron": 1.8, "calcium": 70, "magnesium": 2, "zinc": 1.1,
        "potassium": 356, "vitamin-c": 39, "vitamin-a": 260, "folate": 146,
        "vitamin-b12": 0.3, "sodium": 48}),
    ("Molasses, blackstrap", "Other", False, {
        "energy-kcal": 290, "proteins": 0, "fat": 0.1, "carbohydrates": 75,
        "sugars": 55, "iron": 4.7, "calcium": 205, "magnesium": 242, "zinc": 0.29,
        "potassium": 1464, "copper": 0.49, "manganese": 1.5, "sodium": 37}),
]


def build_records() -> list[dict]:
    """Emit foods.json-format records with stable ids (wf-<n>)."""
    out = []
    for i, (name, category, is_animal, nutrients) in enumerate(_WHOLE_FOODS, 1):
        out.append({
            "id": f"wf-{i:03d}",
            "name": name,
            "category": category,
            "nutrients": {k: v for k, v in nutrients.items() if v is not None},
            "nutri_score": "",
            "nova": 1,
            "_source": "USDA FoodData Central (curated reference)",
            "_is_animal": is_animal,
        })
    return out


def write(path: Path | None = None) -> Path:
    path = path or (Path(__file__).resolve().parent.parent / "whole_foods.json")
    records = build_records()
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    return path


if __name__ == "__main__":
    p = write()
    print(f"Wrote {len(build_records())} curated whole foods to {p}")
