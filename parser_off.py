from data.schema import Food


# nutrients we care about for our graph:
NUTRIENT_TARGET = [
    "proteins", "fat", "carbohydrates", "fiber",
    "sugars", "salt", "energy-kcal",
    "iron", "vitamin-c", "vitamin-e", "vitamin-a", "vitamin-k",
    "calcium", "magnesium", "zinc", "phosphorus",
    "omega-3-fat", "saturated-fat", "sodium", "manganese"
]

def parse_product(raw_json):
    p = raw_json.get("product", {})

    # 1st filter: NOVA 4 = we dont want ultra-processed food
    nova = p.get("nova_group") or p.get("nutriments", {}).get("nova-group")
    if nova is nova == 4:
        return None
    
    # 2nd filter: missing name = we dont want that shi
    name = p.get("product_name", "").strip()  #removes spaces between start and end
    if not name:
        return None
    
    # extract nutrients for _100g:
    nutriments = p.get("nutriments", {})
    nutrients = {}
    for n in NUTRIENT_TARGET:
        value = nutriments.get(f"{n}_100g")
        if value is not None and value > 0:
            nutrients[n] = value

    # 3rd filter: we dont want foods that have missing information
    if len(nutrients) < 2:
        return None
    
    return Food(
        id=raw_json.get("code","unknown"),
        name=name,
        category=p.get("categories", "unknown"),
        nutrients=nutrients,
        nutri_score=p.get("nutriscore_grade", "?"),
        nova=nova or 0
    )