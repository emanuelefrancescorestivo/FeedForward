# FeedForward — Nutritional Knowledge Graph

TAOCP2 final project (Topic #17: Web Scraping)  
PSL University — Bachelor in AI | June 2026

## What it does

FeedForward builds an explainable nutritional knowledge graph from publicly
available food and nutrient data. It scrapes two sources (OpenFoodFacts JSON
API + Wikipedia HTML), constructs a weighted tripartite graph linking foods,
nutrients, and health goals, and exposes interpretable recommendation paths
through Dijkstra's shortest-path algorithm.

## Setup

```bash
pip install -r requirements.txt
```

## Reproduce results

```bash
# Step 1 — scrape products from OpenFoodFacts (cached after first run)
python -m scraper.fetch_category

# Step 2 — scrape nutrient-goal edges from Wikipedia (cached after first run)
python -m scraper.fetch_wiki

# Step 3 — build graph and show statistics
python -m graph.build_graph

# Step 4 — query the graph
python main.py --goal recovery
python main.py --explain "Joly Thon Entier" --goal energy
python main.py --similar "Joly Thon Entier"
python main.py --goal iron_support --constraint vegetarian
```

## Project layout

- `scraper/` — polite crawler (rate limiting, robots.txt, cache, retry), parsers for JSON and HTML
- `data/` — cached raw data, food database, goal edges (scraped + curated)
- `graph/` — adjacency-list graph structure, hand-written Dijkstra, cosine similarity
- `app/` — query engine, greedy recommender with random baseline comparison
- `tests/` — unit tests for graph and Dijkstra

## Data sources

| Source | Format | Edges produced |
|--------|--------|----------------|
| OpenFoodFacts API v2 | JSON | Food → Nutrient (205 products, 7 categories) |
| Wikipedia nutrient pages | HTML (BeautifulSoup) | Nutrient → Goal (9 pages, 49 edges) |

## Graph statistics

- 230 nodes (205 food + 18 nutrient + 7 goal)
- 1695 edges
- Dijkstra query: 0.09 ms
- Full recommend query: 11.7 ms

## Key design decisions

- **Weight inversion**: Dijkstra minimises, but high nutrient content is good. We invert: `weight = 1/normalised_amount`, so nutrient-rich foods have shorter paths.
- **Min-max normalisation**: nutrient amounts (0.001g–30g) normalised to 0–1 before inversion, making scales comparable across nutrients.
- **Negative associations**: sodium and saturated fat are excluded from Dijkstra via an `edge_type` field; surfaced as warnings instead.

## Running tests

```bash
pytest tests/ -v
```

## LLM disclosure

Claude (Anthropic) was used as a tutor throughout the project: explaining concepts, reviewing code, debugging, and providing library syntax. The algorithmic core (graph structure, Dijkstra, cosine similarity, recommender) was written by the team. The crawler policies (rate limiting, retry, caching strategy) were designed by the team.