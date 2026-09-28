# FeedForward

[![tests](https://github.com/emanuelefrancescorestivo/FeedForward/actions/workflows/tests.yml/badge.svg)](https://github.com/emanuelefrancescorestivo/FeedForward/actions/workflows/tests.yml)

**An explainable nutritional knowledge graph.** Most nutrition apps tell you
*what* you ate. FeedForward tells you *why* a food helps — tracing an explicit,
evidence-graded chain from **food → nutrient → health goal**, adjusted for how
much of each nutrient your body can actually absorb.

> A calorie counter says "spinach contains 2.7 mg of iron." That number is
> almost meaningless on its own: plant (non-heme) iron is absorbed at 2–20%, and
> that rate can *triple* in the presence of vitamin C. FeedForward reasons about
> exactly this — the interactions, the bioavailability, and the strength of the
> underlying science.

---

## Why this is different

Three ideas this project combines:

1. **Explicit reasoning chains.** Recommendations are paths through a graph, not
   opaque scores. Every suggestion comes with its route: *this food → this
   nutrient → your goal*, and you can see it.

2. **Bioavailability modelling.** Edge weights reflect *absorbable* nutrient
   delivery, not just raw content. Heme vs non-heme iron, fat-soluble vitamins
   needing dietary fat, vitamin C boosting iron uptake, calcium competing with
   it — all encoded as an auditable rule base ([`engine/bioavailability.py`](backend/feedforward/engine/bioavailability.py)).

3. **Evidence grading.** Each nutrient→goal link carries a grade (A–D) derived
   from the literature — optionally live from PubMed — so a Grade A meta-analytic
   association outranks a Grade C observational one ([`engine/evidence.py`](backend/feedforward/engine/evidence.py)).

On top of the engine sits a **web app** (`/app`): a budgeted weekly meal
plan for a chosen supermarket in France, plus food search, a meal builder and a
sourced dictionary. The API can show a professional view (evidence grades,
citations, ICD-10 codes on goals) to accounts with that tier; there is no
payment system or partner API.

---

## Architecture

```
User surfaces      Web app (/app) · Expo mobile prototype
        │
Backend            FastAPI · SQLAlchemy + Alembic (PostgreSQL; SQLite in tests) · JWT
        │
Scientific Engine  Graph (Dijkstra · Yen) · MILP (PuLP/CBC) · Bioavailability · Evidence
        │
Data               CIQUAL · USDA FoodData · Open Food Facts · Open Prices ·
                   EU health-claims register · PubMed · curated ontology
```

The engine is the crown jewel; the backend and app are scaffolding around it.

### The graph
A tripartite weighted graph: **Food → Nutrient → Goal**. Every edge has a
strength in (0, 1] and a cost of `-log(strength)`, so a path's strength is the
product of its edges and Dijkstra's *shortest* path is exactly the *strongest*
food → nutrient → goal chain; Yen's k-shortest-paths gives the next-strongest
routes. The graph is hand-written (no NetworkX backing store); NetworkX is used
only for offline analytics.

### Scoring (v1.3) — [`engine/scoring.py`](backend/feedforward/engine/scoring.py)
- **Food → Nutrient** = what **one realistic portion** delivers as a share of
  daily need (DRI), adjusted for chemical form (heme vs non-heme iron) and strong
  intrinsic inhibitors (oxalate on calcium), saturating so the tenth day's worth
  adds almost nothing. Portions are data ([`data/portions.json`](backend/feedforward/data/portions.json)):
  2 g of baking powder, 30 g of nuts, 150 g of cooked lentils. A portion over a
  Tolerable Upper Intake Level is discounted.
- **Nutrient → Goal** = association weight × evidence grade.
- **Food → Goal** = strongest route in full plus every other route at half
  weight (noisy-OR), times penalties for sodium / saturated fat / sugars per
  portion (stronger where the goal has a negative edge, e.g. sodium → blood
  pressure) and for exceeding a UL.
- **Enhancers are not routes.** Vitamin C helps iron *absorption*; it is applied
  in meals and suggested as a pairing, so a vitamin C drink no longer ranks as an
  iron source.

Results are diversified (one entry per food family, a cap per food group), and
default recommendations exclude infant foods, supplements (fish oils), products
not sold in the EU (marine mammals) and foods unsafe as listed (raw pokeweed,
raw taro leaves). `python -m feedforward.engine.benchmark -v` scores the
rankings against a sanity benchmark ([`data/benchmark_goals.json`](backend/feedforward/data/benchmark_goals.json)):
v1.2 → v1.3 mean top-20 hit rate 0.31 → 0.68, implausible results 34 → 3.

### Knowledge layer (v1.4) — EU health claims
Nutrient → goal edges come from the **EU Register of authorised health claims**
([`data/ingest/eu_claims.py`](backend/feedforward/data/ingest/eu_claims.py)):
118 authorised edges (grade A, official wording, EFSA opinion cited) and 62
associations EFSA found unsubstantiated, which no longer count (e.g. vitamin E →
heart health). B vitamins, choline, iodine and EPA+DHA were added to the corpus
so that energy, mood and cognition claims reach foods. See
[`docs/SCIENTIFIC_BASIS.md`](docs/SCIENTIFIC_BASIS.md#eu-health-claims-v14--the-knowledge-layer).
Sanity benchmark on the EU-grounded engine: 0.73 (v2 lists, everyday foods first), 0 implausible results.

### Dictionary and explorer UI
`http://localhost:8000/app` is a progressive-disclosure explorer: 8 main goals,
5 everyday foods at a time, "Why?" with the food → nutrient → goal graph, a
shopping list (stored in the browser) and a light/dark theme. The **dictionary**
(`/dictionary/*`, [`feedforward/dictionary/`](backend/feedforward/dictionary/))
builds every entry from a named source: nutrients from the EU claim wording,
EFSA rejections, DRIs and computed everyday sources; foods from our data plus
an attributed Wikipedia summary (cached in `data/wikipedia_cache.json`); terms
from `data/glossary.json` (draft, awaiting dietitian review).

### My week — a budgeted plan for Paris / France (prototype)
The default tab of `/app`. You give age, sex, height, weight, activity, one goal,
a shop, a weekly budget and a diet; you get 7 days of breakfast, lunch and
dinner (+ snacks), and a shopping list priced at that shop. Your answers stay
in the browser (localStorage) and are sent only to compute the plan.

- **Food composition:** ANSES-CIQUAL 2020 (3,185 French foods, Licence Ouverte),
  [`data/ingest/ciqual.py`](backend/feedforward/data/ingest/ciqual.py); energy
  computed with EU 1169/2011 factors where CIQUAL has none.
- **Prices:** Open Prices receipts (ODbL), median €/kg per chain over 30 months,
  outliers beyond 3× the national median dropped, chains with few receipts
  pulled towards national median × chain price index; missing chains estimated
  (shown with ≈). [`data/ingest/prices.py`](backend/feedforward/data/ingest/prices.py).
  Price index, from the data: Netto 0.57, Lidl 0.67, Aldi 0.70, Leclerc 0.93,
  Carrefour 1.06, Monoprix 1.17, Franprix 1.27, Naturalia 1.40, Biocoop 1.49.
- **Needs:** Mifflin–St Jeor × activity level; protein max(DRI, 0.83 g/kg);
  vitamins and minerals by age/sex only ([`engine/needs.py`](backend/feedforward/engine/needs.py)).
  No medical conditions are asked, on purpose.
- **Recipes:** 46 draft recipes + 6 snacks built from 57 ingredients
  ([`data/recipes.json`](backend/feedforward/data/recipes.json), status *draft*,
  to be reviewed by a dietitian), incl. vegan breakfasts and microwave-only meals.
- **Planner:** one MILP ([`engine/week_planner.py`](backend/feedforward/engine/week_planner.py)):
  energy is a hard band (90–115 % of need) and is never traded for budget; if a
  week does not fit, the answer is the minimum budget, not less food. Within the
  budget it maximises coverage of the week's needs (goal nutrients weighted up),
  under WHO limits for sodium, saturated fat and free sugars; fridge/bakery
  items are bought in whole packs, cupboard/freezer items counted by share used.
- API: `GET /plan/options`, `POST /plan/week`, `GET /plan/recipes/{id}`.

Example (man, 24, 178 cm, 72 kg, light activity, goal "focus"): Lidl €50 →
€39.65, 2,361 kcal/day, all needs ≥ 100 % except vitamin D (81 %); Naturalia
€50 → €50.01, fewer fish meals, so iodine and EPA+DHA fall to ~20 %.

### The latency fix
The original prototype ran Dijkstra from all ~1,800 food nodes per query (587 ms).
We reverse the graph and run Dijkstra *once from each goal*, and score every
food for every goal, once at startup. A recommendation query is then a walk
down a pre-sorted list:

```
587 ms  →  ~0.7 ms   (per cached query)
```

---

## Repository layout

```
feedforward/
├── backend/
│   ├── feedforward/
│   │   ├── engine/          # THE SCIENTIFIC ENGINE
│   │   │   ├── schema.py            # dataclasses, EvidenceGrade, NutrientForm
│   │   │   ├── graph.py             # tripartite graph + reverse index
│   │   │   ├── algorithms.py        # Dijkstra, reverse-Dijkstra, Yen, cosine
│   │   │   ├── bioavailability.py   # absorption model (the differentiator)
│   │   │   ├── evidence.py          # A–D grading, PubMed integration
│   │   │   ├── taxonomy.py          # 27 health goals, 9 body systems
│   │   │   ├── build.py             # weighting: content×absorption, assoc×evidence
│   │   │   ├── recommender.py       # orchestration + explanations
│   │   │   ├── meal_optimizer.py    # ILP meal selection (PuLP/CBC)
│   │   │   ├── needs.py             # personal energy and nutrient needs
│   │   │   └── week_planner.py      # weekly plan within a budget (MILP)
│   │   ├── ontology/        # nutrient vocabulary (INFOODS, IT/EN/FR), units, qualifiers
│   │   ├── db/              # SQLAlchemy models, seed, repository (Alembic in backend/alembic)
│   │   ├── api/             # FastAPI: routers, auth (JWT), models
│   │   ├── web/             # the web app (one HTML file, no build step)
│   │   └── data/            # corpora, edges, recipes, prices, sources.json; ingest/ rebuilds them
│   └── tests/               # pytest suite (engine + algorithms + API)
├── mobile/                  # React Native (Expo) prototype; predates the web app
│   └── src/{screens,components,api,theme}
└── docs/                    # architecture, scientific basis; APP_STORE.md is a future checklist
```

---

## Quickstart

### Backend

```bash
cd backend
pip install -r requirements.txt

# Run the API
uvicorn feedforward.api.main:app --reload
# → interactive docs at http://localhost:8000/docs
# → exploration UI at   http://localhost:8000/app

# Run the tests
pytest -q
```

Try the engine directly:

```python
from feedforward.engine import build_engine
rec = build_engine()

for r in rec.foods_for_goal("iron_support", constraints=["vegetarian"], k=3):
    e, top = r.explanation, r.explanation.contributions[0]
    print(f"{r.match:5.1f}  {r.food_name}")
    print(f"       {top['percent_of_need']:.0f}% of daily iron in {e.portion_g:.0f} g  (evidence {e.evidence})")
```

```
 86.2  Cereals, QUAKER, Quick Oats with Iron, Dry
       110% of daily iron in 40 g  (evidence A)
 83.9  Cereals, MALT-O-MEAL, Farina Hot Wheat Cereal, dry
       91% of daily iron in 40 g  (evidence A)
 72.2  Mushrooms, morel, raw
       54% of daily iron in 80 g  (evidence A)
```

Each explanation also lists every route's contribution, the penalties applied
and, for plant iron, a pairing note ("pair with a vitamin C source"): vitamin C
raises non-heme iron absorption, but it is not itself an iron source, so it is a
pairing rather than a route.

### Mobile

```bash
cd mobile
npm install
npx expo start          # then press i (iOS) or a (Android)
```

---

## Status & honest limitations

This is a personal project and a working prototype, not a product in use.
Nothing here has been reviewed by a dietitian or tested with users yet.
What exists today:

- ✅ Engine: graph, bioavailability rules, evidence grading, 27-goal taxonomy, portion-based scoring, meal MILP, weekly budget planner — covered by 187 tests (pytest, run on every push by GitHub Actions).
- ✅ FastAPI backend: recommend / explain / meal-plan / week plan / food detail / dictionary / auth with tiered access.
- ✅ Web app (`/app`): My week, food search, meal builder, dictionary, shopping list; works on phones.
- 🟡 Expo mobile prototype (`mobile/`): early screens against the recommend API; it does not have My week.

Known limitations, stated plainly:

- The bioavailability rules cover the best-established interactions (iron, calcium, fat-soluble vitamins). They are a curated subset of the literature, not exhaustive.
- Evidence grades come from the EU register (authorised claims = A) and a curated table with representative PMIDs; the live PubMed grader is implemented but off by default for reproducibility. `stress_resilience` has no nutrient with established evidence, and sleep rests on one grade-C association.
- The food corpus is ANSES-CIQUAL 2020 (3,185 foods), USDA FoodData Central (~8,000 foods, Foundation + SR Legacy), 88 curated staples and 1,809 OpenFoodFacts products whose micronutrients pass a USDA range gate. Fineli and CREA are not imported yet.
- Week planner: recipes are drafts; prices are medians of crowdsourced receipts (few receipts for some chain × ingredient pairs, marked ≈ when estimated); pack sizes are medians; vitamin D is rarely covered by food alone; vegan weeks are low in B12 and iodine by nature (the app says so).
- Not deployed anywhere; it runs locally. Nothing has been submitted to an app store.

See [`docs/SCIENTIFIC_BASIS.md`](docs/SCIENTIFIC_BASIS.md) for the evidence
approach.

---

## Provenance

FeedForward started as the final project of TAOCP2 (PSL University, Bachelor
in AI, June 2026) by **Emanuele Restivo and Marcos Almodovar**: Open Food Facts
and Wikipedia scrapers, the Food → Nutrient → Goal graph, graph-based
recommendations and an ILP vs greedy meal comparison. Since then it has been
rebuilt and extended by Emanuele Restivo: new scientific engine (bioavailability,
evidence grading, EU claims), the French data and price pipeline, the weekly
planner, an API, a web app and a mobile prototype. Built with AI coding
assistants (Claude Code) as tools; design decisions and their trade-offs are
documented in `docs/`.

## License

Code: MIT, see [`LICENSE`](LICENSE). The data files carry their own licences
(ODbL share-alike for anything derived from Open Food Facts / Open Prices):
see [`DATA_LICENSES.md`](DATA_LICENSES.md).
