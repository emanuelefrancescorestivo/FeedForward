# Design decisions

The choices that shape FeedForward, why they were made, what was considered
instead, and what each one costs. Numbers are the constants in the code at
the time of writing; the file named under each decision is where to look.

---

## Graph and ranking

### 1. Edge cost = −log(strength)
**Decision.** Every Food → Nutrient and Nutrient → Goal edge has a strength in
(0, 1]; its cost for shortest-path search is −log(strength).
**Why.** A path's strength is the product of its edges, and −log turns that
product into a sum, so Dijkstra's shortest path *is* the strongest
food → nutrient → goal chain, and Yen's k-shortest paths are the next-strongest
routes. The explanation shown to the user is exactly the path the ranking used.
**Instead.** Until v1.2 the cost was 1/strength after normalising by the
dataset maximum. That is not multiplicative, and the normalisation let
fortified powders and 100 g of dried herbs win every goal.
**Cost.** Strengths must stay in (0, 1]; a zero-strength edge is dropped, not
given an infinite cost.
*Where:* [`engine/build.py`](backend/feedforward/engine/build.py), [`engine/algorithms.py`](backend/feedforward/engine/algorithms.py)

### 2. Reverse Dijkstra from each goal, every score precomputed at startup
**Decision.** The graph is reversed and Dijkstra runs once from each of the 28
goals; all food × goal scores (≈ 278,000) are computed when the engine starts.
**Why.** The first version ran Dijkstra from every food for each query
(587 ms). A query is now a walk down a sorted list (≈ 0.7 ms).
**Cost.** Start-up takes ≈ 17 s (two thirds of it in the precomputation) and
the process holds ≈ 340 MB. Fine on a laptop or a small paid instance; too
slow for free hosting with 0.1 CPU. The next step would be to write the
precomputed scores to a file at build time and load them at start-up.
*Where:* [`engine/recommender.py`](backend/feedforward/engine/recommender.py)

### 3. Score one realistic portion, saturating at the EU claim thresholds
**Decision.** A food's contribution to a nutrient is what *one portion*
delivers as a share of the daily reference intake, passed through a
saturating curve with K = 4, so 15 % of the need (an EU "source of") scores
0.45, 30 % ("high in") 0.70, 100 % 0.98.
**Why.** Per-100 g rankings reward foods nobody eats 100 g of (baking powder,
dried herbs, spirulina powder). Saturation stops "ten days of vitamin K in a
spoon" from beating a food that covers several needs.
**Instead.** Per-100 g values; linear shares; per-kcal density. All three
produced implausible top results on the sanity benchmark.
**Cost.** Portions are a curated table (`data/portions.json`) that has to be
maintained; a wrong portion rule (lentils read as nuts, oranges as drinks)
moves foods a lot, so the rules are ordered and tested.
*Where:* [`engine/scoring.py`](backend/feedforward/engine/scoring.py), [`engine/portions.py`](backend/feedforward/engine/portions.py)

### 4. Several routes count, but only a few, at 0.3
**Decision.** A food's goal score is the strongest route in full plus the next
3 routes at weight 0.3 (noisy-OR), times penalties for salt, saturated fat and
sugars per portion and for exceeding an upper limit.
**Why.** The EU register links up to ~17 nutrients to one goal ("contributes to
normal cognitive function"). Counting all of them makes every nutrient-dense
food score near 100 and the ranking stops being about the goal; counting only
the best route ignores that a food can help in two ways.
**Cost.** Two constants chosen against the benchmark, not derived from theory.
*Where:* [`engine/scoring.py`](backend/feedforward/engine/scoring.py) (`SECONDARY_WEIGHT`, `SECONDARY_PATHS`)

### 5. Enhancers are pairings, not routes
**Decision.** Vitamin C raises non-heme iron absorption, but it is not an iron
source: it appears as a pairing tip and in meal-level absorption, never as a
route from a food to the iron goal.
**Why.** As a route, a vitamin C drink ranked as an "iron" food.
*Where:* [`engine/bioavailability.py`](backend/feedforward/engine/bioavailability.py), [`engine/recommender.py`](backend/feedforward/engine/recommender.py)

### 6. Familiarity orders results; it never changes a score
**Decision.** Everyday foods are listed first (CIQUAL and curated foods above
branded, restaurant, game or rare items), but the match score shown is
unchanged.
**Why.** Users could not act on "emu" at the top of a list; at the
same time, hiding the true score to push common foods up would be dishonest.
*Where:* [`engine/familiarity.py`](backend/feedforward/engine/familiarity.py)

## Evidence and safety

### 7. The EU register of health claims is the evidence layer
**Decision.** Nutrient → goal links come from the EU register (Regulation
1924/2006): authorised claims are grade A with their official wording; links
EFSA assessed and rejected are removed (e.g. vitamin E → heart health); links
from other sources without a claim are grade D.
**Why.** It is the legally binding, expert-reviewed statement of which
nutrient helps what in the EU, it is public, and it gives wording the app can
show verbatim. Mining PubMed hit counts, tried first, measures how much is
*written* about a topic, not whether it is true.
**Cost.** Coverage follows regulation, not the frontier of research: stress
has no authorised nutrient link, sleep only a grade-C one, and the app says so.
Text never uses the regulated terms ("source of", "high in") for foods; it
states the share of daily need instead.
*Where:* [`data/ingest/eu_claims.py`](backend/feedforward/data/ingest/eu_claims.py), [`docs/SCIENTIFIC_BASIS.md`](docs/SCIENTIFIC_BASIS.md)

### 8. Wellness goals only: no medical conditions, on purpose
**Decision.** The profile asks age, sex, height, weight, activity and
pregnancy/breastfeeding, never a disease or medication.
**Why.** Advice tailored to a condition is a medical decision, and software
that gives it is a medical device under the EU MDR. Staying general-population
keeps the app honest about what it is.
*Where:* [`engine/needs.py`](backend/feedforward/engine/needs.py)

### 9. "Flesh" and "animal-derived" are two properties
**Decision.** `is_animal_source` means animal flesh (heme iron, the meat
factor); `is_animal_derived` adds dairy and eggs (preformed vitamin A and its
upper limit). Both are matched on whole words; a source's own flag, where it
has one, is respected.
**Why.** One flag served both questions. Eggs and cheese got heme iron, and
tofu, filed by CIQUAL under "meat substitute", counted as meat. A test that
runs the diet filters over CIQUAL's own food groups found it.
*Where:* [`engine/build.py`](backend/feedforward/engine/build.py), [`tests/test_week.py`](backend/tests/test_week.py)

## The weekly planner

### 10. One mixed-integer programme for the week
**Decision.** Integer servings of each recipe per meal slot, whole packs for
fridge and bakery items, solved with CBC. The objective is the capped coverage
of each nutrient's weekly need, with the goal's nutrients weighted
1 + 3 × their association to the goal.
**Why.** Budget, packs and "7 breakfasts, 7 lunches, 7 dinners" are hard,
discrete constraints that interact: a greedy choice of the best recipe per
slot overspends or leaves a half-used pack of eggs. The same MILP on the single
meal beats the greedy top-ranked picks on coverage (tested).
**Cost.** A plan takes 0.5 to 3 s instead of milliseconds, and the solver is an
external binary (see decision 15).
*Where:* [`engine/week_planner.py`](backend/feedforward/engine/week_planner.py)

### 11. Energy is a hard constraint; the budget never cuts food
**Decision.** Planned energy must stay within 90–115 % of the person's need.
If no week fits the budget, a second solve finds the cheapest adequate week
and the app shows that minimum budget.
**Why.** An optimiser told to respect a budget will happily plan less food. For
students who already skip meals to save money, a plan that quietly
under-feeds would be harmful.
**Cost.** Some users get "at least €50" instead of a plan. That is the point.
**Revised.** Portions were first bounded to ×0.8–1.4 with at most 2 snacks a
day, which made the band unreachable for big needs: no student-athlete
(≈ 4,000 kcal a day) got a plan anywhere, at any budget, and the app blamed
"too few recipes". Portions now scale ×0.4–2.5 and snacks rise to 3 and 4 a
day above 2,800 and 3,800 kcal, so plans exist from ≈ 500 to ≈ 6,000 kcal a
day. Every "no plan" carries its reason (budget, energy, recipes).
*Where:* [`engine/week_planner.py`](backend/feedforward/engine/week_planner.py) (`ENERGY_BAND`, `PORTION_SCALE`, `SNACKS_PER_DAY`, `_minimum_budget`)

### 12. Variety is soft, and repeats are spread out
**Decision.** A recipe twice a week (three times for batch cooking), with
repeats allowed at a cost: the first extra time costs 1, each further one 3.
**Why.** As a hard cap, narrow settings (vegan + microwave only) had no plan
at all; with a flat penalty, all repeats landed on one dish every night.
*Where:* [`engine/week_planner.py`](backend/feedforward/engine/week_planner.py) (`REPEAT_PENALTY`)

## Data

### 13. Prices from open receipts, with robust statistics
**Decision.** Open Prices receipts (ODbL), last 30 months, per chain: median
€/kg; observations beyond 3× the national median dropped; a chain with *n*
receipts is shrunk towards national median × chain index as
(n · median + 5 · estimate) / (n + 5); chains with none use the estimate and
the app marks it ≈.
**Why.** Supermarkets publish no price data, and scraping their sites breaks
their terms. Crowdsourced receipts are legal and open, but noisy: before the
outlier rule, bananas at one chain came out at €15/kg.
**Instead considered.** Asking the chains for data (an email to their managers
is drafted), which may complement this later.
*Where:* [`data/ingest/prices.py`](backend/feedforward/data/ingest/prices.py)

### 14. One nutrient ontology; conversions that refuse to guess
**Decision.** Every source maps to 36 canonical nutrients (INFOODS tags,
IT/EN/FR aliases). Unit conversion refuses International Units for vitamins A
and E, where the factor depends on the chemical form; "traces" and "< 0.5"
are kept as qualified values, not zeros or guesses. CIQUAL energy missing for a
food is computed with the EU 1169/2011 factors, and the record says so.
**Why.** Merging five sources silently is how an app ends up with iron values
1,000 × too low (Open Food Facts stores grams, which was found and fixed).
*Where:* [`ontology/`](backend/feedforward/ontology/), [`data/ingest/ciqual.py`](backend/feedforward/data/ingest/ciqual.py)

## Engineering

### 15. One adapter around the solver library
**Decision.** All PuLP calls go through [`engine/milp.py`](backend/feedforward/engine/milp.py),
which works with PuLP 3 and 4.
**Why.** PuLP 4 stopped bundling CBC, removed the old variable API and reports
"stopped within the optimality gap" as its own status, so valid plans came
back as "impossible". Running the suite from a fresh clone in a new
environment caught it before CI did.
**Also here: a 1 % optimality gap.** Proving the last fraction of a percent took
20 s for athlete-sized weeks; stopping within 1 % takes under a second and
changed nutrient coverage by less than 0.4 points.

### 16. Unknown input is an error; the input space is tested, not the demo
**Decision.** An unknown diet, appliance or goal, a man marked pregnant, or
pregnant and breastfeeding at once, is rejected with a message instead of
being ignored. A sweep of 531 cases (every shop × diet × kitchen for small,
typical and athlete-sized needs, budget edges, the corners of every input
range, random profiles, every goal) checks that each answer is a plan within
budget and energy band that respects diet and kitchen, or a "no plan" with a
true reason; a smaller version runs in CI.
**Why.** Ignoring a misspelt "vegna" would hand a vegan a week with meat. And
the demo scenario hid that 35 % of the input space was broken.
*Where:* [`engine/week_planner.py`](backend/feedforward/engine/week_planner.py), [`tests/test_week.py`](backend/tests/test_week.py) (`test_planner_handles_the_input_space`)

### 17. "Why this meal?" only from 15 % of the daily need
**Decision.** An opened recipe lists the goal's nutrients one portion gives,
the ingredient each comes from and the evidence for the link, quoting the EU
claim, but only from 15 % of the daily need and only for evidence graded A to
C.
**Why.** 15 % is the EU threshold for a food to be a "source" of a vitamin or
mineral; citing a claim for a trace amount would mislead, and so would
literature-only (grade D) links such as vitamin K for iron.
*Where:* [`engine/week_planner.py`](backend/feedforward/engine/week_planner.py) (`recipe_why`)

### 22. An account, an empty start, and the day as a diary (branch `dashboard-ui`)
**Decision.** The app opens on a sign-in page (Google; on a developer's machine
also a test sign-in by name). A new account answers a few questions, one topic
per screen: about you, one goal and the energy goal are needed; "your day" and
"your food" can be skipped; the last screen lists what the answers turn on,
each strategy with its grade, the answer that triggered it and its sources, and
any can be switched off. Today then starts **empty**: each meal has "+ Add"
(log a food in grams or a recipe in portions) and "Ideas" (three recipes for
that meal, `POST /diary/suggest`). A planned week, the shopping list and the
shop and budget come only when the person asks for them. Everything they keep
(answers, diary, list) is one document in their account (`/me/state`), with
download and deletion in Profile.
**Why.** The first screen of the previous version was a plan and a shopping list
the person had not asked for, with meals they might not like or know how to
cook: a sense of being decided for, not helped. A diary with ideas on demand
keeps the person in charge and still puts the engine to work for each meal. An
account lets the diary follow them from phone to laptop, which a browser-only
store cannot do. Ideas follow the same answers as the week planner (one
`_context`, days = 1), so the two never disagree: foods not eaten, cooking time,
kitchen, "not for me" are hard filters; the strategies for that meal steer the
ranking and show as reasons.
**Instead.** Keeping data in the browser only (decision 18): more private, but
a diary that vanishes with a cleared browser, and no second device.
Email-and-password accounts: the backend already has them, but a password is
one more thing to create and leak; Google sign-in (an ID token checked against
Google's keys, this app as audience, a verified email) asks for nothing new.
**Cost.** The server now stores personal data: what someone eats and their
answers about sleep or training (no medical conditions, as before). It is kept
to one document per account, sent to no one else, downloadable, and deleted with
the account. A strategy that is about the whole day ("40 % of the day's
carbohydrates at dinner") cannot be judged on one meal, so an idea is marked
"carb-rich" when half its energy or more comes from carbohydrates, and the day
shows the real share once the meals are logged. A Google client ID must be
created once per deployment (README).
*Where:* [`engine/diary.py`](backend/feedforward/engine/diary.py), [`api/routers/diary.py`](backend/feedforward/api/routers/diary.py), [`api/routers/me.py`](backend/feedforward/api/routers/me.py), [`api/auth.py`](backend/feedforward/api/auth.py) (`verify_google`, `dev_login_enabled`), [`web/index.html`](backend/feedforward/web/index.html) (`renderGate`, `renderOnboarding`, `renderToday`, `openIdeas`)

### 21. Preferences from questions, grounded in the graph
**Decision.** A few plain questions shape the week: sleep, training, mornings,
study, foods you don't eat, how long you can cook, and an energy goal. The
answers about sleep, training days, energy dips and study turn on goals in the
knowledge graph, at half the weight of the person's own goal (alpha 0.5).
Answers also trigger strategies graded A to C with PubMed IDs, such as "no
caffeine at dinner" for people who sometimes or often take a long time to fall
asleep, or "protein at 1.6 g per kg" for people who train three or more days a
week or have chosen a deficit or a surplus; that 1.6 g/kg is a target the plan
aims for, not a need: coverage stays measured against the reference intake
(0.83 g/kg). Foods not eaten, cooking time, batch cooking and a lighter
breakfast (for people not hungry in the morning) are applied as asked and carry
no grade. The plan shows each strategy with its grade and sources, and the
person can decline any of them. The energy goal is to maintain, a deficit of
15 % or a surplus of 10 %; it is not offered under 18, in pregnancy or while
breastfeeding, and a deficit is not offered under a BMI of 18.5. The week's
energy is never planned below resting energy, and a deficit week is planned at
97 % of its target or more, so never more than 18 % below maintenance. In a
deficit week, meals and snacks are moved between days so that no day falls
below resting energy where the recipes allow; the plan counts any day left
below.
**Why.** A plan people did not choose feels imposed; asking, and showing the
evidence behind what an answer triggered, lets them judge it. A light, bounded
energy goal is a common request, and putting needs first keeps it safe:
the week is first planned for the needs alone (the reference intakes, protein
included), and the strategies may only trade a little of it: a nutrient may
fall to 97 % of its need at most (one already short does not fall further),
salt, saturated fat and free sugars may not go over their limits (nor further
over, where that week already was), the energy may move 3 % further from the
target, and the week may cost 5 % more than the week planned for the needs
alone.
**Cost.** It revisits the "no weight goal" part of decision 19: there is now an
energy goal, optional and bounded, instead of none. The strategies work on the
week, so a single day can miss one, and the plan says on how many of the seven
days each is met. With strategies on, the week is solved twice, and the second
solve stops after 3 s with the best week found by then (with none, the first
week stands): across the 25 random sets of answers (some strategies declined)
of the input-space test the median plan took 0.7 s and the slowest 3.5 s, the
second solve at most 3.1 s (6.1 s before it had a limit of its own). Grade C is
the weakest grade a strategy may carry (smaller trials or a position stand), and
the plan shows the grade and the sources next to each strategy.
*Where:* [`data/strategies.json`](backend/feedforward/data/strategies.json), [`engine/profile.py`](backend/feedforward/engine/profile.py) (`resolve`, `propose`, `energy_options`), [`engine/week_planner.py`](backend/feedforward/engine/week_planner.py) (`_energy_band`, `_after_needs`, `_balance`, `_strategy_report`, `_relax`), [`api/routers/plan.py`](backend/feedforward/api/routers/plan.py) (`/plan/questions`, `/plan/strategies`)

### 20. Food first, and a calmer look (branch `dashboard-ui`)
**Decision.** Each week says how many needs food already covers ("Food covers
25 of 27 needs"), and for each one still short gives a plain note on why (vitamin D
is mostly made in sunlight; B12 on a vegan diet needs a supplement or fortified
foods). The look moves to earthy pastels, one self-hosted typeface (Inter), a
sidebar on desktop and quiet motion, checked against seven laws of UX: Jakob
(layouts people know), Fitts (44 px targets), Hick (one summary line per card,
details on tap), Postel (answers typed as "1,78 m", "160 lb" or "€50" are read
correctly), peak-end ("Your week is ready", errors that offer a way out),
aesthetic-usability, and Von Restorff (a single tinted card, the food-first one).
**Why.** Students buy supplements for needs their plate already meets; the
planner already knows the week's coverage, so saying it is cheap and useful. It
must also say where food falls short, or it would be advice by omission. The
font is served by the app, not a CDN, so opening the page still sends nothing to
a third party.
**Cost.** "Covered" means at least 100 % of the reference intake over the week
as planned; the note for healthy people says so and tells anyone with a
prescription to keep taking it. 48 KB of font on first load.
*Where:* [`web/index.html`](backend/feedforward/web/index.html) (`foodFirst`, `readyBanner`, `readNumber`), [`api/main.py`](backend/feedforward/api/main.py) (`/app/fonts`)

### 19. A diary-style day, without calorie-counting pressure (branch `dashboard-ui`)
**Decision.** Each day is a dashboard in the layout people know from diary
apps: an energy ring with macro bars, meals as cards with an "eaten" tick, four
tabs (Today, Foods, List, Profile). FeedForward's own parts sit inside it: the
goal's nutrients for the day with the meal each comes from and an EU badge only
where an authorised claim backs the link, the recipe sheet (Recipe, Why, Swap),
the budget and the one shopping list.
**Why.** The familiar layout makes the app easy to read at a glance; the
content is what a calorie counter does not have. The ring shows energy
*planned* against the need: there is no "calories left" countdown, nothing turns
red above the need, "eaten" counts meals rather than calories, and there is no
weight goal. Calorie-first interfaces are the part of this category most
criticised for disordered-eating risk.
**Cost.** A second interface to maintain; it lives on its own branch until one
of the two is chosen. Macro targets use the midpoints of EFSA's ranges
(carbohydrates 45-60 %, fat 20-35 % of energy), which is a simplification.
*Where:* [`web/index.html`](backend/feedforward/web/index.html), [`engine/week_planner.py`](backend/feedforward/engine/week_planner.py) (`_assemble`: `targets`, per-day `totals`, `goal_today`, `goal_from`)

### 18. Privacy by construction, and a web app with no build step
**Decision.** *(Superseded in part by 22: answers, diary and list now live in
the person's account.)* The planner's answers live in the browser (localStorage); the
server computes the plan per request and stores nothing, including a week the
user edited, which is sent back and recomputed (`/plan/evaluate`). The web app
is one HTML file with no framework or build step, designed for progressive
disclosure (one question per screen, details on demand).
**Revised.** A word count of every screen found the first version text-heavy
and hard to navigate: 6 tabs that overlapped (three ways to look up a food, a
single-meal planner next to the weekly one, two shopping lists), 417 words on
the week view, a 68-word footer everywhere. It now has three sections (Week,
Foods, List), a 3-step setup, one line per meal with a recipe sheet instead of
inline expansion, one list, and an 8-word footer; the week view dropped to
281 words, the setup to 27 per step.
**Why.** No account is needed to be useful, and there is no personal data to
protect on the server. A single file keeps the front end readable and
deployable anywhere; the cost is less structure than a component framework
would give as the UI grows.
*Where:* [`web/index.html`](backend/feedforward/web/index.html), [`api/routers/plan.py`](backend/feedforward/api/routers/plan.py)
