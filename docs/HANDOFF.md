# FeedForward: handoff brief for the next phase

Read this first if you have never seen FeedForward. It says what the product is,
how to run it, where everything lives, what must not be broken, and what the
owner wants next. Then read `README.md` (product and figures) and `DECISIONS.md`
(22 design decisions with their alternatives and costs).

Branch: `dashboard-ui-oyyga4` (newest work; `main` has an older UI).

---

## 1. The product in one paragraph

FeedForward is a nutrition app grounded in science. A person signs in (Google),
answers a few questions (body data, one goal such as sleep, focus, energy or
iron, an energy goal: keep steady / lose a little / gain a little, optional
habits and food preferences), and gets a diary that **starts empty**. For each
meal they can log what they ate, or tap **Ideas** for three recipes ranked for
their day so far, their goal and their answers, each with the reason ("Magnesium
32%", "Carb-rich, for your evenings · grade C"). An optional **planned week**
fits a budget at their own supermarket (French chains, prices from real
receipts) with a shopping list. Every suggestion can be explained as a graph
path *food → nutrient → goal*, backed by EU-authorised health claims (EFSA) or
graded literature. Think "MyFitnessPal / Yazio, but with the science shown and
the person in charge".

The owner's goal for the next phase: take it to its best possible level as a
product people come back to every day: engaging, habit-forming, social, with AI
features, informed by a real market analysis.

## 2. Run it

```bash
cd backend
pip install -r requirements.txt
uvicorn feedforward.api.main:app --reload      # app: http://localhost:8000/app, API docs: /docs
pytest -q                                      # 297 tests, about 3 minutes
```

Sign-in on a local machine: type any name (test sign-in, off in production).
Google sign-in needs `FEEDFORWARD_GOOGLE_CLIENT_ID` (README, "Sign in with Google").
Playwright + Chromium are a good way to drive the app and take screenshots.

## 3. Architecture map

```
web/index.html (one file, no build step, vanilla JS)  ── the whole web app
        │  fetch, JWT bearer
api/ (FastAPI)
  routers/auth_router.py   /auth: config, google, dev, me, export, delete
  routers/me.py            /me/state: one JSON document per account (answers, diary, list)
  routers/diary.py         /diary: day totals, ideas for one meal, search foods and recipes
  routers/plan.py          /plan: questions, strategies, week, evaluate, swap, recipes, why
  routers/recommend.py, analysis.py, dictionary.py, goals.py   foods, graph explanations, dictionary
engine/ (pure Python, no network)
  build.py, algorithms.py, recommender.py   knowledge graph, Dijkstra from each goal, ranking
  needs.py, reference.py                    personal needs (EFSA reference intakes, Mifflin-St Jeor)
  profile.py + data/strategies.json         questions → strategies (graded A–C, PubMed ids) → "levers"
  week_planner.py, milp.py                  weekly MILP (PuLP/CBC): needs first, then levers, budget
  diary.py                                  logged day vs targets; ideas per meal
db/ (SQLAlchemy, Alembic)  users, user_state, the food corpus. SQLite locally, PostgreSQL in production
mobile/                    early Expo prototype (behind the web app; not maintained)
```

Data: CIQUAL 2020 and USDA (composition), Open Food Facts and Open Prices
(products, prices), the EU register of health claims, PubMed. 52 recipes
(drafts, not yet reviewed by a dietitian). Licences in `DATA_LICENSES.md`.

## 4. Non-negotiables (keep these whatever you change)

1. **Evidence is shown, never invented.** Health wording comes from the EU
   register or from graded literature with its sources. EU regulated nutrition
   claim terms ("rich in", "source of") are not used loosely; the app states the
   share of daily need instead. No fake citations, no AI-generated health claims
   presented as fact.
2. **Information, not medical advice.** No medical conditions are collected (EU
   medical-device rules). AI features must respect this too.
3. **Needs first, nothing restrictive.** Energy is never planned below resting
   energy; a deficit is light (−15 %) and closed to under-18s, pregnancy,
   breastfeeding and BMI < 18.5. The ring is a level to reach, not "calories
   left"; nothing turns red when someone eats more.
4. **The person is in charge.** The app starts empty; plans, lists and
   strategies appear only when asked for, and each can be switched off.
5. **Privacy.** Personal data stays in the person's account, exportable and
   deletable; nothing is sold or sent to third parties without consent.
6. **Tested.** Every engine change comes with tests; the input-space sweep in
   `tests/test_week.py` must keep passing.

## 5. Engagement, done responsibly

The owner wants it engaging and habit-forming: progress, streaks, a social
side, AI features. In a food app this has a known failure mode: calorie
streaks, leaderboards on weight or intake, and shame on a missed day are linked
to disordered eating and to people quitting. So design for **healthy habits and
intrinsic motivation**, for example:

- Progress on what FeedForward is uniquely good at: nutrients covered by food,
  variety of plants and colours, goal nutrients reached, new recipes cooked,
  money saved against the budget. Not weight lost or calories under target.
- Streaks that forgive: logging *or* cooking counts, a missed day pauses rather
  than resets ("freeze" days), weekly rather than daily goals as the default.
- Social around cooking and sharing (recipes, shopping lists, cooking for
  flatmates, challenges such as "5 plant colours this week"), never comparison
  of bodies or intake. Opt-in, private by default.
- AI that helps and cites: describe or photograph a meal to log it (with the
  estimate shown as an estimate), ask "why?" in plain language and get the
  graph path and its sources, turn the fridge's contents into an idea, adapt a
  recipe. AI output must be grounded in the engine's data, not free-written
  nutrition advice.
- A check for every feature: would this make someone with a difficult
  relationship with food feel worse? If yes, change it.

## 6. What is asked of you

Work in this order, and show the owner each step before building the next:

1. **Market analysis.** Competitors (MyFitnessPal, Yazio, Lifesum, Cronometer,
   Noom, Mealime, Eat This Much, Too Good To Go-style budget apps, Strava and
   Duolingo for engagement patterns): positioning, pricing, retention
   mechanics, what users praise and hate in reviews. Who FeedForward is for
   (students on a budget in France first?), and the gap it fills.
2. **Product and UX strategy.** The core loop (open → log or get an idea →
   eat → see progress), onboarding to first value in under a minute,
   retention mechanics from section 5, notifications that help rather than
   nag, accessibility (WCAG AA, already the bar for colours).
3. **UI.** A design system (tokens already exist as CSS variables in
   `web/index.html`, light and dark), screens for the new features, motion,
   real food photography or illustration instead of emoji placeholders.
4. **Architecture for the next stage.** The web app is one 2,500-line HTML
   file with no build step. Decide whether to keep it, move to a component
   framework, or go mobile-first (PWA vs the Expo prototype in `mobile/`), and
   what the backend needs for social features (user-to-user data, moderation,
   notifications, background jobs) and AI features (model calls, cost, caching,
   grounding in the engine). Write it down as decisions in `DECISIONS.md`.
5. **Build it in small steps,** each with tests, screenshots and a short note.

Deliverables the owner expects: a market analysis document, a product
strategy with the engagement design, UI mockups or a working prototype, an
architecture plan, then working code.

## 7. Known limits and open questions

- Recipes (52) are drafts in French and English; no photos; no dietitian review yet.
- Prices cover French chains only (Open Prices receipts, some estimated).
- Ideas per meal are fast (~20 ms) but come from 52 recipes: variety is the
  first thing users will notice. More recipes, user recipes, or products from
  Open Food Facts are open options.
- The test sign-in is for development; Google sign-in needs a client ID per deployment.
- Not yet tested with real users or reviewed by experts; the owner plans to
  show it to dietitians.
- Open questions for the owner: target market and language (France? Italy?
  English?), free vs paid, how social it should be, budget for AI calls.
