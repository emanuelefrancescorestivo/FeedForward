# Architecture

See the top-level [README](../README.md) for the layered diagram and rationale.
This note records the load-bearing engineering decisions.

## Layers
1. **Scientific Engine** (`backend/feedforward/engine/`) — pure Python, no web
   or DB dependencies. Builds the graph, models bioavailability, grades
   evidence, runs the algorithms, orchestrates recommendations. Independently
   testable and importable.
2. **API** (`backend/feedforward/api/`) — FastAPI wrapping the engine. Stateless
   request handlers; the engine is built once (lru_cache) and warmed on startup.
3. **Mobile** (`mobile/`) — Expo React Native, talks to the API over HTTPS.
4. **Ontology** (`backend/feedforward/ontology/`) — the shared vocabulary for
   ingest: canonical nutrient ids with INFOODS tagnames, multilingual aliases
   and source codes (`nutrients.json`), unit conversion that refuses to guess
   (`units.py`), and qualified values for "< 0,5" / "traces" cells
   (`values.py`). Importers resolve through it; the engine only sees ids.

## Key decisions
- **Hand-written graph, not NetworkX-backed.** The adjacency list is ours;
  NetworkX is used only for offline analytics (centrality, community detection).
- **cost = -log(strength).** Path strength is the product of edge strengths,
  so Dijkstra's shortest path is exactly the strongest chain and Yen gives the
  next-strongest. Ranking combines all routes (noisy-OR, strongest route in
  full, others at half weight) with per-portion penalties — see
  `engine/scoring.py`. (Until v1.2 the cost was 1 / strength over a dataset-max
  normalisation, which let fortified powders and 100 g of dried herbs win.)
- **Portions, not 100 g.** Delivery is per reference portion
  (`data/portions.json`), compared with the DRI, so rankings do not change when
  a food is added to the corpus.
- **Meal optimisation is a coverage MILP.** Maximise evidence-weighted coverage
  of the goal's nutrients, capped at 100% of need, under a calorie budget with
  one food per group (`engine/meal_optimizer.py`).
- **Reverse-Dijkstra precompute.** One pass per goal on the reversed graph,
  cached at startup, replaces per-food Dijkstra. 587 ms → ~0.7 ms per query.
- **Rule-based bioavailability.** Chosen over a learned model for auditability;
  every adjustment cites a mechanism.
- **Tiered presentation, single engine.** Consumer vs professional differ only
  in what the API serialises (plain labels vs grades + citations), not in the
  computation.

- **Week planner as data + one MILP.** Ingredients (CIQUAL code, Open Food
  Facts / Open Prices tags, storage, unit weight), recipes and per-chain prices
  are JSON files in `data/` rebuilt by `data/ingest/ciqual.py` and
  `data/ingest/prices.py`; `engine/week_planner.py` only reads them. Adding a
  recipe or a shop is a data change, not a code change.
- **Profile data stays on the device.** The "My week" answers live in the
  browser's localStorage; `POST /plan/week` receives them per request and
  stores nothing. No medical conditions are collected.
- **Networks that do not resolve openfoodfacts.org / anses.fr.** Importers
  fetch with curl and DNS-over-HTTPS (`--doh-url`), and cache raw downloads in
  `data/ingest/cache/`, so rebuilds are offline.

## Production hardening
Done: `FEEDFORWARD_ENV=production` refuses to start on SQLite or without a
strong `FEEDFORWARD_SECRET`; CORS origins are configurable
(`FEEDFORWARD_CORS_ORIGINS`). Not done: a shared cache (e.g. Redis) for several
API processes, JWT key rotation, rate limiting. See [APP_STORE.md](APP_STORE.md).
