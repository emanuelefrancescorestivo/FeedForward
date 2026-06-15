import json
import os

def load_synergies(path="data/synergies.json"):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    synergies = []
    for syn in data.get("synergies", []):
        synergies.append({"a": syn["a"].replace("_", "-"), "b": syn["b"].replace("_", "-"), "effect": syn["effect"]})
    return synergies

# NEW: Added food_name as an argument
def format_path(path, graph, cost, food_name):
    if not path or len(path) < 3:
        return "Invalid path."
        
    food_id, nutrient_id, goal = path[0], path[1], path[-1]
    
    lines = [
        f"Goal: {goal.replace('_', ' ').title()}",
        f"Source Food: {food_name} (ID: {food_id})", # NEW: Using the name!
        f"Optimal Path: {food_name} ➔ {nutrient_id} ➔ {goal}",
        f"Path Cost: {cost:.3f}"
    ]
    
    synergies = load_synergies()
    food_nutrients = [neighbor for neighbor, weight in graph.adj.get(food_id, [])]
    
    synergy_notes = []
    for syn in synergies:
        if nutrient_id == syn["a"] and syn["b"] in food_nutrients:
            synergy_notes.append(f"   Synergy Bonus: Contains {syn['b']} which {syn['effect']}!")
        elif nutrient_id == syn["b"] and syn["a"] in food_nutrients:
            synergy_notes.append(f"   Synergy Bonus: Contains {syn['a']} which {syn['effect']}!")
            
    if synergy_notes:
        lines.append("Synergy Notes:")
        lines.extend(synergy_notes)
        
    return "\n".join(lines)