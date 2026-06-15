# FeedForward — Nutritional Knowledge Graph

**TAOCP2 Final Project — Topic #17 (Web Scraping)**  
PSL University · Bachelor in AI · June 2026  
Emanuele Restivo · Marcos Almodovar

## What it does

FeedForward builds an explainable nutritional recommendation system 
on a weighted knowledge graph. It scrapes two public sources, 
constructs a tripartite graph (Food → Nutrient → Goal), and exposes 
interpretable recommendation paths via graph algorithms.

## Setup

```bash
pip install -r requirements.txt
```

## Reproduce results

```bash
# 1. Scrape products from OpenFoodFacts (cached after first run)
python -m scraper.fetch_category

# 2. Scrape nutrient-goal edges from Wikipedia
python -m scraper.fetch_wiki

# 3. Build graph and show statistics
python -m graph.build_graph

# 4. Run the CLI
python main.py --goal recovery
python main.py --explain "Alvalle Gazpacho l'original" --goal recovery
python main.py --similar "Alvalle Gazpacho l'original"
python main.py --goal iron_support --constraint vegetarian

# 5. ILP vs Greedy comparison
python -c "
from graph.build_graph import load_foods, load_goal_edges, build_graph
from app.meal_optimiser import compare_ilp_vs_greedy
foods = load_foods()
g = build_graph(foods, load_goal_edges())
compare_ilp_vs_greedy(g, foods, 'energy', 400, k=3)
"

# 6. Run tests
pytest tests/ -v

# 7. Benchmarks
python benchmark.py
```

## Graph statistics

| Metric | Value |
|--------|-------|
| Food nodes | 1,809 |
| Nutrient nodes | 21 |
| Goal nodes | 7 |
| Total edges | 15,282 |
| Graph build | ~27 ms |
| Single Dijkstra | 0.47 ms |
| Recommend query | 587 ms |

## Data sources

| Source | Format | Edges |
|--------|--------|-------|
| OpenFoodFacts API v2 | JSON | Food → Nutrient |
| Wikipedia nutrient pages | HTML (BeautifulSoup) | Nutrient → Goal |

## Algorithms

- **Dijkstra** (hand-written, heapq) — shortest path food → goal
- **Yen's k-shortest paths** — top-k explanation paths  
- **Cosine similarity** — nutritionally similar foods
- **Greedy recommender** — constrained recommendation with baseline comparison
- **ILP (PuLP)** — globally optimal meal selection under calorie constraint

## Key design decisions

- **Weight inversion:** Dijkstra minimizes; high nutrient content is good.  
  We invert: `weight = 1 / normalized_amount`.
- **Min-max normalization:** nutrient amounts (0.001g–30g) normalized  
  to 0–1 before inversion for comparable scales.
- **Negative associations:** sodium, saturated fat → heart_health  
  excluded from Dijkstra, surfaced as CLI warnings.
- **Batch scraping:** `/api/v2/search?page_size=100` fetches 100  
  products per call — 50 total calls vs 3,000 individual lookups.

## LLM disclosure

Claude (Anthropic) and one other AI assistant were used as tutors:  
explaining concepts, debugging, library syntax. The algorithmic core  
was written by the team. See §4 of the course briefing.
