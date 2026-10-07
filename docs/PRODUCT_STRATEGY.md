# FeedForward: product and UX strategy

*October 2026. Step 2 of the next phase (see [`HANDOFF.md`](HANDOFF.md), section 6).
Built on [`MARKET_ANALYSIS.md`](MARKET_ANALYSIS.md) and the owner's decisions
below. The non-negotiables of the handoff (section 4) are constraints on every
line of this document.*

---

## 0. Decisions taken

| Question | Decision (owner, 6-7 October 2026) |
|---|---|
| Market and language | France first; interface in French and English |
| Money | Free core forever, no ads; an optional low-price supporter tier later that covers costly AI use; no free feature ever moves behind a paywall |
| Social | Small private circles, invite-only, cooperative, opt-in |
| AI | A capped pilot (about €50 a month in total), only where language understanding saves real effort, grounded in the engine |
| Home screen | The diary stays home (Today), with the engagement features around it |
| Daily loop and first day | Approved as in sections 3-5 |
| Progress, streak, recap, notifications | Approved as in sections 6-10 |
| Circles, AI, safety, accessibility | Approved as in sections 11-14 |

## 1. Goal, and how we will know

FeedForward should be the app a student opens most days because it makes
eating well for little money easier, not because it pulls them back.

| Measure | Target | Why this one |
|---|---|---|
| **Food weeks** (north star): weeks in which a person used FeedForward on 3 days or more (logged, cooked, planned or used the list) | Grows week on week | Weekly, like the streak: frequency itself is not a goal |
| Still active at day 30 | 8 % or more of new accounts | Top quarter for health apps (3-8 % is usual) |
| Time from sign-in to the first idea seen | Under 60 s | The first value has to come before the first chore |
| Day 1: logged a meal or took an idea | 60 % of new accounts (proposed; to set once there are real users) | Shows the first day works |
| Guardrails: notification opt-out rate, streaks hidden, calm mode turned on, circle reports | Watched, never optimised away | A rise is a sign something feels like pressure |

Counts are first-party and aggregate (no third-party analytics), in line with
the privacy non-negotiable; the details belong to the architecture step.

## 2. Who it is for

Students in France, 18 to 26, with €25-60 a week for food (market analysis,
section 8): the budget cook, the student-athlete, the international student.
Their jobs, in their words:

- "Tell me what to eat next that I can make with what I have, cheaply."
- "Is what I eat enough? I'm tired, I train, I have exams."
- "Help me shop for the week without going over."
- "Cooking alone is boring; cooking with my flatmates is fun."

## 3. The daily loop

```
open Today ──► log it fast  ──┐
     │        or tap Ideas  ──┼──► eat ──► it counts: goal card, day dots ──► tomorrow
     │                        │
     └── once a week: "Your week in food" (Sunday) · circle challenge · plan a week if wanted
```

Today keeps its layout (ring, macro bars, meal cards, "Plan a whole week?").
The ring stays a level to reach: no "calories left", nothing red, nothing
"over". What is new sits around it: the week's day dots, a progress entry, a
circle entry, and faster logging.

## 4. The first day: value in under a minute

1. **Two required screens.** *About you* (age, height, weight, sex, activity)
   and *Goal* (one tap). The energy goal starts at *Keep steady*; *lose a
   little* and *gain a little* are in Profile, with the same limits as today
   (not under 18, not in pregnancy or breastfeeding, no deficit under a BMI of
   18.5).
2. **The other questions come later, one at a time,** as cards on Today
   ("When do you usually train? Your dinner ideas will fit it"). When an
   answer turns on a strategy, the card shows it with its grade, the answer
   that triggered it, its sources and a switch. The "Your plan" screen goes.
3. **No waiting between steps:** what the answers turn on is computed in the
   background.
4. **Day one is not empty:** the card of the current meal (by time of day)
   shows its top idea inline, "Idea: Chickpea curry · Iron 38 % EU · more
   ideas", dismissible. Only that card, only until the first log.
5. **The onboarding choices become reachable** by keyboard and screen reader
   (today the radio inputs are hidden with `display: none`).

## 5. Logging, faster

The diary is the home, so logging has to cost almost nothing. In "+ Add":

- **Repeat:** "Same as Monday's breakfast" and recent items at the top; one
  tap logs a whole earlier meal.
- **CROUS lunch:** one tap logs "CROUS meal (main + 2 sides)" as an estimate
  (≈), editable; since May 2026 every student can eat it for €1.
- **Portions:** ½, 1, 2 (already there) and several items in one go.
- **Targets:** a repeated meal in 2 taps at most, a new food in 4.

## 6. Progress: food, never the body

Weekly, from what was logged, and always worded "from what you logged",
because logs are never complete.

| What | Shown as |
|---|---|
| Needs met by food | "Food covered 21 of 27 needs this week" |
| Plant variety | "14 different plants this week, 3 new" |
| Cooking | "4 meals cooked, 2 new recipes" |
| Money | "€18.40 for what you cooked, about €1.30 a meal" (cost at the person's shop, or at the national median price when no shop is set; no "saved", there is no honest baseline) |
| Goal nutrients | "Iron: your need reached on 4 days" (reaching a level only; nothing is shown for going over) |

A benefit stated next to a number (for example "why variety?") carries its
evidence grade and sources, like every other health statement in the app.

## 7. The food-week streak

- **Counted in weeks.** A week counts when the person shows up on 3 days
  (adjustable from 1 to 7). Showing up is logging a meal, cooking an idea,
  planning or using the list; never reaching a number.
- **Rest weeks are built in,** not bought: one earned every 4 weeks, at most 2
  kept, used automatically. A missed week pauses; it does not reset.
- **If it ends,** the words are "Longest run: 6 weeks. A new one starts
  whenever you like." Never "you lost".
- The day dots on Today mark days the person showed up, not what they ate.
  The streak can be hidden.

## 8. Milestones

For variety (10, 20, 30 plants in a week), cooking (first recipe, 10 cooked,
5 new), curiosity (opening a "Why?") and budget (a planned week within its
budget). None for logging every meal, none about energy.

## 9. "Your week in food"

Sunday evening: plants and the new ones, recipes cooked, needs covered by food,
what it cost, one highlight with its evidence ("Most of your iron came from
Tuesday's lentils · EU"), and one idea for next week aimed at the nutrient the
logs were lowest in. No grade, no score. It can be shared to a circle as a
card that shows food and cooking only, never calories.

## 10. Notifications

All opt-in, one a day at most, none after 21:00, each one switchable off in one
tap.

| Kind | Example |
|---|---|
| Meal idea, at a chosen time | "Dinner idea: chickpea curry, 20 min, €1.10" |
| Weekly recap ready | "Your week in food is ready" |
| Circle digest, once a day at most | "Léo cooked the lentil curry · 2 reactions" |
| Shopping reminder, before the usual shop day | "Shopping tomorrow? Your list has 6 items" |

**Never sent:** "you haven't logged", "your streak is about to end",
anything chasing a quiet week.

## 11. Circles

- **Who:** 2 to 8 people (flatmates, friends, a team), joined by link or code;
  up to 3 circles a person; opt-in, nobody is found without an invite.
- **Shared:** a circle shopping list; "I cooked this" posts (recipe linked,
  photo optional); reactions from a small fixed set (😋 👏 🙌). No comments in
  the first version.
- **Cook together:** propose a meal on a day, others tap "I'm in", and the
  ingredients go to the circle list scaled to the number of people.
- **One cooperative challenge a week,** from a fixed list: "30 plants
  together", "everyone cooks one new recipe", "5 plant colours each". One
  progress bar for the circle; members are shown as "joined", never with
  amounts or ranks. No challenge about money or amounts eaten.
- **Never shared:** calories, macros, nutrient shares, weight, the diary. A
  circle sees only what a person posts.
- **Control:** report, remove a member, leave (a person's posts leave with
  them), delete the circle. A minimum age for circles (15 is the French age of
  digital consent) is checked in the architecture step.

## 12. AI, within the capped pilot

| Feature | What the model does | What it never does |
|---|---|---|
| **Describe it** to log ("big plate of pasta with tomato sauce and some cheese") | Picks foods and portions from the engine's own search results; the person sees the estimate (≈), edits, confirms | Invent nutrient values: they come from CIQUAL |
| **Ask why** in plain words ("why lentils for focus?") | Rephrases and cites what the engine gives it: the graph path, the EU claim wording, grades, sources; says so when there is no path | Give free-written nutrition advice; answer about a condition, a medication or a symptom (a fixed answer points to a professional) |

- **Without AI, because the engine already does it:** fridge → idea (an
  ingredient picker feeding the planner's `pantry`), adapting a recipe (Swap).
- **Later:** photo logging (photo-only estimates are about a third too low, and
  cost more).
- **Guardrails:** a hard monthly cap and a daily limit per person; answers
  cached; past the cap the app falls back to normal search and nothing breaks;
  no name or profile details sent; AI output labelled as AI.

## 13. Safety: the harm check

The handoff's test, applied to each feature: *would this make someone with a
difficult relationship with food feel worse?*

| Feature | Risk | Design answer |
|---|---|---|
| Energy ring, macro bars | Numbers that fuel restriction | Level to reach, no countdown, no red; calm mode hides them |
| Goal nutrients | Low: it is about reaching a level | Nothing for going over; calm mode uses words |
| Food-week streak | Compulsion to log | Weekly; any action counts; rest weeks; pauses; can be hidden |
| Milestones | Rewarding tracking itself | None for logging completeness or energy |
| Plant count | Becoming a rule to obey | A count, no imposed target, no failure state |
| Money figure | Students skipping food to save money | Cost per meal only; no "spent too much"; the planner never cuts food for budget (decision 11) |
| Weekly recap | Judgement | No grade, no score; a highlight and one idea |
| Notifications | Guilt | Never about inactivity or the streak |
| Circles | Comparison | Nothing about intake or bodies; no ranking; cooperative challenges only; no money challenges |
| Describe it (AI) | An estimate read as exact | ≈, editable, confirmed by the person |
| Ask why (AI) | Free-written advice | Only the engine's evidence; medical questions declined |
| Weight | Weight as the score | Asked for needs only; never charted, never a trend |
| Inline idea on day one | Feeling told what to eat | One card, dismissible, gone after the first log |

**Calm mode** (Profile): hides calories, macros and percentages everywhere; the
ring shows meals logged; nutrients read "reached" or "on its way". Anyone can
turn it on; the app never guesses who needs it. Profile also lists support
services (chosen with the dietitians).

**Words.** Plain and warm; no "should", no "good" or "bad" foods, no "cheat",
"guilt" or "clean".

## 14. Accessibility and languages

- WCAG 2.2 AA: everything reachable by keyboard with a visible focus; rings
  labelled for screen readers ("Iron, 54 % of today's need"); 44 px targets
  (already); reduced motion (already); text usable at 200 %; nothing said by
  colour alone; automated axe-core checks in the screenshot runs.
- French and English for every screen, `lang` set on the page; recipes are
  already bilingual.

## 15. Money

Everything in this document is in the free core and stays there. The
supporter tier, when it comes, adds more AI requests a day and says thank you;
it never takes a feature away from anyone. No ads, no selling data, cancel in
one tap.

## 16. Not now

Photo logging, comments in circles, a public feed or profiles, leaderboards of
any kind, wearables, barcode scanning (a candidate later: Open Food Facts
products are already in the corpus, and the market values it).

## 17. Release order (proposed)

Each release is small, tested (`pytest -q` green) and shown with screenshots.

| # | Release | Contents |
|---|---|---|
| R1 | Faster first day | Accessibility fix, two-screen onboarding, questions as cards, inline idea, repeat and CROUS in "+ Add" |
| R2 | Progress | Weekly progress, day dots, food-week streak, milestones, calm mode |
| R3 | The week | "Your week in food", notifications (needs web push) |
| R4 | Circles | Circles, shared list, cook together, reactions, challenges |
| R5 | AI pilot | Describe it, ask why, with caps and fallbacks |
| Alongside | Recipes | More recipes, reviewed by a dietitian: variety is the first thing a daily user will notice |

## 18. Questions for the next steps

- **UI (step 3):** the screens for progress, recap, circles and the logging
  sheet; food photography or illustration instead of emoji; motion.
- **Architecture (step 4):** the one-document-per-account store will not serve
  weekly queries, circles or notifications; web app structure (the single
  2,500-line file) and a PWA for push; first-party analytics; AI provider,
  EU data processing and cost control; the minimum age for circles.
