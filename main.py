"""
main.py
-------
Command Line Interface for the FeedForward Nutritional Knowledge Graph.
"""
import argparse
import time
from graph.build_graph import load_foods, load_goal_edges, build_graph
from app.query_engine import foods_for_goal, explain
from graph.algorithms import cosine_similarity
from app.recommender import greedy_recommend, compare
from app.analytics import build_nx_graph, run_centrality_analysis, run_community_detection, plot_graph
from app.meal_optimiser import compare_ilp_vs_greedy

def build_parser():
    p = argparse.ArgumentParser(description="FeedForward nutritional knowledge graph")
    p.add_argument("--goal", type=str, help="Nutritional goal (e.g., iron_support, recovery)")
    p.add_argument("--explain", type=str, help="Food name to explain the path to a goal")
    p.add_argument("--similar", type=str, help="Food name to find nutritionally similar foods")
    p.add_argument("--constraint", type=str, help="Constraint filter (e.g., vegetarian, low_sugar)")
    p.add_argument("--compare", action="store_true", help="Compare greedy heuristic vs baseline")
    p.add_argument("--advanced", action="store_true", help="Run advanced analytics (Centrality, Clustering, ILP)")
    p.add_argument("--runs", type=int, default=100, help="Number of runs for baseline comparison to reduce variance")
    return p

def find_food_by_name(foods, name):
    # Improved to allow partial matches (e.g., typing "Oats" finds "Rolled Oats")
    for food in foods:
        if name.lower() in food.name.lower():
            return food
    return None

def cmd_goal(g, goal):
    print(f"\nEvaluating top foods for goal: '{goal}'...\n")
    # Using the fast backward-traversal from query_engine.py
    print(foods_for_goal(g, goal, top_k=5))

def cmd_explain(foods, g, food_name, goal):
    food = find_food_by_name(foods, food_name)
    if not food:
        print(f"Food containing '{food_name}' not found")
        return
    print(f"\nExplaining paths from '{food.name}' to '{goal}'...\n")
    # Pass the 'food' object directly
    print(explain(g, food, goal, k=3))

def cmd_similar(foods, food_name):
    food = find_food_by_name(foods, food_name)
    if not food:
        print(f"Food containing '{food_name}' not found")
        return
        
    results = []
    for other in foods:
        if other.id != food.id:
            sim = cosine_similarity(food.nutrients, other.nutrients)
            results.append((sim, other))
            
    results.sort(key=lambda x: x[0], reverse=True)
    
    print(f"\nFoods similar to '{food.name}':\n")
    for sim, other in results[:5]:
        print(f"  {other.name}: {sim:.3f}")

def cmd_recommend(foods, g, goal, constraint):
    print(f"\nTop Foods for '{goal}' with constraint '{constraint}':\n")
    # Wrapped constraint in a list because greedy_recommend expects a list
    results = greedy_recommend(g, foods, goal, [constraint], k=5)
    
    if not results:
        print("  No Foods match these constraints.")
        return
        
    for dist, food in results:
        print(f"  {dist:.3f} | {food.name}")

def cmd_compare(foods, g, goal, constraint, runs):
    print(f"\n Running Heuristic Comparison for '{goal}' (Constraint: '{constraint}')...")
    g_avg, g_rel, r_avg, r_rel = compare(g, foods, goal, [constraint], runs=runs)
    print(f"   Greedy Recommender -> Avg Cost: {g_avg:.3f} | Relevance: {g_rel:.1%}")
    print(f"   Random Baseline    -> Avg Cost: {r_avg:.3f} | Relevance: {r_rel:.1%}")

def main():
    args = build_parser().parse_args()
    
    print(" Loading data and building graph...")
    start_time = time.time()
    foods = load_foods()
    goal_edges = load_goal_edges()
    g = build_graph(foods, goal_edges)
    print(f" Graph built in {time.time() - start_time:.3f} seconds.\n")

    if args.advanced:
        print(" RUNNING ADVANCED REPORTING ANALYTICS ")
        nx_graph = build_nx_graph(g)
        run_centrality_analysis(nx_graph)
        run_community_detection(nx_graph)
        plot_graph(nx_graph)
        # Tests the ILP Meal Optimizer (Finding 3 foods for energy under 400 kcal)
        compare_ilp_vs_greedy(g, foods, goal="energy", max_calories=400, k=3)
        return # Exit after running analytics

    if args.similar:
        cmd_similar(foods, args.similar)
    elif args.explain and args.goal:
        cmd_explain(foods, g, args.explain, args.goal)
    elif args.compare and args.goal and args.constraint:
        cmd_compare(foods, g, args.goal, args.constraint, args.runs)
    elif args.goal and args.constraint:
        cmd_recommend(foods, g, args.goal, args.constraint)
    elif args.goal:
        cmd_goal(g, args.goal)
    else:
        build_parser().print_help()

if __name__ == "__main__":
    main()