import json
from graph.feedforward import FeedForwardGraph
from data.schema import Food

def load_foods(path="data/foods.json"):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [Food(**item) for item in raw] #**item = unpacking -> takes a dict. and expands it as argumetns
                                            # this way it creates an object "Food" from "raw"

def load_goal_edges():
    # Scraping from Wikipedia (micronutrients)
    with open("data/goal_edges_scraped.json", "r", encoding="utf-8") as f:
        scraped = json.load(f)["goal_edges"]
    # Curated supplements: macronutrients + negative associations
    with open("data/goal_edges.json", "r", encoding="utf-8") as f:
        curated = json.load(f)["goal_edges"]
    
    seen = {(e["nutrient"], e["goal"]) for e in scraped} # this set of couples nutrient-goal is already covered by scraping, then we add from the curated file only associations that are not there yet
    merged = list(scraped)
    for e in curated:
        if (e["nutrient"], e["goal"]) not in seen:
            merged.append(e)
    return merged

def build_graph(foods, goal_edges):
    g = FeedForwardGraph()

    # find max_value for wach nutrient in the dataset to normalise scales
    max_per_nutrient = {}
    for food in foods:
        for nutrient, amount in food.nutrients.items():
            if nutrient not in max_per_nutrient:
                max_per_nutrient[nutrient] = amount
            else:
                max_per_nutrient[nutrient] = max(max_per_nutrient[nutrient], amount)

    # 1st loop: Food -> Nutrient 
    for food in foods:
        g.add_node(food.id, node_type="food")
        for nutrient, amount in food.nutrients.items():
            g.add_node(nutrient, node_type="nutrient")
            max_val = max_per_nutrient.get(nutrient,1)
            normalised = amount / max_val  #npw between 0 and 1
            weight = 1.0 / normalised if normalised > 0 else 999
            g.add_edge(food.id, nutrient, weight)
    
    #2nd loop: Nutrient -> Goal
    for edge in goal_edges:
        nutrient = edge["nutrient"]
        goal = edge["goal"]
        weight = edge["weight"]
        edge_type = edge.get("type", "positive")
        g.add_node(goal, node_type="goal")

        #here we need to invert for Dijkstra: high weight = short edge = good association nutrient - goal
        if edge_type == "positive":
            g.add_edge(nutrient, goal, 1.0 / weight)
    
    return g

if __name__ == "__main__":
    foods = load_foods()
    goal_edges = load_goal_edges()
    g = build_graph(foods, goal_edges)

    food_nodes = len(foods)
    goal_nodes = len(set(e["goal"] for e in goal_edges))  # iterates on the dictonaries and extracts only the value from goal :) while set removes duplicates and len counts how many unique goals there are :)))
    nutrient_nodes = len(g.adj) - food_nodes - goal_nodes

    print(f"Products (food nodes): {food_nodes}")
    print(f"Nutrients (nutrient nodes): {nutrient_nodes}")
    print(f"Goal nodes: {goal_nodes}")
    print(f"Total Nodes: {len(g.adj)}")
    print(f"Total Edges: {sum(len(v) for v in g.adj.values())}") #for each node, count how many edges stem from it and then sum everything -> .values counts the elements of the adj_list


    #testing dijkstra on a real path
    from graph.algorithms import dijkstra, reconstruct_path

    example = foods[0]
    dist, pred = dijkstra(g, example.id)

    print(f"\nDistances from '{example.name}' to goal:")
    for goal in set(e["goal"] for e in goal_edges):
        if goal in dist and dist[goal] < float('inf'):
            path = reconstruct_path(pred, example.id, goal)
            print(f" {goal}: {dist[goal]:.3f} | path: {' ->'.join(path)}")