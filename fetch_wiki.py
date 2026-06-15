import json
from scraper.crawler import Crawler
from scraper.parser_wiki import parse_factsheet

WIKI_PAGES = {
    "iron":      "https://en.wikipedia.org/wiki/Iron",
    "zinc":      "https://en.wikipedia.org/wiki/Zinc",
    "calcium":   "https://en.wikipedia.org/wiki/Calcium",
    "magnesium": "https://en.wikipedia.org/wiki/Magnesium",
    "vitamin-c": "https://en.wikipedia.org/wiki/Vitamin_C",
    "vitamin-d": "https://en.wikipedia.org/wiki/Vitamin_D",
    "vitamin-e": "https://en.wikipedia.org/wiki/Vitamin_E",
    "vitamin-a": "https://en.wikipedia.org/wiki/Vitamin_A",
    "vitamin-k": "https://en.wikipedia.org/wiki/Vitamin_K",
}

if __name__ == "__main__":
    crawler = Crawler("FeedForward-Crawler/1.0 (PSL University project)")
    all_edges = []
    for nutrient, url in WIKI_PAGES.items():
        html = crawler.get_html(url)
        if not html:
            print(f"{nutrient}: error")
            continue
        edges = parse_factsheet(html, nutrient)
        all_edges.extend(edges)
        print(f"{nutrient}: {len(edges)} edges")
    
    with open("data/goal_edges_scraped.json", "w", encoding="utf-8") as f:
        json.dump({"goal_edges": all_edges}, f, ensure_ascii=False, indent=2)
    
    print(f"\nTotal: {len(all_edges)} edges nutrient->goal saved in data/goal_edges_scraped.json")