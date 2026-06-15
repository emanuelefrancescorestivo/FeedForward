from scraper.crawler import Crawler
from scraper.parser_off import parse_product
import json

def fetch_category(category_tag, max_pages=5, page_size=100):
    crawler = Crawler("FeedForward-Crawler/1.0 (PSL University Project)")
    foods = []
    
    print(f"\n--- Searching category: {category_tag} ---")
    
    for page in range(1, max_pages + 1):
        search_url = (
            f"https://world.openfoodfacts.org/api/v2/search"
            f"?categories_tags={category_tag}"
            f"&page={page}"
            f"&page_size={page_size}"
            f"&fields=code,product_name,nova_group,nutriments,nutriscore_grade,categories"
        )
        
        data = crawler.get(search_url)
        
        if not data:
            print(f"  [Page {page}] Download Error or Blocked.")
            break
            
        raw_products = data.get("products", [])
        print(f"  [Page {page}] Downloaded {len(raw_products)} raw products...")
        
        if not raw_products:
            break # No more products to fetch in this category
            
        # Parse and filter
        valid_count = 0
        for raw in raw_products:
            wrapped = {"product": raw, "code": raw.get("code", "")}
            food = parse_product(wrapped)
            if food:
                foods.append(food)
                valid_count += 1
                
        print(f"  [Page {page}] Kept {valid_count} valid products (Filtered {len(raw_products) - valid_count} items).")

    return foods

if __name__ == "__main__":
    # NEW: Using official OpenFoodFacts English Taxonomy Tags
    # This solves the multi-language problem automatically!
    categories = [
        "en:meats", 
        "en:seafood", 
        "en:dairies", 
        "en:plant-based-foods",
        "en:cereals-and-potatoes", 
        "en:legumes", 
        "en:nuts", 
        "en:seeds",
        "en:fruits-and-vegetables-based-foods",
        "en:eggs"
    ]
    
    all_foods = []
    
    # 5 pages * 100 items = up to 500 raw products fetched per category
    for category in categories:
        foods = fetch_category(category, max_pages=5, page_size=100)
        all_foods.extend(foods)
        print(f"Hitherto Total: {len(all_foods)} valid foods.")
    
    # Remove duplicates (sometimes OFF returns the same barcode on different pages)
    unique_foods = {f.id: f for f in all_foods}.values()
    
    # Save on disk
    output = [
        {
            "id": f.id,
            "name": f.name,
            "category": f.category,
            "nutrients": f.nutrients,
            "nutri_score": f.nutri_score,
            "nova": f.nova
        }
        for f in unique_foods
    ]

    with open("data/foods.json", "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"\n======================================")
    print(f"🎉 Saved {len(output)} UNIQUE products in data/foods.json")
    print(f"======================================")