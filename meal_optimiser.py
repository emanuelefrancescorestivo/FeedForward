"""
app/meal_optimizer.py
---------------------
Integer Linear Programming (ILP) using PuLP. 
Compares a greedy heuristic against a mathematically optimal global solution.
"""
import pulp
from graph.algorithms import dijkstra

def optimal_recommend_ilp(graph, foods, goal, max_calories, k=3):
    """
    Finds exactly K foods that minimize distance to the goal, 
    but strictly ensures their combined calories are under max_calories.
    """
    # 1. Precompute Dijkstra distances to the goal
    valid_foods = []
    for f in foods:
        dist, _ = dijkstra(graph, f.id)
        if goal in dist and dist[goal] < float('inf'):
            kcal = f.nutrients.get("energy-kcal", 0)
            if kcal > 0: # Only include foods with known calories
                valid_foods.append((f, dist[goal], kcal))

    if not valid_foods:
        return None

    # 2. Define the Optimization Problem
    prob = pulp.LpProblem("Optimal_Meal_Selection", pulp.LpMinimize)

    # 3. Define Variables: x_i is a binary variable (1 if food i is chosen, 0 otherwise)
    x = pulp.LpVariable.dicts("food", range(len(valid_foods)), cat='Binary')

    # 4. Objective Function: Minimize total path cost
    prob += pulp.lpSum([x[i] * valid_foods[i][1] for i in range(len(valid_foods))]), "Total_Cost"

    # 5. Constraints
    # Constraint A: Exactly K items must be chosen
    prob += pulp.lpSum([x[i] for i in range(len(valid_foods))]) == k, "Pick_Exactly_K"
    
    # Constraint B: Combined calories must not exceed max_calories
    prob += pulp.lpSum([x[i] * valid_foods[i][2] for i in range(len(valid_foods))]) <= max_calories, "Max_Calories"

    # 6. Solve the problem silently
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    # 7. Extract the winning foods
    if pulp.LpStatus[prob.status] == 'Optimal':
        chosen = [valid_foods[i] for i in range(len(valid_foods)) if x[i].varValue == 1.0]
        return chosen
    else:
        return None

def compare_ilp_vs_greedy(graph, foods, goal, max_calories, k=3):
    print(f"\n--- ALGORITHM COMPARISON: Greedy vs ILP ---")
    print(f"Task: Find {k} foods for '{goal}' under {max_calories} kcal combined.")
    
    # -- THE GREEDY HEURISTIC --
    # Sorts by best path cost, picks top K that individually have low calories
    greedy_picks = []
    current_cals = 0
    total_greedy_cost = 0
    
    # Pre-calculate distances for greedy
    distances = []
    for f in foods:
        d, _ = dijkstra(graph, f.id)
        if goal in d and d[goal] < float('inf'):
            distances.append((d[goal], f))
    distances.sort(key=lambda x: x[0]) # Sort by shortest path
    
    for cost, f in distances:
        kcal = f.nutrients.get("energy-kcal", float('inf'))
        # Heuristic shortcut: Only pick if adding it doesn't break the global limit
        if current_cals + kcal <= max_calories and len(greedy_picks) < k:
            greedy_picks.append((f, cost, kcal))
            current_cals += kcal
            total_greedy_cost += cost
            
    print("\n1. Greedy Heuristic Solution:")
    if len(greedy_picks) == k:
        for f, cost, kcal in greedy_picks:
            print(f"  - {f.name[:30]} | Cost: {cost:.2f} | Kcal: {kcal:.0f}")
        print(f"  >> Total Cost: {total_greedy_cost:.2f} | Total Kcal: {current_cals:.0f}")
    else:
        print("  ❌ Greedy failed to find a valid combination. It got stuck in a local minimum!")

    # -- THE OPTIMAL ILP --
    print("\n2. Global Optimal Solution (PuLP ILP):")
    optimal_picks = optimal_recommend_ilp(graph, foods, goal, max_calories, k)
    if optimal_picks:
        total_opt_cost = sum(cost for _, cost, _ in optimal_picks)
        total_opt_cal = sum(kcal for _, _, kcal in optimal_picks)
        for f, cost, kcal in optimal_picks:
             print(f"  - {f.name[:30]} | Cost: {cost:.2f} | Kcal: {kcal:.0f}")
        print(f"  >> Total Cost: {total_opt_cost:.2f} | Total Kcal: {total_opt_cal:.0f}")
    else:
        print("  ❌ ILP failed. The constraints are mathematically impossible.")