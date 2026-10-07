# FeedForward: market analysis

*October 2026. Step 1 of the next phase (see [`HANDOFF.md`](HANDOFF.md), section 6).
Desk research plus 9,556 App Store reviews coded by theme; every number has
its source, and the scripts that produced the review figures are in
[`market/`](market/).*

---

## In one page

1. **The category is crowded, and it is angry about money, not about features.**
   In recent written reviews of 13 food apps, 1-2 star reviews mention price,
   paywalls or subscriptions 2.8 times as often as 4-5 star reviews, billing
   and cancellation 17.6 times as often, ads 5.5 times. Lifetime ratings of
   4.6-4.9 hide it: recent written reviews of MyFitnessPal, Yazio, Lifesum,
   Noom and Cal AI average 2.5 to 2.9 stars.
2. **Two gaps opened in 2026.** Mealime, the best-loved simple recipe and
   shopping-list app (4.8 stars, 54,000 US ratings), shuts down on
   21 October 2026 with no export. In France, Jow, the closest thing to
   FeedForward's week planner, now asks for a subscription unless you order
   through a partner supermarket's drive (with €0.99 per order); more than half
   of its recent 1-2 star French reviews are about that. Its partners
   (Carrefour, Auchan, Intermarché, U, Monoprix, Leclerc) do not include the
   hard discounters where, in FeedForward's own price data, a week of food
   costs least (Netto €22, Lidl €25, Aldi €26).
3. **What people praise is what FeedForward already does well:** recipes and
   ideas, the shopping list and budget, ease, motivation and accountability.
   These themes are 1.8 to 3.8 times more frequent in 4-5 star reviews than in
   1-2 star ones.
4. **Engagement mechanics work, and forgiving ones work better.** Duolingo's own
   A/B tests: a "weekend amulet" that lets the streak rest made learners 4 %
   more likely to return a week later and 5 % less likely to lose their
   streak. Gamification in health has a small-to-medium effect that persists
   weakly after the novelty (meta-analysis of 16 RCTs: g = 0.42, then 0.15 at
   follow-up). On Strava, runners who receive kudos run more.
5. **The harm is real but specific.** Calorie tracking is consistently
   *associated* with disordered eating (27 studies), causation is unproven, and
   the features implicated are numbers, weight goals, gamification of intake
   and social comparison. 73 % of patients with an eating disorder who used
   MyFitnessPal said it contributed. FeedForward can be engaging by moving the
   game away from those features, as MacroFactor ("adherence-neutral", 4.84
   stars) shows is commercially viable.
6. **The audience is large and under-served.** 3.01 million students in France
   (2024-25). In 2025, two in three said they skip meals every week, mostly for
   lack of money. Since 4 May 2026 every student can eat a €1 lunch at a CROUS
   restaurant, which changes what a student's day of eating looks like.
7. **Trust can be the growth engine.** Yuka (French, no ads, no brand money,
   pay-what-you-want €10-50 a year) reached 83 million users and 18 million
   monthly actives by April 2026 without paid marketing, and is profitable.

**Recommended position:** *the free, honest food companion for students in
France: ideas and a week of meals that fit your budget at the shop you
actually use, with the science shown and no calorie pressure.*

---

## 1. Method and caveats

- **Desk research** on pricing, business models and retention mechanics
  (sources linked inline and listed at the end). Prices are as published for
  2026 and vary by country and promotion.
- **Review mining.** The 500 most recent written reviews per app and store
  (French and US App Store, Apple's public review feed), 13 apps, pulled on
  6 October 2026: 9,556 reviews, 3,262 at 1-2 stars and 5,334 at 4-5 stars.
  Each review is coded by keyword rules in English and French
  ([`market/reviews_code.py`](market/reviews_code.py)) into 17 themes. The
  number reported is the share of reviews mentioning a theme, and the
  **lift** is that share among 1-2 star reviews divided by the share among
  4-5 star reviews (above 1: a complaint driver; below 1: a praise driver).
- **Caveats.** Written reviews skew negative compared with star-only ratings
  (people write when something changed or broke), so recent means are a
  measure of current anger, not of satisfaction. Keyword coding misses
  irony and counts mentions, not sentiment, within a review. Some apps have
  few French reviews (Cronometer 54, MacroFactor 29, Mealime 4). Reviews
  under-report harm: someone harmed by an app rarely writes a review about it,
  which is why section 5 uses the clinical literature instead.

## 2. The landscape

Four groups, and two engagement references from outside food.

| Group | Apps | What the person does | How they pay |
|---|---|---|---|
| Trackers | MyFitnessPal, Yazio, Lifesum, Cronometer, MacroFactor; AI-first: Cal AI, Foodvisor | Records what they ate, against calorie and macro targets | Freemium with ads, €40-80 a year for premium |
| Coaching | Noom | Follows a psychology-based weight-loss course | Expensive subscription, often prepaid for months |
| Planners and recipes | Mealime (closing), Eat This Much, Jow | Is told what to cook and buy | Freemium; Jow by supermarket commission |
| Food-choice utilities | Yuka, Too Good To Go | Scans a product; buys surplus food | Voluntary subscription; commission per bag |
| Engagement references | Duolingo, Strava | Learns daily; records sport | Freemium |

FeedForward sits between trackers and planners: it can record a day like a
tracker, suggests meals like a planner, and adds what neither has, an
explanation of each suggestion grounded in the EU register of health claims
and prices from the person's own supermarket.

### 2.1 Competitors one by one

Recent stars are the mean of the recent written reviews (section 1), next to
the lifetime App Store rating. "Praised" and "Hated" are the most frequent
themes in that app's 4-5 star and 1-2 star reviews (price and AI are left
out of "Praised": people mention them either way).

| App | Price (2026) | Retention mechanics | Praised (4-5★) | Hated (1-2★) | Stars: lifetime / recent |
|---|---|---|---|---|---|
| **MyFitnessPal** | Free with ads; Premium $79.99/yr or $19.99/mo; Premium+ $99.99/yr [1] | Daily log, streak, community forums, reminders | Weight lost 14 %, easy logging 13 % | Paywall 38 % (barcode scanner moved to Premium in 2022 [2]), AI 17 %, bugs 14 % | 4.71 / 2.66 |
| **Yazio** | Free with ads; Pro $47.90/yr or $6.99/mo [3] | Fasting timer, recipes, streaks | Motivation 10 %, weight lost 9 % | Paywall 33 %, AI 25 %, ads 18 % | 4.70 / 2.50 |
| **Lifesum** | Premium about €49.99/yr, promo-led [3] | Diet plans, "life score" | Easy logging 15 %, recipes 12 % | Paywall 40 %, AI 36 %, bugs 22 % | 4.65 / 2.87 |
| **Cronometer** | Gold $59.99/yr or $10.99/mo [4] | Micronutrient targets, trends | Easy logging 17 %, accurate data 14 %, nutrients 13 % | Paywall 25 %, ads 25 %, bugs 17 % | 4.77 / 3.86 |
| **MacroFactor** | Paid, no ads | Adaptive targets; deliberately no shaming [5] | Weight lost 18 %, easy logging 18 % | Paywall 43 %, AI 18 %, database 16 % | 4.84 / 3.80 |
| **Cal AI** | Paid after trial | Photo logging, streaks | Weight lost 16 % | Paywall 40 %, AI 20 %, billing 14 %; photo estimates under by about 345 kcal a meal [6] | 4.80 / 2.72 |
| **Foodvisor** (FR) | Free tier; €59.99/yr or €11.99/mo [7] | Photo logging, coaching | Weight lost 29 %, motivation 16 % | Paywall 44 %, AI 30 %, billing 27 % | 4.60 / 4.21 |
| **Noom** | High, often prepaid; $62 M settlement over auto-renewal and hard cancellation [8] | Daily lessons, coach, group | Weight lost 34 %, motivation 23 % | Paywall 39 %, billing 23 % | 4.70 / 2.81 |
| **Mealime** | Pro free until shutdown on 21 Oct 2026; no export [9] | Weekly plan, shopping list | Recipes 71 %, shopping list 45 % | Recent: the shutdown; before: the Pro paywall | 4.81 / 4.18 |
| **Eat This Much** | $5/mo yearly or $9 monthly [10] | Automatic plan to a calorie target | Recipes 50 %, shopping list 21 % | Recipe variety 34 %, paywall 32 %, billing 18 % | 4.72 / 3.63 |
| **Jow** (FR) | Free if you order through a partner drive (+€0.99 an order); subscription for recipes only [11] | Weekly menu → supermarket basket | Recipes 63 %, shopping list 43 % | Became paid: 129 of 239 recent French 1-2★ reviews (54 %); drive logins broken: 47 (20 %) | 4.67 / 3.22 |
| **Yuka** (FR) | Free; voluntary €10-50/yr; no ads, no brand money [12] | Scan at the shop | Help at the shop 11 %, scanning 9 % | Barcode scanning 17 % | 4.82 / 4.28 |
| **Too Good To Go** | Free; pay per bag | Impact counters (meals, money, CO2 saved), favourites | Saving food 14 %, saving money 12 % | Billing and refunds 17 %, price 17 % | 4.93 / 4.36 |

Two things stand out:

- **Anger tracks monetisation behaviour, not price.** Yuka and Too Good To Go
  charge money and are loved; MyFitnessPal and Jow made something free paid,
  and Noom made cancelling hard. Taking back a free feature is the most
  damaging move visible in these reviews.
- **AI is now a complaint driver** (1.8 times more frequent in 1-2 star
  reviews), for two reasons visible in the reviews: estimates that are wrong
  and presented as right, and AI used as the reason to raise prices. An
  NIH-affiliated test of four photo-logging apps on 102 controlled meals found
  energy under-estimated by about a third [6].

### 2.2 The engagement references

**Duolingo.** The streak is the core mechanic, and the company's own tests
favour forgiveness: the weekend amulet (rest on weekends without losing the
streak) made learners 4 % more likely to return a week later and 5 % less
likely to lose their streak; a streak wager raised day-7 retention by 14 %.
Duolingo also reports that learners who binge are *more* likely to quit than
those who pace themselves [13]. Q2 2026: 58.7 million daily actives.

**Strava.** Social proof without comparison of bodies: kudos, clubs, group
challenges, a yearly "Year in Sport" recap. In a study of 329 runners in five
virtual clubs, runners who received kudos ran more and more often [14].
Its competitive side (segment leaderboards) is the part FeedForward must not
copy: in food, a ranking is a ranking of intake.

## 3. What reviews praise and hate

Share of reviews mentioning each theme (all 13 apps pooled):

| Theme | All | 1-2★ | 4-5★ | Lift |
|---|---:|---:|---:|---:|
| Billing, cancelling, refunds | 3.8 % | 9.6 % | 0.5 % | **17.6** |
| Ads | 3.9 % | 7.7 % | 1.4 % | **5.5** |
| Bugs, sync, crashes | 8.6 % | 13.7 % | 3.8 % | **3.6** |
| Notifications | 1.4 % | 2.1 % | 0.7 % | 2.9 |
| Price, paywall, subscription | 22.1 % | 36.5 % | 12.8 % | **2.8** |
| Database accuracy | 5.7 % | 7.6 % | 4.0 % | 1.9 |
| AI and photos | 15.4 % | 20.6 % | 11.5 % | 1.8 |
| Recipes, ideas, variety | 14.1 % | 9.3 % | 16.5 % | 0.6 |
| Community, friends, sharing | 5.3 % | 4.4 % | 5.7 % | 0.8 |
| Streaks, motivation, habit | 4.7 % | 3.0 % | 6.0 % | 0.5 |
| Health, nutrients, science | 2.8 % | 1.8 % | 3.4 % | 0.5 |
| Shopping list, groceries, budget | 7.9 % | 3.5 % | 11.2 % | **0.3** |
| Ease and speed of logging | 7.6 % | 2.9 % | 11.0 % | **0.3** |
| Weight lost | 6.9 % | 2.5 % | 10.3 % | 0.2 |

Reading it for FeedForward:

- **Never earn a 1-star review on money.** No ads, no dark patterns, cancel in
  one tap, and never move a free feature behind a paywall. These are cheap to
  promise now and very expensive to recover from later.
- **Reliability is a feature.** Bugs and sync failures are the third complaint
  driver; Jow's broken drive logins are a fifth of its anger. FeedForward's
  test discipline (297 tests, the input-space sweep) is a competitive asset to
  keep as features grow.
- **The praise drivers match FeedForward's strengths:** ideas and recipes,
  the shopping list and budget, motivation. Science and nutrients are praised
  by a small, loyal group (Cronometer's users), not by most people: the
  evidence should be one tap away, never in the way.
- **Variety is the risk.** "Recipe variety" is Eat This Much's top complaint
  (34 % of its 1-2 star reviews). FeedForward has 52 recipes; users of a daily
  app will see repeats within a week.
- **Weight loss is the praise driver FeedForward chooses not to compete on.**
  Trackers' happiest users are people who lost weight. FeedForward's happiest
  users will have to be people who eat well for less, cook more, and feel the
  difference in energy and focus. That has to be made visible (section 6).

## 4. Retention: the numbers to beat

- **Benchmarks.** Health and fitness apps keep roughly 3 to 8 % of new users at
  day 30, depending on the source; above 8 % is top quartile [15].
- **Mechanics that move it,** with the version that fits a food app:

| Mechanic | Evidence | Risk in a food app | FeedForward version |
|---|---|---|---|
| Streak | Duolingo: core of daily return [13] | Daily logging streaks reward tracking every bite | Weekly rhythm; counts logging *or* cooking *or* planning; rest days built in; a pause, never a reset |
| Forgiveness (freeze, amulet) | +4 % return a week later, −5 % streak loss [13] | None | Default, not a purchase |
| Points and badges | Small-to-medium effect, weaker after novelty [16] | Badges for "under target" | Milestones for variety, cooking, money saved, needs covered by food |
| Social affirmation | Kudos → more running [14] | Comparison of intake or bodies | Reactions on cooked meals and shared recipes, small private circles |
| Cooperative challenges | Strava clubs, group goals | Competitive intake leaderboards | "5 plant colours this week" for a circle, everyone counts toward one goal |
| Impact counters | Too Good To Go (meals, money, CO2) | None if not about the body | Money saved against budget, meals cooked, new recipes, plants eaten |
| Recaps | Strava Year in Sport, Spotify Wrapped | Body or calorie recaps | Weekly "your week in food": variety, nutrients covered, cooking, spending |

## 5. The harm to design around

- **Levinson et al., 2017**, 105 patients with an eating disorder: 75 % had
  used MyFitnessPal, and 73 % of those said it had at least partly contributed
  to their eating disorder; the endorsement was related to dietary restraint
  [17].
- **Moody et al., 2025**, systematic review of 27 studies (N = 10,584, mostly
  young women and students): fitness and diet tracking is consistently
  associated with disordered eating, restraint and excessive exercise in
  cross-sectional studies; experimental studies found no effect, so the
  direction is unknown. Features implicated: calorie counting and "the
  numbers", gamification and goal setting, weight and shape motives, high
  frequency of use, social comparison; users find ways around safety features
  [18].
- **The audience matters.** The review's populations are FeedForward's: young
  people and students.

What this means as design rules (they will be checked in step 2):

1. Nothing counts down. No "calories left", no red, no "over".
2. No streak, badge, challenge or ranking on energy, weight, or eating less.
3. Frequency is not a goal: the rhythm is weekly, and a quiet week is fine.
4. Social shows food and cooking, never intake, bodies or comparisons.
5. A visible, kind way out: hide numbers entirely, and a link to French help
   services in Profile (which ones to list: a question for the dietitians).

## 6. The French context

- **Students:** 3,012,800 enrolled in higher education in 2024-25, the first
  year above 3 million [19].
- **Food insecurity:** in the FAGE barometer of February 2025, two students in
  three skipped meals every week, mostly for lack of money [20]; the Cop1
  barometer reports similar figures.
- **The €1 lunch:** since 4 May 2026, every student with a card can eat a main
  course and up to two sides at a CROUS restaurant for €1 [21]. For many
  students lunch is no longer cooked at home; a useful app must make "CROUS
  lunch" one tap to log and plan the other meals around it.
- **Shops:** hard discounters are where a budget goes furthest (FeedForward's
  own minimum-budget figure: Netto €22, Lidl €25, Aldi €26 a week against
  Naturalia €50 and Biocoop €53), and they are in-store shops, which Jow's
  drive model does not serve.
- **Proof of appetite:** Yuka, a French app about food transparency, reached
  83 million users and 18 million monthly actives without ads or paid
  marketing [12]. French users adopt health apps that are independent and
  explain themselves, and some pay voluntarily.

## 7. Positioning

Two questions place every app: does it **suggest** what to eat or only
**record** it, and does it lead with **numbers** or with **meaning** (why,
what it costs, what it does for you)?

|  | Leads with numbers | Leads with meaning |
|---|---|---|
| **Records** | MyFitnessPal, Yazio, Lifesum, Cronometer, Cal AI, Foodvisor | Yuka (per product) |
| **Suggests** | Eat This Much (to a calorie target), Noom | Mealime (closing), Jow (drive only), **FeedForward** |

**Positioning statement.** For students in France who eat on a tight budget,
FeedForward is the food companion that turns the shop they already use into
meals that cover their needs, and shows the science behind each one. Unlike
calorie counters, it never counts down or judges; unlike Jow, it works at the
hard discounters, in the shop, for free.

**The gap it fills,** in order of how much users will feel it:

1. **Budget at the shop students use,** priced from real receipts, with the
   honest "this week needs at least €X" instead of planning less food.
2. **Ideas for the next meal from what was already eaten today,** with the
   reason ("Iron 47 %"), not a plan imposed for the week.
3. **Explanations with evidence:** EU-authorised claims and graded
   literature, the one thing no competitor shows.
4. **Calm by design:** no counting down, no shame, no weight goal, as a
   stated feature for people tired of calorie apps.
5. **Honest money:** a free core that stays free, no ads, no dark patterns.

## 8. Who it is for

**Primary: students in France, 18 to 26,** spending €25-60 a week on food,
cooking in a small kitchen (sometimes only a microwave), who care about
energy, focus, sleep or training more than about weight. Three sketches:

- **The budget cook.** First or second year, studio flat, two hot plates,
  shops at Lidl, eats the €1 CROUS lunch on weekdays. Needs: cheap dinners
  that are not pasta again, a list that fits €35, and to know the week is
  "enough".
- **The student-athlete.** Trains four or five times a week, needs 3,000 to
  4,000 kcal, eats a lot and cheaply. Needs: bigger portions, protein
  without supplements marketing, meals around training. (The owner's own
  starting point, and an under-served group: athlete apps assume a large
  budget.)
- **The international student.** New to French shops and products, more at
  ease in English, wants familiar meals from local ingredients.

**Secondary, later:** young workers and flatmates with the same budget
problem; Italy and other countries once composition and price data exist
(CREA, Open Prices coverage).

**Not for:** people seeking a large calorie deficit (the app offers at most
−15 %, by design), and people in treatment for an eating disorder, for whom
the app must be safe but should not present itself as help.

## 9. What this means for the next step

**FeedForward today, against this market** (a new-user walkthrough on a phone,
6 October 2026, branch `dashboard-ui-oyyga4`):

- *Ahead:* ideas with their reasons ("Iron 47 % · EU"), the goal card
  ("Focus today", with the meal each nutrient came from), strategies shown
  with their grade and the answer that turned them on, the budgeted week, no
  ads, nothing red. No competitor shows its evidence like this.
- *Behind:* six onboarding screens (three skippable) with a pause between
  steps before anything useful; an empty Today on first arrival; logging is
  search → amount → add for every item; nothing to come back for tomorrow
  (no history, progress, recap, reminder or other person); 52 recipes; emoji
  instead of food pictures; the choice chips in onboarding cannot be reached
  by keyboard or screen reader (hidden radio inputs), a WCAG failure on the
  first screen.

These go into the product and UX strategy (step 2):

1. **Lead with the value, not the work.** The first minute should end on an
   idea for the next meal, not on an empty diary.
2. **Make logging nearly free:** repeat a meal, "CROUS lunch" in one tap,
   cook-and-log from an idea; photo logging later, shown as an estimate and
   easy to correct.
3. **Progress on food, not on the body:** needs covered by food, plant
   variety and colours, meals cooked, new recipes, money kept within budget.
4. **A weekly, forgiving rhythm** by default, with rest built in.
5. **Social in small circles:** flatmates and friends, shared lists and
   recipes, cooperative challenges, reactions on cooked meals; private by
   default, no public feed.
6. **AI that is grounded and humble:** it describes what the engine computed,
   shows estimates as estimates, cites its sources, and is never the reason
   for a price rise.
7. **Trust as the growth engine:** the Yuka model rather than the
   MyFitnessPal one.
8. **More recipes** before or with any retention feature: repeats will be the
   first thing a daily user notices.

## 10. Open questions for the owner

These change what is built; each has a recommendation from the evidence above.

| Question | Recommendation | Why |
|---|---|---|
| Market and language | France first, interface in French and English | Data (CIQUAL, French chains) is French; 3 M students; international students need English; recipes are already bilingual |
| Free or paid | Free core forever, no ads; an optional low-price supporter tier later, covering costly AI use | Paywalls and billing are the top complaint drivers; Yuka shows voluntary payment works in France |
| How social | Small private circles (flatmates, friends), cooperative, opt-in | Kudos and clubs help; comparison is the harm |
| AI budget | Start small: AI only where it saves real effort (describe a meal to log it, ask "why?"), with a monthly cap | AI anger in reviews comes from wrong estimates and price rises; costs grow with users |

---

## Sources

1. [MyFitnessPal cost 2026](https://www.fitbudd.com/post/myfitnesspal-app-cost)
2. [MyFitnessPal barcode paywall](https://www.pocket-lint.com/apps/news/162386-wow-myfitnesspal-put-its-popular-barcode-scanner-feature-behind-a-paywall/)
3. [Yazio vs Lifesum 2026](https://calorierankings.com/compare/yazio-vs-lifesum/)
4. [Cronometer review 2026](https://www.garagegymreviews.com/cronometer-review)
5. [MacroFactor: adherence neutral](https://macrofactor.com/adherence-neutral/)
6. [AI photo calorie tools underestimate by 33% (NUTRITION 2026 abstract)](https://www.healio.com/news/primary-care/20260804/ai-photobased-calorietracking-tools-underestimate-them-by-33)
7. [Foodvisor 2026](https://kalivia.fr/applications/nutrition/foodvisor/)
8. [Noom $62M settlement](https://www.newsweek.com/noom-pay-62m-customers-forced-renewals-they-didnt-want-1679045)
9. [Mealime on the App Store (shutdown notice)](https://apps.apple.com/us/app/mealime-meal-plans-recipes/id1079999103)
10. [Eat This Much review 2026](https://www.promealplan.com/en/blog/eat-this-much-review-2026)
11. [Jow terms of use](https://jow.fr/pages/misc/conditions-generales-dutilisation)
12. [Yuka: 83 million users](https://www.mind.eu.com/retail/article/avec-83-millions-yuka-simpose-comme-standard-de-la-transparence-produit/)
13. [Duolingo: how streaks keep learners committed](https://blog.duolingo.com/how-streaks-keep-duolingo-learners-committed-to-their-language-goals/)
14. [Kudos make you run! (Social Networks)](https://www.sciencedirect.com/science/article/pii/S0378873322000909)
15. [Mobile app retention benchmarks 2026](https://uxcam.com/blog/mobile-app-retention-benchmarks/)
16. [Mazéas et al. 2022, gamification and physical activity, JMIR](https://www.jmir.org/2022/1/e26779/PDF)
17. [Levinson et al. 2017, MyFitnessPal in eating disorders, Eating Behaviors](https://www.sciencedirect.com/science/article/abs/pii/S1471015317301484)
18. [Moody et al. 2025, systematic review, European Eating Disorders Review](https://pmc.ncbi.nlm.nih.gov/articles/PMC12547374/)
19. [SIES Note Flash 17, July 2025](https://www.enseignementsup-recherche.gouv.fr/sites/default/files/2025-07/nf-sies-2025-17-37563.pdf)
20. [FAGE barometer 2025](https://www.letudiant.fr/lifestyle/aides-financieres/barometre-de-la-fage-sur-la-precarite-2-etudiants-sur-3-sautent-des-repas-toutes-les-semaines.html)
21. [€1 CROUS meal for all students](https://www.etudiant.gouv.fr/fr/comment-beneficier-du-repas-crous-1-eu-3123)

Further reading used: [Jow on Wikipedia (FR)](https://fr.wikipedia.org/wiki/Jow.fr) (9 million users, 5,000 recipes, partner chains);
[Duolingo user statistics 2026](https://okara.ai/blog/how-duolingo-grew); [Mealime shutdown details](https://mealthinker.com/blog/mealime-alternative).
