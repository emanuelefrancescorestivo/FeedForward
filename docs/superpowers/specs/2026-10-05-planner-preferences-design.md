# Planner preferences, grounded in the graph (project A)

*Design spec, 2026-10-05. Branch `dashboard-ui`. Projects B (guided onboarding)
and C (Google sign-in) build on this one and get their own specs.*

## Why

Today the planner knows a person's needs, one goal, a shop and a budget, and
writes a full week from that. People also have an energy goal (deficit or
surplus), a daily rhythm (sleep, training, morning appetite, study) and tastes
and kitchen limits. A plan that ignores them feels imposed: meals they do not
like or cannot cook.

Project A teaches the engine those preferences. The person answers questions
about themselves; the engine turns the answers into **goals in the knowledge
graph** and **strategies**, each strategy an edge in the graph with an evidence
grade and its sources; the planner applies them. Every change to the plan can be
explained as a path in the graph.

## Success criteria

1. Each preference changes the plan in a way the plan reports ("dinner carbs
   44 %, met 6 of 7 days").
2. Needs come first: no preference takes a nutrient that the plan without
   preferences covers below 97 % of the need (the solver works to a 1 % gap),
   tested for each strategy.
3. Only strategies with evidence graded A to C are proposed; each has at least
   one PubMed ID.
4. The input-space sweep, extended with random answers, has 0 broken cases:
   every case returns a plan or an explanation with what to relax.
5. Existing clients keep working: a request without the new fields gives the
   same plan as today.

## Non-goals

- The questionnaire screens and the guided first week (project B).
- Accounts, Google sign-in, server-side storage (project C). In A, answers stay
  in the browser and travel with each request, as today.
- Medical conditions and allergies (EU MDR, decision 8). Exclusions are "foods I
  don't eat", with a note to check labels for allergies.
- More recipes. The pool (46 meals, 6 snacks) is a known limit; A makes the
  engine say when filters leave too few.

## Model

### Answers turn on goals in the graph

The graph has 27 goals; each nutrient has an association `a_g(n)` in [0, 1]
with each goal (EU claims and literature, graded A to D). Today the planner
weights nutrient `n` as `1 + GOAL_BONUS * a_goal(n)` for the one chosen goal.

With preferences, the person has a primary goal (weight 1) and goals turned on
by their answers (weight 0.5 each; the primary keeps 1 if an answer points at it
too). A nutrient's association is its **strongest** link to any of those goals:

    a(n) = max_g ( alpha_g * a_g(n) )        weight(n) = 1 + GOAL_BONUS * a(n)

The maximum, not the sum, keeps `a(n)` in [0, 1] (the scale the objective was
tuned on) and never counts one nutrient twice; the explanation names the goal
that gave the weight.

| Answer | Goal turned on (alpha 0.5) |
|---|---|
| takes a long time to fall asleep: sometimes or often | `sleep_support` |
| trains 3 or more days a week | `muscle_recovery` |
| energy dips (mid-morning or afternoon) | `energy_metabolism` |
| studies or does focused work (any time of day) | `cognitive_function` |

### Strategies are edges in the graph

A strategy links an answer to a goal through one planner lever:

    answer --triggers--> strategy --supports (grade, PMIDs)--> goal

| Strategy | Triggered by | Lever | Goal | Grade | Sources (PMID) |
|---|---|---|---|---|---|
| `evening_carbs` | slow to fall asleep | dinner carbs >= 40 % of the day's | `sleep_support` | C | 17284739 (Afaghi 2007), 27633109 (St-Onge 2016) |
| `no_evening_caffeine` | slow to fall asleep | no caffeine at dinner (hard) | `sleep_support` | B | 24235903 (Drake 2013) |
| `protein_target` | deficit, surplus, or trains >= 3 days | protein need 1.6 g/kg/day | `muscle_recovery` | B | 28698222 (Morton 2018), 24864135 (Helms 2014) |
| `protein_spread` | trains >= 3 days | each main meal >= 0.3 g/kg protein | `muscle_recovery` | C | 23459753 (Areta 2013), 29497353 (Schoenfeld 2018) |
| `post_training_carbs` | trains, and when | the meal after training >= 40 % of the day's carbs | `recovery` | C | 28919842 (Kerksick 2017) |
| `protein_breakfast` | energy dip mid-morning | breakfast >= 0.25 g/kg protein | `energy` | C | 23446906 (Leidy 2013) |
| `big_breakfast` | hungry in the morning | breakfast >= 30 % of the day's energy | `energy` | C | 36087576 (Ruddick-Collins 2022) |

Grades follow the project's scale (decision 7): A = EU authorised claim, B =
systematic review or meta-analysis of trials, C = smaller trials or a position
stand. The wording shown to people states the limits, for example: "Small
studies found people fell asleep faster after a carbohydrate-rich dinner about
four hours before bed."

Not proposed: a low-glycaemic lunch for study afternoons (evidence weak; no GI
values per recipe). Studying turns on `cognitive_function`, whose links are
graded A.

### Preferences are not strategies

Some answers are about comfort or taste, not science. They need no evidence and
are not edges in the graph; they are applied as asked:

- `light_breakfast` (not hungry in the morning): breakfast <= 20 % of the day's
  energy, soft;
- foods not eaten, maximum cooking time, batch cooking, kitchen equipment, meals
  marked "Not for me": hard filters.

## Levers in the planner

The week MILP chooses how many times each recipe appears per meal in the week
(`x[recipe, meal]`, integers); `_schedule` then places them on days. Levers on
"the day's" carbs or energy are therefore written on the **week's totals** in the
MILP, and measured per day after scheduling, which is what the plan reports.

Priority order, as weights in the objective: energy band and budget (hard) >
nutrient coverage > preferences and strategies > variety > cost.

### Energy goal

| `energy_goal` | target |
|---|---|
| `maintain` (default) | Mifflin-St Jeor x PAL, as today |
| `deficit` | 0.85 x that |
| `surplus` | 1.10 x that |

The band stays 90-115 % of the target. The target never goes below the resting
energy (Mifflin-St Jeor without the activity factor). `deficit` and `surplus`
are refused under 18 and in pregnancy or breastfeeding; `deficit` is refused
with a BMI under 18.5. Refusal: HTTP 400 with the reason; `/plan/strategies`
lists the option as unavailable with the same reason so the interface can hide it.

### Soft levers (penalised slack)

With `S_m(n) = sum_r n_r * x[r, m]` the week's intake of `n` from meal `m`:

- share of carbs at meal m >= p: `S_m(carbs) >= p * intake(carbs) - slack`;
- share of energy at breakfast >= p or <= p: same form on `energy-kcal`;
- protein per serving >= t: constant per recipe, penalty `max(0, t - protein_r) * x[r, m]`;
- `protein_target`: raises the weekly protein need to 1.6 g/kg/day; coverage is
  already capped at 100 % in the objective, so it is soft by construction.

Each slack is normalised (by the week's carbs, energy or the threshold) and
weighted below nutrient coverage: `PREFERENCE_WEIGHT = 0.3` (to tune on the
sweep), against coverage terms that sum to 1.

### Hard filters

- `exclude` categories: recipes with any ingredient tagged with them leave the
  pool. Categories: `fish_seafood`, `meat`, `pork`, `mushrooms`, `legumes`,
  `dairy`, `eggs`, `nuts`, `spicy`. Each ingredient in `ingredients.json` gets
  `tags`.
- `no_evening_caffeine`: dinner variables for recipes with a `caffeine`-tagged
  ingredient (coffee, tea, cocoa) are not created.
- `max_minutes` (10, 20, 30 or none): recipes with `time_min` above it leave the
  pool; with `batch_ok`, batch recipes (cooked once for three portions) are
  allowed up to 3 x the limit.
- `avoid_recipes`: recipe ids marked "Not for me".

### When filters leave too few recipes

After filtering, the engine counts recipes per meal. With 0 for a meal the week
is infeasible: `reason: "recipes"` and a `relax` list, one entry per filter that
would help, with the count it would give back (for example `{"filter":
"max_minutes", "now": 10, "try": 20, "dinners": 7}`). With fewer than 3 the plan
is made, with repeats, and the same `relax` list comes as a note.

## Data

`backend/feedforward/data/strategies.json`:

```json
{
  "questions": [
    {"id": "sleep_onset", "text": "Do you take a long time to fall asleep?",
     "options": ["no", "sometimes", "often"]},
    {"id": "training_days", "text": "How many days a week do you train?",
     "options": ["0", "1-2", "3-4", "5+"]},
    {"id": "training_time", "text": "When do you usually train?",
     "options": ["before_breakfast", "morning", "afternoon", "evening"]}
  ],
  "goals": [
    {"when": {"sleep_onset": ["sometimes", "often"]}, "goal": "sleep_support", "alpha": 0.5}
  ],
  "strategies": [
    {"id": "evening_carbs", "kind": "strategy",
     "when": {"sleep_onset": ["sometimes", "often"]},
     "lever": {"type": "meal_carb_share", "meal": "dinner", "min": 0.40},
     "goal": "sleep_support", "grade": "C", "pmids": ["17284739", "27633109"],
     "text": "More of the day's carbohydrates at dinner",
     "why": "Small studies found people fell asleep faster after a carbohydrate-rich dinner about four hours before bed."}
  ]
}
```

Full question set: `energy_goal` (maintain / deficit / surplus), `sleep_onset`,
`training_days`, `training_time`, `morning_hunger` (hungry / normal / not
hungry), `energy_dips` (none / mid_morning / afternoon), `study_time` (rarely /
mornings / afternoons / evenings), `dont_eat` (categories, several), `cook_time`
(10 / 20 / 30 / any), `batch_ok` (yes / no), `kitchen` (full / microwave).
`post_training_carbs` picks its meal from `training_time`: before breakfast ->
breakfast, morning -> lunch, afternoon or evening -> dinner.

## Engine

New module `engine/profile.py`:

- `load_strategies()` reads and validates `strategies.json` (known question ids
  and options, known lever types, goals that exist in the graph, grade A to C
  for `kind: strategy`, at least one PMID).
- `propose(answers, profile) -> Proposal`: goals with alpha, strategies and
  preferences that apply (with text, why, grade, sources, goal), options not
  available with the reason. Unknown question ids or options raise `ValueError`
  (decision 16).
- `resolve(answers, declined, profile) -> Levers`: what the planner applies:
  goal weights, energy factor, protein target, soft levers, hard filters.

`plan_week(rec, profile, *, goal, budget, chain, ..., answers=None,
declined=None, avoid_recipes=None)`. With `answers=None` the planner behaves as
today. `evaluate_week` and `swap_options` take the same arguments; swaps keep
the hard filters and report their effect on the strategies.

## API

- `GET /plan/questions`: the questionnaire (ids, text, options).
- `POST /plan/strategies`: profile + answers -> the proposal (for the interface
  to show and let people accept or decline).
- `POST /plan/week`, `/plan/evaluate`, `/plan/swap-options`: `WeekRequest`
  gains `answers: dict[str, str | list[str]] | None`, `declined: list[str] |
  None` (strategy ids turned down), `avoid_recipes: list[str] | None`. The
  client never sends weights: the server derives them from the answers, so the
  explanation always matches what the planner did.

Response additions:

```json
"energy": {"goal": "deficit", "target_per_day": 2007, "resting": 1739},
"protein_target_g": 115,
"goals": [{"id": "cognitive_function", "alpha": 1.0}, {"id": "sleep_support", "alpha": 0.5}],
"strategies": [{"id": "evening_carbs", "grade": "C", "goal": "sleep_support",
                "pmids": ["17284739", "27633109"], "met_days": 6, "value": "dinner carbs 44 %"}],
"relax": []
```

`targets.protein` (the day dashboard's protein bar) follows `protein_target_g`
when `protein_target` applies.

## Errors

- unknown question, option, strategy id, category or recipe id: 400 (422 for
  shapes the model rejects);
- an energy goal not allowed for the profile: 400 with the reason;
- too few recipes: `feasible: false`, `reason: "recipes"`, `relax`;
- a soft lever not met: never an error; reported per strategy (`met_days`).

## Testing

- `strategies.json` integrity (as in `load_strategies`), as a test.
- Energy: `deficit` = 0.85 x maintenance per day, never below resting energy;
  refused for a 16-year-old, in pregnancy, at BMI 17.
- Goal weights: `max` combination, primary keeps alpha 1, explanation names the
  goal that set each weight.
- One test per lever on the README profile: dinner carb share >= 40 % on most
  days with `evening_carbs`; breakfast share with `big_breakfast` and
  `light_breakfast`; per-meal protein; no caffeinated ingredient at dinner;
  no excluded category anywhere in the plan; `max_minutes` respected;
  `avoid_recipes` never planned.
- Needs first: for the README profile, each strategy alone leaves every
  nutrient that the plain plan covered at >= 97 % of its need.
- `relax`: vegan + 10 minutes + no legumes returns the filter to relax and the
  count it gives back.
- Sweep: `test_planner_handles_the_input_space` gains random answers, declined
  strategies and exclusions (fixed seed); 0 broken cases; median solve time
  reported.
- API round trip for `/plan/questions`, `/plan/strategies` and the new
  `WeekRequest` fields; a request without them returns today's plan.

## Risks

- **Recipe pool.** 46 meals; heavy filters give repeats or no plan. Mitigated by
  `relax`; fixed only by more recipes (with the pending dietitian review).
- **Weekly levers, daily reading.** Shares are enforced on the week and
  reported per day; a day can miss. The report says so (`met_days`).
- **Deficit and disordered eating.** Mitigated by the limits above, a modest
  15 %, needs first, and the interface rules from decision 19 (no countdown, no
  red). Recorded as decision 21 in `DECISIONS.md`, which revisits the "no
  weight goal" part of decision 19.
- **Solve time.** More constraints; checked on the sweep against the current
  0.1-0.7 s median.
