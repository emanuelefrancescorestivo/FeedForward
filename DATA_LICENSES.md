# Data and licences

The **code** in this repository is MIT-licensed ([`LICENSE`](LICENSE)). The
**data files** under `backend/feedforward/data/` come from third parties or
are derived from them, and keep those licences. If you reuse a data file,
reuse it under the licence listed here and keep the attribution.

The web app's typeface, `web/fonts/inter-latin-wght-normal.woff2`, is Inter
(© The Inter Project Authors) under the SIL Open Font License 1.1; the licence
is next to it in [`web/fonts/OFL.txt`](backend/feedforward/web/fonts/OFL.txt).

Raw downloads (`data/ingest/cache/`) and the original Open Food Facts crawl
(`data/raw/`) are not in the repository; the importers in `data/ingest/`
rebuild the derived files from the public sources.

| File | Source | Licence | What we did to it |
|---|---|---|---|
| `ciqual_corpus.json` | ANSES-CIQUAL French food composition table, 2020 | [Licence Ouverte / Etalab 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/) (attribution) | Converted to the canonical nutrient ids and units; vitamin A as RAE, omega-3 sums; energy computed with EU 1169/2011 factors where missing (`data/ingest/ciqual.py`) |
| `usda_corpus.json`, `whole_foods.json` | USDA FoodData Central (Foundation Foods, SR Legacy) | Public domain (CC0 1.0) | Selected nutrients, unit conversion (`data/ingest/usda_bulk.py`); `whole_foods.json` values transcribed by hand |
| `foods.json` | Open Food Facts | **ODbL 1.0** (database), DbCL 1.0 (contents) | Normalised units, range-gated micronutrients (`data/ingest/openfoodfacts.py`). **This derived database is released under ODbL 1.0.** |
| `ingredient_prices.json` | Open Prices (Open Food Facts) receipts and price tags; Open Food Facts pack sizes | **ODbL 1.0** | Median €/kg per chain and ingredient, outlier removal, shrinkage, chain price index (`data/ingest/prices.py`). **This derived database is released under ODbL 1.0.** |
| `eu_health_claims.json`, `goal_edges_eu.json` | EU Register of nutrition and health claims (European Commission) | © European Union; reuse authorised with acknowledgement ([Commission Decision 2011/833/EU](https://eur-lex.europa.eu/eli/dec/2011/833/oj)) | Authorised and rejected claims mapped to nutrient → goal edges (`data/ingest/eu_claims.py`) |
| `wikipedia_cache.json` | Wikipedia page summaries (REST API) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) for the text | Stored with each page's URL, which the app shows next to the text. Images are not stored: the app links the Wikimedia Commons thumbnail, whose own licence is on its `image_page` |
| `goal_edges_scraped.json` | Nutrient roles described on Wikipedia | Facts; weights are ours (MIT) | Weights assigned by FeedForward; shown as grade D unless an EU claim confirms them |
| `evidence_pubmed.json` | PubMed (NCBI) search counts and PMIDs | Bibliographic facts (no abstracts stored) | Counts and first PMIDs per query, used to grade evidence |
| `ingredients.json`, `recipes.json`, `interactions.json`, `goal_edges_curated.json`, `portions.json`, `glossary.json`, `benchmark_goals.json`, `eu_claim_rules.json`, `sources.json` | FeedForward | MIT | Written for this project; citations (PMIDs, CIQUAL codes, Open Food Facts tags) point at the sources above. Recipes are drafts, not reviewed by a dietitian |

## Attribution to show in anything built on this data

> Food composition: ANSES-CIQUAL 2020 and USDA FoodData Central.
> Products and prices: Open Food Facts and Open Prices (ODbL).
> Health claims: EU Register of nutrition and health claims, © European Union.
> Descriptions: Wikipedia (CC BY-SA).

The web app shows this in its footer and next to the prices it uses.

## ODbL in practice

If you publish a database made from `foods.json` or `ingredient_prices.json`
(for example, prices for more ingredients), it must also be under ODbL, with
attribution to Open Food Facts / Open Prices. Using those files inside an
application does not change the application's own licence. See the
[ODbL summary](https://opendatacommons.org/licenses/odbl/summary/).
