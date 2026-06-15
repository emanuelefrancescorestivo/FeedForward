import heapq  
import math

def dijkstra(graph, source):
    dist = {}
    pred = {}

    for node in graph.adj:
        dist[node] = float("inf")
        pred[node] = None
    
    dist[source] = 0

    heap = [(0, source)]
    visited = set()

    while heap:
        cost, node = heapq.heappop(heap)

        if node in visited:
            continue
        visited.add(node)

        for neighbour, weight in graph.neighbours(node):
            new_cost = cost + weight
            if new_cost < dist[neighbour]:
                dist[neighbour] = new_cost
                pred[neighbour] = node
                heapq.heappush(heap, (new_cost, neighbour))
    return dist,pred


def reconstruct_path(predecessors, source, target):
    path = []
    current = target

    while current is not None:
        path.append(current)
        current = predecessors[current] #?

    return path[::-1]

def cosine_similarity(vec_a, vec_b):
    #vectors are dictionaries {nutrient: quantity}

    #union of all nutrients
    all_nutrients = set(vec_a.keys()) | set(vec_b.keys())

    #compute dot product
    dot = sum(vec_a.get(n, 0) * vec_b.get(n, 0) for n in all_nutrients)

    #compute magnitude of A
    mag_a = math.sqrt(sum(vec_a.get(n,0) ** 2 for n in all_nutrients))
    #compute magnitude of b
    mag_b = math.sqrt(sum(vec_b.get(n,0) ** 2 for n in all_nutrients))

    #avoid divisionbyzeroError
    if mag_a == 0 or mag_b == 0:
        return 0.0
    
    return dot / (mag_a * mag_b)

def dijkstra_blocked(graph, source, blocked_edges):
    #it's basically dijkstra but it ignores the edges in blocked_edges :)
    dist, pred = {}, {}
    for node in graph.adj:
        dist[node] = float("inf")
        pred[node] = None
    dist[source] = 0
    heap = [(0, source)]
    visited = set()
    while heap:
        cost, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        for neighbour, weight in graph.neighbours(node):
            if (node, neighbour) in blocked_edges: # skip prohibited edges
                continue
            new_cost = cost + weight
            if new_cost < dist[neighbour]:
                dist[neighbour] = new_cost
                pred[neighbour] = node
                heapq.heappush(heap, (new_cost, neighbour))
    return dist, pred


def k_shortest_paths(graph, source, target, k):
    #returns up to k shortest paths from source to target, ordered by cost
    # 1) find p1 using our original dijkstra
    dist, pred = dijkstra(graph, source)
    if dist.get(target, float("inf")) == float("inf"):
        return []               # no path
    p1 = reconstruct_path(pred, source, target)
    paths = [(dist[target], p1)]            # list of (cost, path)

    candidates = []                 # heap of candidates (cost, path)

    for i in range(1, k):           #we search P2, P3, ..., Pk
        prev_path = paths[-1][1]

        #for each note in the previous path (but the last), we try as SPUR NODE
        for j in range(len(prev_path) - 1):
            spur_node = prev_path[j]
            root_path = prev_path[:j + 1] # from source until spur_node(indluded)

            # prohibit the "next" edge in all already-found paths that have the same root_path so not to have duplicates
            blocked = set()
            for cost_p, p in paths:
                if p[:j + 1] == root_path and len(p) > j + 1:
                    blocked.add((p[j], p[j+1]))
            
            # Dijkstra from spur_node to target avoiding prohibited edges
            d, pr = dijkstra_blocked(graph, spur_node, blocked)
            if d.get(target, float("inf")) == float("inf"):
                continue # no useful deviations from here, logically

            spur_path = reconstruct_path(pr, spur_node, target)
            total_path = root_path[:1] + spur_path[1:] # merge : root (no spur) + spur

            # total cost = cost of root + cost of spur (=d[target])
            # compute the root cost summing the weight of the edges
            root_cost = sum(
                weight
                for i in range(len(root_path) - 1)
                for neighbour, weight in graph.adj[root_path[i]]
                if neighbour == root_path[i + 1]
            )
            total_cost = root_cost + d[target]

            #add to candidates if not present
            if not any(p == total_path for _, p in candidates):
                candidates.append((total_cost, total_path))

        if not candidates:
            break                       # no more alternatives

        #choose the candidate with min_cost -> becomes next P
        candidates.sort(key=lambda x: x[0])
        next_path = candidates.pop(0)
        paths.append(next_path)
    
    return paths