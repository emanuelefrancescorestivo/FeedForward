from graph.algorithms import dijkstra, reconstruct_path, k_shortest_paths
from app.evidence_formatter import format_path
"""
app/query_engine.py
-------------------
Glue between the CLI and graph/algorithms. Translates a user query into calls
on your graph + Dijkstra and returns structured results.
"""


def foods_for_goal(graph, goal, top_k=10):
    """find the best foods for a specific goal. instead of running dijkstra
    with complexity O(V*(V+E)logV) for every single food node
    we leverage the Food->Nutrient->Goal topology
    """
    #1. Find all nutrients that connect directly to the target goal
    nutrients_for_goal = {}
    for node, edges, in graph.adj.items():
        for neighbour, weight in edges:
            if neighbour == goal:
                nutrients_for_goal[node] = weight #node is the nutrient remember
    
    if not nutrients_for_goal:
        return f"No known nutrients support the goal: '{goal}'."
    
    #2. Find all foods that contain those nutrients and calculate the combined path cost
    food_scores = []
    for node, edges in graph.adj.items():
        # only foods point to nutrients.
        #we compute the minimum cost (Food -> Nutrient -> Goal) for this specific node.
        best_cost = float('inf')
        for neighbour, weight in edges:
            if neighbour in nutrients_for_goal:
                cost = weight + nutrients_for_goal[neighbour]
                if cost < best_cost:
                    best_cost = cost
        
        #if we found a valid path to the goal, save the food and its score
        if best_cost < float('inf'):
            food_scores.append((node, best_cost))

    #3. Sort by the lowest cost (shorter distance means highest nutrient-to-goal association)
    food_scores.sort(key=lambda x: x[1])

    # Return the top_k results formatted nicely 
    results = [f"Top {top_k} foods for '{goal}':"]
    for rank, (food_id, score) in enumerate(food_scores[:top_k], 1):
        results.append(f"{rank}. {food_id} (Path Cost: {score:.3f})")
    
    return "\n".join(results)

def explain(graph, food, goal, k=3):
    # Pass food.id to the algorithm
    paths = k_shortest_paths(graph, food.id, goal, k)
    
    if not paths:
        return f"No continuous path found from '{food.name}' to '{goal}'."
        
    results = [f"Top {len(paths)} explanation paths from '{food.name}' to '{goal}':", "-"*55]
    
    for rank, (cost, path) in enumerate(paths, 1):
        results.append(f"\n--- Path {rank} ---")
        # Pass food.name to the formatter!
        results.append(format_path(path, graph, cost, food.name))
        
    return "\n".join(results)