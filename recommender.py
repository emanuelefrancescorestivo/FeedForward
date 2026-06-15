import unicodedata
import random
from graph.algorithms import dijkstra

# thresholds for 100g
SUGAR_LOW = 5.0
PROTEIN_HIGH = 15.0

# categories to exclude (substrings, lowercase) - our idea
MEAT_FISH = ["meat","fish","beef","pork","chicken","viande","poisson","boeuf","porc",
             "thon","tuna","atun","saumon","salmon","sardine","maquereau","anchois",
             "morue","cod","cabillaud","colin","merlu","hareng","crabe","crevette",
             "surimi","jambon","ham","poulet","dinde","turkey","lamb","agneau","veau"]
DAIRY = ["dairy", "milk", "cheese", "yogurt", "lait", "fromage", "yaourt", "skyr"]

def _normalise(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) !="Mn")

def satisfies(food, constraint):
    text = _normalise(food.name + " " + food.category).lower() #search in name and category without accents
    if constraint == "low_sugar":
        return food.nutrients.get("sugars", 0) < SUGAR_LOW
    if constraint == "high_protein":
        return food.nutrients.get("proteins", 0) > PROTEIN_HIGH
    if constraint == "vegetarian":
        return not any(m in text for m in MEAT_FISH)
    if constraint == "vegan":
        return not any(x in text for x in MEAT_FISH + DAIRY)
    return True  # no constraint = no filter

def filter_candidates(foods, constraints):
    return [f for f in foods if all(satisfies(f, c) for c in constraints)]

def greedy_recommend(graph, foods, goal, constraints, k=5):
    candidates = filter_candidates(foods, constraints)
    scored =[]
    for f in candidates:
        dist, pred = dijkstra(graph, f.id)
        if goal in dist and dist[goal] < float("inf"):
            scored.append((dist[goal], f))
    scored.sort(key=lambda x: x[0], reverse=False)
    return scored[:k]

def random_baseline(foods, constraints, k):
    candidates = filter_candidates(foods, constraints)
    return random.sample(candidates, min(k, len(candidates)))

def pick_stats(graph, picks, goal):
    dists = []
    for f in picks:
        d, _ = dijkstra(graph, f.id)
        dist_to_goal = d.get(goal,float("inf"))
        if dist_to_goal < float("inf"):
            dists.append(dist_to_goal)
    avg = sum(dists) / len(dists) if dists else float("inf")
    relevance = len(dists) / len(picks) if picks else 0 #fraction of foods with a path to goal
    return avg, relevance

def compare(graph, foods, goal, constraints, k=5, runs=20):
    # 1st the heuristic: top k foods for greedy_recommend
    greedy_picks = [f for _, f in greedy_recommend(graph, foods, goal, constraints, k)]
    g_avg, g_rel = pick_stats(graph, greedy_picks, goal)

    # --- NEW: Print concrete examples to the console ---
    print(f"\n   [CONCRETE EXAMPLE]")
    print(f"   Greedy Selected : {', '.join([f.name for f in greedy_picks])}")

    # 2nd the casual baseline, repeated 'runs' times
    r_avgs, r_rels = [], []
    for i in range(runs):
        random_picks = random_baseline(foods, constraints, k)
        
        # --- NEW: Print the first random run to compare ---
        if i == 0:
            print(f"   Random Selected : {', '.join([f.name for f in random_picks])}\n")
            
        avg, rel = pick_stats(graph, random_picks, goal)
        if avg < float("inf"):
            r_avgs.append(avg)
        r_rels.append(rel)
        
    r_avg = sum(r_avgs) / len(r_avgs) if r_avgs else float("inf")
    r_rel = sum(r_rels) / len(r_rels)
    return g_avg, g_rel, r_avg, r_rel