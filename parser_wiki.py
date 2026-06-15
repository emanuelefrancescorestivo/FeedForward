from bs4 import BeautifulSoup

GOAL_KEYWORDS = {
    "immune_support":   ["immune", "immunity", "infection"],
    "iron_support":     ["anemia", "anaemia", "hemoglobin", "red blood"],
    "bone_health":      ["bone", "osteoporosis", "skeletal", "teeth"],
    "energy":           ["energy metabolism", "energy production", "fatigue"],
    "recovery":         ["muscle", "tissue repair", "wound"],
    "heart_health":     ["cardiovascular", "blood pressure", "heart disease"],
    "digestive_health": ["digest", "intestin", "bowel"],
}

def parse_factsheet(html, nutrient):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).lower()

    edges = []
    for goal, keywords in GOAL_KEYWORDS.items():
        count = sum(text.count(k) for k in keywords)
        if count > 0:
            weight = min(0.95, (0.5 + count*0.1))  #how do i transform a count in a weight between 0.5 and 0.95
            edges.append({
                "nutrient": nutrient,
                "goal": goal,
                "weight": weight,
                "source": "wikipedia"
            })
    return edges