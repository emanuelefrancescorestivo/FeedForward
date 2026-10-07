# Release 1, "Faster first day": Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new student reaches an idea for their next meal in two screens, logs a usual meal in two taps, sees real food photos, and their diary is stored as rows the server can read.

**Architecture:** The web app stays one HTML file for this release (the module split of decision 23 opens release 2). The diary moves from the per-account JSON document to `diary_entries` rows behind `/diary/entries`; the engine still computes a day from the entries the app sends, so its code changes only to accept a CROUS preset. Photos are served by the app from `web/photos/` with a credit line. A Playwright harness inside pytest checks the screens.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, SQLite in tests, vanilla JS in `web/index.html`, Playwright (Python) for UI tests.

**Spec:** `docs/PRODUCT_STRATEGY.md` (sections 4, 5, 17 R1), `docs/DESIGN_SYSTEM.md` (sections 2, 3, 6, 8), `DECISIONS.md` (24, 30), `docs/HANDOFF.md` section 4.

## Global Constraints

- The non-negotiables of `docs/HANDOFF.md` section 4 hold for every task; `tests/test_week.py::test_planner_handles_the_input_space` keeps passing.
- `cd backend && python -m pytest -q` is green at the end of every task.
- The energy ring is a level to reach: no "calories left", nothing red, nothing "over".
- Opening the app sends nothing to a third party: photos and fonts are served by the app.
- Words: no "should", no good or bad foods, no "cheat", "guilt" or "clean"; every estimate is marked ≈; a photo is credited "Photo: a similar dish · {author}, {licence}".
- Tokens: light `--ring: #6d965e`; dark `--control: #8a8578`; new pairs light `--gold #7a5a10 / --gold-soft #f4e8cc`, `--rest #6a5d9c / --rest-soft #ebe7f5`; dark `--gold #e6c47c / --gold-soft #3a321d`, `--rest #b9addf / --rest-soft #2e2a3d`.
- Accessibility: every control is a real control reachable by keyboard; focus is `outline: 2px solid var(--accent); outline-offset: 2px`; primary targets 44 px, inline chips at least 32 px.
- Interface copy stays in English in this release (French arrives with the strings files in release 2).
- No new runtime dependency for the API. `playwright` is a test dependency; `Pillow` is used only by `scripts/photos.py`.

## Review Focus

- Accounts whose diary is still in the saved document: moved to rows once at start-up, nothing lost, nothing doubled on the next start (Task 6, `test_old_diaries_move_once`).
- A log that fails to save (offline, server error) must stay visible as "Not saved" with a retry, never vanish or look saved (Task 7, `test_failed_save_is_visible_and_retried`).
- The same entry sent twice (double tap, retry after a timeout) is one row (Task 6, `test_same_entry_twice_is_one_row`).
- After the two-screen first run, Profile still opens the energy, day, food and plan screens (Task 10, `test_profile_still_opens_every_screen`).
- A vegetarian who chose the diet on the goal screen never gets meat as the first idea (Task 12, `test_first_idea_respects_the_diet`).

## Not in this release

The module split, French strings and the time zone column (release 2); axe-core checks (release 2); the service worker, offline queue and push (release 3); the Circle tab (release 4).

---

### Task 1: A Playwright harness inside pytest

**Files:**
- Create: `backend/tests/ui/__init__.py`, `backend/tests/ui/conftest.py`, `backend/tests/ui/test_harness.py`
- Modify: `backend/requirements.txt` (Testing: `playwright>=1.47`; Data ingestion: `Pillow>=10.0`), `.github/workflows/tests.yml` (after installing requirements: `python -m playwright install --with-deps chromium`), `backend/pytest.ini` (create if absent; register marker `ui: drives the web app in a browser`)

**Interfaces:**
- Produces: session fixture `server -> str` (base URL of a uvicorn server on a free port in a thread, same temporary SQLite database as `tests/conftest.py`, engine loaded once); fixture `page` (Chromium page, viewport 390×844, a fresh context per test); helpers in `conftest.py`: `sign_in(page, server: str, name: str) -> None` (test sign-in, waits for the first onboarding screen), `finish_first_run(page, *, goal="Focus", diet="Anything") -> None` (fills About you with 21 / 178 / 70, Male, Moderate, then the goal screen; waits for `.energy-card`), `api(page, path, body=None) -> dict` (fetch with the page's stored token), `snap(page, name: str) -> None` (writes `docs/screenshots/release-1/{name}.png` only when `FF_SCREENSHOTS=1`).
- The whole `tests/ui` package is skipped, with a reason, when Playwright or its Chromium is not installed.

- [ ] **Step 1: Write `test_harness.py::test_app_opens_on_sign_in`**: `page.goto(f"{server}/app")`, assert the text "Eat well, at your pace." is visible.
- [ ] **Step 2: Run it** — `python -m pytest tests/ui -q` — expected: error, fixtures missing.
- [ ] **Step 3: Implement the fixtures and helpers** (uvicorn `Server` with `config.should_exit` set at teardown; wait on `/health`). `finish_first_run` targets the current six-screen flow; Task 10 shortens it.
- [ ] **Step 4: Run** `python -m pytest tests/ui -q` — expected: 1 passed. Then `python -m pytest -q` — expected: all pass.
- [ ] **Step 5: Commit** — `git commit -m "UI tests: a Playwright harness inside pytest"`

### Task 2: Choices reachable by keyboard and screen reader

**Files:**
- Modify: `backend/feedforward/web/index.html` (the `.choice input { display: none; }` rule)
- Test: `backend/tests/ui/test_a11y.py`, `backend/tests/test_web.py`

- [ ] **Step 1: Write the tests**
  - `test_web.py::test_choice_inputs_are_not_removed_from_the_page`: the page source has no rule matching `r"\.choice input\s*\{[^}]*display:\s*none"`.
  - `test_a11y.py::test_onboarding_choices_work_by_keyboard`: after `sign_in`, focus the Weight field, press Tab: the focused element is `input[type=radio][name=sex]`; press ArrowRight: `input[name=sex][value=male]` is checked.
- [ ] **Step 2: Run them** — expected: both fail.
- [ ] **Step 3: Replace the rule** with a visually hidden input: `position: absolute; opacity: 0; width: 1px; height: 1px; margin: 0; pointer-events: none;` and give `.choice label` `position: relative`. The existing `.choice label:has(input:focus-visible)` outline stays.
- [ ] **Step 4: Run** the two tests and the full suite — expected: pass.
- [ ] **Step 5: Commit** — `git commit -m "Onboarding choices reachable by keyboard and screen reader"`

### Task 3: The revised and new colour tokens

**Files:**
- Modify: `backend/feedforward/web/index.html` (`:root`, the dark `@media` block, `:root[data-theme="dark"]`)
- Test: `backend/tests/test_design_tokens.py`

**Interfaces:**
- Consumes: `docs/design/contrast.py` (`THEMES`, `check()`), loaded with `importlib` from the repository root.

- [ ] **Step 1: Write the tests**
  - `test_app_tokens_match_the_checked_palette`: parse `--name: #hex` pairs from the light `:root {` block and from `:root[data-theme="dark"]`; for every key whose `THEMES[theme]` value is a hex string and that the app defines, the values are equal.
  - `test_dark_blocks_agree`: the `@media (prefers-color-scheme: dark)` block and `:root[data-theme="dark"]` define the same variables with the same values.
  - `test_palette_passes_contrast`: `contrast.check() == []`.
- [ ] **Step 2: Run them** — expected: the first fails on `ring` and `control`.
- [ ] **Step 3: Edit the tokens** to the Global Constraints values, and add `--s1`…`--s6` (4, 8, 12, 16, 20, 24 px), `--r-sm: 8px`, `--r-lg: 18px`, `--dur-press: 120ms`, `--dur: 200ms`, `--dur-sheet: 280ms`, `--dur-draw: 800ms`, `--dur-moment: 600ms` in `:root`.
- [ ] **Step 4: Run** the tests and the full suite — expected: pass.
- [ ] **Step 5: Commit** — `git commit -m "Tokens: ring and control pass 3:1; gold, rest, space and motion tokens"`

### Task 4: Line icons instead of emoji

**Files:**
- Modify: `backend/feedforward/web/index.html` (`MAIN_GOALS`, `goalIcon`, `EXTRA_GOAL_ICONS`, `ENERGY_CHOICES`, `LEVER_CHIP`, `iconFor`, `recipeIcon`, the gate's points, the plan-week tile, the "✨ Ideas" button)
- Test: `backend/tests/ui/test_icons.py`

**Interfaces:**
- Produces: `ICONS` (name → inner SVG markup, 24 px grid, 2 px stroke) with the set of `docs/design/screens.html` plus `plate` and `calendar`; `icon(name: string, cls = "") -> string` returning `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">…</svg>`.
- Mapping: goals energy `bolt`, focus `focus`, mood `smile`, sleep `moon`, iron `drop`, immunity `shield`, bones `bone`, heart `heart`, any other goal `plate`; energy choices maintain `calm`, deficit `leafs`, surplus `sprout`; levers about the evening or caffeine `moon`, about training `bolt`, about protein `pot`, any other `plate`; gate points `sprout`, `profile`, `check`; plan-week `calendar`; Ideas button `spark`; any food or recipe without a photo `plate`.

- [ ] **Step 1: Write `test_no_emoji_in_the_interface`**: walk sign-in, every first-run screen, Today, the "+ Add" sheet, the Ideas sheet and Profile; on each, `page.inner_text("body")` has no match for `r"[\U0001F300-\U0001FAFF☀-➿]"`.
- [ ] **Step 2: Run it** — expected: fail on the sign-in page.
- [ ] **Step 3: Add `ICONS` and `icon()`; replace every emoji listed above.** Icons sit in the existing `.tile-ic` / `.ic` boxes, coloured with `currentColor`.
- [ ] **Step 4: Run** the test and the full suite — expected: pass.
- [ ] **Step 5: Commit** — `git commit -m "Line icons instead of emoji"`

### Task 5: Photos in the app, credited

**Files:**
- Create: `backend/feedforward/api/routers/photos.py`
- Modify: `backend/feedforward/api/main.py` (route `/app/photos/{name}`, include the router), `backend/feedforward/data/photos.json` (add `"ingredients"` to food photos), `backend/feedforward/web/index.html`
- Test: `backend/tests/test_photos.py`, `backend/tests/ui/test_photos_ui.py`

**Interfaces:**
- Produces: `GET /photos` → `{"recipes": {recipe_id: Photo}, "foods": {food_id: Photo}}`, `Photo = {"src": "/app/photos/{id}.webp", "thumb": "/app/photos/{id}-sq.webp", "author", "licence", "licence_url", "page"}`; foods are keyed by engine food id `ciqual-{code}` from `data/ingredients.json`. `GET /app/photos/{name}` serves only `{id}.webp` or `{id}-sq.webp` files that exist in `web/photos/`, `image/webp`, `Cache-Control: public, max-age=31536000, immutable`; anything else 404.
- Ledger additions (`"ingredients"` on the photo whose `for` names the food): wholemeal-bread → `wholemeal-bread`; natural-yogurt → `yogurt`; apple → `apple`; snack-banana → `banana`; boiled-eggs → `egg`; white-rice → `rice`; cooked-pasta → `pasta`; milk-glass → `milk`; emmental-cheese → `emmental`; cooked-lentils → `green-lentils`; chickpeas → `chickpeas`; rolled-oats → `oats`; tomatoes → `tomato`; carrots → `carrot`; snack-orange → `orange`.
- Web: `photos` loaded once in `enterApp`; `thumbFor(kind: "recipe"|"food", id: string, name: string) -> string` returns `<img class="ph" src="{thumb}" alt="{name}" width="48" height="48" loading="lazy">` or the `plate` icon tile. Used in meal entries, pick rows, ideas, swap options and shopping-list rows. The recipe sheet shows the 800 × 600 photo above the tabs and, under it, `Photo: a similar dish · <a href="{page}">{author}</a>, {licence}`.

- [ ] **Step 1: Write the tests**
  - `test_every_photo_has_both_files_and_is_small`: for each ledger photo, both files exist and each is under 200 KB.
  - `test_every_recipe_has_a_photo_or_is_listed`: every id in `data/recipes.json` is in some photo's `for` as `recipe:{id}` or in `none`.
  - `test_licences_are_open`: each licence starts with one of `accepted_licences` and does not match `r"\bnc\b|\bnd\b"` (case-insensitive).
  - `test_photos_endpoint`: `"lentil-salad"` in `recipes`; `"ciqual-32140"` (rolled oats) in `foods`; every `src` starts with `/app/photos/`.
  - `test_photo_route_serves_only_photos`: `lentil-salad.webp` → 200, `image/webp`, immutable; `nope.webp`, `..%2Findex.html`, `photos.json`, `lentil-salad.png` → 404.
  - `test_photos_ui.py::test_recipe_sheet_credits_the_photo`: after `finish_first_run`, open Ideas for lunch, open a Recipe: the sheet shows an `img` and the text "Photo: a similar dish" with a link to `commons.wikimedia.org`; during the whole test every request goes to the server's host.
- [ ] **Step 2: Run them** — expected: the endpoint and UI tests fail.
- [ ] **Step 3: Implement** the route, the router, the ledger additions and the web changes.
- [ ] **Step 4: Run** the tests and the full suite — expected: pass. `snap(page, "recipe-sheet")`.
- [ ] **Step 5: Commit** — `git commit -m "Recipe and food photos in the app, each credited"`

### Task 6: The diary as rows (server)

**Files:**
- Create: `backend/feedforward/db/diary_rows.py`, `backend/feedforward/api/routers/entries.py`, `backend/alembic/versions/004_diary_rows.py`
- Modify: `backend/feedforward/db/models.py`, `backend/feedforward/db/repository.py` (`delete_user`, `export_user`), `backend/feedforward/api/main.py` (include the router; call `migrate_state_diaries()` in `lifespan` after `create_all`)
- Test: `backend/tests/test_diary_rows.py`

**Interfaces:**
- `DiaryEntryRow` (`diary_entries`): `id` String(40) primary key; `user_id` FK `users.id` ondelete CASCADE; `day` Date; `meal` String(16); `kind` String(16); `item_id` String(80); `servings` Float = 1.0; `grams` Float = 0.0; `name` String(200) = ""; `kcal` Float = 0.0; `source` String(16) = "manual"; `estimate` Boolean = False; `created_at` DateTime(tz); `deleted_at` DateTime(tz) nullable; index (`user_id`, `day`).
- `ActivityDayRow` (`activity_days`): primary key (`user_id`, `day`, `kind`), `kind` String(16).
- `db/diary_rows.py`: `class IdTaken(ValueError)`; `list_entries(email: str, start: date, end: date) -> list[dict] | None` (None: no such user; deleted entries left out; ordered by day then creation); `add_entries(email: str, entries: list[dict]) -> list[dict] | None` (an id already stored for this person is left as it is; an id stored for another person raises `IdTaken`; records `activity_days(day, "logged")`); `delete_entry(email: str, entry_id: str) -> bool` (sets `deleted_at`); `entries_for_export(email: str) -> list[dict]`; `migrate_state_diaries() -> int` (moves every `user_state.data["diary"]` into rows, using the entry's `uid` as id or `uuid5(NAMESPACE_URL, f"{user_id}/{day}/{index}")`, source `"week"` when `src == "week"`, then deletes the `diary` key; returns the number moved). Entry dicts use the keys of `EntryStored`.
- `api/routers/entries.py`, prefix `/diary/entries`, every route `Depends(require_user)`: `GET ?start=YYYY-MM-DD&end=YYYY-MM-DD` → `{"entries": [...]}` (422 when end < start or more than 92 days); `POST {"entries": [EntryStored, 1..30]}` → `{"entries": [...]}` (409 on `IdTaken`); `DELETE /{entry_id}` → `{"deleted": true}` or 404.
- `EntryStored`: `id` pattern `^[A-Za-z0-9_-]{8,40}$`; `day: date`; `meal` breakfast|lunch|dinner|snack; `kind` recipe|food|preset; `item_id` 1–80 chars; `servings` 0 < x ≤ 10 (default 1); `grams` 0 ≤ x ≤ 3000; `name` ≤ 200; `kcal` 0 ≤ x ≤ 10000; `source` manual|idea|repeat|preset|week|describe (default manual); `estimate: bool = False`.
- Migration 004 creates both tables and the index; its docstring says the data move runs at start-up (`migrate_state_diaries`, idempotent), because tests and local databases use `create_all`.

- [ ] **Step 1: Write the tests** (client fixture as in `tests/test_accounts.py`; two test sign-ins)
  - `test_entries_round_trip`: POST two entries on 2026-10-06 and 2026-10-07, GET 06..07 returns both, DELETE one, GET returns one.
  - `test_same_entry_twice_is_one_row`: POST the same id twice → GET returns one.
  - `test_people_cannot_touch_each_others_entries`: B posting A's id → 409; B deleting it → 404.
  - `test_range_is_inclusive_and_bounded`: entries on the start and end days are returned; a 93-day span → 422; end < start → 422.
  - `test_old_diaries_move_once`: save a state document with `"diary": {"2026-10-05": [two entries]}` via `PUT /me/state`; `migrate_state_diaries()` returns 2; GET returns them; the document no longer has `diary`; a second call returns 0.
  - `test_logging_marks_the_day`: after a POST, `activity_days` has `(day, "logged")` for that person.
  - `test_export_and_delete_cover_entries`: `/auth/export` includes the entries; after `DELETE /auth/me` no `diary_entries` or `activity_days` rows remain for that user id.
- [ ] **Step 2: Run them** — expected: fail (routes missing).
- [ ] **Step 3: Implement** models, migration, `diary_rows.py`, router and the start-up call.
- [ ] **Step 4: Run** the tests and the full suite — expected: pass.
- [ ] **Step 5: Commit** — `git commit -m "The diary as rows: /diary/entries, migration 004, old diaries moved at start-up"`

### Task 7: The app reads and writes entries one at a time

**Files:**
- Modify: `backend/feedforward/web/index.html` (`blankApp`, `entriesOf`, `logEntry`, `unlog`, `recentList`, `renderToday`, the planned-week tick, `enterApp`)
- Test: `backend/tests/ui/test_diary_ui.py`, `backend/tests/test_web.py`

**Interfaces:**
- Consumes: Task 6 routes.
- Produces: `diaryCache: Map<string, Entry[]>`; `loadDays(startISO: string, endISO: string) -> Promise<void>`; `entriesOf(iso) -> Entry[]` (from the cache); `logEntries(meal: string, items: object[], source: string) -> Promise<void>` (ids from `crypto.randomUUID()`, inserted at once with `pending: true`; on success `pending` is cleared; on failure the row shows "Not saved" and a Retry button, `data-retry-entry`); `unlog(id)` (DELETE; on failure the row comes back with a note). Today loads the 14 days before `dayISO` and `dayISO` itself. `diary` leaves `blankApp`.

- [ ] **Step 1: Write the tests**
  - `test_web.py::test_the_saved_document_no_longer_holds_the_diary`: the page source has no `app.diary`.
  - `test_logged_meal_follows_the_account`: log a food at breakfast, open a fresh browser context with the same account: the entry is on Today.
  - `test_failed_save_is_visible_and_retried`: `page.route("**/diary/entries", lambda r: r.abort() if r.request.method == "POST" else r.continue_())`; log a food: its row shows "Not saved"; `page.unroute`; click Retry: "Not saved" disappears and `api(page, "/diary/entries?...")` returns it.
- [ ] **Step 2: Run them** — expected: fail.
- [ ] **Step 3: Implement** the cache and the calls; the planned week's tick uses `logEntries`/`unlog` with source `"week"`.
- [ ] **Step 4: Run** the tests and the full suite — expected: pass.
- [ ] **Step 5: Commit** — `git commit -m "The app saves each log on its own; a failed save stays visible"`

### Task 8: The CROUS meal as an estimated preset

**Files:**
- Create: `backend/feedforward/data/presets.json`, `backend/feedforward/engine/presets.py`
- Modify: `backend/feedforward/engine/diary.py` (`Entry`, `entries_from`, `_entry_nutrients`), `backend/feedforward/api/routers/diary.py` (`EntryIn.kind`, `GET /diary/presets`)
- Test: `backend/tests/test_presets.py`

**Interfaces:**
- `presets.json`: `{"about": ..., "presets": [{"id": "crous-meal", "en": "CROUS meal", "fr": "Repas CROUS", "detail_en": "main + 2 sides", "detail_fr": "plat + 2 périphériques", "price_eur": 1.0, "estimate": true, "note_en": "An estimate of a typical plate: the real one changes every day.", "items": [{"ingredient": "chicken", "g": 100}, {"ingredient": "rice", "g": 180}, {"ingredient": "green-beans", "g": 100}, {"ingredient": "rapeseed-oil", "g": 5}, {"ingredient": "yogurt", "g": 125}, {"ingredient": "apple", "g": 150}]}]}`
- `engine/presets.py`: `@dataclass(frozen=True) class Preset: id, en, fr, detail_en, detail_fr, price_eur: float, estimate: bool, note_en: str, items: tuple[tuple[str, float], ...]`; `load_presets() -> dict[str, Preset]` (cached); `preset_nutrients(rec, preset: Preset) -> dict[str, float]` (each ingredient's CIQUAL food `ciqual-{code}` × grams / 100; `KeyError` for an unknown ingredient or food).
- `Entry.kind` accepts `"preset"` (servings 0 < x ≤ 10); `_entry_nutrients` multiplies `preset_nutrients` by servings.
- `GET /diary/presets` → `[{"kind": "preset", "id", "name", "fr", "detail", "kcal", "estimate": true, "price_eur", "note"}]`.

- [ ] **Step 1: Write the tests**
  - `test_crous_meal_is_a_plausible_estimate`: its energy is between 500 and 850 kcal and `estimate` is true.
  - `test_every_preset_ingredient_has_a_food`: each item's ingredient exists in `ingredients.json` and its `ciqual-{code}` food is in the engine.
  - `test_a_preset_counts_in_the_day`: `day_summary` with one `preset` entry at 1.5 servings has energy within 1 kcal of 1.5 × the preset's.
  - `test_unknown_kinds_are_refused`: `entries_from([{"kind": "presets", ...}])` raises `ValueError`.
  - `test_presets_endpoint`: `GET /diary/presets` lists `crous-meal` with `estimate: true`.
- [ ] **Step 2: Run them** — expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests and the full suite (the week sweep included) — expected: pass.
- [ ] **Step 5: Commit** — `git commit -m "The CROUS meal as a preset, marked as an estimate"`

### Task 9: "+ Add": again, CROUS, several at once

**Files:**
- Modify: `backend/feedforward/web/index.html` (`openLog`, `recentList`, `pickRow`, `pickAmount`)
- Test: `backend/tests/ui/test_add_sheet.py`

**Interfaces:**
- Consumes: `logEntries` (Task 7), `GET /diary/presets` (Task 8), `thumbFor` (Task 5).
- The sheet, top to bottom: search; "Again?" with one row, the most recent earlier day in the cache with entries for this meal: "Same as {Weekday}'s {meal}" listing up to two item names and "+n", one Add logs copies with source `"repeat"`; the CROUS row ("CROUS meal ≈", detail, "≈ {kcal} kcal, an estimate") opening portions ½, 1, 1.5, logged with `kind: "preset"`, `estimate: true`, source `"preset"`; "Recent · tap to select several" where each row has a real checkbox, and selecting any shows a sticky "Add {n} to {meal}" button logging each at its usual amount (food: its portion grams; recipe: 1 portion).

- [ ] **Step 1: Write the tests**
  - `test_repeat_a_meal_in_two_taps`: POST yesterday's breakfast (two foods) with `api`; open "+ Add" for breakfast, click the "Same as" row's Add: Today's breakfast lists both foods. Two clicks in total.
  - `test_crous_lunch_is_an_estimate`: "+ Add" at lunch, CROUS row, 1 portion: lunch shows "CROUS meal" with "≈".
  - `test_add_several_recent_items_at_once`: with three recent foods, tick two, click "Add 2 to dinner": dinner lists those two.
- [ ] **Step 2: Run them** — expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests and the full suite — expected: pass. `snap(page, "add-sheet")`.
- [ ] **Step 5: Commit** — `git commit -m "+ Add: repeat a meal, the CROUS meal, several items at once"`

### Task 10: The first run in two screens

**Files:**
- Modify: `backend/feedforward/web/index.html` (`STEPS` use, `startOnboarding`, `renderOnboarding` for `goal`, `collectStep`, `nextStep`, `finishOnboarding`, a `body.first-run` class)
- Modify: `backend/tests/ui/conftest.py` (`finish_first_run` follows the new flow)
- Test: `backend/tests/ui/test_first_run.py`

**Interfaces:**
- `FIRST_RUN = ["you", "goal"]`: a new account sees only these; the progress bar shows two steps; the goal screen adds a "Diet" row (radio `diet`: Anything, Vegetarian, Vegan) under the tiles; its button says "Start" and calls `finishOnboarding()`. `energy_goal` stays unset (the engine treats it as maintain). Profile's edit mode keeps every screen of `STEPS`. While `body.first-run` is set, the tab bar and the top tabs are hidden.

- [ ] **Step 1: Write the tests**
  - `test_first_run_has_two_screens`: after `sign_in`, fill About you, Next, pick Focus and Vegetarian, Start: `.energy-card` is visible after exactly two submits; "Your energy" was never shown; `/me/state` has `setup.diet == "vegetarian"` and `onboarded` true.
  - `test_tab_bar_hidden_during_first_run`: on About you, `.tabbar` is not visible.
  - `test_profile_still_opens_every_screen`: from Profile, the editors titled "Your energy", "Your day", "Your food" and "Your plan" each open.
- [ ] **Step 2: Run them** — expected: fail.
- [ ] **Step 3: Implement**, and update `finish_first_run`.
- [ ] **Step 4: Run** `tests/ui` and the full suite — expected: pass. `snap(page, "first-run-goal")`.
- [ ] **Step 5: Commit** — `git commit -m "First run in two screens; diet on the goal screen"`

### Task 11: The other questions as cards on Today

**Files:**
- Modify: `backend/feedforward/web/index.html` (`drawToday`, the click handler, `blankApp` gains `asked: []`, `qSnooze: null`, `strategyIds: null`)
- Test: `backend/tests/ui/test_question_cards.py`

**Interfaces:**
- `QUESTION_ORDER = ["cook_time", "training_days", "training_time", "sleep_onset", "study_time", "energy_dips", "morning_hunger", "dont_eat", "batch_ok", "kitchen"]`; `kitchen` asks "Only a microwave and a kettle?" (Yes / No, a hob too) and sets `setup.microwave`.
- `nextQuestion() -> string | null`: the first id not in `app.asked` and not already answered; `training_time` only when `training_days` is set and not `"0"`; null when `app.qSnooze === dayISO`.
- One-line reasons, exactly: cook_time "Ideas will fit the time you have."; training_days and training_time "Ideas will take your training into account."; sleep_onset "Evening ideas will take it into account."; study_time "Ideas will take your study hours into account."; energy_dips "Ideas will take it into account."; morning_hunger "Breakfast ideas will match your appetite."; dont_eat "Ideas will leave these out."; batch_ok "Ideas can cook once for three days."; kitchen "Ideas will only need what you have."
- Footer: "{position} of 10 questions · all optional" and "Not now" (sets `qSnooze = dayISO`).
- After an answer: save; `POST /plan/strategies`; strategies whose ids are not in `app.strategyIds` appear in the card with text, grade, the answer that turned them on, "Why?" with PubMed links, and a checked switch (unchecking adds the id to `app.declined`); then "Next question". `dayView = null` so ideas follow the new answers.

- [ ] **Step 1: Write the tests**
  - `test_one_question_card_at_a_time`: after `finish_first_run`, Today shows "How long can you spend cooking a meal?"; choosing "20 min" then "Next question" shows "How many days a week do you train?".
  - `test_an_answer_shows_what_it_turns_on`: answer through to "Do you take long to fall asleep?" with "Sometimes": the card shows "No caffeine at dinner" with grade "B" and a checked switch; unchecking it puts its id in `/me/state` `declined`.
  - `test_not_now_hides_the_card_for_the_day`: "Not now" removes the card; a reload keeps it hidden.
- [ ] **Step 2: Run them** — expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests and the full suite — expected: pass. `snap(page, "question-card")`.
- [ ] **Step 5: Commit** — `git commit -m "Optional questions arrive one at a time on Today, with what they turn on"`

### Task 12: An idea for the meal of the moment, on day one

**Files:**
- Modify: `backend/feedforward/web/index.html` (`drawToday`, `slotCard`; the "Your day starts empty" card is removed)
- Test: `backend/tests/ui/test_inline_idea.py`, `backend/tests/test_diary.py`

**Interfaces:**
- `currentSlot(d: Date) -> "breakfast" | "lunch" | "dinner"`: minutes since midnight < 630 → breakfast; < 930 → lunch; else dinner.
- Shown in that slot's card when `dayISO` is today, the cache has no entry in the last 14 days, and `!app.inlineIdeaOff`; one `POST /diary/suggest` with `k: 1` and the person's preferences. Markup as `docs/design/screens.html` "Today, day one": photo, "An idea for {meal}", name, time and cost, the first two reasons, "I'll have this" (logs with source `"idea"`), "More ideas" (opens Ideas), and a dismiss button labelled "Hide this idea" (sets `app.inlineIdeaOff`).

- [ ] **Step 1: Write the tests**
  - `test_day_one_shows_an_idea_for_the_current_meal`: `page.clock.set_fixed_time` at 12:30 local before loading; after `finish_first_run`, the Lunch card has "An idea for lunch"; "I'll have this" logs it and the idea is gone.
  - `test_first_idea_respects_the_diet`: with diet Vegetarian on the goal screen, the `/diary/suggest` request body has `"diet": "vegetarian"`.
  - `test_diary.py::test_vegetarian_ideas_have_no_animal_flesh`: `suggest_meal` with `diet="vegetarian"` for each meal, k = 6: no option's recipe in `recipes.json` has an ingredient among chicken, ham, minced-beef, mackerel, salmon, sardines, tuna.
- [ ] **Step 2: Run them** — expected: the UI tests fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests and the full suite — expected: pass. `snap(page, "today-day-one")`.
- [ ] **Step 5: Commit** — `git commit -m "Day one: an idea for the meal of the moment"`

### Task 13: Docs and screenshots for the release

**Files:**
- Modify: `README.md` (the app section: first run, "+ Add", photos, the diary as rows; the screenshot list), `DECISIONS.md` (decisions 24 and 30: "Built in release 1" under *Where*)
- Create: `docs/screenshots/release-1/*.png` (with `FF_SCREENSHOTS=1 python -m pytest tests/ui -q`)

- [ ] **Step 1: Generate the screenshots** — `FF_SCREENSHOTS=1 python -m pytest tests/ui -q` — expected: all pass, five PNGs written.
- [ ] **Step 2: Update the README and DECISIONS** in the documents' own style (plain sentences, numbers with their source).
- [ ] **Step 3: Run the full suite** — `python -m pytest -q` — expected: all pass, the input-space sweep included.
- [ ] **Step 4: Commit** — `git commit -m "Release 1: README, decisions and screenshots"`
