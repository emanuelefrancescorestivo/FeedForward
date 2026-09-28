# Scientific Basis

FeedForward's credibility rests on two modelling choices: how it grades
evidence, and how it models bioavailability. This document explains both, and
is deliberately explicit about what is and isn't claimed.

## What FeedForward is (and isn't)

FeedForward is a **nutritional information and reasoning tool**. It surfaces
associations between nutrients and physiological goals, weighted by evidence
strength and absorption. It is **not** a diagnostic tool, does not provide
medical advice, and does not personalise to a diagnosed condition. ICD-10
references in the taxonomy are navigational aids for professionals, not
diagnostic claims.

## Evidence grading

Each nutrient→goal association carries a grade, adapted from the Oxford CEBM
Levels of Evidence and GRADE, collapsed into four product-facing tiers:

| Grade | Meaning | Basis |
|-------|---------|-------|
| **A** | Strong | Meta-analyses / systematic reviews of RCTs (e.g. Cochrane) |
| **B** | Moderate | Individual RCTs or strong pooled cohort evidence |
| **C** | Limited | Observational studies, mechanistic/biochemical evidence |
| **D** | Preliminary | Expert opinion, traditional use, single small studies |

The grade becomes a multiplier on the edge (`A=1.0, B=0.85, C=0.6, D=0.35`), so
better-evidenced associations produce stronger recommendations.

**Two grading modes** ([`engine/evidence.py`](../backend/feedforward/engine/evidence.py)):

1. **Curated** (default) — a maintained table of grades with representative
   PMIDs. Deterministic and offline; this is what ships and what tests use.
2. **PubMed** (opt-in) — queries NCBI E-utilities, counts total literature and
   the subset that is RCT/meta-analytic, and derives a grade from volume and
   study type. Results are disk-cached; on any failure it falls back to curated.

The PubMed thresholds (`A: ≥40 RCT/meta & ≥150 total`, etc.) are conservative
and documented so they can be tuned against expert review.

## Bioavailability model

This is the core differentiator. Nutrient *content* is not nutrient *delivery*.
The model ([`engine/bioavailability.py`](../backend/feedforward/engine/bioavailability.py))
adjusts each Food→Nutrient edge by an absorption factor, and further adjusts for
meal composition.

Encoded mechanisms include:

- **Iron form.** Heme iron (animal flesh) ~25% absorbed; non-heme iron (plants)
  ~10% baseline and highly modifiable.
- **Vitamin C × non-heme iron.** Vitamin C reduces Fe³⁺ to absorbable Fe²⁺,
  raising non-heme iron absorption substantially (modelled ×2.5 at meal level).
- **Calcium × iron competition.** High calcium in a meal inhibits iron
  absorption (×0.6).
- **Fat-soluble vitamins (A, D, E, K).** Require dietary fat; absorption is
  reduced without it and enhanced with it (×1.4 at meal level).
- **Vitamin D × calcium.** Vitamin D promotes active calcium absorption (×1.3).
- **Oxalates.** Calcium from high-oxalate greens (spinach) is poorly absorbed
  (~5–6%).

### Why rules, not a black box

We deliberately use an explicit rule base rather than a learned model. For a
health product, **auditability is the feature**: every adjustment traces to a
documented mechanism a dietitian can inspect and cite, and a consumer can
understand. A parametric model might fit better but couldn't explain itself —
which would defeat the entire premise.

## Representative sources

- Hurrell R, Egli I. *Iron bioavailability and dietary reference values.* Am J Clin Nutr, 2010.
- Institute of Medicine. *Dietary Reference Intakes* (iron, calcium, zinc, vitamin D).
- Heaney RP. *Calcium, dairy products and osteoporosis.* J Am Coll Nutr, 2000.
- Lönnerdal B. *Dietary factors influencing zinc absorption.* J Nutr, 2000.
- Shoba G, et al. *Influence of piperine on the pharmacokinetics of curcumin.* Planta Med, 1998.

Full citations and PMIDs are attached per-association in the curated evidence
table and surfaced to professional-tier users.

## Reproducibility

The engine is deterministic in curated mode. `build_engine()` builds the same
graph every time; the test suite asserts algorithmic correctness (Dijkstra,
reverse-Dijkstra equivalence, Yen), bioavailability ordering (heme > non-heme;
vitamin C boosts iron; fat aids fat-soluble vitamins), and evidence grade
ordering. Run `pytest -q`.

---

## Deepened engine (v1.1): five scientific layers

The engine was extended from a single bioavailability pass into five composable,
independently-sourced layers. Each is auditable and fast (the full stack adds
< 1 ms per query; see the benchmark in the README).

### 1. Reference intakes (DRI) — `engine/reference.py`
RDA/AI values for tracked nutrients across seven demographic groups (IOM/NASEM
DRIs, cross-checked against EFSA DRVs). This turns "contains 3 mg iron" into
"covers X% of *your* daily need" — and the % is demographic-aware (the same
6.5 mg iron is 81% of a man's RDA but 36% of a premenopausal woman's). Tolerable
Upper Intake Levels are included, and "limit nutrients" (sodium, saturated fat,
added sugars) are expressed against upper guidance rather than as targets.

### 2. Interaction matrix — `data/interactions.json` + `engine/bioavailability.py`
The absorption rules are now data-driven: ~17 documented nutrient interactions
(enhancers and inhibitors) with per-interaction magnitude, mechanism, evidence
grade and citations. Adding an interaction is a data edit, not a code change.
The engine models *competing* effects simultaneously — e.g. lentils' phytate
(×0.45, inhibits) and a meal's vitamin C (×2.5, enhances) both apply, and the
net absorbable iron reflects both.

### 3. Anti-nutrient model — `engine/build.py`
Foods are enriched at load time with detected anti-nutrient loads (phytate,
oxalate, tannin) that feed the interaction matrix. In the demonstration corpus
this flags the expected foods (legumes/grains/nuts for phytate; spinach/rhubarb
for oxalate).

### 4. Nutrient density score — `engine/density.py`
A transparent NRF-style index (Drewnowski): Σ capped %DV of beneficial nutrients
minus Σ %-of-limit of nutrients to restrict, energy-adjusted per 100 kcal with a
low-calorie floor to avoid the well-known near-zero-energy artifact. Every term
is inspectable.

### 5. Caution layer — `engine/cautions.py`
Informational food-drug and food-condition flags (e.g. vitamin K × warfarin,
vitamin A × pregnancy, calcium × thyroid medication, high sodium × blood
pressure). **Every flag is framed as educational and defers to a qualified
professional — FeedForward never gives medical advice.**

## Scoring model (v1.3)

`engine/scoring.py` defines what a recommendation means: how much **one
realistic portion** of a food supports a goal.

| Step | Definition | Why |
|---|---|---|
| Portion | Reference portion by food group (`data/portions.json`) | 100 g of baking powder or dried sage is not a serving |
| Delivery | portion amount ÷ DRI × relative bioavailability, saturated as 1 − e^(−4x) | 30% of need per portion (EU "high in") ≈ 0.70; 100% ≈ 0.98 |
| Bioavailability (single food) | Iron form (heme 25% / non-heme 10%, vs the 18% the RDA assumes) and oxalate on calcium | Meal factors (×2.5 for added vitamin C, phytate) come from meal studies and are applied to meals, not to a food's own composition |
| Upper limits | Portion above a UL that applies to food: delivery ×0.25 and the food ×0.6 for every goal | Liver's vitamin A should not make it the top bone-health food |
| Association | weight × evidence multiplier | as before |
| Combination | 1 − (1 − p₁) Π(1 − 0.5 pᵢ) | the goal's main nutrient dominates; many weak routes do not add up to one strong one |
| Penalties | sodium, saturated fat, sugars per portion vs daily limit; goal-specific when the goal has a negative edge | a salty food is not a blood-pressure food |
| Enhancers | `type: enhancer` edges (vitamin C → iron support) are not routes | vitamin C improves absorption; it does not supply iron |

All constants are documented in the module, tested, and meant to be reviewed
with dietitians. Omega-3 (IOM ALA AI) and carbohydrate (IOM RDA 130 g) reference
values were added so their goals can be scored.

## EU health claims (v1.4) — the knowledge layer

Nutrient → goal edges now rest on the **EU Register of nutrition and health
claims** (Regulation (EC) No 1924/2006), downloaded from the Commission's Food
and Feed Information Portal and rebuilt with
`python -m feedforward.data.ingest.eu_claims --fetch`. Snapshot of 2026-09-26:
269 authorised and 2,067 non-authorised claims.

| Register entry | Effect on the graph |
|---|---|
| Authorised claim, nutrient in the ontology, wording mapped to a goal (`data/eu_claim_rules.json`) | Edge with grade **A**, source `eu_authorised`, the **official wording** as explanation, EFSA opinion as citation (118 edges) |
| Rejected because the effect was not substantiated (HC_RR_130/132), no authorised claim for the pair | Existing edge becomes `type: rejected`: never a route, shown with EFSA's reason (62 pairs: e.g. vitamin E → heart, immunity, bone, skin; magnesium → blood pressure, immunity, stress; calcium → blood pressure; omega-3 → joints, bone) |
| Scraped (Wikipedia) vitamin/mineral edge with no authorised claim | Graded **D** — EFSA reviewed vitamin and mineral functions systematically |
| Curated edge with no claim either way | Keeps its grade, flagged `eu_claim: false` (e.g. magnesium → sleep) |
| Curated grade-A association with a narrower rejected claim | Kept, with the rejection recorded next to it (carbohydrate → endurance) |

Mapping choices are data and documented: psychological function maps to mood
only (EFSA rejected magnesium for "resistance to mental stress"); nervous-system
claims count at 0.4 towards cognition; claims whose conditions of use exceed a
portion of food (3 g/day EPA+DHA for blood pressure, 2 g/day for triglycerides)
count at 0.3. The ontology gained the B vitamins, choline, iodine, EPA+DHA and
ALA so that these claims reach foods (USDA values for 36 nutrients).

**Only an `eu_claim: true` explanation is authorised health-claim wording.** The
API exposes the flag so the app never phrases a non-authorised association as
a claim.

**What the register says about the goals:**
- `stress_resilience` has **no** supported nutrient (declared evidence gap).
- `sleep_support` rests on curated magnesium (grade C) only; the one
  authorised sleep claim is for melatonin, which is not a food nutrient.
- 8 goals have routes but no authorised claim behind any of them (blood sugar,
  weight, inflammation, sleep, digestion, microbiome, endurance, recovery).

## Week planner (v1.5) — needs, budget, recipes

**Personal needs** (`engine/needs.py`). Energy = Mifflin–St Jeor resting
energy × physical activity level (1.2 sedentary … 1.9 very active), +340 kcal
in pregnancy, +500 kcal when breastfeeding. Protein = max(reference intake,
0.83 g/kg, the EFSA adult PRI). Vitamins and minerals follow the age/sex
reference intakes of `engine/reference.py`; weight and height do not change
them. The profile takes no medical conditions: condition-specific advice is a
medical decision, and would make the app a medical device under the EU MDR.

**Composition.** Recipes are costed and scored with ANSES-CIQUAL 2020. Vitamin A
is RAE = retinol + β-carotene/12; omega-3 = ALA + EPA + DHA; where CIQUAL gives
no energy value it is computed with the EU 1169/2011 Annex XIV factors, and the
record says so (`_energy_method`).

**Plan model** (`engine/week_planner.py`, MILP, PuLP/CBC). Integer servings of
each recipe per meal slot (7 breakfasts, lunches, dinners), batch recipes up to
3 times, others up to 2; snacks up to 2 a day. Constraints: energy within
90–115 % of need (hard; never traded for cost), cost ≤ budget, WHO limits on
sodium, saturated fat and *free* sugars (honey, chocolate; not the sugars in
fruit and milk) as soft constraints with a heavy penalty. Objective: capped
coverage of each nutrient's weekly need, with goal nutrients weighted
1 + 3 × their association to the goal. If no plan fits the budget, a second
solve finds the cheapest adequate week and the app shows that minimum budget.
Portions scale with energy need (×0.8–1.4 of a 2,100 kcal reference).

**Prices.** Open Prices receipts in France (ODbL), last 30 months, per chain:
median €/kg; observations beyond 3× the ingredient's national median dropped
(mostly wrong pack weights); chains with n receipts shrunk towards national
median × chain index as (n·median + 5·estimate)/(n + 5); chains with none use
the estimate and are flagged. The chain index is the median ratio of a chain's
price to the national median over the ingredients it has.

**What it cannot do yet.** Recipes are drafts (not reviewed by a dietitian or
kitchen-tested); vitamin D is rarely met by food; vegan weeks are low in B12 and
iodine, and the app says to use a B12 supplement or fortified foods and iodised
salt, which is standard public-health guidance.

## Data integrity note

## Data integrity note

The OpenFoodFacts demonstration corpus (1,809 items) originally looked
unreliable: maximum iron ~1.3 and maximum vitamin C ~0.1 "mg" per 100 g.
The cause was a unit error in the crawler, not in OFF: every OFF
`<nutrient>_100g` field is normalised to **grams** (and says so per value,
`iron_unit: "g"`), and the crawler stored those gram values as if they were
mg/µg. Since v1.3 the values are converted through the shared unit
normaliser (`ontology/units.py`). Two independent checks confirm the fix:
EU labelling defines salt = sodium × 2.5, and after conversion the median
salt/sodium ratio across 1,543 products is exactly 2.50 (95% within
2.4–2.6); and almonds now read 3.3 mg iron, 260 mg magnesium, 25 mg
vitamin E, in line with USDA. Values that remain impossible after conversion
(e.g. a kJ figure typed into the kcal field) and values outside 10× the USDA
range for the food's category are still rejected and kept, with the reason,
as `trusted=false` rows.

The curated whole-foods reference corpus (`data/ingest/whole_foods.py`, 88
staples) and the USDA bulk corpus (~8,000 foods) remain the analytical
backbone; `build_engine(whole_foods_only=True)` uses the curated set alone.

## Ontology and provenance (v1.3)

Every importer resolves its labels and codes through one vocabulary,
`ontology/nutrients.json`: engine id, FAO/INFOODS tagname for exactly what is
stored (e.g. `TOCPHA` for alpha-tocopherol, `VITA_RAE`), canonical unit,
names in English/Italian/French, synonyms, and source codes (USDA nutrient
ids, OFF keys). Matching is exact after normalisation, never fuzzy:
"Rétinol" deliberately does not resolve to vitamin A, because retinol is one
input to RAE, not RAE.

European tables publish cells such as "< 0,5" and "traces". These are stored
with a qualifier (`exact | less_than | trace | missing`) and the bound;
only exact values reach the graph, so a food is never recommended on the
strength of a value below detection.

In the database every food points at a `sources` row (dataset, version,
licence), and a converted value keeps the number and unit it was published
in. Tables `food_names` (multilingual) and `food_concepts` (one real food
described by several sources) are in place for the EU importers.

---

## Expansion (v1.2): deeper interactions, broader corpus

**Interaction matrix — 34 documented interactions** (from 17), now covering
additional targets (copper, manganese, folate) and additional modifiers
(fibre, caffeine, fructose, organic acids, mineral-mineral competition).
Notable additions: the zinc→copper metallothionein competition (clinically
important at high zinc intakes), vitamin A / carotenoid enhancement of non-heme
iron, sodium and caffeine effects on calcium retention, and magnesium's role in
vitamin D activation. Mineral-mineral competitions that are only material at
supplemental doses are flagged as such in each entry and given mild factors.

**Whole-foods corpus — 88 staples** (from 45), now carrying trace minerals
(copper, selenium, potassium) and B-vitamins (folate, B12) so the expanded
interactions have real data to act on. Brazil nuts (selenium), oysters (zinc),
shellfish and organ meats (B12), and legumes/seeds (copper, folate) give the
matrix meaningful coverage.

**Reference intakes — 18 nutrients** (from 13), adding copper, selenium,
potassium, folate and B12 DRIs across all demographic groups.

**Citation integrity:** a regression test (`test_no_malformed_citations`)
asserts every interaction citation is a well-formed PMID. Citations remain
representative anchors that must be verified before clinical use — this is
stated in the data file and enforced structurally.

**Scaling path:** the USDA connector (`data/ingest/usda.py`) is now a complete
CLI that fetches Foundation/SR Legacy foods, maps 25 nutrients, and merges
de-duplicated records into the whole-foods corpus — the route from 88 curated
staples to thousands of research-grade entries once run with a free API key.
