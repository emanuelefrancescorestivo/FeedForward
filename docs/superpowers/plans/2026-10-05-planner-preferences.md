# Planner Preferences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The week planner takes a person's answers (energy goal, sleep, training, mornings, study, foods not eaten, cooking time), turns them into weighted goals in the knowledge graph and evidence-graded strategies, and applies them as hard filters and soft MILP levers, needs first.

**Architecture:** A data file (`strategies.json`) holds the questions, the answer → goal links and the strategies (lever, goal, grade, PMIDs, copy). A new engine module (`engine/profile.py`) validates answers and resolves them into a `Levers` object. `week_planner._context` applies the levers (energy factor, protein, goal weights, filters); `plan_week` adds the soft levers to the MILP; `_assemble` reports each strategy per day. The API exposes the questions and proposals and accepts answers on every plan endpoint.

**Tech Stack:** Python 3.12, PuLP/CBC through `engine/milp.py`, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-planner-preferences-design.md`

## Global Constraints

- Energy factors: `maintain` 1.0, `deficit` 0.85, `surplus` 1.10; the daily target never goes below resting energy (Mifflin-St Jeor without PAL).
- `deficit` and `surplus` refused under 18 and in pregnancy or breastfeeding; `deficit` refused at BMI < 18.5.
- Answer-goal alpha 0.5, primary goal 1.0; nutrient association = max over goals of `alpha_g * a_g(n)`.
- Proposed strategies: grade A to C only, at least one PMID each; preferences (`kind: "preference"`) need neither.
- Priority in the objective: energy band and budget (hard) > coverage > levers (`PREFERENCE_WEIGHT = 0.3`, lower it if the needs-first test fails) > variety > cost.
- No preference takes a nutrient the plain plan covers below 97 % of the need.
- Unknown question, option, strategy id, category or recipe id raises `ValueError` (HTTP 400). Partial answers are fine: unanswered questions trigger nothing.
- A request without `answers`, `declined` and `avoid_recipes` returns exactly today's plan.
- `MIN_OPTIONS = 3` recipes per meal before `relax` suggestions appear; 0 for a meal means `feasible: false`, `reason: "recipes"`.
- Kitchen equipment stays the existing `equipment` field; the questionnaire does not ask it again (deviation from the spec's question list, to avoid two sources of truth).
- No medical conditions; exclusions are "foods I don't eat" (no allergy wording).
- Run tests with `python -m pytest backend/tests/<file> -q` from the repo root. Commit with `git commit -F <message file>` (PowerShell 5.1 splits quoted `-m` messages); end messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push without asking.

## Review Focus

1. **Partial answers** (an older client sends only `sleep_onset`): strategies for that answer only, no error. Test in Task 2.
2. **Conflicting answers** (`morning_hunger: not_hungry` + `energy_dips: mid_morning` + `training_days: 5+` + `sleep_onset: often` + deficit): soft levers clash, the week must still be feasible. Test in Task 4.
3. **At-home ingredient in an excluded category** (pantry has `sardines`, `dont_eat` has `fish_seafood`): never planned. Test in Task 3.
4. **Edited week that breaks new preferences** (a swapped-in recipe later marked "Not for me"): `evaluate_week` raises `ValueError` naming the recipe, so the app can drop the edits. Test in Task 6.
5. **Declined ids**: an unknown id is an error; a known strategy that the answers do not trigger is ignored. Test in Task 2.

---

### Task 1: Tags and the strategies file

**Files:**
- Modify: `backend/feedforward/data/ingredients.json` (add `"tags"` lists)
- Modify: `backend/feedforward/data/recipes.json` (add `"tags": ["spicy"]` to 3 recipes)
- Create: `backend/feedforward/data/strategies.json`
- Create: `backend/feedforward/engine/profile.py`
- Create: `backend/tests/test_profile.py`

**Interfaces:**
- Produces: `CATEGORIES: tuple[str, ...]`; `load_strategies() -> dict` (cached, validated); `validate_strategies(data: dict, known_goals: set[str]) -> None` (raises `ValueError`); `questions() -> list[dict]`.

Ingredient tags (every other ingredient gets `"tags": []`):

| tag | ingredients |
|---|---|
| `fish_seafood` | mackerel, salmon, sardines, tuna |
| `meat` | chicken, minced-beef, ham |
| `pork` | ham |
| `mushrooms` | mushroom |
| `legumes` | chickpeas, green-lentils, red-lentils, kidney-beans |
| `dairy` | butter, emmental, fromage-blanc, milk, yogurt |
| `eggs` | egg |
| `nuts` | walnuts, peanut-butter |
| `caffeine` | dark-chocolate |

Recipe tag `spicy`: `bean-chili-rice`, `beef-bean-chili`, `chickpea-spinach-curry`.
`CATEGORIES = ("fish_seafood", "meat", "pork", "mushrooms", "legumes", "dairy", "eggs", "nuts", "spicy")`.

`strategies.json` content (copy is fixed here):

Questions (`multi` only on `dont_eat`):

| id | text | options |
|---|---|---|
| `energy_goal` | Energy: keep it level, a light deficit or a light surplus? | maintain, deficit, surplus |
| `sleep_onset` | Do you take a long time to fall asleep? | no, sometimes, often |
| `training_days` | How many days a week do you train? | 0, 1-2, 3-4, 5+ |
| `training_time` | When do you usually train? | before_breakfast, morning, afternoon, evening |
| `morning_hunger` | Are you hungry in the morning? | hungry, normal, not_hungry |
| `energy_dips` | When does your energy dip? | none, mid_morning, afternoon |
| `study_time` | When do you study or do focused work? | rarely, mornings, afternoons, evenings |
| `dont_eat` | Foods you don't eat | the 9 `CATEGORIES` |
| `cook_time` | How long can you spend cooking a meal? | 10, 20, 30, any |
| `batch_ok` | Cook once for three days? | yes, no |

`when` is a list of condition objects: OR between objects, AND inside one; a value `"*"` means "answered".

Goals: `sleep_onset ∈ {sometimes, often}` → `sleep_support`; `training_days ∈ {3-4, 5+}` → `muscle_recovery`; `energy_dips ∈ {mid_morning, afternoon}` → `energy_metabolism`; `study_time ∈ {mornings, afternoons, evenings}` → `cognitive_function`; all with `alpha: 0.5`.

Strategies (`kind: "strategy"`):

| id | when | lever | goal | grade | pmids | text | why |
|---|---|---|---|---|---|---|---|
| `evening_carbs` | sleep_onset ∈ {sometimes, often} | `{"type": "meal_carb_share", "meal": "dinner", "min": 0.40}` | sleep_support | C | 17284739, 27633109 | More of the day's carbohydrates at dinner | Small studies found people fell asleep faster after a carbohydrate-rich dinner about four hours before bed. |
| `no_evening_caffeine` | same | `{"type": "no_caffeine", "meal": "dinner"}` | sleep_support | B | 24235903 | No caffeine at dinner | In a controlled trial, caffeine taken even six hours before bed shortened sleep. |
| `protein_target` | energy_goal ∈ {deficit, surplus} OR training_days ∈ {3-4, 5+} | `{"type": "protein_target", "g_per_kg": 1.6}` | muscle_recovery | B | 28698222, 24864135 | Protein at 1.6 g per kg of body weight | In a meta-analysis of training studies, gains in muscle levelled off around 1.6 g/kg a day; in a deficit, more protein helps keep muscle. |
| `protein_spread` | training_days ∈ {3-4, 5+} | `{"type": "protein_per_meal", "g_per_kg": 0.3}` | muscle_recovery | C | 23459753, 29497353 | Protein in every main meal | Spreading protein over the day's meals supported muscle repair better than one large serving in training studies. |
| `post_training_carbs` | training_days ∈ {1-2, 3-4, 5+} AND training_time = * | `{"type": "meal_carb_share", "meal_from": "training_time", "map": {"before_breakfast": "breakfast", "morning": "lunch", "afternoon": "dinner", "evening": "dinner"}, "min": 0.40}` | recovery | C | 28919842 | Carbohydrates in the meal after training | Carbohydrate after exercise refills muscle glycogen; it matters most when the next session is within a day. |
| `protein_breakfast` | energy_dips ∈ {mid_morning} | `{"type": "meal_protein", "meal": "breakfast", "g_per_kg": 0.25}` | energy | C | 23446906 | A breakfast with more protein | A higher-protein breakfast reduced hunger and snacking later in the day in a small trial. |
| `big_breakfast` | morning_hunger ∈ {hungry} | `{"type": "meal_energy_share", "meal": "breakfast", "min": 0.30}` | energy | C | 36087576 | A bigger breakfast | Eating more of the day's energy in the morning reduced hunger through the day; body weight changed the same either way. |

Preferences (`kind: "preference"`, no goal, grade or pmids): `light_breakfast` (morning_hunger ∈ {not_hungry}; `{"type": "meal_energy_share", "meal": "breakfast", "max": 0.20}`; "A lighter breakfast"; "You said you're not hungry in the morning."), `foods_not_eaten` (dont_eat = *; `{"type": "exclude_tags", "from": "dont_eat"}`; "Foods you don't eat"), `cook_time` (cook_time = *; `{"type": "max_minutes", "from": "cook_time"}`; "Meals that fit your cooking time"), `batch_cooking` (batch_ok ∈ {yes}; `{"type": "batch_ok"}`; "Cook once for three days").

Known lever types: `meal_carb_share`, `meal_energy_share`, `protein_target`, `protein_per_meal`, `meal_protein`, `no_caffeine`, `exclude_tags`, `max_minutes`, `batch_ok`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_profile.py`

```python
def test_strategies_file_is_valid(engine):
    data = profile.load_strategies()
    profile.validate_strategies(data, set(engine.scorer.positive))     # no exception
    for s in data["strategies"]:
        if s["kind"] == "strategy":
            assert s["grade"] in "ABC" and s["pmids"] and s["goal"] in engine.scorer.positive

def test_validation_rejects_bad_entries(engine):
    data = profile.load_strategies()
    goals = set(engine.scorer.positive)
    for broken in (_with(data, 0, grade="D"), _with(data, 0, pmids=[]), _with(data, 0, goal="telepathy"),
                   _with(data, 0, lever={"type": "levitate"}), _with(data, 0, when=[{"sleep_onset": ["never"]}])):
        with pytest.raises(ValueError):
            profile.validate_strategies(broken, goals)

def test_tags_cover_the_categories():
    ingredients, recipes, _ = wp._load()
    tagged = {t for i in ingredients.values() for t in i["tags"]} | {t for r in recipes for t in r.get("tags", [])}
    assert set(profile.CATEGORIES) | {"caffeine"} == tagged
    assert {r["id"] for r in recipes if "spicy" in r.get("tags", [])} == {"bean-chili-rice", "beef-bean-chili", "chickpea-spinach-curry"}
```

(`_with(data, i, **changes)` returns a deep copy with strategy `i` changed; `engine` is the module fixture from `load_engine()`, as in `test_week.py`.)

- [ ] **Step 2: Run** `python -m pytest backend/tests/test_profile.py -q` — expect ImportError / failures.
- [ ] **Step 3: Add the tags and `strategies.json`, then implement `load_strategies`, `validate_strategies`, `questions`** in `engine/profile.py`. `validate_strategies` checks: question ids unique; every `when` key is a question id and every value one of its options or `"*"`; lever type known; for `meal_carb_share` with `meal_from`, the map covers every option of that question; strategies have grade A-C, at least one PMID, a goal in `known_goals`; goal links have alpha in (0, 1]. `load_strategies` is `lru_cache`d and validates the structure (goal existence is checked where the engine is available: `propose`/`resolve` and the test).
- [ ] **Step 4: Run** the tests — expect 3 passed; run `python -m pytest backend/tests/test_week.py -q` — expect all passed (tags are additive).
- [ ] **Step 5: Commit** "Strategies file and food tags for planner preferences".

### Task 2: From answers to levers

**Files:**
- Modify: `backend/feedforward/engine/needs.py` (add `resting_kcal`, use it in `energy_kcal`)
- Modify: `backend/feedforward/engine/profile.py`
- Modify: `backend/tests/test_profile.py`

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `needs.resting_kcal(p: Profile) -> float` (Mifflin-St Jeor, no PAL, no pregnancy add-on).
  - `ENERGY_FACTORS = {"maintain": 1.0, "deficit": 0.85, "surplus": 1.10}`.
  - `energy_options(p: Profile) -> dict[str, str | None]`: reason per option, `None` when allowed.
  - `@dataclass(frozen=True) class Levers` with fields `goals: dict[str, float]`, `energy_goal: str`, `energy_factor: float`, `protein_g_per_kg: float | None`, `meal_carb_share: dict[str, float]`, `breakfast_energy_min: float | None`, `breakfast_energy_max: float | None`, `protein_per_meal_g_per_kg: float | None`, `breakfast_protein_g_per_kg: float | None`, `no_caffeine_at: frozenset[str]`, `exclude: frozenset[str]`, `avoid_recipes: frozenset[str]`, `max_minutes: int | None`, `batch_ok: bool`, `applied: tuple[dict, ...]`; and `Levers.none(goal: str | None) -> Levers` (today's behaviour).
  - `propose(answers: dict, p: Profile, *, goal: str | None, known_goals: set[str]) -> dict` → `{"goals": [{"id", "alpha", "because"}], "strategies": [entry + "because"], "unavailable": {"energy_goal=deficit": reason, ...}}`.
  - `resolve(answers: dict | None, declined: list[str] | None, p: Profile, *, goal: str | None, known_goals: set[str], avoid_recipes: list[str] | None = None) -> Levers`.

`because` is `{"question": id, "answer": value}` from the first matching condition. Several `meal_carb_share` levers on one meal keep the highest `min`. `max_minutes` is `None` for `any`. Messages for `energy_options`: under 18 "Deficit and surplus are for adults: under 18 the plan follows growth needs."; pregnant or breastfeeding "In pregnancy and breastfeeding the plan follows the needs of those months."; BMI < 18.5 (deficit only) "With a BMI under 18.5 a deficit is not offered."

- [ ] **Step 1: Write the failing tests**

```python
STUDENT = Profile(24, "male", 72, 178, "light")

def test_resting_energy_is_mifflin_without_activity():
    assert resting_kcal(STUDENT) == pytest.approx(10 * 72 + 6.25 * 178 - 5 * 24 + 5)
    assert energy_kcal(STUDENT) == round(resting_kcal(STUDENT) * 1.375)

def test_energy_goal_limits():
    assert profile.energy_options(STUDENT) == {"maintain": None, "deficit": None, "surplus": None}
    assert profile.energy_options(Profile(16, "male", 60, 170))["deficit"]
    assert profile.energy_options(Profile(16, "male", 60, 170))["surplus"]
    assert profile.energy_options(Profile(30, "female", 60, 165, pregnant=True))["deficit"]
    thin = Profile(25, "female", 48, 170)            # BMI 16.6
    assert profile.energy_options(thin)["deficit"] and profile.energy_options(thin)["surplus"] is None
    with pytest.raises(ValueError):
        profile.resolve({"energy_goal": "deficit"}, None, thin, goal=None, known_goals=GOALS)

def test_answers_turn_on_goals_and_strategies():
    lv = profile.resolve({"sleep_onset": "often", "training_days": "3-4", "training_time": "evening"}, None,
                         STUDENT, goal="cognitive_function", known_goals=GOALS)
    assert lv.goals == {"cognitive_function": 1.0, "sleep_support": 0.5, "muscle_recovery": 0.5}
    assert lv.meal_carb_share == {"dinner": 0.40} and lv.no_caffeine_at == {"dinner"}
    assert lv.protein_g_per_kg == 1.6 and lv.protein_per_meal_g_per_kg == 0.3
    assert {a["id"] for a in lv.applied} >= {"evening_carbs", "no_evening_caffeine", "protein_target",
                                              "protein_spread", "post_training_carbs"}

def test_primary_goal_keeps_alpha_one():
    lv = profile.resolve({"study_time": "afternoons"}, None, STUDENT, goal="cognitive_function", known_goals=GOALS)
    assert lv.goals == {"cognitive_function": 1.0}

def test_preferences_and_energy():
    lv = profile.resolve({"energy_goal": "deficit", "dont_eat": ["fish_seafood", "spicy"], "cook_time": "20",
                          "batch_ok": "yes", "morning_hunger": "not_hungry"}, None, STUDENT, goal=None, known_goals=GOALS)
    assert lv.energy_factor == 0.85 and lv.exclude == {"fish_seafood", "spicy"}
    assert lv.max_minutes == 20 and lv.batch_ok and lv.breakfast_energy_max == 0.20

def test_partial_answers_and_declined():                                  # Review Focus 1 and 5
    lv = profile.resolve({"sleep_onset": "often"}, ["evening_carbs", "big_breakfast"], STUDENT, goal=None, known_goals=GOALS)
    assert lv.meal_carb_share == {} and lv.no_caffeine_at == {"dinner"}
    with pytest.raises(ValueError):
        profile.resolve({"sleep_onset": "often"}, ["levitation"], STUDENT, goal=None, known_goals=GOALS)

def test_unknown_answers_are_errors():
    for bad in ({"sleep_onset": "never"}, {"mood": "ok"}, {"dont_eat": ["kale"]}, {"dont_eat": "fish_seafood"}):
        with pytest.raises(ValueError):
            profile.resolve(bad, None, STUDENT, goal=None, known_goals=GOALS)

def test_no_answers_is_today():
    assert profile.resolve(None, None, STUDENT, goal="sleep_support", known_goals=GOALS) == profile.Levers.none("sleep_support")
```

(`GOALS = set(load_engine().scorer.positive)` at module level, or from the fixture.)

- [ ] **Step 2: Run** `python -m pytest backend/tests/test_profile.py -q` — expect the new tests to fail.
- [ ] **Step 3: Implement** `resting_kcal` (and make `energy_kcal` call it), then `energy_options`, `Levers`, `propose`, `resolve` in `engine/profile.py`.
- [ ] **Step 4: Run** `python -m pytest backend/tests/test_profile.py backend/tests/test_week.py -q` — expect all passed.
- [ ] **Step 5: Commit** "Answers resolve into levers: goals, strategies, energy limits".

### Task 3: The planner takes the levers (context, filters, energy, weights)

**Files:**
- Modify: `backend/feedforward/engine/week_planner.py` (`Recipe`, `_recipes`, `portion_scale`, `_Week`, `_context`, `plan_week`, `evaluate_week`, `swap_options`, `_minimum_budget`)
- Create: `backend/tests/test_preferences.py`

**Interfaces:**
- Consumes: `profile.resolve`, `profile.Levers`, `needs.resting_kcal`.
- Produces:
  - `Recipe.tags: frozenset[str]` (its ingredients' tags ∪ its own `tags`).
  - `portion_scale(profile: Profile, kcal: float | None = None) -> float` (uses `kcal` when given).
  - `_Week` gains `levers: Levers`, `goal_of: dict[str, str]` (nutrient → goal that set its weight), `resting_kcal: float`.
  - `_Week.allowed(r: Recipe, meal: str) -> bool` (False at a `no_caffeine_at` meal for a `caffeine`-tagged recipe).
  - `_context(rec, profile, *, goal, chain, diet, equipment, pantry, days, answers=None, declined=None, avoid_recipes=None) -> _Week`.
  - `plan_week`, `evaluate_week`, `swap_options`, `_minimum_budget` gain keyword args `answers: dict | None = None, declined: list[str] | None = None, avoid_recipes: list[str] | None = None` and pass them on (`_minimum_budget` passes them to its inner `plan_week` calls).

In `_context`: resolve the levers (`known_goals = set(rec.scorer.positive)`); daily target = `max(resting_kcal, energy_kcal * energy_factor)`; `kcal_target` = that × days; `scale = portion_scale(profile, daily target)`; weekly protein = `max(current, g_per_kg * weight_kg) * days` when `protein_g_per_kg`; filter recipes by `exclude` (on `Recipe.tags`), `avoid_recipes` (unknown ids raise `ValueError`), `max_minutes` (`time_min <= limit`, or `<= 3 * limit` for batch recipes when `batch_ok`); association `a(n) = max_g alpha_g * a_g(n)` with `goal_of[n]` the arg-max goal; `evidence` per nutrient read from `edge_meta[f"{n}->{goal_of[n]}"]`. Pantry ingredients follow the same filters (an excluded recipe is gone whatever is at home). `plan_week` creates `x[r, m]` only when `ctx.allowed(r, m)`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_preferences.py`

```python
def test_no_answers_gives_todays_plan(engine):
    plain = wp.plan_week(engine, STUDENT, goal="cognitive_function", budget=50, chain="lidl")
    same = wp.plan_week(engine, STUDENT, goal="cognitive_function", budget=50, chain="lidl", answers=None, declined=None)
    assert _composition(plain) == _composition(same) and plain["total_cost"] == same["total_cost"]

def test_energy_goal_moves_the_target(engine):
    base = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl")["energy"]["target_per_day"]
    for goal, factor in (("deficit", 0.85), ("surplus", 1.10)):
        plan = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", answers={"energy_goal": goal})
        assert plan["energy"]["target_per_day"] == pytest.approx(base * factor, abs=2)
        assert plan["energy"]["in_band"]

def test_excluded_foods_never_appear(engine):                     # with Review Focus 3
    plan = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", pantry=["sardines"],
                        answers={"dont_eat": ["fish_seafood", "legumes", "spicy"]})
    assert plan["feasible"] and not _tags_in(plan) & {"fish_seafood", "legumes", "spicy"}

def test_cooking_time_and_not_for_me(engine):
    plan = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", answers={"cook_time": "20"},
                        avoid_recipes=["sardine-tartines"])
    times = [m["time_min"] for d in plan["days"] for m in d["meals"].values()]
    assert max(times) <= 20 and "sardine-tartines" not in _ids(plan)
    with pytest.raises(ValueError):
        wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", avoid_recipes=["nope"])

def test_answers_weight_the_graph_goals(engine):
    ctx = wp._context(engine, STUDENT, goal="cognitive_function", chain="lidl", diet=None, equipment=None,
                      pantry=None, days=7, answers={"sleep_onset": "often"})
    assert ctx.goal_of["magnesium"] in {"sleep_support", "cognitive_function"}
    assert ctx.assoc["magnesium"] >= 0.5 * dict((n, a) for n, a, _ in engine.scorer.positive["sleep_support"])["magnesium"]
    assert ctx.goal_of["epa-dha"] == "cognitive_function"
```

(`_composition`, `_ids(plan)`, `_tags_of(ids)` and `_tags_in(plan)` are small helpers in the test file: recipe ids per day; all planned recipe ids; the union of the tags of some recipe ids (from `wp._recipes(engine)`); `_tags_of(_ids(plan))`.)

- [ ] **Step 2: Run** `python -m pytest backend/tests/test_preferences.py -q` — expect failures (unexpected keyword `answers`).
- [ ] **Step 3: Implement** the interfaces above in `week_planner.py`.
- [ ] **Step 4: Run** `python -m pytest backend/tests/test_preferences.py backend/tests/test_week.py -q` — expect all passed.
- [ ] **Step 5: Commit** "Planner takes the levers: energy goal, protein, graph goal weights, hard filters".

### Task 4: Soft levers in the MILP, and what the plan reports

**Files:**
- Modify: `backend/feedforward/engine/week_planner.py` (`plan_week`, `_assemble`)
- Modify: `backend/tests/test_preferences.py`

**Interfaces:**
- Consumes: Task 3 (`ctx.levers`, `ctx.goal_of`, `ctx.resting_kcal`).
- Produces in the plan dict: `energy.goal`, `energy.resting`; `protein_target_g` (per day); `goals: [{"id", "alpha"}]`; `strategies: [{"id", "kind", "text", "why", "grade", "goal", "pmids", "because", "met_days", "value"}]`; `targets.protein` = protein target per day. `PREFERENCE_WEIGHT = 0.3`.

MILP terms, with `S_m(n) = Σ_r n_r · x[r, m]`, each slack ≥ 0 and divided by the normaliser before weighting:

| lever | constraint | normaliser |
|---|---|---|
| `meal_carb_share[m] = p` | `S_m(carbs) + sl ≥ p · intake(carbs)` | `p · 0.525 · kcal_target / 4` |
| `breakfast_energy_min = p` | `S_b(kcal) + sl ≥ p · intake(kcal)` | `p · kcal_target` |
| `breakfast_energy_max = p` | `S_b(kcal) − sl ≤ p · intake(kcal)` | `p · kcal_target` |
| `protein_per_meal = t` | penalty `Σ_{r, m main} max(0, t·kg − protein_r) / (t·kg) · x[r, m]` (constants) | `3 · days` |
| `breakfast_protein = t` | same, breakfast only | `days` |

Objective: subtract `PREFERENCE_WEIGHT · Σ normalised slacks`. Reporting per day (after `_schedule`): a share lever is met when the day's share ≥ `p − 0.005` (≤ `p + 0.005` for a max); a per-meal protein lever when every main meal (or breakfast) reaches `0.98 · t · kg`; `no_caffeine` and preferences report `met_days = days`. `value` is the week's mean, as text: `"dinner carbs 44 %"`, `"breakfast 31 % of energy"`, `"protein 1.6 g/kg"`, `"main meals ≥ 22 g protein on 6 of 7 days"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_evening_carbs_shifts_carbs_to_dinner(engine):
    plain = _plan(engine)
    sleep = _plan(engine, answers={"sleep_onset": "often"})
    assert _dinner_carb_share(sleep) > _dinner_carb_share(plain)
    s = _strategy(sleep, "evening_carbs")
    assert s["met_days"] >= 5 and s["grade"] == "C" and s["pmids"] == ["17284739", "27633109"]

def test_breakfast_size_follows_morning_hunger(engine):
    big = _plan(engine, answers={"morning_hunger": "hungry"})
    light = _plan(engine, answers={"morning_hunger": "not_hungry"})
    assert _breakfast_energy_share(big) >= 0.30 - 0.01 and _breakfast_energy_share(light) <= 0.20 + 0.01

def test_protein_target_and_spread(engine):
    plan = _plan(engine, answers={"training_days": "5+", "training_time": "afternoon"})
    assert plan["protein_target_g"] == pytest.approx(1.6 * 72, abs=0.5) == plan["targets"]["protein"]
    assert _strategy(plan, "protein_spread")["met_days"] >= 5

def test_needs_come_first(engine):
    plain = _plan(engine)
    covered = [n for n, v in plain["coverage"].items() if v >= 100]
    for answers in ({"sleep_onset": "often"}, {"morning_hunger": "hungry"}, {"morning_hunger": "not_hungry"},
                    {"training_days": "5+", "training_time": "before_breakfast"}, {"energy_dips": "mid_morning"}):
        plan = _plan(engine, answers=answers)
        assert all(plan["coverage"][n] >= 97 for n in covered), (answers, {n: plan["coverage"][n] for n in covered})

def test_conflicting_answers_still_plan(engine):                  # Review Focus 2
    plan = _plan(engine, answers={"energy_goal": "deficit", "morning_hunger": "not_hungry", "energy_dips": "mid_morning",
                                  "training_days": "5+", "training_time": "morning", "sleep_onset": "often"})
    assert plan["feasible"] and plan["energy"]["in_band"] and len(plan["strategies"]) >= 6
```

(`_plan(engine, **kw)` = `wp.plan_week(engine, STUDENT, goal="cognitive_function", budget=60, chain="lidl", **kw)`; `_dinner_carb_share`, `_breakfast_energy_share` are week means from `plan["days"]` totals and meals; `_strategy(plan, id)` finds the entry.)

- [ ] **Step 2: Run** `python -m pytest backend/tests/test_preferences.py -q` — expect the new tests to fail.
- [ ] **Step 3: Implement** the soft levers and the report. If `test_needs_come_first` fails, lower `PREFERENCE_WEIGHT` (0.3 → 0.1) before anything else and note the value in the module docstring.
- [ ] **Step 4: Run** `python -m pytest backend/tests/test_preferences.py backend/tests/test_week.py -q` — expect all passed; note the slowest test time.
- [ ] **Step 5: Commit** "Soft levers in the week MILP, reported per day with their evidence".

### Task 5: Too few recipes: say what to relax

**Files:**
- Modify: `backend/feedforward/engine/week_planner.py` (`_relax`, `plan_week`, `REASONS`)
- Modify: `backend/tests/test_preferences.py`

**Interfaces:**
- Produces: `MIN_OPTIONS = 3`; `_relax(rec, profile, *, goal, chain, diet, equipment, pantry, days, answers, declined, avoid_recipes) -> list[dict]`; plan key `relax` (always present, `[]` when nothing is short); `REASONS["recipes"] = "Too few recipes fit these settings to fill a week."`.

`_relax` counts recipes per meal in the filtered context; for each meal under `MIN_OPTIONS` it tries one change at a time and keeps those that raise that meal's count: `cook_time` to the next level (10 → 20 → 30 → any), each `dont_eat` category removed, `batch_ok` set to `yes`, the avoided recipes for that meal un-avoided (one entry), diet one step looser (vegan → vegetarian → none) last. Entry: `{"filter": "cook_time" | "dont_eat" | "batch_ok" | "avoid_recipes" | "diet", "now": ..., "try": ..., "meal": m, "options_now": count_before, "options": count_after}`, sorted by `options` descending, at most 3 per meal. A meal with 0 recipes returns `{"feasible": False, "reason": "recipes", "note": REASONS["recipes"], "relax": [...], ...}` before solving.

- [ ] **Step 1: Write the failing tests**

```python
def test_no_recipe_for_a_meal_says_what_to_relax(engine):
    breakfasts = [r["id"] for r in wp._load()[1] if "breakfast" in r["meals"]]
    plan = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", avoid_recipes=breakfasts)
    assert not plan["feasible"] and plan["reason"] == "recipes"
    assert "avoid_recipes" in {r["filter"] for r in plan["relax"] if r["meal"] == "breakfast"}

def test_relax_entries_always_help(engine):
    plan = wp.plan_week(engine, STUDENT, goal=None, budget=80, chain="lidl", diet="vegan",
                        answers={"cook_time": "10", "dont_eat": ["legumes", "nuts"]})
    assert all(r["options"] > r["options_now"] for r in plan["relax"])
    assert _plan(engine)["relax"] == []
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement** `_relax` and the early return.
- [ ] **Step 4: Run** `python -m pytest backend/tests/test_preferences.py backend/tests/test_week.py -q` — expect all passed.
- [ ] **Step 5: Commit** "When filters leave too few recipes, say which one to relax".

### Task 6: Edited weeks and swaps keep the preferences

**Files:**
- Modify: `backend/feedforward/engine/week_planner.py` (`_week_from`, `swap_options`)
- Modify: `backend/tests/test_preferences.py`

**Interfaces:**
- Consumes: `ctx.allowed`, the plan's `strategies`.
- Produces: `_week_from` rejects a recipe that is filtered out or not allowed at that meal ("day N: 'id' is not a dinner for these settings"); each swap option gains `"breaks": [strategy ids whose met_days would drop]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_edited_week_with_an_avoided_recipe_is_refused(engine):      # Review Focus 4
    plan = _plan(engine)
    rid = plan["days"][0]["meals"]["dinner"]["id"]
    with pytest.raises(ValueError, match=rid):
        wp.evaluate_week(engine, STUDENT, _composition(plan), goal="cognitive_function", budget=60, chain="lidl",
                         avoid_recipes=[rid])

def test_swaps_keep_filters_and_say_what_they_break(engine):
    answers = {"sleep_onset": "often", "dont_eat": ["fish_seafood"]}
    plan = _plan(engine, answers=answers)
    opts = wp.swap_options(engine, STUDENT, _composition(plan), 2, "dinner", goal="cognitive_function",
                           budget=60, chain="lidl", answers=answers)
    assert opts["options"] and all("breaks" in o for o in opts["options"])
    assert not _tags_of({o["id"] for o in opts["options"]}) & {"fish_seafood"}
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python -m pytest backend/tests/test_preferences.py backend/tests/test_week.py -q` — expect all passed.
- [ ] **Step 5: Commit** "Edited weeks and swaps keep the person's preferences".

### Task 7: API

**Files:**
- Modify: `backend/feedforward/api/routers/plan.py`
- Modify: `backend/tests/test_preferences.py`

**Interfaces:**
- Consumes: `profile.questions`, `profile.propose`, `profile.CATEGORIES`, the new `plan_week` / `evaluate_week` / `swap_options` keywords.
- Produces: `GET /plan/questions` → `{"questions": [...], "categories": [...]}`; `POST /plan/strategies` (body: `WeekRequest`) → `propose(...)` result; `WeekRequest` gains `answers: dict[str, str | list[str]] | None = None`, `declined: list[str] | None = None`, `avoid_recipes: list[str] | None = None`, passed by `_settings`.

- [ ] **Step 1: Write the failing test**

```python
def test_preferences_api_round_trip():
    with TestClient(app) as client:
        q = client.get("/plan/questions").json()
        assert {x["id"] for x in q["questions"]} >= {"energy_goal", "sleep_onset", "dont_eat", "cook_time"}
        body = {"age": 24, "sex": "male", "weight_kg": 72, "height_cm": 178, "goal": "cognitive_function",
                "budget": 60, "chain": "lidl"}
        prop = client.post("/plan/strategies", json={**body, "answers": {"sleep_onset": "often"}}).json()
        assert "evening_carbs" in {s["id"] for s in prop["strategies"]}
        plan = client.post("/plan/week", json={**body, "answers": {"sleep_onset": "often"}, "declined": ["no_evening_caffeine"]}).json()
        assert {s["id"] for s in plan["strategies"]} >= {"evening_carbs"} and "no_evening_caffeine" not in {s["id"] for s in plan["strategies"]}
        teen = {**body, "age": 16, "answers": {"energy_goal": "deficit"}}
        assert client.post("/plan/week", json=teen).status_code == 400
        assert client.post("/plan/strategies", json={**body, "age": 16}).json()["unavailable"]["energy_goal=deficit"]
        assert client.post("/plan/week", json={**body, "answers": {"sleep_onset": "never"}}).status_code == 400
        assert client.post("/plan/week", json={**body, "avoid_recipes": ["nope"]}).status_code == 400
```

- [ ] **Step 2: Run** — expect failures (404 on `/plan/questions`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python -m pytest backend/tests/test_preferences.py backend/tests/test_week.py -q` — expect all passed.
- [ ] **Step 5: Commit** "API: questions, strategy proposals, preferences on every plan endpoint".

### Task 8: Sweep, decision record, README

**Files:**
- Modify: `backend/tests/test_week.py` (`_violations`, `test_planner_handles_the_input_space`)
- Modify: `DECISIONS.md` (decision 21), `README.md` (a "Preferences" paragraph under the app section, test count)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Extend the sweep.** `_violations(plan, profile, budget, diet, kitchen, answers=None)` also checks, for feasible plans: no planned recipe tagged with an `answers["dont_eat"]` category; every main meal within the `cook_time` limit (3× for batch recipes when `batch_ok` is `yes`); no `caffeine`-tagged dinner when `sleep_onset` is `sometimes`/`often` and `no_evening_caffeine` was not declined. For infeasible plans, `reason == "recipes"` is a violation only if `relax` is empty. In `test_planner_handles_the_input_space`, add 25 cases with `random.Random(7)`: a profile from the existing three plus random ones, budget 500 or 60, a chain from `("lidl", "carrefour", "naturalia")`, and answers built by choosing, for each question, "unanswered" or a random option (`dont_eat`: 0-3 random categories); skip `energy_goal` options that `profile.energy_options` refuses.
- [ ] **Step 2: Run** `python -m pytest backend/tests/test_week.py::test_planner_handles_the_input_space -q` — expect PASS; if a case fails, fix the engine, not the test.
- [ ] **Step 3: Write decision 21** in `DECISIONS.md`, above 20: "Preferences from questions, grounded in the graph" (Decision: answers → goals with alpha 0.5 and strategies graded A-C with PMIDs; deficit −15 % / surplus +10 % with the limits. Why: plans people did not choose feel imposed; a light, bounded energy goal is what many students want, and needs first keeps it safe. Cost: revisits the "no weight goal" part of decision 19; weekly levers can miss single days, and the plan says so.) Add the README paragraph (questions, strategies with grades, energy goal limits, `relax`) and update the test count.
- [ ] **Step 4: Run the full suite** `python -m pytest backend -q` — expect all passed (202 + the new tests).
- [ ] **Step 5: Commit** "Input-space sweep with preferences; decision 21; README".
