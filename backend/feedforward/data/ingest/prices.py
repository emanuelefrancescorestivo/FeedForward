"""
Ingredient prices per supermarket chain in France, from open data.

Sources
  Open Prices (Open Food Facts, ODbL): crowdsourced receipts and shelf photos,
      data/ingest/cache/openprices/prices.parquet (Hugging Face mirror, daily).
  Open Food Facts product data (ODbL): pack size of each barcode, fetched per
      category with the search API and cached in cache/off_categories/.

Method
  packaged   price of a barcode / its pack weight -> EUR per kg, for barcodes
             whose Open Food Facts categories match the ingredient
  loose      Open Prices category prices (fresh produce) per kg, or per unit
             converted with the ingredient's typical unit weight
  per chain  median EUR/kg over the last 30 months, with the count and the
             latest date; prices outside 0.2-80 EUR/kg are discarded as errors
  outliers   observations more than 3x away from the ingredient's national
             median are dropped (mostly wrong pack sizes in product data)
  gaps       a chain without an observed price gets national median x the
             chain's price index (median ratio to the national median over
             the ingredients it does have), marked "estimated"
  few data   a chain with few observations is pulled towards that same
             estimate: (n x chain median + 5 x estimate) / (n + 5)

Chains are identified from the store name in OpenStreetMap. Discounters
(Lidl, Aldi) price nationally, so a Lyon receipt stands for Paris too.

    python -m feedforward.data.ingest.prices
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / "cache"
OUT = DATA / "ingredient_prices.json"
OFF_SEARCH = "https://world.openfoodfacts.org/api/v2/search"

CHAINS = [  # (id, label, regex on the lowercase store name, tier)
    ("lidl", "Lidl", r"^lidl", "discount"),
    ("aldi", "Aldi", r"^aldi", "discount"),
    ("netto", "Netto", r"^netto", "discount"),
    ("leclerc", "E.Leclerc", r"leclerc", "hypermarket"),
    ("auchan", "Auchan", r"auchan", "hypermarket"),
    ("intermarche", "Intermarché", r"intermarch", "supermarket"),
    ("carrefour", "Carrefour", r"^carrefour", "supermarket"),
    ("super-u", "Super U / U Express", r"^(super u|hyper u|u express|marché u)", "supermarket"),
    ("casino", "Casino", r"^casino", "supermarket"),
    ("monoprix", "Monoprix", r"^monop", "city"),
    ("franprix", "Franprix", r"^franprix", "city"),
    ("g20", "G20", r"^g ?20", "city"),
    ("picard", "Picard", r"^picard", "frozen"),
    ("naturalia", "Naturalia", r"^naturalia", "organic"),
    ("biocoop", "Biocoop", r"^biocoop", "organic"),
    ("bio-c-bon", "Bio c' Bon", r"^bio c'? ?bon", "organic"),
    ("la-vie-claire", "La Vie Claire", r"^la vie claire", "organic"),
]
_CHAIN_RE = [(cid, re.compile(rx)) for cid, _l, rx, _t in CHAINS]
MIN_EUR_KG, MAX_EUR_KG = 0.2, 80.0
OUTLIER_FACTOR = 3.0   # drop observations beyond national median x/÷ 3
PRIOR_N = 5            # weight of the estimate against a chain's own observations


def chain_of(display_name: str | None) -> str | None:
    name = (display_name or "").split(",")[0].strip().lower()
    for cid, rx in _CHAIN_RE:
        if rx.search(name):
            return cid
    return None


def _curl_json(url: str) -> dict:  # pragma: no cover - network
    """curl with DNS-over-HTTPS: some networks do not resolve openfoodfacts.org."""
    out = subprocess.run(
        ["curl", "-s", "--max-time", "90", "--doh-url", "https://cloudflare-dns.com/dns-query",
         "-A", "FeedForward/1.0 (nutrition research)", url],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def pack_grams(product: dict, unit_g: float | None = None) -> float | None:
    """Pack weight in grams from Open Food Facts fields (ml counted as g)."""
    qty = product.get("product_quantity")
    unit = (product.get("product_quantity_unit") or "").lower()
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        return None
    if qty <= 0:
        return None
    if unit in ("g", "ml", ""):
        if unit == "" and unit_g and qty <= 60:     # a count (eggs: "12")
            return qty * unit_g
        return qty
    if unit in ("kg", "l"):
        return qty * 1000
    return None


OP_PRODUCTS = "https://prices.openfoodfacts.org/api/v1/products"


def off_category_products(tag: str, *, max_pages: int = 30) -> dict[str, dict]:  # pragma: no cover
    """
    barcode -> {product_quantity, unit, name, labels} for products of an Open
    Food Facts category that have at least one price. Uses the Open Prices
    products endpoint, which mirrors Open Food Facts product data (and is not
    subject to the OFF search API's rate limits). Cached per category.
    """
    folder = CACHE / "off_categories"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (tag.replace(":", "_") + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    products: dict[str, dict] = {}
    for page in range(1, max_pages + 1):
        data = _curl_json(f"{OP_PRODUCTS}?categories_tags__contains={tag}&price_count__gte=1&size=100&page={page}")
        for p in data.get("items", []):
            if p.get("code"):
                products[p["code"]] = {"product_quantity": p.get("product_quantity"),
                                       "product_quantity_unit": p.get("product_quantity_unit"),
                                       "product_name": p.get("product_name"),
                                       "labels": p.get("labels_tags") or []}
        if page >= data.get("pages", 1):
            break
        time.sleep(0.3)
    path.write_text(json.dumps(products, ensure_ascii=False), encoding="utf-8")
    return products


def build(ingredients: list[dict], prices_parquet: Path, *, since: date | None = None) -> dict:
    import pandas as pd
    since = since or (date.today() - timedelta(days=915))
    p = pd.read_parquet(prices_parquet)
    p = p[(p.location_osm_address_country_code == "FR") & (p.currency == "EUR")]
    p = p[p.date >= since]
    p["chain"] = p.location_osm_display_name.map(chain_of)
    p = p[p.chain.notna()]
    p["price"] = p["price"].astype(float)

    observations: dict[str, dict[str, list[tuple[float, str]]]] = {}
    pack_sizes: dict[str, dict[str, list[float]]] = {}
    coverage: dict[str, dict] = {}
    for ing in ingredients:
        obs: dict[str, list[tuple[float, str]]] = {}
        # loose produce, priced by category
        cats = p[(p.type == "CATEGORY") & (p.category_tag.isin(ing.get("fresh", [])))]
        for _, row in cats.iterrows():
            if row.price_per == "KILOGRAM":
                eur_kg = row.price
            elif row.price_per == "UNIT" and ing.get("unit_g"):
                eur_kg = row.price / ing["unit_g"] * 1000
            else:
                continue
            obs.setdefault(row.chain, []).append((eur_kg, str(row.date)))
        # packaged products, priced by barcode and pack size
        packs: dict[str, float] = {}
        for tag in ing.get("off", []):
            for code, prod in off_category_products(tag).items():
                grams = pack_grams(prod, ing.get("unit_g"))
                if grams:
                    packs[code] = grams
        prods = p[(p.type == "PRODUCT") & (p.product_code.isin(packs.keys()))]
        sizes: dict[str, list[float]] = {}
        for _, row in prods.iterrows():
            eur_kg = row.price / packs[row.product_code] * 1000
            if MIN_EUR_KG <= eur_kg <= MAX_EUR_KG:
                sizes.setdefault(row.chain, []).append(packs[row.product_code])
            obs.setdefault(row.chain, []).append((eur_kg, str(row.date)))
        pack_sizes[ing["id"]] = sizes
        for chain in list(obs):
            obs[chain] = [(v, d) for v, d in obs[chain] if MIN_EUR_KG <= v <= MAX_EUR_KG]
            if not obs[chain]:
                del obs[chain]
        observations[ing["id"]] = obs
        coverage[ing["id"]] = {"packs_known": len(packs), "chains": len(obs),
                               "observations": sum(len(v) for v in obs.values())}

    national = {}
    for iid, obs in observations.items():
        allv = [v for vals in obs.values() for v, _d in vals]
        if allv:
            national[iid] = statistics.median(allv)
    for iid, obs in observations.items():
        if iid not in national:
            continue
        lo, hi = national[iid] / OUTLIER_FACTOR, national[iid] * OUTLIER_FACTOR
        for chain in list(obs):
            obs[chain] = [(v, d) for v, d in obs[chain] if lo <= v <= hi]
            if not obs[chain]:
                del obs[chain]
    # chain index: median of (chain median / national median) over shared ingredients
    chain_index = {}
    for cid, label, _rx, tier in CHAINS:
        ratios = [statistics.median(v for v, _ in observations[i][cid]) / national[i]
                  for i in observations if cid in observations[i] and i in national]
        chain_index[cid] = {"label": label, "tier": tier, "index": round(statistics.median(ratios), 3) if len(ratios) >= 5 else None,
                            "ingredients_observed": len(ratios)}
    # tier fallback for chains with too little data: median index of the tier
    for tier in {c[3] for c in CHAINS}:
        known = [c["index"] for c in chain_index.values() if c["tier"] == tier and c["index"]]
        for c in chain_index.values():
            if c["tier"] == tier and c["index"] is None:
                c["index"] = round(statistics.median(known), 3) if known else 1.0
                c["index_source"] = "tier median" if known else "default 1.0 (no data)"
    prices = {}
    for iid, obs in observations.items():
        all_sizes = [g for v in pack_sizes.get(iid, {}).values() for g in v]
        entry = {"national_eur_kg": round(national[iid], 2) if iid in national else None,
                 "pack_g": round(statistics.median(all_sizes)) if all_sizes else None,
                 "by_chain": {}}
        for cid in chain_index:
            if cid in obs:
                vals = obs[cid]
                chain_sizes = pack_sizes.get(iid, {}).get(cid)
                own = statistics.median(v for v, _ in vals)
                prior = national[iid] * chain_index[cid]["index"]
                n = len(vals)
                entry["by_chain"][cid] = {"eur_kg": round((n * own + PRIOR_N * prior) / (n + PRIOR_N), 2),
                                          "observed_eur_kg": round(own, 2),
                                          "n": n, "last": max(d for _, d in vals), "estimated": False,
                                          "pack_g": round(statistics.median(chain_sizes)) if chain_sizes else None}
            elif iid in national:
                entry["by_chain"][cid] = {"eur_kg": round(national[iid] * chain_index[cid]["index"], 2),
                                          "n": 0, "last": None, "estimated": True}
        prices[iid] = entry
    return {
        "provenance": {
            "sources": ["Open Prices (Open Food Facts), ODbL — https://prices.openfoodfacts.org",
                        "Open Food Facts product pack sizes, ODbL — https://world.openfoodfacts.org"],
            "built": date.today().isoformat(), "since": since.isoformat(),
            "method": ("median EUR/kg per chain, outliers beyond 3x the national median dropped, "
                       f"shrunk towards national median x chain index with weight {PRIOR_N}; "
                       "gaps = national median x chain index (estimated)"),
        },
        "chains": chain_index, "coverage": coverage, "prices": prices,
    }


def _cli() -> None:  # pragma: no cover
    ingredients = json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))["ingredients"]
    result = build(ingredients, CACHE / "openprices" / "prices.parquet")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    observed = sum(1 for e in result["prices"].values() for c in e["by_chain"].values() if not c["estimated"])
    print(f"Wrote {OUT}: {len(result['prices'])} ingredients, {observed} observed chain prices")


if __name__ == "__main__":
    _cli()
