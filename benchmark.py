import time
from graph.build_graph import load_foods, load_goal_edges, build_graph
from graph.algorithms import dijkstra
from app.recommender import greedy_recommend

#1st build the graph 
t0 = time.perf_counter()
foods = load_foods()
goal_edges = load_goal_edges()
g = build_graph(foods, goal_edges)
t1 = time.perf_counter()
print(f"Graph build: {(t1-t0) * 1000:7.1f} ms ({len(g.adj)} nodes, {sum(len(v) for v in g.adj.values())} edges)")

#2nd a single Dijkstra query
t0 = time.perf_counter()
dijkstra(g, foods[0].id)
t1 = time.perf_counter()
print(f"Single Dijkstra: {(t1-t0) * 1000:7.2f} ms")

#3rd a query by the recommender (so Dijkstra on all candiadtes)
t0 = time.perf_counter()
greedy_recommend(g, foods, "recovery", ["high protein"], 5)
t1 = time.perf_counter()
print(f"Recommend query: {(t1-t0) *1000:7.1f} ms")