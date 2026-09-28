"""
engine/algorithms.py
====================
Graph algorithms. The forward Dijkstra, blocked Dijkstra, Yen's k-shortest
paths and cosine similarity are carried over from the university project
(validated on a 5-node toy graph). Added here:

  * ``dijkstra_reverse`` — runs Dijkstra over the reversed graph, so a single
    pass from a goal node yields the shortest path from *every* food to that
    goal. This is the O(1)-per-query recommendation fix.

Complexity: Dijkstra is O((V + E) log V); Yen's is O(k · V · (V + E) log V).
"""
from __future__ import annotations

import heapq
import math

from .graph import FeedForwardGraph


# ---------------------------------------------------------------------------
# Dijkstra (forward and reverse)
# ---------------------------------------------------------------------------
def dijkstra(graph: FeedForwardGraph, source: str):
    dist = {node: math.inf for node in graph.adj}
    pred: dict[str, str | None] = {node: None for node in graph.adj}
    dist[source] = 0.0
    heap: list[tuple[float, str]] = [(0.0, source)]
    visited: set[str] = set()

    while heap:
        cost, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        for neighbour, weight in graph.neighbours(node):
            nc = cost + weight
            if nc < dist.get(neighbour, math.inf):
                dist[neighbour] = nc
                pred[neighbour] = node
                heapq.heappush(heap, (nc, neighbour))
    return dist, pred


def dijkstra_reverse(graph: FeedForwardGraph, source: str):
    """
    Dijkstra over the REVERSED graph. Starting from a goal node, this computes
    the shortest distance from every other node *to* that goal in the forward
    graph — i.e. from each food to the goal — in a single pass.
    """
    all_nodes = set(graph.adj) | set(graph.radj)
    dist = {node: math.inf for node in all_nodes}
    pred: dict[str, str | None] = {node: None for node in all_nodes}
    dist[source] = 0.0
    heap: list[tuple[float, str]] = [(0.0, source)]
    visited: set[str] = set()

    while heap:
        cost, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        for neighbour, weight in graph.reverse_neighbours(node):
            nc = cost + weight
            if nc < dist.get(neighbour, math.inf):
                dist[neighbour] = nc
                pred[neighbour] = node
                heapq.heappush(heap, (nc, neighbour))
    return dist, pred


def reconstruct_path(pred: dict[str, str | None], source: str, target: str) -> list[str]:
    path: list[str] = []
    current: str | None = target
    while current is not None:
        path.append(current)
        if current == source:
            break
        current = pred.get(current)
    return path[::-1]


def reconstruct_path_reverse(pred: dict[str, str | None], goal: str,
                             food: str) -> list[str]:
    """
    Reconstruct a food -> ... -> goal path from a reverse-Dijkstra predecessor
    map (which points from goal outward toward foods).
    """
    path: list[str] = []
    current: str | None = food
    while current is not None:
        path.append(current)
        if current == goal:
            break
        current = pred.get(current)
    return path  # already food -> goal order


# ---------------------------------------------------------------------------
# Cosine similarity over nutrient vectors
# ---------------------------------------------------------------------------
def cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    keys = set(vec_a) | set(vec_b)
    dot = sum(vec_a.get(n, 0.0) * vec_b.get(n, 0.0) for n in keys)
    mag_a = math.sqrt(sum(vec_a.get(n, 0.0) ** 2 for n in keys))
    mag_b = math.sqrt(sum(vec_b.get(n, 0.0) ** 2 for n in keys))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Yen's k-shortest paths (for richer, multi-path explanations)
# ---------------------------------------------------------------------------
def _dijkstra_blocked(graph: FeedForwardGraph, source: str,
                      blocked_edges: set[tuple[str, str]]):
    dist = {node: math.inf for node in graph.adj}
    pred: dict[str, str | None] = {node: None for node in graph.adj}
    dist[source] = 0.0
    heap: list[tuple[float, str]] = [(0.0, source)]
    visited: set[str] = set()
    while heap:
        cost, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        for neighbour, weight in graph.neighbours(node):
            if (node, neighbour) in blocked_edges:
                continue
            nc = cost + weight
            if nc < dist.get(neighbour, math.inf):
                dist[neighbour] = nc
                pred[neighbour] = node
                heapq.heappush(heap, (nc, neighbour))
    return dist, pred


def k_shortest_paths(graph: FeedForwardGraph, source: str, target: str, k: int):
    dist, pred = dijkstra(graph, source)
    if dist.get(target, math.inf) == math.inf:
        return []
    p1 = reconstruct_path(pred, source, target)
    paths: list[tuple[float, list[str]]] = [(dist[target], p1)]
    candidates: list[tuple[float, list[str]]] = []

    for _ in range(1, k):
        prev_path = paths[-1][1]
        for j in range(len(prev_path) - 1):
            spur_node = prev_path[j]
            root_path = prev_path[: j + 1]
            blocked: set[tuple[str, str]] = set()
            for _cost, p in paths:
                if p[: j + 1] == root_path and len(p) > j + 1:
                    blocked.add((p[j], p[j + 1]))
            d, pr = _dijkstra_blocked(graph, spur_node, blocked)
            if d.get(target, math.inf) == math.inf:
                continue
            spur_path = reconstruct_path(pr, spur_node, target)
            total_path = root_path[:-1] + spur_path
            root_cost = sum(
                weight
                for i in range(len(root_path) - 1)
                for neighbour, weight in graph.adj[root_path[i]]
                if neighbour == root_path[i + 1]
            )
            total_cost = root_cost + d[target]
            if not any(p == total_path for _, p in candidates):
                candidates.append((total_cost, total_path))
        if not candidates:
            break
        candidates.sort(key=lambda x: x[0])
        paths.append(candidates.pop(0))

    return paths
